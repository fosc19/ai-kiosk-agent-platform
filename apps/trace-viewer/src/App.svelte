<script lang="ts">
  import TraceListPage from './routes/TraceListPage.svelte';
  import TraceDetailPage from './routes/TraceDetailPage.svelte';

  let currentView: 'list' | 'detail' = 'list';
  let selectedTraceId: string | null = null;

  function handleSelectTrace(traceId: string) {
    selectedTraceId = traceId;
    currentView = 'detail';
  }

  function handleBack() {
    currentView = 'list';
    selectedTraceId = null;
  }
</script>

<main>
  {#if currentView === 'list'}
    <TraceListPage onSelectTrace={handleSelectTrace} />
  {:else if currentView === 'detail' && selectedTraceId}
    <TraceDetailPage traceId={selectedTraceId} onBack={handleBack} />
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: #f3f4f6;
    color: #1f2937;
  }

  :global(*) {
    box-sizing: border-box;
  }

  main {
    min-height: 100vh;
  }
</style>
