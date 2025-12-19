# Session-Level Agent Configuration Management

> **RFC Proposal: Dynamic Runtime Agent Configuration for Voice Sessions**

## Executive Summary

This document proposes an architecture for managing agent configurations at the **session level**, enabling dynamic runtime modification of agent capabilities without service restarts. The design integrates with existing `MemoManager` session state and Redis persistence, supporting real-time experimentation in sandbox environments.

---

## 1. Problem Statement

### Current Architecture Limitations

| Component | Current Behavior | Limitation |
|-----------|------------------|------------|
| `loader.py` | `discover_agents()` runs once at startup | Agents are immutable after load |
| `LiveOrchestratorAdapter` | Receives static `agents: Dict[str, Any]` | No per-session customization |
| `HANDOFF_MAP` | Global static dict | Same handoff routing for all sessions |
| `VoiceLiveSDKHandler` | Loads registry at startup via `load_registry()` | Cannot modify agent behavior mid-call |

### Desired Capabilities

1. **Per-session agent overrides** - Modify prompts, voice, model, and tools per session
2. **Runtime hot-swap** - Change active agent configuration without disconnecting
3. **Sandbox experimentation** - A/B test agent variations in real-time
4. **Configuration inheritance** - Session configs inherit from base, override selectively
5. **Audit trail** - Track what configurations were active during each session

---

## 2. Architecture Proposal

### 2.1 Core Concept: SessionAgentManager

Introduce a new class that wraps agent configurations with session-scoped mutability:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Voice Session Lifecycle                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌─────────────────────┐    ┌─────────────────┐ │
│  │  Base Agents │───▶│ SessionAgentManager │───▶│   Orchestrator   │ │
│  │  (Immutable) │    │    (Per-Session)    │    │  (VoiceLive/    │ │
│  │              │    │                     │    │   Cascade)      │ │
│  └──────────────┘    └─────────────────────┘    └─────────────────┘ │
│         │                      │                        │           │
│         │            ┌─────────┴─────────┐              │           │
│         │            ▼                   ▼              │           │
│         │    ┌──────────────┐    ┌─────────────┐        │           │
│         │    │ MemoManager  │    │    Redis    │        │           │
│         │    │ (In-Memory)  │◀──▶│ (Persistence)│       │           │
│         │    └──────────────┘    └─────────────┘        │           │
│         │                                               │           │
│         └───────────────────────────────────────────────┘           │
│                      Handoff Events Trigger                          │
│                      Agent Config Reload                             │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Model

#### SessionAgentConfig (extends UnifiedAgent)

```python
@dataclass
class SessionAgentConfig:
    """Per-session agent configuration with override tracking."""
    
    # Base agent reference (immutable)
    base_agent_name: str
    
    # Session-specific overrides
    prompt_override: Optional[str] = None
    voice_override: Optional[VoiceConfig] = None
    model_override: Optional[ModelConfig] = None
    tool_names_override: Optional[List[str]] = None
    template_vars_override: Optional[Dict[str, Any]] = None
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    modified_at: Optional[float] = None
    modification_count: int = 0
    source: Literal["base", "session", "api", "admin"] = "base"


@dataclass  
class SessionAgentRegistry:
    """Complete agent registry for a session."""
    
    session_id: str
    agents: Dict[str, SessionAgentConfig]  # agent_name → config
    handoff_map: Dict[str, str]  # tool_name → agent_name
    active_agent: Optional[str] = None
    
    # Sandbox/experiment tracking
    experiment_id: Optional[str] = None
    variant: Optional[str] = None
```

#### Redis Storage Structure

```json
{
  "session:{session_id}": {
    "corememory": "...",
    "chat_history": "...",
    "agent_registry": {
      "agents": {
        "EricaConcierge": {
          "base_agent_name": "EricaConcierge",
          "prompt_override": "Custom prompt for this session...",
          "voice_override": {"name": "en-US-AvaNeural", "rate": "1.1"},
          "modification_count": 2,
          "source": "api"
        }
      },
      "handoff_map": {
        "transfer_to_fraud": "FraudAgent",
        "transfer_to_auth": "AuthAgent"
      },
      "active_agent": "EricaConcierge",
      "experiment_id": "exp-2024-01-prompt-v2"
    }
  }
}
```

