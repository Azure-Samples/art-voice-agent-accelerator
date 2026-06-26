"""
Unit Tests for Voice Handler Components
=======================================

Tests for the voice handler simplification implementation:
- VoiceSessionContext (typed session context)
- UnifiedAgent.get_model_for_mode method
- TTSPlayback context-based voice resolution

These tests validate the Phase 1-3 implementation of the voice handler
simplification proposal.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.websockets import WebSocketState
from apps.artagent.backend.registries.agentstore.base import (
    ModelConfig,
    UnifiedAgent,
    VoiceConfig,
)
from apps.artagent.backend.voice.tts import (
    SAMPLE_RATE_ACS,
    SAMPLE_RATE_BROWSER,
    TTSPlayback,
)
from apps.artagent.backend.voice.tts.playback import _PCM16_BYTES_PER_SAMPLE
from apps.artagent.backend.voice.shared.context import VoiceSessionContext, TransportType


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_memo_manager():
    """Create a mock MemoManager for testing."""
    memo = MagicMock()
    memo.get_context = MagicMock(return_value=None)
    memo.set_context = MagicMock()
    memo.persist_to_redis_async = AsyncMock()
    return memo


@pytest.fixture
def sample_agent() -> UnifiedAgent:
    """Create a sample UnifiedAgent for testing."""
    return UnifiedAgent(
        name="TestAgent",
        description="Test agent for unit tests",
        greeting="Hello, I'm the test agent.",
        model=ModelConfig(
            deployment_id="gpt-4o",
            temperature=0.7,
            top_p=0.95,
            max_tokens=1024,
        ),
        voice=VoiceConfig(
            name="en-US-JennyNeural",
            style="cheerful",
            rate="+0%",
        ),
        prompt_template="You are a test agent. User: {{user_name}}",
        tool_names=["test_tool"],
    )


@pytest.fixture
def voice_context(mock_memo_manager, sample_agent):
    """Create a VoiceSessionContext for testing."""
    context = VoiceSessionContext(
        session_id="test-session-123",
        call_connection_id="test-call-456",
        transport=TransportType.ACS,
        memo_manager=mock_memo_manager,
    )
    context.current_agent = sample_agent
    return context


# ═══════════════════════════════════════════════════════════════════════════════
# VoiceSessionContext Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoiceSessionContext:
    """Tests for VoiceSessionContext dataclass."""

    def test_context_creation_minimal(self):
        """Context should be creatable with minimal required fields."""
        context = VoiceSessionContext(
            session_id="session-123",
        )

        assert context.session_id == "session-123"
        assert context.call_connection_id is None
        assert context.transport == TransportType.ACS

    def test_context_with_optional_fields(self, mock_memo_manager):
        """Context should support optional fields."""
        context = VoiceSessionContext(
            session_id="session-123",
            call_connection_id="conn-456",
            transport=TransportType.BROWSER,
            memo_manager=mock_memo_manager,
        )

        assert context.memo_manager is mock_memo_manager
        assert context.transport == TransportType.BROWSER

    def test_current_agent_property(self, voice_context, sample_agent):
        """current_agent property should work correctly."""
        assert voice_context.current_agent is sample_agent
        assert voice_context.current_agent.name == "TestAgent"

    def test_current_agent_setter(self, voice_context):
        """current_agent setter should update the agent."""
        new_agent = UnifiedAgent(
            name="NewAgent",
            description="A new test agent",
        )

        voice_context.current_agent = new_agent

        assert voice_context.current_agent is new_agent
        assert voice_context.current_agent.name == "NewAgent"

    def test_current_agent_initially_none(self):
        """current_agent should be None by default."""
        context = VoiceSessionContext(
            session_id="session-123",
        )

        assert context.current_agent is None

    def test_cancel_event_default(self):
        """cancel_event should be created by default."""
        context = VoiceSessionContext(session_id="test-123")

        assert context.cancel_event is not None
        assert isinstance(context.cancel_event, asyncio.Event)
        assert not context.cancel_event.is_set()

    def test_transport_types(self):
        """All transport types should be usable."""
        for transport in TransportType:
            context = VoiceSessionContext(
                session_id="test",
                transport=transport,
            )
            assert context.transport == transport


# ═══════════════════════════════════════════════════════════════════════════════
# UnifiedAgent.get_model_for_mode Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnifiedAgentGetModelForMode:
    """Tests for UnifiedAgent.get_model_for_mode method."""

    def test_get_model_for_cascade_mode(self, sample_agent):
        """get_model_for_mode('cascade') should return the agent's model config."""
        model = sample_agent.get_model_for_mode("cascade")

        assert model is sample_agent.model
        assert model.deployment_id == "gpt-4o"
        assert model.temperature == 0.7

    def test_get_model_for_realtime_mode(self, sample_agent):
        """get_model_for_mode('realtime') should return the agent's model config."""
        model = sample_agent.get_model_for_mode("realtime")

        assert model is sample_agent.model
        assert model.deployment_id == "gpt-4o"

    def test_get_model_for_unknown_mode(self, sample_agent):
        """get_model_for_mode with unknown mode should still return model config."""
        # For now, all modes return the same model
        model = sample_agent.get_model_for_mode("unknown_mode")

        assert model is sample_agent.model

    def test_get_model_returns_model_config_type(self, sample_agent):
        """get_model_for_mode should return a ModelConfig instance."""
        model = sample_agent.get_model_for_mode("cascade")

        assert isinstance(model, ModelConfig)

    def test_model_config_has_expected_fields(self, sample_agent):
        """Returned ModelConfig should have all expected fields."""
        model = sample_agent.get_model_for_mode("cascade")

        assert hasattr(model, "deployment_id")
        assert hasattr(model, "temperature")
        assert hasattr(model, "top_p")
        assert hasattr(model, "max_tokens")

    def test_mode_specific_cascade_model(self):
        """get_model_for_mode('cascade') should return cascade_model when set."""
        agent = UnifiedAgent(
            name="TestAgent",
            model=ModelConfig(deployment_id="gpt-4o-fallback", temperature=0.5),
            cascade_model=ModelConfig(deployment_id="gpt-4o", temperature=0.6),
            voicelive_model=ModelConfig(deployment_id="gpt-4o-realtime-preview", temperature=0.7),
        )

        model = agent.get_model_for_mode("cascade")

        assert model is agent.cascade_model
        assert model.deployment_id == "gpt-4o"
        assert model.temperature == 0.6

    def test_mode_specific_voicelive_model(self):
        """get_model_for_mode('realtime') should return voicelive_model when set."""
        agent = UnifiedAgent(
            name="TestAgent",
            model=ModelConfig(deployment_id="gpt-4o-fallback", temperature=0.5),
            cascade_model=ModelConfig(deployment_id="gpt-4o", temperature=0.6),
            voicelive_model=ModelConfig(deployment_id="gpt-4o-realtime-preview", temperature=0.7),
        )

        model = agent.get_model_for_mode("realtime")

        assert model is agent.voicelive_model
        assert model.deployment_id == "gpt-4o-realtime-preview"
        assert model.temperature == 0.7

    def test_mode_specific_voicelive_alias(self):
        """get_model_for_mode('voicelive') should also return voicelive_model."""
        agent = UnifiedAgent(
            name="TestAgent",
            voicelive_model=ModelConfig(deployment_id="gpt-4o-realtime-preview"),
        )

        model = agent.get_model_for_mode("voicelive")

        assert model is agent.voicelive_model
        assert model.deployment_id == "gpt-4o-realtime-preview"

    def test_mode_specific_media_alias(self):
        """get_model_for_mode('media') should return cascade_model."""
        agent = UnifiedAgent(
            name="TestAgent",
            cascade_model=ModelConfig(deployment_id="gpt-4o"),
        )

        model = agent.get_model_for_mode("media")

        assert model is agent.cascade_model
        assert model.deployment_id == "gpt-4o"

    def test_fallback_when_mode_specific_not_set(self):
        """Should fall back to model when mode-specific config is None."""
        agent = UnifiedAgent(
            name="TestAgent",
            model=ModelConfig(deployment_id="gpt-4o-fallback", temperature=0.5),
            # No cascade_model or voicelive_model set
        )

        cascade = agent.get_model_for_mode("cascade")
        realtime = agent.get_model_for_mode("realtime")

        assert cascade is agent.model
        assert realtime is agent.model
        assert cascade.deployment_id == "gpt-4o-fallback"


