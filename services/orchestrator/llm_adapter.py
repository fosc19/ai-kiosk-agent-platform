"""LLM Adapter for intent classification and response generation.

Supports multiple backends:
- mock: Returns predefined responses (for testing)
- anthropic: Claude API via Anthropic SDK
- gemini: Google Gemini API (FREE tier available)
- grok: xAI Grok API (FREE tier available)
- ollama: Local LLM via Ollama (FREE, runs on server)

F6: LLM-only classification with conversation context for:
- Multilingual support (Spanish, Catalan, English)
- Reference resolution (pronouns, demonstratives)
- Affirmative handling with context
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from conversation_memory import ConversationContext

log = structlog.get_logger()


def format_conversation_history(context: Optional["ConversationContext"]) -> str:
    """Format conversation history for LLM prompt.

    Args:
        context: ConversationContext with turns

    Returns:
        Formatted string with recent conversation turns
    """
    if not context or not context.turns:
        return "(sin historial previo)"

    # Get last 3 turns
    recent_turns = context.turns[-3:]
    lines = []
    for turn in recent_turns:
        role = "Usuario" if turn.role == "user" else "Sofía"
        text = turn.text[:100] + "..." if len(turn.text) > 100 else turn.text
        lines.append(f"  - {role}: {text}")

    return "\n".join(lines) if lines else "(sin historial previo)"


def strip_thinking_output(text: str) -> str:
    """Strip LLM thinking/reasoning output from response.

    Some models output their reasoning process before the actual response.
    This function removes common patterns like:
    - "Thinking... <reasoning> ...done thinking. <response>"
    - "<think>...</think><response>"

    Args:
        text: Raw LLM response text

    Returns:
        Cleaned response text without thinking output
    """
    import re

    # Pattern 1: "Thinking... <text> ...done thinking. <response>"
    # Match case-insensitive, with possible variations
    pattern1 = r"(?i)^thinking\.{0,3}\s*.*?\.{2,3}\s*done\s+thinking\.?\s*"
    cleaned = re.sub(pattern1, "", text, flags=re.DOTALL)

    # Pattern 2: <think>...</think> tags
    pattern2 = r"<think>.*?</think>\s*"
    cleaned = re.sub(pattern2, "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Pattern 3: [thinking]...[/thinking] tags
    pattern3 = r"\[thinking\].*?\[/thinking\]\s*"
    cleaned = re.sub(pattern3, "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    return cleaned.strip()


def get_response_prompt(
    intent: str,
    context: dict,
    conversation_context: Optional["ConversationContext"] = None,
) -> str:
    """Generate prompt for LLM to create natural response.

    Args:
        intent: Classified intent (greeting, list_stores, navigate, etc.)
        context: Rich context with MCP data, user query, available stores
        conversation_context: Optional conversation context for history

    Returns:
        System prompt for natural response generation
    """
    available_stores = context.get("available_stores", [])
    stores_list = ", ".join(available_stores) if available_stores else "ninguna disponible"

    # Format conversation history
    history = "(nueva conversación)"
    if conversation_context:
        history = format_conversation_history(conversation_context)

    # Format data from MCP tools
    data = context.get("data", {})
    data_json = json.dumps(data, ensure_ascii=False, indent=2) if data else "{}"

    user_query = context.get("user_query", "")

    return f"""Eres Sofía, la asistente virtual amigable del centro comercial. Respondes en español de forma natural y breve.

TIENDAS DEL CATÁLOGO: {stores_list}
REGLA CRÍTICA: SOLO puedes mencionar las tiendas listadas arriba. NUNCA inventes otras tiendas.

DATOS DISPONIBLES (de la base de datos):
{data_json}

HISTORIAL DE CONVERSACIÓN:
{history}

INTENCIÓN DETECTADA: {intent}

El usuario dijo: "{user_query}"

INSTRUCCIONES:
1. Genera una respuesta BREVE y DIRECTA (máximo 1-2 oraciones)
2. Responde SOLO lo que el usuario preguntó - NO des información adicional no solicitada
3. Si pregunta "dónde está X" o "puedo hacer Y", responde la ubicación y ofrece indicar cómo llegar
4. NO incluyas horarios, teléfono, servicios extras a menos que lo pregunte específicamente
5. Si no tienes datos suficientes, pide clarificación amablemente
6. NO uses emojis
7. Responde en el MISMO IDIOMA que el usuario (español/catalán/inglés)

EJEMPLO:
- Usuario: "¿Puedo tomar café?" → "Sí, en Coffee Point puedes tomar café. ¿Te indico cómo llegar?"
- NO: "Sí, en Coffee Point puedes tomar café. Está en planta baja, abre de 8 a 22, tiene wifi..."

