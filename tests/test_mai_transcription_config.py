"""MAI authoring, persistence and VoiceLive runtime compatibility contracts."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from apps.artagent.backend.api.v1.endpoints.agent_builder import (
    build_session_agent,
    get_default_config,
)
from apps.artagent.backend.api.v1.schemas.agent_builder import (
    DynamicAgentConfig,
    SessionConfigSchema,
    SpeechConfigSchema,
)
from apps.artagent.backend.registries.agentstore.base import (
    DEFAULT_TRANSCRIPTION_MODEL,
    MAI_VOICELIVE_API_VERSION,
    ModelConfig,
    SpeechConfig,
    UnifiedAgent,
    VoiceConfig,
    VoiceLiveBYOMConfig,
    byom_profile_model_conflict,
    is_managed_voicelive_model,
    validate_voicelive_transcription,
)
from apps.artagent.backend.registries.agentstore.loader import load_agent, load_defaults
from apps.artagent.backend.src.orchestration import session_agents
from apps.artagent.backend.src.orchestration.session_memory import prime_session_definitions
from apps.artagent.backend.voice.voicelive import handler as vl_handler
from apps.artagent.backend.voice.voicelive import session as voicelive_session
from fastapi.websockets import WebSocketState
from src.redis.manager import merge_session_snapshot


def test_cascade_defaults_to_explicit_mai_2_and_preserves_azure_override() -> None:
    assert DEFAULT_TRANSCRIPTION_MODEL == "mai-transcribe-2"
    legacy = {
        "vad_silence_timeout_ms": 800,
        "use_semantic_segmentation": False,
        "candidate_languages": ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT"],
        "enable_diarization": False,
        "speaker_count_hint": 2,
    }
    assert SpeechConfigSchema().transcription_model == "mai-transcribe-2"
    expected = {**legacy, "transcription_model": "mai-transcribe-2"}
    assert SpeechConfig().to_dict() == expected
    assert SpeechConfig.from_dict(legacy).to_dict() == expected
    azure = {**legacy, "transcription_model": "azure-speech"}
    assert SpeechConfig.from_dict(azure).to_dict() == azure
    assert SpeechConfigSchema.model_validate(azure).model_dump() == azure


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("mai-transcribe", "mai-transcribe"),
        ("mai-transcribe-1.5", "mai-transcribe"),
        ("mai-transcribe-2", "mai-transcribe-2"),
        (" MAI-Transcribe-2 ", "mai-transcribe-2"),
    ],
)
def test_mai_alias_roundtrip_and_unedited_fields(alias: str, expected: str) -> None:
    config = DynamicAgentConfig(
        name="MAI agent",
        prompt="You are a helpful banking agent.",
        cascade_model={"deployment_id": "local-llm", "temperature": 0.42},
        voicelive_model={"deployment_id": "gpt-4.1"},
        voice={"name": "en-US-Harper:MAI-Voice-2-Flash", "type": "azure-standard"},
        speech={
            "transcription_model": alias,
            "vad_silence_timeout_ms": 1300,
            "use_semantic_segmentation": True,
            "candidate_languages": ["it-IT"],
            "speaker_count_hint": 3,
        },
        session={"input_audio_transcription_settings": {"model": alias, "language": "it"}},
    )
    agent = build_session_agent(config, "mai-roundtrip", created_at=10.0)
    restored = session_agents._deserialize_agent(
        json.loads(json.dumps(session_agents._serialize_agent(agent)))
    )
    assert restored.speech.to_dict() == {
        "transcription_model": expected,
        "vad_silence_timeout_ms": 1300,
        "use_semantic_segmentation": True,
        "candidate_languages": ["it-IT"],
        "speaker_count_hint": 3,
        "enable_diarization": False,
    }
    assert restored.cascade_model.deployment_id == "local-llm"
    assert restored.cascade_model.temperature == 0.42
    assert restored.voicelive_model.deployment_id == "gpt-4.1"
    assert restored.voice.name == "en-US-Harper:MAI-Voice-2-Flash"
    assert restored.voice.type == "azure-standard"
    assert restored.session["input_audio_transcription_settings"] == {
        "model": expected,
        "language": "it",
    }
    assert SpeechConfig.from_dict({"transcription_model": alias}).transcription_model == expected


@pytest.mark.asyncio
async def test_authoring_defaults_publish_mai_2_and_profile_aware_voicelive() -> None:
    defaults = (await get_default_config())["defaults"]
    assert defaults["speech"]["transcription_model"] == "mai-transcribe-2"
    assert defaults["session"]["input_audio_transcription_settings"]["model"] == "auto"


@pytest.mark.parametrize("speech", [None, {}, {"vad_silence_timeout_ms": 1200}])
def test_dynamic_agent_omitted_provider_survives_serialization(speech) -> None:
    agent = build_session_agent(
        DynamicAgentConfig(name="Default", prompt="You are a helpful assistant.", speech=speech),
        "mai-default",
        created_at=10.0,
    )
    restored = session_agents._deserialize_agent(
        json.loads(json.dumps(session_agents._serialize_agent(agent)))
    )
    assert restored.speech.transcription_model == "mai-transcribe-2"
    assert restored.speech.to_dict()["transcription_model"] == "mai-transcribe-2"


@pytest.mark.parametrize(
    "profile", ["byom-azure-openai-chat-completion", "byom-foundry-anthropic-messages"]
)
@pytest.mark.parametrize("settings", [None, {}, {"language": "en"}, {"model": "auto"}])
def test_text_byom_defaults_to_mai_2_without_mutating_settings(profile, settings) -> None:
    original = copy.deepcopy(settings)
    assert validate_voicelive_transcription(
        settings, model_name="customer-deployment", byom_profile=profile
    ) == {**(settings or {}), "model": "mai-transcribe-2"}
    assert settings == original


@pytest.mark.parametrize(
    "model,profile",
    [("gpt-realtime", None), ("gpt-4.1", None), ("gpt-realtime", "byom-azure-openai-realtime")],
)
def test_non_text_byom_defaults_preserve_previous_behavior(model, profile) -> None:
    assert validate_voicelive_transcription(None, model_name=model, byom_profile=profile) == {}
    assert validate_voicelive_transcription(
        {"model": "auto", "language": "en"}, model_name=model, byom_profile=profile
    ) == {"model": "azure-speech", "language": "en"}


@pytest.mark.parametrize("model", ["azure-speech", "mai-transcribe", "whisper-1"])
def test_text_byom_explicit_provider_wins_over_default(model) -> None:
    settings = {"model": model, "language": "en"}
    assert (
        validate_voicelive_transcription(
            settings,
            model_name="customer-deployment",
            byom_profile="byom-azure-openai-chat-completion",
        )
        == settings
    )


@pytest.mark.parametrize("model", [None, "azure-speech"])
def test_yaml_byom_inheritance_keeps_auto_distinct_from_explicit_override(tmp_path, model) -> None:
    agent_file = tmp_path / "agent.yaml"
    agent_file.write_text(
        "name: Default\n"
        "byom:\n  mode: byom-azure-openai-chat-completion\n"
        "voicelive_model:\n  deployment_id: customer-deployment\n"
        + (
            f"session:\n  input_audio_transcription_settings:\n    model: {model}\n"
            if model
            else ""
        ),
        encoding="utf-8",
    )
    agent = load_agent(agent_file, load_defaults())
    assert agent.speech.transcription_model == "mai-transcribe-2"
    settings = validate_voicelive_transcription(
        agent.session["input_audio_transcription_settings"],
        model_name=agent.voicelive_model.deployment_id,
        byom_profile=agent.byom.mode,
    )
    assert settings["model"] == (model or "mai-transcribe-2")


@pytest.mark.parametrize("field", ["custom_speech", "phrase_list"])
def test_default_mai_does_not_silently_drop_azure_customizations(field) -> None:
    settings = {field: ["retained"]}
    with pytest.raises(ValueError, match=f"does not support {field}"):
        SpeechConfigSchema.model_validate(settings)
    with pytest.raises(ValueError, match=f"does not support {field}"):
        SpeechConfig.from_dict(settings)
    with pytest.raises(ValueError, match=f"does not support {field}"):
        validate_voicelive_transcription(
            settings, model_name="customer-chat", byom_profile="byom-azure-openai-chat-completion"
        )


def test_unknown_cascade_provider_is_not_silently_ignored() -> None:
    with pytest.raises(ValueError, match="transcription_model"):
        SpeechConfigSchema(transcription_model="pretend-mai-sdk")


@pytest.mark.parametrize("model", [1, {"name": "mai-transcribe-2"}, ["mai-transcribe-2"]])
def test_invalid_voicelive_model_shape_is_rejected(model) -> None:
    with pytest.raises(ValueError, match="must be a string"):
        SessionConfigSchema(input_audio_transcription_settings={"model": model})
    with pytest.raises(ValueError, match="must be a string"):
        validate_voicelive_transcription({"model": model}, model_name="gpt-4.1")


@pytest.mark.parametrize("field", ["custom_speech", "phrase_list"])
def test_raw_cascade_mai_customization_is_rejected_before_schema_drops_unknown_fields(
    field,
) -> None:
    settings = {"transcription_model": "mai-transcribe", field: ["retained"]}
    with pytest.raises(ValueError, match=f"does not support {field}"):
        SpeechConfigSchema.model_validate(settings)
    with pytest.raises(ValueError, match=f"does not support {field}"):
        SpeechConfig.from_dict(settings)


@pytest.mark.parametrize(
    "model,byom,transcription",
    [
        ("my-deployment", "byom-azure-openai-chat-completion", None),
        ("my-deployment", "byom-foundry-anthropic-messages", "mai-transcribe"),
        ("gpt-4.1", None, "mai-transcribe"),
        ("gpt-realtime", None, "mai-transcribe"),
    ],
)
def test_opt_in_preserves_explicit_legacy_host_model(model, byom, transcription) -> None:
    config = DynamicAgentConfig(
        name="Legacy host",
        prompt="Use the explicitly selected model without replacing it.",
        model={"deployment_id": model},
        byom={"mode": byom} if byom else None,
        session=(
            {"input_audio_transcription_settings": {"model": transcription}}
            if transcription
            else None
        ),
    )
    agent = build_session_agent(config, "legacy-host", created_at=10.0)
    assert agent.voicelive_model.deployment_id == model
    assert (agent.byom.mode if agent.byom else None) == byom


def test_saving_cascade_does_not_validate_unused_old_voicelive_config() -> None:
    config = DynamicAgentConfig(
        name="Cascade agent",
        prompt="You are a helpful banking agent.",
        speech={"transcription_model": "azure-speech"},
        voicelive_model={"deployment_id": "gpt-realtime"},
        session={
            "input_audio_transcription_settings": {
                "model": "mai-transcribe-1.5",
                "phrase_list": ["Contoso"],
                "custom_speech": {"en-US": "existing-model"},
            }
        },
    )
    agent = build_session_agent(config, "unused-voicelive", created_at=10.0)
    assert agent.speech.transcription_model == "azure-speech"
    assert agent.session["input_audio_transcription_settings"]["phrase_list"] == ["Contoso"]
    assert agent.voicelive_model.deployment_id == "gpt-realtime"
    with pytest.raises(ValueError, match="custom_speech, phrase_list"):
        validate_voicelive_transcription(
            agent.session["input_audio_transcription_settings"], model_name="gpt-realtime"
        )


@pytest.mark.asyncio
async def test_mai_survives_actual_memo_redis_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "mai-worker-reload"
    storage: dict[str, dict] = {}

    async def store(key, data, **kwargs):
        storage[key] = merge_session_snapshot(storage.get(key, {}), data, **kwargs)
        data.clear()
        data.update(storage[key])
        return True

    redis = SimpleNamespace(
        get_session_data=lambda key: dict(storage.get(key, {})),
        get_session_data_async=AsyncMock(
            side_effect=lambda key, **kwargs: dict(storage.get(key, {}))
        ),
        store_session_data_async=store,
    )
    monkeypatch.setattr(session_agents, "_redis_manager", redis)
    monkeypatch.setattr(session_agents, "_adapter_update_callback", None)
    agent = UnifiedAgent(name="Persisted", speech=SpeechConfig())
    session_agents.set_session_agent(session_id, agent)
    await session_agents.persist_session_agents_to_redis(session_id, raise_on_failure=True)
    session_agents._session_agents.pop(session_id, None)
    session_agents._session_load_times.pop(session_id, None)
    session_agents._persisted_agent_data.pop(session_id, None)
    try:
        await prime_session_definitions(session_id)
        restored = session_agents.get_session_agent(session_id, "Persisted")
        assert restored.speech.transcription_model == "mai-transcribe-2"
        assert restored is not agent
    finally:
        session_agents._session_agents.pop(session_id, None)
        session_agents._session_load_times.pop(session_id, None)
        session_agents._persisted_agent_data.pop(session_id, None)
        session_agents._pending_agent_edits.pop(session_id, None)
        session_agents._active_session_agents.pop(session_id, None)
        session_agents._pending_agent_activations.pop(session_id, None)


@pytest.mark.parametrize(
    "model",
    ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-5", "gpt-5.1-chat", "gpt-5.6-terra", "phi4-mini"],
)
def test_managed_text_hosts_allow_mai_without_mutating_settings(model: str) -> None:
    stored = {"model": "mai-transcribe-2", "language": "es"}
    assert is_managed_voicelive_model(model)
    assert validate_voicelive_transcription(stored, model_name=model) == {
        "model": "mai-transcribe-2",
        "language": "es",
    }
    assert stored["model"] == "mai-transcribe-2"


@pytest.mark.parametrize("model", ["gpt-5-chat", "o1", "o3", "o3-mini"])
def test_byom_only_text_models_are_not_misclassified_as_managed_mai_hosts(model: str) -> None:
    assert not is_managed_voicelive_model(model)
    with pytest.raises(ValueError, match="non-multimodal managed text model"):
        validate_voicelive_transcription({"model": "mai-transcribe"}, model_name=model)
    assert validate_voicelive_transcription(
        {"model": "mai-transcribe"},
        model_name=model,
        byom_profile="byom-azure-openai-chat-completion",
    ) == {"model": "mai-transcribe"}


@pytest.mark.parametrize(
    "model",
    [
        "gpt-realtime",
        "gpt-realtime-1.5",
        "gpt-realtime-mini",
        "gpt-4o-realtime-preview",
        "phi4-mm-realtime",
        "azure-realtime",
        "gpt-audio",
        "my-text-deployment",
    ],
)
def test_native_audio_and_unclassified_managed_names_are_rejected(model: str) -> None:
    with pytest.raises(ValueError, match="non-multimodal managed text model"):
        validate_voicelive_transcription({"model": "mai-transcribe"}, model_name=model)


@pytest.mark.parametrize(
    "profile", ["byom-azure-openai-chat-completion", "byom-foundry-anthropic-messages"]
)
def test_explicit_byom_text_profile_wins_over_deployment_name(profile: str) -> None:
    assert validate_voicelive_transcription(
        {"model": "mai-transcribe"},
        model_name="my-realtime-named-deployment",
        byom_profile=profile,
    ) == {"model": "mai-transcribe"}
    assert byom_profile_model_conflict(profile, "my-realtime-named-deployment") is None


def test_byom_realtime_rejected_even_when_deployment_name_looks_textual() -> None:
    with pytest.raises(ValueError, match="cannot use the byom-azure-openai-realtime"):
        validate_voicelive_transcription(
            {"model": "mai-transcribe"},
            model_name="gpt-4.1",
            byom_profile="byom-azure-openai-realtime",
        )


def test_blank_byom_does_not_bypass_native_model_guard() -> None:
    with pytest.raises(ValueError, match="Native realtime/audio"):
        validate_voicelive_transcription(
            {"model": "mai-transcribe"}, model_name="gpt-realtime", byom_profile=""
        )


@pytest.mark.parametrize(
    "field,value", [("custom_speech", {"en-US": "model"}), ("phrase_list", ["bank"])]
)
def test_mai_rejects_retained_azure_options(field: str, value) -> None:
    settings = {"model": "mai-transcribe-1.5", field: value}
    original = copy.deepcopy(settings)
    with pytest.raises(ValueError, match=f"does not support {field}"):
        validate_voicelive_transcription(settings, model_name="gpt-4.1")
    assert settings == original


def test_no_invented_custom_cascade_profile() -> None:
    profile = VoiceLiveBYOMConfig.from_dict({"mode": "custom-cascade"})
    with pytest.raises(ValueError, match="Unsupported VoiceLive BYOM profile"):
        profile.to_query()


@pytest.mark.asyncio
async def test_mai_and_true_voice_identifier_reach_real_request_session() -> None:
    agent = UnifiedAgent(
        name="MAI",
        prompt_template="You are a helpful assistant.",
        voicelive_model=ModelConfig(deployment_id="gpt-4.1"),
        voice=VoiceConfig(name="en-US-Harper:MAI-Voice-2-Flash", type="azure-standard"),
        session={"input_audio_transcription_settings": {"model": "mai-transcribe-1.5"}},
    )
    connection = SimpleNamespace(session=SimpleNamespace(update=AsyncMock()))
    await voicelive_session.apply_voicelive_session(agent, connection)
    payload = connection.session.update.call_args.kwargs["session"].as_dict()
    assert payload["input_audio_transcription"] == {"model": "mai-transcribe"}
    assert payload["voice"]["name"] == "en-US-Harper:MAI-Voice-2-Flash"
    assert payload["voice"]["type"] == "azure-standard"
    assert agent.session["input_audio_transcription_settings"]["model"] == "mai-transcribe-1.5"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile", ["byom-azure-openai-chat-completion", "byom-foundry-anthropic-messages"]
)
@pytest.mark.parametrize("model", [None, "auto", "mai-transcribe-2", "azure-speech"])
async def test_byom_default_and_explicit_choices_reach_real_request_session(profile, model) -> None:
    settings = {"language": "en"}
    if model is not None:
        settings["model"] = model
    agent = UnifiedAgent(
        name="BYOM",
        voicelive_model=ModelConfig(deployment_id="customer-chat"),
        byom=VoiceLiveBYOMConfig(mode=profile),
        session={"input_audio_transcription_settings": settings},
    )
    connection = SimpleNamespace(session=SimpleNamespace(update=AsyncMock()))
    await voicelive_session.apply_voicelive_session(agent, connection)
    payload = connection.session.update.call_args.kwargs["session"].as_dict()
    assert payload["input_audio_transcription"] == {
        "model": "azure-speech" if model == "azure-speech" else "mai-transcribe-2",
        "language": "en",
    }
    assert settings == agent.session["input_audio_transcription_settings"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile,expected",
    [(None, "azure-speech"), ("byom-azure-openai-chat-completion", "mai-transcribe-2")],
)
async def test_handoff_default_follows_actual_connection_not_target_byom(profile, expected) -> None:
    agent = UnifiedAgent(
        name="Target",
        byom=VoiceLiveBYOMConfig(mode="byom-azure-openai-realtime"),
        session={"input_audio_transcription_settings": {"model": "auto"}},
    )
    connection = SimpleNamespace(session=SimpleNamespace(update=AsyncMock()))
    await voicelive_session.apply_voicelive_session(
        agent,
        connection,
        connection_model="gpt-realtime" if profile is None else "customer-chat",
        connection_byom_profile=profile,
    )
    payload = connection.session.update.call_args.kwargs["session"].as_dict()
    assert payload["input_audio_transcription"]["model"] == expected


@pytest.mark.asyncio
async def test_handoff_validates_actual_connection_not_target_agent_model() -> None:
    agent = UnifiedAgent(
        name="Target",
        voicelive_model=ModelConfig(deployment_id="gpt-4.1"),
        session={"input_audio_transcription_settings": {"model": "mai-transcribe"}},
    )
    connection = SimpleNamespace(session=SimpleNamespace(update=AsyncMock()))
    with pytest.raises(ValueError, match="Native realtime/audio"):
        await voicelive_session.apply_voicelive_session(
            agent, connection, connection_model="gpt-realtime"
        )
    connection.session.update.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transcription,api_version",
    [
        ("azure-speech", None),
        ("mai-transcribe", MAI_VOICELIVE_API_VERSION),
        ("mai-transcribe-2", MAI_VOICELIVE_API_VERSION),
        (None, MAI_VOICELIVE_API_VERSION),
        ("auto", MAI_VOICELIVE_API_VERSION),
    ],
)
async def test_only_mai_warmup_opts_into_new_api_version(
    monkeypatch: pytest.MonkeyPatch, transcription: str, api_version: str | None
) -> None:
    agent = UnifiedAgent(
        name="Start",
        voicelive_model=ModelConfig(deployment_id="gpt-4.1"),
        byom=VoiceLiveBYOMConfig(mode="byom-azure-openai-chat-completion"),
        session={"input_audio_transcription_settings": {"model": transcription}},
    )
    byom_query = agent.get_byom_query()
    monkeypatch.setattr(voicelive_session, "apply_voicelive_session", AsyncMock())
    monkeypatch.setattr(
        vl_handler,
        "_resolve_voicelive_warmup_config",
        AsyncMock(return_value=({"Start": agent}, "Start", "gpt-4.1", byom_query, {})),
    )
    monkeypatch.setattr(
        vl_handler,
        "get_settings",
        lambda: SimpleNamespace(
            azure_voicelive_endpoint="https://example.services.ai.azure.com",
            ws_max_msg_size=1024,
            ws_heartbeat=20,
            ws_timeout=20,
        ),
    )
    monkeypatch.setattr(vl_handler.VoiceLiveSDKHandler, "_build_credential", AsyncMock())
    cm = SimpleNamespace(__aenter__=AsyncMock(return_value=object()), __aexit__=AsyncMock())
    connect = Mock(return_value=cm)
    monkeypatch.setattr(vl_handler, "connect", connect)
    prepared = await vl_handler._prepare_voicelive_call_warmup(
        app_state=SimpleNamespace(),
        call_connection_id="call",
        session_id="session",
        scenario_name=None,
        user_email=None,
    )
    assert connect.call_args.kwargs.get("api_version") == api_version
    if api_version is None:
        assert "api_version" not in connect.call_args.kwargs
    assert prepared.matches("gpt-4.1", byom_query, api_version=api_version)
    if api_version:
        assert not prepared.matches("gpt-4.1", byom_query)
    await prepared.close()


def test_session_schema_normalization_preserves_unrelated_options() -> None:
    original = {"model": "mai-transcribe-2", "language": "fr", "phrase_list": ["retained"]}
    schema = SessionConfigSchema(input_audio_transcription_settings=original)
    assert schema.input_audio_transcription_settings == original
    assert original["model"] == "mai-transcribe-2"


def _voicelive_startup(monkeypatch, agent):
    state = SimpleNamespace(unified_agents={"Start": agent}, handoff_map={})
    websocket = SimpleNamespace(
        state=SimpleNamespace(),
        app=SimpleNamespace(state=state),
        application_state=WebSocketState.CONNECTED,
        close=AsyncMock(),
    )
    monkeypatch.setattr(
        vl_handler,
        "get_settings",
        lambda: SimpleNamespace(
            azure_voicelive_endpoint="https://resource.services.ai.azure.com",
            azure_voicelive_model="gpt-realtime",
            start_agent="Start",
            ws_max_msg_size=1024,
            ws_heartbeat=20,
            ws_timeout=20,
        ),
    )
    monkeypatch.setattr(vl_handler, "get_session_agent", lambda *args: None)
    monkeypatch.setattr(
        vl_handler,
        "resolve_orchestrator_config",
        lambda **kwargs: SimpleNamespace(
            start_agent="Start", has_scenario=False, scenario_name=None, handoff_map={}
        ),
    )
    connection = SimpleNamespace()
    cm = SimpleNamespace(__aenter__=AsyncMock(return_value=connection), __aexit__=AsyncMock())
    connect = Mock(return_value=cm)
    credential = AsyncMock(return_value=object())
    monkeypatch.setattr(vl_handler, "connect", connect)
    monkeypatch.setattr(vl_handler.VoiceLiveSDKHandler, "_build_credential", credential)
    monkeypatch.setattr(vl_handler, "register_voicelive_orchestrator", Mock())
    monkeypatch.setattr(vl_handler, "unregister_voicelive_orchestrator", Mock())
    orchestrator = SimpleNamespace(
        start=AsyncMock(),
        cleanup=Mock(),
        cancel_and_join_tasks=AsyncMock(),
        _sync_to_memo_manager=Mock(),
    )
    monkeypatch.setattr(vl_handler, "LiveOrchestrator", Mock(return_value=orchestrator))
    handler = vl_handler.VoiceLiveSDKHandler(
        websocket=websocket, session_id="mai-voicelive-startup"
    )
    handler._emit_agent_inventory = AsyncMock()
    handler._event_loop = AsyncMock()
    return handler, connect, credential, cm


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,profile", [("gpt-realtime", None), ("textual-name", "byom-azure-openai-realtime")]
)
async def test_voicelive_start_rejects_invalid_mai_before_connect_or_auth(
    monkeypatch, model, profile
) -> None:
    agent = UnifiedAgent(
        name="Start",
        voicelive_model=ModelConfig(deployment_id=model),
        byom=VoiceLiveBYOMConfig(mode=profile) if profile else None,
        session={"input_audio_transcription_settings": {"model": "mai-transcribe"}},
    )
    handler, connect, credential, _ = _voicelive_startup(monkeypatch, agent)
    with pytest.raises(ValueError, match="mai-transcribe"):
        await handler.start()
    connect.assert_not_called()
    credential.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,profile,transcription",
    [
        ("gpt-4.1", None, "mai-transcribe-2"),
        ("realtime-named-text-deployment", "byom-azure-openai-chat-completion", "mai-transcribe-2"),
        ("anthropic-deployment", "byom-foundry-anthropic-messages", "mai-transcribe-2"),
        ("customer-chat", "byom-azure-openai-chat-completion", None),
        ("anthropic-deployment", "byom-foundry-anthropic-messages", "auto"),
    ],
)
async def test_voicelive_start_keeps_explicit_model_profile_and_mai_api_version(
    monkeypatch, model, profile, transcription
) -> None:
    agent = UnifiedAgent(
        name="Start",
        voicelive_model=ModelConfig(deployment_id=model),
        byom=VoiceLiveBYOMConfig(mode=profile) if profile else None,
        session={"input_audio_transcription_settings": {"model": transcription}},
    )
    handler, connect, credential, cm = _voicelive_startup(monkeypatch, agent)
    try:
        await handler.start()
        assert connect.call_args.kwargs["model"] == model
        assert connect.call_args.kwargs["api_version"] == "2026-04-10"
        assert connect.call_args.kwargs.get("query") == ({"profile": profile} if profile else None)
        credential.assert_awaited_once()
    finally:
        await handler.stop()
    cm.__aexit__.assert_awaited_once()
