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
hooks: HooksConfig             # Custom analysis hooks (Phase 2)
```

### Turn Object

Two syntax options are supported - **compact** (recommended) and **full** (verbose):

**Compact Syntax (Recommended):**

```yaml
turns:
  # Array shorthand - just tool names
  - turn_id: turn_1
    user_input: "Check my balance"
    expect: [verify_identity, get_balance]

  # Object shorthand - multiple expectation types
  - turn_id: turn_2
    user_input: "Transfer to cards team"
    expect:
      tools: [verify_identity]
      handoff: CardAgent
      contains: ["transferred", "card"]
      excludes: ["error"]
      max_latency: 5000
      no_tools: false
      no_handoff: false
      forbidden: [delete_account]
      min_grounded: 0.7
```

**Compact → Full Mapping:**
| Compact | Full Form |
|---------|-----------|
| `expect: [tools]` | `expectations.tools_called: [tools]` |
| `expect.tools` | `expectations.tools_called` |
| `expect.handoff` | `expectations.handoff.to_agent` |
| `expect.contains` | `expectations.response_constraints.must_include` |
| `expect.excludes` | `expectations.response_constraints.must_not_include` |
| `expect.max_latency` | `expectations.max_latency_ms` |
| `expect.no_tools` | empty `tools_called` |
| `expect.no_handoff` | `expectations.no_handoff: true` |
| `expect.forbidden` | `expectations.tools_forbidden` |
| `expect.min_grounded` | `expectations.min_grounded_ratio` |

**Full Syntax (Verbose):**

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

### Model Profiles (DRY Configuration)

Model profiles enable reusable model configurations, reducing duplication in multi-variant comparisons:

```yaml
model_profiles:
  gpt4o_fast:                  # Profile name
    deployment_id: gpt-4o
    endpoint_preference: chat  # "chat" or "responses"
    temperature: 0.6
    max_tokens: 200

  o3_reasoning:
    deployment_id: o3-mini
    endpoint_preference: responses
    reasoning_effort: medium    # "low", "medium", "high"
    max_completion_tokens: 2000
```

**Available profile fields:**
- `deployment_id` (required): Model deployment name
- `endpoint_preference`: "chat" or "responses" 
- `temperature`, `top_p`, `min_p`, `typical_p`: Sampling parameters
- `max_tokens`, `max_completion_tokens`: Token limits
- `reasoning_effort`, `include_reasoning`: o-series model settings

### Variants (A/B Testing)

Variants can reference model profiles for DRY configuration:

```yaml
# With model profiles (recommended)
variants:
  - variant_id: baseline
    model_profile: gpt4o_fast   # All agents use this profile
  
  - variant_id: reasoning
    model_profile: o3_reasoning
    agent_overrides:            # Per-agent exceptions (optional)
      - agent: CardRecommendation
        model_override:
          reasoning_effort: low

# Legacy format (still supported)
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

### Hooks Configuration

Hooks enable custom analysis without modifying core framework code:

```yaml
hooks:
  # Called after each turn completes
  on_turn_complete:
    - builtin.log_metrics              # Built-in hook
    - module: my_analyzers.sentiment   # Custom hook
      function: analyze_response

  # Called after each tool execution
  on_tool_complete:
    - builtin.validate_tool_result

  # Called before scoring
  pre_score:
    - builtin.aggregate_metrics
    - module: my_analyzers.custom_metrics
      function: compute_domain_metrics
```

**Built-in Hooks:**

| Hook ID | Event | Purpose |
|---------|-------|---------|
| `builtin.log_metrics` | on_turn_complete | Log turn metrics to console |
| `builtin.validate_expectations` | on_turn_complete | Run expectation checks |
| `builtin.capture_reasoning` | on_turn_complete | Extract reasoning tokens (o-series) |
| `builtin.validate_tool_result` | on_tool_complete | Validate tool execution |
| `builtin.aggregate_metrics` | pre_score | Compute aggregate metrics |

**Custom Hook Implementation:**

```python
# my_analyzers/sentiment.py
from tests.evaluation.hooks import TurnHook, HookResult

class SentimentAnalyzer(TurnHook):
    async def on_turn_complete(self, turn, context) -> HookResult:
        sentiment = self._analyze(turn.response_text)
        return HookResult(
            success=True,
            metadata={"sentiment_score": sentiment}
        )
```

---

## Complete Examples

### Model Profile Comparison (Recommended Pattern)

```yaml
scenario_name: model_comparison_with_profiles
description: Compare GPT-4o vs o3-mini using model profiles

# Define reusable profiles
model_profiles:
  gpt4o_fast:
    deployment_id: gpt-4o
    endpoint_preference: chat
    temperature: 0.6
    max_tokens: 200

  o3_reasoning:
    deployment_id: o3-mini
    endpoint_preference: responses
    reasoning_effort: medium
    max_completion_tokens: 2000

# Variants reference profiles (DRY)
variants:
  - variant_id: baseline
    model_profile: gpt4o_fast

  - variant_id: reasoning
    model_profile: o3_reasoning
    agent_overrides:
      - agent: CardRecommendation
        model_override:
          reasoning_effort: low

# Compact turn syntax
turns:
  - turn_id: turn_1
    user_input: "Check my account balance"
    expect: [verify_identity, get_balance]

  - turn_id: turn_2
    user_input: "Connect me to cards team"
    expect:
      handoff: CardRecommendation
      contains: ["transfer", "card"]

  - turn_id: turn_3
    user_input: "What's my credit limit?"
    expect:
      tools: [get_card_details]
      max_latency: 3000
```

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

1. **Use model profiles** - Define once, reuse across variants (70% config reduction)
2. **Use compact expectations** - `expect: [tools]` is clearer than verbose form
3. **Start minimal** - Add expectations incrementally
4. **Use tags** - Group related scenarios for batch runs
5. **Version scenarios** - Track changes alongside agent changes
6. **Document intent** - Use description field liberally
7. **Test locally first** - Run without Foundry export initially
