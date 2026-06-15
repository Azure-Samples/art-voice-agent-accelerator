# Agent Reference Catalog

This section provides focused documentation for each agent in the ART Voice Agent Accelerator. Each agent has a dedicated page with configuration, tools, handoff routes, and usage context.

## Banking Domain

| Agent | Purpose | Entry Point |
|-------|---------|-------------|
| [BankingConcierge](banking-concierge.md) | Primary banking assistant, routes to specialists | ✅ Yes |
| [FraudAgent](fraud-agent.md) | Fraud detection and investigation | No |
| [InvestmentAdvisor](investment-advisor.md) | 401(k), IRA, rollover guidance | No |
| [CardRecommendation](card-recommendation.md) | Credit card recommendations | No |

## Insurance Domain

| Agent | Purpose | Entry Point |
|-------|---------|-------------|
| [PolicyAdvisor](policy-advisor.md) | Policy information and guidance | ✅ Yes |
| [ClaimsSpecialist](claims-specialist.md) | Claims processing and status | No |
| [FNOLAgent](fnol-agent.md) | First Notice of Loss intake | No |
| [SubroAgent](subro-agent.md) | B2B subrogation specialist | No |

## Cross-Domain

| Agent | Purpose | Entry Point |
|-------|---------|-------------|
| [AuthAgent](auth-agent.md) | Authentication and MFA | No |
| [Concierge](concierge.md) | Generic entry point | ✅ Yes |
| [ComplianceDesk](compliance-desk.md) | AML/FATCA verification | No |
| [GeneralKBAgent](general-kb-agent.md) | Knowledge base queries | No |

---

## Handoff Patterns

Agents hand off conversations using two greeting patterns:

=== "Discrete Handoff"

    A **silent** handoff where the new agent continues the conversation naturally without announcing itself. Best for seamless same-team specialist routing.
    
    ```mermaid
    sequenceDiagram
        participant User
        participant Concierge
        participant CardSpec as CardRecommendation
        
        User->>Concierge: I want a new credit card
        Concierge->>CardSpec: handoff_card_recommendation
        Note over Concierge: Silent transfer
        CardSpec->>User: I'd be happy to help you find the perfect card. What do you typically spend the most on?
        Note over CardSpec: No greeting/introduction
    ```
    
    **Use when:** Same-team specialists, natural conversation continuity, internal routing

=== "Announced Handoff"

    An **announced** handoff where the new agent greets the user and introduces itself. This makes the transition explicit and sets expectations.
    
    !!! note "Terminology"
        "Announced" and "non-discrete" are synonymous. The new agent plays a greeting.
    
    ```mermaid
    sequenceDiagram
        participant User
        participant Concierge
        participant Fraud as FraudAgent
        
        User->>Concierge: I think someone stole my card
        Concierge->>Fraud: handoff_fraud_agent
        Note over Concierge: Transfer with greeting
        Fraud->>User: I'm the Fraud Specialist. I understand you're concerned about potential unauthorized activity. Let me help you secure your account immediately.
        Note over Fraud: Agent introduces itself
    ```
    
    **Use when:** Different domain expert, escalation, user should know who they're speaking with

---

### Configuration Example

```yaml
# Discrete handoff: silent, no greeting
handoff:
  trigger: handoff_card_recommendation
  discrete: true  # No greeting from target agent

# Announced handoff: target agent greets/introduces itself
handoff:
  trigger: handoff_fraud_agent
  discrete: false  # Target agent will greet (default)

# Optional: Return to caller after task completion
handoff:
  trigger: handoff_auth
  return_to_caller: true  # Returns after authentication
```

!!! tip "Discrete vs Return"
    - **`discrete`** controls greeting behavior (silent vs announced)
    - **`return_to_caller`** controls flow (one-way vs round-trip)
    
    These are independent — you can have an announced handoff that returns, or a discrete handoff that doesn't.

See [Handoff Strategies](../handoffs.md) for full configuration details.

---

## Agent Configuration Overview

All agents are configured via YAML in `apps/artagent/backend/registries/agentstore/`.

### Key Configuration Sections

| Section | Purpose |
|---------|---------|
| `handoff` | Trigger tool name, entry point flag |
| `voice` | Azure TTS voice settings |
| `voicelive_model` / `cascade_model` | LLM configuration per mode |
| `session` | VoiceLive VAD and transcription |
| `speech` | Cascade mode STT/TTS settings |
| `tools` | Available tool names |
| `prompts.path` | Path to Jinja prompt template |

See [Agent Configuration Schema](../../../architecture/registries/agents.md) for full schema documentation.

---

## Quick Links

- [Agent Framework Overview](../README.md)
- [Handoff Strategies](../handoffs.md)
- [Tool Registry](../../registries/tools.md)
- [Scenario Configuration](../../registries/scenarios.md)
