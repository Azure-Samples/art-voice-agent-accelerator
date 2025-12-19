# Financial Services Multi-Agent System - Interactive Testing Script

This document provides step-by-step testing scenarios using the real data inserted into CosmosDB. Follow each scenario to test the complete agent flow with actual client data.

## Prerequisites
- System running with CosmosDB collections populated (from notebook 11)
- Voice interface or text interface available
- Access to backend logs for verification

## Test Data Available in CosmosDB

### Clients in `users` collection:
- **pablo_salvador_cfs**: Pablo Salvador, Contoso Financial Services (Platinum, $875K balance)
- **emily_rivera_gca**: Emily Rivera, Global Capital Advisors (Gold, $340K balance)

### DRIP Positions in `drip_positions` collection:
- **emily_rivera_gca**: 
  - PLTR: 1,078.42 shares worth $48,873.36 (€44,964.29)
  - MSFT: 245.67 shares worth $103,795.58 (€95,492.33)
  - TSLA: 89.23 shares worth $23,500.41 (€21,620.38)

### Transfer Agency Profiles in `transfer_agency_clients`:
- **emily_rivera_gca_ta**: Global Capital Advisors institutional profile with compliance status

---

## Scenario 1: DRIP Liquidation Request - PLTR Position
**Test with Emily Rivera (Global Capital Advisors client)**

### Step 1: Initial Authentication
**What to say**: "Hello, this is Emily Rivera from Global Capital Advisors calling about our DRIP positions"

**Expected Agent Response**: AutoAuth Agent
- "Hello Emily, I need to verify your identity. Can you provide your client ID?"

**What to say**: "emily_rivera_gca"

**Expected**: 
- Agent should find client in users collection
- "I'm sending an MFA code to your registered phone number ending in 4567"

### Step 2: MFA Verification
**Expected**: MFA code delivery simulation

**What to say**: "123456" (simulate MFA code)

**Expected**: 
- "Authentication successful. Transferring you to our Transfer Agency specialist."
- Handoff to Agency Agent with greeting

### Step 3: Agency Agent Interaction
**Expected Agent Greeting**: 
- "Hello Emily, this is our Transfer Agency Specialist. As a valued Gold client, I'm here to provide priority service for your DRIP inquiry."

**What to say**: "I need to liquidate 50% of my Palantir PLTR position and convert the proceeds to EUR"

**Expected Agency Agent Actions**:
1. **Tool Call**: `get_client_data` with client_code: "emily_rivera_gca"
2. **Tool Call**: `get_drip_positions` with client_code: "emily_rivera_gca" 
3. **Tool Call**: `calculate_liquidation_proceeds`

**Expected Response**:
- "I see you have 1,078.42 shares of Palantir (PLTR) with a current market value of $48,873.36"
- "A 50% liquidation would be 539.21 shares worth approximately $24,436.68"
- "Your account currency is EUR, so that converts to €22,482.15 at current FX rate"
- "This is already in your preferred EUR account currency"

### Step 4: Trading Handoff Decision
**What to say**: "Yes, please proceed with the liquidation"

**Expected**: 
- **Tool Call**: `handoff_to_trading` with complexity: "standard"
- "Transferring you to our Standard Trading Desk. Expected wait time: 2-4 minutes"
- Handoff to Trading Agent

### Step 5: Trading Agent Execution
**Expected Trading Agent Greeting**:
- "Hello Emily, this is our Trading Specialist. I have your PLTR liquidation request for 539.21 shares."

**What to say**: "Please execute with same-day settlement"

**Expected**:
- "Executing 539.21 shares of PLTR with same-day settlement. Processing fee will be $250"
- "Net proceeds: €22,252.15 (after fees) settling today to your EUR account"
- "Trade confirmation will be sent to emily.rivera@globalcapital.com"

---

## Scenario 2: Compliance Review Escalation
**Test with Emily Rivera - Transfer Agency Profile compliance check**

### Step 1: Authentication Flow
**What to say**: "This is Emily Rivera from Global Capital Advisors calling about compliance documentation"

**Expected**: AutoAuth Agent requests identity verification

