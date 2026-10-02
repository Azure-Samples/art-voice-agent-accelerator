"""
UnifiedAgent Base Class
=======================

Orchestrator-agnostic agent that works with both:
- SpeechCascade (gpt_flow) → State-based handoffs
- VoiceLive (LiveOrchestrator) → Tool-based handoffs

The agent itself doesn't know which orchestrator will run it.
The orchestrator adapter handles the translation.

Usage:
    from apps.artagent.agents.base import UnifiedAgent, HandoffConfig

    agent = UnifiedAgent(
        name="FraudAgent",
        description="Fraud detection specialist",
        handoff=HandoffConfig(trigger="handoff_fraud_agent"),
        tool_names=["analyze_transactions", "block_card"],
    )

    # Get tools from shared registry
    tools = agent.get_tools()

    # Render prompt with runtime context
    prompt = agent.render_prompt({"caller_name": "John", "client_id": "123"})
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps.artagent.backend.registries.definitions import decode_definition, definition_payload
from jinja2 import TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment
from utils.ml_logging import get_logger

logger = get_logger("agents.base")


@dataclass
class HandoffConfig:
    """
    Handoff configuration for an agent.

    Attributes:
        trigger: Tool name that routes TO this agent (e.g., "handoff_fraud_agent")
        is_entry_point: Whether this agent is the default starting agent
    """

    trigger: str = ""
    is_entry_point: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandoffConfig:
        """Create HandoffConfig from dict (YAML parsing)."""
        from apps.artagent.backend.registries.definitions import decode_definition

        return decode_definition(cls, data or {})


@dataclass
class VoiceConfig:
    """Voice configuration for TTS."""

    name: str = "en-US-ShimmerTurboMultilingualNeural"
    type: str = "azure-standard"
    style: str = "chat"
    rate: str = "+0%"
    pitch: str = "+0%"
    endpoint_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceConfig:
        """Create VoiceConfig from dict."""
        from apps.artagent.backend.registries.definitions import decode_definition

        return decode_definition(cls, data or {})

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        from apps.artagent.backend.registries.definitions import definition_payload

        return definition_payload(self)


@dataclass
class ModelConfig:
    """Model configuration for LLM with support for both /chat/completions and /responses endpoints."""

    # Core identification
    deployment_id: str = "gpt-4o"
    name: str = "gpt-4o"  # Alias for deployment_id

    # Legacy parameters (chat.completions) - can be None for models that don't support them
    temperature: float | None = 0.7
    top_p: float | None = 0.9
    max_tokens: int | None = 4096

    # New sampling parameters (responses endpoint)
    min_p: float | None = None  # Minimum probability threshold
    typical_p: float | None = None  # Typical sampling parameter

    # Reasoning/thinking parameters (o1/o3/o4 models)
    reasoning_effort: str | None = None  # "low", "medium", "high"
    include_reasoning: bool = False  # Include reasoning tokens in response
    max_completion_tokens: int | None = None  # For reasoning models (replaces max_tokens)

    # Verbosity and output control
    verbosity: int = 0  # Output verbosity level (0=minimal/realtime, 1=standard, 2=detailed)
    store: bool | None = None  # Whether to store the response for later retrieval
    metadata: dict[str, Any] | None = None  # Custom metadata for the request

    # Response format enhancements
    response_format: dict[str, Any] | None = None  # Enhanced JSON schema support

    # Endpoint selection
    endpoint_preference: str = "auto"  # "auto", "chat", "responses"
    api_version: str | None = "v1"  # Responses API version (optional override)

    # Model metadata (auto-detected)
    model_family: str | None = None  # Auto-detect from deployment_id

    def _detect_model_family(self) -> str:
        """Auto-detect model family from deployment_id."""
        deployment = self.deployment_id.lower()
        if "o1" in deployment:
            return "o1"
        if "o3" in deployment:
            return "o3"
        if "o4" in deployment:
            return "o4"
        if "gpt-4" in deployment:
            return "gpt-4"
        if "gpt-5" in deployment:
            return "gpt-5"
        return "unknown"

    @property
    def is_reasoning_model(self) -> bool:
        """Check if this is a reasoning model (o1/o3/o4) that supports reasoning-specific params."""
        family = self.model_family or self._detect_model_family()
        return family in ("o1", "o3", "o4")

    @property
    def supports_reasoning_effort(self) -> bool:
        """True when the deployment accepts a ``reasoning_effort`` value.

        Broader than :attr:`is_reasoning_model`: the o-series are reasoning-only
        models, but the gpt-5 family also accepts ``reasoning_effort`` — including
        ``"none"``/``"minimal"`` to suppress reasoning, which is what a real-time
        voice agent wants since reasoning latency is paid on every turn.

        Without this, ``reasoning_effort`` set on a gpt-5 agent was accepted by the
        schema and then silently dropped when building the request, so there was no
        way to pin "no reasoning" for the models Voice Live BYOM runs on.
        """
        family = self.model_family or self._detect_model_family()
        return family in ("o1", "o3", "o4", "gpt-5")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelConfig:
        """Create ModelConfig from dict."""
        data = dict(data or {})
        data.setdefault("deployment_id", data.get("name") or cls.deployment_id)
        if data.get("name") is None:
            data["name"] = data["deployment_id"]
        instance = decode_definition(cls, data)
        if "model_family" not in data:
            instance.model_family = instance._detect_model_family()
        return instance

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return definition_payload(self)


# Valid Voice Live BYOM (Bring Your Own Model) profile modes. These map to the
# `profile` query parameter on the VoiceLive WebSocket connect() call.
# See: https://learn.microsoft.com/azure/ai-services/speech-service/how-to-bring-your-own-model
VOICELIVE_BYOM_MODES = (
    "byom-azure-openai-realtime",
    "byom-azure-openai-chat-completion",
    "byom-foundry-anthropic-messages",
)

MAI_TRANSCRIPTION_MODEL = "mai-transcribe"
DEFAULT_TRANSCRIPTION_MODEL = "mai-transcribe-2"
MAI_TRANSCRIPTION_MODELS = frozenset({MAI_TRANSCRIPTION_MODEL, DEFAULT_TRANSCRIPTION_MODEL})
MAI_VOICELIVE_API_VERSION = "2026-04-10"


def normalize_transcription_model(model: str) -> str:
    """Normalize MAI names without replacing the explicitly requested 2.0 model."""
    if not isinstance(model, str):
        raise ValueError("transcription_model must be a string")
    normalized = model.strip().lower()
    if normalized == DEFAULT_TRANSCRIPTION_MODEL:
        return DEFAULT_TRANSCRIPTION_MODEL
    if normalized in {"mai-transcribe", "mai-transcribe-1.5"}:
        return MAI_TRANSCRIPTION_MODEL
    return model


def validate_mai_customization(model: str, settings: dict[str, Any]) -> None:
    """Reject retained Azure Speech customization rather than ignoring it for MAI."""
    if normalize_transcription_model(model) not in MAI_TRANSCRIPTION_MODELS:
        return
    incompatible = [
        key for key in ("custom_speech", "phrase_list") if settings.get(key) is not None
    ]
    if incompatible:
        raise ValueError(
            f"{model} does not support {', '.join(incompatible)}. "
            "Remove these Azure Speech options or select azure-speech."
        )


def validate_voicelive_transcription(
    settings: dict[str, Any] | None,
    *,
    model_name: str,
    byom_profile: str | None = None,
) -> dict[str, Any]:
    """Resolve input defaults and reject MAI incompatibilities at runtime.

    Validate against the connection's model/profile during handoffs, not the
    target agent's unused model choice. Do not use this cross-mode check when
    saving an agent: its VoiceLive configuration may be unused in Cascade.
    Text BYOM defaults to MAI 2.0. Explicit ``auto`` retains Azure Speech for
    other profiles; otherwise their omitted settings keep service behavior.
    """
    if byom_profile and byom_profile not in VOICELIVE_BYOM_MODES:
        raise ValueError(
            f"Unsupported VoiceLive BYOM profile '{byom_profile}'. "
            f"Use one of: {', '.join(VOICELIVE_BYOM_MODES)}."
        )
    result = dict(settings or {})
    if isinstance(result.get("model"), str):
        result["model"] = normalize_transcription_model(result["model"])
    elif result.get("model") is not None:
        raise ValueError("VoiceLive transcription model must be a string or null")
    model = result.get("model")
    if not model or model == "auto":
        if byom_profile in (
            "byom-azure-openai-chat-completion",
            "byom-foundry-anthropic-messages",
        ):
            result["model"] = DEFAULT_TRANSCRIPTION_MODEL
        elif model == "auto":
            result["model"] = "azure-speech"
    model = result.get("model")
    if model not in MAI_TRANSCRIPTION_MODELS:
        return result

    validate_mai_customization(model, result)
    if byom_profile == "byom-azure-openai-realtime":
        raise ValueError(
            f"{model} cannot use the byom-azure-openai-realtime profile. "
            "Select a managed text model or an explicit BYOM chat/Anthropic profile."
        )
    if not byom_profile and model_name.strip().lower() not in _VOICELIVE_MANAGED_TEXT_MODELS:
        raise ValueError(
            f"{model} requires a non-multimodal managed text model (for example gpt-4.1), "
            f"not '{model_name}'. Native realtime/audio models are incompatible. "
            "For your own text deployment, explicitly select byom-azure-openai-chat-completion "
            "or byom-foundry-anthropic-messages; model names alone do not select BYOM."
        )
    return result


@dataclass
class VoiceLiveBYOMConfig:
    """Per-agent Voice Live BYOM (Bring Your Own Model) configuration.

    BYOM lets a VoiceLive session use a model deployment you brought yourself
    (a fine-tuned Azure OpenAI model, an Anthropic Claude / Grok / model-router
    deployment, a PTU deployment, etc.) instead of a VoiceLive-managed model.

    It is wired purely at connect() time via a WebSocket query param — the agent's
    ``voicelive_model.deployment_id`` is still the model name (selected from the
    deployments in the connected Foundry resource); this config only adds the
    ``profile`` query param:

        profile=<mode>

    When ``mode`` is None/empty, BYOM is disabled and the connection uses the
    default VoiceLive managed behavior (no profile param sent).
    """

    # BYOM profile mode (one of VOICELIVE_BYOM_MODES) or None to disable.
    mode: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> VoiceLiveBYOMConfig | None:
        """Create a VoiceLiveBYOMConfig from a dict, or None when unset/disabled."""
        if not data:
            return None
        mode = data.get("mode") or data.get("byom") or None
        if isinstance(mode, str):
            mode = mode.strip() or None
        if not mode:
            return None
        return decode_definition(cls, {**data, "mode": mode})

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a YAML/JSON-friendly dict (omits empty fields)."""
        return {"mode": self.mode} if self.mode else {}

    def to_query(self) -> dict[str, str] | None:
        """Build the VoiceLive connect() query params, or None when disabled.

        Returns ``{"profile": <mode>}`` so it can be passed straight to
        ``connect(..., query=...)``.
        """
        if not self.mode:
            return None
        if self.mode not in VOICELIVE_BYOM_MODES:
            raise ValueError(
                f"Unsupported VoiceLive BYOM profile '{self.mode}'. "
                f"Use one of: {', '.join(VOICELIVE_BYOM_MODES)}."
            )
        return {"profile": self.mode}


