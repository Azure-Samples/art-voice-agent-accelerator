# 📚 Architecture Documentation Changelog

> **Status:** Phase 1-5 Complete ✅  
> **Last Updated:** December 4, 2025  
> **Branch:** v2/speech-orchestration-and-monitoring

---

## 🗂️ Folder Reorganization (December 4, 2025)

Reorganized architecture docs into logical topic folders:

### New Folder Structure

```
docs/architecture/
├── README.md                    # Overview
├── CHANGELOG-ARCHITECTURE.md    # This file
├── agents/                      # Agent-related docs
│   ├── README.md               ← agent-framework.md
│   └── handoffs.md             ← handoff-strategies.md
├── orchestration/               # Orchestration (existing)
│   ├── README.md
│   ├── cascade.md
│   └── voicelive.md
├── speech/                      # Speech services
│   ├── README.md               ← streaming-modes.md
│   ├── recognition.md          ← speech-recognition.md
│   └── synthesis.md            ← speech-synthesis.md
├── data/                        # Data & state
│   ├── README.md               ← session-management.md
│   └── flows.md                ← data-flows.md
├── acs/                         # ACS integration
│   ├── README.md               ← acs-flows.md
│   └── integrations.md         ← integrations.md
├── telemetry.md                 # Standalone
├── llm-orchestration.md         # Redirect page
└── archive/                     # Historical docs
```

---

## 🗂️ Documentation Consolidation (December 4, 2025)

Simplified architecture documentation structure for easier maintenance:

### Files Archived → `archive/`

| File | Reason |
|------|--------|
| `agent-configuration-proposal.md` | Implemented → see `agents/README.md` |
| `session-agent-config-proposal.md` | Implemented → `SessionAgentManager` exists |
| `microsoft-agent-framework-evaluation.md` | One-time evaluation, decision made |
| `SESSION_OPTIMIZATION_NOTES.md` | All items completed ✅ |
| `handoff-inventory.md` | All cleanup phases (1-6) completed |
| `backend-voice-agents-architecture.md` | Merged into `orchestration/README.md` |

### Files Renamed

| Old Name | New Name | Reason |
|----------|----------|--------|
| `TELEMETRY_PLAN.md` | `telemetry.md` | Now active reference doc |
| `DOCUMENTATION_UPDATE_PLAN.md` | `CHANGELOG-ARCHITECTURE.md` | Reflects purpose as changelog |

---

## 🔍 Validation Scan (December 4, 2025)

All completed tasks have been verified. Summary:

| Item | Status | Location |
|------|--------|----------|
| **Agent Framework** | ✅ | `agents/README.md` |
| **Handoff Strategies** | ✅ | `agents/handoffs.md` |
| **Orchestration Overview** | ✅ | `orchestration/README.md` |
| **Cascade Orchestrator** | ✅ | `orchestration/cascade.md` |
| **VoiceLive Orchestrator** | ✅ | `orchestration/voicelive.md` |
| **Streaming Modes** | ✅ | `speech/README.md` |
| **Speech Recognition** | ✅ | `speech/recognition.md` |
| **Speech Synthesis** | ✅ | `speech/synthesis.md` |
| **Session Management** | ✅ | `data/README.md` |
| **Data Flows** | ✅ | `data/flows.md` |
| **ACS Flows** | ✅ | `acs/README.md` |
| **Telephony Integration** | ✅ | `acs/integrations.md` |
| **Telemetry** | ✅ | `telemetry.md` |
| **Archive** | ✅ | `archive/` (6 docs) |

---

## 📊 Progress Summary

| Phase | Status | Deliverables |
|-------|--------|--------------|
| **Phase 1: Critical Docs** | ✅ Complete | `agent-framework.md`, `orchestration/`, `handoff-strategies.md` |
| **Phase 2: Code Cleanup** | ✅ Complete | `session_state.py` simplified, legacy code removed |
| **Phase 3: High Priority** | ✅ Complete | `session-management.md`, code optimizations (5 items) |
| **Phase 4: Medium Priority** | ✅ Complete | `streaming-modes.md`, `acs-flows.md`, doc consolidation |
| **Phase 5: Folder Reorg** | ✅ Complete | Topic-based folder structure, cross-ref updates |

---

