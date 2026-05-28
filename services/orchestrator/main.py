"""
Orchestrator Service - Core agente conversacional
FastAPI + WebSocket server para comunicación Pi ↔ VPS
"""

import base64
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from conversation_memory import ConversationMemory
from llm_adapter import LLMAdapter, create_llm_adapter
from mcp_client import MCPToolsClient
from presence import PresenceManager
from response_cache import ResponseCache
from router import BasicRouter
from router_mcp import MCPRouter

# F8: Tracing
try:
    from tracing_setup import setup_tracing, Events, OrchestratorTracer
    tracer: OrchestratorTracer | None = setup_tracing()
except ImportError:
    tracer = None
    Events = None

# HTTP client for services
http_client: Optional[httpx.AsyncClient] = None

# LLM adapter for intent classification (F6: context-aware)
llm_adapter: Optional[LLMAdapter] = None

# F6: Conversation memory
conversation_memory: Optional[ConversationMemory] = None

# F6: Playback state tracking per session (for barge-in detection)
from typing import Dict
playback_state: Dict[str, bool] = {}

# Routers - MCP router preferred when available
basic_router = BasicRouter()
mcp_client: Optional[MCPToolsClient] = None
mcp_router: Optional[MCPRouter] = None
response_cache: Optional[ResponseCache] = None

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level)
    ),
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events"""
    global http_client, llm_adapter, mcp_client, mcp_router, conversation_memory, response_cache

    log.info("orchestrator_starting", version="0.3.0", llm_mode=settings.llm_mode)

    # Initialize HTTP client for services
    http_client = httpx.AsyncClient(timeout=5.0)
    log.info("http_client_initialized", vision_url=settings.vision_service_url)

    # F6: Initialize conversation memory (Redis)
    conversation_memory = ConversationMemory(
        redis_url=settings.redis_url,
        ttl_seconds=settings.conversation_memory_ttl,
        max_turns=settings.conversation_max_turns,
    )
    if await conversation_memory.connect():
        log.info("conversation_memory_connected", ttl=settings.conversation_memory_ttl)
    else:
        log.warning("conversation_memory_unavailable", redis_url=settings.redis_url)
        conversation_memory = None

    # Performance: Initialize response cache (Redis with in-memory fallback)
    response_cache = ResponseCache(
        redis_url=settings.redis_url,
        prefix="llm_response",
        enabled=True,
    )
    await response_cache.connect()
    log.info("response_cache_initialized")

    # Initialize LLM adapter (F5) - select API key based on mode
    # Note: mock mode still uses the LLM classifier (MockLLMAdapter) for testing
    use_llm = True
    api_key_map = {
        "gemini": settings.gemini_api_key,
        "grok": settings.grok_api_key,
        "anthropic": settings.anthropic_api_key,
        "ollama": settings.ollama_base_url,  # URL instead of API key
        "openrouter": settings.openrouter_api_key,
    }
    api_key = api_key_map.get(settings.llm_mode)

    try:
        llm_adapter = create_llm_adapter(
            mode=settings.llm_mode,
            api_key=api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
        )
        log.info("llm_adapter_initialized", mode=settings.llm_mode, use_llm=use_llm)
    except Exception as e:
        log.warning("llm_adapter_init_failed", error=str(e))
        llm_adapter = create_llm_adapter(mode="mock")
        use_llm = False

    # Initialize MCP Tools client
    mcp_client = MCPToolsClient(base_url=settings.mcp_tools_url)

    # Initialize MCP router with LLM support (F5) + memory (F6) + cache (Performance)
    mcp_router = MCPRouter(
        mcp_client=mcp_client,
        llm_adapter=llm_adapter,
        use_llm=use_llm,
        memory=conversation_memory,
        response_cache=response_cache,
    )

    # Check if MCP Tools service is available
    if await mcp_client.health_check():
        log.info("mcp_tools_connected", url=settings.mcp_tools_url)
    else:
        log.warning("mcp_tools_unavailable", url=settings.mcp_tools_url)

    yield

    log.info("orchestrator_shutting_down")
    if response_cache:
        await response_cache.close()
    if conversation_memory:
        await conversation_memory.close()
    if llm_adapter:
        await llm_adapter.close()
    if mcp_client:
        await mcp_client.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="AI Kiosk Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def health_check():
    """Health check endpoint"""
    redis_status = "ok" if conversation_memory else "unavailable"
    return {
        "status": "healthy",
        "service": "orchestrator",
        "version": "0.3.0",
        "checks": {
            "orchestrator": "ok",
            "redis": redis_status,
        },
    }


# ============================================================
# F8: Text endpoint for testing and golden flows
# ============================================================


from pydantic import BaseModel


class TextRequest(BaseModel):
    """Request body for text endpoint."""
    text: str
    session_id: str
    turn_id: str


class TextResponse(BaseModel):
    """Response body for text endpoint."""
    response_text: str
    intent: str
    tool_calls: list[dict] = []
    route_data: dict | None = None
    latency_ms: float = 0.0


@app.post("/text", response_model=TextResponse)
async def process_text(request: TextRequest):
    """Process text input directly (for testing/golden flows).

    This endpoint bypasses the WebSocket and speech pipeline,
    useful for automated testing and golden flow validation.
    """
    import time
    start_time = time.time()

    # F8: Emit turn start trace
    if tracer:
        tracer.set_trace_id(request.session_id)
        tracer.set_turn(request.turn_id)
        tracer.emit(
            Events.TURN_START,
            turn_id=request.turn_id,
            text=request.text,
            source="http",
        )

    # Route the text
    router_result = await _route_transcript(request.text, request.session_id, request.turn_id)

    # F8: Emit turn end trace
    latency_ms = (time.time() - start_time) * 1000
    if tracer:
        tracer.emit(
            Events.TURN_END,
            turn_id=request.turn_id,
            total_latency_ms=latency_ms,
            intent=router_result.intent.value,
            response_length=len(router_result.response_text),
        )

    return TextResponse(
        response_text=router_result.response_text,
        intent=router_result.intent.value,
        tool_calls=[],  # TODO: collect tool calls from router
        route_data=router_result.route_data,
        latency_ms=latency_ms,
    )


# ============================================================
# F6: Barge-in detection helpers
# ============================================================


async def set_playback_active(session_id: str, is_playing: bool) -> None:
    """Set playback state for barge-in detection.

    Updates local state and notifies speech service.
    """
    global playback_state

    playback_state[session_id] = is_playing

    # Notify speech service
    if http_client:
        try:
            await http_client.post(
                f"{settings.speech_service_url}/set-playback-state",
                json={"session_id": session_id, "is_playing": is_playing},
                timeout=2.0,
            )
            log.debug("playback_state_set", session_id=session_id, is_playing=is_playing)
        except Exception as e:
            log.warning("playback_state_notify_failed", error=str(e))


async def _stream_tts_to_websocket(
    websocket: WebSocket,
    text: str,
    session_id: str,
    turn_id: str,
    start_time: float,
) -> bool:
    """Stream TTS audio chunks to websocket progressively.

    Returns True if streaming was successful, False otherwise.
    """
    import json as json_module

    try:
        async with http_client.stream(
            "POST",
            f"{settings.speech_service_url}/synthesize",
            json={
                "text": text,
                "session_id": session_id,
                "turn_id": turn_id,
                "stream": True,
            },
            timeout=60.0,
        ) as response:
            if response.status_code != 200:
                log.warning("tts_stream_failed", status=response.status_code)
                return False

            first_chunk_time = None
            chunk_count = 0

            async for line in response.aiter_lines():
                if not line.strip():
                    continue

                try:
                    chunk_data = json_module.loads(line)
                except json_module.JSONDecodeError:
                    log.warning("tts_chunk_parse_error", line=line[:100])
                    continue

                if first_chunk_time is None:
                    first_chunk_time = time.time()
                    latency_ms = int((first_chunk_time - start_time) * 1000)
                    log.info(
                        "tts_first_chunk",
                        session_id=session_id,
                        turn_id=turn_id,
                        latency_ms=latency_ms,
                    )
                    # F8: Emit TTS first chunk trace
                    if tracer:
                        tracer.emit(
                            Events.TTS_FIRST_CHUNK,
                            turn_id=turn_id,
                            latency_from_start_ms=latency_ms,
                            text_length=len(text),
                        )

                await websocket.send_json({
                    "type": "tts.chunk",
                    "payload": {
                        "audio_data": chunk_data["audio"],
                        "chunk_index": chunk_data["chunk_index"],
                        "total_chunks": chunk_count + 1 if chunk_data["is_last"] else 0,
                        "is_last": chunk_data["is_last"],
                        "turn_id": turn_id,
                    }
                })
                chunk_count += 1

            total_time = int((time.time() - start_time) * 1000)
            log.info(
                "tts_stream_completed",
                session_id=session_id,
                turn_id=turn_id,
                chunk_count=chunk_count,
                total_latency_ms=total_time,
            )
            # F8: Emit TTS end trace
            if tracer:
                tracer.emit(
                    Events.TTS_END,
                    turn_id=turn_id,
                    chunk_count=chunk_count,
                    total_latency_ms=total_time,
                )
            return chunk_count > 0

    except httpx.TimeoutException:
        log.warning("tts_stream_timeout", session_id=session_id)
        return False
    except Exception as e:
        log.warning("tts_stream_error", error=str(e), session_id=session_id)
        return False


async def check_barge_in(
    websocket: WebSocket,
    session_id: str,
    chunk_data: str,
) -> bool:
    """Check for barge-in during playback.

    Returns True if barge-in was detected and handled.
    """
    if not http_client:
        return False

    try:
        response = await http_client.post(
            f"{settings.speech_service_url}/detect-barge-in",
            json={"session_id": session_id, "chunk_data": chunk_data},
            timeout=2.0,
        )

        if response.status_code == 200:
            result = response.json()

            if result.get("detected"):
                log.info(
                    "barge_in_detected",
                    session_id=session_id,
                    speech_duration_ms=result.get("speech_duration_ms"),
                    latency_ms=result.get("latency_ms"),
                )

                # Stop playback
                await set_playback_active(session_id, False)

                # Send stop command to UI
                await websocket.send_json({
                    "type": "control.stop_audio",
                    "payload": {"reason": "barge_in"}
                })

                # Set UI to listening
                await websocket.send_json({
                    "type": "ui.state",
                    "payload": {"state": "listening"}
                })

                return True

    except Exception as e:
        log.warning("barge_in_check_failed", error=str(e))

    return False


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint for Pi ↔ VPS communication
    """
    await websocket.accept()
    client_info = f"{websocket.client.host}:{websocket.client.port}"

    # F6: Generate unique session_id for this connection
    session_id = f"session_{uuid.uuid4().hex[:12]}"

    # F8: Set trace_id for this session
    if tracer:
        tracer.set_trace_id(session_id)
        tracer.emit("session.start", client=client_info)

    log.info("ws_client_connected", client=client_info, session_id=session_id)

    # Create presence manager for this connection
    presence_manager = PresenceManager()

    async def on_presence_change(present: bool):
        await websocket.send_json({
            "type": "presence.update",
            "payload": {
                "present": present,
                "look_direction": presence_manager.state.look_direction,
                "confidence": presence_manager.state.confidence,
            }
        })

    async def on_state_change(state: str):
        await websocket.send_json({
            "type": "ui.state",
            "payload": {"state": state}
        })

    presence_manager.set_callbacks(on_presence_change, on_state_change)

    try:
        # Send initial idle state
        await websocket.send_json({
            "type": "ui.state",
            "payload": {"state": "idle"}
        })

        # Main message loop
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type", "unknown")

                # Only log non-frame messages to reduce noise
                if message_type != "camera.frame":
                    log.info("ws_message_received", type=message_type, client=client_info)

                # Handle different message types
                # F6: Pass session_id to all handlers for memory tracking
                if message_type == "session.start":
                    await handle_session_start(websocket, data, session_id)
                elif message_type == "camera.frame":
                    await handle_camera_frame(websocket, data, presence_manager)
                elif message_type == "audio.utterance":
                    await handle_audio_utterance(websocket, data, presence_manager, session_id)
                elif message_type == "audio.chunk":
                    await handle_audio_chunk(websocket, data, presence_manager, session_id)
                elif message_type == "user.text":
                    await handle_user_text(websocket, data, presence_manager, session_id)
                elif message_type == "control.stop_tts":
                    await handle_stop_tts(websocket, data, session_id)
                elif message_type == "playback.complete":
                    await handle_playback_complete(websocket, data, presence_manager, session_id)
                else:
                    log.warning("ws_unknown_message_type", type=message_type)

            except WebSocketDisconnect:
                log.info("ws_client_disconnected", client=client_info)
                break
            except Exception as e:
                log.error("ws_message_error", error=str(e), client=client_info)
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "Internal error processing message"}
                })

    except Exception as e:
        log.error("ws_connection_error", error=str(e), client=client_info)
    finally:
        presence_manager.cleanup()
        try:
            await websocket.close()
        except:
            pass