# Models the Voice Live service can host itself — i.e. valid to run with BYOM OFF.
# A model NOT in this set (o3-mini, o1, o3, plain gpt-5-chat, or any custom /
# fine-tuned deployment) can ONLY run via a BYOM profile: selecting it for
# VoiceLive without BYOM lets the socket open but the model never responds, so the
# agent goes silent until the ~900s idle timeout. This set is the single-source
# invariant used to catch that (previously silent) misconfiguration.
# Keep in sync with the frontend MANAGED_VOICELIVE_MODELS (foundryModels.js) and:
# https://learn.microsoft.com/azure/ai-services/speech-service/voice-live#supported-models-and-regions
MANAGED_VOICELIVE_MODELS = frozenset(
    {
        # Native speech-to-speech (realtime).
        "gpt-realtime-1.5",
        "gpt-realtime",
        "gpt-realtime-mini",
        "phi4-mm-realtime",
        "azure-realtime",
        # Cascaded (Azure STT -> text LLM -> Azure TTS).
        "gpt-5.6-terra",
        "gpt-5.4",
        "gpt-5.3-chat",
        "gpt-5.2",
        "gpt-5.2-chat",
        "gpt-5.1",
        "gpt-5.1-chat",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-4o-mini",
        "phi4-mini",
    }
)

