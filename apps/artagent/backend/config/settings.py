"""
Application Settings
====================

All environment-loaded configuration in one place, organized by domain.
This is the single source of truth for runtime configuration.

Loading Order:
    1. Load .env.local (if exists) - local development overrides
    2. Environment variables (container/cloud deployments)
    3. Azure App Configuration (if configured) - loaded via appconfig_provider

Usage:
    from config import POOL_SIZE_TTS, AZURE_OPENAI_ENDPOINT
    from config.settings import AzureSettings, AgentSettings
"""

import os
import sys
from pathlib import Path

# Add root directory to path for imports
root_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

# ==============================================================================
# LOAD .env.local FILE (FIRST PRIORITY FOR LOCAL DEVELOPMENT)
# ==============================================================================
# .env.local is loaded FIRST to allow local development overrides.
# Variables already set in the environment will NOT be overridden.
# This supports the workflow:
#   1. .env.local provides local dev values
#   2. Container/cloud env vars take precedence if already set
#   3. Azure App Configuration can layer additional config later

def _load_dotenv_local():
    """
    Load .env.local file if it exists.

    Search order:
    1. apps/artagent/backend/.env.local (app-specific)
    2. Project root .env.local
    3. Project root .env (fallback)

    Only loads values NOT already set in the environment.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        # python-dotenv not available, skip
        return

    # Define search paths relative to this file
    backend_dir = Path(__file__).parent.parent  # apps/artagent/backend
    project_root = backend_dir.parent.parent.parent  # repository root

    # Priority order for .env files
    env_files = [
        backend_dir / ".env.local",      # App-specific local overrides
        project_root / ".env.local",     # Project-wide local overrides
        project_root / ".env",           # Default project env (lowest priority)
    ]

    for env_file in env_files:
        if env_file.exists():
            # override=False means existing env vars are NOT overwritten
            load_dotenv(env_file, override=False)
            break


# Load .env.local BEFORE any os.getenv() calls
_load_dotenv_local()

# StreamMode enum import with fallback
try:
    from src.enums.stream_modes import StreamMode
except ImportError:

    class StreamMode:
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return self.value


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


def _env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes", "on")


def _env_int(key: str, default: int) -> int:
    """Parse integer from environment variable."""
    return int(os.getenv(key, str(default)))


def _env_float(key: str, default: float) -> float:
    """Parse float from environment variable."""
    return float(os.getenv(key, str(default)))


def _env_list(key: str, default: str = "", sep: str = ",") -> list[str]:
    """Parse list from comma-separated environment variable."""
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(sep) if item.strip()]


# ==============================================================================
# AZURE IDENTITY & AUTHENTICATION
# ==============================================================================

AZURE_CLIENT_ID: str = os.getenv("AZURE_CLIENT_ID", "")
AZURE_TENANT_ID: str = os.getenv("AZURE_TENANT_ID", "")
BACKEND_AUTH_CLIENT_ID: str = os.getenv("BACKEND_AUTH_CLIENT_ID", "")

# Allowed client IDs (GUIDs) from environment variable
ALLOWED_CLIENT_IDS: list[str] = _env_list("ALLOWED_CLIENT_IDS")

# Entra ID URLs (derived from tenant)
ENTRA_JWKS_URL = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/discovery/v2.0/keys"
ENTRA_ISSUER = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/v2.0"
ENTRA_AUDIENCE = f"api://{BACKEND_AUTH_CLIENT_ID}"


# ==============================================================================
# AZURE OPENAI
# ==============================================================================

AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY: str = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_CHAT_DEPLOYMENT_ID: str = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_ID", "")

# Model behavior
DEFAULT_TEMPERATURE: float = _env_float("DEFAULT_TEMPERATURE", 0.7)
DEFAULT_MAX_TOKENS: int = _env_int("DEFAULT_MAX_TOKENS", 500)
AOAI_REQUEST_TIMEOUT: float = _env_float("AOAI_REQUEST_TIMEOUT", 30.0)


# ==============================================================================
# AZURE SPEECH SERVICES
# ==============================================================================

AZURE_SPEECH_REGION: str = os.getenv("AZURE_SPEECH_REGION", "")
AZURE_SPEECH_ENDPOINT: str = os.getenv("AZURE_SPEECH_ENDPOINT") or os.environ.get(
    "AZURE_OPENAI_STT_TTS_ENDPOINT", ""
)
AZURE_SPEECH_KEY: str = os.getenv("AZURE_SPEECH_KEY") or os.environ.get(
    "AZURE_OPENAI_STT_TTS_KEY", ""
)
AZURE_SPEECH_RESOURCE_ID: str = os.getenv("AZURE_SPEECH_RESOURCE_ID", "")

# Azure Voice Live (preview)
# Note: Uses AZURE_VOICELIVE_* format to match VoiceLiveSettings pydantic model
AZURE_VOICE_LIVE_ENDPOINT: str = os.getenv("AZURE_VOICELIVE_ENDPOINT", "") or os.getenv(
    "AZURE_VOICE_LIVE_ENDPOINT", ""
)
AZURE_VOICE_API_KEY: str = os.getenv("AZURE_VOICELIVE_API_KEY", "") or os.getenv(
    "AZURE_VOICE_API_KEY", ""
)
AZURE_VOICE_LIVE_MODEL: str = os.getenv("AZURE_VOICELIVE_MODEL", "") or os.getenv(
    "AZURE_VOICE_LIVE_MODEL", "gpt-4o"
)


# ==============================================================================
# AZURE COMMUNICATION SERVICES (ACS)
# ==============================================================================

ACS_ENDPOINT: str = os.getenv("ACS_ENDPOINT", "")
ACS_CONNECTION_STRING: str = os.getenv("ACS_CONNECTION_STRING", "")
ACS_SOURCE_PHONE_NUMBER: str = os.getenv("ACS_SOURCE_PHONE_NUMBER", "")
BASE_URL: str = os.getenv("BASE_URL", "")

# ACS Streaming
ACS_STREAMING_MODE: StreamMode = StreamMode(os.getenv("ACS_STREAMING_MODE", "media").lower())

# ACS Authentication
ACS_JWKS_URL = "https://acscallautomation.communication.azure.com/calling/keys"
ACS_ISSUER = "https://acscallautomation.communication.azure.com"
ACS_AUDIENCE = os.getenv("ACS_AUDIENCE", "")  # ACS Immutable Resource ID


# ==============================================================================
# AZURE STORAGE & COSMOS DB
# ==============================================================================

AZURE_STORAGE_CONTAINER_URL: str = os.getenv("AZURE_STORAGE_CONTAINER_URL", "")

AZURE_COSMOS_CONNECTION_STRING: str = os.getenv("AZURE_COSMOS_CONNECTION_STRING", "")
AZURE_COSMOS_DATABASE_NAME: str = os.getenv("AZURE_COSMOS_DATABASE_NAME", "")
AZURE_COSMOS_COLLECTION_NAME: str = os.getenv("AZURE_COSMOS_COLLECTION_NAME", "")


# ==============================================================================
# VOICE & TTS SETTINGS
# ==============================================================================
# NOTE: Per-agent voice settings are now defined in each agent's agent.yaml.
# These settings provide fallback defaults used by legacy code paths.
# See: apps/artagent/backend/registries/agentstore/<agent_name>/agent.yaml
# ==============================================================================

# Fallback TTS voice (used when agent voice is not available)
# NOTE: Should be empty - voice comes from active agent's agent.yaml
DEFAULT_TTS_VOICE: str = os.getenv("DEFAULT_TTS_VOICE", "")
# Legacy alias - deprecated, use DEFAULT_TTS_VOICE
GREETING_VOICE_TTS: str = os.getenv("GREETING_VOICE_TTS", DEFAULT_TTS_VOICE)

# Fallback voice style/rate (agents define these in agent.yaml voice config)
DEFAULT_VOICE_STYLE: str = os.getenv("DEFAULT_VOICE_STYLE", "chat")
DEFAULT_VOICE_RATE: str = os.getenv("DEFAULT_VOICE_RATE", "+0%")

# TTS audio format
TTS_SAMPLE_RATE_UI: int = _env_int("TTS_SAMPLE_RATE_UI", 48000)
TTS_SAMPLE_RATE_ACS: int = _env_int("TTS_SAMPLE_RATE_ACS", 16000)
TTS_CHUNK_SIZE: int = _env_int("TTS_CHUNK_SIZE", 1024)
TTS_PROCESSING_TIMEOUT: float = _env_float("TTS_PROCESSING_TIMEOUT", 8.0)

# Speech recognition
VAD_SEMANTIC_SEGMENTATION: bool = _env_bool("VAD_SEMANTIC_SEGMENTATION", False)
SILENCE_DURATION_MS: int = _env_int("SILENCE_DURATION_MS", 1300)
AUDIO_FORMAT: str = os.getenv("AUDIO_FORMAT", "pcm")
STT_PROCESSING_TIMEOUT: float = _env_float("STT_PROCESSING_TIMEOUT", 10.0)
RECOGNIZED_LANGUAGE: list[str] = _env_list(
    "RECOGNIZED_LANGUAGE", "en-US,es-ES,fr-FR,ko-KR,it-IT,pt-PT,pt-BR"
)


# ==============================================================================
# CONNECTION & SESSION MANAGEMENT
# ==============================================================================

# WebSocket limits
MAX_WEBSOCKET_CONNECTIONS: int = _env_int("MAX_WEBSOCKET_CONNECTIONS", 200)
CONNECTION_QUEUE_SIZE: int = _env_int("CONNECTION_QUEUE_SIZE", 50)
ENABLE_CONNECTION_LIMITS: bool = _env_bool("ENABLE_CONNECTION_LIMITS", True)

# Connection thresholds
CONNECTION_WARNING_THRESHOLD: int = _env_int("CONNECTION_WARNING_THRESHOLD", 150)
CONNECTION_CRITICAL_THRESHOLD: int = _env_int("CONNECTION_CRITICAL_THRESHOLD", 180)
CONNECTION_TIMEOUT_SECONDS: int = _env_int("CONNECTION_TIMEOUT_SECONDS", 300)
HEARTBEAT_INTERVAL_SECONDS: int = _env_int("HEARTBEAT_INTERVAL_SECONDS", 30)

# Session lifecycle
SESSION_TTL_SECONDS: int = _env_int("SESSION_TTL_SECONDS", 1800)
SESSION_CLEANUP_INTERVAL: int = _env_int("SESSION_CLEANUP_INTERVAL", 300)
MAX_CONCURRENT_SESSIONS: int = _env_int("MAX_CONCURRENT_SESSIONS", 1000)
ENABLE_SESSION_PERSISTENCE: bool = _env_bool("ENABLE_SESSION_PERSISTENCE", True)
SESSION_STATE_TTL: int = _env_int("SESSION_STATE_TTL", 86400)

# Speech service pools
POOL_SIZE_TTS: int = _env_int("POOL_SIZE_TTS", 50)
POOL_SIZE_STT: int = _env_int("POOL_SIZE_STT", 50)
POOL_LOW_WATER_MARK: int = _env_int("POOL_LOW_WATER_MARK", 10)
POOL_HIGH_WATER_MARK: int = _env_int("POOL_HIGH_WATER_MARK", 45)
POOL_ACQUIRE_TIMEOUT: float = _env_float("POOL_ACQUIRE_TIMEOUT", 5.0)

# Warm pool configuration (Phase 3 - pre-warmed resources for low latency)
WARM_POOL_ENABLED: bool = _env_bool("WARM_POOL_ENABLED", True)
WARM_POOL_TTS_SIZE: int = _env_int("WARM_POOL_TTS_SIZE", 3)
WARM_POOL_STT_SIZE: int = _env_int("WARM_POOL_STT_SIZE", 2)
WARM_POOL_BACKGROUND_REFRESH: bool = _env_bool("WARM_POOL_BACKGROUND_REFRESH", True)
WARM_POOL_REFRESH_INTERVAL: float = _env_float("WARM_POOL_REFRESH_INTERVAL", 30.0)
WARM_POOL_SESSION_MAX_AGE: float = _env_float("WARM_POOL_SESSION_MAX_AGE", 1800.0)


# ==============================================================================
# FEATURE FLAGS
# ==============================================================================

DTMF_VALIDATION_ENABLED: bool = _env_bool("DTMF_VALIDATION_ENABLED", False)
ENABLE_AUTH_VALIDATION: bool = _env_bool("ENABLE_AUTH_VALIDATION", False)
ENABLE_ACS_CALL_RECORDING: bool = _env_bool("ENABLE_ACS_CALL_RECORDING", False)

# Environment
DEBUG_MODE: bool = _env_bool("DEBUG", False)
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()

# Documentation (auto-detect based on environment)
_enable_docs_raw = os.getenv("ENABLE_DOCS", "auto").lower()
if _enable_docs_raw == "auto":
    ENABLE_DOCS = ENVIRONMENT not in ("production", "prod", "staging", "uat")
else:
    ENABLE_DOCS = _enable_docs_raw in ("true", "1", "yes", "on")

DOCS_URL: str | None = "/docs" if ENABLE_DOCS else None
REDOC_URL: str | None = "/redoc" if ENABLE_DOCS else None
OPENAPI_URL: str | None = "/openapi.json" if ENABLE_DOCS else None
SECURE_DOCS_URL: str | None = os.getenv("SECURE_DOCS_URL") if ENABLE_DOCS else None

# Monitoring
ENABLE_PERFORMANCE_LOGGING: bool = _env_bool("ENABLE_PERFORMANCE_LOGGING", True)
ENABLE_TRACING: bool = _env_bool("ENABLE_TRACING", True)
METRICS_COLLECTION_INTERVAL: int = _env_int("METRICS_COLLECTION_INTERVAL", 60)
POOL_METRICS_INTERVAL: int = _env_int("POOL_METRICS_INTERVAL", 30)


# ==============================================================================
# SECURITY & CORS
# ==============================================================================

ALLOWED_ORIGINS: list[str] = _env_list("ALLOWED_ORIGINS", "*")

# Import constants for paths (avoid circular import by importing here)
from .constants import ACS_CALL_CALLBACK_PATH, ACS_WEBSOCKET_PATH

ENTRA_EXEMPT_PATHS: list[str] = [
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


# ==============================================================================
# VALIDATION
# ==============================================================================


def validate_settings() -> dict:
    """
    Validate current settings and return validation results.

    Returns:
        Dict with 'valid' (bool), 'issues' (list), 'warnings' (list), 'settings_count' (int)
    """
    issues = []
    warnings = []

    # Pool settings
    if POOL_SIZE_TTS < 1:
        issues.append("POOL_SIZE_TTS must be at least 1")
    elif POOL_SIZE_TTS < 10:
        warnings.append(f"POOL_SIZE_TTS ({POOL_SIZE_TTS}) is quite low for production")

    if POOL_SIZE_STT < 1:
        issues.append("POOL_SIZE_STT must be at least 1")
    elif POOL_SIZE_STT < 10:
        warnings.append(f"POOL_SIZE_STT ({POOL_SIZE_STT}) is quite low for production")

    # Connection settings
    if MAX_WEBSOCKET_CONNECTIONS < 1:
        issues.append("MAX_WEBSOCKET_CONNECTIONS must be at least 1")
    elif MAX_WEBSOCKET_CONNECTIONS > 1000:
        warnings.append(f"MAX_WEBSOCKET_CONNECTIONS ({MAX_WEBSOCKET_CONNECTIONS}) is very high")

    # Timeout settings
    if CONNECTION_TIMEOUT_SECONDS < 60:
        warnings.append(f"CONNECTION_TIMEOUT_SECONDS ({CONNECTION_TIMEOUT_SECONDS}) is quite short")

    # Voice settings - DEFAULT_TTS_VOICE is the primary fallback
    if not DEFAULT_TTS_VOICE:
        issues.append("DEFAULT_TTS_VOICE is empty")

    # Count settings
    import sys

    current_module = sys.modules[__name__]
    settings_count = len(
        [name for name in dir(current_module) if name.isupper() and not name.startswith("_")]
    )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "settings_count": settings_count,
    }


# Alias for backward compatibility
validate_app_settings = validate_settings
