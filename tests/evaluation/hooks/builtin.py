"""
Built-in Hooks
==============

Standard hooks provided by the evaluation framework.

Available Hooks
---------------
- log_metrics: Log turn metrics to console
- validate_expectations: Run expectation checks after each turn
- capture_reasoning: Extract reasoning tokens for o-series models
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from utils.ml_logging import get_logger

from .base import TurnHook, ToolHook, PreScoreHook, HookResult
from .registry import register_builtin

if TYPE_CHECKING:
    from tests.evaluation.schemas import TurnEvent

logger = get_logger(__name__)


class LogMetricsHook(TurnHook):
    """
    Log turn metrics to console after each turn.

    Outputs:
    - Turn ID and timing
    - Tools called
    - Response preview
    - Handoff info (if any)
    """

    async def on_turn_complete(
        self,
        turn: "TurnEvent",
        context: dict[str, Any],
    ) -> HookResult:
        """Log metrics for the completed turn."""
        tools = [tc.name for tc in turn.tool_calls] if turn.tool_calls else []
        handoff = turn.handoff.target_agent if turn.handoff else None

        # Calculate response preview
        response_preview = turn.response_text[:80] + "..." if len(turn.response_text) > 80 else turn.response_text
        response_preview = response_preview.replace("\n", " ")

        logger.info(
            "Turn %s | tools=%s handoff=%s latency=%.0fms | %s",
            turn.turn_id,
            tools or "(none)",
            handoff or "(none)",
            turn.e2e_ms or 0,
            response_preview,
        )

        return HookResult()


class ValidateExpectationsHook(TurnHook):
    """
    Run expectation validation after each turn.

    Validates:
    - Required tools were called
    - Forbidden tools were not called
    - Handoff happened as expected
    - Response constraints met

    Results are added to hook metadata under "validation".
    """

    async def on_turn_complete(
        self,
        turn: "TurnEvent",
        context: dict[str, Any],
    ) -> HookResult:
        """Validate turn against expectations."""
        expectations = context.get("expectations", {})
        if not expectations:
            return HookResult()

        # Lazy import to avoid circular dependency
        from tests.evaluation.validator import ExpectationValidator

        validator = ExpectationValidator()
        result = validator.validate_turn(turn, expectations)

        metadata = {
            "validation": {
                "passed": result.passed,
                "checks": len(result.checks),
                "failed": result.failed_checks,
            }
        }

        warnings = []
        if not result.passed:
            warnings.append(f"Validation failed: {result.message}")

        return HookResult(metadata=metadata, warnings=warnings)


class CaptureReasoningHook(TurnHook):
    """
    Extract reasoning tokens for o-series models.

    Captures:
    - reasoning_tokens from TurnEvent
    - Model config reasoning flags

    Results are added to hook metadata under "reasoning".
    """

    async def on_turn_complete(
        self,
        turn: "TurnEvent",
        context: dict[str, Any],
    ) -> HookResult:
        """Extract reasoning information from turn."""
        metadata: dict[str, Any] = {}

        # Check for reasoning tokens in TurnEvent
        if turn.reasoning_tokens:
            metadata["reasoning"] = {
                "tokens": turn.reasoning_tokens,
                "model": turn.eval_model_config.model_name,
                "include_reasoning": turn.eval_model_config.include_reasoning or False,
            }

        # Add reasoning effort if set
        if turn.eval_model_config.reasoning_effort:
            if "reasoning" not in metadata:
                metadata["reasoning"] = {}
            metadata["reasoning"]["effort"] = turn.eval_model_config.reasoning_effort

        return HookResult(metadata=metadata)


class ToolResultValidatorHook(ToolHook):
    """
    Validate tool results for common issues.

    Checks:
    - Tool returned valid data (not None/empty)
    - No error indicators in result
    - Result type matches expected schema (future)
    """

    async def on_tool_complete(
        self,
        tool_name: str,
        tool_result: Any,
        turn_context: dict[str, Any],
    ) -> HookResult:
        """Validate tool result."""
        warnings = []

        # Check for empty/null results
        if tool_result is None:
            warnings.append(f"Tool '{tool_name}' returned None")
        elif isinstance(tool_result, dict) and not tool_result:
            warnings.append(f"Tool '{tool_name}' returned empty dict")
        elif isinstance(tool_result, str) and not tool_result.strip():
            warnings.append(f"Tool '{tool_name}' returned empty string")

        # Check for error indicators
        if isinstance(tool_result, dict):
            if tool_result.get("error"):
                warnings.append(f"Tool '{tool_name}' returned error: {tool_result['error']}")
            if tool_result.get("status") == "error":
                warnings.append(f"Tool '{tool_name}' status=error")

        return HookResult(warnings=warnings)


class AggregateMetricsHook(PreScoreHook):
    """
    Compute aggregate metrics across all turns before scoring.

    Computes:
    - Total tool calls
    - Unique agents used
    - Handoff chain analysis
    """

    async def pre_score(
        self,
        events: list["TurnEvent"],
        context: dict[str, Any],
    ) -> HookResult:
        """Compute aggregate metrics."""
        total_tools = 0
        unique_tools = set()
        agents_used = set()
        handoff_chain = []

        for event in events:
            # Count tools
            if event.tool_calls:
                total_tools += len(event.tool_calls)
                unique_tools.update(tc.name for tc in event.tool_calls)

            # Track agents and handoffs
            if event.agent_name:
                agents_used.add(event.agent_name)
            if event.handoff and event.handoff.target_agent:
                handoff_chain.append(f"{event.agent_name}->{event.handoff.target_agent}")

        metadata = {
            "aggregate": {
                "total_tool_calls": total_tools,
                "unique_tools": list(unique_tools),
                "unique_tool_count": len(unique_tools),
                "agents_used": list(agents_used),
                "agent_count": len(agents_used),
                "handoff_chain": handoff_chain,
            }
        }

        return HookResult(metadata=metadata)


# Register built-in hooks
register_builtin("log_metrics", LogMetricsHook)
register_builtin("validate_expectations", ValidateExpectationsHook)
register_builtin("capture_reasoning", CaptureReasoningHook)
register_builtin("validate_tool_result", ToolResultValidatorHook)
register_builtin("aggregate_metrics", AggregateMetricsHook)
