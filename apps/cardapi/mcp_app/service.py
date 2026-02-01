"""
MCP Server for Card Decline Code Lookup.
Provides Model Context Protocol interface for AI agents to query decline codes.

Uses FastMCP for clean decorator-based tool/resource/prompt definitions.

Self-contained server that loads data directly from:
1. Azure Cosmos DB (when AZURE_COSMOS_CONNECTION_STRING is set)
2. Local JSON file (development fallback)

Implements MCP standard patterns:
- Resources: Expose decline code data as readable resources
- Tools: Functions for querying and searching codes
- Prompts: Templates for common workflows
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from aiohttp import web
from fastmcp import FastMCP

# Add workspace root to path for imports
workspace_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(workspace_root))

from utils.ml_logging import get_logger

logger = get_logger(__name__)

# HTTP port for health checks and tool endpoints (80 for Container Apps, 8080 for local)
HEALTH_PORT = int(os.getenv("MCP_SERVER_PORT", "8080"))

# Path to local JSON file (for development fallback)
LOCAL_DATA_FILE = Path(__file__).parent.parent / "database" / "decline_codes_policy_pack.json"


# ═══════════════════════════════════════════════════════════════════════════════
# BOOTSTRAP: Load configuration from Azure App Configuration
# ═══════════════════════════════════════════════════════════════════════════════


def _bootstrap_appconfig() -> None:
    """Load configuration from Azure App Configuration at startup.
    
    Resolves Key Vault references for secrets like AZURE_COSMOS_CONNECTION_STRING.
    """
    try:
        from azure.appconfiguration import AzureAppConfigurationClient, SecretReferenceConfigurationSetting
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        
        endpoint = os.getenv("AZURE_APPCONFIG_ENDPOINT")
        label = os.getenv("AZURE_APPCONFIG_LABEL", "")
        
        if not endpoint:
            logger.info("No AZURE_APPCONFIG_ENDPOINT; using direct env vars")
            return
        
        logger.info(f"Loading config from App Configuration: {endpoint}")
        credential = DefaultAzureCredential()
        client = AzureAppConfigurationClient(endpoint, credential)
        
        # Load Cosmos connection string
        try:
            kv = client.get_configuration_setting(key="azure/cosmos/connection-string", label=label)
            if kv:
                if isinstance(kv, SecretReferenceConfigurationSetting):
                    # Resolve Key Vault reference
                    secret_id = kv.secret_id
                    vault_url = secret_id.split('/secrets/')[0]
                    secret_name = secret_id.split('/secrets/')[1].split('/')[0]
                    
                    kv_client = SecretClient(vault_url=vault_url, credential=credential)
                    secret = kv_client.get_secret(secret_name)
                    connection_string = secret.value
                    logger.info(f"Resolved Cosmos connection from Key Vault")
                else:
                    connection_string = kv.value
                    logger.info("Loaded Cosmos connection from App Config")
                
                os.environ["AZURE_COSMOS_CONNECTION_STRING"] = connection_string
        except Exception as e:
            logger.warning(f"Could not load azure/cosmos/connection-string: {e}")
        
        # NOTE: Database/collection names are set by Terraform env vars (cardapi/declinecodes)
        # and should NOT be overridden from App Config (which has main backend's db)
                
    except Exception as e:
        logger.warning(f"App Configuration bootstrap failed: {e}")


# Run bootstrap at module load (before FastMCP init)
_bootstrap_appconfig()


# Initialize FastMCP server
mcp = FastMCP(
    name="card-decline-codes",
    instructions="""
    This MCP server provides access to card decline codes database.
    Use the tools to look up specific codes, search for codes by description,
    or retrieve all codes. The prompts provide guided workflows for common
    customer service scenarios.
    """,
)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING (Self-contained - no backend dependency)
# ═══════════════════════════════════════════════════════════════════════════════

# In-memory cache of decline codes
_decline_codes_data: dict = {}
_scripts_dict: dict = {}


def _load_from_local_file() -> dict:
    """Load decline codes from local JSON file (development fallback)."""
    logger.info(f"Loading decline codes from local file: {LOCAL_DATA_FILE}")

    with open(LOCAL_DATA_FILE) as f:
        data = json.load(f)

    # Add code_type field to each code based on which array it came from
    numeric_codes = data.get("numeric_codes", [])
    for code in numeric_codes:
        code["code_type"] = "numeric"

    alphanumeric_codes = data.get("alphanumeric_codes", [])
    for code in alphanumeric_codes:
        code["code_type"] = "alphanumeric"

    return {
        "metadata": data.get("metadata", {"source": "local_file"}),
        "numeric_codes": numeric_codes,
        "alphanumeric_codes": alphanumeric_codes,
        "scripts": data.get("scripts", {}),
        "global_rules": data.get("global_rules", []),
    }


def _load_from_cosmos() -> dict:
    """Load decline codes from Cosmos DB using the shared library."""
    from src.cosmosdb.manager import CosmosDBMongoCoreManager

    database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME") or "cardapi"
    collection_name = os.getenv("AZURE_COSMOS_COLLECTION_NAME") or "declinecodes"

    logger.info(f"Connecting to Cosmos DB: database={database_name}, collection={collection_name}")

    manager = CosmosDBMongoCoreManager(
        database_name=database_name,
        collection_name=collection_name,
    )

    # Query all documents
    documents = manager.query_documents({}, projection={"_id": 0})

    numeric: list = []
    alpha: list = []
    scripts_dict: dict = {}
    global_rules: list = []
    metadata: dict = {}

    for doc in documents:
        code_type = (doc.get("code_type") or "").lower()
        if code_type == "numeric":
            numeric.append(doc)
        elif code_type == "alphanumeric":
            alpha.append(doc)
        elif "scripts" in doc:
            scripts_dict = doc.get("scripts", {})
        elif "rules" in doc:
            global_rules = doc.get("rules", [])
        elif doc.get("title") or doc.get("description"):
            metadata = doc
        else:
            logger.warning("Skipping document with unknown structure: %s", doc)

    manager.close_connection()

    return {
        "metadata": metadata or {
            "source": "azure_cosmosdb",
            "database": database_name,
            "collection": collection_name,
        },
        "numeric_codes": numeric,
        "alphanumeric_codes": alpha,
        "scripts": scripts_dict,
        "global_rules": global_rules,
    }


async def load_decline_codes() -> None:
    """Load decline codes from Cosmos DB or local file fallback."""
    global _decline_codes_data, _scripts_dict

    connection_string = os.getenv("AZURE_COSMOS_CONNECTION_STRING")

    # Use local file if no Cosmos connection string is set
    if not connection_string:
        logger.info("No AZURE_COSMOS_CONNECTION_STRING set; using local file fallback")
        if LOCAL_DATA_FILE.exists():
            _decline_codes_data = _load_from_local_file()
            _scripts_dict = _decline_codes_data.get("scripts", {})
            logger.info(
                "Loaded %s numeric, %s alphanumeric decline codes from local file",
                len(_decline_codes_data.get("numeric_codes", [])),
                len(_decline_codes_data.get("alphanumeric_codes", [])),
            )
        else:
            logger.warning(f"Local data file not found: {LOCAL_DATA_FILE}")
            _decline_codes_data = {
                "metadata": {"source": "disabled"},
                "numeric_codes": [],
                "alphanumeric_codes": [],
            }
        return

    # Load from Cosmos DB
    try:
        _decline_codes_data = await asyncio.to_thread(_load_from_cosmos)
        _scripts_dict = _decline_codes_data.get("scripts", {})
        logger.info(
            "Loaded %s numeric, %s alphanumeric decline codes, %s scripts from Cosmos DB",
            len(_decline_codes_data.get("numeric_codes", [])),
            len(_decline_codes_data.get("alphanumeric_codes", [])),
            len(_scripts_dict),
        )
    except Exception as e:
        logger.error(f"Failed to load from Cosmos DB: {e}")
        # Fall back to local file
        if LOCAL_DATA_FILE.exists():
            logger.info("Falling back to local file after Cosmos DB failure")
            _decline_codes_data = _load_from_local_file()
            _scripts_dict = _decline_codes_data.get("scripts", {})
        else:
            _decline_codes_data = {
                "metadata": {"source": "error"},
                "numeric_codes": [],
                "alphanumeric_codes": [],
            }


def _resolve_script_refs(script_refs: list[str] | None) -> list[dict] | None:
    """Resolve script references to actual script objects."""
    if not script_refs:
        return None

    resolved_scripts = []
    for ref in script_refs:
        if ref in _scripts_dict:
            script_data = _scripts_dict[ref]
            resolved_scripts.append({
                "ref": ref,
                "title": script_data.get("title", ""),
                "channels": script_data.get("channels"),
                "text": script_data.get("text", ""),
                "notes": script_data.get("notes"),
            })
        else:
            logger.warning(f"Script reference '{ref}' not found in scripts dictionary")

    return resolved_scripts if resolved_scripts else None


def _find_code(code: str) -> dict | None:
    """Find a decline code by code string."""
    code_upper = code.upper()

    for code_data in _decline_codes_data.get("numeric_codes", []):
        if code_data["code"] == code_upper:
            return code_data

    for code_data in _decline_codes_data.get("alphanumeric_codes", []):
        if code_data["code"] == code_upper:
            return code_data

    return None


def _search_codes(query: str, code_type: str | None = None) -> list[dict]:
    """Search codes by query string."""
    query_lower = query.lower()
    matching_codes = []

    def matches_query(code_data: dict) -> bool:
        return (
            query_lower in code_data["description"].lower()
            or query_lower in code_data["information"].lower()
            or any(query_lower in action.lower() for action in code_data.get("actions", []))
        )

    if code_type is None or code_type.lower() == "numeric":
        for code_data in _decline_codes_data.get("numeric_codes", []):
            if matches_query(code_data):
                matching_codes.append(code_data)

    if code_type is None or code_type.lower() == "alphanumeric":
        for code_data in _decline_codes_data.get("alphanumeric_codes", []):
            if matches_query(code_data):
                matching_codes.append(code_data)

    return matching_codes


def _get_all_codes(code_type: str | None = None) -> list[dict]:
    """Get all codes, optionally filtered by type."""
    codes = []

    if code_type is None or code_type.lower() == "numeric":
        codes.extend(_decline_codes_data.get("numeric_codes", []))

    if code_type is None or code_type.lower() == "alphanumeric":
        codes.extend(_decline_codes_data.get("alphanumeric_codes", []))

    return codes


# ═══════════════════════════════════════════════════════════════════════════════
# RESOURCES
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.resource("decline-codes://database/all")
async def get_all_codes_resource() -> str:
    """Complete database of all decline codes with full details."""
    codes = _get_all_codes()
    return json.dumps({"codes": codes, "total": len(codes)}, indent=2)


@mcp.resource("decline-codes://database/metadata")
async def get_metadata_resource() -> str:
    """Metadata about the decline codes database."""
    return json.dumps({
        "metadata": _decline_codes_data.get("metadata", {}),
        "numeric_codes_count": len(_decline_codes_data.get("numeric_codes", [])),
        "alphanumeric_codes_count": len(_decline_codes_data.get("alphanumeric_codes", [])),
    }, indent=2)


@mcp.resource("decline-code://{code}")
async def get_code_resource(code: str) -> str:
    """Get detailed information about a specific decline code."""
    code_data = _find_code(code)
    if code_data:
        return json.dumps(code_data, indent=2)
    return json.dumps({"error": f"Code '{code}' not found"}, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL IMPLEMENTATIONS (callable directly for HTTP handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def _lookup_decline_code_impl(code: str) -> str:
    """Implementation for lookup_decline_code tool."""
    logger.info(f"Looking up decline code: {code}")

    data = _find_code(code)
    if not data:
        error_msg = f"Decline code '{code}' not found in the database."
        logger.warning(error_msg)
        return error_msg

    # Resolve script references
    scripts = _resolve_script_refs(data.get("script_refs"))

    result = f"""**Decline Code: {data['code']}** ({data['code_type']})

