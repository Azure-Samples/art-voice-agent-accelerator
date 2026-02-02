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
                         ┌──────────────────────────────────────────────┐
                         │                                              │
                         ▼                                              │
                  ┌───────────────┐                                     │
                  │   Banking     │  ← Entry Point                      │
                  │   Concierge   │                                     │
                  └───────┬───────┘                                     │
                          │                                             │
         ┌────────────────┼────────────────┬───────────────┐            │
         │                │                │               │            │
         ▼                ▼                ▼               ▼            │
  ┌──────────────┐ ┌────────────────┐ ┌──────────────┐ ┌──────────┐    │
  │    Card      │ │   Investment   │ │   Decline    │ │  Fraud   │    │
  │Recommendation│ │    Advisor     │ │  Specialist  │ │  Agent   │    │
  └──────┬───────┘ └───────┬────────┘ └──────┬───────┘ └──────────┘    │
         │                 │                 │                          │
         │◄───────────────►│                 │                          │
         │  (bidirectional)                  ▼                          │
         │                 │          ┌──────────┐                      │
         │                 │          │  Fraud   │                      │
         │                 │          │  Agent   │  (fraud escalation)  │
         │                 │          └──────────┘                      │
         │                 │                                            │
         └─────────────────┴────────────────────────────────────────────┘
                    (CardRec & InvestAdv return to BankingConcierge)
