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
from config import (
    AZURE_CLIENT_ID,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
)
from utils.ml_logging import logging
from utils.azure_auth import get_credential

logger = logging.getLogger(__name__)

#TODO: Consolidate this service wrapper to reference the module already defined in src/aoai
def create_azure_openai_client():
    """
    Create and configure Azure OpenAI client with appropriate authentication method.

    This function establishes an authenticated connection to Azure OpenAI services,
    supporting both API key authentication for development environments and
    managed identity authentication for production deployments. The client is
    configured with the latest API version for optimal feature compatibility.

    :return: Configured AzureOpenAI client instance ready for conversational AI operations.
    :raises ValueError: If neither API key nor managed identity authentication can be established.
    """

    # Use API key if provided (for development/testing)
    if AZURE_OPENAI_KEY:
        logger.info("Using API key authentication for Azure OpenAI")
        return AzureOpenAI(
            api_version="2025-01-01-preview",
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
        )

    # Use managed identity or service principal for production
    logger.info("Using Azure AD authentication for Azure OpenAI")

    try:
        # Try to use managed identity first (preferred for Azure deployments)
        client_id = AZURE_CLIENT_ID or os.getenv("AZURE_CLIENT_ID")

        if client_id:
            # Use user-assigned managed identity if client ID is provided
            logger.info(
                f"Using user-assigned managed identity with client ID: {client_id}"
            )
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            # Use system-assigned managed identity or get_credential() chain
            logger.info("Using DefaultAzureCredential for Azure OpenAI authentication")
            credential = get_credential()

        azure_ad_token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )

        client = AzureOpenAI(
            api_version="2025-01-01-preview",
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_ad_token_provider=azure_ad_token_provider,
        )

        logger.info(
            "Azure OpenAI client created successfully with Azure AD authentication"
        )
        return client

    except Exception as e:
        logger.error(f"Failed to create Azure OpenAI client with Azure AD: {e}")
        logger.info("Falling back to DefaultAzureCredential")

        # Fallback to basic DefaultAzureCredential
        credential = get_credential()
        azure_ad_token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )

        return AzureOpenAI(
            api_version="2025-01-01-preview",
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_ad_token_provider=azure_ad_token_provider,
        )


client = create_azure_openai_client()

__all__ = ["client", "create_azure_openai_client"]
