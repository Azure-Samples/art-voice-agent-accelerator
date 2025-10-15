"""
Feature Flags and Application Behavior
=======================================

Feature toggles, validation settings, and application behavior flags
for the real-time voice agent.
"""

import os

# ==============================================================================
# FEATURE FLAGS
# ==============================================================================

# Validation features
DTMF_VALIDATION_ENABLED = os.getenv("DTMF_VALIDATION_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
    "on",
)
ENABLE_AUTH_VALIDATION = os.getenv("ENABLE_AUTH_VALIDATION", "false").lower() in (
    "true",
    "1",
    "yes",
    "on",
)

# Environment and debugging
DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes", "on")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

# Documentation features
_enable_docs_raw = os.getenv("ENABLE_DOCS", "auto").lower()

# Auto-detect docs enablement based on environment if not explicitly set
if _enable_docs_raw == "auto":
    ENABLE_DOCS = ENVIRONMENT not in ("production", "prod", "staging", "uat")
elif _enable_docs_raw in ("true", "1", "yes", "on"):
    ENABLE_DOCS = True
else:
    ENABLE_DOCS = False

# OpenAPI endpoints configuration
DOCS_URL = "/docs" if ENABLE_DOCS else None
REDOC_URL = "/redoc" if ENABLE_DOCS else None
OPENAPI_URL = "/openapi.json" if ENABLE_DOCS else None

# Alternative secure docs URL for production access (if needed)
SECURE_DOCS_URL = os.getenv("SECURE_DOCS_URL") if ENABLE_DOCS else None

# ==============================================================================
# MONITORING AND PERFORMANCE FLAGS
# ==============================================================================

# Performance monitoring
ENABLE_PERFORMANCE_LOGGING = (
    os.getenv("ENABLE_PERFORMANCE_LOGGING", "true").lower() == "true"
)
ENABLE_TRACING = os.getenv("ENABLE_TRACING", "true").lower() == "true"

# Metrics collection intervals
METRICS_COLLECTION_INTERVAL = int(
    os.getenv("METRICS_COLLECTION_INTERVAL", "60")
)  # seconds
POOL_METRICS_INTERVAL = int(os.getenv("POOL_METRICS_INTERVAL", "30"))  # seconds
