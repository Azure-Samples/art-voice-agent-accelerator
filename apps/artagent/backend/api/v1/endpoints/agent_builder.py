"""
Agent Builder Endpoints
=======================

REST endpoints for dynamically creating and managing agents at runtime.
Supports session-scoped agent configurations that can be modified through
the frontend without restarting the backend.

Endpoints:
    GET  /api/v1/agent-builder/tools      - List available tools
    GET  /api/v1/agent-builder/voices     - List available voices (from Azure Speech)
    GET  /api/v1/agent-builder/models     - List available model deployments (from Azure AI Foundry)
    GET  /api/v1/agent-builder/defaults   - Get default agent configuration
    POST /api/v1/agent-builder/create     - Create dynamic agent for session
    GET  /api/v1/agent-builder/session/{session_id} - Get session agent config
    PUT  /api/v1/agent-builder/session/{session_id} - Update session agent config
    DELETE /api/v1/agent-builder/session/{session_id} - Reset to default agent
"""

from __future__ import annotations

import copy
import os
import time
from functools import lru_cache
from typing import Any

import yaml
from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    SpeechConfig,
    UnifiedAgent,
    VoiceConfig,
    VoiceLiveBYOMConfig,
    VOICELIVE_BYOM_MODES,
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
from apps.artagent.backend.src.orchestration.naming import find_agent_by_name
from apps.artagent.backend.src.orchestration.session_agents import (
    get_session_agent,
    list_session_agents,
    list_session_agents_by_session,
    persist_session_agents_to_redis,
    remove_session_agent,
    set_session_agent,
)
from config import DEFAULT_TTS_VOICE
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
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
    source: str = "local"  # "local" or "mcp"
    mcp_server: str | None = None  # Server name if source is "mcp"
    mcp_transport: str | None = None  # Transport/protocol if source is "mcp"


class VoiceInfo(BaseModel):
    """Voice information for frontend selection."""

    name: str
    display_name: str
    category: str  # turbo, standard, hd
    language: str = "en-US"


class ModelConfigSchema(BaseModel):
    """Model configuration schema."""

    deployment_id: str = "gpt-4o"
    name: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1, le=16384)

    # Responses API parameters
    endpoint_preference: str = Field(
        default="auto",
        description="Endpoint selection: 'auto' (smart routing), 'chat' (chat/completions), 'responses' (responses API)"
    )
    verbosity: int = Field(default=0, ge=0, le=2, description="Response verbosity: 0=minimal, 1=standard, 2=detailed")
    min_p: float | None = Field(default=None, ge=0.0, le=1.0, description="Minimum probability threshold")
    typical_p: float | None = Field(default=None, ge=0.0, le=1.0, description="Typical sampling parameter")
    reasoning_effort: str | None = Field(
        default=None,
        description="Reasoning effort level: 'low', 'medium', 'high' (for o1/o3/o4 models)"
    )
    include_reasoning: bool = Field(default=False, description="Include reasoning tokens in response")
    max_completion_tokens: int | None = Field(
        default=None,
        ge=1,
        le=32768,
        description="Max completion tokens (for reasoning models and responses API)"
    )

    # Enhanced parameters
    store: bool | None = Field(default=None, description="Store conversation for training")
    metadata: dict[str, Any] | None = Field(default=None, description="Custom metadata")
    response_format: dict[str, Any] | None = Field(default=None, description="Structured output format")


