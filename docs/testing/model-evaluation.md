# Model Evaluation Framework

Evaluate voice agent orchestration quality without modifying production code.

## Overview

The evaluation framework provides tools to measure agent performance across multiple dimensions:

- **Tool Calls**: Precision, recall, efficiency
- **Groundedness**: Response accuracy against evidence
- **Latency**: E2E and TTFT percentiles
- **Verbosity**: Token usage and conciseness
- **Cost**: Per-model token usage and estimated costs

### Key Features

- **Zero production changes** - Uses wrapper pattern, no code modifications
- **API-aware** - Handles both Chat Completions and Responses API
- **Comprehensive metrics** - 6 categories of evaluation metrics
- **Simple outputs** - JSONL events and JSON summaries

!!! warning "Production Isolation"
    This package should **never** be imported in production code. Import guards prevent usage when `ENV=production`.

## Quick Start

### 1. Record Evaluation Events

Wrap your orchestrator to automatically record events:

```python
from apps.artagent.backend.evaluation import (
    EventRecorder,
    EvaluationOrchestratorWrapper
)
from apps.artagent.backend.voice.speech_cascade.orchestrator import (
    CascadeOrchestratorAdapter
)
from pathlib import Path

# Create your real orchestrator
orchestrator = CascadeOrchestratorAdapter.create(
    start_agent="FraudAgent",
    agents={...},
    session_id="eval_session_001"
)

# Wrap it with evaluation recorder
recorder = EventRecorder(
    run_id="fraud_test_001",
    output_dir=Path("runs")
)
eval_orchestrator = EvaluationOrchestratorWrapper(orchestrator, recorder)

# Use it normally - recording happens automatically
result = await eval_orchestrator.process_turn(context)

# Events written to: runs/fraud_test_001_events.jsonl
```

### 2. Score the Events

Use the CLI to compute metrics:

```bash
python -m apps.artagent.backend.evaluation.cli.run \
    --input runs/fraud_test_001_events.jsonl \
    --output runs/fraud_test_001_scores
```

**Outputs:**

- `scores.jsonl` - Per-turn metrics
- `summary.json` - Aggregated metrics with console output

### 3. Review Results

```bash
# View summary
cat runs/fraud_test_001_scores/summary.json

# View per-turn scores
cat runs/fraud_test_001_scores/scores.jsonl
```

## Metrics

### Tool Call Metrics

Measures tool usage accuracy:

| Metric | Formula | Description |
|--------|---------|-------------|
| Precision | `correct_tools / total_tools_called` | Fraction of called tools that were correct |
| Recall | `correct_tools / expected_tools` | Fraction of expected tools that were called |
| Efficiency | `1 - (redundant_calls / total_calls)` | Penalizes duplicate tool calls |

!!! tip "Efficiency Measurement"
    Tool efficiency detects redundant calls using result hashing. Two calls with identical results within 30 seconds are considered redundant.

### Groundedness Metrics

Validates responses against evidence:

| Metric | Description |
|--------|-------------|
| Grounded Span Ratio | Fraction of factual claims supported by evidence |
| Unsupported Claims | Count of ungrounded statements |

Uses string matching to extract and verify:

- Numbers and amounts
- Dates
- Proper nouns

!!! note "Groundedness Implementation"
    Current implementation uses string-based matching. Consider LLM-as-judge for semantic validation in production scenarios.

### Latency Metrics

Tracks response times:

| Metric | Description |
|--------|-------------|
| E2E P50/P95/P99 | End-to-end turn time percentiles |
| TTFT | Time to first token (if captured) |

### Verbosity Metrics (API-Aware)

Measures response conciseness with API-specific budgets:

| Configuration | Token Budget | Notes |
|--------------|:------------:|-------|
| Chat API (baseline) | 150 | Standard chat responses |
| Responses API (verbosity=0) | 105 | 30% reduction for concise mode |
| Responses API (verbosity=1) | 150 | Standard |
| Responses API (verbosity=2) | 225 | 50% increase for detailed mode |
| Reasoning models (include_reasoning) | 2x | Accounts for reasoning tokens |

**Score Calculation:**

- Score = `1.0` if within budget
- Degrades to `0.0` if 2x over budget
- Linear degradation between budget and 2x budget

