"""
Connection and Session Management Configuration
===============================================

WebSocket connections, session lifecycle, and connection pooling settings
for the real-time voice agent.
"""

import os

# ==============================================================================
# WEBSOCKET CONNECTION MANAGEMENT
# ==============================================================================

# Connection limits - Phase 1 scaling
MAX_WEBSOCKET_CONNECTIONS = int(os.getenv("MAX_WEBSOCKET_CONNECTIONS", "200"))
CONNECTION_QUEUE_SIZE = int(os.getenv("CONNECTION_QUEUE_SIZE", "50"))
ENABLE_CONNECTION_LIMITS = (
    os.getenv("ENABLE_CONNECTION_LIMITS", "true").lower() == "true"
)

# Connection monitoring thresholds
CONNECTION_WARNING_THRESHOLD = int(
    os.getenv("CONNECTION_WARNING_THRESHOLD", "150")
)  # 75%
CONNECTION_CRITICAL_THRESHOLD = int(
    os.getenv("CONNECTION_CRITICAL_THRESHOLD", "180")
)  # 90%

# Connection timeout settings
CONNECTION_TIMEOUT_SECONDS = int(
    os.getenv("CONNECTION_TIMEOUT_SECONDS", "300")
)  # 5 minutes
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "30"))

# ==============================================================================
# SESSION MANAGEMENT
# ==============================================================================

# Session lifecycle settings
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "1800"))  # 30 minutes
SESSION_CLEANUP_INTERVAL = int(
    os.getenv("SESSION_CLEANUP_INTERVAL", "300")
)  # 5 minutes
MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", "1000"))

# Session state management
ENABLE_SESSION_PERSISTENCE = (
    os.getenv("ENABLE_SESSION_PERSISTENCE", "true").lower() == "true"
)
SESSION_STATE_TTL = int(os.getenv("SESSION_STATE_TTL", "3600"))  # 1 hour

# ==============================================================================
# CONNECTION POOLING
# ==============================================================================

# Speech service pool sizes - Phase 1 optimized for 100-200 connections
POOL_SIZE_TTS = int(os.getenv("POOL_SIZE_TTS", "50"))
POOL_SIZE_STT = int(os.getenv("POOL_SIZE_STT", "50"))

# Pool monitoring and warnings
POOL_LOW_WATER_MARK = int(os.getenv("POOL_LOW_WATER_MARK", "10"))
POOL_HIGH_WATER_MARK = int(os.getenv("POOL_HIGH_WATER_MARK", "45"))
POOL_ACQUIRE_TIMEOUT = float(os.getenv("POOL_ACQUIRE_TIMEOUT", "5.0"))