class ByomConfigSchema(BaseModel):
    """Voice Live BYOM (Bring Your Own Model) configuration.

    Opt-in, VoiceLive mode only. When ``mode`` is set, the VoiceLive connection
    adds the ``profile`` query param, letting the agent use one of your own model
    deployments in the connected Foundry resource (picked via voicelive_model).
    """

    mode: str | None = Field(
        default=None,
        description=(
            "BYOM profile mode: one of byom-azure-openai-realtime, "
            "byom-azure-openai-chat-completion, byom-foundry-anthropic-messages. "
            "None/empty disables BYOM (managed VoiceLive)."
        ),
    )

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: str | None) -> str | None:
        """Accept None/empty (disabled) or one of the known BYOM profile modes."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if v not in VOICELIVE_BYOM_MODES:
            raise ValueError(
                f"Invalid BYOM mode '{v}'. Must be one of: {', '.join(VOICELIVE_BYOM_MODES)}"
            )
        return v


class VoiceConfigSchema(BaseModel):
    """Voice configuration schema."""

    name: str = "en-US-AvaMultilingualNeural"
    type: str = "azure-standard"
    style: str = "chat"
    rate: str = "+0%"
    pitch: str = Field(default="+0%", description="Voice pitch: -50% to +50%")
    endpoint_id: str | None = Field(default=None, description="Custom voice endpoint ID")


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
    input_audio_transcription_settings: dict[str, Any] | None = Field(
        default=None, description="VoiceLive input transcription settings (model, language)"
    )


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
    byom: ByomConfigSchema | None = Field(
        default=None,
        description="Voice Live BYOM (Bring Your Own Model) config (VoiceLive mode only)",
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


class LiveTurnDetectionPatch(BaseModel):
    """Partial VoiceLive turn-detection update for live tweaks."""

    type: str | None = Field(default=None, description="VAD type (azure_semantic_vad, server_vad)")
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    silence_duration_ms: int | None = Field(default=None, ge=100, le=3000)
    prefix_padding_ms: int | None = Field(default=None, ge=0, le=1000)


class LiveSpeechPatch(BaseModel):
    """Partial Cascade STT (VAD) update for live tweaks."""

    vad_silence_timeout_ms: int | None = Field(default=None, ge=100, le=5000)
    use_semantic_segmentation: bool | None = Field(default=None)


class LiveVoicePatch(BaseModel):
    """Partial TTS voice update for live tweaks."""

    name: str | None = Field(default=None, description="Azure neural voice name")
    rate: str | None = Field(default=None, description="Speaking rate, e.g. '-4%'")


class LiveSettingsRequest(BaseModel):
    """
    Shorthand session-setting tweaks applied to an in-progress call.

    ``mode`` selects the active orchestrator. VoiceLive applies turn_detection /
    voice instantly; Cascade returns needs_reconnect for VAD changes.
    """

    mode: str = Field(default="voicelive", description="voicelive | cascade")
    turn_detection: LiveTurnDetectionPatch | None = None
    speech: LiveSpeechPatch | None = None
    voice: LiveVoicePatch | None = None


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
    cascade_model: dict[str, Any] | None = None
    voicelive_model: dict[str, Any] | None = None
    byom: dict[str, Any] | None = None
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
    # MAI-Voice-2 (preview) - multilingual, high-fidelity expressive synthesis.
    # https://learn.microsoft.com/azure/ai-services/speech-service/mai-voices
    # English (US)
    VoiceInfo(name="en-US-Ethan:MAI-Voice-2", display_name="Ethan (MAI-Voice-2)", category="mai", language="en-US"),
    VoiceInfo(name="en-US-Grant:MAI-Voice-2", display_name="Grant (MAI-Voice-2)", category="mai", language="en-US"),
    VoiceInfo(name="en-US-Harper:MAI-Voice-2", display_name="Harper (MAI-Voice-2)", category="mai", language="en-US"),
    VoiceInfo(name="en-US-Iris:MAI-Voice-2", display_name="Iris (MAI-Voice-2)", category="mai", language="en-US"),
    VoiceInfo(name="en-US-Jasper:MAI-Voice-2", display_name="Jasper (MAI-Voice-2)", category="mai", language="en-US"),
    VoiceInfo(name="en-US-Olivia:MAI-Voice-2", display_name="Olivia (MAI-Voice-2)", category="mai", language="en-US"),
    # English (Australia)
    VoiceInfo(name="en-AU-Lisa:MAI-Voice-2", display_name="Lisa · en-AU (MAI-Voice-2)", category="mai", language="en-AU"),
    # German (Germany)
    VoiceInfo(name="de-DE-Klaus:MAI-Voice-2", display_name="Klaus · de-DE (MAI-Voice-2)", category="mai", language="de-DE"),
    VoiceInfo(name="de-DE-Mia:MAI-Voice-2", display_name="Mia · de-DE (MAI-Voice-2)", category="mai", language="de-DE"),
    # Spanish (Spain / Mexico)
    VoiceInfo(name="es-ES-Marta:MAI-Voice-2", display_name="Marta · es-ES (MAI-Voice-2)", category="mai", language="es-ES"),
    VoiceInfo(name="es-MX-Alejo:MAI-Voice-2", display_name="Alejo · es-MX (MAI-Voice-2)", category="mai", language="es-MX"),
    VoiceInfo(name="es-MX-Valeria:MAI-Voice-2", display_name="Valeria · es-MX (MAI-Voice-2)", category="mai", language="es-MX"),
    # French (France)
    VoiceInfo(name="fr-FR-Marc:MAI-Voice-2", display_name="Marc · fr-FR (MAI-Voice-2)", category="mai", language="fr-FR"),
    VoiceInfo(name="fr-FR-Soleil:MAI-Voice-2", display_name="Soleil · fr-FR (MAI-Voice-2)", category="mai", language="fr-FR"),
    # Hindi (India)
    VoiceInfo(name="hi-IN-Arjun:MAI-Voice-2", display_name="Arjun · hi-IN (MAI-Voice-2)", category="mai", language="hi-IN"),
    VoiceInfo(name="hi-IN-Dhruv:MAI-Voice-2", display_name="Dhruv · hi-IN (MAI-Voice-2)", category="mai", language="hi-IN"),
    VoiceInfo(name="hi-IN-Kavya:MAI-Voice-2", display_name="Kavya · hi-IN (MAI-Voice-2)", category="mai", language="hi-IN"),
    VoiceInfo(name="hi-IN-Priya:MAI-Voice-2", display_name="Priya · hi-IN (MAI-Voice-2)", category="mai", language="hi-IN"),
    # Hungarian (Hungary)
    VoiceInfo(name="hu-HU-Bence:MAI-Voice-2", display_name="Bence · hu-HU (MAI-Voice-2)", category="mai", language="hu-HU"),
    VoiceInfo(name="hu-HU-Levente:MAI-Voice-2", display_name="Levente · hu-HU (MAI-Voice-2)", category="mai", language="hu-HU"),
    VoiceInfo(name="hu-HU-Lilla:MAI-Voice-2", display_name="Lilla · hu-HU (MAI-Voice-2)", category="mai", language="hu-HU"),
    VoiceInfo(name="hu-HU-Réka:MAI-Voice-2", display_name="Réka · hu-HU (MAI-Voice-2)", category="mai", language="hu-HU"),
    # Italian (Italy)
    VoiceInfo(name="it-IT-Luca:MAI-Voice-2", display_name="Luca · it-IT (MAI-Voice-2)", category="mai", language="it-IT"),
    VoiceInfo(name="it-IT-Rosa:MAI-Voice-2", display_name="Rosa · it-IT (MAI-Voice-2)", category="mai", language="it-IT"),
    # Korean (Korea)
    VoiceInfo(name="ko-KR-Hana:MAI-Voice-2", display_name="Hana · ko-KR (MAI-Voice-2)", category="mai", language="ko-KR"),
    VoiceInfo(name="ko-KR-Junho:MAI-Voice-2", display_name="Junho · ko-KR (MAI-Voice-2)", category="mai", language="ko-KR"),
    # Dutch (Netherlands)
    VoiceInfo(name="nl-NL-Fleur:MAI-Voice-2", display_name="Fleur · nl-NL (MAI-Voice-2)", category="mai", language="nl-NL"),
    VoiceInfo(name="nl-NL-Sander:MAI-Voice-2", display_name="Sander · nl-NL (MAI-Voice-2)", category="mai", language="nl-NL"),
    # Portuguese (Brazil / Portugal)
    VoiceInfo(name="pt-BR-Caio:MAI-Voice-2", display_name="Caio · pt-BR (MAI-Voice-2)", category="mai", language="pt-BR"),
    VoiceInfo(name="pt-BR-Luana:MAI-Voice-2", display_name="Luana · pt-BR (MAI-Voice-2)", category="mai", language="pt-BR"),
    VoiceInfo(name="pt-BR-Pedro:MAI-Voice-2", display_name="Pedro · pt-BR (MAI-Voice-2)", category="mai", language="pt-BR"),
    VoiceInfo(name="pt-BR-Rafael:MAI-Voice-2", display_name="Rafael · pt-BR (MAI-Voice-2)", category="mai", language="pt-BR"),
    VoiceInfo(name="pt-PT-Rui:MAI-Voice-2", display_name="Rui · pt-PT (MAI-Voice-2)", category="mai", language="pt-PT"),
    # Romanian (Romania)
    VoiceInfo(name="ro-RO-Andrei:MAI-Voice-2", display_name="Andrei · ro-RO (MAI-Voice-2)", category="mai", language="ro-RO"),
    VoiceInfo(name="ro-RO-Elena:MAI-Voice-2", display_name="Elena · ro-RO (MAI-Voice-2)", category="mai", language="ro-RO"),
    VoiceInfo(name="ro-RO-Ioana:MAI-Voice-2", display_name="Ioana · ro-RO (MAI-Voice-2)", category="mai", language="ro-RO"),
    VoiceInfo(name="ro-RO-Radu:MAI-Voice-2", display_name="Radu · ro-RO (MAI-Voice-2)", category="mai", language="ro-RO"),
    # Russian (Russia)
    VoiceInfo(name="ru-RU-Lev:MAI-Voice-2", display_name="Lev · ru-RU (MAI-Voice-2)", category="mai", language="ru-RU"),
    VoiceInfo(name="ru-RU-Masha:MAI-Voice-2", display_name="Masha · ru-RU (MAI-Voice-2)", category="mai", language="ru-RU"),
    # Thai (Thailand)
    VoiceInfo(name="th-TH-Krit:MAI-Voice-2", display_name="Krit · th-TH (MAI-Voice-2)", category="mai", language="th-TH"),
    VoiceInfo(name="th-TH-Nattapong:MAI-Voice-2", display_name="Nattapong · th-TH (MAI-Voice-2)", category="mai", language="th-TH"),
    # Turkish (Turkey)
    VoiceInfo(name="tr-TR-Aydin:MAI-Voice-2", display_name="Aydın · tr-TR (MAI-Voice-2)", category="mai", language="tr-TR"),
    VoiceInfo(name="tr-TR-Elif:MAI-Voice-2", display_name="Elif · tr-TR (MAI-Voice-2)", category="mai", language="tr-TR"),
    # Chinese (Mandarin, Simplified)
    VoiceInfo(name="zh-CN-Bo:MAI-Voice-2", display_name="Bo · zh-CN (MAI-Voice-2)", category="mai", language="zh-CN"),
    VoiceInfo(name="zh-CN-Lan:MAI-Voice-2", display_name="Lan · zh-CN (MAI-Voice-2)", category="mai", language="zh-CN"),
    VoiceInfo(name="zh-CN-Mei:MAI-Voice-2", display_name="Mei · zh-CN (MAI-Voice-2)", category="mai", language="zh-CN"),
]


# ─────────────────────────────────────────────────────────────────────────────
# REGION VOICE AVAILABILITY
# ─────────────────────────────────────────────────────────────────────────────
# The Speech SDK's get_voices_async() is the authoritative source for which voices
# a given Speech resource supports in its region. We use it to validate the curated
# catalog so the UI never offers a voice that fails at synthesis time (e.g. a
# preview MAI voice not deployed in this region). Result is cached to avoid hitting
# Azure on every /voices call.
_AVAILABLE_VOICES_CACHE: dict[str, Any] = {"names": None, "expires": 0.0}
_AVAILABLE_VOICES_TTL_S = 600.0  # 10 minutes

# Model deployments change rarely (they're provisioned out-of-band in Azure), so
# the live client.models.list() result is cached process-wide to avoid an Azure
# round-trip on every builder open. Callers can force a refresh with ?refresh=true.
_AVAILABLE_MODELS_CACHE: dict[str, Any] = {"payload": None, "expires": 0.0}
_AVAILABLE_MODELS_TTL_S = 600.0  # 10 minutes


def _build_voice_query_speech_config():
    """Build a SpeechConfig for enumerating voices, mirroring the speech stack's
    key/region/AAD resolution. Returns the config or None if speech isn't configured."""
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        return None

    key = os.getenv("AZURE_SPEECH_KEY")
    region = os.getenv("AZURE_SPEECH_REGION")
    endpoint = os.getenv("AZURE_SPEECH_ENDPOINT")

    try:
        if key and region:
            return speechsdk.SpeechConfig(subscription=key, region=region)
        # Entra ID (managed identity / dev credential) path
        if endpoint:
            cfg = speechsdk.SpeechConfig(endpoint=endpoint)
        elif region:
            cfg = speechsdk.SpeechConfig(region=region)
        else:
            return None
        from src.speech.auth_manager import get_speech_token_manager

        get_speech_token_manager().apply_to_config(cfg, force_refresh=True)
        return cfg
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Failed to build speech config for voice listing: %s", e)
        return None


