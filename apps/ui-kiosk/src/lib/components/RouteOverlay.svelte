<script lang="ts">
  import { fade, fly } from 'svelte/transition';
  import { flip } from 'svelte/animate';

  export let route: {
    store_id: string;
    store_name: string;
    steps: Array<{
      instruction: string;
      direction: 'left' | 'right' | 'straight' | 'arrive';
      distance?: number;
    }>;
  } | null = null;

  export let visible = false;

  // Direction icons as SVG paths
  const directionIcons = {
    left: 'M15 19l-7-7 7-7',
    right: 'M9 5l7 7-7 7',
    straight: 'M12 5v14M5 12l7-7 7 7',
    arrive: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
  };

  // Colors for different states
  const directionColors = {
    left: '#3b82f6',
    right: '#3b82f6',
    straight: '#10b981',
    arrive: '#8b5cf6',
  };

  let currentStep = 0;

  function nextStep() {
    if (route && currentStep < route.steps.length - 1) {
      currentStep++;
    }
  }

  function prevStep() {
    if (currentStep > 0) {
      currentStep--;
    }
  }

  function close() {
    visible = false;
    currentStep = 0;
  }

  $: if (!visible) {
    currentStep = 0;
  }
</script>

{#if visible && route}
  <div class="route-overlay" transition:fade={{ duration: 300 }}>
    <div class="route-container" transition:fly={{ y: 50, duration: 400 }}>
      <!-- Header -->
      <div class="route-header">
        <div class="store-info">
          <span class="store-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d={directionIcons.arrive} />
            </svg>
          </span>
          <div>
            <h2>{route.store_name}</h2>
            <span class="step-counter">
              Paso {currentStep + 1} de {route.steps.length}
            </span>
          </div>
        </div>
        <button class="close-btn" on:click={close}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Steps Progress -->
      <div class="steps-progress">
        {#each route.steps as step, i}
          <div
            class="step-dot"
            class:active={i === currentStep}
            class:completed={i < currentStep}
            style="--color: {directionColors[step.direction]}"
          />
          {#if i < route.steps.length - 1}
            <div
              class="step-line"
              class:completed={i < currentStep}
            />
          {/if}
        {/each}
      </div>

      <!-- Current Step -->
      <div class="current-step">
        {#key currentStep}
          <div
            class="step-content"
            in:fly={{ x: 50, duration: 300 }}
            out:fly={{ x: -50, duration: 200 }}
          >
            <div
              class="direction-icon"
              style="background-color: {directionColors[route.steps[currentStep].direction]}20; color: {directionColors[route.steps[currentStep].direction]}"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d={directionIcons[route.steps[currentStep].direction]} />
              </svg>
            </div>
            <p class="instruction">{route.steps[currentStep].instruction}</p>
            {#if route.steps[currentStep].distance}
              <span class="distance">{route.steps[currentStep].distance}m</span>
            {/if}
          </div>
        {/key}
      </div>

      <!-- Navigation Buttons -->
      <div class="nav-buttons">
        <button
          class="nav-btn"
          on:click={prevStep}
          disabled={currentStep === 0}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M15 19l-7-7 7-7" />
          </svg>
          Anterior
        </button>

        {#if currentStep === route.steps.length - 1}
          <button class="nav-btn primary" on:click={close}>
            Finalizar
          </button>
        {:else}
          <button class="nav-btn primary" on:click={nextStep}>
            Siguiente
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 5l7 7-7 7" />
            </svg>
          </button>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .route-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: flex-end;
    justify-content: center;
    padding: 1rem;
    z-index: 100;
  }

  .route-container {
    background: white;
    border-radius: 24px 24px 16px 16px;
    width: 100%;
    max-width: 500px;
    padding: 1.5rem;
    box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.2);
  }

  .route-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1.5rem;
  }

  .store-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .store-icon {
    width: 48px;
    height: 48px;
    background: linear-gradient(135deg, #8b5cf6, #6366f1);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
  }

  .store-icon svg {
    width: 24px;
    height: 24px;
  }

  .store-info h2 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 700;
    color: #1f2937;
  }

  .step-counter {
    font-size: 0.875rem;
    color: #6b7280;
  }

  .close-btn {
    width: 36px;
    height: 36px;
    border: none;
    background: #f3f4f6;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #6b7280;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: #e5e7eb;
    color: #1f2937;
  }

  .close-btn svg {
    width: 20px;
    height: 20px;
  }

  .steps-progress {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    margin-bottom: 1.5rem;
  }

  .step-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #e5e7eb;
    transition: all 0.3s;
    flex-shrink: 0;
  }

  .step-dot.active {
    width: 16px;
    height: 16px;
    background: var(--color);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--color) 20%, transparent);
  }

  .step-dot.completed {
    background: var(--color);
  }

  .step-line {
    width: 24px;
    height: 2px;
    background: #e5e7eb;
    transition: background 0.3s;
  }

  .step-line.completed {
    background: #3b82f6;
  }

  .current-step {
    min-height: 160px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .step-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 1rem;
  }

  .direction-icon {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .direction-icon svg {
    width: 40px;
    height: 40px;
  }

  .instruction {
    font-size: 1.25rem;
    font-weight: 500;
    color: #1f2937;
    margin: 0;
    line-height: 1.4;
  }

  .distance {
    font-size: 0.875rem;
    color: #6b7280;
    background: #f3f4f6;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
  }

  .nav-buttons {
    display: flex;
    gap: 0.75rem;
    margin-top: 1.5rem;
  }

  .nav-btn {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.875rem 1rem;
    border: none;
    border-radius: 12px;
    font-size: 1rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    background: #f3f4f6;
    color: #4b5563;
  }

  .nav-btn:hover:not(:disabled) {
    background: #e5e7eb;
  }

  .nav-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .nav-btn.primary {
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: white;
  }

  .nav-btn.primary:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
  }

  .nav-btn svg {
    width: 18px;
    height: 18px;
  }
</style>
