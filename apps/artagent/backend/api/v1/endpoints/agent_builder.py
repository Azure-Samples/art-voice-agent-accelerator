"""
Agent Builder Endpoints
=======================

REST endpoints for dynamically creating and managing agents at runtime.
Supports session-scoped agent configurations that can be modified through
the frontend without restarting the backend.

Endpoints:
    GET  /api/v1/agent-builder/tools      - List available tools
    GET  /api/v1/agent-builder/voices     - List available voices
    GET  /api/v1/agent-builder/defaults   - Get default agent configuration
    POST /api/v1/agent-builder/create     - Create dynamic agent for session
    GET  /api/v1/agent-builder/session/{session_id} - Get session agent config
    PUT  /api/v1/agent-builder/session/{session_id} - Update session agent config
    DELETE /api/v1/agent-builder/session/{session_id} - Reset to default agent
"""

from __future__ import annotations

import time
from typing import Any

import yaml
from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    SpeechConfig,
    UnifiedAgent,
    VoiceConfig,
)
from apps.artagent.backend.registries.agentstore.loader import (
    AGENTS_DIR,
    load_defaults,
    load_prompt,
)
from apps.artagent.backend.registries.toolstore.registry import (
    _TOOL_DEFINITIONS,
    initialize_tools,
)
from apps.artagent.backend.src.orchestration.session_agents import (
    get_session_agent,
    list_session_agents,
    remove_session_agent,
    set_session_agent,
)
from config import DEFAULT_TTS_VOICE
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from utils.ml_logging import get_logger

logger = get_logger("v1.agent_builder")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class ToolInfo(BaseModel):
    """Tool information for frontend display."""

    name: str
    description: str
    is_handoff: bool = False
    tags: list[str] = []
    parameters: dict[str, Any] | None = None


class VoiceInfo(BaseModel):
    """Voice information for frontend selection."""

    name: str
    display_name: str
    category: str  # turbo, standard, hd
    language: str = "en-US"


class ModelConfigSchema(BaseModel):
    """Model configuration schema."""

    deployment_id: str = "gpt-4o"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1, le=16384)


class VoiceConfigSchema(BaseModel):
    """Voice configuration schema."""

    name: str = "en-US-AvaMultilingualNeural"
    type: str = "azure-standard"
    style: str = "chat"
    rate: str = "+0%"
    pitch: str = Field(default="+0%", description="Voice pitch: -50% to +50%")


class SpeechConfigSchema(BaseModel):
    """Speech recognition (STT) configuration schema."""

    vad_silence_timeout_ms: int = Field(
        default=800,
        ge=100,
        le=5000,
        description="Silence duration (ms) before finalizing recognition",
    )
    use_semantic_segmentation: bool = Field(
        default=False, description="Enable semantic sentence boundary detection"
    )
    candidate_languages: list[str] = Field(
        default_factory=lambda: ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT"],
        description="Languages for automatic detection",
    )
    enable_diarization: bool = Field(default=False, description="Enable speaker diarization")
    speaker_count_hint: int = Field(
        default=2, ge=1, le=10, description="Hint for number of speakers"
    )


class SessionConfigSchema(BaseModel):
    """VoiceLive session configuration schema."""

    modalities: list[str] = Field(
        default_factory=lambda: ["TEXT", "AUDIO"],
        description="Session modalities (TEXT, AUDIO)",
    )
    input_audio_format: str = Field(default="PCM16", description="Input audio format")
    output_audio_format: str = Field(default="PCM16", description="Output audio format")
    turn_detection_type: str = Field(
        default="azure_semantic_vad",
        description="Turn detection type (azure_semantic_vad, server_vad, none)",
    )
    turn_detection_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="VAD threshold"
    )
    silence_duration_ms: int = Field(
        default=700, ge=100, le=3000, description="Silence duration before turn ends"
    )
    prefix_padding_ms: int = Field(
        default=240, ge=0, le=1000, description="Audio prefix padding"
    )
    tool_choice: str = Field(default="auto", description="Tool choice mode (auto, none, required)")


