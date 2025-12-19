import functools
import json
import logging
import os
import time
from collections.abc import Callable

from colorama import Fore, Style
from colorama import init as colorama_init

# Early .env load to check DISABLE_CLOUD_TELEMETRY before importing any OTel
try:
    from dotenv import load_dotenv

    if os.path.isfile(".env"):
        load_dotenv(override=False)
except Exception:
    pass

# Conditionally import OpenTelemetry based on DISABLE_CLOUD_TELEMETRY
_telemetry_disabled = os.getenv("DISABLE_CLOUD_TELEMETRY", "false").lower() == "true"

if not _telemetry_disabled:
    from opentelemetry import trace

    from utils.telemetry_config import (
        is_azure_monitor_configured,
        setup_azure_monitor,
    )
else:
    # Mock objects when telemetry is disabled
    trace = None
    setup_azure_monitor = lambda *args, **kwargs: None
    is_azure_monitor_configured = lambda: False

colorama_init(autoreset=True)

# Define a new logging level named "KEYINFO" with a level of 25
KEYINFO_LEVEL_NUM = 25
logging.addLevelName(KEYINFO_LEVEL_NUM, "KEYINFO")


def keyinfo(self: logging.Logger, message, *args, **kws):
    if self.isEnabledFor(KEYINFO_LEVEL_NUM):
        self._log(KEYINFO_LEVEL_NUM, message, args, **kws)


logging.Logger.keyinfo = keyinfo


class JsonFormatter(logging.Formatter):
    """JSON formatter with optional PII scrubbing for structured logging."""

    def __init__(self, *args, enable_pii_scrubbing: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self._pii_scrubber = None
        if enable_pii_scrubbing:
            try:
                from utils.pii_filter import get_pii_scrubber

                self._pii_scrubber = get_pii_scrubber()
            except ImportError:
                pass

    def _scrub(self, value: str) -> str:
        """Scrub PII from a string if scrubber is enabled."""
        if self._pii_scrubber and isinstance(value, str):
            return self._pii_scrubber.scrub_string(value)
        return value

    def format(self, record: logging.LogRecord) -> str:
        record.funcName = getattr(record, "func_name_override", record.funcName)
        record.filename = getattr(record, "file_name_override", record.filename)
        record.trace_id = getattr(record, "trace_id", "-")
        record.span_id = getattr(record, "span_id", "-")
        record.session_id = getattr(record, "session_id", "-")
        record.call_connection_id = getattr(record, "call_connection_id", "-")

        # Get message and optionally scrub PII
        message = record.getMessage()
        if self._pii_scrubber:
            message = self._scrub(message)

        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "name": record.name,
            "process": record.processName,
            "level": record.levelname,
            "trace_id": record.trace_id,
            "span_id": record.span_id,
            "session_id": record.session_id,
            "call_connection_id": record.call_connection_id,
            "operation_name": getattr(record, "operation_name", "-"),
            "component": getattr(record, "component", "-"),
            "message": message,
            "file": record.filename,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add any custom span attributes as additional fields
        for attr_name in dir(record):
            if attr_name.startswith(("call_", "session_", "agent_", "model_", "operation_")):
                value = getattr(record, attr_name)
                # Scrub PII from custom attributes
                if self._pii_scrubber and isinstance(value, str):
                    value = self._scrub(value)
                log_record[attr_name] = value

        return json.dumps(log_record)


class PrettyFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.MAGENTA,
        "KEYINFO": Fore.BLUE,
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        level = record.levelname
        name = record.name
        msg = record.getMessage()

        color = self.LEVEL_COLORS.get(level, "")
        return f"{Fore.WHITE}[{timestamp}]{Style.RESET_ALL} {color}{level}{Style.RESET_ALL} - {Fore.BLUE}{name}{Style.RESET_ALL}: {msg}"


# Patterns for noisy log messages that should be filtered out
_NOISY_LOG_PATTERNS = [
    # WebSocket frame-level operations
    "websocket receive",
    "websocket send",
    "ws receive",
    "ws send",
    "< TEXT",  # WebSocket frame markers
    "> TEXT",
    "< BINARY",
    "> BINARY",
    "< CLOSE",
    "> CLOSE",
    "< PING",
    "> PING",
    "< PONG",
    "> PONG",
    # Starlette/uvicorn internal
    "ASGI [",
    "application startup",
    "application shutdown",
]


class PIIScrubbingFilter(logging.Filter):
    """
    Logging filter that scrubs PII from log messages before they are emitted.

    This filter modifies the log record's message to remove sensitive data like:
    - Phone numbers
    - Email addresses
    - Social Security Numbers
    - Credit card numbers

    Configuration via environment variables (see utils/pii_filter.py):
    - TELEMETRY_PII_SCRUBBING_ENABLED: Enable/disable (default: true)
    - TELEMETRY_PII_SCRUB_PHONE_NUMBERS, etc.
    """

    def __init__(self, name: str = ""):
        super().__init__(name)
        self._scrubber = None
        try:
            from utils.pii_filter import get_pii_scrubber

            self._scrubber = get_pii_scrubber()
        except ImportError:
            pass

    def filter(self, record: logging.LogRecord) -> bool:
        if self._scrubber and self._scrubber.config.enabled:
            # Scrub the message
            # Note: We modify record.msg directly since getMessage() formats it
            if record.msg and isinstance(record.msg, str):
                record.msg = self._scrubber.scrub_string(record.msg)

            # Also scrub args if they're strings
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: self._scrubber.scrub_string(v) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        self._scrubber.scrub_string(a) if isinstance(a, str) else a
                        for a in record.args
                    )

        return True  # Always pass the record through


