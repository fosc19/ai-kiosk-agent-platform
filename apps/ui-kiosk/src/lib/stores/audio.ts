import { writable, get } from 'svelte/store';
import { MessageType } from '@ai-kiosk/shared-types';
import { send, wsState } from './websocket';
import { session, generateTurnId } from './session';
import {
  initMicrophone,
  createAudioContext,
  encodeWav,
  arrayBufferToBase64,
  SAMPLE_RATE,
  downsampleBuffer,
} from '$lib/utils/audio';
import { AudioQueue, createAudioQueue } from '$lib/utils/audioQueue';

// How often to send audio chunks to backend for VAD (ms)
const CHUNK_INTERVAL_MS = 250;

interface AudioState {
  micStream: MediaStream | null;
  recording: boolean;
  playing: boolean;
  error: string | null;
  permissionDenied: boolean;
}

interface AudioProcessor {
  source: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode;
  chunks: Float32Array[];
  chunkInterval: ReturnType<typeof setInterval> | null;
  turnId: string;
  chunkIndex: number;
}

let audioContext: AudioContext | null = null;
let audioQueue: AudioQueue | null = null;
let audioProcessor: AudioProcessor | null = null;
let currentTurnId: string | null = null;

export const audioState = writable<AudioState>({
  micStream: null,
  recording: false,
  playing: false,
  error: null,
  permissionDenied: false,
});

/**
 * Initialize audio system (microphone + AudioContext)
 */
export async function initAudio(): Promise<boolean> {
  try {
    console.log('[Audio] Initializing audio system...');

    // Create AudioContext
    audioContext = createAudioContext();

    // Resume AudioContext if suspended (browser autoplay policy)
    if (audioContext.state === 'suspended') {
      await audioContext.resume();
    }

    // Initialize AudioQueue for TTS playback with callbacks
    audioQueue = createAudioQueue(audioContext, {
      onPlaybackStart: () => {
        console.log('[Audio] Playback started');
        audioState.update((s) => ({ ...s, playing: true }));
      },
      onPlaybackEnd: () => {
        console.log('[Audio] Playback complete');
        audioState.update((s) => ({ ...s, playing: false }));
        // Notify orchestrator that playback is complete
        if (currentTurnId) {
          send({
            type: MessageType.PLAYBACK_COMPLETE,
            payload: { turn_id: currentTurnId },
          });
          currentTurnId = null;
        }
      },
      onChunkPlayed: (chunkIndex) => {
        console.log(`[Audio] Chunk ${chunkIndex} played`);
      },
      onError: (error) => {
        console.error('[Audio] Playback error:', error);
      },
    });

    // Request microphone
    const stream = await initMicrophone();

    if (!stream) {
      audioState.update((s) => ({
        ...s,
        error: 'Microphone access denied',
        permissionDenied: true,
      }));
      return false;
    }

    audioState.set({
      micStream: stream,
      recording: false,
      playing: false,
      error: null,
      permissionDenied: false,
    });

    console.log('[Audio] Audio system initialized');
    return true;
  } catch (error) {
    const err = error as Error;
    console.error('[Audio] Init error:', err.message);
    audioState.update((s) => ({ ...s, error: err.message }));
    return false;
  }
}

/**
 * Start recording audio from microphone with streaming VAD
 */
