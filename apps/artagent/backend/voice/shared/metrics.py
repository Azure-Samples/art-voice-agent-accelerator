"""
Orchestrator Metrics
====================

Shared token tracking, TTFT metrics, and turn counting for orchestrators.

Extracts common metrics logic from LiveOrchestrator and CascadeOrchestratorAdapter
into a single reusable component.

Usage:
    from apps.artagent.backend.voice.shared.metrics import OrchestratorMetrics

    # Create metrics tracker
    metrics = OrchestratorMetrics(agent_name="Concierge")

    # Track token usage
    metrics.add_tokens(input_tokens=100, output_tokens=50)

    # Track TTFT
    metrics.start_turn()
    # ... LLM processing ...
    metrics.record_first_token()  # Records TTFT

    # On agent switch
    summary = metrics.reset_for_agent_switch("NewAgent")
    # summary contains tokens, duration, turn count for previous agent

    # Get current stats
    stats = metrics.get_stats()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace

try:
    from utils.ml_logging import get_logger
    logger = get_logger("voice.shared.metrics")
except ImportError:
    import logging
    logger = logging.getLogger("voice.shared.metrics")

tracer = trace.get_tracer(__name__)


@dataclass
class AgentSessionSummary:
    """Summary of an agent's session before switching."""

    agent_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    turn_count: int = 0
    response_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/telemetry."""
        return {
            "agent_name": self.agent_name,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "turn_count": self.turn_count,
            "response_count": self.response_count,
        }


@dataclass
class TTFTMetrics:
    """Time-to-first-token metrics for a single turn."""

    turn_number: int = 0
    start_time: float | None = None
    first_token_time: float | None = None

    @property
    def ttft_ms(self) -> float | None:
        """Calculate TTFT in milliseconds."""
        if self.start_time is None or self.first_token_time is None:
            return None
        return (self.first_token_time - self.start_time) * 1000

    def reset(self) -> None:
        """Reset for new turn."""
        self.start_time = None
        self.first_token_time = None


class OrchestratorMetrics:
    """
    Unified metrics tracking for voice orchestrators.

    Tracks:
    - Token usage (input/output) per agent session
    - TTFT (time-to-first-token) per turn
    - Turn count and response count
    - Agent session duration

    Thread-safe for concurrent access from different callbacks.
    """

    def __init__(
        self,
        agent_name: str = "",
        call_connection_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """
        Initialize metrics tracker.

        Args:
            agent_name: Current agent name
            call_connection_id: ACS call connection ID for telemetry
            session_id: Session ID for telemetry
        """
        self._agent_name = agent_name
        self._call_connection_id = call_connection_id
        self._session_id = session_id

        # Token tracking
        self._input_tokens: int = 0
        self._output_tokens: int = 0

        # Timing
        self._agent_start_time: float = time.perf_counter()

        # Turn tracking
        self._turn_count: int = 0
        self._response_count: int = 0

        # TTFT tracking
        self._ttft = TTFTMetrics()

    # ─────────────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────────────

    @property
    def agent_name(self) -> str:
        """Current agent name."""
        return self._agent_name

    @property
    def input_tokens(self) -> int:
        """Total input tokens for current agent session."""
        return self._input_tokens

    @property
    def output_tokens(self) -> int:
        """Total output tokens for current agent session."""
        return self._output_tokens

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output) for current agent session."""
        return self._input_tokens + self._output_tokens

    @property
    def turn_count(self) -> int:
        """Number of turns in current agent session."""
        return self._turn_count

    @property
    def duration_ms(self) -> float:
        """Duration of current agent session in milliseconds."""
        return (time.perf_counter() - self._agent_start_time) * 1000

    @property
    def current_ttft_ms(self) -> float | None:
        """TTFT for current turn in milliseconds (or None if not recorded)."""
        return self._ttft.ttft_ms

    # ─────────────────────────────────────────────────────────────────
    # Token Tracking
    # ─────────────────────────────────────────────────────────────────

    def add_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """
        Add tokens to the running total.

        Args:
            input_tokens: Number of input tokens to add
            output_tokens: Number of output tokens to add
        """
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens

    def set_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """
        Set token counts directly (e.g., from restored state).

        Args:
            input_tokens: Input token count
            output_tokens: Output token count
        """
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    # ─────────────────────────────────────────────────────────────────
    # Turn Tracking
    # ─────────────────────────────────────────────────────────────────

    def start_turn(self) -> int:
        """
        Start a new turn. Call this when user input is received.

        Returns:
            The new turn number
        """
        self._turn_count += 1
        self._ttft.turn_number = self._turn_count
        self._ttft.start_time = time.perf_counter()
        self._ttft.first_token_time = None
        return self._turn_count

    def record_first_token(self) -> float | None:
        """
        Record first token received from LLM.

        Call this when the first token of the response is received.
        Only returns TTFT on the *first* call per turn; subsequent calls return None.

        Returns:
            TTFT in milliseconds on first call, None on subsequent calls or if turn not started
        """
        if self._ttft.start_time is None:
            return None

        # Only record and return TTFT on the actual first token
        if self._ttft.first_token_time is None:
            self._ttft.first_token_time = time.perf_counter()
            return self._ttft.ttft_ms

        # Already recorded first token this turn
        return None

    def record_response(self) -> None:
        """Increment response count for current agent session."""
        self._response_count += 1

    # ─────────────────────────────────────────────────────────────────
    # Agent Switch
    # ─────────────────────────────────────────────────────────────────

    def reset_for_agent_switch(self, new_agent: str) -> AgentSessionSummary:
        """
        Reset metrics for agent switch, returning summary of previous agent.

        Args:
            new_agent: Name of the new agent

        Returns:
            AgentSessionSummary for the previous agent session
        """
        # Capture summary before reset
        summary = AgentSessionSummary(
            agent_name=self._agent_name,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            total_tokens=self.total_tokens,
            duration_ms=self.duration_ms,
            turn_count=self._turn_count,
            response_count=self._response_count,
        )

        # Reset for new agent
        self._agent_name = new_agent
        self._input_tokens = 0
        self._output_tokens = 0
        self._agent_start_time = time.perf_counter()
        # Note: turn_count is NOT reset - it's session-wide
        self._response_count = 0
        self._ttft.reset()

        logger.debug(
            "Metrics reset for agent switch | %s → %s | prev_tokens=%d",
            summary.agent_name,
            new_agent,
            summary.total_tokens,
        )

        return summary

    # ─────────────────────────────────────────────────────────────────
    # State Serialization
    # ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """
        Get current metrics as dictionary.

        Returns:
            Dictionary with all current metrics
        """
        return {
            "agent_name": self._agent_name,
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "turn_count": self._turn_count,
            "response_count": self._response_count,
            "current_ttft_ms": self.current_ttft_ms,
        }

    def to_memo_state(self) -> dict[str, Any]:
        """
        Get state for MemoManager persistence.

        Returns:
            Dictionary suitable for storing in MemoManager
        """
        return {
            "input": self._input_tokens,
            "output": self._output_tokens,
        }

    def restore_from_memo(self, tokens: dict[str, Any] | None) -> None:
        """
        Restore state from MemoManager.

        Args:
            tokens: Dictionary from MemoManager with input/output keys
        """
        if tokens and isinstance(tokens, dict):
            self._input_tokens = tokens.get("input", 0)
            self._output_tokens = tokens.get("output", 0)

    # ─────────────────────────────────────────────────────────────────
    # Telemetry Integration
    # ─────────────────────────────────────────────────────────────────

    def get_span_attributes(self) -> dict[str, Any]:
        """
        Get attributes for OpenTelemetry span.

        Returns:
            Dictionary of span attributes
        """
        attrs = {
            "genai.usage.input_tokens": self._input_tokens,
            "genai.usage.output_tokens": self._output_tokens,
            "orchestrator.agent_name": self._agent_name,
            "orchestrator.turn_count": self._turn_count,
            "orchestrator.duration_ms": self.duration_ms,
        }

        if self._call_connection_id:
            attrs["call_connection_id"] = self._call_connection_id
        if self._session_id:
            attrs["session_id"] = self._session_id
        if self.current_ttft_ms is not None:
            attrs["llm.ttft_ms"] = self.current_ttft_ms

        return attrs


__all__ = [
    "OrchestratorMetrics",
    "AgentSessionSummary",
    "TTFTMetrics",
]
