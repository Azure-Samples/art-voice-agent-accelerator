"""
Azure App Configuration Provider for CardAPI
=============================================

Seamless integration with Azure App Configuration. Falls back to environment
variables when App Config is not available.

Usage:
    from config import bootstrap_appconfig
    bootstrap_appconfig()  # Call before importing settings
"""

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _log(msg):
    """Log to stderr during bootstrap."""
    print(msg, file=sys.stderr, flush=True)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

APPCONFIG_ENDPOINT = os.getenv("AZURE_APPCONFIG_ENDPOINT", "")
APPCONFIG_LABEL = os.getenv("AZURE_APPCONFIG_LABEL", os.getenv("ENVIRONMENT", "dev"))
APPCONFIG_ENABLED = bool(APPCONFIG_ENDPOINT)

_config: dict[str, Any] | None = None

# Key mapping: App Config keys -> Environment variable names
APPCONFIG_KEY_MAP: dict[str, str] = {
    "azure/cosmos/connection-string": "AZURE_COSMOS_CONNECTION_STRING",
}


# ==============================================================================
# PROVIDER-BASED CONFIGURATION LOADING
# ==============================================================================


def _load_config_from_appconfig() -> dict[str, Any] | None:
    """Load configuration from Azure App Configuration."""
    global _config

    if not APPCONFIG_ENABLED:
        return None

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

        # Load with retry
        import time

        last_error = None
        for attempt in range(1, 4):
            try:
                config = load(
                    endpoint=APPCONFIG_ENDPOINT,
                    credential=credential,
                    selects=[SettingSelector(key_filter="*", label_filter=APPCONFIG_LABEL)],
                    keyvault_credential=credential,
                    replica_discovery_enabled=False,
                )
                config_dict = dict(config)
                _config = config_dict
                return config_dict
            except Exception as e:
                last_error = e
                if attempt < 3:
                    time.sleep(2 ** attempt)

        raise last_error

    except ImportError:
        _log("❌ azure-appconfiguration-provider not installed")
        return None
    except Exception as e:
        _log(f"❌ App Config load failed: {e}")
        return None


def sync_appconfig_to_env(config_dict: dict[str, Any] | None = None) -> dict[str, str]:
    """Sync App Configuration values to environment variables."""
    if config_dict is None:
        config_dict = _config

    if not config_dict:
        return {}

    synced: dict[str, str] = {}

    for appconfig_key, env_var_name in APPCONFIG_KEY_MAP.items():
        # Try exact match, then colon format
        value = config_dict.get(appconfig_key) or config_dict.get(appconfig_key.replace("/", ":"))

        if value is not None:
            os.environ[env_var_name] = str(value)
            synced[env_var_name] = str(value)

    if synced:
        endpoint_name = APPCONFIG_ENDPOINT.split("//")[-1].split(".")[0] if APPCONFIG_ENDPOINT else "unknown"
        _log(f"   App Config ({endpoint_name}): {len(synced)} keys synced")

    return synced


def bootstrap_appconfig() -> bool:
    """
    Bootstrap App Configuration at application startup.

    Call this BEFORE importing settings.

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
