# Card API - Updated Schema Reference

## Quick API Usage Examples

### Get a Decline Code by ID

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/codes/51" \
  -H "Content-Type: application/json"
```

**Response (with policy pack data):**
```json
{
  "code": "51",
  "description": "Insufficient funds",
  "information": "Account does not have available funds.",
  "actions": [
    "Transfer funds if applicable",
    "Use another payment method"
  ],
  "code_type": "numeric",
  "script_refs": ["insufficient_funds_handling"],
  "orchestrator_actions": ["SUGGEST_TRANSFER", "CHECK_LINKED_ACCOUNTS"],
  "contextual_rules": null,
  "escalation": {
    "required": false,
    "target": null
  }
}
```

### Get All Codes by Type

**Request (Numeric codes only):**
```bash
curl -X GET "http://localhost:8000/api/v1/codes?code_type=numeric" \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "codes": [
    {
      "code": "02",
      "description": "Personal identification number (PIN) translation error",
      "information": "PIN did not translate. Suggest the client retry the transaction.",
      "actions": ["Retry transaction"],
      "code_type": "numeric",
      "script_refs": null,
      "orchestrator_actions": null,
      "contextual_rules": null,
      "escalation": null
    },
    ...
  ],
  "total": 45
}
```

### Search for Codes

**Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/search?q=expired&code_type=numeric" \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "codes": [
    {
      "code": "33",
      "description": "Expired card",
      "information": "Card is expired. If using digital wallet, delete then re-add the active debit card.",
      "actions": [
        "Replace card",
        "Use another payment method",
        "Re-add to digital wallet"
      ],
      "code_type": "numeric",
      "script_refs": ["expired_card_explain_and_offer_reissue"],
      "orchestrator_actions": ["ORDER_REPLACEMENT_CARD", "OFFER_DIGITAL_INSTANT_ISSUANCE"],
      "contextual_rules": [
        {
          "if_condition": {
            "isDigitalWallet": true
          },
          "add_script_refs": ["wallet_delete_readd_tip"],
          "escalation": null,
          "orchestrator_actions": null
        },
        {
          "if_condition": {
            "blockedStatusIn": ["Fraud", "Base24 Velocity", "AML"]
          },
          "add_script_refs": null,
          "escalation": {
            "required": true,
            "target": "FRAUD_SERVICING"
          },
          "orchestrator_actions": null
        }
      ],
      "escalation": {
        "required": false,
        "target": null
      }
    }
  ],
  "total": 1
}
```

### Handling Escalation Rules

When a decline code has `escalation.required = true`, your agent should:

```python
def handle_decline_code(decline_code_policy):
    # Get the code info
    code = decline_code_policy['code']
    description = decline_code_policy['description']
    
    # Check if escalation is required
    escalation = decline_code_policy.get('escalation', {})
    if escalation.get('required', False):
        target = escalation.get('target')
        print(f"Escalate to {target}")
        # Route to appropriate department:
        # - FRAUD_SERVICING: Fraud team
        # - LOAN_LOC_SERVICE_CENTER: Loan/LOC specialists
        # - AML_OPERATIONS: AML compliance
        # - etc.
    
    # Get script references for customer service
    script_refs = decline_code_policy.get('script_refs', [])
    print(f"Use scripts: {script_refs}")
    
    # Get orchestrator actions for voice agent
    orchestrator_actions = decline_code_policy.get('orchestrator_actions', [])
    for action in orchestrator_actions:
        execute_action(action)
    
    # Apply contextual rules
    contextual_rules = decline_code_policy.get('contextual_rules', [])
    for rule in contextual_rules:
        if check_context(rule['if_condition']):
            apply_rule(rule)
```

## New Fields Explained

### `script_refs` (List[str])
References to customer service scripts for handling this decline code.

**Example values:**
- `expired_card_explain_and_offer_reissue`
- `insufficient_funds_handling`
- `fraud_alert_block_removed_thanks`
- `invalid_pin_options`

### `orchestrator_actions` (List[str])
Actions the voice agent orchestrator should execute.

