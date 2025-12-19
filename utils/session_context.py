"""
Session Context Management for Telemetry Correlation.

This module provides automatic propagation of session correlation attributes
(call_connection_id, session_id, etc.) to all spans and logs within a session.

Design Principles:
    1. Set once at connection level, inherit everywhere below
    2. No need to pass correlation IDs through function arguments
    3. Works across async boundaries and thread bridges
    4. Compatible with OpenTelemetry span context

Usage:
    # At WebSocket/connection entry point (set once):
    async with session_context(
        call_connection_id="abc123",
        session_id="session_xyz",
        transport_type="BROWSER"
    ):
        # All spans and logs within this block automatically get correlation IDs
        await handle_media_stream()

    # In any nested function (no extra params needed):
    logger.info("Processing speech")  # Automatically includes session_id, call_connection_id

    with tracer.start_as_current_span("my_operation"):
        pass  # Span automatically gets session attributes
"""

from __future__ import annotations

import contextvars
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace

# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT VARIABLE - Thread-safe, async-safe session state
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SessionCorrelation:
    """
    Immutable correlation data for a session.

    Attributes:
        call_connection_id: ACS call connection ID or browser session key
        session_id: User/conversation session identifier
        transport_type: "ACS" or "BROWSER"
        agent_name: Current agent handling the session
        extra: Additional custom attributes
    """

    call_connection_id: str | None = None
    session_id: str | None = None
    transport_type: str | None = None
    agent_name: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def short_id(self) -> str:
        """Short identifier for logging prefixes."""
        if self.call_connection_id:
            return self.call_connection_id[-8:]
        if self.session_id:
            return self.session_id[-8:]
        return "unknown"

    def to_span_attributes(self) -> dict[str, Any]:
        """Convert to OpenTelemetry span attributes."""
        attrs = {}
        if self.call_connection_id:
            attrs["call.connection.id"] = self.call_connection_id
            attrs["ai.session.id"] = self.call_connection_id  # App Insights standard
        if self.session_id:
            attrs["session.id"] = self.session_id
            attrs["ai.user.id"] = self.session_id  # App Insights standard
        if self.transport_type:
            attrs["transport.type"] = self.transport_type
        if self.agent_name:
            attrs["agent.name"] = self.agent_name
        # Include extra attributes
        for key, value in self.extra.items():
            if isinstance(value, (str, int, float, bool)):
                attrs[key] = value
        return attrs

    def to_log_record(self) -> dict[str, Any]:
        """Convert to log record extras for structured logging."""
        return {
            "call_connection_id": self.call_connection_id or "-",
            "session_id": self.session_id or "-",
            "transport_type": self.transport_type or "-",
            "agent_name": self.agent_name or "-",
            **{k: v for k, v in self.extra.items() if isinstance(v, (str, int, float, bool))},
        }


# The context variable - async-safe and thread-local
_session_context: contextvars.ContextVar[SessionCorrelation | None] = contextvars.ContextVar(
    "session_correlation", default=None
)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API - Context Managers
# ═══════════════════════════════════════════════════════════════════════════════


@asynccontextmanager
async def session_context(
    call_connection_id: str | None = None,
    session_id: str | None = None,
    transport_type: str | None = None,
    agent_name: str | None = None,
    **extra: Any,
):
    """
    Async context manager that establishes session correlation for all nested operations.

    Use this at the top-level connection handler (WebSocket accept, HTTP request).
    All spans and logs within this context automatically inherit correlation IDs.

    Args:
        call_connection_id: ACS call connection ID or unique connection identifier
        session_id: User/conversation session identifier
        transport_type: "ACS" or "BROWSER"
        agent_name: Name of the agent handling this session
        **extra: Additional custom attributes to include in all spans/logs

    Example:
        async with session_context(
            call_connection_id=config.call_connection_id,
            session_id=config.session_id,
            transport_type="BROWSER"
        ):
            await media_handler.run()  # All logs/spans get correlation
    """
    correlation = SessionCorrelation(
        call_connection_id=call_connection_id,
        session_id=session_id,
        transport_type=transport_type,
        agent_name=agent_name,
        extra=extra,
    )

    token = _session_context.set(correlation)

    # Create a root span for this session with all correlation attributes
    tracer = trace.get_tracer(__name__)
    span_name = f"session[{transport_type or 'unknown'}]"

    with tracer.start_as_current_span(
        span_name,
        kind=trace.SpanKind.SERVER,
        attributes=correlation.to_span_attributes(),
    ):
        try:
            yield correlation
        finally:
            _session_context.reset(token)


