# Scenario System - Architecture Flow

## Overview
Industry-specific scenario selection via query parameter, integrated with orchestrator.

## End-to-End Flow

### 1. **UI → Backend (Query Parameter)**
```javascript
// User clicks "Banking" tab in UI
ws = new WebSocket('ws://localhost:8000/api/v1/browser/conversation?scenario=banking');
```

### 2. **WebSocket Handler** (`browser.py`)
```python
@router.websocket("/conversation")
async def browser_conversation_endpoint(
    websocket: WebSocket,
    scenario: str | None = Query(None),  # ← Scenario from query param
):
    # Create handler config with scenario
    config = MediaHandlerConfig(
        session_id=session_id,
        websocket=websocket,
        scenario=scenario,  # ← Pass to handler
    )
    handler = await MediaHandler.create(config, websocket.app.state)
```

### 3. **MediaHandler** (`media_handler.py`)
```python
@classmethod
async def create(cls, config: MediaHandlerConfig, app_state):
    memory_manager = cls._load_memory_manager(...)
    
    # Store scenario in session memory
    if config.scenario:
        memory_manager.set_corememory("scenario_name", config.scenario)  # ← Persist
    
    # MediaHandler wraps SpeechCascadeHandler
    # which calls route_turn() for orchestration
```

### 4. **Unified Orchestrator** (`unified/__init__.py`)
```python
async def route_turn(cm: MemoManager, transcript: str, ws: WebSocket):
    # Get or create orchestrator adapter
    adapter = _get_or_create_adapter(
        session_id=session_id,
        call_connection_id=call_connection_id,
        app_state=ws.app.state,
        memo_manager=cm,  # ← Contains scenario_name
    )
    
def _get_or_create_adapter(..., memo_manager: MemoManager | None = None):
    if session_id in _adapters:
        return _adapters[session_id]  # Already created
    
    # Get scenario from memory
    scenario_name = None
    if memo_manager:
        scenario_name = memo_manager.get_value_from_corememory("scenario_name", None)
    
    # Create adapter with scenario
    adapter = get_cascade_orchestrator(
        app_state=app_state,
        call_connection_id=call_connection_id,
        session_id=session_id,
        scenario_name=scenario_name,  # ← Pass to orchestrator
    )
```

### 5. **Cascade Orchestrator** (`speech_cascade/orchestrator.py`)
```python
def get_cascade_orchestrator(..., scenario_name: str | None = None):
    \"\"\"Create orchestrator with scenario-filtered agents.\"\"\"
    
    # Load agents based on scenario
    if scenario_name:
        from apps.artagent.backend.registries.scenariostore import get_scenario_agents
        agents = get_scenario_agents(scenario_name)  # ← Filtered by scenario
    else:
        agents = discover_agents()  # All agents
    
    # Build config
    config = CascadeConfig(
        start_agent=start_agent,
        call_connection_id=call_connection_id,
        session_id=session_id,
    )
    
    # Create adapter
    adapter = CascadeOrchestratorAdapter(
        config=config,
        agents={a.name: a for a in agents},  # ← Scenario-filtered agents
    )
    
    return adapter
```

### 6. **Scenario Loader** (`scenariostore/loader.py`)
```python
def get_scenario_agents(scenario_name: str):
    \"\"\"Load agents for specific scenario with overrides applied.\"\"\"
    scenario = load_scenario(scenario_name)
    
    # Load base agents
    base_agents = discover_agents()
    
    # Filter to scenario agents (if specified)
    if scenario.agents:
        agents = {name: base_agents[name] for name in scenario.agents}
    else:
        agents = base_agents  # All agents
    
    # Apply scenario overrides
    for agent_name, override in scenario.agent_overrides.items():
        agent = agents[agent_name]
        if override.greeting:
            agent.greeting = override.greeting
        if override.add_tools:
            agent.tools.extend(override.add_tools)
    
    return list(agents.values())
```

## Scenario YAML Structure

```yaml
# registries/scenariostore/banking/scenario.yaml
name: banking
description: Private banking customer service
start_agent: concierge

# Agents to include (empty = all)
agents:
  - concierge
  - auth_agent
  - investment_advisor
  - card_recommendation

# Agent overrides
agent_overrides:
  concierge:
    greeting: "Welcome to Private Banking. How may I help you?"
    add_tools:
      - customer_intelligence
      - personalized_greeting
    template_vars:
      bank_name: "Private Banking"
  
  investment_advisor:
    add_tools:
      - get_portfolio_summary
    template_vars:
      compliance_mode: true

# Global variables (all agents)
template_vars:
  company_name: "Private Banking"
  industry: "banking"
```

## Session Lifecycle

```
1. WebSocket connects with ?scenario=banking
2. MediaHandler.create() stores "scenario_name" in MemoManager
3. First turn: route_turn() creates adapter with scenario
4. get_cascade_orchestrator() loads banking agents only
5. All subsequent turns use same adapter (same agents)
6. Scenario persists for entire session
```

## Key Design Decisions

### ✅ Session-Based (Not Global)
- Each WebSocket connection has its own scenario
- Multiple concurrent sessions can use different scenarios
- No interference between sessions

### ✅ Stored in MemoManager
- Scenario persists in Redis-backed session state
- Survives network reconnects (if using same session_id)
- Available to all orchestrator code

### ✅ Lazy Adapter Creation
- Adapter created on first turn (not connection)
- Allows session agent injection before first turn
- Reduces connection overhead

### ✅ Backward Compatible
- No scenario = all agents (current behavior)
- `AGENT_SCENARIO` env var still works (global default)
- Existing endpoints unchanged

## Testing

### Test Scenario Loading
```bash
curl http://localhost:8000/api/v1/scenarios
```

### Test Browser Connection
```javascript
// Default (all agents)
ws = new WebSocket('ws://localhost:8000/api/v1/browser/conversation');

// Banking scenario
ws = new WebSocket('ws://localhost:8000/api/v1/browser/conversation?scenario=banking');
```

### Verify in Logs
```
INFO: Loaded scenario: banking
INFO: Session initialized with start agent: concierge
INFO: Agent count: 6
```

## Adding New Scenarios

1. **Create scenario directory:**
   ```bash
   mkdir registries/scenariostore/healthcare
   ```

2. **Create `scenario.yaml`:**
   ```yaml
   name: healthcare
   description: HIPAA-compliant healthcare support
   start_agent: triage_agent
   agents:
     - triage_agent
     - auth_agent
     - appointment_agent
   ```

3. **Test:**
   ```bash
   curl http://localhost:8000/api/v1/scenarios/healthcare
   ```

4. **Use in UI:**
   ```javascript
   ws = new WebSocket('ws://...?scenario=healthcare');
   ```

## Phone (ACS) Support

For ACS phone calls, scenario will come from:
1. Custom SIP header (future)
2. Call context metadata (future)
3. `AGENT_SCENARIO` env var (current default)

Phone implementation is Phase 2 - UI is Phase 1 (complete).
