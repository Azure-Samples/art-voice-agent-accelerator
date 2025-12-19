# Insurance Scenario

> **Model:** Security-first · **Entry:** AuthAgent · **Handoffs:** Mixed (B2C announced, B2B discrete)

---

## Architecture

```
            ┌───────────┐
            │ AuthAgent │ ← Security gate
            └─────┬─────┘
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│  Policy  │ │   FNOL   │ │  Subro   │
│  Advisor │ │  Agent   │ │  Agent   │
└──────────┘ └──────────┘ └──────────┘
     B2C          B2C          B2B
```

**Two caller types:**

| Type | Auth Method | Flow |
|:-----|:------------|:-----|
| B2C (Policyholder) | Policy + Name + SSN4 | → PolicyAdvisor / FNOLAgent |
| B2B (Claimant Carrier) | Company Code + Claim # | → SubroAgent |

---

## Agents

| Agent | Purpose | Key Tools |
|:------|:--------|:----------|
| **AuthAgent** | Entry, identity verification | `verify_client_identity`, `verify_cc_caller` |
| **PolicyAdvisor** | Policy inquiries | `get_policy_details`, `get_coverage_details` |
| **FNOLAgent** | File new claims | `file_new_claim` |
| **SubroAgent** | B2B subrogation | `get_coverage_status`, `evaluate_rush_criteria` |

---

## Test Scripts

### Script 1: B2B Subrogation (Golden Path)

> Claimant carrier rep calling about claim recovery — tests all 6 inquiry steps

??? note "Setup"
    ```
    scenario: insurance
    insurance_role: cc_rep
    test_scenario: golden_path
    ```

??? example "Full Conversation"

    | # | Caller (Lisa) | Agent | Tool |
    |:--|:--------------|:------|:-----|
    | **Auth** ||||
    | 1 | "Lisa Chen, Contoso Insurance" | "Company code?" | — |
    | 2 | "CI-1234" | "Claim number?" | — |
    | 3 | "CLM-2024-1234" | — | `verify_cc_caller` |
    | 4 | — | *(SubroAgent)* "Got it. What do you need?" | → discrete |
    | **1️⃣ Coverage** ||||
    | 5 | "Confirm coverage?" | "Coverage confirmed. Active policy." | `get_coverage_status` |
    | **2️⃣ Liability** ||||
    | 6 | "Liability?" | "Accepted at 80%." | `get_liability_decision` |
    | **3️⃣ Limits** ||||
    | 7 | "PD limits?" | "$50k. Your demand is within limits." | `get_pd_policy_limits` |
    | **4️⃣ Payments** ||||
    | 8 | "Payments made?" | "$14,832 on Nov 15. Check #84521." | `get_subro_payments` |
    | **5️⃣ Demand** ||||
    | 9 | "Demand status?" | "$43,847.52 under review. Sarah Johnson handling." | `get_subro_demand_status` |
    | **6️⃣ Rush** ||||
    | 10 | "We need this expedited" | "Third call detected. Other criteria?" | `evaluate_rush_criteria` |
    | 11 | "Deadline in 30 days" | "Two criteria met. Flagged for rush." | — |

??? abstract "Validated"
    - [x] B2B auth via company code
    - [x] Discrete handoff (no greeting)
    - [x] All 6 inquiry steps pass
    - [x] Rush auto-detects call history
    - [x] Rush requires 2+ criteria

---

### Script 2: Policyholder Claim Status

> Customer checking on existing claim

??? example "Full Conversation"

    | # | Caller (John) | Agent | Tool |
    |:--|:--------------|:------|:-----|
    | 1 | "Check on my claim" | "Policy number?" | — |
    | 2 | "POL-AUTO-789012" | "Name and SSN4?" | — |
    | 3 | "John Smith, 1234" | "Verified. Your Oct 15 claim?" | `verify_client_identity` |
    | 4 | "What's the status?" | "Under investigation. Mike Johnson handling." | `get_claim_status` |
    | 5 | "When do I get paid?" | "3 business days after completion. $500 deductible applies." | `get_payment_status` |

