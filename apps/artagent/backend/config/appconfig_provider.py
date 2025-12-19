"""
Azure App Configuration Provider
================================

Provides seamless integration with Azure App Configuration for centralized
configuration management. Falls back to environment variables when App Config
is not available (backwards compatible).

Uses the official azure-appconfiguration-provider package for simplified
configuration loading.

Usage:
    from config.appconfig_provider import get_config_value, get_feature_flag

    # Get a configuration value (falls back to env var)
    endpoint = get_config_value("azure/openai/endpoint", "AZURE_OPENAI_ENDPOINT")

    # Get a feature flag
    if get_feature_flag("warm-pool"):
        enable_warm_pool()

Architecture:
    1. On startup, uses azure-appconfiguration-provider's load() to fetch all config
    2. Syncs fetched values to environment variables for compatibility
    3. Falls back to environment variables if App Config unavailable
"""

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Startup logging to stderr (before logging is configured)
def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

APPCONFIG_ENDPOINT = os.getenv("AZURE_APPCONFIG_ENDPOINT", "")
APPCONFIG_LABEL = os.getenv("AZURE_APPCONFIG_LABEL", os.getenv("ENVIRONMENT", "dev"))
APPCONFIG_ENABLED = bool(APPCONFIG_ENDPOINT)

# Global configuration dictionary (loaded from App Config)
_config: dict[str, Any] | None = None
_config_lock = threading.Lock()

_dotenv_local_keys_cache: set[str] | None = None


def _find_project_root(start: Path) -> Path | None:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def _get_dotenv_local_keys() -> set[str]:
    """Return env var names declared in local env files (.env.local or .env).

    These keys are treated as user-intentional overrides and should not be
    overwritten by App Configuration when running locally.
    """

    global _dotenv_local_keys_cache
    if _dotenv_local_keys_cache is not None:
        return _dotenv_local_keys_cache

    keys: set[str] = set()
    try:
        from dotenv import dotenv_values
    except Exception:
        _dotenv_local_keys_cache = set()
        return _dotenv_local_keys_cache

    backend_dir = Path(__file__).resolve().parents[1]  # .../backend
    project_root = _find_project_root(backend_dir)

    candidates: list[Path] = [
        backend_dir / ".env.local",
        backend_dir / ".env",
    ]
    if project_root is not None:
        candidates.extend([project_root / ".env.local", project_root / ".env"])

    for path in candidates:
        if not path.exists():
            continue
        try:
            values = dotenv_values(path)
            keys.update({k for k in values.keys() if k})
        except Exception:
            # If parsing fails, fall back to empty (do not accidentally protect keys).
            pass

    _dotenv_local_keys_cache = keys
    return _dotenv_local_keys_cache


def _env_override_allowed_when_appconfig_loaded(env_var_name: str) -> bool:
    """Only allow env-var overrides when explicitly set in .env.local."""

    return env_var_name in _get_dotenv_local_keys() and env_var_name in os.environ


# ==============================================================================
# KEY MAPPING: App Config Keys -> Environment Variable Names
# ==============================================================================

