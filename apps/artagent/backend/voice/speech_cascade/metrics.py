"""
Speech Cascade Metrics
======================

OpenTelemetry metrics for tracking Speech Cascade latencies.
These metrics show up in Application Insights Performance view for analysis.

Metrics tracked:
- STT recognition latency (first partial to final)
- Turn processing latency
- Barge-in detection latency
- TTS synthesis and streaming latencies

Uses the shared metrics factory for lazy initialization, ensuring proper
MeterProvider configuration before instrument creation.
"""

from __future__ import annotations

from apps.artagent.backend.voice.shared.metrics_factory import (
    LazyCounter,
    LazyHistogram,
    LazyMeter,
    build_session_attributes,
    build_tts_attributes,
)
from apps.artagent.backend.voice.shared.core_memory_metrics import (
    schedule_core_memory_update,
)
from utils.ml_logging import get_logger

logger = get_logger("speech_cascade.metrics")

# ═══════════════════════════════════════════════════════════════════════════════
# LAZY METER INITIALIZATION (via shared factory)
# ═══════════════════════════════════════════════════════════════════════════════

_meter = LazyMeter("speech_cascade.latency", version="1.0.0")

# STT Recognition latency (first partial to final)
_stt_recognition_histogram: LazyHistogram = _meter.histogram(
    name="speech_cascade.stt.recognition",
    description="STT recognition latency from first partial to final in milliseconds",
    unit="ms",
)

# Turn processing latency (user speech end to response start)
_turn_processing_histogram: LazyHistogram = _meter.histogram(
    name="speech_cascade.turn.processing",
    description="Turn processing latency in milliseconds",
    unit="ms",
)

# LLM time-to-first-token (LLM request -> first streamed token)
_llm_ttft_histogram: LazyHistogram = _meter.histogram(
    name="speech_cascade.llm.ttft",
    description="LLM time-to-first-token latency in milliseconds",
    unit="ms",
)

# TTS time-to-first-byte (STT final -> first audio chunk dispatched)
_tts_ttfb_histogram: LazyHistogram = _meter.histogram(
    name="speech_cascade.tts.ttfb",
    description="TTS time-to-first-byte latency (turn start -> first audio out) in milliseconds",
    unit="ms",
)

# Barge-in detection latency
_barge_in_histogram: LazyHistogram = _meter.histogram(
    name="speech_cascade.barge_in.latency",
    description="Barge-in detection latency in milliseconds",
    unit="ms",
)

# TTS synthesis latency (text to audio bytes)
_tts_synthesis_histogram: LazyHistogram = _meter.histogram(
    name="speech_cascade.tts.synthesis",
    description="TTS synthesis latency in milliseconds",
    unit="ms",
)

# TTS streaming latency (audio bytes to playback complete)
_tts_streaming_histogram: LazyHistogram = _meter.histogram(
    name="speech_cascade.tts.streaming",
    description="TTS streaming/playback latency in milliseconds",
    unit="ms",
)

# Turn counter
_turn_counter: LazyCounter = _meter.counter(
    name="speech_cascade.turn.count",
    description="Number of conversation turns processed",
    unit="1",
)

# Barge-in counter
_barge_in_counter: LazyCounter = _meter.counter(
    name="speech_cascade.barge_in.count",
    description="Number of barge-in events detected",
    unit="1",
)

# TTS counter
_tts_counter: LazyCounter = _meter.counter(
    name="speech_cascade.tts.count",
    description="Number of TTS synthesis operations",
    unit="1",
)


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC RECORDING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def record_stt_recognition(
    latency_ms: float,
    *,
    session_id: str,
    call_connection_id: str | None = None,
    turn_number: int | None = None,
    transcript_length: int | None = None,
    memo_manager = None,
) -> None:
    """
    Record STT recognition latency metric.

    This measures the time from first meaningful partial to final recognition.

    :param latency_ms: Recognition latency in milliseconds
    :param session_id: Session identifier for correlation
    :param call_connection_id: Call connection ID
    :param turn_number: Turn number within the conversation
    :param transcript_length: Length of final transcript in characters
    :param memo_manager: Optional memo manager for core memory updates
    """
    attributes = build_session_attributes(
        session_id,
        call_connection_id=call_connection_id,
        turn_number=turn_number,
        metric_type="stt_recognition",
    )
    if transcript_length is not None:
        attributes["transcript.length"] = transcript_length

    _stt_recognition_histogram.record(latency_ms, attributes=attributes)
    logger.debug("📊 STT recognition metric: %.2fms | session=%s", latency_ms, session_id)

    # Also update core memory for frontend (async, off hot path)
    schedule_core_memory_update(
        memo_manager=memo_manager,
        session_id=session_id,
        metric_type="stt_latency",  # Use consistent naming with VoiceLive
        value_ms=latency_ms,
        metadata={"transcript_length": transcript_length},
        turn_number=turn_number,
    )


