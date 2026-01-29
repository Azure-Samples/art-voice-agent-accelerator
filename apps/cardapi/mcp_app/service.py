"""
MCP Server for Card Decline Code Lookup.
Provides Model Context Protocol interface for AI agents to query decline codes.

Implements MCP standard patterns:
- Resources: Expose decline code data as readable resources
- Tools: Functions for querying and searching codes
- Prompts: Templates for common workflows
"""
import asyncio
import json
import os
from typing import Any, Dict, List, Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    ResourceTemplate,
    Tool,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from aiohttp import web

from utils.ml_logging import get_logger

logger = get_logger(__name__)

# Backend API configuration
BACKEND_URL = os.getenv("CARDAPI_BACKEND_URL", "http://localhost:8000")
# Bind the embedded health server to port 80 to satisfy Container Apps probes
HEALTH_PORT = 80


class CardDeclineCodeMCPServer:
    """MCP Server for card decline code lookups following MCP best practices."""
    
    def __init__(self):
        self.server = Server("card-decline-codes")
        self.backend_url = BACKEND_URL
        self.setup_resources()
        self.setup_prompts()
        self.setup_tools()
    
    def setup_resources(self):
        """Register MCP resources for decline code data."""
        
        @self.server.list_resources()
        async def list_resources() -> List[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri="decline-codes://database/all",
                    name="All Decline Codes",
                    description="Complete database of all decline codes with full details",
                    mimeType="application/json"
                ),
                Resource(
                    uri="decline-codes://database/metadata",
                    name="Database Metadata",
                    description="Metadata about the decline codes database",
                    mimeType="application/json"
                )
            ]
        
        @self.server.list_resource_templates()
        async def list_resource_templates() -> List[ResourceTemplate]:
            """List resource URI templates."""
            return [
                ResourceTemplate(
                    uriTemplate="decline-code://{code}",
                    name="Decline Code Details",
                    description="Get detailed information about a specific decline code",
                    mimeType="application/json"
                )
            ]
        
        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read resource content by URI."""
            try:
                if uri == "decline-codes://database/all":
                    # Get all codes
                    async with httpx.AsyncClient() as client:
                        response = await client.get(f"{self.backend_url}/api/v1/codes", timeout=10.0)
                        response.raise_for_status()
                        return json.dumps(response.json(), indent=2)
                
                elif uri == "decline-codes://database/metadata":
                    # Get metadata
                    async with httpx.AsyncClient() as client:
                        response = await client.get(f"{self.backend_url}/api/v1/metadata", timeout=10.0)
                        response.raise_for_status()
                        return json.dumps(response.json(), indent=2)
                
                elif uri.startswith("decline-code://"):
                    # Get specific code
                    code = uri.replace("decline-code://", "")
                    async with httpx.AsyncClient() as client:
                        response = await client.get(f"{self.backend_url}/api/v1/codes/{code}", timeout=10.0)
                        response.raise_for_status()
                        return json.dumps(response.json(), indent=2)
                
                else:
                    return json.dumps({"error": f"Unknown resource URI: {uri}"})
            
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return json.dumps({"error": f"Resource not found: {uri}"})
                return json.dumps({"error": f"Backend error: {e.response.status_code}"})
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}", exc_info=True)
                return json.dumps({"error": str(e)})
    
    def setup_prompts(self):
        """Register MCP prompts for common workflows."""
        
        @self.server.list_prompts()
        async def list_prompts() -> List[Prompt]:
            """List available prompts."""
            return [
                Prompt(
                    name="investigate-decline",
                    description="Investigate a card decline code and provide customer guidance",
                    arguments=[
                        PromptArgument(
                            name="code",
                            description="The decline code to investigate",
                            required=True
                        )
                    ]
                ),
                Prompt(
                    name="troubleshoot-issue",
                    description="Troubleshoot a customer issue by searching relevant decline codes",
                    arguments=[
                        PromptArgument(
                            name="issue_description",
                            description="Description of the customer's issue",
                            required=True
                        )
                    ]
                ),
                Prompt(
                    name="escalation-workflow",
                    description="Check if a decline code requires escalation and provide workflow",
                    arguments=[
                        PromptArgument(
                            name="code",
                            description="The decline code to check",
                            required=True
                        )
                    ]
                )
            ]
        
        @self.server.get_prompt()
        async def get_prompt(name: str, arguments: Dict[str, str]) -> List[PromptMessage]:
            """Get prompt content."""
            if name == "investigate-decline":
                code = arguments.get("code", "")
                return [
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""I need to investigate decline code {code}. Please:

1. Look up the code details including description, information, and recommended actions
2. Provide the customer service scripts that should be used
3. List any orchestrator actions that should be taken
4. Check if escalation is required and to which team
5. Note any contextual rules that might apply

Use the lookup_decline_code tool to get this information."""
                        )
                    )
                ]
            
            elif name == "troubleshoot-issue":
                issue = arguments.get("issue_description", "")
                return [
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""A customer is experiencing: {issue}

Please help troubleshoot by:
1. Searching for relevant decline codes related to this issue
2. Identifying the most likely decline code(s)
3. Providing the recommended actions for each code
4. Suggesting next steps for resolution

Use the search_decline_codes tool to find relevant codes."""
                        )
                    )
                ]
            
            elif name == "escalation-workflow":
                code = arguments.get("code", "")
                return [
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""For decline code {code}, check the escalation requirements:

1. Look up the code details
2. Check if escalation is required
3. Identify the escalation target team
4. Provide the escalation workflow steps
5. Note any contextual rules that affect escalation

Use the lookup_decline_code tool to get escalation information."""
                        )
                    )
                ]
            
            else:
                return [
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"Unknown prompt: {name}"
                        )
                    )
                ]
    
    def setup_tools(self):
        """Register MCP tools."""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools for the MCP server."""
            return [
                Tool(
                    name="lookup_decline_code",
                    description="Look up a specific card decline code to get its description, detailed information, recommended actions, customer service scripts (with resolved content), orchestrator actions, contextual rules, and escalation requirements. Use this when you know the exact decline code.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "The decline code to look up (e.g., '02', '51', 'C1', 'RT')"
                            }
                        },
                        "required": ["code"]
                    }
                ),
                Tool(
                    name="search_decline_codes",
                    description="Search for decline codes by description, information, or action keywords. Returns complete policy pack data including scripts, orchestrator actions, and escalation info. Use this when you need to find codes related to a specific issue or symptom.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (e.g., 'insufficient funds', 'expired', 'PIN')"
                            },
                            "code_type": {
                                "type": "string",
                                "description": "Optional: Filter by 'numeric' (Base24) or 'alphanumeric' (FAST)",
                                "enum": ["numeric", "alphanumeric"]
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_all_decline_codes",
                    description="Get all available decline codes with complete policy pack data (scripts, orchestrator actions, escalation), optionally filtered by type (numeric/alphanumeric). Use this to browse all codes or get an overview.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code_type": {
                                "type": "string",
                                "description": "Optional: Filter by 'numeric' (Base24) or 'alphanumeric' (FAST)",
                                "enum": ["numeric", "alphanumeric"]
                            }
                        }
                    }
                ),
                Tool(
                    name="get_decline_codes_metadata",
                    description="Get metadata about the decline codes database, including total counts and system information.",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls."""
            try:
                logger.info(f"Executing MCP tool: {name} with args: {arguments}")
                
                if name == "lookup_decline_code":
                    return await self.lookup_decline_code(arguments["code"])
                elif name == "search_decline_codes":
                    return await self.search_decline_codes(
                        arguments["query"],
                        arguments.get("code_type")
                    )
                elif name == "get_all_decline_codes":
                    return await self.get_all_decline_codes(arguments.get("code_type"))
                elif name == "get_decline_codes_metadata":
                    return await self.get_metadata()
                else:
                    error_msg = f"Unknown tool: {name}"
                    logger.error(error_msg)
                    return [TextContent(type="text", text=f"Error: {error_msg}")]
            except Exception as e:
                error_msg = f"Error calling tool {name}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return [TextContent(type="text", text=f"Error: {error_msg}")]
    
    async def lookup_decline_code(self, code: str) -> List[TextContent]:
        """Look up a specific decline code."""
        try:
            logger.info(f"Looking up decline code: {code}")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.backend_url}/api/v1/codes/{code}",
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                result = f"""**Decline Code: {data['code']}** ({data['code_type']})

**Description:** {data['description']}

**Information:** {data['information']}

**Recommended Actions:**
"""
                for action in data['actions']:
                    result += f"\n- {action}"
                
                # Add orchestrator actions if present
                if data.get('orchestrator_actions'):
                    result += f"\n\n**Orchestrator Actions:**"
                    for action in data['orchestrator_actions']:
                        result += f"\n- {action}"
                
                # Add script references with resolved content
                if data.get('scripts'):
                    result += f"\n\n**Customer Service Scripts:**"
                    for script in data['scripts']:
                        result += f"\n\n**{script['title']}** (Ref: {script['ref']})"
                        if script.get('channels'):
                            result += f"\n- Channels: {', '.join(script['channels'])}"
                        result += f"\n- Script: {script['text']}"
                        if script.get('notes'):
                            result += f"\n- Notes: {script['notes']}"
                
                # Add contextual rules
                if data.get('contextual_rules'):
                    result += f"\n\n**Contextual Rules:**"
                    for i, rule in enumerate(data['contextual_rules'], 1):
                        result += f"\n\n{i}. **Condition:** {rule.get('if', {})}"
                        if rule.get('add_scripts'):
                            result += f"\n   **Additional Scripts:**"
                            for script in rule['add_scripts']:
                                result += f"\n   - {script['title']}: {script['text']}"
                        if rule.get('escalation'):
                            esc = rule['escalation']
                            if esc.get('required'):
                                result += f"\n   **Escalation Required:** {esc.get('target', 'Yes')}"
                        if rule.get('orchestrator_actions'):
                            result += f"\n   **Actions:** {', '.join(rule['orchestrator_actions'])}"
                
                # Add escalation information
                if data.get('escalation'):
                    esc = data['escalation']
                    if esc.get('required'):
                        result += f"\n\n**Escalation Required:** {esc.get('target', 'Yes')}"
                    elif esc.get('target'):
                        result += f"\n\n**Escalation Target:** {esc['target']}"
                
                logger.info(f"Successfully retrieved decline code: {code}")
                return [TextContent(type="text", text=result)]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error_msg = f"Decline code '{code}' not found in the database."
                logger.warning(error_msg)
                return [TextContent(type="text", text=error_msg)]
            else:
                error_msg = f"Backend error: {e.response.status_code} - {e.response.text}"
                logger.error(error_msg)
                return [TextContent(type="text", text=f"Error: {error_msg}")]
        except Exception as e:
            error_msg = f"Failed to lookup code {code}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return [TextContent(type="text", text=f"Error: {error_msg}")]
    
    async def search_decline_codes(
        self,
        query: str,
        code_type: Optional[str] = None
    ) -> List[TextContent]:
        """Search for decline codes by query."""
        try:
            logger.info(f"Searching for decline codes: query='{query}', type={code_type}")
            async with httpx.AsyncClient() as client:
                params = {"q": query}
                if code_type:
                    params["code_type"] = code_type
                
                response = await client.get(
                    f"{self.backend_url}/api/v1/search",
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if data['total'] == 0:
                    msg = f"No decline codes found matching query: '{query}'"
                    logger.info(msg)
                    return [TextContent(type="text", text=msg)]
                
                result = f"**Found {data['total']} matching decline code(s):**\n\n"
                for code_data in data['codes']:
                    result += f"""**Code {code_data['code']}** ({code_data['code_type']}): {code_data['description']}
{code_data['information']}

"""
                
                logger.info(f"Search found {data['total']} codes for query: '{query}'")
                return [TextContent(type="text", text=result)]
        except Exception as e:
            error_msg = f"Failed to search codes with query '{query}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            return [TextContent(type="text", text=f"Error: {error_msg}")]
    
    async def get_all_decline_codes(
        self,
        code_type: Optional[str] = None
    ) -> List[TextContent]:
        """Get all decline codes."""
        try:
            logger.info(f"Getting all decline codes, type filter: {code_type}")
            async with httpx.AsyncClient() as client:
                params = {}
                if code_type:
                    params["code_type"] = code_type
                
                response = await client.get(
                    f"{self.backend_url}/api/v1/codes",
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                type_str = f" {code_type}" if code_type else ""
                result = f"**Total{type_str} decline codes: {data['total']}**\n\n"
                
                for code_data in data['codes']:
                    result += f"- **{code_data['code']}** ({code_data['code_type']}): {code_data['description']}\n"
                
                logger.info(f"Retrieved {data['total']} decline codes")
                return [TextContent(type="text", text=result)]
        except Exception as e:
            error_msg = f"Failed to retrieve all decline codes: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return [TextContent(type="text", text=f"Error: {error_msg}")]
    
    async def get_metadata(self) -> List[TextContent]:
        """Get database metadata."""
        try:
            logger.info("Retrieving decline codes metadata")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.backend_url}/api/v1/metadata",
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                result = f"""**Decline Codes Database Metadata**

**System Information:**
{data['metadata'].get('title', 'N/A')}
{data['metadata'].get('description', '')}

**Statistics:**
- Numeric codes (Base24): {data['numeric_codes_count']}
- Alphanumeric codes (FAST): {data['alphanumeric_codes_count']}
- Total codes: {data['numeric_codes_count'] + data['alphanumeric_codes_count']}

**Notes:**
"""
                for note in data['metadata'].get('notes', []):
                    result += f"\n- {note}"
                
                logger.info(f"Metadata retrieved: {data['numeric_codes_count']} numeric, {data['alphanumeric_codes_count']} alphanumeric codes")
                return [TextContent(type="text", text=result)]
        except Exception as e:
            error_msg = f"Failed to retrieve metadata: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return [TextContent(type="text", text=f"Error: {error_msg}")]
    
    async def run(self):
        """Run the MCP server."""
        try:
            logger.info(f"Starting Card Decline Code MCP Server (backend: {self.backend_url})")
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )
        except Exception as e:
            logger.error(f"MCP server error: {str(e)}", exc_info=True)
            raise