class DynamicAgentConfig(BaseModel):
    """Configuration for creating a dynamic agent."""

    name: str = Field(..., min_length=1, max_length=64, description="Agent display name")
    description: str = Field(default="", max_length=512, description="Agent description")
    greeting: str = Field(default="", max_length=1024, description="Initial greeting message")
    return_greeting: str = Field(
        default="", max_length=1024, description="Return greeting when caller comes back"
    )
    handoff_trigger: str = Field(
        default="", max_length=128, description="Tool name that routes to this agent (e.g., handoff_my_agent)"
    )
    prompt: str = Field(..., min_length=10, description="System prompt for the agent")
    tools: list[str] = Field(default_factory=list, description="List of tool names to enable")
    cascade_model: ModelConfigSchema | None = Field(
        default=None, description="Model config for cascade mode (STT→LLM→TTS)"
    )
    voicelive_model: ModelConfigSchema | None = Field(
        default=None, description="Model config for voicelive mode (realtime API)"
    )
    model: ModelConfigSchema | None = Field(
        default=None, description="Legacy: fallback model config (use cascade_model/voicelive_model instead)"
    )
    voice: VoiceConfigSchema | None = None
    speech: SpeechConfigSchema | None = None
    session: SessionConfigSchema | None = Field(
        default=None, description="VoiceLive session settings (VAD, modalities, etc.)"
    )
    template_vars: dict[str, Any] | None = None


class SessionAgentResponse(BaseModel):
    """Response for session agent operations."""

    session_id: str
    agent_name: str
    status: str
    config: dict[str, Any]
    created_at: float | None = None
    modified_at: float | None = None


class AgentTemplateInfo(BaseModel):
    """Agent template information for frontend display."""

    id: str
    name: str
    description: str
    greeting: str
    prompt_preview: str
    prompt_full: str
    tools: list[str]
    voice: dict[str, Any] | None = None
    model: dict[str, Any] | None = None
    is_entry_point: bool = False
    is_session_agent: bool = False
    session_id: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# AVAILABLE VOICES CATALOG
# ═══════════════════════════════════════════════════════════════════════════════