export function startRecording(): void {
  const state = get(audioState);
  if (!state.micStream || state.recording) {
    console.warn('[Audio] Cannot start recording: no stream or already recording');
    return;
  }

  console.log('[Audio] Starting recording with streaming VAD...');

  if (!audioContext) {
    audioContext = createAudioContext();
  }

  // Resume context if needed
  if (audioContext.state === 'suspended') {
    audioContext.resume();
  }

  const source = audioContext.createMediaStreamSource(state.micStream);

  // LOG: Verificar sample rate real y configuración de AEC
  console.log('[Audio] AudioContext sample rate:', audioContext.sampleRate);
  const track = state.micStream.getAudioTracks()[0];
  if (track) {
    const settings = track.getSettings();
    console.log('[Audio] Track settings:', {
      sampleRate: settings.sampleRate,
      echoCancellation: settings.echoCancellation,
      noiseSuppression: settings.noiseSuppression,
      autoGainControl: settings.autoGainControl,
    });
  }

  const processor = audioContext.createScriptProcessor(4096, 1, 1);

  const chunks: Float32Array[] = [];
  const turnId = generateTurnId();

  let chunkCount = 0;
  processor.onaudioprocess = (e) => {
    const inputData = e.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(inputData));
    chunkCount++;

    // Log every 10 chunks to verify it's working
    if (chunkCount % 10 === 0) {
      console.log(`[Audio] Captured ${chunkCount} audio chunks`);
    }
  };

  source.connect(processor);

  // FIX: ScriptProcessor MUST be connected to destination for onaudioprocess to fire
  // But to avoid echo/feedback, connect through a GainNode with 0 volume
  const silentGain = audioContext.createGain();
  silentGain.gain.value = 0; // Silent - no audio output
  processor.connect(silentGain);
  silentGain.connect(audioContext.destination);

  console.log('[Audio] ScriptProcessor connected (silently) to capture audio');

  // FIX: Create audioProcessor BEFORE the interval starts
  // This prevents the race condition where interval checks audioProcessor before it's assigned
  audioProcessor = { source, processor, chunks, chunkInterval: null, turnId, chunkIndex: 0 };

  // Send chunks periodically for VAD processing
  const chunkInterval = setInterval(() => {
    const ws = get(wsState);
    if (chunks.length > 0 && ws.connected && audioProcessor) {
      // Combine accumulated chunks
      const totalLength = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
      const combined = new Float32Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        combined.set(chunk, offset);
        offset += chunk.length;
      }

      // Clear chunks for next interval
      chunks.length = 0;

      // Only send if we have meaningful audio
      if (combined.length > 0) {
        const inputSampleRate = audioContext ? audioContext.sampleRate : SAMPLE_RATE;
        const resampled =
          inputSampleRate === SAMPLE_RATE
            ? combined
            : downsampleBuffer(combined, inputSampleRate, SAMPLE_RATE);
        const wavBuffer = encodeWav(resampled, SAMPLE_RATE);
        const base64 = arrayBufferToBase64(wavBuffer);

        const sessionState = get(session);

        console.log(`[Audio] Sending chunk ${audioProcessor!.chunkIndex} (${combined.length} samples)`);

        send({
          type: MessageType.AUDIO_CHUNK,
          payload: {
            session_id: sessionState.session_id || 'unknown',
            turn_id: turnId,
            chunk_data: base64,
            chunk_index: audioProcessor!.chunkIndex,
            sample_rate: SAMPLE_RATE,
          },
        });

        audioProcessor!.chunkIndex++;
      }
    }
  }, CHUNK_INTERVAL_MS);

  // Update with the actual interval reference
  audioProcessor.chunkInterval = chunkInterval;

  audioState.update((s) => ({ ...s, recording: true }));
}

/**
 * Stop recording (streaming VAD handles sending)
 */
export function stopRecording(): void {
  const state = get(audioState);
  if (!state.recording) {
    return;
  }

  console.log('[Audio] Stopping recording...');

  if (audioProcessor) {
    const { source, processor, chunkInterval } = audioProcessor;

    // Stop chunk interval
    if (chunkInterval) {
      clearInterval(chunkInterval);
    }

    // Disconnect nodes
    source.disconnect();
    processor.disconnect();

    console.log(`[Audio] Recording stopped, sent ${audioProcessor.chunkIndex} chunks`);
    audioProcessor = null;
  }

  audioState.update((s) => ({ ...s, recording: false }));
}

/**
 * Handle incoming TTS chunk from VPS (streaming)
 */
export async function handleTTSChunk(
  audioData: string,
  chunkIndex: number,
  totalChunks: number,
  turnId: string,
  isLast: boolean = false
): Promise<void> {
  // Use is_last if provided, otherwise fall back to totalChunks for backwards compatibility
  const isFinalChunk = isLast || (totalChunks > 0 && chunkIndex === totalChunks - 1);
  console.log(`[Audio] Received TTS chunk ${chunkIndex}${isFinalChunk ? ' (last)' : ''} for turn ${turnId}`);

  if (!audioQueue) {
    console.warn('[Audio] AudioQueue not initialized');
    return;
  }

  // Track current turn for playback complete notification
  currentTurnId = turnId;

  // Enqueue chunk for progressive playback
  await audioQueue.enqueue({
    audioData,
    chunkIndex,
    isLast: isFinalChunk,
    turnId,
  });
}

/**
 * Stop audio playback immediately (for barge-in)
 */
export function stopPlayback(): void {
  console.log('[Audio] Stopping playback (barge-in)');

  if (audioQueue) {
    audioQueue.stop();
  }
  currentTurnId = null;

  audioState.update((s) => ({ ...s, playing: false }));

  // Notify VPS
  send({
    type: MessageType.CONTROL_STOP_TTS,
    payload: { reason: 'barge_in' },
  });
}

/**
 * Handle stop_audio control message from VPS
 */
export function handleStopAudio(): void {
  console.log('[Audio] Received stop_audio command');

  if (audioQueue) {
    audioQueue.stop();
  }
  currentTurnId = null;

  audioState.update((s) => ({ ...s, playing: false }));
}

/**
 * Cleanup audio system
 */
export function cleanupAudio(): void {
  console.log('[Audio] Cleaning up...');

  // Stop recording if active
  if (audioProcessor) {
    if (audioProcessor.chunkInterval) {
      clearInterval(audioProcessor.chunkInterval);
    }
    audioProcessor.source.disconnect();
    audioProcessor.processor.disconnect();
    audioProcessor = null;
  }

  // Stop playback
  if (audioQueue) {
    audioQueue.stop();
    audioQueue = null;
  }
  currentTurnId = null;

  // Stop mic stream
  const state = get(audioState);
  if (state.micStream) {
    state.micStream.getTracks().forEach((track) => track.stop());
  }

  // Close audio context
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }

  audioState.set({
    micStream: null,
    recording: false,
    playing: false,
    error: null,
    permissionDenied: false,
  });
}
