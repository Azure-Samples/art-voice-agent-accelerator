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
- _session_scenarios: dict[session_id, dict[scenario_name, ScenarioConfig]]
  In-memory cache for fast access. Also persisted to Redis via MemoManager.
- _active_scenario: dict[session_id, scenario_name]
  Tracks which scenario is currently active for each session.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from apps.artagent.backend.registries.scenariostore.loader import ScenarioConfig

logger = get_logger(__name__)

# Session-scoped dynamic scenarios: session_id -> {scenario_name -> ScenarioConfig}
_session_scenarios: dict[str, dict[str, ScenarioConfig]] = {}

# Track the active scenario for each session: session_id -> scenario_name
_active_scenario: dict[str, str] = {}

# Callback for notifying the orchestrator adapter of scenario updates
_scenario_update_callback: Callable[[str, ScenarioConfig], bool] | None = None

# Redis manager reference (set by main.py startup)
_redis_manager: Any = None


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
        all_scenarios_data = memo.get_value_from_corememory("session_scenarios_all")
        active_name = memo.get_value_from_corememory("active_scenario_name")
        
        if all_scenarios_data and isinstance(all_scenarios_data, dict):
            # New format: dict of {scenario_name: scenario_data}
            loaded_scenarios: dict[str, ScenarioConfig] = {}
            for scenario_name, scenario_data in all_scenarios_data.items():
                try:
                    scenario = _parse_scenario_data(scenario_data)
                    loaded_scenarios[scenario_name] = scenario
                except Exception as e:
                    logger.warning("Failed to parse scenario '%s': %s", scenario_name, e)
            
            if loaded_scenarios:
                # Cache in memory
                _session_scenarios[session_id] = loaded_scenarios
                
                # Set active scenario
                if active_name and active_name in loaded_scenarios:
                    _active_scenario[session_id] = active_name
                else:
                    # Default to first scenario
                    _active_scenario[session_id] = next(iter(loaded_scenarios.keys()))
                
                logger.info(
                    "Loaded %d scenarios from Redis | session=%s active=%s",
                    len(loaded_scenarios),
                    session_id,
                    _active_scenario.get(session_id),
                )
                return loaded_scenarios
        
        # Fall back to legacy single-scenario format
        legacy_data = memo.get_value_from_corememory("session_scenario_config")
        if legacy_data:
            scenario = _parse_scenario_data(legacy_data)
            
            # Cache in memory
            if session_id not in _session_scenarios:
                _session_scenarios[session_id] = {}
            _session_scenarios[session_id][scenario.name] = scenario
            _active_scenario[session_id] = scenario.name
            
            logger.info(
                "Loaded scenario from Redis (legacy format) | session=%s scenario=%s",
                session_id,
                scenario.name,
            )
            return {scenario.name: scenario}
        
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


