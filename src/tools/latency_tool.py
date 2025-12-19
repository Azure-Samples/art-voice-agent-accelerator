from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from utils.ml_logging import get_logger

from src.tools.latency_helpers import PersistentLatency

logger = get_logger("tools.latency")
tracer = trace.get_tracer(__name__)


class LatencyTool:
    """
    Backwards-compatible wrapper used at WS layer.

    start(stage) / stop(stage, redis_mgr) keep working,
    but data is written into CoreMemory["latency"] with a per-run grouping.

    Also emits OpenTelemetry spans for each stage to ensure visibility in Application Insights.
    """

    def __init__(self, cm):
        self.cm = cm
        self._store = PersistentLatency(cm)
        # Track active timers to prevent start/stop mismatches
        self._active_timers = set()
        # Track active spans for OTel
        self._active_spans: dict[str, trace.Span] = {}

    # Optional: set current run for this connection
    def set_current_run(self, run_id: str) -> None:
        self._store.set_current_run(run_id)

    def get_current_run(self) -> str | None:
        return self._store.current_run_id()

    def begin_run(self, label: str = "turn") -> str:
        rid = self._store.begin_run(label=label)
        return rid

    def start(self, stage: str) -> None:
        # Track timer state to prevent duplicate starts
        if stage in self._active_timers:
            logger.debug(f"[PERF] Timer '{stage}' already running, skipping duplicate start")
            return

        self._active_timers.add(stage)
        self._store.start(stage)

        # Start OTel span
        try:
            span = tracer.start_span(f"latency.{stage}", kind=SpanKind.INTERNAL)
            self._active_spans[stage] = span
        except Exception as e:
            logger.debug(f"Failed to start span for {stage}: {e}")

    def stop(self, stage: str, redis_mgr, *, meta: dict[str, Any] | None = None) -> None:
        # Check timer state before stopping
        if stage not in self._active_timers:
            logger.debug(f"[PERF] Timer '{stage}' not running, skipping stop")
            return

        self._active_timers.discard(stage)  # Remove from active set
        sample = self._store.stop(stage, redis_mgr=redis_mgr, meta=meta)

        # Stop OTel span
        span = self._active_spans.pop(stage, None)
        if span:
            try:
                if meta:
                    for k, v in meta.items():
                        span.set_attribute(str(k), str(v))

                if sample:
                    # Add duration as standard attribute
                    duration_ms = sample.dur * 1000
                    span.set_attribute("duration_ms", duration_ms)

                    # Auto-calculate TTFB for TTS if not provided (assuming blocking synthesis)
                    if stage == "tts:synthesis" and "ttfb" not in (meta or {}):
                        span.set_attribute("ttfb_ms", duration_ms)
                        span.set_attribute("ttfb", duration_ms)  # Alias

                    # LLM-related stages with GenAI semantic conventions
                    if stage == "llm":
                        # Total LLM round-trip time
                        span.set_attribute("gen_ai.operation.name", "chat")
                        span.set_attribute("gen_ai.system", "azure_openai")
                        span.set_attribute("latency.llm_ms", duration_ms)
                    elif stage == "llm:ttfb":
                        # Time to first byte from Azure OpenAI
                        span.set_attribute("gen_ai.operation.name", "chat")
                        span.set_attribute("gen_ai.system", "azure_openai")
                        span.set_attribute("latency.llm_ttfb_ms", duration_ms)
                        span.set_attribute("ttfb_ms", duration_ms)
                    elif stage == "llm:consume":
                        # Time to consume the full streaming response
                        span.set_attribute("gen_ai.operation.name", "chat")
                        span.set_attribute("gen_ai.system", "azure_openai")
                        span.set_attribute("latency.llm_consume_ms", duration_ms)

                    # STT-related stages
                    elif stage == "stt:recognition":
                        # Speech-to-text recognition time (first partial to final/barge-in)
                        span.set_attribute("speech.operation.name", "recognition")
                        span.set_attribute("speech.system", "azure_speech")
                        span.set_attribute("latency.stt_recognition_ms", duration_ms)

                span.end()
            except Exception as e:
                logger.debug(f"Failed to end span for {stage}: {e}")

    # convenient summaries for dashboards
    def session_summary(self):
        return self._store.session_summary()

    def run_summary(self, run_id: str):
        return self._store.run_summary(run_id)

    def cleanup_timers(self) -> None:
        """Clean up active timers on session disconnect."""
        if self._active_timers:
            logger.debug(
                f"[PERF] Cleaning up {len(self._active_timers)} active timers: {self._active_timers}"
            )
            self._active_timers.clear()

        # End any active spans
        if self._active_spans:
            for stage, span in self._active_spans.items():
                try:
                    span.end()
                except Exception as e:
                    logger.debug(f"Failed to end span for {stage} during cleanup: {e}")
            self._active_spans.clear()
