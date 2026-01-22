# Evaluation Scenario YAML Reference

> **Complete reference for evaluation scenario YAML files.**

## File Location

Place scenario files in:
```
tests/evaluation/scenarios/
├── ab_tests/
│   ├── fraud_detection_comparison.yaml
│   └── model_performance.yaml
├── single/
│   ├── greeting_test.yaml
│   └── simple_query.yaml
└── regression/
    └── golden_scenarios.yaml
```

## Schema

### Root Level

```yaml
# Required
scenario_name: string          # Unique identifier
agent_id: string               # Agent from registry

# Optional
description: string            # Human-readable description
tags: [string]                 # For filtering/grouping
timeout_seconds: int           # Max scenario duration (default: 300)

# Configuration sections
agent_overrides: object        # Override agent settings
variants: object               # A/B test variants
turns: [Turn]                  # Conversation turns
expectations: Expectations     # Global expectations
foundry_export: FoundryConfig  # Azure AI Foundry settings
```

### Turn Object

```yaml
turns:
  - turn_id: int               # Sequential turn number (1-based)
    user_input: string         # User utterance/message
    
    # Optional expectations for this turn
    expected:
      tool_calls: [ToolExpectation]
      response_contains: [string]
      response_not_contains: [string]
      max_response_tokens: int
      min_response_tokens: int
      handoff_agent: string | null
      latency_budget_ms: int
```

### ToolExpectation Object

```yaml
tool_calls:
  - name: string               # Tool function name
    required: bool             # Must be called (default: true)
    order: int                 # Expected call order (optional)
    args_contain:              # Partial argument matching
      key: value
    args_exact:                # Exact argument matching
      key: value
```

### Agent Overrides

```yaml
agent_overrides:
  # Model settings
  model: string                # e.g., "gpt-4o", "gpt-4o-mini"
  temperature: float           # 0.0 - 2.0
  max_tokens: int              # Max completion tokens
  
  # Prompt modifications
  system_prompt_additions: string
  system_prompt_override: string
  
  # Tool configuration
  tools_enabled: [string]      # Whitelist of tools
  tools_disabled: [string]     # Blacklist of tools
  
  # Other
  timeout_per_turn_ms: int
```

### Variants (A/B Testing)

```yaml
variants:
  baseline:                    # First variant name
    model: string
    temperature: float
    # ... any agent_overrides fields
  
  challenger:                  # Second variant name
    model: string
    temperature: float
```

### Global Expectations

```yaml
expectations:
  # Latency
  max_total_latency_ms: int
  max_turn_latency_ms: int
  max_ttft_ms: int
  
  # Tool metrics
  min_tool_precision: float    # 0.0 - 1.0
  min_tool_recall: float       # 0.0 - 1.0
  min_tool_efficiency: float   # 0.0 - 1.0
  
  # Groundedness
  min_grounded_ratio: float    # 0.0 - 1.0
  max_unsupported_claims: int
  
  # Verbosity
  max_avg_tokens: int
  max_budget_violations: int
  
  # Cost
  max_total_cost_usd: float
  max_cost_per_turn_usd: float
```

### Foundry Export Configuration

```yaml
foundry_export:
  enabled: bool                # Enable export (default: false)
  project_name: string         # Azure AI Foundry project
  experiment_name: string      # Experiment identifier
  
  evaluators:
    - id: string               # Evaluator ID (see below)
      column_mapping:          # Map scenario data to evaluator inputs
        query: string          # Field name for query
        response: string       # Field name for response
        context: string        # Field name for context (optional)
        ground_truth: string   # Field name for ground truth (optional)
```

#### Supported Foundry Evaluator IDs

| ID | Description | Required Columns |
|----|-------------|------------------|
| `relevance` | Response relevance to query | query, response |
| `coherence` | Response logical coherence | response |
| `fluency` | Language fluency | response |
| `groundedness` | Factual grounding | query, response, context |
| `similarity` | Semantic similarity | response, ground_truth |
| `f1_score` | Token F1 score | response, ground_truth |

---

## Complete Examples

### Basic Single-Turn Test

```yaml
scenario_name: greeting_test
description: Verify agent greeting behavior
agent_id: customer_service_agent

turns:
  - turn_id: 1
    user_input: "Hello"
    expected:
      response_contains:
        - "hello"
        - "help"
      response_not_contains:
        - "error"
        - "sorry"
      max_response_tokens: 50
```

### Multi-Turn with Tool Expectations

