"""
Scenario Orchestration Contract Tests
======================================

These tests ensure key functional contracts are preserved during the 
layer consolidation refactoring (see docs/proposals/scenario-orchestration-simplification.md).

The tests cover:
1. UnifiedAgent functional contracts (prompts, tools, greetings)
2. VoiceLiveAgentAdapter functional contracts (session building, voice payload)
3. Config resolution contracts (scenario → agents → orchestrator)
4. Handoff state unification contracts

These tests should pass BEFORE and AFTER the refactoring to ensure no regression.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_agent_yaml() -> dict[str, Any]:
    """Sample agent YAML configuration."""
    return {
        "name": "TestAgent",
        "description": "A test agent for contract verification",
        "greeting": "Hello {{ caller_name | default('there') }}, I'm {{ agent_name }}!",
        "return_greeting": "Welcome back, {{ caller_name | default('friend') }}!",
        "handoff": {
            "trigger": "handoff_test_agent",
            "is_entry_point": False,
        },
        "model": {
            "deployment_id": "gpt-4o",
            "temperature": 0.7,
        },
        "voice": {
            "name": "en-US-JennyNeural",
            "type": "azure-standard",
            "style": "friendly",
        },
        "prompt_template": (
            "You are {{ agent_name }}, an assistant at {{ institution_name }}. "
            "The caller is {{ caller_name | default('a customer') }}."
        ),
        "tool_names": ["check_balance", "handoff_concierge"],
        "template_vars": {
            "institution_name": "Test Bank",
        },
        "session": {
            "modalities": ["TEXT", "AUDIO"],
            "input_audio_format": "PCM16",
            "output_audio_format": "PCM16",
            "turn_detection": {
                "type": "semantic",
                "threshold": 0.5,
                "silence_duration_ms": 500,
            },
        },
    }


@pytest.fixture
def unified_agent(sample_agent_yaml):
    """Create a UnifiedAgent from sample YAML."""
    from apps.artagent.backend.registries.agentstore.base import (
        HandoffConfig,
        ModelConfig,
        UnifiedAgent,
        VoiceConfig,
    )

    return UnifiedAgent(
        name=sample_agent_yaml["name"],
        description=sample_agent_yaml["description"],
        greeting=sample_agent_yaml["greeting"],
        return_greeting=sample_agent_yaml["return_greeting"],
        handoff=HandoffConfig.from_dict(sample_agent_yaml["handoff"]),
        model=ModelConfig.from_dict(sample_agent_yaml["model"]),
        voice=VoiceConfig.from_dict(sample_agent_yaml["voice"]),
        prompt_template=sample_agent_yaml["prompt_template"],
        tool_names=sample_agent_yaml["tool_names"],
        template_vars=sample_agent_yaml["template_vars"],
        session=sample_agent_yaml.get("session", {}),
    )


@pytest.fixture
def multi_agent_registry():
    """Create a multi-agent registry for orchestrator tests."""
    from apps.artagent.backend.registries.agentstore.base import (
        HandoffConfig,
        ModelConfig,
        UnifiedAgent,
        VoiceConfig,
    )

    return {
        "Concierge": UnifiedAgent(
            name="Concierge",
            description="Main entry point agent",
            greeting="Hello, I'm your concierge!",
            return_greeting="Welcome back!",
            handoff=HandoffConfig(trigger="handoff_concierge", is_entry_point=True),
            model=ModelConfig(deployment_id="gpt-4o", temperature=0.7),
            voice=VoiceConfig(name="en-US-JennyNeural"),
            prompt_template="You are the Concierge. Help {{ caller_name | default('the customer') }}.",
            tool_names=["get_account_info", "handoff_fraud_agent", "handoff_to_agent"],
        ),
        "FraudAgent": UnifiedAgent(
            name="FraudAgent",
            description="Fraud detection specialist",
            greeting="Hi, I'm the fraud specialist. How can I help?",
            return_greeting="Let me continue helping with fraud concerns.",
            handoff=HandoffConfig(trigger="handoff_fraud_agent"),
            model=ModelConfig(deployment_id="gpt-4o", temperature=0.5),
            voice=VoiceConfig(name="en-US-GuyNeural", style="serious"),
            prompt_template="You are the FraudAgent. Analyze transactions for {{ caller_name }}.",
            tool_names=["analyze_transactions", "block_card", "handoff_concierge"],
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT 1: UnifiedAgent Functional Contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnifiedAgentPromptRendering:
    """
    CONTRACT: UnifiedAgent.render_prompt() must:
    1. Render Jinja2 templates with provided context
    2. Apply default values for missing template vars
    3. Use template_vars as base, then override with runtime context
    4. Filter out None values from context
    """

    def test_renders_template_with_context(self, unified_agent):
        """Prompt should render with provided context values."""
        context = {
            "caller_name": "John",
            "agent_name": "TestAgent",
            "institution_name": "Contoso Bank",
        }
        result = unified_agent.render_prompt(context)

        assert "John" in result
        assert "TestAgent" in result
        assert "Contoso Bank" in result

    def test_uses_template_vars_as_base(self, unified_agent):
        """template_vars should be used as base values."""
        # No runtime context - should use template_vars
        result = unified_agent.render_prompt({})

        # template_vars has institution_name="Test Bank"
        assert "Test Bank" in result

    def test_runtime_context_overrides_template_vars(self, unified_agent):
        """Runtime context should override template_vars."""
        context = {"institution_name": "Runtime Bank"}
        result = unified_agent.render_prompt(context)

        assert "Runtime Bank" in result
        assert "Test Bank" not in result

    def test_filters_none_values(self, unified_agent):
        """None values in context should be filtered out."""
        context = {
            "caller_name": None,  # Should be filtered
            "institution_name": "Valid Bank",
        }
        result = unified_agent.render_prompt(context)

        # Should use default for caller_name since None was filtered
        assert "a customer" in result or "the customer" in result or "customer" in result
        assert "Valid Bank" in result


class TestUnifiedAgentGreetingRendering:
    """
    CONTRACT: UnifiedAgent greeting methods must:
    1. render_greeting() renders the greeting template
    2. render_return_greeting() renders the return greeting template
    3. Both use _get_greeting_context() for consistent context building
    4. Return None if no greeting configured
    """

    def test_render_greeting_with_context(self, unified_agent):
        """Greeting should render with caller name."""
        greeting = unified_agent.render_greeting({"caller_name": "Alice"})

        assert greeting is not None
        assert "Alice" in greeting
        assert "TestAgent" in greeting

    def test_render_greeting_with_defaults(self, unified_agent):
        """Greeting should use Jinja2 defaults for missing vars."""
        greeting = unified_agent.render_greeting({})

        assert greeting is not None
        assert "there" in greeting  # default from template

    def test_render_return_greeting(self, unified_agent):
        """Return greeting should render correctly."""
        greeting = unified_agent.render_return_greeting({"caller_name": "Bob"})

        assert greeting is not None
        assert "Bob" in greeting

    def test_no_greeting_returns_none(self):
        """Agent with no greeting should return None."""
        from apps.artagent.backend.registries.agentstore.base import UnifiedAgent

        agent = UnifiedAgent(name="NoGreeting", greeting="")
        assert agent.render_greeting() is None

    def test_greeting_context_filters_none(self, unified_agent):
        """Greeting context should filter None values."""
        context = unified_agent._get_greeting_context({"caller_name": None})

        # None value should not be in context
        assert context.get("caller_name") != None or "caller_name" not in context


class TestUnifiedAgentToolRetrieval:
    """
    CONTRACT: UnifiedAgent.get_tools() must:
    1. Return OpenAI-compatible tool schemas
    2. Only return tools listed in tool_names
    3. Each schema has type="function" and function dict
    """

    def test_get_tools_returns_schemas(self, unified_agent):
        """get_tools() should return tool schemas."""
        with patch("apps.artagent.backend.registries.toolstore.initialize_tools"):
            with patch(
                "apps.artagent.backend.registries.toolstore.get_tools_for_agent"
            ) as mock_get:
                mock_get.return_value = [
                    {
                        "type": "function",
                        "function": {
                            "name": "check_balance",
                            "description": "Check account balance",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ]

                tools = unified_agent.get_tools()

                assert len(tools) == 1
                assert tools[0]["type"] == "function"
                assert tools[0]["function"]["name"] == "check_balance"
                mock_get.assert_called_once_with(unified_agent.tool_names)


class TestUnifiedAgentHandoffHelpers:
    """
    CONTRACT: UnifiedAgent handoff helpers must:
    1. get_handoff_tools() returns tools starting with "handoff_"
    2. is_handoff_target() checks if tool routes TO this agent
    3. handoff.trigger is accessible via handoff_trigger property
    """

    def test_get_handoff_tools(self, unified_agent):
        """Should return only handoff tools from tool_names."""
        handoff_tools = unified_agent.get_handoff_tools()

        assert len(handoff_tools) == 1
        assert "handoff_concierge" in handoff_tools
        assert "check_balance" not in handoff_tools

    def test_is_handoff_target(self, unified_agent):
        """Should detect if tool routes to this agent."""
        assert unified_agent.is_handoff_target("handoff_test_agent") is True
        assert unified_agent.is_handoff_target("handoff_other") is False

    def test_handoff_trigger_property(self, unified_agent):
        """handoff_trigger property should match handoff.trigger."""
        assert unified_agent.handoff_trigger == unified_agent.handoff.trigger
        assert unified_agent.handoff_trigger == "handoff_test_agent"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT 2: VoiceLiveAgentAdapter Functional Contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoiceLiveAgentAdapterConstruction:
    """
    CONTRACT: VoiceLiveAgentAdapter must:
    1. Parse session config for modalities, audio formats
    2. Build VAD configuration from turn_detection settings
    3. Passthrough properties to underlying UnifiedAgent
    
    NOTE: These contracts will need to be preserved when we merge
    VoiceLiveAgentAdapter into UnifiedAgent.
    """

    def test_parses_modalities(self, unified_agent):
        """Should parse modalities from session config."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        adapter = VoiceLiveAgentAdapter(unified_agent)

        # Should have parsed modalities
        assert len(adapter.modalities) == 2

    def test_passthrough_properties(self, unified_agent):
        """Should passthrough name, description from underlying agent."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        adapter = VoiceLiveAgentAdapter(unified_agent)

        assert adapter.name == unified_agent.name
        assert adapter.description == unified_agent.description
        assert adapter.voice_name == unified_agent.voice.name

    def test_greeting_passthrough(self, unified_agent):
        """render_greeting should delegate to underlying agent."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        adapter = VoiceLiveAgentAdapter(unified_agent)

        greeting = adapter.render_greeting({"caller_name": "Test"})

        assert greeting is not None
        assert "Test" in greeting


