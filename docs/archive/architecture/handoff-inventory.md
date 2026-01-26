# Handoff Logic Inventory

Quick map of where handoff logic is defined or reused across `backend/voice` and `backend/agents`.

> **Status**: Phase 4 completed (Dec 2024). Removed unused HandoffStrategy enum.
> See [Cleanup History](#cleanup-history) for details.

---

## Single Source of Truth: Agent YAMLs → `build_handoff_map()`

The **authoritative** handoff_map is now built dynamically from agent YAML declarations:

```
Agent YAMLs (handoff.trigger)
        ↓
agents/loader.py → build_handoff_map(agents)
        ↓
SessionAgentManager (implements HandoffProvider)
        ↓
Orchestrators (via handoff_provider or static fallback)
```

**Key function**: `apps/artagent/backend/agents/loader.py::build_handoff_map()`

```python
def build_handoff_map(agents: Dict[str, UnifiedAgent]) -> Dict[str, str]:
    """Build handoff map from agent declarations."""
    handoff_map = {}
    for agent in agents.values():
        if agent.handoff.trigger:
            handoff_map[agent.handoff.trigger] = agent.name
    return handoff_map
```

---

## HandoffProvider Protocol

Orchestrators can now accept a `HandoffProvider` for live handoff lookups:

```python
class HandoffProvider(Protocol):
    def get_handoff_target(self, tool_name: str) -> Optional[str]: ...
    @property
    def handoff_map(self) -> Dict[str, str]: ...
    def is_handoff_tool(self, tool_name: str) -> bool: ...
```

**Implementations**:
- `SessionAgentManager` — per-session handoff resolution with update support
- Orchestrators use `get_handoff_target()` method instead of direct map access

---

## Agent Definitions & Registry
- `apps/artagent/backend/agents/base.py`
  - `HandoffConfig` (trigger, is_entry_point) and helpers: `get_handoff_tools()`, `can_handoff_to()`, `is_handoff_target()`, `handoff_trigger`, and `build_handoff_map(agents)`.
- `apps/artagent/backend/agents/loader.py`
  - Parses YAML (`handoff` block or legacy `handoff_trigger`) via `_extract_handoff_config`.
  - **`build_handoff_map()`** — single source for tool → agent mappings.
- `apps/artagent/backend/agents/_defaults.yaml`
  - Default handoff settings (no defaults - each agent defines its own trigger).
- `apps/artagent/backend/agents/tools/registry.py`
  - Tool metadata includes `is_handoff`; `is_handoff_tool(name)` and `list_tools(..., handoffs_only=True)`.
  - Handoff tools registered in `agents/tools/handoffs.py`.
- Agent YAMLs (e.g., `concierge`, `fraud_agent`, `card_recommendation`, `investment_advisor`, `custom_agent`, `compliance_desk`) declare `handoff.trigger` and outbound handoff tools.

## Session & State
- `apps/artagent/backend/agents/session_manager.py`
  - Wraps base agents + `handoff_map` into per-session registry; exposes `is_handoff_tool`, `get_handoff_target`, `update_handoff_map`, `remove_handoff`.
  - Calls `build_handoff_map()` at session creation.

## Orchestration (Voice)
- `apps/artagent/backend/voice/handoffs/__init__.py`
  - Exports: `HandoffContext`, `HandoffResult`, `build_handoff_system_vars`, `sanitize_handoff_context`
  - ~~Strategies removed~~ — see Cleanup History
- `apps/artagent/backend/voice/handoffs/context.py`
  - Dataclasses for `HandoffContext` (source/target/reason/context data) and `HandoffResult`.
  - **`sanitize_handoff_context()`** — removes control flags from raw handoff context
  - **`build_handoff_system_vars()`** — builds system_vars dict for agent switches (used by LiveOrchestrator)
- `apps/artagent/backend/voice/speech_cascade/orchestrator.py`
  - Local shim re-exporting `CascadeOrchestratorAdapter` to keep cascade orchestration discoverable next to the handler.
- `apps/artagent/backend/voice/orchestrators/config_resolver.py`
  - Builds or injects `handoff_map` for voice orchestrators; falls back to agent loader or `app.state`.
- `apps/artagent/backend/voice/orchestrators/live_orchestrator.py`
  - VoiceLive path: accepts optional `handoff_provider` parameter for live lookups
  - Uses `get_handoff_target(tool_name)` method for handoff resolution
  - Falls back to static `handoff_map` if no provider given (backward compatible)
- `apps/artagent/backend/voice/orchestrators/cascade_adapter.py`
  - Speech cascade path: uses `get_handoff_target()` and `is_handoff_tool()` helper methods
  - Separates handoff vs non-handoff tools, executes `_execute_handoff`
- `apps/artagent/backend/voice/voicelive/handler.py`
  - Uses `build_handoff_map(agents)` as fallback when no `app_state.handoff_map` is available.

## Prompts & Context
- Agent prompt templates reference `handoff_context` variables to tailor greetings and continuity.

---

## Cleanup History

### Phase 1: Remove Unused Strategy Pattern (Dec 2024)

**Problem**: The `voice/handoffs/strategies/` folder contained ~600 lines of code that was **never instantiated**:
- `ToolBasedHandoff` class — designed for VoiceLive but handoff logic is inline in `LiveOrchestrator`
- `StateBasedHandoff` class — designed for Cascade but handoff logic is inline in `CascadeOrchestratorAdapter`
- `HANDOFF_MAP` static dict in `registry.py` — duplicated agent YAML declarations

**Resolution**: Deleted unused files:
```
DELETED: apps/artagent/backend/voice/handoffs/strategies/  (entire folder)
         ├── __init__.py
         ├── base.py        # HandoffStrategy ABC
         ├── tool_based.py  # ToolBasedHandoff class
         └── state_based.py # StateBasedHandoff class

DELETED: apps/artagent/backend/voice/handoffs/registry.py  (static HANDOFF_MAP)
```

**Updated exports**:
- `voice/handoffs/__init__.py` — now exports only `HandoffContext`, `HandoffResult`, `HandoffStrategy`
- `voice/orchestrators/__init__.py` — removed strategy class re-exports
- `voice/__init__.py` — removed strategy class re-exports
- `voice/voicelive/handler.py` — replaced static `HANDOFF_MAP` with `build_handoff_map(agents)`

**Lines removed**: ~600

### Phase 2: Orchestrators Support HandoffProvider (Dec 2024)

**Problem**: `handoff_map` was copied to multiple places, preventing runtime updates:
1. `SessionAgentRegistry.handoff_map` (per-session copy)
2. `LiveOrchestrator.handoff_map` (instance copy)
3. `CascadeOrchestratorAdapter.handoff_map` (instance copy)

**Resolution**: Orchestrators now support `HandoffProvider` protocol for live lookups:

```python
# LiveOrchestrator now accepts optional handoff_provider
orchestrator = LiveOrchestrator(
    conn=connection,
    agents=agents,
    handoff_map=fallback_map,  # Optional: static fallback
    handoff_provider=session_manager,  # Optional: live lookups
    ...
)

# Internally uses get_handoff_target() for resolution
target = self.get_handoff_target(tool_name)  # Prefers provider if available
```

**Changes**:
- `LiveOrchestrator.__init__()` — added `handoff_provider` parameter
- `LiveOrchestrator.get_handoff_target()` — new helper method
- `LiveOrchestrator.handoff_map` — property for backward compatibility
- `CascadeOrchestratorAdapter.get_handoff_target()` — new helper method
- `CascadeOrchestratorAdapter.is_handoff_tool()` — new helper method

**Benefit**: Session-level handoff_map updates (via `SessionAgentManager.update_handoff_map()`) now take effect immediately.

### Phase 3: Shared Handoff Context Builder (Dec 2024)

**Problem**: Both orchestrators independently built handoff context dicts with similar logic:
- Extract `previous_agent`, `handoff_reason`, `details` from tool result/args
- Auto-load user profile on `client_id`
- Sanitize control flags like `success`, `target_agent`, `handoff_summary`
- Carry forward session variables (`session_profile`, `client_id`, `customer_intelligence`)

**Resolution**: Extracted shared helpers to `voice/handoffs/context.py`:

```python
# sanitize_handoff_context() - removes control flags
raw = {"reason": "fraud inquiry", "success": True, "target_agent": "FraudAgent"}
clean = sanitize_handoff_context(raw)
# clean = {"reason": "fraud inquiry"}

# build_handoff_system_vars() - builds system_vars for agent.apply_session()
ctx = build_handoff_system_vars(
    source_agent="Concierge",
    target_agent="FraudAgent",
    tool_result={"handoff_summary": "User suspects fraud", ...},
    tool_args={"reason": "fraud inquiry"},
    current_system_vars={"session_profile": {...}, "client_id": "123"},
    user_last_utterance="I think my card was stolen",
)
```

**Changes**:
- `voice/handoffs/context.py` — added `sanitize_handoff_context()` and `build_handoff_system_vars()`
- `voice/handoffs/__init__.py` — exports new helper functions
- `voice/orchestrators/live_orchestrator.py` — uses `build_handoff_system_vars()` instead of inline context building
- Removed `_sanitize_handoff_context()` local helper (now in shared module)

**Lines reduced**: ~25 (inline logic replaced with shared helper call)

**Note**: CascadeAdapter uses a different pattern (`CascadeHandoffContext` dataclass + metadata dict) that works well for its use case, so it retains its current approach.

### Phase 4: Remove Unused HandoffStrategy Enum (Dec 2024)

**Problem**: The `HandoffStrategy` enum (`AUTO`, `TOOL_BASED`, `STATE_BASED`) was:
- Defined in `agents/base.py`
- Parsed from agent YAMLs (`handoff.strategy: auto`)
- Re-exported through multiple modules
- **Never actually used** — VoiceLive always uses tool-based handoffs, Cascade uses state-based

**Resolution**: Removed the enum and simplified agent YAMLs:

```yaml
# Before (strategy field was noise)
handoff:
  trigger: handoff_fraud_agent
  strategy: auto                     # Works with both orchestrators

# After (clean and simple)
handoff:
  trigger: handoff_fraud_agent
```

**Changes**:
- `agents/base.py` — removed `HandoffStrategy` enum, simplified `HandoffConfig` to just `trigger` and `is_entry_point`
- `agents/loader.py` — removed `get_agents_by_handoff_strategy()` function (never called)
- `agents/_defaults.yaml` — removed `strategy` and `state_key` defaults
- All agent YAMLs — removed `strategy: auto` lines
- `agents/__init__.py`, `voice/__init__.py`, `voice/orchestrators/__init__.py`, `voice/handoffs/__init__.py` — removed `HandoffStrategy` exports

**Lines removed**: ~60 (enum definition, parsing logic, filtering function, YAML lines)

---

## Summary

After all cleanup phases, the handoff system is now much simpler:

| Before | After |
|--------|-------|
| ~600 lines of unused strategy patterns | Deleted |
| `HandoffStrategy` enum (3 values, never used) | Removed |
| `get_agents_by_handoff_strategy()` (never called) | Removed |
| Inline context building in each orchestrator | Shared `build_handoff_system_vars()` |
| Static `handoff_map` copies | `HandoffProvider` protocol for live lookups |
| 3 duplicate `is_handoff_tool()` implementations | Consolidated to tool registry (Phase 5) |

**Total lines removed**: ~690

---

## Phase 5 Completed: `is_handoff_tool` Consolidation

### Changes Made

1. **CascadeOrchestratorAdapter** now imports `is_handoff_tool` from tool registry:
   ```python
   from apps.artagent.backend.agents.tools.registry import is_handoff_tool
   ```

2. **Removed duplicate method** from `CascadeOrchestratorAdapter`:
   - Deleted `is_handoff_tool(self, tool_name)` that checked `handoff_map`
   - Now uses module-level `is_handoff_tool(name)` from registry

3. **Kept `SessionAgentManager.is_handoff_tool()`** for different semantic:
   - Registry: "Is this tool TYPE a handoff?" (static, based on registration)
   - SessionAgentManager: "Can this session route this handoff?" (dynamic, may change)
   - The latter is needed for the `remove_handoff()` use case

### Current State

| Location | Checks | Purpose |
|----------|--------|---------|
| `agents/tools/registry.py::is_handoff_tool(name)` | Tool metadata `is_handoff` flag | **Primary source** - "is this tool a handoff type?" |
| `agents/session_manager.py::SessionAgentManager.is_handoff_tool()` | `handoff_map` keys | Session-aware - "can we route this?" |

### Pattern for Orchestrators

Both `LiveOrchestrator` and `CascadeOrchestratorAdapter` now use:
```python
from apps.artagent.backend.agents.tools.registry import is_handoff_tool

# Check if handoff tool, then get target
if is_handoff_tool(name):
    target = self.get_handoff_target(name)
    if not target:
        logger.warning("Handoff tool '%s' not in handoff_map", name)
```

---

## Remaining Complexity (Future Phases)

### Observation: Multiple `get_handoff_target()` Implementations

| Location | Source | Used By |
|----------|--------|---------|
| `LiveOrchestrator.get_handoff_target()` | HandoffProvider or `_handoff_map` | VoiceLive path |
| `CascadeOrchestratorAdapter.get_handoff_target()` | HandoffProvider or `handoff_map` | SpeechCascade path |
| `SessionAgentManager.get_handoff_target()` | `_registry.handoff_map` | Protocol implementation |

### Observation: `handoff_map` Copies

The map is stored in multiple places:

```
build_handoff_map(agents)  ← canonical source
        ↓
app.state.handoff_map  ← FastAPI startup
        ↓
OrchestratorConfigResult.handoff_map  ← config resolution
        ↓
├── LiveOrchestrator._handoff_map  ← fallback copy
├── CascadeOrchestratorAdapter.handoff_map  ← fallback copy
└── SessionAgentRegistry.handoff_map  ← per-session copy (live source)
```

**Status**: Both orchestrators now prefer `HandoffProvider` when available.

---

## Phase 6 Completed: HandoffProvider Support in CascadeAdapter

### Changes Made

1. **Added `HandoffProvider` support to `CascadeOrchestratorAdapter`**:
   - Added `_handoff_provider` field for session-aware lookups
   - Added `set_handoff_provider(provider)` method
   - Added `handoff_provider` parameter to `create()` factory

2. **Updated `get_handoff_target()` to prefer provider**:
   ```python
   def get_handoff_target(self, tool_name: str) -> Optional[str]:
       if self._handoff_provider:
           return self._handoff_provider.get_handoff_target(tool_name)
       return self.handoff_map.get(tool_name)
   ```

3. **Consistent pattern across both orchestrators**:
   - `LiveOrchestrator`: Uses `_handoff_provider` if set, falls back to `_handoff_map`
   - `CascadeOrchestratorAdapter`: Uses `_handoff_provider` if set, falls back to `handoff_map`

### Benefits

- **Session-aware handoffs**: Dynamic handoff_map updates (via `SessionAgentManager.update_handoff_map()`) take effect immediately
- **Backward compatible**: Existing code using static `handoff_map` continues to work
- **Single source of truth**: `SessionAgentRegistry.handoff_map` is the live source when provider is set

### Remaining Static Copies

These remain for backward compatibility but are now fallbacks only:
- `OrchestratorConfigResult.handoff_map` - Initial setup, passed to `SessionAgentManager`
- `LiveOrchestrator._handoff_map` - Fallback when no provider
- `CascadeOrchestratorAdapter.handoff_map` - Fallback when no provider

---

## Summary: All Phases Complete

| Phase | Description | Lines Removed |
|-------|-------------|---------------|
| 1 | Remove unused strategy patterns | ~600 |
| 2 | Add HandoffProvider protocol | 0 (added code) |
| 3 | Shared handoff context builder | ~25 |
| 4 | Remove unused HandoffStrategy enum | ~60 |
| 5 | Consolidate is_handoff_tool | ~5 |
| 6 | HandoffProvider in CascadeAdapter | 0 (added code) |

**Total lines removed**: ~690
