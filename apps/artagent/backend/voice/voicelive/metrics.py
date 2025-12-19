"""
VoiceLive Latency Metrics
=========================

OpenTelemetry metrics for tracking VoiceLive turn latencies.
These metrics show up in Application Insights Performance view for analysis.

Uses the shared metrics factory for lazy initialization, ensuring proper
MeterProvider configuration before instrument creation.
"""

from __future__ import annotations

from apps.artagent.backend.voice.shared.metrics_factory import (
    LazyCounter,
    LazyHistogram,
    LazyMeter,
    build_session_attributes,
)
from utils.ml_logging import get_logger

logger = get_logger("voicelive.metrics")

# ═══════════════════════════════════════════════════════════════════════════════
# LAZY METER INITIALIZATION (via shared factory)
# ═══════════════════════════════════════════════════════════════════════════════

_meter = LazyMeter("voicelive.turn.latency", version="1.0.0")

# LLM Time-To-First-Token (from turn start to first LLM token)
_llm_ttft_histogram: LazyHistogram = _meter.histogram(
    name="voicelive.llm.ttft",
    description="LLM Time-To-First-Token in milliseconds",
    unit="ms",
)

# TTS Time-To-First-Byte (from VAD end to first audio byte - end-to-end latency)
_tts_ttfb_histogram: LazyHistogram = _meter.histogram(
    name="voicelive.tts.ttfb",
    description="TTS Time-To-First-Byte (E2E latency from VAD end to first audio) in milliseconds",
    unit="ms",
)

# STT latency (from VAD end to transcript completion)
_stt_latency_histogram: LazyHistogram = _meter.histogram(
    name="voicelive.stt.latency",
    description="STT latency from VAD end to transcript completion in milliseconds",
    unit="ms",
)

# Total turn duration
_turn_duration_histogram: LazyHistogram = _meter.histogram(
    name="voicelive.turn.duration",
    description="Total turn duration in milliseconds",
    unit="ms",
)

# Turn counter
_turn_counter: LazyCounter = _meter.counter(
    name="voicelive.turn.count",
    description="Number of conversation turns processed",
    unit="1",
)


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC RECORDING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def record_llm_ttft(
    ttft_ms: float,
    *,
    session_id: str,
    turn_number: int,
    agent_name: str | None = None,
) -> None:
    """
    Record LLM Time-To-First-Token metric.

    :param ttft_ms: Time to first token in milliseconds
    :param session_id: Session identifier for correlation
    :param turn_number: Turn number within the conversation
    :param agent_name: Optional agent name handling the turn
    """
    attributes = build_session_attributes(
        session_id,
        turn_number=turn_number,
        agent_name=agent_name,
        metric_type="llm_ttft",
    )

    _llm_ttft_histogram.record(ttft_ms, attributes=attributes)
    logger.info(
        "📊 LLM TTFT metric recorded: %.2fms | session=%s turn=%d agent=%s",
        ttft_ms,
        session_id,
        turn_number,
        agent_name or "unknown",
    )


def record_tts_ttfb(
    ttfb_ms: float,
    *,
    session_id: str,
    turn_number: int,
    reference: str = "vad_end",
    agent_name: str | None = None,
) -> None:
    """
    Record TTS Time-To-First-Byte metric (E2E latency).

    :param ttfb_ms: Time to first audio byte in milliseconds
    :param session_id: Session identifier for correlation
    :param turn_number: Turn number within the conversation
    :param reference: Timing reference point (vad_end or turn_start)
    :param agent_name: Optional agent name handling the turn
    """
    attributes = build_session_attributes(
        session_id,
        turn_number=turn_number,
        agent_name=agent_name,
        metric_type="tts_ttfb",
    )
    attributes["latency.reference"] = reference

    _tts_ttfb_histogram.record(ttfb_ms, attributes=attributes)
    logger.info(
        "📊 TTS TTFB metric recorded: %.2fms | session=%s turn=%d ref=%s agent=%s",
        ttfb_ms,
        session_id,
        turn_number,
        reference,
        agent_name or "unknown",
    )


def record_stt_latency(
    latency_ms: float,
    *,
    session_id: str,
    turn_number: int,
) -> None:
    """
    Record STT latency metric.

    :param latency_ms: STT latency in milliseconds
    :param session_id: Session identifier for correlation
    :param turn_number: Turn number within the conversation
    """
    attributes = build_session_attributes(
        session_id,
        turn_number=turn_number,
        metric_type="stt_latency",
    )

    _stt_latency_histogram.record(latency_ms, attributes=attributes)
    logger.info(
        "📊 STT latency metric recorded: %.2fms | session=%s turn=%d",
        latency_ms,
        session_id,
        turn_number,
    )


def record_turn_complete(
    duration_ms: float,
    *,
    session_id: str,
    turn_number: int,
    stt_latency_ms: float | None = None,
    llm_ttft_ms: float | None = None,
    tts_ttfb_ms: float | None = None,
    agent_name: str | None = None,
) -> None:
    """
    Record turn completion with all latency metrics.

    This records the turn duration histogram and increments the turn counter.
    Individual component metrics (STT, LLM, TTS) should be recorded separately
    when they occur for more accurate timing.

    :param duration_ms: Total turn duration in milliseconds
    :param session_id: Session identifier for correlation
    :param turn_number: Turn number within the conversation
    :param stt_latency_ms: Optional STT latency for the turn
    :param llm_ttft_ms: Optional LLM TTFT for the turn
    :param tts_ttfb_ms: Optional TTS TTFB for the turn
    :param agent_name: Optional agent name handling the turn
    """
    base_attributes = build_session_attributes(
        session_id,
        turn_number=turn_number,
        agent_name=agent_name,
    )

    # Record turn duration
    _turn_duration_histogram.record(
        duration_ms,
        attributes={
            **base_attributes,
            "metric.type": "turn_duration",
        },
    )

    # Increment turn counter
    _turn_counter.add(1, attributes=base_attributes)

    # Log summary
    logger.info(
        "📊 Turn complete metric: duration=%.2fms stt=%s llm=%s tts=%s | session=%s turn=%d",
        duration_ms,
        f"{stt_latency_ms:.2f}ms" if stt_latency_ms else "N/A",
        f"{llm_ttft_ms:.2f}ms" if llm_ttft_ms else "N/A",
        f"{tts_ttfb_ms:.2f}ms" if tts_ttfb_ms else "N/A",
        session_id,
        turn_number,
    )


__all__ = [
    "record_llm_ttft",
    "record_tts_ttfb",
    "record_stt_latency",
    "record_turn_complete",
]