# Maps Azure App Configuration keys to their equivalent environment variables
# This enables seamless fallback when App Config is unavailable
APPCONFIG_KEY_MAP: dict[str, str] = {
    # Azure OpenAI
    "azure/openai/endpoint": "AZURE_OPENAI_ENDPOINT",
    "azure/openai/deployment-id": "AZURE_OPENAI_CHAT_DEPLOYMENT_ID",
    "azure/openai/api-version": "AZURE_OPENAI_API_VERSION",
    "azure/openai/default-temperature": "DEFAULT_TEMPERATURE",
    "azure/openai/default-max-tokens": "DEFAULT_MAX_TOKENS",
    "azure/openai/request-timeout": "AOAI_REQUEST_TIMEOUT",
    # Azure Speech
    "azure/speech/endpoint": "AZURE_SPEECH_ENDPOINT",
    "azure/speech/region": "AZURE_SPEECH_REGION",
    "azure/speech/resource-id": "AZURE_SPEECH_RESOURCE_ID",
    # Azure Communication Services
    "azure/acs/endpoint": "ACS_ENDPOINT",
    "azure/acs/immutable-id": "ACS_IMMUTABLE_ID",
    "azure/acs/source-phone-number": "ACS_SOURCE_PHONE_NUMBER",
    "azure/acs/connection-string": "ACS_CONNECTION_STRING",
    # Redis
    "azure/redis/hostname": "REDIS_HOST",
    "azure/redis/port": "REDIS_PORT",
    # Cosmos DB
    "azure/cosmos/database-name": "AZURE_COSMOS_DATABASE_NAME",
    "azure/cosmos/collection-name": "AZURE_COSMOS_COLLECTION_NAME",
    "azure/cosmos/connection-string": "AZURE_COSMOS_CONNECTION_STRING",
    # Storage
    "azure/storage/account-name": "AZURE_STORAGE_ACCOUNT_NAME",
    "azure/storage/container-url": "AZURE_STORAGE_CONTAINER_URL",
    # Voice Live (note: VoiceLiveSettings expects AZURE_VOICELIVE_* format)
    "azure/voicelive/endpoint": "AZURE_VOICELIVE_ENDPOINT",
    "azure/voicelive/model": "AZURE_VOICELIVE_MODEL",
    "azure/voicelive/resource-id": "AZURE_VOICELIVE_RESOURCE_ID",
    
    # Application Insights
    "azure/appinsights/connection-string": "APPLICATIONINSIGHTS_CONNECTION_STRING",
    # Pool Settings
    "app/pools/tts-size": "POOL_SIZE_TTS",
    "app/pools/stt-size": "POOL_SIZE_STT",
    "app/pools/aoai-size": "AOAI_POOL_SIZE",
    "app/pools/low-water-mark": "POOL_LOW_WATER_MARK",
    "app/pools/high-water-mark": "POOL_HIGH_WATER_MARK",
    "app/pools/acquire-timeout": "POOL_ACQUIRE_TIMEOUT",
    "app/pools/warm-tts-size": "WARM_POOL_TTS_SIZE",
    "app/pools/warm-stt-size": "WARM_POOL_STT_SIZE",
    "app/pools/warm-refresh-interval": "WARM_POOL_REFRESH_INTERVAL",
    "app/pools/warm-session-max-age": "WARM_POOL_SESSION_MAX_AGE",
    # Connection Settings
    "app/connections/max-websocket": "MAX_WEBSOCKET_CONNECTIONS",
    "app/connections/queue-size": "CONNECTION_QUEUE_SIZE",
    "app/connections/warning-threshold": "CONNECTION_WARNING_THRESHOLD",
    "app/connections/critical-threshold": "CONNECTION_CRITICAL_THRESHOLD",
    "app/connections/timeout-seconds": "CONNECTION_TIMEOUT_SECONDS",
    "app/connections/heartbeat-interval": "HEARTBEAT_INTERVAL_SECONDS",
    # Session Settings
    "app/session/ttl-seconds": "SESSION_TTL_SECONDS",
    "app/session/cleanup-interval": "SESSION_CLEANUP_INTERVAL",
    "app/session/state-ttl": "SESSION_STATE_TTL",
    "app/session/max-concurrent": "MAX_CONCURRENT_SESSIONS",
    # Voice & TTS Settings
    "app/voice/tts-sample-rate-ui": "TTS_SAMPLE_RATE_UI",
    "app/voice/tts-sample-rate-acs": "TTS_SAMPLE_RATE_ACS",
    "app/voice/tts-chunk-size": "TTS_CHUNK_SIZE",
    "app/voice/tts-processing-timeout": "TTS_PROCESSING_TIMEOUT",
    "app/voice/stt-processing-timeout": "STT_PROCESSING_TIMEOUT",
    "app/voice/silence-duration-ms": "SILENCE_DURATION_MS",
    "app/voice/recognized-languages": "RECOGNIZED_LANGUAGE",
    "app/voice/default-tts-voice": "DEFAULT_TTS_VOICE",
    # Scaling (informational)
    "app/scaling/min-replicas": "CONTAINER_MIN_REPLICAS",
    "app/scaling/max-replicas": "CONTAINER_MAX_REPLICAS",
    # Monitoring
    "app/monitoring/metrics-interval": "METRICS_COLLECTION_INTERVAL",
    "app/monitoring/pool-metrics-interval": "POOL_METRICS_INTERVAL",
    # Environment
    "app/environment": "ENVIRONMENT",
    # Application URLs (set by postprovision)
    "app/backend/base-url": "BASE_URL",
    "app/frontend/backend-url": "VITE_BACKEND_BASE_URL",
    "app/frontend/ws-url": "VITE_WS_BASE_URL",
}

