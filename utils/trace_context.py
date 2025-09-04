import os
import time
from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind
from opentelemetry.trace.status import Status, StatusCode

from src.enums.monitoring import SpanAttr

# Performance optimization: Cache tracing configuration
_TRACING_ENABLED = os.getenv("ENABLE_TRACING", "false").lower() == "true"
_ORCHESTRATOR_TRACING = os.getenv("ORCHESTRATOR_TRACING", "true").lower() == "true"
_GPT_FLOW_TRACING = os.getenv("GPT_FLOW_TRACING", "true").lower() == "true"
_HIGH_FREQ_SAMPLING = float(
    os.getenv("HIGH_FREQ_SAMPLING", "0.1")
)  # 10% sampling for high-frequency ops


class TraceContext:
    """
    High-performance context manager for tracing spans with configurable overhead.
    Optimized for real-time voice agent scenarios with minimal latency impact.
    Compatible with Azure Application Insights application map visualization.
    Uses component-specific tracer names for proper Application Insights correlation.
    """

    def __init__(
        self,
        name: str,
        component: Optional[str] = None,
        call_connection_id: Optional[str] = None,
        session_id: Optional[str] = None,
        test_case: Optional[str] = None,
        metadata: Optional[dict] = None,
        high_frequency: bool = False,
        sampling_rate: Optional[float] = None,
        span_kind: SpanKind = SpanKind.INTERNAL,
    ):
        self.name = name
        self.component = component
        self.call_connection_id = call_connection_id
        self.session_id = session_id
        self.test_case = test_case
        self.metadata = metadata or {}
        self.high_frequency = high_frequency
        self.span_kind = span_kind
        self.sampling_rate = sampling_rate or (
            _HIGH_FREQ_SAMPLING if high_frequency else 1.0
        )
        self._start_time = None
        self._span: Optional[Span] = None
        self._should_trace = self._should_create_span()

        # Create component-specific tracer for Application Insights correlation
        self._tracer = trace.get_tracer(
            self.component or self._extract_component_from_span_name(self.name)
        )

    def _should_create_span(self) -> bool:
        """Determine if span should be created based on configuration and sampling."""
        if not _TRACING_ENABLED:
            return False

        # Apply sampling for high-frequency operations
        if self.high_frequency and self.sampling_rate < 1.0:
            return random.random() < self.sampling_rate

        return True

    def __enter__(self):
        if not self._should_trace:
            return self

        self._start_time = time.time()

        # Create span with proper kind for Application Insights correlation
        self._span = self._tracer.start_span(name=self.name, kind=self.span_kind)

        # Set essential correlation attributes using the correct format for Application Insights
        if self.call_connection_id:
            self._span.set_attribute(
                SpanAttr.CALL_CONNECTION_ID.value, self.call_connection_id
            )
        if self.session_id:
            self._span.set_attribute(SpanAttr.SESSION_ID.value, self.session_id)
        if self.test_case:
            self._span.set_attribute("test.case", self.test_case)

        # Set component and operation name for Application Insights
        component_name = self._extract_component_from_span_name(self.name)
        self._span.set_attribute("component", component_name)
        self._span.set_attribute(SpanAttr.OPERATION_NAME.value, self.name)

        # Set metadata attributes efficiently with proper namespacing
        for k, v in self.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                # Use consistent attribute naming for Application Insights
                attr_name = (
                    f"{component_name}.{k}" if not k.startswith(component_name) else k
                )
                self._span.set_attribute(attr_name, v)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._should_trace or not self._span:
            return

        try:
            # Calculate and set latency attributes
            if self._start_time:
                duration = (time.time() - self._start_time) * 1000  # in ms
                self._span.set_attribute("duration_ms", duration)
                self._span.set_attribute(
                    "latency.bucket", self._bucket_latency(duration)
                )

            # Set span status based on exception
            if exc_type:
                self._span.set_status(
                    Status(
                        StatusCode.ERROR, str(exc_val) if exc_val else "Unknown error"
                    )
                )
                self._span.set_attribute(SpanAttr.ERROR_TYPE.value, exc_type.__name__)
                if exc_val:
                    self._span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(exc_val))

                # Record exception for Application Insights
                self._span.record_exception(
                    exc_val
                    if exc_val
                    else Exception(f"{exc_type.__name__}: Unknown error")
                )
            else:
                self._span.set_status(Status(StatusCode.OK))

        finally:
            self._span.end()

    def set_attribute(self, key: str, value) -> None:
        """Set an attribute on the span if tracing is enabled."""
        if self._should_trace and self._span:
            self._span.set_attribute(key, value)

    def add_event(self, name: str, attributes: dict = None) -> None:
        """Add an event to the span if tracing is enabled."""
        if self._should_trace and self._span:
            self._span.add_event(name, attributes or {})

    @staticmethod
    def _extract_component_from_span_name(span_name: str) -> str:
        """Extract component name from span name for consistent Application Insights labeling."""
        if "." in span_name:
            parts = span_name.split(".")
            if len(parts) >= 2:
                return parts[0]  # e.g., "tts.synthesize" -> "tts"

        # Fallback patterns
        if span_name.startswith("acs"):
            return "acs"
        elif span_name.startswith("aoai") or span_name.startswith("gpt"):
            return "aoai"
        elif span_name.startswith("tts") or "speech" in span_name.lower():
            return "speech"
        elif span_name.startswith("orchestrator"):
            return "orchestrator"
        else:
            return "application"

    @staticmethod
    def _bucket_latency(duration_ms: float) -> str:
        """Optimized latency bucketing for performance monitoring."""
        if duration_ms < 50:
            return "<50ms"
        elif duration_ms < 100:
            return "50-100ms"
        elif duration_ms < 300:
            return "100-300ms"
        elif duration_ms < 1000:
            return "300ms-1s"
        elif duration_ms < 3000:
            return "1-3s"
        else:
            return ">3s"


class NoOpTraceContext:
    """
    Ultra-lightweight no-operation context manager for optimal performance.
    Used when tracing is disabled to minimize overhead.
    """

    # Memory optimization removed as __slots__ is redundant for this class

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def set_attribute(self, key: str, value) -> None:
        """No-op implementation of set_attribute."""
        pass

    def add_event(self, name: str, attributes: dict = None) -> None:
        """No-op implementation of add_event."""
        pass

    def record_exception(self, exception) -> None:
        """No-op implementation of record_exception."""
        pass


def create_trace_context(
    name: str,
    call_connection_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    high_frequency: bool = False,
    span_kind: SpanKind = SpanKind.INTERNAL,
) -> TraceContext:
    """
    Factory function for creating appropriate trace context based on configuration.

    Args:
        name: Span name
        call_connection_id: ACS call connection ID for correlation
        session_id: Session ID for correlation
        metadata: Additional span attributes
        high_frequency: Whether this is a high-frequency operation (applies sampling)
        span_kind: OpenTelemetry span kind for Application Insights correlation

    Returns:
        TraceContext or NoOpTraceContext based on configuration
    """
    if not _TRACING_ENABLED:
        return NoOpTraceContext()

    return TraceContext(
        name=name,
        call_connection_id=call_connection_id,
        session_id=session_id,
        metadata=metadata,
        high_frequency=high_frequency,
        span_kind=span_kind,
    )