@contextmanager
def session_context_sync(
    call_connection_id: str | None = None,
    session_id: str | None = None,
    transport_type: str | None = None,
    agent_name: str | None = None,
    **extra: Any,
):
    """
    Sync version of session_context for thread-bridge callbacks.

    Use this when crossing from async to sync contexts (e.g., STT callbacks).
    """
    correlation = SessionCorrelation(
        call_connection_id=call_connection_id,
        session_id=session_id,
        transport_type=transport_type,
        agent_name=agent_name,
        extra=extra,
    )

    token = _session_context.set(correlation)

    tracer = trace.get_tracer(__name__)
    span_name = f"session_sync[{transport_type or 'unknown'}]"

    with tracer.start_as_current_span(
        span_name,
        kind=trace.SpanKind.INTERNAL,
        attributes=correlation.to_span_attributes(),
    ):
        try:
            yield correlation
        finally:
            _session_context.reset(token)


def set_session_context(
    call_connection_id: str | None = None,
    session_id: str | None = None,
    transport_type: str | None = None,
    agent_name: str | None = None,
    **extra: Any,
) -> contextvars.Token:
    """
    Set session context without creating a span (for thread bridges).

    Returns a token that MUST be used to reset the context.

    Example:
        token = set_session_context(call_connection_id="abc")
        try:
            do_work()
        finally:
            reset_session_context(token)
    """
    correlation = SessionCorrelation(
        call_connection_id=call_connection_id,
        session_id=session_id,
        transport_type=transport_type,
        agent_name=agent_name,
        extra=extra,
    )
    return _session_context.set(correlation)


def reset_session_context(token: contextvars.Token) -> None:
    """Reset session context using the token from set_session_context."""
    _session_context.reset(token)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API - Accessors
# ═══════════════════════════════════════════════════════════════════════════════


def get_session_correlation() -> SessionCorrelation | None:
    """
    Get current session correlation data.

    Returns None if not within a session_context.
    """
    return _session_context.get()


def get_correlation_id() -> str:
    """Get call_connection_id or session_id, or '-' if not set."""
    ctx = _session_context.get()
    if ctx:
        return ctx.call_connection_id or ctx.session_id or "-"
    return "-"


def get_short_id() -> str:
    """Get short identifier for log prefixes."""
    ctx = _session_context.get()
    return ctx.short_id if ctx else "unknown"


def get_span_attributes() -> dict[str, Any]:
    """
    Get span attributes from current session context.

    Use this to add session correlation to manually created spans:

        with tracer.start_as_current_span("my_span") as span:
            for k, v in get_span_attributes().items():
                span.set_attribute(k, v)
    """
    ctx = _session_context.get()
    return ctx.to_span_attributes() if ctx else {}


def get_log_extras() -> dict[str, Any]:
    """
    Get log record extras from current session context.

    Use this for explicit logging with correlation:

        logger.info("Message", extra=get_log_extras())
    """
    ctx = _session_context.get()
    return (
        ctx.to_log_record()
        if ctx
        else {
            "call_connection_id": "-",
            "session_id": "-",
            "transport_type": "-",
            "agent_name": "-",
        }
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SPAN HELPER - Auto-inject session attributes
# ═══════════════════════════════════════════════════════════════════════════════


def inject_session_attributes(span: trace.Span | None = None) -> None:
    """
    Inject session correlation attributes into the current or provided span.

    This is automatically called by the SpanProcessor, but can be called
    manually for spans created outside the normal flow.
    """
    target_span = span or trace.get_current_span()
    if not target_span or not target_span.is_recording():
        return

    ctx = _session_context.get()
    if not ctx:
        return

    for key, value in ctx.to_span_attributes().items():
        target_span.set_attribute(key, value)


# ═══════════════════════════════════════════════════════════════════════════════
# SPAN PROCESSOR - Auto-inject attributes on span start
# ═══════════════════════════════════════════════════════════════════════════════


class SessionContextSpanProcessor:
    """
    OpenTelemetry SpanProcessor that automatically injects session attributes.

    Add this processor to your TracerProvider to ensure all spans get
    session correlation attributes without manual intervention.

    Usage in telemetry_config.py:
        from utils.session_context import SessionContextSpanProcessor

        provider = TracerProvider(...)
        provider.add_span_processor(SessionContextSpanProcessor())
    """

    def on_start(self, span: trace.Span, parent_context: Any | None = None) -> None:
        """Called when a span starts - inject session attributes."""
        inject_session_attributes(span)

    def on_end(self, span: trace.Span) -> None:
        """Called when a span ends - no action needed."""
        pass

    def shutdown(self) -> None:
        """Shutdown the processor."""
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush - returns True immediately as no buffering."""
        return True
