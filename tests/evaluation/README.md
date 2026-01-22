# Evaluation Package

Model-to-model evaluation framework for voice agent orchestration.

## Quick Start

### Interactive Notebook (Recommended)

The easiest way to explore and validate the evaluation framework:

```bash
# Open in VS Code / Jupyter
samples/labs/dev/evaluation_framework_validation.ipynb
```

This notebook demonstrates:
- Event recording and inspection
- Metrics scoring (tool precision/recall, latency, groundedness)
- Azure AI Foundry submission
- CLI command usage

### Automated Testing with Pytest

Run evaluation scenarios as automated tests:

```bash
# Run all evaluation tests
pytest tests/evaluation/test_scenarios.py -v -m evaluation

# Run specific scenario type
pytest tests/evaluation/test_scenarios.py -k "session" -v

# Run A/B comparison tests
pytest tests/evaluation/test_scenarios.py -k "ab_comparison" -v

# Skip slow E2E tests (use existing data only)
pytest tests/evaluation/test_scenarios.py -m "evaluation and not slow"

# Submit results to Azure AI Foundry
pytest tests/evaluation/test_scenarios.py --submit-to-foundry
```

### CLI Commands

```bash
# Score existing events
python -m tests.evaluation.cli score \
    --input runs/my_run_events.jsonl \
    --output runs/my_run_scores

# Run a scenario
python -m tests.evaluation.cli scenario \
    --input tests/evaluation/scenarios/session_based/banking_multi_agent.yaml

# Run A/B comparison
python -m tests.evaluation.cli compare \
    --input tests/evaluation/scenarios/ab_tests/fraud_detection_comparison.yaml

# Submit to Azure AI Foundry
python -m tests.evaluation.cli submit \
    --input runs/my_run/foundry_eval.jsonl \
    --endpoint "$AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"
```

## Package Structure

```text
tests/evaluation/
├── __init__.py              # Package exports + import guards
├── schemas.py               # Pydantic models (TurnEvent, ToolCall, etc.)
├── recorder.py              # EventRecorder - captures events to JSONL
├── wrappers.py              # EvaluationOrchestratorWrapper
├── scorer.py                # MetricsScorer - computes metrics
├── validator.py             # ExpectationValidator - validates against YAML
├── scenario_runner.py       # ScenarioRunner + ComparisonRunner
├── foundry_exporter.py      # Azure AI Foundry integration
├── conftest.py              # Pytest fixtures
├── test_scenarios.py        # Pytest test runner for scenarios
├── cli/
│   └── __main__.py          # CLI (score, scenario, compare, submit)
├── scenarios/
│   ├── scenario.schema.json # JSON Schema for YAML validation
│   ├── session_based/       # Multi-agent session scenarios
│   │   ├── banking_multi_agent.yaml
│   │   └── all_agents_discovery.yaml
│   └── ab_tests/            # A/B comparison scenarios
│       └── fraud_detection_comparison.yaml
└── README.md                # This file
```

## Test Scenarios

### Session-Based Scenarios

Test multi-agent conversations with handoffs:

```yaml
# scenarios/session_based/banking_multi_agent.yaml
scenario_name: banking_multi_agent
session_config:
  agents: [BankingConcierge, CardRecommendation, InvestmentAdvisor]
  start_agent: BankingConcierge
  generic_handoff:
    enabled: true
turns:
  - turn_id: turn_1
    user_input: "I'd like to check my account"
    expectations:
      tools_called: [verify_client_identity]
```

### A/B Comparison Scenarios

Compare model configurations:

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
| `MetricsScorer` | Computes tool precision/recall, latency, groundedness |
| `ExpectationValidator` | Validates events against YAML expectations |
| `ScenarioRunner` | Executes session-based scenarios |
| `ComparisonRunner` | Runs A/B comparison tests |
| `FoundryExporter` | Exports to Azure AI Foundry format |

## Pytest Markers

```python
@pytest.mark.evaluation  # All evaluation tests
@pytest.mark.slow        # E2E tests that execute scenarios
```

## Import Guards

This package should **NEVER** be imported in production code.
Runtime checks prevent imports when `ENV=production`.
