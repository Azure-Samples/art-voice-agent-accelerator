"""
Configuration Package
====================

Centralized configuration management for the real-time voice agent.

Usage:
    from config import AppConfig, infrastructure, app_settings
    
    # Get main config object
    config = AppConfig()
    
    # Access specific settings
    from config import POOL_SIZE_TTS, MAX_WEBSOCKET_CONNECTIONS
"""

# Import infrastructure settings (Azure services)
from .infrastructure import (
    # Azure Identity
    AZURE_CLIENT_ID,
    AZURE_TENANT_ID,
    BACKEND_AUTH_CLIENT_ID,
    # Azure OpenAI
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_CHAT_DEPLOYMENT_ID,
    # Azure Speech
    AZURE_SPEECH_REGION,
    AZURE_SPEECH_ENDPOINT,
    AZURE_SPEECH_KEY,
    AZURE_SPEECH_RESOURCE_ID,
    # Azure Communication Services
    ACS_ENDPOINT,
    ACS_CONNECTION_STRING,
    ACS_SOURCE_PHONE_NUMBER,
    BASE_URL,
    ACS_STREAMING_MODE,
    ACS_JWKS_URL,
    ACS_ISSUER,
    ACS_AUDIENCE,
    # Azure Storage
    AZURE_STORAGE_CONTAINER_URL,
    # Authentication
    ENTRA_JWKS_URL,
    ENTRA_ISSUER,
    ENTRA_AUDIENCE,
    ALLOWED_CLIENT_IDS,
)

# Import constants
from .constants import (
    # API Endpoints
    ACS_CALL_OUTBOUND_PATH,
    ACS_CALL_INBOUND_PATH,
    ACS_CALL_CALLBACK_PATH,
    ACS_WEBSOCKET_PATH,
    # Audio constants
    RATE,
    CHANNELS,
    FORMAT,
    CHUNK,
    # Voice and TTS
    AVAILABLE_VOICES,
    TTS_END,
    STOP_WORDS,
    # Messages
    GREETING,
    # Supported languages
    SUPPORTED_LANGUAGES,
    DEFAULT_AUDIO_FORMAT,
)

# Import application settings
from .app_settings import (
    # Agent configurations
    AGENT_AUTH_CONFIG,
    AGENT_CLAIM_INTAKE_CONFIG,
    AGENT_GENERAL_INFO_CONFIG,
    # Speech service settings
    POOL_SIZE_TTS,
    POOL_SIZE_STT,
    POOL_LOW_WATER_MARK,
    POOL_HIGH_WATER_MARK,
    POOL_ACQUIRE_TIMEOUT,
    STT_PROCESSING_TIMEOUT,
    TTS_PROCESSING_TIMEOUT,
    # Voice settings
    GREETING_VOICE_TTS,
    DEFAULT_VOICE_STYLE,
    DEFAULT_VOICE_RATE,
    TTS_SAMPLE_RATE_UI,
    TTS_SAMPLE_RATE_ACS,
    TTS_CHUNK_SIZE,
    get_agent_voice,
    # Speech recognition
    VAD_SEMANTIC_SEGMENTATION,
    SILENCE_DURATION_MS,
    AUDIO_FORMAT,
    RECOGNIZED_LANGUAGE,
    # Connection management
    MAX_WEBSOCKET_CONNECTIONS,
    CONNECTION_QUEUE_SIZE,
    ENABLE_CONNECTION_LIMITS,
    CONNECTION_WARNING_THRESHOLD,
    CONNECTION_CRITICAL_THRESHOLD,
    CONNECTION_TIMEOUT_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS,
    # Session management
    SESSION_TTL_SECONDS,
    SESSION_CLEANUP_INTERVAL,
    MAX_CONCURRENT_SESSIONS,
    ENABLE_SESSION_PERSISTENCE,
    SESSION_STATE_TTL,
    # Feature flags
    DTMF_VALIDATION_ENABLED,
    ENABLE_AUTH_VALIDATION,
    # AI settings
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    AOAI_REQUEST_TIMEOUT,
    # CORS and security
    ALLOWED_ORIGINS,
    ENTRA_EXEMPT_PATHS,
    # Documentation and environment
    ENVIRONMENT,
    DEBUG_MODE,
    ENABLE_DOCS,
    DOCS_URL,
    REDOC_URL,
    OPENAPI_URL,
    SECURE_DOCS_URL,
    # Monitoring
    ENABLE_PERFORMANCE_LOGGING,
    ENABLE_TRACING,
    METRICS_COLLECTION_INTERVAL,
    POOL_METRICS_INTERVAL,
    # Validation
    validate_app_settings,
)

