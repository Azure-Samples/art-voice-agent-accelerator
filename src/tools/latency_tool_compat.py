"""
Direct backwards compatibility wrapper for LatencyTool.

This module provides a drop-in replacement for the original LatencyTool
that uses the new LatencyToolV2 implementation under the hood while
maintaining 100% API compatibility.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from utils.ml_logging import get_logger

from src.tools.latency_tool_v2 import LatencyToolV2

logger = get_logger("tools.latency_compat")


class LatencyTool:
    """
    Drop-in replacement for the original LatencyTool.

    This class provides the exact same interface as the original LatencyTool
    but uses LatencyToolV2 internally for enhanced OpenTelemetry-based tracking.

    Usage:
        # Replace this:
        # from src.tools.latency_tool import LatencyTool

        # With this:
        from src.tools.latency_tool_compat import LatencyTool

        # All existing code will work unchanged
        latency_tool = LatencyTool(cm)
        latency_tool.begin_run("turn")
        latency_tool.start("llm")
        latency_tool.stop("llm", redis_mgr)
    """

    def __init__(self, cm, tracer: trace.Tracer | None = None):
        self.cm = cm

        # Get tracer - either provided or from global
        if tracer is None:
            try:
                tracer = trace.get_tracer(__name__)
            except Exception as e:
                logger.warning(f"Failed to get OpenTelemetry tracer: {e}")
                # Create a no-op tracer for fallback
                tracer = trace.NoOpTracer()

        # Create V2 tool with backwards compatibility
        self._v2_tool = LatencyToolV2(tracer, cm)

        logger.debug("LatencyTool compatibility wrapper initialized")

    def set_current_run(self, run_id: str) -> None:
        """Set current run for this connection."""
        return self._v2_tool.set_current_run(run_id)

    def get_current_run(self) -> str | None:
        """Get current run ID."""
        return self._v2_tool.get_current_run()

    def begin_run(self, label: str = "turn") -> str:
        """Begin a new run."""
        return self._v2_tool.begin_run(label)

    def start(self, stage: str) -> None:
        """Start timing a stage."""
        return self._v2_tool.start(stage)

    def stop(self, stage: str, redis_mgr, *, meta: dict[str, Any] | None = None) -> None:
        """Stop timing a stage."""
        return self._v2_tool.stop(stage, redis_mgr, meta=meta)

    def session_summary(self) -> dict[str, dict[str, float]]:
        """Get session summary for dashboards."""
        return self._v2_tool.session_summary()

    def run_summary(self, run_id: str) -> dict[str, dict[str, float]]:
        """Get run summary for specific run."""
        return self._v2_tool.run_summary(run_id)

    def cleanup_timers(self) -> None:
        """Clean up active timers on session disconnect."""
        return self._v2_tool.cleanup_timers()

    # Additional properties for full compatibility
    @property
    def _active_timers(self):
        """Expose active timers for compatibility."""
        return self._v2_tool._active_timers

    @property
    def _store(self):
        """Expose internal store for compatibility (returns None for V2)."""
        logger.debug("Accessing deprecated _store property - consider migrating to V2 API")
        return None


# Legacy import compatibility
# This allows existing imports to continue working
def create_latency_tool(cm, tracer: trace.Tracer | None = None) -> LatencyTool:
    """
    Factory function to create a LatencyTool with backwards compatibility.

    Args:
        cm: Core memory instance
        tracer: Optional OpenTelemetry tracer (will use global if not provided)

    Returns:
        LatencyTool instance with V2 implementation
    """
    return LatencyTool(cm, tracer)