async def handle_session_start(websocket: WebSocket, data: dict[str, Any], session_id: str):
    """Handle session start message"""
    payload = data.get("payload", {})
    kiosk_id = payload.get("kiosk_id", "unknown")

    log.info("session_started", kiosk_id=kiosk_id, session_id=session_id)

    # TODO: Create session in Redis
    # TODO: Validate kiosk_id

    # Send welcome state
    await websocket.send_json({
        "type": "ui.state",
        "payload": {"state": "idle"}
    })

    await websocket.send_json({
        "type": "ui.say",
        "payload": {
            "text": "Hola, soy el asistente del kiosco. ¿En qué puedo ayudarte?",
            "turn_id": "welcome"
        }
    })


async def handle_camera_frame(
    websocket: WebSocket,
    data: dict[str, Any],
    presence_manager: PresenceManager,
):
    """Handle camera frame - forward to Vision service for face detection"""
    payload = data.get("payload", {})
    image_data = payload.get("image_data", "")

    if not image_data or not http_client:
        return

    try:
        # Call Vision service
        response = await http_client.post(
            f"{settings.vision_service_url}/detect",
            json={"image_data": image_data},
        )

        if response.status_code == 200:
            result = response.json()
            await presence_manager.update_presence(
                present=result.get("present", False),
                look_direction=result.get("look_direction", 0),
                confidence=result.get("confidence", 0),
            )
        else:
            log.warning("vision_service_error", status=response.status_code)

    except httpx.TimeoutException:
        log.warning("vision_service_timeout")
    except Exception as e:
        log.error("vision_service_error", error=str(e))


