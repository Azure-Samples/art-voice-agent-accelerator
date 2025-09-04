"""
Azure AI Foundry Agent Builder

Usage:
    from foundryagents.agent_builder import AzureFoundryAgentBuilder
    
    builder = AzureFoundryAgentBuilder()
    agent_id = builder.create_agent_from_yaml("agent_store/customer_support_agent.yaml")
"""

import os
import json
import yaml
import functools
from pathlib import Path
from typing import Callable, Any, Optional, List, Dict
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import FunctionTool, ToolSet
from utils.ml_logging import get_logger

logger = get_logger("foundry_agent_builder")

# Import tool registry (relative import since we're in the same package)
try:
    from .tool_store import tool_registry
except ImportError:
    # Fallback for when running directly
    import sys
    sys.path.append(str(Path(__file__).parent))
    from tool_store import tool_registry


def json_safe_wrapper(func: Callable) -> Callable:
    """Wrap tool functions to return JSON strings - required for Azure AI Foundry."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        # Always return JSON string for Azure AI Foundry
        if isinstance(result, dict):
            return json.dumps(result)
        else:
            return json.dumps({"value": result, "type": type(result).__name__})
    return wrapper


class AzureFoundryAgentBuilder:
    """Azure Foundry Agent Builder - ARTAgent Style with YAML + Tool Registry."""
    
    def __init__(self, endpoint: Optional[str] = None, credential: Optional[Any] = None):
        """Initialize the builder with Azure AI Foundry connection."""
        self.endpoint = endpoint or os.getenv("AZURE_AI_FOUNDRY_URL") or os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
        self.credential = credential or DefaultAzureCredential()
        
        if not self.endpoint:
            raise ValueError("Azure AI Foundry endpoint required")
        
        logger.info(f"🔗 Foundry Agent Builder connecting to: {self.endpoint}")
    
    def create_agent_from_yaml(self, yaml_path: str) -> str:
        """
        Create agent from YAML config - exact same pattern as ARTAgent.
        
        Args:
            yaml_path: Path to YAML configuration file
            
        Returns:
            Agent ID string (like ARTAgent pattern)
        """
        # Load YAML config like ARTAgent does
        config_path = Path(yaml_path)
        with config_path.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        
        # Validate config like ARTAgent
        self._validate_config(config)
        
        # Extract agent config
        agent_config = config["agent"]
        model_config = config["model"]
        
        name = agent_config["name"]
        instructions = agent_config.get("instructions", "You are a helpful assistant that uses available tools.")
        model = model_config["deployment_id"]
        
        # Process tools from YAML like ARTAgent does
        tool_functions = []
        tool_names = config.get("tools", [])
        
        for tool_name in tool_names:
            if isinstance(tool_name, str):
                if tool_name not in tool_registry.TOOL_REGISTRY:
                    available_tools = list(tool_registry.TOOL_REGISTRY.keys())
                    raise ValueError(
                        f"Unknown tool name '{tool_name}' in YAML for {name}. "
                        f"Available tools: {available_tools}"
                    )
                # Get the actual function from registry
                tool_func = tool_registry.get_tool_function(tool_name)
                tool_functions.append(tool_func)
            else:
                raise TypeError("Each tools entry must be a string (tool name)")
        
        # Log tool loading like ARTAgent
        logger.info(f"🛠️ Loaded {len(tool_functions)} tools for {name}: {tool_names}")
        
        # Create agent using exact Azure AI Foundry pattern from notebook
        client = self._get_client()
        toolset = self._create_toolset_from_functions(tool_functions) if tool_functions else None
        
        try:
            agent = client.create_agent(
                model=model,
                name=name,
                instructions=instructions,
                toolset=toolset
            )
            logger.info(f"✅ Agent created: {agent.id}")
            return agent.id
        except Exception as e:
            logger.error(f"❌ Agent creation failed: {e}")
            raise
    
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate YAML config - same as ARTAgent validation."""
        required = [("agent", ["name", "instructions"]), ("model", ["deployment_id"])]
        for section, keys in required:
            if section not in config:
                raise ValueError(f"Missing '{section}' section in YAML config.")
            for key in keys:
                if key not in config[section]:
                    raise ValueError(f"Missing '{section}.{key}' in YAML config.")
    
    def _create_toolset_from_functions(self, tool_functions: List[Callable]) -> Optional[ToolSet]:
        """
        Convert function list to ToolSet - exact Azure AI Foundry pattern from notebook.
        
        Args:
            tool_functions: List of tool functions to wrap
            
        Returns:
            ToolSet configured for Azure AI Foundry
        """
        if not tool_functions:
            return None
            
        # Create JSON-safe versions of all tools (exact pattern from notebook)
        safe_tools = {json_safe_wrapper(func) for func in tool_functions}
        
        # Create FunctionTool and ToolSet (exact pattern from notebook)
        func_tool = FunctionTool(safe_tools)
        toolset = ToolSet()
        toolset.add(func_tool)
        
        logger.debug(f"🛠️ Created toolset with {len(tool_functions)} JSON-safe tools")
        return toolset
    
    def _get_client(self) -> AgentsClient:
        """Get Azure AI Foundry client."""
        return AgentsClient(endpoint=self.endpoint, credential=self.credential)


# Helper function for simple agent creation
def create_agent_from_yaml(yaml_path: str) -> str:
    """Simple function to create agent from YAML - like ARTAgent usage."""
    builder = AzureFoundryAgentBuilder()
    return builder.create_agent_from_yaml(yaml_path)
