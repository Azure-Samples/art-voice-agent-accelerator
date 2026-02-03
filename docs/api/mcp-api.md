# MCP API Reference

Runtime API for managing MCP (Model Context Protocol) servers. These endpoints enable you to connect to MCP servers, discover tools, and make them available to agents—all without restarting the application.

!!! abstract "Context-Driven Agents"
    MCP is fundamentally about providing agents with the context they need to succeed. Each MCP server you connect exposes tools and resources that enrich agent knowledge, enabling more accurate and helpful responses. See the [MCP Integration Guide](../architecture/registries/mcp-integration.md) for architecture details and context management best practices.

!!! info "Startup Behavior"
    MCP servers configured via environment variables are validated and registered during **deferred startup**—the application starts accepting requests immediately while MCP connections are established in the background. Use `/api/v1/ready` to check MCP tool availability.

---

## Base URL

```
/api/v1/mcp
```

---

## Transport Types

The MCP client supports the following transport protocols (per MCP spec 2025-11-25):

| Transport | Value | Description |
|:----------|:------|:------------|
| **Streamable HTTP** | `streamable-http` | Recommended for deployed servers (default) |
| **SSE** | `sse` | Server-Sent Events (legacy, still supported) |
| **HTTP** | `http` | Alias for streamable-http |
| **STDIO** | `stdio` | Standard I/O for local CLI tools |

---

## Server Management

### List MCP Servers

:material-format-list-bulleted: Get all configured MCP servers with their current status and discovered tools.

=== "Request"

    ```http
    GET /api/v1/mcp/servers
    ```

=== "Response"

    ```json
    {
      "servers": [
        {
          "name": "cardapi",
          "url": "http://cardapi-mcp:8080",
          "transport": "streamable-http",
          "timeout": 30.0,
          "status": "healthy",
          "tools_count": 4,
          "tool_names": [
            "cardapi_lookup_decline_code",
            "cardapi_search_decline_codes",
            "cardapi_get_all_decline_codes",
            "cardapi_get_decline_codes_metadata"
          ],
          "error": null,
          "source": "environment",
          "has_auth": false
        },
        {
          "name": "knowledge",
          "url": "http://kb-server:8080",
          "transport": "http",
          "timeout": 30.0,
          "status": "unhealthy",
          "tools_count": 0,
          "tool_names": [],
          "error": "Connection refused",
          "source": "runtime",
          "has_auth": true
        }
      ],
      "total": 2,
      "healthy": 1,
      "unhealthy": 1
    }
    ```

??? info "Response Fields"

    | Field | Type | Description |
    |:------|:-----|:------------|
    | `name` | string | Unique server identifier |
    | `url` | string | MCP server base URL |
    | `transport` | string | Transport type: `sse`, `http`, or `stdio` |
    | `timeout` | number | Connection timeout in seconds |
    | `status` | string | `healthy`, `unhealthy`, or `unknown` |
    | `tools_count` | number | Number of discovered tools |
    | `tool_names` | string[] | List of registered tool names (prefixed) |
    | `error` | string | Error message if unhealthy |
    | `source` | string | `environment` (from env vars) or `runtime` (added via API) |
    | `has_auth` | boolean | Whether authentication is configured |

---

### Add MCP Server

:material-plus-circle: Connect to a new MCP server and register its discovered tools.

=== "Request"

    ```http
    POST /api/v1/mcp/servers
    Content-Type: application/json
    ```
    
    ```json
    {
      "name": "myserver",
      "url": "http://mcp-server:8080",
      "transport": "sse",
      "timeout": 30,
      "auth_token": "optional-bearer-token",
      "headers": {
        "X-Custom-Header": "value"
      },
      "oauth": null
    }
    ```

=== "Response (Success)"

    ```json
    {
      "status": "success",
      "message": "MCP server 'myserver' connected and 3 tools registered",
      "server": {
        "name": "myserver",
        "url": "http://mcp-server:8080",
        "transport": "sse",
        "timeout": 30.0,
        "status": "healthy",
        "tools_count": 3,
        "tool_names": [
          "myserver_tool_a",
          "myserver_tool_b",
          "myserver_tool_c"
        ],
        "has_auth": true
      },
      "response_time_ms": 234.5
    }
    ```

=== "Response (Error)"

    ```json
    {
      "detail": "MCP server 'myserver' already exists. Use DELETE first to replace it."
    }
    ```