class WebSocketNoiseFilter(logging.Filter):
    """
    Filter that drops high-frequency WebSocket-related log messages.

    This complements the NoisySpanFilterSampler (which filters spans) by
    also filtering the corresponding log entries that would pollute App Insights logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()

            # Filter out empty messages - these cause Azure Monitor 400 errors
            # "Field 'message' on type 'MessageData' is required but missing or empty"
            if not msg or msg.strip() == "":
                return False  # Drop empty logs

            msg_lower = msg.lower()

            # Check against noisy patterns
            for pattern in _NOISY_LOG_PATTERNS:
                if pattern.lower() in msg_lower:
                    return False  # Drop this log

            # Also filter by logger name for known noisy sources
            name_lower = record.name.lower()
            if any(n in name_lower for n in ("websocket", "uvicorn.protocols", "starlette")):
                # Drop INFO and DEBUG level from these loggers
                if record.levelno <= logging.INFO:
                    return False

            return True  # Allow this log
        except Exception:
            return True  # On error, let the log through


class TraceLogFilter(logging.Filter):
    """
    Logging filter that enriches log records with session correlation and trace context.

    Correlation is sourced in priority order:
    1. Session context (contextvars) - set once at connection level
    2. Current span attributes - for spans created with correlation
    3. Default values ("-") - when no context available

    This ensures all logs within a session_context automatically get correlation IDs
    without needing to pass them through function arguments.
    """

    def filter(self, record):
        if _telemetry_disabled or trace is None:
            # Set default values when telemetry is disabled
            record.trace_id = "-"
            record.span_id = "-"
            record.session_id = "-"
            record.call_connection_id = "-"
            record.operation_name = "-"
            record.component = "-"
            return True

        # Get trace IDs from current span
        span = trace.get_current_span()
        context = span.get_span_context() if span else None
        record.trace_id = f"{context.trace_id:032x}" if context and context.trace_id else "-"
        record.span_id = f"{context.span_id:016x}" if context and context.span_id else "-"

        # Priority 1: Get correlation from session context (set at connection level)
        try:
            from utils.session_context import get_session_correlation

            session_ctx = get_session_correlation()
        except ImportError:
            session_ctx = None

        if session_ctx:
            # Use session context - this is the preferred path
            record.session_id = session_ctx.session_id or "-"
            record.call_connection_id = session_ctx.call_connection_id or "-"
            record.transport_type = session_ctx.transport_type or "-"
            record.agent_name = session_ctx.agent_name or "-"
            # Safely get span name - NonRecordingSpan doesn't have 'name' attribute
            record.operation_name = getattr(span, "name", "-") if span else "-"
            record.component = session_ctx.extra.get("component", "-")

            # Add any extra attributes from session context
            for key, value in session_ctx.extra.items():
                if isinstance(value, (str, int, float, bool)):
                    log_key = key.replace(".", "_")
                    setattr(record, log_key, value)
        elif span and span.is_recording():
            # Priority 2: Fall back to span attributes
            span_attributes = getattr(span, "_attributes", {})

            record.session_id = span_attributes.get(
                "session.id", span_attributes.get("ai.user.id", "-")
            )
            record.call_connection_id = span_attributes.get(
                "call.connection.id", span_attributes.get("ai.session.id", "-")
            )
            record.operation_name = span_attributes.get(
                "operation.name", getattr(span, "name", "-")
            )
            record.component = span_attributes.get("component", "-")

            # Add custom properties from span
            for key, value in span_attributes.items():
                if key.startswith(("call.", "session.", "agent.", "model.", "operation.")):
                    log_key = key.replace(".", "_")
                    setattr(record, log_key, value)
        else:
            # Priority 3: Default values
            record.session_id = "-"
            record.call_connection_id = "-"
            record.operation_name = "-"
            record.component = "-"

        return True


def set_span_correlation_attributes(
    call_connection_id: str | None = None,
    session_id: str | None = None,
    agent_name: str | None = None,
    operation_name: str | None = None,
    custom_attributes: dict | None = None,
) -> None:
    """
    Set correlation attributes on the current span that will appear as customDimensions in Application Insights.

    Args:
        call_connection_id: ACS call connection ID for correlation
        session_id: User session ID for correlation
        agent_name: Name of the AI agent handling the request
        operation_name: Name of the current operation
        custom_attributes: Additional custom attributes to set
    """
    if _telemetry_disabled or trace is None:
        return

    span = trace.get_current_span()
    if not span or not span.is_recording():
        return

    # Standard correlation attributes
    if call_connection_id:
        span.set_attribute("call.connection.id", call_connection_id)
        span.set_attribute("ai.session.id", call_connection_id)  # Application Insights standard

    if session_id:
        span.set_attribute("session.id", session_id)
        span.set_attribute("ai.user.id", session_id)  # Application Insights standard

    if agent_name:
        span.set_attribute("agent.name", agent_name)

    if operation_name:
        span.set_attribute("operation.name", operation_name)

    # Custom attributes
    if custom_attributes:
        for key, value in custom_attributes.items():
            if isinstance(value, (str, int, float, bool)):
                span.set_attribute(key, value)


def log_with_correlation(
    logger: logging.Logger,
    level: int,
    message: str,
    call_connection_id: str | None = None,
    session_id: str | None = None,
    agent_name: str | None = None,
    operation_name: str | None = None,
    custom_attributes: dict | None = None,
) -> None:
    """
    Log a message with correlation attributes that will appear in Application Insights.

    Args:
        logger: Logger instance
        level: Logging level (logging.INFO, logging.ERROR, etc.)
        message: Log message
        call_connection_id: ACS call connection ID
        session_id: User session ID
        agent_name: AI agent name
        operation_name: Operation name
        custom_attributes: Additional custom attributes
    """
    # Set span attributes first
    set_span_correlation_attributes(
        call_connection_id=call_connection_id,
        session_id=session_id,
        agent_name=agent_name,
        operation_name=operation_name,
        custom_attributes=custom_attributes,
    )

    # Log the message (attributes will be automatically included via TraceLogFilter)
    logger.log(level, message)


def get_logger(
    name: str = "micro",
    level: int | None = None,
    include_stream_handler: bool = True,
) -> logging.Logger:
    """
    Get or create a logger with proper Azure Monitor integration.

    IMPORTANT: To prevent duplicate log entries in Application Insights:
    - configure_azure_monitor() already attaches an OpenTelemetry LoggingHandler to the ROOT logger
    - We do NOT add another LoggingHandler here; logs propagate to root automatically
    - We only add filters and stream handlers for console output

    Args:
        name: Logger name (hierarchical, e.g., "api.v1.endpoints")
        level: Optional logging level; defaults to INFO if logger has no level set
        include_stream_handler: Whether to add a console StreamHandler

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if level is not None or logger.level == 0:
        logger.setLevel(level or logging.INFO)

    is_production = os.environ.get("ENV", "dev").lower() == "prod"

    # ═══════════════════════════════════════════════════════════════════════════
    # DUPLICATE LOG PREVENTION:
    # configure_azure_monitor() adds an OpenTelemetry LoggingHandler to the ROOT logger.
    # Due to Python's logging hierarchy, logs propagate from child loggers -> root.
    # If we add ANOTHER LoggingHandler here, each log would be sent to App Insights TWICE.
    #
    # Solution: Do NOT add LoggingHandler to individual loggers.
    # Only add filters (for enrichment/filtering) and StreamHandler (for console).
    # ═══════════════════════════════════════════════════════════════════════════

    # Add trace filter if not already present (enriches logs with correlation IDs)
    has_trace_filter = any(isinstance(f, TraceLogFilter) for f in logger.filters)
    if not has_trace_filter:
        logger.addFilter(TraceLogFilter())

    # Add WebSocket noise filter if not already present
    has_noise_filter = any(isinstance(f, WebSocketNoiseFilter) for f in logger.filters)
    if not has_noise_filter:
        logger.addFilter(WebSocketNoiseFilter())

    # Add StreamHandler for console output (not for Azure Monitor)
    if include_stream_handler and not any(
        isinstance(h, logging.StreamHandler) for h in logger.handlers
    ):
        sh = logging.StreamHandler()
        sh.setFormatter(JsonFormatter() if is_production else PrettyFormatter())
        sh.addFilter(TraceLogFilter())
        sh.addFilter(WebSocketNoiseFilter())
        logger.addHandler(sh)

    return logger


