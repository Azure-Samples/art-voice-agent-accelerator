"""
Tests for Generic Handoff Tool (handoff_to_agent)
==================================================

Tests for the handoff_to_agent tool executor and its integration
with scenario configurations.
"""

from __future__ import annotations

import pytest

from apps.artagent.backend.registries.toolstore.handoffs import (
    handoff_to_agent,
    handoff_to_agent_schema,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandoffToAgentSchema:
    """Tests for the handoff_to_agent tool schema."""

    def test_schema_name(self):
        """Schema should have correct name."""
        assert handoff_to_agent_schema["name"] == "handoff_to_agent"

    def test_schema_has_required_parameters(self):
        """Schema should require target_agent and reason."""
        params = handoff_to_agent_schema["parameters"]
        assert params["type"] == "object"
        assert "target_agent" in params["required"]
        assert "reason" in params["required"]

    def test_schema_has_optional_parameters(self):
        """Schema should have context and client_id as optional."""
        props = handoff_to_agent_schema["parameters"]["properties"]
        assert "context" in props
        assert "client_id" in props
        # These should NOT be in required
        required = handoff_to_agent_schema["parameters"]["required"]
        assert "context" not in required
        assert "client_id" not in required

    def test_schema_description_mentions_silent_handoff(self):
        """Schema description should mention silent handoff behavior."""
        desc = handoff_to_agent_schema["description"]
        assert "IMPORTANT" in desc
        assert "target_agent" in desc.lower() or "target" in desc.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTOR TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandoffToAgentExecutor:
    """Tests for the handoff_to_agent async executor function."""

    @pytest.mark.asyncio
    async def test_successful_handoff(self):
        """Should return success payload with target_agent."""
        result = await handoff_to_agent({
            "target_agent": "FraudAgent",
            "reason": "Suspicious activity detected",
        })

        assert result["handoff"] is True
        assert result["target_agent"] == "FraudAgent"
        assert "handoff_summary" in result
        assert "Generic handoff" in result["handoff_summary"]
        assert "handoff_context" in result
        assert result["handoff_context"]["reason"] == "Suspicious activity detected"

    @pytest.mark.asyncio
    async def test_handoff_with_context(self):
        """Should include context summary in handoff_context."""
        result = await handoff_to_agent({
            "target_agent": "InvestmentAdvisor",
            "reason": "Retirement planning question",
            "context": "Customer asked about 401k rollover options",
        })

        assert result["handoff"] is True
        assert result["target_agent"] == "InvestmentAdvisor"
        assert result["handoff_context"]["context_summary"] == "Customer asked about 401k rollover options"

    @pytest.mark.asyncio
    async def test_handoff_with_client_id(self):
        """Should include client_id in handoff_context."""
        result = await handoff_to_agent({
            "target_agent": "CardRecommendation",
            "reason": "Card upgrade inquiry",
            "client_id": "CUST-12345",
        })

        assert result["handoff"] is True
        assert result["handoff_context"]["client_id"] == "CUST-12345"

    @pytest.mark.asyncio
    async def test_handoff_missing_target_agent(self):
        """Should fail if target_agent is missing."""
        result = await handoff_to_agent({
            "reason": "Some reason",
        })

        assert result["success"] is False
        assert "target_agent" in result["message"]

    @pytest.mark.asyncio
    async def test_handoff_empty_target_agent(self):
        """Should fail if target_agent is empty string."""
        result = await handoff_to_agent({
            "target_agent": "",
            "reason": "Some reason",
        })

        assert result["success"] is False
        assert "target_agent" in result["message"]

    @pytest.mark.asyncio
    async def test_handoff_whitespace_target_agent(self):
        """Should fail if target_agent is only whitespace."""
        result = await handoff_to_agent({
            "target_agent": "   ",
            "reason": "Some reason",
        })

        assert result["success"] is False
        assert "target_agent" in result["message"]

    @pytest.mark.asyncio
    async def test_handoff_missing_reason(self):
        """Should fail if reason is missing."""
        result = await handoff_to_agent({
            "target_agent": "FraudAgent",
        })

        assert result["success"] is False
        assert "reason" in result["message"]

    @pytest.mark.asyncio
    async def test_handoff_empty_reason(self):
        """Should fail if reason is empty string."""
        result = await handoff_to_agent({
            "target_agent": "FraudAgent",
            "reason": "",
        })

        assert result["success"] is False
        assert "reason" in result["message"]

    @pytest.mark.asyncio
    async def test_handoff_includes_timestamp(self):
        """Should include handoff_timestamp in context."""
        result = await handoff_to_agent({
            "target_agent": "FraudAgent",
            "reason": "Test reason",
        })

        assert "handoff_timestamp" in result["handoff_context"]

    @pytest.mark.asyncio
    async def test_handoff_message_is_empty(self):
        """Message should be empty for silent handoff."""
        result = await handoff_to_agent({
            "target_agent": "FraudAgent",
            "reason": "Test reason",
        })

        # Silent handoff - message should be empty
        assert result["message"] == ""

    @pytest.mark.asyncio
    async def test_handoff_strips_whitespace(self):
        """Should strip whitespace from target_agent and reason."""
        result = await handoff_to_agent({
            "target_agent": "  FraudAgent  ",
            "reason": "  Fraud detected  ",
        })

        assert result["handoff"] is True
        assert result["target_agent"] == "FraudAgent"
        assert result["handoff_context"]["reason"] == "Fraud detected"


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandoffToAgentRegistration:
    """Tests for handoff_to_agent tool registration."""

    def test_tool_is_registered(self):
        """handoff_to_agent should be registered in tool registry."""
        from apps.artagent.backend.registries.toolstore.registry import (
            get_tool_definition,
            is_handoff_tool,
        )

        defn = get_tool_definition("handoff_to_agent")
        assert defn is not None
        assert defn.name == "handoff_to_agent"

    def test_tool_is_marked_as_handoff(self):
        """handoff_to_agent should be marked as a handoff tool."""
        from apps.artagent.backend.registries.toolstore.registry import is_handoff_tool

        assert is_handoff_tool("handoff_to_agent") is True

    def test_tool_has_generic_tag(self):
        """handoff_to_agent should have 'generic' tag."""
        from apps.artagent.backend.registries.toolstore.registry import get_tool_definition

        defn = get_tool_definition("handoff_to_agent")
        assert defn is not None
        assert "generic" in defn.tags
        assert "handoff" in defn.tags


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenericHandoffIntegration:
    """Integration tests for generic handoff with scenario configurations."""

    @pytest.mark.asyncio
    async def test_end_to_end_generic_handoff_flow(self):
        """Test complete flow: tool execution -> HandoffService resolution."""
        from unittest.mock import MagicMock, patch

        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )
        from apps.artagent.backend.voice.shared.handoff_service import HandoffService

        # Step 1: Execute the tool (simulating LLM tool call)
        tool_result = await handoff_to_agent({
            "target_agent": "FraudAgent",
            "reason": "Customer reports unauthorized charge",
            "client_id": "CUST-123",
        })

        assert tool_result["handoff"] is True
        assert tool_result["target_agent"] == "FraudAgent"

        # Step 2: Configure scenario with generic handoffs enabled
        mock_scenario = ScenarioConfig(
            name="banking",
            agents=["Concierge", "FraudAgent", "InvestmentAdvisor"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="discrete",
                share_context=True,
            ),
        )

        mock_agents = {
            "Concierge": MagicMock(name="Concierge"),
            "FraudAgent": MagicMock(name="FraudAgent"),
            "InvestmentAdvisor": MagicMock(name="InvestmentAdvisor"),
        }

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="banking",
                handoff_map={},
                agents=mock_agents,
            )

            # Step 3: Resolve the handoff
            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={
                    "target_agent": "FraudAgent",
                    "reason": "Customer reports unauthorized charge",
                    "client_id": "CUST-123",
                },
                source_agent="Concierge",
                current_system_vars={"session_id": "sess-001"},
                tool_result=tool_result,
            )

            # Verify resolution
            assert resolution.success is True
            assert resolution.target_agent == "FraudAgent"
            assert resolution.source_agent == "Concierge"
            assert resolution.handoff_type == "discrete"
            assert resolution.greet_on_switch is False
            assert resolution.share_context is True

    @pytest.mark.asyncio
    async def test_generic_handoff_respects_allowed_targets(self):
        """Generic handoff should fail if target not in allowed list."""
        from unittest.mock import MagicMock, patch

        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )
        from apps.artagent.backend.voice.shared.handoff_service import HandoffService

        # Scenario only allows FraudAgent for generic handoffs
        mock_scenario = ScenarioConfig(
            name="restricted",
            agents=["Concierge", "FraudAgent", "InvestmentAdvisor"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                allowed_targets=["FraudAgent"],  # Only FraudAgent allowed
            ),
        )

        mock_agents = {
            "Concierge": MagicMock(),
            "FraudAgent": MagicMock(),
            "InvestmentAdvisor": MagicMock(),
        }

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = mock_scenario

            service = HandoffService(
                scenario_name="restricted",
                handoff_map={},
                agents=mock_agents,
            )

            # Should succeed for allowed target
            result = await handoff_to_agent({
                "target_agent": "FraudAgent",
                "reason": "Allowed target",
            })
            assert result["handoff"] is True

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "FraudAgent", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={},
                tool_result=result,
            )
            assert resolution.success is True

            # Should fail for non-allowed target
            result = await handoff_to_agent({
                "target_agent": "InvestmentAdvisor",
                "reason": "Not allowed target",
            })
            assert result["handoff"] is True  # Tool itself succeeds

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "InvestmentAdvisor", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={},
                tool_result=result,
            )
            # But resolution should fail because target not allowed
            assert resolution.success is False
            assert "not allowed" in resolution.error

    @pytest.mark.asyncio
    async def test_announced_vs_discrete_greeting_behavior(self):
        """Verify greeting is used for announced and skipped for discrete."""
        from unittest.mock import MagicMock, patch

        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            ScenarioConfig,
        )
        from apps.artagent.backend.voice.shared.handoff_service import HandoffService

        mock_agent = MagicMock()
        mock_agent.render_greeting.return_value = "Hello from the agent!"
        mock_agent.render_return_greeting.return_value = "Welcome back!"

        mock_agents = {
            "Concierge": MagicMock(),
            "TargetAgent": mock_agent,
        }

        # Test DISCRETE scenario
        discrete_scenario = ScenarioConfig(
            name="discrete_test",
            agents=["Concierge", "TargetAgent"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="discrete",
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = discrete_scenario

            service = HandoffService(
                scenario_name="discrete_test",
                handoff_map={},
                agents=mock_agents,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "TargetAgent", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={},
            )

            # Discrete should NOT have greeting
            greeting = service.select_greeting(
                agent=mock_agent,
                is_first_visit=True,
                greet_on_switch=resolution.greet_on_switch,
                system_vars=resolution.system_vars,
            )
            assert greeting is None

        # Test ANNOUNCED scenario
        announced_scenario = ScenarioConfig(
            name="announced_test",
            agents=["Concierge", "TargetAgent"],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="announced",
            ),
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.load_scenario"
        ) as mock_load:
            mock_load.return_value = announced_scenario

            service = HandoffService(
                scenario_name="announced_test",
                handoff_map={},
                agents=mock_agents,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_to_agent",
                tool_args={"target_agent": "TargetAgent", "reason": "test"},
                source_agent="Concierge",
                current_system_vars={},
            )

            # Announced SHOULD have greeting
            greeting = service.select_greeting(
                agent=mock_agent,
                is_first_visit=True,
                greet_on_switch=resolution.greet_on_switch,
                system_vars=resolution.system_vars,
            )
            assert greeting == "Hello from the agent!"
