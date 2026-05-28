/**
 * AudioQueue - F6: Progressive audio chunk playback for streaming TTS
 *
 * Features:
 * - Queue-based playback (enqueue chunks as they arrive)
 * - Pre-decoding: chunks are decoded as they arrive, not when played
 * - Seamless gapless playback between chunks
 * - Immediate stop for barge-in support
 * - Progress tracking
 * - Lip-sync integration via LipSyncController
 */

import { base64ToArrayBuffer } from './audio';
import { get } from 'svelte/store';
import { lipSyncController } from '$lib/stores/lipSync';

export interface AudioChunk {
  audioData: string; // base64 encoded
  chunkIndex: number;
  isLast: boolean;
  turnId: string;
}

// Internal chunk with pre-decoded buffer
interface DecodedChunk {
  chunk: AudioChunk;
  bufferPromise: Promise<AudioBuffer>;
  decoded: boolean;
}

export interface AudioQueueCallbacks {
  onPlaybackStart?: () => void;
  onPlaybackEnd?: () => void;
  onChunkPlayed?: (chunkIndex: number) => void;
  onError?: (error: Error) => void;
}

export class AudioQueue {
  private audioContext: AudioContext;
  private chunks: DecodedChunk[] = [];
  private isPlaying = false;
  private currentSource: AudioBufferSourceNode | null = null;
  private currentTurnId: string | null = null;
  private callbacks: AudioQueueCallbacks = {};

  // Track playback state
  private chunksPlayed = 0;
  private totalChunksReceived = 0;
  private playbackStartTime: number | null = null;

  constructor(audioContext: AudioContext, callbacks?: AudioQueueCallbacks) {
    this.audioContext = audioContext;
    if (callbacks) {
      this.callbacks = callbacks;
    }
  }

  /**
   * Pre-decode audio chunk in background
   */
  private preDecodeChunk(chunk: AudioChunk): Promise<AudioBuffer> {
    const arrayBuffer = base64ToArrayBuffer(chunk.audioData);
    // decodeAudioData returns a promise - this happens in background
    return this.audioContext.decodeAudioData(arrayBuffer);
  }

  /**
   * Update callbacks
   */
  setCallbacks(callbacks: AudioQueueCallbacks): void {
    this.callbacks = callbacks;
  }

  /**
   * Enqueue an audio chunk for playback (with pre-decoding)
   */
  async enqueue(chunk: AudioChunk): Promise<void> {
    // If new turn, clear previous queue
    if (this.currentTurnId && this.currentTurnId !== chunk.turnId) {
      console.log(`[AudioQueue] New turn ${chunk.turnId}, clearing previous`);
      this.clear();
    }

    this.currentTurnId = chunk.turnId;
    this.totalChunksReceived++;

    // Pre-decode chunk immediately (in background)
    const bufferPromise = this.preDecodeChunk(chunk);

    this.chunks.push({
      chunk,
      bufferPromise,
      decoded: false,
    });

    console.log(
      `[AudioQueue] Enqueued chunk ${chunk.chunkIndex} for turn ${chunk.turnId}, queue size: ${this.chunks.length} (pre-decoding)`
    );

    // Start playback if not already playing
    if (!this.isPlaying) {
      await this.playNext();
    }
  }

  /**
   * Play next chunk in queue (using pre-decoded buffers)
   */
  private async playNext(): Promise<void> {
    if (this.chunks.length === 0) {
      // Queue empty - playback complete
      if (this.isPlaying) {
        this.isPlaying = false;
        const duration = this.playbackStartTime ? Date.now() - this.playbackStartTime : 0;
        console.log(`[AudioQueue] Playback complete, ${this.chunksPlayed} chunks, ${duration}ms`);
        this.callbacks.onPlaybackEnd?.();
      }
      return;
    }

    const decodedChunk = this.chunks.shift()!;
    const { chunk, bufferPromise } = decodedChunk;

    // Mark as playing on first chunk
    if (!this.isPlaying) {
      this.isPlaying = true;
      this.playbackStartTime = Date.now();
      console.log(`[AudioQueue] Starting playback for turn ${chunk.turnId}`);
      this.callbacks.onPlaybackStart?.();
    }

    try {
      // Ensure AudioContext is running
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      // Wait for pre-decoded buffer (should be ready or almost ready)
      const decodeStart = performance.now();
      const audioBuffer = await bufferPromise;
      const decodeWait = performance.now() - decodeStart;

      if (decodeWait > 10) {
        console.log(`[AudioQueue] Waited ${decodeWait.toFixed(1)}ms for pre-decode`);
      }

      // Create source and play
      this.currentSource = this.audioContext.createBufferSource();
      this.currentSource.buffer = audioBuffer;

      // Connect to lip-sync analyser if available
      const lipSync = get(lipSyncController);
      if (lipSync) {
        lipSync.connectSource(this.currentSource, this.audioContext.destination);
      } else {
        // No lip-sync, connect directly
        this.currentSource.connect(this.audioContext.destination);
      }

      // Handle chunk completion
      this.currentSource.onended = () => {
        this.chunksPlayed++;
        this.currentSource = null;
        this.callbacks.onChunkPlayed?.(chunk.chunkIndex);

        // Play next chunk
        this.playNext();
      };

      this.currentSource.start();

      console.log(
        `[AudioQueue] Playing chunk ${chunk.chunkIndex}, buffer duration: ${audioBuffer.duration.toFixed(2)}s`
      );
    } catch (error) {
      console.error(`[AudioQueue] Error playing chunk ${chunk.chunkIndex}:`, error);
      this.callbacks.onError?.(error as Error);

      // Try to continue with next chunk
      this.currentSource = null;
      await this.playNext();
    }
  }

  /**
   * Stop playback immediately (for barge-in)
   */
  stop(): void {
    console.log(`[AudioQueue] Stop requested, clearing queue`);

    // Stop current playback
    if (this.currentSource) {
      try {
        this.currentSource.stop();
        this.currentSource.disconnect();
      } catch {
        // Already stopped
      }
      this.currentSource = null;
    }

    // Clear queue
    this.chunks = [];
    this.isPlaying = false;

    // Notify listeners
    this.callbacks.onPlaybackEnd?.();
  }

  /**
   * Clear queue without stopping current playback
   */
  clear(): void {
    this.chunks = [];
    this.chunksPlayed = 0;
    this.totalChunksReceived = 0;
    this.playbackStartTime = null;
    this.currentTurnId = null;
  }

  /**
   * Check if currently playing
   */
  get playing(): boolean {
    return this.isPlaying;
  }

  /**
   * Get queue status
   */
  get status(): { playing: boolean; queued: number; played: number; turnId: string | null } {
    return {
      playing: this.isPlaying,
      queued: this.chunks.length,
      played: this.chunksPlayed,
      turnId: this.currentTurnId,
    };
  }
}

/**
 * Create AudioQueue instance
 */
export function createAudioQueue(audioContext: AudioContext, callbacks?: AudioQueueCallbacks): AudioQueue {
  return new AudioQueue(audioContext, callbacks);
}
