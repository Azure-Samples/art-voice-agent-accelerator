"""
Tests for HandoffService
=========================

Unit tests for the unified handoff resolution service.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.artagent.backend.voice.shared.handoff_service import (
    HandoffResolution,
    HandoffService,
    create_handoff_service,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_agent():
    """Create a mock UnifiedAgent."""
    agent = MagicMock()
    agent.name = "FraudAgent"
    agent.render_greeting.return_value = "Hi, I'm the fraud specialist. How can I help?"
    agent.render_return_greeting.return_value = "Welcome back! Let me continue helping you."
    return agent


@pytest.fixture
def mock_agents(mock_agent):
    """Create a mock agent registry."""
    concierge = MagicMock()
    concierge.name = "Concierge"
    concierge.render_greeting.return_value = "Hello! I'm your concierge."
    concierge.render_return_greeting.return_value = "Welcome back!"

    return {
        "Concierge": concierge,
        "FraudAgent": mock_agent,
        "InvestmentAdvisor": MagicMock(name="InvestmentAdvisor"),
    }


@pytest.fixture
def handoff_map():
    """Standard handoff map for testing."""
    return {
        "handoff_fraud": "FraudAgent",
        "handoff_investment": "InvestmentAdvisor",
        "handoff_concierge": "Concierge",
    }


@pytest.fixture
def service(mock_agents, handoff_map):
    """Create a HandoffService instance for testing."""
    return HandoffService(
        scenario_name="banking",
        handoff_map=handoff_map,
        agents=mock_agents,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HANDOFF DETECTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsHandoff:
    """Tests for is_handoff() method."""

    def test_handoff_tool_detected(self, service):
        """Handoff tools should be detected via registry."""
        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.registry_is_handoff_tool"
        ) as mock_check:
            mock_check.return_value = True
            assert service.is_handoff("handoff_fraud") is True
            mock_check.assert_called_once_with("handoff_fraud")

    def test_non_handoff_tool(self, service):
        """Non-handoff tools should return False."""
        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.registry_is_handoff_tool"
        ) as mock_check:
            mock_check.return_value = False
            assert service.is_handoff("search_accounts") is False


# ═══════════════════════════════════════════════════════════════════════════════
# TARGET RESOLUTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetHandoffTarget:
    """Tests for get_handoff_target() method."""

    def test_target_found(self, service):
        """Should return target agent from handoff map."""
        assert service.get_handoff_target("handoff_fraud") == "FraudAgent"

    def test_target_not_found(self, service):
        """Should return None for unknown tool."""
        assert service.get_handoff_target("unknown_tool") is None


# ═══════════════════════════════════════════════════════════════════════════════
# HANDOFF RESOLUTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveHandoff:
    """Tests for resolve_handoff() method."""

    def test_successful_resolution(self, service):
        """Should resolve handoff with all required fields."""
        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.get_handoff_config"
        ) as mock_config:
            mock_config.return_value = MagicMock(
                type="announced",
                share_context=True,
                greet_on_switch=True,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_fraud",
                tool_args={"reason": "fraud inquiry"},
                source_agent="Concierge",
                current_system_vars={"session_profile": {"name": "John"}},
                user_last_utterance="I think my card was stolen",
            )

            assert resolution.success is True
            assert resolution.target_agent == "FraudAgent"
            assert resolution.source_agent == "Concierge"
            assert resolution.tool_name == "handoff_fraud"
            assert resolution.greet_on_switch is True
            assert resolution.share_context is True
            assert resolution.handoff_type == "announced"

    def test_discrete_handoff_resolution(self, service):
        """Should respect discrete handoff type from scenario config."""
        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.get_handoff_config"
        ) as mock_config:
            mock_config.return_value = MagicMock(
                type="discrete",
                share_context=True,
                greet_on_switch=False,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_fraud",
                tool_args={"reason": "returning customer"},
                source_agent="Concierge",
                current_system_vars={},
            )

            assert resolution.success is True
            assert resolution.greet_on_switch is False
            assert resolution.handoff_type == "discrete"
            assert resolution.is_discrete is True
            assert resolution.is_announced is False

    def test_unknown_tool_fails(self, service):
        """Should fail if tool not in handoff map."""
        resolution = service.resolve_handoff(
            tool_name="unknown_handoff",
            tool_args={},
            source_agent="Concierge",
            current_system_vars={},
        )

        assert resolution.success is False
        assert resolution.error is not None
        assert "No target agent configured" in resolution.error

    def test_unknown_agent_fails(self, mock_agents, handoff_map):
        """Should fail if target agent not in registry."""
        # Add a handoff to non-existent agent
        handoff_map["handoff_unknown"] = "NonExistentAgent"

        service = HandoffService(
            scenario_name="banking",
            handoff_map=handoff_map,
            agents=mock_agents,
        )

        resolution = service.resolve_handoff(
            tool_name="handoff_unknown",
            tool_args={},
            source_agent="Concierge",
            current_system_vars={},
        )

        assert resolution.success is False
        assert resolution.target_agent == "NonExistentAgent"
        assert "not found in registry" in resolution.error

    def test_system_vars_built_correctly(self, service):
        """Should build system_vars with handoff context."""
        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.get_handoff_config"
        ) as mock_config:
            mock_config.return_value = MagicMock(
                type="announced",
                share_context=True,
                greet_on_switch=True,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_fraud",
                tool_args={"reason": "fraud inquiry"},
                source_agent="Concierge",
                current_system_vars={
                    "session_profile": {"name": "John"},
                    "client_id": "12345",
                },
                user_last_utterance="I think my card was stolen",
            )

            assert resolution.success is True
            system_vars = resolution.system_vars

            # Should have handoff context
            assert system_vars.get("previous_agent") == "Concierge"
            assert system_vars.get("active_agent") == "FraudAgent"
            assert system_vars.get("is_handoff") is True


# ═══════════════════════════════════════════════════════════════════════════════
# GREETING SELECTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelectGreeting:
    """Tests for select_greeting() method."""

    def test_first_visit_greeting(self, service, mock_agent):
        """Should use agent's greeting template for first visit."""
        greeting = service.select_greeting(
            agent=mock_agent,
            is_first_visit=True,
            greet_on_switch=True,
            system_vars={"caller_name": "John"},
        )

        assert greeting is not None
        mock_agent.render_greeting.assert_called_once()

    def test_return_greeting(self, service, mock_agent):
        """Should use agent's return_greeting template for repeat visit."""
        greeting = service.select_greeting(
            agent=mock_agent,
            is_first_visit=False,
            greet_on_switch=True,
            system_vars={},
        )

        assert greeting is not None
        mock_agent.render_return_greeting.assert_called_once()

    def test_discrete_handoff_no_greeting(self, service, mock_agent):
        """Discrete handoffs should not produce a greeting."""
        greeting = service.select_greeting(
            agent=mock_agent,
            is_first_visit=True,
            greet_on_switch=False,  # Discrete
            system_vars={},
        )

        assert greeting is None
        mock_agent.render_greeting.assert_not_called()

    def test_explicit_greeting_override(self, service, mock_agent):
        """Explicit greeting in system_vars should override template."""
        greeting = service.select_greeting(
            agent=mock_agent,
            is_first_visit=True,
            greet_on_switch=True,
            system_vars={"greeting": "Custom greeting message"},
        )

        assert greeting == "Custom greeting message"
        mock_agent.render_greeting.assert_not_called()

    def test_session_overrides_greeting(self, service, mock_agent):
        """Greeting from session_overrides should be used."""
        greeting = service.select_greeting(
            agent=mock_agent,
            is_first_visit=True,
            greet_on_switch=True,
            system_vars={"session_overrides": {"greeting": "Override greeting"}},
        )

        assert greeting == "Override greeting"


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateHandoffService:
    """Tests for create_handoff_service() factory function."""

    def test_creates_with_explicit_args(self, mock_agents, handoff_map):
        """Should create service with explicitly provided arguments."""
        service = create_handoff_service(
            scenario_name="banking",
            agents=mock_agents,
            handoff_map=handoff_map,
        )

        assert service.scenario_name == "banking"
        assert service.handoff_map == handoff_map

    def test_creates_without_agents(self):
        """Should create service even when agent discovery fails."""
        # When agents can't be loaded, service should still be created
        # with empty agents dict
        service = create_handoff_service(
            scenario_name="test",
            agents=None,
            handoff_map={"test_tool": "TestAgent"},
        )

        # Should have the provided handoff_map
        assert service.handoff_map == {"test_tool": "TestAgent"}
        # Scenario should be set
        assert service.scenario_name == "test"


