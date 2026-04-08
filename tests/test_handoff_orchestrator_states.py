"""
Handoff Orchestrator State Tests
================================

Focused tests to ensure both VoiceLive and Cascade orchestrators reach
a successful state after discrete and announced handoffs.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.artagent.backend.voice.shared.base import OrchestratorContext
from apps.artagent.backend.voice.shared.handoff_service import HandoffResolution
from apps.artagent.backend.voice.speech_cascade.orchestrator import (
    CascadeConfig,
    CascadeOrchestratorAdapter,
)
from apps.artagent.backend.voice.voicelive.orchestrator import LiveOrchestrator
from azure.ai.voicelive.models import UserMessageItem


class DummyVoiceLiveConnection:
    """Minimal VoiceLive connection stub for handoff tests."""

    def __init__(self) -> None:
        self.session = MagicMock()
        self.session.update = AsyncMock()
        self.response = MagicMock()
        self.response.cancel = AsyncMock()
        self.response.create = AsyncMock()
        self.conversation = MagicMock()
        self.conversation.item = MagicMock()
        self.conversation.item.create = AsyncMock()

    async def send(self, event: Any) -> None:  # pragma: no cover - not used in tests
        await AsyncMock()(event)


class DummyVoiceLiveAgent:
    """Minimal VoiceLive agent stub."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"{name} agent"

    async def apply_voicelive_session(self, conn, **kwargs) -> None:
        await AsyncMock()()

    async def trigger_voicelive_response(self, conn, *, say: str | None = None, cancel_active: bool = True) -> None:
        await AsyncMock()()


