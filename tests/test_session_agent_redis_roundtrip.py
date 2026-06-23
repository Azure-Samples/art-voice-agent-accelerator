"""
Session Agent Redis Persistence Round-Trip
==========================================

Closes the coverage gap on the *persisted* config path. The endpoint-path test
(test_agent_builder_endpoint_path.py) stubs ``redis=None`` and the manager test
(test_session_agent_manager.py) mocks the Redis manager, so neither exercises a
real write → read-back cycle through ``session_agents.py``.

This module drives the actual persistence path that lets a session agent survive
a process reload and be visible to other workers:

    set_session_agent
        -> _serialize_agent -> _persist_agents_to_redis (corememory + Redis write)
    [fresh worker: in-memory cache empty]
    get_session_agent
        -> _ensure_session_loaded -> _load_agents_from_redis -> _deserialize_agent

A dict-backed ``FakeRedisManager`` stands in for ``AzureRedisManager`` — it
implements only the two methods ``MemoManager`` touches on this path
(``get_session_data`` sync read, ``store_session_data_async`` async write).

The key risk these tests guard: if a field were dropped in ``_serialize_agent``
/ ``_deserialize_agent``, a config saved from the UI would silently fail to
survive a reload, and nothing else in the suite would catch it.
"""

from __future__ import annotations

import asyncio

import pytest

import apps.artagent.backend.src.orchestration.session_agents as sa
from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    SpeechConfig,
    UnifiedAgent,
    VoiceConfig,
)
from apps.artagent.backend.src.orchestration.session_agents import (
    _deserialize_agent,
    _serialize_agent,
    get_session_agent,
    get_session_agents,
    persist_session_agents_to_redis,
    set_session_agent,
)


# =============================================================================
# FAKES / HELPERS
# =============================================================================


class FakeRedisManager:
    """In-memory stand-in for AzureRedisManager.

    MemoManager only calls two methods on the session-agent persistence path:
      * ``get_session_data(key)``           — sync read, returns a dict
      * ``store_session_data_async(key, d)`` — async write, returns success bool

    The stored payload is a dict of JSON strings (MemoManager.to_redis_dict),
    which we keep verbatim so the round-trip mirrors real Redis byte-for-byte.
    """

    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self.write_count = 0

    def get_session_data(self, key: str) -> dict:
        return dict(self.store.get(key, {}))

    async def store_session_data_async(self, key: str, data: dict) -> bool:
        self.store[key] = dict(data)
        self.write_count += 1
        return True


def make_rich_agent(name: str = "BankBot") -> UnifiedAgent:
    """An agent that exercises every serialized config block."""
    return UnifiedAgent(
        name=name,
        description="Rich config agent",
        greeting="Hi there!",
        return_greeting="Welcome back!",
        handoff=HandoffConfig(trigger=f"handoff_{name.lower()}"),
        model=ModelConfig(deployment_id="gpt-4o"),
        cascade_model=ModelConfig(
            deployment_id="gpt-4o",
            temperature=0.3,
            top_p=0.8,
            max_tokens=1024,
        ),
        voicelive_model=ModelConfig(
            deployment_id="gpt-realtime",
            temperature=0.6,
            max_tokens=2048,
        ),
        voice=VoiceConfig(
            name="en-US-GuyNeural",
            type="azure-standard",
            style="serious",
            rate="-4%",
            pitch="+2%",
        ),
        speech=SpeechConfig(
            vad_silence_timeout_ms=650,
            use_semantic_segmentation=True,
            candidate_languages=["en-US", "es-ES"],
            enable_diarization=True,
            speaker_count_hint=3,
        ),
        session={
            "modalities": ["text", "audio"],
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.6,
                "silence_duration_ms": 900,
                "prefix_padding_ms": 300,
            },
            "tool_choice": "auto",
        },
        prompt_template="You are {{brand}} assistant.",
        tool_names=[],
        template_vars={"brand": "Contoso"},
        metadata={"cloned_from": "Concierge"},
    )


def _assert_rich_config_preserved(agent: UnifiedAgent, *, name: str = "BankBot") -> None:
    """Every block that AgentBuilder / Quick Tune can set must survive."""
    assert agent is not None
    assert agent.name == name
    assert agent.greeting == "Hi there!"
    assert agent.return_greeting == "Welcome back!"
    assert agent.handoff.trigger == f"handoff_{name.lower()}"
    assert agent.prompt_template == "You are {{brand}} assistant."
    assert agent.template_vars == {"brand": "Contoso"}
    assert agent.metadata.get("cloned_from") == "Concierge"

    # Voice (TTS) — cascade + voicelive both read this.
    assert agent.voice.name == "en-US-GuyNeural"
    assert agent.voice.style == "serious"
    assert agent.voice.rate == "-4%"
    assert agent.voice.pitch == "+2%"

    # Speech (STT / VAD) — cascade consumes this at connect.
    assert agent.speech.vad_silence_timeout_ms == 650
    assert agent.speech.use_semantic_segmentation is True
    assert agent.speech.candidate_languages == ["en-US", "es-ES"]
    assert agent.speech.enable_diarization is True
    assert agent.speech.speaker_count_hint == 3

    # Session (VoiceLive turn_detection) — Quick Tune writes threshold/silence here.
    td = agent.session["turn_detection"]
    assert td["type"] == "server_vad"
    assert td["threshold"] == 0.6
    assert td["silence_duration_ms"] == 900
    assert td["prefix_padding_ms"] == 300
    assert agent.session["tool_choice"] == "auto"

    # Mode-specific models — cascade vs voicelive deployments must stay distinct.
    assert agent.cascade_model.deployment_id == "gpt-4o"
    assert agent.cascade_model.temperature == 0.3
    assert agent.cascade_model.max_tokens == 1024
    assert agent.voicelive_model.deployment_id == "gpt-realtime"
    assert agent.voicelive_model.max_tokens == 2048


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def session_id() -> str:
    return "session_redis_roundtrip"


