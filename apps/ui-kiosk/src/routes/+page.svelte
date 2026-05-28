<script lang="ts">
  import { onMount } from 'svelte';
  import { connect, disconnect, wsState, transcript, sayText, uiState as wsUIState, routeData } from '$lib/stores/websocket';
  // import VRMAvatar from '$lib/components/VRMAvatar.svelte'; // 3D avatar available
  import Avatar from '$lib/components/Avatar.svelte'; // 2D fallback
  import CameraCapture from '$lib/components/CameraCapture.svelte';
  import AudioCapture from '$lib/components/AudioCapture.svelte';
  import RouteOverlay from '$lib/components/RouteOverlay.svelte';
  import { initUIStateSync, uiState } from '$lib/stores/ui';

  let initialized = false;
  let showRoute = false;

  // Show route overlay when route data arrives
  $: if ($routeData && $wsUIState === 'guiding') {
    showRoute = true;
  }

  function handleStart() {
    console.log('[App] User clicked start - initializing media...');
    initialized = true;
  }

  onMount(() => {
    console.log('[App] Connecting to backend...');
    connect();

    // Initialize UI state sync with WebSocket
    initUIStateSync();

    return () => {
      console.log('[App] Disconnecting from backend...');
      disconnect();
    };
  });
</script>

<svelte:head>
  <title>AI Kiosk Agent Platform</title>
</svelte:head>

<main>
  <CameraCapture shouldInit={initialized} />
  <AudioCapture shouldInit={initialized} />

  {#if !initialized}
    <div class="start-overlay">
      <div class="start-content">
        <h2>AI Kiosk Agent Platform</h2>
        <p>Press to activate the assistant</p>
        <button class="start-button" on:click={handleStart}>
          Start
        </button>
      </div>
    </div>
  {/if}
  <header>
    <h1>AI Kiosk Agent Platform</h1>
    <div class="connection-status">
      {#if $wsState.connected}
        <span class="status-dot connected"></span>
        <span>Connected</span>
      {:else if $wsState.reconnecting}
        <span class="status-dot reconnecting"></span>
        <span>Reconnecting...</span>
      {:else}
        <span class="status-dot disconnected"></span>
        <span>Disconnected</span>
      {/if}
    </div>
  </header>

  <div class="avatar-wrapper">
    <Avatar />
  </div>

  <!-- Transcript and Response Display -->
  {#if initialized && ($transcript || $sayText)}
    <div class="conversation-panel">
      {#if $transcript}
        <div class="transcript">
          <span class="label">You:</span>
          <span class="text">{$transcript.text}</span>
        </div>
      {/if}
      {#if $sayText && $wsUIState === 'speaking'}
        <div class="response">
          <span class="label">Assistant:</span>
          <span class="text">{$sayText.text}</span>
        </div>
      {/if}
    </div>
  {/if}

  <footer>
    <p>Full Pipeline with Navigation</p>
  </footer>

  <!-- Route navigation overlay -->
  <RouteOverlay route={$routeData} bind:visible={showRoute} />
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
  }

  main {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    color: white;
  }

  header {
    padding: 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  h1 {
    margin: 0;
    font-size: 2rem;
    font-weight: 700;
  }

  .connection-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: rgba(255, 255, 255, 0.1);
    padding: 0.5rem 1rem;
    border-radius: 20px;
    backdrop-filter: blur(10px);
  }

  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }

  .status-dot.connected {
    background-color: #10b981;
    box-shadow: 0 0 10px #10b981;
  }

  .status-dot.reconnecting {
    background-color: #f59e0b;
    animation: blink 1s infinite;
  }

  .status-dot.disconnected {
    background-color: #ef4444;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  .avatar-wrapper {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.95);
    margin: 2rem;
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  }

  footer {
    padding: 1rem;
    text-align: center;
    font-size: 0.9rem;
    opacity: 0.8;
  }

  .start-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    backdrop-filter: blur(10px);
  }

  .start-content {
    text-align: center;
    color: white;
  }

  .start-content h2 {
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
  }

  .start-content p {
    font-size: 1.1rem;
    opacity: 0.8;
    margin-bottom: 2rem;
  }

  .start-button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    padding: 1rem 3rem;
    font-size: 1.25rem;
    border-radius: 50px;
    cursor: pointer;
    transition: transform 0.2s, box-shadow 0.2s;
    box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
  }

  .start-button:hover {
    transform: scale(1.05);
    box-shadow: 0 15px 40px rgba(102, 126, 234, 0.5);
  }

  .start-button:active {
    transform: scale(0.98);
  }

  /* Conversation panel styles */
  .conversation-panel {
    position: fixed;
    bottom: 4rem;
    left: 50%;
    transform: translateX(-50%);
    width: 90%;
    max-width: 600px;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(10px);
    border-radius: 16px;
    padding: 1rem;
    z-index: 100;
  }

  .transcript, .response {
    padding: 0.5rem 0;
  }

  .transcript .label {
    color: #a0aec0;
    font-weight: 600;
    margin-right: 0.5rem;
  }

  .transcript .text {
    color: #e2e8f0;
  }

  .response .label {
    color: #667eea;
    font-weight: 600;
    margin-right: 0.5rem;
  }

  .response .text {
    color: white;
  }
</style>
