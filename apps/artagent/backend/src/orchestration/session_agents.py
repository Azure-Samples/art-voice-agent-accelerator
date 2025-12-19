"""
Session Agent Registry
======================

Centralized storage for session-scoped dynamic agents created via Agent Builder.
This module is the single source of truth for session agent state.

Both the agent_builder endpoints and the unified orchestrator import from here,
avoiding circular import issues.

Storage Structure:
- _session_agents: dict[session_id, dict[agent_name, UnifiedAgent]]
  Allows multiple custom agents per session.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from apps.artagent.backend.registries.agentstore.base import UnifiedAgent

logger = get_logger(__name__)

# Session-scoped dynamic agents: session_id -> {agent_name -> UnifiedAgent}
_session_agents: dict[str, dict[str, UnifiedAgent]] = {}

# Callback for notifying the orchestrator adapter of updates
# Set by the unified orchestrator module at import time
_adapter_update_callback: Callable[[str, UnifiedAgent], bool] | None = None


def register_adapter_update_callback(callback: Callable[[str, UnifiedAgent], bool]) -> None:
    """
    Register a callback to be invoked when a session agent is updated.

    This is called by the unified orchestrator to inject updates into live adapters.
    """
    global _adapter_update_callback
    _adapter_update_callback = callback
    logger.debug("Adapter update callback registered")


def get_session_agent(session_id: str, agent_name: str | None = None) -> UnifiedAgent | None:
    """
    Get dynamic agent for a session.
    
    Args:
        session_id: The session ID
        agent_name: Optional agent name. If not provided, returns the first/default agent.
    
    Returns:
        The UnifiedAgent if found, None otherwise.
    """
    session_agents = _session_agents.get(session_id, {})
    if not session_agents:
        return None
    
    if agent_name:
        return session_agents.get(agent_name)
    
    # Return first agent if no name specified (backwards compatibility)
    return next(iter(session_agents.values()), None)


def get_session_agents(session_id: str) -> dict[str, UnifiedAgent]:
    """Get all dynamic agents for a session."""
    return dict(_session_agents.get(session_id, {}))


def set_session_agent(session_id: str, agent: UnifiedAgent) -> None:
    """
    Set dynamic agent for a session.

    This is the single integration point - it both:
    1. Stores the agent in the local cache (by name within the session)
    2. Notifies the orchestrator adapter (if callback registered)

    All downstream components (voice, model, prompt) will automatically
    use the updated configuration.
    """
    if session_id not in _session_agents:
        _session_agents[session_id] = {}
    
    _session_agents[session_id][agent.name] = agent

    # Notify the orchestrator adapter if callback is registered
    adapter_updated = False
    if _adapter_update_callback:
        try:
            adapter_updated = _adapter_update_callback(session_id, agent)
        except Exception as e:
            logger.warning("Failed to update adapter: %s", e)

    logger.info(
        "Session agent set | session=%s agent=%s voice=%s adapter_updated=%s",
        session_id,
        agent.name,
        agent.voice.name if agent.voice else None,
        adapter_updated,
    )


def remove_session_agent(session_id: str, agent_name: str | None = None) -> bool:
    """
    Remove dynamic agent(s) for a session.
    
    Args:
        session_id: The session ID
        agent_name: Optional agent name. If not provided, removes ALL agents for the session.
    
    Returns:
        True if removed, False if not found.
    """
    if session_id not in _session_agents:
        return False
    
    if agent_name:
        # Remove specific agent
        if agent_name in _session_agents[session_id]:
            del _session_agents[session_id][agent_name]
            logger.info("Session agent removed | session=%s agent=%s", session_id, agent_name)
            # Clean up empty session
            if not _session_agents[session_id]:
                del _session_agents[session_id]
            return True
        return False
    else:
        # Remove all agents for session
        del _session_agents[session_id]
        logger.info("All session agents removed | session=%s", session_id)
        return True


def list_session_agents() -> dict[str, UnifiedAgent]:
    """
    Return a flat dict of all session agents across all sessions.
    
    Key format: "{session_id}:{agent_name}" to ensure uniqueness.
    """
    result: dict[str, UnifiedAgent] = {}
    for session_id, agents in _session_agents.items():
        for agent_name, agent in agents.items():
            result[f"{session_id}:{agent_name}"] = agent
    return result


def list_session_agents_by_session(session_id: str) -> dict[str, UnifiedAgent]:
    """Return all agents for a specific session."""
    return dict(_session_agents.get(session_id, {}))


__all__ = [
    "register_adapter_update_callback",
    "get_session_agent",
    "get_session_agents",
    "set_session_agent",
    "remove_session_agent",
    "list_session_agents",
    "list_session_agents_by_session",
]
