"""
Tests for MCP Server Management API Endpoints
==============================================

Tests for the runtime MCP server management API including:
- List servers
- Add server
- Test connection
- Remove server
- List tools
- OAuth flow (start, callback, status)
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.artagent.backend.api.v1.endpoints.mcp import (
    _RUNTIME_MCP_SERVERS,
    _OAUTH_PENDING_STATES,
    _generate_pkce_challenge,
    _generate_pkce_verifier,
    _merge_auth_headers,
    router,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def app():
    """Create test FastAPI app with MCP router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/mcp")
    # Mock app state
    app.state.mcp_servers_status = {}
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_runtime_state():
    """Clear runtime state before each test."""
    _RUNTIME_MCP_SERVERS.clear()
    _OAUTH_PENDING_STATES.clear()
    yield
    _RUNTIME_MCP_SERVERS.clear()
    _OAUTH_PENDING_STATES.clear()


@pytest.fixture
def mock_mcp_session():
    """Mock MCP client session."""
    with patch(
        "apps.artagent.backend.api.v1.endpoints.mcp.MCPClientSession"
    ) as mock_class:
        mock_session = AsyncMock()
        mock_session.connect.return_value = True
        mock_session.disconnect.return_value = None

        # Mock tool discovery
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.input_schema = {"type": "object", "properties": {"arg1": {"type": "string"}}}
        mock_session.list_tools.return_value = [mock_tool]

        mock_class.return_value = mock_session
        yield mock_class


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for health checks and tool calls."""
    with patch("apps.artagent.backend.api.v1.endpoints.mcp.httpx.AsyncClient") as mock:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "tools_count": 1}
        mock_response.text = '{"status": "healthy"}'
        mock_client.get.return_value = mock_response
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_get_enabled_mcp_servers():
    """Mock environment-configured MCP servers."""
    with patch(
        "apps.artagent.backend.api.v1.endpoints.mcp.get_enabled_mcp_servers"
    ) as mock:
        mock.return_value = [
            {
                "name": "env_server",
                "url": "http://env-server:8080",
                "transport": "sse",
                "timeout": 30.0,
            }
        ]
        yield mock


@pytest.fixture
def mock_list_mcp_tools():
    """Mock tool registry listing."""
    with patch(
        "apps.artagent.backend.api.v1.endpoints.mcp.list_mcp_tools"
    ) as mock:
        mock.return_value = ["env_server_tool1", "env_server_tool2"]
        yield mock


@pytest.fixture
def mock_register_mcp_tool():
    """Mock tool registration."""
    with patch(
        "apps.artagent.backend.api.v1.endpoints.mcp.register_mcp_tool"
    ) as mock:
        yield mock


@pytest.fixture
def mock_unregister_mcp_tools():
    """Mock tool unregistration."""
    with patch(
        "apps.artagent.backend.api.v1.endpoints.mcp.unregister_mcp_tools"
    ) as mock:
        mock.return_value = 2  # Number of tools removed
        yield mock


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_merge_auth_headers_with_token(self):
        """Test merging headers with auth token."""
        headers = {"X-Custom": "value"}
        result = _merge_auth_headers(headers, "my-token")
        assert result["X-Custom"] == "value"
        assert result["Authorization"] == "Bearer my-token"

    def test_merge_auth_headers_existing_auth(self):
        """Test that existing Authorization header is not overwritten."""
        headers = {"Authorization": "Bearer existing"}
        result = _merge_auth_headers(headers, "new-token")
        assert result["Authorization"] == "Bearer existing"

    def test_merge_auth_headers_no_token(self):
        """Test merging headers without auth token."""
        headers = {"X-Custom": "value"}
        result = _merge_auth_headers(headers, None)
        assert result == {"X-Custom": "value"}
        assert "Authorization" not in result

    def test_merge_auth_headers_empty(self):
        """Test merging empty headers without token."""
        result = _merge_auth_headers({}, None)
        assert result == {}

    def test_pkce_verifier_generation(self):
        """Test PKCE verifier is generated correctly."""
        verifier = _generate_pkce_verifier()
        assert len(verifier) > 40  # Should be substantial length
        assert isinstance(verifier, str)
        # Should be URL-safe
        assert all(c.isalnum() or c in "-_" for c in verifier)

    def test_pkce_challenge_generation(self):
        """Test PKCE challenge is generated correctly from verifier."""
        verifier = "test_verifier_string_12345"
        challenge = _generate_pkce_challenge(verifier)
        assert isinstance(challenge, str)
        assert len(challenge) > 20
        # Challenge should be different from verifier
        assert challenge != verifier
        # Should be consistent for same input
        assert _generate_pkce_challenge(verifier) == challenge


# ═══════════════════════════════════════════════════════════════════════════════
# LIST SERVERS ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestListServers:
    """Tests for GET /servers endpoint."""

    def test_list_servers_empty(
        self, client, mock_get_enabled_mcp_servers, mock_httpx_client, mock_list_mcp_tools
    ):
        """Test listing servers when no runtime servers exist."""
        response = client.get("/api/v1/mcp/servers")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 1  # Only env server
        assert len(data["servers"]) == 1
        assert data["servers"][0]["name"] == "env_server"
        assert data["servers"][0]["source"] == "environment"

    def test_list_servers_with_runtime_server(
        self, client, mock_get_enabled_mcp_servers, mock_httpx_client, mock_list_mcp_tools
    ):
        """Test listing servers with runtime-added server."""
        # Add a runtime server
        _RUNTIME_MCP_SERVERS["runtime_server"] = {
            "name": "runtime_server",
            "url": "http://runtime:8080",
            "transport": "http",
            "timeout": 30.0,
            "headers": {},
        }

        response = client.get("/api/v1/mcp/servers")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2  # env + runtime
        server_names = [s["name"] for s in data["servers"]]
        assert "env_server" in server_names
        assert "runtime_server" in server_names

    def test_list_servers_shows_health_status(
        self, client, mock_get_enabled_mcp_servers, mock_httpx_client, mock_list_mcp_tools
    ):
        """Test that server health status is included."""
        response = client.get("/api/v1/mcp/servers")
        assert response.status_code == 200

        data = response.json()
        assert data["servers"][0]["status"] == "healthy"

    def test_list_servers_unhealthy(
        self, client, mock_get_enabled_mcp_servers, mock_list_mcp_tools
    ):
        """Test listing servers when health check fails."""
        with patch("apps.artagent.backend.api.v1.endpoints.mcp.httpx.AsyncClient") as mock:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock.return_value = mock_client

            response = client.get("/api/v1/mcp/servers")
            assert response.status_code == 200

            data = response.json()
            assert data["servers"][0]["status"] == "unhealthy"
            assert data["servers"][0]["error"] is not None

    def test_list_servers_includes_startup_status(
        self, client, mock_get_enabled_mcp_servers, mock_httpx_client, mock_list_mcp_tools
    ):
        """Test that startup_status from app state is included."""
        client.app.state.mcp_servers_status = {
            "env_server": {"status": "healthy", "url": "http://env-server:8080"}
        }
        response = client.get("/api/v1/mcp/servers")
        assert response.status_code == 200

        data = response.json()
        assert "startup_status" in data
        assert data["startup_status"]["env_server"]["status"] == "healthy"


# ═══════════════════════════════════════════════════════════════════════════════
# ADD SERVER ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddServer:
    """Tests for POST /servers endpoint."""

    def test_add_server_success(
        self,
        client,
        mock_get_enabled_mcp_servers,
        mock_httpx_client,
        mock_mcp_session,
        mock_register_mcp_tool,
    ):
        """Test successfully adding a new MCP server."""
        response = client.post(
            "/api/v1/mcp/servers",
            json={
                "name": "newserver",
                "url": "http://newserver:8080",
                "transport": "sse",
                "timeout": 30,
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["server"]["name"] == "newserver"
        assert data["server"]["tools_count"] == 1  # From mock
        assert "newserver_test_tool" in data["server"]["tool_names"]
        assert "newserver" in _RUNTIME_MCP_SERVERS
        # App state should be synced for readiness endpoint
        assert "newserver" in client.app.state.mcp_servers_status

    def test_add_server_with_auth_token(
        self,
        client,
        mock_get_enabled_mcp_servers,
        mock_httpx_client,
        mock_mcp_session,
        mock_register_mcp_tool,
    ):
        """Test adding server with bearer token auth."""
        response = client.post(
            "/api/v1/mcp/servers",
            json={
                "name": "authserver",
                "url": "http://authserver:8080",
                "auth_token": "my-secret-token",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["server"]["has_auth"] is True
        assert _RUNTIME_MCP_SERVERS["authserver"]["headers"]["Authorization"] == "Bearer my-secret-token"

    def test_add_server_with_custom_headers(
        self,
        client,
        mock_get_enabled_mcp_servers,
        mock_httpx_client,
        mock_mcp_session,
        mock_register_mcp_tool,
    ):
        """Test adding server with custom headers."""
        response = client.post(
            "/api/v1/mcp/servers",
            json={
                "name": "customserver",
                "url": "http://customserver:8080",
                "headers": {"X-API-Key": "abc123", "X-Tenant": "tenant1"},
            },
        )
        assert response.status_code == 200

        stored_headers = _RUNTIME_MCP_SERVERS["customserver"]["headers"]
        assert stored_headers["X-API-Key"] == "abc123"
        assert stored_headers["X-Tenant"] == "tenant1"

    def test_add_server_duplicate_name(
        self, client, mock_get_enabled_mcp_servers, mock_httpx_client
    ):
        """Test adding server with duplicate name fails."""
        # Add first server
        _RUNTIME_MCP_SERVERS["existing"] = {
            "name": "existing",
            "url": "http://existing:8080",
            "transport": "sse",
            "timeout": 30,
            "headers": {},
        }

        response = client.post(
            "/api/v1/mcp/servers",
            json={"name": "existing", "url": "http://other:8080"},
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_add_server_invalid_url(self, client, mock_get_enabled_mcp_servers):
        """Test adding server with invalid URL fails."""
        response = client.post(
            "/api/v1/mcp/servers",
            json={"name": "badurl", "url": "not-a-url"},
        )
        assert response.status_code == 400
        assert "http://" in response.json()["detail"]

    def test_add_server_connection_failed(
        self, client, mock_get_enabled_mcp_servers
    ):
        """Test adding server when connection fails."""
        with patch("apps.artagent.backend.api.v1.endpoints.mcp.httpx.AsyncClient") as mock:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock.return_value = mock_client

            response = client.post(
                "/api/v1/mcp/servers",
                json={"name": "unreachable", "url": "http://unreachable:8080"},
            )
            assert response.status_code == 503
            assert "Cannot connect" in response.json()["detail"]

    def test_add_server_invalid_name_pattern(self, client):
        """Test adding server with invalid name pattern."""
        response = client.post(
            "/api/v1/mcp/servers",
            json={"name": "Invalid Name!", "url": "http://server:8080"},
        )
        assert response.status_code == 422  # Validation error


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CONNECTION ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestTestConnection:
    """Tests for POST /servers/test endpoint."""

    def test_test_connection_success(
        self, client, mock_httpx_client, mock_mcp_session
    ):
        """Test successful connection test."""
        response = client.post(
            "/api/v1/mcp/servers/test",
            json={"name": "testserver", "url": "http://testserver:8080"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["connected"] is True
        assert data["tools_count"] == 1
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "test_tool"
        assert data["tools"][0]["prefixed_name"] == "testserver_test_tool"

    def test_test_connection_with_auth(
        self, client, mock_httpx_client, mock_mcp_session
    ):
        """Test connection test with authentication."""
        response = client.post(
            "/api/v1/mcp/servers/test",
            json={
                "name": "authtest",
                "url": "http://authtest:8080",
                "auth_token": "test-token",
            },
        )
        assert response.status_code == 200
        assert response.json()["connected"] is True

    def test_test_connection_invalid_url(self, client):
        """Test connection test with invalid URL."""
        response = client.post(
            "/api/v1/mcp/servers/test",
            json={"name": "badurl", "url": "ftp://invalid"},
        )
        assert response.status_code == 200  # Returns error in response body

        data = response.json()
        assert data["status"] == "error"
        assert data["connected"] is False
        assert "http://" in data["error"]

    def test_test_connection_unhealthy(self, client):
        """Test connection test when server is unhealthy."""
        with patch("apps.artagent.backend.api.v1.endpoints.mcp.httpx.AsyncClient") as mock:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock.return_value = mock_client

            response = client.post(
                "/api/v1/mcp/servers/test",
                json={"name": "badserver", "url": "http://badserver:8080"},
            )
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["connected"] is False

    def test_test_connection_does_not_register(
        self, client, mock_httpx_client, mock_mcp_session, mock_register_mcp_tool
    ):
        """Test that testing connection does NOT register tools."""
        response = client.post(
            "/api/v1/mcp/servers/test",
            json={"name": "noregister", "url": "http://noregister:8080"},
        )
        assert response.status_code == 200

        # Tools should not be registered
        mock_register_mcp_tool.assert_not_called()
        # Server should not be added to runtime registry
        assert "noregister" not in _RUNTIME_MCP_SERVERS

    def test_test_connection_no_tools_status_connected(self, client):
        """Test connection health OK but tool discovery empty -> status is connected."""
        with patch("apps.artagent.backend.api.v1.endpoints.mcp.httpx.AsyncClient") as mock_httpx:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "healthy", "tools_count": 0}
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_httpx.return_value = mock_client

            with patch(
                "apps.artagent.backend.api.v1.endpoints.mcp.MCPClientSession"
            ) as mock_session_cls:
                mock_session = AsyncMock()
                mock_session.connect.return_value = True
                mock_session.list_tools.return_value = []
                mock_session.disconnect.return_value = None
                mock_session_cls.return_value = mock_session

                response = client.post(
                    "/api/v1/mcp/servers/test",
                    json={"name": "empties", "url": "http://empties:8080"},
                )
                assert response.status_code == 200

                data = response.json()
                assert data["status"] == "connected"
                assert data["tools_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# REMOVE SERVER ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemoveServer:
    """Tests for DELETE /servers/{name} endpoint."""

    def test_remove_runtime_server_success(
        self,
        client,
        mock_get_enabled_mcp_servers,
        mock_unregister_mcp_tools,
    ):
        """Test successfully removing a runtime server."""
        # Add a runtime server first
        _RUNTIME_MCP_SERVERS["removeme"] = {
            "name": "removeme",
            "url": "http://removeme:8080",
            "transport": "sse",
            "timeout": 30,
            "headers": {},
        }

        response = client.delete("/api/v1/mcp/servers/removeme")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["tools_removed"] == 2  # From mock
        assert "removeme" not in _RUNTIME_MCP_SERVERS

    def test_remove_env_server_fails(
        self, client, mock_get_enabled_mcp_servers
    ):
        """Test that removing environment-configured server fails."""
        response = client.delete("/api/v1/mcp/servers/env_server")
        assert response.status_code == 400
        assert "environment variables" in response.json()["detail"]

    def test_remove_nonexistent_server(
        self, client, mock_get_enabled_mcp_servers
    ):
        """Test removing non-existent server."""
        response = client.delete("/api/v1/mcp/servers/notfound")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════════
# LIST TOOLS ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestListTools:
    """Tests for GET /tools endpoint."""

    def test_list_all_tools(self, client, mock_list_mcp_tools):
        """Test listing all MCP tools."""
        mock_list_mcp_tools.return_value = [
            "server1_tool1",
            "server1_tool2",
            "server2_tool1",
        ]

        response = client.get("/api/v1/mcp/tools")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 3
        assert len(data["tools"]) == 3
        assert "server1" in data["by_server"]
        assert "server2" in data["by_server"]

    def test_list_tools_filtered_by_server(self, client, mock_list_mcp_tools):
        """Test listing tools filtered by server."""
        mock_list_mcp_tools.return_value = ["server1_tool1", "server1_tool2"]

        response = client.get("/api/v1/mcp/tools?server=server1")
        assert response.status_code == 200

        data = response.json()
        assert data["filter"]["server"] == "server1"
        mock_list_mcp_tools.assert_called_with(mcp_server="server1")

    def test_list_tools_empty(self, client, mock_list_mcp_tools):
        """Test listing tools when none registered."""
        mock_list_mcp_tools.return_value = []

        response = client.get("/api/v1/mcp/tools")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["tools"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# OAUTH ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestOAuthFlow:
    """Tests for OAuth endpoints."""

    def test_oauth_start_success(self, client):
        """Test starting OAuth flow."""
        response = client.post(
            "/api/v1/mcp/oauth/start",
            json={
                "name": "oauthserver",
                "url": "http://oauthserver:8080",
                "oauth": {
                    "client_id": "test-client-id",
                    "auth_url": "https://auth.example.com/authorize",
                    "token_url": "https://auth.example.com/token",
                    "scope": "openid profile",
                },
                "redirect_uri": "http://localhost:3000/callback",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert "auth_url" in data
        assert "state" in data
        assert data["auth_url"].startswith("https://auth.example.com/authorize")
        assert "client_id=test-client-id" in data["auth_url"]
        assert "code_challenge=" in data["auth_url"]
        assert "code_challenge_method=S256" in data["auth_url"]

        # Verify state was stored
        assert data["state"] in _OAUTH_PENDING_STATES

    def test_oauth_callback_success(self, client):
        """Test completing OAuth flow."""
        # Setup pending state
        state = "test-state-123"
        _OAUTH_PENDING_STATES[state] = {
            "name": "oauthserver",
            "url": "http://oauthserver:8080",
            "oauth": {
                "client_id": "test-client-id",
                "auth_url": "https://auth.example.com/authorize",
                "token_url": "https://auth.example.com/token",
            },
            "redirect_uri": "http://localhost:3000/callback",
            "code_verifier": "test-verifier",
            "created_at": time.time(),
        }

        with patch("apps.artagent.backend.api.v1.endpoints.mcp.httpx.AsyncClient") as mock:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "expires_in": 3600,
            }
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock.return_value = mock_client

            response = client.post(
                "/api/v1/mcp/oauth/callback",
                json={"code": "auth-code-123", "state": state},
            )
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert data["server_name"] == "oauthserver"
            assert data["has_token"] is True

            # Verify token was stored
            assert "oauthserver" in _RUNTIME_MCP_SERVERS
            assert "Authorization" in _RUNTIME_MCP_SERVERS["oauthserver"]["headers"]

    def test_oauth_callback_invalid_state(self, client):
        """Test OAuth callback with invalid state."""
        response = client.post(
            "/api/v1/mcp/oauth/callback",
            json={"code": "auth-code-123", "state": "invalid-state"},
        )
        assert response.status_code == 400
        assert "Invalid or expired" in response.json()["detail"]

    def test_oauth_callback_expired_state(self, client):
        """Test OAuth callback with expired state."""
        state = "expired-state"
        _OAUTH_PENDING_STATES[state] = {
            "name": "oauthserver",
            "url": "http://oauthserver:8080",
            "oauth": {"client_id": "test", "auth_url": "x", "token_url": "x"},
            "redirect_uri": "http://localhost:3000/callback",
            "code_verifier": "test-verifier",
            "created_at": time.time() - 700,  # More than 10 minutes ago
        }

        response = client.post(
            "/api/v1/mcp/oauth/callback",
            json={"code": "auth-code-123", "state": state},
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"]

    def test_oauth_callback_token_exchange_fails(self, client):
        """Test OAuth callback when token exchange fails."""
        state = "test-state"
        _OAUTH_PENDING_STATES[state] = {
            "name": "oauthserver",
            "url": "http://oauthserver:8080",
            "oauth": {
                "client_id": "test",
                "auth_url": "https://auth.example.com/authorize",
                "token_url": "https://auth.example.com/token",
            },
            "redirect_uri": "http://localhost:3000/callback",
            "code_verifier": "test-verifier",
            "created_at": time.time(),
        }

        with patch("apps.artagent.backend.api.v1.endpoints.mcp.httpx.AsyncClient") as mock:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Invalid client credentials"
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock.return_value = mock_client

            response = client.post(
                "/api/v1/mcp/oauth/callback",
                json={"code": "bad-code", "state": state},
            )
            assert response.status_code == 401
            assert "Token exchange failed" in response.json()["detail"]

    def test_oauth_status_authenticated(self, client):
        """Test OAuth status for authenticated server."""
        _RUNTIME_MCP_SERVERS["authserver"] = {
            "name": "authserver",
            "url": "http://authserver:8080",
            "transport": "sse",
            "timeout": 30,
            "headers": {"Authorization": "Bearer test-token"},
            "oauth_tokens": {"access_token": "test", "refresh_token": "refresh"},
        }

        response = client.get("/api/v1/mcp/oauth/status/authserver")
        assert response.status_code == 200

        data = response.json()
        assert data["server"] == "authserver"
        assert data["authenticated"] is True
        assert data["oauth_configured"] is True
        assert data["has_refresh_token"] is True

    def test_oauth_status_not_authenticated(self, client):
        """Test OAuth status for non-authenticated server."""
        response = client.get("/api/v1/mcp/oauth/status/unknown")
        assert response.status_code == 200

        data = response.json()
        assert data["authenticated"] is False
        assert data["oauth_configured"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestMCPAPIIntegration:
    """Integration tests for MCP API workflow."""

    def test_full_server_lifecycle(
        self,
        client,
        mock_get_enabled_mcp_servers,
        mock_httpx_client,
        mock_mcp_session,
        mock_register_mcp_tool,
        mock_unregister_mcp_tools,
        mock_list_mcp_tools,
    ):
        """Test full lifecycle: test -> add -> list -> remove."""
        # 1. Test connection
        test_response = client.post(
            "/api/v1/mcp/servers/test",
            json={"name": "lifecycle", "url": "http://lifecycle:8080"},
        )
        assert test_response.status_code == 200
        assert test_response.json()["connected"] is True

        # 2. Add server
        add_response = client.post(
            "/api/v1/mcp/servers",
            json={"name": "lifecycle", "url": "http://lifecycle:8080"},
        )
        assert add_response.status_code == 200
        assert add_response.json()["server"]["name"] == "lifecycle"

        # 3. List servers to verify
        mock_list_mcp_tools.return_value = ["lifecycle_test_tool", "env_server_tool1"]
        list_response = client.get("/api/v1/mcp/servers")
        assert list_response.status_code == 200
        server_names = [s["name"] for s in list_response.json()["servers"]]
        assert "lifecycle" in server_names

        # 4. Remove server
        remove_response = client.delete("/api/v1/mcp/servers/lifecycle")
        assert remove_response.status_code == 200
        assert "lifecycle" not in _RUNTIME_MCP_SERVERS

    def test_auth_token_flow(
        self,
        client,
        mock_get_enabled_mcp_servers,
        mock_httpx_client,
        mock_mcp_session,
        mock_register_mcp_tool,
    ):
        """Test adding server with auth and verifying headers are used."""
        # Add server with auth token
        response = client.post(
            "/api/v1/mcp/servers",
            json={
                "name": "secureserver",
                "url": "http://secure:8080",
                "auth_token": "secret-token-123",
            },
        )
        assert response.status_code == 200
        assert response.json()["server"]["has_auth"] is True

        # Verify headers are stored
        stored = _RUNTIME_MCP_SERVERS["secureserver"]
        assert stored["headers"]["Authorization"] == "Bearer secret-token-123"
