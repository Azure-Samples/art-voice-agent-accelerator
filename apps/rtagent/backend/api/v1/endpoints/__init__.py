"""
API Endpoints Package
====================

REST API endpoints organized by domain.

Available endpoints:
- health: Health checks and readiness probes
- calls: Call management and lifecycle operations
- events: Event system monitoring and processing  
- media: Media streaming and transcription services
- realtime: Real-time communication and WebSocket endpoints
"""

from . import health, calls, media, realtime

__all__ = ["health", "calls", "media", "realtime"]
