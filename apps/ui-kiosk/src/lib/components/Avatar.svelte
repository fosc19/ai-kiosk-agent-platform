<script lang="ts">
  import { uiState } from '$lib/stores/websocket';
  import { UIState } from '@ai-kiosk/shared-types';
  import { onMount, onDestroy } from 'svelte';

  // State config with colors
  const stateConfig = {
    [UIState.IDLE]: { color: '#64748b', label: 'En espera', bgColor: '#e2e8f0' },
    [UIState.LISTENING]: { color: '#3b82f6', label: 'Escuchando', bgColor: '#dbeafe' },
    [UIState.THINKING]: { color: '#f59e0b', label: 'Pensando', bgColor: '#fef3c7' },
    [UIState.SPEAKING]: { color: '#10b981', label: 'Hablando', bgColor: '#d1fae5' },
    [UIState.GUIDING]: { color: '#8b5cf6', label: 'Guiando', bgColor: '#ede9fe' },
  };

  $: config = stateConfig[$uiState as UIState] || stateConfig[UIState.IDLE];

  // Eye tracking
  let eyeOffsetX = 0;
  let eyeOffsetY = 0;
  let isBlinking = false;

  // Mouth animation for speaking
  let mouthOpenAmount = 0;
  let speakingInterval: ReturnType<typeof setInterval> | null = null;

  // Idle eye movement
  let idleInterval: ReturnType<typeof setInterval> | null = null;

  function startIdleMovement() {
    if (idleInterval) return;
    idleInterval = setInterval(() => {
      // Random gentle eye movement
      eyeOffsetX = (Math.random() - 0.5) * 6;
      eyeOffsetY = (Math.random() - 0.5) * 3;

      // Occasional blink
      if (Math.random() < 0.15) {
        blink();
      }
    }, 2000);
  }

  function stopIdleMovement() {
    if (idleInterval) {
      clearInterval(idleInterval);
      idleInterval = null;
    }
  }

  function blink() {
    isBlinking = true;
    setTimeout(() => {
      isBlinking = false;
    }, 150);
  }

  function startSpeaking() {
    if (speakingInterval) return;
    speakingInterval = setInterval(() => {
      mouthOpenAmount = Math.random() * 0.8 + 0.2;
    }, 100);
  }

  function stopSpeaking() {
    if (speakingInterval) {
      clearInterval(speakingInterval);
      speakingInterval = null;
    }
    mouthOpenAmount = 0;
  }

  // React to state changes
  $: {
    if ($uiState === 'speaking') {
      startSpeaking();
      stopIdleMovement();
      // Look forward when speaking
      eyeOffsetX = 0;
      eyeOffsetY = 0;
    } else {
      stopSpeaking();
    }

    if ($uiState === 'listening') {
      stopIdleMovement();
      // Look slightly up when listening
      eyeOffsetX = 0;
      eyeOffsetY = -2;
    }

    if ($uiState === 'thinking') {
      stopIdleMovement();
      // Look to the side when thinking
      eyeOffsetX = 4;
      eyeOffsetY = -1;
    }

    if ($uiState === 'idle' || $uiState === 'guiding') {
      startIdleMovement();
    }
  }

  // Periodic blinking
  let blinkInterval: ReturnType<typeof setInterval> | null = null;

  onMount(() => {
    startIdleMovement();
    blinkInterval = setInterval(blink, 4000);
  });

  onDestroy(() => {
    stopIdleMovement();
    stopSpeaking();
    if (blinkInterval) clearInterval(blinkInterval);
  });

  // Computed values for mouth
  $: mouthHeight = $uiState === 'speaking' ? 8 + mouthOpenAmount * 16 :
                   $uiState === 'listening' ? 6 :
                   $uiState === 'thinking' ? 4 : 0;

  $: mouthWidth = $uiState === 'speaking' ? 20 + mouthOpenAmount * 8 :
                  $uiState === 'listening' ? 16 :
                  $uiState === 'thinking' ? 8 : 0;
</script>

