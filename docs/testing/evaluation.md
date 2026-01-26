# Evaluation Framework

Simplified evaluation framework for testing voice agent scenarios.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLI (run / submit)                          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
            ┌───────────────────┴───────────────────┐
            ▼                                       ▼
┌─────────────────────┐                 ┌─────────────────────┐
│   ScenarioRunner    │                 │  ComparisonRunner   │
│   (single YAML)     │◀────────────────│   (A/B tests)       │
└─────────┬───────────┘                 └─────────────────────┘
          │                              Creates ScenarioRunner
          │                              per variant
          ▼
┌─────────────────────┐     ┌───────────────────┐
│ EvaluationOrchest-  │────▶│   EventRecorder   │
│ ratorWrapper        │     │  (JSONL writer)   │
│ (event capture)     │     └───────────────────┘
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐     ┌───────────────────┐
│   MetricsScorer     │────▶│  FoundryExporter  │
│ (precision/recall)  │     │  (cloud eval)     │
└─────────────────────┘     └───────────────────┘
```

## Core Components

| Component | File | Purpose |
|-----------|------|---------|
| `ScenarioRunner` | `scenario_runner.py` | Loads YAML, runs turns, generates summary |
| `ComparisonRunner` | `scenario_runner.py` | Runs variants, generates comparison report |
| `EvaluationOrchestratorWrapper` | `wrappers.py` | Captures events during orchestration |
| `EventRecorder` | `recorder.py` | Writes turn events to JSONL |
| `MetricsScorer` | `scorer.py` | Computes tool precision/recall, latency |
| `ExpectationValidator` | `validator.py` | Validates turn results against expectations |
| `FoundryExporter` | `foundry_exporter.py` | Exports to Azure AI Foundry format |


## Quick Start

```bash
# Run a single scenario
python -m tests.evaluation.cli run --input tests/evaluation/scenarios/smoke/basic_identity_verification.yaml

# Run an A/B comparison (auto-detected from YAML)
python -m tests.evaluation.cli run --input tests/evaluation/scenarios/ab_tests/fraud_detection_comparison.yaml

# Submit results to Azure AI Foundry
python -m tests.evaluation.cli submit --data runs/my_scenario/foundry_eval.jsonl
```

## CLI Reference

### `run` - Execute Scenarios

Runs a scenario or A/B comparison. The type is auto-detected from the YAML structure.

```bash
python -m tests.evaluation.cli run --input <yaml_file> [--output <directory>]
```

| Option | Description |
|--------|-------------|
| `--input`, `-i` | Path to scenario YAML file (required) |
| `--output`, `-o` | Output directory (default: `runs/`) |

**Examples:**

```bash
# Run smoke test
python -m tests.evaluation.cli run -i tests/evaluation/scenarios/smoke/basic_identity_verification.yaml

# Run with custom output directory
python -m tests.evaluation.cli run -i tests/evaluation/scenarios/session_based/banking_multi_agent.yaml -o runs/my_test

# Run A/B comparison
python -m tests.evaluation.cli run -i tests/evaluation/scenarios/ab_tests/fraud_detection_comparison.yaml
```

### `submit` - Upload to Azure AI Foundry

Submits evaluation results to Azure AI Foundry for cloud-based evaluation.

```bash
python -m tests.evaluation.cli submit --data <jsonl_file_or_directory> [options]
```

| Option | Description |
|--------|-------------|
| `--data`, `-d` | Path to `foundry_eval.jsonl` or directory containing it (required) |
| `--config`, `-c` | Path to evaluator config (auto-detected if next to data file) |
| `--endpoint`, `-e` | Azure AI Foundry project endpoint |
| `--dataset-name` | Custom name for uploaded dataset |
| `--evaluation-name` | Custom name for evaluation run |
| `--model-deployment`, `-m` | Model for AI evaluators (default: `gpt-4o`) |

**Example:**

```bash
python -m tests.evaluation.cli submit \
  --data runs/smoke_basic_identity_1737849600/foundry_eval.jsonl \
  --endpoint "https://your-project.api.azureml.ms"
```

## Scenario YAML Format

### Single Scenario

Test a single agent configuration with multiple conversation turns.

```yaml
scenario_name: smoke_basic_identity
description: Verify basic agent functionality

# Reference a pre-defined scenario from scenariostore (optional)
scenario_template: banking

# Define session configuration inline
session_config:
  agents:
    - BankingConcierge
  start_agent: BankingConcierge
  handoffs: []
  generic_handoff:
    enabled: false

