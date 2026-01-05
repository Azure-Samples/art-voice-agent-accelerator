"""
services/openai_client.py
-------------------------
Single shared Azure OpenAI client.  Import `client` anywhere you need
to talk to the Chat Completion API; it will be created once at
import-time with proper JWT token handling for APIM policy evaluation.
"""

import argparse
import json
import os
import sys

from azure.identity import (
    DefaultAzureCredential,
    ManagedIdentityCredential,
    get_bearer_token_provider,
)
from dotenv import load_dotenv
from openai import AzureOpenAI
from utils.azure_auth import get_credential
from utils.ml_logging import logging

logger = logging.getLogger(__name__)
load_dotenv()


def create_azure_openai_client(
    *,
    azure_endpoint: str | None = None,
    azure_api_key: str | None = None,
    azure_client_id: str | None = None,
    credential: DefaultAzureCredential | ManagedIdentityCredential | None = None,
    api_version: str = "2025-01-01-preview",
):
    """
    Create and configure Azure OpenAI client with optional overrides for configuration.

    Parameters default to environment variables when not provided.
    """
    azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_api_key = azure_api_key or os.getenv("AZURE_OPENAI_KEY")
    azure_client_id = azure_client_id or os.getenv("AZURE_CLIENT_ID")

    if not azure_endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT must be provided via argument or environment.")

    if azure_api_key:
        logger.info("Using API key authentication for Azure OpenAI")
        return AzureOpenAI(
            api_version=api_version,
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
        )

    logger.info("Using Azure AD authentication for Azure OpenAI")

    resolved_credential = credential
    if not resolved_credential:
        if azure_client_id:
            logger.info("Using user-assigned managed identity with client ID: %s", azure_client_id)
            resolved_credential = ManagedIdentityCredential(client_id=azure_client_id)
        else:
            logger.info("Using DefaultAzureCredential for Azure OpenAI authentication")
            resolved_credential = get_credential()

    try:
        azure_ad_token_provider = get_bearer_token_provider(
            resolved_credential, "https://cognitiveservices.azure.com/.default"
        )
        client = AzureOpenAI(
            api_version=api_version,
            azure_endpoint=azure_endpoint,
            azure_ad_token_provider=azure_ad_token_provider,
        )
        logger.info("Azure OpenAI client created successfully with Azure AD authentication")
        return client
    except Exception as exc:
        logger.error("Failed to create Azure OpenAI client with Azure AD: %s", exc)
        logger.info("Falling back to DefaultAzureCredential")
        fallback_credential = get_credential()
        azure_ad_token_provider = get_bearer_token_provider(
            fallback_credential, "https://cognitiveservices.azure.com/.default"
        )
        return AzureOpenAI(
            api_version=api_version,
            azure_endpoint=azure_endpoint,
            azure_ad_token_provider=azure_ad_token_provider,
        )


def main() -> None:
    """
    Execute a synchronous smoke test to confirm Azure OpenAI access and optionally run a prompt.

    Inputs:
        Optional CLI --prompt for test content and --deployment override.

    Outputs:
        Logs discovered deployments or prompt response; writes prompt response to stdout.

    Latency:
        Bounded by one control-plane list request or a single prompt inference round trip.
    """

    parser = argparse.ArgumentParser(description="Azure OpenAI client smoke test utility.")
    parser.add_argument(
        "--prompt",
        type=str,
        help="Optional prompt to send to the Azure OpenAI deployment for validation.",
    )
    parser.add_argument(
        "--deployment",
        type=str,
        default=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        help="Azure OpenAI deployment name; defaults to AZURE_OPENAI_DEPLOYMENT.",
    )
    args = parser.parse_args()

    local_client = create_azure_openai_client()
    if not args.prompt:
        try:
            response = local_client.models.list()
            deployments = [model.id for model in getattr(response, "data", [])]
            logger.info("Azure OpenAI deployments discovered", extra={"deployments": deployments})
        except Exception as exc:
            logger.error("Azure OpenAI smoke test failed", extra={"error": str(exc)})
            raise
        return

    if not args.deployment:
        raise ValueError(
            "A deployment name must be supplied via --deployment or AZURE_OPENAI_DEPLOYMENT."
        )

    try:
        response = local_client.responses.create(
            model=args.deployment,
            input=args.prompt,
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            output_segments = []
            for item in getattr(response, "output", []):
                for segment in getattr(item, "content", []):
                    text = getattr(segment, "text", None)
                    if text:
                        output_segments.append(text)
            output_text = " ".join(output_segments)
        logger.info(
            "Azure OpenAI prompt test succeeded",
            extra={"deployment": args.deployment, "response": output_text},
        )
        print(output_text or json.dumps(response.model_dump(), default=str), file=sys.stdout)
    except Exception as exc:
        logger.error(
            "Azure OpenAI prompt test failed",
            extra={"deployment": args.deployment, "error": str(exc)},
        )
        raise


# Lazy client initialization to allow OpenTelemetry instrumentation to be set up first.
# The instrumentor must monkey-patch the openai module BEFORE any clients are created.
_client_instance = None


def get_client():
    """
    Get the shared Azure OpenAI client (lazy initialization).

    This function creates the client on first access, allowing telemetry
    instrumentation to be configured before the openai module is patched.

    Returns:
        AzureOpenAI: Configured Azure OpenAI client instance.

    Raises:
        ValueError: If AZURE_OPENAI_ENDPOINT is not configured.
    """
    global _client_instance
    if _client_instance is None:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        if not endpoint:
            # Log all env vars that start with AZURE_ for debugging
            azure_vars = {
                k: v[:50] + "..." if len(v) > 50 else v
                for k, v in os.environ.items()
                if k.startswith("AZURE_")
            }
            logger.error("AZURE_OPENAI_ENDPOINT not available. Azure env vars: %s", azure_vars)
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT must be provided via environment variable. "
                "Ensure Azure App Configuration has loaded or set the variable directly."
            )
        _client_instance = create_azure_openai_client()
    return _client_instance


