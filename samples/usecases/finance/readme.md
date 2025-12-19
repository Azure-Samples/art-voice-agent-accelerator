
## System Architecture Overview

This is a multi-agent voice-enabled system designed for financial institutions to handle complex client servicing scenarios including transfer agency operations, fraud detection, compliance verification, and institutional trading. The system uses Azure Communication Services for real-time voice interaction and CosmosDB for data persistence.

## Agent Flow Diagram

```
                                    📞 Client Voice Call
                                           │
                                           ▼
                              ┌─────────────────────────┐
                              │      AutoAuth Agent     │
                              │   🔐 MFA & Identity     │
                              │                         │
                              │ Tools: verify_identity, │
                              │ send_mfa, verify_mfa   │
                              └─────────┬───────────────┘
                                       │
                                  ✅ Authenticated
                                       │
                        ┌──────────────┼──────────────┐
                        ▼              ▼              ▼
            ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
            │   Fraud Agent   │ │  Agency Agent   │ │ Direct Escalation│
            │   🛡️ Security    │ │  🏦 Transfer    │ │   👤 Human       │
            │                 │ │                 │ │                 │
            │ 8 Fraud Tools:  │ │ 6 Agency Tools: │ │ Emergency &     │
            │ • Transaction   │ │ • Client Data   │ │ Human Handoff   │
            │   Analysis      │ │ • DRIP Positions│ │                 │
            │ • Case Creation │ │ • Compliance    │ │                 │
            │ • Card Blocking │ │ • Liquidation   │ │                 │
            │ • Email Alerts  │ │ • Handoffs      │ │                 │
            └─────────────────┘ └─────────┬───────┘ └─────────────────┘
                    │                     │
                    │                     │ Specialist Handoffs
                    │                     │
                    ▼                     └─────────┬─────────┐
            ┌─────────────────┐                   ▼         ▼
            │  Case Resolution│           ┌─────────────┐ ┌─────────────┐
            │  📧 Email Alert │           │ Compliance  │ │   Trading   │
            │  🔄 Follow-up   │           │   Agent     │ │   Agent     │
            └─────────────────┘           │ ⚖️ AML/FATCA │ │ 💹 Execution │
                                         │             │ │             │
                                         │ Inherits    │ │ Inherits    │
                                         │ Agency      │ │ Agency      │
                                         │ Tools +     │ │ Tools +     │
                                         │ Compliance  │ │ FX/Trading  │
                                         │ Workflows   │ │ Workflows   │
                                         └─────────────┘ └─────────────┘
                                                 │               │
                                                 ▼               ▼
                                         ┌─────────────┐ ┌─────────────┐
                                         │   Queue:    │ │   Queue:    │
                                         │ 2-15 min    │ │ 2-10 min    │
                                         │ SLA routing │ │ SLA routing │
                                         └─────────────┘ └─────────────┘
```

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CosmosDB Collections                       │
├─────────────────┬─────────────────┬─────────────────────────────────┤
│                 │                 │                                 │
│ transfer_agency │   drip_positions│     compliance_records          │
│    _clients     │                 │                                 │
│                 │                 │                                 │
│ Client Master   │ Position Data   │ Regulatory Status              │
│ • Profile       │ • Holdings      │ • AML/KYC Status               │
│ • Contact Info  │ • Share Balance │ • FATCA Compliance             │
│ • Compliance    │ • Cost Basis    │ • Review History               │
│ • Preferences   │ • Dividends     │ • Documentation                │
└─────────────────┴─────────────────┴─────────────────────────────────┘
         ▲                   ▲                       ▲
         │                   │                       │
         └───────────────────┼───────────────────────┘
                             │
                    ┌─────────────────┐
                    │  Tool Registry  │
                    │   24 Total      │
                    │                 │
                    │ 🔐 Auth: 5      │
                    │ 🛡️ Fraud: 8     │
                    │ 🏦 Agency: 6    │
                    │ 🚨 Emergency: 2 │
                    │ 👤 Handoff: 3   │
                    └─────────────────┘
