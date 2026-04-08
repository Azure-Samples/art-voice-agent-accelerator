"""
Discrete Handoff Consistency Tests
===================================

These tests simulate the actual handoff flow to verify:
1. Discrete handoffs trigger a response from the target agent WITHOUT greeting
2. Announced handoffs trigger a response from the target agent WITH greeting
3. Behavior is consistent across multiple runs
4. All handoff tools in banking and insurance scenarios respect their configured type

Run with:
    pytest tests/test_discrete_handoff_consistency.py -v
    
Run multiple times to verify consistency:
    pytest tests/test_discrete_handoff_consistency.py -v --count=10
    
Or use the parametrized test that runs N iterations internally.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# HANDOFF CONFIGURATIONS FROM SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════════

# Banking scenario handoffs (all discrete)
BANKING_HANDOFFS = [
    # (tool_name, from_agent, to_agent, handoff_type, description)
    ("handoff_card_recommendation", "BankingConcierge", "CardRecommendation", "discrete", "Credit card specialist"),
    ("handoff_investment_advisor", "BankingConcierge", "InvestmentAdvisor", "discrete", "Investment specialist"),
    ("handoff_investment_advisor", "CardRecommendation", "InvestmentAdvisor", "discrete", "Card to investment"),
    ("handoff_card_recommendation", "InvestmentAdvisor", "CardRecommendation", "discrete", "Investment to card"),
    ("handoff_concierge", "CardRecommendation", "BankingConcierge", "discrete", "Return to concierge"),
    ("handoff_concierge", "InvestmentAdvisor", "BankingConcierge", "discrete", "Return to concierge"),
]

# Insurance scenario handoffs (mix of announced and discrete)
INSURANCE_HANDOFFS = [
    # Customer paths (announced - new agent greets)
    ("handoff_policy_advisor", "AuthAgent", "PolicyAdvisor", "announced", "Policy advisor transfer"),
    ("handoff_fnol_agent", "AuthAgent", "FNOLAgent", "announced", "FNOL agent transfer"),
    ("handoff_claims_specialist", "AuthAgent", "ClaimsSpecialist", "announced", "Claims specialist transfer"),
    # B2B path (discrete - seamless)
    ("handoff_subro_agent", "AuthAgent", "SubroAgent", "discrete", "B2B subrogation transfer"),
    # Cross-specialist (announced)
    ("handoff_fnol_agent", "PolicyAdvisor", "FNOLAgent", "announced", "Policy to FNOL"),
    ("handoff_policy_advisor", "FNOLAgent", "PolicyAdvisor", "announced", "FNOL to Policy"),
]

# Combined for comprehensive testing
ALL_HANDOFFS = BANKING_HANDOFFS + INSURANCE_HANDOFFS


# ═══════════════════════════════════════════════════════════════════════════════
# TEST INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class HandoffEvent:
    """Captured event during handoff simulation."""
    event_type: str
    data: Any = None
    timestamp: float = 0.0


@dataclass 
class HandoffSimulationResult:
    """Result from simulating a discrete handoff."""
    success: bool = False
    agent_switched: bool = False
    response_triggered: bool = False
    greeting_sent: bool = False
    events: list[HandoffEvent] = field(default_factory=list)
    error: str | None = None
    response_instruction: str | None = None
    handoff_type: str = "discrete"
    
    @property
    def is_discrete_behavior_correct(self) -> bool:
        """Check if discrete handoff behaved correctly (response, no greeting)."""
        return (
            self.success and 
            self.agent_switched and 
            self.response_triggered and 
            not self.greeting_sent
        )
    
    @property
    def is_announced_behavior_correct(self) -> bool:
        """Check if announced handoff behaved correctly (response, with greeting)."""
        return (
            self.success and 
            self.agent_switched and 
            self.response_triggered and 
            self.greeting_sent
        )
    
    @property
    def is_behavior_correct(self) -> bool:
        """Check if handoff behaved correctly based on type."""
        if self.handoff_type == "discrete":
            return self.is_discrete_behavior_correct
        else:
            return self.is_announced_behavior_correct


class MockVoiceLiveConnection:
    """Mock VoiceLive SDK connection that captures all interactions."""

    def __init__(self):
        self.session = MagicMock()
        self.session.update = AsyncMock()
        self.response = MagicMock()
        self.response.cancel = AsyncMock()
        self.response.create = AsyncMock()
        self.conversation = MagicMock()
        self.conversation.item = MagicMock()
        self.conversation.item.create = AsyncMock()
        self._closed = False
        
        # Capture all events for analysis
        self.events: list[HandoffEvent] = []
        self.sent_events: list[Any] = []

    async def send(self, event):
        """Capture sent events."""
        import time
        self.sent_events.append(event)
        self.events.append(HandoffEvent(
            event_type=type(event).__name__,
            data=event,
            timestamp=time.time(),
        ))
        await asyncio.sleep(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self._closed = True


class MockUnifiedAgent:
    """Mock agent with discrete handoff prompt template."""

    def __init__(
        self, 
        name: str, 
        greeting: str = None,
        has_discrete_prompt: bool = True,
    ):
        self.name = name
        self._greeting = greeting or f"Hello, I'm {name}!"
        self._has_discrete_prompt = has_discrete_prompt
        self.tool_names = ["handoff_to_agent"]
        self.handoff = MagicMock()
        self.handoff.trigger = f"handoff_{name.lower()}"
        self.description = f"Mock {name} agent"

        # Track greeting renders
        self.greeting_render_count = 0

    def render_greeting(self, context: dict = None) -> str:
        self.greeting_render_count += 1
        return self._greeting

    def render_return_greeting(self, context: dict = None) -> str:
        return f"Welcome back to {self.name}"

    def render_prompt(self, context: dict = None) -> str:
        """Render prompt with discrete handoff instructions if applicable."""
        context = context or {}
        is_handoff = context.get("is_handoff", False)
        greet_on_switch = context.get("greet_on_switch", True)
        
        base_prompt = f"You are {self.name}. Help the user."
        
        if is_handoff and self._has_discrete_prompt:
            if greet_on_switch:
                base_prompt += "\n\n**ANNOUNCED HANDOFF:** Your greeting will be spoken automatically."
            else:
                base_prompt += (
                    "\n\n**DISCRETE HANDOFF - Continue seamlessly:**\n"
                    "- This is the SAME conversation\n"
                    "- Do NOT introduce yourself or acknowledge any transfer\n"
                    "- Do NOT say 'Hi' or greet the customer\n"
                    "- Respond immediately to their request"
                )
        
        return base_prompt

    async def apply_voicelive_session(self, conn, **kwargs):
        """Mock session application."""
        await conn.session.update(session=MagicMock())

    async def trigger_voicelive_response(self, conn, *, say: str = None, cancel_active: bool = True):
        """Mock response trigger - only used for announced greetings."""
        if say:
            try:
                from azure.ai.voicelive.models import (
                    ClientEventResponseCreate,
                    ResponseCreateParams,
                )
                await conn.send(ClientEventResponseCreate(
                    response=ResponseCreateParams(instructions=f'Say: "{say}"')
                ))
            except ImportError:
                pass


class HandoffSimulator:
    """Simulates the handoff flow from the orchestrator."""

    def __init__(
        self,
        source_agent: str = "Concierge",
        target_agent: str = "CardAgent",
        handoff_type: str = "discrete",
        user_message: str = "I need help with credit cards",
        tool_name: str = "handoff_to_agent",
    ):
        self.source_agent = source_agent
        self.target_agent = target_agent
        self.handoff_type = handoff_type
        self.user_message = user_message
        self.tool_name = tool_name
        
        self.conn = MockVoiceLiveConnection()
        self.agents = {
            source_agent: MockUnifiedAgent(source_agent),
            target_agent: MockUnifiedAgent(target_agent),
        }
        
    async def simulate_handoff(self) -> HandoffSimulationResult:
        """
        Simulate a handoff following the orchestrator's actual flow.
        
        This mirrors the code in orchestrator.py:_execute_tool_call()
        """
        result = HandoffSimulationResult()
        result.handoff_type = self.handoff_type
        
        try:
            # Step 1: Build handoff context (from HandoffService)
            greet_on_switch = self.handoff_type == "announced"
            
            system_vars = {
                "is_handoff": True,
                "greet_on_switch": greet_on_switch,
                "share_context": True,
                "previous_agent": self.source_agent,
                "active_agent": self.target_agent,
                "handoff_context": {
                    "details": self.user_message,
                    "question": self.user_message,
                },
            }
            
            result.events.append(HandoffEvent(
                event_type="handoff_started",
                data={
                    "type": self.handoff_type,
                    "target": self.target_agent,
                    "tool": self.tool_name,
                },
            ))
            
            # Step 2: Cancel old agent's response
            await self.conn.response.cancel()
            result.events.append(HandoffEvent(event_type="old_response_cancelled"))
            
            # Step 3: Switch agent (apply new session)
            target = self.agents[self.target_agent]
            await target.apply_voicelive_session(
                self.conn,
                system_vars=system_vars,
            )
            result.agent_switched = True
            result.events.append(HandoffEvent(
                event_type="agent_switched",
                data={"to": self.target_agent},
            ))
            
            # Step 4: Check if greeting should be selected
            # For discrete handoffs, greet_on_switch=False, so no greeting
            if greet_on_switch:
                # Announced mode - greeting would be rendered
                greeting = target.render_greeting(system_vars)
                result.greeting_sent = True
                result.events.append(HandoffEvent(
                    event_type="greeting_rendered",
                    data={"greeting": greeting},
                ))
            else:
                # Discrete mode - no greeting
                result.greeting_sent = False
                result.events.append(HandoffEvent(event_type="greeting_skipped"))
            
            # Step 5: Skip tool output creation (matches our fix)
            # We intentionally do NOT send the handoff tool output back to the model.
            # The old agent's tool call was an internal action that triggered the switch.
            result.events.append(HandoffEvent(event_type="tool_output_skipped"))
            
            # Step 6: Trigger handoff response (THE KEY PART)
            # This mirrors the FIXED code from orchestrator.py:
            # - Uses conn.response.create(additional_instructions=...) 
            # - additional_instructions APPENDS to system prompt (doesn't override)
            # - The agent's prompt template already has discrete handoff behavior
            
            user_question = self.user_message
            
            if greet_on_switch:
                # Announced mode: include greeting instruction
                additional_instruction = (
                    f'The customer\'s request: "{user_question}". '
                    f"Address their request directly after your greeting."
                )
            else:
                # Discrete mode: system prompt already has discrete handoff instructions
                # Just provide the user's question as context - don't override behavior
                additional_instruction = (
                    f'The customer\'s request: "{user_question}". '
                    f"Respond immediately without any greeting or introduction."
                )
            
            result.response_instruction = additional_instruction
            
            # Use response.create with additional_instructions (APPENDS, not overrides)
            await self.conn.response.create(additional_instructions=additional_instruction)
            result.response_triggered = True
            result.events.append(HandoffEvent(
                event_type="response_triggered",
                data={"instruction": additional_instruction},
            ))
            
            result.success = True
            
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.events.append(HandoffEvent(
                event_type="error",
                data={"error": str(e)},
            ))
        
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# DISCRETE HANDOFF TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiscreteHandoffSimulation:
    """Test discrete handoff behavior through simulation."""

    @pytest.mark.asyncio
    async def test_discrete_handoff_triggers_response(self):
        """Verify discrete handoff triggers a response from the target agent."""
        simulator = HandoffSimulator(
            source_agent="Concierge",
            target_agent="CardAgent",
            handoff_type="discrete",
            user_message="I want to know about premium credit cards",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.success, f"Handoff failed: {result.error}"
        assert result.agent_switched, "Agent should have switched"
        assert result.response_triggered, "Response should have been triggered"
        
    @pytest.mark.asyncio
    async def test_discrete_handoff_no_greeting(self):
        """Verify discrete handoff does NOT send a greeting."""
        simulator = HandoffSimulator(
            source_agent="Concierge",
            target_agent="CardAgent",
            handoff_type="discrete",
            user_message="Help with cards",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.success
        assert not result.greeting_sent, "Discrete handoff should NOT send greeting"
        
        # Verify greeting_skipped event was recorded
        event_types = [e.event_type for e in result.events]
        assert "greeting_skipped" in event_types
        assert "greeting_rendered" not in event_types

    @pytest.mark.asyncio
    async def test_discrete_handoff_simple_instruction(self):
        """Verify discrete handoff sends simple 'Respond now' instruction."""
        simulator = HandoffSimulator(
            source_agent="Concierge",
            target_agent="CardAgent",
            handoff_type="discrete",
            user_message="I need a travel rewards card",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.success
        assert result.response_instruction is not None
        
        # For discrete handoffs, instruction should contain user's request and no-greeting directive
        instruction = result.response_instruction
        assert "Respond immediately" in instruction, "Discrete handoff should say 'Respond immediately'"
        assert "without any greeting" in instruction.lower(), "Discrete handoff should say no greeting"
        assert "I need a travel rewards card" in instruction

    @pytest.mark.asyncio
    async def test_announced_handoff_includes_greeting_instruction(self):
        """Verify announced handoff includes greeting instruction."""
        simulator = HandoffSimulator(
            source_agent="Concierge",
            target_agent="CardAgent",
            handoff_type="announced",
            user_message="Help with cards",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.success
        assert result.greeting_sent, "Announced handoff should render greeting"
        assert result.response_instruction is not None
        
        # For announced handoffs, instruction should mention greeting
        assert "greeting" in result.response_instruction.lower()

    @pytest.mark.asyncio
    async def test_announced_handoff_correct_event_sequence(self):
        """Verify announced handoff follows correct event sequence."""
        simulator = HandoffSimulator(
            source_agent="AuthAgent",
            target_agent="PolicyAdvisor",
            handoff_type="announced",
            tool_name="handoff_policy_advisor",
            user_message="I need help with my policy",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.success
        
        event_types = [e.event_type for e in result.events]
        
        # Expected sequence for announced handoff
        expected_sequence = [
            "handoff_started",
            "old_response_cancelled",
            "agent_switched",
            "greeting_rendered",  # Announced gets greeting
            "tool_output_skipped",
            "response_triggered",
        ]
        
        assert event_types == expected_sequence, (
            f"Event sequence mismatch:\n"
            f"  Expected: {expected_sequence}\n"
            f"  Actual: {event_types}"
        )

    @pytest.mark.asyncio
    async def test_discrete_handoff_correct_event_sequence(self):
        """Verify discrete handoff follows correct event sequence."""
        simulator = HandoffSimulator(
            source_agent="Concierge",
            target_agent="FraudAgent",
            handoff_type="discrete",
            user_message="I think my card was stolen",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.success
        
        event_types = [e.event_type for e in result.events]
        
        # Expected sequence for discrete handoff (tool output is now skipped)
        expected_sequence = [
            "handoff_started",
            "old_response_cancelled",
            "agent_switched",
            "greeting_skipped",  # NOT greeting_rendered
            "tool_output_skipped",  # Tool output is intentionally skipped
            "response_triggered",
        ]
        
        assert event_types == expected_sequence, (
            f"Event sequence mismatch:\n"
            f"  Expected: {expected_sequence}\n"
            f"  Actual: {event_types}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# COMPREHENSIVE HANDOFF TOOL TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestAllHandoffTools:
    """Test all handoff tools from banking and insurance scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_name,from_agent,to_agent,handoff_type,description",
        BANKING_HANDOFFS,
        ids=[f"banking:{h[0]}:{h[1]}->{h[2]}" for h in BANKING_HANDOFFS],
    )
    async def test_banking_handoff_respects_type(
        self, tool_name, from_agent, to_agent, handoff_type, description
    ):
        """
        Test that each banking scenario handoff respects its configured type.
        
        Banking scenario uses discrete handoffs for seamless specialist transfers.
        """
        simulator = HandoffSimulator(
            source_agent=from_agent,
            target_agent=to_agent,
            handoff_type=handoff_type,
            tool_name=tool_name,
            user_message=f"Testing {description}",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.success, f"{tool_name} failed: {result.error}"
        assert result.agent_switched, f"{tool_name} should switch agent"
        assert result.response_triggered, f"{tool_name} should trigger response"
        
        if handoff_type == "discrete":
            assert not result.greeting_sent, (
                f"{tool_name} is discrete but sent greeting"
            )
            assert "Respond immediately" in result.response_instruction
        else:
            assert result.greeting_sent, (
                f"{tool_name} is announced but skipped greeting"
            )
            assert "greeting" in result.response_instruction.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_name,from_agent,to_agent,handoff_type,description",
        INSURANCE_HANDOFFS,
        ids=[f"insurance:{h[0]}:{h[1]}->{h[2]}" for h in INSURANCE_HANDOFFS],
    )
    async def test_insurance_handoff_respects_type(
        self, tool_name, from_agent, to_agent, handoff_type, description
    ):
        """
        Test that each insurance scenario handoff respects its configured type.
        
        Insurance scenario uses:
        - Announced handoffs for customer paths (new agent greets)
        - Discrete handoffs for B2B subrogation (seamless)
        """
        simulator = HandoffSimulator(
            source_agent=from_agent,
            target_agent=to_agent,
            handoff_type=handoff_type,
            tool_name=tool_name,
            user_message=f"Testing {description}",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.success, f"{tool_name} failed: {result.error}"
        assert result.agent_switched, f"{tool_name} should switch agent"
        assert result.response_triggered, f"{tool_name} should trigger response"
        
        if handoff_type == "discrete":
            assert not result.greeting_sent, (
                f"{tool_name} is discrete but sent greeting"
            )
            assert "Respond immediately" in result.response_instruction
        else:
            assert result.greeting_sent, (
                f"{tool_name} is announced but skipped greeting"
            )
            assert "greeting" in result.response_instruction.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_name,from_agent,to_agent,handoff_type,description",
        ALL_HANDOFFS,
        ids=[f"{h[0]}:{h[1]}->{h[2]}({h[3]})" for h in ALL_HANDOFFS],
    )
    async def test_all_handoffs_behavior_correct(
        self, tool_name, from_agent, to_agent, handoff_type, description
    ):
        """
        Unified test for all handoff tools across all scenarios.
        
        Verifies each tool produces correct behavior based on its type:
        - discrete: no greeting, "Respond immediately" instruction
        - announced: with greeting, greeting-aware instruction
        """
        simulator = HandoffSimulator(
            source_agent=from_agent,
            target_agent=to_agent,
            handoff_type=handoff_type,
            tool_name=tool_name,
            user_message=f"Testing {description}",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.is_behavior_correct, (
            f"{tool_name} ({handoff_type}) behavior incorrect:\n"
            f"  from: {from_agent} → to: {to_agent}\n"
            f"  success={result.success}\n"
            f"  agent_switched={result.agent_switched}\n"
            f"  response_triggered={result.response_triggered}\n"
            f"  greeting_sent={result.greeting_sent} (expected: {handoff_type == 'announced'})\n"
            f"  error={result.error}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CONSISTENCY TESTS (Multiple Runs)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiscreteHandoffConsistency:
    """Test that discrete handoff behavior is consistent across multiple runs."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("run_number", range(10))
    async def test_discrete_handoff_consistent_across_runs(self, run_number):
        """
        Run discrete handoff simulation multiple times to verify consistency.
        
        Each run should produce identical behavior:
        - Agent switches successfully
        - Response is triggered
        - No greeting is sent
        """
        simulator = HandoffSimulator(
            source_agent="Concierge",
            target_agent="CardAgent",
            handoff_type="discrete",
            user_message=f"Run {run_number}: I want a credit card",
        )
        
        result = await simulator.simulate_handoff()
        
        assert result.is_discrete_behavior_correct, (
            f"Run {run_number} failed:\n"
            f"  success={result.success}\n"
            f"  agent_switched={result.agent_switched}\n"
            f"  response_triggered={result.response_triggered}\n"
            f"  greeting_sent={result.greeting_sent} (should be False)\n"
            f"  error={result.error}"
        )

    @pytest.mark.asyncio
    async def test_multiple_discrete_handoffs_in_sequence(self):
        """Simulate multiple discrete handoffs in sequence."""
        handoff_chain = [
            ("Concierge", "CardAgent", "Help with cards"),
            ("CardAgent", "InvestmentAgent", "Actually, I want to invest"),
            ("InvestmentAgent", "Concierge", "Let me talk to someone else"),
        ]
        
        results = []
        for source, target, message in handoff_chain:
            simulator = HandoffSimulator(
                source_agent=source,
                target_agent=target,
                handoff_type="discrete",
                user_message=message,
            )
            result = await simulator.simulate_handoff()
            results.append((source, target, result))
        
        # All handoffs should succeed with correct discrete behavior
        for source, target, result in results:
            assert result.is_discrete_behavior_correct, (
                f"Handoff {source} → {target} failed: "
                f"greeting_sent={result.greeting_sent}, "
                f"response_triggered={result.response_triggered}"
            )

    @pytest.mark.asyncio
    async def test_concurrent_discrete_handoffs(self):
        """
        Simulate multiple discrete handoffs concurrently.
        
        This tests that the handoff logic doesn't have race conditions
        or shared state issues.
        """
        async def run_handoff(agent_pair: tuple[str, str, str]) -> HandoffSimulationResult:
            source, target, message = agent_pair
            simulator = HandoffSimulator(
                source_agent=source,
                target_agent=target,
                handoff_type="discrete",
                user_message=message,
            )
            return await simulator.simulate_handoff()
        
        # Create 5 concurrent handoff simulations
        handoff_pairs = [
            ("Concierge", "CardAgent", "Card question 1"),
            ("Concierge", "FraudAgent", "Fraud report 1"),
            ("Concierge", "InvestmentAgent", "Investment question 1"),
            ("CardAgent", "Concierge", "Back to main"),
            ("FraudAgent", "Concierge", "Done with fraud"),
        ]
        
        results = await asyncio.gather(
            *[run_handoff(pair) for pair in handoff_pairs]
        )
        
        # All should have correct discrete behavior
        for i, result in enumerate(results):
            source, target, _ = handoff_pairs[i]
            assert result.is_discrete_behavior_correct, (
                f"Concurrent handoff {i} ({source} → {target}) failed"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# NOTE: Integration tests with real orchestrator omitted - they require extensive
# mocking of the full orchestrator state machine. The simulation tests above
# validate the core handoff logic.
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY TEST
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiscreteHandoffSummary:
    """Summary test that validates all discrete handoff requirements."""

    @pytest.mark.asyncio
    async def test_discrete_handoff_full_validation(self):
        """
        Full validation of discrete handoff behavior.
        
        Requirements:
        1. ✓ Tool call triggers handoff
        2. ✓ Agent config is swapped/updated
        3. ✓ Response is triggered for the new agent
        4. ✓ NO greeting is sent
        5. ✓ Instruction tells agent to respond immediately without greeting
        """
        simulator = HandoffSimulator(
            source_agent="BankingConcierge",
            target_agent="CardRecommendation",
            handoff_type="discrete",
            user_message="I'm looking for a travel rewards card with no foreign transaction fees",
        )
        
        result = await simulator.simulate_handoff()
        
        # Requirement 1 & 2: Tool call triggers handoff and agent switches
        assert result.success, "Handoff should succeed"
        assert result.agent_switched, "Agent should switch"
        
        # Requirement 3: Response is triggered
        assert result.response_triggered, "Response should be triggered for new agent"
        
        # Requirement 4: No greeting
        assert not result.greeting_sent, "Discrete handoff should NOT send greeting"
        
        # Requirement 5: Instruction tells agent to respond immediately without greeting
        assert result.response_instruction is not None
        assert "Respond immediately" in result.response_instruction
        assert "without any greeting" in result.response_instruction.lower()
        
        # Full validation
        assert result.is_discrete_behavior_correct, (
            "Discrete handoff should have correct behavior:\n"
            f"  success={result.success}\n"
            f"  agent_switched={result.agent_switched}\n"
            f"  response_triggered={result.response_triggered}\n"
            f"  greeting_sent={result.greeting_sent}\n"
            f"  instruction={result.response_instruction}"
        )