def _fetch_available_voice_names() -> set[str] | None:
    """Return the set of voice short_names the Speech resource supports in its
    region (cached for ~10 min), or None if it can't be determined."""
    now = time.time()
    if _AVAILABLE_VOICES_CACHE["names"] is not None and now < _AVAILABLE_VOICES_CACHE["expires"]:
        return _AVAILABLE_VOICES_CACHE["names"]
    try:
        import azure.cognitiveservices.speech as speechsdk

        cfg = _build_voice_query_speech_config()
        if cfg is None:
            return None
        synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
        result = synth.get_voices_async().get()
        if (
            result.reason == speechsdk.ResultReason.VoicesListRetrieved
            and result.voices
        ):
            names = {v.short_name for v in result.voices}
            _AVAILABLE_VOICES_CACHE["names"] = names
            _AVAILABLE_VOICES_CACHE["expires"] = now + _AVAILABLE_VOICES_TTL_S
            logger.info("Region supports %d TTS voices (cached)", len(names))
            return names
        logger.warning(
            "Voice list not retrieved (reason=%s); treating region support as unknown",
            getattr(result, "reason", None),
        )
        return None
    except Exception as e:
        logger.warning("Could not enumerate available voices from Azure: %s", e)
        return None


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
            source=defn.source.value if hasattr(defn.source, 'value') else str(defn.source),
            mcp_server=defn.mcp_server,
            mcp_transport=defn.mcp_transport,
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
    description="Get list of all available TTS voices for agent configuration from Azure Speech Service.",
    tags=["Agent Builder"],
)
async def list_available_voices(
    category: str | None = None,
    use_cache: bool = True,
    include_unverified: bool = False,
) -> dict[str, Any]:
    """
    List TTS voices, validated against what the Speech resource supports in its region.

    The curated catalog (AVAILABLE_VOICES) is cross-checked against the live region
    voice list (Speech SDK ``get_voices_async``) so we never offer a voice that the
    region will reject at synthesis time — e.g. a preview MAI-Voice-2 voice that
    isn't deployed in this region.

    Args:
        category: Filter by category (turbo, standard, hd, mai).
        use_cache: Retained for backward compatibility (no longer changes behavior;
            region availability is cached internally for ~10 min).
        include_unverified: If True, skip region validation and return the full
            curated catalog (including preview voices that may not be available).
    """
    start = time.time()

    # The authoritative source for "what voices does THIS Speech resource support
    # in its region" is the SDK's get_voices_async(). We use it to validate the
    # curated catalog so we never surface a voice the region rejects at synth time
    # (e.g. a preview MAI voice not deployed in this region).
    #   • available_names is a set of supported short_names, or None if we can't
    #     reach the resource (no creds / network / SDK).
    #   • include_unverified=True bypasses validation and returns the full catalog.
    available_names = None if include_unverified else _fetch_available_voice_names()
    verified = available_names is not None

    voices: list[VoiceInfo] = []
    for v in AVAILABLE_VOICES:
        is_preview = v.category == "mai"
        if available_names is not None:
            # We know exactly what the region supports — filter strictly.
            if v.name in available_names:
                voices.append(v)
        else:
            # Can't verify region support. Keep broadly-available voices, but drop
            # preview/MAI voices (the "may or may not be available" ones) unless the
            # caller explicitly opts in.
            if is_preview and not include_unverified:
                continue
            voices.append(v)

    if category:
        voices = [v for v in voices if v.category == category]

    # Group by category
    by_category: dict[str, list[dict[str, Any]]] = {}
    for voice in voices:
        if voice.category not in by_category:
            by_category[voice.category] = []
        by_category[voice.category].append(voice.model_dump() if hasattr(voice, 'model_dump') else {
            "name": voice.name,
            "display_name": voice.display_name,
            "category": voice.category,
            "language": voice.language,
        })

    return {
        "status": "success",
        "total": len(voices),
        "voices": [v.model_dump() if hasattr(v, 'model_dump') else {
            "name": v.name,
            "display_name": v.display_name,
            "category": v.category,
            "language": v.language,
        } for v in voices],
        "by_category": by_category,
        "default_voice": DEFAULT_TTS_VOICE,
        # "verified" = these voices were confirmed against the live region voice
        # list; "unverified" = couldn't reach Azure, so the curated list is used.
        "verified_against_region": verified,
        "source": "region-validated" if verified else "static-catalog",
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


def _categorize_deployment(deployment_id: str) -> tuple[str, str, list[str]]:
    """Classify a deployment/model id → (category, arch, modes).

    arch: 'native' (realtime speech-to-speech) vs 'cascaded' (STT→LLM→TTS).
    modes: which builder dropdowns can offer it — realtime→['voicelive'];
    non-conversational (embedding/transcription/image/tts/etc.)→[]; else both.
    """
    did = (deployment_id or "").lower()
    # Non-conversational types FIRST (so e.g. gpt-4o-transcribe → transcription,
    # not gpt-4; text-embedding-* → embedding).
    if "embed" in did:
        category = "embedding"
    elif "whisper" in did or "transcribe" in did:
        category = "transcription"
    elif any(x in did for x in ("dall-e", "dalle", "tts", "sora", "image", "stable-diffusion", "flux")):
        category = "other"
    elif "realtime" in did:
        category = "realtime"
    elif any(x in did for x in ("o1", "o3", "o4")):
        category = "reasoning"
    elif "gpt-5" in did:
        category = "gpt-5"
    elif "gpt-4" in did:
        category = "gpt-4"
    elif "gpt-3" in did:
        category = "gpt-3"
    else:
        category = "chat"

    arch = "native" if "realtime" in did else "cascaded"
    # Non-conversational types aren't selectable as an LLM; everything else
    # (incl. realtime models, which work in Cascade, managed VoiceLive, and BYOM)
    # is offered in both mode dropdowns.
    if category in ("embedding", "transcription", "other"):
        modes: list[str] = []
    else:
        modes = ["cascade", "voicelive"]
    return category, arch, modes


def _build_model_entry(
    deployment_id: str, model_name: str | None = None, created_at: Any = None
) -> dict[str, Any]:
    """Build the API model entry (deployment_id + categorization flags)."""
    category, arch, modes = _categorize_deployment(deployment_id)
    return {
        "deployment_id": deployment_id,
        "model_name": model_name or deployment_id,
        "category": category,
        "arch": arch,
        "modes": modes,
        "created_at": created_at,
        "supports_chat": category in ("chat", "gpt-4", "gpt-5", "reasoning", "realtime"),
        "supports_streaming": category not in ("embedding", "transcription", "other"),
        "endpoint_type": "responses" if category in ("gpt-5", "reasoning") else "chat",
    }


def _fetch_real_deployments() -> list[dict[str, Any]] | None:
    """List the ACTUAL model deployments on the connected Foundry/Azure OpenAI
    resource via the data-plane REST API.

    ``client.models.list()`` returns the region base-model CATALOG (hundreds of
    entries like ``gpt-4-0125-Preview`` / ``dall-e-3-3.0``), NOT what's actually
    deployed — so this is the correct source for "what models can I use". Reuses
    the same endpoint + key/Entra credential as the OpenAI client (no resource
    group / management plane needed). Returns a list of
    ``{deployment_id, model_name, created_at}`` or None when unavailable.
    """
    import httpx

    endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
    if not endpoint:
        return None

    key = os.getenv("AZURE_OPENAI_KEY")
    if key:
        headers = {"api-key": key}
    else:
        try:
            from utils.azure_auth import get_credential

            token = get_credential().get_token(
                "https://cognitiveservices.azure.com/.default"
            ).token
            headers = {"Authorization": f"Bearer {token}"}
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not acquire token for deployments listing: %s", exc)
            return None

    # Try a few data-plane api-versions; the deployments listing has shifted over
    # time and Foundry vs classic AOAI resources accept different ones.
    for ver in ("2024-10-21", "2023-03-15-preview", "2023-05-01"):
        url = f"{endpoint}/openai/deployments?api-version={ver}"
        try:
            r = httpx.get(url, headers=headers, timeout=8.0)
        except Exception as exc:  # pragma: no cover - network/dns
            logger.debug("Deployments probe (%s) failed: %s", ver, exc)
            continue
        if r.status_code != 200:
            continue
        try:
            body = r.json()
        except Exception:
            continue
        items = body.get("data", body) if isinstance(body, dict) else body
        if not isinstance(items, list):
            continue
        out: list[dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            dep_id = it.get("id") or it.get("name")
            if not dep_id:
                continue
            m = it.get("model")
            model_name = m.get("name") if isinstance(m, dict) else (m or dep_id)
            out.append({
                "deployment_id": dep_id,
                "model_name": model_name or dep_id,
                "created_at": it.get("created_at") or it.get("created"),
            })
        if out:
            logger.info(
                "Listed %d real deployments via data-plane (api-version=%s)", len(out), ver
            )
            return out
    return None


@router.get(
    "/models",
    response_model=dict[str, Any],
    summary="List Available Models",
    description="Get list of all available OpenAI model deployments from Azure AI Foundry.",
    tags=["Agent Builder"],
)
async def list_available_models(refresh: bool = False) -> dict[str, Any]:
    """
    List all available OpenAI model deployments from Azure AI Foundry.

    Deployments change rarely, so the live Azure result is cached in-process for
    ~10 minutes. Pass ``refresh=true`` to bypass the cache and re-query Azure.
    """
    start = time.time()

    # Serve from the TTL cache unless a refresh was explicitly requested.
    now = time.time()
    if (
        not refresh
        and _AVAILABLE_MODELS_CACHE["payload"] is not None
        and now < _AVAILABLE_MODELS_CACHE["expires"]
    ):
        cached = dict(_AVAILABLE_MODELS_CACHE["payload"])
        cached["cached"] = True
        cached["response_time_ms"] = round((time.time() - start) * 1000, 2)
        return cached

    def _cache_and_return(payload: dict[str, Any]) -> dict[str, Any]:
        """Store a successful payload in the TTL cache and return it."""
        _AVAILABLE_MODELS_CACHE["payload"] = payload
        _AVAILABLE_MODELS_CACHE["expires"] = time.time() + _AVAILABLE_MODELS_TTL_S
        return {**payload, "cached": False}

    try:
        # PREFERRED: list the ACTUAL deployments on the connected resource. This
        # is what the user can really use (vs client.models.list()'s 300+ region
        # base-model catalog). Falls back to the catalog below when unavailable.
        real = _fetch_real_deployments()
        if real:
            models = [
                _build_model_entry(d["deployment_id"], d.get("model_name"), d.get("created_at"))
                for d in real
            ]
            by_category: dict[str, list[dict[str, Any]]] = {}
            for model in models:
                by_category.setdefault(model["category"], []).append(model)
            default_model = next(
                (m["deployment_id"] for m in models if "gpt-4o" in m["deployment_id"].lower()),
                None,
            ) or (models[0]["deployment_id"] if models else "gpt-4o")
            return _cache_and_return({
                "status": "success",
                "total": len(models),
                "models": models,
                "by_category": by_category,
                "default_model": default_model,
                "source": "deployments",
                "response_time_ms": round((time.time() - start) * 1000, 2),
            })

        # Import Azure OpenAI client
        from src.aoai.client import get_client as get_aoai_client

        client = get_aoai_client()
        if not client:
            raise HTTPException(
                status_code=503,
                detail="Azure OpenAI client not initialized. Check configuration.",
            )

        # Fallback: base-model catalog (client.models.list() returns region models,
        # NOT deployments — used only when the deployments listing is unavailable).
        models = []
        try:
            # List all deployments
            deployments = client.models.list()

            for deployment in deployments:
                # Extract deployment info
                deployment_id = deployment.id
                model_name = getattr(deployment, "model", deployment_id)
                created_at = getattr(deployment, "created", None)
                models.append(_build_model_entry(deployment_id, model_name, created_at))

            # Group by category
            by_category = {}
            for model in models:
                cat = model["category"]
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(model)

            # Get recommended default
            default_model = "gpt-4o"
            for model in models:
                if "gpt-4o" in model["deployment_id"].lower():
                    default_model = model["deployment_id"]
                    break

            return _cache_and_return({
                "status": "success",
                "total": len(models),
                "models": models,
                "by_category": by_category,
                "default_model": default_model,
                "source": "azure_openai_catalog",
                "response_time_ms": round((time.time() - start) * 1000, 2),
            })

        except AttributeError:
            # Fallback: client might not support .models.list()
            # Use environment variables as fallback
            logger.warning("client.models.list() not supported, using environment fallback")

            # Get deployment from environment
            deployment_id = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

            models = [{
                "deployment_id": deployment_id,
                "model_name": deployment_id,
                "category": "chat",
                "arch": "native" if "realtime" in deployment_id.lower() else "cascaded",
                "modes": ["cascade", "voicelive"],
                "created_at": None,
                "supports_chat": True,
                "supports_streaming": True,
                "endpoint_type": "chat",
            }]

            return _cache_and_return({
                "status": "success",
                "total": len(models),
                "models": models,
                "by_category": {"chat": models},
                "default_model": deployment_id,
                "source": "environment",
                "response_time_ms": round((time.time() - start) * 1000, 2),
            })

    except Exception as e:
        logger.error(f"Failed to fetch models from Azure: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch models from Azure OpenAI: {str(e)}",
        )


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


def _agentstore_mtime() -> float:
    """Newest mtime across agent.yaml files — cache-busting key for base templates.

    A new value invalidates the lru_cache below, so edits to any agent.yaml are
    reflected on the next request (covers local --reload dev). In Container Apps
    the files only change on a new image revision, which starts fresh containers.
    """
    try:
        mtimes = [p.stat().st_mtime for p in AGENTS_DIR.glob("*/agent.yaml")]
        return max(mtimes) if mtimes else 0.0
    except Exception:
        # On any FS error, return a unique-ish value so we don't serve stale data
        return time.time()


@lru_cache(maxsize=1)
def _load_base_templates_cached(_mtime_key: float) -> list[AgentTemplateInfo]:
    """Scan the agentstore once and cache the base template list.

    Keyed on ``_mtime_key`` so it auto-invalidates when any agent.yaml changes.
    The caller MUST copy the returned list before mutating it (the cache holds
    the same list object across calls).
    """
    templates: list[AgentTemplateInfo] = []
    defaults = load_defaults(AGENTS_DIR)

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

            name = raw.get("name") or agent_dir.name.replace("_", " ").title()
            description = raw.get("description", "")
            greeting = raw.get("greeting", "")

            prompt_full = ""
            if "prompts" in raw and raw["prompts"].get("path"):
                prompt_full = load_prompt(agent_dir, raw["prompts"]["path"])
            elif raw.get("prompt"):
                prompt_full = load_prompt(agent_dir, raw["prompt"])

            tools = raw.get("tools", [])

            voice = raw.get("voice") or defaults.get("voice", {})
            model = raw.get("model") or defaults.get("model", {})
            cascade_model = raw.get("cascade_model") or defaults.get("cascade_model")
            voicelive_model = raw.get("voicelive_model") or defaults.get("voicelive_model")
            byom = raw.get("byom") or defaults.get("byom")

            handoff_config = raw.get("handoff", {})
            is_entry_point = handoff_config.get("is_entry_point", False)

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
                    cascade_model=cascade_model,
                    voicelive_model=voicelive_model,
                    byom=byom,
                    is_entry_point=is_entry_point,
                )
            )
        except Exception as e:
            logger.warning("Failed to load agent template %s: %s", agent_dir.name, e)
            continue

    # Sort by name, with entry point first
    templates.sort(key=lambda t: (not t.is_entry_point, t.name))
    return templates


