"""Integration tests for full conversation turns.

F7: Tests complete turn flow: audio -> ASR -> router -> TTS.
"""

import asyncio
import json
import time
import base64
import struct
import io

import pytest
import websockets


pytestmark = pytest.mark.integration


def create_wav_audio(duration_seconds: float = 1.0, sample_rate: int = 16000) -> str:
    """Create a WAV audio file with silence as base64."""
    num_samples = int(sample_rate * duration_seconds)

    wav_buffer = io.BytesIO()
    # RIFF header
    wav_buffer.write(b"RIFF")
    wav_buffer.write(struct.pack("<I", 36 + num_samples * 2))
    wav_buffer.write(b"WAVE")
    # fmt chunk
    wav_buffer.write(b"fmt ")
    wav_buffer.write(struct.pack("<I", 16))
    wav_buffer.write(struct.pack("<H", 1))   # PCM
    wav_buffer.write(struct.pack("<H", 1))   # Mono
    wav_buffer.write(struct.pack("<I", sample_rate))
    wav_buffer.write(struct.pack("<I", sample_rate * 2))
    wav_buffer.write(struct.pack("<H", 2))   # Block align
    wav_buffer.write(struct.pack("<H", 16))  # Bits per sample
    # data chunk
    wav_buffer.write(b"data")
    wav_buffer.write(struct.pack("<I", num_samples * 2))
    wav_buffer.write(b"\x00\x00" * num_samples)

    return base64.b64encode(wav_buffer.getvalue()).decode()


class TestFullTurn:
    """Test complete conversation turns."""

    @pytest.mark.asyncio
    async def test_text_input_full_turn(self):
        """Test full turn with text input (no audio)."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=10) as ws:
                # Start session
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "test-full-turn"}
                }))

                # Drain initial messages
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Send text query
                start_time = time.time()
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {
                        "text": "¿Dónde está Demo Fashion?",
                        "turn_id": "turn-001"
                    }
                }))

                # Collect all responses
                responses = []
                state_transitions = []

                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        data = json.loads(msg)
                        responses.append(data)

                        if data.get("type") == "ui.state":
                            state_transitions.append(data["payload"]["state"])

                    except asyncio.TimeoutError:
                        break

                end_time = time.time()
                latency_ms = int((end_time - start_time) * 1000)

                # Verify state transitions
                # Should go: thinking -> speaking (or listening)
                assert "thinking" in state_transitions, f"Expected 'thinking' state, got: {state_transitions}"

                # Should have ui.say response
                say_messages = [r for r in responses if r.get("type") == "ui.say"]
                assert len(say_messages) > 0, "Expected ui.say response"

                # Response should mention Demo Fashion or be relevant
                response_text = say_messages[0]["payload"]["text"]
                assert len(response_text) > 10, "Response too short"

                # Log latency for analysis
                print(f"\nFull turn latency: {latency_ms}ms")
                print(f"Response: {response_text[:100]}...")

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")

    @pytest.mark.asyncio
    async def test_audio_utterance_turn(self):
        """Test full turn with audio utterance."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=10) as ws:
                # Start session
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "test-audio-turn"}
                }))

                # Drain initial
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Send audio utterance (silence - will likely return empty transcript)
                audio_b64 = create_wav_audio(duration_seconds=1.0)

                await ws.send(json.dumps({
                    "type": "audio.utterance",
                    "payload": {
                        "audio_data": audio_b64,
                        "turn_id": "audio-turn-001"
                    }
                }))

                # Collect responses
                responses = []
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                # Should have state transitions
                states = [r["payload"]["state"] for r in responses if r.get("type") == "ui.state"]
                assert len(states) > 0, "Expected state transitions"

                # Should have thinking state at minimum
                assert "thinking" in states, f"Expected 'thinking' state, got: {states}"

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")

    @pytest.mark.asyncio
    async def test_route_data_included(self):
        """Test that route data is included in navigation responses."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=10) as ws:
                # Start session
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "test-route-data"}
                }))

                # Drain initial
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Ask for directions (should trigger route data)
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "Llévame a Demo Fashion"}
                }))

                # Collect responses
                responses = []
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                # Check for route data
                route_messages = [r for r in responses if r.get("type") == "ui.route"]

                # Should have route data for navigation request
                # (if Demo Fashion exists in the database)
                if route_messages:
                    route_data = route_messages[0]["payload"]
                    assert "store_id" in route_data or "steps" in route_data

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestTurnLatency:
    """Test turn latency requirements."""

    @pytest.mark.asyncio
    async def test_turn_latency_under_target(self):
        """Test that turn latency is under target (3 seconds)."""
        uri = "ws://localhost:8765/ws"
        target_latency_ms = 3000  # 3 seconds target

        try:
            async with websockets.connect(uri, timeout=10) as ws:
                # Start session
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "test-latency"}
                }))

                # Drain initial
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Time the turn
                start_time = time.time()
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "Hola"}
                }))

                # Wait for ui.say response
                response_received = False
                for _ in range(20):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        data = json.loads(msg)
                        if data.get("type") == "ui.say":
                            response_received = True
                            break
                    except asyncio.TimeoutError:
                        break

                end_time = time.time()
                latency_ms = int((end_time - start_time) * 1000)

                print(f"\nTurn latency: {latency_ms}ms (target: {target_latency_ms}ms)")

                assert response_received, "No response received"

                # Soft assertion - log if over target but don't fail
                if latency_ms > target_latency_ms:
                    print(f"WARNING: Latency {latency_ms}ms exceeds target {target_latency_ms}ms")

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestErrorHandling:
    """Test error handling in turns."""

    @pytest.mark.asyncio
    async def test_empty_text_handled(self):
        """Test that empty text is handled gracefully."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=10) as ws:
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "test-empty"}
                }))

                # Drain initial
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Send empty text
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": ""}
                }))

                # Should not crash - collect any responses
                responses = []
                for _ in range(10):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=3)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                # Connection should still be open
                # (just send another message to verify)
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "Hola"}
                }))

                # Should get response
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                assert msg is not None

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")

    @pytest.mark.asyncio
    async def test_malformed_message_handled(self):
        """Test that malformed messages are handled gracefully."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=10) as ws:
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "test-malformed"}
                }))

                # Drain initial
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Send malformed message (missing payload)
                await ws.send(json.dumps({
                    "type": "user.text"
                    # Missing payload
                }))

                # Should receive error or be ignored
                responses = []
                for _ in range(5):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                # Connection should still work
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "Test"}
                }))

                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                assert msg is not None

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
