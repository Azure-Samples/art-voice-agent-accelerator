"""
Evaluation Mocks
=================

Minimal mocks for running evaluation scenarios without full system dependencies.

Design principles:
- Keep it simple - just enough to run scenarios
- No duplication of production code
- Easy to understand and maintain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Mock MemoManager (Session State)
# =============================================================================


class MockChatHistory:
    """Mock ChatHistory for compatibility."""

    def __init__(self):
        self._threads: dict[str, list[dict[str, Any]]] = {}

    def get_all(self) -> dict[str, list[dict[str, Any]]]:
        """Get all conversation threads."""
        return self._threads

    def get_thread(self, agent_name: str) -> list[dict[str, Any]]:
        """Get conversation thread for specific agent."""
        return self._threads.get(agent_name, [])

    def append(self, agent_name: str, message: dict[str, Any]):
        """Append message to agent's thread."""
        if agent_name not in self._threads:
            self._threads[agent_name] = []
        self._threads[agent_name].append(message)


class MockCoreMemory:
    """Mock CoreMemory for compatibility."""

    def __init__(self, initial: dict[str, Any] | None = None):
        self._store = initial or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from memory."""
        return self._store.get(key, default)

    def set(self, key: str, value: Any):
        """Set value in memory."""
        self._store[key] = value


class MockMemoManager:
    """
    Mock MemoManager compatible with real orchestrator.

    Provides the same interface as src.stateful.state_managment.MemoManager
    but without Redis dependencies, perfect for evaluation scenarios.
    """

    def __init__(self, session_id: str, context: dict[str, Any] | None = None):
        """
        Initialize mock memo manager.

        Args:
            session_id: Session ID
            context: Initial context/core memory values
        """
        self.session_id = session_id
        self.chatHistory = MockChatHistory()
        self.corememory = MockCoreMemory(context)
        self._history: dict[str, list[dict[str, Any]]] = {}  # Legacy interface

    # Legacy compatibility properties (used by orchestrator)
    @property
    def histories(self) -> dict[str, list[dict[str, Any]]]:
        """Get all conversation histories (compatibility)."""
        return self.chatHistory.get_all()

    @histories.setter
    def histories(self, value: dict[str, list[dict[str, Any]]]):
        """Set conversation histories (compatibility)."""
        self.chatHistory._threads = value

    @property
    def context(self) -> dict[str, Any]:
        """Get core memory context (compatibility)."""
        return self.corememory._store

    def get_history(self, agent_name: str) -> list[dict[str, Any]]:
        """Get conversation history for an agent."""
        return self.chatHistory.get_thread(agent_name)

    def append_to_history(
        self,
        agent_name: str,
        role: str,
        content: str,
        **kwargs: Any
    ):
        """Add message to conversation history."""
        message = {"role": role, "content": content}
        if kwargs:
            message.update(kwargs)
        self.chatHistory.append(agent_name, message)

    def get_value_from_corememory(
        self,
        key: str,
        default: Any = None
    ) -> Any:
        """Get value from core memory."""
        return self.corememory.get(key, default)

    def set_value_in_corememory(self, key: str, value: Any):
        """Set value in core memory."""
        self.corememory.set(key, value)

    def set_corememory(self, key: str, value: Any):
        """Set value in core memory (alternative method name)."""
        self.corememory.set(key, value)

    def get_corememory(self, key: str, default: Any = None) -> Any:
        """Get value from core memory (alternative method name)."""
        return self.corememory.get(key, default)

    def clear_history(self, agent_name: str | None = None):
        """Clear conversation history."""
        if agent_name:
            threads = self.chatHistory._threads
            threads.pop(agent_name, None)
        else:
            self.chatHistory._threads.clear()


# =============================================================================
# Context Builder
# =============================================================================


@dataclass
class MockOrchestratorContext:
    """
    Minimal mock context for orchestrator turns.

    This is a simplified version of OrchestratorContext
    with just the fields needed for evaluation.
    """

    session_id: str
    user_text: str = ""
    turn_id: str | None = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    websocket: Any = None  # Not needed for eval
    metadata: dict[str, Any] = field(default_factory=dict)
    system_prompt: str | None = None
    tools: list[dict[str, Any]] | None = None
    call_connection_id: str | None = None


def build_context(
    session_id: str,
    user_text: str,
    turn_id: str,
    conversation_history: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MockOrchestratorContext:
    """
    Build orchestrator context for evaluation.

    Args:
        session_id: Session ID
        user_text: User input text
        turn_id: Turn identifier
        conversation_history: Previous conversation
        metadata: Additional metadata

    Returns:
        MockOrchestratorContext ready for orchestrator
    """
    return MockOrchestratorContext(
        session_id=session_id,
        user_text=user_text,
        turn_id=turn_id,
        conversation_history=conversation_history or [],
        metadata=metadata or {},
        websocket=None,  # Not needed for eval
    )


__all__ = [
    "MockMemoManager",
    "MockOrchestratorContext",
    "build_context",
]
