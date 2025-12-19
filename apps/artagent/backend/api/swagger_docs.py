"""
Dynamic Documentation System
============================

Simple documentation generator for the Real-Time Voice Agent API.
"""

from utils.ml_logging import get_logger

logger = get_logger("dynamic_docs")


class DynamicDocsManager:
    """Simple documentation manager."""

    def __init__(self):
        pass

    def generate_tags(self) -> list[dict[str, str]]:
        """Generate OpenAPI tags for all API endpoints."""
        return [
            # ═══════════════════════════════════════════════════════════════════
            # Health & System Operations
            # ═══════════════════════════════════════════════════════════════════
            {
                "name": "Health",
                "description": "Health monitoring, readiness probes, and system status checks",
            },
            # ═══════════════════════════════════════════════════════════════════
            # Call Operations
            # ═══════════════════════════════════════════════════════════════════
            {
                "name": "Call Management",
                "description": "Outbound/inbound call initiation, termination, and lifecycle operations via Azure Communication Services",
            },
            {
                "name": "Call Events",
                "description": "ACS webhook callbacks and call event processing (connected, disconnected, DTMF, etc.)",
            },
            # ═══════════════════════════════════════════════════════════════════
            # Media & WebSocket Streaming
            # ═══════════════════════════════════════════════════════════════════
            {
                "name": "ACS Media Session",
                "description": "Azure Communication Services media streaming for phone calls (Speech Cascade mode)",
            },
            {
                "name": "Browser Communication",
                "description": "Browser-based voice conversations via WebSocket (Voice Live SDK or Speech Cascade)",
            },
            {
                "name": "Browser Status",
                "description": "Browser service status and active WebSocket connection statistics",
            },
            {
                "name": "WebSocket",
                "description": "WebSocket transport endpoints for real-time audio streaming and dashboard relay",
            },
            # ═══════════════════════════════════════════════════════════════════
            # Metrics & Telemetry
            # ═══════════════════════════════════════════════════════════════════
            {
                "name": "Session Metrics",
                "description": "Session telemetry, latency statistics, and turn-level metrics for active conversations",
            },
            {
                "name": "Telemetry",
                "description": "OpenTelemetry-based observability data and performance metrics",
            },
            # ═══════════════════════════════════════════════════════════════════
            # Agent Configuration
            # ═══════════════════════════════════════════════════════════════════
            {
                "name": "Agent Builder",
                "description": "Dynamic agent creation, template management, and session-scoped agent configuration",
            },
            {
                "name": "Scenarios",
                "description": "Multi-agent scenario definitions with handoff routing and orchestration modes",
            },
            # ═══════════════════════════════════════════════════════════════════
            # Demo Environment
            # ═══════════════════════════════════════════════════════════════════
            {
                "name": "demo-env",
                "description": "Demo environment utilities for creating temporary user profiles and test data",
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


def get_tags() -> list[dict[str, str]]:
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
