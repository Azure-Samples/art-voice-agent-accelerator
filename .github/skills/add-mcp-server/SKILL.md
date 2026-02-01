```skill
---
name: add-mcp-server
description: Add or integrate an MCP (Model Context Protocol) server for agent tools
---

# MCP Server Integration Skill

Integrate external tool servers via MCP protocol into the agent framework.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Agent YAML    │────▶│  Tool Registry   │────▶│   MCP Server    │
│  tools:         │     │  (prefixed tools)│     │ (streamable-http│
│   - cardapi_*   │     │                  │     │   or stdio)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Key References (read for deployment context):**
- `apps/cardapi/` - Complete reference implementation
- `infra/terraform/cardapi.tf` - Container App + IAM setup
- `devops/scripts/azd/postprovision.sh` - Data provisioning pattern
- `apps/artagent/backend/config/settings.py` - MCP configuration

---

## Intent 1: Create a New MCP Server

### Directory Structure (follow cardapi pattern)

```
apps/myserver/
├── README.md                 # Service documentation
├── Dockerfile.mcp            # Container build
├── mcp_app/
│   ├── __init__.py
│   ├── service.py            # FastMCP server
│   ├── pyproject.toml        # Dependencies (uv)
│   └── requirements.txt      # pip fallback
├── database/                 # Local dev data (optional)
│   └── data.json
└── scripts/
    ├── provision_data.py     # Cosmos DB seeding
    └── requirements.txt
```

### Server Implementation (FastMCP)

Per MCP spec 2025-11-25, use `streamable-http` transport for deployed servers:

```python
"""apps/myserver/mcp_app/service.py"""
import asyncio
import os
from typing import Literal

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Configuration
MCP_PORT = int(os.getenv("MCP_SERVER_PORT", "8080"))
MCP_TRANSPORT: Literal["stdio", "streamable-http"] = os.getenv(
    "MCP_TRANSPORT", "streamable-http"  # Default for deployed servers
)

mcp = FastMCP(
    name="my-server-name",
    instructions="Description for LLM context.",
)

# ═══════════════════════════════════════════════════════════════════
# TOOL IMPLEMENTATIONS (callable directly for HTTP handlers)
# ═══════════════════════════════════════════════════════════════════

async def _my_tool_impl(param: str) -> str:
    """Actual implementation - callable directly."""
    return f"Result for {param}"

# ═══════════════════════════════════════════════════════════════════
# MCP TOOL REGISTRATION (wrappers)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description for LLM. Args: param: What this param does."""
    return await _my_tool_impl(param)

# ═══════════════════════════════════════════════════════════════════
# HTTP REST ENDPOINTS (for backend tool executor)
# ═══════════════════════════════════════════════════════════════════

@mcp.custom_route("/tools/my_tool", methods=["GET"])
async def tools_my_tool(request: Request) -> Response:
    """REST endpoint - calls implementation directly."""
    param = request.query_params.get("param", "")
    result = await _my_tool_impl(param)
    return JSONResponse({"result": result})

# ═══════════════════════════════════════════════════════════════════
# HEALTH ENDPOINTS (required for Container Apps)
# ═══════════════════════════════════════════════════════════════════

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> Response:
    tools = mcp._tool_manager._tools
    return JSONResponse({
        "status": "healthy",
        "tools_count": len(tools),
        "tool_names": list(tools.keys()),
    })

@mcp.custom_route("/ready", methods=["GET"])
async def ready_check(request: Request) -> Response:
    return JSONResponse({"status": "ready"})

# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

async def main() -> None:
    if MCP_TRANSPORT == "stdio":
        await mcp.run_async(transport="stdio", show_banner=False)
    else:
        # streamable-http: serves MCP protocol AND health endpoints
        await mcp.run_http_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=MCP_PORT,
            show_banner=False,
        )

if __name__ == "__main__":
    asyncio.run(main())
```

**Critical Pattern:** Separate `_impl` functions from `@mcp.tool()`. The decorator returns `FunctionTool` (not callable). HTTP handlers must call `_impl` directly.

---

## Intent 2: Deploy as Container App (Recommended)

### Step 1: Dockerfile

```dockerfile
# apps/myserver/Dockerfile.mcp
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH="/app" PORT=80

COPY apps/myserver/mcp_app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared libs if needed (utils, src/cosmosdb)
COPY utils/ /app/utils/
COPY src/__init__.py /app/src/__init__.py
COPY src/cosmosdb/ /app/src/cosmosdb/

COPY apps/myserver/mcp_app/ /app/mcp_app/

WORKDIR /app/mcp_app
EXPOSE 80
CMD ["python", "service.py"]
```

### Step 2: azure.yaml

```yaml
services:
  # ...existing...
  myserver-mcp:
    project: .
    host: containerapp
    language: python
    docker:
      path: ./apps/myserver/Dockerfile.mcp
      context: .
      platform: linux/amd64
      remoteBuild: true
