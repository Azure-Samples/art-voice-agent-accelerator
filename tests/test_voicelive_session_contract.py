"""
Voice Live Session Contract
===========================

End-to-end contract tests for the two settings that were previously only
asserted at the *persistence* layer — never at the layer that actually talks to
Azure — and therefore could silently regress:

  * **TTS voice** — the agent's ``voice`` must reach ``session.update(voice=...)``
    with the exact name/type/style/rate/pitch that was configured, both on the
    initial session apply and on the Quick Tune instant push.
  * **Model / BYOM** — the start agent's ``voicelive_model`` must reach
    ``connect(model=...)`` and its BYOM profile must reach ``connect(query=...)``.
    Voice Live binds both at connect() time, so a drop here means the session
    runs on the wrong model with no error.

Also covers ``verify_voicelive_session_contract``, which diffs what we requested
against the ``session.updated`` echo so a service-side substitution is visible
instead of silent.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    UnifiedAgent,
    VoiceConfig,
    VoiceLiveBYOMConfig,
)
from apps.artagent.backend.registries.scenariostore.loader import (
    HandoffConfig as ScenarioHandoff,
)
from apps.artagent.backend.registries.scenariostore.loader import ScenarioConfig
from apps.artagent.backend.voice.shared.config_resolver import OrchestratorConfigResult
from apps.artagent.backend.voice.voicelive import session as voicelive_session
from apps.artagent.backend.voice.voicelive.orchestrator import (
    LiveOrchestrator,
    verify_voicelive_session_contract,
)

# =============================================================================
# Fakes
# =============================================================================


class _FakeSessionNamespace:
    """Captures the RequestSession handed to ``conn.session.update``."""

    def __init__(self) -> None:
        self.updates: list[Any] = []

    async def update(self, session=None, **_kwargs):
        self.updates.append(session)


class _FakeConnection:
    def __init__(self) -> None:
        self.session = _FakeSessionNamespace()

    @property
    def last_update(self) -> Any:
        assert self.session.updates, "no session.update() was issued"
        return self.session.updates[-1]


class _EchoSession:
    """Stand-in for the ``session`` object on a ``session.updated`` event."""

    def __init__(self, voice: Any = None, model: str | None = None) -> None:
        self.id = "sess-1"
        self.voice = voice
        self.model = model


def _make_agent(
    *,
    voice: VoiceConfig | None = None,
    voicelive_model: ModelConfig | None = None,
    byom: VoiceLiveBYOMConfig | None = None,
) -> UnifiedAgent:
    return UnifiedAgent(
        name="ContractAgent",
        description="session contract test agent",
        handoff=HandoffConfig(trigger="handoff_contractagent"),
        model=ModelConfig(deployment_id="gpt-realtime"),
        voicelive_model=voicelive_model,
        voice=voice or VoiceConfig(),
        byom=byom,
        prompt_template="You are a test agent.",
    )


# =============================================================================
# build_voicelive_voice — the payload that gets sent
# =============================================================================


def test_voice_payload_carries_name_type_and_customizations():
    agent = _make_agent(
        voice=VoiceConfig(
            name="en-US-EmmaMultilingualNeural",
            type="azure-standard",
            style="cheerful",
            rate="-8%",
            pitch="+3%",
        )
    )

    payload = voicelive_session.build_voicelive_voice(agent)

    assert payload is not None
    assert payload.name == "en-US-EmmaMultilingualNeural"
    assert payload.type == "azure-standard"
    assert payload.style == "cheerful"
    assert payload.rate == "-8%"
    assert payload.pitch == "+3%"


def test_voice_payload_omits_neutral_rate_and_pitch():
    """``+0%`` is the "unset" sentinel and must not be sent as a customization."""
    agent = _make_agent(
        voice=VoiceConfig(name="en-US-AvaMultilingualNeural", rate="+0%", pitch="+0%")
    )

    payload = voicelive_session.build_voicelive_voice(agent)

    assert payload.rate is None
    assert payload.pitch is None


def test_voice_payload_is_none_when_name_missing():
    agent = _make_agent(voice=VoiceConfig(name=""))
    assert voicelive_session.build_voicelive_voice(agent) is None


# =============================================================================
# apply_voicelive_session — voice actually reaches the SDK
# =============================================================================


@pytest.mark.asyncio
async def test_configured_voice_reaches_session_update():
    """The regression this suite exists for: voice must land on the wire."""
    agent = _make_agent(
        voice=VoiceConfig(
            name="en-US-OnyxTurboMultilingualNeural",
            type="azure-standard",
            style="chat",
            rate="-4%",
        )
    )
    conn = _FakeConnection()

    await voicelive_session.apply_voicelive_session(agent, conn, session_id="sess-1")

    sent = conn.last_update
    assert sent.voice is not None, "session.update() was issued without a voice"
    assert sent.voice.name == "en-US-OnyxTurboMultilingualNeural"
    assert sent.voice.style == "chat"
    assert sent.voice.rate == "-4%"


@pytest.mark.asyncio
async def test_session_update_omits_voice_when_agent_has_none():
    agent = _make_agent(voice=VoiceConfig(name=""))
    conn = _FakeConnection()

    await voicelive_session.apply_voicelive_session(agent, conn, session_id="sess-1")

    assert getattr(conn.last_update, "voice", None) is None


@pytest.mark.asyncio
async def test_full_session_preserves_transcription_and_model_controls():
    agent = _make_agent(
        voicelive_model=ModelConfig(
            deployment_id="gpt-4.1", temperature=0.0, max_tokens=1000, max_completion_tokens=640
        )
    )
    agent.session["input_audio_transcription_settings"] = {
        "model": "azure-speech",
        "language": "es-ES",
        "custom_speech": {"endpoint_id": "custom-speech"},
        "phrase_list": ["Contoso"],
    }
    conn = _FakeConnection()

    await voicelive_session.apply_voicelive_session(agent, conn)

    payload = conn.last_update.as_dict()
    assert (
        payload["input_audio_transcription"] == agent.session["input_audio_transcription_settings"]
    )
    assert payload["temperature"] == 0.0
    assert payload["max_response_output_tokens"] == 640
    assert "model" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("temperature", [-0.1, 1.1])
async def test_full_session_rejects_invalid_temperature_before_sending(temperature):
    agent = _make_agent(
        voicelive_model=ModelConfig(deployment_id="gpt-4.1", temperature=temperature)
    )
    conn = _FakeConnection()

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        await voicelive_session.apply_voicelive_session(agent, conn)

    assert conn.session.updates == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "connection_model,profile,allowed",
    [
        ("gpt-4.1", None, True),
        ("my-text-deployment", "byom-azure-openai-chat-completion", True),
        ("my-anthropic-deployment", "byom-foundry-anthropic-messages", True),
        ("gpt-realtime", None, False),
        ("my-realtime-deployment", "byom-azure-openai-realtime", False),
    ],
)
async def test_handoff_transcription_uses_bound_connection_not_target_configuration(
    connection_model, profile, allowed
):
    agent = _make_agent(voicelive_model=ModelConfig(deployment_id="gpt-4.1"))
    agent.session["input_audio_transcription_settings"] = {"model": "mai-transcribe-2"}
    conn = _FakeConnection()
    kwargs = {"connection_model": connection_model, "connection_byom_profile": profile}

    if allowed:
        await voicelive_session.apply_voicelive_session(agent, conn, **kwargs)
        assert conn.last_update.input_audio_transcription.model == "mai-transcribe-2"
        assert agent.session["input_audio_transcription_settings"]["model"] == "mai-transcribe-2"
    else:
        with pytest.raises(ValueError, match="mai-transcribe"):
            await voicelive_session.apply_voicelive_session(agent, conn, **kwargs)
        assert conn.session.updates == []


@pytest.mark.asyncio
async def test_named_scenario_instructions_apply_at_bootstrap_and_scenario_switch(monkeypatch):
    agent = _make_agent()
    specialist = UnifiedAgent(name="Specialist")
    agents = {agent.name: agent, specialist.name: specialist}
    scenario = ScenarioConfig(
        name="Named scenario",
        start_agent=agent.name,
        agents=list(agents),
        handoffs=[
            ScenarioHandoff(
                from_agent=agent.name,
                to_agent=specialist.name,
                handoff_condition="When investigating an order.",
            )
        ],
    )
    config = OrchestratorConfigResult(
        start_agent=agent.name, agents=agents, scenario=scenario, scenario_name=scenario.name
    )
    conn = _FakeConnection()
    orch = LiveOrchestrator(
        conn,
        agents,
        start_agent=agent.name,
        model_name="gpt-realtime",
        orchestrator_config=config,
    )
    from apps.artagent.backend.voice.shared import config_resolver

    def unexpected_resolution(**kwargs):
        raise AssertionError("The connection's named scenario must not be re-resolved.")

    monkeypatch.setattr(config_resolver, "resolve_orchestrator_config", unexpected_resolution)
    try:
        await orch.start()
        assert "When investigating an order." in conn.last_update.instructions
        assert "Specialist" in conn.last_update.instructions
        await orch._update_session_context()
        initial_updates = len(conn.session.updates)
        for text in ("My order is missing", "Please check again"):
            orch._user_message_history.append(text)
            orch._last_assistant_message = "I am checking."
            await orch._update_session_context()
        assert len(conn.session.updates) == initial_updates

        replacement = ScenarioConfig(
            name="Replacement scenario",
            start_agent=agent.name,
            agents=list(agents),
            handoffs=[
                ScenarioHandoff(
                    from_agent=agent.name,
                    to_agent=specialist.name,
                    handoff_condition="When handling a warranty claim.",
                )
            ],
        )
        orch.update_scenario(
            agents,
            {},
            start_agent=agent.name,
            scenario_name=replacement.name,
            scenario=replacement,
        )
        await asyncio.gather(*orch._owned_tasks)
        assert len(conn.session.updates) == initial_updates + 1
        assert "When handling a warranty claim." in conn.last_update.instructions
        assert "When investigating an order." not in conn.last_update.instructions
    finally:
        await orch.cancel_and_join_tasks()
        orch.cleanup()


# =============================================================================
# Quick Tune instant push — apply_live_session_settings
# =============================================================================


def _make_orchestrator(agent: UnifiedAgent, conn: _FakeConnection) -> LiveOrchestrator:
    return LiveOrchestrator(
        conn=conn,
        agents={agent.name: agent},
        start_agent=agent.name,
        model_name="gpt-realtime",
    )


@pytest.mark.asyncio
async def test_live_push_sends_new_voice_name():
    agent = _make_agent(voice=VoiceConfig(name="en-US-AvaMultilingualNeural"))
    conn = _FakeConnection()
    orch = _make_orchestrator(agent, conn)

    pushed = await orch.apply_live_session_settings(voice={"name": "en-US-EmmaMultilingualNeural"})

    assert pushed is True
    assert conn.last_update.voice.name == "en-US-EmmaMultilingualNeural"
    # The owned definition, not the borrowed catalog, carries subsequent updates.
    owned = orch.agents[orch.active]
    assert owned.voice.name == "en-US-EmmaMultilingualNeural"
    assert agent.voice.name == "en-US-AvaMultilingualNeural"
    await voicelive_session.apply_voicelive_session(owned, conn)
    assert conn.last_update.voice.name == "en-US-EmmaMultilingualNeural"


@pytest.mark.asyncio
async def test_live_push_applies_style_and_pitch():
    """Style/pitch used to be dropped, making those Quick Tune controls no-ops."""
    agent = _make_agent(
        voice=VoiceConfig(name="en-US-AvaMultilingualNeural", style="chat", pitch="+0%")
    )
    conn = _FakeConnection()
    orch = _make_orchestrator(agent, conn)

    pushed = await orch.apply_live_session_settings(
        voice={"style": "cheerful", "pitch": "+6%", "rate": "-2%"}
    )

    assert pushed is True
    sent = conn.last_update.voice
    assert sent.style == "cheerful"
    assert sent.pitch == "+6%"
    assert sent.rate == "-2%"
    owned = orch.agents[orch.active]
    assert owned.voice.style == "cheerful"
    assert owned.voice.pitch == "+6%"
    assert agent.voice.style == "chat"
    assert agent.voice.pitch == "+0%"
    await voicelive_session.apply_voicelive_session(owned, conn)
    assert conn.last_update.voice.style == "cheerful"
    assert conn.last_update.voice.pitch == "+6%"


@pytest.mark.asyncio
async def test_live_push_noop_without_changes():
    agent = _make_agent()
    conn = _FakeConnection()
    orch = _make_orchestrator(agent, conn)

    assert await orch.apply_live_session_settings() is False
    assert conn.session.updates == []


@pytest.mark.asyncio
async def test_concurrent_live_tweaks_preserve_both_changes_without_mutating_catalog():
    agent = _make_agent()
    agent.session["turn_detection"] = {"type": "server_vad", "threshold": 0.5}
    conn = _FakeConnection()
    orch = _make_orchestrator(agent, conn)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def update(session=None):
        conn.session.updates.append(session)
        if len(conn.session.updates) == 1:
            entered.set()
            await release.wait()

    conn.session.update = update
    first = asyncio.create_task(orch.apply_live_session_settings(voice={"rate": "-6%"}))
    await asyncio.wait_for(entered.wait(), timeout=1)
    second = asyncio.create_task(
        orch.apply_live_session_settings(turn_detection={"threshold": 0.7})
    )
    release.set()
    assert await asyncio.gather(first, second) == [True, True]

    assert orch.agents[agent.name].voice.rate == "-6%"
    assert orch.agents[agent.name].session["turn_detection"]["threshold"] == 0.7
    assert agent.voice.rate != "-6%"
    assert agent.session["turn_detection"]["threshold"] == 0.5
    assert len(conn.session.updates) == 2


@pytest.mark.asyncio
async def test_live_tuning_ack_from_replaced_connection_cannot_publish(monkeypatch):
    from apps.artagent.backend.src.orchestration import session_agents

    agent = _make_agent()
    conn = _FakeConnection()
    replacement = _FakeConnection()
    orch = _make_orchestrator(agent, conn)
    orch._memo_manager = SimpleNamespace(session_id="connection-race")
    publish = Mock()
    monkeypatch.setattr(session_agents, "get_session_agent", lambda *args: None)
    monkeypatch.setattr(session_agents, "set_session_agent", publish)

    async def update(session=None):
        conn.session.updates.append(session)
        orch.conn = replacement

    conn.session.update = update
    assert await orch.apply_live_session_settings(voice={"rate": "-6%"}) is False
    assert orch.agents[agent.name] is agent
    assert conn.last_update.voice.rate == "-6%"
    assert replacement.session.updates == []
    publish.assert_not_called()


@pytest.mark.asyncio
async def test_live_tuning_preserves_existing_session_provenance_when_cache_is_empty(monkeypatch):
    from apps.artagent.backend.src.orchestration import session_agents

    agent = _make_agent()
    agent.metadata = {
        "source": "dynamic",
        "session_id": "owned-session",
        "created_at": 123.0,
        "cloned_from": "OriginalTemplate",
        "custom": {"nested": ["keep"]},
    }
    conn = _FakeConnection()
    orch = _make_orchestrator(agent, conn)
    orch._memo_manager = SimpleNamespace(session_id="owned-session")
    publish = Mock()
    monkeypatch.setattr(session_agents, "get_session_agent", lambda *args: None)
    monkeypatch.setattr(session_agents, "set_session_agent", publish)

    assert await orch.apply_live_session_settings(voice={"rate": "-6%"}) is True
    updated = orch.agents[agent.name]
    assert updated.metadata == agent.metadata
    assert updated.metadata["custom"] is not agent.metadata["custom"]
    publish.assert_called_once_with("owned-session", updated, set_active=False, persist=False)


# =============================================================================
# verify_voicelive_session_contract — did the service accept what we asked for?
# =============================================================================


def test_contract_ok_when_echo_matches():
    agent = _make_agent(voice=VoiceConfig(name="en-US-AvaMultilingualNeural"))
    result = verify_voicelive_session_contract(
        requested_voice=voicelive_session.build_voicelive_voice(agent),
        requested_model="gpt-realtime",
        session_obj=_EchoSession(
            voice=voicelive_session.build_voicelive_voice(agent), model="gpt-realtime"
        ),
    )

    assert result["ok"] is True
    assert result["voice_ok"] is True
    assert result["model_ok"] is True


def test_contract_detects_voice_substitution():
    agent = _make_agent(voice=VoiceConfig(name="en-US-AvaMultilingualNeural"))
    other = _make_agent(voice=VoiceConfig(name="en-US-EmmaMultilingualNeural"))

    result = verify_voicelive_session_contract(
        requested_voice=voicelive_session.build_voicelive_voice(agent),
        requested_model="gpt-realtime",
        session_obj=_EchoSession(voice=voicelive_session.build_voicelive_voice(other)),
    )

    assert result["voice_ok"] is False
    assert result["ok"] is False
    assert result["voice_requested"] == "en-us-avamultilingualneural"
    assert result["voice_applied"] == "en-us-emmamultilingualneural"


def test_contract_detects_model_substitution():
    result = verify_voicelive_session_contract(
        requested_voice=None,
        requested_model="my-finetuned-realtime",
        session_obj=_EchoSession(model="gpt-4o-realtime-preview"),
    )

    assert result["model_ok"] is False
    assert result["ok"] is False


def test_contract_handles_string_voice_echo():
    """OpenAI-style voices come back as a bare string, not an object."""
    result = verify_voicelive_session_contract(
        requested_voice="alloy",
        requested_model=None,
        session_obj=_EchoSession(voice="Alloy"),
    )

    assert result["voice_ok"] is True


def test_contract_is_not_a_mismatch_when_echo_is_silent():
    """A service that doesn't echo a field must not raise a false alarm."""
    result = verify_voicelive_session_contract(
        requested_voice="alloy",
        requested_model="gpt-realtime",
        session_obj=_EchoSession(voice=None, model=None),
    )

    assert result["voice_ok"] is None
    assert result["model_ok"] is None
    assert result["ok"] is True


