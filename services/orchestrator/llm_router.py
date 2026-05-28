"""LLM-Only Intent Router - F6 context-aware classification.

Uses LLM for all intent classification, passing conversation context for:
- Multilingual support (Spanish, Catalan, English)
- Reference resolution (pronouns, demonstratives)
- Affirmative responses in context
- No rule-based patterns (removed for maintainability)

Trade-off: All requests go through LLM (~500-1500ms vs ~5ms for rules)
Benefit: Better accuracy, multilingual, contextual understanding
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

from conversation_memory import ConversationContext
from llm_adapter import LLMAdapter, LLMClassification
from policies import PolicyEngine

log = structlog.get_logger()


class Intent(Enum):
    """User intents recognized by the router."""

    GREETING = "greeting"
    LIST_STORES = "list_stores"
    STORE_INFO = "store_info"
    NAVIGATE = "navigate"
    HELP = "help"
    GOODBYE = "goodbye"
    DECLINE = "decline"  # User declines an offer (e.g., "No" to "¿Te indico cómo llegar?")
    CLARIFY = "clarify"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result from intent classification."""

    intent: Intent
    store_query: Optional[str] = None
    confidence: float = 1.0
    source: str = "llm"
    latency_ms: float = 0.0
    reasoning: Optional[str] = None
    info_type: Optional[str] = None  # For store_info: "hours", "location", or "general"
    query_type: Optional[str] = None  # For list_stores: "count" or "list"
    filter: Optional[str] = None  # For list_stores: "open_now", "closed", or null


class LLMIntentClassifier:
    """LLM-only intent classifier with conversation context."""

    def __init__(
        self,
        llm_adapter: LLMAdapter,
        policy_engine: PolicyEngine,
    ):
        """Initialize LLM classifier.

        Args:
            llm_adapter: LLM adapter for classification
            policy_engine: Policy engine for guardrails
        """
        self.llm = llm_adapter
        self.policies = policy_engine

        log.info("llm_classifier_initialized")

    async def classify(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional[ConversationContext] = None,
    ) -> ClassificationResult:
        """Classify intent from transcript using LLM with context.

        Args:
            transcript: User's transcribed speech
            available_stores: List of store names from catalog
            context: Optional conversation context for reference resolution

        Returns:
            ClassificationResult with intent and metadata
        """
        start_time = time.perf_counter()
        text = transcript.strip()

        if not text:
            return ClassificationResult(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                source="empty",
                latency_ms=0.0,
            )

        try:
            # Call LLM with conversation context
            llm_result: LLMClassification = await self.llm.classify_intent(
                transcript=transcript,
                available_stores=available_stores,
                context=context,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Map LLM intent string to Intent enum
            intent_map = {
                "greeting": Intent.GREETING,
                "goodbye": Intent.GOODBYE,
                "list_stores": Intent.LIST_STORES,
                "store_info": Intent.STORE_INFO,
                "navigate": Intent.NAVIGATE,
                "help": Intent.HELP,
                "decline": Intent.DECLINE,
                "clarify": Intent.CLARIFY,
                "unknown": Intent.UNKNOWN,
            }

            intent = intent_map.get(llm_result.intent, Intent.UNKNOWN)

            # Apply policies: validate store query
            if llm_result.store_query:
                valid, clarification = self.policies.validate_store_query(
                    llm_result.store_query,
                    llm_result.confidence,
                )
                if not valid:
                    log.info(
                        "store_query_invalid",
                        store_query=llm_result.store_query,
                        clarification=clarification,
                    )
                    return ClassificationResult(
                        intent=Intent.CLARIFY,
                        confidence=0.8,
                        source="llm+policy",
                        latency_ms=latency_ms,
                        reasoning=clarification,
                    )

            log.info(
                "llm_classification",
                transcript=transcript[:50],
                intent=intent.value,
                store_query=llm_result.store_query,
                confidence=llm_result.confidence,
                latency_ms=round(latency_ms, 2),
                has_context=context is not None,
                context_store=context.current_store_name if context else None,
            )

            return ClassificationResult(
                intent=intent,
                store_query=llm_result.store_query,
                confidence=llm_result.confidence,
                source="llm",
                latency_ms=latency_ms,
                reasoning=llm_result.reasoning,
                info_type=llm_result.info_type,
                query_type=llm_result.query_type,
                filter=llm_result.filter,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            log.error("llm_classification_failed", error=str(e))

            return ClassificationResult(
                intent=Intent.UNKNOWN,
                confidence=0.3,
                source="llm_error",
                latency_ms=latency_ms,
            )


# Alias for backwards compatibility during migration
HybridIntentClassifier = LLMIntentClassifier
