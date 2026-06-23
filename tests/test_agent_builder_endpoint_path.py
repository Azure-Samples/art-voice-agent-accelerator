"""
Agent Builder Endpoint Path Validation
======================================

Validates the full update path from the frontend payload shape through the
backend API to session state:

    frontend handleSave / Quick Tune
        -> PUT /agent-builder/session/{id}  (DynamicAgentConfig)
        -> _upsert_session_agent -> build_session_agent
        -> set_session_agent  (in-memory store + Redis + adapter callback)
        -> get_session_agent / GET /session/{id}   (reflects the update)

Also proves:
- POST /create and PUT /session are the SAME upsert (no divergence).
- PUT is idempotent: re-saving preserves created_at and overwrites values.
- Quick Tune live-settings persist onto the session agent, including the
  clone-from-base path when no session agent exists yet.

These call the endpoint coroutines directly (no network) with a stub Request,
so they exercise the real server-side processing without standing up the app.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

import pytest

from apps.artagent.backend.api.v1.endpoints.agent_builder import (
    DynamicAgentConfig,
    LiveSettingsRequest,
    apply_live_session_settings,
    create_dynamic_agent,
    get_session_agent_config,
    update_session_agent,
)
from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    UnifiedAgent,
    VoiceConfig,
)
from apps.artagent.backend.src.orchestration.session_agents import (
    get_session_agent,
    remove_session_agent,
)


# =============================================================================
# HELPERS
# =============================================================================


def frontend_payload(
    *,
    name: str = "My Bot",
    prompt: str = "You are a helpful voice assistant.",
    voice_name: str = "en-US-AvaMultilingualNeural",
    cascade_deployment: str = "gpt-4o",
    voicelive_deployment: str = "gpt-realtime",
    tools: list[str] | None = None,
) -> Dict[str, Any]:
    """Mirror the JSON body that AgentBuilder.jsx / App.jsx Quick Tune POSTs."""
    return {
        "name": name,
        "description": "Test agent",
        "greeting": "Hello!",
        "return_greeting": "Welcome back!",
        "prompt": prompt,
        "tools": tools or [],
        "cascade_model": {
            "deployment_id": cascade_deployment,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 4096,
            "endpoint_preference": "auto",
            "api_version": "v1",
        },
        "voicelive_model": {
            "deployment_id": voicelive_deployment,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 4096,
            "endpoint_preference": "auto",
        },
        "voice": {
            "name": voice_name,
            "type": "azure-standard",
            "style": "chat",
            "rate": "+0%",
        },
        "speech": {
            "vad_silence_timeout_ms": 800,
            "use_semantic_segmentation": False,
            "candidate_languages": ["en-US"],
        },
        "template_vars": {"brand": "Contoso"},
    }


def stub_request(unified_agents: dict | None = None, start_agent: str | None = None):
    """Minimal Request stand-in exposing app.state for live-settings resolution."""
    state = SimpleNamespace(
        unified_agents=unified_agents or {},
        start_agent=start_agent,
        redis=None,
        redis_manager=None,
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


@pytest.fixture
def session_id() -> str:
    return "session_path_test"


@pytest.fixture(autouse=True)
def _clean_session(session_id):
    """Ensure each test starts and ends with no session agent."""
    remove_session_agent(session_id)
    yield
    remove_session_agent(session_id)


# =============================================================================
# FRONTEND PAYLOAD -> PUT -> SESSION STATE
# =============================================================================


class TestUpdatePathPersists:
    """The exact frontend payload must land in session state via PUT."""

    @pytest.mark.asyncio
    async def test_put_persists_frontend_payload(self, session_id) -> None:
        config = DynamicAgentConfig.model_validate(
            frontend_payload(name="My Bot", voice_name="en-US-JennyNeural")
        )

        resp = await update_session_agent(session_id, config, stub_request())
        assert resp.status == "updated"
        assert resp.agent_name == "My Bot"

        # Update landed in the session-agent store (what the orchestrator reads).
        stored = get_session_agent(session_id)
        assert stored is not None
        assert stored.name == "My Bot"
        assert stored.prompt_template == "You are a helpful voice assistant."
        assert stored.voice.name == "en-US-JennyNeural"
        assert stored.cascade_model.deployment_id == "gpt-4o"
        assert stored.voicelive_model.deployment_id == "gpt-realtime"
        assert stored.template_vars == {"brand": "Contoso"}

    @pytest.mark.asyncio
    async def test_get_endpoint_roundtrips_update(self, session_id) -> None:
        config = DynamicAgentConfig.model_validate(frontend_payload(name="RoundTrip"))
        await update_session_agent(session_id, config, stub_request())

        got = await get_session_agent_config(session_id, stub_request())
        assert got.agent_name == "RoundTrip"
        assert got.config["prompt_full"] == "You are a helpful voice assistant."
        assert got.config["voice"]["name"] == "en-US-AvaMultilingualNeural"
        assert got.config["cascade_model"]["deployment_id"] == "gpt-4o"
        assert got.config["voicelive_model"]["deployment_id"] == "gpt-realtime"


class TestUpsertSemantics:
    """PUT is an idempotent upsert; create + update share one path."""

    @pytest.mark.asyncio
    async def test_resave_preserves_created_at_and_overwrites(self, session_id) -> None:
        first = DynamicAgentConfig.model_validate(
            frontend_payload(name="Bot", voice_name="en-US-AvaMultilingualNeural")
        )
        r1 = await update_session_agent(session_id, first, stub_request())
        created_at = r1.created_at

        second = DynamicAgentConfig.model_validate(
            frontend_payload(name="Bot", voice_name="en-US-GuyNeural")
        )
        r2 = await update_session_agent(session_id, second, stub_request())

        # created_at preserved across saves; values overwritten.
        assert r2.created_at == created_at
        assert r2.modified_at >= r1.modified_at
        assert get_session_agent(session_id).voice.name == "en-US-GuyNeural"

    @pytest.mark.asyncio
    async def test_create_and_update_produce_identical_agent(self) -> None:
        payload = frontend_payload(name="Parity", tools=[])
        cfg = DynamicAgentConfig.model_validate(payload)

        sid_create = "session_parity_create"
        sid_update = "session_parity_update"
        remove_session_agent(sid_create)
        remove_session_agent(sid_update)
        try:
            await create_dynamic_agent(cfg, sid_create, stub_request())
            await update_session_agent(sid_update, cfg, stub_request())

            a = get_session_agent(sid_create)
            b = get_session_agent(sid_update)

            # Same build path => identical config (ignoring per-session metadata).
            assert a.name == b.name
            assert a.prompt_template == b.prompt_template
            assert a.tool_names == b.tool_names
            assert a.voice.to_dict() == b.voice.to_dict()
            assert a.cascade_model.to_dict() == b.cascade_model.to_dict()
            assert a.voicelive_model.to_dict() == b.voicelive_model.to_dict()
            assert a.handoff.trigger == b.handoff.trigger
        finally:
            remove_session_agent(sid_create)
            remove_session_agent(sid_update)


class TestInvalidToolsRejected:
    """Tool validation guards both create and update identically."""

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_400(self, session_id) -> None:
        from fastapi import HTTPException

        cfg = DynamicAgentConfig.model_validate(
            frontend_payload(tools=["definitely_not_a_real_tool"])
        )
        with pytest.raises(HTTPException) as exc:
            await update_session_agent(session_id, cfg, stub_request())
        assert exc.value.status_code == 400


# =============================================================================
# QUICK TUNE (live-settings) -> SESSION STATE
# =============================================================================


class TestLiveSettingsPersist:
    """Quick Tune tweaks must be captured in session state."""

    @pytest.mark.asyncio
    async def test_patches_existing_session_agent(self, session_id) -> None:
        # Seed a session agent (as Agent Builder would).
        cfg = DynamicAgentConfig.model_validate(
            frontend_payload(name="Tunable", voice_name="en-US-AvaMultilingualNeural")
        )
        await update_session_agent(session_id, cfg, stub_request())

        payload = LiveSettingsRequest.model_validate(
            {
                "mode": "voicelive",
                "turn_detection": {"threshold": 0.6, "silence_duration_ms": 900},
                "voice": {"name": "en-US-GuyNeural", "rate": "-4%"},
            }
        )
        result = await apply_live_session_settings(session_id, payload, stub_request())

        assert result["applied"] is True
        stored = get_session_agent(session_id)
        assert stored.voice.name == "en-US-GuyNeural"
        assert stored.voice.rate == "-4%"
        assert stored.session["turn_detection"]["threshold"] == 0.6
        assert stored.session["turn_detection"]["silence_duration_ms"] == 900

    @pytest.mark.asyncio
    async def test_clones_base_agent_when_no_session_agent(self, session_id) -> None:
        # No session agent yet; a base agent is "active" for the call.
        base = UnifiedAgent(
            name="Concierge",
            description="base",
            handoff=HandoffConfig(trigger="handoff_concierge"),
            model=ModelConfig(deployment_id="gpt-4o"),
            voice=VoiceConfig(name="en-US-JennyNeural", style="chat"),
            prompt_template="base prompt",
            tool_names=[],
        )
        req = stub_request(unified_agents={"Concierge": base}, start_agent="Concierge")

        assert get_session_agent(session_id) is None

        payload = LiveSettingsRequest.model_validate(
            {"mode": "voicelive", "voice": {"name": "en-US-GuyNeural"}}
        )
        result = await apply_live_session_settings(session_id, payload, req)

        assert result["applied"] is True
        # A session-scoped clone now exists and carries the tweak — not lost on reconnect.
        cloned = get_session_agent(session_id)
        assert cloned is not None
        assert cloned.name == "Concierge"
        assert cloned.voice.name == "en-US-GuyNeural"
        assert cloned.metadata.get("cloned_from") == "Concierge"
        # The shared registry agent must NOT be mutated.
        assert base.voice.name == "en-US-JennyNeural"
