# **ARTVoice Backend**

**FastAPI + multi-agent voice AI** for real-time phone calls via Azure Communication Services.

## **Architecture**

```
Phone → ACS → WebSocket → STT → Multi-Agent AI → TTS → Audio Response
```

## **Key Features**

- **Multi-Agent System**: ARTAgent, LVAgent, FoundryAgents with specialized roles
- **Connection Pooling**: Pre-warmed Azure clients for low-latency responses
- **WebSocket Streaming**: Real-time audio processing for natural conversation
- **Session Management**: Redis-backed state persistence across connections

## **Structure**

```
backend/
├── main.py              # FastAPI app entry point
├── api/v1/              # REST and WebSocket endpoints 
├── config/              # Voice, features, environment config
└── src/                 # Core services and agent framework
```

## **Key Endpoints**

- **`/api/v1/media/stream`** - ACS media streaming
- **`/api/v1/realtime/conversation`** - Real-time voice conversation
- **`/api/v1/calls/*`** - Call management and status
- **`/health`** - System health and readiness
```
api/v1/
├── endpoints/           # WebSocket and REST handlers
│   ├── calls.py         # ACS call management
│   ├── media.py         # Media streaming WebSocket
│   ├── realtime.py      # Real-time conversation WebSocket
│   └── health.py        # Health monitoring
├── handlers/            # Business logic handlers
├── schemas/             # Pydantic models
└── router.py            # Route registration
```

### **Environment Configuration**
```
config/
├── app_config.py        # Main application configuration
├── app_settings.py      # Agent and environment settings
├── connection_config.py # WebSocket and session limits
└── feature_flags.py     # Feature toggles
```

## **Core Application Architecture**

### **Agent System (ARTAgent Framework)**
```
src/agents/              # YAML-driven agent framework
├── base.py              # ARTAgent class for agent creation
├── agent_store/         # Agent YAML configurations
├── prompt_store/        # Jinja prompt templates
├── tool_store/          # Agent tool registry
└── README.md            # Agent creation guide
```

### **Orchestration Engine**
```
src/orchestration/       # Multi-agent routing and coordination
├── orchestrator.py      # Main routing entry point
├── registry.py          # Agent registration system
├── auth.py              # Authentication agent handler
├── specialists.py       # Specialist agent handlers
├── greetings.py         # Agent handoff management
├── gpt_flow.py          # GPT response processing
├── tools.py             # Tool execution framework
├── termination.py       # Session termination logic
├── latency.py           # Performance monitoring
└── README.md            # Orchestrator guide
```

### **Azure Services Integration**
```
src/services/            # External service integrations
├── speech_services.py   # Azure Speech STT/TTS
├── redis_services.py    # Session state management
├── openai_services.py   # Azure OpenAI integration
├── cosmosdb_services.py # CosmosDB document storage
└── acs/                 # Azure Communication Services
```

### **Session Management**
```
src/sessions/            # WebSocket session lifecycle
├── session_statistics.py # Session metrics and monitoring
└── __init__.py          # Session management utilities
```

### **WebSocket Utilities**
```
src/ws_helpers/          # WebSocket session management
├── shared_ws.py         # Shared WebSocket utilities
└── envelopes.py         # Message envelope handling
```

### **Core Utilities**
```
src/utils/               # Core utilities and helpers
├── tracing.py           # OpenTelemetry tracing
└── auth.py              # Authentication utilities
```

### **Connection Pools (Global)**
```
src/pools/               # Connection pooling (shared across apps)
├── async_pool.py        # Async connection pools
├── connection_manager.py # Thread-safe connections
├── session_manager.py   # Session lifecycle management
├── session_metrics.py   # Session monitoring
├── websocket_manager.py # WebSocket connection pooling
├── aoai_pool.py         # Azure OpenAI connection pool
└── dedicated_tts_pool.py # Dedicated TTS connection pool
```

## **Key Features**

- **Real-time WebSocket Streaming** - Low-latency audio and conversation processing
- **Azure Service Integration** - ACS, Speech Services, OpenAI native support
- **Connection Pooling** - Optimized for high-concurrency connections
- **Session Management** - Persistent state with Redis backend
- **Production Ready** - Comprehensive logging, tracing, health monitoring

## **WebSocket Flow**

```
Client → WebSocket → Handler → Azure Services → Response → Client
```

1. **WebSocket Connection** - Connect via `/api/v1/media/stream` or `/api/v1/realtime/conversation`
2. **Audio Processing** - Real-time STT with Azure Speech
3. **AI Response** - Azure OpenAI generates contextual responses  
4. **Speech Synthesis** - Azure Speech TTS for voice responses
5. **Real-time Streaming** - Audio/text streamed back to client