??? info "Request Fields"

    | Field | Type | Required | Description |
    |:------|:-----|:--------:|:------------|
    | `name` | string | :material-check: | Unique identifier (lowercase, alphanumeric, hyphens, underscores) |
    | `url` | string | :material-check: | HTTP endpoint URL |
    | `transport` | string | | Transport type: `sse` (default), `http`, or `stdio` |
    | `timeout` | number | | Connection timeout in seconds (default: 30) |
    | `auth_token` | string | | Bearer token for Authorization header |
    | `headers` | object | | Custom HTTP headers |
    | `oauth` | object | | OAuth configuration (see [OAuth section](#oauth-authentication)) |

---

### Test MCP Connection

:material-connection: Test connection to an MCP server and discover tools without registering them.

!!! tip "Use Before Adding"
    Always test connections before adding servers to verify connectivity and preview available tools.

=== "Request"

    ```http
    POST /api/v1/mcp/servers/test
    Content-Type: application/json
    ```
    
    ```json
    {
      "name": "myserver",
      "url": "http://mcp-server:8080"
    }
    ```

=== "Response"

    ```json
    {
      "status": "healthy",
      "url": "http://mcp-server:8080",
      "connected": true,
      "tools_count": 3,
      "tools": [
        {
          "name": "tool_a",
          "prefixed_name": "myserver_tool_a",
          "description": "Description of tool A",
          "server_name": "myserver",
          "input_schema": {
            "type": "object",
            "properties": {
              "param1": {"type": "string"}
            },
            "required": ["param1"]
          }
        }
      ],
      "error": null,
      "response_time_ms": 156.2
    }
    ```

**Status Values:**

| Status | Meaning |
|:-------|:--------|
| :material-check-circle:{ .green } `healthy` | Connected and tools discovered |
| :material-alert-circle:{ .yellow } `connected` | Connection successful but no tools found |
| :material-close-circle:{ .red } `unhealthy` | Health check failed |
| :material-alert:{ .red } `error` | URL validation or connection error |

---

### Remove MCP Server

:material-minus-circle: Remove an MCP server and unregister all its tools.

!!! warning "Runtime Only"
    Only servers added via the API can be removed. Servers configured via environment variables require a restart to remove.

=== "Request"

    ```http
    DELETE /api/v1/mcp/servers/{name}
    ```

=== "Response (Success)"

    ```json
    {
      "status": "success",
      "message": "MCP server 'myserver' removed successfully",
      "tools_removed": 3,
      "response_time_ms": 12.4
    }
    ```

=== "Response (Error)"

    ```json
    {
      "detail": "MCP server 'cardapi' is configured via environment variables. To remove it, update MCP_ENABLED_SERVERS and restart the application."
    }
    ```

**Path Parameters:**

| Name | Type | Description |
|:-----|:-----|:------------|
| `name` | string | Server name to remove |

---

## Tool Discovery

### List All MCP Tools

:material-tools: Get all registered MCP tools across all servers.

=== "Request"

    ```http
    GET /api/v1/mcp/tools
    GET /api/v1/mcp/tools?server=cardapi
    ```

=== "Response"

    ```json
    {
      "status": "success",
      "total": 7,
      "tools": [
        "cardapi_lookup_decline_code",
        "cardapi_search_decline_codes",
        "cardapi_get_all_decline_codes",
        "cardapi_get_decline_codes_metadata",
        "knowledge_search_articles",
        "knowledge_get_article",
        "knowledge_list_categories"
      ],
      "by_server": {
        "cardapi": [
          "cardapi_lookup_decline_code",
          "cardapi_search_decline_codes",
          "cardapi_get_all_decline_codes",
          "cardapi_get_decline_codes_metadata"
        ],
        "knowledge": [
          "knowledge_search_articles",
          "knowledge_get_article",
          "knowledge_list_categories"
        ]
      },
      "filter": null,
      "response_time_ms": 2.1
    }
    ```

**Query Parameters:**

| Name | Type | Description |
|:-----|:-----|:------------|
| `server` | string | Filter by server name |

---

## OAuth Authentication

For MCP servers requiring OAuth 2.0 authentication.

### Start OAuth Flow

:material-login: Initiate OAuth authorization flow. Returns a URL to redirect the user for authentication.

=== "Request"

    ```http
    POST /api/v1/mcp/oauth/start
    Content-Type: application/json
    ```
    
    ```json
    {
      "name": "enterprise-mcp",
      "url": "https://mcp.enterprise.com",
      "oauth": {
        "client_id": "app-client-id",
        "auth_url": "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/tenant/oauth2/v2.0/token",
        "scope": "api://mcp-server/.default openid",
        "client_secret": null
      },
      "redirect_uri": "https://yourapp.com/oauth/callback.html"
    }
    ```

=== "Response"

    ```json
    {
      "auth_url": "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?client_id=...&response_type=code&redirect_uri=...&state=...&code_challenge=...&code_challenge_method=S256&scope=...",
      "state": "abc123_random_state_value"
    }
    ```

??? info "Request Fields"

    | Field | Type | Required | Description |
    |:------|:-----|:--------:|:------------|
    | `name` | string | :material-check: | MCP server name |
    | `url` | string | :material-check: | MCP server URL |
    | `oauth.client_id` | string | :material-check: | OAuth application client ID |
    | `oauth.auth_url` | string | :material-check: | Authorization endpoint URL |
    | `oauth.token_url` | string | :material-check: | Token endpoint URL |
    | `oauth.scope` | string | | OAuth scopes (space-separated) |
    | `oauth.client_secret` | string | | Client secret (if required) |
    | `redirect_uri` | string | :material-check: | OAuth callback URL |

!!! info "PKCE"
    The OAuth flow automatically uses PKCE (Proof Key for Code Exchange) with the S256 challenge method.

---

### Complete OAuth Flow

:material-check-decagram: Exchange the authorization code for an access token.

=== "Request"

    ```http
    POST /api/v1/mcp/oauth/callback
    Content-Type: application/json
    ```
    
    ```json
    {
      "code": "authorization_code_from_callback",
      "state": "state_from_start_response"
    }
    ```

=== "Response (Success)"

    ```json
    {
      "success": true,
      "server_name": "enterprise-mcp",
      "message": "Successfully authenticated with MCP server 'enterprise-mcp'",
      "has_token": true
    }
    ```

=== "Response (Error)"

    ```json
    {
      "detail": "Invalid or expired OAuth state. Please restart the authentication flow."
    }
    ```

---

### Check OAuth Status

:material-shield-check: Check if an MCP server has valid OAuth tokens.

=== "Request"

    ```http
    GET /api/v1/mcp/oauth/status/{name}
    ```

=== "Response"

    ```json
    {
      "server": "enterprise-mcp",
      "authenticated": true,
      "oauth_configured": true,
      "has_refresh_token": true
    }
    ```

---

## Error Codes

| HTTP Status | Meaning | Common Causes |
|:-----------:|:--------|:--------------|
| `200` | Success | Request completed |
| `400` | Bad Request | Validation error, duplicate server, invalid OAuth state |
| `401` | Unauthorized | OAuth token expired or invalid |
| `404` | Not Found | Server name doesn't exist |
| `502` | Bad Gateway | MCP server unreachable |

---

## Examples

### cURL

=== "List Servers"

    ```bash
    curl -s http://localhost:8000/api/v1/mcp/servers | jq
    ```

=== "Test Connection"

    ```bash
    curl -X POST http://localhost:8000/api/v1/mcp/servers/test \
      -H "Content-Type: application/json" \
      -d '{"name": "test", "url": "http://mcp-server:8080"}' | jq
    ```

=== "Add Server"

    ```bash
    curl -X POST http://localhost:8000/api/v1/mcp/servers \
      -H "Content-Type: application/json" \
      -d '{
        "name": "secure-mcp",
        "url": "https://api.example.com/mcp",
        "auth_token": "sk-abc123"
      }' | jq
    ```

=== "Remove Server"

    ```bash
    curl -X DELETE http://localhost:8000/api/v1/mcp/servers/myserver | jq
    ```

### Python

```python title="mcp_client.py"
import httpx

async def add_mcp_server():
    async with httpx.AsyncClient() as client:
        # Step 1: Test the connection
        response = await client.post(
            "http://localhost:8000/api/v1/mcp/servers/test",
            json={"name": "cardapi", "url": "http://cardapi:8080"}
        )
        test = response.json()
        print(f"Found {test['tools_count']} tools")
        
        # Step 2: Register if connected
        if test["connected"]:
            response = await client.post(
                "http://localhost:8000/api/v1/mcp/servers",
                json={"name": "cardapi", "url": "http://cardapi:8080"}
            )
            print(response.json()["message"])
```