### 2.3 SessionAgentManager Implementation

```python
class SessionAgentManager:
    """
    Manages agent configurations at the session level.
    
    Provides:
    - Session-scoped agent config storage
    - Override inheritance from base agents
    - Runtime modification capabilities
    - Redis persistence integration
    """
    
    _AGENT_REGISTRY_KEY = "agent_registry"
    
    def __init__(
        self,
        session_id: str,
        base_agents: Dict[str, UnifiedAgent],
        memo_manager: MemoManager,
        *,
        redis_mgr: Optional[AzureRedisManager] = None,
    ):
        self.session_id = session_id
        self._base_agents = base_agents  # Immutable reference
        self._memo = memo_manager
        self._redis = redis_mgr
        self._registry: SessionAgentRegistry = self._init_registry()
    
    def _init_registry(self) -> SessionAgentRegistry:
        """Initialize registry from base agents or load from session."""
        # Check if session already has registry in memo/redis
        existing = self._memo.get_context(self._AGENT_REGISTRY_KEY)
        if existing:
            return SessionAgentRegistry.from_dict(existing)
        
        # Create fresh registry from base agents
        return SessionAgentRegistry(
            session_id=self.session_id,
            agents={
                name: SessionAgentConfig(base_agent_name=name)
                for name in self._base_agents
            },
            handoff_map=build_handoff_map(self._base_agents),
        )
    
    # ─────────────────────────────────────────────────────────────────
    # Agent Resolution (with overrides applied)
    # ─────────────────────────────────────────────────────────────────
    
    def get_agent(self, name: str) -> UnifiedAgent:
        """
        Get agent with session overrides applied.
        
        Returns a new UnifiedAgent instance with:
        - Base agent properties
        - Session-specific overrides merged in
        """
        base = self._base_agents.get(name)
        if not base:
            raise ValueError(f"Unknown agent: {name}")
        
        config = self._registry.agents.get(name)
        if not config or config.source == "base":
            return base  # No overrides, return base
        
        # Apply overrides
        return self._apply_overrides(base, config)
    
    def _apply_overrides(
        self,
        base: UnifiedAgent,
        config: SessionAgentConfig,
    ) -> UnifiedAgent:
        """Create new agent with overrides applied."""
        return UnifiedAgent(
            name=base.name,
            description=base.description,
            greeting=base.greeting,
            return_greeting=base.return_greeting,
            handoff=base.handoff,
            model=config.model_override or base.model,
            voice=config.voice_override or base.voice,
            session=base.session,
            prompt_template=config.prompt_override or base.prompt_template,
            tool_names=config.tool_names_override or base.tool_names,
            template_vars={
                **base.template_vars,
                **(config.template_vars_override or {}),
            },
            metadata={
                **base.metadata,
                "session_override": True,
                "override_source": config.source,
            },
            source_dir=base.source_dir,
        )
    
    # ─────────────────────────────────────────────────────────────────
    # Runtime Modification API
    # ─────────────────────────────────────────────────────────────────
    
    def update_agent_prompt(
        self,
        agent_name: str,
        prompt: str,
        *,
        source: str = "api",
    ) -> None:
        """Update an agent's prompt for this session."""
        config = self._ensure_config(agent_name)
        config.prompt_override = prompt
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
    
    def update_agent_voice(
        self,
        agent_name: str,
        voice: VoiceConfig,
        *,
        source: str = "api",
    ) -> None:
        """Update an agent's voice configuration."""
        config = self._ensure_config(agent_name)
        config.voice_override = voice
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
    
    def update_agent_tools(
        self,
        agent_name: str,
        tool_names: List[str],
        *,
        source: str = "api",
    ) -> None:
        """Update an agent's available tools."""
        config = self._ensure_config(agent_name)
        config.tool_names_override = tool_names
        config.modified_at = time.time()
        config.modification_count += 1
        config.source = source
        self._mark_dirty()
    
    def reset_agent(self, agent_name: str) -> None:
        """Reset agent to base configuration."""
        if agent_name in self._registry.agents:
            self._registry.agents[agent_name] = SessionAgentConfig(
                base_agent_name=agent_name
            )
            self._mark_dirty()
    
    def reset_all_agents(self) -> None:
        """Reset all agents to base configuration."""
        self._registry = self._init_registry()
        self._mark_dirty()
    
    # ─────────────────────────────────────────────────────────────────
    # Handoff Management
    # ─────────────────────────────────────────────────────────────────
    
    def update_handoff_map(self, tool_name: str, target_agent: str) -> None:
        """Add or update a handoff mapping."""
        if target_agent not in self._base_agents:
            raise ValueError(f"Unknown target agent: {target_agent}")
        self._registry.handoff_map[tool_name] = target_agent
        self._mark_dirty()
    
    def get_handoff_target(self, tool_name: str) -> Optional[str]:
        """Get the target agent for a handoff tool."""
        return self._registry.handoff_map.get(tool_name)
    
    @property
    def handoff_map(self) -> Dict[str, str]:
        """Get the current handoff map."""
        return self._registry.handoff_map.copy()
    
    # ─────────────────────────────────────────────────────────────────
    # Active Agent Tracking
    # ─────────────────────────────────────────────────────────────────
    
    def set_active_agent(self, agent_name: str) -> None:
        """Set the currently active agent."""
        self._registry.active_agent = agent_name
        self._mark_dirty()
    
    @property
    def active_agent(self) -> Optional[str]:
        """Get the currently active agent."""
        return self._registry.active_agent
    
    # ─────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────
    
    def _ensure_config(self, agent_name: str) -> SessionAgentConfig:
        """Ensure agent has a config entry."""
        if agent_name not in self._registry.agents:
            self._registry.agents[agent_name] = SessionAgentConfig(
                base_agent_name=agent_name
            )
        return self._registry.agents[agent_name]
    
    def _mark_dirty(self) -> None:
        """Mark registry as needing persistence."""
        self._memo.set_context(
            self._AGENT_REGISTRY_KEY,
            self._registry.to_dict(),
        )
    
    async def persist(self) -> None:
        """Persist registry to Redis."""
        if self._redis:
            await self._memo.persist_to_redis_async(self._redis)
    
    async def reload(self) -> None:
        """Reload registry from Redis."""
        if self._redis:
            await self._memo.refresh_from_redis_async(self._redis)
            existing = self._memo.get_context(self._AGENT_REGISTRY_KEY)
            if existing:
                self._registry = SessionAgentRegistry.from_dict(existing)
    
    # ─────────────────────────────────────────────────────────────────
    # Experiment Support
    # ─────────────────────────────────────────────────────────────────
    
    def set_experiment(self, experiment_id: str, variant: str) -> None:
        """Tag session with experiment metadata."""
        self._registry.experiment_id = experiment_id
        self._registry.variant = variant
        self._mark_dirty()
    
    def get_audit_log(self) -> Dict[str, Any]:
        """Get modification history for audit purposes."""
        return {
            "session_id": self.session_id,
            "experiment_id": self._registry.experiment_id,
            "variant": self._registry.variant,
            "agents": {
                name: {
                    "modification_count": config.modification_count,
                    "modified_at": config.modified_at,
                    "source": config.source,
                    "has_prompt_override": config.prompt_override is not None,
                    "has_voice_override": config.voice_override is not None,
                    "has_tools_override": config.tool_names_override is not None,
                }
                for name, config in self._registry.agents.items()
                if config.modification_count > 0
            },
        }
```

