# Financial Services Multi-Agent System - Technical Implementation Guide

## Orchestrator Flow Logic

### Entry Point Authentication
```python
# All calls start with AutoAuth agent for identity verification
if not cm_get(cm, "authenticated", False):
    cm_set(cm, active_agent="AutoAuth")
    # AutoAuth uses MFA tools: send_mfa_code, verify_mfa_code, verify_client_identity
```

### Post-Authentication Routing
```python
# Financial Services handoff processing in tools.py
if handoff_type in ["Transfer", "Fraud", "Compliance", "Trading"]:
    handoff_to_agent_map = {
        "Transfer": "Agency",        # Transfer Agency coordinator
        "Fraud": "Fraud",           # Fraud detection specialist  
        "Compliance": "Compliance", # AML/FATCA specialist
        "Trading": "Trading"        # Trade execution specialist
    }
    
    new_agent = handoff_to_agent_map.get(handoff_type, target_agent)
    cm_set(cm, active_agent=new_agent)
    await send_agent_greeting(cm, ws, new_agent, is_acs)
```

## Agent Tool Registration

### Complete Tool Registry
```python
# From tool_registry.py - All available tools
TOOL_REGISTRY = {
    # Authentication & MFA
    "verify_client_identity": verify_client_identity,
    "send_mfa_code": send_mfa_code,
    "verify_mfa_code": verify_mfa_code,
    "resend_mfa_code": resend_mfa_code,
    "check_transaction_authorization": check_transaction_authorization,
    
    # Fraud Detection (8 tools)
    "analyze_recent_transactions": analyze_recent_transactions,
    "check_suspicious_activity": check_suspicious_activity,
    "create_fraud_case": create_fraud_case,
    "block_card_emergency": block_card_emergency,
    "provide_fraud_education": provide_fraud_education,
    "ship_replacement_card": ship_replacement_card,
    "send_fraud_case_email": send_fraud_case_email,
    "create_transaction_dispute": create_transaction_dispute,
    
    # Transfer Agency (6 tools)
    "get_client_data": get_client_data,
    "get_drip_positions": get_drip_positions,
    "check_compliance_status": check_compliance_status,
    "calculate_liquidation_proceeds": calculate_liquidation_proceeds,
    "handoff_to_compliance": handoff_to_compliance,
    "handoff_to_trading": handoff_to_trading,
    
    # Emergency & Escalation
    "escalate_emergency": escalate_emergency,
    "escalate_human": escalate_human,
    "handoff_fraud_agent": handoff_fraud_agent,
    "handoff_transfer_agency_agent": handoff_transfer_agency_agent,
}
```

## Database Schema Implementation

### CosmosDB Collection Structure
```python
# Database configuration
DATABASE_NAME = "financial_services_db"
COLLECTIONS = [
    "transfer_agency_clients",    # Client master data
    "drip_positions",            # Investment positions
    "compliance_records"         # Compliance verification history
]

# Collection manager instantiation
def get_ta_collection_manager(collection_name: str) -> CosmosDBMongoCoreManager:
    return CosmosDBMongoCoreManager(
        database_name=DATABASE_NAME,
        collection_name=collection_name
    )
```

### Tool-Database Integration Pattern
```python
# Example: get_client_data implementation
def get_client_data(args: GetClientDataArgs) -> Dict[str, Any]:
    try:
        # Get client collection manager
        client_mgr = get_ta_collection_manager("transfer_agency_clients")
        
        # Query database with client_code
        query = {"client_code": args.client_code}
        client_doc = client_mgr.find_one(query)
        
        if not client_doc:
            return {"success": False, "message": f"Client {args.client_code} not found"}
        
        # Extract and format client information
        return {
            "success": True,
            "client_data": {
                "client_code": client_doc["client_code"],
                "client_name": client_doc["client_name"],
                "client_type": client_doc["client_type"],
                "domicile": client_doc["domicile"],
                "account_manager": client_doc["account_manager"],
                "contact_info": client_doc["contact_info"],
                "compliance_status": client_doc["compliance_status"],
                "settlement_preferences": client_doc["settlement_preferences"]
            }
        }
    except Exception as e:
        return {"success": False, "message": f"Database error: {str(e)}"}
```

## Agent Handoff Mechanisms

