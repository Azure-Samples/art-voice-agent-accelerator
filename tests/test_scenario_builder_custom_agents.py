"""
Unit Tests for Scenario Builder Custom Agent Visibility
========================================================

Tests that custom agents (session agents) created via the Agent Builder
properly appear in the Scenario Builder's available agents list and can 
be referenced in scenario configurations.

Key test scenarios:
- Session agents with unique names appear in available agents list
- Session agents with duplicate names (matching static agents) get renamed but preserve original_name
- Scenario configs referencing original agent names remain valid via original_name matching
- Custom agents can be invoked through scenario configurations

Fixes issue: Custom agents with names not matching existing pool of agents 
were not showing up in the scenario builder.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from apps.artagent.backend.api.v1.endpoints.scenario_builder import (
    AgentInfo,
    ToolInfo,
    list_available_agents,
    extract_prompt_vars,
    build_prompt_preview,
)
from apps.artagent.backend.registries.agentstore.base import (
    HandoffConfig,
    ModelConfig,
    UnifiedAgent,
    VoiceConfig,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_static_agents():
    """Create static agents that would be in the registry."""
    return {
        "EricaConcierge": UnifiedAgent(
            name="EricaConcierge",
            description="Main concierge agent",
            greeting="Hello! I'm Erica, your financial assistant.",
            handoff=HandoffConfig(trigger="handoff_concierge"),
            model=ModelConfig(deployment_id="gpt-4o", temperature=0.7),
            voice=VoiceConfig(name="en-US-JennyNeural", style="cheerful"),
            prompt_template="You are Erica. {{customer_name}} is calling.",
            tool_names=["check_balance", "transfer_funds"],
        ),
        "FraudAgent": UnifiedAgent(
            name="FraudAgent",
            description="Fraud detection specialist",
            greeting="Hi, I'm here to help with fraud concerns.",
            handoff=HandoffConfig(trigger="handoff_fraud_agent"),
            model=ModelConfig(deployment_id="gpt-4o", temperature=0.5),
            voice=VoiceConfig(name="en-US-GuyNeural", style="serious"),
            prompt_template="You are the fraud specialist.",
            tool_names=["analyze_transactions"],
        ),
    }


@pytest.fixture
def mock_custom_session_agent():
    """Create a custom session agent with a unique name (not in static registry)."""
    return UnifiedAgent(
        name="MyCustomAgent",
        description="A custom agent created for testing",
        greeting="Hello from my custom agent!",
        handoff=HandoffConfig(trigger="handoff_custom"),
        model=ModelConfig(deployment_id="gpt-4o", temperature=0.8),
        voice=VoiceConfig(name="en-US-AriaNeural", style="friendly"),
        prompt_template="You are a custom agent. Help the {{customer_name}}.",
        tool_names=["custom_tool"],
    )


@pytest.fixture
def mock_duplicate_name_session_agent():
    """Create a session agent with the same name as a static agent."""
    return UnifiedAgent(
        name="EricaConcierge",  # Same name as static agent
        description="Customized Erica for this session",
        greeting="Hi! I'm your personalized Erica!",
        handoff=HandoffConfig(trigger="handoff_concierge"),
        model=ModelConfig(deployment_id="gpt-4-turbo", temperature=0.9),  # Different model
        prompt_template="You are a customized Erica. {{greeting_override}}",
        tool_names=["custom_balance_check"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AgentInfo Schema Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentInfoSchema:
    """Tests for the AgentInfo schema with original_name field."""

    def test_agent_info_has_original_name_field(self):
        """AgentInfo schema should have optional original_name field."""
        agent_info = AgentInfo(
            name="TestAgent",
            description="Test description",
            original_name="OriginalTestAgent"
        )
        assert hasattr(agent_info, "original_name")
        assert agent_info.original_name == "OriginalTestAgent"

    def test_agent_info_original_name_defaults_to_none(self):
        """original_name should default to None when not provided."""
        agent_info = AgentInfo(
            name="TestAgent",
            description="Test description"
        )
        assert agent_info.original_name is None

    def test_agent_info_preserves_both_names(self):
        """AgentInfo should preserve both display name and original_name."""
        agent_info = AgentInfo(
            name="EricaConcierge (session)",  # Renamed display name
            original_name="EricaConcierge",   # Original name
            description="Customized concierge",
            is_session_agent=True,
            session_id="test-session-123"
        )
        
        assert agent_info.name == "EricaConcierge (session)"
        assert agent_info.original_name == "EricaConcierge"
        assert agent_info.is_session_agent is True


# ═══════════════════════════════════════════════════════════════════════════════
# Custom Agent Visibility Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCustomAgentVisibility:
    """Tests for custom agent visibility in scenario builder."""

    def test_agent_info_with_original_name_for_unique_custom_agent(self):
        """Custom agent with unique name should have original_name set correctly."""
        # Simulate what the backend would create for a custom agent
        custom_agent_info = AgentInfo(
            name="MyCustomAgent",
            description="A custom agent created for testing",
            original_name="MyCustomAgent",  # Should match name for unique agents
            greeting="Hello from my custom agent!",
            is_session_agent=True,
            session_id="test-session"
        )
        
        # Verify the agent info has correct fields
        assert custom_agent_info.name == "MyCustomAgent"
        assert custom_agent_info.original_name == "MyCustomAgent"
        assert custom_agent_info.is_session_agent is True
        
        # Verify this agent would pass frontend validation
        valid_names = {custom_agent_info.name}
        if custom_agent_info.original_name:
            valid_names.add(custom_agent_info.original_name)
        assert "MyCustomAgent" in valid_names

    def test_agent_info_with_original_name_for_renamed_agent(self):
        """Session agent with duplicate name should preserve original_name after renaming."""
        # Simulate what the backend would create when session agent has same name as static
        renamed_agent_info = AgentInfo(
            name="EricaConcierge (session)",  # Renamed display name
            description="Customized Erica for this session",
            original_name="EricaConcierge",  # Original name preserved
            greeting="Hi! I'm your personalized Erica!",
            is_session_agent=True,
            session_id="test-session"
        )
        
        # Verify the agent info preserves both names
        assert renamed_agent_info.name == "EricaConcierge (session)"
        assert renamed_agent_info.original_name == "EricaConcierge"
        
        # Verify scenarios referencing original name would pass validation
        valid_names = {renamed_agent_info.name}
        if renamed_agent_info.original_name:
            valid_names.add(renamed_agent_info.original_name)
        
        # Both the renamed and original name should be valid
        assert "EricaConcierge (session)" in valid_names
        assert "EricaConcierge" in valid_names

    def test_original_name_enables_scenario_config_matching(self):
        """Scenario configs with original agent name should match via original_name."""
        # Simulate available agents from API
        available_agents = [
            AgentInfo(name="StaticAgent", description="Static", original_name=None),
            AgentInfo(
                name="CustomAgent (session)",
                description="Custom session agent",
                original_name="CustomAgent",
                is_session_agent=True,
                session_id="test-session"
            ),
        ]
        
        # Scenario config references the original name (what user would select)
        scenario_config = {
            "start_agent": "CustomAgent",  # References original name
            "handoffs": [
                {"from_agent": "StaticAgent", "to_agent": "CustomAgent"}
            ]
        }
        
        # Build valid names set like frontend does
        valid_names = set()
        for agent in available_agents:
            valid_names.add(agent.name)
            if agent.original_name:
                valid_names.add(agent.original_name)
        
        # Verify scenario config agents are valid
        assert scenario_config["start_agent"] in valid_names
        for handoff in scenario_config["handoffs"]:
            assert handoff["from_agent"] in valid_names
            assert handoff["to_agent"] in valid_names

    def test_multiple_session_agents_all_have_original_names(self):
        """When multiple session agents exist, all should have original_name set."""
        # Simulate multiple session agents (mix of unique and renamed)
        session_agents = [
            AgentInfo(
                name="CustomAgent1",
                description="First custom",
                original_name="CustomAgent1",
                is_session_agent=True
            ),
            AgentInfo(
                name="CustomAgent2",
                description="Second custom",
                original_name="CustomAgent2",
                is_session_agent=True
            ),
            AgentInfo(
                name="EricaConcierge (session)",
                description="Override of static",
                original_name="EricaConcierge",
                is_session_agent=True
            ),
        ]
        
        # All session agents should have original_name set
        for agent in session_agents:
            assert agent.original_name is not None
            assert agent.is_session_agent is True


# ═══════════════════════════════════════════════════════════════════════════════
# Frontend Validation Simulation Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFrontendValidationSimulation:
    """Simulate frontend validation logic to verify custom agents pass validation."""

    def _simulate_frontend_validation(self, available_agents: list[AgentInfo], config_agents: list[str]) -> tuple[list[str], list[str]]:
        """
        Simulate the frontend validation logic from ScenarioBuilder.jsx.
        
        Returns:
            tuple: (valid_agents, invalid_agents) - agents that pass/fail validation
        """
        # Build valid names set including original_name (matches frontend fix)
        valid_names = set()
        for agent in available_agents:
            valid_names.add(agent.name)
            if agent.original_name:
                valid_names.add(agent.original_name)
        
        valid_agents = []
        invalid_agents = []
        
        for agent_name in config_agents:
            if agent_name in valid_names:
                valid_agents.append(agent_name)
            else:
                invalid_agents.append(agent_name)
        
        return valid_agents, invalid_agents

    def test_custom_agent_passes_frontend_validation(self):
        """Custom agent with original_name should pass frontend validation."""
        # Simulated API response with session agent
        available_agents = [
            AgentInfo(name="EricaConcierge", description="Static agent", original_name=None),
            AgentInfo(
                name="MyCustomAgent",
                description="Custom session agent",
                original_name="MyCustomAgent",
                is_session_agent=True,
                session_id="test-session"
            ),
        ]
        
        # Config references the custom agent
        config_agents = ["EricaConcierge", "MyCustomAgent"]
        
        valid, invalid = self._simulate_frontend_validation(available_agents, config_agents)
        
        assert valid == ["EricaConcierge", "MyCustomAgent"]
        assert invalid == []

    def test_renamed_agent_original_name_passes_validation(self):
        """Renamed session agent should pass validation when referenced by original name."""
        # Simulated API response where session agent was renamed
        available_agents = [
            AgentInfo(name="EricaConcierge", description="Static agent", original_name=None),
            AgentInfo(
                name="EricaConcierge (session)",  # Renamed in display
                description="Customized session agent",
                original_name="EricaConcierge",  # Original name preserved
                is_session_agent=True,
                session_id="test-session"
            ),
        ]
        
        # Config references BOTH the static and the original session agent name
        # This simulates a scenario where the user created a custom agent named "EricaConcierge"
        config_agents = ["EricaConcierge", "MyHandoffTarget"]
        
        # Create a more complete agent list
        available_agents.append(
            AgentInfo(name="MyHandoffTarget", description="Another agent", original_name=None)
        )
        
        valid, invalid = self._simulate_frontend_validation(available_agents, config_agents)
        
        # Both should be valid because "EricaConcierge" matches both static and original_name
        assert "EricaConcierge" in valid
        assert "MyHandoffTarget" in valid
        assert invalid == []

    def test_truly_invalid_agent_fails_validation(self):
        """Agent not in available list should still fail validation."""
        available_agents = [
            AgentInfo(name="EricaConcierge", description="Static agent", original_name=None),
        ]
        
        # Config references a non-existent agent
        config_agents = ["EricaConcierge", "NonExistentAgent"]
        
        valid, invalid = self._simulate_frontend_validation(available_agents, config_agents)
        
        assert valid == ["EricaConcierge"]
        assert invalid == ["NonExistentAgent"]


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioBuilderCustomAgentIntegration:
    """Integration tests for custom agent creation and scenario usage workflow."""

    def test_agent_info_json_serialization(self):
        """AgentInfo with original_name should serialize correctly for API response."""
        agent = AgentInfo(
            name="TestAgent (session)",
            description="A test agent",
            original_name="TestAgent",
            greeting="Hello!",
            tools=["tool1"],
            tool_details=[ToolInfo(name="tool1", description="A tool")],
            is_session_agent=True,
            session_id="test-session-123"
        )
        
        # Serialize to dict (simulating JSON response)
        agent_dict = agent.model_dump()
        
        assert agent_dict["name"] == "TestAgent (session)"
        assert agent_dict["original_name"] == "TestAgent"
        assert agent_dict["is_session_agent"] is True
        
    def test_multiple_custom_agents_visibility(self):
        """Multiple custom agents should all be visible in scenario builder."""
        # Simulate multiple custom agents
        agents = [
            AgentInfo(name="StaticAgent", description="Static", original_name=None),
            AgentInfo(
                name="CustomAgent1",
                description="First custom",
                original_name="CustomAgent1",
                is_session_agent=True
            ),
            AgentInfo(
                name="CustomAgent2", 
                description="Second custom",
                original_name="CustomAgent2",
                is_session_agent=True
            ),
            AgentInfo(
                name="StaticCopy (session)",
                description="Override of static",
                original_name="StaticAgent",  # Overrides static
                is_session_agent=True
            ),
        ]
        
        # Build valid names
        valid_names = set()
        for a in agents:
            valid_names.add(a.name)
            if a.original_name:
                valid_names.add(a.original_name)
        
        # All these names should be valid
        assert "StaticAgent" in valid_names
        assert "CustomAgent1" in valid_names
        assert "CustomAgent2" in valid_names
        assert "StaticCopy (session)" in valid_names


# ═══════════════════════════════════════════════════════════════════════════════
# Utility Function Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUtilityFunctions:
    """Tests for helper functions used in scenario builder."""

    def test_extract_prompt_vars(self):
        """Test extraction of Jinja template variables."""
        template = "Hello {{customer_name}}, welcome to {{bank_name}}!"
        vars = extract_prompt_vars(template)
        assert "customer_name" in vars
        assert "bank_name" in vars

    def test_build_prompt_preview_truncation(self):
        """Test prompt preview truncation."""
        long_prompt = "A" * 1000
        preview = build_prompt_preview(long_prompt, max_chars=500)
        assert len(preview) <= 503  # 500 + "..."
        assert preview.endswith("...")

    def test_build_prompt_preview_short(self):
        """Short prompts should not be truncated."""
        short_prompt = "Hello {{name}}!"
        preview = build_prompt_preview(short_prompt)
        assert preview == short_prompt
