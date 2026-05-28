"""
Presence management - track user presence per WebSocket connection
"""
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Optional
import time

import structlog

log = structlog.get_logger()

PRESENCE_TIMEOUT_SECONDS = 2.0


@dataclass
class PresenceState:
    present: bool = False
    look_direction: float = 0.0
    confidence: float = 0.0
    last_detection_time: float = 0.0
    ui_state: str = "idle"


@dataclass
class PresenceManager:
    """Manages presence state for a single WebSocket connection"""

    state: PresenceState = field(default_factory=PresenceState)
    _timeout_task: Optional[asyncio.Task] = None
    _on_presence_change: Optional[Callable[[bool], Awaitable[None]]] = None
    _on_state_change: Optional[Callable[[str], Awaitable[None]]] = None

    def set_callbacks(
        self,
        on_presence_change: Callable[[bool], Awaitable[None]],
        on_state_change: Callable[[str], Awaitable[None]],
    ):
        """Set callbacks for presence and state changes"""
        self._on_presence_change = on_presence_change
        self._on_state_change = on_state_change

    async def update_presence(
        self,
        present: bool,
        look_direction: float,
        confidence: float,
    ):
        """Update presence state based on vision detection result"""
        was_present = self.state.present
        self.state.present = present
        self.state.look_direction = look_direction
        self.state.confidence = confidence

        if present:
            self.state.last_detection_time = time.time()

            # Cancel existing timeout
            if self._timeout_task:
                self._timeout_task.cancel()
                self._timeout_task = None

            # Transition to listening if was idle
            if not was_present or self.state.ui_state == "idle":
                self.state.ui_state = "listening"
                if self._on_state_change:
                    await self._on_state_change("listening")

                if self._on_presence_change:
                    await self._on_presence_change(True)

                log.info(
                    "presence_detected",
                    direction=look_direction,
                    confidence=confidence,
                )
        else:
            # No face detected
            log.debug("no_presence_detected")

            # Start timeout timer if was present
            if was_present and self._timeout_task is None:
                log.info("presence_lost_starting_timeout", timeout_seconds=PRESENCE_TIMEOUT_SECONDS)
                self._timeout_task = asyncio.create_task(self._presence_timeout())

    async def _presence_timeout(self):
        """Handle presence timeout - return to idle after PRESENCE_TIMEOUT_SECONDS"""
        try:
            await asyncio.sleep(PRESENCE_TIMEOUT_SECONDS)

            # Double check no recent detection
            elapsed = time.time() - self.state.last_detection_time
            if elapsed >= PRESENCE_TIMEOUT_SECONDS:
                log.info("presence_timeout", elapsed_seconds=elapsed)

                self.state.present = False
                self.state.ui_state = "idle"

                if self._on_presence_change:
                    await self._on_presence_change(False)

                if self._on_state_change:
                    await self._on_state_change("idle")

        except asyncio.CancelledError:
            pass  # Timeout was cancelled because presence was re-detected
        finally:
            self._timeout_task = None

    def cleanup(self):
        """Cleanup resources"""
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None