_MANAGED_VOICELIVE_MODELS_LOWER = frozenset(m.lower() for m in MANAGED_VOICELIVE_MODELS)
_VOICELIVE_MANAGED_TEXT_MODELS = frozenset(
    model for model in _MANAGED_VOICELIVE_MODELS_LOWER if "realtime" not in model
)


def is_managed_voicelive_model(deployment_id: str | None) -> bool:
    """True when ``deployment_id`` is a model managed Voice Live can host itself.

    Managed Voice Live can only serve the models in ``MANAGED_VOICELIVE_MODELS``.
    Any other deployment (o3-mini, o1, a fine-tuned/custom name, ...) REQUIRES a
    BYOM profile — connecting it as managed makes the agent go silent. An empty id
    is treated as managed (nothing to validate; the runtime applies its default).
    """
    if not deployment_id:
        return True
    return deployment_id.strip().lower() in _MANAGED_VOICELIVE_MODELS_LOWER


# A BYOM profile selects the wire protocol Voice Live drives your deployment with,
# so the deployment has to actually expose that API:
#   byom-azure-openai-realtime        -> /realtime         (gpt-realtime, phi4-mm-realtime, ...)
#   byom-azure-openai-chat-completion -> /chat/completions  (gpt-4o, gpt-5.x, o3-mini, ...)
# Pairing a profile with a deployment that speaks the *other* protocol is a second
# silent-failure mode, distinct from the managed-model one above: the socket opens,
# the session contract validates, and STT keeps transcribing, but the LLM leg never
# answers — so the agent is mute until the ~900s idle timeout. Observed in App
# Insights: byom-azure-openai-chat-completion pinned to gpt-realtime produced
# ``ttft=N/A ttfb=N/A synth=N/A`` on every turn while the same agent without the
# profile answered in ~1.1s.
BYOM_REALTIME_MODE = "byom-azure-openai-realtime"
BYOM_CHAT_COMPLETION_MODE = "byom-azure-openai-chat-completion"


