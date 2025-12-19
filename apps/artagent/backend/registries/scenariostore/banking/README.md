# Banking Scenario - Multi-Agent Voice System

## Business Overview

This scenario demonstrates a **private banking voice concierge** that handles high-value customer inquiries through intelligent routing to specialized financial advisors.

### Business Value

| Capability | Business Impact |
|------------|-----------------|
| **VIP Concierge Service** | Premium experience for high-net-worth clients |
| **Card Recommendation Engine** | Increase card product adoption, match benefits to lifestyle |
| **401(k) Rollover Guidance** | Capture rollover assets, grow AUM |
| **Investment Advisory** | Retirement planning, tax optimization |
| **Real-Time Fee Resolution** | Immediate refunds, improved satisfaction |

## Agent Architecture

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
              ┌───────────────┐                           │
              │   Banking     │  ← Entry Point            │
              │   Concierge   │                           │
              └───────┬───────┘                           │
                      │                                   │
            ┌─────────┴─────────┐                         │
            │                   │                         │
            ▼                   ▼                         │
     ┌──────────────┐   ┌────────────────┐                │
     │    Card      │   │   Investment   │                │
     │Recommendation│◄─►│    Advisor     │                │
     └──────┬───────┘   └───────┬────────┘                │
            │                   │                         │
            └─────────┬─────────┘                         │
                      │                                   │
                      └───────────────────────────────────┘
                        (All return to BankingConcierge)