AVAILABLE_VOICES = [
    # Turbo voices - lowest latency
    VoiceInfo(
        name="en-US-AlloyTurboMultilingualNeural", display_name="Alloy (Turbo)", category="turbo"
    ),
    VoiceInfo(
        name="en-US-EchoTurboMultilingualNeural", display_name="Echo (Turbo)", category="turbo"
    ),
    VoiceInfo(
        name="en-US-FableTurboMultilingualNeural", display_name="Fable (Turbo)", category="turbo"
    ),
    VoiceInfo(
        name="en-US-OnyxTurboMultilingualNeural", display_name="Onyx (Turbo)", category="turbo"
    ),
    VoiceInfo(
        name="en-US-NovaTurboMultilingualNeural", display_name="Nova (Turbo)", category="turbo"
    ),
    VoiceInfo(
        name="en-US-ShimmerTurboMultilingualNeural",
        display_name="Shimmer (Turbo)",
        category="turbo",
    ),
    # Standard voices
    VoiceInfo(name="en-US-AvaMultilingualNeural", display_name="Ava", category="standard"),
    VoiceInfo(name="en-US-AndrewMultilingualNeural", display_name="Andrew", category="standard"),
    VoiceInfo(name="en-US-EmmaMultilingualNeural", display_name="Emma", category="standard"),
    VoiceInfo(name="en-US-BrianMultilingualNeural", display_name="Brian", category="standard"),
    # HD voices - highest quality
    VoiceInfo(name="en-US-Ava:DragonHDLatestNeural", display_name="Ava HD", category="hd"),
    VoiceInfo(name="en-US-Andrew:DragonHDLatestNeural", display_name="Andrew HD", category="hd"),
    VoiceInfo(name="en-US-Brian:DragonHDLatestNeural", display_name="Brian HD", category="hd"),
    VoiceInfo(name="en-US-Emma:DragonHDLatestNeural", display_name="Emma HD", category="hd"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION AGENT STORAGE
# ═══════════════════════════════════════════════════════════════════════════════
# Session agent storage is now centralized in:
# apps/artagent/backend/src/orchestration/session_agents.py
# Import get_session_agent, set_session_agent, remove_session_agent from there.


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/tools",
    response_model=dict[str, Any],
    summary="List Available Tools",
    description="Get list of all registered tools that can be assigned to dynamic agents.",
    tags=["Agent Builder"],
)
async def list_available_tools(
    category: str | None = None,
    include_handoffs: bool = True,
) -> dict[str, Any]:
    """
    List all available tools for agent configuration.

    Args:
        category: Filter by category (banking, auth, fraud, etc.)
        include_handoffs: Whether to include handoff tools
    """
    start = time.time()

    # Ensure tools are initialized
    initialize_tools()

    tools_list: list[ToolInfo] = []
    categories: dict[str, int] = {}

    for name, defn in _TOOL_DEFINITIONS.items():
        # Skip handoffs if not requested
        if defn.is_handoff and not include_handoffs:
            continue

        # Filter by category if specified
        if category and category not in defn.tags:
            continue

        # Extract parameter info from schema
        params = None
        if defn.schema and "parameters" in defn.schema:
            params = defn.schema["parameters"]

        tool_info = ToolInfo(
            name=name,
            description=defn.description or defn.schema.get("description", ""),
            is_handoff=defn.is_handoff,
            tags=list(defn.tags),
            parameters=params,
        )
        tools_list.append(tool_info)

        # Count categories
        for tag in defn.tags:
            categories[tag] = categories.get(tag, 0) + 1

    # Sort by name for consistent display
    tools_list.sort(key=lambda t: (t.is_handoff, t.name))

    return {
        "status": "success",
        "total": len(tools_list),
        "tools": [t.model_dump() for t in tools_list],
        "categories": categories,
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


@router.get(
    "/voices",
    response_model=dict[str, Any],
    summary="List Available Voices",
    description="Get list of all available TTS voices for agent configuration.",
    tags=["Agent Builder"],
)
async def list_available_voices(
    category: str | None = None,
) -> dict[str, Any]:
    """
    List all available TTS voices.

    Args:
        category: Filter by category (turbo, standard, hd)
    """
    voices = AVAILABLE_VOICES

    if category:
        voices = [v for v in voices if v.category == category]

    # Group by category
    by_category: dict[str, list[dict[str, Any]]] = {}
    for voice in voices:
        if voice.category not in by_category:
            by_category[voice.category] = []
        by_category[voice.category].append(voice.model_dump())

    return {
        "status": "success",
        "total": len(voices),
        "voices": [v.model_dump() for v in voices],
        "by_category": by_category,
        "default_voice": DEFAULT_TTS_VOICE,
    }


@router.get(
    "/defaults",
    response_model=dict[str, Any],
    summary="Get Default Agent Configuration",
    description="Get the default configuration template for creating new agents.",
    tags=["Agent Builder"],
)
async def get_default_config() -> dict[str, Any]:
    """Get default agent configuration from _defaults.yaml."""
    defaults = load_defaults(AGENTS_DIR)

    return {
        "status": "success",
        "defaults": {
            "model": defaults.get(
                "model",
                {
                    "deployment_id": "gpt-4o",
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 4096,
                },
            ),
            "voice": defaults.get(
                "voice",
                {
                    "name": "en-US-AvaMultilingualNeural",
                    "type": "azure-standard",
                    "style": "chat",
                    "rate": "+0%",
                },
            ),
            "session": defaults.get("session", {}),
            "template_vars": defaults.get(
                "template_vars",
                {
                    "institution_name": "Contoso Financial",
                    "agent_name": "Assistant",
                },
            ),
        },
        "prompt_template": """You are {{ agent_name }}, a helpful assistant for {{ institution_name }}.

## Your Role
Assist customers with their inquiries in a friendly, professional manner.

## Guidelines
- Be concise and helpful
- Ask clarifying questions when needed
- Use the available tools when appropriate
""",
    }


@router.get(
    "/templates",
    response_model=dict[str, Any],
    summary="List Available Agent Templates",
    description="Get list of all existing agent configurations that can be used as templates.",
    tags=["Agent Builder"],
)
async def list_agent_templates() -> dict[str, Any]:
    """
    List all available agent templates from the agents directory.

    Returns agent configurations that can be used as starting points
    for creating new dynamic agents.
    """
    start = time.time()
    templates: list[AgentTemplateInfo] = []
    defaults = load_defaults(AGENTS_DIR)

    # Scan for agent directories
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        if agent_dir.name.startswith("_") or agent_dir.name.startswith("."):
            continue

        agent_file = agent_dir / "agent.yaml"
        if not agent_file.exists():
            continue

        try:
            with open(agent_file) as f:
                raw = yaml.safe_load(f) or {}

            # Extract name and description
            name = raw.get("name") or agent_dir.name.replace("_", " ").title()
            description = raw.get("description", "")
            greeting = raw.get("greeting", "")

            # Load prompt from file or inline
            prompt_full = ""
            if "prompts" in raw and raw["prompts"].get("path"):
                prompt_full = load_prompt(agent_dir, raw["prompts"]["path"])
            elif raw.get("prompt"):
                prompt_full = load_prompt(agent_dir, raw["prompt"])

            # Get tools list
            tools = raw.get("tools", [])

            # Get voice and model configs
            voice = raw.get("voice")
            model = raw.get("model")

            # Check if entry point
            handoff_config = raw.get("handoff", {})
            is_entry_point = handoff_config.get("is_entry_point", False)

            # Create preview (first 300 chars)
            prompt_preview = prompt_full[:300] + "..." if len(prompt_full) > 300 else prompt_full

            templates.append(
                AgentTemplateInfo(
                    id=agent_dir.name,
                    name=name,
                    description=(
                        description if isinstance(description, str) else str(description)[:200]
                    ),
                    greeting=greeting if isinstance(greeting, str) else str(greeting),
                    prompt_preview=prompt_preview,
                    prompt_full=prompt_full,
                    tools=tools,
                    voice=voice,
                    model=model,
                    is_entry_point=is_entry_point,
                )
            )

        except Exception as e:
            logger.warning("Failed to load agent template %s: %s", agent_dir.name, e)
            continue

    # Sort by name, with entry point first
    templates.sort(key=lambda t: (not t.is_entry_point, t.name))

    # Include session agents (custom-created agents)
    # list_session_agents() returns {"{session_id}:{agent_name}": agent}
    session_agents = list_session_agents()
    for composite_key, agent in session_agents.items():
        try:
            # Parse the composite key to extract session_id
            parts = composite_key.split(":", 1)
            session_id = parts[0] if len(parts) > 1 else composite_key
            
            prompt_full = agent.prompt_template or ""
            prompt_preview = prompt_full[:300] + "..." if len(prompt_full) > 300 else prompt_full
            
            templates.append(
                AgentTemplateInfo(
                    id=f"session:{composite_key}",
                    name=agent.name,
                    description=agent.description or "",
                    greeting=agent.greeting or "",
                    prompt_preview=prompt_preview,
                    prompt_full=prompt_full,
                    tools=agent.tool_names or [],
                    voice=agent.voice.to_dict() if agent.voice else None,
                    model=agent.model.to_dict() if agent.model else None,
                    is_entry_point=False,
                    is_session_agent=True,
                    session_id=session_id,
                )
            )
        except Exception as e:
            logger.warning("Failed to include session agent %s: %s", agent.name, e)
            continue

    return {
        "status": "success",
        "total": len(templates),
        "templates": [t.model_dump() for t in templates],
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


@router.get(
    "/templates/{template_id}",
    response_model=dict[str, Any],
    summary="Get Agent Template Details",
    description="Get full details of a specific agent template.",
    tags=["Agent Builder"],
)
async def get_agent_template(template_id: str) -> dict[str, Any]:
    """
    Get the full configuration of a specific agent template.

    Args:
        template_id: The agent directory name (e.g., 'concierge', 'fraud_agent')
    """
    agent_dir = AGENTS_DIR / template_id
    agent_file = agent_dir / "agent.yaml"

    if not agent_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Agent template '{template_id}' not found. Use GET /templates to see available templates.",
        )

    defaults = load_defaults(AGENTS_DIR)

    try:
        with open(agent_file) as f:
            raw = yaml.safe_load(f) or {}

        # Extract all fields
        name = raw.get("name") or template_id.replace("_", " ").title()
        description = raw.get("description", "")
        greeting = raw.get("greeting", "")
        return_greeting = raw.get("return_greeting", "")

        # Load full prompt
        prompt_full = ""
        if "prompts" in raw and raw["prompts"].get("path"):
            prompt_full = load_prompt(agent_dir, raw["prompts"]["path"])
        elif raw.get("prompt"):
            prompt_full = load_prompt(agent_dir, raw["prompt"])

        # Get tools, voice, model
        tools = raw.get("tools", [])
        voice = raw.get("voice") or defaults.get("voice", {})
        model = raw.get("model") or defaults.get("model", {})
        template_vars = raw.get("template_vars") or defaults.get("template_vars", {})

        return {
            "status": "success",
            "template": {
                "id": template_id,
                "name": name,
                "description": description if isinstance(description, str) else str(description),
                "greeting": greeting if isinstance(greeting, str) else str(greeting),
                "return_greeting": return_greeting,
                "prompt": prompt_full,
                "tools": tools,
                "voice": voice,
                "model": model,
                "template_vars": template_vars,
                "handoff": raw.get("handoff", {}),
            },
        }

    except Exception as e:
        logger.error("Failed to load agent template %s: %s", template_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load agent template: {str(e)}",
        )


@router.post(
    "/create",
    response_model=SessionAgentResponse,
    summary="Create Dynamic Agent",
    description="Create a new dynamic agent configuration for a session.",
    tags=["Agent Builder"],
)
async def create_dynamic_agent(
    config: DynamicAgentConfig,
    session_id: str,
    request: Request,
) -> SessionAgentResponse:
    """
    Create a dynamic agent for a specific session.

    This agent will be used instead of the default agent for this session.
    The configuration is stored in memory and can be modified at runtime.
    """
    start = time.time()

    # Validate tools exist
    initialize_tools()
    invalid_tools = [t for t in config.tools if t not in _TOOL_DEFINITIONS]
    if invalid_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tools: {', '.join(invalid_tools)}. Use GET /tools to see available tools.",
        )

    # Build model configs for each orchestration mode
    # Priority: explicit mode-specific config > legacy model config > defaults
    
    # Cascade model (for STT→LLM→TTS mode)
    if config.cascade_model:
        cascade_model = ModelConfig(
            deployment_id=config.cascade_model.deployment_id,
            temperature=config.cascade_model.temperature,
            top_p=config.cascade_model.top_p,
            max_tokens=config.cascade_model.max_tokens,
        )
    elif config.model:
        # Fallback: use legacy model, but swap realtime for gpt-4o
        base_id = config.model.deployment_id
        cascade_model = ModelConfig(
            deployment_id="gpt-4o" if "realtime" in base_id.lower() else base_id,
            temperature=config.model.temperature,
            top_p=config.model.top_p,
            max_tokens=config.model.max_tokens,
        )
    else:
        cascade_model = ModelConfig(
            deployment_id="gpt-4o",
            temperature=0.7,
            top_p=0.9,
            max_tokens=4096,
        )
    
    # VoiceLive model (for realtime API mode)
    if config.voicelive_model:
        voicelive_model = ModelConfig(
            deployment_id=config.voicelive_model.deployment_id,
            temperature=config.voicelive_model.temperature,
            top_p=config.voicelive_model.top_p,
            max_tokens=config.voicelive_model.max_tokens,
        )
    elif config.model:
        # Fallback: use legacy model, but ensure realtime for voicelive
        base_id = config.model.deployment_id
        voicelive_model = ModelConfig(
            deployment_id=base_id if "realtime" in base_id.lower() else "gpt-realtime",
            temperature=config.model.temperature,
            top_p=config.model.top_p,
            max_tokens=config.model.max_tokens,
        )
    else:
        voicelive_model = ModelConfig(
            deployment_id="gpt-realtime",
            temperature=0.7,
            top_p=0.9,
            max_tokens=4096,
        )
    
    # Default model uses cascade config
    model_config = cascade_model

    # Build voice config
    voice_config = VoiceConfig(
        name=config.voice.name if config.voice else "en-US-AvaMultilingualNeural",
        type=config.voice.type if config.voice else "azure-standard",
        style=config.voice.style if config.voice else "chat",
        rate=config.voice.rate if config.voice else "+0%",
        pitch=config.voice.pitch if config.voice else "+0%",
    )

    # Build speech config (STT / VAD settings)
    speech_config = SpeechConfig(
        vad_silence_timeout_ms=config.speech.vad_silence_timeout_ms if config.speech else 800,
        use_semantic_segmentation=(
            config.speech.use_semantic_segmentation if config.speech else False
        ),
        candidate_languages=config.speech.candidate_languages if config.speech else ["en-US"],
        enable_diarization=config.speech.enable_diarization if config.speech else False,
        speaker_count_hint=config.speech.speaker_count_hint if config.speech else 2,
    )

    # Determine handoff trigger (use explicit config or auto-generate)
    handoff_trigger = config.handoff_trigger.strip() if config.handoff_trigger else ""
    if not handoff_trigger:
        handoff_trigger = f"handoff_{config.name.lower().replace(' ', '_')}"

    # Build session config dict for VoiceLive (if provided)
    session_dict = {}
    if config.session:
        session_dict = {
            "modalities": config.session.modalities,
            "input_audio_format": config.session.input_audio_format,
            "output_audio_format": config.session.output_audio_format,
            "turn_detection": {
                "type": config.session.turn_detection_type,
                "threshold": config.session.turn_detection_threshold,
                "silence_duration_ms": config.session.silence_duration_ms,
                "prefix_padding_ms": config.session.prefix_padding_ms,
            },
            "tool_choice": config.session.tool_choice,
        }

    # Create the agent with mode-specific models
    agent = UnifiedAgent(
        name=config.name,
        description=config.description,
        greeting=config.greeting,
        return_greeting=config.return_greeting,
        handoff=HandoffConfig(trigger=handoff_trigger),
        model=model_config,
        cascade_model=cascade_model,
        voicelive_model=voicelive_model,
        voice=voice_config,
        speech=speech_config,
        session=session_dict,
        prompt_template=config.prompt,
        tool_names=config.tools,
        template_vars=config.template_vars or {},
        metadata={
            "source": "dynamic",
            "session_id": session_id,
            "created_at": time.time(),
        },
    )

    # Store in session
    set_session_agent(session_id, agent)

    logger.info(
        "Dynamic agent created | session=%s name=%s tools=%d",
        session_id,
        config.name,
        len(config.tools),
    )

    return SessionAgentResponse(
        session_id=session_id,
        agent_name=config.name,
        status="created",
        config={
            "name": config.name,
            "description": config.description,
            "greeting": config.greeting,
            "return_greeting": config.return_greeting,
            "handoff_trigger": handoff_trigger,
            "prompt_preview": (
                config.prompt[:200] + "..." if len(config.prompt) > 200 else config.prompt
            ),
            "tools": config.tools,
            "cascade_model": cascade_model.to_dict(),
            "voicelive_model": voicelive_model.to_dict(),
            "model": model_config.to_dict(),
            "voice": voice_config.to_dict(),
            "speech": speech_config.to_dict(),
            "session": session_dict,
        },
        created_at=time.time(),
    )


@router.get(
    "/session/{session_id}",
    response_model=SessionAgentResponse,
    summary="Get Session Agent",
    description="Get the current dynamic agent configuration for a session.",
    tags=["Agent Builder"],
)
async def get_session_agent_config(
    session_id: str,
    request: Request,
) -> SessionAgentResponse:
    """Get the dynamic agent for a session."""
    agent = get_session_agent(session_id)

    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"No dynamic agent configured for session {session_id}. Using default agent.",
        )

    return SessionAgentResponse(
        session_id=session_id,
        agent_name=agent.name,
        status="active",
        config={
            "name": agent.name,
            "description": agent.description,
            "greeting": agent.greeting,
            "return_greeting": agent.return_greeting,
            "handoff_trigger": agent.handoff.trigger if agent.handoff else "",
            "prompt_preview": (
                agent.prompt_template[:200] + "..."
                if len(agent.prompt_template) > 200
                else agent.prompt_template
            ),
            "prompt_full": agent.prompt_template,
            "tools": agent.tool_names,
            "model": agent.model.to_dict(),
            "cascade_model": agent.cascade_model.to_dict() if agent.cascade_model else agent.model.to_dict(),
            "voicelive_model": agent.voicelive_model.to_dict() if agent.voicelive_model else agent.model.to_dict(),
            "voice": agent.voice.to_dict(),
            "speech": agent.speech.to_dict() if agent.speech else {},
            "session": agent.session or {},
            "template_vars": agent.template_vars,
        },
        created_at=agent.metadata.get("created_at"),
        modified_at=agent.metadata.get("modified_at"),
    )