## ✅ Completed Work (All Phases)

### Documentation Created

| Document | Location | Description |
|----------|----------|-------------|
| **Agent Framework** | [agents/README.md](agents/README.md) | Comprehensive guide to YAML-driven agent system |
| **Handoff Strategies** | [agents/handoffs.md](agents/handoffs.md) | Multi-agent routing patterns |
| **Orchestration Overview** | [orchestration/README.md](orchestration/README.md) | Dual orchestrator architecture |
| **Cascade Orchestrator** | [orchestration/cascade.md](orchestration/cascade.md) | SpeechCascade mode deep dive |
| **VoiceLive Orchestrator** | [orchestration/voicelive.md](orchestration/voicelive.md) | VoiceLive mode deep dive |
| **Streaming Modes** | [speech/README.md](speech/README.md) | Phone/Browser channel coverage |
| **Session Management** | [data/README.md](data/README.md) | MemoManager, Redis patterns |
| **Telemetry** | [telemetry.md](telemetry.md) | OpenTelemetry, App Insights, SLOs |

### Documentation Updated

| Document | Changes |
|----------|---------|
| **handoff-strategies.md** | Modernized to reflect tool-based handoffs, `build_handoff_map()`, new code examples |
| **llm-orchestration.md** | Converted to redirect page pointing to new orchestration docs |
| **docs/legacy/mkdocs.yml** | Updated navigation with new structure |

### Code Simplified (Phase 2 & 3)

| File | Changes | Lines Removed |
|------|---------|---------------|
| **session_state.py** | Removed frivolous `hasattr` checks, dead legacy code | ~27 lines |
| **state_managment.py** | Removed dead `enable_auto_refresh` code | ~35 lines |
| **state_managment.py** | Fixed `from_redis_with_manager()` placeholder bug | Bug fix |
| **state_managment.py** | Added persist task lifecycle management | +40 lines |
| **session_loader.py** | Consolidated duplicate mock profiles | ~46 lines |
| **CascadeHandoffContext** | Added clarifying docstring about intentional divergence | +5 lines |

### Test Coverage Added

| Test File | Tests | Status |
|-----------|-------|--------|
| **test_memo_optimization.py** | 11 tests | ✅ All passing |

---

## 🎯 Executive Summary

This plan outlines a comprehensive documentation update to align the `docs/architecture/` section with the current codebase. The backend has evolved significantly with the **Unified Agent Framework**, **dual orchestration modes** (SpeechCascade + VoiceLive), and improved **session management**. This update ensures documentation accuracy, discoverability, and developer experience.

---

## 📊 Gap Analysis: Current State vs. Codebase

### 1. **Agent Framework** ✅ COMPLETE

| Aspect | Status | Document |
|--------|--------|----------|
| Agent Configuration | ✅ Documented | [agent-framework.md](agent-framework.md) |
| Agent Loading | ✅ Documented | [agent-framework.md](agent-framework.md) |
| Tool Registry | ✅ Documented | [agent-framework.md](agent-framework.md) |
| Session Manager | ✅ Documented | [agent-framework.md](agent-framework.md) |
| Scenario Support | ✅ Documented | [agent-framework.md](agent-framework.md) |
| Handoff Tools | ✅ Documented | [handoff-strategies.md](handoff-strategies.md) |

### 2. **Orchestration Architecture** ✅ COMPLETE

| Aspect | Status | Document |
|--------|--------|----------|
| Dual Orchestrators | ✅ Documented | [orchestration/README.md](orchestration/README.md) |
| Cascade Orchestrator | ✅ Documented | [orchestration/cascade.md](orchestration/cascade.md) |
| VoiceLive Orchestrator | ✅ Documented | [orchestration/voicelive.md](orchestration/voicelive.md) |
| Handoff Strategies | ✅ Updated | [handoff-strategies.md](handoff-strategies.md) |
| MemoManager Integration | ✅ Documented | [SESSION_MAPPING.md](../../apps/artagent/backend/agents/SESSION_MAPPING.md) |

### 3. **Voice Processing (Moderate Gap)** — Phase 3