def record_turn_processing(
    latency_ms: float,
    *,
    session_id: str,
    call_connection_id: str | None = None,
    turn_number: int | None = None,
    has_tool_calls: bool = False,
    memo_manager = None,
) -> None:
    """
    Record turn processing latency metric.

    :param latency_ms: Processing latency in milliseconds
    :param session_id: Session identifier for correlation
    :param call_connection_id: Call connection ID
    :param turn_number: Turn number within the conversation
    :param has_tool_calls: Whether the turn included tool calls
    :param memo_manager: Optional memo manager for core memory updates
    """
    attributes = build_session_attributes(
        session_id,
        call_connection_id=call_connection_id,
        turn_number=turn_number,
        metric_type="turn_processing",
    )
    attributes["has_tool_calls"] = has_tool_calls

    _turn_processing_histogram.record(latency_ms, attributes=attributes)
    _turn_counter.add(1, attributes={"session.id": session_id})

    logger.debug(
        "📊 Turn processing metric: %.2fms | session=%s tools=%s",
        latency_ms,
        session_id,
        has_tool_calls,
    )

    # Also update core memory for frontend (async, off hot path)
    schedule_core_memory_update(
        memo_manager=memo_manager,
        session_id=session_id,
        metric_type="turn_duration",  # Map to consistent naming
        value_ms=latency_ms,
        metadata={"has_tool_calls": has_tool_calls},
        turn_number=turn_number,
    )


def record_llm_ttft(
    latency_ms: float,
    *,
    session_id: str,
    call_connection_id: str | None = None,
    turn_number: int | None = None,
    agent_name: str | None = None,
    memo_manager=None,
) -> None:
    """
    Record LLM time-to-first-token (TTFT) latency metric.

    Measures the time from the LLM request being issued to the first streamed
    token arriving. This is the primary "is the model responsive?" KPI and the
    cascade equivalent of the VoiceLive ``record_llm_ttft`` metric.

    :param latency_ms: TTFT latency in milliseconds
    :param session_id: Session identifier for correlation
    :param call_connection_id: Call connection ID
    :param turn_number: Turn number within the conversation
    :param agent_name: Active agent that produced the response
    :param memo_manager: Optional memo manager for core memory updates
    """
    attributes = build_session_attributes(
        session_id,
        call_connection_id=call_connection_id,
        turn_number=turn_number,
        metric_type="llm_ttft",
    )
    if agent_name:
        attributes["agent.name"] = agent_name

    _llm_ttft_histogram.record(latency_ms, attributes=attributes)
    logger.debug("📊 LLM TTFT metric: %.2fms | session=%s agent=%s", latency_ms, session_id, agent_name)

    schedule_core_memory_update(
        memo_manager=memo_manager,
        session_id=session_id,
        metric_type="llm_ttft",  # Consistent naming with VoiceLive
        value_ms=latency_ms,
        metadata={"agent_name": agent_name},
        turn_number=turn_number,
    )


def record_tts_ttfb(
    latency_ms: float,
    *,
    session_id: str,
    call_connection_id: str | None = None,
    turn_number: int | None = None,
    agent_name: str | None = None,
    memo_manager=None,
) -> None:
    """
    Record TTS time-to-first-byte (TTFB) latency metric.

    Measures the time from turn start (final transcript ready) to the first
    audio chunk being dispatched to TTS. This is the cascade equivalent of the
    VoiceLive ``record_tts_ttfb`` metric and represents the user-perceived
    "how long until I hear a response" latency.

    :param latency_ms: TTFB latency in milliseconds
    :param session_id: Session identifier for correlation
    :param call_connection_id: Call connection ID
    :param turn_number: Turn number within the conversation
    :param agent_name: Active agent that produced the response
    :param memo_manager: Optional memo manager for core memory updates
    """
    attributes = build_session_attributes(
        session_id,
        call_connection_id=call_connection_id,
        turn_number=turn_number,
        metric_type="tts_ttfb",
    )
    if agent_name:
        attributes["agent.name"] = agent_name

    _tts_ttfb_histogram.record(latency_ms, attributes=attributes)
    logger.debug("📊 TTS TTFB metric: %.2fms | session=%s agent=%s", latency_ms, session_id, agent_name)

    schedule_core_memory_update(
        memo_manager=memo_manager,
        session_id=session_id,
        metric_type="tts_ttfb",  # Consistent naming with VoiceLive
        value_ms=latency_ms,
        metadata={"agent_name": agent_name},
        turn_number=turn_number,
    )


