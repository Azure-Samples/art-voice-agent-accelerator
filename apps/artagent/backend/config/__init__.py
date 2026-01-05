"""
Configuration Package
====================

Centralized configuration for the real-time voice agent.

Structure (4 files):
  - settings.py   : All environment-loaded settings (flat, organized by domain)
  - constants.py  : Hard-coded values that never change
  - types.py      : Dataclass config objects for structured access
  - __init__.py   : This file (exports everything)

Usage:
    # Direct settings access
    from config import POOL_SIZE_TTS, AZURE_OPENAI_ENDPOINT

    # Structured config object
    from config import AppConfig
    config = AppConfig()
    print(config.speech_pools.tts_pool_size)

    # Validation
    from config import validate_settings
    result = validate_settings()
"""

# =============================================================================
# SETTINGS - All environment-loaded configuration
# =============================================================================
# =============================================================================
# APP CONFIGURATION PROVIDER (Phase 2-4)
# =============================================================================
from .appconfig_provider import (  # Initialization; Core functions; Status and monitoring; Cache management
    bootstrap_appconfig,
    get_appconfig_status,  # Alias
    get_config_float,
    get_config_int,
    get_config_value,
    get_feature_flag,
    get_provider_status,
    initialize_appconfig,  # Alias for bootstrap_appconfig
    refresh_appconfig_cache,  # Alias
    refresh_cache,
)

# =============================================================================
# CONSTANTS - Hard-coded values
# =============================================================================
from .constants import (  # API Paths; Voice; Messages; Audio; Languages
    ACS_CALL_CALLBACK_PATH,
    ACS_CALL_INBOUND_PATH,
    ACS_CALL_OUTBOUND_PATH,
    ACS_WEBSOCKET_PATH,
    AVAILABLE_VOICES,
    CHANNELS,
    CHUNK,
    DEFAULT_AUDIO_FORMAT,
    FORMAT,
    GREETING,
    RATE,
    STOP_WORDS,
    SUPPORTED_LANGUAGES,
    TTS_END,
)
from .settings import (  # Azure Communication Services; Security; Azure Identity; Azure OpenAI; Azure Speech; Azure Storage & Cosmos; Voice & TTS (per-agent voice is defined in agent.yaml); Feature Flags; Documentation; Monitoring; Connection Management; Pool Settings; Session Management; Speech Recognition; Warm Pool Settings; Validation
    ACS_AUDIENCE,
    ACS_CONNECTION_STRING,
    ACS_ENDPOINT,
    ACS_ISSUER,
    ACS_JWKS_URL,
    ACS_SOURCE_PHONE_NUMBER,
    ACS_STREAMING_MODE,
    ALLOWED_CLIENT_IDS,
    ALLOWED_ORIGINS,
    AOAI_REQUEST_TIMEOUT,
    AUDIO_FORMAT,
    AZURE_CLIENT_ID,
    AZURE_COSMOS_COLLECTION_NAME,
    AZURE_COSMOS_CONNECTION_STRING,
    AZURE_COSMOS_DATABASE_NAME,
    AZURE_OPENAI_CHAT_DEPLOYMENT_ID,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_SPEECH_ENDPOINT,
    AZURE_SPEECH_KEY,
    AZURE_SPEECH_REGION,
    AZURE_SPEECH_RESOURCE_ID,
    AZURE_STORAGE_CONTAINER_URL,
    AZURE_TENANT_ID,
    AZURE_VOICE_API_KEY,
    AZURE_VOICE_LIVE_ENDPOINT,
    AZURE_VOICE_LIVE_MODEL,
    BACKEND_AUTH_CLIENT_ID,
    BASE_URL,
    CONNECTION_CRITICAL_THRESHOLD,
    CONNECTION_QUEUE_SIZE,
    CONNECTION_TIMEOUT_SECONDS,
    CONNECTION_WARNING_THRESHOLD,
    DEBUG_MODE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TTS_VOICE,
    DEFAULT_VOICE_RATE,
    DEFAULT_VOICE_STYLE,
    DOCS_URL,
    DTMF_VALIDATION_ENABLED,
    ENABLE_ACS_CALL_RECORDING,
    ENABLE_AUTH_VALIDATION,
    ENABLE_CONNECTION_LIMITS,
    ENABLE_DOCS,
    ENABLE_PERFORMANCE_LOGGING,
    ENABLE_SESSION_PERSISTENCE,
    ENABLE_TRACING,
    ENTRA_AUDIENCE,
    ENTRA_EXEMPT_PATHS,
    ENTRA_ISSUER,
    ENTRA_JWKS_URL,
    ENVIRONMENT,
    GREETING_VOICE_TTS,  # Deprecated alias for DEFAULT_TTS_VOICE
    HEARTBEAT_INTERVAL_SECONDS,
    MAX_CONCURRENT_SESSIONS,
    MAX_WEBSOCKET_CONNECTIONS,
    METRICS_COLLECTION_INTERVAL,
    OPENAPI_URL,
    POOL_ACQUIRE_TIMEOUT,
    POOL_HIGH_WATER_MARK,
    POOL_LOW_WATER_MARK,
    POOL_METRICS_INTERVAL,
    POOL_SIZE_STT,
    POOL_SIZE_TTS,
    RECOGNIZED_LANGUAGE,
    REDOC_URL,
    SECURE_DOCS_URL,
    SESSION_CLEANUP_INTERVAL,
    SESSION_STATE_TTL,
    SESSION_TTL_SECONDS,
    SILENCE_DURATION_MS,
    STT_PROCESSING_TIMEOUT,
    TTS_CHUNK_SIZE,
    TTS_PROCESSING_TIMEOUT,
    TTS_SAMPLE_RATE_ACS,
    TTS_SAMPLE_RATE_UI,
    VAD_SEMANTIC_SEGMENTATION,
    WARM_POOL_BACKGROUND_REFRESH,
    WARM_POOL_ENABLED,
    WARM_POOL_MAX_RETRIES,
    WARM_POOL_REFRESH_INTERVAL,
    WARM_POOL_RESTART_ON_FAILURE,
    WARM_POOL_SESSION_MAX_AGE,
    WARM_POOL_STT_SIZE,
    WARM_POOL_TTS_SIZE,
    WARM_POOL_WARMUP_TIMEOUT,
    validate_app_settings,  # Backward compat alias
    validate_settings,
)