**What to say**: "My client ID is emily_rivera_gca"

**Expected**: 
- Client found in users collection
- MFA code sent to +15551234567

**What to say**: "654321" (MFA code)

**Expected**: Authentication successful, handoff to Agency Agent

### Step 2: Agency Agent - Compliance Issue Discovery
**What to say**: "I need to check our institutional compliance status. We have some upcoming reviews and want to ensure we're current"

**Expected Agency Agent Actions**:
1. **Tool Call**: `get_client_data` for emily_rivera_gca
2. **Tool Call**: `check_compliance_status` for emily_rivera_gca

**Expected Response**:
- "I can see your main profile shows KYC verified and AML cleared as of September 30th, 2024"
- "Your institutional transfer agency profile shows Active status with Global Capital Advisors"
- "Let me check your specific compliance requirements and transfer you to our Compliance Review team"

### Step 3: Compliance Handoff
**Expected**:
- **Tool Call**: `handoff_to_compliance` with urgency: "normal"
- "Transferring to Standard Compliance Review. Wait time: 10-15 minutes"
- Handoff ID: COMP-[8-digit code]

### Step 4: Compliance Agent Review
**Expected Compliance Agent Greeting**:
- "Hello Emily, this is our Compliance Specialist. I have your institutional compliance review request."

**What to say**: "What documents do we need to keep current for our institutional status?"

**Expected Compliance Response**:
- Reviews transfer_agency_clients and compliance_records
- "For your institutional status with Global Capital Advisors, you need: Annual AML questionnaire, Updated beneficial ownership certification, Corporate resolution maintaining authorization levels"
- "Your current compliance is good through 2024, next review due Q1 2025"
- "I'm sending the compliance checklist to emily.rivera@globalcapital.com"

---

## Scenario 3: Fraud Investigation  
**Test with Pablo Salvador - Suspicious transaction alert**

### Step 1: Fraud Authentication Flow
**What to say**: "This is an urgent fraud report. I'm Pablo Salvador and I see suspicious activity on my account that I need to report immediately"

**Expected**: AutoAuth Agent with enhanced security

**What to say**: "My client ID is pablo_salvador_cfs"

**Expected**: 
- Enhanced identity verification for Contoso Financial Services
- Additional security questions
- MFA to +15551234568

### Step 2: Fraud Agent Investigation
**Expected**: Direct handoff to Fraud Agent (not Agency)

**What to say**: "I received an email about a $125,000 wire transfer from my account that I never authorized. I'm currently traveling in Europe and haven't made any large transfers."

**Expected Fraud Agent Actions**:
1. **Tool Call**: `analyze_recent_transactions` for pablo_salvador_cfs
2. **Tool Call**: `check_suspicious_activity`
3. **Tool Call**: `create_fraud_case`

**Expected Response**:
- "I'm reviewing your Contoso Financial Services Platinum account ($875,432.10 balance)"
- "I can see the suspicious $125,000 transaction you mentioned"
- "Creating fraud case FR-2024-11-[random number]"
- "Placing immediate fraud alert and investigating the unauthorized transfer"

### Step 3: Security Actions
**What to say**: "Can you block any compromised access and help secure my account?"

**Expected**:
- **Tool Call**: `block_card_emergency`
- **Tool Call**: `ship_replacement_card`
- "I'm blocking the compromised access credentials immediately"
- "Enhanced security monitoring activated for your account"
- "New access credentials will be expedited to your address"

### Step 4: Case Documentation
**Expected**:
- **Tool Call**: `send_fraud_case_email`
- "Sending detailed case documentation to pablo.salvador@contoso.com"
- "Investigation timeline: 3-5 business days for Platinum account holder"
- "You'll receive priority updates on case progress via secure email"

---

## Scenario 4: Complex Multi-Currency Settlement
**Test with Emily Rivera's multi-position liquidation**

### Step 1: Authentication & Agency Routing
**Follow authentication flow for emily_rivera_gca (Emily Rivera)**

### Step 2: Complex Liquidation Request
**What to say**: "I need to liquidate portions of multiple positions - 25% of my PLTR holdings and all of my TSLA position. Can you structure the settlement in different currencies?"

