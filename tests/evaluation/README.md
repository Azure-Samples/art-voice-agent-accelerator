# Evaluation Package

Simplified evaluation framework for voice agent orchestration.

## Quick Start

### Makefile Targets (Recommended)

```bash
# Interactive CLI - browse and run scenarios
make eval

# Run a single scenario with streaming output
make eval-run SCENARIO=tests/evaluation/scenarios/session_based/banking_multi_agent.yaml

# Run all scenarios by category
make eval-smoke       # Quick validation tests
make eval-session     # Multi-turn, multi-agent flows
make eval-ab          # A/B model comparisons
```

### Python CLI (Direct)

```bash
# Interactive menu
python tests/evaluation/eval_cli.py

# Run a scenario (auto-detects single vs A/B comparison)
python tests/evaluation/run-eval-stream.py run \
    --input tests/evaluation/scenarios/session_based/banking_multi_agent.yaml

# Module-based CLI (lower-level)
python -m tests.evaluation.cli run \
    --input tests/evaluation/scenarios/session_based/banking_multi_agent.yaml

# Submit to Azure AI Foundry
python -m tests.evaluation.cli submit \
    --data runs/my_run/foundry_eval.jsonl \
    --endpoint "$AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"
```

### Pytest

```bash
# Run all evaluation tests
pytest tests/evaluation/test_scenarios.py -v

# Run specific scenario
pytest tests/evaluation/test_scenarios.py -k "banking" -v
```

## Package Structure

```text
tests/evaluation/
├── __init__.py              # Package exports
├── schemas/                 # Pydantic models
│   ├── config.py            # SessionAgentConfig
│   ├── events.py            # TurnEvent, ToolCall, HandoffEvent
│   ├── expectations.py      # ScenarioExpectations
│   ├── results.py           # TurnScore, RunSummary
│   └── foundry.py           # Azure AI Foundry types
├── recorder.py              # EventRecorder - captures events to JSONL
├── wrappers.py              # EvaluationOrchestratorWrapper
├── scorer.py                # MetricsScorer - computes metrics
├── validator.py             # ExpectationValidator
├── scenario_runner.py       # ScenarioRunner + ComparisonRunner
├── foundry_exporter.py      # Azure AI Foundry integration
├── conftest.py              # Pytest fixtures
├── test_scenarios.py        # Pytest test runner
├── cli/
│   └── __main__.py          # CLI (run, submit)
├── scenarios/
│   ├── scenario.schema.json # JSON Schema for YAML validation
│   ├── session_based/       # Multi-agent session scenarios
│   └── ab_tests/            # A/B comparison scenarios
└── README.md                # This file
```

## Test Scenarios

### Session-Based Scenarios

```yaml
# scenarios/session_based/banking_multi_agent.yaml
scenario_name: banking_multi_agent
session_config:
  agents: [BankingConcierge, CardRecommendation]
  start_agent: BankingConcierge
turns:
  - turn_id: turn_1
    user_input: "I'd like to check my account"
    expectations:
      tools_called: [verify_client_identity]
```

### A/B Comparison Scenarios

```yaml
# scenarios/ab_tests/fraud_detection_comparison.yaml
comparison_name: fraud_model_comparison
variants:
  - variant_id: gpt4o
    model_override: {deployment_id: gpt-4o}
  - variant_id: gpt4o_mini
    model_override: {deployment_id: gpt-4o-mini}
turns:
  - turn_id: turn_1
    user_input: "I see charges I didn't make"
```

## Key Components

| Component | Purpose |
|-----------|---------|
| `EventRecorder` | Records orchestration events to JSONL |
| `MetricsScorer` | Computes tool precision/recall, latency |
| `ExpectationValidator` | Validates events against YAML expectations |
| `ScenarioRunner` | Executes session-based scenarios |
| `ComparisonRunner` | Runs A/B comparison tests |
| `FoundryExporter` | Exports to Azure AI Foundry format |

## Import Guards

This package should **NEVER** be imported in production code.
Runtime checks prevent imports when `ENV=production`.