async def handle_audio_utterance(
    websocket: WebSocket, data: dict[str, Any], presence_manager: PresenceManager, session_id: str
):
    """Handle complete audio utterance - F3: full speech pipeline."""
    payload = data.get("payload", {})
    turn_id = payload.get("turn_id", "unknown")
    audio_data = payload.get("audio_data", "")

    start_time = time.time()
    log.info("audio_utterance_received", session_id=session_id, turn_id=turn_id)

    # Set UI to thinking while we process
    await websocket.send_json({
        "type": "ui.state",
        "payload": {"state": "thinking"}
    })

    if not http_client or not audio_data:
        await _return_to_listening(websocket, presence_manager)
        return

    try:
        # Step 1: Validate audio format
        validate_response = await http_client.post(
            f"{settings.speech_service_url}/validate-audio",
            json={
                "audio_data": audio_data,
                "session_id": session_id,
                "turn_id": turn_id,
            },
            timeout=10.0,
        )

        if validate_response.status_code != 200 or not validate_response.json().get("valid"):
            log.warning("audio_validation_failed", turn_id=turn_id)
            await _return_to_listening(websocket, presence_manager)
            return

        # Step 2: Process audio through VAD to buffer it
        chunk_response = await http_client.post(
            f"{settings.speech_service_url}/process-chunk",
            json={
                "chunk_data": audio_data,
                "session_id": session_id,
                "turn_id": turn_id,
            },
            timeout=10.0,
        )

        if chunk_response.status_code != 200:
            log.warning("vad_processing_failed", turn_id=turn_id)
            await _return_to_listening(websocket, presence_manager)
            return

        # Step 3: Transcribe the buffered audio
        transcribe_response = await http_client.post(
            f"{settings.speech_service_url}/transcribe",
            json={
                "session_id": session_id,
                "turn_id": turn_id,
            },
            timeout=30.0,
        )

        if transcribe_response.status_code != 200:
            log.warning("asr_failed", turn_id=turn_id)
            await _return_to_listening(websocket, presence_manager)
            return

        transcript_result = transcribe_response.json()
        transcript_text = transcript_result.get("text", "")
        asr_duration = transcript_result.get("duration_ms", 0)

        log.info(
            "asr_completed",
            session_id=session_id,
            turn_id=turn_id,
            text=transcript_text,
            asr_duration_ms=asr_duration,
        )

        # Send transcript to UI
        await websocket.send_json({
            "type": "asr.transcript",
            "payload": {
                "text": transcript_text,
                "turn_id": turn_id,
                "is_final": True,
                "confidence": transcript_result.get("confidence", 0),
            }
        })

        if not transcript_text.strip():
            log.info("empty_transcript", turn_id=turn_id)
            await _return_to_listening(websocket, presence_manager)
            return

        # Step 4: Route transcript to get response (prefer MCP router)
        router_result = await _route_transcript(transcript_text, session_id, turn_id)
        response_text = router_result.response_text

        log.info(
            "router_completed",
            session_id=session_id,
            turn_id=turn_id,
            intent=router_result.intent.value,
            response_length=len(response_text),
            route_data=router_result.route_data is not None,
        )

        # Send route data to UI if available
        if router_result.route_data:
            await websocket.send_json({
                "type": "ui.route",
                "payload": router_result.route_data,
            })

        # Step 5: Synthesize response
        await websocket.send_json({
            "type": "ui.state",
            "payload": {"state": "speaking"}
        })

        # F6: Set playback active for barge-in detection
        await set_playback_active(session_id, True)

        await websocket.send_json({
            "type": "ui.say",
            "payload": {
                "text": response_text,
                "turn_id": turn_id,
            }
        })

        # Stream TTS audio chunks progressively
        tts_success = await _stream_tts_to_websocket(
            websocket=websocket,
            text=response_text,
            session_id=session_id,
            turn_id=turn_id,
            start_time=start_time,
        )

        if not tts_success:
            log.warning("tts_streaming_failed", session_id=session_id, turn_id=turn_id)

    except httpx.TimeoutException:
        log.warning("speech_service_timeout")
    except Exception as e:
        log.error("speech_pipeline_error", error=str(e))

    # Return to appropriate state based on presence
    await _return_to_listening(websocket, presence_manager)