@router.get(
    "/templates",
    response_model=dict[str, Any],
    summary="List Available Agent Templates",
    description="Get list of all existing agent configurations that can be used as templates.",
    tags=["Agent Builder"],
)
async def list_agent_templates(session_id: str | None = None) -> dict[str, Any]:
    """
    List all available agent templates from the agents directory.

    Returns agent configurations that can be used as starting points
    for creating new dynamic agents.

    When ``session_id`` is provided, session agents for that session REPLACE the
    base YAML agent of the same name (so edits are reflected in the card list);
    without it, session agents from all sessions are appended as separate entries.
    """
    start = time.time()
    # Base templates come from immutable, image-local YAML files. Cache the disk
    # scan (yaml + prompt reads) keyed on the agentstore mtime so repeated opens
    # don't re-read every agent.yaml. Per-replica in-process cache — safe in
    # Container Apps because the files are identical per image revision and a new
    # revision starts fresh containers (empty cache). Copy the result before the
    # caller appends session agents so the cached list isn't mutated.
    templates: list[AgentTemplateInfo] = list(_load_base_templates_cached(_agentstore_mtime()))

    # Include session agents (custom-created or edited agents).
    # When session_id is provided, scope to that session and REPLACE the base YAML
    # agent of the same name so the card list reflects saved overrides. Otherwise,
    # fall back to the legacy global behavior (append all sessions as separate cards).
    def _build_session_template(composite_key: str, sid: str, agent: Any) -> AgentTemplateInfo:
        prompt_full = agent.prompt_template or ""
        prompt_preview = prompt_full[:300] + "..." if len(prompt_full) > 300 else prompt_full
        return AgentTemplateInfo(
            id=f"session:{composite_key}",
            name=agent.name,
            description=agent.description or "",
            greeting=agent.greeting or "",
            prompt_preview=prompt_preview,
            prompt_full=prompt_full,
            tools=agent.tool_names or [],
            voice=agent.voice.to_dict() if agent.voice else None,
            model=agent.model.to_dict() if agent.model else None,
            cascade_model=agent.cascade_model.to_dict() if agent.cascade_model else None,
            voicelive_model=agent.voicelive_model.to_dict() if agent.voicelive_model else None,
            byom=agent.byom.to_dict() if agent.byom else None,
            is_entry_point=False,
            is_session_agent=True,
            session_id=sid,
        )

    if session_id:
        session_agents_dict = list_session_agents_by_session(session_id)
        session_agent_names = {agent.name for agent in session_agents_dict.values()}
        # Drop base YAML cards that are overridden by a session agent of the same name
        if session_agent_names:
            templates = [t for t in templates if t.name not in session_agent_names]
        for agent_name, agent in session_agents_dict.items():
            try:
                composite_key = f"{session_id}:{agent.name}"
                templates.append(_build_session_template(composite_key, session_id, agent))
            except Exception as e:
                logger.warning("Failed to include session agent %s: %s", agent_name, e)
                continue
    else:
        # Legacy global view: append every session agent as a separate entry.
        # list_session_agents() returns {"{session_id}:{agent_name}": agent}
        session_agents = list_session_agents()
        for composite_key, agent in session_agents.items():
            try:
                parts = composite_key.split(":", 1)
                sid = parts[0] if len(parts) > 1 else composite_key
                templates.append(_build_session_template(composite_key, sid, agent))
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
        cascade_model = raw.get("cascade_model") or defaults.get("cascade_model", {})
        voicelive_model = raw.get("voicelive_model") or defaults.get("voicelive_model", {})
        byom = raw.get("byom") or defaults.get("byom")
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
                "cascade_model": cascade_model,
                "voicelive_model": voicelive_model,
                "byom": byom,
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


