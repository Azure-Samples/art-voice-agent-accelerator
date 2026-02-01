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
│  mcp_servers:   │     │  (prefixed tools)│     │  (HTTP + stdio) │
│    - cardapi    │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Key Files:**
- `apps/cardapi/mcp_app/service.py` - Example MCP server (FastMCP)
- `apps/artagent/backend/config/settings.py` - Server configurations
- `apps/artagent/backend/lifecycle/steps.py` - Startup registration
- `apps/artagent/backend/registries/toolstore/mcp/` - MCP client modules

---

## Intent 1: Create a New MCP Server

### Server Structure (FastMCP)

```python
"""apps/myserver/mcp_app/service.py"""
from fastmcp import FastMCP
from aiohttp import web
import asyncio

mcp = FastMCP("my-server-name")
HEALTH_PORT = 8081  # Avoid port conflicts

# ═══════════════════════════════════════════════════════════════════
# TOOL IMPLEMENTATIONS (separate from MCP registration)
# ═══════════════════════════════════════════════════════════════════

async def _my_tool_impl(param: str) -> str:
    """Actual implementation - callable directly."""
    return f"Result for {param}"

# ═══════════════════════════════════════════════════════════════════
# MCP TOOL REGISTRATION
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description for LLM. Args: param: What this param does."""
    return await _my_tool_impl(param)

# ═══════════════════════════════════════════════════════════════════
# HTTP ENDPOINTS (for health checks and tool execution)
# ═══════════════════════════════════════════════════════════════════

async def health_check(request: web.Request) -> web.Response:
    tools = mcp._tool_manager._tools
    return web.json_response({
        "status": "healthy",
        "tools_count": len(tools),
        "tool_names": list(tools.keys()),
    })

async def tools_list(request: web.Request) -> web.Response:
    """Return tool schemas for discovery."""
    tools = mcp._tool_manager._tools
    return web.json_response({
        "tools": [
            {
                "name": name,
                "description": getattr(t, 'description', ''),
                "input_schema": {"type": "object", "properties": {}},
            }
            for name, t in tools.items()
        ]
    })

async def my_tool_http(request: web.Request) -> web.Response:
    """HTTP wrapper - calls implementation directly."""
    param = request.query.get("param", "")
    try:
        result = await _my_tool_impl(param)
        return web.json_response({"success": True, "result": result})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def run_health_server() -> None:
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/tools/list", tools_list)
    app.router.add_get("/tools/my_tool", my_tool_http)
    
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", HEALTH_PORT).start()
    await asyncio.Event().wait()

async def main() -> None:
    asyncio.create_task(run_health_server())
    await asyncio.sleep(1)
    await mcp.run_async(transport="stdio")

if __name__ == "__main__":
    asyncio.run(main())
```

**Critical Pattern:** Separate `_impl` functions from `@mcp.tool()` decorated functions. The decorator returns a `FunctionTool` object (not callable). HTTP handlers must call `_impl` directly.

---

## Intent 2: Configure MCP Server in Backend

### 1. Add to settings.py

```python
# apps/artagent/backend/config/settings.py

MCP_ENABLED_SERVERS: list[str] = _env_list("MCP_ENABLED_SERVERS", "cardapi,myserver")

MCP_SERVER_CONFIGS: dict[str, dict] = {
    "myserver": {
        "url": os.environ.get("MCP_MYSERVER_URL", "http://localhost:8081"),
        "transport": "sse",
        "timeout": 30.0,
    },
}
```

### 2. Set Environment Variable

```bash
# .env.local
MCP_ENABLED_SERVERS=cardapi,myserver
MCP_MYSERVER_URL=http://localhost:8081
```

### 3. Startup Registration (Automatic)

The `register_mcp_servers_step` in `lifecycle/steps.py` automatically:
1. Checks `/health` endpoint
2. Fetches `/tools/list` for tool discovery
3. Registers tools with prefix: `{server}_{tool_name}`
4. Creates HTTP executors for each tool

---

## Intent 3: Assign MCP Tools to an Agent

### Agent YAML Configuration

```yaml
# registries/agentstore/my_agent/agent.yaml
name: MyAgent
description: Agent that uses MCP tools

mcp_servers:
  - myserver  # Enables all tools from this server

tools:
  - myserver_my_tool        # Explicit tool reference
  - myserver_another_tool   # Prefixed with server name
  - local_tool              # Can mix with local tools
```

**Tool Naming:** MCP tools are prefixed with server name: `{server}_{original_name}`

---

## Intent 4: Test MCP Integration

### Health Check
```bash
curl http://localhost:8081/health
# {"status": "healthy", "tools_count": 2, "tool_names": ["my_tool", "another_tool"]}
```

### Tool Discovery
```bash
curl http://localhost:8081/tools/list
# {"tools": [{"name": "my_tool", "description": "...", "input_schema": {...}}]}
```

### Direct Tool Call
```bash
curl "http://localhost:8081/tools/my_tool?param=test"
# {"success": true, "result": "Result for test"}
```

### Via Backend (after startup)
```bash
curl -X POST http://localhost:5001/api/v1/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "myserver_my_tool", "arguments": {"param": "test"}}'
```

---

## Intent 5: Add MCP to Evaluations

MCP servers are auto-initialized in `tests/evaluation/scenario_runner.py`:

```python
# Called automatically in ScenarioRunner.run() and ComparisonRunner.run()
await _ensure_mcp_initialized()
```

No additional configuration needed if server is in `MCP_ENABLED_SERVERS`.

---

## Quick Reference

| Task | Location |
|------|----------|
| New MCP server | `apps/{name}/mcp_app/service.py` |
| Server config | `config/settings.py` → `MCP_SERVER_CONFIGS` |
| Enable server | `.env.local` → `MCP_ENABLED_SERVERS` |
| Assign to agent | Agent's `agent.yaml` → `mcp_servers:` |
| MCP client code | `registries/toolstore/mcp/` |
| Startup step | `lifecycle/steps.py` → `register_mcp_servers_step` |
| Eval bootstrap | `tests/evaluation/scenario_runner.py` |

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `FunctionTool not callable` | Calling `@mcp.tool()` function directly | Create separate `_impl` function |
| Tool not found in registry | Server not in `MCP_ENABLED_SERVERS` | Add to env var |
| HTTP 500 on tool endpoint | Missing try/except in HTTP handler | Wrap with error handling |
| Tools not in agent | Missing `mcp_servers:` in agent.yaml | Add server name to list |

```