def is_realtime_voicelive_model(deployment_id: str | None) -> bool:
    """True when ``deployment_id`` names a realtime (speech-to-speech) deployment.

    Mirrors the frontend ``classifyVoiceLiveArch`` heuristic: Azure realtime model
    and deployment names carry ``realtime`` (gpt-realtime, gpt-realtime-mini,
    phi4-mm-realtime, azure-realtime).
    """
    return "realtime" in (deployment_id or "").lower()


def byom_profile_model_conflict(mode: str | None, deployment_id: str | None) -> str | None:
    """Explain why BYOM profile ``mode`` cannot drive ``deployment_id``.

    Returns ``None`` when the pairing is valid (or not decidable). Only the two
    Azure OpenAI profiles are checked — ``byom-foundry-anthropic-messages`` points
    at arbitrarily named Foundry deployments, so there is no reliable signal to
    validate it against and we must not guess.
    """
    if not mode or not deployment_id:
        return None

    realtime = is_realtime_voicelive_model(deployment_id)
    if mode == BYOM_CHAT_COMPLETION_MODE and realtime:
        deployment = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", deployment_id.strip().lower())
        if deployment not in _MANAGED_VOICELIVE_MODELS_LOWER and deployment not in {
            "gpt-4o-realtime-preview",
            "gpt-4o-mini-realtime-preview",
        }:
            # Custom deployment names do not establish their protocol. An
            # explicitly selected text profile must not be silently discarded.
            return None
        return (
            f"BYOM profile '{mode}' drives the deployment over the chat completions "
            f"API, but '{deployment_id}' is a realtime (speech-to-speech) deployment "
            "and does not serve /chat/completions. The session connects and STT keeps "
            "working, but the model never responds. Use a chat deployment (gpt-4o, "
            f"gpt-5.x, ...) or switch the profile to '{BYOM_REALTIME_MODE}'."
        )
    if mode == BYOM_REALTIME_MODE and not realtime:
        return (
            f"BYOM profile '{mode}' drives the deployment over the realtime API, but "
            f"'{deployment_id}' is not a realtime deployment and does not serve "
            "/realtime. The session connects but the model never responds. Use a "
            "realtime deployment (gpt-realtime, ...) or switch the profile to "
            f"'{BYOM_CHAT_COMPLETION_MODE}'."
        )
    return None


