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

Model deployment sources
------------------------
`GET /models` accepts an optional `mode` query parameter that selects which
Azure AI Foundry account the deployment list is read from:

    mode=cascade (default)  -> AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY   (the "-aif" account)
    mode=voicelive          -> AZURE_VOICELIVE_ENDPOINT / AZURE_VOICELIVE_API_KEY ("-avl" account)

This split matters because Voice Live binds the model at WebSocket connect
time against its own Foundry resource. Listing "-aif" deployments in the Voice
Live picker lets a user select a model that does not exist on the Voice Live
account, which produces a connection that never responds. For that reason the
voicelive mode never falls back to the primary catalog: if the Voice Live
endpoint is unset it returns an empty list with `source="unavailable"`.

Resource and region attribution
-------------------------------
Because those are two different accounts, and Voice Live ships in only a subset
of regions, they are routinely provisioned in different geographies from each
other AND from the app — so a turn can pay a hop nothing in the UI would
otherwise reveal. `GET /models` and `GET /voices` therefore tag every list with
the account and region that produced it (`resource_name`, `endpoint_host`,
`region`, `region_key`, `region_source`) plus the app's own region
(`app_region`, `app_region_key`) to compare against.

The region is read from the account actually connected to: Azure AI Services
stamps `x-ms-region` on the deployments listing already being made, so no extra
call, management-plane permission or configuration is required. `region_source`
distinguishes that (`"resource"`) from the configured fallback (`"config"`), and
is `""` when the region could not be determined — in which case the UI omits the
attribution rather than guessing.
"""

from __future__ import annotations

import asyncio
import copy
import os
import time
from functools import lru_cache
from typing import Any

import yaml
from apps.artagent.backend.api.v1.schemas.agent_builder import (
    ByomConfigSchema as ByomConfigSchema,
)
from apps.artagent.backend.api.v1.schemas.agent_builder import (
    DynamicAgentConfig,
    ModelConfigSchema,
)
from apps.artagent.backend.api.v1.schemas.agent_builder import (
    SessionConfigSchema as SessionConfigSchema,
)
from apps.artagent.backend.api.v1.schemas.agent_builder import (
    SpeechConfigSchema as SpeechConfigSchema,
)
from apps.artagent.backend.api.v1.schemas.agent_builder import (
    VoiceConfigSchema as VoiceConfigSchema,
)
from apps.artagent.backend.api.v1.schemas.voices import VoiceCatalogResponse, VoiceInfo
from apps.artagent.backend.registries.agentstore.base import (
    DEFAULT_TRANSCRIPTION_MODEL,
    MAI_TRANSCRIPTION_MODELS,
    HandoffConfig,
    ModelConfig,
    SpeechConfig,
    UnifiedAgent,
    VoiceLiveBYOMConfig,
    byom_profile_model_conflict,
    is_managed_voicelive_model,
)
from apps.artagent.backend.registries.agentstore.loader import (
    AGENTS_DIR,
    discover_agents,
    load_agent,
    load_defaults,
)
from apps.artagent.backend.registries.definitions import (
    agent_api_payload,
    agent_from_payload,
    definition_payload,
)
from apps.artagent.backend.registries.toolstore.registry import (
    _TOOL_DEFINITIONS,
    initialize_tools,
)
from apps.artagent.backend.src.orchestration.naming import (
    agent_key,
    find_agent_by_name,
    names_equal,
    normalize_agent_name,
)
from apps.artagent.backend.src.orchestration.session_agents import (
    get_session_agent,
    list_session_agents,
    list_session_agents_by_session,
    persist_session_agents_to_redis,
    remove_session_agent_async,
    set_session_agent,
)
from apps.artagent.backend.src.orchestration.session_drafts import (
    DraftActivationError,
    DraftPersistenceError,
    DraftStateConflict,
    get_authoring_redis,
    publish_new_session_agent,
    read_authoring_snapshot,
)
from apps.artagent.backend.src.services.voice_catalog import (
    discover_voice_catalog,
    speech_voice_scope,
)
from config import DEFAULT_TTS_VOICE
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from redis.exceptions import RedisError
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
    style: str | None = Field(default=None, description="Speaking style, e.g. 'chat'")
    pitch: str | None = Field(default=None, description="Pitch offset, e.g. '+5%'")


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
    mcp_servers: list[str] = []
    voice: dict[str, Any] | None = None
    model: dict[str, Any] | None = None
    cascade_model: dict[str, Any] | None = None
    voicelive_model: dict[str, Any] | None = None
    byom: dict[str, Any] | None = None
    speech: dict[str, Any] | None = None
    session: dict[str, Any] | None = None
    template_vars: dict[str, Any] = {}
    source: str = "yaml"
    source_path: str | None = None
    is_entry_point: bool = False
    is_session_agent: bool = False
    session_id: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# AVAILABLE VOICES CATALOG
# ═══════════════════════════════════════════════════════════════════════════════
# NOTE: this catalog is a *fallback / supplement*, not the source of truth.
# The authoritative list is the live region voice list (Speech SDK
# ``get_voices_async``), which enumerates every locale the connected Speech
# resource supports. The catalog exists so the builder still shows something
# useful when Azure can't be reached, and so HD voices remain selectable if the
# region enumeration doesn't surface them (see ``_HD_CATALOG`` below).

# Azure Speech HD voice families. HD voice short names use the
# ``<locale>-<Persona>:<HdModel>`` form, e.g. ``en-US-Ava:DragonHDLatestNeural``.
# https://learn.microsoft.com/azure/ai-services/speech-service/high-definition-voices
_HD_SUFFIX_TYPES = (
    (":dragonhdomni", "neural-hd-omni"),
    (":dragonhdflash", "neural-hd-flash"),
    (":dragonhd", "neural-hd"),
)

_CATEGORY_ORDER = {"hd": 0, "turbo": 1, "standard": 2, "mai": 3}


def _classify_voice_name(short_name: str) -> tuple[str, str, bool]:
    """Classify an Azure Speech voice short name → (category, voice_type, is_hd).

    Matching is case-insensitive because Microsoft's docs and the service use
    inconsistent casing for HD short names (``en-us-Ava:DragonHDLatestNeural``
    vs ``en-US-Ava:DragonHDLatestNeural``). Case-sensitive matching here is what
    silently dropped every HD voice from the builder.
    """
    lowered = (short_name or "").lower()
    for suffix, voice_type in _HD_SUFFIX_TYPES:
        if suffix in lowered:
            return "hd", voice_type, True
    if ":mai-voice" in lowered:
        return "mai", "mai", False
    if "turbo" in lowered:
        return "turbo", "neural-turbo", False
    return "standard", "neural", False


def _locale_from_short_name(short_name: str) -> str:
    """Best-effort locale extraction from a voice short name.

    Handles the standard ``en-US-AvaNeural`` shape plus script-qualified locales
    (``sr-Latn-RS-NicholasNeural``) and HD's ``en-US-Ava:DragonHDLatestNeural``.
    """
    base = (short_name or "").split(":", 1)[0]
    parts = base.split("-")
    if len(parts) >= 3 and len(parts[1]) == 4 and parts[1].isalpha():
        # Script subtag, e.g. sr-Latn-RS-...
        return "-".join(parts[:3])
    if len(parts) >= 2:
        return "-".join(parts[:2])
    return base or "en-US"


def _hd_voice(short_name: str, persona: str, gender: str | None = None) -> VoiceInfo:
    """Build a catalog entry for an HD voice from its documented short name."""
    category, voice_type, is_hd = _classify_voice_name(short_name)
    locale = _locale_from_short_name(short_name)
    label = (
        "HD Omni"
        if voice_type == "neural-hd-omni"
        else ("HD Flash" if voice_type == "neural-hd-flash" else "HD")
    )
    suffix = "" if locale == "en-US" else f" · {locale}"
    return VoiceInfo(
        name=short_name,
        display_name=f"{persona}{suffix} ({label})",
        category=category,
        language=locale,
        voice_type=voice_type,
        is_hd=is_hd,
        gender=gender,
    )


# Full documented DragonHD catalog (GA + preview). Previously only four en-US
# HD voices were listed, which is why the picker looked like HD barely existed.
_HD_CATALOG = [
    _hd_voice("de-DE-Florian:DragonHDLatestNeural", "Florian", "Male"),
    _hd_voice("de-DE-Seraphina:DragonHDLatestNeural", "Seraphina", "Female"),
    _hd_voice("en-US-Adam:DragonHDLatestNeural", "Adam", "Male"),
    _hd_voice("en-US-Alloy:DragonHDLatestNeural", "Alloy", "Male"),
    _hd_voice("en-US-Andrew:DragonHDLatestNeural", "Andrew", "Male"),
    _hd_voice("en-US-Andrew2:DragonHDLatestNeural", "Andrew 2", "Male"),
    _hd_voice("en-US-Andrew3:DragonHDLatestNeural", "Andrew 3", "Male"),
    _hd_voice("en-US-Aria:DragonHDLatestNeural", "Aria", "Female"),
    _hd_voice("en-US-Ava:DragonHDLatestNeural", "Ava", "Female"),
    _hd_voice("en-US-Ava3:DragonHDLatestNeural", "Ava 3", "Female"),
    _hd_voice("en-US-Brian:DragonHDLatestNeural", "Brian", "Male"),
    _hd_voice("en-US-Davis:DragonHDLatestNeural", "Davis", "Male"),
    _hd_voice("en-US-Emma:DragonHDLatestNeural", "Emma", "Female"),
    _hd_voice("en-US-Emma2:DragonHDLatestNeural", "Emma 2", "Female"),
    _hd_voice("en-US-Jenny:DragonHDLatestNeural", "Jenny", "Female"),
    _hd_voice("en-US-Nova:DragonHDLatestNeural", "Nova", "Female"),
    _hd_voice("en-US-Phoebe:DragonHDLatestNeural", "Phoebe", "Female"),
    _hd_voice("en-US-Serena:DragonHDLatestNeural", "Serena", "Female"),
    _hd_voice("en-US-Steffan:DragonHDLatestNeural", "Steffan", "Male"),
    _hd_voice("es-ES-Tristan:DragonHDLatestNeural", "Tristan", "Male"),
    _hd_voice("es-ES-Ximena:DragonHDLatestNeural", "Ximena", "Female"),
    _hd_voice("fr-FR-Remy:DragonHDLatestNeural", "Remy", "Male"),
    _hd_voice("fr-FR-Vivienne:DragonHDLatestNeural", "Vivienne", "Female"),
    _hd_voice("ja-JP-Masaru:DragonHDLatestNeural", "Masaru", "Male"),
    _hd_voice("ja-JP-Nanami:DragonHDLatestNeural", "Nanami", "Female"),
    _hd_voice("zh-CN-Xiaochen:DragonHDLatestNeural", "Xiaochen", "Female"),
    _hd_voice("zh-CN-Yunfan:DragonHDLatestNeural", "Yunfan", "Male"),
]


# Flash first: it's the low-latency model documented for real-time voice agents.
_MAI_VOICE_MODELS = ("MAI-Voice-2.1-Flash", "MAI-Voice-2.1")

# https://learn.microsoft.com/azure/ai-services/speech-service/mai-voices#availability-and-regions
MAI_VOICE_REGIONS = (
    "canadacentral",
    "centralindia",
    "eastasia",
    "eastus",
    "eastus2",
    "francecentral",
    "japaneast",
    "northeurope",
    "southeastasia",
    "swedencentral",
    "westeurope",
    "westus",
    "westus2",
    "westus3",
)

# Documented MAI-Voice-2.1 prebuilt voices; each supports every model above.
# https://learn.microsoft.com/azure/ai-services/speech-service/mai-voices#prebuilt-voices
_MAI_VOICE_PERSONAS = [
    ("cs-CZ-Grant", "Male"),
    ("cs-CZ-Harper", "Female"),
    ("da-DK-Grant", "Male"),
    ("da-DK-Harper", "Female"),
    ("de-DE-Grant", "Male"),
    ("de-DE-Harper", "Female"),
    ("de-DE-Klaus", "Male"),
    ("de-DE-Mia", "Female"),
    ("en-AU-Isla", "Female"),
    ("en-GB-Emily", "Female"),
    ("en-GB-Harry", "Male"),
    ("en-IN-Dhruv", "Male"),
    ("en-IN-Priya", "Female"),
    ("en-US-Ethan", "Male"),
    ("en-US-Grant", "Male"),
    ("en-US-Harper", "Female"),
    ("en-US-Iris", "Female"),
    ("en-US-Jasper", "Male"),
    ("en-US-Olivia", "Female"),
    ("en-US-Sage", "Male"),
    ("es-ES-Marta", "Female"),
    ("es-MX-Alejo", "Male"),
    ("es-MX-Grant", "Male"),
    ("es-MX-Harper", "Female"),
    ("es-MX-Valeria", "Female"),
    ("fi-FI-Grant", "Male"),
    ("fi-FI-Harper", "Female"),
    ("fr-FR-Grant", "Male"),
    ("fr-FR-Harper", "Female"),
    ("fr-FR-Marc", "Male"),
    ("fr-FR-Soleil", "Female"),
    ("hi-IN-Arjun", "Male"),
    ("hi-IN-Dhruv", "Male"),
    ("hi-IN-Grant", "Male"),
    ("hi-IN-Harper", "Female"),
    ("hi-IN-Kavya", "Female"),
    ("hi-IN-Priya", "Female"),
    ("hu-HU-Bence", "Male"),
    ("hu-HU-Grant", "Male"),
    ("hu-HU-Harper", "Female"),
    ("hu-HU-Levente", "Male"),
    ("hu-HU-Lilla", "Female"),
    ("hu-HU-Reka", "Female"),
    ("id-ID-Grant", "Male"),
    ("id-ID-Harper", "Female"),
    ("it-IT-Grant", "Male"),
    ("it-IT-Harper", "Female"),
    ("it-IT-Luca", "Male"),
    ("it-IT-Rosa", "Female"),
    ("ko-KR-Grant", "Male"),
    ("ko-KR-Haena", "Female"),
    ("ko-KR-Harper", "Female"),
    ("ko-KR-Junho", "Male"),
    ("nb-NO-Grant", "Male"),
    ("nb-NO-Harper", "Female"),
    ("nl-NL-Grant", "Male"),
    ("nl-NL-Harper", "Female"),
    ("nl-NL-Sander", "Male"),
    ("pl-PL-Grant", "Male"),
    ("pl-PL-Harper", "Female"),
    ("pt-BR-Caio", "Male"),
    ("pt-BR-Grant", "Male"),
    ("pt-BR-Harper", "Female"),
    ("pt-BR-Luana", "Female"),
    ("pt-BR-Pedro", "Male"),
    ("pt-BR-Rafael", "Male"),
    ("pt-PT-Grant", "Male"),
    ("pt-PT-Harper", "Female"),
    ("pt-PT-Rui", "Male"),
    ("ro-RO-Andrei", "Male"),
    ("ro-RO-Elena", "Female"),
    ("ro-RO-Grant", "Male"),
    ("ro-RO-Harper", "Female"),
    ("ro-RO-Ioana", "Female"),
    ("ro-RO-Radu", "Male"),
    ("ru-RU-Grant", "Male"),
    ("ru-RU-Harper", "Female"),
    ("ru-RU-Lev", "Male"),
    ("ru-RU-Masha", "Female"),
    ("sv-SE-Grant", "Male"),
    ("sv-SE-Harper", "Female"),
    ("th-TH-Grant", "Male"),
    ("th-TH-Harper", "Female"),
    ("th-TH-Krit", "Female"),
    ("th-TH-Nattapong", "Male"),
    ("tr-TR-Aydin", "Male"),
    ("tr-TR-Elif", "Female"),
    ("tr-TR-Grant", "Male"),
    ("tr-TR-Harper", "Female"),
    ("vi-VN-Grant", "Male"),
    ("vi-VN-Harper", "Female"),
    ("zh-CN-Bo", "Male"),
    ("zh-CN-Grant", "Male"),
    ("zh-CN-Harper", "Female"),
    ("zh-CN-Lan", "Female"),
    ("zh-CN-Mei", "Female"),
    ("zh-CN-Wei", "Male"),
]


def _mai_voice(voice_id: str, model: str, gender: str | None = None) -> VoiceInfo:
    """Build a catalog entry for a documented MAI prebuilt voice and model."""
    locale = _locale_from_short_name(voice_id)
    persona = voice_id[len(locale) + 1 :]
    suffix = "" if locale == "en-US" else f" · {locale}"
    return VoiceInfo(
        name=f"{voice_id}:{model}",
        display_name=f"{persona}{suffix} ({model})",
        category="mai",
        language=locale,
        gender=gender,
    )


_MAI_CATALOG = [
    _mai_voice(voice_id, model, gender)
    for model in _MAI_VOICE_MODELS
    for voice_id, gender in _MAI_VOICE_PERSONAS
]


AVAILABLE_VOICES = [
    # Turbo voices - lowest latency
    VoiceInfo(
        name="en-US-AlloyTurboMultilingualNeural",
        display_name="Alloy (Turbo)",
        category="turbo",
        voice_type="neural-turbo",
    ),
    VoiceInfo(
        name="en-US-EchoTurboMultilingualNeural",
        display_name="Echo (Turbo)",
        category="turbo",
        voice_type="neural-turbo",
    ),
    VoiceInfo(
        name="en-US-FableTurboMultilingualNeural",
        display_name="Fable (Turbo)",
        category="turbo",
        voice_type="neural-turbo",
    ),
    VoiceInfo(
        name="en-US-OnyxTurboMultilingualNeural",
        display_name="Onyx (Turbo)",
        category="turbo",
        voice_type="neural-turbo",
    ),
    VoiceInfo(
        name="en-US-NovaTurboMultilingualNeural",
        display_name="Nova (Turbo)",
        category="turbo",
        voice_type="neural-turbo",
    ),
    VoiceInfo(
        name="en-US-ShimmerTurboMultilingualNeural",
        display_name="Shimmer (Turbo)",
        category="turbo",
        voice_type="neural-turbo",
    ),
    # Standard voices
    VoiceInfo(name="en-US-AvaMultilingualNeural", display_name="Ava", category="standard"),
    VoiceInfo(name="en-US-AndrewMultilingualNeural", display_name="Andrew", category="standard"),
    VoiceInfo(name="en-US-EmmaMultilingualNeural", display_name="Emma", category="standard"),
    VoiceInfo(name="en-US-BrianMultilingualNeural", display_name="Brian", category="standard"),
    # HD voices - highest quality (full documented DragonHD catalog)
    *_HD_CATALOG,
    # MAI-Voice-2.1 family (preview) - multilingual, expressive synthesis.
    *_MAI_CATALOG,
]

# Keep category / voice_type / is_hd consistent with the short name so a typo in
# a hand-written catalog entry can't mislabel (or hide) a voice.
for _v in AVAILABLE_VOICES:
    _v.category, _v.voice_type, _v.is_hd = _classify_voice_name(_v.name)
del _v

_CATALOG_BY_NAME = {v.name.lower(): v for v in AVAILABLE_VOICES}


# Model deployments change rarely (they're provisioned out-of-band in Azure), so
# the live client.models.list() result is cached process-wide to avoid an Azure
# round-trip on every builder open. Callers can force a refresh with ?refresh=true.
# Keyed by resolved mode ("cascade" | "voicelive") because each mode reads a
# DIFFERENT Azure resource (see _resolve_deployment_source).
_AVAILABLE_MODELS_CACHE: dict[str, dict[str, Any]] = {}
_AVAILABLE_MODELS_TTL_S = 600.0  # 10 minutes


def _voice_sort_key(v: VoiceInfo, preferred_locale: str) -> tuple:
    """Order voices so the picker opens on the most useful options.

    Grouped by category (HD first) — MUI's ``groupBy`` requires the options to be
    sorted by group — then the resource's own locale, then alphabetically.
    """
    return (
        _CATEGORY_ORDER.get(v.category, 99),
        0 if v.language == preferred_locale else 1,
        v.language,
        v.display_name.lower(),
    )


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
            source=defn.source.value if hasattr(defn.source, "value") else str(defn.source),
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
    response_model=VoiceCatalogResponse,
    summary="List Available Voices",
    description="Get list of all available TTS voices for agent configuration from Azure Speech Service.",
    tags=["Agent Builder"],
)
async def list_available_voices(
    category: str | None = None,
    locale: str | None = None,
    hd_only: bool = False,
    use_cache: bool = True,
    include_unverified: bool = False,
    language: str | None = None,
    refresh: bool = False,
    presets_only: bool = False,
) -> VoiceCatalogResponse:
    """
    Return all voices discovered from the configured Speech resource.

    Args:
        category: Filter by category (turbo, standard, hd, mai).
        locale: Exact BCP-47 locale; language also accepts a language prefix.
        hd_only: Return only high-definition voices.
        use_cache: Use the ten-minute resource-scoped cache; false requests a refresh.
        include_unverified: Supplement discovery with explicitly unverified starter presets.
        language: Optional locale or language prefix; omitted returns every locale.
        refresh: Alias for use_cache=false.
        presets_only: Explicit offline preset catalog, with no discovery request.
    """
    start = time.time()
    discovery = (
        None if presets_only else await discover_voice_catalog(use_cache=use_cache and not refresh)
    )
    scope = discovery.scope if discovery else speech_voice_scope()
    snapshot = discovery.snapshot if discovery else None
    warnings = []
    by_name: dict[str, VoiceInfo] = {}
    hd_from_catalog = False
    if snapshot is not None:
        for voice in snapshot.voices:
            category_name, voice_type, is_hd = _classify_voice_name(voice.name)
            curated = _CATALOG_BY_NAME.get(voice.name.lower())
            if curated is not None:
                display_name = curated.display_name
            else:
                persona = voice.local_name or voice.display_name
                suffix = "" if voice.language == "en-US" else f" · {voice.language}"
                badge = {
                    "neural-hd": " (HD)",
                    "neural-hd-omni": " (HD Omni)",
                    "neural-hd-flash": " (HD Flash)",
                    "neural-turbo": " (Turbo)",
                    "mai": f" ({voice.name.split(':', 1)[-1]})",
                }.get(voice_type, "")
                display_name = f"{persona}{suffix}{badge}"
            by_name[voice.name.lower()] = voice.model_copy(
                update={
                    "display_name": display_name,
                    "category": category_name,
                    "voice_type": voice_type,
                    "service_voice_type": voice.service_voice_type or voice.voice_type,
                    "is_hd": is_hd,
                    "region_verified": True,
                }
            )
        if discovery.warning:
            warnings.append(f"Using a cached regional catalog. {discovery.warning}")
        # An empty authoritative catalog stays empty; only supplement a nonempty
        # regional list with the documented HD fallback, clearly marked unverified.
        if by_name and not any(voice.is_hd for voice in by_name.values()):
            hd_from_catalog = True
            for voice in _HD_CATALOG:
                by_name.setdefault(voice.name.lower(), voice)
            warnings.append(
                "The Speech region did not enumerate any HD voices. Documented HD voices "
                "are listed as unverified and may fail at synthesis time in this region."
            )
    else:
        if discovery and discovery.warning:
            warnings.append(discovery.warning)
        warnings.append(
            "Showing limited starter presets, not the full regional voice catalog. Availability is unverified."
        )
    if snapshot is None or include_unverified:
        for voice in AVAILABLE_VOICES:
            if presets_only or include_unverified or voice.category != "mai":
                by_name.setdefault(voice.name.lower(), voice)
    voices = sorted(
        by_name.values(),
        key=lambda voice: _voice_sort_key(voice, _locale_from_short_name(DEFAULT_TTS_VOICE)),
    )
    total_available = len(voices)
    if category:
        voices = [voice for voice in voices if voice.category == category]
    if language:
        wanted = language.lower()
        voices = [
            voice
            for voice in voices
            if voice.language.lower() == wanted or voice.language.lower().startswith(f"{wanted}-")
        ]
    if locale:
        voices = [voice for voice in voices if voice.language.lower() == locale.lower()]
    if hd_only:
        voices = [voice for voice in voices if voice.is_hd]
    by_category: dict[str, list[VoiceInfo]] = {}
    for voice in voices:
        by_category.setdefault(voice.category, []).append(voice)
    stale = bool(discovery and discovery.stale)
    locales = sorted({voice.language for voice in voices})
    region_metadata = _region_payload(scope.region, source="config")
    region_metadata["region"] = scope.region or None
    return VoiceCatalogResponse(
        status="success" if snapshot is not None and not stale else "degraded",
        total=len(voices),
        total_available=total_available,
        voices=voices,
        by_category=by_category,
        category_counts={key: len(values) for key, values in by_category.items()},
        hd_total=sum(voice.is_hd for voice in voices),
        locales=locales,
        locale_count=len(locales),
        runtime_transcription_models={
            "cascade": [DEFAULT_TRANSCRIPTION_MODEL, "azure-speech", "mai-transcribe"],
            "voicelive": [
                DEFAULT_TRANSCRIPTION_MODEL,
                "mai-transcribe",
                "azure-speech",
                "gpt-4o-transcribe",
                "gpt-4o-mini-transcribe",
                "whisper-1",
            ],
        },
        default_voice=DEFAULT_TTS_VOICE,
        verified_against_region=snapshot is not None,
        catalog_complete=(
            snapshot is not None
            and not any((category, locale, language, hd_only, hd_from_catalog, include_unverified))
        ),
        hd_from_catalog=hd_from_catalog,
        mai_voice_regions=list(MAI_VOICE_REGIONS),
        mai_voice_catalog=[voice for voice in _MAI_CATALOG if voice.name.lower() not in by_name],
        source=(
            "regional-cache"
            if stale
            else "region-validated" if snapshot is not None else "static-catalog"
        ),
        resource_host=scope.resource_host,
        resource_name=_endpoint_resource_name(scope.endpoint),
        endpoint_host=_endpoint_host(scope.endpoint),
        **region_metadata,
        cached=bool(discovery and discovery.cached),
        stale=stale,
        retrieved_at=snapshot.retrieved_at if snapshot else None,
        warnings=warnings,
        notes=warnings,
        response_time_ms=round((time.time() - start) * 1000, 2),
    )


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
    elif any(
        x in did for x in ("dall-e", "dalle", "tts", "sora", "image", "stable-diffusion", "flux")
    ):
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
    deployment_id: str,
    model_name: str | None = None,
    created_at: Any = None,
    restrict_modes: list[str] | None = None,
) -> dict[str, Any]:
    """Build the API model entry (deployment_id + categorization flags).

    ``restrict_modes`` narrows the advertised ``modes`` to the intersection with
    the caller's mode. Used when the listing came from a resource that only backs
    one orchestrator (e.g. the Voice Live account), so the builder can't offer a
    deployment for a mode whose resource doesn't actually host it.
    """
    category, arch, modes = _categorize_deployment(deployment_id)
    if restrict_modes is not None:
        modes = [m for m in modes if m in restrict_modes]
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


def _normalize_control_plane_endpoint(endpoint: str) -> str:
    """Normalize a configured endpoint to an https data-plane base URL.

    ``AZURE_VOICELIVE_ENDPOINT`` is consumed by the Voice Live SDK, so it may be
    supplied as ``wss://...`` and/or carry the realtime path. Strip both so the
    deployments REST call targets ``https://<host>/openai/deployments``.
    """
    ep = (endpoint or "").strip()
    if not ep:
        return ""
    if ep.startswith("wss://"):
        ep = "https://" + ep[len("wss://") :]
    elif ep.startswith("ws://"):
        ep = "https://" + ep[len("ws://") :]
    elif not ep.startswith("http"):
        ep = f"https://{ep}"
    # Drop any path/query (e.g. /voice-live/realtime?api-version=...): the
    # deployments listing lives at the account root.
    scheme, _, rest = ep.partition("://")
    host = rest.split("/", 1)[0].split("?", 1)[0]
    return f"{scheme}://{host}" if host else ""


def _resolve_deployment_source(mode: str) -> dict[str, Any]:
    """Resolve which Azure resource backs the model list for ``mode``.

    VoiceLive connects to the Voice Live (AVL) Foundry/AI Services account, which
    is frequently a SEPARATE account in a different region from the primary AI
    Foundry (AIF) account used by SpeechCascade — it hosts its own, much smaller,
    set of deployments. Listing AIF deployments for the VoiceLive dropdown lets a
    user pick a model that AVL cannot serve: the socket connects but the model
    never responds and the session dies on the ~900s idle timeout.

    Returns ``{endpoint, api_key, resource_name, restrict_modes, fell_back, region_hint}``.
    ``region_hint`` is a configured fallback only — the authoritative region is
    the one the account reports on the deployments listing (``x-ms-region``).
    """
    aoai_endpoint = _normalize_control_plane_endpoint(os.getenv("AZURE_OPENAI_ENDPOINT") or "")
    aoai_key = os.getenv("AZURE_OPENAI_KEY") or None
    aoai_region_hint = _configured_primary_region(aoai_endpoint)

    if mode != "voicelive":
        return {
            "endpoint": aoai_endpoint,
            "api_key": aoai_key,
            "resource_name": _endpoint_resource_name(aoai_endpoint),
            "restrict_modes": None,
            "fell_back": False,
            "region_hint": aoai_region_hint,
        }

    vl_endpoint = _normalize_control_plane_endpoint(
        os.getenv("AZURE_VOICELIVE_ENDPOINT") or os.getenv("AZURE_VOICE_LIVE_ENDPOINT") or ""
    )
    if not vl_endpoint:
        # Voice Live not separately provisioned → it runs on the primary account.
        return {
            "endpoint": aoai_endpoint,
            "api_key": aoai_key,
            "resource_name": _endpoint_resource_name(aoai_endpoint),
            "restrict_modes": ["voicelive"],
            "fell_back": True,
            "region_hint": aoai_region_hint,
        }

    vl_key = (
        os.getenv("AZURE_VOICELIVE_API_KEY")
        or os.getenv("AZURE_VOICE_API_KEY")
        # Only reuse the AOAI key when both modes point at the same account.
        or (aoai_key if vl_endpoint == aoai_endpoint else None)
    )
    vl_region_hint = (
        os.getenv("AZURE_VOICELIVE_REGION") or os.getenv("AZURE_VOICE_LIVE_REGION") or ""
    ).strip() or (aoai_region_hint if vl_endpoint == aoai_endpoint else "")
    return {
        "endpoint": vl_endpoint,
        "api_key": vl_key,
        "resource_name": _endpoint_resource_name(vl_endpoint),
        "restrict_modes": ["voicelive"],
        "fell_back": False,
        "region_hint": vl_region_hint,
    }


def _configured_primary_region(aoai_endpoint: str) -> str:
    """Configured region for the primary Azure OpenAI / AI Foundry account.

    ``AZURE_SPEECH_REGION`` is only a valid stand-in when Speech and Azure
    OpenAI are the same Foundry account (the default topology here, where both
    endpoints are exposed by one AIServices resource). When they are separate
    accounts it describes a different resource entirely, so reporting it would
    attribute the wrong region to the model list.
    """
    explicit = (os.getenv("AZURE_OPENAI_REGION") or "").strip()
    if explicit:
        return explicit
    speech_endpoint = os.getenv("AZURE_SPEECH_ENDPOINT") or ""
    same_account = bool(aoai_endpoint) and (
        _endpoint_resource_name(speech_endpoint) == _endpoint_resource_name(aoai_endpoint)
    )
    if same_account:
        return (os.getenv("AZURE_SPEECH_REGION") or "").strip()
    return ""


def _endpoint_resource_name(endpoint: str) -> str:
    """Extract the account name from an endpoint host (for UI attribution)."""
    host = _endpoint_host(endpoint)
    return host.split(".")[0] if host else ""


def _endpoint_host(endpoint: str) -> str:
    """Extract the bare host from an endpoint URL (for UI attribution)."""
    return (endpoint or "").split("://")[-1].split("/")[0].split("?")[0]


# Azure AI Services / Azure OpenAI stamp the serving region onto every
# data-plane response. Reading it off the deployments listing we already make is
# the only region signal that needs no extra call, no management-plane
# permission and no new configuration: the region of the account the app is
# ACTUALLY connected to, as that account reports it.
_REGION_HEADER = "x-ms-region"


def _region_key(value: str | None) -> str:
    """Canonicalize a region for comparison.

    Azure reports regions in two shapes — the display form from
    ``x-ms-region`` ("Sweden Central") and the slug form from configuration
    ("swedencentral"). Comparing them raw makes an identical region look like a
    cross-region hop, so every equality check goes through this.
    """
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _app_region() -> str:
    """Region the backend itself runs in, or "" when it can't be determined.

    Container Apps injects ``CONTAINER_APP_ENV_DNS_SUFFIX`` as
    ``<hash>.<region>.azurecontainerapps.io``, so the region the app serves from
    is already in the environment — no new deployment output needed. An
    environment configured with a custom DNS suffix no longer encodes the
    region, hence the DNS-label boundary check before parsing. ``AZURE_LOCATION``
    covers local/non-Container-Apps hosting.
    """
    suffix = (os.getenv("CONTAINER_APP_ENV_DNS_SUFFIX") or "").strip().lower()
    if suffix.endswith(".azurecontainerapps.io"):
        labels = suffix.split(".")
        # <hash>.<region>.azurecontainerapps.io -> the label before "azurecontainerapps"
        if len(labels) >= 3:
            return labels[-3]
    return (os.getenv("AZURE_LOCATION") or "").strip()


def _region_payload(region: str, *, source: str) -> dict[str, Any]:
    """Build the region attribution block shared by /models and /voices.

    ``source`` is ``"resource"`` when the region came from the account itself
    (``x-ms-region``), ``"config"`` when it came from configuration, and ``""``
    when unknown — the UI stays silent rather than guessing on ``""``.
    """
    app_region = _app_region()
    return {
        "region": region,
        "region_key": _region_key(region),
        "region_source": source if region else "",
        "app_region": app_region,
        "app_region_key": _region_key(app_region),
    }


def _fetch_real_deployments(
    endpoint: str | None = None, api_key: str | None = None
) -> dict[str, Any] | None:
    """List the ACTUAL model deployments on the given Foundry/Azure OpenAI
    resource via the data-plane REST API.

    ``client.models.list()`` returns the region base-model CATALOG (hundreds of
    entries like ``gpt-4-0125-Preview`` / ``dall-e-3-3.0``), NOT what's actually
    deployed — so this is the correct source for "what models can I use". Reuses
    the same endpoint + key/Entra credential as the OpenAI client (no resource
    group / management plane needed). Returns
    ``{"deployments": [{deployment_id, model_name, created_at}, ...], "region": str}``
    or None when unavailable. ``region`` is the serving region the account
    reported via ``x-ms-region``, or "" when the header was absent.

    ``endpoint``/``api_key`` default to the primary Azure OpenAI resource; pass
    the Voice Live account's values to list what VoiceLive can actually serve.
    """
    import httpx

    if endpoint is None:
        endpoint = _normalize_control_plane_endpoint(os.getenv("AZURE_OPENAI_ENDPOINT") or "")
        api_key = api_key or os.getenv("AZURE_OPENAI_KEY")
    endpoint = (endpoint or "").rstrip("/")
    if not endpoint:
        return None

    if api_key:
        headers = {"api-key": api_key}
    else:
        try:
            from utils.azure_auth import get_credential

            token = get_credential().get_token("https://cognitiveservices.azure.com/.default").token
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
            out.append(
                {
                    "deployment_id": dep_id,
                    "model_name": model_name or dep_id,
                    "created_at": it.get("created_at") or it.get("created"),
                }
            )
        if out:
            region = (r.headers.get(_REGION_HEADER) or "").strip()
            logger.info(
                "Listed %d real deployments via data-plane (api-version=%s, region=%s)",
                len(out),
                ver,
                region or "unknown",
            )
            return {"deployments": out, "region": region}
    return None


@router.get(
    "/models",
    response_model=dict[str, Any],
    summary="List Available Models",
    description=(
        "Get list of available OpenAI model deployments. Pass mode=voicelive to "
        "list the deployments on the Voice Live (AVL) resource instead of the "
        "primary AI Foundry resource. The response names the resource and region "
        "that served the list so callers can surface cross-region latency."
    ),
    tags=["Agent Builder"],
)
async def list_available_models(refresh: bool = False, mode: str | None = None) -> dict[str, Any]:
    """
    List all available OpenAI model deployments for an orchestration mode.

    ``mode=voicelive`` (aliases: ``realtime``, ``voice_live``) reads the Voice
    Live account (``AZURE_VOICELIVE_ENDPOINT``) — the resource VoiceLive actually
    connects to. Anything else reads the primary Azure OpenAI / AI Foundry
    account used by SpeechCascade.

    Deployments change rarely, so the live Azure result is cached in-process per
    mode for ~10 minutes. Pass ``refresh=true`` to bypass the cache.
    """
    start = time.time()
    resolved_mode = (
        "voicelive"
        if (mode or "").strip().lower() in ("voicelive", "voice_live", "realtime")
        else "cascade"
    )
    source = _resolve_deployment_source(resolved_mode)

    # Serve from the TTL cache unless a refresh was explicitly requested.
    entry = _AVAILABLE_MODELS_CACHE.get(resolved_mode)
    if not refresh and entry and time.time() < entry["expires"]:
        cached = dict(entry["payload"])
        cached["cached"] = True
        cached["response_time_ms"] = round((time.time() - start) * 1000, 2)
        return cached

    def _cache_and_return(
        payload: dict[str, Any], *, discovered_region: str = ""
    ) -> dict[str, Any]:
        """Store a successful payload in the per-mode TTL cache and return it.

        ``discovered_region`` is what the account itself reported on the
        deployments listing; it always wins over the configured hint, which only
        covers the paths where no listing was retrieved.
        """
        region = discovered_region or source["region_hint"]
        payload = {
            **payload,
            "mode": resolved_mode,
            "resource_name": source["resource_name"],
            # Host of the account actually serving this mode's model list, so the
            # UI can attribute the list to a specific resource unambiguously.
            "endpoint_host": _endpoint_host(source["endpoint"]),
            # True when VoiceLive was asked for but no dedicated AVL resource is
            # configured, so the primary account was used instead.
            "resource_fallback": source["fell_back"],
            **_region_payload(region, source="resource" if discovered_region else "config"),
        }
        _AVAILABLE_MODELS_CACHE[resolved_mode] = {
            "payload": payload,
            "expires": time.time() + _AVAILABLE_MODELS_TTL_S,
        }
        return {**payload, "cached": False}

    try:
        # PREFERRED: list the ACTUAL deployments on the resource that serves this
        # mode. This is what the user can really use (vs client.models.list()'s
        # 300+ region base-model catalog). Falls back to the catalog below.
        real = _fetch_real_deployments(source["endpoint"], source["api_key"])
        if real and real["deployments"]:
            deployments = real["deployments"]
            models = [
                _build_model_entry(
                    d["deployment_id"],
                    d.get("model_name"),
                    d.get("created_at"),
                    restrict_modes=source["restrict_modes"],
                )
                for d in deployments
            ]
            by_category: dict[str, list[dict[str, Any]]] = {}
            for model in models:
                by_category.setdefault(model["category"], []).append(model)
            default_model = next(
                (m["deployment_id"] for m in models if "gpt-4o" in m["deployment_id"].lower()),
                None,
            ) or (models[0]["deployment_id"] if models else "gpt-4o")
            return _cache_and_return(
                {
                    "status": "success",
                    "total": len(models),
                    "models": models,
                    "by_category": by_category,
                    "default_model": default_model,
                    "source": "deployments",
                    "response_time_ms": round((time.time() - start) * 1000, 2),
                },
                discovered_region=real["region"],
            )

        if resolved_mode == "voicelive":
            # Never fall back to the primary AOAI catalog for VoiceLive: offering
            # models the Voice Live resource doesn't host is exactly the failure
            # this split avoids (connects, then never responds). Return empty so
            # the UI falls back to the managed Voice Live catalog.
            logger.warning(
                "No Voice Live deployments listed from %s — returning empty list "
                "so the builder falls back to the managed Voice Live catalog.",
                source["endpoint"] or "<unset>",
            )
            return _cache_and_return(
                {
                    "status": "success",
                    "total": 0,
                    "models": [],
                    "by_category": {},
                    "default_model": os.getenv("AZURE_VOICELIVE_MODEL") or "gpt-realtime",
                    "source": "unavailable",
                    "response_time_ms": round((time.time() - start) * 1000, 2),
                },
                # An empty listing can still have reported the account's region.
                discovered_region=real["region"] if real else "",
            )

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

            return _cache_and_return(
                {
                    "status": "success",
                    "total": len(models),
                    "models": models,
                    "by_category": by_category,
                    "default_model": default_model,
                    "source": "azure_openai_catalog",
                    "response_time_ms": round((time.time() - start) * 1000, 2),
                }
            )

        except AttributeError:
            # Fallback: client might not support .models.list()
            # Use environment variables as fallback
            logger.warning("client.models.list() not supported, using environment fallback")

            # Get deployment from environment
            deployment_id = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

            models = [
                {
                    "deployment_id": deployment_id,
                    "model_name": deployment_id,
                    "category": "chat",
                    "arch": "native" if "realtime" in deployment_id.lower() else "cascaded",
                    "modes": ["cascade", "voicelive"],
                    "created_at": None,
                    "supports_chat": True,
                    "supports_streaming": True,
                    "endpoint_type": "chat",
                }
            ]

            return _cache_and_return(
                {
                    "status": "success",
                    "total": len(models),
                    "models": models,
                    "by_category": {"chat": models},
                    "default_model": deployment_id,
                    "source": "environment",
                    "response_time_ms": round((time.time() - start) * 1000, 2),
                }
            )

    except Exception as e:
        logger.error(f"Failed to fetch models from Azure: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch models from Azure OpenAI: {str(e)}",
        ) from e


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
            "speech": SpeechConfig.from_dict(defaults.get("speech", {})).to_dict(),
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
    """Newest mtime across agent/default/prompt files — cache-busting key.

    A new value invalidates the lru_cache below, so edits to agent.yaml,
    _defaults.yaml, or prompt-only files are reflected on the next request
    (covers local --reload dev). In Container Apps the files only change on a
    new image revision, which starts fresh containers.
    """
    try:
        patterns = ("_defaults.yaml", "*/agent.yaml", "*/*.jinja", "*/*.md", "*/*.txt")
        mtimes = [
            p.stat().st_mtime
            for pattern in patterns
            for p in AGENTS_DIR.glob(pattern)
            if p.is_file()
        ]
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
            agent = load_agent(agent_file, defaults)
            prompt_full = agent.prompt_template or ""

            prompt_preview = prompt_full[:300] + "..." if len(prompt_full) > 300 else prompt_full

            templates.append(
                AgentTemplateInfo(
                    id=agent_dir.name,
                    **{**agent_api_payload(agent), "prompt_preview": prompt_preview},
                    source="yaml",
                    source_path=str(agent_file.relative_to(AGENTS_DIR.parent)),
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
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    start = time.time()
    # Base templates come from immutable, image-local YAML files. Cache the disk
    # scan (yaml + prompt reads) keyed on the agentstore mtime so repeated opens
    # don't re-read every agent.yaml. Per-replica in-process cache — safe in
    # Container Apps because the files are identical per image revision and a new
    # revision starts fresh containers (empty cache). Copy the result before the
    # caller appends session agents so the cached list isn't mutated.
    templates: list[AgentTemplateInfo] = copy.deepcopy(
        _load_base_templates_cached(_agentstore_mtime())
    )

    # Include session agents (custom-created or edited agents).
    # When session_id is provided, scope to that session and REPLACE the base YAML
    # agent of the same name so the card list reflects saved overrides. Otherwise,
    # fall back to the legacy global behavior (append all sessions as separate cards).
    def _build_session_template(composite_key: str, sid: str, agent: Any) -> AgentTemplateInfo:
        prompt_full = agent.prompt_template or ""
        prompt_preview = prompt_full[:300] + "..." if len(prompt_full) > 300 else prompt_full
        return AgentTemplateInfo(
            id=f"session:{composite_key}",
            **{
                **agent_api_payload(agent),
                "prompt_preview": prompt_preview,
                "is_entry_point": False,
            },
            source="session",
            source_path=None,
            is_session_agent=True,
            session_id=sid,
        )

    if session_id:
        session_agents_dict = list_session_agents_by_session(session_id)
        session_agent_names = {agent_key(agent.name) for agent in session_agents_dict.values()}
        # Drop base YAML cards that are overridden by a session agent of the same name
        if session_agent_names:
            templates = [t for t in templates if agent_key(t.name) not in session_agent_names]
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


def _agent_editor_config(agent: UnifiedAgent) -> dict[str, Any]:
    """Return the complete effective configuration used by both editing entry points."""
    return agent_api_payload(agent)


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

    try:
        async with asyncio.timeout(10):
            defaults = await asyncio.to_thread(load_defaults, AGENTS_DIR)
            agent = await asyncio.to_thread(load_agent, agent_file, defaults)
        config = _agent_editor_config(agent)

        return {
            "status": "success",
            "config": config,
            "template": {
                **config,
                "id": template_id,
                "source": "yaml",
                "source_path": str(agent_file.relative_to(AGENTS_DIR.parent)),
            },
        }
    except TimeoutError as e:
        logger.error("Agent template load timed out: %s", template_id)
        raise HTTPException(status_code=504, detail="Loading the agent template timed out.") from e
    except (OSError, ValueError, TypeError, yaml.YAMLError) as e:
        logger.error("Failed to load agent template %s: %s", template_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load agent template: {str(e)}",
        ) from e


def _model_from_schema(
    schema: ModelConfigSchema, *, deployment_id: str | None = None
) -> ModelConfig:
    """Convert a ModelConfigSchema into a ModelConfig (optionally overriding deployment)."""
    data = schema.model_dump()
    if deployment_id:
        data["deployment_id"] = deployment_id
    return ModelConfig.from_dict(data)


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

    Supplied mode overrides bypass creation presets. Explicit null retains the
    generic ``model`` fallback; omitted mode fields receive editor presets.
    """
    # Presets apply only on creation omission; explicit null selects the generic model.
    if "cascade_model" in config.model_fields_set:
        cascade_model = (
            _model_from_schema(config.cascade_model) if config.cascade_model is not None else None
        )
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

    if "voicelive_model" in config.model_fields_set:
        voicelive_model = (
            _model_from_schema(config.voicelive_model)
            if config.voicelive_model is not None
            else None
        )
    elif config.model:
        base_id = config.model.deployment_id
        explicit_host = bool(
            (config.byom and config.byom.mode)
            or (
                config.session
                and (config.session.input_audio_transcription_settings or {}).get("model")
                in MAI_TRANSCRIPTION_MODELS
            )
        )
        voicelive_model = _model_from_schema(
            config.model,
            deployment_id=(
                base_id if explicit_host or "realtime" in base_id.lower() else "gpt-realtime"
            ),
        )
    else:
        voicelive_model = ModelConfig(
            deployment_id="gpt-realtime", temperature=0.7, top_p=0.9, max_tokens=4096
        )

    generic_model = (
        _model_from_schema(config.model)
        if config.model
        else cascade_model
        or ModelConfig(deployment_id="gpt-4o", temperature=0.7, top_p=0.9, max_tokens=4096)
    )
    effective_voicelive_model = voicelive_model or generic_model

    handoff_trigger = config.handoff_trigger.strip() if config.handoff_trigger else ""
    if not handoff_trigger:
        handoff_trigger = f"handoff_{config.name.lower().replace(' ', '_')}"

    session_dict: dict[str, Any] = {}
    if config.session:
        from apps.artagent.backend.registries.definitions import TURN_DETECTION_ALIASES

        session_dict = config.session.model_dump()
        nested_supplied = "turn_detection" in config.session.model_fields_set
        nested = session_dict.get("turn_detection") if nested_supplied else {}
        for flat, key in TURN_DETECTION_ALIASES.items():
            value = session_dict.pop(flat)
            if not nested_supplied or flat in config.session.model_fields_set:
                if isinstance(nested, dict):
                    nested[key] = value
        session_dict["turn_detection"] = nested
        if "input_audio_transcription_settings" not in config.session.model_fields_set:
            session_dict.pop("input_audio_transcription_settings", None)

    metadata: dict[str, Any] = {
        **config.metadata,
        "source": "dynamic",
        "session_id": session_id,
        "created_at": created_at,
    }
    if modified_at is not None:
        metadata["modified_at"] = modified_at

    # Voice Live BYOM (opt-in). None when not configured → managed VoiceLive.
    byom_config = VoiceLiveBYOMConfig.from_dict(config.byom.model_dump()) if config.byom else None

    # Guardrail: a non-managed Voice Live model (o3-mini, o1, custom/fine-tuned,
    # etc.) with BYOM OFF is the silent-failure misconfiguration — it connects to
    # managed Voice Live, which can't serve the model, so the agent never responds
    # (idle timeout + client reconnect storm). Surface it at save time instead of
    # only discovering it live in App Insights. We warn rather than raise because
    # the managed catalog grows over time (mirrors the connect-time check).
    if byom_config is None and not is_managed_voicelive_model(
        effective_voicelive_model.deployment_id
    ):
        logger.warning(
            "[AgentBuilder] non_managed_voicelive_without_byom | agent=%s "
            "voicelive_model=%s session=%s — saved without a BYOM profile; managed "
            "Voice Live cannot serve this model so the agent will not respond. Enable "
            "a BYOM profile or pick a managed Voice Live model.",
            config.name,
            effective_voicelive_model.deployment_id,
            session_id,
        )

    # Guardrail: the mirror-image misconfiguration — a BYOM profile that speaks a
    # different API than the deployment it is pointed at (e.g. Quick Tune saving
    # byom-azure-openai-chat-completion alongside gpt-realtime). Voice Live
    # connects and the session contract validates, so this is invisible until the
    # agent turns out to be mute on every turn. Warn (rather than raise) to match
    # the guard above; the connect path drops the incompatible profile.
    byom_conflict = byom_profile_model_conflict(
        byom_config.mode if byom_config else None, effective_voicelive_model.deployment_id
    )
    if byom_conflict:
        logger.warning(
            "[AgentBuilder] byom_profile_model_conflict | agent=%s voicelive_model=%s "
            "byom=%s session=%s — %s",
            config.name,
            effective_voicelive_model.deployment_id,
            byom_config.mode if byom_config else None,
            session_id,
            byom_conflict,
        )

    return agent_from_payload(
        {
            **config.model_dump(),
            "handoff": (
                config.handoff.model_dump()
                if config.handoff is not None
                else definition_payload(HandoffConfig(trigger=handoff_trigger))
            ),
            "model": definition_payload(generic_model),
            "cascade_model": definition_payload(cascade_model),
            "voicelive_model": definition_payload(voicelive_model),
            "byom": definition_payload(byom_config),
            "voice": (config.voice or VoiceConfigSchema()).model_dump(),
            "speech": (
                config.speech.model_dump() if config.speech else {"candidate_languages": ["en-US"]}
            ),
            "session": session_dict,
            "template_vars": config.template_vars or {},
            "metadata": metadata,
        }
    )