async def health_check(request):
    """Simple health check endpoint for Container Apps probes."""
    return web.Response(text='{"status":"healthy"}', content_type='application/json')


def _flatten_text(contents: List[TextContent]) -> str:
    """Flatten MCP TextContent responses into a single string."""
    return "\n".join(content.text for content in contents)


async def tool_lookup_decline_code(request: web.Request) -> web.Response:
    """HTTP wrapper for MCP lookup_decline_code tool."""
    code = (request.query.get("code") or "").strip()
    if not code:
        return web.json_response({"success": False, "message": "code is required"}, status=400)

    server: CardDeclineCodeMCPServer = request.app["mcp_server"]
    result = await server.lookup_decline_code(code)
    return web.json_response({"success": True, "result": _flatten_text(result)})


async def tool_search_decline_codes(request: web.Request) -> web.Response:
    """HTTP wrapper for MCP search_decline_codes tool."""
    query = (request.query.get("query") or "").strip()
    code_type = (request.query.get("code_type") or "").strip() or None
    if not query:
        return web.json_response({"success": False, "message": "query is required"}, status=400)

    server: CardDeclineCodeMCPServer = request.app["mcp_server"]
    result = await server.search_decline_codes(query=query, code_type=code_type)
    return web.json_response({"success": True, "result": _flatten_text(result)})