def get_session_scenario(session_id: str, scenario_name: str | None = None) -> ScenarioConfig | None:
    """
    Get dynamic scenario for a session.
    
    First checks in-memory cache, then falls back to Redis if not found.
    
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
            result = session_scenarios.get(scenario_name)
            if result:
                return result
        else:
            # Return active scenario if set, otherwise first scenario
            active_name = _active_scenario.get(session_id)
            if active_name and active_name in session_scenarios:
                return session_scenarios[active_name]
            return next(iter(session_scenarios.values()), None)
    
    # Not in memory - try loading from Redis
    redis_scenario = _load_scenario_from_redis(session_id)
    if redis_scenario:
        if scenario_name is None or redis_scenario.name == scenario_name:
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
    
    # Fall back to Redis if not in memory
    if not active_name:
        scenario = _load_scenario_from_redis(session_id)
        if scenario:
            # _load_scenario_from_redis sets _active_scenario
            active_name = _active_scenario.get(session_id)
    
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
        
        # Build dict of ALL scenarios for this session
        session_scenarios = _session_scenarios.get(session_id, {})
        all_scenarios_data = {}
        for name, sc in session_scenarios.items():
            all_scenarios_data[name] = _serialize_scenario(sc)
        
        # Ensure the current scenario is included
        if scenario.name not in all_scenarios_data:
            all_scenarios_data[scenario.name] = _serialize_scenario(scenario)
        
        # Store all scenarios and active name
        memo.set_corememory("session_scenarios_all", all_scenarios_data)
        memo.set_corememory("active_scenario_name", scenario.name)
        
        # Also store legacy format for backward compatibility
        memo.set_corememory("session_scenario_config", _serialize_scenario(scenario))
        
        # Schedule async persistence with proper error handling
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_persist_async(memo, session_id, scenario.name))
            # Add callback to log errors
            task.add_done_callback(_log_persistence_result)
        except RuntimeError:
            # No running loop - skip async persistence
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
        # Clear both new and legacy format keys
        memo.set_corememory("session_scenarios_all", None)
        memo.set_corememory("session_scenario_config", None)
        memo.set_corememory("active_scenario_name", None)
        
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(memo.persist_to_redis_async(_redis_manager))
        except RuntimeError:
            logger.debug("No event loop, skipping async Redis clear")
        
        logger.debug("All scenarios cleared from Redis | session=%s", session_id)
    except Exception as e:
        logger.warning("Failed to clear scenarios from Redis: %s", e)


def set_active_scenario(session_id: str, scenario_name: str) -> bool:
    """
    Set the active scenario for a session.
    
    Returns True if the scenario exists and was set as active.
    """
    session_scenarios = _session_scenarios.get(session_id, {})
    if scenario_name in session_scenarios:
        _active_scenario[session_id] = scenario_name
        logger.info("Active scenario set | session=%s scenario=%s", session_id, scenario_name)
        return True
    return False


def set_session_scenario(session_id: str, scenario: ScenarioConfig) -> None:
    """
    Set dynamic scenario for a session (sync version).

    This is the single integration point - it both:
    1. Stores the scenario in the local cache (by name within the session)
    2. Sets it as the active scenario
    3. Notifies the orchestrator adapter (if callback registered)
    4. Schedules async persistence to Redis

    For guaranteed persistence, use set_session_scenario_async() in async contexts.
    """
    if session_id not in _session_scenarios:
        _session_scenarios[session_id] = {}
    
    _session_scenarios[session_id][scenario.name] = scenario
    _active_scenario[session_id] = scenario.name

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
    """
    if session_id not in _session_scenarios:
        _session_scenarios[session_id] = {}
    
    _session_scenarios[session_id][scenario.name] = scenario
    _active_scenario[session_id] = scenario.name

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
        
        # Build dict of ALL scenarios for this session
        session_scenarios = _session_scenarios.get(session_id, {})
        all_scenarios_data = {}
        for name, sc in session_scenarios.items():
            all_scenarios_data[name] = _serialize_scenario(sc)
        
        # Ensure the current scenario is included
        if scenario.name not in all_scenarios_data:
            all_scenarios_data[scenario.name] = _serialize_scenario(scenario)
        
        # Store all scenarios and active name
        memo.set_corememory("session_scenarios_all", all_scenarios_data)
        memo.set_corememory("active_scenario_name", scenario.name)
        
        # Also store legacy format for backward compatibility
        memo.set_corememory("session_scenario_config", _serialize_scenario(scenario))
        
        # Await persistence to ensure completion
        await memo.persist_to_redis_async(_redis_manager)
        
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
    Return all scenarios for a specific session.
    
    Falls back to Redis if memory cache is empty.
    """
    scenarios = _session_scenarios.get(session_id, {})
    
    # Fall back to Redis if memory cache is empty
    if not scenarios:
        # Use the multi-scenario loader to get all scenarios
        scenarios = _load_scenarios_from_redis(session_id)
        if scenarios:
            logger.debug(
                "Loaded session scenarios from Redis | session=%s count=%d",
                session_id,
                len(scenarios),
            )
    
    return dict(scenarios)


__all__ = [
    "get_session_scenario",
    "get_session_scenarios",
    "get_active_scenario_name",
    "set_active_scenario",
    "set_session_scenario",
    "set_session_scenario_async",
    "set_redis_manager",
    "remove_session_scenario",
    "list_session_scenarios",
    "list_session_scenarios_by_session",
    "register_scenario_update_callback",
]
