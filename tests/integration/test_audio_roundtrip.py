"""Integration tests for audio roundtrip: UI -> Orchestrator -> Speech service."""

import asyncio
import base64
import io
import json
import wave

import pytest
import websockets


def create_test_wav_base64(duration_ms: int = 500) -> str:
    """Create test WAV audio encoded as base64."""
    sample_rate = 16000
    num_frames = int(sample_rate * duration_ms / 1000)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * num_frames)

    return base64.b64encode(buffer.getvalue()).decode()


@pytest.mark.asyncio
async def test_audio_utterance_roundtrip():
    """Test sending audio.utterance and receiving response."""
    uri = "ws://localhost:8765/ws"

    try:
        async with websockets.connect(uri, timeout=5) as ws:
            # Send session start
            await ws.send(
                json.dumps(
                    {
                        "type": "session.start",
                        "payload": {
                            "kiosk_id": "test-kiosk",
                            "device_info": {"model": "Test", "os": "Test", "ip": "127.0.0.1"},
                            "language": "es",
                        },
                    }
                )
            )

            # Wait for initial state messages
            messages_received = []
            for _ in range(3):  # Expect: ui.state (idle), ui.state (idle), ui.say (welcome)
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    messages_received.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Verify we received initial state
            assert any(
                m.get("type") == "ui.state" and m.get("payload", {}).get("state") == "idle"
                for m in messages_received
            ), f"Expected ui.state idle, got: {messages_received}"

            # Send audio utterance
            audio_data = create_test_wav_base64(500)
            await ws.send(
                json.dumps(
                    {
                        "type": "audio.utterance",
                        "payload": {
                            "session_id": "test-session",
                            "turn_id": "test-turn-001",
                            "audio_data": audio_data,
                            "sample_rate": 16000,
                        },
                    }
                )
            )

            # Collect responses
            responses = []
            for _ in range(5):  # Expect: thinking, speaking, ui.say, listening
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Verify thinking state was received
            assert any(
                m.get("type") == "ui.state" and m.get("payload", {}).get("state") == "thinking"
                for m in responses
            ), f"Expected ui.state thinking, got: {responses}"

            # Verify listening state was received (final state)
            assert any(
                m.get("type") == "ui.state" and m.get("payload", {}).get("state") == "listening"
                for m in responses
            ), f"Expected ui.state listening, got: {responses}"

    except ConnectionRefusedError:
        pytest.skip("Orchestrator not running at ws://localhost:8765")
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")


@pytest.mark.asyncio
async def test_audio_utterance_validation_response():
    """Test that valid audio receives proper validation response."""
    uri = "ws://localhost:8765/ws"

    try:
        async with websockets.connect(uri, timeout=5) as ws:
            # Send session start
            await ws.send(
                json.dumps(
                    {
                        "type": "session.start",
                        "payload": {
                            "kiosk_id": "test-kiosk-2",
                            "device_info": {"model": "Test", "os": "Test", "ip": "127.0.0.1"},
                            "language": "es",
                        },
                    }
                )
            )

            # Drain initial messages
            for _ in range(3):
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2)
                except asyncio.TimeoutError:
                    break

            # Send audio utterance
            audio_data = create_test_wav_base64(1000)  # 1 second audio
            await ws.send(
                json.dumps(
                    {
                        "type": "audio.utterance",
                        "payload": {
                            "session_id": "test-session-2",
                            "turn_id": "test-turn-002",
                            "audio_data": audio_data,
                            "sample_rate": 16000,
                        },
                    }
                )
            )

            # Collect responses
            responses = []
            for _ in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Verify speaking state was received (indicates valid audio)
            assert any(
                m.get("type") == "ui.state" and m.get("payload", {}).get("state") == "speaking"
                for m in responses
            ), f"Expected ui.state speaking for valid audio, got: {responses}"

            # Verify ui.say was received
            assert any(
                m.get("type") == "ui.say" for m in responses
            ), f"Expected ui.say response, got: {responses}"

    except ConnectionRefusedError:
        pytest.skip("Orchestrator not running at ws://localhost:8765")
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")


@pytest.mark.asyncio
async def test_barge_in_stop_tts():
    """Test barge-in control message."""
    uri = "ws://localhost:8765/ws"

    try:
        async with websockets.connect(uri, timeout=5) as ws:
            # Send session start
            await ws.send(
                json.dumps(
                    {
                        "type": "session.start",
                        "payload": {
                            "kiosk_id": "test-kiosk-3",
                            "device_info": {"model": "Test", "os": "Test", "ip": "127.0.0.1"},
                            "language": "es",
                        },
                    }
                )
            )

            # Drain initial messages
            for _ in range(3):
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2)
                except asyncio.TimeoutError:
                    break

            # Send barge-in control
            await ws.send(
                json.dumps(
                    {
                        "type": "control.stop_tts",
                        "payload": {"reason": "barge_in"},
                    }
                )
            )

            # Collect responses
            responses = []
            for _ in range(3):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Verify stop_audio was received
            assert any(
                m.get("type") == "control.stop_audio" for m in responses
            ), f"Expected control.stop_audio, got: {responses}"

            # Verify listening state was received
            assert any(
                m.get("type") == "ui.state" and m.get("payload", {}).get("state") == "listening"
                for m in responses
            ), f"Expected ui.state listening after barge-in, got: {responses}"

    except ConnectionRefusedError:
        pytest.skip("Orchestrator not running at ws://localhost:8765")
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
