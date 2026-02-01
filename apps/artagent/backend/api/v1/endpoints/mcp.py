"""
MCP Server Management Endpoints
===============================

REST endpoints for dynamically managing MCP (Model Context Protocol) servers
at runtime. Allows users to connect to new MCP servers, discover their tools,
and make those tools available to agents.

Supports OAuth/OBO authentication flows for secured MCP servers.

Endpoints:
    GET  /api/v1/mcp/servers              - List configured MCP servers with status
    POST /api/v1/mcp/servers              - Add new MCP server connection
    POST /api/v1/mcp/servers/test         - Test connection and discover tools
    DELETE /api/v1/mcp/servers/{name}     - Remove server and unregister its tools
    POST /api/v1/mcp/oauth/start          - Start OAuth flow for an MCP server
    POST /api/v1/mcp/oauth/callback       - Complete OAuth flow (exchange code for token)
"""

from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.artagent.backend.config.settings import (
    MCP_ENABLED_SERVERS,
    MCP_SERVER_TIMEOUT,
    get_enabled_mcp_servers,
    get_mcp_server_config,
)
from apps.artagent.backend.registries.toolstore.mcp import (
    MCPClientSession,
    MCPServerConfig,
    MCPTransport,
)
from apps.artagent.backend.registries.toolstore.registry import (
    list_mcp_tools,
    register_mcp_tool,
    unregister_mcp_tools,
)
from utils.ml_logging import get_logger

logger = get_logger("v1.mcp")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY RUNTIME SERVER REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════
# Runtime-added MCP servers (not from environment variables)
# Key: server name, Value: dict with config, headers, and oauth tokens
_RUNTIME_MCP_SERVERS: dict[str, dict[str, Any]] = {}

# Pending OAuth states (state -> {name, redirect_uri, code_verifier, ...})
_OAUTH_PENDING_STATES: dict[str, dict[str, Any]] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════


class OAuthConfig(BaseModel):
    """OAuth configuration for an MCP server."""

    client_id: str = Field(..., description="OAuth client ID")
    auth_url: str = Field(..., description="Authorization endpoint URL")
    token_url: str = Field(..., description="Token endpoint URL")
    scope: str = Field(default="", description="OAuth scopes (space-separated)")
    client_secret: str | None = Field(default=None, description="Client secret (if required)")