# For backwards compatibility, provide 'client' as a property-like access
# Note: Direct access to 'client' will create the client immediately.
# Prefer using get_client() in new code.
client = None  # Will be set on first import of this module in app startup


def _init_client():
    """
    Initialize the client. Called after telemetry setup.

    This function is resilient - if AZURE_OPENAI_ENDPOINT is not yet available
    (e.g., App Configuration hasn't loaded), it will skip initialization.
    The client will be created lazily on first use via get_client().
    """
    global client
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    if not endpoint:
        logger.warning(
            "AZURE_OPENAI_ENDPOINT not set during _init_client(); "
            "client will be initialized lazily on first use"
        )
        return
    client = get_client()


async def warm_openai_connection(
    deployment: str | None = None,
    timeout_sec: float = 10.0,
) -> bool:
    """
    Warm the OpenAI connection with a minimal request.

    Establishes HTTP/2 connection and token acquisition before first real request,
    eliminating 200-500ms cold-start latency on first LLM call.

    Args:
        deployment: Azure OpenAI deployment name. Defaults to AZURE_OPENAI_DEPLOYMENT.
        timeout_sec: Maximum time to wait for warmup request.

    Returns:
        True if warmup succeeded, False otherwise.

    Latency:
        Expected ~300-500ms for first connection, near-instant on subsequent calls.
    """
    import asyncio

    deployment = (
        deployment
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_ID")
    )
    if not deployment:
        logger.warning("OpenAI warmup skipped: no deployment configured")
        return False

    aoai_client = get_client()

    try:
        # Use a tiny prompt that exercises the connection with minimal tokens
        response = await asyncio.wait_for(
            asyncio.to_thread(
                aoai_client.chat.completions.create,
                model=deployment,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                temperature=0,
            ),
            timeout=timeout_sec,
        )
        logger.info(
            "OpenAI connection warmed successfully",
            extra={"deployment": deployment, "tokens_used": 1},
        )
        return True
    except TimeoutError:
        logger.warning(
            "OpenAI warmup timed out after %.1fs",
            timeout_sec,
            extra={"deployment": deployment},
        )
        return False
    except Exception as e:
        logger.warning(
            "OpenAI warmup failed (non-blocking): %s",
            str(e),
            extra={"deployment": deployment, "error_type": type(e).__name__},
        )
        return False


def test_responses_endpoint(deployment: str, prompt: str = "test") -> bool:
    """
    Test if the /responses endpoint is available for a deployment.

    This function attempts to call the /responses endpoint with a minimal
    prompt to verify availability. Useful for checking if a model supports
    the new responses API before attempting to use it.

    Args:
        deployment: Azure OpenAI deployment name to test
        prompt: Test prompt to send (default: "test")

    Returns:
        True if /responses endpoint is available and working, False otherwise

    Example:
        >>> if test_responses_endpoint("gpt-4o"):
        ...     logger.info("Responses endpoint available")
        ... else:
        ...     logger.warning("Falling back to chat completions")
    """
    try:
        aoai_client = get_client()
        response = aoai_client.responses.create(
            model=deployment,
            input=prompt,
        )
        logger.info(
            "Responses endpoint test succeeded",
            extra={"deployment": deployment, "response_id": getattr(response, "id", "unknown")},
        )
        return True
    except AttributeError as e:
        # responses.create doesn't exist in this SDK version
        logger.warning(
            "Responses endpoint not available (SDK AttributeError)",
            extra={"deployment": deployment, "error": str(e)},
        )
        return False
    except Exception as e:
        logger.warning(
            "Responses endpoint test failed",
            extra={"deployment": deployment, "error_type": type(e).__name__, "error": str(e)},
        )
        return False


__all__ = [
    "client",
    "get_client",
    "create_azure_openai_client",
    "_init_client",
    "warm_openai_connection",
    "test_responses_endpoint",
]
