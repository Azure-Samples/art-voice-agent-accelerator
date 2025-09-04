from typing import Any, Callable, Dict, List

# Import tool functions
try:
    from .customer_support_tools import (
        check_order_status,
        search_knowledge_base,
        create_support_ticket,
        escalate_to_human,
    )
except ImportError:
    # Fallback for direct execution
    from customer_support_tools import (
        check_order_status,
        search_knowledge_base,
        create_support_ticket,
        escalate_to_human,
    )

# Simple logger for standalone operation
import logging
logger = logging.getLogger("tool_registry")
logging.basicConfig(level=logging.INFO)


# Tool Registry - maps tool names to actual functions (ARTAgent style)
TOOL_REGISTRY: Dict[str, Callable[..., Any]] = {
    "check_order_status": check_order_status,
    "search_knowledge_base": search_knowledge_base,
    "create_support_ticket": create_support_ticket,
    "escalate_to_human": escalate_to_human,
}


def get_tool_function(tool_name: str) -> Callable[..., Any]:
    """
    Get a tool function by name from the registry.
    
    Args:
        tool_name: Name of the tool to retrieve
        
    Returns:
        The tool function
        
    Raises:
        ValueError: If tool name is not found in registry
    """
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' not found in registry")
    return TOOL_REGISTRY[tool_name]


def list_available_tools() -> List[str]:
    """Get list of all available tool names."""
    return list(TOOL_REGISTRY.keys())


def validate_tool_registry() -> bool:
    """Validate that all tools in the registry are callable and working."""
    try:
        for tool_name in TOOL_REGISTRY.keys():
            tool_func = TOOL_REGISTRY[tool_name]
            assert callable(tool_func), f"Tool {tool_name} is not callable"
            # Verify the function has proper type hints and docstring
            assert tool_func.__doc__, f"Tool {tool_name} missing docstring"
            assert tool_func.__annotations__, f"Tool {tool_name} missing type hints"
        
        logger.info(f"✅ Tool registry validation passed for {len(TOOL_REGISTRY)} tools")
        return True
    except Exception as e:
        logger.error(f"❌ Tool registry validation failed: {e}")
        return False


if __name__ == "__main__":
    # Demo the registry
    print("🛠️  Customer Support Tool Registry")
    print("=" * 40)
    
    if validate_tool_registry():
        print(f"📋 Registered {len(TOOL_REGISTRY)} tools:")
        for tool_name, tool_func in TOOL_REGISTRY.items():
            # Get first line of docstring for summary
            doc_summary = tool_func.__doc__.split('\n')[1].strip() if tool_func.__doc__ else "No description"
            print(f"   • {tool_name}: {doc_summary}")
            
        print("\n🧪 Testing a tool:")
        test_tool = get_tool_function('check_order_status')
        result = test_tool('TEST-12345')
        print(f"   check_order_status('TEST-12345') -> {type(result).__name__}")
    else:
        print("❌ Tool registry validation failed")
