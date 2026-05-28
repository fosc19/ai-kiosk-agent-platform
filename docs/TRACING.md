# Tracing

Latency-sensitive AI systems are hard to debug without turn-level traces.

This project includes a trace model, trace collector, analysis scripts and a Svelte trace viewer. A typical turn may include:

- audio received;
- ASR final transcript;
- orchestrator route decision;
- tool call started/completed;
- LLM first token/final response;
- TTS audio started/completed;
- UI state update.

The goal is to identify where latency or failure appears in the pipeline instead of treating the AI response as a black box.
