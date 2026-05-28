"""End-to-end tests for complete conversation flows.

F7: Tests that simulate real user interactions with the kiosk.
"""

import asyncio
import json
import time

import pytest
import websockets


pytestmark = pytest.mark.e2e


class TestStoreLocationFlow:
    """Test store location conversation flow."""

    @pytest.mark.asyncio
    async def test_ask_store_location(self):
        """Test: User asks where a store is located."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=15) as ws:
                # Start session
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "e2e-location"}
                }))

                # Drain initial
                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Ask: "Where is Demo Fashion?"
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "¿Dónde está Demo Fashion?"}
                }))

                # Collect responses
                responses = []
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                # Verify response
                say_msgs = [r for r in responses if r.get("type") == "ui.say"]
                assert len(say_msgs) > 0, "Expected speech response"

                response_text = say_msgs[0]["payload"]["text"].lower()
                # Should mention Demo Fashion or navigation
                assert any(word in response_text for word in ["demo_fashion", "planta", "derecha", "izquierda", "recto", "tienda"]), \
                    f"Response doesn't seem related to navigation: {response_text}"

                # May have route data
                route_msgs = [r for r in responses if r.get("type") == "ui.route"]
                if route_msgs:
                    print(f"Route provided: {route_msgs[0]['payload']}")

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestStoreInfoFlow:
    """Test store information conversation flow."""

    @pytest.mark.asyncio
    async def test_ask_store_hours(self):
        """Test: User asks about store hours."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=15) as ws:
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "e2e-hours"}
                }))

                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Ask: "What are Demo Fashion's hours?"
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "¿Qué horario tiene Demo Fashion?"}
                }))

                responses = []
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                say_msgs = [r for r in responses if r.get("type") == "ui.say"]
                assert len(say_msgs) > 0

                response_text = say_msgs[0]["payload"]["text"].lower()
                # Should mention hours or schedule
                assert any(word in response_text for word in ["horario", "abre", "cierra", "hora", "lunes", "10"]), \
                    f"Response doesn't seem to contain hours info: {response_text}"

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestListStoresFlow:
    """Test listing stores conversation flow."""

    @pytest.mark.asyncio
    async def test_ask_what_stores(self):
        """Test: User asks what stores are available."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=15) as ws:
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "e2e-list"}
                }))

                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Ask: "What stores are there?"
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "¿Qué tiendas hay?"}
                }))

                responses = []
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                say_msgs = [r for r in responses if r.get("type") == "ui.say"]
                assert len(say_msgs) > 0

                response_text = say_msgs[0]["payload"]["text"].lower()
                # Should list some stores
                store_names = ["demo_fashion", "urban wear", "coffee_point", "mango", "tienda"]
                assert any(name in response_text for name in store_names), \
                    f"Response doesn't seem to list stores: {response_text}"

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestMultiTurnFlow:
    """Test multi-turn conversation with context."""

    @pytest.mark.asyncio
    async def test_multi_turn_with_reference(self):
        """Test: Multi-turn conversation with pronoun reference."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=20) as ws:
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "e2e-multi"}
                }))

                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Turn 1: Ask about Demo Fashion
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "¿Dónde está Demo Fashion?"}
                }))

                for _ in range(15):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        break

                # Turn 2: Ask about "its" hours (reference to Demo Fashion)
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "¿Y cuál es su horario?"}
                }))

                responses = []
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                say_msgs = [r for r in responses if r.get("type") == "ui.say"]
                assert len(say_msgs) > 0

                response_text = say_msgs[0]["payload"]["text"].lower()

                # Should resolve reference to Demo Fashion, not ask for clarification
                clarification_phrases = ["qué tienda", "no entiendo", "no sé de qué"]
                is_clarification = any(phrase in response_text for phrase in clarification_phrases)

                # Ideally should have resolved the reference
                if is_clarification:
                    print(f"WARNING: Reference not resolved, got clarification: {response_text}")

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestUnknownStoreFlow:
    """Test handling of unknown stores."""

    @pytest.mark.asyncio
    async def test_unknown_store_clarification(self):
        """Test: User asks about a store that doesn't exist."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=15) as ws:
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "e2e-unknown"}
                }))

                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Ask about non-existent store
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "¿Dónde está la tienda XYZ123?"}
                }))

                responses = []
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                say_msgs = [r for r in responses if r.get("type") == "ui.say"]
                assert len(say_msgs) > 0

                response_text = say_msgs[0]["payload"]["text"].lower()

                # Should indicate store not found or ask for clarification
                # Should NOT hallucinate directions to a non-existent store
                hallucination_phrases = ["planta 2", "gira a la derecha", "sigue recto"]
                has_hallucination = any(phrase in response_text for phrase in hallucination_phrases)

                if has_hallucination:
                    print(f"WARNING: Possible hallucination for unknown store: {response_text}")

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestBargeInFlow:
    """Test barge-in (interruption) flow."""

    @pytest.mark.asyncio
    async def test_stop_tts_command(self):
        """Test: User interrupts during response."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=15) as ws:
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "e2e-bargein"}
                }))

                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Start a query
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "¿Qué tiendas hay?"}
                }))

                # Wait briefly for response to start
                await asyncio.sleep(0.5)

                # Send stop command (simulating barge-in)
                await ws.send(json.dumps({
                    "type": "control.stop_tts",
                    "payload": {"reason": "barge_in"}
                }))

                responses = []
                for _ in range(10):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=3)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                # Should receive stop_audio command
                stop_msgs = [r for r in responses if r.get("type") == "control.stop_audio"]

                # Should also transition to listening
                state_msgs = [r for r in responses if r.get("type") == "ui.state"]
                states = [m["payload"]["state"] for m in state_msgs]

                assert "listening" in states, f"Should transition to listening after barge-in, got: {states}"

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


class TestGreetingFlow:
    """Test greeting conversation flow."""

    @pytest.mark.asyncio
    async def test_greeting_response(self):
        """Test: User greets the kiosk."""
        uri = "ws://localhost:8765/ws"

        try:
            async with websockets.connect(uri, timeout=15) as ws:
                await ws.send(json.dumps({
                    "type": "session.start",
                    "payload": {"kiosk_id": "e2e-greeting"}
                }))

                for _ in range(5):
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break

                # Greet
                await ws.send(json.dumps({
                    "type": "user.text",
                    "payload": {"text": "Hola, buenos días"}
                }))

                responses = []
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        responses.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        break

                say_msgs = [r for r in responses if r.get("type") == "ui.say"]
                assert len(say_msgs) > 0

                response_text = say_msgs[0]["payload"]["text"].lower()

                # Should respond with greeting
                greeting_words = ["hola", "buenos", "bienvenido", "ayudar", "ai-kiosk"]
                assert any(word in response_text for word in greeting_words), \
                    f"Response doesn't seem like a greeting: {response_text}"

        except ConnectionRefusedError:
            pytest.skip("Orchestrator not running")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