def _model_from_schema(
    schema: ModelConfigSchema, *, deployment_id: str | None = None
) -> ModelConfig:
    """Convert a ModelConfigSchema into a ModelConfig (optionally overriding deployment)."""
    return ModelConfig(
        deployment_id=deployment_id or schema.deployment_id,
        name=schema.name,
        temperature=schema.temperature,
        top_p=schema.top_p,
        max_tokens=schema.max_tokens,
        endpoint_preference=schema.endpoint_preference,
        verbosity=schema.verbosity,
        min_p=schema.min_p,
        typical_p=schema.typical_p,
        reasoning_effort=schema.reasoning_effort,
        include_reasoning=schema.include_reasoning,
        max_completion_tokens=schema.max_completion_tokens,
        store=schema.store,
        metadata=schema.metadata,
        response_format=schema.response_format,
    )


def build_session_agent(
    config: DynamicAgentConfig,
    session_id: str,
    *,
    created_at: float,
    modified_at: float | None = None,
) -> UnifiedAgent:
    """
    Build a :class:`UnifiedAgent` from a ``DynamicAgentConfig``.

    Single source of truth shared by both ``POST /create`` and
    ``PUT /session/{id}`` so the two endpoints can never diverge. Tool
    validation is the caller's responsibility (it raises HTTP errors).

    Mode-specific models are resolved with this priority:
    explicit ``cascade_model`` / ``voicelive_model`` > legacy ``model`` > defaults.
    """
    # Cascade model (STT→LLM→TTS): never a realtime deployment.
    if config.cascade_model:
        cascade_model = _model_from_schema(config.cascade_model)
    elif config.model:
        base_id = config.model.deployment_id
        cascade_model = _model_from_schema(
            config.model,
            deployment_id="gpt-4o" if "realtime" in base_id.lower() else base_id,
        )
    else:
        cascade_model = ModelConfig(
            deployment_id="gpt-4o", temperature=0.7, top_p=0.9, max_tokens=4096
        )

    # VoiceLive model (realtime API): always a realtime deployment.
    if config.voicelive_model:
        voicelive_model = _model_from_schema(config.voicelive_model)
    elif config.model:
        base_id = config.model.deployment_id
        voicelive_model = _model_from_schema(
            config.model,
            deployment_id=base_id if "realtime" in base_id.lower() else "gpt-realtime",
        )
    else:
        voicelive_model = ModelConfig(
            deployment_id="gpt-realtime", temperature=0.7, top_p=0.9, max_tokens=4096
        )

    voice_config = VoiceConfig(
        name=config.voice.name if config.voice else "en-US-AvaMultilingualNeural",
        type=config.voice.type if config.voice else "azure-standard",
        style=config.voice.style if config.voice else "chat",
        rate=config.voice.rate if config.voice else "+0%",
        pitch=config.voice.pitch if config.voice else "+0%",
        endpoint_id=config.voice.endpoint_id if config.voice else None,
    )

    speech_config = SpeechConfig(
        vad_silence_timeout_ms=config.speech.vad_silence_timeout_ms if config.speech else 800,
        use_semantic_segmentation=(
            config.speech.use_semantic_segmentation if config.speech else False
        ),
        candidate_languages=config.speech.candidate_languages if config.speech else ["en-US"],
        enable_diarization=config.speech.enable_diarization if config.speech else False,
        speaker_count_hint=config.speech.speaker_count_hint if config.speech else 2,
    )

    handoff_trigger = config.handoff_trigger.strip() if config.handoff_trigger else ""
    if not handoff_trigger:
        handoff_trigger = f"handoff_{config.name.lower().replace(' ', '_')}"

    session_dict: dict[str, Any] = {}
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
        if config.session.input_audio_transcription_settings:
            session_dict["input_audio_transcription_settings"] = {
                "model": config.session.input_audio_transcription_settings.get("model"),
                "language": config.session.input_audio_transcription_settings.get("language"),
            }

    metadata: dict[str, Any] = {
        "source": "dynamic",
        "session_id": session_id,
        "created_at": created_at,
    }
    if modified_at is not None:
        metadata["modified_at"] = modified_at

    # Voice Live BYOM (opt-in). None when not configured → managed VoiceLive.
    byom_config = (
        VoiceLiveBYOMConfig.from_dict(config.byom.model_dump()) if config.byom else None
    )

    return UnifiedAgent(
        name=config.name,
        description=config.description,
        greeting=config.greeting,
        return_greeting=config.return_greeting,
        handoff=HandoffConfig(trigger=handoff_trigger),
        model=cascade_model,
        cascade_model=cascade_model,
        voicelive_model=voicelive_model,
        byom=byom_config,
        voice=voice_config,
        speech=speech_config,
        session=session_dict,
        prompt_template=config.prompt,
        tool_names=config.tools,
        template_vars=config.template_vars or {},
        metadata=metadata,
    )


