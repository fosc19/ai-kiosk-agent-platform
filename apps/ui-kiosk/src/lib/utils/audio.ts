/**
 * Audio utilities for capture and playback
 * - getUserMedia with AEC (echo cancellation)
 * - PCM WAV encoding
 * - Web Audio API for TTS playback
 */

export const SAMPLE_RATE = 16000;
export const CHANNELS = 1;

/**
 * Audio constraints for getUserMedia with AEC
 */
export const AUDIO_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
  // Avoid forcing sampleRate here; Firefox errors if track rate != AudioContext rate.
  // We'll downsample to SAMPLE_RATE before sending to backend.
  channelCount: CHANNELS,
};

/**
 * Request microphone access with AEC enabled
 */
export async function initMicrophone(): Promise<MediaStream | null> {
  try {
    console.log('[Audio] Requesting microphone access...');
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: AUDIO_CONSTRAINTS,
      video: false,
    });
    console.log('[Audio] Microphone access granted');
    return stream;
  } catch (error) {
    const err = error as Error;
    console.error('[Audio] Microphone access denied:', err.message);
    return null;
  }
}

/**
 * Create AudioContext for capture and playback
 */
export function createAudioContext(): AudioContext {
  const AudioContextClass =
    window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  // Use device/default sample rate for compatibility (Firefox).
  return new AudioContextClass();
}

/**
 * Convert Float32Array audio samples to PCM 16-bit WAV format
 */
export function encodeWav(samples: Float32Array, sampleRate: number = SAMPLE_RATE): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  // WAV header
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, CHANNELS, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * CHANNELS * 2, true); // byte rate
  view.setUint16(32, CHANNELS * 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);

  // Convert float samples to 16-bit PCM
  const offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }

  return buffer;
}

/**
 * Downsample a Float32Array buffer to a target sample rate.
 * Simple averaging resampler (good enough for speech VAD/ASR).
 */
export function downsampleBuffer(
  buffer: Float32Array,
  inputSampleRate: number,
  outputSampleRate: number
): Float32Array {
  if (outputSampleRate === inputSampleRate) {
    return buffer;
  }

  const sampleRateRatio = inputSampleRate / outputSampleRate;
  const newLength = Math.round(buffer.length / sampleRateRatio);
  const result = new Float32Array(newLength);

  if (outputSampleRate < inputSampleRate) {
    // Downsample by averaging
    let offsetResult = 0;
    let offsetBuffer = 0;

    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
      let accum = 0;
      let count = 0;

      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i];
        count++;
      }

      result[offsetResult] = count > 0 ? accum / count : 0;
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
  } else {
    // Upsample with linear interpolation
    for (let i = 0; i < result.length; i++) {
      const position = i * sampleRateRatio;
      const index = Math.floor(position);
      const nextIndex = Math.min(index + 1, buffer.length - 1);
      const weight = position - index;
      result[i] = buffer[index] * (1 - weight) + buffer[nextIndex] * weight;
    }
  }

  return result;
}

/**
 * Write string to DataView at offset
 */
function writeString(view: DataView, offset: number, string: string): void {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

/**
 * Convert ArrayBuffer to base64 string
 */
export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Convert base64 string to ArrayBuffer
 */
export function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

/**
 * Decode base64 audio and play it using Web Audio API
 */
export async function playAudioChunk(
  audioContext: AudioContext,
  audioBase64: string,
  onEnded?: () => void
): Promise<AudioBufferSourceNode> {
  const arrayBuffer = base64ToArrayBuffer(audioBase64);
  const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);

  if (onEnded) {
    source.onended = onEnded;
  }

  source.start();
  return source;
}

/**
 * Stop audio playback immediately
 */
export function stopAudioPlayback(source: AudioBufferSourceNode | null): void {
  if (source) {
    try {
      source.stop();
    } catch {
      // Already stopped
    }
  }
}