# Feature flag mapping: App Config feature name -> Environment variable name
FEATURE_FLAG_MAP: dict[str, str] = {
    "dtmf-validation": "DTMF_VALIDATION_ENABLED",
    "auth-validation": "ENABLE_AUTH_VALIDATION",
    "call-recording": "ENABLE_ACS_CALL_RECORDING",
    "warm-pool": "WARM_POOL_ENABLED",
    "session-persistence": "ENABLE_SESSION_PERSISTENCE",
    "performance-logging": "ENABLE_PERFORMANCE_LOGGING",
    "tracing": "ENABLE_TRACING",
    "connection-limits": "ENABLE_CONNECTION_LIMITS",
}


# ==============================================================================
# PROVIDER-BASED CONFIGURATION LOADING
# ==============================================================================


def _load_config_from_appconfig() -> dict[str, Any] | None:
    """
    Load all configuration from Azure App Configuration using the provider package.

    Returns:
        Dictionary of all configuration values, or None if loading fails
    """
    global _config

    if not APPCONFIG_ENABLED:
        return None

    # Validate endpoint format
    if not APPCONFIG_ENDPOINT.endswith(".azconfig.io"):
        _log(f"⚠️  Invalid App Config endpoint: {APPCONFIG_ENDPOINT}")
        return None

    try:
        from azure.appconfiguration.provider import SettingSelector, load
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

        # Choose credential based on AZURE_CLIENT_ID
        azure_client_id = os.getenv("AZURE_CLIENT_ID")
        if azure_client_id:
            credential = ManagedIdentityCredential(client_id=azure_client_id)
        else:
            credential = DefaultAzureCredential()

        # Load with retry (exponential backoff)
        import time
        last_error = None

        for attempt in range(1, 4):
            try:
                config = load(
                    endpoint=APPCONFIG_ENDPOINT,
                    credential=credential,
                    selects=[SettingSelector(key_filter="*", label_filter=APPCONFIG_LABEL)],
                    keyvault_credential=credential,
                    replica_discovery_enabled=False,  # Avoid DNS SRV lookup issues
                )

                config_dict = dict(config)

                with _config_lock:
                    _config = config_dict
                return config_dict

            except Exception as e:
                last_error = e
                if attempt < 3:
                    time.sleep(2 ** attempt)  # 2, 4 seconds

        raise last_error

    except ImportError:
        _log("❌ azure-appconfiguration-provider not installed")
        return None
    except Exception as e:
        _log(f"❌ App Config load failed: {e}")
        return None


def sync_appconfig_to_env(config_dict: dict[str, Any] | None = None) -> dict[str, str]:
    """
    Sync App Configuration values to environment variables.

    Args:
        config_dict: Configuration dictionary (uses global if not provided)

    Returns:
        Dict of synced key-value pairs (env_var_name -> value)
    """
    if config_dict is None:
        with _config_lock:
            config_dict = _config

    if not config_dict:
        return {}

    synced: dict[str, str] = {}
    skipped_local = 0

    for appconfig_key, env_var_name in APPCONFIG_KEY_MAP.items():
        # Try exact match, then colon format
        value = config_dict.get(appconfig_key) or config_dict.get(appconfig_key.replace("/", ":"))

        if value is not None:
            # Skip if explicitly set in .env.local
            if _env_override_allowed_when_appconfig_loaded(env_var_name):
                skipped_local += 1
                continue
            os.environ[env_var_name] = str(value)
            synced[env_var_name] = str(value)

    # Single summary line
    endpoint_name = APPCONFIG_ENDPOINT.split("//")[-1].split(".")[0] if APPCONFIG_ENDPOINT else "unknown"
    local_note = f", {skipped_local} local overrides" if skipped_local else ""
    _log(f"   App Config ({endpoint_name}): {len(synced)} keys synced{local_note}")

    return synced


def bootstrap_appconfig() -> bool:
    """
    Bootstrap App Configuration at application startup.

    Call this BEFORE any other imports that depend on environment variables.

    Returns:
        True if App Config loaded successfully, False otherwise
    """
    if not APPCONFIG_ENABLED:
        _log("   App Config: Not configured (using env vars)")
        return False

    config_dict = _load_config_from_appconfig()
    if not config_dict:
        _log("⚠️  App Config: Failed to load (using env vars)")
        return False

    sync_appconfig_to_env(config_dict)
    return True


