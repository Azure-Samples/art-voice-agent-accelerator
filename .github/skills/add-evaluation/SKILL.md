---
name: add-evaluation
description: Create or update evaluation scenarios for the tests/evaluation framework, including session-based scenarios and A/B comparisons
---

# Add Evaluation Skill

Create evaluation scenarios in `tests/evaluation/scenarios/`.

## Scenario Types

| Type | Location | Purpose |
|------|----------|---------|
| Session-based | `session_based/` | Multi-agent sessions and handoffs |
| A/B Comparison | `ab_tests/` | Compare model variants |

## Session-Based Scenario Template

```yaml
# tests/evaluation/scenarios/session_based/{scenario_name}.yaml
scenario_name: banking_multi_agent
description: "Session-based multi-agent evaluation"

# Optional: Create demo user for realistic tool responses
demo_user:
  full_name: "Sarah Johnson"
  email: "sarah.johnson@example.com"
  phone_number: "+18885551234"
  scenario: banking  # or "insurance"
  seed: 42           # Fixed seed for reproducible data
  persist: false     # Don't persist to database

session_config:
  agents: [BankingConcierge, CardRecommendation]
  start_agent: BankingConcierge
  handoff_type: announced

turns:
  - turn_id: turn_1
    user_input: "I'd like to check my account"
    expectations:
      tools_called:
        - verify_client_identity
```

## Demo User Configuration

The `demo_user` section creates a realistic user profile before running the scenario.
This ensures tools like `get_user_profile`, `verify_client_identity`, and `lookup_decline_code`
have actual data to return.

```yaml
demo_user:
  full_name: "Sarah Johnson"     # Required: User's name
  email: "sarah@example.com"     # Required: User's email
  phone_number: "+18885551234"   # Optional: E.164 format
  scenario: banking              # "banking" or "insurance"
  seed: 42                       # Optional: For reproducible data
  persist: false                 # Whether to save to database
  
  # Insurance-only options:
  insurance_role: policyholder   # "policyholder" or "cc_rep"
  insurance_company_name: "..."  # If cc_rep
  test_scenario: golden_path     # Predefined test scenarios
```

**Banking demo user includes:**
- Client ID and SSN last 4 for verification
- Multiple cards with different names/statuses
- Recent transactions with decline codes
- Customer intelligence profile

**Insurance demo user includes:**
- Policies (auto, home, umbrella)
- Claims with various statuses
- Subrogation demands

## A/B Comparison Template

```yaml
# tests/evaluation/scenarios/ab_tests/{comparison_name}.yaml
comparison_name: fraud_model_comparison
scenario_template: banking
description: "Compare model variants for banking scenario"

variants:
  - variant_id: baseline
    agent_overrides:
      - agent: BankingConcierge
        model_override:
          deployment_id: gpt-4o
          temperature: 0.6

  - variant_id: experimental
    agent_overrides:
      - agent: BankingConcierge
        model_override:
          deployment_id: gpt-5.1
          reasoning_effort: medium

turns:
  - turn_id: turn_1
    user_input: "Test message"
    expectations:
      tools_called:
        - expected_tool

comparison_metrics:
  - tool_precision
  - latency_p95_ms
  - cost_per_turn
```

## Steps

1. Choose scenario type (session_based or ab_tests)
2. Create YAML file in appropriate directory
3. Define turns with user inputs
4. Add expectations (tools, handoffs, constraints)
5. Run evaluation:

```bash
# Via Makefile (recommended)
make eval-run SCENARIO=tests/evaluation/scenarios/session_based/my_scenario.yaml

# Or interactive CLI
make eval
```

```bash
# Submit to Azure AI Foundry (optional)
python -m tests.evaluation.cli submit \
    --data runs/my_run/foundry_eval.jsonl \
    --endpoint "$AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"
```

## Expectations Reference

```yaml
expectations:
  tools_called: [tool1, tool2]      # Required tools
  tools_optional: [tool3]           # Won't fail if missing
  tools_forbidden: [tool4]          # Must NOT be called
  handoff:
    to_agent: TargetAgent           # Expected handoff
  no_handoff: false                 # Assert no handoff occurs
  response_constraints:
    max_tokens: 150
    must_include: ["keyword"]
    must_not_include: ["forbidden"]
    must_ask_for: ["missing info"]
  max_latency_ms: 5000
```

## Azure AI Foundry Export

Export evaluation results to Azure AI Foundry format for cloud-based evaluation:

```yaml
# Add to any scenario or comparison YAML
foundry_export:
  enabled: true
  output_filename: foundry_eval.jsonl
  include_metadata: true
  context_source: evidence  # 'evidence' | 'raw_tool_results' | 'none'
  evaluators:
    # AI-based quality evaluators (require model deployment)
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
    - id: builtin.groundedness
      init_params:
        deployment_name: gpt-4o

    # Safety evaluators (no model required)
    - id: builtin.violence
    - id: builtin.self_harm
    - id: builtin.hate_unfairness

    # NLP metrics (no model required)
    - id: builtin.f1_score
    - id: builtin.bleu_score
```

### Available Evaluator IDs

| Category | Evaluator ID | Requires Model |
|----------|-------------|----------------|
| Quality | `builtin.relevance` | Yes |
| Quality | `builtin.coherence` | Yes |
| Quality | `builtin.fluency` | Yes |
| Quality | `builtin.groundedness` | Yes |
| Quality | `builtin.similarity` | Yes |
| Safety | `builtin.violence` | No |
| Safety | `builtin.sexual` | No |
| Safety | `builtin.self_harm` | No |
| Safety | `builtin.hate_unfairness` | No |
| NLP | `builtin.f1_score` | No |
| NLP | `builtin.bleu_score` | No |
| NLP | `builtin.rouge_score` | No |

### Generated Foundry Files

When `foundry_export.enabled: true`, these files are added to the run output:

- `foundry_eval.jsonl` - Dataset for Foundry upload
- `foundry_evaluators.json` - Evaluator configuration (if evaluators specified)

### Uploading to Foundry

```python
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

client = AIProjectClient.from_connection_string(
    credential=DefaultAzureCredential(),
    conn_str="<connection_string>"
)

# Upload dataset
dataset = client.datasets.upload_file(
    file_path="runs/my_scenario/foundry_eval.jsonl",
    name="my_evaluation_data"
)

# Run evaluation with configured evaluators
import json
with open("runs/my_scenario/foundry_evaluators.json") as f:
    evaluator_config = json.load(f)

# Use with Evaluation API...
```