**Description:** {data['description']}

**Information:** {data['information']}

**Recommended Actions:**
"""
    for action in data.get("actions", []):
        result += f"\n- {action}"

    # Add orchestrator actions if present
    if data.get("orchestrator_actions"):
        result += "\n\n**Orchestrator Actions:**"
        for action in data["orchestrator_actions"]:
            result += f"\n- {action}"

    # Add script references with resolved content
    if scripts:
        result += "\n\n**Customer Service Scripts:**"
        for script in scripts:
            result += f"\n\n**{script['title']}** (Ref: {script['ref']})"
            if script.get("channels"):
                result += f"\n- Channels: {', '.join(script['channels'])}"
            result += f"\n- Script: {script['text']}"
            if script.get("notes"):
                result += f"\n- Notes: {script['notes']}"

    # Add contextual rules
    if data.get("contextual_rules"):
        result += "\n\n**Contextual Rules:**"
        for i, rule in enumerate(data["contextual_rules"], 1):
            result += f"\n\n{i}. **Condition:** {rule.get('if', {})}"
            if rule.get("add_script_refs"):
                add_scripts = _resolve_script_refs(rule.get("add_script_refs"))
                if add_scripts:
                    result += "\n   **Additional Scripts:**"
                    for script in add_scripts:
                        result += f"\n   - {script['title']}: {script['text']}"
            if rule.get("escalation"):
                esc = rule["escalation"]
                if esc.get("required"):
                    result += f"\n   **Escalation Required:** {esc.get('target', 'Yes')}"
            if rule.get("orchestrator_actions"):
                result += f"\n   **Actions:** {', '.join(rule['orchestrator_actions'])}"

    # Add escalation information
    if data.get("escalation"):
        esc = data["escalation"]
        if esc.get("required"):
            result += f"\n\n**Escalation Required:** {esc.get('target', 'Yes')}"
        elif esc.get("target"):
            result += f"\n\n**Escalation Target:** {esc['target']}"

    logger.info(f"Successfully retrieved decline code: {code}")
    return result


async def _search_decline_codes_impl(query: str, code_type: str | None = None) -> str:
    """Implementation for search_decline_codes tool."""
    logger.info(f"Searching for decline codes: query='{query}', type={code_type}")

    matching_codes = _search_codes(query, code_type)

    if not matching_codes:
        msg = f"No decline codes found matching query: '{query}'"
        logger.info(msg)
        return msg

    result = f"**Found {len(matching_codes)} matching decline code(s):**\n\n"
    for code_data in matching_codes:
        result += f"""**Code {code_data['code']}** ({code_data['code_type']}): {code_data['description']}
{code_data['information']}

