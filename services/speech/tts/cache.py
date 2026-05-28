"""TTS cache for common phrases."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional

import structlog

from .base import TTSProvider

log = structlog.get_logger()


@dataclass
class TTSCacheEntry:
    """Cached TTS audio entry."""

    audio_bytes: bytes
    text: str
    created_at: float


@dataclass
class TTSCacheConfig:
    """Configuration for TTS cache."""

    cache_dir: str = "/tmp/tts_cache"
    preload_phrases: list[str] = field(default_factory=list)
    max_entries: int = 100
    persist_to_disk: bool = True


# Common phrases for Spanish kiosk (from router)
DEFAULT_CACHED_PHRASES = [
    # Greetings
    "¡Hola! Soy Sofía, tu asistente del centro comercial. Puedo ayudarte a encontrar tiendas o indicarte cómo llegar a ellas. ¿En qué puedo ayudarte?",
    # Goodbyes
    "¡Hasta luego! Que tengas un buen día.",
    # Help
    "Puedo ayudarte con: ver las tiendas disponibles, darte información sobre una tienda, o indicarte cómo llegar. Por ejemplo, puedes decir: ¿Dónde está Demo Fashion?",
    # List stores
    "Tenemos Demo Fashion, Urban Wear y Nike. ¿Cuál te interesa?",
    # Navigation
    "Para llegar a Demo Fashion: Sigue recto por el pasillo principal y lo encontrarás a tu derecha.",
    "Para llegar a Urban Wear: Sigue recto por el pasillo principal y lo encontrarás a tu derecha.",
    "Para llegar a Nike: Sube al segundo piso por las escaleras mecánicas y está justo al frente.",
    "¿A qué tienda te gustaría ir? Tenemos Demo Fashion, Urban Wear y Nike.",
    # Store info
    "Demo Fashion está en el piso 1. Ropa y accesorios de moda. ¿Te indico cómo llegar?",
    "Urban Wear está en el piso 1. Moda asequible para toda la familia. ¿Te indico cómo llegar?",
    "Nike está en el piso 2. Ropa y calzado deportivo. ¿Te indico cómo llegar?",
    "¿Te gustaría saber más sobre Demo Fashion o que te indique cómo llegar?",
    "¿Te gustaría saber más sobre Urban Wear o que te indique cómo llegar?",
    "¿Te gustaría saber más sobre Nike o que te indique cómo llegar?",
    # Clarifications
    "No estoy segura de haber entendido. Puedes preguntarme por tiendas o cómo llegar a ellas.",
    "No te escuché bien. ¿Puedes repetir?",
]


class CachedTTSProvider(TTSProvider):
    """TTS provider with caching for common phrases."""

    def __init__(
        self,
        provider: TTSProvider,
        config: TTSCacheConfig,
    ):
        """Initialize cached TTS provider.

        Args:
            provider: Underlying TTS provider
            config: Cache configuration
        """
        self.provider = provider
        self.config = config
        self._cache: dict[str, TTSCacheEntry] = {}
        self._cache_dir = Path(config.cache_dir)

    def _cache_key(self, text: str) -> str:
        """Generate cache key from text (normalized + hashed).

        Args:
            text: Input text

        Returns:
            Cache key (16 char hex string)
        """
        normalized = text.strip().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    async def preload_cache(self) -> None:
        """Pre-generate audio for common phrases."""
        phrases = self.config.preload_phrases or DEFAULT_CACHED_PHRASES

        log.info("tts_cache_preloading", count=len(phrases))

        loaded_from_disk = 0
        generated = 0
        failed = 0

        for phrase in phrases:
            key = self._cache_key(phrase)

            # Skip if already in memory
            if key in self._cache:
                continue

            # Try to load from disk first
            if self.config.persist_to_disk:
                cache_file = self._cache_dir / f"{key}.mp3"
                if cache_file.exists():
                    try:
                        audio = cache_file.read_bytes()
                        self._cache[key] = TTSCacheEntry(
                            audio_bytes=audio,
                            text=phrase,
                            created_at=cache_file.stat().st_mtime,
                        )
                        loaded_from_disk += 1
                        continue
                    except Exception as e:
                        log.debug("cache_disk_load_failed", key=key, error=str(e))

            # Generate new audio
            try:
                audio = await self.provider.synthesize(phrase)
                self._add_to_cache(phrase, audio)
                generated += 1
            except Exception as e:
                log.warning(
                    "tts_cache_preload_failed",
                    phrase=phrase[:30],
                    error=str(e),
                )
                failed += 1

        log.info(
            "tts_cache_preloaded",
            total=len(self._cache),
            loaded_from_disk=loaded_from_disk,
            generated=generated,
            failed=failed,
        )

    def _add_to_cache(self, text: str, audio_bytes: bytes) -> None:
        """Add entry to cache.

        Args:
            text: Original text
            audio_bytes: Generated audio
        """
        key = self._cache_key(text)

        self._cache[key] = TTSCacheEntry(
            audio_bytes=audio_bytes,
            text=text,
            created_at=time.time(),
        )

        # Persist to disk if enabled
        if self.config.persist_to_disk:
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                cache_file = self._cache_dir / f"{key}.mp3"
                cache_file.write_bytes(audio_bytes)
            except Exception as e:
                log.debug("cache_disk_save_failed", key=key, error=str(e))

        # Evict old entries if over limit
        if len(self._cache) > self.config.max_entries:
            self._evict_oldest()

    def _evict_oldest(self) -> None:
        """Evict oldest cache entries."""
        if not self._cache:
            return

        # Sort by created_at and remove oldest
        sorted_keys = sorted(
            self._cache.keys(),
            key=lambda k: self._cache[k].created_at,
        )

        # Remove oldest 10%
        to_remove = max(1, len(sorted_keys) // 10)
        for key in sorted_keys[:to_remove]:
            del self._cache[key]

        log.debug("cache_evicted", count=to_remove)

    async def synthesize(self, text: str) -> bytes:
        """Synthesize with cache lookup.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes (from cache or freshly generated)
        """
        key = self._cache_key(text)

        # Check memory cache
        if key in self._cache:
            log.debug("tts_cache_hit", key=key)
            return self._cache[key].audio_bytes

        # Check disk cache
        if self.config.persist_to_disk:
            cache_file = self._cache_dir / f"{key}.mp3"
            if cache_file.exists():
                try:
                    audio = cache_file.read_bytes()
                    self._cache[key] = TTSCacheEntry(
                        audio_bytes=audio,
                        text=text,
                        created_at=cache_file.stat().st_mtime,
                    )
                    log.debug("tts_cache_disk_hit", key=key)
                    return audio
                except Exception as e:
                    log.debug("cache_disk_load_failed", key=key, error=str(e))

        # Cache miss - generate and cache
        log.debug("tts_cache_miss", key=key)
        audio = await self.provider.synthesize(text)
        self._add_to_cache(text, audio)
        return audio

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Streaming synthesis with cache support.

        For cached phrases, yields entire audio at once.

        Args:
            text: Text to synthesize

        Yields:
            Audio chunks
        """
        key = self._cache_key(text)

        # Check if cached
        if key in self._cache:
            log.debug("tts_cache_stream_hit", key=key)
            yield self._cache[key].audio_bytes
            return

        # Check disk cache
        if self.config.persist_to_disk:
            cache_file = self._cache_dir / f"{key}.mp3"
            if cache_file.exists():
                try:
                    audio = cache_file.read_bytes()
                    self._cache[key] = TTSCacheEntry(
                        audio_bytes=audio,
                        text=text,
                        created_at=cache_file.stat().st_mtime,
                    )
                    log.debug("tts_cache_stream_disk_hit", key=key)
                    yield audio
                    return
                except Exception as e:
                    log.debug("cache_disk_load_failed", key=key, error=str(e))

        # Cache miss - stream from provider
        # Note: We can't cache streamed audio easily, so just pass through
        log.debug("tts_cache_stream_miss", key=key)
        async for chunk in self.provider.synthesize_stream(text):
            yield chunk