class MCPServerRequest(BaseModel):
    """Request schema for adding a new MCP server."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique name for the MCP server (e.g., 'cardapi', 'knowledge')",
        pattern=r"^[a-z0-9_-]+$",
    )
    url: str = Field(
        ...,
        description="HTTP endpoint URL for the MCP server (e.g., 'http://localhost:8080/mcp')",
    )
    transport: str = Field(
        default="streamable-http",
        description="Transport type: 'streamable-http' (MCP spec 2025-11-25), 'sse', or 'stdio'",
    )
    timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
        description="Request timeout in seconds",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Custom HTTP headers (e.g., Authorization, Accept). Supports OBO tokens.",
    )
    auth_token: str | None = Field(
        default=None,
        description="Bearer token for Authorization header (convenience field, merged into headers)",
    )
    oauth: OAuthConfig | None = Field(
        default=None,
        description="OAuth configuration for servers requiring OAuth authentication",
    )


class MCPServerInfo(BaseModel):
    """Information about an MCP server."""

    name: str
    url: str
    transport: str
    timeout: float
    status: str  # "healthy", "unhealthy", "unknown"
    tools_count: int
    tool_names: list[str]
    error: str | None = None
    source: str  # "environment" or "runtime"
    has_auth: bool = False  # Whether auth headers are configured


class MCPToolInfo(BaseModel):
    """Information about a tool discovered from an MCP server."""

    name: str
    prefixed_name: str
    description: str
    server_name: str
    input_schema: dict[str, Any]


class MCPTestResponse(BaseModel):
    """Response from testing an MCP server connection."""

    status: str
    url: str
    connected: bool
    tools_count: int
    tools: list[MCPToolInfo]
    error: str | None = None
    response_time_ms: float


class OAuthStartRequest(BaseModel):
    """Request to start OAuth flow for an MCP server."""

    name: str = Field(..., description="MCP server name")
    url: str = Field(..., description="MCP server URL")
    oauth: OAuthConfig = Field(..., description="OAuth configuration")
    redirect_uri: str = Field(..., description="URI to redirect after OAuth completes")


class OAuthStartResponse(BaseModel):
    """Response containing the OAuth authorization URL."""

    auth_url: str = Field(..., description="Full authorization URL to redirect user to")
    state: str = Field(..., description="State parameter for CSRF protection")


class OAuthCallbackRequest(BaseModel):
    """Request to complete OAuth flow with auth code."""

    code: str = Field(..., description="Authorization code from OAuth callback")
    state: str = Field(..., description="State parameter from OAuth callback")


class OAuthCallbackResponse(BaseModel):
    """Response from OAuth callback - server is now authenticated."""

    success: bool
    server_name: str
    message: str
    has_token: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _get_all_servers() -> dict[str, dict[str, Any]]:
    """
    Get all configured MCP servers from both environment and runtime.

    Returns:
        Dict mapping server name to config with source field
    """
    servers = {}

    # Environment-configured servers
    for server_config in get_enabled_mcp_servers():
        name = server_config["name"]
        servers[name] = {**server_config, "source": "environment", "headers": {}}

    # Runtime-added servers
    for name, config in _RUNTIME_MCP_SERVERS.items():
        servers[name] = {
            "name": config["name"],
            "url": config["url"],
            "transport": config["transport"],
            "timeout": config["timeout"],
            "headers": config.get("headers", {}),
            "source": "runtime",
        }

    return servers


async def _sync_app_state_mcp_status(app_state: Any) -> None:
    """
    Sync app.state.mcp_servers_status with current MCP server state.
    
    This ensures the readiness endpoint returns accurate MCP server info
    after runtime changes (add/remove servers).
    """
    all_servers = _get_all_servers()
    mcp_status: dict[str, dict] = {}
    
    for name, config in all_servers.items():
        url = config["url"]
        transport = config.get("transport", "streamable-http")
        headers = config.get("headers", {})
        
        # Quick health check
        is_healthy, health_data, error = await _check_server_health(
            url, timeout=min(config.get("timeout", 5.0), 5.0), headers=headers
        )
        
        # Get tool count from health data or registry
        tools_count = 0
        tool_names: list[str] = []
        if health_data:
            tools_count = health_data.get("tools_count", 0)
            tool_names = health_data.get("tool_names", [])
        if not tool_names:
            tool_names = list_mcp_tools(mcp_server=name)
            tools_count = len(tool_names)
        
        mcp_status[name] = {
            "status": "healthy" if is_healthy else "unhealthy",
            "url": url,
            "transport": transport,
            "tools_count": tools_count,
            "tool_names": tool_names,
            "error": error,
        }
    
    app_state.mcp_servers_status = mcp_status


def _merge_auth_headers(headers: dict[str, str], auth_token: str | None) -> dict[str, str]:
    """Merge explicit headers with auth_token convenience field."""
    merged = dict(headers) if headers else {}
    if auth_token:
        # Only set if not already present in headers
        if "Authorization" not in merged and "authorization" not in merged:
            merged["Authorization"] = f"Bearer {auth_token}"
    return merged


async def _check_server_health(
    url: str,
    timeout: float = 5.0,
    headers: dict[str, str] | None = None,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Check health of an MCP server.

    Returns:
        Tuple of (is_healthy, health_data, error_message)
    """
    health_url = f"{url.rstrip('/')}/health"
    request_headers = headers or {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(health_url, headers=request_headers)
            if response.status_code == 200:
                try:
                    data = response.json()
                    return True, data, None
                except Exception:
                    return True, {}, None
            else:
                return False, None, f"HTTP {response.status_code}"
    except httpx.ConnectError as e:
        return False, None, f"Connection failed: {e}"
    except httpx.TimeoutException:
        return False, None, "Connection timeout"
    except Exception as e:
        return False, None, str(e)


async def _discover_and_register_tools(
    name: str,
    url: str,
    transport: str,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> tuple[int, list[str], str | None]:
    """
    Connect to MCP server, discover tools, and register them.

    Returns:
        Tuple of (tools_count, tool_names, error_message)
    """
    try:
        config = MCPServerConfig(
            name=name,
            url=url,
            transport=MCPTransport(transport),
            timeout=timeout,
            headers=headers or {},
        )
        session = MCPClientSession(config)

        if not await session.connect():
            return 0, [], "MCP client connection failed"

        # Discover tools
        discovered_tools = await session.list_tools()
        tool_names = []

        # Register each tool
        for tool_info in discovered_tools:
            prefixed_name = f"{name}_{tool_info.name}"
            tool_names.append(prefixed_name)

            # Create executor that calls the MCP server with auth headers
            original_name = tool_info.name
            server_url = url
            server_timeout = timeout
            server_headers = dict(headers) if headers else {}

            def make_executor(
                tool_original_name: str,
                mcp_url: str,
                mcp_timeout: float,
                mcp_headers: dict[str, str],
            ):
                async def executor(args: dict) -> dict:
                    """Execute MCP tool via HTTP endpoint with authentication."""
                    # Strip /mcp suffix if present - REST tool endpoints are at /tools/*
                    # while MCP JSON-RPC endpoint is at /mcp
                    base_url = mcp_url.rstrip("/")
                    if base_url.endswith("/mcp"):
                        base_url = base_url[:-4]
                    tool_endpoint = f"{base_url}/tools/{tool_original_name}"
                    try:
                        async with httpx.AsyncClient(timeout=mcp_timeout) as client:
                            response = await client.get(
                                tool_endpoint,
                                params=args,
                                headers=mcp_headers,
                            )
                            if response.status_code == 200:
                                data = response.json()
                                if "result" in data:
                                    return {"success": True, "result": data["result"]}
                                return {"success": True, "result": data}
                            elif response.status_code == 401:
                                return {
                                    "success": False,
                                    "error": "Authentication failed (401). Token may have expired.",
                                }
                            elif response.status_code == 403:
                                return {
                                    "success": False,
                                    "error": "Access denied (403). Insufficient permissions.",
                                }
                            else:
                                return {
                                    "success": False,
                                    "error": f"MCP tool returned HTTP {response.status_code}: {response.text[:200]}",
                                }
                    except httpx.ConnectError as e:
                        return {"success": False, "error": f"Failed to connect to MCP server: {e}"}
                    except Exception as e:
                        return {"success": False, "error": f"MCP tool execution failed: {e}"}
                return executor

            executor = make_executor(original_name, server_url, server_timeout, server_headers)

            schema = {
                "name": prefixed_name,
                "description": tool_info.description or f"MCP tool from {name}",
                "parameters": tool_info.input_schema or {"type": "object", "properties": {}},
            }

            register_mcp_tool(
                name=prefixed_name,
                schema=schema,
                mcp_server=name,
                mcp_transport=transport,
                executor=executor,
                override=True,
            )

        await session.disconnect()
        return len(tool_names), tool_names, None

    except Exception as e:
        logger.error(f"Failed to discover/register tools from {name}: {e}")
        return 0, [], str(e)


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/servers",
    response_model=dict[str, Any],
    summary="List MCP Servers",
    description="Get list of all configured MCP servers with their status and registered tools.",
    tags=["MCP"],
)
async def list_mcp_servers(request: Request) -> dict[str, Any]:
    """
    List all configured MCP servers with status.

    Returns servers from both environment configuration and runtime additions.
    """
    start = time.time()
    servers_list: list[MCPServerInfo] = []

    # Get all servers
    all_servers = _get_all_servers()

    # Check status of each server
    for name, config in all_servers.items():
        url = config["url"]
        timeout = config.get("timeout", MCP_SERVER_TIMEOUT)
        source = config.get("source", "unknown")
        headers = config.get("headers", {})

        # Check health (with auth headers if configured)
        is_healthy, health_data, error = await _check_server_health(
            url, timeout=min(timeout, 5.0), headers=headers
        )

        # Get registered tools for this server
        registered_tools = list_mcp_tools(mcp_server=name)

        # Extract tools info from health response if available
        tools_count = health_data.get("tools_count", len(registered_tools)) if health_data else len(registered_tools)
        tool_names = health_data.get("tool_names", registered_tools) if health_data else registered_tools

        servers_list.append(
            MCPServerInfo(
                name=name,
                url=url,
                transport=config.get("transport", "streamable-http"),
                timeout=timeout,
                status="healthy" if is_healthy else "unhealthy",
                tools_count=tools_count,
                tool_names=tool_names,
                error=error,
                source=source,
                has_auth=bool(headers.get("Authorization") or headers.get("authorization")),
            )
        )

    # Also include status from app.state if available
    app_mcp_status = getattr(request.app.state, "mcp_servers_status", {})

    return {
        "status": "success",
        "total": len(servers_list),
        "servers": [s.model_dump() for s in servers_list],
        "startup_status": app_mcp_status,
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


@router.post(
    "/servers",
    response_model=dict[str, Any],
    summary="Add MCP Server",
    description="Add a new MCP server connection at runtime and register its tools.",
    tags=["MCP"],
)
async def add_mcp_server(
    server: MCPServerRequest,
    request: Request,
) -> dict[str, Any]:
    """
    Add a new MCP server at runtime.

    This will:
    1. Connect to the MCP server
    2. Discover available tools
    3. Register tools in the central registry
    4. Make tools available for agent configuration
    """
    start = time.time()

    # Check if server name already exists
    all_servers = _get_all_servers()
    if server.name in all_servers:
        raise HTTPException(
            status_code=409,
            detail=f"MCP server '{server.name}' already exists. Use DELETE to remove it first.",
        )

    # Validate URL format
    if not server.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="URL must start with http:// or https://",
        )

    # Merge headers with auth_token convenience field
    merged_headers = _merge_auth_headers(server.headers, server.auth_token)

    # Check health first (with auth headers)
    is_healthy, health_data, error = await _check_server_health(
        server.url, timeout=server.timeout, headers=merged_headers
    )
    if not is_healthy:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to MCP server at {server.url}: {error}",
        )

    # Discover and register tools (with auth headers)
    tools_count, tool_names, register_error = await _discover_and_register_tools(
        name=server.name,
        url=server.url,
        transport=server.transport,
        timeout=server.timeout,
        headers=merged_headers,
    )

    if register_error:
        raise HTTPException(
            status_code=500,
            detail=f"Connected to server but failed to register tools: {register_error}",
        )

    # Store in runtime registry (including headers for tool execution)
    _RUNTIME_MCP_SERVERS[server.name] = {
        "name": server.name,
        "url": server.url,
        "transport": server.transport,
        "timeout": server.timeout,
        "headers": merged_headers,
    }

    logger.info(
        f"Added MCP server '{server.name}' at {server.url} with {tools_count} tools: {tool_names}"
    )

    # Sync app.state.mcp_servers_status so readiness endpoint reflects the change
    await _sync_app_state_mcp_status(request.app.state)

    return {
        "status": "success",
        "message": f"MCP server '{server.name}' added successfully",
        "server": {
            "name": server.name,
            "url": server.url,
            "transport": server.transport,
            "timeout": server.timeout,
            "status": "healthy",
            "tools_count": tools_count,
            "tool_names": tool_names,
            "source": "runtime",
            "has_auth": bool(merged_headers.get("Authorization")),
        },
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


@router.post(
    "/servers/test",
    response_model=MCPTestResponse,
    summary="Test MCP Server Connection",
    description="Test connection to an MCP server and discover its tools without registering them.",
    tags=["MCP"],
)
async def test_mcp_server(
    server: MCPServerRequest,
) -> MCPTestResponse:
    """
    Test MCP server connection and discover tools.

    This is a read-only operation - tools are NOT registered.
    Use POST /servers to actually add the server and register tools.

    Supports authentication via:
    - auth_token: Convenience field for Bearer token (sets Authorization header)
    - headers: Custom headers dict for any auth scheme
    """
    start = time.time()

    # Merge auth headers
    merged_headers = _merge_auth_headers(server.headers, server.auth_token)

    # Validate URL format
    if not server.url.startswith(("http://", "https://")):
        return MCPTestResponse(
            status="error",
            url=server.url,
            connected=False,
            tools_count=0,
            tools=[],
            error="URL must start with http:// or https://",
            response_time_ms=round((time.time() - start) * 1000, 2),
        )

    # Check health
    is_healthy, health_data, error = await _check_server_health(
        server.url, timeout=server.timeout, headers=merged_headers
    )
    if not is_healthy:
        return MCPTestResponse(
            status="unhealthy",
            url=server.url,
            connected=False,
            tools_count=0,
            tools=[],
            error=error,
            response_time_ms=round((time.time() - start) * 1000, 2),
        )

    # Try to discover tools
    tools: list[MCPToolInfo] = []
    try:
        config = MCPServerConfig(
            name=server.name,
            url=server.url,
            transport=MCPTransport(server.transport),
            timeout=server.timeout,
            headers=merged_headers if merged_headers else None,
        )
        session = MCPClientSession(config)

        if await session.connect():
            discovered = await session.list_tools()
            for tool_info in discovered:
                tools.append(
                    MCPToolInfo(
                        name=tool_info.name,
                        prefixed_name=f"{server.name}_{tool_info.name}",
                        description=tool_info.description or f"Tool from {server.name}",
                        server_name=server.name,
                        input_schema=tool_info.input_schema or {"type": "object", "properties": {}},
                    )
                )
            await session.disconnect()
        else:
            error = "Failed to establish MCP client connection"

    except Exception as e:
        error = f"Tool discovery failed: {e}"
        logger.warning(f"Tool discovery failed for {server.url}: {e}")

    return MCPTestResponse(
        status="healthy" if tools else ("connected" if is_healthy else "unhealthy"),
        url=server.url,
        connected=is_healthy,
        tools_count=len(tools),
        tools=tools,
        error=error if not tools and error else None,
        response_time_ms=round((time.time() - start) * 1000, 2),
    )


@router.delete(
    "/servers/{name}",
    response_model=dict[str, Any],
    summary="Remove MCP Server",
    description="Remove an MCP server and unregister all its tools.",
    tags=["MCP"],
)
async def remove_mcp_server(
    name: str,
    request: Request,
) -> dict[str, Any]:
    """
    Remove an MCP server and unregister its tools.

    Only runtime-added servers can be removed. Environment-configured servers
    require environment variable changes and a restart.
    """
    start = time.time()

    # Check if server exists
    all_servers = _get_all_servers()
    if name not in all_servers:
        raise HTTPException(
            status_code=404,
            detail=f"MCP server '{name}' not found",
        )

    # Check if it's a runtime server
    if name not in _RUNTIME_MCP_SERVERS:
        raise HTTPException(
            status_code=400,
            detail=f"MCP server '{name}' is configured via environment variables. "
            "To remove it, update MCP_ENABLED_SERVERS and restart the application.",
        )

    # Unregister tools
    tools_removed = unregister_mcp_tools(mcp_server=name)

    # Remove from runtime registry
    del _RUNTIME_MCP_SERVERS[name]

    logger.info(f"Removed MCP server '{name}' and {tools_removed} tools")

    # Sync app.state.mcp_servers_status so readiness endpoint reflects the change
    await _sync_app_state_mcp_status(request.app.state)

    return {
        "status": "success",
        "message": f"MCP server '{name}' removed successfully",
        "tools_removed": tools_removed,
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


@router.get(
    "/tools",
    response_model=dict[str, Any],
    summary="List MCP Tools",
    description="Get list of all registered MCP tools across all servers.",
    tags=["MCP"],
)
async def list_all_mcp_tools(
    server: str | None = None,
) -> dict[str, Any]:
    """
    List all registered MCP tools.

    Args:
        server: Optional filter by MCP server name
    """
    start = time.time()

    tool_names = list_mcp_tools(mcp_server=server)

    # Group by server
    by_server: dict[str, list[str]] = {}
    for tool_name in tool_names:
        # Parse server name from prefixed tool name (format: "servername_toolname")
        parts = tool_name.split("_", 1)
        if len(parts) == 2:
            srv_name = parts[0]
            if srv_name not in by_server:
                by_server[srv_name] = []
            by_server[srv_name].append(tool_name)
        else:
            if "unknown" not in by_server:
                by_server["unknown"] = []
            by_server["unknown"].append(tool_name)

    return {
        "status": "success",
        "total": len(tool_names),
        "tools": tool_names,
        "by_server": by_server,
        "filter": {"server": server} if server else None,
        "response_time_ms": round((time.time() - start) * 1000, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OAUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


def _generate_pkce_verifier() -> str:
    """Generate a PKCE code verifier."""
    return secrets.token_urlsafe(32)


def _generate_pkce_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge (S256)."""
    import base64
    import hashlib

    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@router.post(
    "/oauth/start",
    response_model=OAuthStartResponse,
    summary="Start OAuth Flow",
    description="Start OAuth authentication flow for an MCP server. Returns the authorization URL.",
    tags=["MCP", "OAuth"],
)
async def oauth_start(
    request: OAuthStartRequest,
) -> OAuthStartResponse:
    """
    Start OAuth flow for authenticating with an MCP server.

    Generates PKCE challenge and returns the full authorization URL.
    The frontend should redirect/popup to this URL for user authentication.
    """
    # Generate state and PKCE values
    state = secrets.token_urlsafe(32)
    code_verifier = _generate_pkce_verifier()
    code_challenge = _generate_pkce_challenge(code_verifier)

    # Store pending OAuth state
    _OAUTH_PENDING_STATES[state] = {
        "name": request.name,
        "url": request.url,
        "oauth": request.oauth.model_dump(),
        "redirect_uri": request.redirect_uri,
        "code_verifier": code_verifier,
        "created_at": time.time(),
    }

    # Build authorization URL
    params = {
        "client_id": request.oauth.client_id,
        "response_type": "code",
        "redirect_uri": request.redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if request.oauth.scope:
        params["scope"] = request.oauth.scope

    auth_url = f"{request.oauth.auth_url}?{urlencode(params)}"

    logger.info(f"Started OAuth flow for MCP server '{request.name}' (state={state[:8]}...)")

    return OAuthStartResponse(auth_url=auth_url, state=state)


@router.post(
    "/oauth/callback",
    response_model=OAuthCallbackResponse,
    summary="Complete OAuth Flow",
    description="Complete OAuth flow by exchanging the authorization code for an access token.",
    tags=["MCP", "OAuth"],
)
async def oauth_callback(
    request: OAuthCallbackRequest,
) -> OAuthCallbackResponse:
    """
    Complete OAuth flow by exchanging the authorization code for tokens.

    The obtained access token is automatically stored and used for MCP server requests.
    """
    # Validate state
    pending = _OAUTH_PENDING_STATES.pop(request.state, None)
    if not pending:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth state. Please restart the authentication flow.",
        )

    # Check state expiry (10 minute limit)
    if time.time() - pending["created_at"] > 600:
        raise HTTPException(
            status_code=400,
            detail="OAuth state expired. Please restart the authentication flow.",
        )

    oauth_config = pending["oauth"]

    # Exchange code for token
    token_data = {
        "grant_type": "authorization_code",
        "client_id": oauth_config["client_id"],
        "code": request.code,
        "redirect_uri": pending["redirect_uri"],
        "code_verifier": pending["code_verifier"],
    }
    if oauth_config.get("client_secret"):
        token_data["client_secret"] = oauth_config["client_secret"]

    logger.info(
        f"Exchanging OAuth code for token at '{oauth_config['token_url']}' "
        f"for MCP server '{pending['name']}'"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                oauth_config["token_url"],
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_detail = response.text[:500] if response.text else "Unknown error"
                logger.warning(
                    f"OAuth token exchange failed for '{pending['name']}': "
                    f"status={response.status_code}, url={oauth_config['token_url']}, detail={error_detail}"
                )
                # Pass through the actual status code for better debugging
                raise HTTPException(
                    status_code=response.status_code if response.status_code in (400, 401, 403, 405) else 400,
                    detail=f"Token exchange failed (HTTP {response.status_code}): {error_detail}",
                )

            tokens = response.json()
            access_token = tokens.get("access_token")
            if not access_token:
                raise HTTPException(
                    status_code=400,
                    detail="No access_token in token response",
                )

    except httpx.RequestError as e:
        logger.error(f"OAuth token exchange request failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to contact token endpoint: {e}",
        )

    # Store the token with the MCP server config
    server_name = pending["name"]
    if server_name in _RUNTIME_MCP_SERVERS:
        # Update existing server with new token
        _RUNTIME_MCP_SERVERS[server_name]["headers"]["Authorization"] = f"Bearer {access_token}"
        _RUNTIME_MCP_SERVERS[server_name]["oauth_tokens"] = tokens
        logger.info(f"Updated OAuth token for existing MCP server '{server_name}'")
    else:
        # Store pending config for when server is added
        _RUNTIME_MCP_SERVERS[server_name] = {
            "name": server_name,
            "url": pending["url"],
            "transport": "streamable-http",
            "timeout": MCP_SERVER_TIMEOUT,
            "headers": {"Authorization": f"Bearer {access_token}"},
            "oauth_config": oauth_config,
            "oauth_tokens": tokens,
        }
        logger.info(f"Stored OAuth config for MCP server '{server_name}'")

    return OAuthCallbackResponse(
        success=True,
        server_name=server_name,
        message=f"Successfully authenticated with MCP server '{server_name}'",
        has_token=True,
    )


@router.get(
    "/oauth/status/{name}",
    response_model=dict[str, Any],
    summary="Check OAuth Status",
    description="Check if an MCP server has valid OAuth tokens.",
    tags=["MCP", "OAuth"],
)
async def oauth_status(
    name: str,
) -> dict[str, Any]:
    """Check OAuth authentication status for an MCP server."""
    if name in _RUNTIME_MCP_SERVERS:
        config = _RUNTIME_MCP_SERVERS[name]
        has_token = "Authorization" in config.get("headers", {})
        has_oauth = "oauth_tokens" in config
        return {
            "server": name,
            "authenticated": has_token,
            "oauth_configured": has_oauth,
            "has_refresh_token": bool(config.get("oauth_tokens", {}).get("refresh_token")),
        }

    return {
        "server": name,
        "authenticated": False,
        "oauth_configured": False,
        "has_refresh_token": False,
    }
