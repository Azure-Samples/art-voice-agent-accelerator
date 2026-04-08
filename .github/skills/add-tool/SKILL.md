---
name: add-tool
description: Add a new tool to the agent toolstore registry
---

# Add Tool Skill

Add tools to `apps/artagent/backend/registries/toolstore/`.

## Tool File Structure

```python
"""
Tool Module Name
================

Brief description of tools in this module.
"""

from __future__ import annotations

from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.module_name")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

tool_name_schema: dict[str, Any] = {
    "name": "tool_name",
    "description": "Clear description of what this tool does and when to use it.",
    "parameters": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Parameter description"},
            "param2": {"type": "integer", "description": "Optional param"},
        },
        "required": ["param1"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_name(args: dict[str, Any]) -> dict[str, Any]:
    """Execute the tool with given arguments."""
    param1 = (args.get("param1") or "").strip()

    if not param1:
        return {"success": False, "message": "param1 is required."}

    # Tool implementation
    logger.info("Tool executed: %s", param1)

    return {
        "success": True,
        "result": "Tool output",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "tool_name",
    tool_name_schema,
    tool_name,
    tags={"category1", "category2"},
)
```

## Steps

1. Create or edit file in `registries/toolstore/`
2. Define OpenAI-compatible schema with name, description, parameters
3. Implement async executor function that takes `args: dict[str, Any]`
4. Register tool with `register_tool()` at module level
5. Import module in `registry.py` `initialize_tools()` function
6. Add tool name to agent's `tools:` list in their `agent.yaml`

## Registration Function

```python
register_tool(
    name="tool_name",           # Unique identifier
    schema=tool_name_schema,    # OpenAI function schema
    executor=tool_name,         # Async function
    is_handoff=False,           # True if triggers agent transfer
    tags={"category"},          # Optional categorization
    override=False,             # Allow re-registration
)
```

## Handoff Tools

For agent transfer tools, use `is_handoff=True`:

```python
handoff_specialist_schema = {
    "name": "handoff_specialist",
    "description": "Transfer to specialist agent for [reason].",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why transferring"},
            "context": {"type": "string", "description": "Relevant context"},
        },
        "required": ["reason"],
    },
}

async def handoff_specialist(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "handoff": True,
        "target_agent": "specialist",
        "reason": args.get("reason", ""),
    }

register_tool(
    "handoff_specialist",
    handoff_specialist_schema,
    handoff_specialist,
    is_handoff=True,
    tags={"handoff"},
)
```

## Return Format

Always return dict with:
- `success: bool` - Whether operation succeeded
- `message: str` - Error message if failed
- Additional result fields as needed

## Registry Location

`apps/artagent/backend/registries/toolstore/registry.py`

Key functions:
- `register_tool()` - Register a tool
- `get_tools_for_agent(tool_names)` - Get schemas for agent
- `execute_tool(name, args)` - Execute a tool
- `initialize_tools()` - Load all tool modules
