"""
services/openai_client.py
-------------------------
Single shared Azure OpenAI client.  Import `client` anywhere you need
to talk to the Chat Completion API; it will be created once at
import-time with proper JWT token handling for APIM policy evaluation.

This module serves as a legacy compatibility layer for the consolidated
client architecture.
"""

# For backward compatibility, we re-export the client instance
# Import using absolute import to avoid path resolution issues
import sys
import os

# Ensure the project root is in the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.aoai.client import client as AzureOpenAIClient

__all__ = ["AzureOpenAIClient"]
