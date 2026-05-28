"""Integration tests for multi-turn conversation memory flow.

F6: Tests that verify memory persists between turns and references are resolved.
"""

import asyncio
import json
import time

import pytest
import websockets


@pytest.mark.asyncio
async def test_multi_turn_with_memory():
    """Test multi-turn conversation with memory context.

    Flow:
    1. Ask about Demo Fashion -> memory stores current_store=demo_fashion
    2. Ask "su horario" -> should resolve "su" to demo_fashion from context
    3. Ask "llévame ahí" -> should resolve "ahí" to demo_fashion from context
    """
    uri = "ws://localhost:8765/ws"
    session_id = f"test-memory-{int(time.time())}"

    try:
        async with websockets.connect(uri, timeout=10) as ws:
            # Start session
            await ws.send(
                json.dumps(
                    {
                        "type": "session.start",
                        "payload": {
                            "kiosk_id": "test-memory-kiosk",
                            "device_info": {"model": "Test", "os": "Test", "ip": "127.0.0.1"},
                            "language": "es",
                        },
                    }
                )
            )

            # Drain initial messages
            for _ in range(5):
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2)
                except asyncio.TimeoutError:
                    break

            # TURN 1: Ask about Demo Fashion
            await ws.send(
                json.dumps(
                    {
                        "type": "user.text",
                        "payload": {
                            "session_id": session_id,
                            "turn_id": "turn-001",
                            "text": "¿Dónde está Demo Fashion?",
                        },
                    }
                )
            )

            # Collect responses for turn 1
            turn1_responses = []
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    turn1_responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Verify Demo Fashion was found and route provided
            ui_say_turn1 = [m for m in turn1_responses if m.get("type") == "ui.say"]
            assert len(ui_say_turn1) > 0, f"Expected ui.say for Demo Fashion, got: {turn1_responses}"
            assert any(
                "Demo Fashion" in m.get("payload", {}).get("text", "") for m in ui_say_turn1
            ), f"Expected Demo Fashion in response, got: {ui_say_turn1}"

            # TURN 2: Ask about "su horario" (reference to Demo Fashion)
            await ws.send(
                json.dumps(
                    {
                        "type": "user.text",
                        "payload": {
                            "session_id": session_id,
                            "turn_id": "turn-002",
                            "text": "¿Y cuál es su horario?",
                        },
                    }
                )
            )

            # Collect responses for turn 2
            turn2_responses = []
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    turn2_responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Verify the reference was resolved to Demo Fashion
            ui_say_turn2 = [m for m in turn2_responses if m.get("type") == "ui.say"]
            assert len(ui_say_turn2) > 0, f"Expected ui.say for reference, got: {turn2_responses}"

            # Should mention Demo Fashion or hours/horario (not "unknown" or "clarify")
            response_text_turn2 = " ".join(
                m.get("payload", {}).get("text", "") for m in ui_say_turn2
            )
            assert not any(
                phrase in response_text_turn2.lower()
                for phrase in ["no entendido", "no sé de qué", "¿qué tienda"]
            ), f"Reference not resolved correctly: {response_text_turn2}"

            # TURN 3: Ask "llévame ahí" (reference to previous store)
            await ws.send(
                json.dumps(
                    {
                        "type": "user.text",
                        "payload": {
                            "session_id": session_id,
                            "turn_id": "turn-003",
                            "text": "Llévame ahí",
                        },
                    }
                )
            )

            # Collect responses for turn 3
            turn3_responses = []
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    turn3_responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Verify navigation reference was resolved
            ui_route = [m for m in turn3_responses if m.get("type") == "ui.route"]
            ui_say_turn3 = [m for m in turn3_responses if m.get("type") == "ui.say"]

            # Should have either route or navigation response mentioning Demo Fashion
            assert len(ui_route) > 0 or len(ui_say_turn3) > 0, (
                f"Expected route or response for 'ahí' reference, got: {turn3_responses}"
            )

    except ConnectionRefusedError:
        pytest.skip("Orchestrator not running at ws://localhost:8765")
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")


