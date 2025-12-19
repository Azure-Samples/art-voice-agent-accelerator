"""
Orchestrator Configuration Resolver
=====================================

Shared configuration resolution for voice channel orchestrators.
Provides scenario-aware agent and handoff map resolution.

CascadeOrchestratorAdapter and LiveOrchestrator use this resolver for:
- Start agent selection
- Agent registry loading
- Handoff map building
- Greeting configuration

Usage:
    from apps.artagent.backend.voice.shared import (
        resolve_orchestrator_config,
        OrchestratorConfigResult,
    )

    # Resolve config (will use scenario if AGENT_SCENARIO is set)
    config = resolve_orchestrator_config()

    # Use resolved values
    adapter = CascadeOrchestratorAdapter.create(
        start_agent=config.start_agent,
        agents=config.agents,
        handoff_map=config.handoff_map,
    )
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.artagent.backend.registries.scenariostore.loader import ScenarioConfig

try:
    from utils.ml_logging import get_logger

    logger = get_logger("voice.shared.config_resolver")
except ImportError:
    import logging

    logger = logging.getLogger("voice.shared.config_resolver")


# ─────────────────────────────────────────────────────────────────────
# Default Configuration
# ─────────────────────────────────────────────────────────────────────

# Unified default start agent name (used by both adapters)
DEFAULT_START_AGENT = "BankingConcierge"

# Environment variable for scenario selection
SCENARIO_ENV_VAR = "AGENT_SCENARIO"


# ─────────────────────────────────────────────────────────────────────
# Configuration Result
# ─────────────────────────────────────────────────────────────────────


@dataclass
class OrchestratorConfigResult:
    """
    Resolved orchestrator configuration.

    Contains all the configuration needed to initialize an orchestrator
    with scenario-aware defaults.

    Attributes:
        start_agent: Name of the starting agent
        agents: Registry of agent definitions
        handoff_map: Tool name → agent name mapping
        scenario: Optional loaded scenario config
        scenario_name: Name of the active scenario (if any)
        template_vars: Global template variables from scenario
    """

    start_agent: str = DEFAULT_START_AGENT
    agents: dict[str, Any] = field(default_factory=dict)
    handoff_map: dict[str, str] = field(default_factory=dict)
    scenario: ScenarioConfig | None = None
    scenario_name: str | None = None
    template_vars: dict[str, Any] = field(default_factory=dict)

    @property
    def has_scenario(self) -> bool:
        """Whether a scenario is active."""
        return self.scenario is not None

    def get_agent(self, name: str) -> Any | None:
        """Get an agent by name."""
        return self.agents.get(name)

    def get_start_agent_config(self) -> Any | None:
        """Get the starting agent configuration."""
        return self.agents.get(self.start_agent)


# ─────────────────────────────────────────────────────────────────────
# Resolution Functions
# ─────────────────────────────────────────────────────────────────────


def _load_base_agents() -> dict[str, Any]:
    """Load agents from the unified agent registry."""
    try:
        from apps.artagent.backend.registries.agentstore.loader import discover_agents

        return discover_agents()
    except ImportError as e:
        logger.warning("Failed to import discover_agents: %s", e)
        return {}


def _build_base_handoff_map(agents: dict[str, Any]) -> dict[str, str]:
    """Build handoff map from agent declarations."""
    try:
        from apps.artagent.backend.registries.agentstore.loader import build_handoff_map

        return build_handoff_map(agents)
    except ImportError as e:
        logger.warning("Failed to import build_handoff_map: %s", e)
        return {}


def _load_scenario(scenario_name: str) -> ScenarioConfig | None:
    """Load a scenario configuration."""
    try:
        from apps.artagent.backend.registries.scenariostore import load_scenario

        return load_scenario(scenario_name)
    except ImportError as e:
        logger.warning("Failed to import load_scenario: %s", e)
        return None


def _get_scenario_agents(scenario_name: str) -> dict[str, Any]:
    """Get agents with scenario overrides applied."""
    try:
        from apps.artagent.backend.registries.scenariostore import get_scenario_agents

        return get_scenario_agents(scenario_name)
    except ImportError as e:
        logger.warning("Failed to import get_scenario_agents: %s", e)
        return _load_base_agents()


def _build_agents_from_session_scenario(scenario: ScenarioConfig) -> dict[str, Any]:
    """
    Build agent registry from a session-scoped scenario.
    
    Session scenarios specify which agents to include via ScenarioConfig.agents list (list of names).
    If the list is empty, all base agents are included.
    
    Note: We preserve UnifiedAgent objects as-is to maintain compatibility with downstream
    orchestrator adapters that expect UnifiedAgent instances.
    """
    # Start with base agents (dict of UnifiedAgent objects)
    base_agents = _load_base_agents()
    
    # If scenario specifies agent list, filter to only those agents
    if scenario.agents:
        # scenario.agents is list[str] of agent names to include
        filtered_agents = {}
        for agent_name in scenario.agents:
            if agent_name in base_agents:
                # Preserve the UnifiedAgent object directly
                filtered_agents[agent_name] = base_agents[agent_name]
            else:
                # Agent not found in base - log warning but skip
                logger.warning(
                    "Scenario agent '%s' not found in base agents, skipping",
                    agent_name,
                )
        base_agents = filtered_agents
    
    logger.debug(
        "Built agents from session scenario | included=%s start_agent=%s",
        list(base_agents.keys()),
        scenario.start_agent,
    )
    
    return base_agents


def resolve_orchestrator_config(
    *,
    session_id: str | None = None,
    scenario_name: str | None = None,
    start_agent: str | None = None,
    agents: dict[str, Any] | None = None,
    handoff_map: dict[str, str] | None = None,
) -> OrchestratorConfigResult:
    """
    Resolve orchestrator configuration with scenario support.

    Resolution order:
    1. Explicit parameters (if provided)
    2. Session-scoped scenario (if session_id is provided and session has an active scenario)
    3. Scenario configuration (if AGENT_SCENARIO env var is set)
    4. Default values

    Args:
        session_id: Optional session ID to check for session-scoped scenarios
        scenario_name: Override scenario name (defaults to AGENT_SCENARIO env var)
        start_agent: Override start agent (defaults to scenario or DEFAULT_START_AGENT)
        agents: Override agent registry (defaults to scenario-aware loading)
        handoff_map: Override handoff map (defaults to building from agents)

    Returns:
        OrchestratorConfigResult with resolved configuration
    """
    result = OrchestratorConfigResult()

    # Check for session-scoped scenario first
    session_scenario = None
    if session_id:
        logger.info(
            "Checking for session-scoped scenario | session_id=%s scenario_name=%s",
            session_id,
            scenario_name,
        )
        try:
            from apps.artagent.backend.src.orchestration.session_scenarios import (
                get_session_scenario,
                list_session_scenarios_by_session,
            )
            # Debug: log what scenarios are stored for this session
            stored_scenarios = list_session_scenarios_by_session(session_id)
            if stored_scenarios:
                logger.info(
                    "Session has stored scenarios | session_id=%s scenarios=%s",
                    session_id,
                    list(stored_scenarios.keys()),
                )
                
                # Priority 1: Try to get the active session scenario (ignore URL scenario_name)
                # This ensures custom scenarios created via ScenarioBuilder take precedence
                session_scenario = get_session_scenario(session_id, None)  # Get active scenario
                
                # Priority 2: If no active scenario but scenario_name matches a stored one
                if not session_scenario and scenario_name:
                    session_scenario = get_session_scenario(session_id, scenario_name)
                
            else:
                logger.info("No stored scenarios for session | session_id=%s", session_id)
            
            if session_scenario:
                logger.info(
                    "Found session-scoped scenario | session=%s scenario_name=%s start_agent=%s agents=%s",
                    session_id,
                    session_scenario.name,
                    session_scenario.start_agent,
                    session_scenario.agents,  # agents is list[str]
                )
        except ImportError as e:
            logger.warning("Failed to import session_scenarios: %s", e)
    else:
        logger.info("No session_id provided, skipping session scenario lookup")

    # Use session scenario if available
    if session_scenario:
        result.scenario = session_scenario
        result.scenario_name = getattr(session_scenario, "name", "custom")
        result.template_vars = session_scenario.global_template_vars.copy()
        
        # Use session scenario start_agent if not explicitly overridden
        if start_agent is None and session_scenario.start_agent:
            result.start_agent = session_scenario.start_agent
        
        # Build agents from session scenario
        if agents is None:
            result.agents = _build_agents_from_session_scenario(session_scenario)
        
        # Build handoff map: merge scenario-defined with agent-derived (scenario takes precedence)
        if handoff_map is None:
            # Start with agent-derived handoff_map (from handoff.trigger fields)
            base_handoff_map = _build_base_handoff_map(result.agents)
            # Overlay scenario-defined handoffs (these take precedence)
            scenario_handoff_map = session_scenario.build_handoff_map()
            result.handoff_map = {**base_handoff_map, **scenario_handoff_map}
            logger.debug(
                "Built handoff_map | base=%d scenario=%d total=%d",
                len(base_handoff_map),
                len(scenario_handoff_map),
                len(result.handoff_map),
            )
        
        logger.info(
            "Resolved config with session scenario",
            extra={
                "session_id": session_id,
                "start_agent": result.start_agent,
                "agent_count": len(result.agents),
            },
        )
        
        # Apply explicit overrides
        if agents is not None:
            result.agents = agents
        if start_agent is not None:
            result.start_agent = start_agent
        if handoff_map is not None:
            result.handoff_map = handoff_map
        
        return result

    # Determine scenario name from parameter or environment
    effective_scenario = scenario_name or os.getenv(SCENARIO_ENV_VAR, "").strip()

    if effective_scenario:
        # Load scenario
        scenario = _load_scenario(effective_scenario)

        if scenario:
            result.scenario = scenario
            result.scenario_name = effective_scenario
            result.template_vars = scenario.global_template_vars.copy()

            # Use scenario start_agent if not explicitly overridden
            if start_agent is None and scenario.start_agent:
                result.start_agent = scenario.start_agent

            # Load agents with scenario overrides if not explicitly provided
            if agents is None:
                result.agents = _get_scenario_agents(effective_scenario)

            logger.info(
                "Resolved config with scenario",
                extra={
                    "scenario": effective_scenario,
                    "start_agent": result.start_agent,
                    "agent_count": len(result.agents),
                },
            )
        else:
            logger.warning(
                "Scenario '%s' not found, using defaults",
                effective_scenario,
            )
            # Fall back to base agents
            if agents is None:
                result.agents = _load_base_agents()
    else:
        # No scenario - use base agents
        if agents is None:
            result.agents = _load_base_agents()

    # Apply explicit overrides
    if agents is not None:
        result.agents = agents

    if start_agent is not None:
        result.start_agent = start_agent

    # Build handoff map if not provided
    if handoff_map is not None:
        result.handoff_map = handoff_map
    elif result.scenario:
        # Merge: agent-derived (base) + scenario-defined (overlay, takes precedence)
        base_handoff_map = _build_base_handoff_map(result.agents)
        scenario_handoff_map = result.scenario.build_handoff_map()
        result.handoff_map = {**base_handoff_map, **scenario_handoff_map}
        logger.debug(
            "Built handoff_map from scenario '%s' | base=%d scenario=%d total=%d",
            result.scenario_name,
            len(base_handoff_map),
            len(scenario_handoff_map),
            len(result.handoff_map),
        )
    else:
        # Fall back to building from agent handoff.trigger properties
        result.handoff_map = _build_base_handoff_map(result.agents)

    # Validate start agent exists
    if result.start_agent and result.agents and result.start_agent not in result.agents:
        available = list(result.agents.keys())[:5]
        logger.warning(
            "Start agent '%s' not found in registry. Available: %s",
            result.start_agent,
            available,
        )
        # Fall back to first available or default
        if available:
            result.start_agent = available[0]
            logger.info("Falling back to start agent: %s", result.start_agent)

    return result


def get_scenario_greeting(
    agent_name: str,
    config: OrchestratorConfigResult,
    is_first_visit: bool = True,
) -> str | None:
    """
    Get greeting for an agent from scenario config.

    Args:
        agent_name: Name of the agent
        config: Resolved orchestrator config
        is_first_visit: Whether this is the first visit to this agent

    Returns:
        Greeting string or None if not configured
    """
    agent = config.get_agent(agent_name)
    if not agent:
        return None

    if is_first_visit:
        return getattr(agent, "greeting", None)
    return getattr(agent, "return_greeting", None)


# ─────────────────────────────────────────────────────────────────────
# App State Integration
# ─────────────────────────────────────────────────────────────────────


def resolve_from_app_state(app_state: Any) -> OrchestratorConfigResult:
    """
    Resolve configuration from FastAPI app.state.

    Uses pre-loaded agents and scenario from main.py startup.

    Args:
        app_state: FastAPI app.state object

    Returns:
        OrchestratorConfigResult from app state
    """
    result = OrchestratorConfigResult()

    # Get unified agents from app.state
    result.agents = getattr(app_state, "unified_agents", None) or {}

    # Get handoff map from app.state
    result.handoff_map = getattr(app_state, "handoff_map", None) or {}

    # Get scenario from app.state
    result.scenario = getattr(app_state, "scenario", None)
    if result.scenario:
        result.scenario_name = result.scenario.name
        result.template_vars = result.scenario.global_template_vars.copy()

    # Get start agent from app.state
    result.start_agent = getattr(app_state, "start_agent", DEFAULT_START_AGENT)

    # Build handoff map if not available
    if not result.handoff_map and result.agents:
        result.handoff_map = _build_base_handoff_map(result.agents)

    return result


__all__ = [
    "DEFAULT_START_AGENT",
    "SCENARIO_ENV_VAR",
    "OrchestratorConfigResult",
    "resolve_orchestrator_config",
    "resolve_from_app_state",
    "get_scenario_greeting",
]