```

### Agent Roles

| Agent | Purpose | Specialization |
|-------|---------|----------------|
| **BankingConcierge** | Entry point, triage, general inquiries | Account summaries, transactions, fee resolution |
| **CardRecommendation** | Credit card specialist | Product matching, applications, e-sign |
| **InvestmentAdvisor** | Retirement planning | 401(k) rollovers, tax impact, IRA guidance |

## 🎯 Test Scenarios

### Scenario A: Account Inquiry & Fee Dispute

> **Persona**: Michael, a Premier client, calling about a foreign transaction fee.

#### Setup
1. Create demo profile: `scenario=banking`
2. Note the SSN4 (e.g., `1234`) for verification

#### Script

| Turn | Caller Says | Agent Does | Tool Triggered |
|------|-------------|------------|----------------|
| 1 | "Hi, I need to check my account" | Asks for name + SSN4 | — |
| 2 | "Michael Chen, last four 9999" | Verifies identity | `verify_client_identity` ✓ |
| 3 | — | Loads profile | `get_user_profile` ✓ |
| 4 | "What's my checking balance?" | Retrieves accounts | `get_account_summary` ✓ |
| 5 | "I see a foreign transaction fee, can you waive it?" | Checks transactions, refunds | `get_recent_transactions` ✓ → `refund_fee` ✓ |
| 6 | "Thanks, that's all" | Confirms and closes | — |

#### Business Rules Tested
- ✅ Must authenticate before accessing account data
- ✅ Fee refunds based on relationship tier
- ✅ Transaction details include fee breakdowns

### Scenario B: Credit Card Recommendation & Application

> **Persona**: Sarah, looking for a travel rewards card.

#### Script

| Turn | Caller Says | Agent Does | Tool Triggered |
|------|-------------|------------|----------------|
| 1 | "I want a new credit card for travel" | Verifies identity first | `verify_client_identity` ✓ |
| 2 | — | Routes to CardRecommendation | Handoff |
| 3 | "I travel internationally a lot" | Searches card products | `search_card_products` ✓ |
| 4 | "Tell me more about the Sapphire Reserve" | Gets details | `get_card_details` ✓ |
| 5 | "What's the annual fee?" | Searches FAQs | `search_credit_card_faqs` ✓ |
| 6 | "I'd like to apply" | Checks eligibility | `evaluate_card_eligibility` ✓ |
| 7 | — | Sends e-sign agreement | `send_card_agreement` ✓ |
| 8 | "I signed it" | Verifies signature | `verify_esignature` ✓ |
| 9 | — | Finalizes application | `finalize_card_application` ✓ |

#### Card Products Available
- 🔷 **Sapphire Reserve** - Premium travel, lounge access, 3x points
- 🔷 **Sapphire Preferred** - Mid-tier travel, 2x points
- 🔷 **Freedom Unlimited** - Cash back, no annual fee
- 🔷 **Freedom Flex** - Rotating 5% categories
- 🔷 **Business Ink** - Business expenses, 2x on travel

#### Business Rules Tested
- ✅ Recommendations based on spending profile
- ✅ Credit limit based on income tier
- ✅ E-signature workflow with email delivery
- ✅ Application finalization with instant decision

### Scenario C: 401(k) Rollover Consultation

> **Persona**: David, just left his job and needs help with his old 401(k).

#### Script

| Turn | Caller Says | Agent Does | Tool Triggered |
|------|-------------|------------|----------------|
| 1 | "I need help with my 401k from my old job" | Verifies identity | `verify_client_identity` ✓ |
| 2 | — | Routes to InvestmentAdvisor | Handoff |
| 3 | "What are my options?" | Presents rollover choices | `get_rollover_options` ✓ |
| 4 | "What's the tax impact if I cash out?" | Calculates taxes | `calculate_tax_impact` ✓ |
| 5 | "What about rolling to a Roth?" | Calculates Roth conversion | `calculate_tax_impact` ✓ |
| 6 | "What are the contribution limits?" | Searches guidance | `search_rollover_guidance` ✓ |
| 7 | "I'll do a direct rollover to IRA" | Confirms best option | — |

#### Rollover Options Explained

| Option | Tax Impact | Pros | Cons |
|--------|------------|------|------|
| **Leave in old plan** | None | No action needed | Limited control, potential fees |
| **Direct rollover to IRA** | None | More investment choices | Requires paperwork |
| **Roth conversion** | Pay taxes now | Tax-free growth | Upfront tax hit |
| **Cash out** | 20% withholding + 10% penalty | Immediate cash | Massive tax bill |

#### Business Rules Tested
- ✅ Tax calculations based on estimated bracket
- ✅ Early withdrawal penalty (10% if under 59½)
- ✅ IRS guidance from knowledge base
- ✅ Personalized recommendations

### Scenario D: Direct Deposit Setup

> **Persona**: New employee setting up payroll.

#### Script

| Turn | Caller Says | Agent Does | Tool Triggered |
|------|-------------|------------|----------------|
| 1 | "I need my account and routing number for direct deposit" | Verifies identity | `verify_client_identity` ✓ |
| 2 | — | Retrieves routing info | `get_account_routing_info` ✓ |
| 3 | "Can you repeat the account number?" | Confirms details | — |

#### Business Rules Tested
- ✅ Must authenticate before disclosing account numbers
- ✅ Returns routing + account for primary checking

### Scenario E: Cross-Agent Handoff (Card → Investment)

> **Persona**: Client asking about cards, then pivots to retirement.

#### Script

| Turn | Caller Says | Agent Does | Tool Triggered |
|------|-------------|------------|----------------|
| 1 | [Verifies identity] | Loads profile | `verify_client_identity` ✓ |
| 2 | "I want to look at credit cards" | Routes to Card specialist | Handoff |
| 3 | [Gets card recommendations] | Card search | `search_card_products` ✓ |
| 4 | "Actually, I have a 401k question too" | Routes to Investment | `handoff_investment_advisor` |
| 5 | "What are my retirement accounts?" | Retrieves accounts | `get_retirement_accounts` ✓ |
| 6 | "That's all, thanks" | Returns to Concierge | `handoff_concierge` |

#### Business Rules Tested
- ✅ Seamless cross-specialist handoffs
- ✅ Context preserved across agents
- ✅ Return to entry point when done


## 🔧 Tools Reference

### Authentication Tools (auth.py)

| Tool | Purpose |
|------|---------|
| `verify_client_identity` | Name + SSN4 verification |
| `send_mfa_code` | Send 6-digit code via SMS/email |
| `verify_mfa_code` | Validate MFA code |

### Banking Tools (banking.py)

| Tool | Returns |
|------|---------|
| `get_user_profile` | Tier, preferences, contact info |
| `get_account_summary` | Balances, account numbers |
| `get_recent_transactions` | Transactions with fee details |
| `refund_fee` | Processes fee refund |

### Card Tools (banking.py)

| Tool | Returns |
|------|---------|
| `search_card_products` | Matched card recommendations |
| `get_card_details` | Benefits, fees, rates |
| `search_credit_card_faqs` | FAQ answers |
| `evaluate_card_eligibility` | Approval likelihood, limit |
| `send_card_agreement` | Emails e-sign document |
| `verify_esignature` | Validates MFA code as signature |
| `finalize_card_application` | Submits application |

### Investment Tools (investments.py)

| Tool | Returns |
|------|---------|
| `get_account_routing_info` | Routing + account numbers |
| `get_401k_details` | Balance, contributions, match |
| `get_retirement_accounts` | All retirement accounts |
| `get_rollover_options` | Options with pros/cons |
| `calculate_tax_impact` | Tax estimates by scenario |
| `search_rollover_guidance` | IRS rules, limits |


## 📊 System Capabilities Summary

| Capability | How It's Demonstrated |
|------------|----------------------|
| **Multi-Agent Orchestration** | Concierge → CardRec/InvestmentAdvisor → Return |
| **B2C Authentication** | Name + SSN4 + optional MFA |
| **Real-Time Data Access** | Live Cosmos DB queries for profiles/accounts |
| **Personalized Recommendations** | Card matching based on spending profile |
| **E-Signature Workflow** | Email agreement → MFA verification → Finalize |
| **Tax Calculations** | Rollover scenarios with withholding/penalties |
| **Knowledge Base Search** | IRS rules, card FAQs |
| **Fee Resolution** | Automatic refunds based on tier |
| **Cross-Agent Context** | Seamless specialist transitions |
