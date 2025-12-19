"""
Scenario Builder Endpoints
==========================

REST endpoints for dynamically creating and managing scenarios at runtime.
Supports session-scoped scenario configurations that can be modified through
the frontend without restarting the backend.

Scenarios define:
- Which agents are available
- Handoff routing between agents (directed graph)
- Handoff behavior (announced vs discrete)
- Agent overrides (greetings, template vars)
- Starting agent

Endpoints:
    GET  /api/v1/scenario-builder/templates     - List available scenario templates
    GET  /api/v1/scenario-builder/templates/{id} - Get scenario template details
    GET  /api/v1/scenario-builder/agents        - List available agents for scenarios
    GET  /api/v1/scenario-builder/defaults      - Get default scenario configuration
    POST /api/v1/scenario-builder/create        - Create dynamic scenario for session
    GET  /api/v1/scenario-builder/session/{session_id} - Get session scenario config
    PUT  /api/v1/scenario-builder/session/{session_id} - Update session scenario config
    DELETE /api/v1/scenario-builder/session/{session_id} - Reset to default scenario
    GET  /api/v1/scenario-builder/sessions      - List all sessions with custom scenarios
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.artagent.backend.registries.agentstore.loader import discover_agents
from apps.artagent.backend.registries.scenariostore.loader import (
    AgentOverride,
    HandoffConfig,
    ScenarioConfig,
    _SCENARIOS_DIR,
    list_scenarios,
    load_scenario,
)
from apps.artagent.backend.registries.toolstore.registry import get_tool_definition
from apps.artagent.backend.src.orchestration.session_agents import (
    list_session_agents,
    list_session_agents_by_session,
)
from apps.artagent.backend.src.orchestration.session_scenarios import (
    get_session_scenario,
    get_session_scenarios,
    list_session_scenarios,
    list_session_scenarios_by_session,
    remove_session_scenario,
    set_session_scenario_async,
)
from utils.ml_logging import get_logger

logger = get_logger("v1.scenario_builder")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class HandoffConfigSchema(BaseModel):
    """Configuration for a handoff route - a directed edge in the agent graph."""

    from_agent: str = Field(..., description="Source agent initiating the handoff")
    to_agent: str = Field(..., description="Target agent receiving the handoff")
    tool: str = Field(..., description="Handoff tool name that triggers this route")
    type: str = Field(
        default="announced",
        description="'discrete' (silent) or 'announced' (greet on switch)",
    )
    share_context: bool = Field(
        default=True, description="Whether to pass conversation context"
    )
    handoff_condition: str = Field(
        default="",
        description="User-defined condition describing when to trigger this handoff. "
        "This text is injected into the source agent's system prompt.",
    )


class AgentOverrideSchema(BaseModel):
    """Override settings for a specific agent in a scenario."""

    greeting: str | None = Field(default=None, description="Custom greeting override")
    return_greeting: str | None = Field(
        default=None, description="Custom return greeting override"
    )
    description: str | None = Field(
        default=None, description="Custom description override"
    )
    template_vars: dict[str, Any] = Field(
        default_factory=dict, description="Template variable overrides"
    )
    voice_name: str | None = Field(default=None, description="Voice name override")
    voice_rate: str | None = Field(default=None, description="Voice rate override")


class DynamicScenarioConfig(BaseModel):
    """Configuration for creating a dynamic scenario."""

    name: str = Field(
        ..., min_length=1, max_length=64, description="Scenario display name"
    )
    description: str = Field(
        default="", max_length=512, description="Scenario description"
    )
    icon: str = Field(
        default="🎭", max_length=8, description="Emoji icon for the scenario"
    )
    agents: list[str] = Field(
        default_factory=list,
        description="List of agent names to include (empty = all agents)",
    )
    start_agent: str | None = Field(
        default=None, description="Starting agent for the scenario"
    )
    handoff_type: str = Field(
        default="announced",
        description="Default handoff behavior ('announced' or 'discrete')",
    )
    handoffs: list[HandoffConfigSchema] = Field(
        default_factory=list,
        description="List of handoff configurations (directed edges)",
    )
    agent_defaults: AgentOverrideSchema | None = Field(
        default=None, description="Default overrides applied to all agents"
    )
    global_template_vars: dict[str, Any] = Field(
        default_factory=dict, description="Global template variables for all agents"
    )
    tools: list[str] = Field(
        default_factory=list, description="Additional tools to register for scenario"
    )


class SessionScenarioResponse(BaseModel):
    """Response for session scenario operations."""

    session_id: str
    scenario_name: str
    status: str
    config: dict[str, Any]
    created_at: float | None = None
    modified_at: float | None = None


class ScenarioTemplateInfo(BaseModel):
    """Scenario template information for frontend display."""

    id: str
    name: str
    description: str
    icon: str = "🎭"
    agents: list[str]
    start_agent: str | None
    handoff_type: str
    handoffs: list[dict[str, Any]]
    global_template_vars: dict[str, Any]


class ToolInfo(BaseModel):
    """Tool information with name and description."""
    
    name: str
    description: str = ""


class AgentInfo(BaseModel):
    """Agent information for scenario configuration."""

    name: str
    description: str
    greeting: str | None = None
    return_greeting: str | None = None
    tools: list[str] = []  # Keep for backward compatibility
    tool_details: list[ToolInfo] = []  # Full tool info with descriptions
    is_entry_point: bool = False
    is_session_agent: bool = False  # True if this is a dynamically created session agent
    session_id: str | None = None  # Session ID if this is a session agent


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/templates",
    response_model=dict[str, Any],
    summary="List Available Scenario Templates",
    description="Get list of all existing scenario configurations that can be used as templates.",
    tags=["Scenario Builder"],
)
async def list_scenario_templates() -> dict[str, Any]:
    """
    List all available scenario templates from the scenarios directory.

    Returns scenario configurations that can be used as starting points
    for creating new dynamic scenarios.
    """
    start = time.time()
    templates: list[ScenarioTemplateInfo] = []

    scenario_names = list_scenarios()

    for name in scenario_names:
        scenario = load_scenario(name)
        if scenario:
            templates.append(
                ScenarioTemplateInfo(
                    id=name,
                    name=scenario.name,
                    description=scenario.description,
                    icon=scenario.icon,
                    agents=scenario.agents,
                    start_agent=scenario.start_agent,
                    handoff_type=scenario.handoff_type,
                    handoffs=[
                        {
                            "from_agent": h.from_agent,
                            "to_agent": h.to_agent,
                            "tool": h.tool,
                            "type": h.type,
                            "share_context": h.share_context,
                            "handoff_condition": h.handoff_condition,
                        }
                        for h in scenario.handoffs
                    ],
                    global_template_vars=scenario.global_template_vars,
                )
            )

    # Sort by name
    templates.sort(key=lambda t: t.name)

    return {
        "status": "success",
        "total": len(templates),
        "templates": [t.model_dump() for t in templates],
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


@router.get(
    "/templates/{template_id}",
    response_model=dict[str, Any],
    summary="Get Scenario Template Details",
    description="Get full details of a specific scenario template.",
    tags=["Scenario Builder"],
)
async def get_scenario_template(template_id: str) -> dict[str, Any]:
    """
    Get the full configuration of a specific scenario template.

    Args:
        template_id: The scenario directory name (e.g., 'banking', 'insurance')
    """
    scenario = load_scenario(template_id)

    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario template '{template_id}' not found",
        )

    return {
        "status": "success",
        "template": {
            "id": template_id,
            "name": scenario.name,
            "description": scenario.description,
            "icon": scenario.icon,
            "agents": scenario.agents,
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
                }
                for h in scenario.handoffs
            ],
            "global_template_vars": scenario.global_template_vars,
            "agent_defaults": (
                {
                    "greeting": scenario.agent_defaults.greeting,
                    "return_greeting": scenario.agent_defaults.return_greeting,
                    "description": scenario.agent_defaults.description,
                    "template_vars": scenario.agent_defaults.template_vars,
                    "voice_name": scenario.agent_defaults.voice_name,
                    "voice_rate": scenario.agent_defaults.voice_rate,
                }
                if scenario.agent_defaults
                else None
            ),
        },
    }


@router.get(
    "/agents",
    response_model=dict[str, Any],
    summary="List Available Agents",
    description="Get list of all registered agents that can be included in scenarios.",
    tags=["Scenario Builder"],
)
async def list_available_agents(session_id: str | None = None) -> dict[str, Any]:
    """
    List all available agents for scenario configuration.

    Returns agent information for building scenario orchestration graphs.
    Includes both static agents from YAML files and dynamic session agents.
    
    If session_id is provided, only returns session agents for that specific session.
    """
    start = time.time()

    def get_tool_details(tool_names: list[str]) -> list[ToolInfo]:
        """Get tool info with descriptions for the given tool names."""
        details = []
        for tool_name in tool_names:
            tool_def = get_tool_definition(tool_name)
            if tool_def:
                # Get description from schema or definition
                desc = tool_def.schema.get("description", "") or tool_def.description
                details.append(ToolInfo(name=tool_name, description=desc))
            else:
                details.append(ToolInfo(name=tool_name, description=""))
        return details

    # Get static agents from registry (YAML files)
    agents_registry = discover_agents()
    agents_list: list[AgentInfo] = []

    for name, agent in agents_registry.items():
        tool_names = agent.tool_names if hasattr(agent, "tool_names") else []
        agents_list.append(
            AgentInfo(
                name=name,
                description=agent.description or "",
                greeting=agent.greeting,
                return_greeting=getattr(agent, "return_greeting", None),
                tools=tool_names,
                tool_details=get_tool_details(tool_names),
                is_entry_point=name.lower() == "concierge"
                or "concierge" in name.lower(),
                is_session_agent=False,
                session_id=None,
            )
        )

    # Get dynamic session agents - use optimized function if filtering by session
    session_agents_added = 0
    if session_id:
        # Efficient: only get agents for this specific session
        session_agents_dict = list_session_agents_by_session(session_id)
        for agent_name, agent in session_agents_dict.items():
            # Check if this session agent already exists in static registry
            existing_names = {a.name for a in agents_list}
            display_name = agent.name

            # If duplicate name, suffix with (session)
            if display_name in existing_names:
                display_name = f"{agent.name} (session)"

            tool_names = agent.tool_names if hasattr(agent, "tool_names") else []
            agents_list.append(
                AgentInfo(
                    name=display_name,
                    description=agent.description or f"Dynamic agent for session {session_id[:8]}",
                    greeting=agent.greeting,
                    return_greeting=getattr(agent, "return_greeting", None),
                    tools=tool_names,
                    tool_details=get_tool_details(tool_names),
                    is_entry_point=False,
                    is_session_agent=True,
                    session_id=session_id,
                )
            )
            session_agents_added += 1
    else:
        # No filter: get all session agents across all sessions
        # list_session_agents() returns {"{session_id}:{agent_name}": agent}
        all_session_agents = list_session_agents()
        for composite_key, agent in all_session_agents.items():
            # Parse the composite key to extract session_id
            parts = composite_key.split(":", 1)
            agent_session_id = parts[0] if len(parts) > 1 else composite_key
            
            # Check if this session agent already exists in static registry
            existing_names = {a.name for a in agents_list}
            agent_name = agent.name

            # If duplicate name, suffix with session ID
            if agent_name in existing_names:
                agent_name = f"{agent.name} (session)"

            tool_names = agent.tool_names if hasattr(agent, "tool_names") else []
            agents_list.append(
                AgentInfo(
                    name=agent_name,
                    description=agent.description or f"Dynamic agent for session {agent_session_id[:8]}",
                    greeting=agent.greeting,
                    return_greeting=getattr(agent, "return_greeting", None),
                    tools=tool_names,
                    tool_details=get_tool_details(tool_names),
                    is_entry_point=False,
                    is_session_agent=True,
                    session_id=agent_session_id,
                )
            )
            session_agents_added += 1

    # Sort by name, with entry points first, then static agents, then session agents
    agents_list.sort(key=lambda a: (a.is_session_agent, not a.is_entry_point, a.name))

    return {
        "status": "success",
        "total": len(agents_list),
        "agents": [a.model_dump() for a in agents_list],
        "static_count": len(agents_registry),
        "session_count": session_agents_added,
        "filtered_by_session": session_id,
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


@router.get(
    "/defaults",
    response_model=dict[str, Any],
    summary="Get Default Scenario Configuration",
    description="Get the default configuration template for creating new scenarios.",
    tags=["Scenario Builder"],
)
async def get_default_config() -> dict[str, Any]:
    """Get default scenario configuration for creating new scenarios."""
    # Get available agents for reference (static + session)
    agents_registry = discover_agents()
    session_agents = list_session_agents()

    # Combine agent names
    agent_names = list(agents_registry.keys())
    # session_agents format: {"{session_id}:{agent_name}": agent}
    for composite_key, agent in session_agents.items():
        if agent.name not in agent_names:
            agent_names.append(agent.name)

    return {
        "status": "success",
        "defaults": {
            "name": "Custom Scenario",
            "description": "",
            "agents": [],  # Empty = all agents
            "start_agent": agent_names[0] if agent_names else None,
            "handoff_type": "announced",
            "handoffs": [],
            "global_template_vars": {
                "company_name": "ART Voice Agent",
                "industry": "general",
            },
            "agent_defaults": None,
        },
        "available_agents": agent_names,
        "handoff_types": ["announced", "discrete"],
    }


@router.post(
    "/create",
    response_model=SessionScenarioResponse,
    summary="Create Dynamic Scenario",
    description="Create a new dynamic scenario configuration for a session.",
    tags=["Scenario Builder"],
)
async def create_dynamic_scenario(
    config: DynamicScenarioConfig,
    session_id: str,
    request: Request,
) -> SessionScenarioResponse:
    """
    Create a dynamic scenario for a specific session.

    This scenario will be used instead of the default for this session.
    The configuration is stored in memory and can be modified at runtime.
    """
    start = time.time()

    # Validate agents exist (include both template agents and session-scoped custom agents)
    agents_registry = discover_agents()
    session_agents = list_session_agents_by_session(session_id)
    all_valid_agents = set(agents_registry.keys()) | set(session_agents.keys())
    if config.agents:
        invalid_agents = [a for a in config.agents if a not in all_valid_agents]
        if invalid_agents:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid agents: {invalid_agents}. Available: {list(all_valid_agents)}",
            )

    # Validate start_agent
    if config.start_agent:
        if config.agents and config.start_agent not in config.agents:
            raise HTTPException(
                status_code=400,
                detail=f"start_agent '{config.start_agent}' must be in agents list",
            )
        if not config.agents and config.start_agent not in all_valid_agents:
            raise HTTPException(
                status_code=400,
                detail=f"start_agent '{config.start_agent}' not found in registry or session agents",
            )

    # Build agent_defaults
    agent_defaults = None
    if config.agent_defaults:
        agent_defaults = AgentOverride(
            greeting=config.agent_defaults.greeting,
            return_greeting=config.agent_defaults.return_greeting,
            description=config.agent_defaults.description,
            template_vars=config.agent_defaults.template_vars,
            voice_name=config.agent_defaults.voice_name,
            voice_rate=config.agent_defaults.voice_rate,
        )

    # Build handoff configs
    handoffs: list[HandoffConfig] = []
    for h in config.handoffs:
        handoffs.append(
            HandoffConfig(
                from_agent=h.from_agent,
                to_agent=h.to_agent,
                tool=h.tool,
                type=h.type,
                share_context=h.share_context,
                handoff_condition=h.handoff_condition,
            )
        )

    # Create the scenario
    scenario = ScenarioConfig(
        name=config.name,
        description=config.description,
        icon=config.icon,
        agents=config.agents,
        agent_defaults=agent_defaults,
        global_template_vars=config.global_template_vars,
        tools=config.tools,
        start_agent=config.start_agent,
        handoff_type=config.handoff_type,
        handoffs=handoffs,
    )

    # Store in session (in-memory cache + Redis persistence)
    # Use async version to ensure persistence completes before returning
    await set_session_scenario_async(session_id, scenario)

    logger.info(
        "Dynamic scenario created | session=%s name=%s agents=%d handoffs=%d",
        session_id,
        config.name,
        len(config.agents),
        len(config.handoffs),
    )

    return SessionScenarioResponse(
        session_id=session_id,
        scenario_name=config.name,
        status="created",
        config={
            "name": config.name,
            "description": config.description,
            "icon": config.icon,
            "agents": config.agents,
            "start_agent": config.start_agent,
            "handoff_type": config.handoff_type,
            "handoffs": [
                {
                    "from_agent": h.from_agent,
                    "to_agent": h.to_agent,
                    "tool": h.tool,
                    "type": h.type,
                    "share_context": h.share_context,
                    "handoff_condition": h.handoff_condition,
                }
                for h in handoffs
            ],
            "global_template_vars": config.global_template_vars,
        },
        created_at=time.time(),
    )


@router.get(
    "/session/{session_id}",
    response_model=SessionScenarioResponse,
    summary="Get Session Scenario",
    description="Get the current dynamic scenario configuration for a session.",
    tags=["Scenario Builder"],
)
async def get_session_scenario_config(
    session_id: str,
    request: Request,
) -> SessionScenarioResponse:
    """Get the dynamic scenario for a session."""
    scenario = get_session_scenario(session_id)

    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"No dynamic scenario found for session '{session_id}'",
        )

    return SessionScenarioResponse(
        session_id=session_id,
        scenario_name=scenario.name,
        status="active",
        config={
            "name": scenario.name,
            "description": scenario.description,
            "icon": scenario.icon,
            "agents": scenario.agents,
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
                }
                for h in scenario.handoffs
            ],
            "global_template_vars": scenario.global_template_vars,
            "agent_defaults": (
                {
                    "greeting": scenario.agent_defaults.greeting,
                    "return_greeting": scenario.agent_defaults.return_greeting,
                    "description": scenario.agent_defaults.description,
                    "template_vars": scenario.agent_defaults.template_vars,
                    "voice_name": scenario.agent_defaults.voice_name,
                    "voice_rate": scenario.agent_defaults.voice_rate,
                }
                if scenario.agent_defaults
                else None
            ),
        },
    )


@router.put(
    "/session/{session_id}",
    response_model=SessionScenarioResponse,
    summary="Update Session Scenario",
    description="Update the dynamic scenario configuration for a session.",
    tags=["Scenario Builder"],
)
async def update_session_scenario(
    session_id: str,
    config: DynamicScenarioConfig,
    request: Request,
) -> SessionScenarioResponse:
    """
    Update the dynamic scenario for a session.

    Creates a new scenario if one doesn't exist.
    """
    # Validate agents exist (include both template agents and session-scoped custom agents)
    agents_registry = discover_agents()
    session_agents = list_session_agents_by_session(session_id)
    all_valid_agents = set(agents_registry.keys()) | set(session_agents.keys())
    if config.agents:
        invalid_agents = [a for a in config.agents if a not in all_valid_agents]
        if invalid_agents:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid agents: {invalid_agents}. Available: {list(all_valid_agents)}",
            )

    # Validate start_agent
    if config.start_agent:
        if config.agents and config.start_agent not in config.agents:
            raise HTTPException(
                status_code=400,
                detail=f"start_agent '{config.start_agent}' must be in agents list",
            )
        if not config.agents and config.start_agent not in all_valid_agents:
            raise HTTPException(
                status_code=400,
                detail=f"start_agent '{config.start_agent}' not found in registry or session agents",
            )

    existing = get_session_scenario(session_id)
    created_at = time.time()

    # Build agent_defaults
    agent_defaults = None
    if config.agent_defaults:
        agent_defaults = AgentOverride(
            greeting=config.agent_defaults.greeting,
            return_greeting=config.agent_defaults.return_greeting,
            description=config.agent_defaults.description,
            template_vars=config.agent_defaults.template_vars,
            voice_name=config.agent_defaults.voice_name,
            voice_rate=config.agent_defaults.voice_rate,
        )

    # Build handoff configs
    handoffs: list[HandoffConfig] = []
    for h in config.handoffs:
        handoffs.append(
            HandoffConfig(
                from_agent=h.from_agent,
                to_agent=h.to_agent,
                tool=h.tool,
                type=h.type,
                share_context=h.share_context,
                handoff_condition=h.handoff_condition,
            )
        )

    # Create the updated scenario
    scenario = ScenarioConfig(
        name=config.name,
        description=config.description,
        icon=config.icon,
        agents=config.agents,
        agent_defaults=agent_defaults,
        global_template_vars=config.global_template_vars,
        tools=config.tools,
        start_agent=config.start_agent,
        handoff_type=config.handoff_type,
        handoffs=handoffs,
    )

    # Store in session (async to ensure Redis persistence)
    await set_session_scenario_async(session_id, scenario)

    logger.info(
        "Dynamic scenario updated | session=%s name=%s agents=%d handoffs=%d",
        session_id,
        config.name,
        len(config.agents),
        len(config.handoffs),
    )

    return SessionScenarioResponse(
        session_id=session_id,
        scenario_name=config.name,
        status="updated" if existing else "created",
        config={
            "name": config.name,
            "description": config.description,
            "icon": config.icon,
            "agents": config.agents,
            "start_agent": config.start_agent,
            "handoff_type": config.handoff_type,
            "handoffs": [
                {
                    "from_agent": h.from_agent,
                    "to_agent": h.to_agent,
                    "tool": h.tool,
                    "type": h.type,
                    "share_context": h.share_context,
                    "handoff_condition": h.handoff_condition,
                }
                for h in handoffs
            ],
            "global_template_vars": config.global_template_vars,
        },
        created_at=created_at,
        modified_at=time.time(),
    )


@router.delete(
    "/session/{session_id}",
    summary="Reset Session Scenario",
    description="Remove the dynamic scenario for a session, reverting to default behavior.",
    tags=["Scenario Builder"],
)
async def reset_session_scenario(
    session_id: str,
    request: Request,
) -> dict[str, Any]:
    """Remove the dynamic scenario for a session."""
    removed = remove_session_scenario(session_id)

    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"No dynamic scenario found for session '{session_id}'",
        )

    logger.info("Dynamic scenario removed | session=%s", session_id)

    return {
        "status": "success",
        "message": f"Scenario removed for session '{session_id}'",
        "session_id": session_id,
    }


@router.post(
    "/session/{session_id}/active",
    summary="Set Active Scenario",
    description="Set the active scenario for a session by name.",
    tags=["Scenario Builder"],
)
async def set_active_scenario_endpoint(
    session_id: str,
    scenario_name: str,
    request: Request,
) -> dict[str, Any]:
    """Set the active scenario for a session."""
    from apps.artagent.backend.src.orchestration.session_scenarios import set_active_scenario
    
    success = set_active_scenario(session_id, scenario_name)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario '{scenario_name}' not found for session '{session_id}'",
        )
    
    logger.info("Active scenario set | session=%s scenario=%s", session_id, scenario_name)
    
    return {
        "status": "success",
        "message": f"Active scenario set to '{scenario_name}'",
        "session_id": session_id,
        "scenario_name": scenario_name,
    }


@router.post(
    "/session/{session_id}/apply-template",
    summary="Apply Industry Template",
    description="Load an industry template from disk and apply it as the session's active scenario.",
    tags=["Scenario Builder"],
)
async def apply_template_to_session(
    session_id: str,
    template_id: str,
    request: Request,
) -> dict[str, Any]:
    """
    Apply an industry template (e.g., 'banking', 'insurance') to a session.

    This loads the template from disk, creates a session scenario from it,
    and sets it as the active scenario. The orchestrator adapter will be
    updated with the new agents and handoff configuration.

    Args:
        session_id: The session to apply the template to
        template_id: The template directory name (e.g., 'banking', 'insurance')
    """
    # Load the template from disk
    scenario = load_scenario(template_id)
    
    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_id}' not found",
        )
    
    # Set the scenario for this session (async to ensure Redis persistence)
    await set_session_scenario_async(session_id, scenario)
    
    logger.info(
        "Industry template applied | session=%s template=%s start_agent=%s agents=%d",
        session_id,
        template_id,
        scenario.start_agent,
        len(scenario.agents),
    )
    
    return {
        "status": "success",
        "message": f"Applied template '{template_id}' to session",
        "session_id": session_id,
        "template_id": template_id,
        "scenario": {
            "name": scenario.name,
            "description": scenario.description,
            "icon": scenario.icon,
            "start_agent": scenario.start_agent,
            "agents": scenario.agents,
            "handoff_count": len(scenario.handoffs),
        },
    }


@router.get(
    "/session/{session_id}/scenarios",
    summary="List Session Scenarios",
    description="List all custom scenarios for a specific session.",
    tags=["Scenario Builder"],
)
async def list_scenarios_for_session(
    session_id: str,
    request: Request,
) -> dict[str, Any]:
    """List all custom scenarios for a specific session."""
    from apps.artagent.backend.src.orchestration.session_scenarios import get_active_scenario_name
    
    scenarios = list_session_scenarios_by_session(session_id)
    active_name = get_active_scenario_name(session_id)

    return {
        "status": "success",
        "session_id": session_id,
        "total": len(scenarios),
        "active_scenario": active_name,
        "scenarios": [
            {
                "name": scenario.name,
                "description": scenario.description,
                "icon": scenario.icon,
                "agents": scenario.agents,
                "start_agent": scenario.start_agent,
                "handoffs": [
                    {
                        "from_agent": h.from_agent,
                        "to_agent": h.to_agent,
                        "tool": h.tool,
                        "type": h.type,
                        "share_context": h.share_context,
                        "handoff_condition": h.handoff_condition,
                    }
                    for h in scenario.handoffs
                ],
                "handoff_type": scenario.handoff_type,
                "global_template_vars": scenario.global_template_vars,
                "is_active": scenario.name == active_name,
            }
            for scenario in scenarios.values()
        ],
    }


@router.get(
    "/sessions",
    summary="List All Session Scenarios",
    description="List all sessions with dynamic scenarios configured.",
    tags=["Scenario Builder"],
)
async def list_session_scenarios_endpoint() -> dict[str, Any]:
    """List all sessions with custom scenarios."""
    scenarios = list_session_scenarios()

    return {
        "status": "success",
        "total": len(scenarios),
        "sessions": [
            {
                "key": key,
                "session_id": key.split(":")[0] if ":" in key else key,
                "scenario_name": scenario.name,
                "agents": scenario.agents,
                "start_agent": scenario.start_agent,
                "handoff_count": len(scenario.handoffs),
            }
            for key, scenario in scenarios.items()
        ],
    }


@router.post(
    "/reload-scenarios",
    summary="Reload Scenario Templates",
    description="Re-discover and reload all scenario templates from disk.",
    tags=["Scenario Builder"],
)
async def reload_scenario_templates(request: Request) -> dict[str, Any]:
    """
    Reload all scenario templates from disk.

    This clears the scenario cache and re-discovers scenarios
    from the scenariostore directory.
    """
    from apps.artagent.backend.registries.scenariostore.loader import (
        _SCENARIOS,
        _discover_scenarios,
    )

    # Clear the cache
    _SCENARIOS.clear()

    # Re-discover scenarios
    _discover_scenarios()

    scenario_names = list_scenarios()

    logger.info("Scenario templates reloaded | count=%d", len(scenario_names))

    return {
        "status": "success",
        "message": f"Reloaded {len(scenario_names)} scenario templates",
        "scenarios": scenario_names,
    }