# -----------------------------------------------------------------------------
# Deployment SKU tolerance — Azure echoes the *deployment* name, not the model
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "applied, expected_sku",
    [
        ("gpt-realtime", None),
        ("gpt-realtime-datazone-standard", "datazone-standard"),
        ("gpt-realtime-globalstandard", "globalstandard"),
        ("gpt-realtime-global-standard", "global-standard"),
        ("gpt-realtime-standard", "standard"),
        ("gpt-realtime-provisioned-managed", "provisioned-managed"),
        ("GPT-Realtime-DataZone-Standard", "datazone-standard"),
    ],
)
def test_contract_tolerates_deployment_sku_suffix(applied: str, expected_sku: str | None):
    """The tier suffix on a deployment name is not a model substitution.

    Production requests ``gpt-realtime`` and Azure echoes
    ``gpt-realtime-datazone-standard`` — the same model on a data-zone
    deployment. Flagging that fired a WARNING on 100% of ``session.updated``
    events and pinned ``voicelive.session_contract_ok`` to False.
    """
    result = verify_voicelive_session_contract(
        requested_voice=None,
        requested_model="gpt-realtime",
        session_obj=_EchoSession(model=applied),
    )

    assert result["model_ok"] is True
    assert result["ok"] is True
    # The raw echo is preserved so operators can still see which tier applied.
    assert result["model_applied"] == applied.lower()
    assert result["model_applied_base"] == "gpt-realtime"
    assert result["model_applied_sku"] == expected_sku


