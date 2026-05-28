"""Conversation Memory - Context persistence between turns.

F6: Provides memory for multi-turn conversations, allowing the bot to:
- Remember the current store being discussed
- Remember the last intent (for "otra tienda", "y que mas")
- Keep a history of turns for context

Supports:
- Redis (production/Docker)
- In-memory dict (development/local)

TTL: 5 minutes (configurable) - session expires after inactivity.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import structlog

# Redis is optional - fallback to in-memory if not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False

log = structlog.get_logger()


@dataclass
class TurnRecord:
    """Record of a single conversation turn."""

    role: str  # "user" or "assistant"
    text: str
    timestamp: float = field(default_factory=time.time)
    intent: Optional[str] = None
    store_id: Optional[str] = None


@dataclass
class ConversationContext:
    """Context state for a conversation session."""

    session_id: str
    current_store_id: Optional[str] = None
    current_store_name: Optional[str] = None
    last_intent: Optional[str] = None
    last_query: Optional[str] = None
    turns: list[TurnRecord] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "session_id": self.session_id,
            "current_store_id": self.current_store_id,
            "current_store_name": self.current_store_name,
            "last_intent": self.last_intent,
            "last_query": self.last_query,
            "turns": [asdict(t) for t in self.turns],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationContext":
        """Create from dictionary (Redis storage)."""
        turns = [TurnRecord(**t) for t in data.get("turns", [])]
        return cls(
            session_id=data["session_id"],
            current_store_id=data.get("current_store_id"),
            current_store_name=data.get("current_store_name"),
            last_intent=data.get("last_intent"),
            last_query=data.get("last_query"),
            turns=turns,
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


class InMemoryStore:
    """Simple in-memory store with TTL support (fallback when Redis unavailable)."""

    def __init__(self, ttl_seconds: int = 300):
        self._store: dict[str, tuple[float, str]] = {}  # key -> (expires_at, value)
        self.ttl_seconds = ttl_seconds

    def _cleanup_expired(self):
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (exp, _) in self._store.items() if exp < now]
        for k in expired:
            del self._store[k]

    def get(self, key: str) -> Optional[str]:
        self._cleanup_expired()
        if key in self._store:
            expires_at, value = self._store[key]
            if expires_at > time.time():
                return value
            del self._store[key]
        return None

    def setex(self, key: str, ttl: int, value: str):
        self._store[key] = (time.time() + ttl, value)

    def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            return 1
        return 0

    def expire(self, key: str, ttl: int) -> bool:
        if key in self._store:
            _, value = self._store[key]
            self._store[key] = (time.time() + ttl, value)
            return True
        return False


class ConversationMemory:
    """Manages conversation context with Redis or in-memory fallback.

    Usage:
        memory = ConversationMemory(redis_url="redis://localhost:6379")
        await memory.connect()

        # Get or create context
        ctx = await memory.get("session123")

        # Update after routing
        await memory.update(
            "session123",
            current_store_id="demo_fashion",
            current_store_name="Demo Fashion",
            last_intent="navigate",
        )

        # Add turn to history
        await memory.add_turn("session123", "user", "llévame a Demo Fashion")
        await memory.add_turn("session123", "assistant", "Para llegar a Demo Fashion...")
    """

    KEY_PREFIX = "conversation:"

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        ttl_seconds: int = 300,  # 5 minutes
        max_turns: int = 10,
    ):
        """Initialize memory manager.

        Args:
            redis_url: Redis connection URL
            ttl_seconds: Time-to-live for session (default: 5 min)
            max_turns: Maximum turns to keep in history (default: 10)
        """
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.max_turns = max_turns
        self._redis = None
        self._memory_store: Optional[InMemoryStore] = None
        self._using_memory = False

    async def connect(self) -> bool:
        """Connect to Redis, fallback to in-memory if unavailable.

        Returns:
            True if connected (Redis or memory), False otherwise
        """
        # Try Redis first
        if REDIS_AVAILABLE:
            try:
                self._redis = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Test connection
                await self._redis.ping()
                log.info("conversation_memory_connected", backend="redis", redis_url=self.redis_url)
                return True
            except Exception as e:
                log.warning("redis_connection_failed", error=str(e))
                self._redis = None

        # Fallback to in-memory
        self._memory_store = InMemoryStore(self.ttl_seconds)
        self._using_memory = True
        log.info("conversation_memory_connected", backend="in-memory")
        return True

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        self._memory_store = None
        log.info("conversation_memory_closed")

    def _key(self, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"{self.KEY_PREFIX}{session_id}"

    def _is_available(self) -> bool:
        """Check if any backend is available."""
        return self._redis is not None or self._memory_store is not None

    async def _store_get(self, key: str) -> Optional[str]:
        """Get value from storage backend."""
        if self._redis:
            return await self._redis.get(key)
        elif self._memory_store:
            return self._memory_store.get(key)
        return None

    async def _store_setex(self, key: str, ttl: int, value: str) -> None:
        """Set value with TTL in storage backend."""
        if self._redis:
            await self._redis.setex(key, ttl, value)
        elif self._memory_store:
            self._memory_store.setex(key, ttl, value)

    async def _store_delete(self, key: str) -> int:
        """Delete key from storage backend."""
        if self._redis:
            return await self._redis.delete(key)
        elif self._memory_store:
            return self._memory_store.delete(key)
        return 0

    async def _store_expire(self, key: str, ttl: int) -> bool:
        """Update TTL for key in storage backend."""
        if self._redis:
            return await self._redis.expire(key, ttl)
        elif self._memory_store:
            return self._memory_store.expire(key, ttl)
        return False

    async def get(self, session_id: str) -> Optional[ConversationContext]:
        """Get conversation context for session.

        Args:
            session_id: Session identifier

        Returns:
            ConversationContext if exists, None otherwise
        """
        if not self._is_available():
            return None

        try:
            data = await self._store_get(self._key(session_id))
            if data:
                ctx = ConversationContext.from_dict(json.loads(data))
                log.debug(
                    "memory_get",
                    session_id=session_id,
                    current_store=ctx.current_store_id,
                    last_intent=ctx.last_intent,
                    turns=len(ctx.turns),
                )
                return ctx
            return None
        except Exception as e:
            log.warning("memory_get_error", session_id=session_id, error=str(e))
            return None

    async def update(
        self,
        session_id: str,
        current_store_id: Optional[str] = None,
        current_store_name: Optional[str] = None,
        last_intent: Optional[str] = None,
        last_query: Optional[str] = None,
    ) -> Optional[ConversationContext]:
        """Update conversation context.

        Only updates fields that are provided (not None).

        Args:
            session_id: Session identifier
            current_store_id: Store ID to set as current
            current_store_name: Store name to set as current
            last_intent: Last classified intent
            last_query: Last user query

        Returns:
            Updated ConversationContext
        """
        if not self._is_available():
            return None

        try:
            # Get existing or create new
            ctx = await self.get(session_id)
            if not ctx:
                ctx = ConversationContext(session_id=session_id)

            # Update only provided fields
            if current_store_id is not None:
                ctx.current_store_id = current_store_id
            if current_store_name is not None:
                ctx.current_store_name = current_store_name
            if last_intent is not None:
                ctx.last_intent = last_intent
            if last_query is not None:
                ctx.last_query = last_query

            ctx.updated_at = time.time()

            # Save with TTL
            await self._store_setex(
                self._key(session_id),
                self.ttl_seconds,
                json.dumps(ctx.to_dict()),
            )

            log.debug(
                "memory_updated",
                session_id=session_id,
                current_store=ctx.current_store_id,
                last_intent=ctx.last_intent,
            )

            return ctx

        except Exception as e:
            log.warning("memory_update_error", session_id=session_id, error=str(e))
            return None

    async def add_turn(
        self,
        session_id: str,
        role: str,
        text: str,
        intent: Optional[str] = None,
        store_id: Optional[str] = None,
    ) -> None:
        """Add a turn to conversation history.

        Args:
            session_id: Session identifier
            role: "user" or "assistant"
            text: Turn text content
            intent: Optional intent for the turn
            store_id: Optional store ID mentioned
        """
        if not self._is_available():
            return

        try:
            ctx = await self.get(session_id)
            if not ctx:
                ctx = ConversationContext(session_id=session_id)

            # Add new turn
            turn = TurnRecord(
                role=role,
                text=text,
                intent=intent,
                store_id=store_id,
            )
            ctx.turns.append(turn)

            # Trim to max turns
            if len(ctx.turns) > self.max_turns:
                ctx.turns = ctx.turns[-self.max_turns :]

            ctx.updated_at = time.time()

            # Save with TTL refresh
            await self._store_setex(
                self._key(session_id),
                self.ttl_seconds,
                json.dumps(ctx.to_dict()),
            )

            log.debug(
                "memory_turn_added",
                session_id=session_id,
                role=role,
                turns=len(ctx.turns),
            )

        except Exception as e:
            log.warning("memory_add_turn_error", session_id=session_id, error=str(e))

    async def clear(self, session_id: str) -> bool:
        """Clear conversation context for session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared, False otherwise
        """
        if not self._is_available():
            return False

        try:
            result = await self._store_delete(self._key(session_id))
            log.info("memory_cleared", session_id=session_id)
            return result > 0
        except Exception as e:
            log.warning("memory_clear_error", session_id=session_id, error=str(e))
            return False

    async def refresh_ttl(self, session_id: str) -> bool:
        """Refresh TTL for session (keep alive).

        Args:
            session_id: Session identifier

        Returns:
            True if refreshed, False otherwise
        """
        if not self._is_available():
            return False

        try:
            return await self._store_expire(self._key(session_id), self.ttl_seconds)
        except Exception as e:
            log.warning("memory_refresh_error", session_id=session_id, error=str(e))
            return False

    def get_context_for_llm(self, ctx: ConversationContext, max_chars: int = 500) -> str:
        """Format context for LLM prompt injection.

        Args:
            ctx: Conversation context
            max_chars: Maximum characters for context summary

        Returns:
            Formatted string for LLM context
        """
        parts = []

        if ctx.current_store_name:
            parts.append(f"Tienda actual: {ctx.current_store_name}")

        if ctx.last_intent:
            intent_map = {
                "navigate": "navegación",
                "store_info": "información de tienda",
                "list_stores": "listar tiendas",
            }
            parts.append(f"Última acción: {intent_map.get(ctx.last_intent, ctx.last_intent)}")

        # Add recent turns
        if ctx.turns:
            recent = ctx.turns[-3:]  # Last 3 turns
            for turn in recent:
                prefix = "Usuario" if turn.role == "user" else "Sofía"
                text = turn.text[:100] + "..." if len(turn.text) > 100 else turn.text
                parts.append(f"{prefix}: {text}")

        context_str = "\n".join(parts)
        if len(context_str) > max_chars:
            context_str = context_str[:max_chars] + "..."

        return context_str