<div class="avatar-container" style="--avatar-color: {config.color}; --avatar-bg: {config.bgColor}">
  <div class="avatar-wrapper">
    <svg viewBox="0 0 200 200" class="avatar-svg" class:thinking={$uiState === 'thinking'}>
      <defs>
        <!-- Face gradient -->
        <linearGradient id="faceGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color={config.bgColor} />
          <stop offset="100%" stop-color={config.color} stop-opacity="0.3" />
        </linearGradient>

        <!-- Eye shine -->
        <radialGradient id="eyeShine" cx="30%" cy="30%">
          <stop offset="0%" stop-color="white" />
          <stop offset="100%" stop-color="#f0f0f0" />
        </radialGradient>

        <!-- Shadow -->
        <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color={config.color} flood-opacity="0.3"/>
        </filter>
      </defs>

      <!-- Main face circle -->
      <circle
        cx="100"
        cy="100"
        r="85"
        fill="url(#faceGrad)"
        stroke={config.color}
        stroke-width="3"
        filter="url(#shadow)"
        class="face"
      />

      <!-- Inner face highlight -->
      <ellipse
        cx="85"
        cy="80"
        rx="50"
        ry="40"
        fill="white"
        opacity="0.4"
      />

      <!-- Left eye white -->
      <ellipse
        cx="65"
        cy="85"
        rx="22"
        ry={isBlinking ? 2 : 18}
        fill="url(#eyeShine)"
        class="eye-white"
      />

      <!-- Right eye white -->
      <ellipse
        cx="135"
        cy="85"
        rx="22"
        ry={isBlinking ? 2 : 18}
        fill="url(#eyeShine)"
        class="eye-white"
      />

      <!-- Left pupil -->
      {#if !isBlinking}
        <circle
          cx={65 + eyeOffsetX}
          cy={88 + eyeOffsetY}
          r="10"
          fill="#1e293b"
          class="pupil"
        />
        <circle
          cx={62 + eyeOffsetX}
          cy={85 + eyeOffsetY}
          r="3"
          fill="white"
          class="eye-highlight"
        />
      {/if}

      <!-- Right pupil -->
      {#if !isBlinking}
        <circle
          cx={135 + eyeOffsetX}
          cy={88 + eyeOffsetY}
          r="10"
          fill="#1e293b"
          class="pupil"
        />
        <circle
          cx={132 + eyeOffsetX}
          cy={85 + eyeOffsetY}
          r="3"
          fill="white"
          class="eye-highlight"
        />
      {/if}

      <!-- Eyebrows -->
      <path
        d="M 45 {$uiState === 'listening' ? 62 : $uiState === 'thinking' ? 68 : 65} Q 65 {$uiState === 'listening' ? 55 : 60} 85 {$uiState === 'listening' ? 62 : 65}"
        stroke={config.color}
        stroke-width="4"
        stroke-linecap="round"
        fill="none"
        class="eyebrow"
      />
      <path
        d="M 115 {$uiState === 'listening' ? 62 : $uiState === 'thinking' ? 65 : 65} Q 135 {$uiState === 'listening' ? 55 : $uiState === 'thinking' ? 62 : 60} 155 {$uiState === 'listening' ? 62 : $uiState === 'thinking' ? 70 : 65}"
        stroke={config.color}
        stroke-width="4"
        stroke-linecap="round"
        fill="none"
        class="eyebrow"
      />

      <!-- Mouth -->
      {#if $uiState === 'speaking' || $uiState === 'listening' || $uiState === 'thinking'}
        <!-- Open mouth for speaking/listening/thinking -->
        <ellipse
          cx="100"
          cy="140"
          rx={mouthWidth / 2}
          ry={mouthHeight / 2}
          fill={$uiState === 'speaking' ? '#1e293b' : config.color}
          opacity={$uiState === 'speaking' ? 1 : 0.6}
          class="mouth-open"
        />
        {#if $uiState === 'speaking' && mouthOpenAmount > 0.3}
          <!-- Tongue hint when mouth is open -->
          <ellipse
            cx="100"
            cy={145 + mouthOpenAmount * 3}
            rx={mouthWidth / 3}
            ry="4"
            fill="#ef4444"
            opacity="0.7"
          />
        {/if}
      {:else}
        <!-- Smile for idle/guiding -->
        <path
          d="M 70 135 Q 100 160 130 135"
          stroke={config.color}
          stroke-width="5"
          stroke-linecap="round"
          fill="none"
          class="smile"
        />
      {/if}

      <!-- Cheek blush -->
      <circle cx="45" cy="115" r="12" fill={config.color} opacity="0.2" />
      <circle cx="155" cy="115" r="12" fill={config.color} opacity="0.2" />
    </svg>

    <!-- Pulse rings -->
    <div class="pulse-ring"></div>
    <div class="pulse-ring delay"></div>

    <!-- State indicator dot -->
    <div class="state-dot"></div>
  </div>

  <p class="avatar-label">{config.label}</p>
</div>

<style>
  .avatar-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
  }

  .avatar-wrapper {
    position: relative;
    width: 220px;
    height: 220px;
  }

  .avatar-svg {
    width: 100%;
    height: 100%;
    transition: transform 0.3s ease;
  }

  .avatar-svg.thinking {
    animation: think-wobble 2s ease-in-out infinite;
  }

  @keyframes think-wobble {
    0%, 100% { transform: rotate(0deg); }
    25% { transform: rotate(-2deg); }
    75% { transform: rotate(2deg); }
  }

  .face {
    transition: all 0.3s ease;
  }

  .eye-white {
    transition: ry 0.1s ease;
  }

  .pupil {
    transition: cx 0.3s ease, cy 0.3s ease;
  }

  .eye-highlight {
    transition: cx 0.3s ease, cy 0.3s ease;
  }

  .eyebrow {
    transition: d 0.3s ease;
  }

  .mouth-open {
    transition: rx 0.1s ease, ry 0.1s ease;
  }

  .smile {
    transition: d 0.3s ease;
  }

  .pulse-ring {
    position: absolute;
    inset: -10px;
    border-radius: 50%;
    border: 3px solid var(--avatar-color);
    opacity: 0;
    animation: pulse 2.5s ease-out infinite;
    pointer-events: none;
  }

  .pulse-ring.delay {
    animation-delay: 1.25s;
  }

  @keyframes pulse {
    0% {
      transform: scale(0.9);
      opacity: 0.6;
    }
    100% {
      transform: scale(1.2);
      opacity: 0;
    }
  }

  .state-dot {
    position: absolute;
    bottom: 10px;
    right: 10px;
    width: 16px;
    height: 16px;
    background: var(--avatar-color);
    border-radius: 50%;
    border: 3px solid white;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    animation: dot-pulse 1.5s ease-in-out infinite;
  }

  @keyframes dot-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.2); }
  }

  .avatar-label {
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--avatar-color);
    margin: 0;
    text-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    letter-spacing: 0.5px;
    transition: color 0.3s ease;
  }
</style>