def _session_agent_response(
    agent: UnifiedAgent, session_id: str, *, status: str
) -> SessionAgentResponse:
    """Build the standard SessionAgentResponse from a built UnifiedAgent."""
    prompt = agent.prompt_template or ""
    return SessionAgentResponse(
        session_id=session_id,
        agent_name=agent.name,
        status=status,
        config={
            "name": agent.name,
            "description": agent.description,
            "greeting": agent.greeting,
            "return_greeting": agent.return_greeting,
            "handoff_trigger": agent.handoff.trigger if agent.handoff else "",
            "prompt_preview": (prompt[:200] + "...") if len(prompt) > 200 else prompt,
            "tools": agent.tool_names,
            "cascade_model": agent.cascade_model.to_dict() if agent.cascade_model else {},
            "voicelive_model": agent.voicelive_model.to_dict() if agent.voicelive_model else {},
            "byom": agent.byom.to_dict() if agent.byom else None,
            "model": agent.model.to_dict() if agent.model else {},
            "voice": agent.voice.to_dict() if agent.voice else {},
            "speech": agent.speech.to_dict() if agent.speech else {},
            "session": agent.session or {},
        },
        created_at=agent.metadata.get("created_at"),
        modified_at=agent.metadata.get("modified_at"),
    )


def _resolve_live_session_agent(session_id: str, request: Request) -> UnifiedAgent | None:
    """
    Return the session-scoped agent to patch for a live-settings change.

    If the session already has an Agent Builder / Quick Tune agent, that is
    returned. Otherwise the currently-active base agent (resolved from corememory
    ``active_agent`` → ``app_state.start_agent`` → first registry agent) is
    deep-copied into session scope so live tweaks are captured in session state
    instead of being lost on the next reconnect. The clone is never the shared
    registry object, avoiding cross-session leakage.
    """
    existing = get_session_agent(session_id)
    if existing is not None:
        return existing

    app_state = request.app.state
    unified_agents: dict[str, UnifiedAgent] = getattr(app_state, "unified_agents", {}) or {}
    if not unified_agents:
        return None

    # Resolve the active agent name: corememory active_agent → start_agent → first.
    active_name: str | None = None
    try:
        redis_mgr = getattr(app_state, "redis", None) or getattr(
            app_state, "redis_manager", None
        )
        if redis_mgr is not None:
            from src.stateful.state_managment import MemoManager

            memo = MemoManager.from_redis(session_id, redis_mgr)
            active_name = memo.get_value_from_corememory("active_agent")
    except Exception:  # pragma: no cover - defensive
        active_name = None
    if not active_name:
        active_name = getattr(app_state, "start_agent", None)

    base_agent: UnifiedAgent | None = None
    if active_name:
        _, base_agent = find_agent_by_name(unified_agents, active_name)
    if base_agent is None:
        base_agent = next(iter(unified_agents.values()), None)
    if base_agent is None:
        return None

    # Session-scoped clone so live tweaks never mutate the shared registry agent.
    clone = copy.deepcopy(base_agent)
    clone.metadata = {
        **(getattr(clone, "metadata", None) or {}),
        "source": "dynamic",
        "session_id": session_id,
        "created_at": time.time(),
        "cloned_from": getattr(base_agent, "name", None),
    }
    return clone


