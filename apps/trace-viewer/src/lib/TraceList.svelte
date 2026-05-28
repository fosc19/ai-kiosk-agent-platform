<script lang="ts">
  import type { TraceSummary } from './types';

  export let traces: TraceSummary[] = [];
  export let onSelectTrace: (traceId: string) => void = () => {};
  export let loading: boolean = false;

  function formatDuration(ms?: number): string {
    if (ms === undefined) return 'N/A';
    if (ms < 1000) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  }

  function getStatusIcon(trace: TraceSummary): string {
    if (trace.violations) return '🔴';
    if (trace.duration_ms && trace.duration_ms > 2500) return '🟡';
    return '✅';
  }

  function getStatusText(trace: TraceSummary): string {
    if (trace.violations) return 'SLA Violation';
    if (trace.duration_ms && trace.duration_ms > 2500) return 'Warning';
    return 'OK';
  }
</script>

<div class="trace-list">
  <div class="header">
    <h2>Available Traces</h2>
    <span class="count">{traces.length} traces</span>
  </div>

  {#if loading}
    <div class="loading">
      <div class="spinner"></div>
      <p>Loading traces...</p>
    </div>
  {:else if traces.length === 0}
    <div class="empty">
      <p>No traces found</p>
      <p class="help">Start a session to generate traces</p>
    </div>
  {:else}
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Trace ID</th>
            <th>Events</th>
            <th>Turns</th>
            <th>Duration</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each traces as trace}
            <tr class:violation={trace.violations}>
              <td class="status">
                <span class="status-icon">{getStatusIcon(trace)}</span>
                <span class="status-text">{getStatusText(trace)}</span>
              </td>
              <td class="trace-id">
                <code>{trace.trace_id}</code>
              </td>
              <td class="centered">{trace.event_count}</td>
              <td class="centered">{trace.turn_count}</td>
              <td class="duration">{formatDuration(trace.duration_ms)}</td>
              <td>
                <button class="btn-view" on:click={() => onSelectTrace(trace.trace_id)}>
                  View
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .trace-list {
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    padding: 20px;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
  }

  h2 {
    margin: 0;
    font-size: 20px;
    color: #1f2937;
  }

  .count {
    font-size: 14px;
    color: #6b7280;
    background: #f3f4f6;
    padding: 4px 12px;
    border-radius: 12px;
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

  .empty p {
    margin: 5px 0;
  }

  .help {
    font-size: 14px;
  }

  .table-container {
    overflow-x: auto;
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

  tr:hover {
    background: #f9fafb;
  }

  tr.violation {
    background: #fef2f2;
  }

  tr.violation:hover {
    background: #fee2e2;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-icon {
    font-size: 16px;
  }

  .status-text {
    font-size: 13px;
    font-weight: 500;
  }

  .trace-id code {
    background: #f3f4f6;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'Courier New', monospace;
    color: #374151;
  }

  .centered {
    text-align: center;
  }

  .duration {
    font-family: 'Courier New', monospace;
    color: #374151;
  }

  .btn-view {
    background: #3b82f6;
    color: white;
    border: none;
    padding: 6px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
  }

  .btn-view:hover {
    background: #2563eb;
  }
</style>