```

### Agent Roles

| Agent | Purpose | Specialization |
|-------|---------|----------------|
| **BankingConcierge** | Entry point, triage, general inquiries | Account summaries, transactions, fee resolution |
| **CardRecommendation** | Credit card specialist | Product matching, applications, e-sign |
| **InvestmentAdvisor** | Retirement planning | 401(k) rollovers, tax impact, IRA guidance |
| **DeclineSpecialist** | Decline resolution | Decline code lookup, customer scripts, resolution |
| **FraudAgent** | Fraud prevention | Suspicious activity, disputes, card blocks |

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

---

### Scenario C: Declined Transaction Resolution (Happy Path) 🎯

> **Persona**: Marcus, a customer whose debit card was declined at a store. Full flow demonstrating decline lookup, account check, and resolution.

#### Setup
1. Create demo profile: `scenario=banking`
2. Note the SSN4 (e.g., `9999`) for verification

#### Complete Script (BankingConcierge → DeclineSpecialist → Multiple Declines → FraudAgent → Back)

| Turn | Agent | Caller Says | Agent Does | Tool Triggered |
|------|-------|-------------|------------|----------------|
| 1 | **BankingConcierge** | "Hi, my debit card got declined" | Investigates first | `get_recent_transactions` ✓ |
| 2 | **BankingConcierge** | — | Found 2 declines, lists them | — |
| 3 | **BankingConcierge** | — | Asks: "Which one are you asking about?" | — |
| 4 | **BankingConcierge** | "The latest one" | **HANDOFF** to DeclineSpecialist | `handoff_decline_specialist(code=87)` |
| 5 | **DeclineSpecialist** | — | Greets + immediately looks up code | `cardapi_lookup_decline_code(87)` ✓ |
| 6 | **DeclineSpecialist** | — | Explains: "Magnetic stripe damaged. I can order replacement." | — |
| 7 | **DeclineSpecialist** | "Yes please" | Orders replacement card | `ship_replacement_card` ✓ |
| 8 | **DeclineSpecialist** | — | "Done! Anything else about your card?" | — |
| 9 | **DeclineSpecialist** | "What about my Contoso Electronics decline?" | **Stays in DeclineSpecialist** - looks up second code | `cardapi_lookup_decline_code(0W-0Z)` ✓ |
| 10 | **DeclineSpecialist** | — | Explains: "This was fraud protection. Do you recognize that transaction?" | — |
| 11 | **DeclineSpecialist** | "No, I didn't try to buy that" | Offers fraud help + asks consent | — |
| 12 | **DeclineSpecialist** | — | "I can connect you with our fraud team. Would you like that?" | — |
| 13 | **DeclineSpecialist** | "Yes" | **HANDOFF** to FraudAgent (with consent) | `handoff_fraud_agent(reason, context)` |
| 14 | **FraudAgent** | — | Greets: "You're with the Fraud Prevention desk..." | — |
| 15 | **FraudAgent** | — | Reviews transactions | `analyze_recent_transactions` ✓ |
| 16 | **FraudAgent** | "Block my card please" | Blocks card immediately | `block_card_emergency` ✓ |
| 17 | **FraudAgent** | — | Creates fraud case | `create_fraud_case` ✓ |
| 18 | **FraudAgent** | — | Ships replacement | `ship_replacement_card` ✓ |
| 19 | **FraudAgent** | — | Sends confirmation email | `send_fraud_case_email` ✓ |
| 20 | **FraudAgent** | "That's all" | Returns to concierge | `handoff_concierge` |
| 21 | **BankingConcierge** | — | "Welcome back. Anything else?" | — |

#### Key Flow Improvements:
1. **BankingConcierge investigates first** - calls `get_recent_transactions` before handoff
2. **DeclineSpecialist handles ALL decline inquiries** - does NOT hand off to itself for second decline
3. **Fraud escalation requires consent** - explains, asks, THEN transfers
4. **Full resolution loop** - returns to BankingConcierge when done

#### Decline Codes Reference (from CardAPI MCP Server)

| Code | Name | Customer Script | Orchestrator Action |
|------|------|-----------------|---------------------|
| **51** | Insufficient Funds | "Your available balance was lower than the transaction amount..." | Check account, offer overdraft |
| **14** | Invalid Card Number | "The card number entered doesn't match our records..." | Verify card, reissue if needed |
| **54** | Expired Card | "Your card has passed its expiration date..." | Offer instant digital card |
| **61** | Exceeds Withdrawal Limit | "This purchase would exceed your daily spending limit..." | Offer temporary limit increase |
| **43** | Stolen Card | "For your security, we need to verify this transaction..." | **Transfer to FraudAgent** |
| **59** | Suspected Fraud | "Our fraud protection system flagged this..." | **Transfer to FraudAgent** |

#### Business Rules Tested
- ✅ Identity verification before accessing decline info
- ✅ Decline code lookup via MCP server (cardapi)
- ✅ Customer service scripts from policy pack
- ✅ Account balance/transaction cross-check
- ✅ Fraud escalation when suspicious activity detected
- ✅ Seamless handoff DeclineSpecialist → FraudAgent
- ✅ Emergency card block + replacement shipping
- ✅ Return to BankingConcierge when resolved

---

### Scenario D: 401(k) Rollover Consultation

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

### Decline Specialist Tools (MCP: cardapi)

| Tool | Purpose | Returns |
|------|---------|---------|
| `cardapi_lookup_decline_code` | Look up a specific decline code | Code details, customer script, orchestrator action |
| `cardapi_search_decline_codes` | Search codes by keyword | Matching decline codes |
| `cardapi_get_all_decline_codes` | Get all available codes | Complete decline code list |
| `cardapi_get_decline_codes_metadata` | Get metadata about the dataset | Code categories, count, version |
| `get_account_summary` | Check customer balances | Account balances for verification |
| `get_recent_transactions` | View recent activity | Transactions to identify issues |
| `ship_replacement_card` | Send new card | Shipping confirmation |
| `verify_client_identity` | Confirm customer | Identity verified |

### Fraud Agent Tools (fraud.py)

| Tool | Purpose | Returns |
|------|---------|---------|
| `analyze_recent_transactions` | Review recent activity | Flagged suspicious transactions |
| `check_suspicious_activity` | Analyze patterns | Risk score, fraud indicators |
| `block_card_emergency` | Immediately block card | Block confirmation |
| `create_fraud_case` | Open investigation case | Case number, status |
| `create_transaction_dispute` | Dispute a transaction | Dispute ID, timeline |
| `ship_replacement_card` | Send new card | Shipping details |
| `send_fraud_case_email` | Email case summary | Delivery confirmation |
| `provide_fraud_education` | Security tips | Prevention guidance |

### Handoff Tools (All Agents)

| Tool | From | To | Type |
|------|------|-----|------|
| `handoff_card_recommendation` | BankingConcierge | CardRecommendation | discrete |
| `handoff_investment_advisor` | BankingConcierge | InvestmentAdvisor | discrete |
| `handoff_to_agent(DeclineSpecialist)` | BankingConcierge | DeclineSpecialist | announced |
| `handoff_to_agent(FraudAgent)` | BankingConcierge, DeclineSpecialist | FraudAgent | announced |
| `handoff_concierge` | CardRec, InvestAdv, FraudAgent | BankingConcierge | discrete |
| `handoff_fraud_agent` | DeclineSpecialist | FraudAgent | announced |


## 📊 System Capabilities Summary

| Capability | How It's Demonstrated |
|------------|----------------------|
| **Multi-Agent Orchestration** | Concierge → CardRec/InvestAdv/DeclineSpec/Fraud → Return |
| **B2C Authentication** | Name + SSN4 + optional MFA |
| **Real-Time Data Access** | Live Cosmos DB queries for profiles/accounts |
| **MCP Server Integration** | CardAPI MCP for decline code lookup |
| **Personalized Recommendations** | Card matching based on spending profile |
| **E-Signature Workflow** | Email agreement → MFA verification → Finalize |
| **Tax Calculations** | Rollover scenarios with withholding/penalties |
| **Knowledge Base Search** | IRS rules, card FAQs |
| **Fee Resolution** | Automatic refunds based on tier |
| **Cross-Agent Context** | Seamless specialist transitions |
| **Fraud Prevention** | Emergency card block, dispute creation |
| **Decline Resolution** | Code lookup, customer scripts, escalation |

## 🗺️ Complete Handoff Map

```
                           BANKING SCENARIO - HANDOFF FLOWS
