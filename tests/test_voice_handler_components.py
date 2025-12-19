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
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from apps.artagent.backend.registries.agentstore.base import (
    ModelConfig,
    UnifiedAgent,
    VoiceConfig,
)
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