Responde directamente sin explicaciones adicionales:"""


def get_classification_prompt(
    stores_list: str,
    context: Optional["ConversationContext"] = None,
) -> str:
    """Generate classification prompt with conversation context.

    Args:
        stores_list: Comma-separated list of available stores
        context: Optional conversation context for reference resolution

    Returns:
        Complete system prompt for LLM classification
    """
    # Extract context info
    current_store = "ninguna"
    last_intent = "ninguna"
    conversation_history = "(sin historial previo)"

    if context:
        if context.current_store_name:
            current_store = context.current_store_name
        if context.last_intent:
            intent_map = {
                "navigate": "navegación",
                "store_info": "información de tienda",
                "list_stores": "listar tiendas",
                "greeting": "saludo",
                "goodbye": "despedida",
            }
            last_intent = intent_map.get(context.last_intent, context.last_intent)
        conversation_history = format_conversation_history(context)

    return f"""Eres un asistente de clasificación de intenciones para un kiosko de centro comercial.

TIENDAS DISPONIBLES: {stores_list}

CONTEXTO CONVERSACIONAL:
- Tienda actual en contexto: {current_store}
- Última acción del usuario: {last_intent}
- Historial reciente:
{conversation_history}

INTENCIONES VÁLIDAS:
- greeting: Saludo (hola, buenos días, hey, bon dia)
- goodbye: Despedida (adiós, hasta luego, chao, adéu)
- list_stores: Pedir lista de tiendas
- store_info: Pedir información sobre una tienda específica
- navigate: Pedir direcciones/ruta a una tienda
- help: Pedir ayuda sobre qué puede hacer el kiosko
- decline: Rechaza una oferta (no, no gracias, ahora no, no hace falta, no thank you)
- clarify: La pregunta es ambigua o la tienda no existe
- unknown: No se puede determinar la intención

CAMPO info_type (solo para store_info):
Cuando la intención es "store_info", incluye "info_type" para indicar qué información específica pide el usuario:
- "hours": Solo pregunta por horario (¿qué horario tiene?, ¿a qué hora abre/cierra?, ¿está abierto?)
- "location": Solo pregunta por ubicación (¿dónde está?, ¿en qué planta?)
- "general": Pregunta general sobre la tienda (háblame de..., información de...)

CAMPO query_type (solo para list_stores):
Cuando la intención es "list_stores", incluye "query_type" para indicar qué quiere saber el usuario:
- "count": Pregunta por cantidad/número (¿cuántas tiendas hay?, dime el número de tiendas, ¿cuántas son?)
- "list": Quiere ver la lista de tiendas (¿qué tiendas hay?, lista las tiendas, ¿cuáles son?)

CAMPO filter (solo para list_stores):
Cuando el usuario quiere filtrar tiendas por estado, incluye "filter":
- "open_now": Tiendas abiertas ahora (¿qué tiendas están abiertas?, ¿cuáles puedo visitar ahora?, ¿hay alguna abierta?)
- "closed": Tiendas cerradas (¿qué tiendas están cerradas?, ¿cuáles no están abiertas?)
- null: Sin filtro (por defecto)

REGLAS IMPORTANTES:
1. RESPUESTAS AFIRMATIVAS: Si el usuario dice "sí", "vale", "ok", "d'acord", "yes", "claro":
   - Después de "información de tienda" → interpret as "navigate" a la tienda actual
   - Después de "navegación" o sin contexto → interpret as "navigate" si hay tienda en contexto

2. RESPUESTAS NEGATIVAS: Si el usuario dice "no", "no gracias", "ahora no", "no hace falta", "no thank you":
   - Después de cualquier pregunta u oferta → interpret as "decline"
   - El usuario rechaza la oferta anterior pero puede querer otra cosa

3. REFERENCIAS Y PRONOMBRES:
   - "ahí", "allí", "esa tienda", "ese local", "there" → usa la tienda del CONTEXTO
   - "su horario", "su información", "its hours" → store_info de la tienda del CONTEXTO
   - "otra", "otra tienda", "another" → list_stores

4. MULTIIDIOMA: Soporta ESPAÑOL, CATALÁN e INGLÉS:
   - "On és Demo Fashion?" → navigate
   - "Where is Urban Wear?" → navigate
   - "Porta'm a Mango" → navigate

5. ERRORES DE TRANSCRIPCIÓN ASR (PRIORITARIO):
   - SIEMPRE busca si el nombre SUENA SIMILAR a una tienda del catálogo
   - Errores comunes: F↔Z, B↔P, D↔T, S↔Z, vocal incorrecta, letras faltantes
   - Ejemplos: "Fara"→Demo Fashion, "Sara"→Demo Fashion, "Sarbucks"→Coffee Point, "HyM"→Urban Wear, "Sata"→Demo Fashion
   - Si suena parecido → usa la tienda correcta en store_query
   - SOLO usa "clarify" si NO hay NINGUNA tienda similar

6. Patrones de existencia ("hay X", "existe X", "tienen X"):
   - "¿Hay la tienda Sara?" → store_info con store_query="Demo Fashion" (corregido de Sara)
   - "¿Existe Coffee Point?" → store_info con store_query="Coffee Point"

7. store_query: Extrae SIEMPRE el nombre de tienda si aplica:
   - Si menciona una tienda explícitamente → esa tienda
   - Si usa pronombre/referencia y hay tienda en contexto → tienda del contexto
   - Si es afirmativo y hay tienda en contexto → tienda del contexto

