"""
services/openai_client.py
-------------------------
Shared Azure OpenAI client accessor. Uses lazy initialization to allow
OpenTelemetry instrumentation to be configured before the client is created.
"""

from src.aoai.client import get_client


# For backwards compatibility, provide AzureOpenAIClient as a callable
# that returns the lazily-initialized client
def AzureOpenAIClient():
    """Get the shared Azure OpenAI client (lazy initialization)."""
    return get_client()


__all__ = ["AzureOpenAIClient", "get_client"]
