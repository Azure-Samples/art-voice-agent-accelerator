# Scenario Orchestration Simplification Analysis

## Executive Summary

This document analyzes the current scenario orchestration system, identifies pain points in code complexity, and proposes simplifications for the voice pipeline hot paths (VoiceLive and SpeechCascade modes).

**Key Findings:**
1. **Too Many Abstraction Layers**: 6+ layers between scenario config and actual agent execution
2. **Redundant Wrappers**: Agent adapters, session managers, and config resolvers that duplicate responsibilities
3. **Hot Path Latency**: Session sync and context refresh operations blocking the audio processing loop
4. **Inconsistent Patterns**: Different handoff resolution paths between orchestrators despite `HandoffService` unification
5. **Complex Greeting Logic**: Greeting selection scattered across 4+ modules with overlapping fallbacks

---

## Architecture Overview

### Current Flow (Scenario → Agent Execution)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SCENARIO DEFINITION                             │
│  scenariostore/loader.py → ScenarioConfig                                   │
│    ├── HandoffConfig (per-edge behavior)                                    │
│    ├── AgentOverride (greeting, voice, template_vars)                       │
│    └── GenericHandoffConfig                                                 │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CONFIG RESOLUTION                                 │
│  shared/config_resolver.py → OrchestratorConfigResult                       │
│    ├── resolve_orchestrator_config() ← session scenarios                    │
│    ├── resolve_from_app_state() ← FastAPI preload                          │
│    └── _build_agents_from_session_scenario()                                │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SESSION AGENT MANAGER                               │
│  agentstore/session_manager.py → SessionAgentManager                        │
│    ├── SessionAgentConfig (per-session overrides)                           │
│    ├── SessionAgentRegistry (agents + handoff_map + active)                 │
│    └── AgentProvider / HandoffProvider protocols                            │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AGENT ADAPTATION                                │
│  voicelive/agent_adapter.py → VoiceLiveAgentAdapter                         │
│    ├── Wraps UnifiedAgent for VoiceLive SDK                                 │
│    ├── _build_function_tools() → FunctionTool[]                             │
│    └── apply_session() / trigger_response()                                 │
│                                                                              │
│  (Cascade mode uses UnifiedAgent directly)                                  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ORCHESTRATORS                                   │
│  voicelive/orchestrator.py → LiveOrchestrator (2147 lines)                  │
│  speech_cascade/orchestrator.py → CascadeOrchestratorAdapter (2060 lines)   │
│    ├── handle_event() / process_turn()                                      │
│    ├── _execute_tool_call() / _execute_handoff()                            │
│    ├── HandoffService (shared)                                              │
│    └── MemoManager sync at turn boundaries                                  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             HANDOFF SERVICE                                  │
│  shared/handoff_service.py → HandoffService                                 │
│    ├── resolve_handoff() → HandoffResolution                                │
│    ├── select_greeting()                                                    │
│    └── build_handoff_system_vars() (from handoffs/context.py)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Pain Points Analysis

### 1. **Unnecessary Abstraction Layers**

| Layer | File | Purpose | Issue |
|-------|------|---------|-------|
| `ScenarioConfig` | scenariostore/loader.py | Define agent graph + handoffs | ✅ Necessary |
| `OrchestratorConfigResult` | shared/config_resolver.py | Resolve scenario at startup | ⚠️ Could be simpler |
| `SessionAgentManager` | agentstore/session_manager.py | Per-session agent overrides | ❌ Rarely used in practice |
| `VoiceLiveAgentAdapter` | voicelive/agent_adapter.py | Wrap UnifiedAgent for SDK | ⚠️ Could be merged into UnifiedAgent |
| `HandoffService` | shared/handoff_service.py | Resolve handoff routing | ✅ Necessary but duplicated lookups |
| `HandoffResolution` | shared/handoff_service.py | Result DTO | ✅ Useful |

