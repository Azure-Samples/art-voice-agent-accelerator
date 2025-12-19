"""
Start Agent Resolver
====================

Centralized logic for resolving the starting agent for a session.

Consolidates the scattered start agent resolution from MediaHandler,
config_resolver, and orchestrators into a single source of truth.

Resolution Priority:
1. Session Agent (from Agent Builder UI)
2. Session Scenario start_agent (from Scenario Builder UI)  
3. URL scenario parameter start_agent
4. App state default start_agent
5. First available agent in registry

Usage:
    from apps.artagent.backend.voice.shared.start_agent_resolver import (
        resolve_start_agent,
        StartAgentResult,
    )

    result = resolve_start_agent(
        session_id="session_123",
        scenario_name="banking",
        app_state=request.app.state,
    )

    print(f"Start agent: {result.agent_name} (source: {result.source})")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.artagent.backend.registries.agentstore.base import UnifiedAgent

try:
    from utils.ml_logging import get_logger
    logger = get_logger("voice.shared.start_agent_resolver")
except ImportError:
    import logging
    logger = logging.getLogger("voice.shared.start_agent_resolver")


class StartAgentSource(str, Enum):
    """Source of the resolved start agent."""

    SESSION_AGENT = "session_agent"  # Agent Builder created agent
    SESSION_SCENARIO = "session_scenario"  # Scenario Builder scenario
    URL_SCENARIO = "url_scenario"  # URL parameter scenario
    APP_STATE = "app_state"  # Default from app.state
    FALLBACK = "fallback"  # First available agent


@dataclass
class StartAgentResult:
    """
    Result from start agent resolution.

    Attributes:
        agent_name: Name of the resolved start agent
        agent: The UnifiedAgent instance (or None if not found)
        source: Where the agent was resolved from
        scenario_name: Active scenario name (if any)
        error: Error message if resolution failed
    """

    agent_name: str
    agent: UnifiedAgent | None = None
    source: StartAgentSource = StartAgentSource.FALLBACK
    scenario_name: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Whether resolution succeeded."""
        return self.agent is not None and self.error is None


def _get_session_agent(session_id: str | None) -> tuple[UnifiedAgent | None, str | None]:
    """
    Check for session-scoped agent from Agent Builder.

    Returns:
        Tuple of (agent, agent_name) or (None, None)
    """
    if not session_id:
        return None, None

    try:
        from apps.artagent.backend.src.orchestration.session_agents import get_session_agent
        agent = get_session_agent(session_id)
        if agent:
            return agent, agent.name
    except ImportError:
        logger.debug("session_agents module not available")
    except Exception as e:
        logger.debug("Failed to get session agent: %s", e)

    return None, None


def _get_scenario_start_agent(
    session_id: str | None,
    scenario_name: str | None,
) -> tuple[str | None, str | None, str]:
    """
    Get start agent from scenario configuration.

    Checks session-scoped scenarios first, then URL/env scenarios.

    Returns:
        Tuple of (start_agent_name, scenario_name, source)
    """
    # Try session-scoped scenario first
    if session_id:
        try:
            from apps.artagent.backend.voice.shared.config_resolver import (
                resolve_orchestrator_config,
            )
            config = resolve_orchestrator_config(
                session_id=session_id,
                scenario_name=scenario_name,
            )
            if config.has_scenario:
                source = (
                    StartAgentSource.SESSION_SCENARIO.value
                    if not scenario_name
                    else StartAgentSource.URL_SCENARIO.value
                )
                return config.start_agent, config.scenario_name, source
        except ImportError:
            logger.debug("config_resolver not available")
        except Exception as e:
            logger.debug("Failed to resolve scenario config: %s", e)

    return None, None, ""


def resolve_start_agent(
    *,
    session_id: str | None = None,
    scenario_name: str | None = None,
    app_state: Any | None = None,
    agents: dict[str, UnifiedAgent] | None = None,
) -> StartAgentResult:
    """
    Resolve the starting agent for a session.

    Resolution order:
    1. Session Agent (from Agent Builder)
    2. Session Scenario start_agent (from Scenario Builder)
    3. URL scenario start_agent
    4. App state default
    5. First available agent

    Args:
        session_id: Session identifier
        scenario_name: Scenario name from URL parameter
        app_state: FastAPI app.state
        agents: Agent registry (will use app_state.unified_agents if not provided)

    Returns:
        StartAgentResult with resolved agent
    """
    # Get agent registry
    if agents is None and app_state:
        agents = getattr(app_state, "unified_agents", {})
    agents = agents or {}

    # Priority 1: Session Agent (from Agent Builder)
    session_agent, session_agent_name = _get_session_agent(session_id)
    if session_agent:
        logger.info(
            "Start agent resolved from session agent | session=%s agent=%s",
            session_id,
            session_agent_name,
        )
        return StartAgentResult(
            agent_name=session_agent_name or "CustomAgent",
            agent=session_agent,
            source=StartAgentSource.SESSION_AGENT,
        )

    # Priority 2 & 3: Session or URL Scenario
    scenario_start, resolved_scenario, source_str = _get_scenario_start_agent(
        session_id, scenario_name
    )
    if scenario_start:
        agent = agents.get(scenario_start)
        if agent:
            logger.info(
                "Start agent resolved from scenario | session=%s scenario=%s agent=%s",
                session_id,
                resolved_scenario,
                scenario_start,
            )
            return StartAgentResult(
                agent_name=scenario_start,
                agent=agent,
                source=StartAgentSource(source_str),
                scenario_name=resolved_scenario,
            )
        else:
            logger.warning(
                "Scenario start_agent '%s' not found in registry | scenario=%s",
                scenario_start,
                resolved_scenario,
            )

    # Priority 4: App state default
    if app_state:
        default_start = getattr(app_state, "start_agent", None)
        if default_start:
            agent = agents.get(default_start)
            if agent:
                logger.info(
                    "Start agent resolved from app state | agent=%s",
                    default_start,
                )
                return StartAgentResult(
                    agent_name=default_start,
                    agent=agent,
                    source=StartAgentSource.APP_STATE,
                )

    # Priority 5: First available agent
    if agents:
        first_agent_name = next(iter(agents.keys()))
        first_agent = agents[first_agent_name]
        logger.info(
            "Start agent resolved from fallback (first available) | agent=%s",
            first_agent_name,
        )
        return StartAgentResult(
            agent_name=first_agent_name,
            agent=first_agent,
            source=StartAgentSource.FALLBACK,
        )

    # No agents available
    logger.error("No agents available for start agent resolution")
    return StartAgentResult(
        agent_name="",
        agent=None,
        source=StartAgentSource.FALLBACK,
        error="No agents available in registry",
    )


__all__ = [
    "resolve_start_agent",
    "StartAgentResult",
    "StartAgentSource",
]
