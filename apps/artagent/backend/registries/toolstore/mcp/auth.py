"""
MCP Authentication Module
=========================

Provides token acquisition for EasyAuth-protected MCP servers using
Azure Managed Identity or DefaultAzureCredential.

When MCP servers are protected by Azure Container Apps EasyAuth (Microsoft
Entra ID), the backend must acquire tokens to authenticate requests.

Usage:
    from apps.artagent.backend.registries.toolstore.mcp.auth import (
        get_mcp_auth_token,
        get_mcp_auth_headers,
    )

    # Get token for a specific MCP server's app ID
    token = await get_mcp_auth_token("api://cardapi-mcp-easyauth")
    
    # Or get headers dict directly
    headers = await get_mcp_auth_headers("api://cardapi-mcp-easyauth")
    # Returns: {"Authorization": "Bearer eyJ..."}
"""

from __future__ import annotations

import asyncio
import os
import time
from functools import lru_cache
from typing import Any

from utils.ml_logging import get_logger

logger = get_logger("mcp.auth")

# Token cache: app_id -> (token, expiry_time)
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_CACHE_LOCK = asyncio.Lock()

# Refresh token 5 minutes before expiry
_TOKEN_REFRESH_MARGIN_SEC = 300


def _get_credential():
    """
    Get Azure credential for token acquisition.
    
    Uses ManagedIdentityCredential when AZURE_CLIENT_ID is set (deployed),
    otherwise falls back to DefaultAzureCredential for local development.
    """
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    
    azure_client_id = os.getenv("AZURE_CLIENT_ID")
    
    if azure_client_id:
        logger.debug(f"Using ManagedIdentityCredential with client_id={azure_client_id}")
        return ManagedIdentityCredential(client_id=azure_client_id)
    
    # Local development - use CLI credential
    logger.debug("Using DefaultAzureCredential (local dev mode)")
    return DefaultAzureCredential(
        exclude_managed_identity_credential=True,
        exclude_workload_identity_credential=True,
        exclude_shared_token_cache_credential=True,
        exclude_visual_studio_code_credential=True,
        exclude_powershell_credential=True,
        exclude_interactive_browser_credential=True,
    )


async def get_mcp_auth_token(app_id: str) -> str | None:
    """
    Get an authentication token for an MCP server's Entra ID app.
    
    Acquires a token using Managed Identity (deployed) or Azure CLI (local).
    Tokens are cached and automatically refreshed before expiry.
    
    Args:
        app_id: The Entra ID application ID URI or client ID for the MCP server.
                Typically in format "api://app-name" or a GUID.
                
    Returns:
        Access token string, or None if token acquisition fails.
        
    Example:
        token = await get_mcp_auth_token("api://cardapi-mcp-easyauth")
        # Use token in Authorization header
    """
    if not app_id:
        logger.warning("Cannot acquire token: app_id is empty")
        return None
    
    # Normalize scope (add /.default if not present)
    scope = app_id if app_id.endswith("/.default") else f"{app_id}/.default"
    
    async with _TOKEN_CACHE_LOCK:
        # Check cache
        cached = _TOKEN_CACHE.get(app_id)
        if cached:
            token, expiry = cached
            if time.time() < expiry - _TOKEN_REFRESH_MARGIN_SEC:
                logger.debug(f"Using cached token for {app_id}")
                return token
    
    # Acquire new token
    try:
        credential = _get_credential()
        
        # Run in thread pool since credential.get_token is sync
        loop = asyncio.get_event_loop()
        token_result = await loop.run_in_executor(
            None,
            lambda: credential.get_token(scope)
        )
        
        token = token_result.token
        expiry = token_result.expires_on
        
        # Cache the token
        async with _TOKEN_CACHE_LOCK:
            _TOKEN_CACHE[app_id] = (token, expiry)
        
        logger.info(f"Acquired auth token for MCP server (app_id={app_id[:30]}...)")
        return token
        
    except Exception as e:
        logger.error(f"Failed to acquire token for {app_id}: {e}")
        return None


async def get_mcp_auth_headers(app_id: str) -> dict[str, str]:
    """
    Get authentication headers for an MCP server.
    
    Convenience method that returns a headers dict suitable for httpx requests.
    
    Args:
        app_id: The Entra ID application ID URI or client ID for the MCP server.
        
    Returns:
        Dict with Authorization header, or empty dict if token acquisition fails.
        
    Example:
        headers = await get_mcp_auth_headers("api://cardapi-mcp-easyauth")
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
    """
    token = await get_mcp_auth_token(app_id)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def clear_token_cache(app_id: str | None = None) -> None:
    """
    Clear cached tokens.
    
    Args:
        app_id: Specific app ID to clear, or None to clear all cached tokens.
    """
    global _TOKEN_CACHE
    if app_id:
        _TOKEN_CACHE.pop(app_id, None)
        logger.debug(f"Cleared token cache for {app_id}")
    else:
        _TOKEN_CACHE.clear()
        logger.debug("Cleared all token cache")


async def validate_mcp_auth_config(
    name: str,
    url: str,
    app_id: str,
) -> tuple[bool, str | None]:
    """
    Validate that MCP auth is properly configured and token can be acquired.
    
    Args:
        name: MCP server name (for logging)
        url: MCP server URL
        app_id: Entra ID app ID for the server
        
    Returns:
        Tuple of (success, error_message)
    """
    if not app_id:
        return False, "app_id is required for authenticated MCP servers"
    
    try:
        token = await get_mcp_auth_token(app_id)
        if token:
            logger.info(f"MCP auth validation successful for '{name}'")
            return True, None
        else:
            return False, "Failed to acquire token (unknown error)"
    except Exception as e:
        return False, f"Token acquisition failed: {e}"