# ═══════════════════════════════════════════════════════════════════════════════
# ModelConfig Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_default_model_config(self):
        """ModelConfig should have sensible defaults."""
        config = ModelConfig()

        # Should have deployment_id (may be empty or default)
        assert hasattr(config, "deployment_id")
        assert hasattr(config, "temperature")
        assert hasattr(config, "top_p")
        assert hasattr(config, "max_tokens")

    def test_model_config_custom_values(self):
        """ModelConfig should accept custom values."""
        config = ModelConfig(
            deployment_id="gpt-4o-mini",
            temperature=0.5,
            top_p=0.8,
            max_tokens=2048,
        )

        assert config.deployment_id == "gpt-4o-mini"
        assert config.temperature == 0.5
        assert config.top_p == 0.8
        assert config.max_tokens == 2048


# ═══════════════════════════════════════════════════════════════════════════════
# VoiceConfig Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoiceConfig:
    """Tests for VoiceConfig dataclass."""

    def test_default_voice_config(self):
        """VoiceConfig should have sensible defaults."""
        config = VoiceConfig()

        assert hasattr(config, "name")
        assert hasattr(config, "style")
        assert hasattr(config, "rate")

    def test_voice_config_custom_values(self):
        """VoiceConfig should accept custom values."""
        config = VoiceConfig(
            name="en-US-AvaNeural",
            style="professional",
            rate="+10%",
        )

        assert config.name == "en-US-AvaNeural"
        assert config.style == "professional"
        assert config.rate == "+10%"


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Voice Resolution Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentVoiceResolution:
    """Tests for resolving voice settings from agent via context."""

    def test_voice_from_context_agent(self, voice_context):
        """Voice settings should be accessible via context.current_agent."""
        agent = voice_context.current_agent

        assert agent is not None
        assert agent.voice.name == "en-US-JennyNeural"
        assert agent.voice.style == "cheerful"

    def test_voice_resolution_with_different_agents(self, voice_context):
        """Voice should update when agent changes."""
        # Initial agent
        assert voice_context.current_agent.voice.name == "en-US-JennyNeural"

        # Change to new agent with different voice
        new_agent = UnifiedAgent(
            name="FraudAgent",
            voice=VoiceConfig(name="en-US-GuyNeural", style="serious"),
        )
        voice_context.current_agent = new_agent

        assert voice_context.current_agent.voice.name == "en-US-GuyNeural"
        assert voice_context.current_agent.voice.style == "serious"