@pytest.mark.parametrize(
    "applied",
    [
        "gpt-4o-realtime-preview",
        "gpt-realtime-mini",
        "gpt-realtime-preview",
        "gpt-4o-mini-realtime-preview",
    ],
)
def test_contract_still_detects_genuine_model_substitution(applied: str):
    """SKU tolerance must not degrade into a prefix/substring match.

    ``gpt-realtime-mini`` shares the requested model's prefix but is a different,
    cheaper model — exactly the substitution this check exists to catch. Only
    suffixes on the recognized deployment-tier allowlist are forgiven.
    """
    result = verify_voicelive_session_contract(
        requested_voice=None,
        requested_model="gpt-realtime",
        session_obj=_EchoSession(model=applied),
    )

    assert result["model_ok"] is False
    assert result["ok"] is False


def test_contract_sku_normalization_is_symmetric():
    """Our own configured deployment name may be the SKU-qualified one."""
    result = verify_voicelive_session_contract(
        requested_voice=None,
        requested_model="gpt-realtime-datazone-standard",
        session_obj=_EchoSession(model="gpt-realtime"),
    )

    assert result["model_ok"] is True
    assert result["model_requested"] == "gpt-realtime-datazone-standard"
    assert result["model_requested_base"] == "gpt-realtime"
    assert result["model_requested_sku"] == "datazone-standard"


