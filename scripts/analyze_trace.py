#!/usr/bin/env python3
"""
CLI tool for analyzing AI Kiosk traces.

Usage:
    python scripts/analyze_trace.py <trace_id>
    python scripts/analyze_trace.py --golden-flow tests/golden_flows/navigation/store_location.yml
    python scripts/analyze_trace.py --list
"""

import argparse
import json
import sys
from pathlib import Path

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "shared"))

try:
    from tracing import TraceCollectorClient, GoldenFlow
    from tracing.collector import load_golden_flow
except ImportError:
    print("Error: Could not import tracing module")
    print("Make sure services/shared/tracing exists")
    sys.exit(1)


def analyze_trace(trace_id: str, traces_dir: str = "data/traces"):
    """Analyze a specific trace."""
    client = TraceCollectorClient(traces_dir=traces_dir)

    try:
        events = client.load_trace_from_file(trace_id)
    except FileNotFoundError:
        print(f"Error: Trace not found: {trace_id}")
        print(f"Looking in: {traces_dir}")
        sys.exit(1)

    analysis = client.analyze(events)

    # Print results
    print(f"\n{'='*60}")
    print(f"Trace Analysis: {trace_id}")
    print(f"{'='*60}\n")

    print(f"Events: {len(analysis.events)}")
    print(f"Turns: {analysis.turn_count}")
    print(f"Total Duration: {analysis.total_duration_ms:.2f}ms")

    print(f"\n--- Latencies ---")
    for key, value in sorted(analysis.latencies.items()):
        print(f"  {key}: {value:.2f}ms")

    if analysis.violations:
        print(f"\n--- Violations ({len(analysis.violations)}) ---")
        for v in analysis.violations:
            severity_icon = {"warning": "⚠️", "error": "❌", "critical": "🔴"}.get(v.severity, "•")
            print(f"  {severity_icon} [{v.type}] {v.message}")
    else:
        print(f"\n✅ No violations detected")

    print(f"\n--- Timeline ---")
    for entry in analysis.timeline[:20]:  # First 20 events
        print(f"  {entry['offset_ms']:8.2f}ms | {entry['service']:12} | {entry['event']}")

    if len(analysis.timeline) > 20:
        print(f"  ... and {len(analysis.timeline) - 20} more events")


def validate_golden_flow(flow_path: str, trace_id: str = None, traces_dir: str = "data/traces"):
    """Validate a trace against a golden flow."""
    try:
        import yaml
        with open(flow_path) as f:
            data = yaml.safe_load(f)
        golden_flow = GoldenFlow.from_dict(data)
    except Exception as e:
        print(f"Error loading golden flow: {e}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Golden Flow: {golden_flow.name}")
    print(f"{'='*60}")
    print(f"Description: {golden_flow.description}")
    print(f"Input: {golden_flow.input_text}")

    if trace_id:
        client = TraceCollectorClient(traces_dir=traces_dir)
        try:
            events = client.load_trace_from_file(trace_id)
        except FileNotFoundError:
            print(f"Error: Trace not found: {trace_id}")
            sys.exit(1)

        analysis = client.analyze(events, golden_flow)

        print(f"\n--- SLA Check ---")
        sla = golden_flow.sla
        print(f"  max_turn_latency: {sla.max_turn_latency_ms}ms")
        print(f"  max_asr_latency: {sla.max_asr_latency_ms}ms")
        print(f"  max_llm_first_token: {sla.max_llm_first_token_ms}ms")

        if analysis.violations:
            print(f"\n--- Violations ({len(analysis.violations)}) ---")
            for v in analysis.violations:
                severity_icon = {"warning": "⚠️", "error": "❌", "critical": "🔴"}.get(v.severity, "•")
                print(f"  {severity_icon} [{v.type}] {v.message}")
            print(f"\n❌ Validation FAILED")
        else:
            print(f"\n✅ Validation PASSED")
    else:
        print("\nExpected:")
        print(f"  Intent: {golden_flow.expected.intent}")
        if golden_flow.expected.info_type:
            print(f"  Info Type: {golden_flow.expected.info_type}")
        if golden_flow.expected.tool_calls:
            print(f"  Tool Calls:")
            for tc in golden_flow.expected.tool_calls:
                print(f"    - {tc.name}")
        if golden_flow.expected.response_contains:
            print(f"  Response Contains: {golden_flow.expected.response_contains}")
        if golden_flow.expected.response_not_contains:
            print(f"  Response NOT Contains: {golden_flow.expected.response_not_contains}")

        print(f"\nSLA:")
        sla = golden_flow.sla
        print(f"  max_turn_latency: {sla.max_turn_latency_ms}ms")
        print(f"  max_asr_latency: {sla.max_asr_latency_ms}ms")
        print(f"  max_llm_first_token: {sla.max_llm_first_token_ms}ms")


def list_traces(traces_dir: str = "data/traces"):
    """List available traces."""
    sessions_dir = Path(traces_dir) / "sessions"
    if not sessions_dir.exists():
        print(f"No traces found in {traces_dir}")
        return

    traces = sorted(sessions_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)

    print(f"\n{'='*60}")
    print(f"Available Traces ({len(traces)})")
    print(f"{'='*60}\n")

    for trace_dir in traces[:20]:
        events_file = trace_dir / "events.jsonl"
        if events_file.exists():
            with open(events_file) as f:
                event_count = sum(1 for _ in f)
            print(f"  {trace_dir.name} ({event_count} events)")

    if len(traces) > 20:
        print(f"\n  ... and {len(traces) - 20} more traces")


def list_golden_flows(flows_dir: str = "tests/golden_flows"):
    """List available golden flows."""
    flows_path = Path(flows_dir)
    if not flows_path.exists():
        print(f"No golden flows found in {flows_dir}")
        return

    print(f"\n{'='*60}")
    print(f"Available Golden Flows")
    print(f"{'='*60}\n")

    for yaml_file in sorted(flows_path.rglob("*.yml")):
        relative = yaml_file.relative_to(flows_path)
        print(f"  {relative}")


def main():
    parser = argparse.ArgumentParser(description="Analyze AI Kiosk traces")
    parser.add_argument("trace_id", nargs="?", help="Trace ID to analyze")
    parser.add_argument("--golden-flow", "-g", help="Golden flow YAML to validate against")
    parser.add_argument("--list", "-l", action="store_true", help="List available traces")
    parser.add_argument("--list-flows", action="store_true", help="List available golden flows")
    parser.add_argument("--traces-dir", default="data/traces", help="Directory containing traces")

    args = parser.parse_args()

    if args.list:
        list_traces(args.traces_dir)
    elif args.list_flows:
        list_golden_flows()
    elif args.golden_flow:
        validate_golden_flow(args.golden_flow, args.trace_id, args.traces_dir)
    elif args.trace_id:
        analyze_trace(args.trace_id, args.traces_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
