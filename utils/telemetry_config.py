# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License in the project root for
# license information.
# --------------------------------------------------------------------------
import logging
import os

# Ensure environment variables from .env are available BEFORE we check DISABLE_CLOUD_TELEMETRY.
try:  # minimal, silent if python-dotenv missing
    from dotenv import load_dotenv  # type: ignore

    # Only load if it looks like a .env file exists and variables not already present
    if os.path.isfile(".env"):
        load_dotenv(override=False)
except Exception:
    pass

from azure.core.exceptions import HttpResponseError
from utils.azure_auth import get_credential, ManagedIdentityCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.sdk.resources import Resource, ResourceAttributes
from opentelemetry.sdk.trace import TracerProvider

# Set up logger for this module
logger = logging.getLogger(__name__)


# Suppress Azure credential noise early
def suppress_azure_credential_logs():
    """Suppress noisy Azure credential logs that occur during DefaultAzureCredential attempts."""
    azure_loggers = [
        "azure.identity",
        "azure.identity._credentials.managed_identity",
        "azure.identity._credentials.app_service",
        "azure.identity._internal.msal_managed_identity_client",
        "azure.core.pipeline.policies._authentication",
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.monitor.opentelemetry.exporter.export._base",
    ]

    for logger_name in azure_loggers:
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)


# Apply suppression when module is imported
suppress_azure_credential_logs()


def setup_azure_monitor(logger_name: str = None):
    """
    Configure Azure Monitor / Application Insights if connection string is available.
    Implements fallback authentication and graceful degradation for live metrics.

    Args:
        logger_name (str, optional): Name for the Azure Monitor logger. Defaults to environment variable or 'default'.
    """
    # Allow hard opt-out for local dev or debugging.
    if os.getenv("DISABLE_CLOUD_TELEMETRY", "false").lower() == "true":
        logger.info(
            "Telemetry disabled (DISABLE_CLOUD_TELEMETRY=true) – skipping Azure Monitor setup"
        )
        return

    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    logger_name = logger_name or os.getenv("AZURE_MONITOR_LOGGER_NAME", "default")

    # Check if we should disable live metrics due to permission issues
    disable_live_metrics = (
        os.getenv("AZURE_MONITOR_DISABLE_LIVE_METRICS", "false").lower() == "true"
    )
    # Build resource attributes, include environment name if present
    resource_attrs = {
        "service.name": "rtagent-api",
        "service.namespace": "callcenter-app",
    }
    env_name = os.getenv("ENVIRONMENT")
    if env_name:
        resource_attrs["service.environment"] = env_name
    resource = Resource.create(resource_attrs)

    if not connection_string:
        logger.info(
            "ℹ️ APPLICATIONINSIGHTS_CONNECTION_STRING not found, skipping Azure Monitor configuration"
        )
        return

    logger.info(f"Setting up Azure Monitor with logger_name: {logger_name}")
    logger.info(f"Connection string found: {connection_string[:50]}...")
    logger.info(f"Resource attributes: {resource_attrs}")

    try:
        # Try to get appropriate credential
        credential = _get_azure_credential()

        # Configure with live metrics initially disabled if environment variable is set
        # or if we're in a development environment
        enable_live_metrics = not disable_live_metrics
        # enable_live_metrics = not disable_live_metrics and _should_enable_live_metrics()
        logger.info(
            f"Configuring Azure Monitor with live metrics: {enable_live_metrics}"
        )

        logger.info(
            f"Configuring Azure Monitor with live metrics: {enable_live_metrics}"
        )

        resource = Resource(attributes=resource_attrs)
        tracer_provider = TracerProvider(resource=resource)
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
            logging_formatter=None,  # Explicitly set logging_formatter to None or provide a custom formatter if needed
            instrumentation_options={
                "azure_sdk": {"enabled": True},
                "redis": {"enabled": True},
                "aiohttp": {"enabled": True},
                "fastapi": {"enabled": True},
                "flask": {"enabled": True},
                "requests": {"enabled": True},
                "urllib3": {"enabled": True},
                "psycopg2": {"enabled": False},  # Disable psycopg2 since we use MongoDB
                "django": {"enabled": False},  # Disable django since we use FastAPI
            },
        )

        status_msg = "✅ Azure Monitor configured successfully"
        if not enable_live_metrics:
            status_msg += " (live metrics disabled)"
        logger.info(status_msg)

        # Test the configuration by creating a test trace
        from opentelemetry import trace

        tracer = trace.get_tracer("azure_monitor_setup_test")
        with tracer.start_as_current_span("azure_monitor_configuration_test") as span:
            span.set_attributes(
                {
                    "setup.success": True,
                    "setup.logger_name": logger_name,
                    "setup.live_metrics_enabled": enable_live_metrics,
                }
            )
            logger.info("🧪 Azure Monitor configuration test trace created")

    except ImportError:
        logger.warning(
            "⚠️ Azure Monitor OpenTelemetry not available. Install azure-monitor-opentelemetry package."
        )
    except HttpResponseError as e:
        if "Forbidden" in str(e) or "permissions" in str(e).lower():
            logger.warning(
                "⚠️ Insufficient permissions for Application Insights. Retrying with live metrics disabled..."
            )
            _retry_without_live_metrics(logger_name, connection_string)
        else:
            logger.error(f"⚠️ HTTP error configuring Azure Monitor: {e}")
    except Exception as e:
        logger.error(f"⚠️ Failed to configure Azure Monitor: {e}")
        import traceback

        logger.error(f"⚠️ Full traceback: {traceback.format_exc()}")


def _get_azure_credential():
    """
    Get the appropriate Azure credential based on the environment.
    Prioritizes managed identity in Azure-hosted environments.
    """
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


def _should_enable_live_metrics():
    """
    Determine if live metrics should be enabled based on environment.
    """
    # Disable in development environments by default
    if os.getenv("ENVIRONMENT", "").lower() in ["dev", "development", "local"]:
        return False

    # Enable in production environments
    if os.getenv("ENVIRONMENT", "").lower() in ["prod", "production"]:
        return True

    # For other environments, check if we're in Azure
    return bool(os.getenv("WEBSITE_SITE_NAME") or os.getenv("CONTAINER_APP_NAME"))


def _retry_without_live_metrics(logger_name: str, connection_string: str):
    """
    Retry Azure Monitor configuration without live metrics if permission errors occur.
    """
    try:
        credential = _get_azure_credential()

        configure_azure_monitor(
            logger_name=logger_name,
            credential=credential,
            connection_string=connection_string,
            enable_live_metrics=False,  # Disable live metrics
            disable_logging=False,
            disable_tracing=False,
            disable_metrics=False,
            instrumentation_options={
                "azure_sdk": {"enabled": True},
                "aiohttp": {"enabled": True},
                "fastapi": {"enabled": True},
                "flask": {"enabled": True},
                "requests": {"enabled": True},
                "urllib3": {"enabled": True},
                "psycopg2": {"enabled": False},  # Disable psycopg2 since we use MongoDB
                "django": {"enabled": False},  # Disable django since we use FastAPI
            },
        )
        logger.info(
            "✅ Azure Monitor configured successfully (live metrics disabled due to permissions)"
        )

    except Exception as e:
        logger.error(
            f"⚠️ Failed to configure Azure Monitor even without live metrics: {e}"
        )
