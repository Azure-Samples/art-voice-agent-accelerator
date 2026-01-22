---
name: add-evaluation
description: Create a new evaluation scenario for agent testing
---

# Add Evaluation Skill

Create evaluation scenarios in `tests/eval_scenarios/`.

## Scenario Types

| Type | Location | Purpose |
|------|----------|---------|
| Agent | `agents/` | Test single agent tool calling |
| Workflow | `workflows/` | Test multi-agent handoffs |
| A/B Test | `ab_tests/` | Compare model variants |

## Agent Scenario Template

```yaml
# tests/eval_scenarios/agents/{agent_name}_basic.yaml
scenario_name: agent_name_tool_calling
agent: AgentName
scope: agent

metadata:
  environment: development
  version: "1.0.0"
  tags:
    - agent-evaluation

turns:
  - turn_id: turn_1
    user_input: "User message here"
    expectations:
      tools_called:
        - expected_tool_name
      tools_optional:
        - optional_tool
      response_constraints:
        max_tokens: 150
```

## Workflow Scenario Template

```yaml
# tests/eval_scenarios/workflows/{workflow_name}.yaml
scenario_name: workflow_name
scope: scenario

agents:
  - Concierge
  - SpecialistAgent

turns:
  - turn_id: turn_1
    user_input: "Initial message"
    expected_agent: Concierge
    expectations:
      handoff:
        to_agent: SpecialistAgent

  - turn_id: turn_2
    user_input: "Follow-up message"
    expected_agent: SpecialistAgent
    expectations:
      tools_called:
        - specialist_tool
```

## A/B Comparison Template

```yaml
# tests/eval_scenarios/ab_tests/{comparison_name}.yaml
comparison_name: model_a_vs_model_b
scope: agent

variants:
  - variant_id: baseline
    agent: AgentName
    model_override:
      deployment_id: gpt-4o
      temperature: 0.6

  - variant_id: experimental
    agent: AgentName
    model_override:
      deployment_id: o1-preview
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
  - cost_per_turn_usd
```

## Steps

1. Choose scenario type (agent, workflow, or ab_test)
2. Create YAML file in appropriate directory
3. Define turns with user inputs
4. Add expectations (tools, handoffs, constraints)
5. Run evaluation:

```bash
# Single scenario
python -m tests.evaluation.cli scenario \
    --input tests/eval_scenarios/agents/my_scenario.yaml

# A/B comparison
python -m tests.evaluation.cli compare \
    --input tests/eval_scenarios/ab_tests/my_comparison.yaml
```

## Expectations Reference

```yaml
expectations:
  tools_called: [tool1, tool2]      # Required tools
  tools_optional: [tool3]           # Won't fail if missing
  handoff:
    to_agent: TargetAgent           # Expected handoff
  response_constraints:
    max_tokens: 150
    must_include: ["keyword"]
```

## Azure AI Foundry Export

Export evaluation results to Azure AI Foundry format for cloud-based evaluation:

```yaml
# Add to any scenario or comparison YAML
foundry_export:
  enabled: true
  output_filename: foundry_eval.jsonl
  include_metadata: true
  context_source: evidence  # 'evidence' | 'conversation' | 'none'
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
