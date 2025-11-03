"""
services/openai_client.py
-------------------------
Single shared Azure OpenAI client.  Import `client` anywhere you need
to talk to the Chat Completion API; it will be created once at
import-time with proper JWT token handling for APIM policy evaluation.
"""

import os

from azure.identity import (
    DefaultAzureCredential,
    ManagedIdentityCredential,
    get_bearer_token_provider,
)
from openai import AzureOpenAI

from utils.ml_logging import logging
from utils.azure_auth import get_credential
from dotenv import load_dotenv
import argparse
import json
import sys

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

client = create_azure_openai_client()

__all__ = ["client", "create_azure_openai_client"]