### Internal Agent Handoffs (Transfer Agency Tools)
```python
# handoff_to_compliance implementation
def handoff_to_compliance(args: HandoffComplianceArgs) -> Dict[str, Any]:
    # Generate unique handoff ID
    handoff_id = f"COMP-{uuid.uuid4().hex[:8].upper()}"
    
    # Get queue information from constants
    queue_info = get_specialist_queue_info("compliance", args.urgency)
    
    # Return orchestrator-compatible handoff format
    return {
        "success": True,
        "message": f"Transferring {args.client_name} to compliance specialist",
        "handoff": "Compliance",           # Triggers orchestrator routing
        "target_agent": "Compliance",      # Target agent name
        "handoff_id": handoff_id,
        "specialist_queue": queue_info["queue_name"],
        "estimated_wait": queue_info["wait_time"],
        "client_name": args.client_name,
        "compliance_issue": args.compliance_issue,
        "urgency": args.urgency
    }
```

### External Agent Handoffs (Main Handoff Tools)
```python
# handoff_fraud_agent implementation  
async def handoff_fraud_agent(args: HandoffFraudArgs) -> Dict[str, Any]:
    return {
        "success": True,
        "message": "Caller transferred to Fraud Detection specialist.",
        "handoff": "Fraud",                # Maps to orchestrator routing
        "target_agent": "Fraud Detection",
        "caller_name": args.caller_name,
        "client_id": args.client_id,
        "institution_name": args.institution_name,
        "service_type": args.service_type
    }
```

## Constants and Configuration Management

### FX Rate Implementation
```python
# Real-time FX rates with helper functions
CURRENT_FX_RATES = {
    "USD_EUR": 1.0725,
    "USD_GBP": 0.8150,
    "USD_CHF": 0.9050,
    "USD_CAD": 1.3450,
    "USD_JPY": 149.25,
    "USD_AUD": 1.5280,
    "EUR_GBP": 0.7598,
    "EUR_CHF": 0.8437,
    "last_updated": "2025-10-27T09:00:00Z"
}

def get_fx_rate(from_currency: str, to_currency: str) -> float:
    """Get FX rate between two currencies"""
    if from_currency == to_currency:
        return 1.0
    
    rate_key = f"{from_currency}_{to_currency}"
    if rate_key in CURRENT_FX_RATES:
        return CURRENT_FX_RATES[rate_key]
    
    # Try inverse rate
    inverse_key = f"{to_currency}_{from_currency}"
    if inverse_key in CURRENT_FX_RATES:
        return 1.0 / CURRENT_FX_RATES[inverse_key]
    
    return 0.0  # Rate not available
```

### Queue Management System
```python
# Specialist queue configuration
SPECIALIST_QUEUES = {
    "compliance": {
        "expedited": {"queue_name": "Expedited Compliance Review", "wait_time": "2-3 minutes"},
        "high": {"queue_name": "Priority Compliance Review", "wait_time": "5-7 minutes"},
        "normal": {"queue_name": "Standard Compliance Review", "wait_time": "10-15 minutes"}
    },
    "trading": {
        "institutional": {"queue_name": "Institutional Sales Desk", "wait_time": "immediate"},
        "complex": {"queue_name": "Complex Trades Desk", "wait_time": "5-10 minutes"},
        "standard": {"queue_name": "Standard Trading Desk", "wait_time": "2-4 minutes"}
    }
}

def get_specialist_queue_info(specialist_type: str, priority_level: str) -> Dict[str, str]:
    """Get queue information for specialist routing"""
    return SPECIALIST_QUEUES.get(specialist_type, {}).get(
        priority_level, 
        {"queue_name": "General Queue", "wait_time": "5-10 minutes"}
    )
```

## Greeting System Implementation

### Agent Identification for Greetings
```python
# From greetings.py - Agent name mapping for professional greetings
def get_agent_display_name(agent_name: str) -> str:
    agent_name_map = {
        "Fraud": "Fraud Specialist",
        "Agency": "Transfer Agency Specialist", 
        "Compliance": "Compliance Specialist",
        "Trading": "Trading Specialist"
    }
    return agent_name_map.get(agent_name, agent_name)
```

