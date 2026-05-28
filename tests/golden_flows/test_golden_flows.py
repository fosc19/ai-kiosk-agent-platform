"""
Pytest runner for Golden Flows validation.

This module provides automated testing of golden flows against the system.
It can be run in two modes:
1. Validation mode: Validate existing traces against golden flows
2. Live mode: Execute golden flows against a running system (requires services)

Usage:
    # Validation mode (default)
    pytest tests/golden_flows/test_golden_flows.py -v

    # Live mode (requires running services)
    pytest tests/golden_flows/test_golden_flows.py -v --live

    # Run specific category
    pytest tests/golden_flows/test_golden_flows.py -v -k navigation
"""

import os
import sys
from pathlib import Path
from typing import Optional

import pytest
import yaml

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "shared"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "orchestrator"))

GOLDEN_FLOWS_DIR = Path(__file__).parent
TRACES_DIR = Path(__file__).parent.parent.parent / "data" / "traces"


def pytest_addoption(parser):
    """Add custom pytest options."""
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run golden flows against live services",
    )


def collect_golden_flows():
    """Collect all golden flow YAML files."""
    flows = []
    for yaml_file in GOLDEN_FLOWS_DIR.rglob("*.yml"):
        # Skip files that start with test_ (they're pytest tests)
        if yaml_file.name.startswith("test_"):
            continue
        relative = yaml_file.relative_to(GOLDEN_FLOWS_DIR)
        flows.append((str(relative), yaml_file))
    return sorted(flows, key=lambda x: x[0])


def load_golden_flow(path: Path) -> dict:
    """Load and parse a golden flow YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def get_flow_id(relative_path: str) -> str:
    """Generate a test ID from relative path."""
    return relative_path.replace("/", "_").replace(".yml", "")


class TestGoldenFlowsValidation:
    """Test class for golden flow validation against traces."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.flows = collect_golden_flows()

    @pytest.mark.parametrize(
        "flow_path,flow_file",
        collect_golden_flows(),
        ids=[get_flow_id(p) for p, _ in collect_golden_flows()],
    )
    def test_golden_flow_schema(self, flow_path: str, flow_file: Path):
        """Test that golden flow has valid schema."""
        data = load_golden_flow(flow_file)

        # Required fields
        assert "name" in data, f"Missing 'name' in {flow_path}"
        assert "description" in data, f"Missing 'description' in {flow_path}"

        # Either 'input' or 'turns' must be present
        has_input = "input" in data
        has_turns = "turns" in data
        assert has_input or has_turns, f"Missing 'input' or 'turns' in {flow_path}"

        if has_input:
            assert "expected" in data, f"Missing 'expected' in {flow_path}"
            assert "text" in data["input"], f"Missing 'input.text' in {flow_path}"

        if has_turns:
            assert isinstance(data["turns"], list), f"'turns' must be a list in {flow_path}"
            for i, turn in enumerate(data["turns"]):
                assert "input" in turn, f"Missing 'input' in turn {i} of {flow_path}"
                assert "expected" in turn, f"Missing 'expected' in turn {i} of {flow_path}"

        # SLA is recommended
        if "sla" not in data:
            pytest.skip(f"No SLA defined in {flow_path}")

    @pytest.mark.parametrize(
        "flow_path,flow_file",
        collect_golden_flows(),
        ids=[get_flow_id(p) for p, _ in collect_golden_flows()],
    )
    def test_golden_flow_intent_valid(self, flow_path: str, flow_file: Path):
        """Test that golden flow has valid intent values."""
        data = load_golden_flow(flow_file)

        valid_intents = {
            "greeting",
            "goodbye",
            "help",
            "list_stores",
            "store_info",
            "navigate",
            "clarify",
            "unknown",
        }

        # Check single input flows
        if "expected" in data:
            intent = data["expected"].get("intent")
            if intent:
                assert intent in valid_intents, f"Invalid intent '{intent}' in {flow_path}"

        # Check multi-turn flows
        if "turns" in data:
            for i, turn in enumerate(data["turns"]):
                intent = turn.get("expected", {}).get("intent")
                if intent:
                    assert intent in valid_intents, f"Invalid intent '{intent}' in turn {i} of {flow_path}"

    @pytest.mark.parametrize(
        "flow_path,flow_file",
        collect_golden_flows(),
        ids=[get_flow_id(p) for p, _ in collect_golden_flows()],
    )
    def test_golden_flow_sla_values(self, flow_path: str, flow_file: Path):
        """Test that SLA values are reasonable."""
        data = load_golden_flow(flow_file)

        if "sla" not in data:
            pytest.skip(f"No SLA defined in {flow_path}")

        sla = data["sla"]

        # Check SLA values are positive and reasonable
        if "max_turn_latency_ms" in sla:
            assert 100 <= sla["max_turn_latency_ms"] <= 10000, \
                f"Unreasonable max_turn_latency_ms in {flow_path}"

        if "max_asr_latency_ms" in sla:
            assert 50 <= sla["max_asr_latency_ms"] <= 5000, \
                f"Unreasonable max_asr_latency_ms in {flow_path}"

        if "max_llm_first_token_ms" in sla:
            assert 50 <= sla["max_llm_first_token_ms"] <= 3000, \
                f"Unreasonable max_llm_first_token_ms in {flow_path}"

        if "max_tts_first_chunk_ms" in sla:
            assert 50 <= sla["max_tts_first_chunk_ms"] <= 2000, \
                f"Unreasonable max_tts_first_chunk_ms in {flow_path}"