**Example values:**
- `ORDER_REPLACEMENT_CARD` - Initiate card replacement
- `OFFER_DIGITAL_INSTANT_ISSUANCE` - Offer instant digital card
- `SUGGEST_TRANSFER` - Suggest fund transfer
- `OFFER_ATM_LOCATOR` - Offer ATM location service
- `CHANGE_LINKAGE` - Help change account linkage
- `OFFER_INDIVIDUALIZED_LIMITS` - Offer custom limits

### `contextual_rules` (List[ContextualRule])
Conditional rules that override actions based on context.

**Structure:**
```json
{
  "if_condition": {
    "key": "value"  // Arbitrary condition object
  },
  "add_script_refs": ["script1", "script2"],  // Optional
  "escalation": {                              // Optional
    "required": true,
    "target": "FRAUD_SERVICING"
  },
  "orchestrator_actions": ["ACTION1"]          // Optional
}
```

### `escalation` (EscalationConfig)
Escalation requirements for this decline code.

**Fields:**
- `required` (bool): Whether escalation to human agent is required
- `target` (Optional[str]): Target department for escalation

**Valid targets:**
- `FRAUD_SERVICING` - Fraud detection and servicing
- `LOAN_LOC_SERVICE_CENTER` - Loan/Line of Credit services
- `AML_OPERATIONS` - Anti-Money Laundering compliance
- `CONSUMER_AML_OPERATIONS` - Consumer-facing AML operations
- `RECOVERY_SERVICES` - Debt recovery services

## Filtering and Search

### By Code Type

```bash
# Numeric codes (Base24)
curl http://localhost:8000/api/v1/codes?code_type=numeric

# Alphanumeric codes (FAST)
curl http://localhost:8000/api/v1/codes?code_type=alphanumeric

# All codes (default)
curl http://localhost:8000/api/v1/codes
```

### By Description/Keywords

```bash
# Search for "insufficient"
curl http://localhost:8000/api/v1/search?q=insufficient

# Search with type filter
curl http://localhost:8000/api/v1/search?q=card&code_type=alphanumeric
```

## Integration with Voice Agents

When integrating with the voice agent orchestrator:

```python
from fastapi import HTTPException
import httpx

class CardDeclineHandler:
    def __init__(self, cardapi_url: str = "http://localhost:8000"):
        self.cardapi_url = cardapi_url
    
    async def get_decline_policy(self, code: str) -> dict:
        """Fetch decline code policy pack data."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.cardapi_url}/api/v1/codes/{code}"
            )
            if response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Decline code {code} not found"
                )
            return response.json()
    
    async def handle_decline(self, code: str, context: dict) -> dict:
        """Handle decline code with full policy context."""
        policy = await self.get_decline_policy(code)
        
        return {
            "code": policy["code"],
            "customer_message": policy["information"],
            "recommended_actions": policy["actions"],
            "scripts": policy.get("script_refs", []),
            "orchestrator_actions": policy.get("orchestrator_actions", []),
            "requires_escalation": policy.get("escalation", {}).get("required", False),
            "escalation_target": policy.get("escalation", {}).get("target"),
            "contextual_rules": self._apply_rules(
                policy.get("contextual_rules", []),
                context
            )
        }
    
    def _apply_rules(self, rules: list, context: dict) -> list:
        """Apply contextual rules based on current context."""
        applied = []
        for rule in rules:
            if self._matches_condition(rule["if_condition"], context):
                applied.append(rule)
        return applied
    
    def _matches_condition(self, condition: dict, context: dict) -> bool:
        """Check if condition matches context."""
        # Simple implementation - can be extended
        for key, value in condition.items():
            if context.get(key) != value:
                return False
        return True
```

## Error Responses

All endpoints follow standard HTTP error codes:

```json
{
  "detail": "Error message"
}
```

**Common status codes:**
- `200`: Success
- `400`: Bad request (invalid parameters)
- `404`: Decline code not found
- `503`: Database not initialized (Cosmos DB connection failed)
- `500`: Internal server error