async def handle_audio_chunk(
    websocket: WebSocket, data: dict[str, Any], presence_manager: PresenceManager, session_id: str
):
    """Handle streaming audio chunk - F3: process through VAD, F6: barge-in detection."""
    payload = data.get("payload", {})
    turn_id = payload.get("turn_id", "unknown")
    chunk_data = payload.get("chunk_data", "")
    chunk_index = payload.get("chunk_index", 0)

    if not http_client or not chunk_data:
        return

    # F6: Check for barge-in if playback is active
    if playback_state.get(session_id, False):
        barge_in_detected = await check_barge_in(websocket, session_id, chunk_data)
        if barge_in_detected:
            # Barge-in handled, don't process VAD
            return

    try:
        # Process chunk through VAD
        response = await http_client.post(
            f"{settings.speech_service_url}/process-chunk",
            json={
                "chunk_data": chunk_data,
                "session_id": session_id,
                "turn_id": turn_id,
            },
            timeout=5.0,
        )

        if response.status_code == 200:
            result = response.json()

            # Check if VAD detected end of speech
            if result.get("end_of_speech"):
                log.info(
                    "vad_end_of_speech",
                    session_id=session_id,
                    turn_id=turn_id,
                    speech_duration_ms=result.get("speech_duration_ms"),
                )

                # Notify UI that speech ended
                await websocket.send_json({
                    "type": "vad.end_of_speech",
                    "payload": {
                        "turn_id": turn_id,
                        "speech_duration_ms": result.get("speech_duration_ms", 0),
                    }
                })

                # Now transcribe and respond
                await _process_transcription(websocket, session_id, turn_id, presence_manager)

    except httpx.TimeoutException:
        log.warning("vad_timeout", chunk_index=chunk_index)
    except Exception as e:
        log.error("vad_error", error=str(e), chunk_index=chunk_index)