# Import structured config objects
from .app_config import (
    AppConfig,
    SpeechPoolConfig,
    ConnectionConfig,
    SessionConfig,
    VoiceConfig,
    MonitoringConfig,
    SecurityConfig,
)

# Main config instance - single source of truth
app_config = AppConfig()

# Quick access aliases for most commonly used settings
config = app_config

# ==============================================================================
# MANAGEMENT FUNCTIONS
# ==============================================================================


def get_app_config() -> AppConfig:
    """Get the main application configuration object."""
    return app_config


def reload_app_config() -> AppConfig:
    """Reload the application configuration (useful for testing)."""
    global app_config
    app_config = AppConfig()
    return app_config


def validate_and_log_config():
    """Validate configuration and log results."""
    import logging

    logger = logging.getLogger(__name__)

    result = validate_app_settings()

    if result["valid"]:
        logger.info(
            f"✅ Configuration validation passed ({result['settings_count']} settings)"
        )
    else:
        logger.error(
            f"❌ Configuration validation failed with {len(result['issues'])} issues"
        )
        for issue in result["issues"]:
            logger.error(f"Config issue: {issue}")

    if result["warnings"]:
        for warning in result["warnings"]:
            logger.warning(f"Config warning: {warning}")

    return result


def get_speech_pool_config() -> SpeechPoolConfig:
    """Get speech pool configuration."""
    return app_config.speech_pools


def get_connection_config() -> ConnectionConfig:
    """Get connection configuration."""
    return app_config.connections


def get_session_config() -> SessionConfig:
    """Get session configuration."""
    return app_config.sessions


def get_monitoring_config() -> MonitoringConfig:
    """Get monitoring configuration."""
    return app_config.monitoring


# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    # Main config objects
    "app_config",
    "config",
    "AppConfig",
    # Config sections
    "SpeechPoolConfig",
    "ConnectionConfig",
    "SessionConfig",
    "VoiceConfig",
    "MonitoringConfig",
    "SecurityConfig",
    # Management functions
    "get_app_config",
    "reload_app_config",
    "validate_and_log_config",
    "get_speech_pool_config",
    "get_connection_config",
    "get_session_config",
    "get_monitoring_config",
    # Most commonly used settings
    "POOL_SIZE_TTS",
    "POOL_SIZE_STT",
    "MAX_WEBSOCKET_CONNECTIONS",
    "CONNECTION_QUEUE_SIZE",
    "ENABLE_CONNECTION_LIMITS",
    "SESSION_TTL_SECONDS",
    "GREETING_VOICE_TTS",
    "AOAI_REQUEST_TIMEOUT",
    "ENVIRONMENT",
    "DEBUG_MODE",
    # Infrastructure (Azure services)
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_SPEECH_REGION",
    "ACS_ENDPOINT",
    "BASE_URL",
    # Authentication
    "ENABLE_AUTH_VALIDATION",
    "ENTRA_EXEMPT_PATHS",
    "ALLOWED_ORIGINS",
    # Agent configs
    "AGENT_AUTH_CONFIG",
    "AGENT_CLAIM_INTAKE_CONFIG",
    "AGENT_GENERAL_INFO_CONFIG",
    # API paths
    "ACS_CALL_OUTBOUND_PATH",
    "ACS_CALL_INBOUND_PATH",
    "ACS_CALL_CALLBACK_PATH",
    "ACS_WEBSOCKET_PATH",
    # Data storage
    "AZURE_COSMOS_CONNECTION_STRING",
    "AZURE_COSMOS_DATABASE_NAME",
    "AZURE_COSMOS_COLLECTION_NAME",
    # Voice and speech
    "AUDIO_FORMAT",
    "RECOGNIZED_LANGUAGE",
    "VAD_SEMANTIC_SEGMENTATION",
    "SILENCE_DURATION_MS",
    # Documentation
    "ENABLE_DOCS",
    "DOCS_URL",
    "REDOC_URL",
    "OPENAPI_URL",
    # Validation
    "validate_app_settings",
]