```

### Step 3: Terraform (`infra/terraform/myserver.tf`)

See `cardapi.tf` for full pattern. Key resources:

```terraform
# Managed Identity
resource "azurerm_user_assigned_identity" "myserver_mcp" {
  name                = "${var.name}-myserver-mcp-${local.resource_token}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

# Role assignments: AcrPull, App Configuration Reader, Key Vault Secrets User

# Container App
resource "azurerm_container_app" "myserver_mcp" {
  name                         = "myserver-mcp-${local.resource_token}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  # ... ingress, template, probes (see cardapi.tf)
  
  tags = merge(local.tags, { "azd-service-name" = "myserver-mcp" })
}

output "MYSERVER_MCP_CONTAINER_APP_URL" {
  value = "https://${azurerm_container_app.myserver_mcp.ingress[0].fqdn}"
}
```

### Step 4: Postprovision (if data seeding)

Add to `devops/scripts/azd/postprovision.sh`:

```bash
task_myserver_provision() {
    header "💾 MyServer Data Provisioning"
    # Follow cardapi pattern: get cosmos creds, run provision script
    python3 "$(pwd)/apps/myserver/scripts/provision_data.py"
    footer
}
```

### Step 5: App Config URL Sync

`devops/scripts/azd/helpers/sync-appconfig.sh`:

```bash
myserver_url=$(azd_get "MYSERVER_MCP_CONTAINER_APP_URL")
[[ -n "$myserver_url" ]] && appconfig_set "$endpoint" "app/mcp/servers/myserver/url" "${myserver_url}/mcp" "$label"
```

`config/appconfig_provider.py`:

```python
APPCONFIG_KEY_MAP = {
    "app/mcp/servers/myserver/url": "MCP_SERVER_MYSERVER_URL",
}
```

---

## Intent 3: Deploy as Azure Function (Alternative)

For event-driven/cost-optimized deployments:

```python
# apps/myserver/function_app.py
import azure.functions as func
import json
from mcp_app.service import _my_tool_impl

app = func.FunctionApp()

@app.route(route="tools/my_tool", methods=["GET"])
async def my_tool_http(req: func.HttpRequest) -> func.HttpResponse:
    result = await _my_tool_impl(req.params.get("param", ""))
    return func.HttpResponse(json.dumps({"result": result}), mimetype="application/json")
```

```yaml
# azure.yaml
services:
  myserver-mcp:
    project: apps/myserver
    host: function        # Instead of containerapp
    language: python
```

| Aspect | Container App | Function App |
|--------|--------------|--------------|
| Cold start | ~2-5s | ~5-15s |
| Min instances | 1+ | 0 (scale to zero) |
| Cost | Fixed min | Pay-per-execution |
| Best for | Always-on servers | Low-traffic tools |

---

## Intent 4: Configure Backend

### Environment Variables

```bash
# .env.local
MCP_ENABLED_SERVERS=cardapi,myserver
MCP_SERVER_MYSERVER_URL=http://localhost:8080/mcp
```

### settings.py

```python
MCP_SERVER_MYSERVER_URL: str = os.getenv("MCP_SERVER_MYSERVER_URL", "")

def get_enabled_mcp_servers() -> list[dict]:
    servers = []
    for name in MCP_ENABLED_SERVERS:
        if name == "myserver" and MCP_SERVER_MYSERVER_URL:
            servers.append({
                "name": "myserver",
                "url": MCP_SERVER_MYSERVER_URL,
                "transport": "streamable-http",
                "timeout": MCP_SERVER_TIMEOUT,
            })
    return servers
```

---

## Intent 5: Assign Tools to Agent

```yaml
# registries/agentstore/my_agent/agent.yaml
name: MyAgent
tools:
  - myserver_my_tool        # Prefixed: {server}_{tool}
  - myserver_another_tool
  - local_tool              # Mix with native tools
```

---

## Quick Reference

| Task | File(s) |
|------|---------|
| MCP server code | `apps/{name}/mcp_app/service.py` |
| Dockerfile | `apps/{name}/Dockerfile.mcp` |
| azure.yaml | Add service entry |
| Terraform | `infra/terraform/{name}.tf` |
| Postprovision | `devops/scripts/azd/postprovision.sh` |
| App Config sync | `devops/scripts/azd/helpers/sync-appconfig.sh` |
| Config mapping | `config/appconfig_provider.py` |
| Settings | `config/settings.py` |

## Transport Types (MCP Spec 2025-11-25)

| Transport | Use Case |
|-----------|----------|
| `streamable-http` | Deployed servers (recommended) |
| `stdio` | Local CLI development |
| `sse` | Legacy (deprecated) |

## Common Issues

| Issue | Fix |
|-------|-----|
| `FunctionTool not callable` | Use separate `_impl` function |
| Tool not found | Add to `MCP_ENABLED_SERVERS` |
| Health check fails | Add `/health` endpoint |
| Deferred startup | Check `/api/v1/ready` |

```
