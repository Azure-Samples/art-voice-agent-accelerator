"""
Orchestrator Data Classes
==========================

Shared data classes for orchestrator context and results.
Used by CascadeOrchestratorAdapter and LiveOrchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import WebSocket


@dataclass
class OrchestratorContext:
    """Context passed to orchestrator for each turn."""

    session_id: str
    websocket: WebSocket | None = None
    call_connection_id: str | None = None
    user_text: str = ""
    turn_id: str | None = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    system_prompt: str | None = None
    tools: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    """Result from an orchestrator turn."""

    response_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    agent_name: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    interrupted: bool = False
    error: str | None = None


__all__ = [
    "OrchestratorContext",
    "OrchestratorResult",
]
