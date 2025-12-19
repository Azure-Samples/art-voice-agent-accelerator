# Utilities and Infrastructure Services

Supporting utilities and infrastructure services provide the foundation for the Real-Time Voice Agent's scalability, resilience, and configurability.

## Resource Pool Management

### Speech Resource Pools

The platform uses `WarmableResourcePool` for managing TTS and STT clients:

```python
from src.pools import WarmableResourcePool, AllocationTier

# Create TTS pool with pre-warming
tts_pool = WarmableResourcePool(
    factory=create_tts_client,
    name="tts_pool",
    warm_pool_size=3,              # Pre-warm 3 clients
    enable_background_warmup=True, # Keep pool filled
    session_awareness=True,        # Per-session caching
)

await tts_pool.prepare()  # Initialize and pre-warm
```

### Allocation Tiers

| Tier | Source | Latency | Use Case |
|------|--------|---------|----------|
| `DEDICATED` | Session cache | 0ms | Same session requesting again |
| `WARM` | Pre-warmed queue | <50ms | First request with warmed pool |
| `COLD` | Factory creation | ~200ms | Pool empty, on-demand creation |

### Usage Pattern

```python
# Session-aware acquisition (recommended)
synth, tier = await pool.acquire_for_session(session_id)
# ... use synth ...
await pool.release_for_session(session_id)

# Anonymous acquisition
synth = await pool.acquire(timeout=2.0)
await pool.release(synth)
```

> **See Also**: [Resource Pools Documentation](../architecture/speech/resource-pools.md)

---

## Tool Registry

### Overview

The unified tool registry (`registries/toolstore/`) provides centralized tool management for all agents:

```python
from apps.artagent.backend.registries.toolstore import (
    register_tool,
    get_tools_for_agent,
    execute_tool,
    initialize_tools,
)

# Initialize all tools at startup
initialize_tools()

# Get tools for a specific agent
tools = get_tools_for_agent(["get_account_summary", "handoff_fraud_agent"])

# Execute a tool
result = await execute_tool("get_account_summary", {"client_id": "123"})
```

### Available Tool Categories

| Module | Purpose | Example Tools |
|--------|---------|---------------|
| `banking/banking.py` | Account operations | `get_account_summary`, `get_recent_transactions`, `refund_fee` |
| `banking/investments.py` | Investment tools | `get_portfolio_summary`, `execute_trade` |
| `auth.py` | Identity verification | `verify_client_identity`, `send_mfa_code` |
| `handoffs.py` | Agent transfers | `handoff_concierge`, `handoff_fraud_agent`, `handoff_policy_advisor` |
| `insurance.py` | Policy & claims | `get_policy_details`, `file_new_claim`, `check_claim_status` |
| `fraud.py` | Fraud detection | `flag_suspicious_transaction`, `verify_transaction` |
| `compliance.py` | Compliance checks | `check_aml_status`, `verify_fatca` |
| `escalation.py` | Human escalation | `escalate_human`, `transfer_call_to_call_center` |
| `knowledge_base.py` | RAG search | `search_knowledge_base` |
| `call_transfer.py` | Call routing | `transfer_call`, `warm_transfer` |
| `voicemail.py` | Voicemail | `leave_voicemail`, `check_voicemail` |

### Registering Custom Tools

```python
# In registries/toolstore/my_tools.py

from apps.artagent.backend.registries.toolstore.registry import register_tool

# Define schema (OpenAI function calling format)
my_tool_schema = {
    "name": "my_custom_tool",
    "description": "Does something useful",
    "parameters": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "First parameter"},
            "param2": {"type": "integer", "description": "Second parameter"},
        },
        "required": ["param1"],
    },
}

# Define executor
async def my_custom_tool(args: dict) -> dict:
    param1 = args.get("param1", "")
    param2 = args.get("param2", 0)
    
    # Your logic here
    return {"success": True, "result": f"Processed {param1}"}

# Register the tool
register_tool(
    "my_custom_tool",
    my_tool_schema,
    my_custom_tool,
    tags={"custom"},  # Optional categorization
)
```

### Knowledge Base Tool

The `search_knowledge_base` tool provides semantic search:

```python
# Tool usage in agent
result = await execute_tool("search_knowledge_base", {
    "query": "What is the fee refund policy?",
    "collection": "policies",
    "top_k": 5,
})

# Returns:
# {
#     "success": True,
#     "results": [
#         {"title": "Fee Refund Policy", "content": "...", "score": 0.92},
#         ...
#     ],
#     "source": "cosmos_vector"  # or "mock" if Cosmos not configured
# }
```

---

## Agent Registry

### Overview

The agent registry (`registries/agentstore/`) manages agent definitions:

```python
from apps.artagent.backend.registries.agentstore.loader import AgentLoader

# Load an agent
loader = AgentLoader()
agent = loader.load_agent("concierge")

# Get agent tools
tools = agent.tools  # List of tool names
```

### Agent Structure

Each agent folder contains:

```
📁 registries/agentstore/concierge/
├── 📄 agent.yaml      # Agent configuration
└── 📄 prompt.md       # System prompt template (Jinja2)
```

### Scenario Registry

Scenarios group agents and provide overrides:

```python
from apps.artagent.backend.registries.scenariostore.loader import ScenarioLoader

# Load a scenario
loader = ScenarioLoader()
scenario = loader.load_scenario("banking")

# Get scenario agents
agents = scenario.agents  # List of agent names
start_agent = scenario.start_agent  # Entry point agent
```

---

## State Management

### Memory Manager

Session state and conversation history:

```python
from src.stateful.state_managment import MemoManager

# Load or create session
memory_manager = MemoManager.from_redis(session_id, redis_mgr)

# Conversation history
memory_manager.append_to_history("user", "Hello")
memory_manager.append_to_history("assistant", "Hi there!")

# Context storage
memory_manager.set_context("target_number", "+1234567890")

# Persist to Redis
await memory_manager.persist_to_redis_async(redis_mgr)
```

### Redis Session Management

```python
from src.redis.manager import AzureRedisManager

redis_mgr = AzureRedisManager(
    host="your-redis.redis.cache.windows.net",
    credential=DefaultAzureCredential()
)

# Session data with TTL
await redis_mgr.set_value_async(f"session:{session_id}", data, expire=3600)
```

---

## Observability

### OpenTelemetry Tracing

```python
from utils.telemetry_config import configure_tracing

configure_tracing(
    service_name="voice-agent-api",
    service_version="v1.0.0",
    otlp_endpoint=OTEL_EXPORTER_OTLP_ENDPOINT
)
```

### Structured Logging

```python
from utils.ml_logging import get_logger

logger = get_logger("api.v1.media")

logger.info(
    "Session started",
    extra={
        "session_id": session_id,
        "call_connection_id": call_connection_id,
    }
)
```

### Latency Tracking

```python
from src.tools.latency_tool import LatencyTool

latency_tool = LatencyTool(memory_manager)

latency_tool.start("greeting_ttfb")
await send_greeting_audio()
latency_tool.stop("greeting_ttfb")
```

---

## Authentication

### Azure Entra ID Integration

```python
from azure.identity import DefaultAzureCredential

# Keyless authentication for all Azure services
credential = DefaultAzureCredential()
```

### WebSocket Authentication

```python
from apps.artagent.backend.src.utils.auth import validate_acs_ws_auth

try:
    await validate_acs_ws_auth(websocket, required_scope="media.stream")
except AuthError:
    await websocket.close(code=4001, reason="Authentication required")
```

---

## Configuration Management

### Azure App Configuration

The application pulls configuration from Azure App Configuration:

```python
from apps.artagent.backend.config.appconfig_provider import AppConfigProvider

# Initialize provider
provider = AppConfigProvider(
    endpoint=os.getenv("AZURE_APPCONFIG_ENDPOINT"),
    label=os.getenv("AZURE_APPCONFIG_LABEL"),
)

# Get configuration
config = await provider.get_all_settings()
```

### Environment Variables

Key environment variables:

| Variable | Description |
|----------|-------------|
| `AZURE_APPCONFIG_ENDPOINT` | App Configuration endpoint |
| `AZURE_APPCONFIG_LABEL` | Configuration label (environment) |
| `ACS_STREAMING_MODE` | `voice_live` or `media` (cascade) |
| `AZURE_SPEECH_KEY` | Speech service API key |
| `AZURE_SPEECH_REGION` | Speech service region |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint |

---

## Demo Environment

### Mock User Generation

The demo environment endpoint generates mock users for testing:

```python
# GET /api/v1/demo/user
# Returns a randomly generated user with:
# - Profile (name, email, phone)
# - Accounts (checking, savings)
# - Transactions (including international)
# - Credit cards
# - Investments
```

### Features

- **Mock Transactions**: Realistic transaction data with merchants and categories
- **International Transactions**: Foreign transactions with 3% fees
- **Policy/Claims Data**: Insurance demo data for policy advisor scenarios

---

## Related Documentation

- [Resource Pools](../architecture/speech/README.md) - Pool configuration and troubleshooting
- [Agent Registry](../architecture/agents/README.md) - Creating and configuring agents
- [API Reference](../api/api-reference.md) - Building custom tools
- [Streaming Modes](../architecture/speech/README.md) - SpeechCascade vs VoiceLive
