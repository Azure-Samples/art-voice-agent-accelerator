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
# Use multiple import strategies to handle different environments
import sys
import os

# Strategy 1: Try direct import (works in most cases)
try:
    from src.aoai.client import client as AzureOpenAIClient
    _import_source = "src.aoai.client"
except ImportError:
    # Strategy 2: Add project root to path and retry
    try:
        # Calculate project root from current file location
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '../../../../../'))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from src.aoai.client import client as AzureOpenAIClient
        _import_source = "src.aoai.client (with path fix)"
    except ImportError:
        # Strategy 3: Try with working directory as base
        try:
            cwd = os.getcwd()
            if cwd not in sys.path:
                sys.path.insert(0, cwd)
            from src.aoai.client import client as AzureOpenAIClient
            _import_source = "src.aoai.client (with cwd)"
        except ImportError:
            # Strategy 4: For CI environments, try relative to repo root
            try:
                # Look for common CI paths
                possible_roots = [
                    '/home/runner/work/art-voice-agent-accelerator/art-voice-agent-accelerator',
                    os.path.abspath(os.path.join(current_dir, '../../../../../../')),
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))))
                ]
                for root in possible_roots:
                    if os.path.exists(root) and root not in sys.path:
                        sys.path.insert(0, root)
                        try:
                            from src.aoai.client import client as AzureOpenAIClient
                            _import_source = f"src.aoai.client (from {root})"
                            break
                        except ImportError:
                            continue
                else:
                    raise ImportError("Could not import AzureOpenAI client from any location")
            except ImportError:
                # Final fallback: Use the local backup client
                try:
                    from .azure_openai_client import fallback_client as AzureOpenAIClient
                    _import_source = "fallback client"
                    print(f"Using fallback Azure OpenAI client")
                except ImportError as e:
                    # Absolute final fallback: Create a dummy client
                    print(f"Warning: Could not import Azure OpenAI client from any source: {e}")
                    print(f"Current working directory: {os.getcwd()}")
                    print(f"Python path: {sys.path}")
                    print(f"Current file location: {__file__}")
                    AzureOpenAIClient = None
                    _import_source = "none (failed)"

# Log which import source was used for debugging
if AzureOpenAIClient is not None:
    print(f"Azure OpenAI client imported from: {_import_source}")

__all__ = ["AzureOpenAIClient"]