@pytest.fixture
def fake_redis():
    """Register a fake Redis manager for the duration of a test."""
    fake = FakeRedisManager()
    sa.set_redis_manager(fake)
    try:
        yield fake
    finally:
        sa.set_redis_manager(None)


@pytest.fixture(autouse=True)
def _isolate_session_state(session_id):
    """Clear the module-level in-memory caches before and after each test."""

    def _clear():
        sa._session_agents.pop(session_id, None)
        sa._session_load_times.pop(session_id, None)

    _clear()
    yield
    _clear()


def _simulate_fresh_worker(session_id: str) -> None:
    """Drop the in-memory cache so the next read must come from Redis."""
    sa._session_agents.pop(session_id, None)
    sa._session_load_times.pop(session_id, None)


# =============================================================================
# PURE SERIALIZATION ROUND-TRIP (no Redis)
# =============================================================================


class TestAgentSerializationRoundTrip:
    """_serialize_agent -> _deserialize_agent preserves every config block."""

    def test_full_config_survives_serialize_deserialize(self) -> None:
        original = make_rich_agent("BankBot")

        data = _serialize_agent(original)
        # Serialized form must be JSON-safe (this is what lands in Redis).
        import json

        json.dumps(data)

        restored = _deserialize_agent(data)
        _assert_rich_config_preserved(restored, name="BankBot")

    def test_minimal_agent_serialize_deserialize(self) -> None:
        minimal = UnifiedAgent(
            name="Tiny",
            description="",
            handoff=HandoffConfig(trigger="handoff_tiny"),
            model=ModelConfig(deployment_id="gpt-4o"),
            prompt_template="hi",
            tool_names=[],
        )

        restored = _deserialize_agent(_serialize_agent(minimal))
        assert restored.name == "Tiny"
        assert restored.handoff.trigger == "handoff_tiny"
        # Optional blocks default cleanly rather than raising.
        assert restored.cascade_model is None
        assert restored.voicelive_model is None
        assert restored.session == {}


# =============================================================================
# FULL REDIS ROUND-TRIP VIA PUBLIC API
# =============================================================================


class TestSessionAgentRedisRoundTrip:
    """set_session_agent -> Redis -> fresh worker -> get_session_agent."""

    @pytest.mark.asyncio
    async def test_set_then_fresh_load_preserves_config(self, session_id, fake_redis) -> None:
        agent = make_rich_agent("BankBot")

        set_session_agent(session_id, agent)
        # Guarantee the durable write (the path FastAPI endpoints await).
        await persist_session_agents_to_redis(session_id)
        await asyncio.sleep(0)  # let any fire-and-forget persist settle

        assert fake_redis.write_count >= 1
        assert fake_redis.store, "expected agent payload written to Redis"

        # A fresh worker has nothing in memory but can see the Redis copy.
        _simulate_fresh_worker(session_id)
        assert session_id not in sa._session_agents

        loaded = get_session_agent(session_id, "BankBot")
        _assert_rich_config_preserved(loaded, name="BankBot")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fake_redis")
    async def test_case_insensitive_lookup_after_reload(self, session_id) -> None:
        set_session_agent(session_id, make_rich_agent("BankBot"))
        await persist_session_agents_to_redis(session_id)
        _simulate_fresh_worker(session_id)

        # find_agent_by_name resolves case-insensitively against Redis-loaded data.
        loaded = get_session_agent(session_id, "bankbot")
        assert loaded is not None
        assert loaded.name == "BankBot"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fake_redis")
    async def test_multiple_agents_survive_reload(self, session_id) -> None:
        set_session_agent(session_id, make_rich_agent("BankBot"))
        set_session_agent(session_id, make_rich_agent("FraudBot"))
        await persist_session_agents_to_redis(session_id)
        _simulate_fresh_worker(session_id)

        loaded = get_session_agents(session_id)
        assert set(loaded.keys()) == {"BankBot", "FraudBot"}
        _assert_rich_config_preserved(loaded["BankBot"], name="BankBot")
        _assert_rich_config_preserved(loaded["FraudBot"], name="FraudBot")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("fake_redis")
    async def test_resave_overwrites_persisted_voice(self, session_id) -> None:
        agent = make_rich_agent("BankBot")
        set_session_agent(session_id, agent)
        await persist_session_agents_to_redis(session_id)

        # Re-tune the voice (as Quick Tune would) and persist again.
        agent.voice.name = "en-US-JennyNeural"
        set_session_agent(session_id, agent)
        await persist_session_agents_to_redis(session_id)

        _simulate_fresh_worker(session_id)
        loaded = get_session_agent(session_id, "BankBot")
        assert loaded.voice.name == "en-US-JennyNeural"

    @pytest.mark.asyncio
    async def test_no_redis_manager_is_safe(self, session_id) -> None:
        # No fake_redis fixture here → _redis_manager is None.
        agent = make_rich_agent("BankBot")
        set_session_agent(session_id, agent)  # must not raise
        await persist_session_agents_to_redis(session_id)  # no-op, must not raise

        # In-memory copy is still usable on this worker.
        loaded = get_session_agent(session_id, "BankBot")
        assert loaded is not None
        assert loaded.voice.name == "en-US-GuyNeural"