| Aspect | Current Docs | Actual Codebase | Priority |
|--------|--------------|-----------------|----------|
| Speech Cascade | Three-thread model documented | Handler + orchestrator separation | 🟡 High |
| VoiceLive SDK | Basic overview | Full handler with audio processor, messenger | 🟡 High |
| TTS Sender | Not documented | `tts_sender.py` for audio streaming | 🟢 Medium |
| Barge-In Detection | Covered | Enhanced with cancel event patterns | 🟢 Medium |

### 4. **API Structure (Moderate Gap)**

| Aspect | Current Docs | Actual Codebase | Priority |
|--------|--------------|-----------------|----------|
| Event System | Not documented | `api/v1/events/` with registration, processor, handlers | 🟡 High |
| Agent Endpoints | Not documented | `/api/v1/agents`, `/api/v1/agents/{name}` | 🟡 High |
| Metrics Endpoint | Not documented | `/api/v1/metrics/` for session statistics | 🟢 Medium |

### 5. **Configuration & Settings (Minor Gap)**

| Aspect | Current Docs | Actual Codebase | Priority |
|--------|--------------|-----------------|----------|
| Feature Flags | Basic | `config/feature_flags.py` fully documented | 🟢 Medium |
| Voice Config | Basic | `config/voice_config.py` with presets | 🟢 Medium |
| App Settings | Covered | `config/app_settings.py` expanded | 🟢 Low |

---

## 🗂️ Proposed Documentation Structure

### Updated `mkdocs.yml` Navigation

```yaml
nav:
  - Architecture:
    - Overview: architecture/README.md
    - Agent Framework: architecture/agent-framework.md           # NEW
    - Orchestration:
      - Overview: architecture/orchestration/README.md           # NEW
      - Cascade Orchestrator: architecture/orchestration/cascade.md   # NEW
      - VoiceLive Orchestrator: architecture/orchestration/voicelive.md # NEW
    - Voice Processing:
      - Speech Recognition: architecture/speech-recognition.md
      - Speech Synthesis: architecture/speech-synthesis.md
      - Streaming Modes: architecture/streaming-modes.md
    - Data & State:
      - Data Flows: architecture/data-flows.md
      - Session Management: architecture/session-management.md   # NEW
    - Handoffs:
      - Strategies: architecture/handoff-strategies.md           # UPDATE
      - Inventory: architecture/handoff-inventory.md             # MOVE/UPDATE
    - ACS Integration: architecture/acs-flows.md
    - Integrations: architecture/integrations.md
```

---

## 📝 Document-by-Document Plan

### ✅ Phase 1: Critical Priority (COMPLETE)

#### 1. **`agent-framework.md`** ✅ CREATED

Comprehensive guide to the unified agent system covering:
- Directory structure and YAML configuration
- Agent loading with `discover_agents()` and `build_handoff_map()`
- Tool registry patterns
- Prompt templates with Jinja2
- Session-level overrides
- Adding new agents walkthrough

#### 2. **`orchestration/README.md`** ✅ CREATED

Overview of dual orchestration architecture:
- Mode selection via `ACS_STREAMING_MODE`
- Comparison: Cascade vs VoiceLive
- Shared abstractions (`OrchestratorContext`, `OrchestratorResult`)
- Turn processing patterns

#### 3. **`orchestration/cascade.md`** ✅ CREATED

Deep dive into SpeechCascade orchestration:
- `CascadeOrchestratorAdapter` class
- Sentence-level TTS streaming
- State-based handoffs
- MemoManager sync patterns

#### 4. **`orchestration/voicelive.md`** ✅ CREATED

Deep dive into VoiceLive orchestration:
- `LiveOrchestrator` event handling
- Tool-based handoffs
- Barge-in handling
- LLM TTFT telemetry

#### 5. **`llm-orchestration.md`** ✅ UPDATED

Converted to redirect page pointing to new orchestration docs.

#### 6. **`handoff-strategies.md`** ✅ UPDATED

Modernized with:
- Tool-based detection with `build_handoff_map()`
- Updated architecture diagrams
- New code examples matching current API
- Helper function documentation (`build_handoff_system_vars`, `sanitize_handoff_context`)

### ✅ Phase 2: Code Cleanup (COMPLETE)

#### **`session_state.py`** Simplification ✅

- Removed ~27 lines of frivolous `hasattr` checks
- Removed dead legacy code (`mm.system_vars`, `mm.user_profile`)
- Simplified `_get_from_memo` and `_set_to_memo` helpers
- All 51 related tests passing