async def _process_transcription(
    websocket: WebSocket,
    session_id: str,
    turn_id: str,
    presence_manager: PresenceManager,
):
    """Process transcription after VAD detected end of speech."""
    start_time = time.time()

    # F8: Emit turn start trace
    if tracer:
        tracer.set_turn(turn_id)
        tracer.emit(
            Events.TURN_START,
            turn_id=turn_id,
            source="audio",
        )

    # Set UI to thinking
    await websocket.send_json({
        "type": "ui.state",
        "payload": {"state": "thinking"}
    })

    try:
        # Transcribe buffered audio
        transcribe_response = await http_client.post(
            f"{settings.speech_service_url}/transcribe",
            json={
                "session_id": session_id,
                "turn_id": turn_id,
            },
            timeout=30.0,
        )

        if transcribe_response.status_code != 200:
            log.warning("asr_failed", turn_id=turn_id)
            await _return_to_listening(websocket, presence_manager)
            return

        transcript_result = transcribe_response.json()
        transcript_text = transcript_result.get("text", "")
        asr_duration = transcript_result.get("duration_ms", 0)

        log.info(
            "asr_completed",
            session_id=session_id,
            turn_id=turn_id,
            text=transcript_text,
            asr_duration_ms=asr_duration,
        )

        # F8: Emit ASR final trace
        if tracer:
            tracer.emit(
                Events.ASR_FINAL,
                turn_id=turn_id,
                text=transcript_text,
                duration_ms=asr_duration,
                confidence=transcript_result.get("confidence", 0),
            )

        # Send transcript to UI
        await websocket.send_json({
            "type": "asr.transcript",
            "payload": {
                "text": transcript_text,
                "turn_id": turn_id,
                "is_final": True,
                "confidence": transcript_result.get("confidence", 0),
            }
        })

        if not transcript_text.strip():
            await _return_to_listening(websocket, presence_manager)
            return

        # Route and respond (prefer MCP router)
        router_result = await _route_transcript(transcript_text, session_id, turn_id)
        response_text = router_result.response_text

        log.info(
            "router_completed",
            session_id=session_id,
            turn_id=turn_id,
            intent=router_result.intent.value,
            route_data=router_result.route_data is not None,
            response_text_length=len(response_text) if response_text else 0,
        )

        log.info("debug_before_speak", response_text=response_text[:50] if response_text else "EMPTY")

        # Send route data to UI if available
        if router_result.route_data:
            await websocket.send_json({
                "type": "ui.route",
                "payload": router_result.route_data,
            })

        # Speak response
        log.info("debug_sending_speaking_state")
        await websocket.send_json({
            "type": "ui.state",
            "payload": {"state": "speaking"}
        })
        log.info("debug_sent_speaking_state")

        # F6: Set playback active for barge-in detection
        await set_playback_active(session_id, True)

        log.info("debug_sending_ui_say")
        await websocket.send_json({
            "type": "ui.say",
            "payload": {
                "text": response_text,
                "turn_id": turn_id,
            }
        })
        log.info("debug_sent_ui_say")

        # Stream TTS audio chunks progressively
        log.info("debug_starting_tts_stream", speech_url=settings.speech_service_url)
        tts_success = await _stream_tts_to_websocket(
            websocket=websocket,
            text=response_text,
            session_id=session_id,
            turn_id=turn_id,
            start_time=start_time,
        )

        if tts_success:
            # F8: Emit turn end trace
            total_latency_ms = int((time.time() - start_time) * 1000)
            if tracer:
                tracer.emit(
                    Events.TURN_END,
                    turn_id=turn_id,
                    total_latency_ms=total_latency_ms,
                    intent=router_result.intent.value,
                    response_length=len(response_text),
                )
            # Stay in SPEAKING state - UI will signal when playback completes
            return
        else:
            log.warning("tts_streaming_failed", session_id=session_id, turn_id=turn_id)

    except Exception as e:
        log.error("transcription_error", error=str(e))

    # Only return to listening if no TTS was sent (error cases)
    await _return_to_listening(websocket, presence_manager)