# ═══════════════════════════════════════════════════════════════════════════════
# HANDOFF RESOLUTION DATACLASS TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandoffResolution:
    """Tests for HandoffResolution dataclass."""

    def test_is_discrete_property(self):
        """is_discrete should return True for discrete type."""
        resolution = HandoffResolution(
            success=True,
            handoff_type="discrete",
        )
        assert resolution.is_discrete is True
        assert resolution.is_announced is False

    def test_is_announced_property(self):
        """is_announced should return True for announced type."""
        resolution = HandoffResolution(
            success=True,
            handoff_type="announced",
        )
        assert resolution.is_discrete is False
        assert resolution.is_announced is True

    def test_default_values(self):
        """Should have sensible defaults."""
        resolution = HandoffResolution(success=True)

        assert resolution.target_agent == ""
        assert resolution.source_agent == ""
        assert resolution.system_vars == {}
        assert resolution.greet_on_switch is True
        assert resolution.share_context is True
        assert resolution.handoff_type == "announced"
        assert resolution.error is None


# ═══════════════════════════════════════════════════════════════════════════════
# GENERIC HANDOFF TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenericHandoff:
    """Tests for generic handoff_to_agent functionality."""

    @pytest.fixture
    def mock_agents_for_generic(self):
        """Create agents for generic handoff testing."""
        return {
            "Concierge": MagicMock(name="Concierge"),
            "FraudAgent": MagicMock(name="FraudAgent"),
            "InvestmentAdvisor": MagicMock(name="InvestmentAdvisor"),
            "CardRecommendation": MagicMock(name="CardRecommendation"),
        }

    @pytest.fixture
    def service_with_generic(self, mock_agents_for_generic):
        """Create service with generic handoff enabled."""
        return HandoffService(
            scenario_name="banking",
            handoff_map={},  # No explicit mappings
            agents=mock_agents_for_generic,
        )

    def test_generic_handoff_with_scenario_enabled(self, mock_agents_for_generic):
        """Should resolve generic handoff when scenario allows it."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            HandoffConfig,
            ScenarioConfig,
        )

        # Create a mock scenario with generic handoffs enabled
        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent", "InvestmentAdvisor"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                allowed_targets=[],  # All scenario agents allowed
                default_type="discrete",
                share_context=True,
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_for_generic,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "fraud inquiry"},
                source_agent="Concierge",
                current_system_vars={},
            )

            assert resolution.success is True
            assert resolution.target_agent == "FraudAgent"
            assert resolution.handoff_type == "discrete"
            assert resolution.share_context is True

    def test_generic_handoff_fails_when_disabled(self, mock_agents_for_generic):
        """Should fail if scenario has generic handoffs disabled."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(enabled=False),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_for_generic,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={},
            )

            assert resolution.success is False
            assert "not allowed" in resolution.error

    def test_generic_handoff_with_allowed_targets(self, mock_agents_for_generic):
        """Should only allow targets in allowed_targets list."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent", "InvestmentAdvisor"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                allowed_targets=["FraudAgent"],  # Only FraudAgent allowed
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_for_generic,
            )

            # Should succeed for allowed target
            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={},
            )
            assert resolution.success is True

            # Should fail for non-allowed target
            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "InvestmentAdvisor", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={},
            )
            assert resolution.success is False
            assert "not allowed" in resolution.error

    def test_generic_handoff_missing_target_agent(self, mock_agents_for_generic):
        """Should fail if target_agent not provided."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(enabled=True),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_for_generic,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"reason": "test"},  # Missing target_agent
                source_agent="Concierge",
                current_system_vars={},
            )

            assert resolution.success is False
            assert "target_agent" in resolution.error

    def test_generic_handoff_target_not_in_registry(self, mock_agents_for_generic):
        """Should fail if target agent not in agent registry."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent", "NonExistent"],
            generic_handoff=GenericHandoffConfig(enabled=True),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_for_generic,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "NonExistent", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={},
            )

            assert resolution.success is False
            assert "not found in registry" in resolution.error

    def test_generic_handoff_no_scenario(self, mock_agents_for_generic):
        """Should fail if no scenario configured."""
        service = HandoffService(
            scenario_name=None,  # No scenario
            handoff_map={},
            agents=mock_agents_for_generic,
        )

        resolution = service.resolve_handoff(
            tool_name="handoff_to_agent",
            tool_args={"target_agent": "FraudAgent", "reason": "test"},
            source_agent="Concierge",
            current_system_vars={},
        )

        assert resolution.success is False
        assert "not allowed" in resolution.error

    def test_generic_handoff_extracts_target_from_tool_result(
        self, mock_agents_for_generic
    ):
        """Should extract target from tool_result if not in args."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(enabled=True),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_for_generic,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"reason": "test"},  # No target in args
                source_agent="Concierge",
                current_system_vars={},
                tool_result={"target_agent": "FraudAgent"},  # Target in result
            )

            assert resolution.success is True
            assert resolution.target_agent == "FraudAgent"


