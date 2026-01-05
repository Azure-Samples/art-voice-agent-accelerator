# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License in the project root for
# license information.
# --------------------------------------------------------------------------
"""
Azure Monitor / Application Insights telemetry configuration.

This module provides a simplified, maintainable setup for OpenTelemetry with Azure Monitor.

Configuration via environment variables:
- APPLICATIONINSIGHTS_CONNECTION_STRING: Required for Azure Monitor export
- DISABLE_CLOUD_TELEMETRY: Set to "true" to disable all cloud telemetry
- AZURE_MONITOR_DISABLE_LIVE_METRICS: Disable live metrics stream (auto-disabled for local dev)
- TELEMETRY_PII_SCRUBBING_ENABLED: Enable PII scrubbing (default: true)

See utils/pii_filter.py for PII scrubbing configuration options.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import uuid
import warnings
from re import Pattern

# Suppress OpenTelemetry deprecation warnings
warnings.filterwarnings(
    "ignore", message="LogRecord init with.*is deprecated", module="opentelemetry"
)

# Load .env early
try:
    from dotenv import load_dotenv

    if os.path.isfile(".env"):
        load_dotenv(override=False)
except Exception:
    pass

logger = logging.getLogger("utils.telemetry_config")


# ═══════════════════════════════════════════════════════════════════════════════
# NOISY LOGGER SUPPRESSION
# ═══════════════════════════════════════════════════════════════════════════════

# Loggers to suppress (set to WARNING or CRITICAL level)
NOISY_LOGGERS = [
    "azure.identity",
    "azure.identity._credentials.managed_identity",
    "azure.identity._credentials.app_service",
    "azure.identity._internal.msal_managed_identity_client",
    "azure.core.pipeline.policies._authentication",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.core.pipeline",
    "azure.monitor.opentelemetry.exporter",
    "azure.monitor.opentelemetry.exporter._quickpulse",
    "azure.monitor.opentelemetry.exporter.export._base",
    "azure.core.exceptions",
    "websockets",
    "aiohttp",
    "httpx",
    "httpcore",
    "uvicorn.protocols.websockets",
    "uvicorn.error",
    "uvicorn.access",
    "starlette.routing",
    "fastapi",
    "opentelemetry.sdk.trace",
    "opentelemetry.exporter",
    "redis.asyncio.connection",
]


def _suppress_noisy_loggers(level: int = logging.WARNING) -> None:
    """Set noisy loggers to specified level to reduce noise."""
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(level)


def suppress_azure_credential_logs() -> None:
    """Suppress noisy Azure credential logs that occur during DefaultAzureCredential attempts."""
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.CRITICAL)


# Apply suppression when module is imported
suppress_azure_credential_logs()


# ═══════════════════════════════════════════════════════════════════════════════
# SPAN FILTERING
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns for noisy spans to drop
NOISY_SPAN_PATTERNS: list[Pattern[str]] = [
    re.compile(r".*websocket\s*(receive|send).*", re.IGNORECASE),
    re.compile(r".*ws[._](receive|send).*", re.IGNORECASE),
    re.compile(r"HTTP.*websocket.*", re.IGNORECASE),
    re.compile(r"^(GET|POST)\s+.*(websocket|/ws/).*", re.IGNORECASE),
    re.compile(r".*audio[._](chunk|frame).*", re.IGNORECASE),
    re.compile(r".*(process|stream|emit)[._](frame|chunk).*", re.IGNORECASE),
    re.compile(r".*redis[._](ping|pool|connection).*", re.IGNORECASE),
    re.compile(r".*(poll|heartbeat)[._]session.*", re.IGNORECASE),
    # VoiceLive high-frequency streaming events
    re.compile(r"voicelive\.event\.response\.audio\.delta", re.IGNORECASE),
    re.compile(r"voicelive\.event\.response\.audio_transcript\.delta", re.IGNORECASE),
    re.compile(r"voicelive\.event\.response\.function_call_arguments\.delta", re.IGNORECASE),
    re.compile(r"voicelive\.event\.response\.text\.delta", re.IGNORECASE),
    re.compile(r"voicelive\.event\.response\.content_part\.delta", re.IGNORECASE),
    re.compile(r"voicelive\.event\.input_audio_buffer\.", re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════════════════════════
# SPAN PROCESSOR WITH FILTERING AND PII SCRUBBING
# ═══════════════════════════════════════════════════════════════════════════════

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor


class FilteringSpanProcessor(SpanProcessor):
    """
    SpanProcessor that filters noisy spans and scrubs PII from attributes.

    Combines noise filtering and PII scrubbing in a single processor
    for better performance and simpler configuration.
    """

    def __init__(self, next_processor: SpanProcessor, enable_pii_scrubbing: bool = True):
        self._next = next_processor
        self._enable_pii_scrubbing = enable_pii_scrubbing
        self._pii_scrubber = None

        if enable_pii_scrubbing:
            try:
                from utils.pii_filter import get_pii_scrubber

                self._pii_scrubber = get_pii_scrubber()
            except ImportError:
                logger.debug("PII scrubber not available")

    def on_start(self, span, parent_context=None) -> None:
        self._next.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        # Filter noisy spans
        for pattern in NOISY_SPAN_PATTERNS:
            if pattern.match(span.name):
                return  # Drop span

        # PII scrubbing is handled at attribute level during span creation
        # and in the log exporter filter - we pass through here
        self._next.on_end(span)

    def shutdown(self) -> None:
        self._next.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._next.force_flush(timeout_millis)


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _get_instance_id() -> str:
    """Generate unique instance ID for Application Map visualization."""
    # Azure App Service
    if instance_id := os.getenv("WEBSITE_INSTANCE_ID"):
        return instance_id[:8]
    # Container Apps
    if replica := os.getenv("CONTAINER_APP_REPLICA_NAME"):
        return replica
    # Kubernetes
    if pod := os.getenv("HOSTNAME"):
        if "-" in pod:
            return pod
    # Fallback
    try:
        return socket.gethostname()
    except Exception:
        return str(uuid.uuid4())[:8]


def _get_azure_credential():
    """
    Get the appropriate Azure credential based on the environment.
    Prioritizes managed identity in Azure-hosted environments.
    """
    from utils.azure_auth import ManagedIdentityCredential, get_credential

    try:
        # Try managed identity first if we're in Azure
        if os.getenv("WEBSITE_SITE_NAME") or os.getenv("CONTAINER_APP_NAME"):
            logger.debug("Using ManagedIdentityCredential for Azure-hosted environment")
            return ManagedIdentityCredential()
    except Exception as e:
        logger.debug(f"ManagedIdentityCredential not available: {e}")

    # Fall back to DefaultAzureCredential
    logger.debug("Using DefaultAzureCredential")
    return get_credential()


def _should_enable_live_metrics() -> bool:
    """
    Determine if live metrics should be enabled based on environment.
    """
    # Disable in development environments by default
    env = os.getenv("ENVIRONMENT", "").lower()
    if env in ("dev", "development", "local"):
        return False

    # Enable in production environments
    if env in ("prod", "production"):
        return True

    # For other environments, check if we're in Azure
    return bool(os.getenv("WEBSITE_SITE_NAME") or os.getenv("CONTAINER_APP_NAME"))


def _is_local_dev() -> bool:
    """Check if running in local development mode."""
    from utils.azure_auth import _is_local_dev as _auth_is_local_dev

    return _auth_is_local_dev()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE STATE
# ═══════════════════════════════════════════════════════════════════════════════

_azure_monitor_configured = False
_live_metrics_permanently_disabled = False


def is_azure_monitor_configured() -> bool:
    """Return True if Azure Monitor was configured successfully."""
    return _azure_monitor_configured


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SETUP FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════


def setup_azure_monitor(logger_name: str = None) -> bool:
    """
    Configure Azure Monitor / Application Insights if connection string is available.
    Implements fallback authentication and graceful degradation for live metrics.

    Args:
        logger_name: Name for the Azure Monitor logger. Defaults to environment variable or empty string.

    Returns:
        True if configuration succeeded, False otherwise.
    """
    global _live_metrics_permanently_disabled, _azure_monitor_configured

    from azure.core.exceptions import HttpResponseError, ServiceResponseError
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    # Allow hard opt-out for local dev or debugging
    if os.getenv("DISABLE_CLOUD_TELEMETRY", "false").lower() == "true":
        logger.info(
            "Telemetry disabled (DISABLE_CLOUD_TELEMETRY=true) – skipping Azure Monitor setup"
        )
        return False

    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    logger_name = logger_name or os.getenv("AZURE_MONITOR_LOGGER_NAME", "")

    # Check if we should disable live metrics due to permission issues
    disable_live_metrics_env = (
        os.getenv("AZURE_MONITOR_DISABLE_LIVE_METRICS", "false").lower() == "true"
    )

    # Build resource attributes
    resource_attrs = {
        "service.name": os.getenv("SERVICE_NAME", "artagent-api"),
        "service.namespace": os.getenv("SERVICE_NAMESPACE", "callcenter-app"),
        "service.instance.id": _get_instance_id(),
    }
    env_name = os.getenv("ENVIRONMENT")
    if env_name:
        resource_attrs["service.environment"] = env_name
    service_version = os.getenv("SERVICE_VERSION") or os.getenv("APP_VERSION")
    if service_version:
        resource_attrs["service.version"] = service_version

    if not connection_string:
        logger.info(
            "ℹ️ APPLICATIONINSIGHTS_CONNECTION_STRING not found, skipping Azure Monitor configuration"
        )
        return False

    logger.info(f"Setting up Azure Monitor with logger_name: {logger_name or '(root)'}")
    logger.debug(f"Connection string found: {connection_string[:50]}...")
    logger.debug(f"Resource attributes: {resource_attrs}")

    try:
        # Try to get appropriate credential
        credential = _get_azure_credential()

        # Configure with live metrics initially disabled if environment variable is set
        # or if we're in a development environment
        enable_live_metrics = (
            not disable_live_metrics_env
            and not _live_metrics_permanently_disabled
            and _should_enable_live_metrics()
        )

        logger.info(
            "Configuring Azure Monitor with live metrics: %s (env_disable=%s, permanent_disable=%s)",
            enable_live_metrics,
            disable_live_metrics_env,
            _live_metrics_permanently_disabled,
        )

        resource = Resource(attributes=resource_attrs)
        tracer_provider = TracerProvider(resource=resource)

        # Build instrumentation options
        instrumentation_options = {
            "azure_sdk": {"enabled": True},
            "redis": {"enabled": True},
            "aiohttp": {"enabled": True},
            "fastapi": {"enabled": True},
            "flask": {"enabled": False},
            "requests": {"enabled": True},
            "urllib3": {"enabled": True},
            "psycopg2": {"enabled": False},  # Disable psycopg2 since we use MongoDB
            "django": {"enabled": False},  # Disable django since we use FastAPI
        }

        configure_azure_monitor(
            resource=resource,
            logger_name=logger_name,
            credential=credential,
            connection_string=connection_string,
            enable_live_metrics=enable_live_metrics,
            tracer_provider=tracer_provider,
            disable_logging=False,
            disable_tracing=False,
            disable_metrics=False,
            instrumentation_options=instrumentation_options,
        )

        # Install filtering span processor for noise reduction
        _install_filtering_processor()

        # Install session context span processor for automatic correlation
        _install_session_context_processor()

        status_msg = "✅ Azure Monitor configured successfully"
        if not enable_live_metrics:
            status_msg += " (live metrics disabled)"
        logger.info(status_msg)
        _azure_monitor_configured = True
        return True

    except ImportError:
        logger.warning(
            "⚠️ Azure Monitor OpenTelemetry not available. Install azure-monitor-opentelemetry package."
        )
        return False
    except HttpResponseError as e:
        if "Forbidden" in str(e) or "permissions" in str(e).lower():
            logger.warning(
                "⚠️ Insufficient permissions for Application Insights. Retrying with live metrics disabled..."
            )
            return _retry_without_live_metrics(logger_name, connection_string, resource_attrs)
        else:
            logger.error(f"⚠️ HTTP error configuring Azure Monitor: {e}")
            return False
    except ServiceResponseError as e:
        _disable_live_metrics_permanently(
            "Live metrics ping failed during setup", exc_info=e
        )
        return _retry_without_live_metrics(logger_name, connection_string, resource_attrs)
    except Exception as e:
        logger.error(f"⚠️ Failed to configure Azure Monitor: {e}")
        import traceback

        logger.debug(f"⚠️ Full traceback: {traceback.format_exc()}")
        return False


def _retry_without_live_metrics(
    logger_name: str, connection_string: str, resource_attrs: dict
) -> bool:
    """
    Retry Azure Monitor configuration without live metrics if permission errors occur.
    """
    if not connection_string:
        return False

    global _azure_monitor_configured

    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry.sdk.resources import Resource

    try:
        credential = _get_azure_credential()
        resource = Resource(attributes=resource_attrs)

        configure_azure_monitor(
            resource=resource,
            logger_name=logger_name,
            credential=credential,
            connection_string=connection_string,
            enable_live_metrics=False,  # Disable live metrics
            disable_logging=False,
            disable_tracing=False,
            disable_metrics=False,
            instrumentation_options={
                "azure_sdk": {"enabled": True},
                "redis": {"enabled": True},
                "aiohttp": {"enabled": True},
                "fastapi": {"enabled": True},
                "flask": {"enabled": False},
                "requests": {"enabled": True},
                "urllib3": {"enabled": True},
                "psycopg2": {"enabled": False},
                "django": {"enabled": False},
            },
        )

        # Install filtering span processor
        _install_filtering_processor()

        # Install session context span processor
        _install_session_context_processor()

        logger.info(
            "✅ Azure Monitor configured successfully (live metrics disabled due to permissions)"
        )
        _azure_monitor_configured = True
        return True

    except Exception as e:
        logger.error(
            f"⚠️ Failed to configure Azure Monitor even without live metrics: {e}"
        )
        _azure_monitor_configured = False
        return False


def _disable_live_metrics_permanently(reason: str, exc_info: Exception | None = None):
    """Set a module-level guard and environment flag to stop future QuickPulse attempts."""
    global _live_metrics_permanently_disabled
    if _live_metrics_permanently_disabled:
        return

    _live_metrics_permanently_disabled = True
    os.environ["AZURE_MONITOR_DISABLE_LIVE_METRICS"] = "true"

    if exc_info:
        logger.warning(
            "⚠️ %s. Live metrics disabled for remainder of process.",
            reason,
            exc_info=exc_info,
        )
    else:
        logger.warning(
            "⚠️ %s. Live metrics disabled for remainder of process.", reason
        )


def _install_filtering_processor(enable_pii_scrubbing: bool = True) -> None:
    """Install FilteringSpanProcessor to wrap existing processors."""
    try:
        from opentelemetry import trace as otel_trace

        provider = otel_trace.get_tracer_provider()
        if hasattr(provider, "_active_span_processor"):
            original = provider._active_span_processor
            provider._active_span_processor = FilteringSpanProcessor(original, enable_pii_scrubbing)
            logger.debug("FilteringSpanProcessor installed")
    except Exception as e:
        logger.warning(f"Could not install FilteringSpanProcessor: {e}")


def _install_session_context_processor() -> None:
    """Install SessionContextSpanProcessor for automatic session correlation."""
    try:
        from opentelemetry import trace as otel_trace
        from utils.session_context import SessionContextSpanProcessor

        provider = otel_trace.get_tracer_provider()
        if hasattr(provider, "add_span_processor"):
            provider.add_span_processor(SessionContextSpanProcessor())
            logger.debug("SessionContextSpanProcessor installed for automatic session correlation")
        else:
            logger.warning("TracerProvider does not support add_span_processor")
    except ImportError:
        logger.debug("SessionContextSpanProcessor not available (session_context module not found)")
    except Exception as e:
        logger.warning(f"Could not install SessionContextSpanProcessor: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════════════════


def suppress_noisy_loggers(level: int = logging.WARNING) -> None:
    """Legacy function for backwards compatibility."""
    _suppress_noisy_loggers(level)