```yaml
scenario_name: fraud_detection_flow
description: Complete fraud detection conversation
agent_id: fraud_detection_agent

turns:
  - turn_id: 1
    user_input: "I think someone is using my card"
    expected:
      tool_calls:
        - name: get_recent_transactions
          required: true
      response_contains:
        - "transactions"

  - turn_id: 2
    user_input: "I see a $500 charge I didn't make"
    expected:
      tool_calls:
        - name: flag_transaction
          required: true
          args_contain:
            amount: 500
        - name: create_dispute
          required: true
      response_contains:
        - "flagged"
        - "dispute"

  - turn_id: 3
    user_input: "What happens next?"
    expected:
      tool_calls: []  # No tools expected
      response_contains:
        - "investigate"
        - "48 hours"

expectations:
  min_tool_precision: 0.9
  min_tool_recall: 0.95
  max_total_latency_ms: 10000
```

### A/B Model Comparison

```yaml
scenario_name: model_performance_comparison
description: Compare GPT-4o vs GPT-4o-mini for customer service
agent_id: customer_service_agent

variants:
  gpt4o_baseline:
    model: gpt-4o
    temperature: 0.7
    max_tokens: 300
  
  gpt4o_mini_challenger:
    model: gpt-4o-mini
    temperature: 0.7
    max_tokens: 300

turns:
  - turn_id: 1
    user_input: "Explain my last bill in detail"
    expected:
      tool_calls:
        - name: get_billing_details
          required: true
      response_contains:
        - "charges"
      max_response_tokens: 250

  - turn_id: 2
    user_input: "Why did the price go up?"
    expected:
      response_contains:
        - "increase"
        - "plan"

expectations:
  min_tool_precision: 0.85
  min_grounded_ratio: 0.7
  max_avg_tokens: 200
```

### With Azure AI Foundry Export

```yaml
scenario_name: foundry_evaluation_test
description: Full evaluation with Foundry export
agent_id: knowledge_base_agent

foundry_export:
  enabled: true
  project_name: voice-agent-evals
  experiment_name: kb-agent-v2.1
  
  evaluators:
    - id: relevance
      column_mapping:
        query: user_input
        response: assistant_response
    
    - id: groundedness
      column_mapping:
        query: user_input
        response: assistant_response
        context: retrieved_context
    
    - id: coherence
      column_mapping:
        response: assistant_response
    
    - id: fluency
      column_mapping:
        response: assistant_response

turns:
  - turn_id: 1
    user_input: "What is the return policy?"
    expected:
      tool_calls:
        - name: search_knowledge_base
          required: true
      response_contains:
        - "return"
        - "days"

  - turn_id: 2
    user_input: "What if it's damaged?"
    expected:
      response_contains:
        - "damaged"
        - "replacement"

expectations:
  min_grounded_ratio: 0.8
  max_unsupported_claims: 1
```

### Agent Override Example

```yaml
scenario_name: conservative_mode_test
description: Test agent with conservative settings
agent_id: customer_service_agent

agent_overrides:
  model: gpt-4o
  temperature: 0.2              # Lower for consistency
  max_tokens: 150               # Enforce brevity
  
  system_prompt_additions: |
    IMPORTANT: Be extra concise in this session.
    Limit responses to essential information only.
  
  tools_disabled:
    - send_marketing_email      # Disable for this test
    - schedule_callback

turns:
  - turn_id: 1
    user_input: "What's my balance?"
    expected:
      tool_calls:
        - name: get_account_balance
          required: true
      max_response_tokens: 50

expectations:
  max_avg_tokens: 75
  max_budget_violations: 0
```

### Handoff Testing

```yaml
scenario_name: escalation_handoff_test
description: Test escalation to human agent
agent_id: tier1_support_agent

turns:
  - turn_id: 1
    user_input: "I want to cancel my account"
    expected:
      tool_calls:
        - name: get_account_status
          required: true
      response_contains:
        - "understand"
        - "help"

  - turn_id: 2
    user_input: "I've already tried that, just cancel it"
    expected:
      handoff_agent: retention_specialist
      response_contains:
        - "specialist"
        - "transfer"

expectations:
  min_tool_precision: 1.0
```

---

## Validation

Scenarios are validated at load time. Common errors:

| Error | Cause | Fix |
|-------|-------|-----|
| `Unknown agent_id` | Agent not in registry | Check agent registry |
| `Invalid turn_id sequence` | Non-sequential IDs | Use 1, 2, 3... |
| `Unknown tool in expectations` | Tool not registered | Verify tool names |
| `Invalid variant config` | Missing required fields | Check variant structure |
| `Foundry evaluator unknown` | Invalid evaluator ID | Use supported IDs |

## Tips

1. **Start minimal** - Add expectations incrementally
2. **Use tags** - Group related scenarios for batch runs
3. **Version scenarios** - Track changes alongside agent changes
4. **Document intent** - Use description field liberally
5. **Test locally first** - Run without Foundry export initially