@router.put(
    "/session/{session_id}",
    response_model=SessionAgentResponse,
    summary="Update Session Agent",
    description="Update the dynamic agent configuration for a session.",
    tags=["Agent Builder"],
)
async def update_session_agent(
    session_id: str,
    config: DynamicAgentConfig,
    request: Request,
) -> SessionAgentResponse:
    """
    Update the dynamic agent for a session.

    Creates a new agent if one doesn't exist.
    """
    # Validate tools exist
    initialize_tools()
    invalid_tools = [t for t in config.tools if t not in _TOOL_DEFINITIONS]
    if invalid_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tools: {', '.join(invalid_tools)}",
        )

    existing = get_session_agent(session_id)
    created_at = existing.metadata.get("created_at") if existing else time.time()

    # Build model configs for each orchestration mode
    if config.cascade_model:
        cascade_model = ModelConfig(
            deployment_id=config.cascade_model.deployment_id,
            temperature=config.cascade_model.temperature,
            top_p=config.cascade_model.top_p,
            max_tokens=config.cascade_model.max_tokens,
        )
    elif config.model:
        base_id = config.model.deployment_id
        cascade_model = ModelConfig(
            deployment_id="gpt-4o" if "realtime" in base_id.lower() else base_id,
            temperature=config.model.temperature,
            top_p=config.model.top_p,
            max_tokens=config.model.max_tokens,
        )
    else:
        cascade_model = ModelConfig(
            deployment_id="gpt-4o",
            temperature=0.7,
            top_p=0.9,
            max_tokens=4096,
        )
    
    if config.voicelive_model:
        voicelive_model = ModelConfig(
            deployment_id=config.voicelive_model.deployment_id,
            temperature=config.voicelive_model.temperature,
            top_p=config.voicelive_model.top_p,
            max_tokens=config.voicelive_model.max_tokens,
        )
    elif config.model:
        base_id = config.model.deployment_id
        voicelive_model = ModelConfig(
            deployment_id=base_id if "realtime" in base_id.lower() else "gpt-realtime",
            temperature=config.model.temperature,
            top_p=config.model.top_p,
            max_tokens=config.model.max_tokens,
        )
    else:
        voicelive_model = ModelConfig(
            deployment_id="gpt-realtime",
            temperature=0.7,
            top_p=0.9,
            max_tokens=4096,
        )
    
    model_config = cascade_model  # Default fallback

    voice_config = VoiceConfig(
        name=config.voice.name if config.voice else "en-US-AvaMultilingualNeural",
        type=config.voice.type if config.voice else "azure-standard",
        style=config.voice.style if config.voice else "chat",
        rate=config.voice.rate if config.voice else "+0%",
        pitch=config.voice.pitch if config.voice else "+0%",
    )

    # Build speech config (STT / VAD settings)
    speech_config = SpeechConfig(
        vad_silence_timeout_ms=config.speech.vad_silence_timeout_ms if config.speech else 800,
        use_semantic_segmentation=(
            config.speech.use_semantic_segmentation if config.speech else False
        ),
        candidate_languages=config.speech.candidate_languages if config.speech else ["en-US"],
        enable_diarization=config.speech.enable_diarization if config.speech else False,
        speaker_count_hint=config.speech.speaker_count_hint if config.speech else 2,
    )

    # Determine handoff trigger (use explicit config or auto-generate)
    handoff_trigger = config.handoff_trigger.strip() if config.handoff_trigger else ""
    if not handoff_trigger:
        handoff_trigger = f"handoff_{config.name.lower().replace(' ', '_')}"

    # Build session config dict for VoiceLive (if provided)
    session_dict = {}
    if config.session:
        session_dict = {
            "modalities": config.session.modalities,
            "input_audio_format": config.session.input_audio_format,
            "output_audio_format": config.session.output_audio_format,
            "turn_detection": {
                "type": config.session.turn_detection_type,
                "threshold": config.session.turn_detection_threshold,
                "silence_duration_ms": config.session.silence_duration_ms,
                "prefix_padding_ms": config.session.prefix_padding_ms,
            },
            "tool_choice": config.session.tool_choice,
        }

    # Create updated agent with mode-specific models
    agent = UnifiedAgent(
        name=config.name,
        description=config.description,
        greeting=config.greeting,
        return_greeting=config.return_greeting,
        handoff=HandoffConfig(trigger=handoff_trigger),
        model=model_config,
        cascade_model=cascade_model,
        voicelive_model=voicelive_model,
        voice=voice_config,
        speech=speech_config,
        session=session_dict,
        prompt_template=config.prompt,
        tool_names=config.tools,
        template_vars=config.template_vars or {},
        metadata={
            "source": "dynamic",
            "session_id": session_id,
            "created_at": created_at,
            "modified_at": time.time(),
        },
    )

    set_session_agent(session_id, agent)

    logger.info(
        "Dynamic agent updated | session=%s name=%s",
        session_id,
        config.name,
    )

    return SessionAgentResponse(
        session_id=session_id,
        agent_name=config.name,
        status="updated",
        config={
            "name": config.name,
            "description": config.description,
            "greeting": config.greeting,
            "return_greeting": config.return_greeting,
            "handoff_trigger": handoff_trigger,
            "prompt_preview": config.prompt[:200] + "...",
            "tools": config.tools,
            "cascade_model": cascade_model.to_dict(),
            "voicelive_model": voicelive_model.to_dict(),
            "model": model_config.to_dict(),
            "voice": voice_config.to_dict(),
            "speech": speech_config.to_dict(),
            "session": session_dict,
        },
        created_at=created_at,
        modified_at=time.time(),
    )


