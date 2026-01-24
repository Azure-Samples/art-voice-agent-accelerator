"""
Tool Registry Core
==================

Central registry for all agent tools.
Self-contained - does not reference legacy vlagent/artagent structures.

Usage:
    from apps.artagent.backend.registries.toolstore.registry import (
        register_tool,
        get_tools_for_agent,
        execute_tool,
        initialize_tools,
    )
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from pydantic import BaseModel
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.registry")

# Type aliases
ToolExecutor: TypeAlias = Callable[..., Any]
AsyncToolExecutor: TypeAlias = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class ToolDefinition:
    """Complete tool definition with schema and executor."""

    name: str
    schema: dict[str, Any]
    executor: ToolExecutor
    is_handoff: bool = False
    description: str = ""
    tags: set[str] = field(default_factory=set)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY STATE
# ═══════════════════════════════════════════════════════════════════════════════

_TOOL_DEFINITIONS: dict[str, ToolDefinition] = {}
_INITIALIZED: bool = False


def register_tool(
    name: str,
    schema: dict[str, Any],
    executor: ToolExecutor,
    *,
    is_handoff: bool = False,
    tags: set[str] | None = None,
    override: bool = False,
) -> None:
    """
    Register a tool with schema and executor.

    :param name: Unique tool name
    :param schema: OpenAI-compatible function schema
    :param executor: Callable implementation (sync or async)
    :param is_handoff: True if tool triggers agent handoff
    :param tags: Optional categorization tags (e.g., {'banking', 'auth'})
    :param override: If True, allow overriding existing registration
    """
    if name in _TOOL_DEFINITIONS and not override:
        logger.debug("Tool '%s' already registered, skipping", name)
        return

    _TOOL_DEFINITIONS[name] = ToolDefinition(
        name=name,
        schema=schema,
        executor=executor,
        is_handoff=is_handoff,
        description=schema.get("description", ""),
        tags=tags or set(),
    )
    logger.debug("Registered tool: %s (handoff=%s)", name, is_handoff)


def get_tool_schema(name: str) -> dict[str, Any] | None:
    """Get the schema for a registered tool."""
    defn = _TOOL_DEFINITIONS.get(name)
    return defn.schema if defn else None


def get_tool_executor(name: str) -> ToolExecutor | None:
    """Get the executor for a registered tool."""
    defn = _TOOL_DEFINITIONS.get(name)
    return defn.executor if defn else None


def get_tool_definition(name: str) -> ToolDefinition | None:
    """Get the complete definition for a tool."""
    return _TOOL_DEFINITIONS.get(name)


def is_handoff_tool(name: str) -> bool:
    """Check if a tool triggers agent handoff."""
    defn = _TOOL_DEFINITIONS.get(name)
    return defn.is_handoff if defn else False


def list_tools(*, tags: set[str] | None = None, handoffs_only: bool = False) -> list[str]:
    """
    List registered tool names with optional filtering.

    :param tags: Only return tools with ALL specified tags
    :param handoffs_only: Only return handoff tools
    """
    result = []
    for name, defn in _TOOL_DEFINITIONS.items():
        if handoffs_only and not defn.is_handoff:
            continue
        if tags and not tags.issubset(defn.tags):
            continue
        result.append(name)
    return result


def get_tools_for_agent(tool_names: list[str]) -> list[dict[str, Any]]:
    """
    Build OpenAI-compatible tool list for specified tools.

    :param tool_names: List of tool names to include
    :return: List of {"type": "function", "function": schema} dicts
    """
    tools = []
    for name in tool_names:
        defn = _TOOL_DEFINITIONS.get(name)
        if defn:
            tools.append({"type": "function", "function": defn.schema})
        else:
            logger.warning("Tool '%s' not found in registry", name)
    return tools


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _prepare_args(
    fn: Callable[..., Any], raw_args: dict[str, Any]
) -> tuple[list[Any], dict[str, Any]]:
    """Coerce dict arguments into the tool's declared signature."""
    signature = inspect.signature(fn)
    params = list(signature.parameters.values())

    if not params:
        return [], {}

    if len(params) == 1:
        param = params[0]
        annotation = param.annotation
        if annotation is not inspect._empty and inspect.isclass(annotation):
            try:
                if issubclass(annotation, BaseModel):
                    return [annotation(**raw_args)], {}
            except TypeError:
                pass
        return [raw_args], {}

    return [], raw_args


