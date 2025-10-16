import functools
import json
import logging
import os
import time
from typing import Callable, Optional

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
    from opentelemetry.sdk._logs import LoggingHandler
    from utils.telemetry_config import (
        setup_azure_monitor,
        is_azure_monitor_configured,
    )
else:
    # Mock objects when telemetry is disabled
    trace = None
    LoggingHandler = None
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
    def format(self, record: logging.LogRecord) -> str:
        record.funcName = getattr(record, "func_name_override", record.funcName)
        record.filename = getattr(record, "file_name_override", record.filename)
        record.trace_id = getattr(record, "trace_id", "-")
        record.span_id = getattr(record, "span_id", "-")
        record.session_id = getattr(record, "session_id", "-")
        record.call_connection_id = getattr(record, "call_connection_id", "-")

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
            "message": record.getMessage(),
            "file": record.filename,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add any custom span attributes as additional fields
        for attr_name in dir(record):
            if attr_name.startswith(
                ("call_", "session_", "agent_", "model_", "operation_")
            ):
                log_record[attr_name] = getattr(record, attr_name)

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


class TraceLogFilter(logging.Filter):
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

        span = trace.get_current_span()
        context = span.get_span_context() if span else None
        record.trace_id = (
            f"{context.trace_id:032x}" if context and context.trace_id else "-"
        )
        record.span_id = (
            f"{context.span_id:016x}" if context and context.span_id else "-"
        )

        # Extract span attributes for correlation - these become customDimensions in App Insights
        if span and span.is_recording():
            # Get span attributes that were set via TraceContext or manually
            span_attributes = getattr(span, "_attributes", {})

            # Extract key correlation IDs from span attributes
            record.session_id = span_attributes.get(
                "session.id", span_attributes.get("ai.user.id", "-")
            )
            record.call_connection_id = span_attributes.get(
                "call.connection.id", span_attributes.get("ai.session.id", "-")
            )

            # Add other useful span attributes to the log record for search/filtering
            record.operation_name = span_attributes.get("operation.name", span.name)
            record.component = span_attributes.get("component", "-")

            # Add custom properties that will appear in customDimensions
            for key, value in span_attributes.items():
                if key.startswith(
                    ("call.", "session.", "agent.", "model.", "operation.")
                ):
                    # Sanitize key name for logging
                    log_key = key.replace(".", "_")
                    setattr(record, log_key, value)
        else:
            record.session_id = "-"
            record.call_connection_id = "-"
            record.operation_name = "-"
            record.component = "-"

        return True


def set_span_correlation_attributes(
    call_connection_id: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    operation_name: Optional[str] = None,
    custom_attributes: Optional[dict] = None,
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
        span.set_attribute(
            "ai.session.id", call_connection_id
        )  # Application Insights standard

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
    call_connection_id: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    operation_name: Optional[str] = None,
    custom_attributes: Optional[dict] = None,
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
    level: Optional[int] = None,
    include_stream_handler: bool = True,
) -> logging.Logger:
    logger = logging.getLogger(name)

    if level is not None or logger.level == 0:
        logger.setLevel(level or logging.INFO)

    is_production = os.environ.get("ENV", "dev").lower() == "prod"

    # Ensure Azure Monitor LoggingHandler is attached if not already present
    has_azure_handler = LoggingHandler is not None and any(
        isinstance(h, LoggingHandler) for h in logger.handlers
    )
    should_attach_azure_handler = (
        not has_azure_handler
        and not _telemetry_disabled
        and LoggingHandler is not None
        and is_azure_monitor_configured()
    )

    if should_attach_azure_handler:
        try:
            azure_handler = LoggingHandler(level=logging.INFO)
            logger.addHandler(azure_handler)
            logger.debug(f"Azure Monitor LoggingHandler attached to logger: {name}")
        except Exception as e:
            logger.debug(f"Failed to attach Azure Monitor handler: {e}")

    # Add trace filter if not already present
    has_trace_filter = any(isinstance(f, TraceLogFilter) for f in logger.filters)
    if not has_trace_filter:
        logger.addFilter(TraceLogFilter())

    if include_stream_handler and not any(
        isinstance(h, logging.StreamHandler) for h in logger.handlers
    ):
        if not has_azure_handler:
            logger.debug(
                "OTEL LoggingHandler not attached. Ensure configure_azure_monitor was called."
            )
        sh = logging.StreamHandler()
        sh.setFormatter(JsonFormatter() if is_production else PrettyFormatter())
        sh.addFilter(TraceLogFilter())
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