### Personalized Greeting Generation
```python
# Ultra-personalized greeting using 360° customer intelligence
def create_personalized_greeting(
    caller_name: Optional[str],
    agent_name: str,
    customer_intelligence: Dict[str, Any], 
    institution_name: str,
    topic: str
) -> str:
    
    # Extract intelligence data
    relationship_context = customer_intelligence.get("relationship_context", {})
    account_status = customer_intelligence.get("account_status", {})
    
    # Create contextual greeting
    first_name = caller_name.split()[0] if caller_name else "there"
    agent_display = get_agent_display_name(agent_name)
    
    if relationship_context.get("tenure_years", 0) > 5:
        return f"Hello {first_name}, this is {agent_display}. As a valued long-term client, I'm here to provide you with priority service today."
    else:
        return f"Hello {first_name}, this is {agent_display}. I'm here to assist you with your {topic} inquiry today."
```

## Agent Specialist Implementation

### Shared Specialist Runner Pattern
```python
# All financial agents use this shared pattern
async def _run_specialist_base(
    *,
    agent_key: str,                    # "Fraud", "Agency", "Compliance", "Trading"
    cm: "MemoManager",                 # Conversation memory
    utterance: str,                    # Client input
    ws: WebSocket,                     # WebSocket connection
    is_acs: bool,                      # Azure Communication Services flag
    context_message: str,              # Agent context for logging
    respond_kwargs: Dict[str, Any],    # Agent-specific parameters
    latency_label: str,                # Performance tracking label
) -> None:
    
    # Get agent instance from bindings
    agent = get_agent_instance(ws, agent_key)
    
    # Add context to conversation history
    cm.append_to_history(agent.name, "assistant", context_message)
    
    # Execute agent with latency tracking
    async with track_latency(ws.state.lt, latency_label, ws.app.state.redis):
        resp = await agent.respond(cm, utterance, ws, is_acs=is_acs, **respond_kwargs)
    
    # Process tool responses and handle handoffs
    await process_tool_response(cm, resp, ws, is_acs)
```

### Agency Agent Implementation
```python
async def run_agency_agent(cm: "MemoManager", utterance: str, ws: WebSocket, *, is_acs: bool) -> None:
    """Handle Transfer Agency coordination - DRIP liquidations, compliance, and specialist delegation."""
    
    # Extract authenticated client context
    caller_name = cm_get(cm, "caller_name")
    client_id = cm_get(cm, "client_id")
    institution_name = cm_get(cm, "institution_name")
    customer_intelligence = cm_get(cm, "customer_intelligence") or {}
    
    # Create context message for logging
    context_msg = f"Transfer Agency Agent serving {caller_name or 'client'}"
    if institution_name:
        context_msg += f" from {institution_name}"
    context_msg += " for DRIP liquidations and institutional services."
    
    # Execute with shared pattern
    await _run_specialist_base(
        agent_key="Agency",
        cm=cm,
        utterance=utterance,
        ws=ws,
        is_acs=is_acs,
        context_message=context_msg,
        respond_kwargs={
            "caller_name": caller_name,
            "client_id": client_id,
            "institution_name": institution_name,
            "customer_intelligence": customer_intelligence,
        },
        latency_label="agency_agent",
    )
```

## Error Handling and Logging

### Database Error Patterns
```python
# Consistent error handling across all tools
def safe_database_operation(operation_func, *args, **kwargs):
    try:
        return operation_func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Database operation failed: {str(e)}", exc_info=True)
        return {"success": False, "message": f"Database error: {str(e)}"}
```

### Structured Logging
```python
# Financial services specific logging with correlation IDs
logger.info(
    "Financial Services Hand-off → %s (type: %s)", 
    new_agent, 
    handoff_type,
    extra={
        "correlation_id": cm_get(cm, "correlation_id"),
        "client_id": cm_get(cm, "client_id"),
        "agent_transition": f"{prev_agent} -> {new_agent}",
        "handoff_type": handoff_type
    }
)
```

## Performance and Scalability

### Latency Tracking
```python
# All agent operations are tracked for performance monitoring
async with track_latency(ws.state.lt, latency_label, ws.app.state.redis, meta={"agent": agent_key}):
    resp = await agent.respond(cm, utterance, ws, is_acs=is_acs, **respond_kwargs)
```

### Database Connection Pooling
```python
# CosmosDBMongoCoreManager handles connection pooling internally
# Multiple collection managers can be instantiated without connection overhead
client_mgr = get_ta_collection_manager("transfer_agency_clients")
position_mgr = get_ta_collection_manager("drip_positions") 
compliance_mgr = get_ta_collection_manager("compliance_records")
```
