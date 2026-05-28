<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { uiState, messages } from '$lib/stores/websocket';
  import { MessageType, UIState } from '@ai-kiosk/shared-types';
  import {
    audioState,
    initAudio,
    cleanupAudio,
    startRecording,
    stopRecording,
    handleTTSChunk,
    handleStopAudio,
    stopPlayback,
  } from '$lib/stores/audio';

  // Prop to control when to initialize (after user interaction)
  export let shouldInit = false;

  // Track UI state for automatic recording control
  let wasListening = false;
  let unsubscribe: (() => void) | null = null;
  let audioInitialized = false;

  // Initialize audio when shouldInit becomes true (after user click)
  $: if (shouldInit && !audioInitialized) {
    audioInitialized = true;
    initAudio();
  }

  onMount(() => {
    // Subscribe to incoming messages for TTS chunks and control messages
    unsubscribe = messages.subscribe((msgs) => {
      const latest = msgs[msgs.length - 1];
      if (!latest) return;

      if (latest.type === MessageType.TTS_CHUNK) {
        const { audio_data, chunk_index, total_chunks, turn_id, is_last } = latest.payload;
        handleTTSChunk(audio_data, chunk_index, total_chunks || 0, turn_id, is_last || false);
      } else if (latest.type === MessageType.CONTROL_STOP_AUDIO) {
        handleStopAudio();
      } else if (latest.type === 'vad.end_of_speech') {
        // VAD detected end of speech - stop recording immediately
        console.log('[AudioCapture] VAD end of speech detected');
        if ($audioState.recording) {
          stopRecording();
        }
      }
    });
  });

  onDestroy(() => {
    if (unsubscribe) {
      unsubscribe();
    }
    cleanupAudio();
  });

  // Auto-start/stop recording based on UI state
  // Keep recording during SPEAKING to enable barge-in detection via backend
  // Also react to audioState.micStream changes to handle race condition
  $: {
    const currentState = $uiState as UIState;
    const shouldRecord = currentState === UIState.LISTENING || currentState === UIState.SPEAKING;
    const hasMicStream = $audioState.micStream !== null;

    if (shouldRecord && !wasListening) {
      // Transitioned to listening or speaking state - start recording
      wasListening = true;
      if (hasMicStream) {
        startRecording();
      } else {
        console.log('[AudioCapture] Waiting for mic stream to initialize...');
      }
    } else if (!shouldRecord && wasListening) {
      wasListening = false;
      // Stop recording when leaving listening/speaking state
      if ($audioState.recording) {
        stopRecording();
      }
    } else if (shouldRecord && wasListening && hasMicStream && !$audioState.recording) {
      // FIX: If we should be recording but aren't (due to race condition), start now
      console.log('[AudioCapture] Mic stream ready, starting recording...');
      startRecording();
    }

    // Note: Barge-in detection is handled by the backend (speech service)
    // which analyzes audio energy and sends control.stop_audio when detected
  }
</script>

{#if $audioState.error}
  <div class="audio-error">
    {#if $audioState.permissionDenied}
      <p>Permiso de microfono denegado</p>
      <p class="hint">Por favor, permite el acceso al microfono</p>
    {:else}
      <p>Error audio: {$audioState.error}</p>
    {/if}
  </div>
{/if}

{#if $audioState.recording}
  <div class="recording-indicator">
    <span class="pulse-dot"></span>
    <span>Grabando...</span>
  </div>
{/if}

{#if $audioState.playing}
  <div class="playing-indicator">
    <span class="speaker-icon">🔊</span>
    <span>Reproduciendo...</span>
  </div>
{/if}

<style>
  .audio-error {
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(239, 68, 68, 0.9);
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    text-align: center;
    z-index: 100;
  }

  .audio-error p {
    margin: 0;
  }

  .audio-error .hint {
    font-size: 0.875rem;
    opacity: 0.8;
    margin-top: 4px;
  }

  .recording-indicator,
  .playing-indicator {
    position: fixed;
    top: 20px;
    right: 20px;
    background: rgba(0, 0, 0, 0.7);
    color: white;
    padding: 8px 16px;
    border-radius: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
    z-index: 100;
  }

  .recording-indicator {
    background: rgba(239, 68, 68, 0.9);
  }

  .playing-indicator {
    top: 60px;
    background: rgba(59, 130, 246, 0.9);
  }

  .pulse-dot {
    width: 10px;
    height: 10px;
    background-color: white;
    border-radius: 50%;
    animation: pulse 1s infinite;
  }

  .speaker-icon {
    font-size: 1rem;
  }

  @keyframes pulse {
    0%,
    100% {
      transform: scale(1);
      opacity: 1;
    }
    50% {
      transform: scale(1.2);
      opacity: 0.7;
    }
  }
</style>
