<script lang="ts">
  import { onMount } from 'svelte';
  import WaterfallChart from '$lib/WaterfallChart.svelte';
  import { traceCollectorClient } from '$lib/api';
  import { groupBarsByTurn, calculateTotalDuration } from '$lib/waterfall-utils';
  import type { TraceEvent, TraceAnalysis, WaterfallBar } from '$lib/types';

  export let traceId: string;
  export let onBack: () => void;

  let events: TraceEvent[] = [];
  let analysis: TraceAnalysis | null = null;
  let loading = true;
  let error: string | null = null;
  let selectedTurn: string | null = null;
  let turns: string[] = [];
  let turnBars: Map<string, WaterfallBar[]> = new Map();

  async function loadTrace() {
    try {
      loading = true;
      error = null;

      // Load events and analysis in parallel
      const [eventsData, analysisData] = await Promise.all([
        traceCollectorClient.getTrace(traceId),
        traceCollectorClient.analyzeTrace(traceId),
      ]);

      events = eventsData;
      analysis = analysisData;

      // Group by turns
      turnBars = groupBarsByTurn(events);
      turns = Array.from(turnBars.keys()).filter(Boolean);

      // Select first turn by default
      if (turns.length > 0 && !selectedTurn) {
        selectedTurn = turns[0];
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load trace';
      console.error('Error loading trace:', err);
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    loadTrace();
  });

  $: currentBars = selectedTurn ? turnBars.get(selectedTurn) || [] : [];
  $: totalDuration = currentBars.length > 0 ? calculateTotalDuration(currentBars) : 0;
  $: violations = currentBars.filter(b => b.violation).length;
</script>

<div class="page">
  <header class="page-header">
    <button class="btn-back" on:click={onBack}>
      ← Back to List
    </button>
    <div class="title-section">
      <h1>Trace Details</h1>
      <code class="trace-id">{traceId}</code>
    </div>
  </header>

  {#if loading}
    <div class="loading">
      <div class="spinner"></div>
      <p>Loading trace...</p>
    </div>
  {:else if error}
    <div class="alert alert-error">
      <strong>Error</strong>
      <p>{error}</p>
    </div>
  {:else if analysis}
    <!-- Summary cards -->
    <div class="summary-cards">
      <div class="card">
        <div class="card-label">Events</div>
        <div class="card-value">{analysis.event_count}</div>
      </div>
      <div class="card">
        <div class="card-label">Turns</div>
        <div class="card-value">{analysis.turn_count}</div>
      </div>
      <div class="card">
        <div class="card-label">Duration</div>
        <div class="card-value">{totalDuration.toFixed(0)}ms</div>
      </div>
      <div class="card" class:warning={violations > 0}>
        <div class="card-label">SLA Violations</div>
        <div class="card-value">{violations} {violations > 0 ? '🔴' : '✅'}</div>
      </div>
    </div>

    <!-- Turn selector -->
    {#if turns.length > 0}
      <div class="turn-selector">
        <label for="turn-select">Select Turn:</label>
        <select id="turn-select" bind:value={selectedTurn}>
          {#each turns as turn}
            <option value={turn}>{turn}</option>
          {/each}
        </select>
      </div>
    {/if}

    <!-- Waterfall chart -->
    {#if currentBars.length > 0}
      <div class="chart-section">
        <WaterfallChart
          bars={currentBars}
          title={selectedTurn ? `Turn: ${selectedTurn}` : 'Trace Timeline'}
          width={1200}
          height={Math.max(400, currentBars.length * 40 + 100)}
        />
      </div>
    {:else}
      <div class="empty">
        <p>No events found for this turn</p>
      </div>
    {/if}

    <!-- Latencies table -->
    {#if analysis.latencies && Object.keys(analysis.latencies).length > 0}
      <div class="latencies-section">
        <h2>Latencies</h2>
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Duration</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {#each Object.entries(analysis.latencies) as [key, value]}
              <tr>
                <td><code>{key}</code></td>
                <td class="duration">{value.toFixed(2)}ms</td>
                <td>
                  {#if key.includes('_total') && value > 3000}
                    <span class="badge badge-error">🔴 Slow</span>
                  {:else if key.includes('classify') && value > 150}
                    <span class="badge badge-error">🔴 Slow</span>
                  {:else if key.includes('_total') && value > 2500}
                    <span class="badge badge-warning">🟡 Warning</span>
                  {:else}
                    <span class="badge badge-success">✅ OK</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {/if}
</div>

<style>
  .page {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
  }

  .page-header {
    display: flex;
    flex-direction: column;
    gap: 15px;
    margin-bottom: 30px;
  }

  .btn-back {
    background: #f3f4f6;
    color: #374151;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 14px;
    cursor: pointer;
    align-self: flex-start;
    transition: background 0.2s;
  }

  .btn-back:hover {
    background: #e5e7eb;
  }

  .title-section {
    display: flex;
    align-items: center;
    gap: 15px;
  }

  h1 {
    margin: 0;
    font-size: 28px;
    color: #1f2937;
  }

  .trace-id {
    background: #f3f4f6;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-family: 'Courier New', monospace;
    color: #374151;
  }

  .loading, .empty {
    text-align: center;
    padding: 60px 20px;
    color: #6b7280;
  }

  .spinner {
    border: 3px solid #f3f4f6;
    border-top: 3px solid #3b82f6;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin: 0 auto 20px;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
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

  .summary-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
  }

  .card {
    background: white;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .card.warning {
    background: #fef2f2;
    border: 2px solid #fecaca;
  }

  .card-label {
    font-size: 13px;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
  }

  .card-value {
    font-size: 28px;
    font-weight: bold;
    color: #1f2937;
  }

  .turn-selector {
    background: white;
    padding: 15px 20px;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .turn-selector label {
    font-size: 14px;
    font-weight: 500;
    color: #374151;
  }

  .turn-selector select {
    padding: 8px 12px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 14px;
    color: #374151;
    background: white;
    cursor: pointer;
  }

  .chart-section {
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    padding: 20px;
    margin-bottom: 30px;
    overflow-x: auto;
  }

  .latencies-section {
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    padding: 20px;
  }

  .latencies-section h2 {
    margin: 0 0 20px 0;
    font-size: 20px;
    color: #1f2937;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  thead {
    background: #f9fafb;
  }

  th {
    padding: 12px;
    text-align: left;
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 2px solid #e5e7eb;
  }

  td {
    padding: 12px;
    border-bottom: 1px solid #e5e7eb;
    font-size: 14px;
  }

  td code {
    background: #f3f4f6;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 12px;
    font-family: 'Courier New', monospace;
  }

  .duration {
    font-family: 'Courier New', monospace;
    color: #374151;
  }

  .badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
  }

  .badge-success {
    background: #d1fae5;
    color: #065f46;
  }

  .badge-warning {
    background: #fef3c7;
    color: #92400e;
  }

  .badge-error {
    background: #fee2e2;
    color: #991b1b;
  }
</style>
