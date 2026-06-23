"""
Cascade Session Speech-Settings Consumption
===========================================

Validates that the cascade pipeline consumes the session agent's speech/VAD
config at connect — the cascade equivalent of how VoiceLive applies the agent's
session (turn_detection) config. Without this, Agent Builder / Quick Tune speech
overrides persist to the session agent but never take effect on a cascade call.

Exercises VoiceHandler._apply_session_speech_settings against a lightweight stub
recognizer (the real method only reads ``self._context`` / ``self._session_id``).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    SpeechConfig,
    UnifiedAgent,
    VoiceConfig,
)
from apps.artagent.backend.src.orchestration.session_agents import (
    remove_session_agent,
    set_session_agent,
)
from apps.artagent.backend.voice.handler import VoiceHandler


# =============================================================================
# HELPERS
# =============================================================================


def make_stt_stub() -> SimpleNamespace:
    """Recognizer stand-in exposing the per-session VAD attributes."""
    return SimpleNamespace(
        vad_silence_timeout_ms=800,
        use_semantic=False,
        candidate_languages=["en-US"],
    )


def make_handler_stub(session_id: str, stt, active_agent: str | None = None):
    """Minimal object exposing what _apply_session_speech_settings reads."""
    memo = SimpleNamespace(
        get_value_from_corememory=lambda key, *a: (
            active_agent if key == "active_agent" else (a[0] if a else None)
        )
    )
    ctx = SimpleNamespace(stt_client=stt, memo_manager=memo)
    return SimpleNamespace(
        _context=ctx,
        _session_id=session_id,
        _session_short=session_id[-8:],
    )


def make_agent(name: str, *, vad_ms: int, semantic: bool, langs: list[str]) -> UnifiedAgent:
    return UnifiedAgent(
        name=name,
        description="cascade test agent",
        handoff=HandoffConfig(trigger=f"handoff_{name.lower()}"),
        model=ModelConfig(deployment_id="gpt-4o"),
        voice=VoiceConfig(name="en-US-AvaMultilingualNeural"),
        speech=SpeechConfig(
            vad_silence_timeout_ms=vad_ms,
            use_semantic_segmentation=semantic,
            candidate_languages=langs,
        ),
        prompt_template="You are a test agent.",
        tool_names=[],
    )


@pytest.fixture
def session_id() -> str:
    return "session_cascade_speech"


@pytest.fixture(autouse=True)
def _clean(session_id):
    remove_session_agent(session_id)
    yield
    remove_session_agent(session_id)


# =============================================================================
# TESTS
# =============================================================================


class TestCascadeConsumesSessionSpeech:
    def test_applies_overrides_by_active_agent_name(self, session_id) -> None:
        agent = make_agent("CustomCascade", vad_ms=1500, semantic=False, langs=["es-ES"])
        set_session_agent(session_id, agent)

        stt = make_stt_stub()
        handler = make_handler_stub(session_id, stt, active_agent="CustomCascade")

        VoiceHandler._apply_session_speech_settings(handler)

        assert stt.vad_silence_timeout_ms == 1500
        assert stt.use_semantic is False
        assert stt.candidate_languages == ["es-ES"]

    def test_falls_back_to_session_default_agent(self, session_id) -> None:
        # No active_agent name in corememory -> resolve the session's only agent.
        agent = make_agent("OnlyAgent", vad_ms=2000, semantic=True, langs=["en-US"])
        set_session_agent(session_id, agent)

        stt = make_stt_stub()
        handler = make_handler_stub(session_id, stt, active_agent=None)

        VoiceHandler._apply_session_speech_settings(handler)

        assert stt.vad_silence_timeout_ms == 2000
        assert stt.use_semantic is True

    def test_noop_when_no_session_agent(self, session_id) -> None:
        stt = make_stt_stub()
        handler = make_handler_stub(session_id, stt, active_agent=None)

        VoiceHandler._apply_session_speech_settings(handler)

        # Untouched pooled defaults.
        assert stt.vad_silence_timeout_ms == 800
        assert stt.use_semantic is False
        assert stt.candidate_languages == ["en-US"]

    def test_noop_when_no_stt_client(self, session_id) -> None:
        agent = make_agent("CustomCascade", vad_ms=1500, semantic=False, langs=["es-ES"])
        set_session_agent(session_id, agent)

        handler = make_handler_stub(session_id, None, active_agent="CustomCascade")
        # Must not raise when there is no recognizer to configure.
        VoiceHandler._apply_session_speech_settings(handler)