Responde SOLO con JSON válido, sin explicaciones adicionales.

Formato de respuesta:
{{"intent": "navigate", "store_query": "Demo Fashion", "confidence": 0.95, "reasoning": "Usuario confirma navegación a Demo Fashion del contexto"}}

Para store_info con info_type:
{{"intent": "store_info", "store_query": "Demo Fashion", "info_type": "hours", "confidence": 0.95, "reasoning": "Usuario pregunta específicamente por horario"}}

Para list_stores con query_type:
{{"intent": "list_stores", "query_type": "count", "confidence": 0.95, "reasoning": "Usuario pregunta por cantidad de tiendas"}}

Para list_stores con filter:
{{"intent": "list_stores", "filter": "open_now", "confidence": 0.95, "reasoning": "Usuario pregunta por tiendas abiertas"}}
"""


def parse_json_response(response_text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks and thinking."""
    import re

    text = response_text.strip()

    # Handle markdown code blocks
    if "```" in text:
        # Extract content between code blocks
        parts = text.split("```")
        for part in parts[1::2]:  # Get odd-indexed parts (inside ```)
            if part.startswith("json"):
                part = part[4:]
            part = part.strip()
            if part.startswith("{"):
                text = part
                break

    # Try to find JSON object in text (for models that output thinking first)
    if not text.startswith("{"):
        match = re.search(r'\{[^{}]*"intent"[^{}]*\}', text)
        if match:
            text = match.group(0)

    return json.loads(text)


@dataclass
class LLMClassification:
    """Result from LLM intent classification."""

    intent: str  # greeting, list_stores, store_info, navigate, help, goodbye, clarify, unknown
    store_query: Optional[str] = None  # Extracted store name/query if applicable
    confidence: float = 0.9
    reasoning: Optional[str] = None  # LLM's reasoning (for debugging)
    info_type: Optional[str] = None  # For store_info: "hours", "location", or "general"
    query_type: Optional[str] = None  # For list_stores: "count" or "list"
    filter: Optional[str] = None  # For list_stores: "open_now", "closed", or null


@dataclass
class LLMResponse:
    """Generated response from LLM."""

    text: str
    intent: str
    store_id: Optional[str] = None
    needs_clarification: bool = False


