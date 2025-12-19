# ARTVoice Backend

FastAPI backend for real-time voice AI via Azure Communication Services.

## Architecture

```
Phone → ACS → WebSocket → STT → Multi-Agent AI → TTS → Audio
```

## Structure

```
backend/
├── main.py              # FastAPI app + startup
├── api/v1/              # REST + WebSocket endpoints
├── voice/               # Voice orchestration (SpeechCascade, VoiceLive)
├── registries/          # Agent, tool, scenario registration
└── config/              # Settings and feature flags
```

## Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/api/v1/media/stream` | ACS media streaming WebSocket |
| `/api/v1/realtime/conversation` | Real-time voice WebSocket |
| `/api/v1/calls/*` | Call management |
| `/health` | Health check |

## Core Folders

### `registries/` - Agent, Tool, Scenario System
```
registries/
├── agentstore/          # Agent definitions (YAML-based)
├── toolstore/           # Tool registry (@register_tool)
└── scenariostore/       # Industry scenarios (banking, etc.)
```

**Usage:**
```python
from apps.artagent.backend.registries.agentstore import discover_agents
from apps.artagent.backend.registries.toolstore import register_tool
from apps.artagent.backend.registries.scenariostore import load_scenario
```

See [`registries/README.md`](./registries/README.md) for details.

### `voice/` - Voice Orchestration
```
voice/
├── speech_cascade/      # Custom STT/TTS pipeline orchestrator
├── voicelive/           # Azure OpenAI Realtime API orchestrator
└── handoffs/            # Agent handoff logic
```

Two orchestration paths:
- **SpeechCascade**: Custom pipeline (Azure Speech STT → AOAI → Azure Speech TTS)
- **VoiceLive**: Managed API (Azure OpenAI Realtime with built-in voice)

### `api/v1/` - HTTP + WebSocket APIs
```
api/v1/
├── endpoints/
│   ├── calls.py         # ACS call management
│   ├── media.py         # Media streaming handler
│   ├── realtime.py      # Real-time voice handler
│   └── health.py        # Health checks
└── schemas/             # Pydantic request/response models
```

### `config/` - Configuration
```
config/
├── app_config.py        # Main app settings
├── app_settings.py      # Agent/orchestrator settings
└── feature_flags.py     # Feature toggles
```

## Quick Start

### Run Backend
```bash
make start_backend
```

### Add New Agent
1. Create YAML in `registries/agentstore/`
2. Define prompts, tools, handoffs
3. Restart or call `/api/v1/agents/refresh`

### Add New Tool
```python
# In registries/toolstore/your_tool.py
from apps.artagent.backend.registries.toolstore.registry import register_tool

@register_tool(name="your_tool", description="...")
async def your_tool(param: str) -> dict:
    return {"result": "..."}
```

### Load Scenario
```python
from apps.artagent.backend.registries.scenariostore import load_scenario

scenario = load_scenario("banking_customer_service")
agents = get_scenario_agents("banking_customer_service")
```

## WebSocket Flow

```
1. Client connects → /api/v1/media/stream or /api/v1/realtime/conversation
2. Audio chunks → STT (Azure Speech or Realtime API)
3. Text → Multi-agent orchestrator
4. Response → TTS (Azure Speech or Realtime API)
5. Audio → Stream back to client
```

## Troubleshooting

### Import Errors
Use new paths:
```python
# ✅ Correct
from apps.artagent.backend.registries.agentstore import discover_agents

# ❌ Old (deprecated)
from apps.artagent.backend.agents_store import discover_agents
```

### Agent Not Found
```python
agents = discover_agents()
print([a.name for a in agents])  # List all discovered agents
```

### Tool Not Registered
```python
from apps.artagent.backend.registries.toolstore.registry import list_tools
print(list_tools())  # List all registered tools
```

### Health Check Failed
```bash
curl http://localhost:8000/health
```

Check logs for Azure service connectivity issues (Speech, OpenAI, Redis, CosmosDB).


