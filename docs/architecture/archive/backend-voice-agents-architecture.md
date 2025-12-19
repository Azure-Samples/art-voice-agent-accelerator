# Backend Voice & Agents Architecture

This document describes the architecture of the `apps/artagent/backend/` modules, specifically the separation of concerns between `voice/` (transport & orchestration) and `agents/` (configuration & business logic).

---

## High-Level Overview

```
                                    External Calls (ACS/WebSocket)
                                              │
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                                    backend/                                          │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌──────────────────────────────────────────┐    ┌─────────────────────────────────┐ │
│  │              voice/                      │    │            agents/              │ │
│  │     (Transport & Orchestration)          │    │     (Config & Business Logic)   │ │
│  │                                          │    │                                 │ │
│  │  ┌────────────────────────────────────┐  │    │  ┌───────────────────────────┐  │ │
│  │  │ voicelive/                         │  │    │  │ Agent Definitions         │  │ │
│  │  │   ├─ handler.py     (SDK bridge)   │  │    │  │   ├─ concierge/           │  │ │
│  │  │   ├─ agent_adapter.py              │  │    │  │   │   ├─ agent.yaml       │  │ │
│  │  │   ├─ session_loader.py             │  │    │  │   │   └─ prompt.jinja     │  │ │
│  │  │   └─ metrics.py                    │  │    │  │   ├─ fraud_agent/         │  │ │
│  │  └────────────────────────────────────┘  │    │  │   ├─ investment_advisor/  │  │ │
│  │                 │                        │    │  │   ├─ compliance_desk/     │  │ │
│  │                 ▼                        │    │  │   └─ ...                  │  │ │
│  │  ┌────────────────────────────────────┐  │    │  └───────────────────────────┘  │ │
│  │  │ speech_cascade/                    │  │    │                                 │ │
│  │  │   ├─ handler.py  (STT→LLM→TTS)     │  │    │  ┌───────────────────────────┐  │ │
│  │  │   └─ metrics.py                    │  │    │  │ tools/                    │  │ │
│  │  └────────────────────────────────────┘  │    │  │   ├─ registry.py          │  │ │
│  │                 │                        │    │  │   │   ├─ register_tool()  │  │ │
│  │                 ▼                        │    │  │   │   ├─ execute_tool()   │  │ │
│  │  ┌────────────────────────────────────┐  │    │  │   │   └─ is_handoff_tool()│  │ │
│  │  │ orchestrators/                     │  │    │  │   ├─ handoffs.py          │  │ │
│  │  │   ├─ live_orchestrator.py ─────────┼──┼────┼──┤   ├─ banking.py           │  │ │
│  │  │   │     (VoiceLive multi-agent)    │  │    │  │   ├─ fraud.py             │  │ │
│  │  │   ├─ cascade_adapter.py ───────────┼──┼────┼──┤   └─ ...                  │  │ │
│  │  │   │     (Cascade multi-agent)      │  │    │  └───────────────────────────┘  │ │
│  │  │   └─ config_resolver.py            │  │    │                                 │ │
│  │  │         (scenario-aware config)    │  │    │  ┌───────────────────────────┐  │ │
│  │  └────────────────────────────────────┘  │    │  │ Core Modules              │  │ │
│  │                 │                        │    │  │   ├─ base.py              │  │ │
│  │                 ▼                        │    │  │   │   └─ UnifiedAgent     │  │ │
│  │  ┌────────────────────────────────────┐  │    │  │   ├─ loader.py            │  │ │
│  │  │ handoffs/                          │  │    │  │   │   ├─ discover_agents()│  │ │
│  │  │   └─ context.py                    │  │    │  │   │   └─ build_handoff_   │  │ │
│  │  │       ├─ HandoffContext            │  │    │  │   │         map()         │  │ │
│  │  │       ├─ HandoffResult             │  │    │  │   └─ session_manager.py   │  │ │
│  │  │       ├─ build_handoff_system_vars │  │    │  │       ├─ SessionAgentMgr  │  │ │
│  │  │       └─ sanitize_handoff_context  │  │    │  │       └─ HandoffProvider  │  │ │
│  │  └────────────────────────────────────┘  │    │  └───────────────────────────┘  │ │
│  │                                          │    │                                 │ │
│  └──────────────────────────────────────────┘    └─────────────────────────────────┘ │
│                                                                                      │
│                               Data Flow                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐ │
│  │  discover_agents() ──► UnifiedAgent dict ──► build_handoff_map() ──► handoff_map│ │
│  │                              │                                           │      │ │
│  │                              ▼                                           ▼      │ │
│  │                    Orchestrators use agents          HandoffProvider lookups    │ │
│  └─────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Responsibilities

### `backend/agents/` — Configuration & Business Logic

**Purpose**: Define WHAT agents do (prompts, tools, handoffs) without knowing HOW they'll be invoked.

| Component | Responsibility |
|-----------|----------------|
| `base.py` | `UnifiedAgent` dataclass — orchestrator-agnostic agent definition |
| `loader.py` | Auto-discovers agents from folder structure, builds `handoff_map` |
| `session_manager.py` | Session-scoped agent overrides, `HandoffProvider` protocol |
| `tools/registry.py` | Central tool registry with schemas and executors |
| `tools/*.py` | Tool implementations (banking, handoffs, fraud, etc.) |
| `{agent}/agent.yaml` | Per-agent configuration (prompt, tools, voice, handoff trigger) |
| `{agent}/prompt.jinja` | Agent's system prompt template |
| `scenarios/` | Scenario-based agent overrides for demo configurations |

**Key Abstractions**:
- `UnifiedAgent`: Orchestrator-agnostic agent configuration
- `HandoffConfig`: Defines how to reach an agent (`trigger` tool name)
- `HandoffProvider` protocol: Session-aware handoff target resolution
- Tool Registry: `register_tool()`, `execute_tool()`, `is_handoff_tool()`

### `backend/voice/` — Transport & Orchestration

**Purpose**: Define HOW agents are invoked (WebSocket handling, audio streaming, multi-agent switching).

| Component | Responsibility |
|-----------|----------------|
| `voicelive/handler.py` | VoiceLive SDK WebSocket handler, audio streaming |
| `voicelive/agent_adapter.py` | Adapts `UnifiedAgent` to VoiceLive session format |
| `speech_cascade/handler.py` | Three-thread architecture for STT→LLM→TTS pipeline |
| `orchestrators/live_orchestrator.py` | Multi-agent switching for VoiceLive (real-time) |
| `orchestrators/cascade_adapter.py` | Multi-agent switching for SpeechCascade (turn-based) |
| `orchestrators/config_resolver.py` | Scenario-aware agent/handoff resolution |
| `handoffs/context.py` | Shared handoff context builders and dataclasses |

**Key Abstractions**:
- `LiveOrchestrator`: Event-driven orchestration for VoiceLive
- `CascadeOrchestratorAdapter`: Turn-based orchestration for SpeechCascade
- `OrchestratorContext` / `OrchestratorResult`: Shared data structures
- `HandoffContext` / `HandoffResult`: Handoff execution data

---

## Separation of Concerns

### ✅ Clean Boundaries

| Concern | Owned By | NOT Owned By |
|---------|----------|--------------|
| Agent prompts & tools | `agents/` | `voice/` |
| Handoff tool definitions | `agents/tools/handoffs.py` | `voice/` |
| Handoff target resolution | `agents/session_manager.py` | - |
| Tool execution | `agents/tools/registry.py` | `voice/` |
| Audio streaming | `voice/voicelive/` | `agents/` |
| Turn processing | `voice/speech_cascade/` | `agents/` |
| Multi-agent switching | `voice/orchestrators/` | `agents/` |
| Handoff context building | `voice/handoffs/context.py` | `agents/` |

### Key Design Decisions

1. **Agents are orchestrator-agnostic**: `UnifiedAgent` works with both VoiceLive and SpeechCascade
2. **Tools are centralized**: All tools registered in `agents/tools/registry.py`
3. **Handoff routing via `handoff_map`**: Built from agent YAML declarations
4. **`is_handoff_tool()` from registry**: Single source for "is this a handoff tool type?"
5. **`HandoffProvider` for live lookups**: Session-aware handoff target resolution

---

## Data Flow

### VoiceLive Path (Real-Time)

```
External Call (ACS)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  VoiceLiveSDKHandler (voice/voicelive/handler.py)           │
│    - WebSocket connection to VoiceLive SDK                  │
│    - Audio streaming (PCM16)                                │
│    - Session management                                     │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  LiveOrchestrator (voice/orchestrators/live_orchestrator.py)│
│    - Event handling (tool calls, transcripts)               │
│    - Multi-agent switching via handoff tools                │
│    - Tool execution via registry                            │
└─────────────────────────────────────────────────────────────┘
       │
       ├──────────────────────────────────────────────────────┐
       ▼                                                      │
┌─────────────────────────────────┐    ┌─────────────────────────────────┐
│  VoiceLiveAgentAdapter          │    │  Tool Registry                  │
│  (voice/voicelive/agent_adapter)│    │  (agents/tools/registry.py)     │
│    - UnifiedAgent → session     │    │    - execute_tool()             │
│    - apply_session() to SDK     │    │    - is_handoff_tool()          │
└─────────────────────────────────┘    └─────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│  UnifiedAgent                   │
│  (agents/base.py)               │
│    - Prompt template            │
│    - Tool list                  │
│    - Handoff config             │
└─────────────────────────────────┘
```

### SpeechCascade Path (Turn-Based)

```
External Call (ACS)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  SpeechCascadeHandler (voice/speech_cascade/handler.py)     │
│    - Three-thread architecture                              │
│    - STT → LLM → TTS pipeline                               │
│    - Barge-in handling                                      │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  CascadeOrchestratorAdapter (voice/orchestrators/cascade_adapter.py) │
│    - Turn-based processing                                  │
│    - Multi-agent switching                                  │
│    - Tool execution via registry                            │
└─────────────────────────────────────────────────────────────┘
       │
       ├──────────────────────────────────────────────────────┐
       ▼                                                      │
┌─────────────────────────────────┐    ┌─────────────────────────────────┐
│  UnifiedAgent                   │    │  Tool Registry                  │
│  (agents/base.py)               │    │  (agents/tools/registry.py)     │
│    - render_prompt()            │    │    - execute_tool()             │
│    - get_tools()                │    │    - is_handoff_tool()          │
└─────────────────────────────────┘    └─────────────────────────────────┘
```

---

## Handoff Flow

```
1. LLM calls handoff tool (e.g., "handoff_fraud_agent")
       │
       ▼
2. Orchestrator detects handoff
   ┌─────────────────────────────────────────────────────────────────┐
   │  if is_handoff_tool(tool_name):  # from agents/tools/registry   │
   │      target = get_handoff_target(tool_name)  # from handoff_map │
   └─────────────────────────────────────────────────────────────────┘
       │
       ▼
3. Build handoff context (voice/handoffs/context.py)
   ┌─────────────────────────────────────────────────────────────────┐
   │  system_vars = build_handoff_system_vars(                       │
   │      source_agent="Concierge",                                  │
   │      target_agent="FraudAgent",                                 │
   │      tool_result={...},                                         │
   │      tool_args={...},                                           │
   │      current_system_vars={...},                                 │
   │  )                                                              │
   └─────────────────────────────────────────────────────────────────┘
       │
       ▼
4. Switch to target agent
   ┌─────────────────────────────────────────────────────────────────┐
   │  # VoiceLive: agent.apply_session(conn, system_vars)            │
   │  # Cascade: set _active_agent, render new prompt                │
   └─────────────────────────────────────────────────────────────────┘
       │
       ▼
5. Target agent responds with greeting
```

---

## Key Protocols

### `HandoffProvider` (agents/session_manager.py)

```python
class HandoffProvider(Protocol):
    """Protocol for session-aware handoff resolution."""
    
    def get_handoff_target(self, tool_name: str) -> Optional[str]:
        """Get target agent for a handoff tool."""
        ...
    
    @property
    def handoff_map(self) -> Dict[str, str]:
        """Get current handoff mappings."""
        ...
    
    def is_handoff_tool(self, tool_name: str) -> bool:
        """Check if a tool triggers a handoff (session-aware)."""
        ...
```

**Implementations**:
- `SessionAgentManager`: Per-session handoff configuration with runtime updates

**Consumers**:
- `LiveOrchestrator`: Uses `HandoffProvider` for live lookups
- `CascadeOrchestratorAdapter`: Uses `HandoffProvider` or static `handoff_map`

---

## File Inventory

### `backend/voice/`

```
voice/
├── __init__.py
├── handoffs/
│   ├── __init__.py          # Exports HandoffContext, HandoffResult, helpers
│   └── context.py           # Dataclasses + build_handoff_system_vars()
├── messaging/               # WebSocket message helpers
├── orchestrators/
│   ├── __init__.py          # Exports LiveOrchestrator, CascadeOrchestratorAdapter
│   ├── base.py              # OrchestratorContext, OrchestratorResult
│   ├── cascade_adapter.py   # SpeechCascade orchestration
│   ├── config_resolver.py   # Scenario-aware config resolution
│   └── live_orchestrator.py # VoiceLive orchestration
├── speech_cascade/
│   ├── handler.py           # Three-thread STT→LLM→TTS handler
│   ├── metrics.py           # Latency metrics
│   └── orchestrator.py      # Legacy orchestrator (deprecated)
└── voicelive/
    ├── agent_adapter.py     # UnifiedAgent → VoiceLive adapter
    ├── handler.py           # VoiceLive SDK WebSocket handler
    ├── metrics.py           # Latency metrics
    ├── session_loader.py    # User profile loading
    ├── settings.py          # VoiceLive settings
    └── tool_helpers.py      # Tool notification helpers
```

### `backend/agents/`

```
agents/
├── __init__.py
├── _defaults.yaml           # Default agent configuration
├── base.py                  # UnifiedAgent, HandoffConfig, VoiceConfig, ModelConfig
├── loader.py                # discover_agents(), build_handoff_map()
├── session_manager.py       # SessionAgentManager, HandoffProvider protocol
├── scenarios/               # Scenario-based overrides
│   └── loader.py
├── tools/
│   ├── __init__.py          # Tool initialization and exports
│   ├── registry.py          # Tool registration and execution
│   ├── handoffs.py          # Handoff tool implementations
│   ├── banking.py           # Banking tools
│   ├── fraud.py             # Fraud detection tools
│   └── ...                  # Other tool modules
└── {agent_name}/
    ├── agent.yaml           # Agent configuration
    └── prompt.jinja         # System prompt template
```

---

## Summary

The architecture cleanly separates:

1. **Business Logic** (`agents/`): What agents do, their prompts, tools, and handoff triggers
2. **Transport** (`voice/`): How agents are invoked via VoiceLive or SpeechCascade
3. **Orchestration** (`voice/orchestrators/`): Multi-agent switching and tool execution

Both orchestrators (`LiveOrchestrator`, `CascadeOrchestratorAdapter`) use:
- `is_handoff_tool(name)` from the tool registry for handoff detection
- `HandoffProvider.get_handoff_target(name)` or `handoff_map` for target resolution
- `build_handoff_system_vars()` from `voice/handoffs/context.py` for context building

This enables **orchestrator-agnostic agents** that work with any voice transport layer.

---

## Recent Cleanup (Phases 1-6)

The handoff system was simplified through six phases documented in [handoff-inventory.md](handoff-inventory.md):

| Phase | Change | Impact |
|-------|--------|--------|
| 1 | Removed unused strategy patterns | ~600 lines deleted |
| 2 | Added `HandoffProvider` protocol | Live handoff lookups |
| 3 | Extracted shared handoff context builder | ~25 lines reduced |
| 4 | Removed unused `HandoffStrategy` enum | ~60 lines deleted |
| 5 | Consolidated `is_handoff_tool()` to registry | Single source of truth |
| 6 | Added `HandoffProvider` to CascadeAdapter | Session-aware handoffs |

**Total lines removed**: ~690