---

### ✅ Phase 3: High Priority (COMPLETE)

#### 1. **`session-management.md`** ✅ CREATED

Comprehensive session state documentation covering:
- MemoManager deep dive (CoreMemory, ChatHistory, MessageQueue)
- Redis key patterns (`session:{session_id}`)
- session_state.py sync functions (`sync_state_from_memo`, `sync_state_to_memo`)
- User profile loading (Cosmos DB / mock fallback)
- Latency tracking and TTS interrupt handling
- Quick reference table for common operations

**Optimization review completed:** See [SESSION_OPTIMIZATION_NOTES.md](SESSION_OPTIMIZATION_NOTES.md)

#### 2. **Code Optimizations** ✅ IMPLEMENTED

All high and medium priority optimizations from SESSION_OPTIMIZATION_NOTES.md:

| Optimization | Status |
|--------------|--------|
| Remove dead `enable_auto_refresh` code (~35 lines) | ✅ Done |
| Fix `from_redis_with_manager()` placeholder bug | ✅ Done |
| Consolidate duplicate mock profiles (~46 lines) | ✅ Done |
| Simplify TTS interrupt key pattern | ✅ Done |
| Add persist task lifecycle management | ✅ Done |

Test coverage: 11 tests in `tests/test_memo_optimization.py`, all passing.

---

### 🟡 Phase 4: Medium Priority (IN PROGRESS)

#### 1. **UPDATE: `streaming-modes.md`** ✅ COMPLETE

Updated with:
- Current handler class names (`SpeechCascadeHandler`, `VoiceLiveSDKHandler`)
- Handler factory pattern from `_create_media_handler()`
- Pre-initialization for VoiceLive agents
- Comparison tables for mode selection
- Troubleshooting section

---

#### 2. **UPDATE: `acs-flows.md`** ✅ COMPLETE

Updated with:
- V1 Event Processor section with handler registration patterns
- Handler integration (`SpeechCascadeHandler`, `VoiceLiveSDKHandler`)
- Simplified three-thread architecture diagram
- Call lifecycle flow with handler factory
- Configuration and troubleshooting sections

---

### 🟢 Phase 4: Medium Priority

#### 1. **UPDATE: `speech-recognition.md`**

**Changes:**
1. Update pool management patterns
2. Add phrase list manager integration
3. Document on-demand resource pools
4. Update WebSocket endpoint handlers

---

#### 2. **UPDATE: `speech-synthesis.md`**

**Changes:**
1. Document TTS sender pattern
2. Add sentence-level streaming
3. Update pool configuration
4. Document voice config resolution

---

#### 3. **UPDATE: `data-flows.md`**

**Changes:**
1. Add session profile flow
2. Document tool output persistence
3. Update Redis key patterns for cascade
4. Add agent switch data flow

---

#### 4. **UPDATE: `README.md` (Architecture Overview)**

**Changes:**
1. Update capability table
2. Add orchestration mode selection
3. Update deep dive links
4. Add agent framework to core capabilities
5. Refresh architecture diagrams

---

### 🔵 Phase 5: Enhancement

#### 1. **NEW: `telemetry.md`** (Optional)

**Purpose:** OpenTelemetry patterns for voice agents

**Sections:**
1. GenAI Semantic Conventions
2. invoke_agent Spans
3. Token Attribution
4. LLM TTFT Tracking
5. App Insights Agents Blade

---

#### 2. **Cleanup Tasks**

1. Remove/archive obsolete files:
   - `agent-configuration-proposal.md` → Archive
   - `session-agent-config-proposal.md` → Merge into agent-framework.md
   - `microsoft-agent-framework-evaluation.md` → Archive
   - `backend-voice-agents-architecture.md` → Merge into orchestration overview
   - `TELEMETRY_PLAN.md` → Merge into telemetry.md or archive

2. Standardize diagram styles (Mermaid)

3. Update all code examples to use current imports

4. Add "Last Updated" timestamps

---

## ✅ Acceptance Criteria

