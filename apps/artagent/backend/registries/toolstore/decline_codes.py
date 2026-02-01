"""
Decline Code Tools
==================

Tools for querying card decline codes via the MCP server.
Connects to the Card Decline Code MCP service for policy pack information.

These tools use the MCP server's tool endpoints (not the raw CardAPI backend)
to leverage MCP's standardized tool interface and formatted responses.
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


def get_mcp_server_url() -> str:
    """Get the CardAPI MCP server URL from app config or environment.

    Priority:
    1. MCP_SERVER_CARDAPI_URL environment variable (set by app config loading)
    2. CARDAPI_MCP_URL environment variable (alternative)
    3. Localhost default (for local development - matches launch.json MCP Server config)
    """
    url = os.getenv("MCP_SERVER_CARDAPI_URL") or os.getenv("CARDAPI_MCP_URL")
    if url:
        return url.rstrip("/")
    return "http://localhost:8080"


MCP_SERVER_URL = get_mcp_server_url()
MCP_REQUEST_TIMEOUT = 30.0  # seconds (MCP calls may take longer than direct API)


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS (via MCP Server Tool Endpoints)
# ═══════════════════════════════════════════════════════════════════════════════


async def lookup_decline_code(args: dict[str, Any]) -> dict[str, Any]:
    """Look up a specific decline code via CardAPI MCP server tool endpoint."""
    code = (args.get("code") or "").strip()

    if not code:
        return {
            "success": False,
            "message": "Decline code is required.",
        }

    try:
        logger.info("Looking up decline code via MCP: %s (server=%s)", code, MCP_SERVER_URL)

        async with httpx.AsyncClient(timeout=MCP_REQUEST_TIMEOUT) as client:
            # Call MCP server tool endpoint
            response = await client.get(
                f"{MCP_SERVER_URL}/tools/lookup_decline_code",
                params={"code": code},
            )
            response.raise_for_status()

            data = response.json()
            logger.debug("MCP lookup_decline_code response: success=%s", data.get("success"))

            if data.get("success"):
                return {
                    "success": True,
                    "code": code,
                    "result": data.get("result", ""),
                }
            else:
                return {
                    "success": False,
                    "message": data.get("message", f"Decline code '{code}' not found."),
                }

    except httpx.HTTPStatusError as e:
        error_msg = f"MCP tool call failed: {e.response.status_code} {e.response.text}"
        logger.warning(error_msg)
        return {
            "success": False,
            "message": f"Decline code '{code}' not found or lookup failed.",
            "error": str(e),
        }
    except httpx.ConnectError:
        error_msg = f"Could not connect to CardAPI MCP server at {MCP_SERVER_URL}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": "Decline code service temporarily unavailable.",
            "error": error_msg,
        }
    except Exception as e:
        logger.exception("Error looking up decline code via MCP: %s", code)
        return {
            "success": False,
            "message": "Error retrieving decline code information.",
            "error": str(e),
        }


async def search_decline_codes(args: dict[str, Any]) -> dict[str, Any]:
    """Search for decline codes via CardAPI MCP server tool endpoint."""
    query = (args.get("query") or "").strip()
    code_type = (args.get("code_type") or "").strip() or None

    if not query:
        return {
            "success": False,
            "message": "Search query is required.",
        }

    try:
        logger.info(
            "Searching decline codes via MCP: query=%s, type=%s (server=%s)",
            query,
            code_type,
            MCP_SERVER_URL,
        )

        params: dict[str, str] = {"query": query}
        if code_type:
            params["code_type"] = code_type

        async with httpx.AsyncClient(timeout=MCP_REQUEST_TIMEOUT) as client:
            # Call MCP server tool endpoint
            response = await client.get(
                f"{MCP_SERVER_URL}/tools/search_decline_codes",
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            logger.debug("MCP search_decline_codes response: success=%s", data.get("success"))

            if data.get("success"):
                return {
                    "success": True,
                    "query": query,
                    "code_type": code_type,
                    "result": data.get("result", ""),
                }
            else:
                return {
                    "success": False,
                    "message": data.get("message", "Search failed."),
                }

    except httpx.HTTPStatusError as e:
        error_msg = f"MCP tool call failed: {e.response.status_code} {e.response.text}"
        logger.warning(error_msg)
        return {
            "success": False,
            "message": "Search for decline codes failed.",
            "error": str(e),
        }
    except httpx.ConnectError:
        error_msg = f"Could not connect to CardAPI MCP server at {MCP_SERVER_URL}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": "Decline code service temporarily unavailable.",
            "error": error_msg,
        }
    except Exception as e:
        logger.exception("Error searching decline codes via MCP: %s", query)
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
    tags={"banking", "decline-codes", "cardapi", "mcp"},
)

register_tool(
    "search_decline_codes",
    search_decline_codes_schema,
    search_decline_codes,
    tags={"banking", "decline-codes", "cardapi", "search", "mcp"},
)