# Conversation turns to execute
turns:
  - turn_id: turn_1
    user_input: "Hello, I need help with my account."
    expectations:
      tools_called: []
      response_constraints:
        must_include_any: ["help", "assist"]

  - turn_id: turn_2
    user_input: "My name is John Smith and my last four SSN is 1234."
    expectations:
      tools_called:
        - verify_client_identity

# Pass/fail thresholds
thresholds:
  min_tool_precision: 0.5
  min_tool_recall: 0.5
  max_latency_p95_ms: 15000
```

### A/B Comparison (ComparisonRunner)

Compare multiple model configurations using the same conversation turns. The `ComparisonRunner` executes each variant sequentially and generates a comparison report.

```yaml
comparison_name: gpt4o_vs_o3_banking
description: Compare GPT-4o vs GPT-5.1 for banking scenarios

# Reference scenario template for agent discovery
scenario_template: banking

# Define variants - each runs the same turns with different models
variants:
  - variant_id: gpt4o_baseline
    agent_overrides:
      - agent: BankingConcierge
        model_override:
          deployment_id: gpt-4o
          temperature: 0.6
          max_tokens: 200
      - agent: CardRecommendation
        model_override:
          deployment_id: gpt-4o
          temperature: 0.6

  - variant_id: gpt51_challenger
    agent_overrides:
      - agent: BankingConcierge
        model_override:
          deployment_id: gpt-5.1
          max_completion_tokens: 2000
          reasoning_effort: low
      - agent: CardRecommendation
        model_override:
          deployment_id: gpt-5.1
          reasoning_effort: medium

# Shared turns executed for each variant
turns:
  - turn_id: turn_1
    user_input: "I need to check a charge. My name is Alice Brown, SSN 1234."
    expectations:
      tools_called:
        - verify_client_identity

  - turn_id: turn_2
    user_input: "Can you suggest a better rewards card?"
    expectations:
      tools_called:
        - handoff_to_agent

# Metrics to compare across variants
comparison_metrics:
  - latency_p95_ms
  - tool_precision
  - tool_recall
  - grounded_span_ratio
  - cost_per_turn

# Thresholds apply to all variants
thresholds:
  min_tool_precision: 0.05
  min_tool_recall: 0.10
  max_latency_p95_ms: 20000
```

### Model Profiles (DRY Configuration)

Use `model_profiles` to define reusable configurations:

```yaml
model_profiles:
  gpt4o_fast:
    deployment_id: gpt-4o
    temperature: 0.6
    max_tokens: 200
  o3_reasoning:
    deployment_id: o3-mini
    reasoning_effort: low
    max_completion_tokens: 2000

variants:
  - variant_id: baseline
    model_profile: gpt4o_fast  # Applied to ALL agents

  - variant_id: challenger
    model_profile: o3_reasoning
    # Per-agent overrides merge on top of profile
    agent_overrides:
      - agent: InvestmentAdvisor
        model_override:
          reasoning_effort: medium  # Override just this field
```

## How ComparisonRunner Works

The `ComparisonRunner` orchestrates A/B tests:

1. **Load comparison YAML** - Parses variants, turns, and thresholds
2. **Resolve model profiles** - Expands `model_profile` references to `agent_overrides`
3. **For each variant:**
   - Creates a temporary scenario file
   - Instantiates a `ScenarioRunner` with variant-specific model overrides
   - Runs all turns and records events
   - Generates per-variant summary
4. **Compare results** - Aggregates metrics and determines winners per metric
5. **Output comparison report** - Saves `comparison.json` with detailed breakdown

**Output structure:**

```
runs/<comparison_name>/
├── comparison.json           # Summary with winners per metric
├── gpt4o_baseline/
│   ├── <run_id>_events.jsonl
│   └── <run_id>/
│       ├── summary.json
│       └── session.json
└── gpt51_challenger/
    ├── <run_id>_events.jsonl
    └── <run_id>/
        ├── summary.json
        └── session.json
```

**Console output:**

```
======================================================================
📊 COMPARISON: gpt4o_vs_o3_banking
======================================================================

▶ gpt4o_baseline:
  Primary Model: gpt-4o

  Per-turn metrics:
    turn_1: BankingConcierge | 1234ms | expected=[verify_client_identity] actual=[verify_client_identity] ✓
    turn_2: BankingConcierge | 890ms | expected=[handoff_to_agent] actual=[handoff_to_agent] ✓

  Aggregated:
    Turns: 2
    Precision: 100.00%
    Recall: 100.00%
    Latency P50/P95: 1062ms / 1234ms
    Cost/turn: $0.0023

▶ gpt51_challenger:
  ...