def test_contract_sku_fields_are_none_when_model_is_absent():
    """Absent echo stays 'not verifiable', and the added fields follow suit."""
    result = verify_voicelive_session_contract(
        requested_voice=None,
        requested_model=None,
        session_obj=_EchoSession(model=None),
    )

    assert result["model_ok"] is None
    assert result["model_applied"] is None
    assert result["model_applied_base"] is None
    assert result["model_applied_sku"] is None
    assert result["model_requested_base"] is None
    assert result["model_requested_sku"] is None
    assert result["ok"] is True


def test_contract_preserves_public_result_keys():
    """Callers depend on these exact keys; new fields are additive only."""
    result = verify_voicelive_session_contract(
        requested_voice="alloy",
        requested_model="gpt-realtime",
        session_obj=_EchoSession(voice="alloy", model="gpt-realtime-datazone-standard"),
    )

    assert {
        "voice_requested",
        "voice_applied",
        "voice_ok",
        "model_requested",
        "model_applied",
        "model_ok",
        "ok",
    } <= set(result)


def test_contract_still_fails_when_voice_is_wrong_despite_sku_match():
    """SKU tolerance on the model must not rescue a genuine voice mismatch."""
    result = verify_voicelive_session_contract(
        requested_voice="alloy",
        requested_model="gpt-realtime",
        session_obj=_EchoSession(voice="echo", model="gpt-realtime-datazone-standard"),
    )

    assert result["model_ok"] is True
    assert result["voice_ok"] is False
    assert result["ok"] is False