def _session_agent_response(
    agent: UnifiedAgent, session_id: str, *, status: str
) -> SessionAgentResponse:
    """Build the standard SessionAgentResponse from a built UnifiedAgent."""
    return SessionAgentResponse(
        session_id=session_id,
        agent_name=agent.name,
        status=status,
        config=agent_api_payload(agent),
        created_at=agent.metadata.get("created_at"),
        modified_at=agent.metadata.get("modified_at"),
    )


async def _resolve_live_session_agent(
    session_id: str,
    request: Request,
    *,
    agent_name: str | None = None,
    active_name: str | None = None,
    live_agent: UnifiedAgent | None = None,
    mode: str = "voicelive",
) -> UnifiedAgent | None:
    """Clone the named/current agent, never an unrelated session override."""
    from apps.artagent.backend.src.orchestration.session_memory import session_memo
    from apps.artagent.backend.src.orchestration.unified import _adapters
    from apps.artagent.backend.voice.voicelive.orchestrator import get_voicelive_orchestrator

    if agent_name is not None and not normalize_agent_name(agent_name):
        raise HTTPException(status_code=422, detail="agent_name must not be blank")
    app_state = request.app.state
    unified_agents: dict[str, UnifiedAgent] = getattr(app_state, "unified_agents", {}) or {}
    live = get_voicelive_orchestrator(session_id) if mode in ("voicelive", "voice_live") else None
    cascade = _adapters.get(session_id) if mode not in ("voicelive", "voice_live") else None
    if live is not None:
        unified_agents = {**unified_agents, **live.agents}
        active_name = active_name or live.active
    elif cascade is not None:
        unified_agents = {**unified_agents, **cascade.agents}
        active_name = active_name or cascade.active_agent
    if agent_name is None and not active_name:
        redis_mgr = getattr(app_state, "redis", None) or getattr(app_state, "redis_manager", None)
        try:
            memo = await asyncio.wait_for(session_memo(session_id, redis_mgr), timeout=5)
        except (RedisError, TimeoutError, ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Cannot resolve the active agent. Check Redis and retry with agent_name.",
            ) from exc
        active_name = memo.get_value_from_corememory("active_agent")

    target_name = agent_name or active_name or getattr(app_state, "start_agent", None)
    if target_name is None:
        default_agent = get_session_agent(session_id)
        target_name = default_agent.name if default_agent else next(iter(unified_agents), None)
    existing = get_session_agent(session_id, target_name)
    if existing is not None:
        return copy.deepcopy(existing)

    _, base_agent = find_agent_by_name(unified_agents, target_name)
    if live_agent is not None and names_equal(live_agent.name, target_name):
        base_agent = live_agent
    if base_agent is None:
        return None

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
    activate: bool = False,
    create_only: bool = False,
    app_state: Any = None,
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

    snapshot = None
    source_agent = None
    redis_manager = get_authoring_redis(app_state) if create_only else None
    if create_only:
        name = normalize_agent_name(config.name)
        if not name:
            raise HTTPException(status_code=422, detail="A new agent name must not be blank.")
        try:
            snapshot = await read_authoring_snapshot(session_id, redis_manager)
        except (
            RedisError,
            TimeoutError,
            ValueError,
            TypeError,
            KeyError,
            DraftPersistenceError,
        ) as exc:
            raise HTTPException(
                status_code=503,
                detail="Unable to read session agents. Check Redis connectivity before creating a duplicate.",
            ) from exc
        builtin_agents = discover_agents()
        app_agents = getattr(app_state, "unified_agents", {}) or {}
        reserved_names = {
            agent_key(value)
            for registry in (builtin_agents, app_agents, snapshot.agents)
            for key, item in registry.items()
            for value in (key, item.name)
        }
        if agent_key(name) in reserved_names:
            raise HTTPException(
                status_code=409,
                detail=f"Agent '{name}' already exists in the session or builtin registry. Choose an unused name.",
            )
        config = config.model_copy(update={"name": name})
        existing = None
    else:
        name = normalize_agent_name(config.name)
        if not name:
            raise HTTPException(status_code=422, detail="Agent name must not be blank.")
        existing = get_session_agent(session_id, config.name)
        source_agent = existing or find_agent_by_name(discover_agents(), config.name)[1]
        config = config.model_copy(update={"name": source_agent.name if source_agent else name})
    now = time.time()
    created_at = existing.metadata.get("created_at", now) if existing else now

    agent = build_session_agent(config, session_id, created_at=created_at, modified_at=now)
    if source_agent is not None and agent_key(source_agent.name) == agent_key(agent.name):
        agent.source_dir = source_agent.source_dir

    if create_only:
        try:
            await publish_new_session_agent(
                session_id,
                agent,
                snapshot=snapshot,
                redis_manager=redis_manager,
                activate=activate,
            )
        except DraftStateConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DraftActivationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (RedisError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Unable to create the agent durably. Check Redis connectivity and retry.",
            ) from exc
    else:
        set_session_agent(session_id, agent, set_active=activate, persist=False)
        # Legacy upserts preserve memory-only mode; create-only requires an atomic Redis commit.
        try:
            await persist_session_agents_to_redis(session_id, raise_on_failure=True)
        except (RedisError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Unable to persist the agent override. Check Redis connectivity and retry.",
            ) from exc

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
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    return await _upsert_session_agent(config, session_id, status="created", activate=True)


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
    agent_name: str | None = None,
) -> SessionAgentResponse:
    """Get a named session override, or the legacy default when no name is supplied."""
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    if agent_name is not None and not normalize_agent_name(agent_name):
        raise HTTPException(status_code=422, detail="agent_name must not be blank")
    agent = get_session_agent(session_id, agent_name)

    if not agent:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No dynamic agent '{agent_name}' configured for session {session_id}."
                if agent_name is not None
                else f"No dynamic agent configured for session {session_id}. Using default agent."
            ),
        )

    return SessionAgentResponse(
        session_id=session_id,
        agent_name=agent.name,
        status="active",
        config=_agent_editor_config(agent),
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
    activate: bool = False,
    create_only: bool = False,
) -> SessionAgentResponse:
    """
    Update the dynamic agent for a session.

    By default this is a legacy upsert. create_only=True instead rejects builtin
    and session name collisions and uses an atomic Redis commit for duplication.
    """
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    if not create_only:
        await prime_session_definitions(session_id)
    return await _upsert_session_agent(
        config,
        session_id,
        status="created" if create_only else "updated",
        activate=activate,
        create_only=create_only,
        app_state=request.app.state,
    )


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
    agent_name: str | None = None,
) -> dict[str, Any]:
    """
    Push quick session-setting changes ("shorthand") to a live call.

    - **VoiceLive**: turn_detection (threshold / silence_duration_ms /
      prefix_padding_ms) and voice (name / rate / style / pitch) are pushed live
      via a partial ``session.update``; the change also persists to the in-memory
      session agent so it survives subsequent turns. ``applied`` and ``live`` are
      both true.
    - **Cascade**: the Azure Speech recognizer binds VAD at construction and the
      SDK cannot change it mid-stream, so VAD changes return
      ``needs_reconnect=true`` (the client restarts the STT leg). Voice changes
      also return needs_reconnect so the next connection picks them up. Settings
      are persisted to the session agent (if one exists) so a reconnect applies
      them and the builder reflects them.
    """
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    mode = (payload.mode or "voicelive").lower()
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    td_dict = changes.get("turn_detection", {})
    voice_dict = {key: value for key, value in changes.get("voice", {}).items() if value}
    speech_dict = changes.get("speech", {})
    if not (td_dict or voice_dict or speech_dict):
        return {
            "status": "noop",
            "mode": mode,
            "applied": False,
            "live": False,
            "needs_reconnect": False,
        }

    orch = None
    if mode in ("voice_live", "voicelive"):
        try:
            from apps.artagent.backend.voice.voicelive.orchestrator import (
                get_voicelive_orchestrator,
            )
        except ImportError:
            get_voicelive_orchestrator = None
        if get_voicelive_orchestrator:
            orch = get_voicelive_orchestrator(session_id)

    active_name = getattr(orch, "active", None)
    live_agent = (getattr(orch, "agents", {}) or {}).get(active_name)
    live_agent = getattr(live_agent, "_agent", live_agent)
    existing = await _resolve_live_session_agent(
        session_id,
        request,
        agent_name=agent_name,
        active_name=active_name,
        live_agent=live_agent,
        mode=mode,
    )
    if existing is None and agent_name is not None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' was not found in this session or registry.",
        )

    persisted = False
    if existing is not None:
        if td_dict:
            sess = dict(existing.session or {})
            td = dict(sess.get("turn_detection") or {})
            td.update(td_dict)
            sess["turn_detection"] = td
            existing.session = sess
        if existing.speech is not None:
            for key, value in speech_dict.items():
                setattr(existing.speech, key, value)
        if existing.voice is not None:
            for key, value in voice_dict.items():
                setattr(existing.voice, key, value)
        set_session_agent(session_id, existing, set_active=False, persist=False)
        try:
            await persist_session_agents_to_redis(session_id, raise_on_failure=True)
        except (RedisError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Unable to persist agent settings. Check Redis connectivity and retry.",
            ) from exc
        persisted = True

    if mode in ("voice_live", "voicelive"):
        if orch is None or getattr(orch, "conn", None) is None:
            return {
                "status": "no_active_session",
                "mode": mode,
                "applied": persisted,
                "live": False,
                "needs_reconnect": False,
                "message": "No active VoiceLive connection; settings saved for next connect.",
            }

        if existing is None or not names_equal(existing.name, getattr(orch, "active", None)):
            return {
                "status": "saved",
                "mode": "voicelive",
                "applied": persisted,
                "live": False,
                "needs_reconnect": False,
                "message": "Selected agent is not the live agent; settings saved without switching.",
            }
        try:
            pushed = await orch.apply_live_session_settings(
                turn_detection=td_dict or None, voice=voice_dict or None
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
    from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions

    await prime_session_definitions(session_id)
    try:
        removed = await remove_session_agent_async(session_id, raise_on_failure=True)
    except Exception as exc:
        logger.error("Failed to persist session agent reset | session=%s error=%s", session_id, exc)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Dynamic agent for session {session_id} was removed in memory but "
                "could not be cleared from Redis. Please retry."
            ),
        ) from exc

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
        ) from e