```

## Agent Architecture

### Entry Point
- **AutoAuth Agent**: Handles multi-factor authentication and client identity verification

### Core Service Agents
- **Fraud Agent**: Fraud detection, dispute resolution, and security case management
- **Agency Agent**: Transfer agency coordination for DRIP liquidations and institutional services

### Specialist Agents
- **Compliance Agent**: AML/FATCA verification and regulatory compliance review
- **Trading Agent**: Complex trade execution, FX conversion, and institutional settlement

## Agent Flow Patterns

### 1. Fraud Detection Flow
```
Client Call ──► AutoAuth ──► MFA ──► Fraud Agent ──► Case Creation ──► Email
```

### 2. Transfer Agency Flow
```
Client Call ──► AutoAuth ──► Agency ──► Specialist ──► Resolution
```

### 3. Compliance Review Flow
```
Agency Agent ──► Compliance Handoff ──► AML/FATCA Check ──► Decision
```

### 4. Trading Execution Flow
```
Agency Agent ──► Trading Handoff ──► FX Lock ──► Execution ──► Settlement
```
## Database Collections and Data Model

### Collection: transfer_agency_clients
**Purpose**: Store institutional client data and account information
```json
{
  "_id": "client_001",
  "client_code": "INST-2024-001",
  "client_name": "Vanguard Institutional",
  "client_type": "institutional",
  "domicile": "US",
  "account_manager": "Sarah Chen",
  "contact_info": {
    "primary_email": "operations@vanguard.com",
    "primary_phone": "+1-555-0123",
    "emergency_contact": "+1-555-0124"
  },
  "compliance_status": {
    "aml_status": "compliant",
    "fatca_status": "compliant", 
    "last_kyc_review": "2024-03-15",
    "next_review_due": "2025-03-15",
    "w8ben_expiry": "2025-12-31"
  },
  "settlement_preferences": {
    "preferred_currency": "USD",
    "settlement_method": "wire_transfer",
    "standard_settlement_days": 2
  }
}
```

### Collection: drip_positions
**Purpose**: Track dividend reinvestment plan positions and holdings
```json
{
  "_id": "position_001",
  "client_code": "INST-2024-001",
  "fund_name": "Global Equity Fund",
  "fund_isin": "US1234567890",
  "position_details": {
    "total_shares": 125000.75,
    "cost_basis_usd": 2500000.00,
    "current_nav": 22.45,
    "accrued_dividends": 15750.25,
    "reinvestment_frequency": "quarterly"
  },
  "liquidation_instructions": {
    "liquidation_percentage": 25.0,
    "settlement_currency": "EUR",
    "fx_hedge_required": true,
    "tax_lot_method": "FIFO"
  }
}
```

### Collection: compliance_records
**Purpose**: Store compliance verification history and status
```json
{
  "_id": "compliance_001",
  "client_code": "INST-2024-001",
  "compliance_type": "aml_review",
  "review_date": "2024-10-15",
  "status": "compliant",
  "findings": "Annual AML review completed successfully",
  "next_review_date": "2025-10-15",
  "reviewer": "compliance_specialist_001",
  "risk_rating": "low",
  "documentation": [
    "aml_questionnaire_2024.pdf",
    "beneficial_ownership_cert.pdf"
  ]
}
```

## Tool Capabilities by Agent

### AutoAuth Agent Tools
1. **verify_client_identity**: Verify caller identity using personal information
2. **send_mfa_code**: Send multi-factor authentication code via SMS/email
3. **verify_mfa_code**: Validate MFA code entered by client
4. **resend_mfa_code**: Resend MFA code if not received
5. **check_transaction_authorization**: Verify authorization for high-value transactions

### Fraud Agent Tools
1. **analyze_recent_transactions**: Review recent account activity for suspicious patterns
2. **check_suspicious_activity**: Cross-reference against fraud databases and watchlists
3. **create_fraud_case**: Generate formal fraud investigation case with case ID
4. **block_card_emergency**: Immediately block compromised cards or accounts
5. **provide_fraud_education**: Offer guidance on fraud prevention best practices
6. **ship_replacement_card**: Order replacement cards with expedited delivery
7. **send_fraud_case_email**: Send professional case notification emails to clients
8. **create_transaction_dispute**: File formal disputes for unauthorized transactions

### Agency Agent Tools
1. **get_client_data**: Retrieve comprehensive client information from CosmosDB
   - Client profile, contact information, compliance status
   - Account manager details, settlement preferences
   - Historical service interactions and preferences

2. **get_drip_positions**: Fetch dividend reinvestment plan positions
   - Current holdings, share balances, cost basis calculations
   - Accrued dividend amounts, reinvestment schedules
   - NAV pricing, performance metrics

3. **check_compliance_status**: Verify regulatory compliance standing
   - AML/KYC status verification, FATCA compliance checks
   - W-8BEN form expiry monitoring, beneficial ownership verification
   - Risk rating assessment, documentation completeness

4. **calculate_liquidation_proceeds**: Compute liquidation scenarios
   - Gross proceeds calculation with current NAV pricing
   - FX conversion using real-time rates (USD/EUR: 1.0725, USD/GBP: 0.8150)
   - Tax withholding computation (US: 15% dividend, EU: 10% treaty rate)
   - Net settlement amount after fees and taxes

5. **handoff_to_compliance**: Transfer complex cases to compliance specialists
   - AML/FATCA review queue routing
   - Expedited (2-3 min), Priority (5-7 min), Standard (10-15 min) queues
   - Case context preservation and specialist briefing

6. **handoff_to_trading**: Route to trading desk for execution
   - Standard Trading Desk (2-4 min wait), Complex Trades (5-10 min)
   - Institutional Sales Desk (immediate), High Touch Desk (varies)
   - Trade parameters, settlement instructions, FX hedge requirements

### Compliance Agent Tools
- **Inherits all Agency tools for data access**
- **Specialized compliance verification workflows**
- **Regulatory reporting and documentation**
- **Risk assessment and escalation procedures**

### Trading Agent Tools
- **Inherits all Agency tools for position data**
- **Real-time FX rate access and hedging**
- **Trade execution and settlement coordination**
- **Institutional counterparty management**

## FX Rate Management

### Current Rates (Updated Real-time)
```
USD/EUR: 1.0725    USD/GBP: 0.8150    USD/CHF: 0.9050
USD/CAD: 1.3450    USD/JPY: 149.25    USD/AUD: 1.5280
EUR/GBP: 0.7598    EUR/CHF: 0.8437
```

### Rate Lock Options
- **Immediate Lock**: Current market rate with 2-hour validity
- **Market Close Lock**: Rate fixed at 4:00 PM EST for next-day settlement
- **Forward Contracts**: Custom rate locks for future settlement dates

## Fee Structure

### Processing Fees by Settlement Speed
- **Standard Settlement (2-3 days)**: $50.00
- **Priority Settlement (next day)**: $150.00  
- **Expedited Settlement (same day)**: $250.00

### Tax Withholding by Jurisdiction
- **US Clients**: 15% dividend withholding, 20% capital gains
- **EU Treaty Clients**: 10% dividend withholding, 15% capital gains
- **UK Treaty Clients**: 5% dividend withholding, 10% capital gains
- **Non-Treaty**: 30% standard withholding on all distributions

## Example Use Cases and Scenarios

### Scenario 1: DRIP Liquidation Request
**Client**: "I need to liquidate 25% of my Global Equity Fund position and convert to EUR"

**Agent Flow**:
1. **AutoAuth**: Verify identity and send MFA code
2. **Agency**: Retrieve position data showing 125,000.75 shares worth $2.8M
3. **Agency**: Calculate 25% liquidation = 31,250.19 shares = $701,374.25 gross
4. **Agency**: Apply USD/EUR rate (1.0725) = €653,174.31 gross
5. **Agency**: Deduct 10% EU treaty withholding = €587,857.08 net
6. **Trading**: Execute trade with same-day settlement for $250 fee

### Scenario 2: Compliance Review Escalation
**Client**: "My AML documentation is expiring next month, what do I need to provide?"

**Agent Flow**:
1. **AutoAuth**: Identity verification via MFA
2. **Agency**: Check compliance status - AML expires in 30 days
3. **Compliance Handoff**: Route to Priority Compliance Review queue (5-7 min wait)
4. **Compliance**: Review current documentation, identify renewal requirements
5. **Compliance**: Provide checklist of required documents and submission deadlines

### Scenario 3: Fraud Investigation
**Client**: "I see unauthorized transactions on my account totaling $50,000"

**Agent Flow**:
1. **AutoAuth**: Enhanced identity verification for fraud case
2. **Fraud**: Analyze recent 90-day transaction history
3. **Fraud**: Identify 3 suspicious transactions not matching client patterns  
4. **Fraud**: Create case FR-2024-10-001 with provisional credit authorization
5. **Fraud**: Block compromised access methods, order replacement credentials
6. **Fraud**: Send professional case email with 5-7 business day investigation timeline

### Scenario 4: Complex Multi-Currency Settlement
**Client**: "Liquidate my entire European equity position, hedge 50% to GBP, 50% to CHF"

**Agent Flow**:
1. **AutoAuth**: Multi-factor authentication for high-value transaction
2. **Agency**: Retrieve €2.5M position across 5 European equity funds
3. **Agency**: Calculate gross proceeds, identify tax implications across jurisdictions
4. **Trading Handoff**: Route to Complex Trades desk (5-10 min queue)
5. **Trading**: Structure FX hedges - 50% EUR/GBP (0.7598), 50% EUR/CHF (0.8437)
6. **Trading**: Execute coordinated liquidation with currency hedging
7. **Trading**: Confirm settlement: £949,750 + CHF 1,054,625 net of fees

## System Capabilities Summary

### Real-time Processing
- Voice-to-text transcription with Azure Speech Services (< 500ms latency)
- Immediate MFA code delivery via SMS/email (< 30s delivery)
- Real-time FX rate updates and trade execution (sub-second pricing)
- Sub-second database queries across all collections (< 100ms average)

### Data Integration
- CosmosDB collections for client data, positions, compliance records
- 360-degree client intelligence with relationship context
- Historical interaction patterns and preference learning
- Cross-reference fraud databases and regulatory watchlists

### Regulatory Compliance
- Automated AML/KYC status monitoring with 30-day expiry alerts
- FATCA compliance verification workflows with annual reviews
- W-8BEN form expiry tracking and renewal alerts (60-day notice)
- Beneficial ownership certification management and audit trails

### Multi-Currency Operations
- 8 major currency pairs with real-time rates (updated every 15 seconds)
- Forward contract and hedge management with institutional counterparties
- Multi-jurisdiction tax withholding calculation (US: 15%, EU: 10%, UK: 5%)
- Cross-border settlement coordination with same-day execution

### Advanced Features
- Intelligent agent handoff with context preservation and conversation history
- Queue management with SLA-based routing (2-15 minute guarantees)
- Professional email template generation with institutional branding
- Audit trail maintenance for regulatory reporting and compliance verification
