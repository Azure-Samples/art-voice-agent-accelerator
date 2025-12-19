"""
Unit Tests for SessionAgentManager
===================================

Tests for session-level agent configuration management including:
- SessionAgentConfig serialization/deserialization
- SessionAgentRegistry lifecycle
- SessionAgentManager override resolution
- Handoff map management
- Experiment tracking
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    UnifiedAgent,
    VoiceConfig,
)
from apps.artagent.backend.registries.agentstore.session_manager import (
    SessionAgentConfig,
    SessionAgentManager,
    SessionAgentRegistry,
)

# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def base_agents() -> dict[str, UnifiedAgent]:
    """Create a set of base agents for testing."""
    return {
        "EricaConcierge": UnifiedAgent(
            name="EricaConcierge",
            description="Main concierge agent",
            greeting="Hello! I'm Erica, your financial assistant.",
            handoff=HandoffConfig(trigger="handoff_concierge"),
            model=ModelConfig(deployment_id="gpt-4o", temperature=0.7),
            voice=VoiceConfig(name="en-US-JennyNeural", style="cheerful"),
            prompt_template="You are Erica. {{customer_name}} is calling.",
            tool_names=["check_balance", "transfer_funds", "handoff_fraud_agent"],
            template_vars={"bank_name": "TestBank"},
        ),
        "FraudAgent": UnifiedAgent(
            name="FraudAgent",
            description="Fraud detection specialist",
            greeting="Hi, I'm here to help with fraud concerns.",
            handoff=HandoffConfig(trigger="handoff_fraud_agent"),
            model=ModelConfig(deployment_id="gpt-4o", temperature=0.5),
            voice=VoiceConfig(name="en-US-GuyNeural", style="serious"),
            prompt_template="You are the fraud specialist. Analyze for {{customer_name}}.",
            tool_names=["analyze_transactions", "block_card", "handoff_concierge"],
        ),
        "AuthAgent": UnifiedAgent(
            name="AuthAgent",
            description="Authentication agent",
            handoff=HandoffConfig(trigger="handoff_auth_agent"),
            tool_names=["verify_pin", "check_identity"],
        ),
    }


@pytest.fixture
def mock_memo_manager():
    """Create a mock MemoManager."""
    memo = MagicMock()
    memo.get_context = MagicMock(return_value=None)
    memo.set_context = MagicMock()
    memo.persist_to_redis_async = AsyncMock()
    memo.persist_background = AsyncMock()
    memo.refresh_from_redis_async = AsyncMock()
    return memo


@pytest.fixture
def mock_redis_manager():
    """Create a mock Redis manager."""
    return MagicMock()


@pytest.fixture
def session_manager(base_agents, mock_memo_manager):
    """Create a SessionAgentManager for testing."""
    return SessionAgentManager(
        session_id="test_session_123",
        base_agents=base_agents,
        memo_manager=mock_memo_manager,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SessionAgentConfig Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentConfig:
    """Tests for SessionAgentConfig dataclass."""

    def test_default_config_no_overrides(self):
        """Default config should have no overrides."""
        config = SessionAgentConfig(base_agent_name="TestAgent")

        assert config.base_agent_name == "TestAgent"
        assert config.prompt_override is None
        assert config.voice_override is None
        assert config.model_override is None
        assert config.tool_names_override is None
        assert config.has_overrides() is False
        assert config.source == "base"
        assert config.modification_count == 0

    def test_config_with_overrides(self):
        """Config with overrides should report has_overrides=True."""
        config = SessionAgentConfig(
            base_agent_name="TestAgent",
            prompt_override="Custom prompt",
            voice_override=VoiceConfig(name="en-US-AvaNeural"),
        )

        assert config.has_overrides() is True

    def test_serialization_roundtrip(self):
        """Config should serialize and deserialize correctly."""
        original = SessionAgentConfig(
            base_agent_name="FraudAgent",
            prompt_override="Custom fraud prompt",
            voice_override=VoiceConfig(name="en-US-AvaNeural", rate="+10%"),
            model_override=ModelConfig(deployment_id="gpt-4o-mini", temperature=0.3),
            tool_names_override=["tool_a", "tool_b"],
            template_vars_override={"key": "value"},
            greeting_override="Hello fraud!",
            modification_count=3,
            source="api",
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = SessionAgentConfig.from_dict(data)

        # Verify
        assert restored.base_agent_name == original.base_agent_name
        assert restored.prompt_override == original.prompt_override
        assert restored.voice_override.name == original.voice_override.name
        assert restored.voice_override.rate == original.voice_override.rate
        assert restored.model_override.deployment_id == original.model_override.deployment_id
        assert restored.model_override.temperature == original.model_override.temperature
        assert restored.tool_names_override == original.tool_names_override
        assert restored.template_vars_override == original.template_vars_override
        assert restored.greeting_override == original.greeting_override
        assert restored.modification_count == original.modification_count
        assert restored.source == original.source

    def test_serialization_minimal(self):
        """Minimal config should serialize without optional fields."""
        config = SessionAgentConfig(base_agent_name="TestAgent")
        data = config.to_dict()

        assert "base_agent_name" in data
        assert "prompt_override" not in data
        assert "voice_override" not in data
        assert "model_override" not in data


# ═══════════════════════════════════════════════════════════════════════════════
# SessionAgentRegistry Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentRegistry:
    """Tests for SessionAgentRegistry dataclass."""

    def test_default_registry(self):
        """Default registry should be empty."""
        registry = SessionAgentRegistry(session_id="test_123")

        assert registry.session_id == "test_123"
        assert registry.agents == {}
        assert registry.handoff_map == {}
        assert registry.active_agent is None
        assert registry.experiment_id is None

    def test_registry_with_agents(self):
        """Registry should store agents correctly."""
        agents = {
            "Agent1": SessionAgentConfig(base_agent_name="Agent1"),
            "Agent2": SessionAgentConfig(
                base_agent_name="Agent2",
                prompt_override="Custom",
            ),
        }

        registry = SessionAgentRegistry(
            session_id="test_123",
            agents=agents,
            handoff_map={"handoff_agent2": "Agent2"},
            active_agent="Agent1",
        )

        assert len(registry.agents) == 2
        assert registry.active_agent == "Agent1"
        assert registry.handoff_map["handoff_agent2"] == "Agent2"

    def test_serialization_roundtrip(self):
        """Registry should serialize and deserialize correctly."""
        original = SessionAgentRegistry(
            session_id="test_session_456",
            agents={
                "AgentA": SessionAgentConfig(
                    base_agent_name="AgentA",
                    prompt_override="Prompt A",
                ),
                "AgentB": SessionAgentConfig(base_agent_name="AgentB"),
            },
            handoff_map={"tool_a": "AgentA", "tool_b": "AgentB"},
            active_agent="AgentA",
            experiment_id="exp-001",
            variant="treatment",
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = SessionAgentRegistry.from_dict(data)

        # Verify
        assert restored.session_id == original.session_id
        assert len(restored.agents) == 2
        assert restored.agents["AgentA"].prompt_override == "Prompt A"
        assert restored.handoff_map == original.handoff_map
        assert restored.active_agent == original.active_agent
        assert restored.experiment_id == original.experiment_id
        assert restored.variant == original.variant


# ═══════════════════════════════════════════════════════════════════════════════
# SessionAgentManager Tests - Core Functionality
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentManagerCore:
    """Tests for SessionAgentManager core functionality."""

    def test_initialization(self, session_manager, base_agents):
        """Manager should initialize with base agents."""
        assert session_manager.session_id == "test_session_123"
        # Use set comparison to avoid dict ordering issues
        assert set(session_manager.list_agents()) == set(base_agents.keys())
        assert session_manager.active_agent is None

    def test_get_agent_without_overrides(self, session_manager, base_agents):
        """Getting agent without overrides should return base agent."""
        agent = session_manager.get_agent("EricaConcierge")
        base = base_agents["EricaConcierge"]

        assert agent.name == base.name
        assert agent.prompt_template == base.prompt_template
        assert agent.voice.name == base.voice.name
        assert agent.tool_names == base.tool_names

    def test_get_agent_unknown_raises(self, session_manager):
        """Getting unknown agent should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown agent"):
            session_manager.get_agent("NonExistentAgent")

    def test_set_active_agent(self, session_manager, mock_memo_manager):
        """Setting active agent should persist to memo."""
        session_manager.set_active_agent("FraudAgent")

        assert session_manager.active_agent == "FraudAgent"
        mock_memo_manager.set_context.assert_called()

    def test_set_active_agent_unknown_raises(self, session_manager):
        """Setting unknown agent as active should raise."""
        with pytest.raises(ValueError, match="Unknown agent"):
            session_manager.set_active_agent("NonExistent")


