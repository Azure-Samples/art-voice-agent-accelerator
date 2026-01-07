# Codebase Cleanup Analysis: Legacy Code & Redundancies

**Project**: Azure Real-Time (ART) Agent Accelerator v2.0.0-beta.1
**Analysis Date**: 2026-01-05
**Status**: Migration in Progress

---

## Executive Summary

This analysis identifies cleanup opportunities in the ART Agent Accelerator codebase, focusing on legacy implementations, redundant wrappers, and architectural inconsistencies. The codebase is actively maintained and undergoing architectural improvements, creating temporary duplication during migration.

**Key Findings**:
- ~1,500 lines of code can be eliminated through consolidation
- 3 handler implementations with 60% overlap
- Multiple legacy directories safe for deletion
- Active VoiceHandler migration incomplete

---

## 1. Handler Architecture Analysis

### Current State: Three Handler Implementations

#### A. MediaHandler (PRIMARY - ACTIVE)
**Location**: `apps/artagent/backend/api/v1/handlers/media_handler.py`
**Size**: 1,438 lines
**Status**: Production handler (Dec 2025)
**Purpose**: Unified handler for Browser and ACS transports

**Key Responsibilities**:
- TTS/STT pool management
- WebSocket lifecycle management
- Transport routing (Browser/ACS)
- Composes with `SpeechCascadeHandler` for 3-thread architecture
- Factory pattern: `MediaHandler.create()`

**Issues**:
- Large monolithic class
- Mixes transport logic with business logic
- Direct websocket.state manipulation

#### B. VoiceHandler (EXPERIMENTAL - MIGRATION TARGET)
**Location**: `apps/artagent/backend/voice/handler.py`
**Size**: 1,314 lines
**Status**: Incomplete migration (per recent commits)
**Purpose**: Consolidate MediaHandler + SpeechCascadeHandler

**Key Differences**:
- Uses `VoiceSessionContext` typed class (better than websocket.state)
- Attempts to inline SpeechCascadeHandler logic
- Only referenced in compatibility tests

**Issues**:
- **~60% code overlap with MediaHandler**
- Not yet integrated with production endpoints
- Creates confusion about which handler to use
- Migration incomplete

**Critical Decision Needed**: Complete migration OR remove VoiceHandler

#### C. VoiceLiveSDKHandler (ACTIVE - SEPARATE PATH)
**Location**: `apps/artagent/backend/voice/voicelive/handler.py`
**Size**: 2,117 lines
**Status**: Production VoiceLive transport
**Purpose**: Azure VoiceLive SDK integration

**Key Differences**:
- Completely different architecture
- Uses `LiveOrchestrator` for real-time voice AI
- Better session abstraction via `_SessionMessenger`
- Cannot be easily unified with Browser/ACS handlers

**Recommendation**: Keep separate but extract shared services

### Architecture Evolution

```
LEGACY (v1.x):
  ACS Handler → Media Handler → Speech Processing

CURRENT (v2.0):
  ┌─ Browser/ACS → MediaHandler → SpeechCascadeHandler → Orchestrator
  └─ VoiceLive → VoiceLiveSDKHandler → LiveOrchestrator → Tools

TARGET (proposed):
  All Transports → Unified VoiceHandler → Orchestrator
```

### Redundancy Analysis

**Code Overlap Between MediaHandler and VoiceHandler (~800 lines)**:
1. TTS/STT pool management (identical)
2. Greeting derivation logic (similar)
3. Barge-in handling (different approaches)
4. WebSocket state setup (different abstractions)
5. Session lifecycle methods (similar)

---

## 2. Dead Code & Legacy Directories

### Confirmed Safe to Delete

#### A. Legacy Redis Module
**Location**: `/src/redis/legacy/`
**Files**:
- `async_manager.py` (194 lines)
- `key_manager.py`
- `__backup.py`

**Status**: Superseded by `/src/redis/manager.py`
**Action**: Delete after verifying no imports
**Risk**: Low (last modified pre-2.0)

#### B. Legacy Test Directory
**Location**: `/tests/_legacy_v1_tests/`
**Status**: Empty directory (0 files)
**Action**: Delete immediately
**Risk**: None

#### C. Deprecated Infrastructure
**Location**: `/infra/bicep/deprecated/`
**Status**: Replaced by Terraform modules
**Action**: Archive or delete
**Risk**: Low (infrastructure code, not runtime)