═══════════════════════════════════════════════════════════════════════════════

                              ┌─────────────────┐
                              │ BankingConcierge│  (Entry Point)
                              │                 │
                              │ Tools:          │
                              │ • verify_client │
                              │ • get_profile   │
                              │ • get_accounts  │
                              │ • refund_fee    │
                              └────────┬────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        │ handoff_card_recommendation  │ handoff_to_agent            │ handoff_to_agent
        │ (discrete)                   │ (announced)                 │ (announced)
        ▼                              ▼                              ▼
┌───────────────────┐       ┌───────────────────┐          ┌─────────────────┐
│ CardRecommendation│◄─────►│ InvestmentAdvisor │          │DeclineSpecialist│
│                   │       │                   │          │                 │
│ Tools:            │       │ Tools:            │          │ Tools (MCP):    │
│ • search_cards    │       │ • get_401k        │          │ • lookup_code   │
│ • get_card_detail │       │ • get_retirement  │          │ • search_codes  │
│ • evaluate_elig   │       │ • calc_tax_impact │          │ • get_accounts  │
│ • send_agreement  │       │ • rollover_opts   │          │ • get_txns      │
│ • verify_esign    │       │ • search_guidance │          │ • ship_card     │
│ • finalize_app    │       │                   │          │                 │
└─────────┬─────────┘       └─────────┬─────────┘          └────────┬────────┘
          │                           │                             │
          │                           │                             │ handoff_to_agent
          │                           │                             │ (announced)
          │ handoff_concierge         │ handoff_concierge           ▼
          │ (discrete)                │ (discrete)          ┌─────────────────┐
          │                           │                     │   FraudAgent    │
          └───────────────────────────┴─────────────────────│                 │
                              │                             │ Tools:          │
                              ▼                             │ • analyze_txns  │
                       ┌─────────────────┐                  │ • check_suspect │
                       │ BankingConcierge│                  │ • block_card    │
                       │   (Return)      │◄─────────────────│ • create_case   │
                       └─────────────────┘  handoff_        │ • create_dispute│
                                            concierge       │ • ship_card     │
                                            (discrete)      └─────────────────┘

═══════════════════════════════════════════════════════════════════════════════
LEGEND:
  ────► = One-way handoff       ◄────► = Bidirectional handoff
  (discrete) = Seamless transition, same conversation
  (announced) = Agent introduces themselves, context shared
═══════════════════════════════════════════════════════════════════════════════
```