# ═══════════════════════════════════════════════════════════════════════════════
# SessionAgentManager Tests - Override Resolution
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentManagerOverrides:
    """Tests for override resolution in SessionAgentManager."""

    def test_update_agent_prompt(self, session_manager):
        """Updating prompt should create override."""
        session_manager.update_agent_prompt(
            "EricaConcierge",
            "You are a custom Erica with special powers.",
            source="api",
        )

        agent = session_manager.get_agent("EricaConcierge")

        assert agent.prompt_template == "You are a custom Erica with special powers."
        assert agent.metadata.get("_session_override") is True
        assert agent.metadata.get("_override_source") == "api"

    def test_update_agent_voice(self, session_manager):
        """Updating voice should create override."""
        new_voice = VoiceConfig(name="en-US-AvaNeural", rate="+20%", style="excited")
        session_manager.update_agent_voice("FraudAgent", new_voice)

        agent = session_manager.get_agent("FraudAgent")

        assert agent.voice.name == "en-US-AvaNeural"
        assert agent.voice.rate == "+20%"
        assert agent.voice.style == "excited"

    def test_update_agent_model(self, session_manager):
        """Updating model should create override."""
        new_model = ModelConfig(
            deployment_id="gpt-4o-mini",
            temperature=0.2,
            max_tokens=2048,
        )
        session_manager.update_agent_model("AuthAgent", new_model)

        agent = session_manager.get_agent("AuthAgent")

        assert agent.model.deployment_id == "gpt-4o-mini"
        assert agent.model.temperature == 0.2
        assert agent.model.max_tokens == 2048

    def test_update_agent_tools(self, session_manager, base_agents):
        """Updating tools should replace tool list."""
        original_tools = base_agents["EricaConcierge"].tool_names.copy()
        new_tools = ["custom_tool_1", "custom_tool_2"]

        session_manager.update_agent_tools("EricaConcierge", new_tools)
        agent = session_manager.get_agent("EricaConcierge")

        assert agent.tool_names == new_tools
        assert agent.tool_names != original_tools

    def test_update_agent_greeting(self, session_manager):
        """Updating greeting should create override."""
        session_manager.update_agent_greeting("EricaConcierge", "Hey there, custom greeting!")

        agent = session_manager.get_agent("EricaConcierge")

        assert agent.greeting == "Hey there, custom greeting!"

    def test_update_template_vars_merge(self, session_manager, base_agents):
        """Template vars should merge with base by default."""
        # EricaConcierge has template_vars = {"bank_name": "TestBank"}
        session_manager.update_agent_template_vars(
            "EricaConcierge",
            {"custom_key": "custom_value"},
            merge=True,
        )

        agent = session_manager.get_agent("EricaConcierge")

        # Should have both base and override vars
        assert agent.template_vars.get("bank_name") == "TestBank"
        assert agent.template_vars.get("custom_key") == "custom_value"

    def test_update_template_vars_replace(self, session_manager):
        """Template vars with merge=False should replace."""
        session_manager.update_agent_template_vars(
            "EricaConcierge",
            {"only_this": "value"},
            merge=False,
        )

        # Now update without merge
        config = session_manager._registry.agents["EricaConcierge"]

        assert config.template_vars_override == {"only_this": "value"}

    def test_reset_agent(self, session_manager):
        """Resetting agent should remove overrides."""
        # Apply overrides
        session_manager.update_agent_prompt("EricaConcierge", "Custom prompt")
        session_manager.update_agent_greeting("EricaConcierge", "Custom greeting")

        # Verify overrides exist
        assert session_manager.has_overrides("EricaConcierge") is True

        # Reset
        session_manager.reset_agent("EricaConcierge")

        # Verify overrides removed
        assert session_manager.has_overrides("EricaConcierge") is False

    def test_reset_all_agents(self, session_manager):
        """Resetting all agents should clear all overrides."""
        # Apply overrides to multiple agents
        session_manager.update_agent_prompt("EricaConcierge", "Custom 1")
        session_manager.update_agent_prompt("FraudAgent", "Custom 2")
        session_manager.set_active_agent("FraudAgent")
        session_manager.set_experiment("exp-1", "variant-a")

        # Reset all
        session_manager.reset_all_agents()

        # Verify overrides cleared but metadata preserved
        assert session_manager.has_overrides("EricaConcierge") is False
        assert session_manager.has_overrides("FraudAgent") is False
        assert session_manager.active_agent == "FraudAgent"  # Preserved
        assert session_manager.experiment_id == "exp-1"  # Preserved

    def test_modification_count_increments(self, session_manager):
        """Modification count should increment on each update."""
        session_manager.update_agent_prompt("EricaConcierge", "First change")
        session_manager.update_agent_prompt("EricaConcierge", "Second change")
        session_manager.update_agent_voice(
            "EricaConcierge",
            VoiceConfig(name="en-US-AvaNeural"),
        )

        config = session_manager._registry.agents["EricaConcierge"]

        assert config.modification_count == 3