async def run_health_server():
    """Run the health check and HTTP tool server."""
    try:
        http_app = web.Application()
        http_app["mcp_server"] = CardDeclineCodeMCPServer()

        # Health endpoints
        http_app.router.add_get("/health", health_check)
        http_app.router.add_get("/ready", health_check)
        http_app.router.add_get("/", health_check)

        # Tool endpoints
        http_app.router.add_get("/tools/lookup_decline_code", tool_lookup_decline_code)
        http_app.router.add_get("/tools/search_decline_codes", tool_search_decline_codes)

        runner = web.AppRunner(http_app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', HEALTH_PORT)
        await site.start()
        logger.info(f"HTTP server started on port {HEALTH_PORT}")

        # Keep the server running
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        # Graceful shutdown; no error logging
        return
    except Exception as e:
        logger.error(f"Health server failed: {e}", exc_info=True)
        # Do not crash the container because of health server issues
        await asyncio.sleep(1)


async def main():
    """Main entry point for the MCP server."""
    try:
        logger.info("Initializing Card Decline Code MCP Server")
        
        # Start HTTP server (health + tools) in background task
        health_task = asyncio.create_task(run_health_server())

        # If the health server ever exits, log the reason
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
        
        # Run MCP server on stdio - wrap in try/except to keep container alive
        try:
            server = CardDeclineCodeMCPServer()
            await server.run()
        except EOFError:
            # stdin/stdout closed; normal when running in container without direct agent connection
            logger.info("MCP server connection closed, waiting for health checks")
        except Exception as e:
            logger.error(f"MCP server error: {str(e)}", exc_info=True)
        
        # Keep the container running by waiting on an event
        # The health server will keep responding to probes
        logger.info("MCP container keeping health server alive")
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Failed to start MCP server: {str(e)}", exc_info=True)
        # Don't raise - let the health server keep the container alive


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP server shut down by user")
    except Exception as e:
        logger.error(f"MCP server crashed: {str(e)}", exc_info=True)
        exit(1)
