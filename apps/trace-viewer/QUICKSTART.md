# Trace Viewer - Quick Start

Quick guide to start using the Trace Viewer in 5 minutes.

## Step 1: Start the Trace Collector

From the project root:

```bash
task trace:collector
```

You should see something like:
```
🚀 Trace Collector starting on http://localhost:9002
```

Keep this process running.

## Step 2: Start the Trace Viewer

In another terminal:

```bash
task trace:viewer
```

Or start both at the same time:

```bash
task trace:full
```

The viewer will be at `http://localhost:9003`

## Step 3: Generate Test Traces

To have data to visualize, you need to run the system and generate some sessions.

### Option A: Using the full system

```bash
# Terminal 1: backend services
task dev:services

# Terminal 2: UI
task dev:ui

# Interact with the UI to generate traces
```

### Option B: Using a Golden Flow

```bash
# Run a test that generates traces
task trace:golden FLOW=navigation/store_location.yml
```

## Step 4: Visualize

1. Open `http://localhost:9003` in your browser
2. You'll see the list of available traces
3. Click "View" to see the waterfall of a specific trace

## Interpreting the Waterfall

```
Turn turn_001 (Total: 2345ms) ━━━━━━━━━━━━━━━━━━━━━
  ┌─────────────────────────────────────────────┐
  │ VAD End        ▓▓░  50ms   ✅              │
  │ ASR           ░░▓▓▓▓░ 420ms ✅              │
  │ Classify      ░░░░░░▓ 80ms  ✅              │
  │ Tool: resolve ░░░░░░░▓ 30ms ✅              │
  │ LLM Response  ░░░░░░░░▓▓▓▓ 650ms ✅         │
  │ TTS First     ░░░░░░░░░░░▓▓ 320ms ✅        │
  └─────────────────────────────────────────────┘
     0ms    500ms   1000ms   1500ms   2000ms
```

### Colors

- 🔵 Blue = Orchestrator
- 🟢 Green = MCP Tools
- 🟡 Yellow = ASR (transcription)
- 🟠 Orange = TTS (synthesis)
- 🔴 Red = SLA violation

### Red Bars = Problems

If you see red bars, that component exceeded the SLA:

- Turn total > 3000ms
- ASR > 500ms
- TTS first chunk > 500ms
- Classify > 150ms

## Troubleshooting

### "Cannot connect to Trace Collector"

```bash
# Check if it's running
curl http://localhost:9002/healthz

# If not responding, start it
task trace:collector
```

### "No traces found"

This is normal on first run. Generate traces:

```bash
# Quick option
task trace:golden

# Or use the full system
task dev:services
task dev:ui
# Interact with the UI
```

### Port 9003 in use

```bash
# Find the process using it
lsof -i :9003

# Kill the process
kill -9 <PID>

# Or change the port in vite.config.ts
```

## Useful Commands

```bash
# View only the viewer
task trace:viewer

# View only the collector
task trace:collector

# View both (recommended)
task trace:full

# Health check
curl http://localhost:9002/healthz
curl http://localhost:9003

# List traces via API
curl http://localhost:9002/traces | jq .

# View trace detail
curl http://localhost:9002/traces/session_abc123 | jq .
```

## Next Steps

1. **CI/CD Integration** - Capture traces in automated tests
2. **Compare Runs** - View differences between versions
3. **Golden Flow Regression** - Detect performance degradation
4. **Export Reports** - PDFs with waterfalls for documentation