class LLMAdapter(ABC):
    """Abstract base class for LLM adapters."""

    @abstractmethod
    async def classify_intent(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional["ConversationContext"] = None,
    ) -> LLMClassification:
        """Classify user intent from transcript with conversation context.

        Args:
            transcript: User's spoken text
            available_stores: List of valid store names
            context: Optional conversation context for reference resolution

        Returns:
            LLMClassification with intent and optional store_query
        """
        pass

    @abstractmethod
    async def generate_response(
        self,
        intent: str,
        context: dict,
        conversation_context: Optional["ConversationContext"] = None,
    ) -> LLMResponse:
        """Generate natural language response using MCP data.

        Args:
            intent: Classified intent
            context: Rich context with MCP data, user query, available stores
            conversation_context: Optional conversation context for history

        Returns:
            LLMResponse with natural text
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass


class MockLLMAdapter(LLMAdapter):
    """Mock LLM adapter for testing with context support."""

    async def classify_intent(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional["ConversationContext"] = None,
    ) -> LLMClassification:
        """Return mock classification based on simple rules + context."""
        text = transcript.lower()

        # Check for affirmative responses with context
        if any(w in text for w in ["sí", "si", "vale", "ok", "claro", "yes", "d'acord"]):
            if context and context.current_store_name:
                # After store_info -> navigate
                if context.last_intent == "store_info":
                    return LLMClassification(
                        intent="navigate",
                        store_query=context.current_store_name,
                        reasoning="Affirmative after store_info",
                    )
                # Otherwise navigate to context store
                return LLMClassification(
                    intent="navigate",
                    store_query=context.current_store_name,
                    reasoning="Affirmative with store in context",
                )

        # Check for references with context
        if any(w in text for w in ["ahí", "ahi", "allí", "alli", "esa tienda", "ese local"]):
            if context and context.current_store_name:
                return LLMClassification(
                    intent="navigate",
                    store_query=context.current_store_name,
                    reasoning="Location reference resolved from context",
                )

        if any(w in text for w in ["su horario", "su información", "su info"]):
            if context and context.current_store_name:
                return LLMClassification(
                    intent="store_info",
                    store_query=context.current_store_name,
                    reasoning="Possessive reference resolved from context",
                )

        # Basic patterns (multilingual)
        if any(w in text for w in ["hola", "buenas", "hey", "bon dia", "hello", "hi"]):
            return LLMClassification(intent="greeting")

        if any(w in text for w in ["adiós", "adios", "chao", "adéu", "bye", "goodbye"]):
            return LLMClassification(intent="goodbye")

        if any(w in text for w in ["ayuda", "help", "ayudarme", "puedes hacer"]):
            return LLMClassification(intent="help")

        if any(w in text for w in ["tiendas", "lista", "cuáles", "botigues", "stores"]):
            return LLMClassification(intent="list_stores")

        if any(w in text for w in ["dónde", "donde", "llegar", "ir a", "where", "on és", "porta'm"]):
            for store in available_stores:
                if store.lower() in text:
                    return LLMClassification(intent="navigate", store_query=store)
            # F6: Use context store if no explicit store mentioned
            if context and context.current_store_name:
                return LLMClassification(
                    intent="navigate",
                    store_query=context.current_store_name,
                    reasoning="Implicit reference - using store from context",
                )
            return LLMClassification(intent="navigate", store_query=None)

        if any(w in text for w in ["información", "horario", "info", "informació", "hours"]):
            for store in available_stores:
                if store.lower() in text:
                    return LLMClassification(intent="store_info", store_query=store)
            # F6: Use context store if no explicit store mentioned
            if context and context.current_store_name:
                return LLMClassification(
                    intent="store_info",
                    store_query=context.current_store_name,
                    reasoning="Implicit reference - using store from context",
                )
            return LLMClassification(intent="store_info", store_query=None)

        return LLMClassification(intent="unknown", confidence=0.5)

    async def generate_response(
        self,
        intent: str,
        context: dict,
        conversation_context: Optional["ConversationContext"] = None,
    ) -> LLMResponse:
        """Mock response generator for testing."""
        # Generate contextual mock responses based on intent
        data = context.get("data", {})
        user_query = context.get("user_query", "")

        if intent == "greeting":
            return LLMResponse(text="Hola, soy Sofía. ¿En qué puedo ayudarte?", intent=intent)
        elif intent == "goodbye":
            return LLMResponse(text="Hasta luego, que tengas un buen día.", intent=intent)
        elif intent == "list_stores":
            stores = data.get("stores", [])
            if stores:
                names = ", ".join([s.get("name", "") for s in stores[:3]])
                return LLMResponse(text=f"Tenemos {names} y más. ¿Cuál te interesa?", intent=intent)
        elif intent == "store_info":
            name = data.get("name", "la tienda")
            info_type = data.get("info_type")
            if info_type == "hours":
                hours = data.get("hours", "horario no disponible")
                return LLMResponse(
                    text=f"{name} abre {hours}.",
                    intent=intent,
                )
            elif info_type == "location":
                location = data.get("location", "el centro comercial")
                return LLMResponse(
                    text=f"{name} está en {location}.",
                    intent=intent,
                )
            else:
                # General query - concise answer
                location = data.get("location", "")
                if location:
                    return LLMResponse(
                        text=f"{name} está en {location}. ¿Te indico cómo llegar?",
                        intent=intent,
                    )
                return LLMResponse(
                    text=f"Sí, puedes ir a {name}. ¿Te indico cómo llegar?",
                    intent=intent,
                )
        elif intent == "navigate":
            steps = data.get("steps", [])
            store_name = data.get("store_name", "tu destino")
            if steps:
                return LLMResponse(
                    text=f"Para llegar a {store_name}: {steps[0].get('instruction', 'sigue recto')}",
                    intent=intent,
                )
        elif intent == "decline":
            return LLMResponse(text="De acuerdo. ¿Puedo ayudarte con algo más?", intent=intent)
        elif intent == "help":
            return LLMResponse(
                text="Puedo ayudarte a encontrar tiendas, darte información sobre ellas o indicarte cómo llegar.",
                intent=intent,
            )
        elif intent == "clarify":
            alternatives = data.get("alternatives", [])
            if alternatives:
                # alternatives is a list of strings like ["Demo Fashion", "Urban Wear"]
                names = ", ".join(alternatives[:3])
                return LLMResponse(
                    text=f"No encontré esa tienda. ¿Quizás te refieres a {names}?",
                    intent=intent,
                )

        return LLMResponse(text="No estoy segura de entender. ¿Puedes repetir?", intent=intent)

    async def close(self) -> None:
        pass


class GeminiLLMAdapter(LLMAdapter):
    """LLM adapter using Google Gemini API (FREE tier available)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.3,
    ):
        """Initialize Gemini client.

        Args:
            api_key: Google AI API key (free at https://aistudio.google.com)
            model: Model to use (gemini-1.5-flash is free)
            temperature: Temperature for generation
        """
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("google-generativeai required. Install with: pip install google-generativeai")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.model_name = model
        self.temperature = temperature

        log.info("gemini_adapter_initialized", model=model)

    async def classify_intent(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional["ConversationContext"] = None,
    ) -> LLMClassification:
        """Classify intent using Gemini with conversation context."""
        stores_list = ", ".join(available_stores) if available_stores else "ninguna disponible"
        system_prompt = get_classification_prompt(stores_list, context)
        user_message = f"Clasifica la siguiente frase del usuario:\n\n\"{transcript}\""

        try:
            # Gemini uses generate_content (sync, but fast)
            response = self.model.generate_content(
                f"{system_prompt}\n\n{user_message}",
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": 200,
                },
            )

            response_text = response.text.strip()

            log.info(
                "gemini_raw_response",
                transcript=transcript[:50],
                response=response_text[:200],
            )

            result = parse_json_response(response_text)

            log.info(
                "gemini_classification",
                transcript=transcript[:50],
                result=result,
                has_context=context is not None,
            )

            return LLMClassification(
                intent=result.get("intent", "unknown"),
                store_query=result.get("store_query"),
                confidence=result.get("confidence", 0.9),
                reasoning=result.get("reasoning"),
                info_type=result.get("info_type"),
                query_type=result.get("query_type"),
                filter=result.get("filter"),
            )

        except json.JSONDecodeError as e:
            log.warning("gemini_json_parse_error", error=str(e), response=response_text[:200])
            return LLMClassification(intent="unknown", confidence=0.3, reasoning="JSON parse error")
        except Exception as e:
            log.error("gemini_classification_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3)

    async def generate_response(
        self,
        intent: str,
        context: dict,
        conversation_context: Optional["ConversationContext"] = None,
    ) -> LLMResponse:
        """Generate natural response using Gemini with rich context."""
        store_data = context.get("store_data", {})

        # Use the new prompt generator
        prompt = get_response_prompt(intent, context, conversation_context)

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={"temperature": 0.7, "max_output_tokens": 200},
            )

            response_text = response.text.strip()

            log.info(
                "gemini_response_generated",
                intent=intent,
                response_length=len(response_text),
            )

            return LLMResponse(
                text=response_text,
                intent=intent,
                store_id=store_data.get("id"),
            )
        except Exception as e:
            log.error("gemini_response_error", error=str(e))
            return LLMResponse(
                text="Lo siento, ha ocurrido un error. ¿Puedes repetir?",
                intent=intent,
                needs_clarification=True,
            )

    async def close(self) -> None:
        pass  # Gemini client doesn't need closing


