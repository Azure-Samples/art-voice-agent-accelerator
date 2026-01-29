# MCP Server Updates - Script Resolution Support

## Overview
The MCP server has been updated to surface the new policy pack data including resolved scripts, orchestrator actions, contextual rules, and escalation information.

## Changes Made

### 1. Updated Tool Descriptions

**`lookup_decline_code`** - Now mentions that it returns:
- Customer service scripts (with resolved content)
- Orchestrator actions
- Contextual rules
- Escalation requirements

**`search_decline_codes`** - Now mentions it returns complete policy pack data including scripts, orchestrator actions, and escalation info

**`get_all_decline_codes`** - Now mentions it returns complete policy pack data

### 2. Enhanced Response Formatting

The `lookup_decline_code` method now includes:

```python
# Orchestrator Actions
if data.get('orchestrator_actions'):
    result += "\n\n**Orchestrator Actions:**"
    for action in data['orchestrator_actions']:
        result += f"\n- {action}"

# Customer Service Scripts (Resolved)
if data.get('scripts'):
    result += "\n\n**Customer Service Scripts:**"
    for script in data['scripts']:
        result += f"\n\n**{script['title']}** (Ref: {script['ref']})"
        if script.get('channels'):
            result += f"\n- Channels: {', '.join(script['channels'])}"
        result += f"\n- Script: {script['text']}"
        if script.get('notes'):
            result += f"\n- Notes: {script['notes']}"

# Contextual Rules
if data.get('contextual_rules'):
    result += "\n\n**Contextual Rules:**"
    for i, rule in enumerate(data['contextual_rules'], 1):
        result += f"\n\n{i}. **Condition:** {rule.get('if', {})}"
        if rule.get('add_scripts'):
            result += "\n   **Additional Scripts:**"
            for script in rule['add_scripts']:
                result += f"\n   - {script['title']}: {script['text']}"
        if rule.get('escalation'):
            esc = rule['escalation']
            if esc.get('required'):
                result += f"\n   **Escalation Required:** {esc.get('target', 'Yes')}"
        if rule.get('orchestrator_actions'):
            result += f"\n   **Actions:** {', '.join(rule['orchestrator_actions'])}"

# Escalation Information
if data.get('escalation'):
    esc = data['escalation']
    if esc.get('required'):
        result += f"\n\n**Escalation Required:** {esc.get('target', 'Yes')}"
    elif esc.get('target'):
        result += f"\n\n**Escalation Target:** {esc['target']}"
```

## Example MCP Tool Response

When an AI agent calls `lookup_decline_code` with code "33", it will now receive:

```
**Decline Code: 33** (numeric)

**Description:** Expired card

**Information:** Card is expired. If using digital wallet, delete then re-add the active debit card.

**Recommended Actions:**
- Replace card
- Use another payment method
- Re-add to digital wallet

**Orchestrator Actions:**
- ORDER_REPLACEMENT_CARD
- OFFER_DIGITAL_INSTANT_ISSUANCE

**Customer Service Scripts:**

**Expired Card - Explain & Offer Reissue** (Ref: expired_card_explain_and_offer_reissue)
- Channels: chat, voice, sms
- Script: Your debit card ending in {{last4}} is expired{{expiry_suffix}} which caused the decline. I can order your replacement card now. While waiting, please use another payment method.
- Notes: Synthesized from Job Aid actions; {{expiry_suffix}} may be formatted like ' ({{expiryMMYY}})'.

**Contextual Rules:**

1. **Condition:** {'isDigitalWallet': True}
   **Additional Scripts:**
   - Wallet - Delete & Re-add: If you use a mobile wallet, after you receive and activate the new card, please delete the old card from the wallet and re-add the new card to ensure payments work.

2. **Condition:** {'blockedStatusIn': ['Fraud', 'Base24 Velocity', 'AML']}
   **Escalation Required:** FRAUD_SERVICING
```

## Benefits for AI Agents

1. **Direct Script Access** - Agents get full script text without needing separate lookups
2. **Action Guidance** - Clear orchestrator actions help agents know what operations to trigger
3. **Contextual Awareness** - Conditional rules help agents adapt responses based on context
4. **Escalation Clarity** - Clear indication when human intervention is required
5. **Template Variables** - Script text includes placeholders ({{last4}}, {{expiryMMYY}}) for dynamic insertion

## Files Modified

✅ [apps/cardapi/mcp_app/service.py](apps/cardapi/mcp_app/service.py) - Enhanced tool descriptions and response formatting

## Testing

The MCP server can be tested using standard MCP tooling or by running the service and observing the formatted responses.

```bash
# Start the MCP server
cd apps/cardapi
python mcp_app/service.py
```

The server will now return enriched responses with all policy pack data including resolved scripts.