---

## 3. Duplicative Code Patterns

### A. Orchestrator Implementations (3 Found)

1. **LiveOrchestrator** (`apps/artagent/backend/voice/voicelive/orchestrator.py`)
   - VoiceLive-specific orchestration
   - Handles real-time tool calls
   - Status: Active, keep separate

2. **CascadeOrchestratorAdapter** (`apps/artagent/backend/voice/speech_cascade/orchestrator.py`)
   - Adapter for unified orchestration
   - Status: Active with MediaHandler
   - Consider: Merge into unified orchestrator

3. **Unified Orchestrator** (`apps/artagent/backend/src/orchestration/unified/`)
   - `route_turn()` function - common entry point
   - Status: Target implementation
   - Keep as primary

**Recommendation**: Consolidate CascadeOrchestratorAdapter into unified orchestrator once VoiceHandler migration is decided.

### B. Greeting Logic Duplication (~200 lines)

**Found in 3 locations**:

1. **MediaHandler._derive_greeting()** (line ~850-995)
   - 145 lines of greeting logic
   - Checks session agent
   - Falls back to unified agents
   - Applies Jinja2 templates
   - Handles return greetings

2. **VoiceHandler._derive_greeting()** (line ~600-640)
   - 40 lines (simplified version)
   - Same logic, different implementation

3. **Greeting Service Module**
   - Some shared utilities exist
   - Not fully utilized by handlers

**Recommendation**:
```python
# Create: apps/artagent/backend/voice/shared/greeting_service.py
class GreetingService:
    @staticmethod
    async def derive_greeting(
        session_id: str,
        agent_config: Dict,
        is_return: bool = False
    ) -> str:
        # Consolidated implementation
        pass
```

**Impact**: Eliminate ~180 lines of duplicated code

### C. Barge-In Logic Duplication (~300 lines)

**Three different implementations**:

1. **MediaHandler._on_barge_in()** (line ~700-800)
   - ACS-specific: `stop_recognizing_async()`
   - Browser-specific: Different handling
   - Mixed transport logic

2. **VoiceHandler.handle_barge_in()** (line ~500-550)
   - Unified approach
   - Uses VoiceSessionContext
   - Cleaner abstraction

3. **VoiceLiveSDKHandler._trigger_barge_in()** (line ~1200-1250)
   - Uses metadata triggers
   - Different mechanism entirely

**Recommendation**:
```python
# Create: apps/artagent/backend/voice/shared/barge_in_controller.py
class BargeInController:
    async def trigger(self, transport_type: str, context: Any):
        # Dispatch to transport-specific handler
        pass
```

**Impact**: Standardize pattern, reduce ~200 lines

### D. TTS Playback Handling

**Current State**:
- **TTSPlayback** class exists (`apps/artagent/backend/voice/tts/playback.py`) as unified handler
- MediaHandler has TTS logic inlined
- VoiceHandler delegates to TTSPlayback properly
- VoiceLiveSDKHandler uses different audio pipeline

**Recommendation**: Ensure MediaHandler uses TTSPlayback consistently

---

## 4. Backward Compatibility Aliases

### Found in media_handler.py (line 1420)

```python
# Backward compatibility
ACSMediaHandler = MediaHandler
```

**Action**:
1. Search for imports of `ACSMediaHandler`
2. If none found, remove alias
3. If found, update imports to use `MediaHandler`

### Legacy Constants (line 107-110)

```python
# Duplication for backward compatibility
VOICE_LIVE_PCM_SAMPLE_RATE = BROWSER_PCM_SAMPLE_RATE
VOICE_LIVE_SPEECH_RMS_THRESHOLD = BROWSER_SPEECH_RMS_THRESHOLD
VOICE_LIVE_SILENCE_GAP_SECONDS = BROWSER_SILENCE_GAP_SECONDS
```

**Action**:
1. Verify if any code uses VOICE_LIVE_* constants
2. Replace with BROWSER_* equivalents
3. Remove duplicates

---

## 5. Commented Code Blocks

### Files with Significant Dead Code

1. **apps/artagent/backend/voice/speech_cascade/__init__.py**
   - Multiple commented import statements
   - Suggests recent refactoring

2. **apps/artagent/backend/main.py**
   - Commented class definitions
   - Old implementations preserved as reference

