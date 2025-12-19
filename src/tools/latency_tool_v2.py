"""
Latency Tool V2 - OpenTelemetry-based Conversational Turn Tracking

This tool provides detailed latency tracking for conversational turns using
OpenTelemetry spans and semantic attributes. It tracks the complete flow from
user input through LLM inference to TTS synthesis and delivery.

Key improvements over V1:
- OpenTelemetry spans for standardized observability
- Conversational turn-based tracking with detailed breakdown
- LLM inference tracking with token metadata
- TTS synthesis tracking with chunk metadata
- Semantic attributes for rich telemetry data
- Simplified API while maintaining comprehensive metrics
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from utils.ml_logging import get_logger

logger = get_logger("tools.latency_v2")


@dataclass
class ConversationTurnMetrics:
    """Metrics for a complete conversational turn."""

    turn_id: str
    call_connection_id: str | None = None
    session_id: str | None = None
    user_input_duration: float | None = None
    llm_inference_duration: float | None = None
    tts_synthesis_duration: float | None = None
    total_turn_duration: float | None = None

    # LLM-specific metrics
    llm_tokens_prompt: int | None = None
    llm_tokens_completion: int | None = None
    llm_tokens_per_second: float | None = None
    llm_time_to_first_token: float | None = None

    # TTS-specific metrics
    tts_text_length: int | None = None
    tts_audio_duration: float | None = None
    tts_synthesis_speed: float | None = None  # chars per second
    tts_chunk_count: int | None = None

    # Network/transport metrics
    network_latency: float | None = None
    end_to_end_latency: float | None = None

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class LatencyTrackerProtocol(Protocol):
    """Protocol for latency tracking dependencies."""

    def get_tracer(self) -> trace.Tracer:
        """Get the OpenTelemetry tracer instance."""
        ...


class ConversationTurnTracker:
    """
    OpenTelemetry-based tracker for individual conversation turns.

    Provides detailed span-based tracking of each phase in a conversation turn:
    - User input processing
    - LLM inference with token metrics
    - TTS synthesis with audio metrics
    - Network transport and delivery
    """

    def __init__(
        self,
        tracker: LatencyTrackerProtocol,
        turn_id: str | None = None,
        call_connection_id: str | None = None,
        session_id: str | None = None,
    ):
        self.tracker = tracker
        self.tracer = tracker.get_tracer()
        self.metrics = ConversationTurnMetrics(
            turn_id=turn_id or self._generate_turn_id(),
            call_connection_id=call_connection_id,
            session_id=session_id,
        )

        self._turn_span: trace.Span | None = None
        self._active_spans: dict[str, trace.Span] = {}
        self._phase_start_times: dict[str, float] = {}

    def _generate_turn_id(self) -> str:
        """Generate a unique turn ID."""
        return f"turn_{uuid.uuid4().hex[:8]}"

    def _get_base_attributes(self) -> dict[str, Any]:
        """Get base span attributes for all operations."""
        attrs = {
            "conversation.turn.id": self.metrics.turn_id,
            "component": "conversation_tracker",
            "service.version": "2.0.0",
        }

        if self.metrics.call_connection_id:
            attrs["rt.call.connection_id"] = self.metrics.call_connection_id
        if self.metrics.session_id:
            attrs["rt.session.id"] = self.metrics.session_id

        return attrs

    @contextmanager
    def track_turn(self):
        """
        Context manager to track an entire conversation turn.

        Creates a root span for the turn and ensures proper cleanup.
        """
        attrs = self._get_base_attributes()
        attrs.update(
            {
                "conversation.turn.phase": "complete",
                "span.type": "conversation_turn",
            }
        )

        start_time = time.perf_counter()

        # Use descriptive span name: voice.turn.<id>.total for end-to-end tracking
        self._turn_span = self.tracer.start_span(
            f"voice.turn.{self.metrics.turn_id}.total",
            kind=SpanKind.INTERNAL,
            attributes=attrs,
        )

        try:
            logger.info(
                "Starting conversation turn tracking",
                extra={
                    "turn_id": self.metrics.turn_id,
                    "call_connection_id": self.metrics.call_connection_id,
                    "session_id": self.metrics.session_id,
                },
            )
            yield self

            # Calculate total turn duration
            self.metrics.total_turn_duration = time.perf_counter() - start_time

            # Add final metrics to span
            self._add_turn_metrics_to_span()

        except Exception as e:
            if self._turn_span:
                self._turn_span.set_status(Status(StatusCode.ERROR, str(e)))
                self._turn_span.add_event(
                    "conversation.turn.error",
                    {"error.type": type(e).__name__, "error.message": str(e)},
                )
            logger.error(
                f"Error in conversation turn: {e}",
                extra={"turn_id": self.metrics.turn_id, "error": str(e)},
            )
            raise
        finally:
            # Clean up any remaining active spans
            for span_name, span in self._active_spans.items():
                logger.warning(f"Force-closing unclosed span: {span_name}")
                span.end()
            self._active_spans.clear()

            if self._turn_span:
                self._turn_span.end()

            logger.info(
                "Completed conversation turn tracking",
                extra={
                    "turn_id": self.metrics.turn_id,
                    "total_duration_ms": (
                        (self.metrics.total_turn_duration * 1000)
                        if self.metrics.total_turn_duration
                        else None
                    ),
                },
            )

    @contextmanager
    def track_user_input(self, input_type: str = "speech"):
        """
        Track user input processing phase.

        Args:
            input_type: Type of input (speech, text, etc.)
        """
        with self._track_phase(
            "user_input",
            {
                "conversation.input.type": input_type,
                "conversation.turn.phase": "user_input",
            },
        ) as span:
            start_time = time.perf_counter()
            try:
                yield span
            finally:
                self.metrics.user_input_duration = time.perf_counter() - start_time
                span.set_attribute(
                    "conversation.input.duration_ms", self.metrics.user_input_duration * 1000
                )

    @contextmanager
    def track_llm_inference(
        self,
        model_name: str,
        prompt_tokens: int | None = None,
    ):
        """
        Track LLM inference phase with token metrics.

        Args:
            model_name: Name of the LLM model being used
            prompt_tokens: Number of tokens in the prompt
        """
        attrs = {
            "conversation.turn.phase": "llm_inference",
            "llm.model.name": model_name,
            "peer.service": "azure-openai-service",
        }

        if prompt_tokens:
            attrs["llm.tokens.prompt"] = prompt_tokens
            self.metrics.llm_tokens_prompt = prompt_tokens

        with self._track_phase("llm_inference", attrs) as span:
            start_time = time.perf_counter()
            first_token_time = None

            # Helper to track first token
            def mark_first_token():
                nonlocal first_token_time
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    self.metrics.llm_time_to_first_token = first_token_time - start_time
                    span.add_event(
                        "llm.first_token_received",
                        {"time_to_first_token_ms": self.metrics.llm_time_to_first_token * 1000},
                    )

            try:
                yield span, mark_first_token
            finally:
                self.metrics.llm_inference_duration = time.perf_counter() - start_time

                # Calculate tokens per second if we have completion tokens
                if self.metrics.llm_tokens_completion and self.metrics.llm_inference_duration:
                    self.metrics.llm_tokens_per_second = (
                        self.metrics.llm_tokens_completion / self.metrics.llm_inference_duration
                    )

                # Add final LLM metrics to span
                span.set_attribute(
                    "llm.inference.duration_ms", self.metrics.llm_inference_duration * 1000
                )
                if self.metrics.llm_tokens_completion:
                    span.set_attribute("llm.tokens.completion", self.metrics.llm_tokens_completion)
                if self.metrics.llm_tokens_per_second:
                    span.set_attribute("llm.tokens_per_second", self.metrics.llm_tokens_per_second)
                if self.metrics.llm_time_to_first_token:
                    span.set_attribute(
                        "llm.time_to_first_token_ms", self.metrics.llm_time_to_first_token * 1000
                    )

    def set_llm_completion_tokens(self, completion_tokens: int):
        """Set the number of completion tokens generated."""
        self.metrics.llm_tokens_completion = completion_tokens

    @contextmanager
    def track_tts_synthesis(
        self,
        text_length: int,
        voice_name: str | None = None,
    ):
        """
        Track TTS synthesis phase with audio metrics.

        Args:
            text_length: Length of text being synthesized
            voice_name: Name of the TTS voice being used
        """
        attrs = {
            "conversation.turn.phase": "tts_synthesis",
            "tts.text.length": text_length,
            "peer.service": "azure-speech-service",
        }

        if voice_name:
            attrs["tts.voice.name"] = voice_name

        self.metrics.tts_text_length = text_length

        with self._track_phase("tts_synthesis", attrs) as span:
            start_time = time.perf_counter()
            chunk_count = 0

            def mark_chunk_generated(audio_duration: float | None = None):
                nonlocal chunk_count
                chunk_count += 1
                span.add_event(
                    "tts.chunk_generated",
                    {
                        "chunk_number": chunk_count,
                        "audio_duration_ms": (audio_duration * 1000) if audio_duration else None,
                    },
                )

            try:
                yield span, mark_chunk_generated
            finally:
                self.metrics.tts_synthesis_duration = time.perf_counter() - start_time
                self.metrics.tts_chunk_count = chunk_count

                # Calculate synthesis speed
                if self.metrics.tts_text_length and self.metrics.tts_synthesis_duration:
                    self.metrics.tts_synthesis_speed = (
                        self.metrics.tts_text_length / self.metrics.tts_synthesis_duration
                    )

                # Add final TTS metrics to span
                span.set_attribute(
                    "tts.synthesis.duration_ms", self.metrics.tts_synthesis_duration * 1000
                )
                span.set_attribute("tts.chunk.count", chunk_count)
                if self.metrics.tts_synthesis_speed:
                    span.set_attribute(
                        "tts.synthesis.chars_per_second", self.metrics.tts_synthesis_speed
                    )
                if self.metrics.tts_audio_duration:
                    span.set_attribute(
                        "tts.audio.duration_ms", self.metrics.tts_audio_duration * 1000
                    )

    def set_tts_audio_duration(self, audio_duration: float):
        """Set the total duration of generated audio."""
        self.metrics.tts_audio_duration = audio_duration

    @contextmanager
    def track_network_delivery(self, transport_type: str = "websocket"):
        """
        Track network delivery phase.

        Args:
            transport_type: Type of transport (websocket, http, etc.)
        """
        attrs = {
            "conversation.turn.phase": "network_delivery",
            "network.transport.type": transport_type,
        }

        if transport_type == "websocket":
            attrs["network.protocol.name"] = "websocket"

        with self._track_phase("network_delivery", attrs) as span:
            start_time = time.perf_counter()
            try:
                yield span
            finally:
                self.metrics.network_latency = time.perf_counter() - start_time
                span.set_attribute("network.latency_ms", self.metrics.network_latency * 1000)

    @contextmanager
    def _track_phase(self, phase_name: str, extra_attrs: dict[str, Any] = None):
        """Internal helper to track a conversation phase."""
        if phase_name in self._active_spans:
            logger.warning(f"Phase '{phase_name}' already active, skipping duplicate")
            yield self._active_spans[phase_name]
            return

        attrs = self._get_base_attributes()
        if extra_attrs:
            attrs.update(extra_attrs)

        # Use descriptive span names: voice.turn.<id>.<phase>
        # Maps internal phase names to user-friendly span names:
        # - user_input -> stt (speech-to-text)
        # - llm_inference -> llm (language model)
        # - tts_synthesis -> tts (text-to-speech)
        # - network_delivery -> delivery
        phase_display_map = {
            "user_input": "stt",
            "llm_inference": "llm",
            "tts_synthesis": "tts",
            "network_delivery": "delivery",
        }
        display_name = phase_display_map.get(phase_name, phase_name)

        span = self.tracer.start_span(
            f"voice.turn.{self.metrics.turn_id}.{display_name}",
            kind=SpanKind.INTERNAL,
            attributes=attrs,
        )

        self._active_spans[phase_name] = span

        try:
            yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.add_event(
                f"conversation.{phase_name}.error",
                {"error.type": type(e).__name__, "error.message": str(e)},
            )
            raise
        finally:
            span.end()
            self._active_spans.pop(phase_name, None)

    def _add_turn_metrics_to_span(self):
        """Add final turn metrics to the root span."""
        if not self._turn_span:
            return

        metrics_attrs = {}

        # Timing metrics with descriptive attribute names (all in milliseconds)
        if self.metrics.total_turn_duration:
            metrics_attrs["turn.total_latency_ms"] = self.metrics.total_turn_duration * 1000
        if self.metrics.user_input_duration:
            metrics_attrs["turn.stt.latency_ms"] = self.metrics.user_input_duration * 1000
        if self.metrics.llm_inference_duration:
            metrics_attrs["turn.llm.total_ms"] = self.metrics.llm_inference_duration * 1000
        if self.metrics.tts_synthesis_duration:
            metrics_attrs["turn.tts.total_ms"] = self.metrics.tts_synthesis_duration * 1000
        if self.metrics.network_latency:
            metrics_attrs["turn.delivery.latency_ms"] = self.metrics.network_latency * 1000

        # LLM TTFB (time to first token)
        if self.metrics.llm_time_to_first_token:
            metrics_attrs["turn.llm.ttfb_ms"] = self.metrics.llm_time_to_first_token * 1000

        # Token metrics - critical for cost/performance analysis
        if self.metrics.llm_tokens_prompt:
            metrics_attrs["turn.llm.input_tokens"] = self.metrics.llm_tokens_prompt
            metrics_attrs["gen_ai.usage.input_tokens"] = self.metrics.llm_tokens_prompt
        if self.metrics.llm_tokens_completion:
            metrics_attrs["turn.llm.output_tokens"] = self.metrics.llm_tokens_completion
            metrics_attrs["gen_ai.usage.output_tokens"] = self.metrics.llm_tokens_completion

        # Tokens per second - throughput metric
        if self.metrics.llm_tokens_per_second:
            metrics_attrs["turn.llm.tokens_per_sec"] = self.metrics.llm_tokens_per_second

        # TTS metrics
        if self.metrics.tts_text_length:
            metrics_attrs["turn.tts.text_length"] = self.metrics.tts_text_length
        if self.metrics.tts_chunk_count:
            metrics_attrs["turn.tts.chunk_count"] = self.metrics.tts_chunk_count
        if self.metrics.tts_synthesis_speed:
            metrics_attrs["turn.tts.chars_per_sec"] = self.metrics.tts_synthesis_speed

        for key, value in metrics_attrs.items():
            self._turn_span.set_attribute(key, value)

    def add_metadata(self, key: str, value: Any):
        """Add custom metadata to the turn metrics."""
        self.metrics.metadata[key] = value
        if self._turn_span:
            self._turn_span.set_attribute(f"conversation.turn.metadata.{key}", value)

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get a summary of all collected metrics."""
        return {
            "turn_id": self.metrics.turn_id,
            "call_connection_id": self.metrics.call_connection_id,
            "session_id": self.metrics.session_id,
            "durations": {
                "total_turn_ms": (
                    (self.metrics.total_turn_duration * 1000)
                    if self.metrics.total_turn_duration
                    else None
                ),
                "user_input_ms": (
                    (self.metrics.user_input_duration * 1000)
                    if self.metrics.user_input_duration
                    else None
                ),
                "llm_inference_ms": (
                    (self.metrics.llm_inference_duration * 1000)
                    if self.metrics.llm_inference_duration
                    else None
                ),
                "tts_synthesis_ms": (
                    (self.metrics.tts_synthesis_duration * 1000)
                    if self.metrics.tts_synthesis_duration
                    else None
                ),
                "network_latency_ms": (
                    (self.metrics.network_latency * 1000) if self.metrics.network_latency else None
                ),
            },
            "llm_metrics": {
                "tokens_prompt": self.metrics.llm_tokens_prompt,
                "tokens_completion": self.metrics.llm_tokens_completion,
                "tokens_per_second": self.metrics.llm_tokens_per_second,
                "time_to_first_token_ms": (
                    (self.metrics.llm_time_to_first_token * 1000)
                    if self.metrics.llm_time_to_first_token
                    else None
                ),
            },
            "tts_metrics": {
                "text_length": self.metrics.tts_text_length,
                "audio_duration_ms": (
                    (self.metrics.tts_audio_duration * 1000)
                    if self.metrics.tts_audio_duration
                    else None
                ),
                "synthesis_chars_per_second": self.metrics.tts_synthesis_speed,
                "chunk_count": self.metrics.tts_chunk_count,
            },
            "metadata": self.metrics.metadata,
        }


