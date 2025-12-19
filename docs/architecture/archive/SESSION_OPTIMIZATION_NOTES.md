# Session Management Optimization Notes

> **Status:** Review findings from code analysis (December 2025)  
> **Scope:** MemoManager, session_state.py, session_loader.py

---

## 🔴 High Priority Optimizations

### 1. Dead Code: `enable_auto_refresh()` Never Used

**Location:** `src/stateful/state_managment.py:1340-1375`

**Finding:** The auto-refresh feature (polling Redis every N seconds) is fully implemented but never called from any production code. All 3 grep matches are in docstrings or the definition itself.

**Options:**
- **A) Remove it** - Dead code adds maintenance burden
- **B) Integrate it** - Use for long-running sessions with multi-process coordination

**Recommendation:** Remove unless there's a specific use case. The current design syncs at turn boundaries, which is sufficient for single-session voice calls.

```python
# ~35 lines of dead code:
def enable_auto_refresh(...)
def disable_auto_refresh(...)
async def _auto_refresh_loop(...)
```

---

### 2. Duplicate Profile Data in Mock Dictionaries

**Location:** `apps/artagent/backend/src/services/session_loader.py`

**Finding:** Same profile data is duplicated in both `_EMAIL_TO_PROFILE` and `_CLIENT_ID_TO_PROFILE` dictionaries.

**Current:**
```python
_EMAIL_TO_PROFILE = {
    "john.smith@email.com": { ... profile ... }
}

_CLIENT_ID_TO_PROFILE = {
    "CLT-001-JS": { ... same profile ... }
}
```

**Optimization:**
```python
# Single source of truth
_MOCK_PROFILES = [
    {"full_name": "John Smith", "client_id": "CLT-001-JS", "email": "john.smith@email.com", ...},
    {"full_name": "Jane Doe", "client_id": "CLT-002-JD", "email": "jane.doe@email.com", ...},
]

# Build indexes at module load
_EMAIL_INDEX = {p["email"]: p for p in _MOCK_PROFILES}
_CLIENT_ID_INDEX = {p["client_id"]: p for p in _MOCK_PROFILES}
```

---

### 3. `tts_interrupted` Key Pattern Inconsistency

**Location:** `src/stateful/state_managment.py:609, 649, 652`

**Finding:** TTS interrupt state uses `f"tts_interrupted:{session_id}"` as the key, but this creates a key like `tts_interrupted:abc123` inside corememory, which is redundant since corememory is already scoped to the session.

**Current:**
```python
await self.set_live_context_value(
    redis_mgr, f"tts_interrupted:{session_id}", value
)
```

**Should be:**
```python
# Inside session-scoped corememory, no need to include session_id
await self.set_live_context_value(redis_mgr, "tts_interrupted", value)
```

---

## 🟡 Medium Priority Optimizations

### 4. `persist_background()` Task Lifecycle

**Location:** `src/stateful/state_managment.py:468-507`

**Finding:** Background tasks are fire-and-forget but no mechanism exists to:
- Track if a persist is already in flight (could queue multiple)
- Cancel pending persists on session end
- Report failures to monitoring

**Potential Enhancement:**
```python
class MemoManager:
    _pending_persist: Optional[asyncio.Task] = None
    
    async def persist_background(self, redis_mgr=None, ttl_seconds=None):
        # Cancel previous if still running
        if self._pending_persist and not self._pending_persist.done():
            self._pending_persist.cancel()
        
        self._pending_persist = asyncio.create_task(
            self._background_persist_task(mgr, ttl_seconds),
            name=f"persist_session_{self.session_id}",
        )
```

---

### 5. `from_redis_with_manager()` is Incomplete

**Location:** `src/stateful/state_managment.py:299-320`

**Finding:** The method has a comment `# ...existing logic...` but no actual implementation beyond creating an empty manager.

**Current:**
```python
@classmethod
def from_redis_with_manager(cls, session_id, redis_mgr):
    cm = cls(session_id=session_id, redis_mgr=redis_mgr)
    # ...existing logic...  # ← This is the ONLY line
    return cm
```

