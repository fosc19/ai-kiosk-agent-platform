"""
Trace event models and data structures.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import time
import uuid


class ServiceName(str, Enum):
    """Valid service names for tracing."""
    UI = "ui"
    ORCHESTRATOR = "orchestrator"
    SPEECH = "speech"
    MCP_TOOLS = "mcp-tools"
    COLLECTOR = "collector"


@dataclass
class TraceEvent:
    """
    A single trace event emitted by a service.

    Attributes:
        trace_id: UUID for the entire session/trace
        turn_id: Unique ID for a conversational turn
        span_id: Unique ID for this specific operation
        parent_span_id: Optional parent span for hierarchical tracing
        service: Which service emitted this event
        event: Event name (e.g., "turn_start", "llm_end")
        ts_ms: Unix timestamp in milliseconds (for cross-service sync)
        mono_ms: Monotonic time since service start (for precision)
        payload: Optional additional data
    """
    trace_id: str
    turn_id: str
    span_id: str
    service: str
    event: str
    ts_ms: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    mono_ms: float = field(default_factory=lambda: time.monotonic() * 1000)
    parent_span_id: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        service: str,
        event: str,
        trace_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> "TraceEvent":
        """Factory method to create a TraceEvent with defaults."""
        return cls(
            trace_id=trace_id or str(uuid.uuid4()),
            turn_id=turn_id or str(uuid.uuid4()),
            span_id=span_id or str(uuid.uuid4()),
            service=service,
            event=event,
            parent_span_id=parent_span_id,
            payload=payload or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceEvent":
        """Create from dictionary."""
        return cls(**data)


class ViolationType(str, Enum):
    """Types of architectural violations."""
    HALLUCINATION = "hallucination"
    SLA_TURN = "sla_turn"
    SLA_ASR = "sla_asr"
    SLA_LLM = "sla_llm"
    SLA_TTS = "sla_tts"
    MISSING_TOOL = "missing_tool"
    UNEXPECTED_TOOL = "unexpected_tool"
    PROMPT_BUDGET = "prompt_budget"
    DIRECT_DB_ACCESS = "direct_db_access"


@dataclass
class Violation:
    """
    An architectural or SLA violation detected in a trace.
    """
    type: ViolationType
    message: str
    severity: str = "warning"  # "warning", "error", "critical"
    event_span_id: Optional[str] = None
    expected: Optional[Any] = None
    actual: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value if isinstance(self.type, ViolationType) else self.type,
            "message": self.message,
            "severity": self.severity,
            "event_span_id": self.event_span_id,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class SLA:
    """
    Service Level Agreement thresholds for a golden flow.
    """
    max_turn_latency_ms: int = 3000
    max_asr_latency_ms: int = 500
    max_llm_first_token_ms: int = 800
    max_tts_first_chunk_ms: int = 500

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SLA":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ExpectedToolCall:
    """Expected tool call in a golden flow."""
    name: str
    args_contain: Optional[dict[str, Any]] = None
    result_contains: Optional[list[str]] = None


@dataclass
class GoldenFlowExpectation:
    """Expected outcomes for a golden flow."""
    intent: Optional[str] = None
    info_type: Optional[str] = None
    query_type: Optional[str] = None
    tool_calls: list[ExpectedToolCall] = field(default_factory=list)
    response_contains: list[str] = field(default_factory=list)
    response_not_contains: list[str] = field(default_factory=list)


@dataclass
class GoldenFlow:
    """
    A golden flow definition for E2E testing.

    Defines expected behavior for a specific user input.
    """
    name: str
    description: str
    input_text: str
    expected: GoldenFlowExpectation
    sla: SLA = field(default_factory=SLA)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoldenFlow":
        """Create from dictionary (parsed YAML)."""
        expected_data = data.get("expected", {})
        tool_calls = [
            ExpectedToolCall(
                name=tc["name"],
                args_contain=tc.get("args_contain"),
                result_contains=tc.get("result_contains"),
            )
            for tc in expected_data.get("tool_calls", [])
        ]

        expected = GoldenFlowExpectation(
            intent=expected_data.get("intent"),
            info_type=expected_data.get("info_type"),
            query_type=expected_data.get("query_type"),
            tool_calls=tool_calls,
            response_contains=expected_data.get("response_contains", []),
            response_not_contains=expected_data.get("response_not_contains", []),
        )

        sla = SLA.from_dict(data.get("sla", {}))

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            input_text=data.get("input", {}).get("text", ""),
            expected=expected,
            sla=sla,
            tags=data.get("tags", []),
        )


# Event name constants for type safety
class Events:
    """Standard event names by category."""

    # UI / Audio events
    UI_SESSION_START = "ui.session_start"
    UI_PRESENCE_DETECTED = "ui.presence_detected"
    UI_VAD_START = "ui.vad_start"
    UI_VAD_END = "ui.vad_end"
    UI_AUDIO_SENT = "ui.audio_sent"
    UI_TTS_PLAY_START = "ui.tts_play_start"
    UI_TTS_PLAY_END = "ui.tts_play_end"
    UI_BARGE_IN = "ui.barge_in"

    # Speech events
    SPEECH_ASR_START = "speech.asr_start"
    SPEECH_ASR_END = "speech.asr_end"
    SPEECH_ASR_ERROR = "speech.asr_error"
    SPEECH_TTS_START = "speech.tts_start"
    SPEECH_TTS_CHUNK = "speech.tts_chunk"
    SPEECH_TTS_END = "speech.tts_end"

    # Orchestrator events
    ORCH_TURN_START = "orch.turn_start"
    ORCH_CLASSIFY_START = "orch.classify_start"
    ORCH_CLASSIFY_END = "orch.classify_end"
    ORCH_LLM_START = "orch.llm_start"
    ORCH_LLM_FIRST_TOKEN = "orch.llm_first_token"
    ORCH_LLM_END = "orch.llm_end"
    ORCH_TOOL_CALL = "orch.tool_call"
    ORCH_TOOL_RESULT = "orch.tool_result"
    ORCH_TURN_END = "orch.turn_end"

    # MCP Tools events
    MCP_CALL_START = "mcp.call_start"
    MCP_DB_QUERY = "mcp.db_query"
    MCP_CALL_END = "mcp.call_end"
    MCP_CALL_ERROR = "mcp.call_error"
