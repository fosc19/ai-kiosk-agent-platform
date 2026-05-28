"""Tests for WebSocket message handlers in Orchestrator.

F7: Unit tests for all WebSocket message types.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

import pytest

# Add services path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "orchestrator"))

from presence import PresenceManager, PresenceState


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.sent_messages = []
        self.closed = False
        self.client = MagicMock()
        self.client.host = "127.0.0.1"
        self.client.port = 12345

    async def accept(self):
        pass

    async def send_json(self, data: dict):
        self.sent_messages.append(data)

    async def receive_json(self):
        raise NotImplementedError("Use receive_queue for testing")

    async def close(self):
        self.closed = True

    def get_sent_types(self) -> list[str]:
        """Get list of sent message types."""
        return [m.get("type") for m in self.sent_messages]

    def get_sent_by_type(self, msg_type: str) -> list[dict]:
        """Get all sent messages of a specific type."""
        return [m for m in self.sent_messages if m.get("type") == msg_type]

    def clear_sent(self):
        """Clear sent messages for next test."""
        self.sent_messages = []


class TestPresenceManager:
    """Test PresenceManager behavior."""

    @pytest.mark.asyncio
    async def test_initial_state_is_idle(self):
        """Test that initial state is idle and not present."""
        manager = PresenceManager()

        assert manager.state.present is False
        assert manager.state.ui_state == "idle"

    @pytest.mark.asyncio
    async def test_presence_detected_transitions_to_listening(self):
        """Test presence detection triggers listening state."""
        manager = PresenceManager()
        state_changes = []

        async def on_state_change(state: str):
            state_changes.append(state)

        async def on_presence_change(present: bool):
            pass

        manager.set_callbacks(on_presence_change, on_state_change)

        await manager.update_presence(present=True, look_direction=0.0, confidence=0.9)

        assert manager.state.present is True
        assert manager.state.ui_state == "listening"
        assert "listening" in state_changes

    @pytest.mark.asyncio
    async def test_presence_lost_starts_timeout(self):
        """Test that losing presence starts a timeout."""
        manager = PresenceManager()

        async def noop(x):
            pass

        manager.set_callbacks(noop, noop)

        # First detect presence
        await manager.update_presence(present=True, look_direction=0.0, confidence=0.9)
        assert manager.state.present is True

        # Then lose presence
        await manager.update_presence(present=False, look_direction=0.0, confidence=0.0)

        # Timeout task should be created
        assert manager._timeout_task is not None

        # Cleanup
        manager.cleanup()

    @pytest.mark.asyncio
    async def test_presence_redetected_cancels_timeout(self):
        """Test that re-detecting presence cancels timeout."""
        manager = PresenceManager()

        async def noop(x):
            pass

        manager.set_callbacks(noop, noop)

        # Detect -> lose -> re-detect
        await manager.update_presence(present=True, look_direction=0.0, confidence=0.9)
        await manager.update_presence(present=False, look_direction=0.0, confidence=0.0)
        assert manager._timeout_task is not None

        await manager.update_presence(present=True, look_direction=0.0, confidence=0.9)

        # Timeout should be cancelled
        assert manager._timeout_task is None
        assert manager.state.present is True

    @pytest.mark.asyncio
    async def test_look_direction_is_stored(self):
        """Test that look direction is stored correctly."""
        manager = PresenceManager()

        async def noop(x):
            pass

        manager.set_callbacks(noop, noop)

        await manager.update_presence(present=True, look_direction=-0.5, confidence=0.8)

        assert manager.state.look_direction == -0.5
        assert manager.state.confidence == 0.8

    def test_cleanup_cancels_timeout(self):
        """Test that cleanup cancels pending timeout."""
        manager = PresenceManager()
        mock_task = MagicMock()
        manager._timeout_task = mock_task

        manager.cleanup()

        mock_task.cancel.assert_called_once()
        assert manager._timeout_task is None


class TestSessionStartHandler:
    """Test session.start message handler."""

    @pytest.mark.asyncio
    async def test_session_start_sends_idle_state(self):
        """Test that session start sends idle state."""
        ws = MockWebSocket()

        # Import handler directly
        from main import handle_session_start

        await handle_session_start(
            ws,
            {
                "type": "session.start",
                "payload": {"kiosk_id": "test-kiosk-001"},
            },
            "session_123"
        )

        # Should send idle state and welcome message
        sent_types = ws.get_sent_types()
        assert "ui.state" in sent_types
        assert "ui.say" in sent_types

        # Verify idle state
        state_msgs = ws.get_sent_by_type("ui.state")
        assert any(m["payload"]["state"] == "idle" for m in state_msgs)

    @pytest.mark.asyncio
    async def test_session_start_sends_welcome_message(self):
        """Test that session start sends welcome message."""
        ws = MockWebSocket()

        from main import handle_session_start

        await handle_session_start(
            ws,
            {
                "type": "session.start",
                "payload": {"kiosk_id": "test-kiosk-001"},
            },
            "session_123"
        )

        say_msgs = ws.get_sent_by_type("ui.say")
        assert len(say_msgs) > 0
        assert "asistente del kiosco" in say_msgs[0]["payload"]["text"]


class TestCameraFrameHandler:
    """Test camera.frame message handler."""

    @pytest.mark.asyncio
    async def test_camera_frame_calls_vision_service(self):
        """Test that camera frame forwards to vision service."""
        from main import handle_camera_frame

        ws = MockWebSocket()
        presence_manager = PresenceManager()

        async def noop(x):
            pass

        presence_manager.set_callbacks(noop, noop)

        # Mock http_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "present": True,
            "look_direction": 0.0,
            "confidence": 0.95,
        }

        with patch("main.http_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            await handle_camera_frame(
                ws,
                {
                    "type": "camera.frame",
                    "payload": {"image_data": "base64_image_data_here"},
                },
                presence_manager,
            )

            # Should call vision service
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/detect" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_camera_frame_empty_data_skipped(self):
        """Test that empty image data is skipped."""
        from main import handle_camera_frame

        ws = MockWebSocket()
        presence_manager = PresenceManager()

        with patch("main.http_client") as mock_client:
            mock_client.post = AsyncMock()

            await handle_camera_frame(
                ws,
                {
                    "type": "camera.frame",
                    "payload": {"image_data": ""},  # Empty
                },
                presence_manager,
            )

            # Should NOT call vision service
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_camera_frame_updates_presence_state(self):
        """Test that camera frame updates presence state."""
        from main import handle_camera_frame

        ws = MockWebSocket()
        presence_manager = PresenceManager()

        async def noop(x):
            pass

        presence_manager.set_callbacks(noop, noop)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "present": True,
            "look_direction": -0.3,
            "confidence": 0.85,
        }

        with patch("main.http_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            await handle_camera_frame(
                ws,
                {
                    "type": "camera.frame",
                    "payload": {"image_data": "base64_data"},
                },
                presence_manager,
            )

            # Presence should be updated
            assert presence_manager.state.present is True
            assert presence_manager.state.look_direction == -0.3


class TestStopTtsHandler:
    """Test control.stop_tts (barge-in) message handler."""

    @pytest.mark.asyncio
    async def test_stop_tts_sends_stop_audio(self):
        """Test that stop TTS sends stop audio command."""
        ws = MockWebSocket()

        from main import handle_stop_tts

        with patch("main.set_playback_active", new_callable=AsyncMock):
            await handle_stop_tts(
                ws,
                {
                    "type": "control.stop_tts",
                    "payload": {"reason": "barge_in"},
                },
                "session_123"
            )

        sent_types = ws.get_sent_types()
        assert "control.stop_audio" in sent_types
        assert "ui.state" in sent_types

        # Should transition to listening
        state_msgs = ws.get_sent_by_type("ui.state")
        assert any(m["payload"]["state"] == "listening" for m in state_msgs)

    @pytest.mark.asyncio
    async def test_stop_tts_resets_playback_state(self):
        """Test that stop TTS resets playback state."""
        ws = MockWebSocket()

        from main import handle_stop_tts

        with patch("main.set_playback_active", new_callable=AsyncMock) as mock_set:
            await handle_stop_tts(
                ws,
                {
                    "type": "control.stop_tts",
                    "payload": {"reason": "user_requested"},
                },
                "session_123"
            )

            # Should reset playback state to False
            mock_set.assert_called_once_with("session_123", False)


class TestPlaybackCompleteHandler:
    """Test playback.complete message handler."""

    @pytest.mark.asyncio
    async def test_playback_complete_returns_to_listening(self):
        """Test that playback complete returns to listening state."""
        ws = MockWebSocket()
        presence_manager = PresenceManager()
        presence_manager.state.present = True

        from main import handle_playback_complete

        with patch("main.set_playback_active", new_callable=AsyncMock):
            await handle_playback_complete(
                ws,
                {
                    "type": "playback.complete",
                    "payload": {"turn_id": "turn_001"},
                },
                presence_manager,
                "session_123"
            )

        state_msgs = ws.get_sent_by_type("ui.state")
        assert len(state_msgs) > 0
        # Should go to listening if present
        assert state_msgs[0]["payload"]["state"] == "listening"

    @pytest.mark.asyncio
    async def test_playback_complete_returns_to_idle_when_not_present(self):
        """Test that playback complete returns to idle if not present."""
        ws = MockWebSocket()
        presence_manager = PresenceManager()
        presence_manager.state.present = False

        from main import handle_playback_complete

        with patch("main.set_playback_active", new_callable=AsyncMock):
            await handle_playback_complete(
                ws,
                {
                    "type": "playback.complete",
                    "payload": {"turn_id": "turn_001"},
                },
                presence_manager,
                "session_123"
            )

        state_msgs = ws.get_sent_by_type("ui.state")
        assert len(state_msgs) > 0
        # Should go to idle if not present
        assert state_msgs[0]["payload"]["state"] == "idle"


class TestUserTextHandler:
    """Test user.text message handler."""

    @pytest.mark.asyncio
    async def test_user_text_sets_thinking_state(self):
        """Test that user text sets thinking state."""
        ws = MockWebSocket()
        presence_manager = PresenceManager()

        from main import handle_user_text

        # Mock the router
        mock_result = MagicMock()
        mock_result.response_text = "Test response"
        mock_result.intent = MagicMock()
        mock_result.intent.value = "test"
        mock_result.route_data = None

        with patch("main._route_transcript", new_callable=AsyncMock, return_value=mock_result):
            with patch("main.set_playback_active", new_callable=AsyncMock):
                await handle_user_text(
                    ws,
                    {
                        "type": "user.text",
                        "payload": {"text": "Hola"},
                    },
                    presence_manager,
                    "session_123"
                )

        sent_types = ws.get_sent_types()
        assert "ui.state" in sent_types

        # First state should be thinking
        state_msgs = ws.get_sent_by_type("ui.state")
        assert state_msgs[0]["payload"]["state"] == "thinking"

    @pytest.mark.asyncio
    async def test_user_text_sends_response(self):
        """Test that user text routes and sends response."""
        ws = MockWebSocket()
        presence_manager = PresenceManager()

        from main import handle_user_text

        mock_result = MagicMock()
        mock_result.response_text = "Hola, soy el asistente del kiosco"
        mock_result.intent = MagicMock()
        mock_result.intent.value = "greeting"
        mock_result.route_data = None

        with patch("main._route_transcript", new_callable=AsyncMock, return_value=mock_result):
            with patch("main.set_playback_active", new_callable=AsyncMock):
                await handle_user_text(
                    ws,
                    {
                        "type": "user.text",
                        "payload": {"text": "Hola"},
                    },
                    presence_manager,
                    "session_123"
                )

        # Should send ui.say with response
        say_msgs = ws.get_sent_by_type("ui.say")
        assert len(say_msgs) > 0
        assert say_msgs[0]["payload"]["text"] == "Hola, soy el asistente del kiosco"

    @pytest.mark.asyncio
    async def test_user_text_sends_route_data(self):
        """Test that user text sends route data when available."""
        ws = MockWebSocket()
        presence_manager = PresenceManager()

        from main import handle_user_text

        mock_result = MagicMock()
        mock_result.response_text = "Te llevo a Demo Fashion"
        mock_result.intent = MagicMock()
        mock_result.intent.value = "navigate"
        mock_result.route_data = {
            "store_id": "demo_fashion",
            "store_name": "Demo Fashion",
            "steps": ["Gira a la derecha", "Sigue recto"],
        }

        with patch("main._route_transcript", new_callable=AsyncMock, return_value=mock_result):
            with patch("main.set_playback_active", new_callable=AsyncMock):
                await handle_user_text(
                    ws,
                    {
                        "type": "user.text",
                        "payload": {"text": "Llévame a Demo Fashion"},
                    },
                    presence_manager,
                    "session_123"
                )

        # Should send ui.route
        route_msgs = ws.get_sent_by_type("ui.route")
        assert len(route_msgs) > 0
        assert route_msgs[0]["payload"]["store_id"] == "demo_fashion"


class TestReturnToListening:
    """Test _return_to_listening helper."""

    @pytest.mark.asyncio
    async def test_return_to_listening_when_present(self):
        """Test returning to listening when user is present."""
        ws = MockWebSocket()
        presence_manager = PresenceManager()
        presence_manager.state.present = True

        from main import _return_to_listening

        await _return_to_listening(ws, presence_manager)

        state_msgs = ws.get_sent_by_type("ui.state")
        assert len(state_msgs) == 1
        assert state_msgs[0]["payload"]["state"] == "listening"

    @pytest.mark.asyncio
    async def test_return_to_idle_when_not_present(self):
        """Test returning to idle when user is not present."""
        ws = MockWebSocket()
        presence_manager = PresenceManager()
        presence_manager.state.present = False

        from main import _return_to_listening

        await _return_to_listening(ws, presence_manager)

        state_msgs = ws.get_sent_by_type("ui.state")
        assert len(state_msgs) == 1
        assert state_msgs[0]["payload"]["state"] == "idle"


class TestBargeInDetection:
    """Test barge-in detection during playback."""

    @pytest.mark.asyncio
    async def test_check_barge_in_sends_stop_on_detection(self):
        """Test that barge-in detection sends stop command."""
        ws = MockWebSocket()

        from main import check_barge_in

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "detected": True,
            "speech_duration_ms": 200,
            "latency_ms": 150,
        }

        with patch("main.http_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            with patch("main.set_playback_active", new_callable=AsyncMock):
                result = await check_barge_in(ws, "session_123", "audio_chunk_data")

        assert result is True
        assert "control.stop_audio" in ws.get_sent_types()

    @pytest.mark.asyncio
    async def test_check_barge_in_returns_false_when_not_detected(self):
        """Test that no barge-in returns False."""
        ws = MockWebSocket()

        from main import check_barge_in

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "detected": False,
        }

        with patch("main.http_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            result = await check_barge_in(ws, "session_123", "audio_chunk_data")

        assert result is False
        assert len(ws.sent_messages) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
