"""
Shared tracing utilities for OpenTelemetry instrumentation.

Provides common helper functions for span attributes and structured logging
without overriding OpenTelemetry Resource settings. These helpers avoid
encoding `service.name` or `span.kind` as span attributes—set `service.name`
via the TracerProvider Resource and pass `kind=SpanKind.*` when starting spans.

The helpers also prefer semantic attributes for edges (e.g., `peer.service`,
`net.peer.name`, `network.protocol.name`).
"""

import os
from typing import Any

from opentelemetry.trace import SpanKind, Status, StatusCode
from utils.ml_logging import get_logger

# Default logger for fallback usage
_default_logger = get_logger(__name__)

TRACING_ENABLED = os.getenv("ENABLE_TRACING", "false").lower() == "true"

# Logical service names used in logs/attributes (Resource `service.name` should
# be configured at process startup; these are for human-friendly values only.)
SERVICE_NAMES = {
    "acs_router": "acs-router",
    "acs_media_ws": "acs-websocket",
    "acs_media_handler": "acs-media-handler",
    "orchestrator": "orchestration-engine",
    "fraud_agent": "fraud-detection-service",
    "claim_intake_agent": "claims-service",
    "gpt_flow": "gpt-completion-service",
    "azure_openai": "azure-openai-service",
    # Legacy aliases
    "websocket": "acs-websocket",
    "media_handler": "acs-media-handler",
    "orchestration": "orchestration-engine",
    "auth_agent": "auth-service",
    "general_agent": "general-info-service",
    "claims_agent": "claims-service",
}


def create_span_attrs(
    component: str = "unknown",
    service: str = "unknown",
    **kwargs,
) -> dict[str, Any]:
    """Create generic span attributes with common fields.

    NOTE: We intentionally DO NOT set `service.name` or `span.kind` here.
    Set `service.name` on the Resource, and pass `kind=SpanKind.*` when
    creating spans.
    """
    attrs = {
        "component": component,
        "service": service,
        "service.version": "1.0.0",
    }
    attrs.update({k: v for k, v in kwargs.items() if v is not None})
    return attrs


