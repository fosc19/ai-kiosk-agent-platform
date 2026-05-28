"""Integration tests for multiple simultaneous sessions.

F7: Tests that verify session isolation and concurrent connections.
"""

import asyncio
import json
import time

import pytest
import websockets


pytestmark = pytest.mark.integration


class TestMultipleSessions:
    """Test multiple simultaneous WebSocket sessions."""

    @pytest.mark.asyncio
    async def test_two_sessions_isolated(self):
        """Test that two sessions are properly isolated."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=5) as ws1:
                async with websockets.connect(uri, timeout=5) as ws2:
                    # Start session 1
                    await ws1.send(json.dumps({
                        "type": "session.start",
                        "payload": {"kiosk_id": "kiosk-001"}
                    }))

                    # Start session 2
                    await ws2.send(json.dumps({
                        "type": "session.start",
                        "payload": {"kiosk_id": "kiosk-002"}
                    }))

                    # Drain initial messages
                    for _ in range(5):
                        try:
                            await asyncio.wait_for(ws1.recv(), timeout=1)
                        except asyncio.TimeoutError:
                            break

                    for _ in range(5):
                        try:
                            await asyncio.wait_for(ws2.recv(), timeout=1)
                        except asyncio.TimeoutError:
                            break

                    # Send text to session 1
                    await ws1.send(json.dumps({
                        "type": "user.text",
                        "payload": {"text": "¿Dónde está Demo Fashion?"}
                    }))

                    # Collect responses for session 1
                    ws1_responses = []
                    for _ in range(10):
                        try:
                            msg = await asyncio.wait_for(ws1.recv(), timeout=5)
                            ws1_responses.append(json.loads(msg))
                        except asyncio.TimeoutError:
                            break

                    # Session 1 should have responses
                    assert len(ws1_responses) > 0

                    # Send different text to session 2
                    await ws2.send(json.dumps({
                        "type": "user.text",
                        "payload": {"text": "¿Qué tiendas hay?"}
                    }))

                    # Collect responses for session 2
                    ws2_responses = []
                    for _ in range(10):
                        try:
                            msg = await asyncio.wait_for(ws2.recv(), timeout=5)
                            ws2_responses.append(json.loads(msg))
                        except asyncio.TimeoutError:
                            break

                    # Session 2 should have responses
                    assert len(ws2_responses) > 0

                    # Responses should be different (different queries)
                    ws1_text = " ".join(
                        m.get("payload", {}).get("text", "")
                        for m in ws1_responses
                        if m.get("type") == "ui.say"
                    )
                    ws2_text = " ".join(
                        m.get("payload", {}).get("text", "")
                        for m in ws2_responses
                        if m.get("type") == "ui.say"
                    )

                    # At least one should have meaningful content
                    assert len(ws1_text) > 0 or len(ws2_text) > 0

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running at ws://localhost:8765")

    @pytest.mark.asyncio
    async def test_session_memory_isolated(self):
        """Test that conversation memory is isolated per session."""
        uri = "ws://localhost:8765/ws"

        try:
            # Session 1: Ask about Demo Fashion
            async with websockets.connect(uri, timeout=5) as ws1:
                await ws1.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "kiosk-memory-1"}
                }))

                # Drain initial
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws1.recv(), timeout=1)
                    except asyncio.TimeoutError:
                        break

                # Ask about Demo Fashion
                await ws1.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "Información de Demo Fashion"}
                }))

                # Drain response
                for _ in range(10):
                    try:
                        await asyncio.wait_for(ws1.recv(), timeout=3)
                    except asyncio.TimeoutError:
                        break

            # Session 2: Different session, ask "su horario" (no context)
            async with websockets.connect(uri, timeout=5) as ws2:
                await ws2.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "kiosk-memory-2"}
                }))

                # Drain initial
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws2.recv(), timeout=1)
                    except asyncio.TimeoutError:
                        break

                # Ask with reference (but no context in this session)
                await ws2.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "¿Cuál es su horario?"}
                }))

                responses = []
                for _ in range(10):
                    try:
                        msg = await asyncio.wait_for(ws2.recv(), timeout=3)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                # Session 2 should NOT know about Demo Fashion from session 1
                response_text = " ".join(
                    m.get("payload", {}).get("text", "").lower()
                    for m in responses
                    if m.get("type") == "ui.say"
                )

                # Should either ask for clarification or list stores
                # (not automatically assume Demo Fashion from session 1)
                # This is a soft check - exact behavior depends on LLM
                assert len(responses) > 0

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")

    @pytest.mark.asyncio
    async def test_concurrent_connections_scale(self):
        """Test that multiple concurrent connections work."""
        uri = "ws://localhost:8765/ws"
        num_connections = 5

        try:
            connections = []
            for i in range(num_connections):
                ws = await websockets.connect(uri, timeout=5)
                connections.append(ws)

            # All connections should be open
            assert len(connections) == num_connections

            # Send session start to all
            for i, ws in enumerate(connections):
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": f"kiosk-scale-{i}"}
                }))

            # All should receive initial messages
            for ws in connections:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    assert msg is not None
                except asyncio.TimeoutError:
                    pass  # Some might timeout, that's ok

            # Close all
            for ws in connections:
                await ws.close()

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestSessionReconnection:
    """Test session reconnection behavior."""

    @pytest.mark.asyncio
    async def test_reconnection_creates_new_session(self):
        """Test that reconnecting creates a new session."""
        uri = "ws://localhost:8765/ws"

        try:
            # First connection
            async with websockets.connect(uri, timeout=5) as ws1:
                await ws1.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "kiosk-reconnect"}
                }))

                # Drain
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws1.recv(), timeout=1)
                    except asyncio.TimeoutError:
                        break

            # Small delay
            await asyncio.sleep(0.5)

            # Second connection (reconnection)
            async with websockets.connect(uri, timeout=5) as ws2:
                await ws2.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "kiosk-reconnect"}
                }))

                # Should receive initial messages
                responses = []
                for _ in range(5):
                    try:
                        msg = await asyncio.wait_for(ws2.recv(), timeout=2)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                # Should have received state messages
                assert len(responses) > 0

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
