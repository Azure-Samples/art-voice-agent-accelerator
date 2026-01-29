"""
Decline Code Tools
==================

Tools for querying card decline codes via the MCP server.
Connects to the Card Decline Code MCP service for policy pack information.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.decline_codes")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

lookup_decline_code_schema: dict[str, Any] = {
    "name": "lookup_decline_code",
    "description": (
        "Look up a specific card decline code to get its description, detailed information, "
        "recommended actions, customer service scripts, orchestrator actions, contextual rules, "
        "and escalation requirements. Use this when you know the exact decline code."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The decline code to look up (e.g., '02', '51', 'C1', 'RT')",
            }
        },
        "required": ["code"],
    },
}

search_decline_codes_schema: dict[str, Any] = {
    "name": "search_decline_codes",
    "description": (
        "Search for decline codes by description, information, or action keywords. "
        "Returns complete policy pack data including scripts, orchestrator actions, and escalation info. "
        "Use this when you need to find codes related to a specific issue or symptom."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g., 'insufficient funds', 'expired', 'PIN')",
            },
            "code_type": {
                "type": "string",
                "enum": ["numeric", "alphanumeric"],
                "description": "Optional: Filter by 'numeric' (Base24) or 'alphanumeric' (FAST)",
            },
        },
        "required": ["query"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# MCP server endpoint - loaded from App Configuration (set during postprovision)
# Defaults to localhost for local development
def get_mcp_server_url() -> str:
    """Get the cardapi MCP server URL from app config or environment.
    
    Priority:
    1. CARDAPI_MCP_URL environment variable (set by app config loading)
    2. Localhost default (for local development)
    """
    url = os.getenv("CARDAPI_MCP_URL")
    if url:
        return url
    return "http://localhost:8001"


MCP_SERVER_URL = get_mcp_server_url()
MCP_REQUEST_TIMEOUT = 10.0  # seconds


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def lookup_decline_code(args: dict[str, Any]) -> dict[str, Any]:
    """Look up a specific decline code via MCP server."""
    code = (args.get("code") or "").strip()

    if not code:
        return {
            "success": False,
            "message": "Decline code is required.",
        }

    try:
        logger.info("Looking up decline code: %s", code)
        
        async with httpx.AsyncClient(timeout=MCP_REQUEST_TIMEOUT) as client:
            # Call MCP server endpoint for decline code lookup
            response = await client.get(
                f"{MCP_SERVER_URL}/tools/lookup_decline_code",
                params={"code": code},
            )
            response.raise_for_status()
            
            data = response.json()
            logger.debug("Successfully retrieved decline code data: %s", code)
            
            return {
                "success": True,
                "code": code,
                "result": data,
            }

    except httpx.HTTPStatusError as e:
        error_msg = f"Decline code lookup failed: {e.status_code} {e.response.text}"
        logger.warning(error_msg)
        return {
            "success": False,
            "message": f"Decline code '{code}' not found or lookup failed.",
            "error": str(e),
        }
    except httpx.ConnectError:
        error_msg = f"Could not connect to MCP server at {MCP_SERVER_URL}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": "Decline code service temporarily unavailable.",
            "error": error_msg,
        }
    except Exception as e:
        logger.exception("Error looking up decline code: %s", code)
        return {
            "success": False,
            "message": "Error retrieving decline code information.",
            "error": str(e),
        }


async def search_decline_codes(args: dict[str, Any]) -> dict[str, Any]:
    """Search for decline codes matching query keywords."""
    query = (args.get("query") or "").strip()
    code_type = (args.get("code_type") or "").strip() or None

    if not query:
        return {
            "success": False,
            "message": "Search query is required.",
        }

    try:
        logger.info("Searching decline codes: query=%s, type=%s", query, code_type)
        
        params = {"query": query}
        if code_type:
            params["code_type"] = code_type
        
        async with httpx.AsyncClient(timeout=MCP_REQUEST_TIMEOUT) as client:
            response = await client.get(
                f"{MCP_SERVER_URL}/tools/search_decline_codes",
                params=params,
            )
            response.raise_for_status()
            
            data = response.json()
            logger.debug("Successfully searched decline codes with query: %s", query)
            
            return {
                "success": True,
                "query": query,
                "code_type": code_type,
                "results": data.get("results", []),
                "count": len(data.get("results", [])),
            }

    except httpx.HTTPStatusError as e:
        error_msg = f"Decline code search failed: {e.status_code} {e.response.text}"
        logger.warning(error_msg)
        return {
            "success": False,
            "message": "Search for decline codes failed.",
            "error": str(e),
        }
    except httpx.ConnectError:
        error_msg = f"Could not connect to MCP server at {MCP_SERVER_URL}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": "Decline code service temporarily unavailable.",
            "error": error_msg,
        }
    except Exception as e:
        logger.exception("Error searching decline codes: %s", query)
        return {
            "success": False,
            "message": "Error searching decline codes.",
            "error": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "lookup_decline_code",
    lookup_decline_code_schema,
    lookup_decline_code,
    tags={"banking", "decline-codes", "cardapi"},
)

register_tool(
    "search_decline_codes",
    search_decline_codes_schema,
    search_decline_codes,
    tags={"banking", "decline-codes", "cardapi", "search"},
)
