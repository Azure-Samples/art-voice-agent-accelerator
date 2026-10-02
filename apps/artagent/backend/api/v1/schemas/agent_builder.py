"""Agent Builder transport schemas, shared with scenario draft authoring."""

from __future__ import annotations

from typing import Any, Literal

from apps.artagent.backend.registries.agentstore.base import (
    VOICELIVE_BYOM_MODES,
    HandoffConfig,
    ModelConfig,
    SpeechConfig,
    UnifiedAgent,
    VoiceConfig,
    VoiceLiveBYOMConfig,
    normalize_transcription_model,
    validate_mai_customization,
)
from apps.artagent.backend.registries.definitions import (
    TURN_DETECTION_ALIASES,
    definition_fields,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    field_validator,
    model_serializer,
    model_validator,
)


class ModelConfigSchema(
    create_model("ModelDefinitionSchema", __base__=BaseModel, **definition_fields(ModelConfig))
):
    """Model configuration schema."""

    name: str | None = None
    temperature: float | None = Field(default=ModelConfig.temperature, ge=0.0, le=2.0)
    top_p: float | None = Field(default=ModelConfig.top_p, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=ModelConfig.max_tokens, ge=1, le=16384)
    verbosity: int = Field(default=ModelConfig.verbosity, ge=0, le=2)
    min_p: float | None = Field(default=None, ge=0.0, le=1.0)
    typical_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=32768)


class ByomConfigSchema(
    create_model(
        "ByomDefinitionSchema", __base__=BaseModel, **definition_fields(VoiceLiveBYOMConfig)
    )
):
    """Opt-in Voice Live Bring Your Own Model profile."""

    mode: str | None = Field(
        default=None,
        description="A supported Voice Live BYOM profile, or None for managed VoiceLive.",
    )

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if value not in VOICELIVE_BYOM_MODES:
            raise ValueError(
                f"Invalid BYOM mode '{value}'. Must be one of: {', '.join(VOICELIVE_BYOM_MODES)}"
            )
        return value


class VoiceLiveModelConfigSchema(ModelConfigSchema):
    """VoiceLive generation bounds from the RequestSession service contract."""

    temperature: float | None = Field(default=0.7, ge=0.0, le=1.0)


class VoiceConfigSchema(
    create_model("VoiceDefinitionSchema", __base__=BaseModel, **definition_fields(VoiceConfig))
):
    """Voice configuration schema."""

    name: str = "en-US-AvaMultilingualNeural"


class SpeechConfigSchema(
    create_model("SpeechDefinitionSchema", __base__=BaseModel, **definition_fields(SpeechConfig))
):
    """Speech recognition (STT) configuration schema."""

    transcription_model: Literal["azure-speech", "mai-transcribe", "mai-transcribe-2"] = (
        SpeechConfig.transcription_model
    )
    vad_silence_timeout_ms: int = Field(
        default=SpeechConfig.vad_silence_timeout_ms, ge=100, le=5000
    )
    speaker_count_hint: int = Field(default=SpeechConfig.speaker_count_hint, ge=1, le=10)

    @field_validator("transcription_model", mode="before")
    @classmethod
    def _normalize_model(cls, value: Any) -> Any:
        return normalize_transcription_model(value) if isinstance(value, str) else value

    @model_validator(mode="before")
    @classmethod
    def _reject_mai_customization(cls, value: Any) -> Any:
        if isinstance(value, dict):
            model = value.get("transcription_model", SpeechConfig.transcription_model)
            if isinstance(model, str):
                validate_mai_customization(model, value)
        return value


class SessionConfigSchema(BaseModel):
    """VoiceLive session configuration schema."""

    model_config = ConfigDict(extra="allow")
    modalities: list[str] = Field(default_factory=lambda: ["TEXT", "AUDIO"])
    input_audio_format: str = "PCM16"
    output_audio_format: str = "PCM16"
    turn_detection_type: str = "azure_semantic_vad"
    turn_detection_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    silence_duration_ms: int = Field(default=700, ge=100, le=3000)
    prefix_padding_ms: int = Field(default=240, ge=0, le=1000)
    turn_detection: dict[str, Any] | None = None
    tool_choice: str = "auto"
    input_audio_transcription_settings: dict[str, Any] | None = None

    @field_validator("input_audio_transcription_settings")
    @classmethod
    def _normalize_transcription(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and value.get("model") is not None:
            return {**value, "model": normalize_transcription_model(value["model"])}
        return value

    @model_validator(mode="before")
    @classmethod
    def _accept_nested_turn_detection(cls, data: Any) -> Any:
        """Accept the persisted SDK shape without replacing explicit nulls or empty settings."""
        if not isinstance(data, dict):
            return data
        turn_detection = data.get("turn_detection")
        if isinstance(turn_detection, dict):
            data = dict(data)
            for field_name, nested_name in TURN_DETECTION_ALIASES.items():
                if field_name not in data and nested_name in turn_detection:
                    data[field_name] = turn_detection[nested_name]
        return data

    @model_serializer(mode="wrap")
    def _preserve_turn_detection_omission(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if "turn_detection" not in self.model_fields_set:
            data.pop("turn_detection", None)
        return data


class AgentHandoffConfigSchema(
    create_model(
        "AgentHandoffDefinitionSchema", __base__=BaseModel, **definition_fields(HandoffConfig)
    )
):
    """The agent's incoming handoff identity, not scenario routing."""


class DynamicAgentConfig(
    create_model(
        "AgentDefinitionSchema",
        __base__=BaseModel,
        **{
            {"tool_names": "tools", "prompt_template": "prompt"}.get(name, name): definition
            for name, definition in definition_fields(UnifiedAgent).items()
            if name != "source_dir"
        },
    )
):
    """Configuration for creating a dynamic agent in either orchestration mode."""

    name: str = Field(..., min_length=1, max_length=64, description="Agent display name")
    description: str = Field(default=UnifiedAgent.description, max_length=512)
    greeting: str = Field(default=UnifiedAgent.greeting, max_length=1024)
    return_greeting: str = Field(default=UnifiedAgent.return_greeting, max_length=1024)
    handoff_trigger: str = Field(default="", max_length=128)
    prompt: str = Field(..., min_length=10, description="System prompt for the agent")
    cascade_model: ModelConfigSchema | None = None
    voicelive_model: VoiceLiveModelConfigSchema | None = None
    byom: ByomConfigSchema | None = None
    model: ModelConfigSchema | None = None
    voice: VoiceConfigSchema | None = None
    speech: SpeechConfigSchema | None = None
    session: SessionConfigSchema | None = None
    template_vars: dict[str, Any] | None = None
    handoff: AgentHandoffConfigSchema | None = None

    @model_validator(mode="after")
    def _apply_explicit_handoff_alias(self) -> DynamicAgentConfig:
        if "handoff_trigger" in self.model_fields_set:
            self.handoff_trigger = self.handoff_trigger.strip()
            if self.handoff is not None:
                self.handoff = self.handoff.model_copy(update={"trigger": self.handoff_trigger})
        return self

    @model_serializer(mode="wrap")
    def _preserve_edit_omission(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        for name in ("cascade_model", "voicelive_model", "handoff_trigger"):
            if name not in self.model_fields_set:
                data.pop(name, None)
        return data