@router.delete(
    "/session/{session_id}",
    summary="Reset Session Agent",
    description="Remove the dynamic agent for a session, reverting to default behavior.",
    tags=["Agent Builder"],
)
async def reset_session_agent(
    session_id: str,
    request: Request,
) -> dict[str, Any]:
    """Remove the dynamic agent for a session."""
    removed = remove_session_agent(session_id)

    if not removed:
        return {
            "status": "not_found",
            "message": f"No dynamic agent configured for session {session_id}",
            "session_id": session_id,
        }

    return {
        "status": "removed",
        "message": f"Dynamic agent removed for session {session_id}. Using default agent.",
        "session_id": session_id,
    }


@router.get(
    "/sessions",
    summary="List All Session Agents",
    description="List all sessions with dynamic agents configured.",
    tags=["Agent Builder"],
)
async def list_session_agents_endpoint() -> dict[str, Any]:
    """List all sessions with dynamic agents."""
    all_agents = list_session_agents()
    sessions = []
    for session_id, agent in all_agents.items():
        sessions.append(
            {
                "session_id": session_id,
                "agent_name": agent.name,
                "tools_count": len(agent.tool_names),
                "created_at": agent.metadata.get("created_at"),
                "modified_at": agent.metadata.get("modified_at"),
            }
        )

    return {
        "status": "success",
        "total": len(sessions),
        "sessions": sessions,
    }