async def _upsert_session_agent(
    config: DynamicAgentConfig,
    session_id: str,
    *,
    status: str,
) -> SessionAgentResponse:
    """
    Validate, build, store and persist a session agent (create + update share this).

    The session-agent registry is an upsert keyed by ``agent.name`` — there is no
    semantic difference between ``POST /create`` and ``PUT /session/{id}`` beyond
    the response ``status`` label, so both route through here. ``created_at`` is
    preserved from any existing agent and Redis persistence is awaited so the
    override survives a process restart before the next connection.
    """
    initialize_tools()
    invalid_tools = [t for t in config.tools if t not in _TOOL_DEFINITIONS]
    if invalid_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tools: {', '.join(invalid_tools)}. Use GET /tools to see available tools.",
        )

    existing = get_session_agent(session_id)
    now = time.time()
    created_at = existing.metadata.get("created_at", now) if existing else now

    agent = build_session_agent(
        config, session_id, created_at=created_at, modified_at=now
    )

    set_session_agent(session_id, agent)
    # Await Redis persistence directly so the override survives a process restart
    # between this write and the next WebSocket connection.
    await persist_session_agents_to_redis(session_id)

    logger.info(
        "session.agent.%s session=%s name=%s tools=%d",
        status,
        session_id,
        config.name,
        len(config.tools),
    )

    return _session_agent_response(agent, session_id, status=status)


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
    return await _upsert_session_agent(config, session_id, status="created")


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
            "byom": agent.byom.to_dict() if agent.byom else None,
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

    Creates a new agent if one doesn't exist (upsert). Shares the exact build /
    store / persist path with ``POST /create`` via ``_upsert_session_agent``.
    """
    return await _upsert_session_agent(config, session_id, status="updated")


@router.post(
    "/session/{session_id}/live-settings",
    summary="Apply Live Session Settings",
    description=(
        "Apply VAD / turn-detection and voice tweaks to an in-progress call. "
        "VoiceLive applies them instantly via session.update (no reconnect). "
        "Custom Speech Cascade cannot hot-swap STT VAD mid-stream, so it returns "
        "needs_reconnect=true for the client to restart the STT leg."
    ),
    tags=["Agent Builder"],
)
async def apply_live_session_settings(
    session_id: str,
    payload: LiveSettingsRequest,
    request: Request,
) -> dict[str, Any]:
    """
    Push quick session-setting changes ("shorthand") to a live call.

    - **VoiceLive**: turn_detection (threshold / silence_duration_ms /
      prefix_padding_ms) and voice (name / rate) are pushed live via a partial
      ``session.update``; the change also persists to the in-memory session agent
      so it survives subsequent turns. ``applied`` and ``live`` are both true.
    - **Cascade**: the Azure Speech recognizer binds VAD at construction and the
      SDK cannot change it mid-stream, so VAD changes return
      ``needs_reconnect=true`` (the client restarts the STT leg). Voice changes
      also return needs_reconnect so the next connection picks them up. Settings
      are persisted to the session agent (if one exists) so a reconnect applies
      them and the builder reflects them.
    """
    mode = (payload.mode or "voicelive").lower()

    # Best-effort persist onto the session agent so the builder and any reconnect
    # reflect the new values. If no Agent Builder agent exists yet (e.g. a live
    # scenario/base-agent call), clone the active base agent into session scope so
    # the tweak is captured in session state rather than lost on reconnect.
    persisted = False
    existing = _resolve_live_session_agent(session_id, request)
    if existing is not None:
        try:
            if payload.turn_detection is not None:
                sess = dict(existing.session or {})
                td = dict(sess.get("turn_detection") or {})
                for key in ("type", "threshold", "silence_duration_ms", "prefix_padding_ms"):
                    val = getattr(payload.turn_detection, key, None)
                    if val is not None:
                        td[key] = val
                sess["turn_detection"] = td
                existing.session = sess
            if payload.speech is not None and existing.speech is not None:
                if payload.speech.vad_silence_timeout_ms is not None:
                    existing.speech.vad_silence_timeout_ms = payload.speech.vad_silence_timeout_ms
                if payload.speech.use_semantic_segmentation is not None:
                    existing.speech.use_semantic_segmentation = (
                        payload.speech.use_semantic_segmentation
                    )
            if payload.voice is not None and existing.voice is not None:
                if payload.voice.name:
                    existing.voice.name = payload.voice.name
                if payload.voice.rate:
                    existing.voice.rate = payload.voice.rate
            set_session_agent(session_id, existing)
            persisted = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to persist live settings for %s: %s", session_id, exc)

    if mode in ("voice_live", "voicelive"):
        # Import lazily to avoid a hard dependency when VoiceLive isn't installed.
        try:
            from apps.artagent.backend.voice.voicelive.orchestrator import (
                get_voicelive_orchestrator,
            )
        except Exception:  # pragma: no cover - defensive
            get_voicelive_orchestrator = None  # type: ignore[assignment]

        orch = get_voicelive_orchestrator(session_id) if get_voicelive_orchestrator else None
        if orch is None or getattr(orch, "conn", None) is None:
            return {
                "status": "no_active_session",
                "mode": mode,
                "applied": persisted,
                "live": False,
                "needs_reconnect": False,
                "message": "No active VoiceLive connection; settings saved for next connect.",
            }

        td_dict = (
            {
                "type": payload.turn_detection.type,
                "threshold": payload.turn_detection.threshold,
                "silence_duration_ms": payload.turn_detection.silence_duration_ms,
                "prefix_padding_ms": payload.turn_detection.prefix_padding_ms,
            }
            if payload.turn_detection is not None
            else None
        )
        voice_dict = (
            {"name": payload.voice.name, "rate": payload.voice.rate}
            if payload.voice is not None
            else None
        )
        try:
            pushed = await orch.apply_live_session_settings(
                turn_detection=td_dict, voice=voice_dict
            )
        except Exception as exc:
            logger.error("Live VoiceLive session update failed | session=%s: %s", session_id, exc)
            raise HTTPException(status_code=502, detail=f"Live update failed: {exc}") from exc

        return {
            "status": "applied" if pushed else "noop",
            "mode": "voicelive",
            "applied": True,
            "live": pushed,
            "needs_reconnect": False,
        }

    # Cascade: VAD is bound at recognizer construction; the Azure Speech SDK
    # cannot change it mid-stream. Signal the client to restart the STT leg.
    return {
        "status": "needs_reconnect",
        "mode": "cascade",
        "applied": persisted,
        "live": False,
        "needs_reconnect": True,
        "message": (
            "Custom Speech Cascade cannot change STT VAD mid-stream. "
            "Restart the stream to apply the new settings."
        ),
    }


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
