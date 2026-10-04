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
    POST /api/v1/scenario-builder/session/{session_id}/start-agent - Set the session start agent
    GET  /api/v1/scenario-builder/sessions      - List all sessions with custom scenarios
"""

from __future__ import annotations

import copy
import re
import time
from typing import Any

from apps.artagent.backend.api.v1.schemas.scenario_builder import (
    AgentOverrideSchema as AgentOverrideSchema,
)
from apps.artagent.backend.api.v1.schemas.scenario_builder import (
    DynamicScenarioConfig,
    SessionScenarioResponse,
)
from apps.artagent.backend.api.v1.schemas.scenario_builder import (
    GenericHandoffConfigSchema as GenericHandoffConfigSchema,
)
from apps.artagent.backend.api.v1.schemas.scenario_builder import (
    HandoffConfigSchema as HandoffConfigSchema,
)
from apps.artagent.backend.registries.agentstore.loader import discover_agents
from apps.artagent.backend.registries.definitions import (
    decode_definition,
    definition_payload,
)
from apps.artagent.backend.registries.definitions import (
    definition_payload as _agent_defaults_to_dict,
)
from apps.artagent.backend.registries.definitions import (
    definition_payload as _handoff_to_dict,
)
from apps.artagent.backend.registries.definitions import (
    definition_payload as _scenario_to_config_payload,
)
from apps.artagent.backend.registries.scenariostore.loader import (
    AgentOverride,
    GenericHandoffConfig,
    HandoffConfig,
    ScenarioConfig,
    list_scenarios,
    load_scenario,
)
from apps.artagent.backend.registries.toolstore.registry import get_tool_definition
from apps.artagent.backend.src.orchestration.naming import (
    agent_key,
)
from apps.artagent.backend.src.orchestration.naming import (
    normalize_agent_name as _normalize_agent_name,
)
from apps.artagent.backend.src.orchestration.naming import (
    normalize_agent_names as _normalize_agent_names,
)
from apps.artagent.backend.src.orchestration.naming import (
    find_agent_by_name,
)
from apps.artagent.backend.src.orchestration.naming import (
    normalize_scenario_name as _normalize_scenario_name,
)
from apps.artagent.backend.src.orchestration.session_agents import (
    get_session_agent,
    list_session_agents,
    list_session_agents_by_session,
)
from apps.artagent.backend.src.orchestration.session_scenarios import (
    get_session_scenario,
    list_session_scenarios,
    list_session_scenarios_by_session,
    remove_session_scenario_async,
    set_session_scenario_async,
)
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from utils.ml_logging import get_logger

logger = get_logger("v1.scenario_builder")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


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
    generic_handoff: dict[str, Any] = Field(default_factory=dict)
    agent_defaults: dict[str, Any] | None = None


class ToolInfo(BaseModel):
    """Tool information with name and description."""

    name: str
    description: str = ""


class AgentInfo(BaseModel):
    """Agent information for scenario configuration."""

    name: str
    description: str
    original_name: str | None = (
        None  # Original unmodified agent name for matching (before any display modifications)
    )
    greeting: str | None = None
    return_greeting: str | None = None
    tools: list[str] = []  # Keep for backward compatibility
    tool_details: list[ToolInfo] = []  # Full tool info with descriptions
    prompt_preview: str | None = None  # Truncated prompt for UI context
    prompt_full: str | None = None  # Full prompt for UI detail views
    prompt_vars: list[str] = []  # Jinja vars referenced in prompts
    handoff_context_vars: list[str] = []  # Jinja vars referenced in prompts (handoff_context.*)
    is_entry_point: bool = False
    is_session_agent: bool = False  # True if this is a dynamically created session agent
    session_id: str | None = None  # Session ID if this is a session agent
    # Model and voice configuration for UI display
    model: dict[str, Any] | None = None  # Primary model config
    cascade_model: dict[str, Any] | None = None  # Cascade mode model config
    voicelive_model: dict[str, Any] | None = None  # VoiceLive mode model config
    voice: dict[str, Any] | None = None  # Voice/TTS config


_JINJA_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)(?:\s*\|[^}]*)?\s*\}\}")
_GET_VAR_RE = re.compile(r"([a-zA-Z0-9_.]+)\.get\(['\"]([a-zA-Z0-9_.]+)['\"]\)")


def extract_prompt_vars(prompt_template: str | None) -> list[str]:
    """Extract variable names from a Jinja prompt template."""
    if not prompt_template:
        return []

    matches = {match.group(1).strip() for match in _JINJA_VAR_RE.finditer(prompt_template)}
    for prefix, key in _GET_VAR_RE.findall(prompt_template):
        if prefix and key:
            matches.add(f"{prefix}.{key}")
    cleaned = {m for m in matches if m and not m.endswith(".get")}
    return sorted(cleaned)


def build_prompt_preview(prompt_template: str | None, max_chars: int = 500) -> str | None:
    """Build a truncated prompt preview for UI display."""
    if not prompt_template:
        return None

    preview = prompt_template.strip()
    if len(preview) <= max_chars:
        return preview
    return preview[:max_chars].rstrip() + "..."


def extract_handoff_context_vars(prompt_template: str | None) -> list[str]:
    """Extract handoff_context.* variable names from a Jinja prompt template."""
    return [
        var for var in extract_prompt_vars(prompt_template) if var.startswith("handoff_context.")
    ]


def extract_model_config(agent: Any) -> dict[str, Any] | None:
    """Extract model configuration as a dict for API response."""
    model = getattr(agent, "model", None)
    if model is None:
        return None
    if hasattr(model, "to_dict"):
        return model.to_dict()
    if hasattr(model, "__dict__"):
        return {
            "deployment_id": getattr(model, "deployment_id", None),
            "model_name": getattr(model, "model_name", None),
            "endpoint": getattr(model, "endpoint", None),
        }
    return None


def extract_mode_model_config(agent: Any, mode: str) -> dict[str, Any] | None:
    """Extract cascade_model or voicelive_model config as a dict for API response."""
    model = getattr(agent, mode, None)
    if model is None:
        return None
    if hasattr(model, "to_dict"):
        return model.to_dict()
    if hasattr(model, "__dict__"):
        return {
            "deployment_id": getattr(model, "deployment_id", None),
            "model_name": getattr(model, "model_name", None),
            "endpoint": getattr(model, "endpoint", None),
        }
    return None


def extract_voice_config(agent: Any) -> dict[str, Any] | None:
    """Extract voice configuration as a dict for API response."""
    voice = getattr(agent, "voice", None)
    if voice is None:
        return None
    if hasattr(voice, "to_dict"):
        return voice.to_dict()
    if hasattr(voice, "__dict__"):
        return {
            "voice_name": getattr(voice, "voice_name", None),
            "display_name": getattr(voice, "display_name", None)
            or getattr(voice, "voice_name", None),
            "provider": getattr(voice, "provider", None),
            "language": getattr(voice, "language", None),
        }
    return None


def _scenario_response_config(scenario: ScenarioConfig) -> dict[str, Any]:
    """Return the complete editable configuration shared by all Builder clients."""
    return definition_payload(scenario)


def _generic_handoff_to_dict(config: GenericHandoffConfig | None) -> dict[str, Any]:
    """Serialize generic handoff settings for API responses and Redis payloads."""
    return definition_payload(config or GenericHandoffConfig())


def _build_agent_defaults(config: DynamicScenarioConfig) -> AgentOverride | None:
    """Build AgentOverride from the request schema."""
    if not config.agent_defaults:
        return None
    return AgentOverride.from_dict(config.agent_defaults.model_dump())


def _build_generic_handoff(
    config: DynamicScenarioConfig,
    existing: ScenarioConfig | None = None,
) -> GenericHandoffConfig:
    """Build GenericHandoffConfig from the request schema."""
    if not config.generic_handoff:
        if existing is not None:
            return existing.generic_handoff
        return GenericHandoffConfig(
            enabled=True,
            default_type=config.handoff_type,
            share_context=True,
            require_client_id=False,
        )
    data = config.generic_handoff.model_dump()
    data["allowed_targets"] = _normalize_agent_names(data["allowed_targets"])
    return GenericHandoffConfig.from_dict(data)


def _build_handoffs(config: DynamicScenarioConfig) -> list[HandoffConfig]:
    """Build normalized handoff route dataclasses from the request schema."""
    handoffs: list[HandoffConfig] = []
    for h in config.handoffs:
        normalized_from = _normalize_agent_name(h.from_agent)
        normalized_to = _normalize_agent_name(h.to_agent)
        handoffs.append(
            HandoffConfig.from_dict(
                {
                    **h.model_dump(),
                    "from_agent": normalized_from or "",
                    "to_agent": normalized_to or "",
                }
            )
        )
    return handoffs


def _validate_scenario_references(
    *,
    agents: list[str],
    start_agent: str | None,
    handoffs: list[HandoffConfig],
    generic_handoff: GenericHandoffConfig,
    all_valid_keys: set[str],
) -> None:
    """Validate scenario agent references without changing handoff policy."""
    scenario_keys = {agent.lower() for agent in agents}
    allowed_scope = scenario_keys or all_valid_keys

    def _invalid(names: list[str]) -> list[str]:
        return [
            name
            for name in names
            if name and name.lower() not in allowed_scope and name.lower() not in all_valid_keys
        ]

    if start_agent:
        if agents and start_agent.lower() not in scenario_keys:
            raise HTTPException(
                status_code=400,
                detail=f"start_agent '{start_agent}' must be in agents list",
            )
        if start_agent.lower() not in all_valid_keys:
            raise HTTPException(
                status_code=400,
                detail=f"start_agent '{start_agent}' not found in registry or session agents",
            )

    route_refs = [name for handoff in handoffs for name in (handoff.from_agent, handoff.to_agent)]
    invalid_route_refs = _invalid(route_refs)
    if invalid_route_refs:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid handoff agent references: {invalid_route_refs}",
        )

    invalid_targets = _invalid(generic_handoff.allowed_targets)
    if invalid_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid generic_handoff allowed_targets: {invalid_targets}",
        )


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
                    handoffs=[_handoff_to_dict(h) for h in scenario.handoffs],
                    global_template_vars=scenario.global_template_vars,
                    generic_handoff=_generic_handoff_to_dict(scenario.generic_handoff),
                    agent_defaults=_agent_defaults_to_dict(scenario.agent_defaults),
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

    config = _scenario_response_config(scenario)
    return {
        "status": "success",
        "config": config,
        "template": {"id": template_id, **config},
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
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
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
        prompt_template = getattr(agent, "prompt_template", None)
        prompt_vars = extract_prompt_vars(prompt_template)
        handoff_context_vars = [var for var in prompt_vars if var.startswith("handoff_context.")]
        prompt_preview = build_prompt_preview(prompt_template)
        agents_list.append(
            AgentInfo(
                name=name,
                description=agent.description or "",
                greeting=agent.greeting,
                return_greeting=getattr(agent, "return_greeting", None),
                tools=tool_names,
                tool_details=get_tool_details(tool_names),
                prompt_preview=prompt_preview,
                prompt_full=prompt_template,
                prompt_vars=prompt_vars,
                handoff_context_vars=handoff_context_vars,
                is_entry_point=name.lower() == "concierge" or "concierge" in name.lower(),
                is_session_agent=False,
                session_id=None,
                model=extract_model_config(agent),
                cascade_model=extract_mode_model_config(agent, "cascade_model"),
                voicelive_model=extract_mode_model_config(agent, "voicelive_model"),
                voice=extract_voice_config(agent),
            )
        )

    # Get dynamic session agents - use optimized function if filtering by session
    session_agents_added = 0
    session_agent_names = set()  # Track names of session agents for replacement logic

    if session_id:
        # Efficient: only get agents for this specific session
        session_agents_dict = list_session_agents_by_session(session_id)

        # First pass: collect session agent names
        session_agent_names = {agent_key(agent.name) for agent in session_agents_dict.values()}

        # Remove base agents that will be overridden by session agents
        # Session agents with same name REPLACE base agents, not duplicate them
        agents_list = [a for a in agents_list if agent_key(a.name) not in session_agent_names]

        for _agent_name, agent in session_agents_dict.items():
            # Session agent replaces base agent - use original name (no suffix)
            display_name = agent.name
            original_name = (
                agent.name
            )  # Store original name before any modification for frontend matching

            tool_names = agent.tool_names if hasattr(agent, "tool_names") else []
            prompt_template = getattr(agent, "prompt_template", None)
            prompt_vars = extract_prompt_vars(prompt_template)
            handoff_context_vars = [
                var for var in prompt_vars if var.startswith("handoff_context.")
            ]
            prompt_preview = build_prompt_preview(prompt_template)
            agents_list.append(
                AgentInfo(
                    name=display_name,
                    original_name=original_name,
                    description=agent.description or f"Dynamic agent for session {session_id[:8]}",
                    greeting=agent.greeting,
                    return_greeting=getattr(agent, "return_greeting", None),
                    tools=tool_names,
                    tool_details=get_tool_details(tool_names),
                    prompt_preview=prompt_preview,
                    prompt_full=prompt_template,
                    prompt_vars=prompt_vars,
                    handoff_context_vars=handoff_context_vars,
                    is_entry_point=False,
                    is_session_agent=True,
                    session_id=session_id,
                    model=extract_model_config(agent),
                    cascade_model=extract_mode_model_config(agent, "cascade_model"),
                    voicelive_model=extract_mode_model_config(agent, "voicelive_model"),
                    voice=extract_voice_config(agent),
                )
            )
            session_agents_added += 1
    else:
        # No filter: get all session agents across all sessions
        # In this global view, we show session overrides separately with session context
        # list_session_agents() returns {"{session_id}:{agent_name}": agent}
        all_session_agents = list_session_agents()
        for composite_key, agent in all_session_agents.items():
            # Parse the composite key to extract session_id
            parts = composite_key.split(":", 1)
            agent_session_id = parts[0] if len(parts) > 1 else composite_key

            # Check if this session agent overrides a base agent
            existing_names = {a.name for a in agents_list}
            agent_name = agent.name
            original_name = (
                agent.name
            )  # Store original name before any modification for frontend matching

            # In global view (no session filter), suffix with session ID to show it's an override
            if agent_name in existing_names:
                agent_name = f"{agent.name} [{agent_session_id[:8]}]"

            tool_names = agent.tool_names if hasattr(agent, "tool_names") else []
            prompt_template = getattr(agent, "prompt_template", None)
            prompt_vars = extract_prompt_vars(prompt_template)
            handoff_context_vars = [
                var for var in prompt_vars if var.startswith("handoff_context.")
            ]
            prompt_preview = build_prompt_preview(prompt_template)
            agents_list.append(
                AgentInfo(
                    name=agent_name,
                    original_name=original_name,
                    description=agent.description
                    or f"Dynamic agent for session {agent_session_id[:8]}",
                    greeting=agent.greeting,
                    return_greeting=getattr(agent, "return_greeting", None),
                    tools=tool_names,
                    tool_details=get_tool_details(tool_names),
                    prompt_preview=prompt_preview,
                    prompt_full=prompt_template,
                    prompt_vars=prompt_vars,
                    handoff_context_vars=handoff_context_vars,
                    is_entry_point=False,
                    is_session_agent=True,
                    session_id=agent_session_id,
                    model=extract_model_config(agent),
                    cascade_model=extract_mode_model_config(agent, "cascade_model"),
                    voicelive_model=extract_mode_model_config(agent, "voicelive_model"),
                    voice=extract_voice_config(agent),
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
    for _composite_key, agent in session_agents.items():
        if agent.name not in agent_names:
            agent_names.append(agent.name)

    return {
        "status": "success",
        "defaults": DynamicScenarioConfig(
            name="Custom Scenario",
            start_agent=agent_names[0] if agent_names else None,
            global_template_vars={
                "company_name": "ART Voice Agent",
                "industry": "general",
            },
        ).model_dump(),
        "available_agents": agent_names,
        "handoff_types": ["announced", "discrete"],
    }


def _build_session_scenario(
    config: DynamicScenarioConfig, session_id: str, *, existing: ScenarioConfig | None = None
) -> ScenarioConfig:
    """Apply builder aliases/reference checks over the canonical definition codec."""
    name = _normalize_scenario_name(config.name)
    if not name:
        raise HTTPException(status_code=400, detail="Scenario name is required")
    agents = _normalize_agent_names(config.agents)
    start_agent = _normalize_agent_name(config.start_agent)
    registry = discover_agents()
    valid_keys = {key.lower() for key in registry} | {
        key.lower() for key in list_session_agents_by_session(session_id)
    }
    invalid_agents = [agent for agent in agents if agent.lower() not in valid_keys]
    if invalid_agents:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agents: {invalid_agents}. Available: {list(registry)}",
        )
    generic_handoff = _build_generic_handoff(config, existing)
    handoffs = _build_handoffs(config)
    _validate_scenario_references(
        agents=agents,
        start_agent=start_agent,
        handoffs=handoffs,
        generic_handoff=generic_handoff,
        all_valid_keys=valid_keys,
    )
    return decode_definition(
        ScenarioConfig,
        {
            **config.model_dump(),
            "name": name,
            "agents": agents,
            "start_agent": start_agent,
            "agent_defaults": definition_payload(_build_agent_defaults(config)),
            "generic_handoff": definition_payload(generic_handoff),
            "handoffs": definition_payload(handoffs),
        },
    )


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
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    scenario = _build_session_scenario(config, session_id)
    normalized_scenario_name = scenario.name

    # Store in session (in-memory cache + Redis persistence)
    # Use async version to ensure persistence completes before returning.
    # If Redis write fails, _persist_scenario_to_redis_async raises so
    # clients get 500 instead of a misleading 200.
    try:
        await set_session_scenario_async(session_id, scenario)
    except Exception as e:
        logger.error(
            "Scenario created in memory but Redis persistence failed | session=%s name=%s error=%s",
            session_id,
            normalized_scenario_name,
            e,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Scenario '{normalized_scenario_name}' was configured in memory but could not be "
                "persisted to Redis. It may not survive across requests. Please retry."
            ),
        ) from e

    logger.info(
        "Dynamic scenario created | session=%s name=%s agents=%d handoffs=%d",
        session_id,
        normalized_scenario_name,
        len(config.agents),
        len(config.handoffs),
    )

    return SessionScenarioResponse(
        session_id=session_id,
        scenario_name=normalized_scenario_name,
        status="created",
        config=_scenario_to_config_payload(scenario),
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
    scenario_name: str | None = None,
) -> SessionScenarioResponse:
    """Read the active or explicitly named scenario without changing activation."""
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    if scenario_name is not None and not _normalize_scenario_name(scenario_name):
        raise HTTPException(status_code=422, detail="scenario_name must not be blank")
    scenario = get_session_scenario(session_id, scenario_name)

    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"No matching dynamic scenario found for session '{session_id}'",
        )

    return SessionScenarioResponse(
        session_id=session_id,
        scenario_name=scenario.name,
        status="loaded" if scenario_name else "active",
        config=_scenario_response_config(scenario),
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
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    existing = get_session_scenario(session_id, _normalize_scenario_name(config.name))
    scenario = _build_session_scenario(config, session_id, existing=existing)
    normalized_scenario_name = scenario.name
    created_at = time.time()

    # Store in session (async to ensure Redis persistence)
    try:
        await set_session_scenario_async(session_id, scenario)
    except Exception as e:
        logger.error(
            "Scenario updated in memory but Redis persistence failed | session=%s name=%s error=%s",
            session_id,
            normalized_scenario_name,
            e,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Scenario '{normalized_scenario_name}' was updated in memory but could not be "
                "persisted to Redis. It may not survive across requests. Please retry."
            ),
        ) from e

    logger.info(
        "Dynamic scenario updated | session=%s name=%s agents=%d handoffs=%d",
        session_id,
        normalized_scenario_name,
        len(config.agents),
        len(config.handoffs),
    )

    return SessionScenarioResponse(
        session_id=session_id,
        scenario_name=normalized_scenario_name,
        status="updated" if existing else "created",
        config=_scenario_response_config(scenario),
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
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    try:
        removed = await remove_session_scenario_async(session_id, raise_on_failure=True)
    except Exception as exc:
        logger.error(
            "Failed to persist session scenario reset | session=%s error=%s",
            session_id,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Dynamic scenario for session {session_id} was removed in memory but "
                "could not be cleared from Redis. Please retry."
            ),
        ) from exc

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
    """Set the active scenario for a session.

    Uses awaited Redis persistence so the caller can rely on the response
    being fully committed — no stale reads on subsequent GETs.
    """
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    from apps.artagent.backend.src.orchestration.session_scenarios import (
        _ensure_session_loaded,
        get_session_scenario,
        set_active_scenario_async,
    )

    normalized_scenario_name = _normalize_scenario_name(scenario_name)
    if not normalized_scenario_name:
        raise HTTPException(status_code=400, detail="scenario_name is required")

    activation_candidates = [normalized_scenario_name]
    if normalized_scenario_name.startswith("custom_"):
        activation_candidates.append(normalized_scenario_name[len("custom_") :])
    else:
        activation_candidates.append(f"custom_{normalized_scenario_name}")

    success = False
    for candidate_name in activation_candidates:
        success = await set_active_scenario_async(session_id, candidate_name)
        if success:
            normalized_scenario_name = candidate_name
            break

    if not success:
        # Retry once after forcing a fresh Redis reload — the scenario may
        # exist in Redis but not in this worker's memory cache.
        _ensure_session_loaded(session_id, force=True)
        for candidate_name in activation_candidates:
            success = await set_active_scenario_async(session_id, candidate_name)
            if success:
                normalized_scenario_name = candidate_name
                break

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario '{scenario_name}' not found for session '{session_id}'.",
        )

    # Get the scenario to return its start_agent
    scenario = get_session_scenario(session_id, normalized_scenario_name)

    logger.info(
        "Active scenario set | session=%s scenario=%s", session_id, normalized_scenario_name
    )

    return {
        "status": "success",
        "message": f"Active scenario set to '{normalized_scenario_name}'",
        "session_id": session_id,
        "scenario_name": normalized_scenario_name,
        "scenario": {
            "name": scenario.name if scenario else normalized_scenario_name,
            "start_agent": scenario.start_agent if scenario else None,
            "agents": scenario.agents if scenario else [],
        },
    }


@router.post(
    "/session/{session_id}/start-agent",
    response_model=SessionScenarioResponse,
    summary="Set Session Start Agent",
    description=(
        "Make an agent the start agent of the session's active scenario (or the named "
        "scenario/template). The agent joins the scenario if it lists explicit agents. "
        "Takes effect on the next connection."
    ),
    tags=["Scenario Builder"],
)
async def set_session_start_agent(
    session_id: str,
    agent_name: str,
    request: Request,
    scenario_name: str | None = None,
) -> SessionScenarioResponse:
    """Activate an agent for the session by making it the scenario start agent."""
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    name = _normalize_agent_name(agent_name)
    if not name:
        raise HTTPException(status_code=422, detail="agent_name must not be blank")
    requested = _normalize_scenario_name(scenario_name) if scenario_name is not None else None
    if scenario_name is not None and not requested:
        raise HTTPException(status_code=422, detail="scenario_name must not be blank")

    agent = get_session_agent(session_id, name) or find_agent_by_name(discover_agents(), name)[1]
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' was not found.")

    scenario = get_session_scenario(session_id, requested)
    if scenario is None and requested:
        scenario = load_scenario(requested.lower().replace(" ", "_"))
    if scenario is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active scenario found for session '{session_id}'. Select a scenario first.",
        )

    updated = copy.deepcopy(scenario)
    updated.start_agent = agent.name
    if updated.agents and not any(agent_key(item) == agent_key(agent.name) for item in updated.agents):
        updated.agents = [*updated.agents, agent.name]

    try:
        await set_session_scenario_async(session_id, updated)
    except Exception as exc:
        logger.error(
            "Start agent update could not be persisted | session=%s scenario=%s agent=%s error=%s",
            session_id,
            updated.name,
            agent.name,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to persist the start agent. Check Redis connectivity and retry.",
        ) from exc

    logger.info(
        "Session start agent set | session=%s scenario=%s agent=%s",
        session_id,
        updated.name,
        agent.name,
    )
    return SessionScenarioResponse(
        session_id=session_id,
        scenario_name=updated.name,
        status="updated",
        config=_scenario_response_config(updated),
        modified_at=time.time(),
    )


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
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
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
    description="List all scenarios for a session: both session-custom scenarios and built-in scenario templates.",
    tags=["Scenario Builder"],
)
async def list_scenarios_for_session(
    session_id: str,
    request: Request,
) -> dict[str, Any]:
    """
    List all scenarios available for a session.

    Returns both:
    - Session-custom scenarios (created via Scenario Builder)
    - Built-in scenario templates (from the scenarios directory)

    The active_scenario field indicates which scenario is currently selected.
    """
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    from apps.artagent.backend.src.orchestration.session_scenarios import get_active_scenario_name

    session_scenarios = list_session_scenarios_by_session(session_id)
    session_overrides = {scenario.name.lower(): scenario for scenario in session_scenarios.values()}
    active_name = get_active_scenario_name(session_id)

    # Normalize active_name for case-insensitive comparison
    active_name_lower = (active_name or "").lower()

    # Resolve active scenario's start_agent and icon for the frontend
    active_start_agent = None
    active_scenario_icon = None

    # Build built-in scenarios list FIRST so we know which names are builtins
    builtin_scenario_names = list_scenarios()
    builtin_name_set = {n.lower() for n in builtin_scenario_names}
    builtin_scenario_list = []
    for name in builtin_scenario_names:
        scenario = load_scenario(name)
        if scenario:
            builtin_name_set.add(scenario.name.lower())
            overridden = scenario.name.lower() in session_overrides
            scenario = session_overrides.get(scenario.name.lower(), scenario)
            is_active = scenario.name.lower() == active_name_lower
            entry = {
                **_scenario_response_config(scenario),
                "id": name,
                "is_active": is_active,
                "is_custom": False,
                "is_session_override": overridden,
            }
            builtin_scenario_list.append(entry)
            if is_active:
                active_start_agent = scenario.start_agent
                active_scenario_icon = scenario.icon

    # Build session scenarios list (only truly custom, exclude applied builtins)
    session_scenario_list = []
    for scenario in session_scenarios.values():
        # Skip scenarios that originated from applying a builtin template.
        # They're already represented in the builtins list above.
        if scenario.name.lower() in builtin_name_set:
            continue
        is_active = scenario.name.lower() == active_name_lower
        entry = {
            **_scenario_response_config(scenario),
            "is_active": is_active,
            "is_custom": True,
        }
        session_scenario_list.append(entry)
        if is_active:
            # Custom scenario takes precedence for active_start_agent
            active_start_agent = scenario.start_agent
            active_scenario_icon = scenario.icon

    return {
        "status": "success",
        "session_id": session_id,
        "total": len(session_scenario_list) + len(builtin_scenario_list),
        "active_scenario": active_name,
        "active_start_agent": active_start_agent,
        "active_scenario_icon": active_scenario_icon,
        # Combine all scenarios - builtin first as templates, then custom
        "scenarios": builtin_scenario_list + session_scenario_list,
        # Keep separate arrays for backwards compatibility
        "custom_scenarios": session_scenario_list,
        "builtin_scenarios": builtin_scenario_list,
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
                "generic_handoff": _generic_handoff_to_dict(scenario.generic_handoff),
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
