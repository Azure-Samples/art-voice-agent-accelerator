"""
Session Scenario Registry
=========================

Centralized storage for session-scoped dynamic scenarios created via Scenario Builder.
This module is the single source of truth for session scenario state.

Session scenarios allow runtime customization of:
- Agent orchestration graph (handoffs between agents)
- Agent overrides (greetings, template vars)
- Starting agent
- Handoff behavior (announced vs discrete)

Storage Structure:
- _session_scenarios: dict[session_id, dict[scenario_key, ScenarioConfig]]
  In-memory cache for fast access. Keys are lowercase for case-insensitive lookup.
  Also persisted to Redis via MemoManager.
- _active_scenario: dict[session_id, scenario_key]
  Tracks which scenario is currently active for each session (lowercase key).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from apps.artagent.backend.src.orchestration.naming import (
    SCENARIO_KEY_ACTIVE,
    SCENARIO_KEY_ALL,
    SCENARIO_KEY_CONFIG,
    find_scenario_by_name,
    scenario_key,
)
from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from apps.artagent.backend.registries.scenariostore.loader import ScenarioConfig

logger = get_logger(__name__)

# Session-scoped dynamic scenarios: session_id -> {scenario_key (lowercase) -> ScenarioConfig}
_session_scenarios: dict[str, dict[str, ScenarioConfig]] = {}

# Track the active scenario for each session: session_id -> scenario_key (lowercase)
_active_scenario: dict[str, str] = {}

# Callback for notifying the orchestrator adapter of scenario updates
_scenario_update_callback: Callable[[str, ScenarioConfig], bool] | None = None

# Redis manager reference (set by main.py startup)
_redis_manager: Any = None

# Time-based cooldown for Redis reads — avoids hammering Redis when rapid
# successive reads hit _ensure_session_loaded (e.g., frontend polling).
_session_load_times: dict[str, float] = {}
_REDIS_LOAD_COOLDOWN_S: float = 2.0


def set_redis_manager(redis_mgr: Any) -> None:
    """Set the Redis manager reference for persistence operations."""
    global _redis_manager
    _redis_manager = redis_mgr
    logger.debug("Redis manager set for session_scenarios")


def register_scenario_update_callback(
    callback: Callable[[str, ScenarioConfig], bool]
) -> None:
    """
    Register a callback to be invoked when a session scenario is updated.

    This is called by the unified orchestrator to inject updates into live adapters.
    """
    global _scenario_update_callback
    _scenario_update_callback = callback
    logger.debug("Scenario update callback registered")


def _parse_scenario_data(scenario_data: dict) -> ScenarioConfig:
    """
    Parse a scenario data dict into a ScenarioConfig object.
    
    Helper function to avoid code duplication.
    """
    from apps.artagent.backend.registries.scenariostore.loader import (
        AgentOverride,
        GenericHandoffConfig,
        HandoffConfig,
        ScenarioConfig,
    )
    
    # Parse handoffs
    handoffs = []
    for h in scenario_data.get("handoffs", []):
        context_vars = h.get("context_vars", h.get("handoff_context", {}))
        if not isinstance(context_vars, dict):
            context_vars = {}
        handoffs.append(HandoffConfig(
            from_agent=h.get("from_agent", ""),
            to_agent=h.get("to_agent", ""),
            tool=h.get("tool", ""),
            type=h.get("type", "announced"),
            share_context=h.get("share_context", True),
            handoff_condition=h.get("handoff_condition", ""),
            context_vars=context_vars,
        ))
    
    # Parse agent_defaults
    agent_defaults = None
    agent_defaults_data = scenario_data.get("agent_defaults")
    if agent_defaults_data:
        agent_defaults = AgentOverride(
            greeting=agent_defaults_data.get("greeting"),
            return_greeting=agent_defaults_data.get("return_greeting"),
            description=agent_defaults_data.get("description"),
            template_vars=agent_defaults_data.get("template_vars", {}),
            voice_name=agent_defaults_data.get("voice_name"),
            voice_rate=agent_defaults_data.get("voice_rate"),
        )
    
    # Parse generic_handoff
    generic_handoff_data = scenario_data.get("generic_handoff", {})
    generic_handoff = GenericHandoffConfig(
        enabled=generic_handoff_data.get("enabled", False),
        allowed_targets=generic_handoff_data.get("allowed_targets", []),
        require_client_id=generic_handoff_data.get("require_client_id", False),
        default_type=generic_handoff_data.get("default_type", "announced"),
        share_context=generic_handoff_data.get("share_context", True),
    )
    
    # Create ScenarioConfig with all fields
    return ScenarioConfig(
        name=scenario_data.get("name", "custom"),
        description=scenario_data.get("description", ""),
        icon=scenario_data.get("icon", "🎭"),
        agents=scenario_data.get("agents", []),
        agent_defaults=agent_defaults,
        global_template_vars=scenario_data.get("global_template_vars", {}),
        tools=scenario_data.get("tools", []),
        start_agent=scenario_data.get("start_agent"),
        handoff_type=scenario_data.get("handoff_type", "announced"),
        handoffs=handoffs,
        generic_handoff=generic_handoff,
    )


def _load_scenarios_from_redis(session_id: str) -> dict[str, ScenarioConfig]:
    """
    Load ALL scenarios for a session from Redis via MemoManager.
    
    Supports both new format (session_scenarios_all) and legacy format (session_scenario_config).
    
    Returns dict of scenario_name -> ScenarioConfig.
    """
    if not _redis_manager:
        return {}
    
    try:
        from src.stateful.state_managment import MemoManager
        
        memo = MemoManager.from_redis(session_id, _redis_manager)
        
        # Try new multi-scenario format first
        all_scenarios_data = memo.get_value_from_corememory(SCENARIO_KEY_ALL)
        active_name = memo.get_value_from_corememory(SCENARIO_KEY_ACTIVE)
        
        if all_scenarios_data and isinstance(all_scenarios_data, dict):
            # New format: dict of {scenario_name: scenario_data}
            loaded_scenarios: dict[str, ScenarioConfig] = {}
            for scenario_name, scenario_data in all_scenarios_data.items():
                try:
                    scenario = _parse_scenario_data(scenario_data)
                    loaded_scenarios[scenario_key(scenario_name)] = scenario
                except Exception as e:
                    logger.warning("Failed to parse scenario '%s': %s", scenario_name, e)
            
            if loaded_scenarios:
                # Merge with existing in-memory cache, but let Redis win.
                # In a multi-worker deployment, Redis is the shared source of
                # truth and this worker's in-memory cache may be stale.
                existing = _session_scenarios.get(session_id, {})
                merged = {**existing, **loaded_scenarios}
                _session_scenarios[session_id] = merged
                
                # Set active scenario — normalize to lowercase for matching
                active_key = (active_name or "").lower()
                if active_key and active_key in merged:
                    _active_scenario[session_id] = active_key
                elif merged:
                    # Keep cached active only if it still exists; otherwise
                    # choose a deterministic fallback from the merged set.
                    cached_active = _active_scenario.get(session_id)
                    if not cached_active or cached_active not in merged:
                        _active_scenario[session_id] = next(iter(merged.keys()))
                
                logger.info(
                    "Loaded %d scenarios from Redis | session=%s active=%s",
                    len(loaded_scenarios),
                    session_id,
                    _active_scenario.get(session_id),
                )
                return loaded_scenarios
        
        # Fall back to legacy single-scenario format
        legacy_data = memo.get_value_from_corememory(SCENARIO_KEY_CONFIG)
        if legacy_data:
            scenario = _parse_scenario_data(legacy_data)
            normalized_name = scenario_key(scenario.name)
            
            # Cache in memory
            if session_id not in _session_scenarios:
                _session_scenarios[session_id] = {}
            _session_scenarios[session_id][normalized_name] = scenario
            _active_scenario[session_id] = normalized_name
            
            logger.info(
                "Loaded scenario from Redis (legacy format) | session=%s scenario=%s",
                session_id,
                normalized_name,
            )
            return {normalized_name: scenario}
        
        return {}
    except Exception as e:
        logger.warning("Failed to load scenarios from Redis: %s", e)
        return {}


def _load_scenario_from_redis(session_id: str) -> ScenarioConfig | None:
    """
    Load scenario config from Redis via MemoManager.
    
    Returns the active ScenarioConfig if found, None otherwise.
    Delegates to _load_scenarios_from_redis for actual loading.
    """
    scenarios = _load_scenarios_from_redis(session_id)
    if not scenarios:
        return None
    
    # Return the active scenario
    active_name = _active_scenario.get(session_id)
    if active_name and active_name in scenarios:
        return scenarios[active_name]
    
    # Return first scenario as fallback
    return next(iter(scenarios.values()), None)


def _ensure_session_loaded(session_id: str, *, force: bool = False) -> None:
    """
    Ensure all scenarios for a session are merged from Redis into memory.

    Skips the Redis round-trip when the session was loaded within the last
    ``_REDIS_LOAD_COOLDOWN_S`` seconds (default 2 s) unless *force* is True.
    This prevents hammering Redis during rapid successive reads (e.g.,
    frontend polling or repeated GET /scenarios calls).

    Merge strategy: Redis data is the base, in-memory data overrides
    (in-memory is considered more recent).
    """
    if not force and session_id in _session_scenarios:
        last_load = _session_load_times.get(session_id, 0)
        if (time.monotonic() - last_load) < _REDIS_LOAD_COOLDOWN_S:
            return

    loaded = _load_scenarios_from_redis(session_id)
    _session_load_times[session_id] = time.monotonic()
    # _load_scenarios_from_redis normally updates _session_scenarios as a
    # side effect.  But if it returned data without updating the dict
    # (e.g., Redis unavailable, or the function was mocked), merge the
    # returned data explicitly so callers always see a complete picture.
    if session_id not in _session_scenarios:
        _session_scenarios[session_id] = loaded if loaded else {}
    elif loaded:
        for key, sc in loaded.items():
            if key not in _session_scenarios[session_id]:
                _session_scenarios[session_id][key] = sc


def get_session_scenario(session_id: str, scenario_name: str | None = None) -> ScenarioConfig | None:
    """
    Get dynamic scenario for a session.
    
    First checks in-memory cache, then falls back to Redis if not found.
    Uses case-insensitive lookup for scenario_name.
    
    Args:
        session_id: The session ID
        scenario_name: Optional scenario name. If not provided, returns the active scenario.
    
    Returns:
        The ScenarioConfig if found, None otherwise.
    """
    session_scenarios = _session_scenarios.get(session_id, {})
    
    # Check in-memory cache first
    if session_scenarios:
        if scenario_name:
            # Case-insensitive lookup
            _, result = find_scenario_by_name(session_scenarios, scenario_name)
            if result:
                return result
            # Not found in current cache; force a Redis merge and try once more.
            # This handles stale/partial worker memory when scenarios were
            # created or updated on a different worker.
            _ensure_session_loaded(session_id)
            refreshed = _session_scenarios.get(session_id, {})
            _, result = find_scenario_by_name(refreshed, scenario_name)
            if result:
                return result
        else:
            # Return active scenario if set, otherwise first scenario
            active_key = _active_scenario.get(session_id)
            if active_key and active_key in session_scenarios:
                return session_scenarios[active_key]
            return next(iter(session_scenarios.values()), None)
    
    # Not in memory - try loading from Redis
    redis_scenario = _load_scenario_from_redis(session_id)
    if redis_scenario:
        if scenario_name is None:
            return redis_scenario
        # Case-insensitive compare
        if scenario_key(redis_scenario.name) == scenario_key(scenario_name):
            return redis_scenario
    
    return None


def get_session_scenarios(session_id: str) -> dict[str, ScenarioConfig]:
    """
    Get all dynamic scenarios for a session.
    
    Falls back to Redis if memory cache is empty.
    """
    scenarios = _session_scenarios.get(session_id, {})
    
    # Fall back to Redis if memory cache is empty
    if not scenarios:
        # Use the multi-scenario loader to get all scenarios
        scenarios = _load_scenarios_from_redis(session_id)
    
    return dict(scenarios)


def get_active_scenario_name(session_id: str) -> str | None:
    """
    Get the name of the currently active scenario for a session.
    
    Falls back to Redis if not found in memory cache.
    """
    active_name = _active_scenario.get(session_id)

    # If we have a cached active and the session scenarios are present,
    # trust it only while it still points to an existing key.
    session_scenarios = _session_scenarios.get(session_id)
    if active_name and session_scenarios and active_name in session_scenarios:
        return active_name

    # Otherwise refresh from Redis and return the reconciled active key.
    scenario = _load_scenario_from_redis(session_id)
    if scenario:
        return _active_scenario.get(session_id)

    return active_name


def _serialize_scenario(scenario: ScenarioConfig) -> dict:
    """Serialize a ScenarioConfig to a dict for JSON storage."""
    # Serialize agent_defaults if present
    agent_defaults_data = None
    if scenario.agent_defaults:
        agent_defaults_data = {
            "greeting": scenario.agent_defaults.greeting,
            "return_greeting": scenario.agent_defaults.return_greeting,
            "description": scenario.agent_defaults.description,
            "template_vars": scenario.agent_defaults.template_vars or {},
            "voice_name": scenario.agent_defaults.voice_name,
            "voice_rate": scenario.agent_defaults.voice_rate,
        }
    
    # Serialize generic_handoff config
    generic_handoff_data = {
        "enabled": scenario.generic_handoff.enabled,
        "allowed_targets": scenario.generic_handoff.allowed_targets,
        "require_client_id": scenario.generic_handoff.require_client_id,
        "default_type": scenario.generic_handoff.default_type,
        "share_context": scenario.generic_handoff.share_context,
    }
    
    return {
        "name": scenario.name,
        "description": scenario.description,
        "icon": scenario.icon,
        "agents": scenario.agents,
        "agent_defaults": agent_defaults_data,
        "global_template_vars": scenario.global_template_vars or {},
        "tools": scenario.tools or [],
        "start_agent": scenario.start_agent,
        "handoff_type": scenario.handoff_type,
        "handoffs": [
            {
                "from_agent": h.from_agent,
                "to_agent": h.to_agent,
                "tool": h.tool,
                "type": h.type,
                "share_context": h.share_context,
                "handoff_condition": h.handoff_condition,
                "context_vars": h.context_vars or {},
            }
            for h in (scenario.handoffs or [])
        ],
        "generic_handoff": generic_handoff_data,
    }


def _persist_scenario_to_redis(session_id: str, scenario: ScenarioConfig) -> None:
    """
    Persist ALL scenarios for a session to Redis via MemoManager.
    
    Stores all scenarios in 'session_scenarios_all' dict, indexed by name.
    Uses asyncio to schedule persistence but logs if it fails.
    """
    if not _redis_manager:
        logger.debug("No Redis manager available, skipping persistence")
        return
    
    try:
        from src.stateful.state_managment import MemoManager
        
        memo = MemoManager.from_redis(session_id, _redis_manager)
        
        # _ensure_session_loaded already merges Redis → in-memory, so we
        # just serialize whatever is in _session_scenarios right now.
        all_scenarios_data = {
            name: _serialize_scenario(sc)
            for name, sc in _session_scenarios.get(session_id, {}).items()
        }
        
        memo.set_corememory(SCENARIO_KEY_ALL, all_scenarios_data)
        memo.set_corememory(SCENARIO_KEY_ACTIVE, scenario_key(scenario.name))
        memo.set_corememory(SCENARIO_KEY_CONFIG, _serialize_scenario(scenario))
        
        if scenario.start_agent:
            memo.set_corememory("active_agent", scenario.start_agent)
        
        # Schedule async persistence with proper error handling
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_persist_async(memo, session_id, scenario.name))
            task.add_done_callback(_log_persistence_result)
            _session_load_times[session_id] = time.monotonic()
        except RuntimeError:
            logger.debug("No event loop, skipping async Redis persistence")
        
        logger.debug(
            "All scenarios queued for Redis persistence | session=%s count=%d active=%s",
            session_id,
            len(all_scenarios_data),
            scenario.name,
        )
    except Exception as e:
        logger.warning("Failed to persist scenarios to Redis: %s", e)


async def _persist_async(memo, session_id: str, scenario_name: str) -> None:
    """Async helper to persist MemoManager to Redis."""
    try:
        await memo.persist_to_redis_async(_redis_manager)
        logger.debug("Scenario persisted to Redis | session=%s scenario=%s", session_id, scenario_name)
    except Exception as e:
        logger.error("Failed to persist scenario to Redis | session=%s error=%s", session_id, e)
        raise


def _log_persistence_result(task) -> None:
    """Callback to log persistence task result."""
    if task.cancelled():
        logger.warning("Scenario persistence task was cancelled")
    elif task.exception():
        logger.error("Scenario persistence failed: %s", task.exception())


def _clear_scenario_from_redis(session_id: str) -> None:
    """Clear ALL scenario config from Redis via MemoManager."""
    if not _redis_manager:
        return
    
    try:
        from src.stateful.state_managment import MemoManager
        
        memo = MemoManager.from_redis(session_id, _redis_manager)
        # Clear all scenario-related keys using standardized constants
        memo.set_corememory(SCENARIO_KEY_ALL, None)
        memo.set_corememory(SCENARIO_KEY_CONFIG, None)
        memo.set_corememory(SCENARIO_KEY_ACTIVE, None)
        
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(memo.persist_to_redis_async(_redis_manager))
        except RuntimeError:
            logger.debug("No event loop, skipping async Redis clear")
        
        logger.debug("All scenarios cleared from Redis | session=%s", session_id)
    except Exception as e:
        logger.warning("Failed to clear scenarios from Redis: %s", e)


def _activate_scenario_core(session_id: str, scenario_name: str) -> tuple[str, ScenarioConfig] | None:
    """Lookup, set active in-memory, notify callback. Returns (key, scenario) or None."""
    # Check in-memory first to avoid a Redis round-trip when the scenario
    # is already cached (common case for single-worker and rapid switches).
    session_scenarios = _session_scenarios.get(session_id, {})
    actual_key, scenario = find_scenario_by_name(session_scenarios, scenario_name)
    if not scenario:
        # Fall back to Redis — scenario may have been created on another worker
        _ensure_session_loaded(session_id, force=True)
        session_scenarios = _session_scenarios.get(session_id, {})
        actual_key, scenario = find_scenario_by_name(session_scenarios, scenario_name)
        if not scenario:
            return None

    _active_scenario[session_id] = actual_key

    if _scenario_update_callback:
        try:
            _scenario_update_callback(session_id, scenario)
        except Exception as e:
            logger.warning("Failed to update adapter with scenario: %s", e)

    return actual_key, scenario


def set_active_scenario(session_id: str, scenario_name: str) -> bool:
    """
    Set the active scenario for a session.
    
    Uses case-insensitive lookup for scenario_name.
    
    Returns True if the scenario exists and was set as active.
    """
    result = _activate_scenario_core(session_id, scenario_name)
    if not result:
        return False

    actual_key, scenario = result

    # Fire-and-forget async persist
    if _redis_manager:
        try:
            from src.stateful.state_managment import MemoManager
            memo = MemoManager.from_redis(session_id, _redis_manager)
            memo.set_corememory(SCENARIO_KEY_ACTIVE, actual_key)
            if scenario.start_agent:
                memo.set_corememory("active_agent", scenario.start_agent)
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(memo.persist_to_redis_async(_redis_manager))
                _session_load_times[session_id] = time.monotonic()
            except RuntimeError:
                pass
        except Exception as e:
            logger.warning("Failed to persist active scenario to Redis: %s", e)

    logger.info(
        "Active scenario set | session=%s scenario=%s start_agent=%s",
        session_id, actual_key, scenario.start_agent,
    )
    return True


async def set_active_scenario_async(session_id: str, scenario_name: str) -> bool:
    """
    Set the active scenario for a session (async version with guaranteed persistence).

    Same as set_active_scenario() but awaits Redis persistence instead of
    fire-and-forget.  Use this in async FastAPI endpoints.

    Returns True if the scenario exists and was set as active.
    """
    result = _activate_scenario_core(session_id, scenario_name)
    if not result:
        return False

    actual_key, scenario = result

    if _redis_manager:
        try:
            from src.stateful.state_managment import MemoManager
            memo = MemoManager.from_redis(session_id, _redis_manager)
            memo.set_corememory(SCENARIO_KEY_ACTIVE, actual_key)
            if scenario.start_agent:
                memo.set_corememory("active_agent", scenario.start_agent)
            await memo.persist_to_redis_async(_redis_manager)
            # Mark session as fresh — the in-memory state IS Redis state now,
            # so subsequent reads within the cooldown window can skip HGETALL.
            _session_load_times[session_id] = time.monotonic()
        except Exception as e:
            logger.warning("Failed to persist active scenario to Redis: %s", e)

    logger.info(
        "Active scenario set (async) | session=%s scenario=%s start_agent=%s",
        session_id, actual_key, scenario.start_agent,
    )
    return True


def set_session_scenario(session_id: str, scenario: ScenarioConfig) -> None:
    """
    Set dynamic scenario for a session (sync version).

    This is the single integration point - it both:
    1. Stores the scenario in the local cache (by name within the session)
    2. Sets it as the active scenario
    3. Notifies the orchestrator adapter (if callback registered)
    4. Schedules async persistence to Redis

    For guaranteed persistence, use set_session_scenario_async() in async contexts.
    
    Scenario names are normalized to lowercase for case-insensitive storage.
    If a scenario with the same name (case-insensitive) already exists, it is updated.
    """
    # Always merge Redis state into memory to prevent losing custom
    # scenarios that exist in Redis but not in this worker's memory
    # (e.g., created on another worker or before a restart).
    _ensure_session_loaded(session_id)
    
    # Normalize scenario key to lowercase for case-insensitive storage
    normalized_key = scenario_key(scenario.name)
    if not normalized_key:
        logger.warning("Skipping session scenario set: empty scenario name | session=%s", session_id)
        return
    
    # Remove any existing scenario with different casing (to avoid duplicates)
    keys_to_remove = [k for k in _session_scenarios[session_id] if k.lower() == normalized_key and k != normalized_key]
    for old_key in keys_to_remove:
        del _session_scenarios[session_id][old_key]
        logger.debug("Removed duplicate scenario key | session=%s old_key=%s new_key=%s", session_id, old_key, normalized_key)
    
    _session_scenarios[session_id][normalized_key] = scenario
    _active_scenario[session_id] = normalized_key

    # Notify the orchestrator adapter if callback is registered
    adapter_updated = False
    if _scenario_update_callback:
        try:
            adapter_updated = _scenario_update_callback(session_id, scenario)
        except Exception as e:
            logger.warning("Failed to update adapter with scenario: %s", e)

    # Persist to Redis for durability (async, fire-and-forget)
    _persist_scenario_to_redis(session_id, scenario)

    logger.info(
        "Session scenario set | session=%s scenario=%s start_agent=%s agents=%d handoffs=%d adapter_updated=%s",
        session_id,
        scenario.name,
        scenario.start_agent,
        len(scenario.agents),
        len(scenario.handoffs),
        adapter_updated,
    )


async def set_session_scenario_async(session_id: str, scenario: ScenarioConfig) -> None:
    """
    Set dynamic scenario for a session (async version with guaranteed persistence).

    Use this in async contexts (e.g., FastAPI endpoints) to ensure the scenario
    is persisted to Redis before returning to the caller.

    This prevents data loss on browser refresh or server restart.
    
    Scenario names are normalized to lowercase for case-insensitive storage.
    If a scenario with the same name (case-insensitive) already exists, it is updated.
    """
    # Always merge Redis state into memory to prevent losing custom
    # scenarios that exist in Redis but not in this worker's memory
    # (e.g., created on another worker or before a restart).
    _ensure_session_loaded(session_id)
    
    # Normalize scenario key to lowercase for case-insensitive storage
    normalized_key = scenario_key(scenario.name)
    if not normalized_key:
        logger.warning("Skipping async session scenario set: empty scenario name | session=%s", session_id)
        return
    
    # Remove any existing scenario with different casing (to avoid duplicates)
    keys_to_remove = [k for k in _session_scenarios[session_id] if k.lower() == normalized_key and k != normalized_key]
    for old_key in keys_to_remove:
        del _session_scenarios[session_id][old_key]
        logger.debug("Removed duplicate scenario key | session=%s old_key=%s new_key=%s", session_id, old_key, normalized_key)
    
    _session_scenarios[session_id][normalized_key] = scenario
    _active_scenario[session_id] = normalized_key

    # Notify the orchestrator adapter if callback is registered
    adapter_updated = False
    if _scenario_update_callback:
        try:
            adapter_updated = _scenario_update_callback(session_id, scenario)
        except Exception as e:
            logger.warning("Failed to update adapter with scenario: %s", e)

    # Persist to Redis with await to guarantee completion
    await _persist_scenario_to_redis_async(session_id, scenario)

    logger.info(
        "Session scenario set (async) | session=%s scenario=%s start_agent=%s agents=%d handoffs=%d adapter_updated=%s",
        session_id,
        scenario.name,
        scenario.start_agent,
        len(scenario.agents),
        len(scenario.handoffs),
        adapter_updated,
    )


async def _persist_scenario_to_redis_async(session_id: str, scenario: ScenarioConfig) -> None:
    """
    Async version of scenario persistence to Redis.
    
    Persists ALL scenarios for the session to ensure no data loss.
    Awaits the persistence to ensure data is written before returning.
    """
    if not _redis_manager:
        logger.debug("No Redis manager available, skipping persistence")
        return
    
    try:
        from src.stateful.state_managment import MemoManager
        
        memo = MemoManager.from_redis(session_id, _redis_manager)
        
        # _ensure_session_loaded already merges Redis → in-memory, so we
        # just serialize whatever is in _session_scenarios right now.
        all_scenarios_data = {
            name: _serialize_scenario(sc)
            for name, sc in _session_scenarios.get(session_id, {}).items()
        }
        
        memo.set_corememory(SCENARIO_KEY_ALL, all_scenarios_data)
        memo.set_corememory(SCENARIO_KEY_ACTIVE, scenario_key(scenario.name))
        memo.set_corememory(SCENARIO_KEY_CONFIG, _serialize_scenario(scenario))
        
        if scenario.start_agent:
            memo.set_corememory("active_agent", scenario.start_agent)
        
        # Await persistence with raise_on_failure to detect silent Redis
        # write failures.  Without this, store_session_data_async may return
        # False (write failed) yet the caller would never know, leading to
        # /create returning 200 while the data never reaches Redis — and a
        # subsequent /active on another worker would 404.
        await memo.persist_to_redis_async(_redis_manager, raise_on_failure=True)
        # Mark session as fresh so reads within the cooldown skip HGETALL.
        _session_load_times[session_id] = time.monotonic()
        
        logger.debug(
            "All scenarios persisted to Redis (async) | session=%s count=%d active=%s",
            session_id,
            len(all_scenarios_data),
            scenario.name,
        )
    except Exception as e:
        logger.error("Failed to persist scenario to Redis: %s", e)
        raise


def remove_session_scenario(session_id: str, scenario_name: str | None = None) -> bool:
    """
    Remove dynamic scenario(s) for a session.
    
    Args:
        session_id: The session ID
        scenario_name: Optional scenario name. If not provided, removes ALL scenarios for the session.
    
    Returns:
        True if removed, False if not found.
    """
    if session_id not in _session_scenarios:
        return False
    
    if scenario_name:
        # Remove specific scenario
        if scenario_name in _session_scenarios[session_id]:
            del _session_scenarios[session_id][scenario_name]
            logger.info("Session scenario removed | session=%s scenario=%s", session_id, scenario_name)
            
            # Update active scenario if needed
            if _active_scenario.get(session_id) == scenario_name:
                remaining = _session_scenarios[session_id]
                if remaining:
                    _active_scenario[session_id] = next(iter(remaining.keys()))
                else:
                    del _active_scenario[session_id]
                    # Clear from Redis when no scenarios remain
                    _clear_scenario_from_redis(session_id)
            
            # Clean up empty session
            if not _session_scenarios[session_id]:
                del _session_scenarios[session_id]
            return True
        return False
    else:
        # Remove all scenarios for session
        del _session_scenarios[session_id]
        if session_id in _active_scenario:
            del _active_scenario[session_id]
        # Clear from Redis
        _clear_scenario_from_redis(session_id)
        logger.info("All session scenarios removed | session=%s", session_id)
        return True


def list_session_scenarios() -> dict[str, ScenarioConfig]:
    """
    Return a flat dict of all session scenarios across all sessions.
    
    Key format: "{session_id}:{scenario_name}" to ensure uniqueness.
    """
    result: dict[str, ScenarioConfig] = {}
    for session_id, scenarios in _session_scenarios.items():
        for scenario_name, scenario in scenarios.items():
            result[f"{session_id}:{scenario_name}"] = scenario
    return result


def list_session_scenarios_by_session(session_id: str) -> dict[str, ScenarioConfig]:
    """
    Return all scenarios for a specific session (deduplicated by name, case-insensitive).

    Always merges Redis state before returning so a worker with a non-empty but
    stale/partial in-memory cache does not hide scenarios created elsewhere.
    """
    # Always refresh/merge from Redis first. This prevents returning stale
    # empty/partial scenario lists when this worker has outdated in-memory data.
    _ensure_session_loaded(session_id)
    scenarios = _session_scenarios.get(session_id, {})

    logger.debug(
        "Listing session scenarios | session=%s count=%d",
        session_id,
        len(scenarios),
    )
    
    # Deduplicate by lowercase name (keep latest)
    deduplicated: dict[str, ScenarioConfig] = {}
    for key, scenario in scenarios.items():
        normalized_key = key.lower()
        deduplicated[normalized_key] = scenario
    
    return deduplicated


__all__ = [
    "get_session_scenario",
    "get_session_scenarios",
    "get_active_scenario_name",
    "set_active_scenario",
    "set_active_scenario_async",
    "set_session_scenario",
    "set_session_scenario_async",
    "set_redis_manager",
    "remove_session_scenario",
    "list_session_scenarios",
    "list_session_scenarios_by_session",
    "register_scenario_update_callback",
]
