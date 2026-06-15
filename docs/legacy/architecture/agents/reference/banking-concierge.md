# BankingConcierge Agent

Primary entry point for banking customers. Routes to specialists based on customer intent.

---

## Configuration

| Property | Value |
|----------|-------|
| **Name** | `BankingConcierge` |
| **Industry** | Banking |
| **Entry Point** | ✅ Yes |
| **Handoff Trigger** | `handoff_concierge` |
| **Voice** | `en-US-OnyxTurboMultilingualNeural` |

**Source:** `apps/artagent/backend/registries/agentstore/banking_concierge/agent.yaml`

---

## Capabilities

- Account summary retrieval
- Recent transaction lookup
- Fee refund processing
- Client identity verification
- Route to specialists based on needs

---

## Tools

### Account Operations
| Tool | Purpose |
|------|---------|
| `get_user_profile` | Retrieve caller's profile information |
| `get_account_summary` | Retrieve account balances and status |
| `get_recent_transactions` | List recent account transactions |
| `refund_fee` | Process fee refunds |

### Identity
| Tool | Purpose |
|------|---------|
| `verify_client_identity` | Verify caller identity |

### Handoffs
| Tool | Destination Agent |
|------|-------------------|
| `handoff_card_recommendation` | [CardRecommendation](card-recommendation.md) |
| `handoff_investment_advisor` | [InvestmentAdvisor](investment-advisor.md) |

### Escalation
| Tool | Purpose |
|------|---------|
| `escalate_human` | Transfer to human agent |
| `escalate_emergency` | Emergency escalation |
| `transfer_call_to_call_center` | Direct call center transfer |

---

## Handoff Graph

```mermaid
flowchart LR
    BC[BankingConcierge] --> CR[CardRecommendation]
    BC --> IA[InvestmentAdvisor]
    BC --> H[Human Agent]
    
    CR --> BC
    IA --> BC
    
    AA[AuthAgent] --> BC
    FA[FraudAgent] --> BC
```

---

## Voice Configuration

```yaml
voice:
  name: en-US-OnyxTurboMultilingualNeural
  type: azure-standard
  rate: "0%"
```

---

## Prompt Template

Located at: `apps/artagent/backend/registries/agentstore/banking_concierge/prompt.jinja`

### Context Variables
| Variable | Description |
|----------|-------------|
| `caller_name` | Authenticated caller name |
| `phone_number` | Caller's phone number |
| `accounts` | List of user accounts |
| `handoff_context` | Context from previous agent |
| `collected_information` | Data gathered during call |

---

## Usage Scenarios

### Primary Flow
1. Caller arrives at BankingConcierge (entry point)
2. Agent greets and verifies identity
3. Handles request or routes to specialist

### Return Flow
1. Specialist completes task
2. Specialist hands off back to BankingConcierge
3. BankingConcierge confirms and closes

---

## Related Agents

- [CardRecommendation](card-recommendation.md) - Credit card specialist
- [InvestmentAdvisor](investment-advisor.md) - Retirement accounts
- [FraudAgent](fraud-agent.md) - Fraud investigations
- [AuthAgent](auth-agent.md) - Step-up authentication