class DummyCascadeAgent:
    """Minimal Cascade agent stub for prompt rendering and greetings."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"{name} agent"

    def render_prompt(self, context: dict | None = None) -> str:
        return f"You are {self.name}."

    def get_tools(self) -> list[dict[str, Any]]:
        return []

    def render_greeting(self, context: dict | None = None) -> str:
        return f"Hello from {self.name}."

    def render_return_greeting(self, context: dict | None = None) -> str:
        return f"Welcome back to {self.name}."


class StubHandoffService:
    """Simple handoff service stub with configurable resolution."""

    def __init__(self, resolution: HandoffResolution, greeting: str | None = None) -> None:
        self._resolution = resolution
        self._greeting = greeting
        self.last_greet_on_switch: bool | None = None

    def is_handoff(self, tool_name: str) -> bool:
        return True

    def resolve_handoff(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        source_agent: str,
        current_system_vars: dict[str, Any],
        user_last_utterance: str | None = None,
        tool_result: dict[str, Any] | None = None,
    ) -> HandoffResolution:
        return self._resolution

    def select_greeting(
        self,
        agent: Any,
        is_first_visit: bool,
        greet_on_switch: bool,
        system_vars: dict[str, Any],
    ) -> str | None:
        self.last_greet_on_switch = greet_on_switch
        if not greet_on_switch:
            return None
        return self._greeting


def _make_voicelive_orchestrator(resolution: HandoffResolution) -> tuple[LiveOrchestrator, DummyVoiceLiveConnection]:
    conn = DummyVoiceLiveConnection()
    agents = {
        "Concierge": DummyVoiceLiveAgent("Concierge"),
        "Advisor": DummyVoiceLiveAgent("Advisor"),
    }
    orchestrator = LiveOrchestrator(
        conn=conn,
        agents=agents,
        handoff_map={"handoff_to_agent": "Advisor"},
        start_agent="Concierge",
        messenger=None,
    )
    orchestrator._handoff_service = StubHandoffService(resolution, greeting=None)
    orchestrator._user_message_history = deque(maxlen=5)
    return orchestrator, conn


def _make_cascade_adapter(resolution: HandoffResolution) -> CascadeOrchestratorAdapter:
    agents = {
        "Concierge": DummyCascadeAgent("Concierge"),
        "Advisor": DummyCascadeAgent("Advisor"),
    }
    config = CascadeConfig(
        start_agent="Concierge",
        session_id="test-session",
        call_connection_id="test-call",
    )
    adapter = CascadeOrchestratorAdapter(
        config=config,
        agents=agents,
        handoff_map={"handoff_to_agent": "Advisor"},
    )
    adapter._cached_orchestrator_config = MagicMock(
        scenario=None,
        scenario_name=None,
        has_scenario=False,
        agents=agents,
        handoff_map=adapter.handoff_map,
        start_agent=config.start_agent,
    )
    adapter._handoff_service = StubHandoffService(resolution, greeting="Hello from Advisor.")
    return adapter


@pytest.mark.asyncio
async def test_voicelive_discrete_handoff_success_state() -> None:
    user_question = "I need help with credit cards."
    resolution = HandoffResolution(
        success=True,
        target_agent="Advisor",
        source_agent="Concierge",
        tool_name="handoff_to_agent",
        system_vars={
            "is_handoff": True,
            "greet_on_switch": False,
            "handoff_context": {"question": user_question},
        },
        greet_on_switch=False,
        share_context=True,
        handoff_type="discrete",
    )
    orchestrator, conn = _make_voicelive_orchestrator(resolution)
    orchestrator._last_user_message = user_question

    with patch(
        "apps.artagent.backend.voice.voicelive.orchestrator.execute_tool",
        new=AsyncMock(return_value={"handoff_summary": "summary"}),
    ):
        result = await orchestrator._execute_tool_call(
            call_id="call-1",
            name="handoff_to_agent",
            args_json=json.dumps({"target_agent": "Advisor", "reason": "Card help"}),
        )

    assert result is True
    assert orchestrator.active == "Advisor"
    assert orchestrator._handoff_response_pending is True

    additional_instruction = conn.response.create.call_args.kwargs["additional_instructions"]
    assert "respond immediately" in additional_instruction.lower()
    assert "without any greeting" in additional_instruction.lower()
    assert user_question in additional_instruction

    assert conn.conversation.item.create.call_count == 1
    item = conn.conversation.item.create.call_args.kwargs["item"]
    assert isinstance(item, UserMessageItem)
    assert item.content[0].text == user_question


@pytest.mark.asyncio
async def test_voicelive_announced_handoff_success_state() -> None:
    user_question = "I want to update my policy."
    resolution = HandoffResolution(
        success=True,
        target_agent="Advisor",
        source_agent="Concierge",
        tool_name="handoff_to_agent",
        system_vars={
            "is_handoff": True,
            "greet_on_switch": True,
            "handoff_context": {"question": user_question},
        },
        greet_on_switch=True,
        share_context=True,
        handoff_type="announced",
    )
    orchestrator, conn = _make_voicelive_orchestrator(resolution)
    orchestrator._last_user_message = user_question

    with patch(
        "apps.artagent.backend.voice.voicelive.orchestrator.execute_tool",
        new=AsyncMock(return_value={"handoff_summary": "summary"}),
    ):
        result = await orchestrator._execute_tool_call(
            call_id="call-2",
            name="handoff_to_agent",
            args_json=json.dumps({"target_agent": "Advisor", "reason": "Policy help"}),
        )

    assert result is True
    assert orchestrator.active == "Advisor"
    assert orchestrator._handoff_response_pending is True

    additional_instruction = conn.response.create.call_args.kwargs["additional_instructions"]
    assert "after your greeting" in additional_instruction.lower()
    assert user_question in additional_instruction

    assert conn.conversation.item.create.call_count == 0


@pytest.mark.asyncio
async def test_cascade_discrete_handoff_success_state() -> None:
    resolution = HandoffResolution(
        success=True,
        target_agent="Advisor",
        source_agent="Concierge",
        tool_name="handoff_to_agent",
        system_vars={"greet_on_switch": False},
        greet_on_switch=False,
        share_context=True,
        handoff_type="discrete",
    )
    adapter = _make_cascade_adapter(resolution)

    tool_call = {
        "name": "handoff_to_agent",
        "arguments": json.dumps({"target_agent": "Advisor", "reason": "Card help"}),
    }
    adapter._process_llm = AsyncMock(
        side_effect=[
            ("Transferring you now.", [tool_call]),
            ("Sure, I can help with that.", []),
        ]
    )

    context = OrchestratorContext(
        session_id="test-session",
        user_text="I need help with cards.",
        conversation_history=[],
        metadata={},
    )

    with patch.object(adapter, "_get_tools_with_handoffs", return_value=[]):
        result = await adapter.process_turn(context)

    assert adapter._active_agent == "Advisor"
    assert result.agent_name == "Advisor"
    assert result.response_text == "Sure, I can help with that."
    assert adapter.handoff_service.last_greet_on_switch is False


@pytest.mark.asyncio
async def test_cascade_announced_handoff_success_state() -> None:
    resolution = HandoffResolution(
        success=True,
        target_agent="Advisor",
        source_agent="Concierge",
        tool_name="handoff_to_agent",
        system_vars={"greet_on_switch": True},
        greet_on_switch=True,
        share_context=True,
        handoff_type="announced",
    )
    adapter = _make_cascade_adapter(resolution)

    tool_call = {
        "name": "handoff_to_agent",
        "arguments": json.dumps({"target_agent": "Advisor", "reason": "Policy help"}),
    }
    adapter._process_llm = AsyncMock(
        side_effect=[
            ("Let me connect you.", [tool_call]),
            ("Happy to help with your policy.", []),
        ]
    )

    context = OrchestratorContext(
        session_id="test-session",
        user_text="I want to update my policy.",
        conversation_history=[],
        metadata={},
    )

    with patch.object(adapter, "_get_tools_with_handoffs", return_value=[]):
        result = await adapter.process_turn(context)

    assert adapter._active_agent == "Advisor"
    assert result.agent_name == "Advisor"
    assert result.response_text == "Happy to help with your policy."
    assert adapter.handoff_service.last_greet_on_switch is True
