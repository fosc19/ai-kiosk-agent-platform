<script lang="ts">
  import { onMount } from 'svelte';
  import TraceList from '$lib/TraceList.svelte';
  import { traceCollectorClient } from '$lib/api';
  import type { TraceSummary } from '$lib/types';

  export let onSelectTrace: (traceId: string) => void;

  let traces: TraceSummary[] = [];
  let loading = true;
  let error: string | null = null;
  let healthOk = false;
  let autoRefresh = false;
  let refreshInterval: number | null = null;

  async function loadTraces() {
    try {
      loading = true;
      error = null;
      traces = await traceCollectorClient.getTraceSummaries(50);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load traces';
      console.error('Error loading traces:', err);
    } finally {
      loading = false;
    }
  }

  async function checkHealth() {
    healthOk = await traceCollectorClient.healthCheck();
    if (!healthOk) {
      error = 'Trace Collector is not responding. Make sure it is running on port 9002.';
    }
  }

  function toggleAutoRefresh() {
    autoRefresh = !autoRefresh;
    if (autoRefresh) {
      refreshInterval = window.setInterval(loadTraces, 5000);
    } else {
      if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
      }
    }
  }

  onMount(() => {
    checkHealth().then(() => {
      if (healthOk) {
        loadTraces();
      }
    });

    return () => {
      if (refreshInterval) {
        clearInterval(refreshInterval);
      }
    };
  });
</script>

<div class="page">
  <header class="page-header">
    <div>
      <h1>AI Kiosk Trace Viewer</h1>
      <p class="subtitle">Waterfall visualization for debugging latencies</p>
    </div>
    <div class="header-actions">
      <button class="btn-refresh" on:click={loadTraces} disabled={loading}>
        {loading ? '↻ Loading...' : '↻ Refresh'}
      </button>
      <label class="auto-refresh">
        <input type="checkbox" checked={autoRefresh} on:change={toggleAutoRefresh} />
        Auto-refresh (5s)
      </label>
    </div>
  </header>

  {#if !healthOk}
    <div class="alert alert-error">
      <strong>⚠️ Connection Error</strong>
      <p>{error || 'Cannot connect to Trace Collector'}</p>
      <p class="help">
        Make sure the Trace Collector is running:
        <code>task trace:collector</code>
      </p>
    </div>
  {:else if error}
    <div class="alert alert-error">
      <strong>Error</strong>
      <p>{error}</p>
    </div>
  {:else}
    <TraceList {traces} {loading} {onSelectTrace} />
  {/if}

  <footer class="page-footer">
    <p>
      Status:
      <span class="status-indicator" class:online={healthOk} class:offline={!healthOk}>
        {healthOk ? '● Online' : '● Offline'}
      </span>
    </p>
    <p class="help-text">
      For documentation, see
      <a href="https://github.com/yourusername/ai-kiosk" target="_blank">OBSERVABILITY_PLAN.md</a>
    </p>
  </footer>
</div>

<style>
  .page {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
  }

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 30px;
  }

  h1 {
    margin: 0 0 5px 0;
    font-size: 32px;
    color: #1f2937;
  }

  .subtitle {
    margin: 0;
    color: #6b7280;
    font-size: 16px;
  }

  .header-actions {
    display: flex;
    gap: 15px;
    align-items: center;
  }

  .btn-refresh {
    background: #3b82f6;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
  }

  .btn-refresh:hover:not(:disabled) {
    background: #2563eb;
  }

  .btn-refresh:disabled {
    background: #9ca3af;
    cursor: not-allowed;
  }

  .auto-refresh {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: #374151;
    cursor: pointer;
  }

  .auto-refresh input[type="checkbox"] {
    cursor: pointer;
  }

  .alert {
    padding: 16px 20px;
    border-radius: 8px;
    margin-bottom: 20px;
  }

  .alert-error {
    background: #fef2f2;
    border: 1px solid #fecaca;
    color: #991b1b;
  }

  .alert strong {
    display: block;
    margin-bottom: 8px;
    font-size: 16px;
  }

  .alert p {
    margin: 5px 0;
    font-size: 14px;
  }

  .alert code {
    background: #fee2e2;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
  }

  .page-footer {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #e5e7eb;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 14px;
    color: #6b7280;
  }

  .page-footer p {
    margin: 0;
  }

  .status-indicator {
    font-weight: 500;
  }

  .status-indicator.online {
    color: #10b981;
  }

  .status-indicator.offline {
    color: #ef4444;
  }

  .help-text a {
    color: #3b82f6;
    text-decoration: none;
  }

  .help-text a:hover {
    text-decoration: underline;
  }
</style>
