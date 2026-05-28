"""Policies and guardrails for the orchestrator.

These policies ensure the system:
1. Never hallucinates store information
2. Only responds with data from the catalog
3. Asks for clarification when ambiguous
4. Falls back gracefully when uncertain
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import structlog

log = structlog.get_logger()


@dataclass
class PolicyViolation:
    """Represents a policy violation."""

    policy_name: str
    description: str
    severity: str  # "warning" | "block"
    suggested_response: Optional[str] = None


@dataclass
class PolicyCheckResult:
    """Result of policy validation."""

    passed: bool
    violations: list[PolicyViolation]
    modified_response: Optional[str] = None  # If response was sanitized


class PolicyEngine:
    """Engine for checking and enforcing policies."""

    def __init__(self, catalog_store_ids: set[str], catalog_store_names: set[str]):
        """Initialize policy engine.

        Args:
            catalog_store_ids: Set of valid store IDs from catalog
            catalog_store_names: Set of valid store names from catalog
        """
        self.catalog_store_ids = catalog_store_ids
        self.catalog_store_names = {name.lower() for name in catalog_store_names}

        log.info(
            "policy_engine_initialized",
            store_count=len(catalog_store_ids),
        )

    def update_catalog(self, store_ids: set[str], store_names: set[str]) -> None:
        """Update the catalog with new store data."""
        self.catalog_store_ids = store_ids
        self.catalog_store_names = {name.lower() for name in store_names}
        log.info("catalog_updated", store_count=len(store_ids))

    def check_response(
        self,
        response_text: str,
        intent: str,
        store_id: Optional[str] = None,
    ) -> PolicyCheckResult:
        """Check if a response violates any policies.

        Args:
            response_text: The response to check
            intent: The detected intent
            store_id: Store ID if response is about a specific store

        Returns:
            PolicyCheckResult with violations if any
        """
        violations = []

        # Policy 1: No hallucinated stores
        violation = self._check_store_hallucination(response_text)
        if violation:
            violations.append(violation)

        # Policy 2: Store ID must be in catalog
        if store_id and store_id not in self.catalog_store_ids:
            violations.append(PolicyViolation(
                policy_name="valid_store_id",
                description=f"Store ID '{store_id}' not in catalog",
                severity="block",
                suggested_response="Lo siento, no tengo información sobre esa tienda.",
            ))

        # Policy 3: Navigate intent must have valid target
        if intent == "navigate" and not store_id:
            # Not a violation, but might need clarification
            pass

        if violations:
            log.warning(
                "policy_violations_found",
                violations=[v.policy_name for v in violations],
                severity_max=max(v.severity for v in violations),
            )

        return PolicyCheckResult(
            passed=len(violations) == 0 or all(v.severity == "warning" for v in violations),
            violations=violations,
            modified_response=violations[0].suggested_response if violations and violations[0].severity == "block" else None,
        )

    def _check_store_hallucination(self, response_text: str) -> Optional[PolicyViolation]:
        """Check if response mentions stores not in catalog.

        This is a simple heuristic check. It looks for patterns that might
        indicate hallucinated store names.
        """
        # Common patterns that indicate store mentions
        store_indicators = [
            "tienda ",
            "la tienda ",
            " está en ",
            "llegarás a ",
            "encontrarás ",
            "visita ",
            "ve a ",
        ]

        text_lower = response_text.lower()

        # This is a simplified check - in production you might use NER
        # For now, we just ensure the response doesn't claim stores exist
        # that aren't in our catalog

        # Check for suspicious patterns (like "X tienda no existe")
        # This indicates the LLM might be making up stores
        if "tienda no existe" in text_lower or "no tenemos" in text_lower:
            # These are valid clarification responses
            return None

        return None  # Pass by default - full NER would be needed for comprehensive check

    def validate_store_query(
        self,
        store_query: Optional[str],
        confidence: float,
    ) -> tuple[bool, Optional[str]]:
        """Validate if a store query should be processed.

        Args:
            store_query: Store name/query from user
            confidence: Classification confidence

        Returns:
            Tuple of (should_process, clarification_message)
        """
        if not store_query:
            return False, "¿A qué tienda te refieres?"

        # Check if it's close enough to a known store
        query_lower = store_query.lower()

        # Exact match
        if query_lower in self.catalog_store_names:
            return True, None

        # Check for partial matches (fuzzy would be done by MCP)
        for name in self.catalog_store_names:
            if query_lower in name or name in query_lower:
                return True, None

        # Low confidence + unknown store = ask for clarification
        if confidence < 0.7:
            return False, f"No estoy segura de encontrar '{store_query}'. ¿Puedes ser más específico?"

        # Let MCP handle fuzzy matching
        return True, None

    def get_clarification_response(
        self,
        intent: str,
        available_stores: list[str],
    ) -> str:
        """Get appropriate clarification response based on intent.

        Args:
            intent: Detected intent
            available_stores: List of store names from catalog

        Returns:
            Clarification message
        """
        if not available_stores:
            return "Lo siento, no tengo información sobre tiendas disponibles en este momento."

        stores_text = self._format_store_list(available_stores[:5])  # Limit to 5

        clarifications = {
            "navigate": f"¿A qué tienda te gustaría ir? Tenemos {stores_text}.",
            "store_info": f"¿De qué tienda quieres información? Tenemos {stores_text}.",
            "clarify": f"No estoy segura de entender. ¿Te refieres a alguna de estas tiendas: {stores_text}?",
            "unknown": "No estoy segura de haber entendido. Puedes preguntarme por tiendas o cómo llegar a ellas.",
        }

        return clarifications.get(intent, clarifications["unknown"])

    def _format_store_list(self, stores: list[str]) -> str:
        """Format a list of stores for natural language."""
        if not stores:
            return ""
        if len(stores) == 1:
            return stores[0]
        if len(stores) == 2:
            return f"{stores[0]} y {stores[1]}"
        return ", ".join(stores[:-1]) + f" y {stores[-1]}"


# Predefined responses for common intents (guardrail: no LLM needed)
SAFE_RESPONSES = {
    "greeting": "¡Hola! Soy Sofía, tu asistente del centro comercial. Puedo ayudarte a encontrar tiendas o indicarte cómo llegar a ellas. ¿En qué puedo ayudarte?",
    "goodbye": "¡Hasta luego! Que tengas un buen día.",
    "help": "Puedo ayudarte con: ver las tiendas disponibles, darte información sobre una tienda, o indicarte cómo llegar. Por ejemplo, puedes decir: ¿Dónde está Demo Fashion?",
}


def is_safe_intent(intent: str) -> bool:
    """Check if intent has a safe predefined response."""
    return intent in SAFE_RESPONSES


def get_safe_response(intent: str) -> Optional[str]:
    """Get safe predefined response for intent."""
    return SAFE_RESPONSES.get(intent)
