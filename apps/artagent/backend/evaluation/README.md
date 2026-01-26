# Evaluation Package

Model-to-model evaluation framework for voice agent orchestration.

## Quick Links

📚 **[Full Documentation](../../../../docs/testing/model-evaluation.md)** - Complete guide with examples

📋 **[Validation Status](./VALIDATION.md)** - What's been validated

📝 **[Phase 3 Simplification](./PHASE3_SIMPLIFIED.md)** - Consolidated architecture

## Quick Start

### 1. Record Events

```python
from apps.artagent.backend.evaluation import (
    EventRecorder,
    EvaluationOrchestratorWrapper
)
from pathlib import Path

# Wrap your orchestrator
recorder = EventRecorder(run_id="test_001", output_dir=Path("runs"))
eval_orch = EvaluationOrchestratorWrapper(your_orchestrator, recorder)

# Use normally - recording happens automatically
await eval_orch.process_turn(context)
```

### 2. Score Events (Unified CLI)

```bash
# Score existing events
python -m apps.artagent.backend.evaluation.cli score \
    --input runs/test_001_events.jsonl \
    --output runs/test_001_scores

# Run a scenario
python -m apps.artagent.backend.evaluation.cli scenario \
    --input tests/eval_scenarios/fraud_basic.yaml

# Run A/B comparison
python -m apps.artagent.backend.evaluation.cli compare \
    --input tests/eval_scenarios/ab_tests/fraud_detection_comparison.yaml
```

## Package Structure

```text
evaluation/
├── __init__.py              # Package exports + import guards
├── schemas.py               # Pydantic models (TurnEvent, etc.)
├── recorder.py              # EventRecorder
├── wrappers.py              # EvaluationOrchestratorWrapper
├── scorer.py                # MetricsScorer
├── validate_phases.py       # Validation tests
├── cli/
│   └── run.py              # CLI interface
├── README.md               # This file
└── VALIDATION.md           # Validated features
```

## Key Principles

✅ **Zero production changes** - Wrapper pattern, no code modifications
✅ **API-aware** - Handles Chat Completions and Responses API
✅ **Import guards** - Prevents accidental production imports
✅ **One-way imports** - eval → production (never reverse)

## Validation

Run automated tests:

```bash
# All tests
python apps/artagent/backend/evaluation/validate_phases.py

# Specific phase
python apps/artagent/backend/evaluation/validate_phases.py --phase 1
```

## Components

### Core (Phases 1-2)

- **EventRecorder**: Records orchestration events to JSONL
- **EvaluationOrchestratorWrapper**: Wraps orchestrator via composition
- **MetricsScorer**: Computes 6 categories of metrics + comparisons

### Scenario Running (Phase 3)

- **ScenarioRunner**: Executes YAML scenarios
- **ComparisonRunner**: Runs A/B tests
- **MockMemoManager**: Minimal test mocks
- **Unified CLI**: Single entry point with subcommands

## Documentation

For complete documentation including:
- Architecture overview
- API reference
- Usage examples
- Metrics definitions
- Troubleshooting

See: **[docs/testing/model-evaluation.md](../../../../docs/testing/model-evaluation.md)**

## Import Guards

This package should **NEVER** be imported in production code:

❌ Production paths (forbidden):

- `apps/artagent/backend/voice/`
- `apps/artagent/backend/api/`
- `apps/artagent/backend/registries/`

✅ Allowed paths:

- Test files
- Evaluation scripts
- CI jobs

Runtime checks prevent production imports when `ENV=production`.