# ═══════════════════════════════════════════════════════════════════════════════
# SessionAgentManager Tests - Handoff Management
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentManagerHandoffs:
    """Tests for handoff management in SessionAgentManager."""

    def test_initial_handoff_map(self, session_manager):
        """Manager should build handoff map from base agents."""
        handoff_map = session_manager.handoff_map

        assert handoff_map["handoff_concierge"] == "EricaConcierge"
        assert handoff_map["handoff_fraud_agent"] == "FraudAgent"
        assert handoff_map["handoff_auth_agent"] == "AuthAgent"

    def test_get_handoff_target(self, session_manager):
        """Should return target agent for handoff tool."""
        target = session_manager.get_handoff_target("handoff_fraud_agent")

        assert target == "FraudAgent"

    def test_get_handoff_target_unknown(self, session_manager):
        """Should return None for unknown handoff tool."""
        target = session_manager.get_handoff_target("unknown_tool")

        assert target is None

    def test_is_handoff_tool(self, session_manager):
        """Should correctly identify handoff tools."""
        assert session_manager.is_handoff_tool("handoff_fraud_agent") is True
        assert session_manager.is_handoff_tool("check_balance") is False

    def test_update_handoff_map(self, session_manager):
        """Should allow adding new handoff mappings."""
        session_manager.update_handoff_map("custom_handoff", "EricaConcierge")

        assert session_manager.get_handoff_target("custom_handoff") == "EricaConcierge"

    def test_update_handoff_map_unknown_agent_raises(self, session_manager):
        """Should raise when target agent is unknown."""
        with pytest.raises(ValueError, match="Unknown target agent"):
            session_manager.update_handoff_map("handoff_x", "NonExistent")

    def test_remove_handoff(self, session_manager):
        """Should allow removing handoff mappings."""
        assert session_manager.is_handoff_tool("handoff_fraud_agent") is True

        result = session_manager.remove_handoff("handoff_fraud_agent")

        assert result is True
        assert session_manager.is_handoff_tool("handoff_fraud_agent") is False

    def test_remove_handoff_nonexistent(self, session_manager):
        """Removing nonexistent handoff should return False."""
        result = session_manager.remove_handoff("nonexistent_tool")

        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# SessionAgentManager Tests - Experiment Tracking
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentManagerExperiments:
    """Tests for experiment tracking in SessionAgentManager."""

    def test_set_experiment(self, session_manager):
        """Should track experiment metadata."""
        session_manager.set_experiment("exp-prompt-v2", "treatment")

        assert session_manager.experiment_id == "exp-prompt-v2"
        assert session_manager.variant == "treatment"

    def test_clear_experiment(self, session_manager):
        """Should clear experiment metadata."""
        session_manager.set_experiment("exp-1", "control")
        session_manager.clear_experiment()

        assert session_manager.experiment_id is None
        assert session_manager.variant is None

    def test_audit_log_empty(self, session_manager):
        """Audit log should be minimal when no modifications."""
        audit = session_manager.get_audit_log()

        assert audit["session_id"] == "test_session_123"
        assert audit["agents"] == {}  # No modifications

    def test_audit_log_with_modifications(self, session_manager):
        """Audit log should capture modifications."""
        session_manager.update_agent_prompt("EricaConcierge", "Custom")
        session_manager.update_agent_voice(
            "FraudAgent",
            VoiceConfig(name="en-US-AvaNeural"),
        )
        session_manager.set_active_agent("FraudAgent")
        session_manager.set_experiment("exp-1", "treatment")

        audit = session_manager.get_audit_log()

        assert audit["session_id"] == "test_session_123"
        assert audit["active_agent"] == "FraudAgent"
        assert audit["experiment_id"] == "exp-1"
        assert audit["variant"] == "treatment"
        assert "EricaConcierge" in audit["agents"]
        assert "FraudAgent" in audit["agents"]
        assert audit["agents"]["EricaConcierge"]["has_prompt_override"] is True
        assert audit["agents"]["FraudAgent"]["has_voice_override"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# SessionAgentManager Tests - Persistence
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentManagerPersistence:
    """Tests for persistence in SessionAgentManager."""

    def test_auto_persist_on_modification(self, session_manager, mock_memo_manager):
        """Modifications should auto-persist to MemoManager."""
        session_manager.update_agent_prompt("EricaConcierge", "New prompt")

        mock_memo_manager.set_context.assert_called()
        call_args = mock_memo_manager.set_context.call_args
        assert call_args[0][0] == "agent_registry"

    @pytest.mark.asyncio
    async def test_persist_to_redis(self, session_manager, mock_memo_manager, mock_redis_manager):
        """Persist should save to Redis via MemoManager."""
        session_manager._redis = mock_redis_manager
        session_manager.update_agent_prompt("EricaConcierge", "New prompt")

        await session_manager.persist()

        mock_memo_manager.persist_to_redis_async.assert_called_once_with(mock_redis_manager)

    @pytest.mark.asyncio
    async def test_reload_from_redis(self, base_agents, mock_memo_manager, mock_redis_manager):
        """Reload should restore from Redis via MemoManager."""
        # Setup: Create registry data that would come from Redis
        registry_data = SessionAgentRegistry(
            session_id="test_session_123",
            agents={
                "EricaConcierge": SessionAgentConfig(
                    base_agent_name="EricaConcierge",
                    prompt_override="Reloaded prompt",
                ),
            },
            active_agent="EricaConcierge",
        ).to_dict()

        # Mock memo to return reloaded data
        mock_memo_manager.get_context.return_value = registry_data

        manager = SessionAgentManager(
            session_id="test_session_123",
            base_agents=base_agents,
            memo_manager=mock_memo_manager,
            redis_mgr=mock_redis_manager,
        )

        await manager.reload()

        mock_memo_manager.refresh_from_redis_async.assert_called_once()

    def test_to_dict_export(self, session_manager):
        """Should export registry as dictionary."""
        session_manager.update_agent_prompt("EricaConcierge", "Export test")
        session_manager.set_active_agent("EricaConcierge")

        data = session_manager.to_dict()

        assert data["session_id"] == "test_session_123"
        assert "EricaConcierge" in data["agents"]
        assert data["active_agent"] == "EricaConcierge"

    def test_from_dict_import(self, base_agents, mock_memo_manager):
        """Should create manager from serialized data."""
        registry_data = {
            "session_id": "imported_session",
            "agents": {
                "FraudAgent": {
                    "base_agent_name": "FraudAgent",
                    "prompt_override": "Imported prompt",
                    "modification_count": 1,
                    "source": "api",
                    "created_at": time.time(),
                },
            },
            "handoff_map": {"handoff_fraud_agent": "FraudAgent"},
            "active_agent": "FraudAgent",
            "experiment_id": "exp-imported",
            "variant": "control",
            "created_at": time.time(),
        }

        manager = SessionAgentManager.from_dict(
            registry_data,
            base_agents=base_agents,
            memo_manager=mock_memo_manager,
        )

        assert manager.session_id == "imported_session"
        assert manager.active_agent == "FraudAgent"
        assert manager.experiment_id == "exp-imported"

        agent = manager.get_agent("FraudAgent")
        assert agent.prompt_template == "Imported prompt"


# ═══════════════════════════════════════════════════════════════════════════════
# SessionAgentManager Tests - Load from Existing Session
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentManagerLoadExisting:
    """Tests for loading from existing session state."""

    def test_load_existing_registry(self, base_agents):
        """Should load registry from MemoManager if exists."""
        existing_data = SessionAgentRegistry(
            session_id="existing_session",
            agents={
                "EricaConcierge": SessionAgentConfig(
                    base_agent_name="EricaConcierge",
                    prompt_override="Previously saved prompt",
                    modification_count=5,
                ),
            },
            active_agent="EricaConcierge",
        ).to_dict()

        mock_memo = MagicMock()
        mock_memo.get_context.return_value = existing_data
        mock_memo.set_context = MagicMock()

        manager = SessionAgentManager(
            session_id="existing_session",
            base_agents=base_agents,
            memo_manager=mock_memo,
        )

        # Should have loaded the existing prompt override
        agent = manager.get_agent("EricaConcierge")
        assert agent.prompt_template == "Previously saved prompt"
        assert manager._registry.agents["EricaConcierge"].modification_count == 5

    def test_create_fresh_if_no_existing(self, base_agents, mock_memo_manager):
        """Should create fresh registry if none exists."""
        mock_memo_manager.get_context.return_value = None

        manager = SessionAgentManager(
            session_id="new_session",
            base_agents=base_agents,
            memo_manager=mock_memo_manager,
        )

        # Should have created configs for all base agents
        assert len(manager._registry.agents) == len(base_agents)
        for name in base_agents:
            assert name in manager._registry.agents


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAgentManagerIntegration:
    """Integration tests for SessionAgentManager."""

    def test_full_workflow(self, base_agents, mock_memo_manager, mock_redis_manager):
        """Test complete workflow of session agent management."""
        # 1. Create manager
        manager = SessionAgentManager(
            session_id="workflow_test",
            base_agents=base_agents,
            memo_manager=mock_memo_manager,
            redis_mgr=mock_redis_manager,
        )

        # 2. Set experiment
        manager.set_experiment("prompt-test-v1", "treatment")

        # 3. Modify agents
        manager.update_agent_prompt(
            "EricaConcierge",
            "You are a friendly bot named Erica. Be concise.",
        )
        manager.update_agent_voice(
            "EricaConcierge",
            VoiceConfig(name="en-US-AvaNeural", rate="+10%"),
        )
        manager.update_agent_tools(
            "EricaConcierge",
            ["check_balance", "get_account_summary"],
        )

        # 4. Set active agent
        manager.set_active_agent("EricaConcierge")

        # 5. Verify resolved agent
        agent = manager.get_agent("EricaConcierge")
        assert agent.prompt_template == "You are a friendly bot named Erica. Be concise."
        assert agent.voice.name == "en-US-AvaNeural"
        assert agent.voice.rate == "+10%"
        assert agent.tool_names == ["check_balance", "get_account_summary"]

        # 6. Verify audit
        audit = manager.get_audit_log()
        assert audit["experiment_id"] == "prompt-test-v1"
        assert audit["variant"] == "treatment"
        assert "EricaConcierge" in audit["agents"]

        # 7. Verify export
        data = manager.to_dict()
        assert data["session_id"] == "workflow_test"
        assert data["experiment_id"] == "prompt-test-v1"

        # 8. Reset and verify
        manager.reset_agent("EricaConcierge")
        agent = manager.get_agent("EricaConcierge")
        assert agent.prompt_template == base_agents["EricaConcierge"].prompt_template


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