class GrokLLMAdapter(LLMAdapter):
    """LLM adapter using xAI Grok API (FREE tier available).

    Grok API is OpenAI-compatible, so we use the OpenAI SDK.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "grok-beta",
        temperature: float = 0.3,
    ):
        """Initialize Grok client.

        Args:
            api_key: xAI API key (free at https://console.x.ai)
            model: Model to use (grok-beta)
            temperature: Temperature for generation
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai required. Install with: pip install openai")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
        )
        self.model = model
        self.temperature = temperature

        log.info("grok_adapter_initialized", model=model)

    async def classify_intent(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional["ConversationContext"] = None,
    ) -> LLMClassification:
        """Classify intent using Grok with conversation context."""
        stores_list = ", ".join(available_stores) if available_stores else "ninguna disponible"
        system_prompt = get_classification_prompt(stores_list, context)
        user_message = f"Clasifica la siguiente frase del usuario:\n\n\"{transcript}\""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=200,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )

            response_text = response.choices[0].message.content.strip()
            result = parse_json_response(response_text)

            log.debug(
                "grok_classification",
                transcript=transcript[:50],
                result=result,
                has_context=context is not None,
            )

            return LLMClassification(
                intent=result.get("intent", "unknown"),
                store_query=result.get("store_query"),
                confidence=result.get("confidence", 0.9),
                reasoning=result.get("reasoning"),
                info_type=result.get("info_type"),
                query_type=result.get("query_type"),
                filter=result.get("filter"),
            )

        except json.JSONDecodeError as e:
            log.warning("grok_json_parse_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3)
        except Exception as e:
            log.error("grok_classification_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3)

    async def generate_response(
        self,
        intent: str,
        context: dict,
        conversation_context: Optional["ConversationContext"] = None,
    ) -> LLMResponse:
        """Generate natural response using Grok with rich context."""
        store_data = context.get("store_data", {})

        # Use the new prompt generator
        prompt = get_response_prompt(intent, context, conversation_context)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=200,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )

            response_text = response.choices[0].message.content.strip()

            log.info(
                "grok_response_generated",
                intent=intent,
                response_length=len(response_text),
            )

            return LLMResponse(
                text=response_text,
                intent=intent,
                store_id=store_data.get("id"),
            )
        except Exception as e:
            log.error("grok_response_error", error=str(e))
            return LLMResponse(
                text="Lo siento, ha ocurrido un error. ¿Puedes repetir?",
                intent=intent,
                needs_clarification=True,
            )

    async def close(self) -> None:
        if hasattr(self, "client") and self.client:
            await self.client.close()


class OpenRouterLLMAdapter(LLMAdapter):
    """LLM adapter using OpenRouter API (OpenAI-compatible).

    OpenRouter provides access to multiple models including Gemini, Claude, etc.
    through a unified OpenAI-compatible API.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-flash-1.5",
        temperature: float = 0.3,
    ):
        """Initialize OpenRouter client.

        Args:
            api_key: OpenRouter API key (from https://openrouter.ai)
            model: Model to use (e.g., google/gemini-flash-1.5, anthropic/claude-3.5-sonnet)
            temperature: Temperature for generation
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai required. Install with: pip install openai")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self.model = model
        self.temperature = temperature

        log.info("openrouter_adapter_initialized", model=model)

    async def classify_intent(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional["ConversationContext"] = None,
    ) -> LLMClassification:
        """Classify intent using OpenRouter with conversation context."""
        stores_list = ", ".join(available_stores) if available_stores else "ninguna disponible"
        system_prompt = get_classification_prompt(stores_list, context)
        user_message = f"Clasifica la siguiente frase del usuario:\n\n\"{transcript}\""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=200,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )

            response_text = response.choices[0].message.content.strip()
            result = parse_json_response(response_text)

            log.debug(
                "openrouter_classification",
                transcript=transcript[:50],
                result=result,
                has_context=context is not None,
            )

            return LLMClassification(
                intent=result.get("intent", "unknown"),
                store_query=result.get("store_query"),
                confidence=result.get("confidence", 0.9),
                reasoning=result.get("reasoning"),
                info_type=result.get("info_type"),
                query_type=result.get("query_type"),
                filter=result.get("filter"),
            )

        except json.JSONDecodeError as e:
            log.warning("openrouter_json_parse_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3)
        except Exception as e:
            log.error("openrouter_classification_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3)

    async def generate_response(
        self,
        intent: str,
        context: dict,
        conversation_context: Optional["ConversationContext"] = None,
    ) -> LLMResponse:
        """Generate natural response using OpenRouter with rich context."""
        store_data = context.get("store_data", {})

        # Use the new prompt generator
        prompt = get_response_prompt(intent, context, conversation_context)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=200,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )

            response_text = response.choices[0].message.content.strip()

            log.info(
                "openrouter_response_generated",
                intent=intent,
                response_length=len(response_text),
            )

            return LLMResponse(
                text=response_text,
                intent=intent,
                store_id=store_data.get("id"),
            )
        except Exception as e:
            log.error("openrouter_response_error", error=str(e))
            return LLMResponse(
                text="Lo siento, ha ocurrido un error. ¿Puedes repetir?",
                intent=intent,
                needs_clarification=True,
            )

    async def close(self) -> None:
        if hasattr(self, "client") and self.client:
            await self.client.close()


class AnthropicLLMAdapter(LLMAdapter):
    """LLM adapter using Anthropic Claude API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.3,
    ):
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("anthropic required. Install with: pip install anthropic")

        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.temperature = temperature

        log.info("anthropic_adapter_initialized", model=model)

    async def classify_intent(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional["ConversationContext"] = None,
    ) -> LLMClassification:
        """Classify intent using Anthropic Claude with conversation context."""
        stores_list = ", ".join(available_stores) if available_stores else "ninguna disponible"
        system_prompt = get_classification_prompt(stores_list, context)
        user_message = f"Clasifica la siguiente frase del usuario:\n\n\"{transcript}\""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=200,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            response_text = response.content[0].text.strip()
            result = parse_json_response(response_text)

            log.debug(
                "anthropic_classification",
                transcript=transcript[:50],
                result=result,
                has_context=context is not None,
            )

            return LLMClassification(
                intent=result.get("intent", "unknown"),
                store_query=result.get("store_query"),
                confidence=result.get("confidence", 0.9),
                reasoning=result.get("reasoning"),
                info_type=result.get("info_type"),
                query_type=result.get("query_type"),
                filter=result.get("filter"),
            )

        except json.JSONDecodeError as e:
            log.warning("anthropic_json_parse_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3)
        except Exception as e:
            log.error("anthropic_classification_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3)

    async def generate_response(
        self,
        intent: str,
        context: dict,
        conversation_context: Optional["ConversationContext"] = None,
    ) -> LLMResponse:
        """Generate natural response using Anthropic Claude with rich context."""
        store_data = context.get("store_data", {})

        # Use the new prompt generator
        prompt = get_response_prompt(intent, context, conversation_context)

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=200,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text.strip()

            log.info(
                "anthropic_response_generated",
                intent=intent,
                response_length=len(response_text),
            )

            return LLMResponse(
                text=response_text,
                intent=intent,
                store_id=store_data.get("id"),
            )
        except Exception as e:
            log.error("anthropic_response_error", error=str(e))
            return LLMResponse(
                text="Lo siento, ha ocurrido un error. ¿Puedes repetir?",
                intent=intent,
                needs_clarification=True,
            )

    async def close(self) -> None:
        if hasattr(self, "client") and self.client:
            await self.client.close()


class OllamaCliAdapter(LLMAdapter):
    """LLM adapter using Ollama CLI (subprocess).

    For cloud models like gpt-oss:120b-cloud that only work via CLI.
    Uses `ollama run` command instead of HTTP API.
    """

    def __init__(
        self,
        model: str = "gpt-oss:120b-cloud",
        temperature: float = 0.3,
        timeout: float = 60.0,
    ):
        """Initialize Ollama CLI adapter.

        Args:
            model: Model to use (default: gpt-oss:120b-cloud)
            temperature: Temperature for generation (not used in CLI)
            timeout: Command timeout in seconds
        """
        import shutil

        self.ollama_path = shutil.which("ollama") or "/opt/homebrew/bin/ollama"
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

        log.info("ollama_cli_adapter_initialized", model=model)

    async def classify_intent(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional["ConversationContext"] = None,
    ) -> LLMClassification:
        """Classify intent using Ollama CLI with conversation context."""
        import asyncio

        stores_list = ", ".join(available_stores) if available_stores else "ninguna disponible"
        system_prompt = get_classification_prompt(stores_list, context)
        user_message = f'Clasifica la siguiente frase del usuario:\n\n"{transcript}"'

        full_prompt = f"{system_prompt}\n\n{user_message}"

        try:
            process = await asyncio.create_subprocess_exec(
                self.ollama_path,
                "run",
                self.model,
                full_prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            response_text = stdout.decode().strip()

            log.debug(
                "ollama_cli_raw_response",
                transcript=transcript[:50],
                response=response_text[:200],
            )

            result = parse_json_response(response_text)

            log.info(
                "ollama_cli_classification",
                transcript=transcript[:50],
                result=result,
                has_context=context is not None,
            )

            return LLMClassification(
                intent=result.get("intent", "unknown"),
                store_query=result.get("store_query"),
                confidence=result.get("confidence", 0.9),
                reasoning=result.get("reasoning"),
                info_type=result.get("info_type"),
                query_type=result.get("query_type"),
                filter=result.get("filter"),
            )

        except asyncio.TimeoutError:
            log.error("ollama_cli_timeout", timeout=self.timeout)
            return LLMClassification(intent="unknown", confidence=0.3, reasoning="Timeout")
        except json.JSONDecodeError as e:
            log.warning(
                "ollama_cli_json_parse_error",
                error=str(e),
                response=response_text[:200] if "response_text" in locals() else "N/A",
            )
            return LLMClassification(intent="unknown", confidence=0.3, reasoning="JSON parse error")
        except Exception as e:
            log.error("ollama_cli_classification_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3, reasoning=str(e))

    async def generate_response(
        self,
        intent: str,
        context: dict,
        conversation_context: Optional["ConversationContext"] = None,
    ) -> LLMResponse:
        """Generate natural response using Ollama CLI with rich context.

        Args:
            intent: Classified intent
            context: Rich context with MCP data, user query, available stores
            conversation_context: Optional conversation context for history

        Returns:
            LLMResponse with natural text
        """
        import asyncio

        store_data = context.get("store_data", {})

        # Use the new prompt generator
        prompt = get_response_prompt(intent, context, conversation_context)

        try:
            process = await asyncio.create_subprocess_exec(
                self.ollama_path,
                "run",
                self.model,
                prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            raw_response = stdout.decode().strip()

            # Strip thinking/reasoning output from response
            response_text = strip_thinking_output(raw_response)

            log.info(
                "ollama_cli_response_generated",
                intent=intent,
                response_length=len(response_text),
                raw_length=len(raw_response),
            )

            return LLMResponse(
                text=response_text,
                intent=intent,
                store_id=store_data.get("id"),
            )
        except asyncio.TimeoutError:
            log.error("ollama_cli_response_timeout", timeout=self.timeout)
            return LLMResponse(
                text="Lo siento, estoy tardando demasiado. ¿Puedes repetir?",
                intent=intent,
                needs_clarification=True,
            )
        except Exception as e:
            log.error("ollama_cli_response_error", error=str(e))
            return LLMResponse(
                text="Lo siento, ha ocurrido un error. ¿Puedes repetir?",
                intent=intent,
                needs_clarification=True,
            )

    async def close(self) -> None:
        pass  # No resources to clean up


class OllamaLLMAdapter(LLMAdapter):
    """LLM adapter using local Ollama server with OpenAI-compatible API.

    Ollama exposes an OpenAI-compatible endpoint at /v1/chat/completions.
    Default model is Qwen2.5 which excels at instruction following and JSON output.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b-instruct",
        temperature: float = 0.3,
        timeout: float = 30.0,
    ):
        """Initialize Ollama client.

        Args:
            base_url: Ollama server URL (default: http://localhost:11434)
            model: Model to use (default: qwen2.5:3b-instruct for speed)
            temperature: Temperature for generation
            timeout: Request timeout in seconds
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai required. Install with: pip install openai")

        # Ollama exposes OpenAI-compatible API at /v1
        self.client = AsyncOpenAI(
            api_key="ollama",  # Ollama doesn't require a real API key
            base_url=f"{base_url}/v1",
            timeout=timeout,
        )
        self.model = model
        self.temperature = temperature
        self.base_url = base_url

        log.info("ollama_adapter_initialized", model=model, base_url=base_url)

    async def classify_intent(
        self,
        transcript: str,
        available_stores: list[str],
        context: Optional["ConversationContext"] = None,
    ) -> LLMClassification:
        """Classify intent using local Ollama with conversation context."""
        stores_list = ", ".join(available_stores) if available_stores else "ninguna disponible"
        system_prompt = get_classification_prompt(stores_list, context)
        user_message = f'Clasifica la siguiente frase del usuario:\n\n"{transcript}"'

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=200,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )

            response_text = response.choices[0].message.content.strip()

            log.debug(
                "ollama_raw_response",
                transcript=transcript[:50],
                response=response_text[:200],
            )

            result = parse_json_response(response_text)

            log.info(
                "ollama_classification",
                transcript=transcript[:50],
                result=result,
                has_context=context is not None,
            )

            return LLMClassification(
                intent=result.get("intent", "unknown"),
                store_query=result.get("store_query"),
                confidence=result.get("confidence", 0.9),
                reasoning=result.get("reasoning"),
                info_type=result.get("info_type"),
                query_type=result.get("query_type"),
                filter=result.get("filter"),
            )

        except json.JSONDecodeError as e:
            log.warning(
                "ollama_json_parse_error",
                error=str(e),
                response=response_text[:200] if "response_text" in locals() else "N/A",
            )
            return LLMClassification(intent="unknown", confidence=0.3, reasoning="JSON parse error")
        except Exception as e:
            log.error("ollama_classification_error", error=str(e))
            return LLMClassification(intent="unknown", confidence=0.3, reasoning=str(e))

    async def generate_response(
        self,
        intent: str,
        context: dict,
        conversation_context: Optional["ConversationContext"] = None,
    ) -> LLMResponse:
        """Generate natural response using local Ollama with rich context."""
        store_data = context.get("store_data", {})

        # Use the new prompt generator
        prompt = get_response_prompt(intent, context, conversation_context)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=200,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )

            raw_response = response.choices[0].message.content.strip()

            # Strip thinking/reasoning output from response
            response_text = strip_thinking_output(raw_response)

            log.info(
                "ollama_response_generated",
                intent=intent,
                response_length=len(response_text),
            )

            return LLMResponse(
                text=response_text,
                intent=intent,
                store_id=store_data.get("id"),
            )
        except Exception as e:
            log.error("ollama_response_error", error=str(e))
            return LLMResponse(
                text="Lo siento, ha ocurrido un error. ¿Puedes repetir?",
                intent=intent,
                needs_clarification=True,
            )

    async def close(self) -> None:
        """Close the async client."""
        if hasattr(self, "client") and self.client:
            await self.client.close()


def create_llm_adapter(
    mode: str = "mock",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
) -> LLMAdapter:
    """Factory function to create LLM adapter.

    Args:
        mode: "mock", "gemini", "grok", "anthropic", or "ollama"
        api_key: API key for cloud providers, or base_url for ollama
        model: Model name (uses defaults if not specified)
        temperature: Temperature for generation

    Returns:
        LLMAdapter instance

    Models:
        - gemini: gemini-1.5-flash (FREE), gemini-1.5-pro
        - grok: grok-beta (FREE with limits)
        - anthropic: claude-3-5-sonnet-20241022
        - ollama: qwen2.5:3b-instruct (local, FREE)
    """
    if mode == "mock":
        log.info("creating_mock_llm_adapter")
        return MockLLMAdapter()

    if mode == "gemini":
        if not api_key:
            raise ValueError("GEMINI_API_KEY required. Get free key at https://aistudio.google.com")
        model = model or "gemini-1.5-flash"
        log.info("creating_gemini_llm_adapter", model=model)
        return GeminiLLMAdapter(api_key=api_key, model=model, temperature=temperature)

    if mode == "grok":
        if not api_key:
            raise ValueError("GROK_API_KEY required. Get free key at https://console.x.ai")
        model = model or "grok-beta"
        log.info("creating_grok_llm_adapter", model=model)
        return GrokLLMAdapter(api_key=api_key, model=model, temperature=temperature)

    if mode == "anthropic":
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required")
        model = model or "claude-3-5-sonnet-20241022"
        log.info("creating_anthropic_llm_adapter", model=model)
        return AnthropicLLMAdapter(api_key=api_key, model=model, temperature=temperature)

    if mode == "ollama":
        # api_key parameter is used for base_url in ollama mode
        base_url = api_key or "http://localhost:11434"
        model = model or "qwen2.5:3b-instruct"
        log.info("creating_ollama_llm_adapter", model=model, base_url=base_url)
        return OllamaLLMAdapter(base_url=base_url, model=model, temperature=temperature)

    if mode == "ollama-cli":
        # Use CLI for cloud models like gpt-oss:120b-cloud
        model = model or "gpt-oss:120b-cloud"
        log.info("creating_ollama_cli_adapter", model=model)
        return OllamaCliAdapter(model=model, temperature=temperature)

    if mode == "openrouter":
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY required. Get key at https://openrouter.ai")
        model = model or "google/gemini-flash-1.5"
        log.info("creating_openrouter_llm_adapter", model=model)
        return OpenRouterLLMAdapter(api_key=api_key, model=model, temperature=temperature)

    raise ValueError(f"Unknown LLM mode: {mode}. Supported: mock, gemini, grok, anthropic, ollama, ollama-cli, openrouter")