async def _route_transcript(transcript: str, session_id: str, turn_id: str = ""):
    """Route transcript using MCP router if available, fallback to basic."""
    global mcp_router, basic_router

    # F8: Set turn for tracing
    if tracer:
        tracer.set_turn(turn_id)

    if mcp_router:
        try:
            result = await mcp_router.route(transcript, session_id)

            # F8: Emit intent detected trace
            if tracer:
                tracer.emit(
                    Events.INTENT_DETECTED,
                    turn_id=turn_id,
                    intent=result.intent.value,
                    confidence=result.confidence,
                    source=result.classification_source,
                )

            return result
        except Exception as e:
            log.warning("mcp_router_failed", error=str(e))
            # Fallback to basic router
            result = basic_router.route(transcript)

            if tracer:
                tracer.emit(
                    Events.INTENT_DETECTED,
                    turn_id=turn_id,
                    intent=result.intent.value,
                    fallback=True,
                )

            return result
    else:
        result = basic_router.route(transcript)

        if tracer:
            tracer.emit(
                Events.INTENT_DETECTED,
                turn_id=turn_id,
                intent=result.intent.value,
                basic_router=True,
            )

        return result


async def _return_to_listening(websocket: WebSocket, presence_manager: PresenceManager):
    """Return UI to appropriate state based on presence."""
    if presence_manager.state.present:
        await websocket.send_json({
            "type": "ui.state",
            "payload": {"state": "listening"}
        })
    else:
        await websocket.send_json({
            "type": "ui.state",
            "payload": {"state": "idle"}
        })