🏆 Winners:
  winner_latency_p95_ms: gpt4o_baseline
  winner_tool_precision: gpt4o_baseline
  winner_cost_per_turn: gpt4o_baseline

📁 Results: runs/gpt4o_vs_o3_banking/comparison.json
======================================================================
```

## Expectations

Define expected behavior for each turn:

| Field | Description |
|-------|-------------|
| `tools_called` | List of tools that MUST be called |
| `tools_optional` | Tools that MAY be called (no penalty if missing) |
| `response_constraints.must_include_any` | Response must contain at least one |
| `response_constraints.must_not_include` | Response must NOT contain any |
| `response_constraints.latency_threshold_ms` | Max allowed latency |

**Example:**

```yaml
turns:
  - turn_id: turn_1
    user_input: "Check my balance"
    expectations:
      tools_called:
        - verify_client_identity
        - get_account_balance
      tools_optional:
        - get_user_profile
      response_constraints:
        must_include_any: ["balance", "account"]
        must_not_include: ["error", "sorry"]
        latency_threshold_ms: 5000
```

## Thresholds

Set pass/fail criteria for scenarios:

```yaml
thresholds:
  min_tool_precision: 0.8   # Called tools must be expected
  min_tool_recall: 0.8      # Expected tools must be called
  min_grounded_ratio: 0.5   # Response grounded in tool results
  max_latency_p95_ms: 10000 # 95th percentile latency limit
```

## Output Files

After running a scenario:

```
runs/<scenario_name>/
├── <run_id>_events.jsonl    # Raw turn events (JSONL format)
└── <run_id>/
    ├── summary.json         # Aggregated metrics
    ├── session.json         # Session manifest
    └── foundry_eval.jsonl   # Foundry-format data (if configured)
```

## Azure AI Foundry Integration

Enable cloud-based evaluation with AI evaluators:

```yaml
foundry_export:
  enabled: true
  output_filename: foundry_eval.jsonl
  context_source: evidence  # Use tool results as context
  evaluators:
    - id: builtin.relevance
      init_params:
        deployment_name: gpt-4o
      data_mapping:
        query: "${data.query}"
        response: "${data.response}"
        context: "${data.context}"
    - id: builtin.coherence
      init_params:
        deployment_name: gpt-4o
```

Then submit:

```bash
python -m tests.evaluation.cli submit \
  --data runs/my_scenario/ \
  --endpoint "https://your-project.api.azureml.ms"
```

## Running with pytest (End-to-End)

The pytest-based runner provides end-to-end evaluation with built-in Foundry submission support.

### pytest CLI Options

| Option | Description |
|--------|-------------|
| `--submit-to-foundry` | Submit results to Azure AI Foundry after running |
| `--foundry-endpoint` | Azure AI Foundry project endpoint (overrides env var) |
| `--eval-output-dir` | Output directory for results (default: `runs/`) |
| `--eval-model` | Model deployment for AI-based Foundry evaluators (default: `gpt-4o`) |

### Basic Usage

```bash
# Run all A/B comparison tests
pytest tests/evaluation/test_scenarios.py -v -m evaluation

# Run all session-based scenario tests
pytest tests/evaluation/test_scenarios.py::test_session_scenario_e2e -v

# Run specific scenario by name
pytest tests/evaluation/test_scenarios.py -k "fraud_detection" -v

# Skip slow tests (use existing data only)
pytest tests/evaluation/test_scenarios.py -m "not slow"
```

### Running with Foundry Submission

```bash
# Run A/B tests and submit results to Foundry
pytest tests/evaluation/test_scenarios.py::test_ab_comparison_e2e \
  --submit-to-foundry \
  --foundry-endpoint "https://your-project.api.azureml.ms" \
  -v

# Or set endpoint via environment variable
export AZURE_AI_FOUNDRY_PROJECT_ENDPOINT="https://your-project.api.azureml.ms"
pytest tests/evaluation/test_scenarios.py --submit-to-foundry -v

# Run session scenarios with Foundry submission
pytest tests/evaluation/test_scenarios.py::test_session_scenario_e2e \
  --submit-to-foundry \
  --foundry-endpoint "https://your-project.api.azureml.ms" \
  --eval-model gpt-4o \
  -v