---

## 3. Integration Points

### 3.1 VoiceLiveSDKHandler Integration

```python
# Current (static):
agents = load_registry(str(self._settings.agents_path))
self._orchestrator = LiveOrchestrator(
    conn=self._connection,
    agents=agents,
    handoff_map=HANDOFF_MAP,
    ...
)

# Proposed (session-aware):
base_agents = load_registry(str(self._settings.agents_path))
session_agent_mgr = SessionAgentManager(
    session_id=self.session_id,
    base_agents=base_agents,
    memo_manager=memo_manager,  # Pass through from session
    redis_mgr=redis_mgr,
)

# Orchestrator uses session manager for agent resolution
self._orchestrator = LiveOrchestrator(
    conn=self._connection,
    agent_provider=session_agent_mgr,  # New protocol
    handoff_provider=session_agent_mgr,  # Unified interface
    ...
)
```

### 3.2 LiveOrchestratorAdapter Protocol Update

```python
class AgentProvider(Protocol):
    """Protocol for session-aware agent resolution."""
    
    def get_agent(self, name: str) -> UnifiedAgent:
        """Get agent configuration (with session overrides)."""
        ...
    
    @property
    def active_agent(self) -> Optional[str]:
        """Get currently active agent."""
        ...
    
    def set_active_agent(self, name: str) -> None:
        """Set the active agent."""
        ...


class HandoffProvider(Protocol):
    """Protocol for session-aware handoff resolution."""
    
    def get_handoff_target(self, tool_name: str) -> Optional[str]:
        """Get target agent for handoff tool."""
        ...
    
    @property
    def handoff_map(self) -> Dict[str, str]:
        """Get current handoff mappings."""
        ...
```

