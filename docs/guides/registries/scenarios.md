# Scenarios Guide

Scenarios define which agents are active and how they route to each other for a specific use case. They enable the same agents to behave differently depending on the industry or context.

## Overview

Scenarios are YAML configuration files that:

1. **Select agents** - Which agents are available
2. **Define handoffs** - How agents route to each other
3. **Override settings** - Customize greetings, variables, etc.

```
scenariostore/
├── banking/
│   └── orchestration.yaml
├── insurance/
│   └── orchestration.yaml
└── default/
    └── orchestration.yaml
```

```mermaid
flowchart TB
    subgraph Scenario
        S[scenario.yaml]
    end
    
    subgraph Agents
        A1[Concierge]
        A2[FraudAgent]
        A3[InvestmentAdvisor]
    end
    
    subgraph Tools
        T1[verify_identity]
        T2[handoff_fraud]
        T3[handoff_invest]
    end
    
    S -->|selects| A1
    S -->|selects| A2
    S -->|selects| A3
    S -->|defines routes| H[Handoff Graph]
    A1 --> T1
    A1 --> T2
    A1 --> T3
```

## Why Scenarios?

Without scenarios, you'd need separate agent definitions for each use case. Scenarios let you:

- **Reuse agents** across different deployments
- **Customize routing** per industry
- **Override settings** without editing agent files
- **Control handoff behavior** (announced vs discrete)

## Scenario Configuration

### Basic Structure

```yaml
# scenariostore/banking/orchestration.yaml

name: banking
description: Private banking customer service
icon: "🏦"

# Starting agent
start_agent: BankingConcierge

# Agents to include
agents:
  - BankingConcierge
  - CardRecommendation
  - InvestmentAdvisor

# Default handoff behavior
handoff_type: announced  # or "discrete"

# Handoff routes (agent graph)
handoffs:
  - from: BankingConcierge
    to: CardRecommendation
    tool: handoff_card_recommendation
    type: discrete
    
  - from: BankingConcierge
    to: InvestmentAdvisor
    tool: handoff_investment_advisor
    type: discrete

  - from: CardRecommendation
    to: BankingConcierge
    tool: handoff_concierge
    type: discrete

# Global template variables
template_vars:
  institution_name: "Contoso Bank"
  region: "US"

# Agent defaults
agent_defaults:
  company_name: "{{ institution_name }}"
  compliance_required: true
```

## Configuration Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | *required* | Scenario identifier |
| `description` | string | `""` | Human-readable description |
| `icon` | string | `"🎭"` | Emoji for UI |
| `start_agent` | string | First in list | Default starting agent |
| `agents` | list | All agents | Agents to include |
| `handoff_type` | string | `"announced"` | Default: `"announced"` or `"discrete"` |
| `handoffs` | list | `[]` | Handoff route definitions |
| `template_vars` | dict | `{}` | Global variables for prompts |
| `agent_defaults` | object | `{}` | Overrides applied to all agents |
| `generic_handoff` | object | disabled | Dynamic handoff configuration |

## Handoff Configuration

### Handoff Types

| Type | Behavior |
|------|----------|
| `announced` | Target agent greets the customer on switch |
| `discrete` | Silent handoff, conversation continues naturally |

### Defining Handoffs

Each handoff is a directed edge in the agent graph:

```yaml
handoffs:
  - from: Concierge          # Source agent
    to: FraudAgent           # Target agent
    tool: handoff_fraud      # Tool name that triggers this route
    type: discrete           # Silent handoff
    share_context: true      # Pass conversation context
    handoff_condition: |     # When to trigger (injected into prompt)
      Transfer when customer reports:
      - Unauthorized transactions
      - Suspicious activity
      - Potential fraud
```

### Handoff Graph Example

```yaml
# Banking scenario handoff graph:
#
#              ┌─────────────────────────────────────┐
#              │                                     │
#              ▼                                     │
#        ┌───────────────┐                           │
#        │BankingConcierge│ (Entry Point)            │
#        └───────┬───────┘                           │
#                │                                   │
#      ┌─────────┴─────────┐                         │
#      │                   │                         │
#      ▼                   ▼                         │
# ┌──────────────┐   ┌────────────────┐              │
# │    Card      │   │   Investment   │              │
# │Recommendation│◄─►│    Advisor     │              │
# └──────┬───────┘   └───────┬────────┘              │
#        │                   │                       │
#        └─────────┬─────────┘                       │
#                  │                                 │
#                  └─────────────────────────────────┘
#                    (All return to BankingConcierge)

handoffs:
  # Concierge → Specialists
  - from: BankingConcierge
    to: CardRecommendation
    tool: handoff_card_recommendation
    type: discrete
    handoff_condition: |
      Transfer when customer asks about credit cards,
      card benefits, or wants card recommendations.

  - from: BankingConcierge
    to: InvestmentAdvisor
    tool: handoff_investment_advisor
    type: discrete
    handoff_condition: |
      Transfer when customer asks about investments,
      retirement planning, or wealth management.

  # Cross-specialist routing
  - from: CardRecommendation
    to: InvestmentAdvisor
    tool: handoff_investment_advisor
    type: discrete
    handoff_condition: |
      Transfer when conversation shifts from cards
      to investment topics.

  - from: InvestmentAdvisor
    to: CardRecommendation
    tool: handoff_card_recommendation
    type: discrete

  # Return routes
  - from: CardRecommendation
    to: BankingConcierge
    tool: handoff_concierge
    type: discrete

  - from: InvestmentAdvisor
    to: BankingConcierge
    tool: handoff_concierge
    type: discrete
```

