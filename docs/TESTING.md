# Testing

The repository contains representative unit, integration and golden-flow tests.

## Python syntax check

```bash
python -m compileall services scripts tests
```

## Golden flows

Golden flows define expected conversational paths and latency budgets.

```bash
python scripts/run_golden_flows.py tests/golden_flows
```

## Full test task

```bash
task test
```

Some tests require local services or provider-specific dependencies. In a portfolio review, the important part is the structure: flows, service boundaries, tracing and validation logic.
