<script lang="ts">
  import { onDestroy } from 'svelte';
  import {
    cameraState,
    initCamera,
    stopCamera,
    setVideoElement,
    startFrameCapture,
    stopFrameCapture,
  } from '$lib/stores/camera';

  // Prop to control when to initialize (after user interaction)
  export let shouldInit = false;

  let videoElement: HTMLVideoElement;
  let cameraInitialized = false;

  // Initialize camera when shouldInit becomes true (after user click)
  $: if (shouldInit && !cameraInitialized && videoElement) {
    cameraInitialized = true;
    initCameraWithVideo();
  }

  async function initCameraWithVideo() {
    const stream = await initCamera();

    if (stream && videoElement) {
      videoElement.srcObject = stream;
      setVideoElement(videoElement);

      // Wait for video to be ready, then start capturing
      videoElement.onloadedmetadata = () => {
        videoElement.play();
        startFrameCapture();
      };
    }
  }

  onDestroy(() => {
    stopFrameCapture();
    stopCamera();
  });
</script>

<!-- Hidden video element for camera capture -->
<video
  bind:this={videoElement}
  autoplay
  playsinline
  muted
  class="camera-video"
/>

{#if $cameraState.error}
  <div class="camera-error">
    {#if $cameraState.permissionDenied}
      <p>Permiso de cámara denegado</p>
      <p class="hint">Por favor, permite el acceso a la cámara</p>
    {:else}
      <p>Error: {$cameraState.error}</p>
    {/if}
  </div>
{/if}

<style>
  .camera-video {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
    pointer-events: none;
  }

  .camera-error {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(239, 68, 68, 0.9);
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    text-align: center;
    z-index: 100;
  }

  .camera-error p {
    margin: 0;
  }

  .camera-error .hint {
    font-size: 0.875rem;
    opacity: 0.8;
    margin-top: 4px;
  }
</style>