??? abstract "Validated"
    - [x] Policy + name + SSN4 auth
    - [x] Claim status retrieval
    - [x] Payment timeline explained

---

### Script 3: First Notice of Loss (FNOL)

> Filing a new claim after accident

??? example "Full Conversation"

    | # | Caller (Maria) | Agent | Tool |
    |:--|:---------------|:------|:-----|
    | 1 | "I was in an accident" | "Are you okay? Let me help file a claim." | — |
    | 2 | *[Provides policy + verification]* | — | `verify_client_identity` |
    | 3 | — | *(FNOLAgent)* "Tell me what happened" | → announced |
    | 4 | "Rear-ended at stoplight" | "When?" | — |
    | 5 | "An hour ago" | "Where?" | — |
    | 6 | "Main & 5th" | "Injuries?" | — |
    | 7 | "No, just vehicle damage" | "Creating claim..." | `file_new_claim` |
    | 8 | — | "Claim CLM-2024-NEW123. Adjuster calls within 24h." | — |

??? abstract "Validated"
    - [x] Empathetic response
    - [x] Announced handoff to FNOLAgent
    - [x] Loss details collected
    - [x] Immediate claim number

---

## B2B Subrogation: 6-Step Flow

```
1️⃣ Coverage → 2️⃣ Liability → 3️⃣ Limits → 4️⃣ Payments → 5️⃣ Demand → 6️⃣ Rush
```

| Step | Question | Tool | Returns |
|:----:|:---------|:-----|:--------|
| 1️⃣ | "Coverage confirmed?" | `get_coverage_status` | Confirmed / Denied / CVQ |
| 2️⃣ | "Liability decision?" | `get_liability_decision` | % + basis |
| 3️⃣ | "PD limits?" | `get_pd_policy_limits` | Limits + demand comparison |
| 4️⃣ | "Payments made?" | `get_subro_payments` | List with dates/amounts |
| 5️⃣ | "Demand status?" | `get_subro_demand_status` | Status + handler |
| 6️⃣ | "Rush eligible?" | `evaluate_rush_criteria` | Requires 2+ criteria |

### Rush Criteria (need 2+)

| Criterion | Check |
|:----------|:------|
| Third+ call | ⚡ Auto-detected |
| Deadline < 60 days | Caller provides |
| Litigation pending | Caller provides |
| Prior demands ignored | Caller provides |

---

## Test Scenarios

| `test_scenario` | Claim | What It Tests |
|:----------------|:------|:--------------|
| `golden_path` | CLM-2024-1234 | Full B2B workflow |
| `demand_paid` | CLM-2024-005678 | Already paid |
| `coverage_denied` | CLM-2024-003456 | Policy lapsed |
| `liability_denied` | CLM-2024-002468 | Fault rejected |
| `demand_exceeds_limits` | CLM-2024-024680 | $85k vs $25k limit |

---

## Configuration

```yaml title="registries/scenariostore/insurance/orchestration.yaml"
name: insurance
start_agent: AuthAgent

agents:
  - AuthAgent
  - PolicyAdvisor
  - FNOLAgent
  - SubroAgent

handoffs:
  # B2C: Announced (new specialist greets)
  - from: AuthAgent
    to: PolicyAdvisor
    tool: handoff_policy_advisor
    type: announced

  - from: AuthAgent
    to: FNOLAgent
    tool: handoff_fnol_agent
    type: announced

  # B2B: Discrete (seamless for professionals)
  - from: AuthAgent
    to: SubroAgent
    tool: handoff_subro_agent
    type: discrete

  # Cross-specialist
  - from: PolicyAdvisor
    to: FNOLAgent
    tool: handoff_fnol_agent
    type: announced

  - from: FNOLAgent
    to: PolicyAdvisor
    tool: handoff_policy_advisor
    type: announced
```
