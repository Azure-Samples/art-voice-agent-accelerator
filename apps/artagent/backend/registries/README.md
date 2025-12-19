# Registries

Agent, tool, and scenario registration system.

## Structure

```
registries/
├── agentstore/          # Agent definitions (YAML)
│   ├── base.py          # BaseAgent class
│   ├── loader.py        # discover_agents(), build_handoff_map()
│   └── session_manager.py  # Session-level agent state
│
├── toolstore/           # Tool registry
│   ├── registry.py      # @register_tool decorator
│   ├── banking.py       # Banking tools
│   └── *.py             # Domain-specific tools
│
└── scenariostore/       # Industry scenarios
    ├── loader.py        # load_scenario()
    └── banking/         # Banking configs
```

## Usage

### Agents
```python
from apps.artagent.backend.registries.agentstore import discover_agents, build_handoff_map

agents = discover_agents()  # Load all YAML agents
handoffs = build_handoff_map(agents)  # Build routing map
```

### Tools
```python
from apps.artagent.backend.registries.toolstore.registry import register_tool

@register_tool(name="check_balance", description="Check account balance")
async def check_balance(account_id: str) -> dict:
    return {"balance": 1000.00}
```

### Scenarios
```python
from apps.artagent.backend.registries.scenariostore import load_scenario, get_scenario_agents

scenario = load_scenario("banking_customer_service")
agents = get_scenario_agents("banking_customer_service")
```

## How It Works

### 1. Agent Discovery
- Scans `agentstore/` for YAML files
- Loads agent config (prompts, tools, handoffs)
- Builds handoff map for agent routing

### 2. Tool Registration
- `@register_tool()` decorator registers tools
- Auto-generates schema from function signature
- Tools referenced by name in agent YAML

### 3. Scenario Loading
- Industry-specific agent configurations
- YAML-based scenario definitions
- Override default agent settings

## Troubleshooting

### Agent Not Found
```python
agents = discover_agents()
print([a.name for a in agents])
```

### Tool Not Registered
```python
from apps.artagent.backend.registries.toolstore.registry import list_tools
print(list_tools())
```

### Import Errors
Use new paths:
```python
# ✅ Correct
from apps.artagent.backend.registries.agentstore import discover_agents

# ❌ Old
from apps.artagent.backend.agents_store import discover_agents
```

## Migration

| Old Path | New Path |
|----------|----------|
| `agents_store.*` | `registries.agentstore.*` |
| `tools_store.*` | `registries.toolstore.*` |
| `scenarios_store.*` | `registries.scenariostore.*` |