"""

    logger.info(f"Search found {len(matching_codes)} codes for query: '{query}'")
    return result


async def _get_all_decline_codes_impl(code_type: str | None = None) -> str:
    """Implementation for get_all_decline_codes tool."""
    logger.info(f"Getting all decline codes, type filter: {code_type}")

    codes = _get_all_codes(code_type)

    type_str = f" {code_type}" if code_type else ""
    result = f"**Total{type_str} decline codes: {len(codes)}**\n\n"

    for code_data in codes:
        result += (
            f"- **{code_data['code']}** ({code_data['code_type']}): "
            f"{code_data['description']}\n"
        )

    logger.info(f"Retrieved {len(codes)} decline codes")
    return result


async def _get_decline_codes_metadata_impl() -> str:
    """Implementation for get_decline_codes_metadata tool."""
    logger.info("Retrieving decline codes metadata")

    metadata = _decline_codes_data.get("metadata", {})
    numeric_count = len(_decline_codes_data.get("numeric_codes", []))
    alphanumeric_count = len(_decline_codes_data.get("alphanumeric_codes", []))

    result = f"""**Decline Codes Database Metadata**

**System Information:**
{metadata.get('title', 'N/A')}
{metadata.get('description', '')}

**Statistics:**
- Numeric codes (Base24): {numeric_count}
- Alphanumeric codes (FAST): {alphanumeric_count}
- Total codes: {numeric_count + alphanumeric_count}