# ═══════════════════════════════════════════════════════════════════════════════
# GENERIC HANDOFF BEHAVIOR TESTS (DISCRETE vs ANNOUNCED)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenericHandoffBehavior:
    """Tests for generic handoff discrete/announced behavior based on scenario config."""

    @pytest.fixture
    def mock_agents_with_greetings(self):
        """Create agents with greeting templates."""
        concierge = MagicMock(name="Concierge")
        concierge.render_greeting.return_value = "Hello! I'm your concierge."
        concierge.render_return_greeting.return_value = "Welcome back to concierge!"

        fraud_agent = MagicMock(name="FraudAgent")
        fraud_agent.render_greeting.return_value = "Hi, I'm the fraud specialist."
        fraud_agent.render_return_greeting.return_value = "Welcome back! Let me continue with fraud."

        investment = MagicMock(name="InvestmentAdvisor")
        investment.render_greeting.return_value = "Hello, I'm your investment advisor."
        investment.render_return_greeting.return_value = "Welcome back to investments!"

        return {
            "Concierge": concierge,
            "FraudAgent": fraud_agent,
            "InvestmentAdvisor": investment,
        }

    def test_discrete_handoff_no_greeting(self, mock_agents_with_greetings):
        """Discrete handoff should have greet_on_switch=False."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="discrete",  # DISCRETE handoff
                share_context=True,
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_with_greetings,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "fraud inquiry"},
                source_agent="Concierge",
                current_system_vars={},
            )

            # Discrete handoffs should NOT greet
            assert resolution.success is True
            assert resolution.handoff_type == "discrete"
            assert resolution.greet_on_switch is False
            assert resolution.is_discrete is True
            assert resolution.is_announced is False

            # Greeting selection should return None for discrete
            greeting = service.select_greeting(
                agent=mock_agents_with_greetings["FraudAgent"],
                is_first_visit=True,
                greet_on_switch=resolution.greet_on_switch,
                system_vars=resolution.system_vars,
            )
            assert greeting is None

    def test_announced_handoff_with_greeting(self, mock_agents_with_greetings):
        """Announced handoff should have greet_on_switch=True and return greeting."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="announced",  # ANNOUNCED handoff
                share_context=True,
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_with_greetings,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "fraud inquiry"},
                source_agent="Concierge",
                current_system_vars={},
            )

            # Announced handoffs SHOULD greet
            assert resolution.success is True
            assert resolution.handoff_type == "announced"
            assert resolution.greet_on_switch is True
            assert resolution.is_discrete is False
            assert resolution.is_announced is True

            # Greeting selection should return agent's greeting
            greeting = service.select_greeting(
                agent=mock_agents_with_greetings["FraudAgent"],
                is_first_visit=True,
                greet_on_switch=resolution.greet_on_switch,
                system_vars=resolution.system_vars,
            )
            assert greeting == "Hi, I'm the fraud specialist."

    def test_share_context_true_includes_context(self, mock_agents_with_greetings):
        """share_context=True should include context in system_vars."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="discrete",
                share_context=True,  # Share context
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_with_greetings,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "fraud detected"},
                source_agent="Concierge",
                current_system_vars={
                    "client_id": "12345",
                    "session_profile": {"name": "John"},
                },
                user_last_utterance="I think someone stole my card",
            )

            assert resolution.success is True
            assert resolution.share_context is True

            # System vars should include handoff context
            system_vars = resolution.system_vars
            assert system_vars.get("is_handoff") is True
            assert system_vars.get("share_context") is True
            assert system_vars.get("previous_agent") == "Concierge"
            assert system_vars.get("active_agent") == "FraudAgent"

    def test_share_context_false_limits_context(self, mock_agents_with_greetings):
        """share_context=False should be reflected in resolution."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="announced",
                share_context=False,  # Don't share context
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_with_greetings,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={"sensitive_data": "secret"},
            )

            assert resolution.success is True
            assert resolution.share_context is False
            assert resolution.system_vars.get("share_context") is False

    def test_return_greeting_for_revisit(self, mock_agents_with_greetings):
        """Should use return_greeting for non-first visits in announced mode."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="announced",
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_with_greetings,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "followup"},
                source_agent="Concierge",
                current_system_vars={},
            )

            # First visit greeting
            first_greeting = service.select_greeting(
                agent=mock_agents_with_greetings["FraudAgent"],
                is_first_visit=True,
                greet_on_switch=resolution.greet_on_switch,
                system_vars=resolution.system_vars,
            )
            assert first_greeting == "Hi, I'm the fraud specialist."

            # Return visit greeting
            return_greeting = service.select_greeting(
                agent=mock_agents_with_greetings["FraudAgent"],
                is_first_visit=False,  # Not first visit
                greet_on_switch=resolution.greet_on_switch,
                system_vars=resolution.system_vars,
            )
            assert return_greeting == "Welcome back! Let me continue with fraud."

    def test_explicit_greeting_override(self, mock_agents_with_greetings):
        """Explicit greeting in system_vars should override agent greeting."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="announced",
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={},
                agents=mock_agents_with_greetings,
            )

            # Custom greeting should override agent's greeting
            custom_greeting = "Custom greeting from handoff context"
            greeting = service.select_greeting(
                agent=mock_agents_with_greetings["FraudAgent"],
                is_first_visit=True,
                greet_on_switch=True,
                system_vars={"greeting": custom_greeting},
            )
            assert greeting == custom_greeting

    def test_mixed_scenario_explicit_vs_generic_handoffs(self, mock_agents_with_greetings):
        """Scenario with both explicit and generic handoffs should work correctly."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            HandoffConfig,
            ScenarioConfig,
        )

        mock_scenario = ScenarioConfig(
            name="test_scenario",
            agents=["Concierge", "FraudAgent", "InvestmentAdvisor"],
            handoffs=[
                # Explicit handoff: Concierge -> FraudAgent (announced)
                HandoffConfig(
                    from_agent="Concierge",
                    to_agent="FraudAgent",
                    tool="handoff_fraud",
                    type="announced",
                    share_context=True,
                ),
            ],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="discrete",  # Generic defaults to discrete
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="test_scenario",
                handoff_map={"handoff_fraud": "FraudAgent"},
                agents=mock_agents_with_greetings,
            )

            # Explicit handoff should use its config (announced)
            with patch(
                "apps.artagent.backend.voice.shared.handoff_service.get_handoff_config"
            ) as mock_config:
                mock_config.return_value = MagicMock(
                    type="announced",
                    share_context=True,
                    greet_on_switch=True,
                )

                explicit_resolution = service.resolve_handoff(
                    tool_name="handoff_fraud",
                    tool_args={"reason": "fraud detected"},
                    source_agent="Concierge",
                    current_system_vars={},
                )

                assert explicit_resolution.success is True
                assert explicit_resolution.handoff_type == "announced"
                assert explicit_resolution.greet_on_switch is True

            # Generic handoff should use generic config (discrete)
            generic_resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "InvestmentAdvisor", "reason": "investment inquiry"},
                source_agent="Concierge",
                current_system_vars={},
            )

            assert generic_resolution.success is True
            assert generic_resolution.handoff_type == "discrete"
            assert generic_resolution.greet_on_switch is False


class TestGenericHandoffConfigDataclass:
    """Tests for GenericHandoffConfig dataclass and methods."""

    def test_from_dict_with_all_fields(self):
        """Should parse all fields from dictionary."""
        from apps.artagent.backend.registries.scenariostore.loader import GenericHandoffConfig

        data = {
            "enabled": True,
            "allowed_targets": ["Agent1", "Agent2"],
            "require_client_id": True,
            "default_type": "discrete",
            "share_context": False,
        }

        config = GenericHandoffConfig.from_dict(data)

        assert config.enabled is True
        assert config.allowed_targets == ["Agent1", "Agent2"]
        assert config.require_client_id is True
        assert config.default_type == "discrete"
        assert config.share_context is False

    def test_from_dict_with_defaults(self):
        """Should use defaults for missing fields."""
        from apps.artagent.backend.registries.scenariostore.loader import GenericHandoffConfig

        config = GenericHandoffConfig.from_dict({})

        assert config.enabled is False
        assert config.allowed_targets == []
        assert config.require_client_id is False
        assert config.default_type == "announced"
        assert config.share_context is True

    def test_from_dict_with_none(self):
        """Should handle None input."""
        from apps.artagent.backend.registries.scenariostore.loader import GenericHandoffConfig

        config = GenericHandoffConfig.from_dict(None)

        assert config.enabled is False
        assert config.allowed_targets == []

    def test_is_target_allowed_when_disabled(self):
        """Should return False when disabled."""
        from apps.artagent.backend.registries.scenariostore.loader import GenericHandoffConfig

        config = GenericHandoffConfig(enabled=False)

        assert config.is_target_allowed("AnyAgent", ["AnyAgent"]) is False

    def test_is_target_allowed_with_allowed_targets(self):
        """Should check against allowed_targets list."""
        from apps.artagent.backend.registries.scenariostore.loader import GenericHandoffConfig

        config = GenericHandoffConfig(
            enabled=True,
            allowed_targets=["AllowedAgent"],
        )

        assert config.is_target_allowed("AllowedAgent", []) is True
        assert config.is_target_allowed("NotAllowedAgent", []) is False

    def test_is_target_allowed_with_empty_allowed_targets(self):
        """Should allow any scenario agent when allowed_targets is empty."""
        from apps.artagent.backend.registries.scenariostore.loader import GenericHandoffConfig

        config = GenericHandoffConfig(
            enabled=True,
            allowed_targets=[],  # Empty = all scenario agents
        )

        scenario_agents = ["Agent1", "Agent2", "Agent3"]

        assert config.is_target_allowed("Agent1", scenario_agents) is True
        assert config.is_target_allowed("Agent2", scenario_agents) is True
        assert config.is_target_allowed("NotInScenario", scenario_agents) is False


class TestScenarioConfigGenericHandoff:
    """Tests for ScenarioConfig.get_generic_handoff_config method."""

    def test_get_generic_handoff_config_enabled(self):
        """Should return HandoffConfig when generic handoffs are enabled."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        scenario = ScenarioConfig(
            name="test",
            agents=["Agent1", "Agent2"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="discrete",
                share_context=False,
            ),
        )

        config = scenario.get_generic_handoff_config("Agent1", "Agent2")

        assert config is not None
        assert config.from_agent == "Agent1"
        assert config.to_agent == "Agent2"
        assert config.tool == "handoff_to_agent"
        assert config.type == "discrete"
        assert config.share_context is False

    def test_get_generic_handoff_config_disabled(self):
        """Should return None when generic handoffs are disabled."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        scenario = ScenarioConfig(
            name="test",
            agents=["Agent1", "Agent2"],
            generic_handoff=GenericHandoffConfig(enabled=False),
        )

        config = scenario.get_generic_handoff_config("Agent1", "Agent2")

        assert config is None

    def test_get_generic_handoff_config_target_not_allowed(self):
        """Should return None when target is not in allowed_targets."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )

        scenario = ScenarioConfig(
            name="test",
            agents=["Agent1", "Agent2", "Agent3"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                allowed_targets=["Agent2"],  # Only Agent2 allowed
            ),
        )

        # Agent2 is allowed
        config = scenario.get_generic_handoff_config("Agent1", "Agent2")
        assert config is not None

        # Agent3 is not allowed
        config = scenario.get_generic_handoff_config("Agent1", "Agent3")
        assert config is None