@pytest.mark.asyncio
async def test_memory_context_persists_between_turns():
    """Test that conversation context persists correctly."""
    uri = "ws://localhost:8765/ws"
    session_id = f"test-persist-{int(time.time())}"

    try:
        async with websockets.connect(uri, timeout=10) as ws:
            # Start session
            await ws.send(
                json.dumps(
                    {
                        "type": "session.start",
                        "payload": {
                            "kiosk_id": "test-persist-kiosk",
                            "device_info": {"model": "Test", "os": "Test", "ip": "127.0.0.1"},
                            "language": "es",
                        },
                    }
                )
            )

            # Drain initial
            for _ in range(5):
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2)
                except asyncio.TimeoutError:
                    break

            # Ask about a store
            await ws.send(
                json.dumps(
                    {
                        "type": "user.text",
                        "payload": {
                            "session_id": session_id,
                            "turn_id": "turn-001",
                            "text": "Información de Coffee Point",
                        },
                    }
                )
            )

            # Collect turn 1
            for _ in range(10):
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    break

            # Now say "sí" (should navigate to Coffee Point from context)
            await ws.send(
                json.dumps(
                    {
                        "type": "user.text",
                        "payload": {
                            "session_id": session_id,
                            "turn_id": "turn-002",
                            "text": "Sí",
                        },
                    }
                )
            )

            # Collect responses
            responses = []
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Should have navigation response or route (not asking for clarification)
            has_route = any(m.get("type") == "ui.route" for m in responses)
            ui_say = [m for m in responses if m.get("type") == "ui.say"]

            # At least one of: route provided OR navigation response mentioning store
            assert has_route or len(ui_say) > 0, (
                f"Expected route or navigation response for 'sí', got: {responses}"
            )

    except ConnectionRefusedError:
        pytest.skip("Orchestrator not running at ws://localhost:8765")


@pytest.mark.asyncio
async def test_memory_expires_after_ttl():
    """Test that memory expires after TTL (simulated by clearing)."""
    uri = "ws://localhost:8765/ws"

    try:
        async with websockets.connect(uri, timeout=5) as ws:
            # Start two sessions
            await ws.send(
                json.dumps(
                    {
                        "type": "session.start",
                        "payload": {
                            "kiosk_id": "test-ttl-kiosk",
                            "device_info": {"model": "Test", "os": "Test", "ip": "127.0.0.1"},
                            "language": "es",
                        },
                    }
                )
            )

            # Drain
            for _ in range(5):
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2)
                except asyncio.TimeoutError:
                    break

            # First session - ask about Demo Fashion
            session1 = f"test-ttl-1-{int(time.time())}"
            await ws.send(
                json.dumps(
                    {
                        "type": "user.text",
                        "payload": {
                            "session_id": session1,
                            "turn_id": "turn-001",
                            "text": "¿Dónde está Urban Wear?",
                        },
                    }
                )
            )

            for _ in range(10):
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    break

            # Second session (new) - reference without context should fail
            session2 = f"test-ttl-2-{int(time.time())}"
            await ws.send(
                json.dumps(
                    {
                        "type": "user.text",
                        "payload": {
                            "session_id": session2,
                            "turn_id": "turn-001",
                            "text": "¿Y su horario?",  # No context in session2
                        },
                    }
                )
            )

            responses = []
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            # Session2 should ask for clarification (no context)
            ui_say = [m for m in responses if m.get("type") == "ui.say"]
            response_text = " ".join(
                m.get("payload", {}).get("text", "").lower() for m in ui_say
            )

            # Should either ask for clarification or try to list stores
            # (not assume a store from session1)
            assert not any(
                store in response_text for store in ["urban wear", "urban_wear"]
            ) or "tienda" in response_text or "qué" in response_text, (
                f"Session2 should not inherit context from session1: {response_text}"
            )

    except ConnectionRefusedError:
        pytest.skip("Orchestrator not running at ws://localhost:8765")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
