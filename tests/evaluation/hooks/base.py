"""
Hook Base Classes
=================

Abstract interfaces for evaluation hooks.

These hooks allow custom analysis and metadata injection without
modifying core evaluation framework code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from tests.evaluation.schemas import TurnEvent


@dataclass
class HookResult:
    """Result returned from a hook execution."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata to attach to the turn/event."""

    warnings: list[str] = field(default_factory=list)
    """Non-fatal warnings encountered during hook execution."""

    def merge(self, other: "HookResult") -> "HookResult":
        """Merge another HookResult into this one."""
        return HookResult(
            metadata={**self.metadata, **other.metadata},
            warnings=[*self.warnings, *other.warnings],
        )


class TurnHook(ABC):
    """
    Hook called after each turn completes.

    Use for:
    - Custom metrics computation
    - Sentiment/quality analysis
    - External system notifications
    - Logging/debugging

    Example
    -------
    ```python
    class SentimentHook(TurnHook):
        async def on_turn_complete(self, turn, context):
            score = await analyze_sentiment(turn.response_text)
            return HookResult(metadata={"sentiment": score})
    ```
    """

    @abstractmethod
    async def on_turn_complete(
        self,
        turn: "TurnEvent",
        context: dict[str, Any],
    ) -> HookResult:
        """
        Called after each turn completes.

        Args:
            turn: The completed turn event with all recorded data
            context: Execution context including:
                - scenario_name: Current scenario name
                - variant_id: Current variant (if comparison)
                - turn_id: Turn identifier
                - run_id: Run identifier
                - expectations: Turn expectations (if defined)

        Returns:
            HookResult with optional metadata to attach to turn
        """
        pass


class ToolHook(ABC):
    """
    Hook called after each tool execution.

    Use for:
    - Tool-specific validation
    - Result quality checks
    - Tool usage analytics
    - Performance monitoring

    Example
    -------
    ```python
    class ToolValidatorHook(ToolHook):
        async def on_tool_complete(self, tool_name, result, context):
            if tool_name == "get_balance" and result.get("balance") < 0:
                return HookResult(warnings=["Negative balance detected"])
            return HookResult()
    ```
    """

    @abstractmethod
    async def on_tool_complete(
        self,
        tool_name: str,
        tool_result: Any,
        turn_context: dict[str, Any],
    ) -> HookResult:
        """
        Called after each tool execution.

        Args:
            tool_name: Name of the tool that was called
            tool_result: Result returned by the tool
            turn_context: Current turn context including:
                - turn_id: Current turn identifier
                - user_input: User's input text
                - tools_called_so_far: List of tools called in this turn

        Returns:
            HookResult with optional metadata to attach
        """
        pass


class PreScoreHook(ABC):
    """
    Hook called before metrics scoring.

    Use for:
    - Custom domain-specific metrics
    - Aggregating turn-level hook results
    - Pre-processing data for scoring
    - Adding computed fields

    Example
    -------
    ```python
    class DomainMetricsHook(PreScoreHook):
        async def pre_score(self, events, context):
            banking_accuracy = self._compute_banking_accuracy(events)
            return HookResult(metadata={"banking_accuracy": banking_accuracy})
    ```
    """

    @abstractmethod
    async def pre_score(
        self,
        events: list["TurnEvent"],
        context: dict[str, Any],
    ) -> HookResult:
        """
        Called before metrics scoring begins.

        Args:
            events: All turn events for the scenario run
            context: Scoring context including:
                - scenario_name: Scenario being scored
                - run_id: Run identifier
                - expectations: Global scenario expectations

        Returns:
            HookResult with optional metadata to include in summary
        """
        pass