# =============================================================================
# TYPES - Structured config objects
# =============================================================================
from .types import (
    AIConfig,
    AppConfig,
    ConnectionConfig,
    MonitoringConfig,
    SecurityConfig,
    SessionConfig,
    SpeechPoolConfig,
    VoiceConfig,
)

# =============================================================================
# CONVENIENCE
# =============================================================================

# Global config instance
app_config = AppConfig()
config = app_config  # Alias


def get_app_config() -> AppConfig:
    """Get the application configuration object."""
    return app_config


def reload_app_config() -> AppConfig:
    """Reload configuration (useful for testing)."""
    global app_config, config
    app_config = AppConfig()
    config = app_config
    return app_config


# =============================================================================
# EXPORTS
# =============================================================================
__all__ = [
    # Config objects
    "AppConfig",
    "SpeechPoolConfig",
    "ConnectionConfig",
    "SessionConfig",
    "VoiceConfig",
    "AIConfig",
    "MonitoringConfig",
    "SecurityConfig",
    "app_config",
    "config",
    "get_app_config",
    "reload_app_config",
    # Validation
    "validate_settings",
    "validate_app_settings",
    # App Configuration Provider
    "get_config_value",
    "get_config_int",
    "get_config_float",
    "get_feature_flag",
    "refresh_cache",
    "refresh_appconfig_cache",
    "get_provider_status",
    "get_appconfig_status",
    "bootstrap_appconfig",
    "initialize_appconfig",
    # Most-used settings (alphabetical)
    "ACS_CONNECTION_STRING",
    "ACS_ENDPOINT",
    "ACS_SOURCE_PHONE_NUMBER",
    "ALLOWED_ORIGINS",
    "DEFAULT_TTS_VOICE",
    "AOAI_REQUEST_TIMEOUT",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_SPEECH_REGION",
    "BASE_URL",
    "DEBUG_MODE",
    "ENABLE_AUTH_VALIDATION",
    "ENABLE_DOCS",
    "ENVIRONMENT",
    "GREETING_VOICE_TTS",
    "MAX_WEBSOCKET_CONNECTIONS",
    "POOL_SIZE_TTS",
    "POOL_SIZE_STT",
    "WARM_POOL_ENABLED",
    "WARM_POOL_TTS_SIZE",
    "WARM_POOL_STT_SIZE",
    "WARM_POOL_RESTART_ON_FAILURE",
    "WARM_POOL_WARMUP_TIMEOUT",
    "WARM_POOL_MAX_RETRIES",
    "SESSION_TTL_SECONDS",
]