```

### Test Functions

| Test | Description | Markers |
|------|-------------|---------|
| `test_ab_comparison_e2e` | Full A/B comparison with validation and thresholds | `evaluation`, `slow` |
| `test_session_scenario_e2e` | Session-based multi-agent scenarios | `evaluation`, `slow` |
| `test_expectations_from_existing_data` | Fast validation on existing A/B data | `evaluation` |
| `test_session_expectations_from_existing_data` | Fast validation on existing session data | `evaluation` |
| `TestEvaluationMetrics` | Threshold checks on existing A/B comparison data | `evaluation` |
| `TestSessionMetrics` | Threshold checks on existing session data | `evaluation` |

**Currently discovered scenarios:**

- A/B Tests: `fraud_detection_comparison`
- Session-based: `all_agents_discovery`, `banking_multi_agent`

### E2E Test Workflow

Each E2E test (`test_ab_comparison_e2e`, `test_session_scenario_e2e`) follows this workflow:

1. **Run scenario/comparison** - Executes all turns against live agents
2. **Validate expectations** - Checks tools called, handoffs, response constraints
3. **Submit to Foundry** (if `--submit-to-foundry`) - Uploads data BEFORE assertions
4. **Assert expectations pass** - Fails test if any turn expectations fail
5. **Assert metric thresholds** - Validates precision, recall, latency, groundedness

### Environment Variable Overrides

Override default thresholds via environment variables:

```bash
# Set custom thresholds
export EVAL_MIN_PRECISION=0.8
export EVAL_MIN_RECALL=0.7
export EVAL_MAX_LATENCY_MS=5000
export EVAL_MIN_GROUNDED=0.5

pytest tests/evaluation/test_scenarios.py -v
```

### Fast Iteration Mode

Use expectation-only tests to iterate quickly without re-running scenarios:

```bash
# First, run full E2E to generate data
pytest tests/evaluation/test_scenarios.py::test_ab_comparison_e2e -k "fraud_detection" -v

# Then iterate on expectations using existing data (fast)
pytest tests/evaluation/test_scenarios.py::test_expectations_from_existing_data -k "fraud_detection" -v
```

### Sample Output with Foundry Submission

```
$ pytest tests/evaluation/test_scenarios.py::test_ab_comparison_e2e \
    --submit-to-foundry \
    --foundry-endpoint "https://my-project.api.azureml.ms" \
    -v

============================= test session starts ==============================
collected 1 item

test_scenarios.py::test_ab_comparison_e2e[fraud_detection_comparison]
🚀 Running E2E A/B comparison: fraud_detection_comparison.yaml

▶ gpt4o_baseline:
  Per-turn metrics:
    turn_1: FraudDetection | 1234ms | expected=[verify_client_identity] actual=[verify_client_identity] ✓
    turn_2: FraudDetection | 890ms | expected=[check_fraud_alert] actual=[check_fraud_alert] ✓

📤 Submitting gpt4o_baseline to Foundry: runs/fraud_detection_comparison/.../foundry_eval.jsonl
✅ Foundry submission complete for gpt4o_baseline
🔗 View in portal: https://ai.azure.com/project/.../evaluation/...

▶ gpt51_challenger:
  ...

✅ All variants pass thresholds
PASSED
```

## Troubleshooting

**No agents discovered:**
- Ensure `scenario_template` references a valid scenario in `scenariostore/`
- Or define `session_config.agents` list explicitly

**Model override not applied:**
- Check `agent_overrides` uses correct agent names (case-sensitive)
- Verify `deployment_id` exists in your Azure OpenAI resource

**Foundry submission fails:**

The test reads the Foundry endpoint from these sources (in order):
1. `--foundry-endpoint` CLI option
2. `AZURE_AI_FOUNDRY_PROJECT_ENDPOINT` environment variable
3. App Configuration (via `azure/ai-foundry/project-endpoint` key)

To configure:

```bash
# Option A: Add to .env.local (recommended - uses existing App Config pattern)
echo 'AZURE_AI_FOUNDRY_PROJECT_ENDPOINT=https://your-project.api.azureml.ms' >> .env.local

# Option B: Set environment variable directly
export AZURE_AI_FOUNDRY_PROJECT_ENDPOINT="https://your-project.api.azureml.ms"

# Option C: Pass via CLI
pytest tests/evaluation/test_scenarios.py --submit-to-foundry --foundry-endpoint "https://your-project.api.azureml.ms"
```

Find your endpoint in Azure Portal > Azure AI Foundry > Your Project > Settings > Properties.

**pytest --submit-to-foundry fails with missing endpoint:**
- Test now fails loudly if `--submit-to-foundry` is used without a valid endpoint
- Add endpoint to `.env.local` or pass `--foundry-endpoint` argument
- Endpoint format: `https://<project>.api.azureml.ms` or `https://<region>.api.azureml.ms`

**No studio_url in Foundry result:**
- Storage account must be linked to the Azure AI Foundry project
- Check project permissions include "Azure AI Developer" role