## Generic Handoffs

Enable dynamic agent transfers without explicit tool definitions:

```yaml
generic_handoff:
  enabled: true
  allowed_targets: []          # Empty = all scenario agents
  default_type: discrete       # Default handoff type
  share_context: true          # Pass conversation context
  require_client_id: false     # Whether client_id required

# With generic handoffs, agents can use:
# handoff_to_agent(target_agent="InvestmentAdvisor", reason="...")
```

## Agent Defaults

Apply settings to all agents in the scenario:

```yaml
agent_defaults:
  # Greeting override
  greeting: "Welcome to {{ company_name }}!"
  
  # Template variables
  company_name: "Contoso Bank"
  industry: "banking"
  compliance_required: true
  
  # Voice override
  voice:
    name: en-US-AriaNeural
    rate: "-5%"
```

## Using Scenarios

### Load a Scenario

```python
from apps.artagent.backend.registries.scenariostore import (
    load_scenario,
    get_scenario_agents,
    get_scenario_start_agent,
    build_handoff_map_from_scenario,
)

# Load scenario configuration
scenario = load_scenario("banking")

# Get agents with scenario overrides applied
agents = get_scenario_agents("banking")

# Get starting agent
start = get_scenario_start_agent("banking")
# Returns: "BankingConcierge"

# Build handoff routing map
handoff_map = build_handoff_map_from_scenario("banking")
# Returns: {"handoff_card_recommendation": "CardRecommendation", ...}
```

### Get Handoff Configuration

```python
from apps.artagent.backend.registries.scenariostore import get_handoff_config

# Get specific handoff settings
config = get_handoff_config(
    scenario_name="banking",
    from_agent="BankingConcierge",
    tool_name="handoff_card_recommendation",
)
# Returns: HandoffConfig(type="discrete", share_context=True, ...)
```

### Get Handoff Instructions

Auto-generate handoff instructions for agent prompts:

```python
from apps.artagent.backend.registries.scenariostore import get_handoff_instructions

instructions = get_handoff_instructions("banking", "BankingConcierge")
# Returns formatted prompt block describing when to handoff
```

## Creating a New Scenario

### Step 1: Create Directory

```bash
mkdir -p apps/artagent/backend/registries/scenariostore/healthcare
```

### Step 2: Create orchestration.yaml

```yaml
# scenariostore/healthcare/orchestration.yaml

name: healthcare
description: Healthcare customer service
icon: "🏥"

start_agent: HealthcareReceptionist

agents:
  - HealthcareReceptionist
  - AppointmentScheduler
  - InsuranceVerifier
  - PriorAuthAgent

handoff_type: announced

handoffs:
  - from: HealthcareReceptionist
    to: AppointmentScheduler
    tool: handoff_appointments
    type: discrete
    handoff_condition: |
      Transfer when patient wants to schedule,
      reschedule, or cancel appointments.

  - from: HealthcareReceptionist
    to: InsuranceVerifier
    tool: handoff_insurance
    type: discrete
    handoff_condition: |
      Transfer for insurance eligibility checks
      or coverage questions.

  - from: AppointmentScheduler
    to: HealthcareReceptionist
    tool: handoff_reception
    type: discrete

  - from: InsuranceVerifier
    to: HealthcareReceptionist
    tool: handoff_reception
    type: discrete

template_vars:
  institution_name: "Contoso Health"
  support_phone: "1-800-HEALTH"

agent_defaults:
  hipaa_compliant: true
  region: "US"
```

### Step 3: Ensure Agents Exist

Make sure referenced agents exist in `agentstore/`:

```
agentstore/
├── healthcare_receptionist/
│   ├── agent.yaml
│   └── prompt.jinja
├── appointment_scheduler/
│   ├── agent.yaml
│   └── prompt.jinja
└── ...
```

## Scenario vs Agent Handoffs

| Approach | Where Defined | Use Case |
|----------|---------------|----------|
| Agent `handoff.trigger` | `agent.yaml` | Single-scenario apps |
| Scenario `handoffs` | `orchestration.yaml` | Multi-scenario apps |

The scenario-based approach is recommended because:

- Routes are visible in one place
- Easy to add `handoff_condition` prompts
- Different behaviors per deployment

## Next Steps

- [Tools Guide](tools.md) - Learn how to create tools
- [Agents Guide](agents.md) - Learn how to create agents
- [Overview](index.md) - Understand how everything connects