async def handle_user_text(
    websocket: WebSocket, data: dict[str, Any], presence_manager: PresenceManager, session_id: str
):
    """Handle text input - F3: use router for response."""
    payload = data.get("payload", {})
    text = payload.get("text", "")
    turn_id = payload.get("turn_id", f"turn_{uuid.uuid4().hex[:8]}")

    start_time = time.time()
    log.info("user_text_received", text=text)

    # F8: Emit turn start trace
    if tracer:
        tracer.set_turn(turn_id)
        tracer.emit(
            Events.TURN_START,
            turn_id=turn_id,
            text=text,
            source="text",
        )

    await websocket.send_json({
        "type": "ui.state",
        "payload": {"state": "thinking"}
    })

    # Route text to get response (prefer MCP router)
    router_result = await _route_transcript(text, session_id, turn_id)
    response_text = router_result.response_text

    log.info(
        "router_completed",
        text=text,
        intent=router_result.intent.value,
        route_data=router_result.route_data is not None,
    )

    # Send route data to UI if available
    if router_result.route_data:
        await websocket.send_json({
            "type": "ui.route",
            "payload": router_result.route_data,
        })

    await websocket.send_json({
        "type": "ui.state",
        "payload": {"state": "speaking"}
    })

    # F6: Set playback active for barge-in detection
    # Playback will be reset when UI sends playback.complete
    await set_playback_active(session_id, True)

    await websocket.send_json({
        "type": "ui.say",
        "payload": {
            "text": response_text,
            "turn_id": turn_id,
            "session_id": session_id,
        }
    })

    # F8: Emit turn end trace
    total_latency_ms = int((time.time() - start_time) * 1000)
    if tracer:
        tracer.emit(
            Events.TURN_END,
            turn_id=turn_id,
            total_latency_ms=total_latency_ms,
            intent=router_result.intent.value,
            response_length=len(response_text),
        )

    # Don't return to listening - wait for playback.complete from UI
    # The UI should send playback.complete when TTS finishes


async def handle_playback_complete(
    websocket: WebSocket, data: dict[str, Any], presence_manager: PresenceManager, session_id: str
):
    """Handle playback complete notification from UI."""
    payload = data.get("payload", {})
    turn_id = payload.get("turn_id", "unknown")

    log.info("playback_complete", turn_id=turn_id, session_id=session_id)

    # F6: Reset playback state
    await set_playback_active(session_id, False)

    # Now safe to return to listening state
    await _return_to_listening(websocket, presence_manager)


async def handle_stop_tts(websocket: WebSocket, data: dict[str, Any], session_id: str):
    """Handle barge-in / stop TTS"""
    payload = data.get("payload", {})
    reason = payload.get("reason", "unknown")

    log.info("stop_tts_requested", reason=reason, session_id=session_id)

    # F6: Reset playback state
    await set_playback_active(session_id, False)

    # Send stop command back to UI
    await websocket.send_json({
        "type": "control.stop_audio",
        "payload": {}
    })

    # Reset to listening
    await websocket.send_json({
        "type": "ui.state",
        "payload": {"state": "listening"}
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
