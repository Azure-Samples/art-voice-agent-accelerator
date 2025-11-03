"""
services/openai_client.py
-------------------------
Single shared Azure OpenAI client.  Import `client` anywhere you need
to talk to the Chat Completion API; it will be created once at
import-time with proper JWT token handling for APIM policy evaluation.
"""

from src.aoai.client import client as AzureOpenAIClient

__all__ = ["AzureOpenAIClient"]