async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a registered tool with the given arguments.

    Handles both sync and async executors.
    """
    defn = _TOOL_DEFINITIONS.get(name)
    if not defn:
        return {
            "success": False,
            "error": f"Tool '{name}' not found",
            "message": f"Tool '{name}' is not registered.",
        }

    fn = defn.executor
    positional, keyword = _prepare_args(fn, arguments)

    try:
        if inspect.iscoroutinefunction(fn):
            result = await fn(*positional, **keyword)
        else:
            result = await asyncio.to_thread(fn, *positional, **keyword)

        # Normalize result
        if isinstance(result, dict):
            return result
        return {"success": True, "result": result}

    except Exception as exc:
        logger.exception("Tool '%s' execution failed", name)
        return {
            "success": False,
            "error": str(exc),
            "message": f"Tool execution failed: {exc}",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════


def initialize_tools() -> int:
    """
    Load and register all tools.
    
    Robust loading: if individual tool modules fail to import, they are logged
    as warnings but do not prevent other tools from loading.

    Returns the number of tools registered.
    """
    global _INITIALIZED

    if _INITIALIZED:
        logger.debug("Tools already initialized, skipping")
        return len(_TOOL_DEFINITIONS)

    # Import tool modules - this triggers their registration
    # Each module registers its tools at import time via register_tool()
    # Wrapped in try-except to prevent single tool failures from breaking all tools
    
    tool_modules = [
        ("auth", lambda: __import__("apps.artagent.backend.registries.toolstore.auth", fromlist=[""])),
        ("call_transfer", lambda: __import__("apps.artagent.backend.registries.toolstore.call_transfer", fromlist=[""])),
        ("compliance", lambda: __import__("apps.artagent.backend.registries.toolstore.compliance", fromlist=[""])),
        ("customer_intelligence", lambda: __import__("apps.artagent.backend.registries.toolstore.customer_intelligence", fromlist=[""])),
        ("escalation", lambda: __import__("apps.artagent.backend.registries.toolstore.escalation", fromlist=[""])),
        ("fraud", lambda: __import__("apps.artagent.backend.registries.toolstore.fraud", fromlist=[""])),
        ("handoffs", lambda: __import__("apps.artagent.backend.registries.toolstore.handoffs", fromlist=[""])),
        ("knowledge_base", lambda: __import__("apps.artagent.backend.registries.toolstore.knowledge_base", fromlist=[""])),
        ("personalized_greeting", lambda: __import__("apps.artagent.backend.registries.toolstore.personalized_greeting", fromlist=[""])),
        ("rag_retrieval", lambda: __import__("apps.artagent.backend.registries.toolstore.rag_retrieval", fromlist=[""])),
        ("transfer_agency", lambda: __import__("apps.artagent.backend.registries.toolstore.transfer_agency", fromlist=[""])),
        ("voicemail", lambda: __import__("apps.artagent.backend.registries.toolstore.voicemail", fromlist=[""])),
        # ("document_intelligence", lambda: __import__("apps.artagent.backend.registries.toolstore.document_intelligence", fromlist=[""])),
        # Banking tools
        ("banking.banking", lambda: __import__("apps.artagent.backend.registries.toolstore.banking.banking", fromlist=[""])),
        ("banking.investments", lambda: __import__("apps.artagent.backend.registries.toolstore.banking.investments", fromlist=[""])),
        # Insurance tools
        ("insurance.fnol", lambda: __import__("apps.artagent.backend.registries.toolstore.insurance.fnol", fromlist=[""])),
        ("insurance.policy", lambda: __import__("apps.artagent.backend.registries.toolstore.insurance.policy", fromlist=[""])),
        ("insurance.subro", lambda: __import__("apps.artagent.backend.registries.toolstore.insurance.subro", fromlist=[""])),
    ]
    
    failed_modules = []
    for module_name, import_func in tool_modules:
        try:
            import_func()
            logger.debug(f"✓ Loaded tool module: {module_name}")
        except Exception as e:
            failed_modules.append(module_name)
            logger.warning(
                f"Failed to load tool module '{module_name}': {type(e).__name__}: {e}",
                exc_info=False  # Set to True for full stack trace in debug mode
            )

    _INITIALIZED = True
    
    if failed_modules:
        logger.warning(
            f"Tool registry initialized with {len(_TOOL_DEFINITIONS)} tools. "
            f"Failed to load {len(failed_modules)} modules: {', '.join(failed_modules)}"
        )
    else:
        logger.info(f"Tool registry initialized successfully with {len(_TOOL_DEFINITIONS)} tools")
    
    return len(_TOOL_DEFINITIONS)


def reset_registry() -> None:
    """Reset the registry (for testing)."""
    global _INITIALIZED
    _TOOL_DEFINITIONS.clear()
    _INITIALIZED = False


__all__ = [
    "register_tool",
    "get_tool_schema",
    "get_tool_executor",
    "get_tool_definition",
    "is_handoff_tool",
    "list_tools",
    "get_tools_for_agent",
    "execute_tool",
    "initialize_tools",
    "reset_registry",
    "ToolDefinition",
    "ToolExecutor",
]