def record_barge_in(
    latency_ms: float,
    *,
    session_id: str,
    call_connection_id: str | None = None,
    trigger: str = "partial",
    tts_was_playing: bool = True,
) -> None:
    """
    Record barge-in detection latency metric.

    :param latency_ms: Detection latency in milliseconds
    :param session_id: Session identifier for correlation
    :param call_connection_id: Call connection ID
    :param trigger: What triggered the barge-in (partial, energy, etc.)
    :param tts_was_playing: Whether TTS was actively playing
    """
    attributes = build_session_attributes(
        session_id,
        call_connection_id=call_connection_id,
        metric_type="barge_in",
    )
    attributes["barge_in.trigger"] = trigger
    attributes["tts_was_playing"] = tts_was_playing

    _barge_in_histogram.record(latency_ms, attributes=attributes)
    _barge_in_counter.add(
        1,
        attributes={
            "session.id": session_id,
            "barge_in.trigger": trigger,
        },
    )

    logger.debug(
        "📊 Barge-in metric: %.2fms | session=%s trigger=%s", latency_ms, session_id, trigger
    )


def record_tts_synthesis(
    latency_ms: float,
    *,
    session_id: str,
    call_connection_id: str | None = None,
    voice_name: str | None = None,
    text_length: int | None = None,
    audio_bytes: int | None = None,
    transport: str = "browser",
    memo_manager = None,
) -> None:
    """
    Record TTS synthesis latency metric.

    :param latency_ms: Synthesis latency in milliseconds
    :param session_id: Session identifier for correlation
    :param call_connection_id: Call connection ID
    :param voice_name: Azure TTS voice used
    :param text_length: Length of text synthesized
    :param audio_bytes: Size of audio output in bytes
    :param transport: Transport type (browser/acs)
    :param memo_manager: Optional memo manager for core memory updates
    """
    attributes = build_tts_attributes(
        session_id,
        transport=transport,
        voice_name=voice_name,
        text_length=text_length,
        audio_bytes=audio_bytes,
    )
    attributes["metric.type"] = "tts_synthesis"
    if call_connection_id:
        attributes["call.connection.id"] = call_connection_id

    _tts_synthesis_histogram.record(latency_ms, attributes=attributes)
    _tts_counter.add(1, attributes={"session.id": session_id, "tts.transport": transport})

    logger.debug(
        "📊 TTS synthesis metric: %.2fms | session=%s voice=%s text_len=%s",
        latency_ms,
        session_id,
        voice_name,
        text_length,
    )

    # Also update core memory for frontend (async, off hot path)
    schedule_core_memory_update(
        memo_manager=memo_manager,
        session_id=session_id,
        metric_type="tts_ttfb",  # Use consistent naming with VoiceLive
        value_ms=latency_ms,
        metadata={
            "voice_name": voice_name,
            "text_length": text_length,
            "audio_bytes": audio_bytes,
            "transport": transport,
        },
        turn_number=None,  # TTS events may not have turn numbers in speech cascade
    )


def record_tts_streaming(
    latency_ms: float,
    *,
    session_id: str,
    call_connection_id: str | None = None,
    chunks_sent: int | None = None,
    audio_bytes: int | None = None,
    transport: str = "browser",
    cancelled: bool = False,
) -> None:
    """
    Record TTS streaming/playback latency metric.

    :param latency_ms: Streaming latency in milliseconds
    :param session_id: Session identifier for correlation
    :param call_connection_id: Call connection ID
    :param chunks_sent: Number of audio chunks sent
    :param audio_bytes: Total audio bytes streamed
    :param transport: Transport type (browser/acs)
    :param cancelled: Whether playback was cancelled (barge-in)
    """
    attributes = build_tts_attributes(
        session_id,
        transport=transport,
        audio_bytes=audio_bytes,
        cancelled=cancelled,
    )
    attributes["metric.type"] = "tts_streaming"
    if call_connection_id:
        attributes["call.connection.id"] = call_connection_id
    if chunks_sent is not None:
        attributes["tts.chunks_sent"] = chunks_sent

    _tts_streaming_histogram.record(latency_ms, attributes=attributes)

    logger.debug(
        "📊 TTS streaming metric: %.2fms | session=%s chunks=%s cancelled=%s",
        latency_ms,
        session_id,
        chunks_sent,
        cancelled,
    )


__all__ = [
    "record_stt_recognition",
    "record_turn_processing",
    "record_llm_ttft",
    "record_tts_ttfb",
    "record_barge_in",
    "record_tts_synthesis",
    "record_tts_streaming",
]
