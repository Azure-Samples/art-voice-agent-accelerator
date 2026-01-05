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
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Template
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
        if not data:
            return cls()

        return cls(
            trigger=data.get("trigger", ""),
            is_entry_point=data.get("is_entry_point", False),
        )


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
        if not data:
            return cls()
        return cls(
            name=data.get("name", cls.name),
            type=data.get("type", cls.type),
            style=data.get("style", cls.style),
            rate=data.get("rate", cls.rate),
            pitch=data.get("pitch", cls.pitch),
            endpoint_id=data.get("endpoint_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "name": self.name,
            "type": self.type,
            "style": self.style,
            "rate": self.rate,
            "pitch": self.pitch,
            "endpoint_id": self.endpoint_id,
        }


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelConfig:
        """Create ModelConfig from dict."""
        if not data:
            return cls()
        deployment_id = data.get("deployment_id", data.get("name", cls.deployment_id))

        # Parse legacy parameters (allow None)
        temperature = data.get("temperature")
        if temperature is not None:
            temperature = float(temperature)
        else:
            temperature = cls.temperature

        top_p = data.get("top_p")
        if top_p is not None:
            top_p = float(top_p)
        else:
            top_p = cls.top_p

        max_tokens = data.get("max_tokens")
        if max_tokens is not None:
            max_tokens = int(max_tokens)
        else:
            max_tokens = cls.max_tokens

        # Parse new parameters (default to None if not present)
        min_p = data.get("min_p")
        if min_p is not None:
            min_p = float(min_p)

        typical_p = data.get("typical_p")
        if typical_p is not None:
            typical_p = float(typical_p)

        max_completion_tokens = data.get("max_completion_tokens")
        if max_completion_tokens is not None:
            max_completion_tokens = int(max_completion_tokens)

        # Parse verbosity parameter (default to 0 for real-time performance)
        verbosity = data.get("verbosity", 0)
        if verbosity is not None:
            verbosity = int(verbosity)

        # Parse store parameter
        store = data.get("store")
        if store is not None:
            store = bool(store)

        # Create instance
        instance = cls(
            deployment_id=deployment_id,
            name=data.get("name", deployment_id),
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            min_p=min_p,
            typical_p=typical_p,
            reasoning_effort=data.get("reasoning_effort"),
            include_reasoning=bool(data.get("include_reasoning", False)),
            max_completion_tokens=max_completion_tokens,
            verbosity=verbosity,
            store=store,
            metadata=data.get("metadata"),
            response_format=data.get("response_format"),
            endpoint_preference=data.get("endpoint_preference", "auto"),
            api_version=data.get("api_version", "v1"),
            model_family=data.get("model_family"),
        )

        # Auto-detect model family if not provided
        if not instance.model_family:
            instance.model_family = instance._detect_model_family()

        return instance

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "deployment_id": self.deployment_id,
            "name": self.name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }

        # Add new parameters only if they're set
        if self.min_p is not None:
            result["min_p"] = self.min_p
        if self.typical_p is not None:
            result["typical_p"] = self.typical_p
        if self.reasoning_effort is not None:
            result["reasoning_effort"] = self.reasoning_effort
        if self.include_reasoning:
            result["include_reasoning"] = self.include_reasoning
        if self.max_completion_tokens is not None:
            result["max_completion_tokens"] = self.max_completion_tokens
        if self.verbosity != 0:  # Only serialize if non-default
            result["verbosity"] = self.verbosity
        if self.store is not None:
            result["store"] = self.store
        if self.metadata is not None:
            result["metadata"] = self.metadata
        if self.response_format is not None:
            result["response_format"] = self.response_format
        if self.endpoint_preference != "auto":
            result["endpoint_preference"] = self.endpoint_preference
        if self.api_version:
            result["api_version"] = self.api_version
        if self.model_family:
            result["model_family"] = self.model_family

        return result


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

    # Default languages constant for from_dict
    _DEFAULT_LANGS: list[str] = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self):
        """Initialize default languages constant."""
        object.__setattr__(self, "_DEFAULT_LANGS", ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeechConfig:
        """Create SpeechConfig from dict."""
        if not data:
            return cls()
        default_langs = ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT"]
        return cls(
            vad_silence_timeout_ms=int(data.get("vad_silence_timeout_ms", 800)),
            use_semantic_segmentation=bool(data.get("use_semantic_segmentation", False)),
            candidate_languages=data.get("candidate_languages", default_langs),
            enable_diarization=bool(data.get("enable_diarization", False)),
            speaker_count_hint=int(data.get("speaker_count_hint", 2)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "vad_silence_timeout_ms": self.vad_silence_timeout_ms,
            "use_semantic_segmentation": self.use_semantic_segmentation,
            "candidate_languages": self.candidate_languages,
            "enable_diarization": self.enable_diarization,
            "speaker_count_hint": self.speaker_count_hint,
        }


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

    def render_prompt(self, context: dict[str, Any]) -> str:
        """
        Render prompt template with runtime context.

        Args:
            context: Runtime context (caller_name, customer_intelligence, etc.)

        Returns:
            Rendered prompt string
        """
        import os

        # Provide sensible defaults for common template variables
        defaults = {
            "agent_name": self.name or os.getenv("AGENT_NAME", "Erica"),
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
        full_context = {**defaults, **self.template_vars, **filtered_context}

        try:
            template = Template(self.prompt_template)
            return template.render(**full_context)
        except Exception as e:
            logger.error("Failed to render prompt for %s: %s", self.name, e)
            return self.prompt_template

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
        agent_display_name = self.name or os.getenv("AGENT_NAME", "Erica")

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
        - {{ agent_name | default('Erica') }}
        - {{ institution_name | default('Contoso Bank') }}

        Args:
            context: Optional runtime context overrides

        Returns:
            Rendered greeting string, or None if no greeting configured
        """
        if not self.greeting:
            return None

        try:
            template = Template(self.greeting)
            rendered = template.render(**self._get_greeting_context(context))
            return rendered.strip() or None
        except Exception as e:
            logger.error("Failed to render greeting for %s: %s", self.name, e)
            return self.greeting.strip() or None

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
            template = Template(self.return_greeting)
            rendered = template.render(**self._get_greeting_context(context))
            return rendered.strip() or None
        except Exception as e:
            logger.error("Failed to render return_greeting for %s: %s", self.name, e)
            return self.return_greeting.strip() or None

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

    # ═══════════════════════════════════════════════════════════════════
    # VOICELIVE SDK METHODS
    # ═══════════════════════════════════════════════════════════════════
    # These methods support the VoiceLive orchestrator directly without
    # needing a separate adapter layer. They are no-ops if the SDK is
    # not available.

    def build_voicelive_tools(self) -> list[Any]:
        """
        Build VoiceLive FunctionTool objects from this agent's tool schemas.

        Returns:
            List of FunctionTool objects for VoiceLive SDK, or empty list
            if VoiceLive SDK is not available.
        """
        try:
            from azure.ai.voicelive.models import FunctionTool
        except ImportError:
            return []

        tools = []
        tool_schemas = self.get_tools()

        for schema in tool_schemas:
            if schema.get("type") != "function":
                continue

            func = schema.get("function", {})
            tools.append(
                FunctionTool(
                    name=func.get("name", ""),
                    description=func.get("description", ""),
                    parameters=func.get("parameters", {}),
                )
            )

        return tools

    def _build_voicelive_tools_with_handoffs(self, session_id: str | None = None) -> list[Any]:
        """
        Build VoiceLive FunctionTool objects with centralized handoff tool.

        This method:
        1. Filters OUT explicit handoff tools (e.g., handoff_concierge)
        2. Auto-injects the generic `handoff_to_agent` tool when needed

        The scenario edges define handoff routing and conditions, so we only
        need the single centralized `handoff_to_agent` tool.

        Args:
            session_id: Session ID to look up scenario configuration

        Returns:
            List of FunctionTool objects for VoiceLive SDK
        """
        try:
            from azure.ai.voicelive.models import FunctionTool
        except ImportError:
            return []

        from apps.artagent.backend.registries.toolstore.registry import is_handoff_tool

        # Get base tool schemas and filter out explicit handoff tools
        tool_schemas = self.get_tools()
        filtered_schemas = []
        for schema in tool_schemas:
            if schema.get("type") != "function":
                continue
            func_name = schema.get("function", {}).get("name", "")
            if func_name == "handoff_to_agent":
                filtered_schemas.append(schema)
            elif is_handoff_tool(func_name):
                logger.debug(
                    "VoiceLive: Filtering explicit handoff tool | tool=%s agent=%s",
                    func_name,
                    self.name,
                )
            else:
                filtered_schemas.append(schema)

        tool_schemas = filtered_schemas
        tool_names = {s.get("function", {}).get("name") for s in tool_schemas}

        # Check if we need to inject handoff_to_agent
        if "handoff_to_agent" not in tool_names and session_id:
            try:
                from apps.artagent.backend.voice.shared.config_resolver import resolve_orchestrator_config

                # Use already-resolved scenario (supports both file-based and session-scoped)
                config = resolve_orchestrator_config(session_id=session_id)
                scenario = config.scenario
                if scenario:
                    should_add = False
                    if scenario.generic_handoff.enabled:
                        should_add = True
                        logger.debug(
                            "VoiceLive: Auto-adding handoff_to_agent | agent=%s reason=generic_handoff_enabled",
                            self.name,
                        )
                    else:
                        outgoing = scenario.get_outgoing_handoffs(self.name)
                        if outgoing:
                            should_add = True
                            logger.debug(
                                "VoiceLive: Auto-adding handoff_to_agent | agent=%s reason=has_outgoing_handoffs count=%d targets=%s",
                                self.name,
                                len(outgoing),
                                [h.to_agent for h in outgoing],
                            )

                    if should_add:
                        from apps.artagent.backend.registries.toolstore import get_tools_for_agent, initialize_tools
                        initialize_tools()
                        handoff_tool_schemas = get_tools_for_agent(["handoff_to_agent"])
                        tool_schemas = list(tool_schemas) + handoff_tool_schemas
                        logger.info(
                            "VoiceLive: Added handoff_to_agent tool | agent=%s scenario=%s",
                            self.name,
                            config.scenario_name,
                        )

            except Exception as e:
                logger.debug("Failed to check scenario for handoff tool injection: %s", e)

        # Convert to FunctionTool objects
        tools = []
        for schema in tool_schemas:
            func = schema.get("function", {})
            tools.append(
                FunctionTool(
                    name=func.get("name", ""),
                    description=func.get("description", ""),
                    parameters=func.get("parameters", {}),
                )
            )

        return tools

    def build_voicelive_voice(self) -> Any | None:
        """
        Build VoiceLive voice configuration from this agent's voice settings.

        Returns:
            AzureStandardVoice or similar object, or None if SDK not available.
        """
        try:
            from azure.ai.voicelive.models import AzureStandardVoice
            try:
                from azure.ai.voicelive.models import AzureCustomVoice
            except ImportError:
                AzureCustomVoice = None
        except ImportError:
            return None

        if not self.voice.name:
            return None

        voice_type = self.voice.type.lower().strip()

        if voice_type in {"azure-custom", "azure_custom"}:
            if AzureCustomVoice and self.voice.endpoint_id:
                return AzureCustomVoice(
                    name=self.voice.name,
                    endpoint_id=self.voice.endpoint_id,
                )
            return AzureStandardVoice(name=self.voice.name)

        if voice_type in {"azure-standard", "azure_standard", "azure"}:
            optionals = {}
            for key in ("style", "pitch", "rate"):
                val = getattr(self.voice, key, None)
                if val is not None and val != "+0%":
                    optionals[key] = val
            return AzureStandardVoice(name=self.voice.name, **optionals)

        # Default to standard voice
        return AzureStandardVoice(name=self.voice.name)

    def build_voicelive_vad(self) -> Any | None:
        """
        Build VoiceLive VAD (turn detection) configuration.

        Returns:
            TurnDetection object (AzureSemanticVad or ServerVad), or None.
        """
        try:
            from azure.ai.voicelive.models import AzureSemanticVad, ServerVad
        except ImportError:
            return None

        cfg = self.session.get("turn_detection") if self.session else None
        if not cfg:
            return None

        vad_type = (cfg.get("type") or "semantic").lower()

        common_kwargs: dict[str, Any] = {}
        if "threshold" in cfg:
            common_kwargs["threshold"] = float(cfg["threshold"])
        if "prefix_padding_ms" in cfg:
            common_kwargs["prefix_padding_ms"] = int(cfg["prefix_padding_ms"])
        if "silence_duration_ms" in cfg:
            common_kwargs["silence_duration_ms"] = int(cfg["silence_duration_ms"])

        if vad_type in ("semantic", "azure_semantic", "azure_semantic_vad"):
            return AzureSemanticVad(**common_kwargs)
        elif vad_type in ("server", "server_vad"):
            return ServerVad(**common_kwargs)

        return AzureSemanticVad(**common_kwargs)

    def get_voicelive_modalities(self) -> list[Any]:
        """
        Get VoiceLive modality enums from session config.

        Returns:
            List of Modality enums (TEXT, AUDIO), or empty list if SDK unavailable.
        """
        try:
            from azure.ai.voicelive.models import Modality
        except ImportError:
            return []

        values = self.session.get("modalities") if self.session else None
        vals = [v.lower() for v in (values or ["TEXT", "AUDIO"])]
        out = []
        for v in vals:
            if v in ("text", "TEXT"):
                out.append(Modality.TEXT)
            elif v in ("audio", "AUDIO"):
                out.append(Modality.AUDIO)
        return out

    def get_voicelive_audio_formats(self) -> tuple[Any | None, Any | None]:
        """
        Get input and output audio format enums for VoiceLive.

        Returns:
            Tuple of (InputAudioFormat, OutputAudioFormat), or (None, None).
        """
        try:
            from azure.ai.voicelive.models import InputAudioFormat, OutputAudioFormat
        except ImportError:
            return None, None

        in_fmt_str = (self.session.get("input_audio_format") or "PCM16").lower()
        out_fmt_str = (self.session.get("output_audio_format") or "PCM16").lower()

        in_fmt = InputAudioFormat.PCM16 if in_fmt_str == "pcm16" else InputAudioFormat.PCM16
        out_fmt = OutputAudioFormat.PCM16 if out_fmt_str == "pcm16" else OutputAudioFormat.PCM16

        return in_fmt, out_fmt

    async def apply_voicelive_session(
        self,
        conn,
        *,
        system_vars: dict[str, Any] | None = None,
        say: str | None = None,
        session_id: str | None = None,
        call_connection_id: str | None = None,
    ) -> None:
        """
        Apply this agent's configuration to a VoiceLive session.

        Updates voice, VAD settings, instructions, and tools on the connection.
        Automatically injects the handoff_to_agent tool when the scenario has
        generic handoffs enabled or when the agent has outgoing edges defined.

        Args:
            conn: VoiceLive connection object
            system_vars: Runtime variables for prompt rendering
            say: Optional greeting text to trigger after session update
            session_id: Session ID for tracing
            call_connection_id: Call connection ID for tracing
        """
        try:
            from azure.ai.voicelive.models import (
                AudioInputTranscriptionOptions,
                RequestSession,
            )
        except ImportError:
            logger.error("VoiceLive SDK not available, cannot apply session")
            return

        from opentelemetry import trace
        from opentelemetry.trace import SpanKind, Status, StatusCode

        tracer = trace.get_tracer(__name__)

        with tracer.start_as_current_span(
            f"invoke_agent {self.name}",
            kind=SpanKind.INTERNAL,
            attributes={
                "component": "voicelive",
                "ai.session.id": session_id or "",
                "gen_ai.agent.name": self.name,
                "gen_ai.agent.description": self.description or "",
            },
        ) as span:
            # Render instructions
            system_vars = system_vars or {}
            system_vars.setdefault("active_agent", self.name)
            instructions = self.render_prompt(system_vars)

            # Build session components
            voice_payload = self.build_voicelive_voice()
            vad = self.build_voicelive_vad()
            modalities = self.get_voicelive_modalities()
            in_fmt, out_fmt = self.get_voicelive_audio_formats()
            tools = self._build_voicelive_tools_with_handoffs(session_id)

            logger.debug(
                "[%s] Applying session | voice=%s",
                self.name,
                getattr(voice_payload, "name", None) if voice_payload else None,
            )

            # Build transcription settings
            transcription_cfg = self.session.get("input_audio_transcription_settings") or {}
            transcription_kwargs: dict[str, Any] = {}
            if transcription_cfg.get("model"):
                transcription_kwargs["model"] = transcription_cfg["model"]
            if transcription_cfg.get("language"):
                transcription_kwargs["language"] = transcription_cfg["language"]

            input_audio_transcription = (
                AudioInputTranscriptionOptions(**transcription_kwargs)
                if transcription_kwargs
                else None
            )

            # Build session update kwargs
            kwargs: dict[str, Any] = dict(
                modalities=modalities,
                instructions=instructions,
                input_audio_format=in_fmt,
                output_audio_format=out_fmt,
                turn_detection=vad,
            )

            if input_audio_transcription:
                kwargs["input_audio_transcription"] = input_audio_transcription

            if voice_payload:
                kwargs["voice"] = voice_payload

            if tools:
                kwargs["tools"] = tools
                tool_choice = self.session.get("tool_choice", "auto") if self.session else "auto"
                if tool_choice:
                    kwargs["tool_choice"] = tool_choice

            # Apply session
            session_payload = RequestSession(**kwargs)
            await conn.session.update(session=session_payload)

            logger.info("[%s] Session updated successfully", self.name)
            span.set_status(Status(StatusCode.OK))

            # Trigger greeting if provided
            if say:
                logger.info(
                    "[%s] Triggering greeting: %s",
                    self.name,
                    say[:50] + "..." if len(say) > 50 else say,
                )
                await self.trigger_voicelive_response(conn, say=say)

    async def trigger_voicelive_response(
        self,
        conn,
        *,
        say: str | None = None,
        cancel_active: bool = True,
    ) -> None:
        """
        Trigger a response from the agent on a VoiceLive connection.

        Args:
            conn: VoiceLive connection object
            say: Text for the agent to say verbatim
            cancel_active: If True, cancel any active response first
        """
        try:
            from azure.ai.voicelive.models import (
                ClientEventResponseCreate,
                ResponseCreateParams,
            )
        except ImportError:
            return

        if not say:
            return

        # Cancel any active response first to avoid conflicts
        if cancel_active:
            try:
                await conn.response.cancel()
            except Exception:
                pass  # No active response to cancel

        # Create response with explicit instruction to say the greeting verbatim
        verbatim_instruction = (
            f"Say exactly the following greeting to the user, word for word. "
            f"Do not add anything before or after. Do not modify the wording:\n\n"
            f'"{say}"'
        )

        try:
            await conn.send(
                ClientEventResponseCreate(
                    response=ResponseCreateParams(
                        instructions=verbatim_instruction,
                    )
                )
            )
            logger.debug("[%s] Triggered verbatim greeting response", self.name)
        except Exception as e:
            logger.warning("trigger_voicelive_response failed: %s", e)

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