class TestVoiceLiveAgentAdapterToolBuilding:
    """
    CONTRACT: VoiceLiveAgentAdapter.tools must:
    1. Build FunctionTool objects from UnifiedAgent.get_tools()
    2. Cache built tools (only build once)
    3. Return empty list if VoiceLive SDK not available
    
    NOTE: This logic will move into UnifiedAgent.build_voicelive_tools()
    """

    def test_builds_function_tools(self, unified_agent):
        """Should build FunctionTool objects from tool schemas."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        with patch.object(
            unified_agent,
            "get_tools",
            return_value=[
                {
                    "type": "function",
                    "function": {
                        "name": "test_tool",
                        "description": "A test tool",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        ):
            adapter = VoiceLiveAgentAdapter(unified_agent)
            tools = adapter.tools

            assert len(tools) == 1
            assert tools[0].name == "test_tool"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT 3: Handoff Resolution Contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandoffServiceContracts:
    """
    CONTRACT: HandoffService must preserve these behaviors:
    1. resolve_handoff() returns HandoffResolution with all fields
    2. select_greeting() respects discrete vs announced type
    3. Handoff map correctly maps tool_name → agent_name
    4. Generic handoffs respect scenario config
    
    These are critical for the handoff state unification.
    """

    @pytest.fixture
    def handoff_service(self, multi_agent_registry):
        """Create HandoffService for testing."""
        from apps.artagent.backend.voice.shared.handoff_service import HandoffService

        handoff_map = {
            "handoff_concierge": "Concierge",
            "handoff_fraud_agent": "FraudAgent",
        }

        return HandoffService(
            scenario_name="test_scenario",
            handoff_map=handoff_map,
            agents=multi_agent_registry,
        )

    def test_resolve_handoff_returns_complete_resolution(
        self, handoff_service, multi_agent_registry
    ):
        """resolve_handoff should return HandoffResolution with all fields."""
        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.get_handoff_config"
        ) as mock_config:
            mock_config.return_value = MagicMock(
                type="announced",
                share_context=True,
                greet_on_switch=True,
            )

            resolution = handoff_service.resolve_handoff(
                tool_name="handoff_fraud_agent",
                tool_args={"reason": "fraud concern"},
                source_agent="Concierge",
                current_system_vars={"caller_name": "John"},
            )

            # Verify all required fields present
            assert resolution.success is True
            assert resolution.target_agent == "FraudAgent"
            assert resolution.source_agent == "Concierge"
            assert resolution.handoff_type == "announced"
            assert resolution.greet_on_switch is True
            assert "is_handoff" in resolution.system_vars

    def test_select_greeting_discrete_vs_announced(
        self, handoff_service, multi_agent_registry
    ):
        """
        CONTRACT: select_greeting must:
        - Return None for discrete handoffs (greet_on_switch=False)
        - Return rendered greeting for announced handoffs
        """
        agent = multi_agent_registry["FraudAgent"]

        # Discrete: no greeting
        discrete_greeting = handoff_service.select_greeting(
            agent=agent,
            is_first_visit=True,
            greet_on_switch=False,
            system_vars={},
        )
        assert discrete_greeting is None

        # Announced: should greet
        announced_greeting = handoff_service.select_greeting(
            agent=agent,
            is_first_visit=True,
            greet_on_switch=True,
            system_vars={},
        )
        assert announced_greeting is not None
        assert "fraud" in announced_greeting.lower()

    def test_get_handoff_target(self, handoff_service):
        """get_handoff_target should return correct target agent."""
        assert handoff_service.get_handoff_target("handoff_fraud_agent") == "FraudAgent"
        assert handoff_service.get_handoff_target("handoff_concierge") == "Concierge"
        assert handoff_service.get_handoff_target("unknown_tool") is None


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT 4: Scenario Config Contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioConfigContracts:
    """
    CONTRACT: ScenarioConfig must preserve:
    1. build_handoff_map() returns tool_name → agent_name mapping
    2. start_agent specifies the default starting agent
    3. Generic handoff config is accessible and correct
    """

    @pytest.fixture
    def scenario_config(self):
        """Create a ScenarioConfig for testing."""
        from apps.artagent.backend.registries.scenariostore.loader import (
            GenericHandoffConfig,
            HandoffConfig,
            ScenarioConfig,
        )

        return ScenarioConfig(
            name="test_banking",
            description="Test banking scenario",
            agents=["Concierge", "FraudAgent", "InvestmentAdvisor"],
            start_agent="Concierge",  # Entry agent is called start_agent
            handoffs=[
                HandoffConfig(
                    from_agent="Concierge",
                    to_agent="FraudAgent",
                    tool="handoff_fraud_agent",
                    type="announced",
                    share_context=True,
                ),
                HandoffConfig(
                    from_agent="Concierge",
                    to_agent="InvestmentAdvisor",
                    tool="handoff_investment",
                    type="discrete",
                    share_context=False,
                ),
            ],
            generic_handoff=GenericHandoffConfig(
                enabled=True,
                default_type="discrete",
                share_context=True,
            ),
        )

    def test_build_handoff_map(self, scenario_config):
        """build_handoff_map should return correct mapping."""
        handoff_map = scenario_config.build_handoff_map()

        assert handoff_map["handoff_fraud_agent"] == "FraudAgent"
        assert handoff_map["handoff_investment"] == "InvestmentAdvisor"

    def test_start_agent(self, scenario_config):
        """start_agent should specify the default starting agent."""
        # ScenarioConfig uses start_agent, not entry_agent
        assert scenario_config.start_agent == "Concierge"

    def test_generic_handoff_config_accessible(self, scenario_config):
        """Generic handoff config should be accessible."""
        assert scenario_config.generic_handoff is not None
        assert scenario_config.generic_handoff.enabled is True
        assert scenario_config.generic_handoff.default_type == "discrete"

    def test_get_generic_handoff_config_for_target(self, scenario_config):
        """get_generic_handoff_config should return HandoffConfig for valid target.
        
        When there's an explicit edge, it returns the edge configuration.
        When there's no explicit edge, it uses generic_handoff settings.
        """
        # FraudAgent has an explicit edge from Concierge - should use edge config
        config = scenario_config.get_generic_handoff_config("Concierge", "FraudAgent")
        assert config is not None
        assert config.to_agent == "FraudAgent"
        assert config.type == "announced"  # From explicit edge

        # InvestmentAdvisor has explicit edge with discrete type
        config = scenario_config.get_generic_handoff_config("Concierge", "InvestmentAdvisor")
        assert config is not None
        assert config.to_agent == "InvestmentAdvisor"
        assert config.type == "discrete"  # From explicit edge

    def test_get_generic_handoff_config_without_edge(self, scenario_config):
        """get_generic_handoff_config uses generic settings when no explicit edge."""
        # No edge from FraudAgent to Concierge - should use generic config
        config = scenario_config.get_generic_handoff_config("FraudAgent", "Concierge")
        assert config is not None
        assert config.to_agent == "Concierge"
        assert config.type == "discrete"  # From generic_handoff.default_type


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT 5: Config Resolution Path Contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfigResolutionContracts:
    """
    CONTRACT: Config resolution must preserve:
    1. Scenario name → loaded scenario config
    2. Scenario → filtered agents for that scenario
    3. Agents + scenario → handoff map
    4. Entry agent is correctly identified
    
    This tests the end-to-end config resolution path.
    """

    def test_scenario_filters_agents(self, multi_agent_registry):
        """Scenario should filter agents to only those in scenario.agents list."""
        from apps.artagent.backend.registries.scenariostore.loader import ScenarioConfig

        scenario = ScenarioConfig(
            name="test",
            agents=["Concierge"],  # Only Concierge
        )

        # Only Concierge should be included
        filtered = {
            name: agent
            for name, agent in multi_agent_registry.items()
            if name in scenario.agents
        }

        assert len(filtered) == 1
        assert "Concierge" in filtered
        assert "FraudAgent" not in filtered

    def test_agents_build_correct_handoff_map(self, multi_agent_registry):
        """build_handoff_map should use agent.handoff.trigger."""
        from apps.artagent.backend.registries.agentstore.base import build_handoff_map

        handoff_map = build_handoff_map(multi_agent_registry)

        assert handoff_map["handoff_concierge"] == "Concierge"
        assert handoff_map["handoff_fraud_agent"] == "FraudAgent"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT 6: Agent Visit Tracking Contracts (for greeting selection)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentVisitTrackingContracts:
    """
    CONTRACT: Agent visit tracking must preserve:
    1. First visit → render_greeting()
    2. Return visit → render_return_greeting()
    3. Visit tracking persists across handoffs
    
    This is critical for the layer consolidation to unify visit tracking.
    """

    def test_first_visit_gets_greeting(self, unified_agent):
        """First visit should use primary greeting."""
        greeting = unified_agent.render_greeting({"caller_name": "New Caller"})

        assert "Hello" in greeting
        assert "New Caller" in greeting

    def test_return_visit_gets_return_greeting(self, unified_agent):
        """Return visit should use return greeting."""
        greeting = unified_agent.render_return_greeting({"caller_name": "Returning"})

        assert "Welcome back" in greeting
        assert "Returning" in greeting


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT 7: Voice Payload Building Contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoicePayloadContracts:
    """
    CONTRACT: Voice payload building must preserve:
    1. Azure standard voices get correct payload structure
    2. Voice style, rate, pitch are applied correctly
    3. Fallback to default voice if none specified
    
    NOTE: This logic will move into UnifiedAgent when we merge the adapter.
    """

    def test_azure_standard_voice_payload(self, unified_agent):
        """Should build correct payload for azure-standard voice."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
            from azure.ai.voicelive.models import AzureStandardVoice
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        adapter = VoiceLiveAgentAdapter(unified_agent)
        payload = adapter._build_voice_payload()

        assert isinstance(payload, AzureStandardVoice)
        assert payload.name == "en-US-JennyNeural"

    def test_voice_style_applied(self, unified_agent):
        """Voice style from config should be applied."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        adapter = VoiceLiveAgentAdapter(unified_agent)
        payload = adapter._build_voice_payload()

        # Style should be passed to voice payload
        assert payload.style == "friendly"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT 8: Tool Choice Configuration Contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolChoiceContracts:
    """
    CONTRACT: Tool choice configuration must preserve:
    1. Default tool_choice is "auto"
    2. Can be overridden in session config
    3. Passed correctly to session update
    """

    def test_default_tool_choice_is_auto(self, unified_agent):
        """Default tool_choice should be 'auto'."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        adapter = VoiceLiveAgentAdapter(unified_agent)
        assert adapter.tool_choice == "auto"


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION CONTRACT: Full Orchestration Flow
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationFlowContracts:
    """
    CONTRACT: Full orchestration flow must preserve:
    1. Scenario name → load scenario → filter agents → build orchestrator
    2. Initial agent is entry_agent from scenario
    3. Handoff resolution uses unified HandoffService
    4. Agent switching updates active_agent correctly
    """

    def test_entry_agent_is_initial(self, multi_agent_registry):
        """Entry agent from scenario should be the initial active agent."""
        from apps.artagent.backend.registries.scenariostore.loader import ScenarioConfig

        scenario = ScenarioConfig(
            name="test",
            agents=["Concierge", "FraudAgent"],
            start_agent="Concierge",  # Use start_agent instead of entry_agent
        )

        # start_agent specifies the initial agent
        initial_agent = scenario.start_agent
        assert initial_agent == "Concierge"

    def test_handoff_changes_active_agent(self, multi_agent_registry):
        """
        Handoff resolution should correctly identify new active agent.
        
        This contract ensures that when a handoff is resolved:
        1. target_agent is correctly identified
        2. system_vars['active_agent'] is updated
        """
        from apps.artagent.backend.voice.shared.handoff_service import HandoffService

        service = HandoffService(
            scenario_name="test",
            handoff_map={"handoff_fraud_agent": "FraudAgent"},
            agents=multi_agent_registry,
        )

        with patch(
            "apps.artagent.backend.voice.shared.handoff_service.get_handoff_config"
        ) as mock_config:
            mock_config.return_value = MagicMock(
                type="announced",
                share_context=True,
                greet_on_switch=True,
            )

            resolution = service.resolve_handoff(
                tool_name="handoff_fraud_agent",
                tool_args={},
                source_agent="Concierge",
                current_system_vars={"active_agent": "Concierge"},
            )

            assert resolution.success is True
            assert resolution.target_agent == "FraudAgent"
            assert resolution.system_vars.get("active_agent") == "FraudAgent"
            assert resolution.system_vars.get("previous_agent") == "Concierge"


# ═══════════════════════════════════════════════════════════════════════════════
# VAD CONFIGURATION CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestVADConfigurationContracts:
    """
    CONTRACT: VAD configuration must preserve:
    1. Semantic VAD is default
    2. Server VAD can be selected
    3. Threshold, prefix_padding_ms, silence_duration_ms are passed
    """

    def test_semantic_vad_default(self, unified_agent):
        """Default VAD type should be semantic."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
            from azure.ai.voicelive.models import AzureSemanticVad
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        adapter = VoiceLiveAgentAdapter(unified_agent)

        assert isinstance(adapter.turn_detection, AzureSemanticVad)

    def test_vad_params_passed(self, unified_agent):
        """VAD parameters should be passed correctly."""
        try:
            from apps.artagent.backend.voice.voicelive.agent_adapter import (
                VoiceLiveAgentAdapter,
            )
        except ImportError:
            pytest.skip("VoiceLive SDK not available")

        adapter = VoiceLiveAgentAdapter(unified_agent)

        # From session config
        assert adapter.turn_detection.threshold == 0.5
        assert adapter.turn_detection.silence_duration_ms == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