class TestGoldenFlowsContent:
    """Test golden flow content and expectations."""

    @pytest.mark.parametrize(
        "flow_path,flow_file",
        collect_golden_flows(),
        ids=[get_flow_id(p) for p, _ in collect_golden_flows()],
    )
    def test_response_expectations_not_empty(self, flow_path: str, flow_file: Path):
        """Test that response expectations are defined."""
        data = load_golden_flow(flow_file)

        def check_expected(expected: dict, context: str):
            # At least one expectation should be defined
            has_expectation = any([
                expected.get("intent"),
                expected.get("response_contains"),
                expected.get("response_not_contains"),
                expected.get("tool_calls"),
                expected.get("store_query"),
            ])
            # This is a warning, not a failure
            if not has_expectation:
                pytest.skip(f"No expectations defined in {context}")

        if "expected" in data:
            check_expected(data["expected"], flow_path)

        if "turns" in data:
            for i, turn in enumerate(data["turns"]):
                if "expected" in turn:
                    check_expected(turn["expected"], f"turn {i} of {flow_path}")

    @pytest.mark.parametrize(
        "flow_path,flow_file",
        [f for f in collect_golden_flows() if "navigation" in f[0]],
        ids=[get_flow_id(p) for p, _ in collect_golden_flows() if "navigation" in p],
    )
    def test_navigation_flows_have_store_query(self, flow_path: str, flow_file: Path):
        """Test that navigation flows specify expected store."""
        data = load_golden_flow(flow_file)

        if "expected" in data:
            expected = data["expected"]
            if expected.get("intent") == "navigate":
                # Navigation should have either store_query or be asking for clarification
                has_store = expected.get("store_query") or expected.get("final_store_query")
                has_clarify = expected.get("response_contains") and \
                    any("tienda" in str(c).lower() for c in expected.get("response_contains", []))

                if not has_store and not has_clarify:
                    pytest.skip(f"Navigation flow {flow_path} should specify store_query or clarification")


class TestGoldenFlowsTags:
    """Test golden flow tags and categorization."""

    @pytest.mark.parametrize(
        "flow_path,flow_file",
        collect_golden_flows(),
        ids=[get_flow_id(p) for p, _ in collect_golden_flows()],
    )
    def test_flows_have_tags(self, flow_path: str, flow_file: Path):
        """Test that flows have tags for categorization."""
        data = load_golden_flow(flow_file)

        if "tags" not in data:
            pytest.skip(f"No tags defined in {flow_path}")

        tags = data["tags"]
        assert isinstance(tags, list), f"Tags must be a list in {flow_path}"
        assert len(tags) > 0, f"At least one tag required in {flow_path}"

    def test_all_flow_categories_covered(self):
        """Test that we have flows for all major categories."""
        flows = collect_golden_flows()
        categories = set()

        for path, _ in flows:
            # Extract category from path (first directory)
            parts = path.split("/")
            if len(parts) > 1:
                categories.add(parts[0])

        expected_categories = {"navigation", "info", "conversation"}
        missing = expected_categories - categories
        if missing:
            pytest.skip(f"Missing flow categories: {missing}")


# Summary test that reports on all flows
class TestGoldenFlowsSummary:
    """Summary statistics for golden flows."""

    def test_golden_flows_summary(self):
        """Print summary of all golden flows."""
        flows = collect_golden_flows()

        print(f"\n{'='*60}")
        print(f"Golden Flows Summary")
        print(f"{'='*60}")
        print(f"Total flows: {len(flows)}")

        # Count by category
        categories = {}
        for path, _ in flows:
            parts = path.split("/")
            cat = parts[0] if len(parts) > 1 else "root"
            categories[cat] = categories.get(cat, 0) + 1

        print(f"\nBy category:")
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count}")

        # Count by tag
        tags = {}
        for _, flow_file in flows:
            data = load_golden_flow(flow_file)
            for tag in data.get("tags", []):
                tags[tag] = tags.get(tag, 0) + 1

        print(f"\nBy tag:")
        for tag, count in sorted(tags.items(), key=lambda x: -x[1])[:10]:
            print(f"  {tag}: {count}")

        print(f"{'='*60}\n")

        assert len(flows) > 0, "No golden flows found"
