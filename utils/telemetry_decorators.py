"""
Telemetry Decorators for OpenTelemetry Instrumentation.

This module provides decorator-based instrumentation for external service calls,
designed for Azure Application Insights Application Map visualization.

Usage:
    from utils.telemetry_decorators import trace_llm_call, trace_dependency, trace_speech

    @trace_llm_call(operation="chat", model="gpt-4o")
    async def call_openai(...):
        ...

    @trace_dependency(peer_service=PeerService.REDIS, operation="get")
    async def get_from_cache(...):
        ...

    # Turn-level tracking
    async with ConversationTurnSpan(
        call_connection_id="abc123",
        session_id="session_xyz",
        turn_number=1,
    ) as turn:
        # STT, LLM, TTS operations happen here
        turn.record_stt_complete(latency_ms=150.0)
        turn.record_llm_complete(ttfb_ms=120.0, total_ms=450.0, input_tokens=100, output_tokens=50)
        turn.record_tts_start()
"""

import functools
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.enums.monitoring import GenAIOperation, GenAIProvider, PeerService, SpanAttr

# Type variable for generic function typing
F = TypeVar("F", bound=Callable[..., Any])

# Module-level tracer
tracer = trace.get_tracer(__name__)


def trace_dependency(
    peer_service: str,
    operation: str | None = None,
    span_name: str | None = None,
    server_address: str | None = None,
    db_system: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator for tracing external dependency calls.

    Creates CLIENT spans with proper Application Map attributes for
    Azure App Insights visualization.

    Args:
        peer_service: Target service name (creates edge in App Map).
                     Use PeerService constants.
        operation: Operation name (e.g., "GET", "POST", "query")
        span_name: Custom span name. Defaults to function name.
        server_address: Target hostname/IP for the dependency.
        db_system: Database system type (for DB dependencies).

    Example:
        @trace_dependency(peer_service=PeerService.REDIS, operation="get")
        async def get_cached_value(key: str):
            return await redis.get(key)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = span_name or f"{peer_service}.{operation or func.__name__}"
            with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
                # Set Application Map attributes
                span.set_attribute(SpanAttr.PEER_SERVICE.value, peer_service)
                if operation:
                    span.set_attribute(SpanAttr.OPERATION_NAME.value, operation)
                if server_address:
                    span.set_attribute(SpanAttr.SERVER_ADDRESS.value, server_address)
                if db_system:
                    span.set_attribute(SpanAttr.DB_SYSTEM.value, db_system)
                    span.set_attribute(SpanAttr.DB_OPERATION.value, operation or func.__name__)

                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute(SpanAttr.ERROR_TYPE.value, type(e).__name__)
                    span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = span_name or f"{peer_service}.{operation or func.__name__}"
            with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
                # Set Application Map attributes
                span.set_attribute(SpanAttr.PEER_SERVICE.value, peer_service)
                if operation:
                    span.set_attribute(SpanAttr.OPERATION_NAME.value, operation)
                if server_address:
                    span.set_attribute(SpanAttr.SERVER_ADDRESS.value, server_address)
                if db_system:
                    span.set_attribute(SpanAttr.DB_SYSTEM.value, db_system)
                    span.set_attribute(SpanAttr.DB_OPERATION.value, operation or func.__name__)

                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute(SpanAttr.ERROR_TYPE.value, type(e).__name__)
                    span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def trace_llm_call(
    operation: str = GenAIOperation.CHAT,
    model: str | None = None,
    provider: str = GenAIProvider.AZURE_OPENAI,
    span_name: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator for tracing LLM/GenAI calls with OpenTelemetry semantic conventions.

    Creates CLIENT spans with GenAI attributes and Application Map support.

    Args:
        operation: GenAI operation type. Use GenAIOperation constants.
        model: Model name (e.g., "gpt-4o", "gpt-4o-mini")
        provider: GenAI provider. Use GenAIProvider constants.
        span_name: Custom span name. Defaults to "{provider}.{operation}".

    Example:
        @trace_llm_call(operation=GenAIOperation.CHAT, model="gpt-4o")
        async def generate_response(messages: list):
            return await client.chat.completions.create(...)

    Note:
        Token usage should be added to the span after the response:
        >>> span = trace.get_current_span()
        >>> span.set_attribute(SpanAttr.GENAI_USAGE_INPUT_TOKENS.value, usage.prompt_tokens)
        >>> span.set_attribute(SpanAttr.GENAI_USAGE_OUTPUT_TOKENS.value, usage.completion_tokens)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = span_name or f"{provider}.{operation}"
            with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
                # Application Map attributes
                span.set_attribute(SpanAttr.PEER_SERVICE.value, provider)

                # GenAI semantic convention attributes
                span.set_attribute(SpanAttr.GENAI_PROVIDER_NAME.value, provider)
                span.set_attribute(SpanAttr.GENAI_OPERATION_NAME.value, operation)
                if model:
                    span.set_attribute(SpanAttr.GENAI_REQUEST_MODEL.value, model)

                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute(SpanAttr.ERROR_TYPE.value, type(e).__name__)
                    span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute(SpanAttr.GENAI_CLIENT_OPERATION_DURATION.value, duration_ms)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = span_name or f"{provider}.{operation}"
            with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
                # Application Map attributes
                span.set_attribute(SpanAttr.PEER_SERVICE.value, provider)

                # GenAI semantic convention attributes
                span.set_attribute(SpanAttr.GENAI_PROVIDER_NAME.value, provider)
                span.set_attribute(SpanAttr.GENAI_OPERATION_NAME.value, operation)
                if model:
                    span.set_attribute(SpanAttr.GENAI_REQUEST_MODEL.value, model)

                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute(SpanAttr.ERROR_TYPE.value, type(e).__name__)
                    span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute(SpanAttr.GENAI_CLIENT_OPERATION_DURATION.value, duration_ms)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def trace_speech(
    operation: str,
    provider: str = GenAIProvider.AZURE_SPEECH,
    span_name: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator for tracing Azure Speech service calls.

    Creates CLIENT spans with Speech-specific attributes and Application Map support.

    Args:
        operation: Operation type (e.g., "synthesize", "recognize", "translate")
        provider: Speech provider. Defaults to Azure Speech.
        span_name: Custom span name. Defaults to "{provider}.{operation}".

    Example:
        @trace_speech(operation="synthesize")
        async def synthesize_speech(text: str, voice: str):
            # Speech synthesis logic
            ...

    Note:
        Speech-specific metrics should be added after synthesis:
        >>> span = trace.get_current_span()
        >>> span.set_attribute(SpanAttr.SPEECH_TTS_VOICE.value, voice_name)
        >>> span.set_attribute(SpanAttr.SPEECH_TTS_AUDIO_SIZE_BYTES.value, audio_size)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = span_name or f"{provider}.{operation}"
            with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
                # Application Map attributes
                span.set_attribute(SpanAttr.PEER_SERVICE.value, PeerService.AZURE_SPEECH)
                span.set_attribute(SpanAttr.OPERATION_NAME.value, operation)

                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute(SpanAttr.ERROR_TYPE.value, type(e).__name__)
                    span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    if "tts" in operation.lower() or "synth" in operation.lower():
                        span.set_attribute(
                            SpanAttr.SPEECH_TTS_SYNTHESIS_DURATION.value, duration_ms
                        )
                    else:
                        span.set_attribute(
                            SpanAttr.SPEECH_STT_RECOGNITION_DURATION.value, duration_ms
                        )

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = span_name or f"{provider}.{operation}"
            with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
                # Application Map attributes
                span.set_attribute(SpanAttr.PEER_SERVICE.value, PeerService.AZURE_SPEECH)
                span.set_attribute(SpanAttr.OPERATION_NAME.value, operation)

                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute(SpanAttr.ERROR_TYPE.value, type(e).__name__)
                    span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    if "tts" in operation.lower() or "synth" in operation.lower():
                        span.set_attribute(
                            SpanAttr.SPEECH_TTS_SYNTHESIS_DURATION.value, duration_ms
                        )
                    else:
                        span.set_attribute(
                            SpanAttr.SPEECH_STT_RECOGNITION_DURATION.value, duration_ms
                        )

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def trace_acs(
    operation: str,
    span_name: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator for tracing Azure Communication Services calls.

    Creates CLIENT spans with ACS-specific attributes and Application Map support.

    Args:
        operation: ACS operation (e.g., "answer", "play", "hangup", "transfer")
        span_name: Custom span name. Defaults to "azure.communication.{operation}".

    Example:
        @trace_acs(operation="answer")
        async def answer_call(incoming_call_context: str):
            return await call_automation.answer_call(...)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = span_name or f"azure.communication.{operation}"
            with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
                # Application Map attributes
                span.set_attribute(SpanAttr.PEER_SERVICE.value, PeerService.AZURE_COMMUNICATION)
                span.set_attribute(SpanAttr.ACS_OPERATION.value, operation)

                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute(SpanAttr.ERROR_TYPE.value, type(e).__name__)
                    span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = span_name or f"azure.communication.{operation}"
            with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
                # Application Map attributes
                span.set_attribute(SpanAttr.PEER_SERVICE.value, PeerService.AZURE_COMMUNICATION)
                span.set_attribute(SpanAttr.ACS_OPERATION.value, operation)

                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute(SpanAttr.ERROR_TYPE.value, type(e).__name__)
                    span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS - For adding attributes after function execution
# ═══════════════════════════════════════════════════════════════════════════════


def add_genai_usage(
    input_tokens: int,
    output_tokens: int,
    response_model: str | None = None,
    response_id: str | None = None,
    finish_reasons: list[str] | None = None,
) -> None:
    """
    Add GenAI token usage to the current span.

    Call this within a traced function after receiving the LLM response.

    Args:
        input_tokens: Number of prompt tokens used.
        output_tokens: Number of completion tokens generated.
        response_model: Actual model that processed the request.
        response_id: Response identifier from the API.
        finish_reasons: List of completion reasons (e.g., ["stop"]).

    Example:
        @trace_llm_call(operation="chat", model="gpt-4o")
        async def generate_response(messages):
            response = await client.chat.completions.create(...)
            add_genai_usage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                response_model=response.model,
                response_id=response.id,
            )
            return response
    """
    span = trace.get_current_span()
    span.set_attribute(SpanAttr.GENAI_USAGE_INPUT_TOKENS.value, input_tokens)
    span.set_attribute(SpanAttr.GENAI_USAGE_OUTPUT_TOKENS.value, output_tokens)
    if response_model:
        span.set_attribute(SpanAttr.GENAI_RESPONSE_MODEL.value, response_model)
    if response_id:
        span.set_attribute(SpanAttr.GENAI_RESPONSE_ID.value, response_id)
    if finish_reasons:
        span.set_attribute(SpanAttr.GENAI_RESPONSE_FINISH_REASONS.value, finish_reasons)


def add_speech_tts_metrics(
    voice: str | None = None,
    audio_size_bytes: int | None = None,
    text_length: int | None = None,
    output_format: str | None = None,
    sample_rate: int | None = None,
    frame_count: int | None = None,
) -> None:
    """
    Add TTS-specific metrics to the current span.

    Call this within a traced TTS function after synthesis completes.

    Args:
        voice: Voice name used for synthesis.
        audio_size_bytes: Total size of generated audio in bytes.
        text_length: Length of input text.
        output_format: Audio output format (e.g., "audio-24khz-48kbitrate-mono-mp3").
        sample_rate: Audio sample rate in Hz.
        frame_count: Number of audio frames generated.
    """
    span = trace.get_current_span()
    if voice:
        span.set_attribute(SpanAttr.SPEECH_TTS_VOICE.value, voice)
    if audio_size_bytes is not None:
        span.set_attribute(SpanAttr.SPEECH_TTS_AUDIO_SIZE_BYTES.value, audio_size_bytes)
    if text_length is not None:
        span.set_attribute(SpanAttr.SPEECH_TTS_TEXT_LENGTH.value, text_length)
    if output_format:
        span.set_attribute(SpanAttr.SPEECH_TTS_OUTPUT_FORMAT.value, output_format)
    if sample_rate is not None:
        span.set_attribute(SpanAttr.SPEECH_TTS_SAMPLE_RATE.value, sample_rate)
    if frame_count is not None:
        span.set_attribute(SpanAttr.SPEECH_TTS_FRAME_COUNT.value, frame_count)


def add_speech_stt_metrics(
    language: str | None = None,
    confidence: float | None = None,
    text_length: int | None = None,
    result_reason: str | None = None,
) -> None:
    """
    Add STT-specific metrics to the current span.

    Call this within a traced STT function after recognition completes.

    Args:
        language: Detected or specified language.
        confidence: Recognition confidence score (0.0-1.0).
        text_length: Length of recognized text.
        result_reason: Recognition result reason.
    """
    span = trace.get_current_span()
    if language:
        span.set_attribute(SpanAttr.SPEECH_STT_LANGUAGE.value, language)
    if confidence is not None:
        span.set_attribute(SpanAttr.SPEECH_STT_CONFIDENCE.value, confidence)
    if text_length is not None:
        span.set_attribute(SpanAttr.SPEECH_STT_TEXT_LENGTH.value, text_length)
    if result_reason:
        span.set_attribute(SpanAttr.SPEECH_STT_RESULT_REASON.value, result_reason)


def add_turn_metrics(
    turn_number: int,
    stt_latency_ms: float | None = None,
    llm_ttfb_ms: float | None = None,
    llm_total_ms: float | None = None,
    tts_ttfb_ms: float | None = None,
    tts_total_ms: float | None = None,
    total_latency_ms: float | None = None,
    transport_type: str | None = None,
) -> None:
    """
    Add per-turn latency metrics to the current span.

    Call this at the end of a conversation turn to record timing.

    Args:
        turn_number: Sequential turn number in the conversation.
        stt_latency_ms: Speech-to-text processing time.
        llm_ttfb_ms: Time to first LLM token.
        llm_total_ms: Total LLM processing time.
        tts_ttfb_ms: Time to first TTS audio.
        tts_total_ms: Total TTS synthesis time.
        total_latency_ms: End-to-end turn latency.
        transport_type: "acs" or "browser".
    """
    span = trace.get_current_span()
    span.set_attribute(SpanAttr.TURN_NUMBER.value, turn_number)
    if stt_latency_ms is not None:
        span.set_attribute(SpanAttr.TURN_STT_LATENCY_MS.value, stt_latency_ms)
    if llm_ttfb_ms is not None:
        span.set_attribute(SpanAttr.TURN_LLM_TTFB_MS.value, llm_ttfb_ms)
    if llm_total_ms is not None:
        span.set_attribute(SpanAttr.TURN_LLM_TOTAL_MS.value, llm_total_ms)
    if tts_ttfb_ms is not None:
        span.set_attribute(SpanAttr.TURN_TTS_TTFB_MS.value, tts_ttfb_ms)
    if tts_total_ms is not None:
        span.set_attribute(SpanAttr.TURN_TTS_TOTAL_MS.value, tts_total_ms)
    if total_latency_ms is not None:
        span.set_attribute(SpanAttr.TURN_TOTAL_LATENCY_MS.value, total_latency_ms)
    if transport_type:
        span.set_attribute(SpanAttr.TURN_TRANSPORT_TYPE.value, transport_type)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION TURN SPAN - Context Manager for Turn-Level Tracking
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class TurnMetrics:
    """Collected metrics for a conversation turn."""

    # Timing metrics (all in milliseconds)
    stt_latency_ms: float | None = None
    llm_ttfb_ms: float | None = None
    llm_total_ms: float | None = None
    tts_ttfb_ms: float | None = None
    tts_total_ms: float | None = None
    total_latency_ms: float | None = None
    speech_cascade_ttfb_ms: float | None = None

    # Token metrics
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None

    # Content metrics
    user_text_length: int | None = None
    assistant_text_length: int | None = None

    # Timestamps for computing deltas
    turn_start_time: float = field(default_factory=time.perf_counter)
    stt_complete_time: float | None = None
    llm_first_token_time: float | None = None
    llm_complete_time: float | None = None
    tts_start_time: float | None = None
    tts_first_audio_time: float | None = None
    tts_complete_time: float | None = None


class ConversationTurnSpan:
    """
    Context manager for tracking a complete conversation turn with OpenTelemetry.

    Creates an INTERNAL span that wraps an entire turn (user speech → LLM → TTS)
    and collects timing metrics at each stage.

    Usage:
        async with ConversationTurnSpan(
            call_connection_id="abc123",
            session_id="session_xyz",
            turn_number=1,
            transport_type="acs",
        ) as turn:
            # After STT completes
            turn.record_stt_complete(text="Hello", latency_ms=150.0)

            # After LLM first token
            turn.record_llm_first_token()

            # After LLM completes
            turn.record_llm_complete(
                total_ms=450.0,
                input_tokens=100,
                output_tokens=50,
                response_text="Hi there!",
            )

            # When TTS starts streaming
            turn.record_tts_start()

            # When first audio chunk is ready
            turn.record_tts_first_audio()

            # Turn ends when context exits - metrics auto-calculated

    Attributes:
        turn_id: Unique identifier for this turn
        metrics: TurnMetrics dataclass with all collected metrics
        span: The underlying OpenTelemetry span
    """

    def __init__(
        self,
        call_connection_id: str | None = None,
        session_id: str | None = None,
        turn_number: int | None = None,
        transport_type: str | None = None,
        user_intent_preview: str | None = None,
    ):
        """
        Initialize turn tracking.

        Args:
            call_connection_id: ACS call connection ID for correlation.
            session_id: Session identifier for correlation.
            turn_number: Sequential turn number (1-indexed).
            transport_type: "acs" or "browser".
            user_intent_preview: Brief preview of user intent (first ~50 chars).
        """
        self.turn_id = f"turn_{uuid.uuid4().hex[:8]}"
        self.call_connection_id = call_connection_id
        self.session_id = session_id
        self.turn_number = turn_number
        self.transport_type = transport_type
        self.user_intent_preview = user_intent_preview

        self.metrics = TurnMetrics()
        self.span: trace.Span | None = None
        self._entered = False

    async def __aenter__(self) -> "ConversationTurnSpan":
        """Enter the turn span context."""
        attrs = {
            SpanAttr.TURN_ID.value: self.turn_id,
            "conversation.turn.phase": "complete",
        }

        if self.call_connection_id:
            attrs[SpanAttr.CALL_CONNECTION_ID.value] = self.call_connection_id
        if self.session_id:
            attrs[SpanAttr.SESSION_ID.value] = self.session_id
        if self.turn_number is not None:
            attrs[SpanAttr.TURN_NUMBER.value] = self.turn_number
        if self.transport_type:
            attrs[SpanAttr.TURN_TRANSPORT_TYPE.value] = self.transport_type
        if self.user_intent_preview:
            attrs[SpanAttr.TURN_USER_INTENT_PREVIEW.value] = self.user_intent_preview[:50]

        # Use descriptive span name: voice.turn.<N>.total for end-to-end tracking
        turn_label = self.turn_number if self.turn_number is not None else self.turn_id
        self.span = tracer.start_span(
            f"voice.turn.{turn_label}.total",
            kind=SpanKind.INTERNAL,
            attributes=attrs,
        )
        self.metrics.turn_start_time = time.perf_counter()
        self._entered = True

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the turn span context and finalize metrics."""
        if not self.span:
            return

        try:
            # Calculate total latency
            end_time = time.perf_counter()
            self.metrics.total_latency_ms = (end_time - self.metrics.turn_start_time) * 1000

            # Set all collected metrics on span
            self._set_final_metrics()

            # Add turn completion event
            self.span.add_event(
                "turn.complete",
                attributes={
                    "turn.total_latency_ms": self.metrics.total_latency_ms,
                    "turn.success": exc_type is None,
                },
            )

            # Handle exceptions
            if exc_type is not None:
                self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self.span.set_attribute(SpanAttr.ERROR_TYPE.value, exc_type.__name__)
                self.span.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(exc_val))
            else:
                self.span.set_status(Status(StatusCode.OK))

        finally:
            self.span.end()

    def _set_final_metrics(self) -> None:
        """Set all collected metrics on the span."""
        if not self.span:
            return

        # Timing metrics - use descriptive attribute names with _MS suffix
        if self.metrics.stt_latency_ms is not None:
            self.span.set_attribute(SpanAttr.TURN_STT_LATENCY_MS.value, self.metrics.stt_latency_ms)
        if self.metrics.llm_ttfb_ms is not None:
            self.span.set_attribute(SpanAttr.TURN_LLM_TTFB_MS.value, self.metrics.llm_ttfb_ms)
        if self.metrics.llm_total_ms is not None:
            self.span.set_attribute(SpanAttr.TURN_LLM_TOTAL_MS.value, self.metrics.llm_total_ms)
        if self.metrics.tts_ttfb_ms is not None:
            self.span.set_attribute(SpanAttr.TURN_TTS_TTFB_MS.value, self.metrics.tts_ttfb_ms)
        if self.metrics.tts_total_ms is not None:
            self.span.set_attribute(SpanAttr.TURN_TTS_TOTAL_MS.value, self.metrics.tts_total_ms)
        if self.metrics.total_latency_ms is not None:
            self.span.set_attribute(
                SpanAttr.TURN_TOTAL_LATENCY_MS.value, self.metrics.total_latency_ms
            )
        if self.metrics.speech_cascade_ttfb_ms is not None:
            self.span.set_attribute(
                "turn.speech_cascade_ttfb_ms", self.metrics.speech_cascade_ttfb_ms
            )

        # Token metrics - set on both GenAI standard and turn-specific attributes
        if self.metrics.llm_input_tokens is not None:
            self.span.set_attribute(
                SpanAttr.GENAI_USAGE_INPUT_TOKENS.value, self.metrics.llm_input_tokens
            )
            self.span.set_attribute(
                SpanAttr.TURN_LLM_INPUT_TOKENS.value, self.metrics.llm_input_tokens
            )
        if self.metrics.llm_output_tokens is not None:
            self.span.set_attribute(
                SpanAttr.GENAI_USAGE_OUTPUT_TOKENS.value, self.metrics.llm_output_tokens
            )
            self.span.set_attribute(
                SpanAttr.TURN_LLM_OUTPUT_TOKENS.value, self.metrics.llm_output_tokens
            )

        # Calculate tokens per second if we have the data
        if (
            self.metrics.llm_output_tokens
            and self.metrics.llm_total_ms
            and self.metrics.llm_total_ms > 0
        ):
            tokens_per_sec = (self.metrics.llm_output_tokens / self.metrics.llm_total_ms) * 1000
            self.span.set_attribute(SpanAttr.TURN_LLM_TOKENS_PER_SEC.value, tokens_per_sec)

        # Content metrics
        if self.metrics.user_text_length is not None:
            self.span.set_attribute("turn.user_text_length", self.metrics.user_text_length)
        if self.metrics.assistant_text_length is not None:
            self.span.set_attribute(
                "turn.assistant_text_length", self.metrics.assistant_text_length
            )

    def record_stt_complete(
        self,
        text: str | None = None,
        latency_ms: float | None = None,
        language: str | None = None,
        confidence: float | None = None,
    ) -> None:
        """
        Record STT completion.

        Args:
            text: Recognized user text.
            latency_ms: STT processing time. If None, computed from turn start.
            language: Detected language.
            confidence: Recognition confidence.
        """
        now = time.perf_counter()
        self.metrics.stt_complete_time = now

        if latency_ms is not None:
            self.metrics.stt_latency_ms = latency_ms
        else:
            self.metrics.stt_latency_ms = (now - self.metrics.turn_start_time) * 1000

        if text:
            self.metrics.user_text_length = len(text)
            # Update user intent preview if not already set
            if not self.user_intent_preview and self.span:
                preview = text[:50] + "..." if len(text) > 50 else text
                self.span.set_attribute(SpanAttr.TURN_USER_INTENT_PREVIEW.value, preview)

        if self.span:
            self.span.add_event(
                "stt.complete",
                attributes={
                    "stt.latency_ms": self.metrics.stt_latency_ms,
                    **({"stt.language": language} if language else {}),
                    **({"stt.confidence": confidence} if confidence is not None else {}),
                    **({"stt.text_length": len(text)} if text else {}),
                },
            )

    def record_llm_first_token(self) -> None:
        """Record when the first LLM token is received."""
        now = time.perf_counter()
        self.metrics.llm_first_token_time = now

        # TTFB from STT complete (or turn start if STT not recorded)
        reference_time = self.metrics.stt_complete_time or self.metrics.turn_start_time
        self.metrics.llm_ttfb_ms = (now - reference_time) * 1000

        if self.span:
            self.span.add_event(
                "llm.first_token", attributes={"llm.ttfb_ms": self.metrics.llm_ttfb_ms}
            )

    def record_llm_complete(
        self,
        total_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        response_text: str | None = None,
        model: str | None = None,
    ) -> None:
        """
        Record LLM completion.

        Args:
            total_ms: Total LLM processing time. If None, computed from STT complete.
            input_tokens: Number of prompt tokens.
            output_tokens: Number of completion tokens.
            response_text: Generated response text.
            model: Model used for generation.
        """
        now = time.perf_counter()
        self.metrics.llm_complete_time = now

        if total_ms is not None:
            self.metrics.llm_total_ms = total_ms
        else:
            reference_time = self.metrics.stt_complete_time or self.metrics.turn_start_time
            self.metrics.llm_total_ms = (now - reference_time) * 1000

        if input_tokens is not None:
            self.metrics.llm_input_tokens = input_tokens
        if output_tokens is not None:
            self.metrics.llm_output_tokens = output_tokens
        if response_text:
            self.metrics.assistant_text_length = len(response_text)

        if self.span:
            event_attrs = {"llm.total_ms": self.metrics.llm_total_ms}
            if input_tokens is not None:
                event_attrs["llm.input_tokens"] = input_tokens
            if output_tokens is not None:
                event_attrs["llm.output_tokens"] = output_tokens
            if model:
                event_attrs["llm.model"] = model
            self.span.add_event("llm.complete", attributes=event_attrs)

    def record_tts_start(self) -> None:
        """Record when TTS synthesis starts."""
        self.metrics.tts_start_time = time.perf_counter()

        if self.span:
            self.span.add_event("tts.start")

    def record_tts_first_audio(self) -> None:
        """Record when first TTS audio chunk is ready."""
        now = time.perf_counter()
        self.metrics.tts_first_audio_time = now

        # TTFB from LLM complete (or TTS start)
        reference_time = (
            self.metrics.llm_complete_time
            or self.metrics.tts_start_time
            or self.metrics.turn_start_time
        )
        self.metrics.tts_ttfb_ms = (now - reference_time) * 1000

        # Speech Cascade TTFB: STT Complete -> First Audio
        if self.metrics.stt_complete_time:
            self.metrics.speech_cascade_ttfb_ms = (now - self.metrics.stt_complete_time) * 1000

        if self.span:
            attrs = {"tts.ttfb_ms": self.metrics.tts_ttfb_ms}
            if self.metrics.speech_cascade_ttfb_ms is not None:
                attrs["turn.speech_cascade_ttfb_ms"] = self.metrics.speech_cascade_ttfb_ms

            self.span.add_event("tts.first_audio", attributes=attrs)

    def record_tts_complete(self, total_ms: float | None = None) -> None:
        """
        Record TTS completion.

        Args:
            total_ms: Total TTS synthesis time. If None, computed from TTS start.
        """
        now = time.perf_counter()
        self.metrics.tts_complete_time = now

        if total_ms is not None:
            self.metrics.tts_total_ms = total_ms
        elif self.metrics.tts_start_time:
            self.metrics.tts_total_ms = (now - self.metrics.tts_start_time) * 1000

        if self.span:
            self.span.add_event(
                "tts.complete", attributes={"tts.total_ms": self.metrics.tts_total_ms or 0}
            )

    def add_metadata(self, key: str, value: Any) -> None:
        """Add custom metadata to the turn span."""
        if self.span:
            self.span.set_attribute(f"turn.metadata.{key}", str(value))