def create_service_dependency_attrs(
    source_service: str,
    target_service: str,
    call_connection_id: str | None = None,
    session_id: str | None = None,
    *,
    ws: bool | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Create attributes for CLIENT spans that represent dependencies.

    Uses semantic keys to help App Map draw edges correctly.
    - peer.service: logical target
    - net.peer.name: target name/host (same logical value if not DNS based)
    - network.protocol.name: "websocket" for WS edges when ws=True
    """
    target_name = SERVICE_NAMES.get(target_service, target_service)

    attrs: dict[str, Any] = {
        "component": source_service,
        "peer.service": target_name,
        "net.peer.name": target_name,
    }
    if ws:
        attrs["network.protocol.name"] = "websocket"
    if call_connection_id is not None:
        attrs["rt.call.connection_id"] = call_connection_id
    if session_id is not None:
        attrs["rt.session.id"] = session_id

    # Merge any extra attributes
    attrs.update({k: v for k, v in kwargs.items() if v is not None})
    return attrs


def create_service_handler_attrs(
    service_name: str,
    call_connection_id: str | None = None,
    session_id: str | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Create attributes for SERVER spans that represent handlers.

    These identify the component and include stable correlation keys.
    """
    attrs: dict[str, Any] = {
        "component": service_name,
    }
    if call_connection_id:
        attrs["rt.call.connection_id"] = call_connection_id
    if session_id:
        attrs["rt.session.id"] = session_id

    attrs.update({k: v for k, v in kwargs.items() if v is not None})
    return attrs


def log_with_context(
    logger,
    level: str,
    message: str,
    operation: str | None = None,
    **kwargs,
) -> None:
    """Structured logging with consistent context.

    Filters None values to keep logs clean.
    """
    extra = {"operation_name": operation}
    extra.update({k: v for k, v in kwargs.items() if v is not None})

    try:
        getattr(logger, level)(message, extra=extra)
    except AttributeError:
        _default_logger.warning(f"Invalid log level '{level}' for message: {message}", extra=extra)


# ============================================================================
# High-Level Tracing Helpers - Clean & Simple
# ============================================================================


class TracedOperation:
    """Context manager for traced operations that handles all the boilerplate."""

    def __init__(
        self,
        tracer,
        logger,
        span_name: str,
        service_name: str,
        operation: str,
        span_kind: Any = SpanKind.INTERNAL,
        call_connection_id: str | None = None,
        session_id: str | None = None,
        **extra_attrs,
    ):
        self.tracer = tracer
        self.logger = logger
        self.span_name = span_name
        self.service_name = service_name
        self.operation = operation
        self.span_kind = span_kind
        self.call_connection_id = call_connection_id
        self.session_id = session_id
        self.extra_attrs = extra_attrs
        self.span = None

    def __enter__(self):
        attrs = create_service_handler_attrs(
            service_name=self.service_name,
            operation=self.operation,
            call_connection_id=self.call_connection_id,
            session_id=self.session_id,
            **self.extra_attrs,
        )

        self.span = self.tracer.start_span(self.span_name, kind=self.span_kind, attributes=attrs)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span and hasattr(self.span, "set_status"):
            if exc_type:
                try:
                    self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                    self.log_error(f"Operation failed: {exc_val}")
                except AttributeError:
                    # Handle NonRecordingSpan which doesn't have set_status
                    self.log_error(f"Operation failed (tracing disabled): {exc_val}")
            self.span.end()
        elif self.span:
            # Handle spans that don't support set_status
            if exc_type:
                self.log_error(f"Operation failed (span without status): {exc_val}")
            try:
                self.span.end()
            except AttributeError:
                pass

    def log_info(self, message: str, **kwargs):
        """Log info with consistent context."""
        log_with_context(
            self.logger,
            "info",
            message,
            operation=self.operation,
            call_connection_id=self.call_connection_id,
            session_id=self.session_id,
            **kwargs,
        )

    def log_error(self, message: str, **kwargs):
        """Log error with consistent context."""
        log_with_context(
            self.logger,
            "error",
            message,
            operation=self.operation,
            call_connection_id=self.call_connection_id,
            session_id=self.session_id,
            **kwargs,
        )

    def log_debug(self, message: str, **kwargs):
        """Log debug with consistent context."""
        log_with_context(
            self.logger,
            "debug",
            message,
            operation=self.operation,
            call_connection_id=self.call_connection_id,
            session_id=self.session_id,
            **kwargs,
        )

    def set_error(self, error_message: str):
        """Mark span as error with message."""
        if self.span and hasattr(self.span, "set_status"):
            try:
                self.span.set_status(Status(StatusCode.ERROR, error_message))
            except AttributeError:
                # Handle NonRecordingSpan which doesn't have set_status
                pass


def trace_acs_operation(
    tracer,
    logger,
    operation: str,
    call_connection_id: str | None = None,
    session_id: str | None = None,
    span_kind: Any = SpanKind.INTERNAL,
    **extra_attrs,
) -> TracedOperation:
    """
    Create a traced ACS operation with consistent naming and attributes.

    Usage:
        with trace_acs_operation(tracer, logger, "handle_call_connected", call_id) as op:
            op.log_info("Processing call connected event")
            # ... do work ...
    """
    return TracedOperation(
        tracer=tracer,
        logger=logger,
        span_name=f"acs_events.{operation}",
        service_name="acs_event_handlers",
        operation=operation,
        span_kind=span_kind,
        call_connection_id=call_connection_id,
        session_id=session_id,
        **extra_attrs,
    )


def trace_acs_dependency(
    tracer,
    logger,
    target_service: str,
    operation: str,
    call_connection_id: str | None = None,
    session_id: str | None = None,
    **extra_attrs,
) -> TracedOperation:
    """
    Create a traced dependency call with consistent naming and attributes.

    Usage:
        with trace_acs_dependency(tracer, logger, "azure_openai", "generate", call_id) as op:
            op.log_info("Calling Azure OpenAI")
            result = await openai_client.generate(...)
    """
    attrs = create_service_dependency_attrs(
        source_service="acs_event_handlers",
        target_service=target_service,
        call_connection_id=call_connection_id,
        session_id=session_id,
        **extra_attrs,
    )

    return TracedOperation(
        tracer=tracer,
        logger=logger,
        span_name=f"acs_events.call_{target_service}",
        service_name="acs_event_handlers",
        operation=operation,
        span_kind=SpanKind.CLIENT,
        call_connection_id=call_connection_id,
        session_id=session_id,
        **attrs,
    )


def get_acs_context_keys(event_context) -> dict[str, str | None]:
    """
    Extract consistent context keys from an ACS event context.

    Returns a dict with standardized keys that can be used across
    all ACS operations for consistent correlation.
    """
    return {
        "call_connection_id": getattr(event_context, "call_connection_id", None),
        "session_id": (
            getattr(event_context.memo_manager, "session_id", None)
            if hasattr(event_context, "memo_manager") and event_context.memo_manager
            else None
        ),
        "event_type": (
            getattr(event_context.event, "type", None) if hasattr(event_context, "event") else None
        ),
    }