def test_orchestrator_does_not_warn_on_sku_suffixed_model():
    """The production regression, end-to-end through the orchestrator."""
    agent = _make_agent(voice=VoiceConfig(name="en-US-AlloyTurboMultilingualNeural"))
    orch = _make_orchestrator(agent, _FakeConnection())

    result = orch._verify_session_contract(
        _EchoSession(
            voice=voicelive_session.build_voicelive_voice(agent),
            model="gpt-realtime-datazone-standard",
        )
    )

    assert result is not None
    assert result["ok"] is True
    assert result["model_ok"] is True


def test_orchestrator_verifies_against_active_agent_voice():
    agent = _make_agent(voice=VoiceConfig(name="en-US-AvaMultilingualNeural"))
    orch = _make_orchestrator(agent, _FakeConnection())

    result = orch._verify_session_contract(
        _EchoSession(voice=voicelive_session.build_voicelive_voice(agent), model="gpt-realtime")
    )

    assert result is not None and result["ok"] is True


def test_orchestrator_flags_mismatch_against_active_agent_voice():
    agent = _make_agent(voice=VoiceConfig(name="en-US-AvaMultilingualNeural"))
    orch = _make_orchestrator(agent, _FakeConnection())

    result = orch._verify_session_contract(_EchoSession(voice="alloy"))

    assert result is not None and result["ok"] is False


