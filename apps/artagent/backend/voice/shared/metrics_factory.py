"""
Metrics Factory
===============

Shared metrics infrastructure for voice orchestrators.

Provides lazy-initialization patterns for OpenTelemetry metrics that
ensure proper MeterProvider configuration before instrument creation.

This module eliminates duplication between voicelive/metrics.py and
speech_cascade/metrics.py by providing common patterns.

Usage:
    from apps.artagent.backend.voice.shared.metrics_factory import (
        LazyMeter,
        create_latency_histogram,
        create_count_counter,
    )

    # Create a lazy meter for your module
    meter = LazyMeter("voicelive.turn.latency", version="1.0.0")

    # Create histograms and counters (lazy initialization)
    llm_ttft = meter.histogram(
        name="voicelive.llm.ttft",
        description="LLM Time-To-First-Token in milliseconds",
        unit="ms",
    )

    turn_count = meter.counter(
        name="voicelive.turn.count",
        description="Number of conversation turns processed",
        unit="1",
    )

    # Record metrics (instruments are created lazily on first use)
    llm_ttft.record(150.5, attributes={"session.id": "abc123"})
    turn_count.add(1, attributes={"session.id": "abc123"})
"""

from __future__ import annotations

from typing import Any

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, Meter

try:
    from utils.ml_logging import get_logger

    logger = get_logger("voice.shared.metrics_factory")
except ImportError:
    import logging

    logger = logging.getLogger("voice.shared.metrics_factory")


class LazyHistogram:
    """
    Lazy-initialized histogram that creates the instrument on first use.

    This ensures the MeterProvider is configured before instrument creation,
    avoiding no-op meters when Azure Monitor hasn't been initialized yet.
    """

    def __init__(
        self,
        meter_getter: callable,
        name: str,
        description: str,
        unit: str,
    ) -> None:
        self._meter_getter = meter_getter
        self._name = name
        self._description = description
        self._unit = unit
        self._histogram: Histogram | None = None

    def _ensure_initialized(self) -> Histogram:
        if self._histogram is None:
            meter = self._meter_getter()
            self._histogram = meter.create_histogram(
                name=self._name,
                description=self._description,
                unit=self._unit,
            )
        return self._histogram

    def record(self, value: float, attributes: dict[str, Any] | None = None) -> None:
        """Record a value to the histogram."""
        histogram = self._ensure_initialized()
        histogram.record(value, attributes=attributes)


class LazyCounter:
    """
    Lazy-initialized counter that creates the instrument on first use.

    This ensures the MeterProvider is configured before instrument creation.
    """

    def __init__(
        self,
        meter_getter: callable,
        name: str,
        description: str,
        unit: str,
    ) -> None:
        self._meter_getter = meter_getter
        self._name = name
        self._description = description
        self._unit = unit
        self._counter: Counter | None = None

    def _ensure_initialized(self) -> Counter:
        if self._counter is None:
            meter = self._meter_getter()
            self._counter = meter.create_counter(
                name=self._name,
                description=self._description,
                unit=self._unit,
            )
        return self._counter

    def add(self, amount: int, attributes: dict[str, Any] | None = None) -> None:
        """Add to the counter."""
        counter = self._ensure_initialized()
        counter.add(amount, attributes=attributes)


class LazyMeter:
    """
    Lazy-initialized meter that defers OpenTelemetry meter creation.

    Provides factory methods for creating lazy histograms and counters
    that are thread-safe and ensure proper initialization order.

    Example:
        meter = LazyMeter("voicelive.turn.latency", version="1.0.0")

        # These don't create instruments until first use
        ttft_histogram = meter.histogram("llm.ttft", "LLM TTFT in ms", "ms")
        turn_counter = meter.counter("turn.count", "Turn count", "1")

        # First record/add creates the underlying instrument
        ttft_histogram.record(150.5, {"session.id": "abc"})
    """

    def __init__(self, name: str, version: str = "1.0.0") -> None:
        self._name = name
        self._version = version
        self._meter: Meter | None = None
        self._initialized = False

    def _get_meter(self) -> Meter:
        """Get or create the underlying OpenTelemetry meter."""
        if self._meter is None:
            self._meter = metrics.get_meter(self._name, version=self._version)
            if not self._initialized:
                logger.info("Initialized meter: %s (v%s)", self._name, self._version)
                self._initialized = True
        return self._meter

    def histogram(
        self,
        name: str,
        description: str,
        unit: str = "ms",
    ) -> LazyHistogram:
        """
        Create a lazy histogram.

        Args:
            name: Metric name (e.g., "voicelive.llm.ttft")
            description: Human-readable description
            unit: Unit of measurement (default: "ms")

        Returns:
            LazyHistogram that initializes on first record()
        """
        return LazyHistogram(
            meter_getter=self._get_meter,
            name=name,
            description=description,
            unit=unit,
        )

    def counter(
        self,
        name: str,
        description: str,
        unit: str = "1",
    ) -> LazyCounter:
        """
        Create a lazy counter.

        Args:
            name: Metric name (e.g., "voicelive.turn.count")
            description: Human-readable description
            unit: Unit of measurement (default: "1")

        Returns:
            LazyCounter that initializes on first add()
        """
        return LazyCounter(
            meter_getter=self._get_meter,
            name=name,
            description=description,
            unit=unit,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# COMMON ATTRIBUTE BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════


def build_session_attributes(
    session_id: str,
    *,
    turn_number: int | None = None,
    call_connection_id: str | None = None,
    agent_name: str | None = None,
    metric_type: str | None = None,
) -> dict[str, Any]:
    """
    Build common session attributes for metrics.

    Provides consistent attribute naming across all voice metrics.

    Args:
        session_id: Session identifier for correlation
        turn_number: Optional turn number within conversation
        call_connection_id: Optional ACS call connection ID
        agent_name: Optional agent name handling the turn
        metric_type: Optional metric type label

    Returns:
        Dict of attributes suitable for OpenTelemetry metrics
    """
    attributes: dict[str, Any] = {
        "session.id": session_id,
    }

    if turn_number is not None:
        attributes["turn.number"] = turn_number
    if call_connection_id:
        attributes["call.connection.id"] = call_connection_id
    if agent_name:
        attributes["agent.name"] = agent_name
    if metric_type:
        attributes["metric.type"] = metric_type

    return attributes


def build_tts_attributes(
    session_id: str,
    *,
    transport: str = "browser",
    voice_name: str | None = None,
    text_length: int | None = None,
    audio_bytes: int | None = None,
    cancelled: bool = False,
) -> dict[str, Any]:
    """
    Build TTS-specific attributes for metrics.

    Args:
        session_id: Session identifier
        transport: Transport type (browser/acs)
        voice_name: Azure TTS voice used
        text_length: Length of text synthesized
        audio_bytes: Size of audio output in bytes
        cancelled: Whether playback was cancelled

    Returns:
        Dict of attributes for TTS metrics
    """
    attributes: dict[str, Any] = {
        "session.id": session_id,
        "tts.transport": transport,
    }

    if voice_name:
        attributes["tts.voice"] = voice_name
    if text_length is not None:
        attributes["tts.text_length"] = text_length
    if audio_bytes is not None:
        attributes["tts.audio_bytes"] = audio_bytes
    if cancelled:
        attributes["tts.cancelled"] = cancelled

    return attributes


__all__ = [
    "LazyMeter",
    "LazyHistogram",
    "LazyCounter",
    "build_session_attributes",
    "build_tts_attributes",
]