- [x] Agent framework has comprehensive YAML reference → `agent-framework.md`
- [x] Both orchestrators have dedicated deep-dive docs → `orchestration/cascade.md`, `orchestration/voicelive.md`
- [x] Handoff strategies are clearly explained with diagrams → `handoff-strategies.md` updated
- [x] Code cleanup completed → `session_state.py` simplified
- [ ] Session management documented → `session-management.md` (Phase 3)
- [ ] All architecture docs reference current file paths
- [ ] Code examples are copy-paste runnable
- [ ] Diagrams match current architecture
- [ ] Navigation structure is intuitive
- [ ] No broken internal links

---

## 📅 Timeline & Progress

| Phase | Status | Deliverables |
|-------|--------|--------------|
| Phase 1 | ✅ COMPLETE | `agent-framework.md`, `orchestration/` folder, `handoff-strategies.md` updated |
| Phase 2 | ✅ COMPLETE | `session_state.py` simplified (~27 lines removed) |
| Phase 3 | 🟡 NEXT | `session-management.md`, `streaming-modes.md`, `acs-flows.md` |
| Phase 4 | ⏳ Pending | Speech docs, `data-flows.md`, README update |
| Phase 5 | ⏳ Pending | `telemetry.md`, cleanup, archive obsolete files |

---

## 🔗 Key Source Files Reference

### Agent Framework
- [`apps/artagent/backend/agents/README.md`](../../../apps/artagent/backend/agents/README.md)
- [`apps/artagent/backend/agents/base.py`](../../../apps/artagent/backend/agents/base.py)
- [`apps/artagent/backend/agents/loader.py`](../../../apps/artagent/backend/agents/loader.py)
- [`apps/artagent/backend/agents/tools/registry.py`](../../../apps/artagent/backend/agents/tools/registry.py)

### Orchestration
- [`apps/artagent/backend/voice/speech_cascade/orchestrator.py`](../../../apps/artagent/backend/voice/speech_cascade/orchestrator.py)
- [`apps/artagent/backend/voice/voicelive/orchestrator.py`](../../../apps/artagent/backend/voice/voicelive/orchestrator.py)
- [`apps/artagent/backend/voice/shared/base.py`](../../../apps/artagent/backend/voice/shared/base.py)

### Voice Handlers
- [`apps/artagent/backend/voice/speech_cascade/handler.py`](../../../apps/artagent/backend/voice/speech_cascade/handler.py)
- [`apps/artagent/backend/voice/voicelive/handler.py`](../../../apps/artagent/backend/voice/voicelive/handler.py)

### Session & State
- [`apps/artagent/backend/src/services/session_loader.py`](../../../apps/artagent/backend/src/services/session_loader.py)
- [`apps/artagent/backend/agents/session_manager.py`](../../../apps/artagent/backend/agents/session_manager.py)
- [`apps/artagent/backend/voice/shared/session_state.py`](../../../apps/artagent/backend/voice/shared/session_state.py) - Shared sync utilities
- [`apps/artagent/backend/agents/SESSION_MAPPING.md`](../../../apps/artagent/backend/agents/SESSION_MAPPING.md) - Onboarding guide

### API Events
- [`apps/artagent/backend/api/v1/events/`](../../../apps/artagent/backend/api/v1/events/)

---

## 💬 Discussion Points

1. **Agent README.md Quality:** The existing `agents/README.md` is comprehensive. Should we migrate it to docs/ or reference it inline?

2. **Telemetry Documentation:** Should we create a dedicated telemetry section or fold it into operations/monitoring?

3. **Proposal Files:** Archive or merge the proposal files (`agent-configuration-proposal.md`, etc.)?

4. **Industry Solutions:** Should industry-specific agent configurations be documented in architecture/ or industry/?

---

## 📋 Next Steps

**Phase 3 Ready to Start:**

1. **`session-management.md`** - Create comprehensive session state documentation
   - MemoManager internals
   - Core memory vs slots
   - Session profile loading from Redis/Cosmos
   - Reference the simplified `session_state.py` sync utilities

2. **`streaming-modes.md`** - Update with current handler class names
   - Pre-initialization patterns for VoiceLive
   - Handler factory patterns

3. **`acs-flows.md`** - Update thread architecture
   - Barge-in with cancel event patterns
   - Event registration system

---

*Plan last updated after Phase 1 & 2 completion. All critical agent framework and orchestration docs are now in place.*
