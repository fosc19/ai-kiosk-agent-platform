# Architecture

The system is split into an edge client and backend services.

## Edge client

`apps/ui-kiosk` is a Svelte/Vite app intended for a kiosk or lightweight edge device. It handles:

- microphone capture;
- camera capture;
- WebSocket connection lifecycle;
- UI states such as idle, listening, thinking and speaking;
- avatar/lip-sync hooks;
- route/action overlays.

## Backend services

`services/orchestrator` is the main FastAPI service. It owns session state, message routing, policy checks, cache, tool calls and structured responses back to the kiosk.

`services/speech` isolates ASR/TTS logic behind provider adapters. It can be configured for local or external providers.

`services/vision` provides a service boundary for presence or visual context.

`services/mcp-tools` exposes structured operational data through MCP-style/HTTP tool endpoints. In this portfolio edition the data is synthetic.

`services/trace-collector` and `apps/trace-viewer` provide debugging and latency analysis for conversation turns.

## Design principles

- Keep the edge UI simple and resilient.
- Put heavy integrations and provider logic behind backend service boundaries.
- Use typed contracts for WebSocket messages.
- Treat LLMs as one component in a larger operational system.
- Track latency and reliability with traces and golden flows.