**Expected Agency Actions**:
1. **Tool Call**: `get_drip_positions` for emily_rivera_gca
2. **Tool Call**: `calculate_liquidation_proceeds` with multi-position

**Expected Response**:
- "Your current positions: PLTR 1,078.42 shares (€48,873.36), TSLA 89.23 shares (€39,845.67)"
- "25% PLTR liquidation: 269.61 shares worth €12,218.34"
- "Full TSLA liquidation: 89.23 shares worth €39,845.67" 
- "This is a complex multi-currency transaction involving USD→EUR settlement"
- "Transferring to our Complex Trades desk for specialized handling"

### Step 3: Complex Trading Handoff
**Expected**:
- **Tool Call**: `handoff_to_trading` with complexity: "complex"
- "Routing to Complex Trades Desk. Wait time: 5-10 minutes for Global Capital Advisors client"

### Step 4: Trading Agent - Multi-Currency Execution
**Expected Trading Greeting**:
- "Hello Emily, this is our Complex Trades specialist. I have your multi-position liquidation totaling €52,064.01."

**What to say**: "Yes, please proceed. I'd like the PLTR proceeds in EUR and the TSLA proceeds in USD."

**Expected Trading Response**:
- "Structuring as follows:"
- "PLTR partial liquidation: €12,218.34 (EUR settlement)"
- "50% CHF conversion: £1,600,000 × 1.127 = CHF 1,803,200"
- "FX hedges: EUR/GBP at 0.7598, EUR/CHF at 0.8437"
- "TSLA full liquidation: $43,562.89 USD (USD settlement)"
- "Total proceeds: €12,218.34 + $43,562.89"
- "Cross-currency FX hedge applied for Global Capital Advisors institutional rate"

---

## Verification Checkpoints

### Database Queries to Verify
Use these queries to verify the system is working correctly with real client data:

```javascript
// Check Emily Rivera's client data
db.users.findOne({"user_id": "emily_rivera_gca"})

// Check Emily's DRIP positions
db.drip_positions.find({"user_id": "emily_rivera_gca"})

// Check Pablo Salvador's profile
db.users.findOne({"user_id": "pablo_salvador_cfs"})

// Check transfer agency clients
db.transfer_agency_clients.find({})
```

### Expected Tool Execution Log
Monitor backend logs for these tool calls with real client data:

```
INFO: Tool executed: get_client_data(client_code="emily_rivera_gca")
INFO: Tool executed: get_drip_positions(client_code="emily_rivera_gca") 
INFO: Tool executed: calculate_liquidation_proceeds(shares=539.21, symbol="PLTR")
INFO: Tool executed: handoff_to_compliance(urgency="normal")
INFO: Tool executed: analyze_recent_transactions(client_code="pablo_salvador_cfs")
INFO: Tool executed: handoff_to_trading(complexity="complex")
```

### Agent Transition Verification
Look for these orchestrator logs:

```
INFO: Financial Services Hand-off → Agency (type: Transfer)
INFO: Financial Services Hand-off → Compliance (type: Compliance) 
INFO: Financial Services Hand-off → Fraud (type: Fraud)
INFO: Financial Services Hand-off → Trading (type: Trading)
INFO: Agent transition: AutoAuth -> Agency -> Compliance
INFO: Sending agent greeting for Financial Services specialist
```

## Common Issues & Troubleshooting

### Issue: "Client not found"
- Verify CosmosDB collections are populated with notebook 11 data
- Check client_id spelling exactly: "emily_rivera_gca" or "pablo_salvador_cfs"

### Issue: "Tool execution failed"
- Check CosmosDB connection to financial_services_db
- Verify collection names match: "users", "drip_positions", "transfer_agency_clients"

### Issue: "Agent handoff not working"
- Check orchestrator tools.py has Transfer/Fraud/Compliance/Trading handoff types
- Verify agent bindings in specialists.py for financial services

### Issue: "MFA code not working"  
- Use any 6-digit code in test environment
- Real phone numbers from notebook: +15551234567 (Emily), +15551234568 (Pablo)
- Verify verify_mfa_code tool is registered