# ═══════════════════════════════════════════════════════════════════════════════
# TTS Warmup Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTTSPlaybackWarmup:
    """Tests for session-scoped TTS voice warmup."""

    @pytest.mark.asyncio
    async def test_prepare_voice_uses_session_client_and_agent_voice(self, voice_context):
        """prepare_voice should warm the session client with the active agent voice."""
        synth = Mock()
        synth.is_ready = True
        synth.warm_connection = Mock(return_value=True)
        voice_context.tts_client = synth

        playback = TTSPlayback(voice_context, app_state=MagicMock(speech_executor=None))

        result = await playback.prepare_voice(sample_rate=SAMPLE_RATE_ACS, timeout_sec=1.0)

        assert result is True
        synth.warm_connection.assert_called_once_with(
            voice="en-US-JennyNeural",
            sample_rate=SAMPLE_RATE_ACS,
            style="cheerful",
            rate="+0%",
        )

    @pytest.mark.asyncio
    async def test_play_to_acs_reuses_context_tts_client(self, voice_context):
        """play_to_acs should not bypass the warmed session-owned TTS client."""
        synth = Mock()
        synth.is_ready = True
        synth.synthesize_to_pcm_stream = Mock()
        voice_context.tts_client = synth

        app_state = MagicMock(speech_executor=None)
        app_state.tts_pool.acquire_for_session = AsyncMock()
        playback = TTSPlayback(voice_context, app_state=app_state)

        with patch.object(playback, "_stream_synth_to_acs", new_callable=AsyncMock) as stream:
            stream.return_value = True
            result = await playback.play_to_acs("Hello")

        assert result is True
        app_state.tts_pool.acquire_for_session.assert_not_called()
        assert stream.await_args.args[0] is synth

    def test_acs_queued_audio_counts_as_playing(self, voice_context):
        """ACS audio may still be playing after chunks have been sent."""
        playback = TTSPlayback(voice_context, app_state=MagicMock())

        playback._mark_acs_audio_queued(SAMPLE_RATE_ACS * 2)

        assert playback.is_playing

    def test_recent_acs_audio_remains_stoppable_after_estimate_expires(self, voice_context):
        """ACS StopAudio should still be allowed just after local playback estimate expires."""
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        playback._transport_playback_until = time.perf_counter() - 0.1
        playback._last_transport_audio_sent_at = time.perf_counter()

        assert playback.has_pending_transport_playback

    def test_browser_queued_audio_counts_as_pending_playback(self, voice_context):
        """Browser audio is buffered client-side, so barge-in must stay armed.

        Regression: the backend finishes *sending* frames well before the
        browser finishes *playing* them. If pending playback were only tracked
        for ACS, web-client barge-in would be silently dropped once the last
        frame was sent.
        """
        voice_context.transport = TransportType.BROWSER
        playback = TTSPlayback(voice_context, app_state=MagicMock())

        # 2 seconds of 48kHz PCM16 audio just streamed to the browser.
        playback._mark_browser_audio_queued(SAMPLE_RATE_BROWSER * _PCM16_BYTES_PER_SAMPLE * 2)

        assert playback.is_playing
        assert playback.has_pending_transport_playback

    def test_reset_transport_playback_tracking_clears_pending_state(self, voice_context):
        """After a browser audio_stop, buffered-playback bookkeeping is dropped."""
        voice_context.transport = TransportType.BROWSER
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        playback._mark_browser_audio_queued(SAMPLE_RATE_BROWSER * _PCM16_BYTES_PER_SAMPLE * 2)

        playback.reset_transport_playback_tracking()

        assert not playback.is_playing
        assert not playback.has_pending_transport_playback


