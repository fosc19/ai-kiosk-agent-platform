"""Intent router using MCP Tools for data access with LLM-only classification.

This router combines:
- LLM-only intent classification with conversation context (F6)
- MCP Tools service for real store data
- Policy engine for guardrails (no hallucination)
- F6: Conversation memory for context between turns
- F6: LLM handles references, pronouns, multilingual via context

Note: Reference resolution is now handled by the LLM via conversation context
(see llm_adapter.py get_classification_prompt)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import structlog

from llm_router import LLMIntentClassifier, Intent, ClassificationResult
from llm_adapter import LLMAdapter
from mcp_client import MCPToolsClient
from policies import PolicyEngine
from conversation_memory import ConversationMemory, ConversationContext
from response_cache import ResponseCache, CachedResponse

# F8: Tracing
try:
    from tracing_setup import setup_tracing, Events, OrchestratorTracer
    tracer: OrchestratorTracer | None = setup_tracing()
except ImportError:
    tracer = None
    Events = None

log = structlog.get_logger()


def is_store_open(opening_hours: str, current_time: Optional[datetime] = None) -> bool:
    """Check if a store is currently open based on its opening hours.

    Args:
        opening_hours: Opening hours string (e.g., "10:00-22:00", "09:00-21:00")
        current_time: Time to check (defaults to now)

    Returns:
        True if the store is currently open, False otherwise
    """
    if not opening_hours:
        return False

    if current_time is None:
        current_time = datetime.now()

    # Parse opening hours format: "HH:MM-HH:MM"
    match = re.match(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", opening_hours.strip())
    if not match:
        log.warning("invalid_opening_hours_format", opening_hours=opening_hours)
        return False

    open_hour, open_min, close_hour, close_min = map(int, match.groups())

    current_minutes = current_time.hour * 60 + current_time.minute
    open_minutes = open_hour * 60 + open_min
    close_minutes = close_hour * 60 + close_min

    return open_minutes <= current_minutes < close_minutes


@dataclass
class RouterResult:
    """Result from intent routing."""

    intent: Intent
    params: dict
    response_text: str
    confidence: float = 1.0
    route_data: Optional[dict] = None  # For navigation responses
    classification_source: str = "rules"  # "rules" or "llm"
    latency_ms: float = 0.0


class MCPRouter:
    """Intent router that uses MCP Tools for data with LLM classification.

    F6: Uses conversation context for LLM classification.
    References and pronouns are resolved by the LLM using context.
    """

    def __init__(
        self,
        mcp_client: MCPToolsClient,
        llm_adapter: Optional[LLMAdapter] = None,
        use_llm: bool = True,  # Default to True since LLM-only
        memory: Optional[ConversationMemory] = None,
        response_cache: Optional[ResponseCache] = None,
    ):
        """Initialize router with MCP client and LLM.

        Args:
            mcp_client: Client for MCP Tools service
            llm_adapter: LLM adapter for classification (required for F6)
            use_llm: Whether to use LLM (default True, kept for compatibility)
            memory: F6 - Conversation memory for context persistence
            response_cache: Optional cache for LLM responses
        """
        self.mcp = mcp_client
        self.llm = llm_adapter

        # F6: Memory for conversation context
        self.memory = memory

        # Performance: Response cache for LLM responses
        self.cache = response_cache

        # Initialize empty - will be populated when catalog is loaded
        self._store_cache: list[dict] = []
        self._store_names: list[str] = []
        self._store_ids: set[str] = set()

        # Policy engine - initialized with empty catalog
        self.policies = PolicyEngine(
            catalog_store_ids=set(),
            catalog_store_names=set(),
        )

        # LLM classifier - will be initialized once we have catalog
        self.classifier: Optional[LLMIntentClassifier] = None

        log.info(
            "mcp_router_initialized",
            has_llm=llm_adapter is not None,
            has_memory=memory is not None,
            has_cache=response_cache is not None,
        )

    async def _ensure_catalog_loaded(self) -> None:
        """Ensure store catalog is loaded from MCP."""
        if self._store_cache:
            return  # Already loaded

        try:
            result = await self.mcp.list_stores()
            stores = result.get("stores", [])

            self._store_cache = stores
            self._store_names = [s["name"] for s in stores]
            self._store_ids = {s["id"] for s in stores}

            # Update policy engine
            self.policies.update_catalog(
                store_ids=self._store_ids,
                store_names=set(self._store_names),
            )

            # Initialize LLM classifier
            if self.llm:
                self.classifier = LLMIntentClassifier(
                    llm_adapter=self.llm,
                    policy_engine=self.policies,
                )

            log.info("catalog_loaded", store_count=len(stores))

        except Exception as e:
            log.warning("catalog_load_failed", error=str(e))
            # Continue with empty catalog

    async def route(self, transcript: str, session_id: str = "unknown") -> RouterResult:
        """Route transcript to intent and generate response.

        F6: Uses conversation memory and LLM-based classification.
        References and pronouns are resolved by the LLM using context.

        Args:
            transcript: User's transcribed speech
            session_id: Session ID for logging

        Returns:
            RouterResult with intent, params, and response
        """
        start_time = time.perf_counter()
        text = transcript.strip()

        if not text:
            return RouterResult(
                intent=Intent.UNKNOWN,
                params={},
                response_text="No te escuché bien. ¿Puedes repetir?",
                confidence=0.0,
            )

        # Ensure catalog is loaded
        await self._ensure_catalog_loaded()

        # Performance: Check response cache first (for context-independent queries)
        # Only cache simple queries without store context dependency
        if self.cache:
            cached = await self.cache.get(text, current_store_id=None)
            if cached:
                log.info(
                    "cache_hit",
                    intent=cached.intent,
                    hit_count=cached.hit_count,
                    latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
                )
                return RouterResult(
                    intent=Intent[cached.intent.upper()],
                    params={"store_id": cached.store_id} if cached.store_id else {},
                    response_text=cached.response_text,
                    confidence=1.0,
                    route_data=cached.route_data,
                    classification_source="cache",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

        # F6: Get conversation context for LLM
        context: Optional[ConversationContext] = None
        if self.memory:
            context = await self.memory.get(session_id)
            if context:
                log.debug(
                    "context_loaded",
                    session_id=session_id,
                    current_store=context.current_store_name,
                    last_intent=context.last_intent,
                    turns=len(context.turns),
                )

        # Log the query
        try:
            await self.mcp.log_event(session_id, "query", {"text": transcript})
        except Exception as e:
            log.warning("failed_to_log_event", error=str(e))

        # Step 1: Classify intent using LLM with conversation context
        # LLM handles references, pronouns, and multilingual via context
        if self.classifier:
            log.debug("using_llm_classifier", stores=self._store_names, has_context=context is not None)
            classification = await self.classifier.classify(
                transcript=text,
                available_stores=self._store_names,
                context=context,
            )
        else:
            # Fallback to simple rules (should rarely happen)
            log.warning("using_rules_fallback", reason="classifier is None")
            classification = self._classify_by_rules(text.lower())

        log.info(
            "intent_classified",
            intent=classification.intent.value,
            confidence=classification.confidence,
            source=classification.source,
            store_query=classification.store_query,
            reasoning=classification.reasoning,
            latency_ms=round(classification.latency_ms, 2),
        )

        # Step 2: Handle intent with MCP data and generate LLM response
        # Note: All intents (including greeting, goodbye, help) now go through LLM
        result = await self._handle_intent(
            classification=classification,
            original_text=text,
            session_id=session_id,
            context=context,
        )

        result.latency_ms = (time.perf_counter() - start_time) * 1000
        result.classification_source = classification.source

        # F6: Update conversation memory with results
        if self.memory:
            store_id = result.params.get("store_id")
            store_name = result.params.get("store_name")

            # Update context
            await self.memory.update(
                session_id=session_id,
                current_store_id=store_id,
                current_store_name=store_name,
                last_intent=result.intent.value,
                last_query=transcript,
            )

            # Add turns to history
            await self.memory.add_turn(
                session_id=session_id,
                role="user",
                text=transcript,
                intent=result.intent.value,
                store_id=store_id,
            )
            await self.memory.add_turn(
                session_id=session_id,
                role="assistant",
                text=result.response_text,
                intent=result.intent.value,
                store_id=store_id,
            )

        log.info(
            "route_complete",
            intent=result.intent.value,
            has_route=result.route_data is not None,
            total_latency_ms=round(result.latency_ms, 2),
        )

        # Performance: Cache the response for future similar queries
        # Cache stable intents (greeting, goodbye, help, list_stores)
        if self.cache and result.intent.value in {"greeting", "goodbye", "help", "list_stores"}:
            cached_response = CachedResponse(
                response_text=result.response_text,
                intent=result.intent.value,
                store_id=result.params.get("store_id"),
                route_data=result.route_data,
            )
            await self.cache.set(text, cached_response)
            log.debug("response_cached", intent=result.intent.value)

        return result

    def _classify_by_rules(self, text: str) -> ClassificationResult:
        """Simple rule-based classification (fallback when no LLM).

        Note: This is a basic fallback. For full functionality with
        context-aware classification, ensure LLM adapter is configured.
        """
        text = text.lower()
        greeting_words = ["hola", "buenas", "buenos", "hey", "saludos"]
        goodbye_words = ["adiós", "adios", "chao", "hasta luego", "bye"]
        list_words = ["tiendas", "lista", "qué hay", "cuáles", "cuales"]
        navigate_words = ["dónde", "donde", "cómo llego", "como llego", "llevar", "llévame", "llevame", "ir a", "llegar", "vamos a", "quiero ir"]
        info_words = ["información", "informacion", "info", "horario", "abre", "cierra"]
        help_words = ["ayuda", "help", "qué puedes", "que puedes"]

        def matches(words):
            return any(w in text for w in words)

        if matches(greeting_words):
            return ClassificationResult(intent=Intent.GREETING, confidence=0.95, source="rules_fallback")

        if matches(goodbye_words):
            return ClassificationResult(intent=Intent.GOODBYE, confidence=0.95, source="rules_fallback")

        if matches(help_words):
            return ClassificationResult(intent=Intent.HELP, confidence=0.95, source="rules_fallback")

        if matches(list_words):
            return ClassificationResult(intent=Intent.LIST_STORES, confidence=0.9, source="rules_fallback")

        if matches(navigate_words):
            store = self._extract_store_from_text(text)
            return ClassificationResult(
                intent=Intent.NAVIGATE,
                store_query=store,
                confidence=0.85 if store else 0.7,
                source="rules_fallback",
            )

        if matches(info_words):
            store = self._extract_store_from_text(text)
            return ClassificationResult(
                intent=Intent.STORE_INFO,
                store_query=store,
                confidence=0.8 if store else 0.6,
                source="rules_fallback",
            )

        # Check if just a store mention
        store = self._extract_store_from_text(text)
        if store:
            return ClassificationResult(
                intent=Intent.STORE_INFO,
                store_query=store,
                confidence=0.7,
                source="rules_fallback",
            )

        return ClassificationResult(intent=Intent.UNKNOWN, confidence=0.5, source="rules_fallback")

    def _extract_store_from_text(self, text: str) -> Optional[str]:
        """Extract store name from text."""
        text_lower = text.lower()
        for name in self._store_names:
            if name.lower() in text_lower:
                return name
            # Handle Urban Wear variations
            if name.lower() == "urban wear" and ("h y m" in text_lower or "hache" in text_lower):
                return name
        return None

    async def _handle_intent(
        self,
        classification: ClassificationResult,
        original_text: str,
        session_id: str,
        context: Optional[ConversationContext] = None,
    ) -> RouterResult:
        """Handle classified intent with MCP data and LLM-generated response."""
        intent = classification.intent

        if intent == Intent.LIST_STORES:
            return await self._handle_list_stores(
                query_type=classification.query_type,
                filter_type=classification.filter,
                original_text=original_text,
                context=context,
            )

        if intent == Intent.NAVIGATE:
            return await self._handle_navigate(
                classification.store_query or original_text,
                session_id,
                original_text=original_text,
                context=context,
            )

        if intent == Intent.STORE_INFO:
            return await self._handle_store_info(
                classification.store_query or original_text,
                info_type=classification.info_type,
                original_text=original_text,
                context=context,
            )

        # For simple intents (greeting, goodbye, help, clarify, decline, unknown)
        # Use LLM to generate natural response
        return await self._handle_simple_intent(
            intent=intent,
            original_text=original_text,
            context=context,
            confidence=classification.confidence,
        )

    async def _handle_simple_intent(
        self,
        intent: Intent,
        original_text: str,
        context: Optional[ConversationContext] = None,
        confidence: float = 1.0,
    ) -> RouterResult:
        """Handle simple intents (greeting, goodbye, help, clarify, decline, unknown) with LLM.

        Args:
            intent: The classified intent
            original_text: User's original text
            context: Optional conversation context
            confidence: Classification confidence

        Returns:
            RouterResult with LLM-generated response
        """
        if not self.llm:
            # Fallback if no LLM adapter
            fallback_responses = {
                Intent.GREETING: "Hola, soy Sofía. ¿En qué puedo ayudarte?",
                Intent.GOODBYE: "Hasta luego, que tengas un buen día.",
                Intent.HELP: "Puedo ayudarte a encontrar tiendas y cómo llegar a ellas.",
                Intent.DECLINE: "De acuerdo. ¿Puedo ayudarte con algo más?",
                Intent.CLARIFY: "No entendí bien. ¿Puedes repetir?",
                Intent.UNKNOWN: "No estoy segura de entender. ¿Puedes preguntarme de otra forma?",
            }
            return RouterResult(
                intent=intent,
                params={},
                response_text=fallback_responses.get(intent, "¿Puedo ayudarte?"),
                confidence=confidence,
            )

        # Use LLM to generate natural response
        try:
            response = await self.llm.generate_response(
                intent=intent.value,
                context={
                    "user_query": original_text,
                    "available_stores": self._store_names,
                    "data": {},  # No MCP data for simple intents
                },
                conversation_context=context,
            )

            return RouterResult(
                intent=intent,
                params={},
                response_text=response.text,
                confidence=confidence,
            )
        except Exception as e:
            log.error("llm_response_error", intent=intent.value, error=str(e))
            return RouterResult(
                intent=intent,
                params={},
                response_text="Lo siento, ha ocurrido un error. ¿Puedes repetir?",
                confidence=0.5,
            )

    async def _generate_llm_response(
        self,
        intent: Intent,
        data: dict,
        original_text: str,
        context: Optional[ConversationContext] = None,
        params: Optional[dict] = None,
        confidence: float = 1.0,
    ) -> RouterResult:
        """Generate LLM response with MCP data.

        Args:
            intent: The intent type
            data: MCP data to include in prompt
            original_text: User's original text
            context: Conversation context
            params: Optional params for RouterResult
            confidence: Confidence score

        Returns:
            RouterResult with LLM-generated response
        """
        if not self.llm:
            # Fallback if no LLM
            return RouterResult(
                intent=intent,
                params=params or {},
                response_text="No puedo generar una respuesta en este momento.",
                confidence=0.5,
            )

        try:
            response = await self.llm.generate_response(
                intent=intent.value,
                context={
                    "user_query": original_text,
                    "available_stores": self._store_names,
                    "data": data,
                },
                conversation_context=context,
            )

            log.info(
                "llm_response_generated",
                intent=intent.value,
                response_length=len(response.text),
            )

            return RouterResult(
                intent=intent,
                params=params or {},
                response_text=response.text,
                confidence=confidence,
            )
        except Exception as e:
            log.error("llm_response_generation_error", intent=intent.value, error=str(e))
            return RouterResult(
                intent=intent,
                params=params or {},
                response_text="Lo siento, ha ocurrido un error. ¿Puedes repetir?",
                confidence=0.5,
            )

    async def _handle_list_stores(
        self,
        query_type: Optional[str] = None,
        filter_type: Optional[str] = None,
        original_text: str = "",
        context: Optional[ConversationContext] = None,
    ) -> RouterResult:
        """Handle list stores intent using MCP and LLM-generated response.

        Args:
            query_type: Type of query - "count" for number of stores, "list" for store names
            filter_type: Filter - "open_now" for open stores, "closed" for closed stores
            original_text: User's original query
            context: Conversation context
        """
        try:
            result = await self.mcp.list_stores()
            stores = result.get("stores", [])

            if not stores:
                # Use LLM even for empty results
                return await self._generate_llm_response(
                    intent=Intent.LIST_STORES,
                    data={"stores": [], "count": 0, "message": "no_stores_available"},
                    original_text=original_text,
                    context=context,
                )

            # Apply filter if specified
            final_stores = stores
            filter_applied = None

            if filter_type == "open_now":
                filtered_stores = []
                for store in stores:
                    try:
                        info = await self.mcp.get_store_info(store["id"])
                        if info.get("found"):
                            opening_hours = info.get("opening_hours", "")
                            if is_store_open(opening_hours):
                                filtered_stores.append(store)
                    except Exception:
                        pass
                final_stores = filtered_stores
                filter_applied = "open_now"

            elif filter_type == "closed":
                filtered_stores = []
                for store in stores:
                    try:
                        info = await self.mcp.get_store_info(store["id"])
                        if info.get("found"):
                            opening_hours = info.get("opening_hours", "")
                            if not is_store_open(opening_hours):
                                filtered_stores.append(store)
                    except Exception:
                        pass
                final_stores = filtered_stores
                filter_applied = "closed"

            # Build data for LLM
            store_data = {
                "stores": final_stores,
                "count": len(final_stores),
                "query_type": query_type,
                "filter": filter_applied,
                "all_stores_count": len(stores),
            }

            # Generate LLM response
            return await self._generate_llm_response(
                intent=Intent.LIST_STORES,
                data=store_data,
                original_text=original_text,
                context=context,
                params={"stores": [s["id"] for s in final_stores]},
            )

        except Exception as e:
            log.error("list_stores_failed", error=str(e))
            return RouterResult(
                intent=Intent.LIST_STORES,
                params={},
                response_text="Lo siento, no puedo acceder a la lista de tiendas en este momento.",
                confidence=0.5,
            )

    async def _handle_navigate(
        self,
        query: str,
        session_id: str,
        original_text: str = "",
        context: Optional[ConversationContext] = None,
    ) -> RouterResult:
        """Handle navigation intent using MCP and LLM-generated response."""
        try:
            # F8: Trace tool call
            tool_span_id = None
            if tracer:
                tool_span_id = tracer.new_span()
                tracer.emit(
                    Events.TOOL_CALL_START,
                    span_id=tool_span_id,
                    tool_name="resolve_store",
                    args={"query": query},
                )

            # Try to resolve the store from the query
            resolve_result = await self.mcp.resolve_store(query)

            # F8: Trace tool result
            if tracer:
                tracer.emit(
                    Events.TOOL_CALL_END,
                    span_id=tool_span_id,
                    tool_name="resolve_store",
                    success=resolve_result.get("found", False),
                )

            if not resolve_result.get("found"):
                # No confident match - use LLM for clarification
                alternatives = resolve_result.get("alternatives", [])
                return await self._generate_llm_response(
                    intent=Intent.CLARIFY,
                    data={
                        "reason": "store_not_found",
                        "query": query,
                        "alternatives": [a["name"] for a in alternatives[:3]] if alternatives else [],
                    },
                    original_text=original_text,
                    context=context,
                    confidence=0.7,
                )

            store = resolve_result["store"]
            store_id = store["id"]

            # Validate store against policies
            policy_check = self.policies.check_response("", "navigate", store_id)
            if not policy_check.passed:
                log.warning("policy_violation_navigate", store_id=store_id)
                return await self._generate_llm_response(
                    intent=Intent.CLARIFY,
                    data={"reason": "policy_violation", "store": store["name"]},
                    original_text=original_text,
                    context=context,
                    confidence=0.5,
                )

            # F8: Trace get_route call
            route_span_id = None
            if tracer:
                route_span_id = tracer.new_span()
                tracer.emit(
                    Events.TOOL_CALL_START,
                    span_id=route_span_id,
                    tool_name="get_route",
                    args={"store_id": store_id},
                )

            # Get route
            route_result = await self.mcp.get_route(store_id)

            # F8: Trace tool result
            if tracer:
                tracer.emit(
                    Events.TOOL_CALL_END,
                    span_id=route_span_id,
                    tool_name="get_route",
                    success=route_result.get("found", False),
                )

            store_name = route_result.get("store_name", store["name"])
            steps = route_result.get("steps", [])

            # Log route shown event
            try:
                await self.mcp.log_event(session_id, "route_shown", {
                    "store_id": store_id,
                    "steps": len(steps),
                })
            except Exception:
                pass

            # Build data for LLM
            navigate_data = {
                "store": store,
                "store_name": store_name,
                "route_found": route_result.get("found", False),
                "steps": steps,
            }

            # Generate LLM response
            result = await self._generate_llm_response(
                intent=Intent.NAVIGATE,
                data=navigate_data,
                original_text=original_text,
                context=context,
                params={"store_id": store_id, "store_name": store_name},
            )
            result.route_data = route_result
            return result

        except Exception as e:
            log.error("navigation_failed", error=str(e))
            return RouterResult(
                intent=Intent.NAVIGATE,
                params={},
                response_text="Lo siento, no puedo obtener la ruta en este momento.",
                confidence=0.5,
            )

    async def _handle_store_info(
        self,
        query: str,
        info_type: Optional[str] = None,
        original_text: str = "",
        context: Optional[ConversationContext] = None,
    ) -> RouterResult:
        """Handle store info intent using MCP and LLM-generated response.

        Args:
            query: Store name or query
            info_type: Type of info requested - "hours", "location", or "general" (default)
            original_text: User's original query
            context: Conversation context
        """
        try:
            resolve_result = await self.mcp.resolve_store(query)

            if not resolve_result.get("found"):
                return await self._generate_llm_response(
                    intent=Intent.CLARIFY,
                    data={"reason": "store_not_found", "query": query},
                    original_text=original_text,
                    context=context,
                    confidence=0.7,
                )

            store = resolve_result["store"]
            info = await self.mcp.get_store_info(store["id"])

            # Build data for LLM - only include relevant fields based on info_type
            store_name = info.get("name", store["name"]) if info.get("found") else store["name"]
            store_data = {
                "name": store_name,
                "info_type": info_type,
            }

            # Only include data relevant to the question
            if info.get("found"):
                if info_type == "hours":
                    store_data["hours"] = info.get("opening_hours", "")
                elif info_type == "location":
                    store_data["location"] = info.get("location", "")
                elif info_type == "phone":
                    store_data["phone"] = info.get("phone", "")
                else:
                    # For general queries (like "puedo tomar café"), only include location
                    # User can ask follow-up for hours/details
                    store_data["location"] = info.get("location", "")

            # Generate LLM response
            return await self._generate_llm_response(
                intent=Intent.STORE_INFO,
                data=store_data,
                original_text=original_text,
                context=context,
                params={"store_id": store["id"], "store_name": store_data["name"]},
            )

        except Exception as e:
            log.error("store_info_failed", error=str(e))
            return RouterResult(
                intent=Intent.STORE_INFO,
                params={},
                response_text="Lo siento, no puedo obtener la información en este momento.",
                confidence=0.5,
            )

    def _format_store_list(self, names: list[str]) -> str:
        """Format store list for natural language."""
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} y {names[1]}"
        return ", ".join(names[:-1]) + f" y {names[-1]}"