!!! example "Verbosity Example"
    For Responses API with `verbosity=0` (concise mode):

    - Budget: 105 tokens
    - Response: 80 tokens → Score: 1.0 (within budget)
    - Response: 150 tokens → Score: 0.70 (exceeds budget by 30%)
    - Response: 210+ tokens → Score: 0.0 (2x over budget)

### Handoff Metrics

Validates agent routing:

| Metric | Description |
|--------|-------------|
| Handoff Accuracy | Percentage of correct agent transitions |
| Total Handoffs | Count of agent switches |

### Cost Metrics

Tracks token usage and estimates costs:

- **Per-model breakdown**: Input, output, reasoning tokens
- **Estimated USD**: Based on current pricing
- **Cost distribution**: Percentage by API type

### Metrics Flow

![Metrics aggregation animation](https://flowgif.com/gif/pako:eNq9lkuPmzAQgP8Kcq5U4hEI5JZuX1ulDyWrXlZ7MGa8QUvwyjiJVlH-e8eJWYy7laomyiGBAfzx2eMZsSdrMt0TRaZktlHi3ayp1lRB6X2qxY6tqFTEJyXenS_whJNpgv8YZ0Fw8EmhxzZker8nFT6zVKfnazxfABOyRNDHLTSq9b4uf3yf471W39MohsPuQ5-sqsdVjT9FHvz7yCfPUjBo26p51BdinzCxfq5BgQ7HwzCxw4eDf9K4E6L-BkpWrDUy-op3Q-va6693IlucVGT5VA1lqtqC0Rnoxa7eP_l8lmLT4FI0OM4I2Ze8mxWwp-sqzTHHDXsxNibyfoJkmKyqhuva_AJZiLZSnc9r7C1xE11Z5gttSsG5UTGRN2NsI-lxxa6nciParpz0qfdeAn0qxa65qsVys15T2eXGRN4CnsWx2G2R-O8idhg7XmPXyxF5OL4am0xrNRn1R6W_6CZmLYkyJrdG4cPMvHxmZufinEI9m9dX2dkou0TOhvVb_GyU2aL_xRlmTw22mg2M3wDeGt4JPB6CnTxekNxn9IJQO7cXxPZZviDU5PsSRKxqdqxq_IDo28Oxoez1lwYZ8YznnJoeMyoBIkh1tCPT8DiYjGhZJEVJDtpPc_q-YoMg5hF-tRhQHjDKcwOKDCjMJ2kZ9aC3dDiPIegonBeTcelQIE3CIOgpVlsbkGJIeNKRCppmLHNIKQ2LnPak1344mFfGE8g7ThaySTZ2FiiCSRlb8wIphXSmBQVABwGe05w6MiyNsijrIe2GsVNtWS4BrnHYYcZlkVLmYIIgzROGGNxOROqRDPv6HoO6OB1xc-HxcPgNIKoLDg)

*Flowgifs animation summarizing how each metric family contributes to the final summary report.*

## Architecture

### Design Principles

1. **Zero-Touch**: No production code modifications
2. **Composition Over Inheritance**: Wrapper pattern for orchestrator
3. **One-Way Imports**: eval → production (never reverse)
4. **API-Aware**: Separate handling for Chat vs Responses API

### Components

![Instrumentation flow animation](https://flowgif.com/gif/pako:eNqtlVtP2zAUgP9KZB6Xbblf-tbRInViY4JJe0AVcuxjmilNKtsBoar_HbtxqWNAqhAPTXqa-Dvfcc5ptmiNJlsk0QRNe9l9nbb1Gkug3kXTPZIV5hL5iKqrf2fqC0OTXB1VXATBzkeVXtuiye0W1ZqgbmnU-Q_vaE9k3bXeFScrEJJj2XF1Vair1xpE1KLb0Eer-n7VqI9ES_828tGGdwSEqNt7_UPsI9KtNw1I0GEyDtNxmI3D3A6XO39Q_GEU5w-46bFWtA3_cbzZgC36oEqOLN-6xaqwBzC6I_3Y1f8E3_MXX2jlNZCO01d-8ft-dhg7uomr-xG_mfHjfSu-q8NdTe9Au4pv_0XXNo5qcrKqHSaOeeqan6Q6N6q_QPKaiBu1l6-2Mv2onx2mjm7m6r7td2H8hBYz2-d98US_XmP-tI8d2-yTbO0wc-Qd1-XeUc27MPMuzVA9WfM_jBH1qidrgqQRXRjD2dS4Tc0eCEOSpu1t4tD5whtay-p7l7ow0IGejOnnhj575VtLEN7Pm6vfl1ajvsdeGPSQIx3nmJkccyfHZYdd__SEHAuTYsiVjXPNTa4LJ9e5emC9rmg9tLrVLqfmW5h0Q97c5FVPn-yfvvrPP3bNvim3-uWAzljBSoZNn55RgAgyHT2iSbhfjM4wrdKKop2uQnOO7WaDIGaRetEYUBkQzEoDigwoLPOMRkfQWzqMxRAcKIxVeUIdCmRpGARHijWqI1IMKUsPpApnBSkcUobDqsRH0svcjOoqWArlgVOEJC8SZ4MiyGls1QWcH16eL2VBBXCAACtxiR0ZkkVFVBwhoie6rLFLoPY4PGASWmWYOJggyMqUKIxqOsT1SqI6bKuCphrOQurzbvcMeEBi0g)

*Animated with Flowgifs to highlight how the wrapper records and scores evaluation events.*

!!! info "Composition Pattern"
    The wrapper uses composition rather than inheritance to avoid modifying production code. It intercepts `process_turn()` and delegates all other calls transparently via `__getattr__`.

### Import Guards

Three layers prevent accidental production imports:

1. **Runtime checks**: Raises error if `ENV=production`
2. **Warning system**: Detects imports from production paths
3. **Package metadata**: Tracks forbidden import sources

Forbidden paths:

- `apps/artagent/backend/voice/`
- `apps/artagent/backend/api/`
- `apps/artagent/backend/registries/`

## API Reference

### EventRecorder

Records orchestration events to JSONL.

**Initialization:**

```python
recorder = EventRecorder(
    run_id: str,           # Unique identifier for this run
    output_dir: Path       # Directory for events.jsonl
)
```

**Methods** (automatically called by wrapper):

- `record_turn_start(turn_id, agent, user_text, timestamp)`
- `record_tool_start(tool_name, arguments, timestamp)`
- `record_tool_end(tool_name, result, end_ts, start_ts)`
- `record_handoff(source_agent, target_agent, timestamp)`
- `record_turn_end(turn_id, agent, response_text, e2e_ms, ...)`

### EvaluationOrchestratorWrapper

Wraps orchestrator to inject recording.

**Initialization:**

```python
wrapper = EvaluationOrchestratorWrapper(
    orchestrator: CascadeOrchestratorAdapter,  # Custom Cascade Orchestrator
    recorder: EventRecorder
)
```

**Usage:**

```python
# Drop-in replacement for orchestrator
result = await wrapper.process_turn(context, **kwargs)
```

### MetricsScorer

Computes metrics from recorded events.

**Basic Usage:**

```python
from apps.artagent.backend.evaluation.scorer import MetricsScorer

scorer = MetricsScorer()

# Load events
events = scorer.load_events(Path("runs/test_events.jsonl"))

# Score single turn
turn_score = scorer.score_turn(event)

# Generate summary
summary = scorer.generate_summary(events)
```

### CLI

Score events from command line:

```bash
python -m apps.artagent.backend.evaluation.cli.run \
    --input <events.jsonl> \
    --output <output_dir> \
    --verbose
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--input` | Path to events.jsonl file | Required |
| `--output` | Output directory | Same as input directory |
| `--verbose` | Show detailed output | False |

## Event Schema

### TurnEvent

Complete record of a conversation turn:

```python
{
    "session_id": str,
    "turn_id": str,
    "agent_name": str,
    "user_text": str,
    "response_text": str,
    "e2e_ms": float,
    "tool_calls": [ToolCall],
    "evidence_blobs": [EvidenceBlob],
    "eval_model_config": EvalModelConfig,
    # ... additional fields
}
```

### EvalModelConfig

API-aware model configuration:

**Chat Completions API:**

```python
{
    "model_name": "gpt-4o",
    "endpoint_used": "chat",
    "temperature": 0.7,
    "top_p": 0.9,
    "max_tokens": 150
}
```

**Responses API:**

```python
{
    "model_name": "o1-preview",
    "endpoint_used": "responses",
    "verbosity": 0,  # 0=concise, 1=standard, 2=detailed
    "reasoning_effort": "medium",
    "max_completion_tokens": 500
}
```

## Usage Patterns

### Compare Model Configurations

Test different configurations on the same scenarios:

```python
# Test 1: GPT-4o with temperature=0.7
recorder1 = EventRecorder(run_id="gpt4o_temp07", ...)
eval_orch1 = EvaluationOrchestratorWrapper(orch1, recorder1)
await eval_orch1.process_turn(context)

# Test 2: o1-preview with verbosity=1
recorder2 = EventRecorder(run_id="o1_verbosity1", ...)
eval_orch2 = EvaluationOrchestratorWrapper(orch2, recorder2)
await eval_orch2.process_turn(context)

# Compare results
# Both runs produce summary.json for comparison
```

### Monitor Verbosity Changes

Track if responses stay concise:

```bash
# Before prompt change
python -m apps.artagent.backend.evaluation.cli.run \
    --input baseline_events.jsonl

# After prompt change
python -m apps.artagent.backend.evaluation.cli.run \
    --input new_prompt_events.jsonl

# Compare verbosity_metrics in both summary.json files
```

### Validate Tool Usage

Ensure agents call expected tools:

1. Record events with specific user inputs
2. Review `tool_calls` in events.jsonl
3. Check tool_precision and tool_recall in summary

## Validation

The framework includes automated tests to validate functionality:

```bash
# Run all validation tests
python apps/artagent/backend/evaluation/validate_phases.py

# Run specific phase
python apps/artagent/backend/evaluation/validate_phases.py --phase 1
python apps/artagent/backend/evaluation/validate_phases.py --phase 2
```

!!! success "Validation Status"
    - **Phase 1**: 7/7 tests passing
    - **Phase 2**: 5/6 tests passing (1 known limitation)

    See [Validation Manifest](../../apps/artagent/backend/evaluation/VALIDATION.md) for details.

## Limitations

### Current Scope

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Complete | Recording and instrumentation |
| Phase 2 | Complete | Metrics scoring |
| Phase 3 | Planned | Scenario runner (YAML-based) |
| Phase 4 | Planned | CI integration |
| Phase 5 | Planned | Cost optimization |

### Known Limitations

!!! warning "Groundedness String Matching"
    Current implementation uses strict string matching:

    **May miss:**

    - Formatting differences: `$1,234` vs `1234`
    - Date variations: `12/25/2024` vs `2024-12-25`
    - Synonyms: `Seattle` vs `Seattle, WA`

    **Future improvements:**

    - Add normalization for numbers and dates
    - Consider LLM-as-judge for semantic validation

!!! info "No Scenario Runner"
    **Current state:**

    - Manual conversation recording required
    - No automated multi-turn scenarios
    - No YAML scenario support

    **Planned for Phase 3:**

    - YAML scenario definitions
    - Automated multi-turn execution
    - Expected behavior validation

!!! info "No CI Integration"
    **Current state:**

    - Manual test execution
    - No golden test baselines
    - No automated regression detection

    **Planned for Phase 4:**

    - GitHub Actions integration
    - Golden scenario comparison
    - Threshold-based pass/fail

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError`:

```bash
# Set Python path
export PYTHONPATH=/path/to/art-voice-agent-accelerator:$PYTHONPATH
```

### Production Import Warning

If you see import warnings:

```
⚠️ WARNING: Evaluation package imported from production module
```

**Fix**: Move evaluation imports to test files only. The evaluation package should never be imported in production paths.

### Events Not Recording

Check:

1. EventRecorder output directory exists
2. Wrapper is being used (not original orchestrator)
3. Callbacks are firing (check logs)

## Next Steps

Planned enhancements:

- **Phase 3**: YAML scenario runner for repeatable tests
- **Phase 4**: CI integration with golden test baselines
- **Phase 5**: Cost optimization and agent selection

## Related Documentation

- [Package README](../../apps/artagent/backend/evaluation/README.md) - Package overview
- [Validation Manifest](../../apps/artagent/backend/evaluation/VALIDATION.md) - Validated features

## Support

For questions or issues:

- Review validation tests: `validate_phases.py`
- Check package README for examples
- Consult architecture documentation above
