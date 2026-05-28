#!/usr/bin/env python3
"""
Golden Flow Runner for AI Kiosk.

Validates golden flows against the orchestrator and trace collector.
Runs flows, checks expectations, and validates SLAs.

Usage:
    python scripts/run_golden_flows.py [--orchestrator-url URL] [--collector-url URL] [--tag TAG]

Examples:
    python scripts/run_golden_flows.py
    python scripts/run_golden_flows.py --tag basic
    python scripts/run_golden_flows.py --tag navigation --verbose
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml


@dataclass
class FlowResult:
    """Result from running a golden flow."""

    flow_name: str
    flow_file: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    response_text: str = ""
    intent: str = ""
    trace_id: str = ""
    turn_id: str = ""
    duration_ms: float = 0.0


@dataclass
class ValidationContext:
    """Context for flow validation."""

    intent: str
    response_text: str
    tool_calls: list[dict]
    traces: list[dict]
    metrics: dict[str, float]


class GoldenFlowRunner:
    """Runs and validates golden flows."""

    def __init__(
        self,
        orchestrator_url: str = "http://localhost:8765",
        collector_url: str = "http://localhost:9010",
        verbose: bool = False,
    ):
        self.orchestrator_url = orchestrator_url
        self.collector_url = collector_url
        self.verbose = verbose
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def run_flow(self, flow: dict, flow_file: str) -> FlowResult:
        """Run a single golden flow and validate results.

        Args:
            flow: The golden flow definition
            flow_file: Path to the flow file

        Returns:
            FlowResult with pass/fail status and details
        """
        flow_name = flow.get("name", "Unknown")
        result = FlowResult(
            flow_name=flow_name,
            flow_file=flow_file,
            passed=True,
        )

        try:
            # Generate unique session and turn IDs
            import uuid
            session_id = f"golden-{uuid.uuid4().hex[:8]}"
            turn_id = f"turn-{uuid.uuid4().hex[:8]}"
            result.trace_id = session_id
            result.turn_id = turn_id

            # Get input text
            input_text = flow.get("input", {}).get("text", "")
            if not input_text:
                result.passed = False
                result.errors.append("No input text specified")
                return result

            # Send text to orchestrator via HTTP endpoint
            start_time = time.perf_counter()

            response = await self.client.post(
                f"{self.orchestrator_url}/text",
                json={
                    "text": input_text,
                    "session_id": session_id,
                    "turn_id": turn_id,
                },
            )

            result.duration_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code != 200:
                result.passed = False
                result.errors.append(f"Orchestrator returned {response.status_code}")
                return result

            orch_result = response.json()
            result.response_text = orch_result.get("response_text", "")
            result.intent = orch_result.get("intent", "")

            # Get traces from collector
            traces = await self._get_traces(session_id, turn_id)

            # Calculate metrics from traces
            metrics = self._calculate_metrics(traces)
            result.metrics = metrics

            # Build validation context
            context = ValidationContext(
                intent=result.intent,
                response_text=result.response_text,
                tool_calls=orch_result.get("tool_calls", []),
                traces=traces,
                metrics=metrics,
            )

            # Validate expectations
            expected = flow.get("expected", {})
            self._validate_expectations(expected, context, result)

            # Validate SLAs
            sla = flow.get("sla", {})
            self._validate_sla(sla, context, result)

            # Validate architectural rules
            self._validate_architecture(expected, context, result)

        except httpx.ConnectError:
            result.passed = False
            result.errors.append("Could not connect to orchestrator")
        except Exception as e:
            result.passed = False
            result.errors.append(f"Error running flow: {str(e)}")

        return result

    async def _get_traces(self, trace_id: str, turn_id: str) -> list[dict]:
        """Get traces from the collector."""
        try:
            response = await self.client.get(
                f"{self.collector_url}/trace/turn/{trace_id}/{turn_id}",
            )
            if response.status_code == 200:
                return response.json().get("events", [])
        except Exception:
            pass
        return []

    def _calculate_metrics(self, traces: list[dict]) -> dict[str, float]:
        """Calculate latency metrics from traces."""
        events = {e["event"]: e for e in traces}
        metrics = {}

        # ASR latency: vad.end -> asr.final
        if "vad.end" in events and "asr.final" in events:
            metrics["asr_latency_ms"] = (
                events["asr.final"]["mono_ms"] - events["vad.end"]["mono_ms"]
            )

        # LLM first token: asr.final -> llm.first_token
        if "asr.final" in events and "llm.first_token" in events:
            metrics["llm_first_token_ms"] = (
                events["llm.first_token"]["mono_ms"] - events["asr.final"]["mono_ms"]
            )

        # TTS first chunk: some point -> tts.first_chunk
        if "tts.first_chunk" in events:
            # Find the earliest trace
            if "orch.turn.start" in events:
                metrics["tts_first_chunk_ms"] = (
                    events["tts.first_chunk"]["mono_ms"]
                    - events["orch.turn.start"]["mono_ms"]
                )

        # Turn duration: orch.turn.start -> orch.turn.end
        if "orch.turn.start" in events and "orch.turn.end" in events:
            metrics["turn_latency_ms"] = (
                events["orch.turn.end"]["mono_ms"]
                - events["orch.turn.start"]["mono_ms"]
            )

        return metrics

    def _validate_expectations(
        self,
        expected: dict,
        context: ValidationContext,
        result: FlowResult,
    ) -> None:
        """Validate flow expectations."""
        # Check intent
        expected_intent = expected.get("intent")
        if expected_intent and context.intent != expected_intent:
            result.passed = False
            result.errors.append(
                f"Intent mismatch: got '{context.intent}', expected '{expected_intent}'"
            )

        # Check tool calls
        expected_tools = expected.get("tool_calls", [])
        if expected_tools:
            actual_tool_names = {t.get("name") for t in context.tool_calls}
            for expected_tool in expected_tools:
                tool_name = expected_tool.get("name")
                if tool_name and tool_name not in actual_tool_names:
                    result.passed = False
                    result.errors.append(f"Expected tool '{tool_name}' was not called")

        # Check response_contains
        response_contains = expected.get("response_contains", [])
        response_lower = context.response_text.lower()
        for phrase in response_contains:
            if phrase.lower() not in response_lower:
                result.passed = False
                result.errors.append(
                    f"Response missing expected phrase: '{phrase}'"
                )

        # Check response_not_contains
        response_not_contains = expected.get("response_not_contains", [])
        for phrase in response_not_contains:
            if phrase.lower() in response_lower:
                result.passed = False
                result.errors.append(
                    f"Response contains forbidden phrase: '{phrase}'"
                )

    def _validate_sla(
        self,
        sla: dict,
        context: ValidationContext,
        result: FlowResult,
    ) -> None:
        """Validate SLA requirements."""
        sla_mapping = {
            "max_turn_latency_ms": "turn_latency_ms",
            "max_asr_latency_ms": "asr_latency_ms",
            "max_llm_first_token_ms": "llm_first_token_ms",
            "max_tts_first_chunk_ms": "tts_first_chunk_ms",
        }

        for sla_key, metric_key in sla_mapping.items():
            threshold = sla.get(sla_key)
            if threshold is not None:
                actual = context.metrics.get(metric_key)
                if actual is not None and actual > threshold:
                    result.warnings.append(
                        f"SLA violation: {metric_key}={actual:.0f}ms > {threshold}ms"
                    )

    def _validate_architecture(
        self,
        expected: dict,
        context: ValidationContext,
        result: FlowResult,
    ) -> None:
        """Validate architectural rules."""
        validator = ArchitectureValidator()

        # Validate prompt budget
        budget_errors = validator.validate_prompt_budget(context.traces)
        for error in budget_errors:
            result.warnings.append(error)

        # Validate tool enforcement if expected tools specified
        expected_tools = expected.get("tool_calls", [])
        if expected_tools:
            tool_names = [t.get("name") for t in expected_tools if t.get("name")]
            tool_errors = validator.validate_tool_enforcement(context.traces, tool_names)
            for error in tool_errors:
                result.errors.append(error)
                result.passed = False


class ArchitectureValidator:
    """Validates architectural rules from traces."""

    MAX_PROMPT_TOKENS = 900  # For simple intents

    def validate_prompt_budget(self, traces: list[dict]) -> list[str]:
        """Check if prompt budget is exceeded."""
        errors = []
        for trace in traces:
            if trace.get("event") == "llm.complete":
                tokens = trace.get("attrs", {}).get("prompt_tokens", 0)
                if tokens > self.MAX_PROMPT_TOKENS:
                    errors.append(
                        f"Prompt budget exceeded: {tokens} > {self.MAX_PROMPT_TOKENS}"
                    )
        return errors

    def validate_tool_enforcement(
        self,
        traces: list[dict],
        expected_tools: list[str],
    ) -> list[str]:
        """Check if required tools were called."""
        errors = []
        actual_tools = {
            t.get("attrs", {}).get("tool_name")
            for t in traces
            if t.get("event") == "tool.call.end"
        }

        for tool in expected_tools:
            if tool not in actual_tools:
                errors.append(f"Required tool not called: {tool}")
        return errors


def load_flows(flows_dir: Path, tag: Optional[str] = None) -> list[tuple[dict, str]]:
    """Load all golden flow YAML files.

    Args:
        flows_dir: Directory containing golden flows
        tag: Optional tag to filter flows

    Returns:
        List of (flow_dict, file_path) tuples
    """
    flows = []

    for yaml_file in flows_dir.rglob("*.yml"):
        try:
            flow = yaml.safe_load(yaml_file.read_text())
            if flow:
                # Filter by tag if specified
                if tag:
                    flow_tags = flow.get("tags", [])
                    if tag not in flow_tags:
                        continue
                flows.append((flow, str(yaml_file)))
        except Exception as e:
            print(f"Warning: Could not load {yaml_file}: {e}")

    return flows


def print_result(result: FlowResult, verbose: bool = False) -> None:
    """Print a flow result."""
    status = "\033[92m✓\033[0m" if result.passed else "\033[91m✗\033[0m"
    print(f"{status} {result.flow_name}")

    if verbose or not result.passed:
        if result.errors:
            for error in result.errors:
                print(f"   \033[91m✗\033[0m {error}")
        if result.warnings:
            for warning in result.warnings:
                print(f"   \033[93m!\033[0m {warning}")

    if verbose and result.metrics:
        metrics_str = ", ".join(
            f"{k}={v:.0f}ms" for k, v in result.metrics.items()
        )
        print(f"   Metrics: {metrics_str}")


async def main():
    parser = argparse.ArgumentParser(
        description="Run AI Kiosk golden flows and validate SLAs"
    )
    parser.add_argument(
        "--orchestrator-url",
        default="http://localhost:8765",
        help="Orchestrator URL",
    )
    parser.add_argument(
        "--collector-url",
        default="http://localhost:9010",
        help="Trace Collector URL",
    )
    parser.add_argument(
        "--flows-dir",
        default="tests/golden_flows",
        help="Golden flows directory",
    )
    parser.add_argument(
        "--tag",
        help="Only run flows with this tag",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Load flows
    flows_dir = Path(args.flows_dir)
    if not flows_dir.exists():
        print(f"Error: Flows directory not found: {flows_dir}")
        sys.exit(1)

    flows = load_flows(flows_dir, args.tag)
    if not flows:
        print("No golden flows found")
        sys.exit(1)

    if not args.json:
        print(f"\nRunning {len(flows)} golden flows...\n")

    # Run flows
    runner = GoldenFlowRunner(
        orchestrator_url=args.orchestrator_url,
        collector_url=args.collector_url,
        verbose=args.verbose,
    )

    results = []
    try:
        for flow, flow_file in flows:
            result = await runner.run_flow(flow, flow_file)
            results.append(result)

            if not args.json:
                print_result(result, args.verbose)

    finally:
        await runner.close()

    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    if args.json:
        output = {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": total - passed,
            },
            "results": [
                {
                    "name": r.flow_name,
                    "file": r.flow_file,
                    "passed": r.passed,
                    "errors": r.errors,
                    "warnings": r.warnings,
                    "metrics": r.metrics,
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'='*50}")
        if passed == total:
            print(f"\033[92m{passed}/{total} flows passed\033[0m")
        else:
            print(f"\033[91m{passed}/{total} flows passed\033[0m")

    # Exit with error if any failed
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