# =============================================================================
# Model + BYOM reach connect()
# =============================================================================


class _StubSettings:
    azure_voicelive_endpoint = "wss://contoso-avl.cognitiveservices.azure.com"
    azure_voicelive_model = "gpt-realtime"
    ws_max_msg_size = 1024
    ws_heartbeat = 10
    ws_timeout = 30
    start_agent = "ContractAgent"


class _StubConnectionCM:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_exc):
        return False


@pytest.fixture
def warmup_env(monkeypatch):
    """Patch the warmup seam so only model/BYOM/voice resolution is under test.

    Yields ``(handler_module, connect_kwargs, fake_connection)`` so a test can
    assert on both what was passed to ``connect()`` and what was pushed to
    ``session.update()`` on the resulting connection.
    """
    from apps.artagent.backend.voice.voicelive import handler as vh

    captured: dict[str, Any] = {}
    conn = _FakeConnection()

    def _fake_connect(**kwargs):
        captured.update(kwargs)
        return _StubConnectionCM(conn)

    async def _fake_credential(_settings):
        return object()

    monkeypatch.setattr(vh, "connect", _fake_connect)
    monkeypatch.setattr(vh, "get_settings", lambda: _StubSettings())
    monkeypatch.setattr(vh, "resolve_orchestrator_config", lambda **_kw: None)
    monkeypatch.setattr(vh, "discover_agents", dict)
    monkeypatch.setattr(vh.VoiceLiveSDKHandler, "_build_credential", staticmethod(_fake_credential))
    return vh, captured, conn


