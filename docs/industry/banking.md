# Banking Scenario

> **Model:** Service-first · **Entry:** BankingConcierge · **Handoffs:** All discrete

---

## Architecture

```
         ┌──────────────────┐
         │ BankingConcierge │ ← Handles 80% of requests
         └────────┬─────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
  ┌───────────┐      ┌──────────────┐
  │   Cards   │ ◄──► │ Investments  │
  └───────────┘      └──────────────┘
```

**All handoffs are discrete** — feels like one continuous conversation.

---

## Agents

| Agent | Purpose | Key Tools |
|:------|:--------|:----------|
| **BankingConcierge** | Entry point, general banking | `get_account_summary`, `refund_fee` |
| **CardRecommendation** | Credit cards, e-signature | `search_card_products`, `finalize_card_application` |
| **InvestmentAdvisor** | 401k, retirement, tax | `get_rollover_options`, `calculate_tax_impact` |

---

## Test Scripts

### Script 1: New Job Setup (Golden Path)

> Customer needs direct deposit + 401k rollover guidance

??? example "Full Conversation"

    | # | Caller | Agent | Tool |
    |:--|:-------|:------|:-----|
    | 1 | "I just started a new job" | "Congrats! Direct deposit or 401k questions?" | — |
    | 2 | "Direct deposit first" | "Your routing: 021000021, account ends 4567" | `get_account_summary` |
    | 3 | "Now my old 401k" | "Let me check your retirement accounts" | → `handoff_investment_advisor` |
    | 4 | — | "You have $75k at TechCorp. Four options..." | `get_401k_details` |
    | 5 | "What if I cash out?" | "20% withholding + 10% penalty = $30k+ loss" | `calculate_tax_impact` |
    | 6 | "I'll do the IRA" | "Smart. Contact TechCorp to initiate." | — |
    | 7 | "Any travel cards?" | "Let me find options" | → `handoff_card_recommendation` |
    | 8 | — | "Sapphire Reserve: no foreign fees, lounge access" | `search_card_products` |

??? abstract "Validated"
    - [x] Discrete handoff Concierge → Investment
    - [x] Cross-specialist handoff Investment → Cards  
    - [x] Tax impact calculation with penalties
    - [x] Natural conversation flow

---

### Script 2: Card Application (E-Signature)

> Customer applies for travel card with full e-sign flow

??? example "Full Conversation"

    | # | Caller | Agent | Tool |
    |:--|:-------|:------|:-----|
    | 1 | "I want a travel card" | "International travel often?" | — |
    | 2 | "5 times a year" | "Sapphire Reserve is best. No foreign fees." | `search_card_products` |
    | 3 | "Annual fee?" | "$550, but credits offset for travelers" | `search_credit_card_faqs` |
    | 4 | "I'll apply" | "You're pre-approved! Sending agreement..." | `evaluate_card_eligibility` |
    | 5 | — | "Check email for 6-digit code" | `send_card_agreement` |
    | 6 | "Code is 385729" | "Verified. Finalizing..." | `verify_esignature` |
    | 7 | — | "Approved! Ships in 3-5 days." | `finalize_card_application` |

??? abstract "Validated"
    - [x] Product search by preference
    - [x] FAQ retrieval for fees/APR
    - [x] Full e-signature flow
    - [x] Application finalization

---

### Script 3: Fee Dispute

> Platinum customer disputes foreign ATM fee

??? example "Full Conversation"

    | # | Caller | Agent | Tool |
    |:--|:-------|:------|:-----|
    | 1 | "Question about a fee" | "Let me pull your transactions" | `get_recent_transactions` |
    | 2 | "The London ATM fee" | "$18: $10 bank fee + $8 ATM owner fee" | — |
    | 3 | "Can you waive it?" | "As Platinum, yes. Process refund?" | — |
    | 4 | "Yes" | "Done. Credit in 2 business days." | `refund_fee` |
    | 5 | — | "Cards with no foreign fees could help. Interested?" | — |

??? abstract "Validated"
    - [x] Transaction lookup with fee breakdown
    - [x] Tier-based waiver eligibility
    - [x] Permission before refund
    - [x] Proactive next-best-action

---

## Configuration

```yaml title="registries/scenariostore/banking/orchestration.yaml"
name: banking
start_agent: BankingConcierge

agents:
  - BankingConcierge
  - CardRecommendation
  - InvestmentAdvisor

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
    to: InvestmentAdvisor
    tool: handoff_investment_advisor
    type: discrete

  - from: InvestmentAdvisor
    to: CardRecommendation
    tool: handoff_card_recommendation
    type: discrete

  - from: CardRecommendation
    to: BankingConcierge
    tool: handoff_concierge
    type: discrete

  - from: InvestmentAdvisor
    to: BankingConcierge
    tool: handoff_concierge
    type: discrete
```