### 3.3 SpeechCascadeHandler Integration

The `SpeechCascadeHandler` uses `MemoManager` already. Integration is simpler:

```python
class SpeechCascadeHandler:
    def __init__(
        self,
        connection_id: str,
        orchestrator_func: Callable,
        memory_manager: MemoManager,
        agent_manager: Optional[SessionAgentManager] = None,  # New
        ...
    ):
        self._agent_mgr = agent_manager
```

### 3.4 WebSocket API for Runtime Modification

Add endpoints for sandbox experimentation:

```python
@router.websocket("/session/{session_id}/config")
async def session_config_ws(
    websocket: WebSocket,
    session_id: str,
    agent_mgr: SessionAgentManager = Depends(get_session_agent_manager),
):
    """WebSocket for real-time agent configuration updates."""
    await websocket.accept()
    
    async for message in websocket.iter_json():
        action = message.get("action")
        
        if action == "update_prompt":
            agent_mgr.update_agent_prompt(
                message["agent_name"],
                message["prompt"],
                source="websocket",
            )
            await agent_mgr.persist()
            await websocket.send_json({"status": "ok", "action": action})
        
        elif action == "update_voice":
            agent_mgr.update_agent_voice(
                message["agent_name"],
                VoiceConfig.from_dict(message["voice"]),
                source="websocket",
            )
            await agent_mgr.persist()
            await websocket.send_json({"status": "ok", "action": action})
        
        elif action == "reset_agent":
            agent_mgr.reset_agent(message["agent_name"])
            await agent_mgr.persist()
            await websocket.send_json({"status": "ok", "action": action})
        
        elif action == "get_audit":
            await websocket.send_json({
                "status": "ok",
                "action": action,
                "data": agent_mgr.get_audit_log(),
            })
```

---

## 4. Migration Path

### Phase 1: Foundation (Week 1)

1. **Create `SessionAgentManager` class** in `apps/artagent/agents/session_manager.py`
2. **Add serialization to `SessionAgentRegistry`** and `SessionAgentConfig`
3. **Update `MemoManager`** with `_AGENT_REGISTRY_KEY` handling
4. **Unit tests** for override resolution

### Phase 2: Integration (Week 2)