@pytest.mark.asyncio
async def test_start_agent_model_and_byom_reach_connect(warmup_env, monkeypatch):
    vh, captured, _conn = warmup_env
    agent = _make_agent(
        voicelive_model=ModelConfig(deployment_id="my-finetuned-realtime"),
        byom=VoiceLiveBYOMConfig(mode="byom-azure-openai-realtime"),
    )
    monkeypatch.setattr(vh, "get_session_agent", lambda _sid: agent)

    prepared = await vh._prepare_voicelive_call_warmup(
        app_state=None,
        call_connection_id="call-1",
        session_id="sess-1",
        scenario_name=None,
        user_email=None,
    )

    assert captured["model"] == "my-finetuned-realtime"
    assert captured["query"] == {"profile": "byom-azure-openai-realtime"}
    assert prepared is not None
    assert prepared.model == "my-finetuned-realtime"
    assert prepared.session_prepared is True


@pytest.mark.asyncio
async def test_managed_start_agent_sends_no_byom_profile(warmup_env, monkeypatch):
    vh, captured, _conn = warmup_env
    agent = _make_agent(voicelive_model=ModelConfig(deployment_id="gpt-realtime"))
    monkeypatch.setattr(vh, "get_session_agent", lambda _sid: agent)

    await vh._prepare_voicelive_call_warmup(
        app_state=None,
        call_connection_id="call-1",
        session_id="sess-1",
        scenario_name=None,
        user_email=None,
    )

    assert captured["model"] == "gpt-realtime"
    assert "query" not in captured


@pytest.mark.asyncio
async def test_warmup_applies_start_agent_voice_to_prepared_session(warmup_env, monkeypatch):
    """A warm connection must be primed with the agent's voice, not a default."""
    vh, _captured, conn = warmup_env
    agent = _make_agent(voice=VoiceConfig(name="en-US-EmmaMultilingualNeural"))
    monkeypatch.setattr(vh, "get_session_agent", lambda _sid: agent)

    await vh._prepare_voicelive_call_warmup(
        app_state=None,
        call_connection_id="call-1",
        session_id="sess-1",
        scenario_name=None,
        user_email=None,
    )

    assert conn.last_update.voice.name == "en-US-EmmaMultilingualNeural"


# =============================================================================
# Warmup connection reuse must not serve a stale model/BYOM combination
# =============================================================================


def _prepared(model: str, byom_query: dict[str, str] | None):
    from apps.artagent.backend.voice.voicelive.handler import VoiceLivePreparedConnection

    return VoiceLivePreparedConnection(
        connection=object(),
        connection_cm=object(),
        credential=object(),  # type: ignore[arg-type]
        settings=_StubSettings(),
        model=model,
        byom_query=byom_query,
    )


def test_prepared_connection_rejects_different_model():
    assert _prepared("gpt-realtime", None).matches("my-finetuned-realtime", None) is False


def test_prepared_connection_rejects_different_byom_profile():
    warm = _prepared("gpt-realtime", {"profile": "byom-azure-openai-realtime"})
    assert warm.matches("gpt-realtime", None) is False
    assert warm.matches("gpt-realtime", {"profile": "byom-azure-openai-chat-completion"}) is False
    assert warm.matches("gpt-realtime", {"profile": "byom-azure-openai-realtime"}) is True
