import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.artagent.backend.registries.toolstore.mcp.adapter import mcp_schema_to_openai
from apps.artagent.backend.registries.toolstore.mcp.client import (
    MCPClientSession,
    MCPServerConfig,
    MCPToolInfo,
    MCPTransport,
)
from apps.artagent.backend.registries.toolstore.mcp.session_manager import MCPSessionManager
from apps.artagent.backend.registries.toolstore.mcp import auth as mcp_auth


def _mock_httpx_client(tool_list_payload=None):
    client = AsyncMock()

    async def get(path, *args, **kwargs):
        response = MagicMock()
        if path == "/health":
            response.status_code = 200
            response.json.return_value = {"status": "healthy"}
            return response
        if path == "/tools/list":
            response.status_code = 200
            response.json.return_value = tool_list_payload or {"tools": []}
            return response
        response.status_code = 404
        response.json.return_value = {}
        return response

    client.get.side_effect = get
    client.post.return_value = MagicMock(status_code=200, json=lambda: {"result": {"ok": True}})
    client.aclose = AsyncMock()
    return client


def test_transport_aliases():
    assert MCPTransport("streamablehttp") == MCPTransport.STREAMABLE_HTTP
    assert MCPTransport("http") == MCPTransport.HTTP
    assert MCPTransport("sse") == MCPTransport.SSE


def test_server_config_unknown_transport_defaults():
    config = MCPServerConfig(name="srv", url="http://x", transport="weird")
    assert config.transport == MCPTransport.STREAMABLE_HTTP


@pytest.mark.asyncio
async def test_list_tools_dynamic_discovery():
    tool_payload = {
        "tools": [
            {
                "name": "search",
                "description": "Search tool",
                "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
            }
        ]
    }
    mock_client = _mock_httpx_client(tool_list_payload=tool_payload)
    with patch(
        "apps.artagent.backend.registries.toolstore.mcp.client.httpx.AsyncClient",
        return_value=mock_client,
    ):
        session = MCPClientSession(MCPServerConfig(name="knowledge", url="http://mcp"))
        assert await session.connect() is True
        tools = await session.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "search"


@pytest.mark.asyncio
async def test_list_tools_cardapi_dynamic():
    """Verify CardAPI uses standard /tools/list discovery (no longer uses hardcoded fallback)."""
    tool_payload = {
        "tools": [
            {
                "name": "lookup_decline_code",
                "description": "Look up a decline code",
                "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}},
            },
            {
                "name": "search_decline_codes",
                "description": "Search decline codes",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        ]
    }
    mock_client = _mock_httpx_client(tool_list_payload=tool_payload)
    with patch(
        "apps.artagent.backend.registries.toolstore.mcp.client.httpx.AsyncClient",
        return_value=mock_client,
    ):
        session = MCPClientSession(MCPServerConfig(name="cardapi", url="http://mcp"))
        assert await session.connect() is True
        tools = await session.list_tools()
        assert len(tools) == 2
        assert any(tool.name == "lookup_decline_code" for tool in tools)
        # CardAPI should now call /tools/list like any other MCP server
        assert any(call.args[0] == "/tools/list" for call in mock_client.get.call_args_list)


@pytest.mark.asyncio
async def test_call_tool_cardapi_get():
    session = MCPClientSession(MCPServerConfig(name="cardapi", url="http://mcp"))
    session._client = AsyncMock()
    session._connected = True
    response = MagicMock()
    response.json.return_value = {"result": {"code": "51"}}
    session._client.get.return_value = response

    result = await session.call_tool("lookup_decline_code", {"code": "51"})
    session._client.get.assert_called_once()
    assert result["success"] is True
    assert result["result"]["code"] == "51"


@pytest.mark.asyncio
async def test_call_tool_default_post():
    session = MCPClientSession(MCPServerConfig(name="srv", url="http://mcp"))
    session._client = AsyncMock()
    session._connected = True
    response = MagicMock()
    response.json.return_value = {"ok": True}
    session._client.post.return_value = response

    result = await session.call_tool("custom_tool", {"a": 1})
    session._client.post.assert_called_once()
    assert result["success"] is True
    assert result["result"]["ok"] is True


def test_adapter_schema_minimums():
    tool = MCPToolInfo(
        name="demo",
        description="Demo tool",
        input_schema={},
        server_name="srv",
    )
    schema = mcp_schema_to_openai(tool, use_prefix=True)
    assert schema["parameters"]["type"] == "object"
    assert "properties" in schema["parameters"]


@pytest.mark.asyncio
async def test_session_manager_execute_tool_uses_original_name():
    manager = MCPSessionManager(session_id="s1")
    tool = MCPToolInfo(
        name="lookup",
        description="Lookup",
        input_schema={"type": "object", "properties": {}},
        server_name="srv",
    )
    manager._tools_cache = {"srv_lookup": tool}
    session = AsyncMock()
    session.is_connected = True
    session.call_tool = AsyncMock(return_value={"success": True})
    manager._sessions = {"srv": session}

    result = await manager.execute_tool("srv_lookup", {"code": "51"})
    session.call_tool.assert_called_once_with("lookup", {"code": "51"})
    assert result["success"] is True


@pytest.mark.asyncio
async def test_get_mcp_auth_token_caches():
    class _Token:
        def __init__(self):
            self.token = "tok"
            self.expires_on = time.time() + 3600

    class _Cred:
        def __init__(self):
            self.calls = 0

        def get_token(self, _scope):
            self.calls += 1
            return _Token()

    cred = _Cred()
    mcp_auth.clear_token_cache()

    with patch(
        "apps.artagent.backend.registries.toolstore.mcp.auth._get_credential", return_value=cred
    ):
        token1 = await mcp_auth.get_mcp_auth_token("api://app")
        token2 = await mcp_auth.get_mcp_auth_token("api://app")

    assert token1 == "tok"
    assert token2 == "tok"
    assert cred.calls == 1


@pytest.mark.asyncio
async def test_get_mcp_auth_headers():
    with patch(
        "apps.artagent.backend.registries.toolstore.mcp.auth.get_mcp_auth_token",
        new=AsyncMock(return_value="abc"),
    ):
        headers = await mcp_auth.get_mcp_auth_headers("api://app")
        assert headers["Authorization"] == "Bearer abc"