@dataclass
class SpeechConfig:
    """
    Speech recognition (STT) configuration for the agent.

    Controls VAD, segmentation, language detection, and other speech processing settings.
    These settings affect how the speech recognizer processes incoming audio.
    """

    # VAD (Voice Activity Detection)
    vad_silence_timeout_ms: int = 800  # Silence duration before finalizing recognition
    use_semantic_segmentation: bool = False  # Enable semantic sentence boundary detection

    # Language settings
    candidate_languages: list[str] = field(
        default_factory=lambda: ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT"]
    )

    # Advanced features
    enable_diarization: bool = False  # Speaker diarization for multi-speaker scenarios
    speaker_count_hint: int = 2  # Hint for number of speakers in diarization
    transcription_model: str = DEFAULT_TRANSCRIPTION_MODEL

    def __post_init__(self) -> None:
        self.transcription_model = normalize_transcription_model(self.transcription_model)
        if self.transcription_model not in {"azure-speech", *MAI_TRANSCRIPTION_MODELS}:
            raise ValueError(
                "transcription_model must be azure-speech, mai-transcribe or mai-transcribe-2"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeechConfig:
        """Create SpeechConfig from dict."""
        data = dict(data or {})
        validate_mai_customization(data.get("transcription_model", cls.transcription_model), data)
        return decode_definition(cls, data)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return definition_payload(self)


@dataclass
class UnifiedAgent:
    """
    Orchestrator-agnostic agent configuration.

    Works with both:
    - SpeechCascade (gpt_flow) → State-based handoffs
    - VoiceLive (LiveOrchestrator) → Tool-based handoffs

    The agent itself doesn't know which orchestrator will run it.
    The orchestrator adapter handles the translation.
    """

    # ─────────────────────────────────────────────────────────────────
    # Identity
    # ─────────────────────────────────────────────────────────────────
    name: str
    description: str = ""

    # ─────────────────────────────────────────────────────────────────
    # Greetings
    # ─────────────────────────────────────────────────────────────────
    greeting: str = ""
    return_greeting: str = ""

    # ─────────────────────────────────────────────────────────────────
    # Handoff Configuration
    # ─────────────────────────────────────────────────────────────────
    handoff: HandoffConfig = field(default_factory=HandoffConfig)

    # ─────────────────────────────────────────────────────────────────
    # Model Settings
    # ─────────────────────────────────────────────────────────────────
    model: ModelConfig = field(default_factory=ModelConfig)

    # Mode-specific model overrides (if both are set, orchestrator picks)
    cascade_model: ModelConfig | None = None
    voicelive_model: ModelConfig | None = None

    # Voice Live BYOM (Bring Your Own Model) — opt-in, VoiceLive mode only.
    # When set, adds the `profile` (and optional `foundry-resource-override`)
    # query params at connect() time. None = default managed VoiceLive behavior.
    byom: VoiceLiveBYOMConfig | None = None

    # ─────────────────────────────────────────────────────────────────
    # Voice Settings (TTS)
    # ─────────────────────────────────────────────────────────────────
    voice: VoiceConfig = field(default_factory=VoiceConfig)

    # ─────────────────────────────────────────────────────────────────
    # Speech Recognition Settings (STT)
    # ─────────────────────────────────────────────────────────────────
    speech: SpeechConfig = field(default_factory=SpeechConfig)

    # ─────────────────────────────────────────────────────────────────
    # Session Settings (VoiceLive-specific)
    # ─────────────────────────────────────────────────────────────────
    session: dict[str, Any] = field(default_factory=dict)

    # ─────────────────────────────────────────────────────────────────
    # Prompt
    # ─────────────────────────────────────────────────────────────────
    prompt_template: str = ""

    # ─────────────────────────────────────────────────────────────────
    # Tools
    # ─────────────────────────────────────────────────────────────────
    tool_names: list[str] = field(default_factory=list)

    # ─────────────────────────────────────────────────────────────────
    # MCP Servers (external tool providers)
    # ─────────────────────────────────────────────────────────────────
    mcp_servers: list[str] = field(default_factory=list)

    # ─────────────────────────────────────────────────────────────────
    # Template Variables (for prompt rendering)
    # ─────────────────────────────────────────────────────────────────
    template_vars: dict[str, Any] = field(default_factory=dict)

    # ─────────────────────────────────────────────────────────────────
    # Metadata
    # ─────────────────────────────────────────────────────────────────
    metadata: dict[str, Any] = field(default_factory=dict)
    source_dir: Path | None = None
    _custom_tools_loaded: bool = field(default=False, init=False, repr=False)
    _cached_tools: list[dict[str, Any]] | None = field(default=None, init=False, repr=False)

    # ═══════════════════════════════════════════════════════════════════
    # TOOL INTEGRATION (via shared registry)
    # ═══════════════════════════════════════════════════════════════════

    def _load_custom_tools(self) -> None:
        """
        Load agent-scoped tools from tools.py in the agent directory.

        If present, this file can register tools with override=True to take
        precedence over shared tool configs. An optional TOOL_NAMES iterable
        in that module will replace the agent's tool list.
        """
        if self._custom_tools_loaded or not self.source_dir:
            return

        tools_file = self.source_dir / "tools.py"
        if not tools_file.exists():
            return

        module_name = f"agent_tools_{self.name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, tools_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Optional: let tools.py specify the tool set explicitly
                tool_names_override = getattr(module, "TOOL_NAMES", None)
                if tool_names_override:
                    self.tool_names = list(tool_names_override)

                # Optional: call register_tools if provided
                register_fn = getattr(module, "register_tools", None)
                if callable(register_fn):
                    try:
                        register_fn()
                    except TypeError as exc:
                        logger.warning(
                            "register_tools signature unexpected for %s: %s",
                            self.name,
                            exc,
                        )

                logger.info(
                    "Loaded custom tools for agent %s from %s",
                    self.name,
                    tools_file,
                )
                self._custom_tools_loaded = True
        except Exception as exc:  # pragma: no cover - defensive log only
            logger.warning(
                "Failed to load custom tools for %s from %s: %s",
                self.name,
                tools_file,
                exc,
            )

    def get_tools(self, use_cache: bool = True) -> list[dict[str, Any]]:
        """
        Get OpenAI-compatible tool schemas from shared registry.

        Args:
            use_cache: If True, return cached tools if available (default).
                       Set to False to force refresh (e.g., after tool_names change).

        Returns:
            List of {"type": "function", "function": {...}} dicts
        """
        # Return cached tools if available and caching enabled
        if use_cache and self._cached_tools is not None:
            return self._cached_tools

        from apps.artagent.backend.registries.toolstore import get_tools_for_agent, initialize_tools

        initialize_tools()
        self._load_custom_tools()
        tools = get_tools_for_agent(self.tool_names)

        # Cache the tools for future calls
        self._cached_tools = tools
        return tools

    def invalidate_tool_cache(self) -> None:
        """
        Invalidate the cached tools, forcing next get_tools() to rebuild.

        Call this when tool_names are modified at runtime.
        """
        self._cached_tools = None

    def get_tool_executor(self, tool_name: str) -> Callable | None:
        """Get the executor function for a specific tool."""
        from apps.artagent.backend.registries.toolstore import get_tool_executor, initialize_tools

        initialize_tools()
        self._load_custom_tools()
        return get_tool_executor(tool_name)

    async def execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name with the given arguments."""
        from apps.artagent.backend.registries.toolstore import execute_tool, initialize_tools

        initialize_tools()
        return await execute_tool(tool_name, args)

    # ═══════════════════════════════════════════════════════════════════
    # PROMPT RENDERING
    # ═══════════════════════════════════════════════════════════════════

    def get_prompt_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Resolve defaults and runtime bindings without rendering or executing tools."""
        import os

        # Provide sensible defaults for common template variables
        defaults = {
            "agent_name": self.name or os.getenv("AGENT_NAME", "Assistant"),
            "institution_name": os.getenv("INSTITUTION_NAME", "Contoso Bank"),
        }

        # Filter out None values from context - Jinja2 default filter only
        # works for undefined variables, not None values
        filtered_context = {}
        if context:
            for k, v in context.items():
                if v is not None and v != "None":
                    filtered_context[k] = v

        # Merge: defaults < template_vars < filtered runtime context
        return {**defaults, **self.template_vars, **filtered_context}

    def render_prompt(self, context: dict[str, Any]) -> str:
        """Render a sandboxed runtime prompt, surfacing invalid templates to the caller."""
        full_context = self.get_prompt_context(context)

        try:
            template = ImmutableSandboxedEnvironment(autoescape=False).from_string(
                self.prompt_template
            )
            return template.render(**full_context)
        except TemplateError as e:
            logger.error("Failed to render prompt for %s: %s", self.name, e)
            raise

    # ═══════════════════════════════════════════════════════════════════
    # GREETING RENDERING
    # ═══════════════════════════════════════════════════════════════════

    def _get_greeting_context(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Build context for greeting template rendering.

        Provides default values for common greeting variables from
        environment variables, with optional overrides from context.

        Note: This method filters out None values from context to ensure
        Jinja2 default filters work correctly (they only apply to undefined,
        not None values).

        Args:
            context: Optional runtime overrides

        Returns:
            Dict with agent_name, institution_name, and any overrides
        """
        import os

        # Use agent's own name as fallback for agent_name
        agent_display_name = self.name or os.getenv("AGENT_NAME", "Assistant")

        defaults = {
            "agent_name": agent_display_name,
            "institution_name": os.getenv("INSTITUTION_NAME", "Contoso Bank"),
        }

        # Filter out None values from context - Jinja2 default filter only
        # works for undefined variables, not None values
        filtered_context = {}
        if context:
            for k, v in context.items():
                if v is not None and v != "None":
                    filtered_context[k] = v

        # Merge with template_vars and filtered runtime context
        return {**defaults, **self.template_vars, **filtered_context}

    def render_greeting(self, context: dict[str, Any] | None = None) -> str | None:
        """
        Render the greeting template with context.

        Uses Jinja2 templating to render greeting with variables like:
        - {{ agent_name | default('Assistant') }}
        - {{ institution_name | default('Contoso Bank') }}

        Args:
            context: Optional runtime context overrides

        Returns:
            Rendered greeting string, or None if no greeting configured
        """
        if not self.greeting:
            return None

        try:
            template = ImmutableSandboxedEnvironment(autoescape=False).from_string(self.greeting)
            rendered = template.render(**self._get_greeting_context(context))
            return rendered.strip() or None
        except TemplateError as e:
            logger.error("Failed to render greeting for %s: %s", self.name, e)
            raise

    def render_return_greeting(self, context: dict[str, Any] | None = None) -> str | None:
        """
        Render the return greeting template with context.

        Args:
            context: Optional runtime context overrides

        Returns:
            Rendered return greeting string, or None if not configured
        """
        if not self.return_greeting:
            return None

        try:
            template = ImmutableSandboxedEnvironment(autoescape=False).from_string(
                self.return_greeting
            )
            rendered = template.render(**self._get_greeting_context(context))
            return rendered.strip() or None
        except TemplateError as e:
            logger.error("Failed to render return_greeting for %s: %s", self.name, e)
            raise

    # ═══════════════════════════════════════════════════════════════════
    # HANDOFF HELPERS
    # ═══════════════════════════════════════════════════════════════════

    def get_handoff_tools(self) -> list[str]:
        """Get list of handoff tool names this agent can call."""
        return [t for t in self.tool_names if t.startswith("handoff_")]

    def can_handoff_to(self, agent_name: str) -> bool:
        """Check if this agent has a handoff tool for the target."""
        trigger = f"handoff_{agent_name.lower()}"
        return any(trigger in t.lower() for t in self.tool_names)

    def is_handoff_target(self, tool_name: str) -> bool:
        """Check if the given tool name routes to this agent."""
        return self.handoff.trigger == tool_name

    def get_model_for_mode(self, mode: str) -> ModelConfig:
        """
        Get the appropriate model config for the given orchestration mode.

        Args:
            mode: "cascade", "media" (alias for cascade), "voicelive", or "realtime" (alias for voicelive)

        Returns:
            The mode-specific model if defined, otherwise falls back to self.model
        """
        # Normalize mode aliases
        if mode in ("cascade", "media"):
            if self.cascade_model is not None:
                return self.cascade_model
        elif mode in ("voicelive", "realtime"):
            if self.voicelive_model is not None:
                return self.voicelive_model

        # Fall back to default model
        return self.model

    def get_byom_query(self) -> dict[str, str] | None:
        """Return the VoiceLive BYOM connect() query params, or None when disabled.

        Maps the agent's ``byom`` config to ``{"profile": <mode>[,
        "foundry-resource-override": <res>]}`` for ``connect(..., query=...)``.
        Only relevant in VoiceLive mode.
        """
        if self.byom is None:
            return None
        return self.byom.to_query()

    # ═══════════════════════════════════════════════════════════════════
    # CONVENIENCE PROPERTIES
    # ═══════════════════════════════════════════════════════════════════

    @property
    def model_id(self) -> str:
        """Alias for model.deployment_id for backward compatibility."""
        return self.model.deployment_id

    @property
    def temperature(self) -> float:
        """Alias for model.temperature for backward compatibility."""
        return self.model.temperature

    @property
    def voice_name(self) -> str:
        """Alias for voice.name for backward compatibility."""
        return self.voice.name

    @property
    def handoff_trigger(self) -> str:
        """Alias for handoff.trigger for backward compatibility."""
        return self.handoff.trigger

    def __repr__(self) -> str:
        return (
            f"UnifiedAgent(name={self.name!r}, "
            f"tools={len(self.tool_names)}, "
            f"handoff_trigger={self.handoff.trigger!r})"
        )


def build_handoff_map(agents: dict[str, UnifiedAgent]) -> dict[str, str]:
    """
    Build handoff map from agent declarations.

    Each agent can declare a `handoff.trigger` which is the tool name
    that other agents use to transfer to this agent.

    Args:
        agents: Dict of agent_name → UnifiedAgent

    Returns:
        Dict of tool_name → agent_name
    """
    handoff_map: dict[str, str] = {}
    for agent in agents.values():
        if agent.handoff.trigger:
            handoff_map[agent.handoff.trigger] = agent.name
    return handoff_map


__all__ = [
    "UnifiedAgent",
    "HandoffConfig",
    "VoiceConfig",
    "ModelConfig",
    "build_handoff_map",
]