3. **apps/artagent/backend/evaluation/scenario_runner.py**
   - TODO comments
   - Experimental code paths

4. **apps/artagent/backend/registries/toolstore/** (multiple files)
   - banking.py, subro.py, auth.py
   - Commented imports suggest incomplete refactoring

**Recommendation**:
- Review each commented block
- Remove if superseded by working implementation
- Move TODOs to issue tracker
- Use git history instead of commented code

---

## 6. Architecture Inconsistencies

### A. Session Context Handling

**Three different approaches**:

1. **MediaHandler**: Direct `websocket.state` dictionary manipulation
   ```python
   websocket.state["session_id"] = session_id
   ```

2. **VoiceHandler**: Typed `VoiceSessionContext` class
   ```python
   context = VoiceSessionContext(session_id=session_id, ...)
   ```

3. **VoiceLiveSDKHandler**: `_SessionMessenger` helper class
   ```python
   messenger = _SessionMessenger(websocket)
   ```

**Best Practice**: VoiceHandler's typed context is cleanest
**Recommendation**: Standardize on `VoiceSessionContext` pattern across all handlers

### B. Event Emission Patterns

**Three different approaches**:

1. **MediaHandler**: Direct functions
   ```python
   send_session_envelope(websocket, event)
   send_user_transcript(websocket, text)
   ```

2. **VoiceHandler**: Similar but with context
   ```python
   send_session_envelope(self.context.websocket, event)
   ```

3. **VoiceLiveSDKHandler**: Abstracted messenger
   ```python
   self._messenger.send_envelope(event)
   ```

**Best Practice**: VoiceLive's messenger abstraction is cleanest
**Recommendation**: Adopt messenger pattern across all handlers

---

## 7. Code Metrics & Cleanup Potential

### Current Code Size
- **MediaHandler**: 1,438 lines
- **VoiceHandler**: 1,314 lines
- **VoiceLiveSDKHandler**: 2,117 lines
- **Total Handler Code**: ~4,900 lines

### Duplication Estimate
- MediaHandler/VoiceHandler overlap: **~800 lines**
- Greeting logic duplication: **~200 lines**
- Barge-in logic duplication: **~300 lines**
- Commented/dead code: **~200 lines**
- **Total Cleanup Potential: ~1,500 lines**

### Impact
- **30% reduction** in handler code complexity
- Improved maintainability
- Clearer architectural intent
- Reduced cognitive load for developers

---

## 8. Cleanup Recommendations (Prioritized)

### HIGH PRIORITY (Start Here)

#### 1. Complete VoiceHandler Migration OR Remove It
**Decision Point**: This is the critical architectural decision

**Option A: Complete Migration**
- Add VoiceHandler to production endpoints
- Migrate all MediaHandler logic
- Update tests and documentation
- Deprecate MediaHandler
- Timeline: Major effort (weeks)

**Option B: Remove VoiceHandler**
- Delete `apps/artagent/backend/voice/handler.py`
- Delete compatibility tests
- Continue improving MediaHandler
- Timeline: Quick (days)

**Recommendation**: Decide based on:
- Is VoiceHandler's typed context worth the migration effort?
- Are there active PRs/branches using VoiceHandler?
- What's the team consensus?

#### 2. Delete Confirmed Legacy Code
**Immediate wins, no risk**:

```bash
# Delete legacy Redis module
rm -rf src/redis/legacy/

# Delete empty test directory
rm -rf tests/_legacy_v1_tests/

# Archive deprecated infrastructure
mv infra/bicep/deprecated/ docs/archived/bicep-deprecated/
```

**Impact**: Clean codebase, reduce confusion
**Risk**: Low (verify no imports first)

#### 3. Consolidate Greeting Logic
**Create shared service**:

```python
# apps/artagent/backend/voice/shared/greeting_service.py
class GreetingService:
    @staticmethod
    async def derive_greeting(
        session_id: str,
        agent_config: Dict,
        is_return: bool = False
    ) -> Tuple[str, Optional[str]]:
        """
        Consolidated greeting derivation logic.
        Returns: (greeting_text, audio_url)
        """
        # Implementation from MediaHandler._derive_greeting
        pass
```

**Update handlers**:
- MediaHandler: Replace `_derive_greeting()` with `GreetingService.derive_greeting()`
- VoiceHandler: Same (if kept)
- Add tests

**Impact**: Remove ~180 lines of duplication
**Risk**: Medium (requires testing)

### MEDIUM PRIORITY

#### 4. Standardize Session Context Pattern
**Adopt VoiceSessionContext everywhere**:

```python
# Define standard context in: apps/artagent/backend/voice/shared/context.py
@dataclass
class VoiceSessionContext:
    session_id: str
    websocket: WebSocket
    agent_config: Dict
    pools: Dict[str, Any]
    transport_type: str
    # ... other fields
```

**Update handlers**:
- MediaHandler: Replace websocket.state with VoiceSessionContext
- VoiceLiveSDKHandler: Adapt to use standard context

**Impact**: Type safety, better IDE support
**Risk**: Medium (large refactor)

#### 5. Unify Barge-In Logic
**Create controller**:

```python
# apps/artagent/backend/voice/shared/barge_in_controller.py
class BargeInController:
    def __init__(self, transport_type: str):
        self.transport_type = transport_type

    async def trigger(self, context: VoiceSessionContext):
        if self.transport_type == "acs":
            # ACS-specific logic
        elif self.transport_type == "browser":
            # Browser-specific logic
        elif self.transport_type == "voicelive":
            # VoiceLive-specific logic
```

**Impact**: Reduce ~200 lines, standardize pattern
**Risk**: Medium (requires thorough testing)

#### 6. Clean Commented Code
**Process**:
1. Review each file with commented blocks
2. Create issues for TODOs
3. Remove superseded code
4. Commit with clear messages

**Files to review**:
- `apps/artagent/backend/voice/speech_cascade/__init__.py`
- `apps/artagent/backend/main.py`
- `apps/artagent/backend/evaluation/scenario_runner.py`
- `apps/artagent/backend/registries/toolstore/*.py`

**Impact**: Cleaner code, remove confusion
**Risk**: Low (use git history for reference)

### LOW PRIORITY

#### 7. Remove Backward Compatibility Aliases
**After verification**:
```python
# Search for usage
grep -r "ACSMediaHandler" apps/

# If no results, remove from media_handler.py line 1420
# ACSMediaHandler = MediaHandler  # DELETE THIS

# Same for VOICE_LIVE_* constants
```

**Impact**: Minor cleanup
**Risk**: Very low

#### 8. Optimize Imports
**Use automated tools**:
```bash
# Remove unused imports
autoflake --remove-all-unused-imports --recursive apps/

# Sort imports
isort apps/

# Format code
black apps/
```

**Impact**: Code style consistency
**Risk**: Very low (automated)

---

## 9. Proposed Target Architecture

### Clean, Unified Design

```
┌─────────────────────────────────────────┐
│  Transport Layer                         │
│  - Browser (WebSocket)                   │
│  - ACS (WebSocket)                       │
│  - VoiceLive (SDK)                       │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  Unified VoiceHandler                    │
│  - Transport routing via adapter pattern │
│  - Typed VoiceSessionContext             │
│  - Pool management (TTS/STT)             │
│  - Session lifecycle                     │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  Speech Processing Layer                 │
│  - SpeechCascade (Browser/ACS)           │
│  - VoiceLive SDK (Real-time)             │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  Unified Orchestrator                    │
│  - route_turn() entry point              │
│  - Agent resolution                      │
│  - Tool execution                        │
│  - Context management                    │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  Shared Services                         │
│  - GreetingService                       │
│  - BargeInController                     │
│  - SessionMessenger                      │
│  - TTSPlayback                           │
└─────────────────────────────────────────┘
```

### Key Principles
1. **Single Responsibility**: Each component has one clear purpose
2. **Typed Contexts**: Use dataclasses for session state
3. **Adapter Pattern**: Handle transport differences at edges
4. **Shared Services**: Extract common logic to services
5. **Consistent Abstractions**: Same patterns across all handlers

---

## 10. Migration Strategy (Updated 2026-01-05)

### Phase 1: Quick Wins ⏳ IN PROGRESS
1. ✅ Remove MediaHandler (COMPLETE - 1,438 lines removed)
2. ⏳ Delete legacy Redis module (NEXT)
3. ⏳ Delete empty test directory (NEXT)
4. TODO: Remove commented code blocks
5. ✅ Remove unused backward compatibility aliases (COMPLETE)

**Impact**: Immediate codebase cleanup
**Risk**: Very low
**Progress**: 40% complete

### Phase 2: Consolidate Services (PENDING)
1. TODO: Create GreetingService
2. TODO: Create BargeInController
3. TODO: Create SessionMessenger abstraction
4. TODO: Update handlers to use services

**Impact**: Reduce duplication
**Risk**: Medium (requires testing)
**Estimated**: ~300 lines can be consolidated

### Phase 3: VoiceHandler Migration ✅ COMPLETE
1. ✅ Team decision: Complete migration (DONE)
2. ✅ Delete MediaHandler (DONE - 2026-01-05)
3. ✅ Migrate endpoints to VoiceHandler (Already done in previous work)

**Impact**: Resolve architectural ambiguity
**Risk**: High (major decision)

### Phase 4: Standardize Patterns (2-4 weeks)
1. Adopt VoiceSessionContext everywhere
2. Standardize event emission via SessionMessenger
3. Unify error handling patterns
4. Update documentation

**Impact**: Long-term maintainability
**Risk**: Medium (large refactor)

---

## 11. Critical Paths to Preserve

### DO NOT TOUCH (Active Production Code)
1. **MediaHandler** - Primary voice handler (until migration complete)
2. **VoiceLiveSDKHandler** - Production VoiceLive path
3. **TTSPlayback** - Unified TTS implementation
4. **LiveOrchestrator** & **unified.route_turn** - Core orchestration
5. **SpeechCascadeHandler** - Active 3-thread architecture
6. **All tool implementations** under `/registries/toolstore/`

### Modify with Caution
1. WebSocket endpoint handlers
2. Session lifecycle management
3. Pool initialization logic
4. Orchestrator routing

---

## 12. Testing Strategy

### Before Any Cleanup
1. Document current test coverage
2. Run full test suite: `pytest apps/artagent/backend/tests/`
3. Test all voice transports (Browser, ACS, VoiceLive)
4. Verify greeting flows
5. Test barge-in scenarios

### After Each Cleanup Step
1. Run affected tests
2. Manual smoke test each transport
3. Check for regressions
4. Update tests if needed

### Recommended Tests to Add
1. Greeting service unit tests
2. Barge-in controller unit tests
3. Session context serialization tests
4. Integration tests for handler migration

---

## 13. Next Steps

### Immediate Actions
1. **Team Discussion**: Schedule meeting to decide on VoiceHandler fate
2. **Verify Imports**: Run search for legacy code imports
3. **Create Issues**: Track each cleanup task in issue tracker
4. **Backup**: Create feature branch for cleanup work

### Recommended Issue Tracker Structure
```
Epic: Codebase Cleanup & Refactoring
├── Issue: Delete legacy Redis module
├── Issue: Remove empty test directories
├── Issue: VoiceHandler migration decision
├── Issue: Consolidate greeting logic
├── Issue: Unify barge-in handling
├── Issue: Standardize session context
├── Issue: Clean commented code
└── Issue: Remove backward compatibility aliases
```

---

## 14. Risks & Mitigation

### Risk 1: Breaking Production
**Mitigation**:
- Feature branch development
- Comprehensive testing before merge
- Gradual rollout with feature flags
- Keep MediaHandler stable during migration

### Risk 2: Incomplete Migration State
**Mitigation**:
- Make VoiceHandler decision quickly
- Avoid long-running feature branches
- Complete or remove, don't leave partial

### Risk 3: Lost Historical Context
**Mitigation**:
- Document reasons for removals in commit messages
- Archive (don't delete) infrastructure code
- Use git tags for major transitions

---

## Conclusion

The ART Agent Accelerator codebase is well-structured but in an active migration state. The primary cleanup opportunity is resolving the MediaHandler/VoiceHandler duplication and consolidating shared service logic.

**Summary of Cleanup Potential**:
- ✅ **1,438 lines eliminated** (MediaHandler removed 2026-01-05)
- **3 legacy directories** remaining to delete
- ✅ **~30% reduction** in handler complexity achieved
- **~300 lines** still available for consolidation (greeting + barge-in)

**Recommended Priority** (Updated 2026-01-05):
1. ✅ ~~VoiceHandler decision~~ - **COMPLETE**
2. Quick wins (delete legacy code) - **IN PROGRESS**
3. Service consolidation - **Next up**
4. Pattern standardization - **Long-term investment**

**Current Status**: Migration complete, continuing with quick wins and service consolidation.