**Impact**: Each layer adds function call overhead, memory allocations, and cognitive load for developers.

**Recommendation**: 
- Merge `VoiceLiveAgentAdapter` capabilities into `UnifiedAgent` as a `to_voicelive_session()` method
- Simplify `SessionAgentManager` to a thin wrapper or remove if not actively used
- Consider direct scenario-to-orchestrator binding without intermediate resolver

---

### 2. **Hot Path Latency Issues**

#### VoiceLive Hot Path (audio event → response)
```python
# Current hot path in LiveOrchestrator._handle_transcription_completed()
async def _handle_transcription_completed(self, event):
    # 1. Parse transcript (fast)
    user_text = event.transcript.strip()
    
    # 2. Append to history deque (fast)
    self._user_message_history.append(user_text)
    
    # 3. Persist to MemoManager (potential I/O) ❌
    self._memo_manager.append_to_history(self.active, "user", user_text)
    
    # 4. Mark pending session update ✅ (deferred correctly)
    self._pending_session_update = True
```

**Issue**: `_memo_manager.append_to_history()` is called synchronously on the hot path. While MemoManager operations are in-memory, they trigger dict updates that can add latency.

**Location**: [orchestrator.py#L755-L765](apps/artagent/backend/voice/voicelive/orchestrator.py#L755-L765)

#### Cascade Hot Path
```python
# Current hot path in CascadeOrchestratorAdapter.process_turn()
# Called for EVERY user turn

# 1. Build messages (many dict operations)
messages = self._build_messages(context, agent)

# 2. Get tools (calls agent.get_tools() → tool registry lookup)
tools = agent.get_tools()  # Repeated every turn!

# 3. Process LLM (streaming)
response_text, tool_calls = await self._process_llm(...)
```

**Issue**: `agent.get_tools()` rebuilds the tool list every turn. Tools rarely change mid-session.

**Location**: [orchestrator.py#L645-L657](apps/artagent/backend/voice/speech_cascade/orchestrator.py#L645-L657)

---

### 3. **Greeting Logic Complexity**

Greeting selection is scattered across multiple locations:

| Location | Method | Responsibility |
|----------|--------|----------------|
| `UnifiedAgent` | `render_greeting()` / `render_return_greeting()` | Jinja template rendering |
| `VoiceLiveAgentAdapter` | `render_greeting()` | Delegates to UnifiedAgent |
| `LiveOrchestrator` | `_select_pending_greeting()` | Selects which greeting to use |
| `HandoffService` | `select_greeting()` | Unified greeting selection |
| `handoffs/context.py` | `build_handoff_system_vars()` | Sets `greet_on_switch` flag |

**Issue**: 5 different places touch greeting logic, making it hard to understand the actual flow.

**Current Flow**:
```
1. HandoffService.resolve_handoff() sets greet_on_switch from ScenarioConfig
2. LiveOrchestrator._switch_to() calls _select_pending_greeting()
3. _select_pending_greeting() delegates to HandoffService.select_greeting()
4. select_greeting() calls agent.render_greeting() or render_return_greeting()
5. Result stored in self._pending_greeting for later use
```

**Recommendation**: Consolidate into a single `GreetingResolver` or move all logic into `HandoffService`.

---

### 4. **Redundant Handoff Resolution**

Both orchestrators now use `HandoffService`, but still maintain:
- Local `handoff_map` copies
- `_handoff_provider` references
- Fallback lookups that duplicate `HandoffService` logic

**VoiceLive (orchestrator.py)**:
```python
def get_handoff_target(self, tool_name: str) -> str | None:
    if self._handoff_provider:  # Why check provider if HandoffService exists?
        return self._handoff_provider.get_handoff_target(tool_name)
    return self._handoff_map.get(tool_name)
```

**Recommendation**: Remove `_handoff_provider` and `_handoff_map` from orchestrators; rely solely on `HandoffService`.

---

### 5. **Session State Sync Complexity**

Both orchestrators implement similar but slightly different sync patterns:

| Operation | VoiceLive | Cascade |
|-----------|-----------|---------|
| Sync from memo at init | `_sync_from_memo_manager()` | `sync_from_memo_manager()` |
| Sync to memo at turn end | `_sync_to_memo_manager()` | `sync_to_memo_manager()` |
| Background sync | `_schedule_background_sync()` | `_persist_to_redis_background()` |
| Throttling | Yes (`_session_update_min_interval`) | No |

**Good**: Shared utilities exist in `session_state.py`

**Issue**: Orchestrators still have ~100 lines each of sync logic that could be further consolidated.

---

### 6. **Tool Registry Lookup on Hot Path**

```python
# In agent.get_tools() - called every turn
def get_tools(self) -> list[dict[str, Any]]:
    from apps.artagent.backend.registries.toolstore import get_tools_for_agent, initialize_tools
    initialize_tools()  # Repeated check every call
    self._load_custom_tools()  # Module import check
    return get_tools_for_agent(self.tool_names)
```

**Issue**: `initialize_tools()` is called on every `get_tools()` invocation, even though tools are immutable after startup.

**Location**: [base.py#L257-L263](apps/artagent/backend/registries/agentstore/base.py#L257-L263)

---

## Detailed Component Analysis

### A. ScenarioStore (scenariostore/loader.py)

**Lines**: ~470
**Purpose**: Load and parse scenario YAML files

**Strengths**:
- Clean dataclass-based config models
- Good separation of `ScenarioConfig`, `HandoffConfig`, `GenericHandoffConfig`
- Single source of truth for handoff routing

**Issues**:
1. `get_handoff_config()` creates new `HandoffConfig` objects on every call
2. `_discover_scenarios()` runs on first access (lazy loading) but could be pre-warmed

**Recommendation**: Pre-compute handoff lookup tables in `ScenarioConfig` constructor.

---

### B. AgentStore (agentstore/)

#### loader.py (~280 lines)
**Purpose**: Discover and load agent YAML files

**Strengths**:
- Clean YAML parsing with defaults
- Supports mode-specific models (`cascade_model`, `voicelive_model`)

**Issues**:
1. `discover_agents()` is called multiple times without caching at module level
2. `_load_custom_tools()` does module import on every agent access

#### session_manager.py (~700 lines)
**Purpose**: Per-session agent configuration overrides

**Strengths**:
- Clean protocol definitions (`AgentProvider`, `HandoffProvider`)
- Experiment tracking for A/B testing

**Issues**:
1. **Rarely used in practice** - most sessions use base agents
2. Heavy initialization for features that may not be needed
3. Redis persistence logic duplicated from MemoManager

**Recommendation**: Make `SessionAgentManager` opt-in or lazy-load only when overrides are detected.

---

### C. VoiceLive Orchestrator (2147 lines)

**Hot Path Methods**:
- `handle_event()` - Event dispatch (~15 lines, fast)
- `_handle_transcription_completed()` - User speech done (~40 lines)
- `_execute_tool_call()` - Tool execution (~200 lines)
- `_switch_to()` - Agent switch (~150 lines)

**Cold Path Methods**:
- `start()` - Session initialization
- `update_scenario()` - Scenario change
- Telemetry/metrics emission

**Issues**:
1. `_update_session_context()` rebuilds conversation recap on every call
2. `_inject_conversation_history()` creates SDK objects repeatedly
3. Agent registry updates trigger background `asyncio.create_task()` without cleanup tracking

---

### D. Cascade Orchestrator (2060 lines)

**Hot Path Methods**:
- `process_turn()` - Main turn processing (~200 lines)
- `_process_llm()` - LLM streaming (~350 lines)
- `_execute_handoff()` - Agent switch (~100 lines)

**Issues**:
1. `_build_messages()` recreates conversation history list every turn
2. `_record_turn()` does redundant history appends
3. Session context copied multiple times (`_build_session_context()` + parameter passing)

---

## Layer Absorption Plan

### Current Layer Stack (6 layers)

```
Layer 6: Orchestrator (LiveOrchestrator / CascadeOrchestratorAdapter)
Layer 5: HandoffService (handoff resolution)
Layer 4: VoiceLiveAgentAdapter (SDK wrapper) ← REMOVE
Layer 3: SessionAgentManager (per-session overrides) ← MAKE OPTIONAL
Layer 2: OrchestratorConfigResult (config resolution) ← SIMPLIFY
Layer 1: ScenarioConfig + UnifiedAgent (core definitions) ← KEEP
```

### Target Layer Stack (3 layers)

```
Layer 3: Orchestrator (uses UnifiedAgent directly)
Layer 2: HandoffService (handoff resolution, greeting selection)
Layer 1: ScenarioConfig + UnifiedAgent (with VoiceLive capabilities built-in)
```

---

## Absorption Strategy 1: Merge VoiceLiveAgentAdapter into UnifiedAgent

### Why
`VoiceLiveAgentAdapter` wraps `UnifiedAgent` but only adds:
1. VoiceLive-specific session building (`apply_session()`)
2. Tool conversion to `FunctionTool` objects
3. Voice payload building

These are SDK-specific serialization concerns that can live as methods on `UnifiedAgent`.

### Current (340 lines in agent_adapter.py)
```python
# agent_adapter.py
class VoiceLiveAgentAdapter:
    def __init__(self, agent: UnifiedAgent):
        self._agent = agent
        # Parse session configuration
        sess = agent.session or {}
        self.modalities = _mods(sess.get("modalities"))
        ...
    
    async def apply_session(self, conn, *, system_vars=None, ...):
        # Build RequestSession and call conn.session.update()
        ...
    
    def _build_function_tools(self) -> list[FunctionTool]:
        # Convert tool schemas to VoiceLive FunctionTool
        ...
```

### Proposed (Add to UnifiedAgent in base.py)
```python
# base.py - UnifiedAgent
class UnifiedAgent:
    # ... existing code ...
    
    # ═══════════════════════════════════════════════════════════════════
    # VOICELIVE SDK INTEGRATION
    # ═══════════════════════════════════════════════════════════════════
    
    def to_voicelive_session(
        self, 
        system_vars: dict[str, Any] | None = None,
    ) -> "RequestSession":
        """
        Build VoiceLive RequestSession from agent configuration.
        
        This is the SDK serialization layer - no separate adapter needed.
        """
        from azure.ai.voicelive.models import (
            RequestSession, FunctionTool, AzureStandardVoice, ...
        )
        
        instructions = self.render_prompt(system_vars or {})
        voice_payload = self._build_voice_payload()
        tools = self._build_voicelive_tools()
        
        return RequestSession(
            modalities=self._parse_modalities(),
            instructions=instructions,
            voice=voice_payload,
            tools=tools,
            ...
        )
    
    def _build_voicelive_tools(self) -> list["FunctionTool"]:
        """Convert tool schemas to VoiceLive FunctionTool objects."""
        from azure.ai.voicelive.models import FunctionTool
        return [
            FunctionTool(
                name=t["function"]["name"],
                description=t["function"]["description"],
                parameters=t["function"]["parameters"],
            )
            for t in self.get_tools()
            if t.get("type") == "function"
        ]
    
    def _build_voice_payload(self) -> "AzureStandardVoice | None":
        """Build VoiceLive voice configuration."""
        if not self.voice.name:
            return None
        from azure.ai.voicelive.models import AzureStandardVoice
        return AzureStandardVoice(
            name=self.voice.name,
            style=self.voice.style,
            rate=self.voice.rate,
            pitch=self.voice.pitch,
        )
```

### Migration Steps
1. Add VoiceLive methods to `UnifiedAgent` (guarded by try/except for SDK import)
2. Update `LiveOrchestrator` to call `agent.to_voicelive_session()` directly
3. Deprecate `VoiceLiveAgentAdapter` with warning
4. Remove `agent_adapter.py` in next release

### Lines Removed: ~340

---

## Absorption Strategy 2: Make SessionAgentManager Opt-In

### Why
`SessionAgentManager` provides per-session agent overrides (prompt, voice, tools), but:
- Most sessions use base agents without modification
- 700 lines of code initialized for every session
- Adds `AgentProvider` / `HandoffProvider` protocol indirection

### Current Usage Pattern
```python
# In orchestrator initialization
self._session_agent_manager = SessionAgentManager(
    session_id=session_id,
    base_agents=discover_agents(),
    memo_manager=memo,
)
# Then used as: self._session_agent_manager.get_agent(name)
```

### Proposed: Lazy Initialization
```python
# In orchestrator
@property
def session_agent_manager(self) -> SessionAgentManager | None:
    """Lazily create SessionAgentManager only when overrides are detected."""
    if self._session_agent_manager is None:
        # Check if session has any overrides stored
        if self._memo_manager and self._has_session_overrides():
            self._session_agent_manager = SessionAgentManager(...)
    return self._session_agent_manager

def get_agent(self, name: str) -> UnifiedAgent:
    """Get agent, preferring session overrides if available."""
    if self.session_agent_manager:
        return self.session_agent_manager.get_agent(name)
    return self._base_agents[name]

def _has_session_overrides(self) -> bool:
    """Check if MemoManager has stored agent overrides."""
    registry = self._memo_manager.get_context("agent_registry")
    if not registry:
        return False
    # Check if any agent has non-default config
    for config in registry.get("agents", {}).values():
        if config.get("modification_count", 0) > 0:
            return True
    return False
```

### Alternative: Remove Entirely
If `SessionAgentManager` is truly unused:
1. Audit codebase for `SessionAgentManager` usage
2. If only used in tests, mark as test-only utility
3. Remove from hot path entirely

### Lines Saved: ~700 (or moved to optional module)

---

## Absorption Strategy 3: Simplify Config Resolution

### Why
`config_resolver.py` does:
1. Environment variable lookup (`AGENT_SCENARIO`)
2. Session scenario lookup
3. Agent registry loading
4. Handoff map building

This can be simplified into direct scenario loading.

### Current (350 lines)
```python
# config_resolver.py
def resolve_orchestrator_config(
    session_id: str | None = None,
    scenario_name: str | None = None,
    ...
) -> OrchestratorConfigResult:
    # Check session scenario
    # Check environment
    # Load from scenario store
    # Build handoff map
    # Return result object
    ...
```

### Proposed: Inline into Orchestrator
```python
# In orchestrator __init__ or factory
def _resolve_config(self) -> None:
    """Resolve scenario and load agents."""
    # 1. Determine scenario name
    scenario_name = (
        self._get_session_scenario_name() or
        os.getenv("AGENT_SCENARIO") or
        None
    )
    
    # 2. Load scenario if specified
    if scenario_name:
        from apps.artagent.backend.registries.scenariostore import load_scenario
        self._scenario = load_scenario(scenario_name)
    
    # 3. Load agents (scenario-filtered or all)
    from apps.artagent.backend.registries.agentstore import discover_agents
    base_agents = discover_agents()
    
    if self._scenario and self._scenario.agents:
        self._agents = {k: v for k, v in base_agents.items() if k in self._scenario.agents}
    else:
        self._agents = base_agents
    
    # 4. Build handoff map from scenario
    self._handoff_map = self._scenario.build_handoff_map() if self._scenario else {}
    
    # 5. Set start agent
    self._active_agent = self._scenario.start_agent if self._scenario else "BankingConcierge"
```

### Benefit
- No intermediate `OrchestratorConfigResult` object
- No separate module to maintain
- Logic is visible where it's used

### Lines Removed: ~350

---

## Absorption Strategy 4: Unify Handoff State

### Why
Both orchestrators maintain redundant handoff state:
```python
# LiveOrchestrator
self._handoff_provider = handoff_provider  # Protocol for lookups
self._handoff_map = handoff_map or {}      # Static fallback
self._handoff_service = None               # Lazy-loaded service

# CascadeOrchestratorAdapter  
self._handoff_provider = None              # Same pattern
self.handoff_map = {}                      # Same redundancy
self._handoff_service = None               # Same lazy service
```

### Proposed: Single Source of Truth
```python
# In both orchestrators
def __init__(self, ...):
    # HandoffService IS the single source of truth
    self._handoff_service = HandoffService(
        scenario_name=scenario_name,
        handoff_map=handoff_map,  # Passed once at init
        agents=agents,
    )
    # Remove: self._handoff_provider
    # Remove: self._handoff_map

def get_handoff_target(self, tool_name: str) -> str | None:
    """Delegate to HandoffService."""
    return self._handoff_service.get_handoff_target(tool_name)

@property
def handoff_map(self) -> dict[str, str]:
    """For backward compatibility only."""
    return self._handoff_service.handoff_map
```

### Lines Removed: ~50 per orchestrator (100 total)

---

## Summary: Absorption Impact

| Strategy | Files Affected | Lines Removed | Complexity Reduction |
|----------|---------------|---------------|---------------------|
| Merge VoiceLiveAgentAdapter into UnifiedAgent | agent_adapter.py, base.py | ~340 | High |
| Make SessionAgentManager opt-in | session_manager.py, orchestrators | ~700 (moved) | Medium |
| Simplify config resolution | config_resolver.py, orchestrators | ~350 | Medium |
| Unify handoff state | orchestrators | ~100 | Low |
| **Total** | | **~1500** | **High** |

---

## Implementation Order

### Phase 1: Low-Risk Simplifications (Week 1)
1. Unify handoff state in both orchestrators
2. Remove `_handoff_provider` / `_handoff_map` redundancy
3. Add tool caching to `UnifiedAgent.get_tools()`

### Phase 2: VoiceLiveAgentAdapter Absorption (Week 2)
1. Add `to_voicelive_session()` to `UnifiedAgent`
2. Update `LiveOrchestrator` to use it directly
3. Deprecate `VoiceLiveAgentAdapter`
4. Update tests

### Phase 3: Config Resolution Simplification (Week 3)
1. Inline config resolution into orchestrators
2. Remove `OrchestratorConfigResult` class
3. Deprecate `config_resolver.py`

### Phase 4: SessionAgentManager (Week 4)
1. Audit actual usage patterns
2. Either make lazy/opt-in or remove if unused
3. Update documentation

---

## Recommendations Summary

### Quick Wins (Low Risk, High Impact)

| Item | Effort | Impact | Files |
|------|--------|--------|-------|
| Cache `agent.get_tools()` result after first call | 1h | Medium | base.py |
| Remove `initialize_tools()` guard from hot path | 30m | Low | base.py |
| Pre-compute `ScenarioConfig.handoff_lookup` | 2h | Medium | scenariostore/loader.py |
| Remove `_handoff_provider` / `_handoff_map` from orchestrators | 2h | Low | orchestrator.py (both) |

### Medium-Term Simplifications

| Item | Effort | Impact | Files |
|------|--------|--------|-------|
| Merge `VoiceLiveAgentAdapter` into `UnifiedAgent` | 4h | Medium | agent_adapter.py, base.py |
| Consolidate greeting logic into `HandoffService` | 4h | High | orchestrator.py (both), handoff_service.py |
| Make `SessionAgentManager` opt-in/lazy | 3h | Low | session_manager.py |
| Remove `config_resolver.py` - inline into orchestrators | 3h | Medium | config_resolver.py, orchestrator.py |

### Larger Refactors (Future Consideration)

| Item | Effort | Impact | Description |
|------|--------|--------|-------------|
| Unified Orchestrator Base Class | 2-3d | High | Extract common patterns into abstract base |
| Event-Based State Machine | 1w | High | Replace procedural handoff logic with FSM |
| Scenario as First-Class Concept | 1w | High | Scenarios own agents rather than filtering them |

---

## Hot Path Optimization Checklist

### VoiceLive Mode

- [ ] Move MemoManager writes to background task in `_handle_transcription_completed()`
- [ ] Cache `agent.get_tools()` on agent switch only
- [ ] Pre-build `RequestSession` objects in `VoiceLiveAgentAdapter`
- [ ] Pool `FunctionTool` objects instead of rebuilding
- [ ] Throttle `_update_session_context()` more aggressively (currently 2s)

### Cascade Mode

- [ ] Reuse `messages` list across turns (append-only)
- [ ] Cache `tools` list at adapter level
- [ ] Avoid `json.dumps()`/`json.loads()` for tool call history storage
- [ ] Pre-allocate `OrchestratorResult` object

---

## File Reference Map

| Component | File | Lines | Hot Path? |
|-----------|------|-------|-----------|
| Scenario Config | `scenariostore/loader.py` | ~470 | No |
| Agent Base | `agentstore/base.py` | ~530 | Yes |
| Agent Loader | `agentstore/loader.py` | ~280 | No |
| Session Manager | `agentstore/session_manager.py` | ~700 | No |
| VoiceLive Adapter | `voicelive/agent_adapter.py` | ~340 | Yes |
| VoiceLive Orchestrator | `voicelive/orchestrator.py` | ~2150 | **Yes** |
| Cascade Orchestrator | `speech_cascade/orchestrator.py` | ~2060 | **Yes** |
| Handoff Service | `shared/handoff_service.py` | ~470 | Yes |
| Handoff Context | `handoffs/context.py` | ~220 | Yes |
| Session State | `shared/session_state.py` | ~230 | No |
| Config Resolver | `shared/config_resolver.py` | ~350 | No |

---

## Next Steps

1. **Review & Prioritize**: Discuss which items to tackle first based on current pain points
2. **Benchmark**: Add latency instrumentation to hot path methods to measure improvement
3. **Incremental Implementation**: Start with quick wins to build confidence
4. **Test Coverage**: Ensure existing tests pass before/after each change

---

## Implementation Progress

### ✅ Completed Items

#### 1. Contract Tests Created
- Created `tests/test_scenario_orchestration_contracts.py` with **35 comprehensive tests**
- Test classes cover all key functional contracts:
  - `TestUnifiedAgentPromptRendering` - Prompt template rendering
  - `TestUnifiedAgentGreetingRendering` - Greeting selection logic
  - `TestUnifiedAgentToolRetrieval` - Tool registry integration
  - `TestVoiceLiveAgentAdapterConstruction` - Adapter initialization
  - `TestHandoffServiceContracts` - Handoff resolution
  - `TestScenarioConfigContracts` - Scenario configuration
  - `TestConfigResolutionContracts` - Config resolution paths
  - `TestOrchestrationFlowContracts` - Full orchestration flows
  - `TestVADConfigurationContracts` - VAD/turn detection config

#### 2. Strategy 4: Unified Handoff State ✅
- **Finding**: Already unified! `HandoffService` is the single source of truth
- `visited_agents` tracking works via `session_state.py` (`sync_state_from_memo` / `sync_state_to_memo`)
- No changes needed - existing design is correct

#### 3. Strategy 1: VoiceLiveAgentAdapter Merged into UnifiedAgent ✅
- Added ~250 lines of VoiceLive SDK methods to `UnifiedAgent` in `base.py`:
  - `build_voicelive_tools()` - Converts tool schemas to `FunctionTool` objects
  - `build_voicelive_voice()` - Builds `AzureStandardVoice` configuration
  - `build_voicelive_vad()` - Builds VAD/turn detection config
  - `get_voicelive_modalities()` - Returns `Modality` enums
  - `get_voicelive_audio_formats()` - Returns audio format enums
  - `apply_voicelive_session()` - Applies agent config to VoiceLive connection
  - `trigger_voicelive_response()` - Triggers verbatim greeting response
- Updated `VoiceLiveAgentAdapter` to delegate to `UnifiedAgent` methods
- Adapter is now a deprecated thin wrapper (backward compatibility preserved)
- All 123 tests passing (35 contract + 88 existing)

#### 4. Strategy 3: Simplify Config Resolution - **Revised Assessment** ✅
After detailed analysis, **full elimination is NOT recommended**. The `config_resolver.py` module serves important purposes:

**Why It's Needed:**
1. Supports **4 resolution paths** that are all actively used:
   - Session-scoped scenarios (ScenarioBuilder API)
   - Environment variable (`AGENT_SCENARIO`)  
   - FastAPI app.state preloading
   - Explicit parameter overrides
2. Encapsulates **complex scenario loading logic** including:
   - Base agent discovery and filtering
   - Handoff map building from scenario
   - Template variable inheritance
3. Used in **5+ locations** across codebase:
   - `media_handler.py`, `handler.py` (VoiceLive), `orchestrator.py` (Cascade)
   - `unified/__init__.py`, tests

**Revised Recommendation:**
Instead of removing, apply **targeted simplifications**:
1. ✅ Keep `OrchestratorConfigResult` as a clean DTO
2. ⚠️ Merge `resolve_from_app_state()` into `resolve_orchestrator_config()` as an optional `app_state` parameter
3. ⚠️ Simplify priority order documentation
4. ⚠️ Add caching for repeated calls within same request

#### 5. Strategy 2: SessionAgentManager Audit ✅
**Finding: `SessionAgentManager` is NOT used in production!**

| Component | Used in Production? | Action |
|-----------|---------------------|--------|
| `SessionAgentManager` | ❌ No (tests only) | Keep for future extensibility |
| `SessionAgentConfig` | ❌ No (tests only) | Keep for future extensibility |
| `_handoff_provider` in orchestrators | ❌ Always None | **REMOVED** |
| `HandoffProvider` protocol | Type hint only | Keep as API contract |

**Changes Made:**
- Removed `_handoff_provider` field from `LiveOrchestrator` and `CascadeOrchestratorAdapter`
- Removed `handoff_provider` parameter from `LiveOrchestrator.__init__()` and `CascadeOrchestratorAdapter.create()`
- Removed `set_handoff_provider()` method from `CascadeOrchestratorAdapter`
- Removed unused `HandoffProvider` imports from both orchestrators
- All 151 tests passing (35 contract + 81 handoff + 35 voicelive)

### 📋 Remaining Work (Future Improvements)

- ⚠️ Merge `resolve_from_app_state()` into `resolve_orchestrator_config()`
- ⚠️ Add request-scoped caching for config resolution
- ⚠️ Consider shared `OrchestratorBase` abstract class

---

## Open Questions

1. ~~Is `SessionAgentManager` actively used? Can we deprecate?~~ **RESOLVED: Not used in production, but kept for future extensibility**
2. ~~Should `VoiceLiveAgentAdapter` be absorbed into `UnifiedAgent` or kept separate for SDK isolation?~~ **RESOLVED: Absorbed with deprecation notice**
3. Is the 2-second throttle on `_update_session_context()` appropriate for all scenarios?
4. Should we consider a shared `OrchestratorBase` abstract class?

---

*Document created: December 15, 2025*
*Last updated: December 15, 2025*