**Notes:**
"""
    for note in metadata.get("notes", []):
        result += f"\n- {note}"

    logger.info(f"Metadata retrieved: {numeric_count} numeric, {alphanumeric_count} alphanumeric codes")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOL REGISTRATIONS (wrappers that call implementations)
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
async def lookup_decline_code(code: str) -> str:
    """
    Look up a specific card decline code to get its description, detailed information,
    recommended actions, customer service scripts (with resolved content), orchestrator
    actions, contextual rules, and escalation requirements.

    Use this when you know the exact decline code.

    Args:
        code: The decline code to look up (e.g., '02', '51', 'C1', 'RT')
    """
    return await _lookup_decline_code_impl(code)


@mcp.tool()
async def search_decline_codes(query: str, code_type: str | None = None) -> str:
    """
    Search for decline codes by description, information, or action keywords.
    Returns complete policy pack data including scripts, orchestrator actions,
    and escalation info.

    Use this when you need to find codes related to a specific issue or symptom.

    Args:
        query: Search query (e.g., 'insufficient funds', 'expired', 'PIN')
        code_type: Optional filter by 'numeric' (Base24) or 'alphanumeric' (FAST)
    """
    return await _search_decline_codes_impl(query, code_type)


@mcp.tool()
async def get_all_decline_codes(code_type: str | None = None) -> str:
    """
    Get all available decline codes with complete policy pack data (scripts,
    orchestrator actions, escalation), optionally filtered by type.

    Use this to browse all codes or get an overview.

    Args:
        code_type: Optional filter by 'numeric' (Base24) or 'alphanumeric' (FAST)
    """
    return await _get_all_decline_codes_impl(code_type)


@mcp.tool()
async def get_decline_codes_metadata() -> str:
    """
    Get metadata about the decline codes database, including total counts
    and system information.
    """
    return await _get_decline_codes_metadata_impl()


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.prompt()
def investigate_decline(code: str) -> str:
    """
    Investigate a card decline code and provide customer guidance.

    Args:
        code: The decline code to investigate
    """
    return f"""I need to investigate decline code {code}. Please:

1. Look up the code details including description, information, and recommended actions
2. Provide the customer service scripts that should be used
3. List any orchestrator actions that should be taken
4. Check if escalation is required and to which team
5. Note any contextual rules that might apply

Use the lookup_decline_code tool to get this information."""


@mcp.prompt()
def troubleshoot_issue(issue_description: str) -> str:
    """
    Troubleshoot a customer issue by searching relevant decline codes.

    Args:
        issue_description: Description of the customer's issue
    """
    return f"""A customer is experiencing: {issue_description}

Please help troubleshoot by:
1. Searching for relevant decline codes related to this issue
2. Identifying the most likely decline code(s)
3. Providing the recommended actions for each code
4. Suggesting next steps for resolution

Use the search_decline_codes tool to find relevant codes."""


@mcp.prompt()
def escalation_workflow(code: str) -> str:
    """
    Check if a decline code requires escalation and provide workflow.

    Args:
        code: The decline code to check
    """
    return f"""For decline code {code}, check the escalation requirements:

1. Look up the code details
2. Check if escalation is required
3. Identify the escalation target team
4. Provide the escalation workflow steps
5. Note any contextual rules that affect escalation

Use the lookup_decline_code tool to get escalation information."""


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP HEALTH & TOOL ENDPOINTS (for Container Apps and direct access)
# ═══════════════════════════════════════════════════════════════════════════════


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint for Container Apps probes.
    
    Returns status, tools_count, and tool_names for MCP startup validation.
    """
    # Get registered tools from FastMCP tool manager
    tools = mcp._tool_manager._tools
    tool_names = list(tools.keys())
    
    response = {
        "status": "healthy",
        "tools_count": len(tools),
        "tool_names": tool_names,
    }
    return web.json_response(response)


