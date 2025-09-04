"""
API Version 1
=============

V1 REST API endpoints for the Real-Time Audio Agent.

This package provides enterprise-grade REST API endpoints including:
- Health checks and readiness probes
- Call management and lifecycle operations  
- Event system monitoring and processing
- Media streaming and transcription services

All endpoints follow OpenAPI 3.0 standards with comprehensive documentation.
"""

from .router import v1_router

__all__ = ["v1_router"]
