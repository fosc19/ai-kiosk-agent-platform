"""Basic intent router using rules (no LLM).

For F3, this router uses simple keyword matching.
F5 will add LLM-based routing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

log = structlog.get_logger()


class Intent(Enum):
    """User intents recognized by the router."""

    GREETING = "greeting"
    LIST_STORES = "list_stores"
    STORE_INFO = "store_info"
    NAVIGATE = "navigate"
    HELP = "help"
    GOODBYE = "goodbye"
    UNKNOWN = "unknown"


@dataclass
class RouterResult:
    """Result from intent routing."""

    intent: Intent
    params: dict
    response_text: str
    confidence: float = 1.0
    route_data: Optional[dict] = None  # F4: populated when MCP provides route


# Store data (hardcoded for F3, will come from MCP tools in F4)
STORES = {
    "demo_fashion": {
        "id": "demo_fashion",
        "name": "Demo Fashion",
        "category": "Moda",
        "floor": 1,
        "description": "Ropa y accesorios de moda",
    },
    "urban_wear": {
        "id": "urban_wear",
        "name": "Urban Wear",
        "category": "Moda",
        "floor": 1,
        "description": "Moda asequible para toda la familia",
    },
    "nike": {
        "id": "nike",
        "name": "Nike",
        "category": "Deportes",
        "floor": 2,
        "description": "Ropa y calzado deportivo",
    },
}


class BasicRouter:
    """Rule-based intent router for F3."""

    def __init__(self):
        """Initialize router with keyword patterns."""
        self.greeting_words = ["hola", "buenas", "buenos", "hey", "saludos", "qué tal"]
        self.goodbye_words = ["adiós", "adios", "chao", "hasta luego", "bye", "nos vemos"]
        self.list_words = ["tiendas", "lista", "qué hay", "cuáles", "cuales", "opciones"]
        self.navigate_words = ["dónde", "donde", "cómo llego", "como llego", "llevar", "ir a", "encontrar", "busco"]
        self.info_words = ["información", "informacion", "info", "horario", "qué es", "que es", "qué venden"]
        self.help_words = ["ayuda", "help", "qué puedes", "que puedes", "opciones"]

    def route(self, transcript: str) -> RouterResult:
        """Route transcript to intent and generate response.

        Args:
            transcript: User's transcribed speech

        Returns:
            RouterResult with intent, params, and response
        """
        text = transcript.lower().strip()

        if not text:
            return RouterResult(
                intent=Intent.UNKNOWN,
                params={},
                response_text="No te escuché bien. ¿Puedes repetir?",
                confidence=0.0,
            )

        # Check intents in order of priority
        if self._matches_any(text, self.greeting_words):
            return self._handle_greeting()

        if self._matches_any(text, self.goodbye_words):
            return self._handle_goodbye()

        if self._matches_any(text, self.help_words):
            return self._handle_help()

        if self._matches_any(text, self.list_words):
            return self._handle_list_stores()

        # Check for navigation (has higher priority than info)
        if self._matches_any(text, self.navigate_words):
            store = self._extract_store(text)
            if store:
                return self._handle_navigate(store)
            return self._handle_navigate_unknown()

        # Check for store info
        if self._matches_any(text, self.info_words):
            store = self._extract_store(text)
            if store:
                return self._handle_store_info(store)

        # Check if just mentioning a store name
        store = self._extract_store(text)
        if store:
            return self._handle_store_mention(store)

        # Unknown intent
        return self._handle_unknown()

    def _matches_any(self, text: str, words: list[str]) -> bool:
        """Check if text contains any of the words."""
        return any(word in text for word in words)

    def _extract_store(self, text: str) -> Optional[dict]:
        """Extract store from text."""
        text_lower = text.lower()

        # Direct name match
        for store_key, store_data in STORES.items():
            if store_key in text_lower or store_data["name"].lower() in text_lower:
                return store_data

        # Fuzzy match for common variations
        if "h y m" in text_lower or "urban wear" in text_lower or "hache" in text_lower:
            return STORES["urban_wear"]

        return None

    def _handle_greeting(self) -> RouterResult:
        return RouterResult(
            intent=Intent.GREETING,
            params={},
            response_text="¡Hola! Soy Sofía, tu asistente del centro comercial. Puedo ayudarte a encontrar tiendas o indicarte cómo llegar a ellas. ¿En qué puedo ayudarte?",
        )

    def _handle_goodbye(self) -> RouterResult:
        return RouterResult(
            intent=Intent.GOODBYE,
            params={},
            response_text="¡Hasta luego! Que tengas un buen día.",
        )

    def _handle_help(self) -> RouterResult:
        return RouterResult(
            intent=Intent.HELP,
            params={},
            response_text="Puedo ayudarte con: ver las tiendas disponibles, darte información sobre una tienda, o indicarte cómo llegar. Por ejemplo, puedes decir: ¿Dónde está Demo Fashion?",
        )

    def _handle_list_stores(self) -> RouterResult:
        store_names = [s["name"] for s in STORES.values()]
        stores_text = ", ".join(store_names[:-1]) + f" y {store_names[-1]}"

        return RouterResult(
            intent=Intent.LIST_STORES,
            params={"stores": list(STORES.keys())},
            response_text=f"Tenemos {stores_text}. ¿Cuál te interesa?",
        )

    def _handle_navigate(self, store: dict) -> RouterResult:
        # Simple directions based on floor
        if store["floor"] == 1:
            directions = "Sigue recto por el pasillo principal y lo encontrarás a tu derecha."
        else:
            directions = "Sube al segundo piso por las escaleras mecánicas y está justo al frente."

        return RouterResult(
            intent=Intent.NAVIGATE,
            params={"store_id": store["id"], "store_name": store["name"]},
            response_text=f"Para llegar a {store['name']}: {directions}",
        )

    def _handle_navigate_unknown(self) -> RouterResult:
        return RouterResult(
            intent=Intent.NAVIGATE,
            params={},
            response_text="¿A qué tienda te gustaría ir? Tenemos Demo Fashion, Urban Wear y Nike.",
            confidence=0.7,
        )

    def _handle_store_info(self, store: dict) -> RouterResult:
        return RouterResult(
            intent=Intent.STORE_INFO,
            params={"store_id": store["id"]},
            response_text=f"{store['name']} está en el piso {store['floor']}. {store['description']}. ¿Te indico cómo llegar?",
        )

    def _handle_store_mention(self, store: dict) -> RouterResult:
        return RouterResult(
            intent=Intent.STORE_INFO,
            params={"store_id": store["id"]},
            response_text=f"¿Te gustaría saber más sobre {store['name']} o que te indique cómo llegar?",
            confidence=0.8,
        )

    def _handle_unknown(self) -> RouterResult:
        return RouterResult(
            intent=Intent.UNKNOWN,
            params={},
            response_text="No estoy segura de haber entendido. Puedes preguntarme por tiendas o cómo llegar a ellas.",
            confidence=0.5,
        )
