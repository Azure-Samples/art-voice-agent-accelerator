"""
Security and CORS Configuration
================================

CORS settings, authentication paths, and security-related configuration
for the real-time voice agent.
"""

import os
from .constants import ACS_CALL_CALLBACK_PATH, ACS_WEBSOCKET_PATH

# ==============================================================================
# CORS AND SECURITY SETTINGS
# ==============================================================================

# CORS configuration
ALLOWED_ORIGINS = (
    os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if os.getenv("ALLOWED_ORIGINS")
    else ["*"]
)

# Entra ID exempt paths (paths that don't require authentication)
ENTRA_EXEMPT_PATHS = [
    ACS_CALL_CALLBACK_PATH,
    ACS_WEBSOCKET_PATH,
    "/health",
    "/readiness",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/v1/health",
]
