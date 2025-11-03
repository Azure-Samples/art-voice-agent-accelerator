"""
Backup Azure OpenAI client for CI environments.

This is a fallback implementation that provides the essential client functionality
when the main src.aoai.client module cannot be imported due to path resolution
issues in CI environments.
"""

import os
import logging
from typing import Optional

try:
    from openai import AzureOpenAI
    from azure.identity import DefaultAzureCredential
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AzureOpenAI = None
    DefaultAzureCredential = None

logger = logging.getLogger(__name__)

def create_fallback_azure_openai_client() -> Optional['AzureOpenAI']:
    """Create a fallback Azure OpenAI client for CI environments."""
    if not OPENAI_AVAILABLE:
        logger.warning("OpenAI and Azure Identity packages not available")
        return None
    
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    
    if not endpoint:
        logger.warning("AZURE_OPENAI_ENDPOINT not set, creating minimal client")
        return None
    
    try:
        if api_key:
            # Use API key authentication
            client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version="2024-02-01"
            )
            logger.info("Fallback Azure OpenAI client created with API key authentication")
        else:
            # Use Azure AD authentication
            credential = DefaultAzureCredential()
            client = AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token,
                api_version="2024-02-01"
            )
            logger.info("Fallback Azure OpenAI client created with Azure AD authentication")
        
        return client
    except Exception as e:
        logger.error(f"Failed to create fallback Azure OpenAI client: {e}")
        return None

# Create the fallback client instance
fallback_client = create_fallback_azure_openai_client()

__all__ = ["fallback_client", "create_fallback_azure_openai_client"]