**Should be:**
```python
@classmethod
def from_redis_with_manager(cls, session_id, redis_mgr):
    key = cls.build_redis_key(session_id)
    data = redis_mgr.get_session_data(key)
    mm = cls(session_id=session_id, redis_mgr=redis_mgr)
    if cls._CORE_KEY in data:
        mm.corememory.from_json(data[cls._CORE_KEY])
    if cls._HISTORY_KEY in data:
        mm.chatHistory.from_json(data[cls._HISTORY_KEY])
    return mm
```

---

### 6. Missing `__all__` in session_loader.py

**Location:** `apps/artagent/backend/src/services/session_loader.py`

**Finding:** The file exports via `__all__` but could also export the sanitization helper for reuse.

---

## 🟢 Low Priority / Future Considerations

### 7. SessionAgentManager Integration

**Status:** Fully implemented but not used in production orchestrators.

**Current state:** 
- Has comprehensive per-session agent override support
- Implements `AgentProvider` and `HandoffProvider` protocols
- Supports A/B testing with experiment tracking

**Next steps when ready:**
1. Add feature flag to enable session overrides
2. Wire into `CascadeOrchestratorAdapter` and `LiveOrchestrator`
3. Add admin API endpoint for runtime prompt modification

---

### 8. Latency Tracking Complexity

**Location:** `src/stateful/state_managment.py:766-810`

**Observation:** Latency tracking uses a complex nested structure with `runs`, `order`, and `samples`. This is more complex than needed for typical monitoring.

**Current structure:**
```python
{
    "latency": {
        "runs": {
            "run_id": {
                "samples": [{"stage": "stt", "dur": 0.2}, ...]
            }
        },
        "order": ["run_id", ...],
        "current_run_id": "..."
    }
}
```

**Simpler alternative (if no multi-run tracking needed):**
```python
{
    "latency": {
        "stt": [0.2, 0.25, 0.18],  # Raw samples
        "llm": [1.2, 0.9, 1.5]
    }
}
```

---

### 9. EphemeralMemoManager TODO

**Location:** `src/agenticmemory/types.py:136`

```python
# TODO: Implement EphemeralMemoManager
# class EphemeralMemoManager():
```

**Purpose:** For app-layer components that must not persist to Redis. Currently not needed but noted for future.

---

## Action Items

| Priority | Item | Effort | Impact | Status |
|----------|------|--------|--------|--------|
| 🔴 High | Remove `enable_auto_refresh` dead code | 1hr | Code cleanup | ✅ Done |
| 🔴 High | Fix `from_redis_with_manager` implementation | 30min | Bug fix | ✅ Done |
| 🟡 Medium | Deduplicate mock profiles | 1hr | Maintainability | ✅ Done |
| 🟡 Medium | Simplify `tts_interrupted` key | 30min | Clarity | ✅ Done |
| 🟡 Medium | Add persist task lifecycle mgmt | 2hr | Reliability | ✅ Done |
| 🟢 Low | Integrate SessionAgentManager | 4hr | New feature | ⏳ Future |

---

## Completed Optimizations (December 2025)

### Summary of Changes

1. **Removed ~35 lines of dead auto-refresh code** from `state_managment.py`:
   - `enable_auto_refresh()`, `disable_auto_refresh()`, `_auto_refresh_loop()`
   - Removed unused attributes: `auto_refresh_interval`, `last_refresh_time`, `_refresh_task`

2. **Fixed `from_redis_with_manager()`** - Was a stub with placeholder comment, now actually loads data from Redis and stores manager reference.

3. **Consolidated mock profiles** in `session_loader.py`:
   - Merged duplicate `_EMAIL_TO_PROFILE` and `_CLIENT_ID_TO_PROFILE` into single `_MOCK_PROFILES` list
   - Built `_EMAIL_INDEX` and `_CLIENT_ID_INDEX` at module load
   - Reduced ~46 lines of duplicate data

4. **Simplified TTS interrupt key** - Changed from redundant `f"tts_interrupted:{session_id}"` to just `"tts_interrupted"` (corememory is already session-scoped)

5. **Added persist task lifecycle management** in `state_managment.py`:
   - Added `_pending_persist_task` attribute to track active background persist
   - Updated `persist_background()` to cancel previous task before creating new one (deduplication)
   - Added `cancel_pending_persist()` method for explicit cleanup on session end
   - Added graceful `CancelledError` handling in `_background_persist_task()`

### Test Coverage

Added `tests/test_memo_optimization.py` with 11 tests validating all changes.

---

*Generated from code review on December 2025. Updated with completed items.*
