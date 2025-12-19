"""
Migration Guide: LatencyTool V1 to V2

This guide helps migrate from the legacy latency tool to the new OpenTelemetry-based
v2 latency tool. It provides compatibility wrappers and migration strategies.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from utils.ml_logging import get_logger

from src.tools.latency_tool_v2 import ConversationTurnTracker, LatencyToolV2

logger = get_logger("tools.latency_migration")


class LatencyToolV1CompatibilityWrapper:
    """
    Compatibility wrapper that provides the old V1 API while using V2 internally.

    This allows gradual migration from V1 to V2 without breaking existing code.
    Use this as a drop-in replacement for the old LatencyTool.
    """

    def __init__(self, tracer: trace.Tracer, cm=None):
        self.v2_tool = LatencyToolV2(tracer)
        self.cm = cm  # Keep for backward compatibility

        # Track current turn and active operations
        self._current_tracker: ConversationTurnTracker | None = None
        self._active_operations: dict[str, Any] = {}
        self._current_run_id: str | None = None

    def set_current_run(self, run_id: str) -> None:
        """Legacy V1 method - adapted to V2."""
        self._current_run_id = run_id
        if self._current_tracker:
            self._current_tracker.add_metadata("legacy_run_id", run_id)

    def get_current_run(self) -> str | None:
        """Legacy V1 method - adapted to V2."""
        return self._current_run_id or (
            self._current_tracker.metrics.turn_id if self._current_tracker else None
        )

    def begin_run(self, label: str = "turn") -> str:
        """Legacy V1 method - creates new V2 turn tracker."""
        # End any existing tracker
        if self._current_tracker:
            logger.warning("Starting new run while previous run still active")

        # Create new turn tracker
        self._current_tracker = self.v2_tool.create_turn_tracker(turn_id=self._current_run_id)
        self._current_tracker.add_metadata("legacy_label", label)

        # Start the turn context (but don't use context manager here for compatibility)
        self._current_tracker._turn_span = self._current_tracker.tracer.start_span(
            f"conversation.turn.{self._current_tracker.metrics.turn_id}",
            kind=trace.SpanKind.INTERNAL,
            attributes=self._current_tracker._get_base_attributes(),
        )

        run_id = self._current_tracker.metrics.turn_id
        self._current_run_id = run_id

        logger.info(f"Legacy begin_run called - created turn {run_id}")
        return run_id

    def start(self, stage: str) -> None:
        """Legacy V1 method - adapted to V2 span tracking."""
        if not self._current_tracker:
            logger.warning(f"start({stage}) called without active run, creating one")
            self.begin_run()

        if stage in self._active_operations:
            logger.debug(f"Stage '{stage}' already started, ignoring duplicate start")
            return

        # Map legacy stages to V2 tracking methods
        stage_mapping = {
            "stt": "user_input",
            "speech_to_text": "user_input",
            "llm": "llm_inference",
            "llm_inference": "llm_inference",
            "openai": "llm_inference",
            "azure_openai": "llm_inference",
            "tts": "tts_synthesis",
            "text_to_speech": "tts_synthesis",
            "synthesis": "tts_synthesis",
            "network": "network_delivery",
            "delivery": "network_delivery",
        }

        v2_phase = stage_mapping.get(stage, "custom")

        if v2_phase == "custom":
            # Handle custom stages with generic tracking
            attrs = self._current_tracker._get_base_attributes()
            attrs.update(
                {
                    "conversation.turn.phase": f"custom_{stage}",
                    "legacy.stage_name": stage,
                }
            )

            span = self._current_tracker.tracer.start_span(
                f"conversation.turn.legacy_{stage}",
                kind=trace.SpanKind.INTERNAL,
                attributes=attrs,
            )

            self._active_operations[stage] = {
                "type": "custom",
                "span": span,
                "start_time": trace.time_ns(),
            }
        else:
            # For known stages, we'll track them when stop() is called
            self._active_operations[stage] = {
                "type": "mapped",
                "v2_phase": v2_phase,
                "start_time": trace.time_ns(),
            }

        logger.debug(f"Legacy start({stage}) -> {v2_phase}")

    def stop(self, stage: str, redis_mgr=None, *, meta: dict[str, Any] | None = None) -> None:
        """Legacy V1 method - adapted to V2 span tracking."""
        if not self._current_tracker:
            logger.warning(f"stop({stage}) called without active run")
            return

        if stage not in self._active_operations:
            logger.debug(f"stop({stage}) called without matching start")
            return

        operation = self._active_operations.pop(stage)

        if operation["type"] == "custom":
            # End custom span
            operation["span"].end()
        elif operation["type"] == "mapped":
            # Handle mapped stages with proper V2 tracking
            v2_phase = operation["v2_phase"]

            # Create appropriate V2 context for this phase
            if v2_phase == "user_input":
                with self._current_tracker.track_user_input() as span:
                    if meta:
                        for key, value in meta.items():
                            span.set_attribute(f"legacy.meta.{key}", str(value))
            elif v2_phase == "llm_inference":
                # Extract LLM-specific metadata if available
                model_name = (meta or {}).get("model", "unknown")
                prompt_tokens = (meta or {}).get("prompt_tokens")

                with self._current_tracker.track_llm_inference(model_name, prompt_tokens) as (
                    span,
                    mark_first_token,
                ):
                    if meta:
                        for key, value in meta.items():
                            span.set_attribute(f"legacy.meta.{key}", str(value))
                        # Auto-mark first token if we have completion info
                        if "completion_tokens" in meta:
                            mark_first_token()
                            self._current_tracker.set_llm_completion_tokens(
                                meta["completion_tokens"]
                            )
            elif v2_phase == "tts_synthesis":
                # Extract TTS-specific metadata
                text_length = (meta or {}).get("text_length", 0)
                voice_name = (meta or {}).get("voice_name")

                with self._current_tracker.track_tts_synthesis(text_length, voice_name) as (
                    span,
                    mark_chunk,
                ):
                    if meta:
                        for key, value in meta.items():
                            span.set_attribute(f"legacy.meta.{key}", str(value))
                        # Auto-mark chunks if we have chunk info
                        if "chunk_count" in meta:
                            for _ in range(meta["chunk_count"]):
                                mark_chunk()
            elif v2_phase == "network_delivery":
                transport = (meta or {}).get("transport", "websocket")
                with self._current_tracker.track_network_delivery(transport) as span:
                    if meta:
                        for key, value in meta.items():
                            span.set_attribute(f"legacy.meta.{key}", str(value))

        # Legacy persistence - for V2 this is handled automatically via spans
        if redis_mgr and self.cm:
            try:
                self.cm.persist_to_redis(redis_mgr)
            except Exception as e:
                logger.error(f"Failed to persist legacy compatibility data: {e}")

        logger.debug(f"Legacy stop({stage}) completed")

    def cleanup_timers(self) -> None:
        """Legacy V1 method - cleanup active operations."""
        for stage, operation in self._active_operations.items():
            logger.warning(f"Cleaning up unclosed operation: {stage}")
            if operation["type"] == "custom" and "span" in operation:
                operation["span"].end()

        self._active_operations.clear()

        # End turn span if active
        if self._current_tracker and self._current_tracker._turn_span:
            self._current_tracker._turn_span.end()
            self._current_tracker = None

    def session_summary(self) -> dict[str, dict[str, float]]:
        """Legacy V1 method - return empty dict (use V2 metrics instead)."""
        logger.warning("session_summary() is deprecated, use V2 metrics instead")
        return {}

    def run_summary(self, run_id: str) -> dict[str, dict[str, float]]:
        """Legacy V1 method - return empty dict (use V2 metrics instead)."""
        logger.warning("run_summary() is deprecated, use V2 metrics instead")
        return {}


class GradualMigrationHelper:
    """
    Helper class to gradually migrate from V1 to V2 patterns.

    Provides utilities to identify migration opportunities and convert
    existing V1 usage patterns to V2.
    """

    def __init__(self, v1_tool, v2_tool: LatencyToolV2):
        self.v1_tool = v1_tool
        self.v2_tool = v2_tool

    @contextmanager
    def migrate_stage_tracking(
        self,
        stage: str,
        call_connection_id: str | None = None,
        session_id: str | None = None,
        **metadata,
    ):
        """
        Context manager that provides both V1 and V2 tracking for comparison.

        Usage:
            with migration_helper.migrate_stage_tracking("llm", call_id, session_id) as (v1_tracker, v2_tracker):
                # Your existing code here
                pass
        """
        # Start V1 tracking
        self.v1_tool.start(stage)

        # Start V2 tracking
        if not hasattr(self, "_v2_turn_tracker") or self._v2_turn_tracker is None:
            self._v2_turn_tracker = self.v2_tool.create_turn_tracker(
                call_connection_id=call_connection_id,
                session_id=session_id,
            )

        # Map stage to appropriate V2 method
        stage_contexts = {
            "stt": lambda: self._v2_turn_tracker.track_user_input(),
            "llm": lambda: self._v2_turn_tracker.track_llm_inference(
                metadata.get("model", "unknown"), metadata.get("prompt_tokens")
            ),
            "tts": lambda: self._v2_turn_tracker.track_tts_synthesis(
                metadata.get("text_length", 0), metadata.get("voice_name")
            ),
            "network": lambda: self._v2_turn_tracker.track_network_delivery(),
        }

        v2_context = stage_contexts.get(
            stage, lambda: self._v2_turn_tracker._track_phase(f"legacy_{stage}")
        )

        try:
            with v2_context() as v2_span:
                yield self.v1_tool, (v2_span, self._v2_turn_tracker)
        finally:
            # Stop V1 tracking
            self.v1_tool.stop(stage, None, meta=metadata)

    def analyze_migration_opportunities(self, code_file: str) -> dict[str, Any]:
        """
        Analyze code file for V1 usage patterns and suggest V2 migrations.

        This would typically be used as part of a code analysis tool.
        """
        suggestions = {
            "v1_patterns_found": [],
            "suggested_v2_replacements": [],
            "migration_complexity": "low",
        }

        # This would be implemented with actual code analysis
        # For now, return a template

        suggestions["v1_patterns_found"] = [
            "latency_tool.start('llm')",
            "latency_tool.stop('llm', redis_mgr)",
        ]

        suggestions["suggested_v2_replacements"] = [
            "with tracker.track_llm_inference(model_name, prompt_tokens) as (span, mark_first_token):",
        ]

        return suggestions


# Migration examples and patterns
def example_v1_to_v2_migration():
    """
    Example showing how to migrate from V1 to V2 patterns.
    """

    # OLD V1 Pattern
    def old_llm_processing_v1(latency_tool, redis_mgr, text: str):
        latency_tool.start("llm")
        try:
            # LLM processing code
            response = "example response"
            return response
        finally:
            latency_tool.stop("llm", redis_mgr, meta={"text_length": len(text)})

    # NEW V2 Pattern
    async def new_llm_processing_v2(
        turn_tracker: ConversationTurnTracker, text: str, model: str = "gpt-4"
    ):
        with turn_tracker.track_llm_inference(model, len(text) // 4) as (span, mark_first_token):
            span.add_event("llm.processing_started", {"input_length": len(text)})

            # LLM processing code
            mark_first_token()  # Call when first token received
            response = "example response"
            turn_tracker.set_llm_completion_tokens(len(response) // 4)

            span.add_event("llm.processing_completed", {"output_length": len(response)})
            return response


def create_migration_wrapper(
    existing_v1_tool, tracer: trace.Tracer
) -> LatencyToolV1CompatibilityWrapper:
    """
    Create a compatibility wrapper for gradual migration.

    This allows you to replace your existing V1 tool with minimal code changes
    while getting V2 benefits under the hood.
    """
    wrapper = LatencyToolV1CompatibilityWrapper(
        tracer, existing_v1_tool.cm if hasattr(existing_v1_tool, "cm") else None
    )

    logger.info("Created V1 compatibility wrapper - migration helper active")
    return wrapper


# Example of side-by-side comparison during migration
async def example_side_by_side_comparison(v1_tool, v2_tool: LatencyToolV2):
    """
    Example showing how to run V1 and V2 tracking side-by-side for comparison.
    """
    # V1 tracking
    v1_tool.begin_run("comparison_test")
    v1_tool.start("llm")

    # V2 tracking
    with v2_tool.track_conversation_turn() as v2_tracker:
        with v2_tracker.track_llm_inference("gpt-4", 100) as (span, mark_first_token):
            # Simulate work
            await asyncio.sleep(0.5)
            mark_first_token()
            await asyncio.sleep(0.3)
            v2_tracker.set_llm_completion_tokens(75)

    # End V1 tracking
    v1_tool.stop("llm", None)

    # Compare results
    v1_summary = v1_tool.run_summary(v1_tool.get_current_run())
    v2_metrics = v2_tracker.get_metrics_summary()

    logger.info(f"V1 duration: {v1_summary.get('llm', {}).get('total', 0):.3f}s")
    logger.info(f"V2 duration: {v2_metrics['durations']['llm_inference_ms']/1000:.3f}s")

    return {
        "v1_results": v1_summary,
        "v2_results": v2_metrics,
    }


# ============================================================================
# Direct Drop-in Replacement Strategy
# ============================================================================


def migrate_with_direct_replacement():
    """
    The simplest migration strategy: direct import replacement.

    Step 1: Replace the import
    OLD: from src.tools.latency_tool import LatencyTool
    NEW: from src.tools.latency_tool_compat import LatencyTool

    Step 2: That's it! All existing code works unchanged.

    The compatibility wrapper automatically uses LatencyToolV2 under the hood
    while maintaining the exact same API surface.
    """

    # Example of zero-code-change migration:

    # OLD CODE (still works):
    def old_websocket_handler(websocket, cm, redis_mgr):
        from src.tools.latency_tool_compat import LatencyTool  # Only change needed

        latency_tool = LatencyTool(cm)  # Same constructor

        run_id = latency_tool.begin_run("voice_interaction")  # Same API
        latency_tool.start("stt")  # Same API

        # ... existing processing code ...

        latency_tool.stop("stt", redis_mgr)  # Same API
        latency_tool.start("llm")

        # ... more existing code ...

        latency_tool.stop("llm", redis_mgr, meta={"tokens": 150})
        latency_tool.cleanup_timers()  # Same cleanup

        # All existing dashboard code works unchanged
        summary = latency_tool.session_summary()
        return summary


def setup_direct_replacement_with_tracer(cm, tracer: trace.Tracer):
    """
    Set up the compatibility wrapper with a specific tracer.

    This gives you the benefits of V2 OpenTelemetry integration
    while maintaining the V1 API.
    """
    from src.tools.latency_tool_compat import LatencyTool

    # Create with explicit tracer for better telemetry
    latency_tool = LatencyTool(cm, tracer)

    logger.info("Direct replacement LatencyTool initialized with custom tracer")
    return latency_tool