@router.post(
    "/reload-agents",
    summary="Reload Agent Templates",
    description="Re-discover and reload all agent templates from disk into the running application.",
    tags=["Agent Builder"],
)
async def reload_agent_templates(request: Request) -> dict[str, Any]:
    """
    Reload agent templates from disk.

    This endpoint re-runs discover_agents() and updates app.state.unified_agents,
    making newly created or modified agents available without restarting the server.
    """
    from apps.artagent.backend.registries.agentstore.loader import (
        build_agent_summaries,
        build_handoff_map,
        discover_agents,
    )

    start = time.time()

    try:
        # Re-discover agents from disk
        unified_agents = discover_agents()

        # Rebuild handoff map and summaries
        handoff_map = build_handoff_map(unified_agents)
        agent_summaries = build_agent_summaries(unified_agents)

        # Update app state
        request.app.state.unified_agents = unified_agents
        request.app.state.handoff_map = handoff_map
        request.app.state.agent_summaries = agent_summaries

        logger.info(
            "Agent templates reloaded",
            extra={
                "agent_count": len(unified_agents),
                "agents": list(unified_agents.keys()),
            },
        )

        return {
            "status": "success",
            "message": f"Reloaded {len(unified_agents)} agent templates",
            "agents": list(unified_agents.keys()),
            "agent_count": len(unified_agents),
            "response_time_ms": round((time.time() - start) * 1000, 2),
        }

    except Exception as e:
        logger.error("Failed to reload agent templates: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload agent templates: {str(e)}",
        )