def log_function_call(
    logger_name: str, log_inputs: bool = False, log_output: bool = False
) -> Callable:
    def decorator_log_function_call(func):
        @functools.wraps(func)
        def wrapper_log_function_call(*args, **kwargs):
            if not _telemetry_disabled and trace is not None:
                from opentelemetry.trace import get_current_span

                span = get_current_span()
                if span and span.is_recording():
                    # These values must be passed via kwargs or resolved from context/session manager
                    session_id = kwargs.get("session_id", "-")
                    call_connection_id = kwargs.get("call_connection_id", "-")

                    span.set_attribute("ai.session.id", call_connection_id)
                    span.set_attribute("ai.user.id", session_id)

            logger = get_logger(logger_name)
            func_name = func.__name__

            if log_inputs:
                args_str = ", ".join(map(str, args))
                kwargs_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
                logger.info(
                    f"Function {func_name} called with arguments: {args_str} and keyword arguments: {kwargs_str}"
                )
            else:
                logger.info(f"Function {func_name} called")

            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            if log_output:
                logger.info(f"Function {func_name} output: {result}")

            logger.info(
                json.dumps(
                    {
                        "event": "execution_duration",
                        "function": func_name,
                        "duration_seconds": round(duration, 2),
                    }
                )
            )
            logger.info(f"Function {func_name} completed")

            return result

        return wrapper_log_function_call

    return decorator_log_function_call
