"""
Trace collector client for querying and analyzing traces.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .models import (
    TraceEvent,
    Violation,
    ViolationType,
    GoldenFlow,
    Events,
)


@dataclass
class TraceAnalysis:
    """Analysis results for a trace."""
    trace_id: str
    turn_count: int
    total_duration_ms: float
    events: list[TraceEvent]
    latencies: dict[str, float]
    violations: list[Violation]
    timeline: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "turn_count": self.turn_count,
            "total_duration_ms": self.total_duration_ms,
            "latencies": self.latencies,
            "violations": [v.to_dict() for v in self.violations],
            "timeline": self.timeline,
        }


class TraceCollectorClient:
    """
    Client for interacting with the trace collector.

    Can work in two modes:
    - HTTP mode: Query a running collector service
    - File mode: Read traces directly from JSONL files
    """

    def __init__(
        self,
        collector_url: Optional[str] = None,
        traces_dir: Optional[str] = None,
    ):
        """
        Initialize the collector client.

        Args:
            collector_url: URL of the trace collector service
            traces_dir: Directory containing trace files (for file mode)
        """
        self.collector_url = collector_url
        self.traces_dir = Path(traces_dir) if traces_dir else None

    def load_trace_from_file(self, trace_id: str) -> list[TraceEvent]:
        """Load trace events from local files."""
        if not self.traces_dir:
            raise ValueError("traces_dir not configured")

        events_file = self.traces_dir / trace_id / "events.jsonl"
        if not events_file.exists():
            raise FileNotFoundError(f"Trace not found: {trace_id}")

        events = []
        with open(events_file) as f:
            for line in f:
                if line.strip():
                    events.append(TraceEvent.from_dict(json.loads(line)))

        return sorted(events, key=lambda e: e.mono_ms)

    def load_trace_from_events(self, events: list[TraceEvent]) -> list[TraceEvent]:
        """Load from provided events (for testing)."""
        return sorted(events, key=lambda e: e.mono_ms)

    async def fetch_trace(self, trace_id: str) -> list[TraceEvent]:
        """Fetch trace events from collector service."""
        if not self.collector_url:
            raise ValueError("collector_url not configured")

        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.collector_url}/traces/{trace_id}")
            response.raise_for_status()
            data = response.json()
            return [TraceEvent.from_dict(e) for e in data]

    def analyze(
        self,
        events: list[TraceEvent],
        golden_flow: Optional[GoldenFlow] = None,
    ) -> TraceAnalysis:
        """
        Analyze a trace and detect violations.

        Args:
            events: List of trace events
            golden_flow: Optional golden flow to validate against

        Returns:
            TraceAnalysis with latencies, violations, and timeline
        """
        if not events:
            return TraceAnalysis(
                trace_id="",
                turn_count=0,
                total_duration_ms=0,
                events=[],
                latencies={},
                violations=[],
                timeline=[],
            )

        trace_id = events[0].trace_id
        events = sorted(events, key=lambda e: e.mono_ms)

        # Calculate latencies
        latencies = self._calculate_latencies(events)

        # Build timeline
        timeline = self._build_timeline(events)

        # Detect violations
        violations = self._detect_violations(events, latencies, golden_flow)

        # Count turns
        turn_ids = set(e.turn_id for e in events if e.turn_id)

        # Total duration
        total_duration = events[-1].mono_ms - events[0].mono_ms if len(events) > 1 else 0

        return TraceAnalysis(
            trace_id=trace_id,
            turn_count=len(turn_ids),
            total_duration_ms=total_duration,
            events=events,
            latencies=latencies,
            violations=violations,
            timeline=timeline,
        )

    def _calculate_latencies(self, events: list[TraceEvent]) -> dict[str, float]:
        """Calculate key latencies from events."""
        latencies = {}

        # Group by turn
        turns: dict[str, list[TraceEvent]] = {}
        for e in events:
            if e.turn_id:
                turns.setdefault(e.turn_id, []).append(e)

        for turn_id, turn_events in turns.items():
            # Turn latency
            turn_start = next((e for e in turn_events if "turn_start" in e.event), None)
            turn_end = next((e for e in turn_events if "turn_end" in e.event), None)
            if turn_start and turn_end:
                latencies[f"turn_{turn_id}_total"] = turn_end.mono_ms - turn_start.mono_ms

            # ASR latency
            asr_start = next((e for e in turn_events if "asr_start" in e.event), None)
            asr_end = next((e for e in turn_events if "asr_end" in e.event), None)
            if asr_start and asr_end:
                latencies[f"turn_{turn_id}_asr"] = asr_end.mono_ms - asr_start.mono_ms

            # LLM first token latency
            llm_start = next((e for e in turn_events if "llm_start" in e.event), None)
            llm_first = next((e for e in turn_events if "llm_first_token" in e.event), None)
            if llm_start and llm_first:
                latencies[f"turn_{turn_id}_llm_first_token"] = llm_first.mono_ms - llm_start.mono_ms

            # LLM total latency
            llm_end = next((e for e in turn_events if "llm_end" in e.event), None)
            if llm_start and llm_end:
                latencies[f"turn_{turn_id}_llm_total"] = llm_end.mono_ms - llm_start.mono_ms

            # TTS first chunk latency
            tts_start = next((e for e in turn_events if "tts_start" in e.event), None)
            tts_chunk = next((e for e in turn_events if "tts_chunk" in e.event), None)
            if tts_start and tts_chunk:
                latencies[f"turn_{turn_id}_tts_first_chunk"] = tts_chunk.mono_ms - tts_start.mono_ms

        return latencies

    def _build_timeline(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        """Build a timeline view of events."""
        if not events:
            return []

        start_ms = events[0].mono_ms
        timeline = []

        for event in events:
            timeline.append({
                "offset_ms": round(event.mono_ms - start_ms, 2),
                "service": event.service,
                "event": event.event,
                "turn_id": event.turn_id,
                "span_id": event.span_id,
                "payload": event.payload,
            })

        return timeline

    def _detect_violations(
        self,
        events: list[TraceEvent],
        latencies: dict[str, float],
        golden_flow: Optional[GoldenFlow],
    ) -> list[Violation]:
        """Detect violations in the trace."""
        violations = []

        # Check SLA violations if golden flow provided
        if golden_flow:
            violations.extend(self._check_sla_violations(latencies, golden_flow))
            violations.extend(self._check_tool_violations(events, golden_flow))
            violations.extend(self._check_response_violations(events, golden_flow))

        # Check general violations
        violations.extend(self._check_prompt_budget(events))

        return violations

    def _check_sla_violations(
        self,
        latencies: dict[str, float],
        golden_flow: GoldenFlow,
    ) -> list[Violation]:
        """Check SLA violations."""
        violations = []
        sla = golden_flow.sla

        for key, value in latencies.items():
            if "_total" in key and value > sla.max_turn_latency_ms:
                violations.append(Violation(
                    type=ViolationType.SLA_TURN,
                    message=f"Turn latency {value:.0f}ms exceeds SLA {sla.max_turn_latency_ms}ms",
                    severity="warning",
                    expected=sla.max_turn_latency_ms,
                    actual=value,
                ))

            if "_asr" in key and value > sla.max_asr_latency_ms:
                violations.append(Violation(
                    type=ViolationType.SLA_ASR,
                    message=f"ASR latency {value:.0f}ms exceeds SLA {sla.max_asr_latency_ms}ms",
                    severity="warning",
                    expected=sla.max_asr_latency_ms,
                    actual=value,
                ))

            if "_llm_first_token" in key and value > sla.max_llm_first_token_ms:
                violations.append(Violation(
                    type=ViolationType.SLA_LLM,
                    message=f"LLM first token {value:.0f}ms exceeds SLA {sla.max_llm_first_token_ms}ms",
                    severity="warning",
                    expected=sla.max_llm_first_token_ms,
                    actual=value,
                ))

            if "_tts_first_chunk" in key and value > sla.max_tts_first_chunk_ms:
                violations.append(Violation(
                    type=ViolationType.SLA_TTS,
                    message=f"TTS first chunk {value:.0f}ms exceeds SLA {sla.max_tts_first_chunk_ms}ms",
                    severity="warning",
                    expected=sla.max_tts_first_chunk_ms,
                    actual=value,
                ))

        return violations

    def _check_tool_violations(
        self,
        events: list[TraceEvent],
        golden_flow: GoldenFlow,
    ) -> list[Violation]:
        """Check tool call violations."""
        violations = []

        # Get actual tool calls
        tool_calls = [
            e for e in events
            if e.event in (Events.ORCH_TOOL_CALL, "orch.tool_call")
        ]
        actual_tools = {e.payload.get("tool_name") for e in tool_calls}

        # Check expected tools
        for expected in golden_flow.expected.tool_calls:
            if expected.name not in actual_tools:
                violations.append(Violation(
                    type=ViolationType.MISSING_TOOL,
                    message=f"Expected tool '{expected.name}' was not called",
                    severity="error",
                    expected=expected.name,
                    actual=list(actual_tools),
                ))

            # Check args if specified
            if expected.args_contain:
                matching_call = next(
                    (e for e in tool_calls if e.payload.get("tool_name") == expected.name),
                    None
                )
                if matching_call:
                    actual_args = matching_call.payload.get("args", {})
                    for key, value in expected.args_contain.items():
                        if key not in actual_args:
                            violations.append(Violation(
                                type=ViolationType.MISSING_TOOL,
                                message=f"Tool '{expected.name}' missing arg '{key}'",
                                severity="warning",
                                expected={key: value},
                                actual=actual_args,
                            ))
                        elif value not in str(actual_args.get(key, "")):
                            violations.append(Violation(
                                type=ViolationType.MISSING_TOOL,
                                message=f"Tool '{expected.name}' arg '{key}' doesn't contain '{value}'",
                                severity="warning",
                                expected=value,
                                actual=actual_args.get(key),
                            ))

        return violations

    def _check_response_violations(
        self,
        events: list[TraceEvent],
        golden_flow: GoldenFlow,
    ) -> list[Violation]:
        """Check response content violations."""
        violations = []

        # Find the response text
        turn_end_events = [e for e in events if "turn_end" in e.event]
        response_text = ""
        for e in turn_end_events:
            if "response" in e.payload:
                response_text = e.payload["response"].lower()
                break

        if not response_text:
            # Try to find it in other events
            say_events = [e for e in events if "say" in e.event or "speak" in e.event]
            for e in say_events:
                if "text" in e.payload:
                    response_text = e.payload["text"].lower()
                    break

        # Check response_contains
        for expected_phrase in golden_flow.expected.response_contains:
            if expected_phrase.lower() not in response_text:
                violations.append(Violation(
                    type=ViolationType.HALLUCINATION,
                    message=f"Response missing expected phrase: '{expected_phrase}'",
                    severity="warning",
                    expected=expected_phrase,
                    actual=response_text[:200],
                ))

        # Check response_not_contains
        for forbidden_phrase in golden_flow.expected.response_not_contains:
            if forbidden_phrase.lower() in response_text:
                violations.append(Violation(
                    type=ViolationType.HALLUCINATION,
                    message=f"Response contains forbidden phrase: '{forbidden_phrase}'",
                    severity="error",
                    expected=f"not '{forbidden_phrase}'",
                    actual=response_text[:200],
                ))

        return violations

    def _check_prompt_budget(self, events: list[TraceEvent]) -> list[Violation]:
        """Check prompt token budget violations."""
        violations = []
        max_prompt_tokens = 4000  # Configurable

        llm_start_events = [e for e in events if "llm_start" in e.event]
        for e in llm_start_events:
            prompt_tokens = e.payload.get("prompt_tokens", 0)
            if prompt_tokens > max_prompt_tokens:
                violations.append(Violation(
                    type=ViolationType.PROMPT_BUDGET,
                    message=f"Prompt tokens {prompt_tokens} exceeds budget {max_prompt_tokens}",
                    severity="warning",
                    expected=max_prompt_tokens,
                    actual=prompt_tokens,
                ))

        return violations


def load_golden_flow(filepath: str) -> GoldenFlow:
    """Load a golden flow from a YAML file."""
    import yaml
    with open(filepath) as f:
        data = yaml.safe_load(f)
    return GoldenFlow.from_dict(data)


def load_golden_flows_from_dir(directory: str) -> list[GoldenFlow]:
    """Load all golden flows from a directory."""
    import yaml
    flows = []
    dir_path = Path(directory)

    for yaml_file in dir_path.rglob("*.yml"):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        flows.append(GoldenFlow.from_dict(data))

    return flows