# ==============================================================================
# PUBLIC API - Configuration Access
# ==============================================================================


def get_config_value(
    appconfig_key: str,
    env_var_name: str | None = None,
    default: str | None = None,
) -> str | None:
    """
    Get a configuration value with fallback:
    1. Loaded App Configuration (in memory)
    2. Environment variable
    3. Default value

    Args:
        appconfig_key: Key in App Configuration (e.g., "azure/openai/endpoint")
        env_var_name: Environment variable name for fallback (auto-mapped if None)
        default: Default value if not found anywhere

    Returns:
        Configuration value or default
    """
    # Determine env var name
    if env_var_name is None:
        env_var_name = APPCONFIG_KEY_MAP.get(appconfig_key)

    # Check loaded config first
    with _config_lock:
        config_loaded = _config is not None
        if _config and appconfig_key in _config:
            return str(_config[appconfig_key])

    # Fall back to environment variable
    if env_var_name:
        # When AppConfig is loaded, ignore ambient env vars unless explicitly
        # provided via .env.local (to avoid surprising/incorrect behavior).
        if APPCONFIG_ENABLED and config_loaded and not _env_override_allowed_when_appconfig_loaded(
            env_var_name
        ):
            return default
        value = os.getenv(env_var_name)
        if value is not None:
            return value

    return default


def get_feature_flag(
    name: str,
    env_var_name: str | None = None,
    default: bool = False,
) -> bool:
    """
    Get a feature flag with fallback:
    1. Loaded App Configuration feature flags
    2. Environment variable (parsed as bool)
    3. Default value

    Args:
        name: Feature flag name (e.g., "warm-pool")
        env_var_name: Environment variable for fallback (auto-mapped if None)
        default: Default value if not found

    Returns:
        Feature flag state (True/False)
    """
    # Determine env var name
    if env_var_name is None:
        env_var_name = FEATURE_FLAG_MAP.get(name)

    # Feature flags in App Config use a special key prefix
    feature_key = f".appconfig.featureflag/{name}"

    # Check loaded config
    with _config_lock:
        config_loaded = _config is not None
        if _config and feature_key in _config:
            flag_data = _config[feature_key]
            if isinstance(flag_data, dict):
                return flag_data.get("enabled", default)
            return bool(flag_data)

    # Fall back to environment variable
    if env_var_name:
        if APPCONFIG_ENABLED and config_loaded and not _env_override_allowed_when_appconfig_loaded(
            env_var_name
        ):
            return default
        env_value = os.getenv(env_var_name, "").lower()
        if env_value in ("true", "1", "yes", "on"):
            return True
        elif env_value in ("false", "0", "no", "off"):
            return False

    return default


def get_config_int(
    appconfig_key: str,
    env_var_name: str | None = None,
    default: int = 0,
) -> int:
    """Get a configuration value as integer."""
    value = get_config_value(appconfig_key, env_var_name)
    if value is not None:
        try:
            return int(value)
        except ValueError:
            logger.warning(f"Invalid int value for {appconfig_key}: {value}")
    return default


def get_config_float(
    appconfig_key: str,
    env_var_name: str | None = None,
    default: float = 0.0,
) -> float:
    """Get a configuration value as float."""
    value = get_config_value(appconfig_key, env_var_name)
    if value is not None:
        try:
            return float(value)
        except ValueError:
            logger.warning(f"Invalid float value for {appconfig_key}: {value}")
    return default


def get_provider_status() -> dict[str, Any]:
    """
    Get the status of the App Configuration provider.

    Returns:
        Dict with status information
    """
    with _config_lock:
        config_loaded = _config is not None
        config_count = len(_config) if _config else 0

    return {
        "enabled": APPCONFIG_ENABLED,
        "endpoint": APPCONFIG_ENDPOINT if APPCONFIG_ENABLED else None,
        "label": APPCONFIG_LABEL,
        "loaded": config_loaded,
        "key_count": config_count,
    }


def refresh_cache() -> None:
    """Clear the configuration and force reload."""
    global _config
    with _config_lock:
        _config = None
    logger.info("App Configuration cleared")


# ==============================================================================
# CONVENIENCE ALIASES
# ==============================================================================

refresh_appconfig_cache = refresh_cache
get_appconfig_status = get_provider_status
initialize_appconfig = bootstrap_appconfig
