"""
Dynamic Documentation System
============================

Simple documentation generator for the Real-Time Voice Agent API.
"""

import time
from typing import Dict, List, Any

from utils.ml_logging import get_logger

logger = get_logger("dynamic_docs")


class DynamicDocsManager:
    """Simple documentation manager."""

    def __init__(self):
        pass

    def generate_tags(self) -> List[Dict[str, str]]:
        """Generate OpenAPI tags."""
        return [
            # V1 API Tags
            {
                "name": "Call Management",
                "description": "V1 API - Advanced call management with lifecycle operations",
            },
            {
                "name": "Call Events",
                "description": "V1 API - Event processing and webhook management",
            },
            {
                "name": "Real-time Communication",
                "description": "V1 API - Real-time audio streaming and processing",
            },
            {
                "name": "Media Session",
                "description": "V1 API - Media streaming and session management",
            },
            {
                "name": "Health",
                "description": "V1 API - Health monitoring and system status",
            },
        ]

    def generate_description(self) -> str:
        """
        Generate a clean, readable API description for OpenAPI docs.

        Returns:
            str: Markdown-formatted description.
        """
        return (
            "## Real-Time Agentic Voice API powered by Azure Communication Services\n\n"
            "### Overview\n"
            "This API enables low-latency, real-time voice interactions with advanced call management, event processing, and media streaming capabilities.\n\n"
            "### Features\n"
            "- **Call Management:** Advanced call initiation, lifecycle operations, event processing, webhook support, and pluggable orchestrator for conversation engines.\n"
            "- **Real-Time Communication:** WebSocket dashboard broadcasting, browser endpoints with orchestrator injection, low-latency audio streaming/processing, and Redis-backed session management.\n"
            "- **Production Operations:** Health checks with dependency monitoring, OpenTelemetry tracing/observability, dynamic status reporting, and Cosmos DB analytics storage.\n"
            "- **Security & Authentication:** JWT token validation (configurable exemptions), role-based access control, and secure webhook endpoint protection.\n"
            "- **Integration Points:**\n"
            "  - Azure Communication Services: Outbound/inbound calling, media streaming\n"
            "  - Azure Speech Services: Real-time STT/TTS, voice activity detection\n"
            "  - Azure OpenAI: Intelligent conversation processing\n"
            "  - Redis: Session state management and caching\n"
            "  - Cosmos DB: Analytics and conversation storage\n"
            "- **Migration & Compatibility:** V1 API with enhanced features and pluggable architecture, legacy API backward compatibility, and progressive migration between API versions.\n"
        )


# Global instance
dynamic_docs_manager = DynamicDocsManager()


def get_tags() -> List[Dict[str, str]]:
    """Get OpenAPI tags."""
    return dynamic_docs_manager.generate_tags()


def get_description() -> str:
    """Get API description."""
    return dynamic_docs_manager.generate_description()


def setup_app_documentation(app) -> bool:
    """
    Setup the FastAPI app's documentation.

    Args:
        app: The FastAPI application instance

    Returns:
        bool: True if setup was successful, False otherwise
    """
    try:
        # Set static tags and description
        app.openapi_tags = get_tags()
        app.description = get_description()

        logger.info("Successfully setup application documentation")
        return True

    except Exception as e:
        logger.error(f"Failed to setup app documentation: {e}")
        return False
