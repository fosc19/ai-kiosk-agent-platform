# Case study: conversational AI kiosk

## Problem

A kiosk-style assistant needs to interact with users in real time, understand spoken requests, call tools over structured data, return useful answers and guide users through a physical environment.

A simple chatbot is not enough. The system needs UI state, audio handling, backend orchestration, external AI/voice adapters, structured tools, traces and operational fallbacks.

## Solution

This project implements a portfolio version of that architecture:

- Svelte edge UI for kiosk interaction;
- FastAPI WebSocket orchestrator;
- ASR/TTS service abstraction;
- vision/presence service boundary;
- MCP-style tools over store and routing data;
- Redis/PostgreSQL service layer;
- tracing and golden-flow validation.

## Engineering value

The project demonstrates the ability to design and build beyond the prompt layer:

- asynchronous backend services;
- real-time WebSocket communication;
- provider abstraction for LLM/voice services;
- tool execution over structured data;
- frontend/backend contracts;
- deployment-oriented architecture;
- debugging and observability for latency-sensitive AI flows.

## Portfolio scope

This public edition uses synthetic demo data and sanitized configuration. It preserves the architecture and representative code patterns while removing private assets, production configuration and internal planning material.
