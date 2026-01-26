"""
Evaluation Wrappers
===================

Wrapper classes for orchestrators - ZERO modifications to production code.

CRITICAL: This module does NOT modify Custom Cascade Orchestrators.
It wraps existing orchestrators using composition to inject recording capabilities.

The wrapper pattern allows us to:
1. Keep production code completely untouched
2. Add evaluation instrumentation externally
3. Use existing callbacks (on_tool_start, on_tool_end, on_agent_switch)
4. Maintain drop-in compatibility via __getattr__ delegation
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from apps.artagent.backend.evaluation.recorder import EventRecorder
from apps.artagent.backend.evaluation.schemas import EvalModelConfig
from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from apps.artagent.backend.voice import OrchestratorContext, OrchestratorResult
    from apps.artagent.backend.voice.speech_cascade.orchestrator import (
        CascadeOrchestratorAdapter,
    )

logger = get_logger(__name__)


class EvaluationOrchestratorWrapper:
    """
    Wraps CascadeOrchestratorAdapter to inject evaluation recording.

    Does NOT modify or inherit from the real orchestrator.
    Uses composition to delegate all real work to the wrapped instance.

    Key design principles:
    - Composition over inheritance (self._orchestrator holds real instance)
    - Non-invasive (wraps callbacks, doesn't modify orchestrator methods)
    - Transparent (uses __getattr__ for drop-in compatibility)
    - Standalone (only depends on EventRecorder, not production internals)
    """

    def __init__(
        self,
        orchestrator: CascadeOrchestratorAdapter,
        recorder: EventRecorder,
    ):
        """
        Initialize wrapper.

        Args:
            orchestrator: The REAL Custom Cascade Orchestrator instance
            recorder: EventRecorder to capture metrics
        """
        self._orchestrator = orchestrator
        self._recorder = recorder
        self._tool_call_timestamps: Dict[str, float] = {}

        logger.info(
            f"EvaluationOrchestratorWrapper initialized | "
            f"orchestrator={type(orchestrator).__name__} "
            f"recorder={recorder.run_id}"
        )

    async def process_turn(
        self,
        context: OrchestratorContext,
        on_tts_chunk: Optional[Callable] = None,
        on_tool_start: Optional[Callable] = None,
        on_tool_end: Optional[Callable] = None,
        on_agent_switch: Optional[Callable] = None,
        **kwargs,
    ) -> OrchestratorResult:
        """
        Wrap process_turn to inject recording WITHOUT modifying source.

        Strategy:
        1. Record turn start with metadata
        2. Wrap existing callbacks to also record events
        3. Delegate to real orchestrator (zero production code changes!)
        4. Record turn end with results
        5. Return real orchestrator result unchanged

        Args:
            context: Orchestrator context (from production code)
            on_tts_chunk: Optional TTS chunk callback
            on_tool_start: Optional tool start callback
            on_tool_end: Optional tool end callback
            on_agent_switch: Optional agent switch callback
            **kwargs: Additional kwargs passed to orchestrator

        Returns:
            OrchestratorResult from real orchestrator (unchanged)
        """
        turn_start = time.perf_counter()
        turn_id = context.metadata.get("run_id", f"turn_{int(time.time())}")

        # Get active agent from orchestrator
        active_agent = getattr(self._orchestrator, "_active_agent", None) or "unknown"

        # Extract context for evidence
        context_dict = {
            "caller_name": context.metadata.get("caller_name"),
            "client_id": context.metadata.get("client_id"),
            "customer_intelligence": context.metadata.get("customer_intelligence"),
            "session_profile": context.metadata.get("session_profile"),
        }
        context_dict = {k: v for k, v in context_dict.items() if v is not None}

        # Record turn start
        self._recorder.record_turn_start(
            turn_id=turn_id,
            agent=active_agent,
            user_text=context.user_text,
            timestamp=turn_start,
            context=context_dict,
        )

        # Wrap callbacks to also record (chain with original callbacks)
        wrapped_on_tool_start = self._wrap_tool_start_callback(on_tool_start)
        wrapped_on_tool_end = self._wrap_tool_end_callback(on_tool_end)
        wrapped_on_agent_switch = self._wrap_agent_switch_callback(on_agent_switch)

        # Delegate to REAL orchestrator (zero changes to production code!)
        try:
            result = await self._orchestrator.process_turn(
                context,
                on_tts_chunk=on_tts_chunk,
                on_tool_start=wrapped_on_tool_start,
                on_tool_end=wrapped_on_tool_end,
                **kwargs,
            )

            # Record turn end (success)
            turn_end = time.perf_counter()
            final_agent = getattr(self._orchestrator, "_active_agent", None) or active_agent

            # Extract model config from orchestrator state
            model_config = self._extract_model_config(final_agent)

            self._recorder.record_turn_end(
                turn_id=turn_id,
                agent=final_agent,
                response_text=result.response_text or "",
                e2e_ms=(turn_end - turn_start) * 1000,
                timestamp=turn_end,
                model_config=model_config,
                response_tokens=getattr(result, "response_tokens", None),
                input_tokens=getattr(result, "input_tokens", None),
                error=result.error if hasattr(result, "error") else None,
            )

            return result

        except Exception as exc:
            # Record turn end (error)
            turn_end = time.perf_counter()
            self._recorder.record_turn_end(
                turn_id=turn_id,
                agent=active_agent,
                response_text="",
                e2e_ms=(turn_end - turn_start) * 1000,
                timestamp=turn_end,
                model_config=self._extract_model_config(active_agent),
                error=str(exc),
            )
            raise

    def _wrap_tool_start_callback(
        self, original_callback: Optional[Callable]
    ) -> Callable:
        """Wrap tool_start callback to also record to EventRecorder."""

        async def wrapped(tool_name: str, arguments: Any):
            ts = time.perf_counter()
            self._tool_call_timestamps[tool_name] = ts

            # Record to EventRecorder
            self._recorder.record_tool_start(tool_name, arguments, ts)

            # Call original callback if exists
            if original_callback:
                await original_callback(tool_name, arguments)

        return wrapped

    def _wrap_tool_end_callback(
        self, original_callback: Optional[Callable]
    ) -> Callable:
        """Wrap tool_end callback to also record to EventRecorder."""

        async def wrapped(tool_name: str, result: Any):
            ts = time.perf_counter()
            start_ts = self._tool_call_timestamps.pop(tool_name, ts)

            # Record to EventRecorder
            self._recorder.record_tool_end(tool_name, result, ts, start_ts)

            # Call original callback if exists
            if original_callback:
                await original_callback(tool_name, result)

        return wrapped

    def _wrap_agent_switch_callback(
        self, original_callback: Optional[Callable]
    ) -> Callable:
        """Wrap agent_switch callback to record handoffs."""

        async def wrapped(previous_agent: str, new_agent: str):
            # Record handoff
            self._recorder.record_handoff(
                source_agent=previous_agent,
                target_agent=new_agent,
                timestamp=time.perf_counter(),
            )

            # Call original callback if exists
            if original_callback:
                await original_callback(previous_agent, new_agent)

        return wrapped

    def _extract_model_config(self, agent_name: str) -> EvalModelConfig:
        """
        Extract model configuration from orchestrator state.

        This method attempts to extract model config from the wrapped orchestrator
        without depending on internal implementation details.
        """
        try:
            # Try to get agent config from orchestrator
            agents = getattr(self._orchestrator, "agents", {})
            agent = agents.get(agent_name)

            if agent and hasattr(agent, "model"):
                model = agent.model
                return EvalModelConfig(
                    model_name=getattr(model, "deployment_id", "unknown"),
                    model_family=getattr(model, "model_family", None),
                    endpoint_used=self._detect_endpoint(model),
                    temperature=getattr(model, "temperature", None),
                    top_p=getattr(model, "top_p", None),
                    max_tokens=getattr(model, "max_tokens", None),
                    max_completion_tokens=getattr(model, "max_completion_tokens", None),
                    verbosity=getattr(model, "verbosity", None),
                    reasoning_effort=getattr(model, "reasoning_effort", None),
                    include_reasoning=getattr(model, "include_reasoning", None),
                    min_p=getattr(model, "min_p", None),
                    typical_p=getattr(model, "typical_p", None),
                )
        except Exception as e:
            logger.warning(f"Failed to extract model config: {e}")

        # Fallback to default
        return EvalModelConfig(
            model_name="unknown",
            endpoint_used="chat",
        )

    def _detect_endpoint(self, model: Any) -> str:
        """Detect which API endpoint was used based on model config."""
        # Check explicit preference
        if hasattr(model, "endpoint_preference"):
            pref = model.endpoint_preference
            if pref in ["chat", "responses"]:
                return pref

        # Infer from model family
        if hasattr(model, "model_family"):
            family = model.model_family
            if family in ["o1", "o3", "o4", "gpt-5"]:
                return "responses"

        # Infer from deployment_id
        if hasattr(model, "deployment_id"):
            deployment = model.deployment_id.lower()
            if any(name in deployment for name in ["o1", "o3", "o4", "gpt-5"]):
                return "responses"

        # Default to chat
        return "chat"

    def __getattr__(self, name: str):
        """
        Delegate all other attribute access to the real orchestrator.

        This allows the wrapper to be a drop-in replacement without
        implementing every single method.

        Args:
            name: Attribute name

        Returns:
            Attribute from wrapped orchestrator
        """
        return getattr(self._orchestrator, name)


__all__ = ["EvaluationOrchestratorWrapper"]