class LatencyToolV2:
    """
    V2 Latency Tool with OpenTelemetry integration.

    Provides conversational turn tracking with detailed phase breakdown
    and rich telemetry data. Built on OpenTelemetry best practices.

    Maintains backwards compatibility with the original LatencyTool API
    while providing enhanced OpenTelemetry-based tracking.
    """

    def __init__(self, tracer: trace.Tracer, cm=None):
        self.tracer = tracer
        self.cm = cm  # Core memory for backwards compatibility

        # Backwards compatibility state
        self._current_tracker: ConversationTurnTracker | None = None
        self._active_timers: set[str] = set()
        self._current_run_id: str | None = None
        self._legacy_mode: bool = False

    def get_tracer(self) -> trace.Tracer:
        """Implementation of LatencyTrackerProtocol."""
        return self.tracer

    def create_turn_tracker(
        self,
        turn_id: str | None = None,
        call_connection_id: str | None = None,
        session_id: str | None = None,
    ) -> ConversationTurnTracker:
        """
        Create a new conversation turn tracker.

        Args:
            turn_id: Optional custom turn ID
            call_connection_id: ACS call connection ID for correlation
            session_id: Session ID for correlation

        Returns:
            ConversationTurnTracker instance
        """
        return ConversationTurnTracker(
            tracker=self,
            turn_id=turn_id,
            call_connection_id=call_connection_id,
            session_id=session_id,
        )

    @contextmanager
    def track_conversation_turn(
        self,
        turn_id: str | None = None,
        call_connection_id: str | None = None,
        session_id: str | None = None,
    ):
        """
        Convenience method to track a complete conversation turn.

        Usage:
            with latency_tool.track_conversation_turn(call_id, session_id) as tracker:
                with tracker.track_user_input():
                    # Process user input
                    pass

                with tracker.track_llm_inference("gpt-4", prompt_tokens=150) as (span, mark_first_token):
                    # Call LLM
                    mark_first_token()  # Call when first token received
                    tracker.set_llm_completion_tokens(75)

                with tracker.track_tts_synthesis(len(response_text)) as (span, mark_chunk):
                    # Generate TTS
                    mark_chunk(audio_duration=1.5)  # Call for each chunk

                with tracker.track_network_delivery():
                    # Send to client
                    pass
        """
        tracker = self.create_turn_tracker(turn_id, call_connection_id, session_id)
        with tracker.track_turn():
            yield tracker

    # ========================================================================
    # Backwards Compatibility API - Maintains original LatencyTool interface
    # ========================================================================

    def set_current_run(self, run_id: str) -> None:
        """Backwards compatibility: Set current run ID."""
        self._current_run_id = run_id
        if self._current_tracker:
            self._current_tracker.add_metadata("legacy_run_id", run_id)
        logger.debug(f"[COMPAT] Set current run: {run_id}")

    def get_current_run(self) -> str | None:
        """Backwards compatibility: Get current run ID."""
        return self._current_run_id or (
            self._current_tracker.metrics.turn_id if self._current_tracker else None
        )

    def begin_run(self, label: str = "turn") -> str:
        """Backwards compatibility: Begin a new run."""
        self._legacy_mode = True

        # Clean up any existing tracker
        if self._current_tracker:
            logger.warning("[COMPAT] Starting new run while previous run still active")
            self.cleanup_timers()

        # Create new turn tracker
        self._current_tracker = self.create_turn_tracker(turn_id=self._current_run_id)
        self._current_tracker.add_metadata("legacy_label", label)

        # Start the turn span manually (not using context manager for compatibility)
        attrs = self._current_tracker._get_base_attributes()
        attrs.update(
            {
                "conversation.turn.phase": "legacy_run",
                "legacy.label": label,
                "span.type": "legacy_conversation_turn",
            }
        )

        self._current_tracker._turn_span = self.tracer.start_span(
            f"conversation.turn.legacy.{self._current_tracker.metrics.turn_id}",
            kind=trace.SpanKind.INTERNAL,
            attributes=attrs,
        )

        run_id = self._current_tracker.metrics.turn_id
        self._current_run_id = run_id

        logger.info(
            f"[COMPAT] Legacy begin_run called - created turn {run_id}",
            extra={"label": label, "turn_id": run_id},
        )
        return run_id

    def start(self, stage: str) -> None:
        """Backwards compatibility: Start timing a stage."""
        if not self._current_tracker:
            logger.warning(f"[COMPAT] start({stage}) called without active run, creating one")
            self.begin_run()

        # Track timer state to prevent duplicate starts (like original)
        if stage in self._active_timers:
            logger.debug(f"[COMPAT] Timer '{stage}' already running, skipping duplicate start")
            return

        self._active_timers.add(stage)

        # Map legacy stages to V2 tracking with immediate span creation
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

        # Create span immediately for legacy compatibility
        attrs = self._current_tracker._get_base_attributes()
        attrs.update(
            {
                "conversation.turn.phase": f"legacy_{v2_phase}",
                "legacy.stage_name": stage,
                "legacy.v2_phase": v2_phase,
            }
        )

        span = self.tracer.start_span(
            f"conversation.turn.legacy.{stage}",
            kind=trace.SpanKind.INTERNAL,
            attributes=attrs,
        )

        # Store span in active spans for cleanup
        self._current_tracker._active_spans[f"legacy_{stage}"] = span

        logger.debug(f"[COMPAT] Legacy start({stage}) -> {v2_phase}")

    def stop(self, stage: str, redis_mgr, *, meta: dict[str, Any] | None = None) -> None:
        """Backwards compatibility: Stop timing a stage."""
        if not self._current_tracker:
            logger.warning(f"[COMPAT] stop({stage}) called without active run")
            return

        # Check timer state before stopping (like original)
        if stage not in self._active_timers:
            logger.debug(f"[COMPAT] Timer '{stage}' not running, skipping stop")
            return

        self._active_timers.discard(stage)

        # End the span if it exists
        span_key = f"legacy_{stage}"
        if span_key in self._current_tracker._active_spans:
            span = self._current_tracker._active_spans.pop(span_key)

            # Add metadata to span if provided
            if meta:
                for key, value in meta.items():
                    try:
                        span.set_attribute(f"legacy.meta.{key}", str(value))
                    except Exception as e:
                        logger.debug(f"Failed to set span attribute {key}: {e}")

            span.end()

        # Legacy persistence - persist to Redis if cm and redis_mgr provided
        if redis_mgr and self.cm:
            try:
                # Create a legacy-compatible metrics entry
                legacy_data = {
                    "stage": stage,
                    "turn_id": self._current_tracker.metrics.turn_id,
                    "metadata": meta or {},
                }

                # Store in core memory for compatibility
                existing = self.cm.get_context("legacy_latency", {})
                if "stages" not in existing:
                    existing["stages"] = []
                existing["stages"].append(legacy_data)
                self.cm.set_context("legacy_latency", existing)

                # Persist to Redis
                self.cm.persist_to_redis(redis_mgr)
            except Exception as e:
                logger.error(f"[COMPAT] Failed to persist legacy latency to Redis: {e}")

        logger.debug(f"[COMPAT] Legacy stop({stage}) completed")

    def session_summary(self) -> dict[str, dict[str, float]]:
        """Backwards compatibility: Get session summary."""
        logger.debug("[COMPAT] session_summary() called - returning legacy format")

        if not self.cm:
            logger.warning("[COMPAT] No core memory available for legacy session summary")
            return {}

        try:
            # Get legacy data from core memory
            legacy_data = self.cm.get_context("legacy_latency", {})
            stages_data = legacy_data.get("stages", [])

            # Aggregate by stage (mimicking original PersistentLatency behavior)
            summary = {}
            for stage_entry in stages_data:
                stage = stage_entry["stage"]
                if stage not in summary:
                    summary[stage] = {
                        "count": 0,
                        "total": 0.0,
                        "avg": 0.0,
                        "min": float("inf"),
                        "max": 0.0,
                    }

                # For backwards compatibility, we'll use a default duration
                # In a real implementation, you'd track actual durations
                duration = 0.1  # Default duration for compatibility

                summary[stage]["count"] += 1
                summary[stage]["total"] += duration
                summary[stage]["min"] = min(summary[stage]["min"], duration)
                summary[stage]["max"] = max(summary[stage]["max"], duration)

            # Calculate averages
            for stage_summary in summary.values():
                if stage_summary["count"] > 0:
                    stage_summary["avg"] = stage_summary["total"] / stage_summary["count"]
                if stage_summary["min"] == float("inf"):
                    stage_summary["min"] = 0.0

            return summary

        except Exception as e:
            logger.error(f"[COMPAT] Error generating session summary: {e}")
            return {}

    def run_summary(self, run_id: str) -> dict[str, dict[str, float]]:
        """Backwards compatibility: Get run summary for specific run."""
        logger.debug(f"[COMPAT] run_summary({run_id}) called - returning legacy format")

        if not self.cm:
            logger.warning("[COMPAT] No core memory available for legacy run summary")
            return {}

        try:
            # Get legacy data for specific run
            legacy_data = self.cm.get_context("legacy_latency", {})
            stages_data = legacy_data.get("stages", [])

            # Filter by run_id and aggregate
            summary = {}
            for stage_entry in stages_data:
                if stage_entry.get("turn_id") != run_id:
                    continue

                stage = stage_entry["stage"]
                if stage not in summary:
                    summary[stage] = {
                        "count": 0,
                        "total": 0.0,
                        "avg": 0.0,
                        "min": float("inf"),
                        "max": 0.0,
                    }

                # Default duration for compatibility
                duration = 0.1

                summary[stage]["count"] += 1
                summary[stage]["total"] += duration
                summary[stage]["min"] = min(summary[stage]["min"], duration)
                summary[stage]["max"] = max(summary[stage]["max"], duration)

            # Calculate averages
            for stage_summary in summary.values():
                if stage_summary["count"] > 0:
                    stage_summary["avg"] = stage_summary["total"] / stage_summary["count"]
                if stage_summary["min"] == float("inf"):
                    stage_summary["min"] = 0.0

            return summary

        except Exception as e:
            logger.error(f"[COMPAT] Error generating run summary for {run_id}: {e}")
            return {}

    def cleanup_timers(self) -> None:
        """Backwards compatibility: Clean up active timers on session disconnect."""
        if self._active_timers:
            logger.debug(
                f"[COMPAT] Cleaning up {len(self._active_timers)} active timers: {self._active_timers}"
            )
            self._active_timers.clear()

        # Clean up any active spans in the current tracker
        if self._current_tracker:
            for span_name, span in self._current_tracker._active_spans.items():
                logger.warning(f"[COMPAT] Force-closing unclosed span: {span_name}")
                try:
                    span.end()
                except Exception as e:
                    logger.debug(f"Error ending span {span_name}: {e}")

            self._current_tracker._active_spans.clear()

            # End turn span if active
            if self._current_tracker._turn_span:
                try:
                    self._current_tracker._turn_span.end()
                except Exception as e:
                    logger.debug(f"Error ending turn span: {e}")
                self._current_tracker._turn_span = None

            self._current_tracker = None

        self._current_run_id = None
        logger.debug("[COMPAT] Cleanup completed")