1. **Update `VoiceLiveSDKHandler`** to use `SessionAgentManager`
2. **Implement `AgentProvider`/`HandoffProvider` protocols** in `LiveOrchestratorAdapter`
3. **Update `SpeechCascadeHandler`** integration
4. **Integration tests** with Redis persistence

### Phase 3: API & UI (Week 3)

1. **Add WebSocket config endpoint**
2. **Frontend sandbox UI** for agent modification
3. **Experiment tracking integration**
4. **Documentation and examples**

---

## 5. Storage Considerations

### Memory vs Redis Trade-offs

| Aspect | In-Memory (MemoManager) | Redis |
|--------|------------------------|-------|
| Latency | ~0ms | 1-5ms |
| Durability | Session-scoped | Persistent |
| Sharing | Single process | Multi-process |
| Failover | Lost on crash | Survives restart |

### Recommended Strategy

1. **Write-through**: Update `MemoManager` immediately, persist to Redis async
2. **Lazy load**: On session restore, load from Redis if available
3. **Periodic sync**: Background task syncs every N seconds during active session

```python
# In SessionAgentManager
async def persist_background(self) -> None:
    """Non-blocking persist for hot path."""
    asyncio.create_task(self.persist())

def _mark_dirty(self) -> None:
    """Mark for persistence without blocking."""
    self._memo.set_context(self._AGENT_REGISTRY_KEY, self._registry.to_dict())
    # Background persist if redis available
    if self._redis and asyncio.get_running_loop():
        asyncio.create_task(self._memo.persist_background(self._redis))
```

---

## 6. Observability

### Telemetry Attributes

Add to existing span attributes:

```python
class SessionAgentSpanAttr:
    AGENT_OVERRIDE_COUNT = "session.agent.override_count"
    AGENT_OVERRIDE_SOURCE = "session.agent.override_source"
    EXPERIMENT_ID = "session.experiment.id"
    EXPERIMENT_VARIANT = "session.experiment.variant"
```

### Logging

```python
logger.info(
    "Agent config modified | session=%s agent=%s field=%s source=%s",
    session_id,
    agent_name,
    "prompt",
    "api",
)
```

---

## 7. Security Considerations

1. **Input validation**: Validate prompt content, voice names against allowlist
2. **Rate limiting**: Limit config changes per session (e.g., 10/minute)
3. **Audit trail**: Log all modifications with source and timestamp
4. **Rollback**: Keep previous N configurations for rollback

---

## 8. Open Questions

1. **Tool validation**: Should we validate that overridden tools exist in registry?
2. **Schema versioning**: How to handle schema changes in persisted configs?
3. **Cross-session sharing**: Should experiment variants be shareable across sessions?
4. **Quota limits**: Max override size per agent (prompt length, etc.)?

---

## 9. Appendix: Full File Structure

```
apps/artagent/
├── agents/
│   ├── base.py                    # UnifiedAgent (existing)
│   ├── loader.py                  # discover_agents() (existing)
│   ├── session_manager.py         # NEW: SessionAgentManager
│   └── tools/
│       └── registry.py            # Tool registry (existing)
├── backend/
│   ├── voice_channels/
│   │   ├── orchestrators/
│   │   │   ├── base.py            # AgentProvider protocol (updated)
│   │   │   └── live_adapter.py    # Uses SessionAgentManager
│   │   └── voicelive/
│   │       └── handler.py         # Creates SessionAgentManager
│   └── routes/
│       └── session_config.py      # NEW: WebSocket API
└── frontend/
    └── components/
        └── AgentSandbox.tsx       # NEW: Config UI
```

---

## 10. References

- [UnifiedAgent base class](apps/artagent/agents/base.py)
- [Agent loader](apps/artagent/agents/loader.py)
- [MemoManager](src/stateful/state_managment.py)
- [LiveOrchestratorAdapter](apps/artagent/backend/voice_channels/orchestrators/live_adapter.py)
- [VoiceLiveSDKHandler](apps/artagent/backend/voice_channels/voicelive/handler.py)
