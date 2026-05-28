"""Tests for ConversationMemory - F6 context persistence."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add services path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "orchestrator"))

from conversation_memory import (
    ConversationMemory,
    ConversationContext,
    TurnRecord,
)


class TestConversationContext:
    """Test ConversationContext dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        ctx = ConversationContext(
            session_id="test123",
            current_store_id="demo_fashion",
            current_store_name="Demo Fashion",
            last_intent="navigate",
            last_query="llévame a demo_fashion",
        )

        data = ctx.to_dict()

        assert data["session_id"] == "test123"
        assert data["current_store_id"] == "demo_fashion"
        assert data["current_store_name"] == "Demo Fashion"
        assert data["last_intent"] == "navigate"
        assert data["turns"] == []

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "session_id": "test123",
            "current_store_id": "urban_wear",
            "current_store_name": "Urban Wear",
            "last_intent": "store_info",
            "last_query": "horario de urban wear",
            "turns": [
                {"role": "user", "text": "hola", "timestamp": 1234567890.0},
                {"role": "assistant", "text": "Hola!", "timestamp": 1234567891.0},
            ],
            "created_at": 1234567890.0,
            "updated_at": 1234567891.0,
        }

        ctx = ConversationContext.from_dict(data)

        assert ctx.session_id == "test123"
        assert ctx.current_store_id == "urban_wear"
        assert len(ctx.turns) == 2
        assert ctx.turns[0].role == "user"
        assert ctx.turns[1].text == "Hola!"


class TestConversationMemory:
    """Test ConversationMemory Redis operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.ping = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        redis.aclose = AsyncMock()
        return redis

    @pytest.fixture
    def memory(self, mock_redis):
        """Create ConversationMemory with mock Redis."""
        mem = ConversationMemory(
            redis_url="redis://localhost:6379",
            ttl_seconds=300,
            max_turns=10,
        )
        mem._redis = mock_redis
        return mem

    @pytest.mark.asyncio
    async def test_get_returns_none_when_empty(self, memory, mock_redis):
        """Test get returns None for non-existent session."""
        mock_redis.get.return_value = None

        ctx = await memory.get("session123")

        assert ctx is None
        mock_redis.get.assert_called_once_with("conversation:session123")

    @pytest.mark.asyncio
    async def test_get_returns_context(self, memory, mock_redis):
        """Test get returns ConversationContext."""
        ctx_data = {
            "session_id": "session123",
            "current_store_id": "demo_fashion",
            "current_store_name": "Demo Fashion",
            "last_intent": "navigate",
            "turns": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        mock_redis.get.return_value = json.dumps(ctx_data)

        ctx = await memory.get("session123")

        assert ctx is not None
        assert ctx.session_id == "session123"
        assert ctx.current_store_id == "demo_fashion"
        assert ctx.current_store_name == "Demo Fashion"

    @pytest.mark.asyncio
    async def test_update_creates_new_context(self, memory, mock_redis):
        """Test update creates context if not exists."""
        mock_redis.get.return_value = None

        ctx = await memory.update(
            "session123",
            current_store_id="demo_fashion",
            current_store_name="Demo Fashion",
            last_intent="navigate",
        )

        assert ctx is not None
        assert ctx.current_store_id == "demo_fashion"
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_preserves_existing_fields(self, memory, mock_redis):
        """Test update only changes provided fields."""
        existing = {
            "session_id": "session123",
            "current_store_id": "demo_fashion",
            "current_store_name": "Demo Fashion",
            "last_intent": "navigate",
            "last_query": "where is demo_fashion",
            "turns": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        mock_redis.get.return_value = json.dumps(existing)

        ctx = await memory.update(
            "session123",
            last_intent="store_info",  # Only update intent
        )

        assert ctx.current_store_id == "demo_fashion"  # Preserved
        assert ctx.current_store_name == "Demo Fashion"  # Preserved
        assert ctx.last_intent == "store_info"  # Updated

    @pytest.mark.asyncio
    async def test_add_turn(self, memory, mock_redis):
        """Test adding turns to history."""
        existing = {
            "session_id": "session123",
            "current_store_id": None,
            "turns": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        mock_redis.get.return_value = json.dumps(existing)

        await memory.add_turn("session123", "user", "hola")

        # Check that setex was called with the turn
        call_args = mock_redis.setex.call_args
        saved_data = json.loads(call_args[0][2])
        assert len(saved_data["turns"]) == 1
        assert saved_data["turns"][0]["role"] == "user"
        assert saved_data["turns"][0]["text"] == "hola"

    @pytest.mark.asyncio
    async def test_add_turn_trims_to_max(self, memory, mock_redis):
        """Test that turns are trimmed to max_turns."""
        memory.max_turns = 3

        existing = {
            "session_id": "session123",
            "turns": [
                {"role": "user", "text": "1", "timestamp": 1.0},
                {"role": "user", "text": "2", "timestamp": 2.0},
                {"role": "user", "text": "3", "timestamp": 3.0},
            ],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        mock_redis.get.return_value = json.dumps(existing)

        await memory.add_turn("session123", "user", "4")

        call_args = mock_redis.setex.call_args
        saved_data = json.loads(call_args[0][2])
        assert len(saved_data["turns"]) == 3
        # Oldest should be removed
        assert saved_data["turns"][0]["text"] == "2"
        assert saved_data["turns"][2]["text"] == "4"

    @pytest.mark.asyncio
    async def test_clear(self, memory, mock_redis):
        """Test clearing a session."""
        result = await memory.clear("session123")

        assert result is True
        mock_redis.delete.assert_called_once_with("conversation:session123")

    def test_get_context_for_llm(self, memory):
        """Test formatting context for LLM prompt."""
        ctx = ConversationContext(
            session_id="test",
            current_store_id="demo_fashion",
            current_store_name="Demo Fashion",
            last_intent="navigate",
            turns=[
                TurnRecord(role="user", text="hola"),
                TurnRecord(role="assistant", text="Hola, soy el asistente del kiosco"),
            ],
        )

        llm_context = memory.get_context_for_llm(ctx)

        assert "Tienda actual: Demo Fashion" in llm_context
        assert "Última acción: navegación" in llm_context
        assert "Usuario: hola" in llm_context
        assert "Asistente: Hola, soy el asistente del kiosco" in llm_context

    @pytest.mark.asyncio
    async def test_no_redis_returns_none(self):
        """Test that operations return None when Redis is not connected."""
        memory = ConversationMemory()
        memory._redis = None

        ctx = await memory.get("session123")
        assert ctx is None

        result = await memory.update("session123", current_store_id="demo_fashion")
        assert result is None

        result = await memory.clear("session123")
        assert result is False