async def tools_list(request: web.Request) -> web.Response:
    """List all available tools with their full schemas.
    
    Returns tool definitions in a format compatible with MCP client discovery.
    """
    try:
        tools = mcp._tool_manager._tools
        tool_list = []
        
        for name, tool in tools.items():
            # Extract input schema safely
            input_schema = {"type": "object", "properties": {}}
            try:
                if hasattr(tool, 'parameters') and tool.parameters is not None:
                    input_schema = tool.parameters.model_json_schema()
                elif hasattr(tool, 'fn'):
                    # Try to inspect function signature
                    import inspect
                    sig = inspect.signature(tool.fn)
                    props = {}
                    required = []
                    for param_name, param in sig.parameters.items():
                        if param_name == 'self':
                            continue
                        param_type = "string"
                        if param.annotation != inspect.Parameter.empty:
                            if param.annotation == str or param.annotation == "str":
                                param_type = "string"
                            elif param.annotation == int:
                                param_type = "integer"
                            elif param.annotation == bool:
                                param_type = "boolean"
                        props[param_name] = {"type": param_type}
                        if param.default == inspect.Parameter.empty:
                            required.append(param_name)
                    input_schema = {"type": "object", "properties": props, "required": required}
            except Exception as e:
                logger.debug(f"Failed to get schema for tool {name}: {e}")
            
            tool_info = {
                "name": name,
                "description": getattr(tool, 'description', None) or f"Tool: {name}",
                "input_schema": input_schema,
            }
            tool_list.append(tool_info)
        
        return web.json_response({"tools": tool_list})
    except Exception as e:
        logger.error(f"tools_list failed: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def tool_lookup_decline_code_http(request: web.Request) -> web.Response:
    """HTTP wrapper for lookup_decline_code tool."""
    code = (request.query.get("code") or "").strip()
    if not code:
        return web.json_response({"success": False, "message": "code is required"}, status=400)

    try:
        result = await _lookup_decline_code_impl(code)
        return web.json_response({"success": True, "result": result})
    except Exception as e:
        logger.error(f"lookup_decline_code failed: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def tool_search_decline_codes_http(request: web.Request) -> web.Response:
    """HTTP wrapper for search_decline_codes tool."""
    query = (request.query.get("query") or "").strip()
    code_type = (request.query.get("code_type") or "").strip() or None
    if not query:
        return web.json_response({"success": False, "message": "query is required"}, status=400)

    try:
        result = await _search_decline_codes_impl(query=query, code_type=code_type)
        return web.json_response({"success": True, "result": result})
    except Exception as e:
        logger.error(f"search_decline_codes failed: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def tool_get_all_decline_codes_http(request: web.Request) -> web.Response:
    """HTTP wrapper for get_all_decline_codes tool."""
    code_type = (request.query.get("code_type") or "").strip() or None
    
    try:
        result = await _get_all_decline_codes_impl(code_type=code_type)
        return web.json_response({"success": True, "result": result})
    except Exception as e:
        logger.error(f"get_all_decline_codes failed: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def tool_get_decline_codes_metadata_http(request: web.Request) -> web.Response:
    """HTTP wrapper for get_decline_codes_metadata tool."""
    try:
        result = await _get_decline_codes_metadata_impl()
        return web.json_response({"success": True, "result": result})
    except Exception as e:
        logger.error(f"get_decline_codes_metadata failed: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def run_health_server() -> None:
    """Run the health check and HTTP tool server."""
    try:
        http_app = web.Application()

        # Add error handling middleware
        @web.middleware
        async def error_middleware(request, handler):
            try:
                return await handler(request)
            except web.HTTPException:
                raise  # Let aiohttp handle HTTP exceptions
            except Exception as e:
                logger.error(f"Unhandled error in {request.path}: {e}", exc_info=True)
                return web.json_response(
                    {"success": False, "error": str(e), "path": request.path},
                    status=500
                )
        
        http_app.middlewares.append(error_middleware)

        # Health endpoints
        http_app.router.add_get("/health", health_check)
        http_app.router.add_get("/ready", health_check)
        http_app.router.add_get("/", health_check)

        # Tool discovery endpoint (for MCP client)
        http_app.router.add_get("/tools/list", tools_list)

        # Tool endpoints (for direct HTTP access)
        http_app.router.add_get("/tools/lookup_decline_code", tool_lookup_decline_code_http)
        http_app.router.add_get("/tools/search_decline_codes", tool_search_decline_codes_http)
        http_app.router.add_get("/tools/get_all_decline_codes", tool_get_all_decline_codes_http)
        http_app.router.add_get("/tools/get_decline_codes_metadata", tool_get_decline_codes_metadata_http)

        runner = web.AppRunner(http_app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
        await site.start()
        logger.info(f"HTTP server started on port {HEALTH_PORT}")

        # Keep the server running
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        # Graceful shutdown
        return
    except Exception as e:
        logger.error(f"Health server failed: {e}", exc_info=True)
        await asyncio.sleep(1)


async def main() -> None:
    """Main entry point for the MCP server."""
    logger.info("Initializing Card Decline Code MCP Server (self-contained)")

    # Load decline codes data at startup
    await load_decline_codes()

    # Start HTTP server (health + tools) in background task
    health_task = asyncio.create_task(run_health_server())

    def _health_done(task: asyncio.Task) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc and not isinstance(exc, asyncio.CancelledError):
            logger.error(f"Health server task ended: {exc}", exc_info=True)

    health_task.add_done_callback(_health_done)

    # Give health server time to start
    await asyncio.sleep(1)

    # Run FastMCP server on stdio
    try:
        logger.info("Starting FastMCP stdio server...")
        await mcp.run_async(transport="stdio")
    except EOFError:
        # stdin/stdout closed; normal when running in container without direct agent connection
        logger.info("MCP server connection closed, waiting for health checks")
    except Exception as e:
        logger.error(f"MCP server error: {str(e)}", exc_info=True)

    # Keep the container running by waiting on the health server
    logger.info("MCP container keeping health server alive")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP server shut down by user")
    except Exception as e:
        logger.error(f"MCP server crashed: {str(e)}", exc_info=True)
        exit(1)
