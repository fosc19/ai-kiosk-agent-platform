"""LLM Response Cache for Orchestrator.

Caches LLM-generated responses to reduce latency and API costs.
Uses Redis for distributed caching with fallback to in-memory.

Cache key structure:
- llm_response:{hash(transcript + context_key)}

TTL strategy:
- Greeting/goodbye: 24h (very stable)
- Help: 24h (stable)
- Store info: 1h (may change)
- Navigation: 30min (route-specific)
- Unknown/clarify: 5min (context-dependent)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

import structlog
import redis.asyncio as redis

log = structlog.get_logger()


@dataclass
class CachedResponse:
    """Cached LLM response with metadata."""

    response_text: str
    intent: str
    store_id: Optional[str] = None
    route_data: Optional[Dict[str, Any]] = None
    created_at: float = 0.0
    hit_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CachedResponse":
        return cls(**data)


# TTL by intent (seconds)
INTENT_TTL = {
    "greeting": 86400,      # 24 hours
    "goodbye": 86400,       # 24 hours
    "help": 86400,          # 24 hours
    "list_stores": 3600,    # 1 hour
    "store_info": 3600,     # 1 hour
    "navigate": 1800,       # 30 minutes
    "clarify": 300,         # 5 minutes
    "unknown": 300,         # 5 minutes
}

DEFAULT_TTL = 1800  # 30 minutes


class ResponseCache:
    """Cache for LLM responses with Redis backend."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        prefix: str = "llm_response",
        enabled: bool = True,
    ):
        self.redis_url = redis_url
        self.prefix = prefix
        self.enabled = enabled
        self._redis: Optional[redis.Redis] = None
        self._local_cache: Dict[str, CachedResponse] = {}
        self._local_ttl: Dict[str, float] = {}

    async def connect(self) -> None:
        """Connect to Redis."""
        if not self.enabled:
            return

        try:
            self._redis = redis.from_url(self.redis_url)
            await self._redis.ping()
            log.info("response_cache_connected", redis_url=self.redis_url)
        except Exception as e:
            log.warning("response_cache_redis_unavailable", error=str(e))
            self._redis = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    def _generate_key(
        self,
        transcript: str,
        current_store_id: Optional[str] = None,
    ) -> str:
        """Generate cache key from transcript and context.

        Uses normalized transcript (lowercase, stripped) plus context
        to ensure consistent cache hits.
        """
        normalized = transcript.lower().strip()
        context_key = current_store_id or "none"

        # Hash to keep keys short
        content = f"{normalized}:{context_key}"
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]

        return f"{self.prefix}:{hash_value}"

    async def get(
        self,
        transcript: str,
        current_store_id: Optional[str] = None,
    ) -> Optional[CachedResponse]:
        """Get cached response for transcript.

        Args:
            transcript: User's utterance
            current_store_id: Current store context (if any)

        Returns:
            CachedResponse if found and valid, None otherwise
        """
        if not self.enabled:
            return None

        key = self._generate_key(transcript, current_store_id)

        # Try Redis first
        if self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    response = CachedResponse.from_dict(json.loads(data))
                    response.hit_count += 1

                    # Update hit count (fire and forget)
                    await self._redis.set(
                        key,
                        json.dumps(response.to_dict()),
                        xx=True,  # Only if exists
                        keepttl=True,  # Keep existing TTL
                    )

                    log.debug(
                        "response_cache_hit",
                        key=key,
                        intent=response.intent,
                        hit_count=response.hit_count,
                    )
                    return response
            except Exception as e:
                log.warning("response_cache_redis_error", error=str(e))

        # Fallback to local cache
        if key in self._local_cache:
            ttl = self._local_ttl.get(key, 0)
            if time.time() < ttl:
                response = self._local_cache[key]
                response.hit_count += 1
                log.debug(
                    "response_cache_hit_local",
                    key=key,
                    intent=response.intent,
                )
                return response
            else:
                # Expired
                del self._local_cache[key]
                del self._local_ttl[key]

        log.debug("response_cache_miss", key=key)
        return None

    async def set(
        self,
        transcript: str,
        response: CachedResponse,
        current_store_id: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> None:
        """Cache a response.

        Args:
            transcript: User's utterance
            response: Response to cache
            current_store_id: Current store context
            ttl: Override TTL (uses intent-based TTL if None)
        """
        if not self.enabled:
            return

        key = self._generate_key(transcript, current_store_id)

        # Determine TTL
        if ttl is None:
            ttl = INTENT_TTL.get(response.intent, DEFAULT_TTL)

        response.created_at = time.time()
        data = json.dumps(response.to_dict())

        # Try Redis
        if self._redis:
            try:
                await self._redis.setex(key, ttl, data)
                log.debug(
                    "response_cache_set",
                    key=key,
                    intent=response.intent,
                    ttl=ttl,
                )
                return
            except Exception as e:
                log.warning("response_cache_redis_set_error", error=str(e))

        # Fallback to local cache
        self._local_cache[key] = response
        self._local_ttl[key] = time.time() + ttl

        # Limit local cache size
        if len(self._local_cache) > 100:
            self._cleanup_local()

        log.debug("response_cache_set_local", key=key, intent=response.intent)

    def _cleanup_local(self) -> None:
        """Remove expired entries from local cache."""
        now = time.time()
        expired = [k for k, ttl in self._local_ttl.items() if now >= ttl]

        for key in expired:
            del self._local_cache[key]
            del self._local_ttl[key]

        # If still too large, remove oldest
        if len(self._local_cache) > 100:
            sorted_keys = sorted(
                self._local_cache.keys(),
                key=lambda k: self._local_cache[k].created_at,
            )
            for key in sorted_keys[:50]:  # Remove oldest 50
                del self._local_cache[key]
                del self._local_ttl[key]

    async def invalidate(
        self,
        transcript: str,
        current_store_id: Optional[str] = None,
    ) -> None:
        """Invalidate a cached response."""
        key = self._generate_key(transcript, current_store_id)

        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception:
                pass

        self._local_cache.pop(key, None)
        self._local_ttl.pop(key, None)

        log.debug("response_cache_invalidated", key=key)

    async def clear(self) -> None:
        """Clear all cached responses."""
        if self._redis:
            try:
                # Find all keys with our prefix
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor,
                        match=f"{self.prefix}:*",
                        count=100,
                    )
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                log.warning("response_cache_clear_error", error=str(e))

        self._local_cache.clear()
        self._local_ttl.clear()

        log.info("response_cache_cleared")

    async def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "enabled": self.enabled,
            "redis_connected": self._redis is not None,
            "local_entries": len(self._local_cache),
        }

        if self._redis:
            try:
                # Count keys
                cursor = 0
                count = 0
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor,
                        match=f"{self.prefix}:*",
                        count=100,
                    )
                    count += len(keys)
                    if cursor == 0:
                        break
                stats["redis_entries"] = count
            except Exception:
                stats["redis_entries"] = -1

        return stats


# Global instance
_response_cache: Optional[ResponseCache] = None


async def get_response_cache(
    redis_url: str = "redis://localhost:6379",
) -> ResponseCache:
    """Get or create response cache singleton."""
    global _response_cache

    if _response_cache is None:
        _response_cache = ResponseCache(redis_url=redis_url)
        await _response_cache.connect()

    return _response_cache