# ═══════════════════════════════════════════════════════════════════════════════
# Cancel-Event Ownership Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTTSPlaybackCancelOwnership:
    """TTS playback must only READ the cancel event, never clear it.

    The barge-in handler is the single owner of the cancel event. If a TTS
    method cleared it, a turn queued during the barge-in settle window could
    slip through and play over the user (the original ACS bug).
    """

    @pytest.mark.asyncio
    async def test_play_to_acs_bails_without_clearing_cancel(self, voice_context):
        """A cancelled ACS turn returns False and leaves the signal intact."""
        voice_context.cancel_event.set()
        playback = TTSPlayback(voice_context, app_state=MagicMock())

        result = await playback.play_to_acs("hello")

        assert result is False
        assert voice_context.cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_play_to_browser_bails_without_clearing_cancel(self, voice_context):
        """A cancelled browser turn returns False and leaves the signal intact."""
        voice_context.transport = TransportType.BROWSER
        voice_context.cancel_event.set()
        playback = TTSPlayback(voice_context, app_state=MagicMock())

        result = await playback.play_to_browser("hello")

        assert result is False
        assert voice_context.cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_stream_to_acs_leaves_cancel_set(self, voice_context):
        """The ACS streaming loop bails on cancel without clearing the signal."""
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        playback._context._websocket = MagicMock()
        voice_context.cancel_event.set()

        result = await playback._stream_to_acs(
            b"\x00" * 4096, blocking=False, on_first_audio=None, run_id="x"
        )

        assert result is False
        assert voice_context.cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_stream_to_browser_leaves_cancel_set(self, voice_context):
        """The browser streaming loop bails on cancel without clearing the signal."""
        voice_context.transport = TransportType.BROWSER
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        playback._context._websocket = MagicMock()
        voice_context.cancel_event.set()

        result = await playback._stream_to_browser(
            b"\x00" * 4096, on_first_audio=None, run_id="x"
        )

        assert result is False
        assert voice_context.cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_acs_audiodata_suppressed_once_cancel_set(self, voice_context):
        """ACS AudioData writes are dropped under the lock once barge-in fires."""
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        ws = MagicMock()
        ws.send_json = AsyncMock()
        playback._context._websocket = ws
        voice_context.cancel_event.set()

        sent = await playback._send_acs_json({"kind": "AudioData", "audioData": {}})

        assert sent is False
        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_acs_stopaudio_bypasses_cancel_gate(self, voice_context):
        """StopAudio must still be written even while cancel is in effect."""
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        ws = MagicMock()
        ws.send_json = AsyncMock()
        playback._context._websocket = ws
        voice_context.cancel_event.set()

        sent = await playback._send_acs_json(
            {"kind": "StopAudio", "AudioData": None, "StopAudio": {}},
            allow_during_cancel=True,
        )

        assert sent is True
        ws.send_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_audiodata_after_stopaudio(self, voice_context):
        """After StopAudio, no further AudioData frame may reach ACS."""
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        sent_messages: list[dict] = []

        async def capture(message):
            sent_messages.append(message)

        ws = MagicMock()
        ws.send_json = capture
        ws.client_state = WebSocketState.CONNECTED
        ws.application_state = WebSocketState.CONNECTED
        playback._context._websocket = ws

        stopped = await playback.stop_transport_playback()
        assert stopped is True
        assert any(m.get("kind") == "StopAudio" for m in sent_messages)

        # A frame that loses the race and tries to send after the stop is dropped.
        sent = await playback._send_acs_json(
            {"kind": "AudioData", "audioData": {"data": "AAAA"}}
        )
        assert sent is False
        assert not any(m.get("kind") == "AudioData" for m in sent_messages)

    @pytest.mark.asyncio
    async def test_streaming_stops_emitting_audiodata_once_cancelled(self, voice_context):
        """End-to-end: the ACS stream halts at the first frame after barge-in.

        Simulates the barge-in firing the instant the first AudioData frame is
        on the wire. The streaming loop must not emit any further frames — this
        is the behavior that made playback stop immediately for ACS instead of
        only at the next chunk.
        """
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        audiodata_count = {"n": 0}

        async def send_json(message):
            if message.get("kind") == "AudioData":
                audiodata_count["n"] += 1
                # Barge-in sets the cancel flag right after the first frame.
                playback.cancel()

        ws = MagicMock()
        ws.send_json = send_json
        ws.client_state = WebSocketState.CONNECTED
        ws.application_state = WebSocketState.CONNECTED
        playback._context._websocket = ws

        # 10 chunks' worth of PCM (1280 bytes per ACS frame).
        result = await playback._stream_to_acs(
            b"\x00" * (1280 * 10), blocking=False, on_first_audio=None, run_id="t"
        )

        assert result is False  # stream aborted by the cancel signal
        assert audiodata_count["n"] == 1  # only the in-flight frame, none after

    @pytest.mark.asyncio
    async def test_browser_streaming_stops_emitting_after_cancel(self, voice_context):
        """End-to-end: the browser stream halts at the first frame after barge-in.

        Browser is airtight without a transport lock because asyncio is
        single-threaded and there is no await between the cancel check and the
        send_json — once cancelled, the next loop iteration bails.
        """
        voice_context.transport = TransportType.BROWSER
        playback = TTSPlayback(voice_context, app_state=MagicMock())
        audiodata_count = {"n": 0}

        async def send_json(message):
            if message.get("type") == "audio_data":
                audiodata_count["n"] += 1
                # Barge-in sets the cancel flag right after the first frame.
                playback.cancel()

        ws = MagicMock()
        ws.send_json = send_json
        ws.client_state = WebSocketState.CONNECTED
        ws.application_state = WebSocketState.CONNECTED
        playback._context._websocket = ws

        # 10 chunks' worth of PCM (4800 bytes per browser frame).
        result = await playback._stream_to_browser(
            b"\x00" * (4800 * 10), on_first_audio=None, run_id="t"
        )

        assert result is False  # stream aborted by the cancel signal
        assert audiodata_count["n"] == 1  # only the in-flight frame, none after



# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoiceHandlerIntegration:
    """Integration tests for voice handler components working together."""

    def test_context_agent_model_chain(self, voice_context):
        """Context → Agent → Model chain should work correctly."""
        agent = voice_context.current_agent
        model = agent.get_model_for_mode("cascade")

        assert agent.name == "TestAgent"
        assert model.deployment_id == "gpt-4o"
        assert model.temperature == 0.7

    def test_context_agent_voice_chain(self, voice_context):
        """Context → Agent → Voice chain should work correctly."""
        agent = voice_context.current_agent
        voice = agent.voice

        assert agent.name == "TestAgent"
        assert voice.name == "en-US-JennyNeural"
        assert voice.style == "cheerful"

    def test_full_context_lifecycle(self, mock_memo_manager):
        """Full context lifecycle should work correctly."""
        # Create context
        context = VoiceSessionContext(
            session_id="lifecycle-test-123",
            call_connection_id="call-456",
            memo_manager=mock_memo_manager,
        )

        # Initially no agent
        assert context.current_agent is None

        # Set initial agent
        agent1 = UnifiedAgent(
            name="ConciergeAgent",
            model=ModelConfig(deployment_id="gpt-4o", temperature=0.7),
            voice=VoiceConfig(name="en-US-JennyNeural"),
        )
        context.current_agent = agent1

        assert context.current_agent.name == "ConciergeAgent"
        assert context.current_agent.get_model_for_mode("cascade").deployment_id == "gpt-4o"

        # Handoff to different agent
        agent2 = UnifiedAgent(
            name="FraudAgent",
            model=ModelConfig(deployment_id="gpt-4o-mini", temperature=0.5),
            voice=VoiceConfig(name="en-US-GuyNeural"),
        )
        context.current_agent = agent2

        assert context.current_agent.name == "FraudAgent"
        assert context.current_agent.get_model_for_mode("cascade").deployment_id == "gpt-4o-mini"
        assert context.current_agent.voice.name == "en-US-GuyNeural"
