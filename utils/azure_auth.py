# src/utils/azure_auth.py
import logging
import os
from functools import lru_cache

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

logging.getLogger("azure.identity").setLevel(logging.WARNING)

# Timeout for credential acquisition (prevents hanging on auth failures)
_CREDENTIAL_TIMEOUT_SEC = float(os.getenv("AZURE_CREDENTIAL_TIMEOUT_SEC", "10.0"))


def _using_managed_identity() -> bool:
    """Check if running with Managed Identity (Azure hosted environment)."""
    return bool(
        os.getenv("AZURE_CLIENT_ID") or os.getenv("MSI_ENDPOINT") or os.getenv("IDENTITY_ENDPOINT")
    )


def _is_local_dev() -> bool:
    """
    Check if running in local development mode.

    Detection priority:
    1. ENVIRONMENT env var: "dev", "development", "local" = local dev
    2. Azure hosting signals: WEBSITE_SITE_NAME, CONTAINER_APP_NAME = production
    3. Default: assume local dev if no signals present
    """
    env = os.getenv("ENVIRONMENT", "").lower()

    if env not in ("prod", "production", "staging"):
        return True

    # Fall back to Azure hosting signals
    is_azure_hosted = bool(
        os.getenv("WEBSITE_SITE_NAME")  # App Service
        or os.getenv("CONTAINER_APP_NAME")  # Container Apps
        or os.getenv("FUNCTIONS_WORKER_RUNTIME")  # Functions
    )

    return not is_azure_hosted


def _create_credential_internal():
    """
    Internal credential creation - not cached.
    
    Returns the appropriate credential based on environment.
    """
    if _using_managed_identity():
        return ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))

    # For local development, allow CLI credential (from `az login`)
    if _is_local_dev():
        return DefaultAzureCredential(
            exclude_environment_credential=False,
            exclude_managed_identity_credential=True,  # Not available locally
            exclude_workload_identity_credential=True,
            exclude_shared_token_cache_credential=True,
            exclude_visual_studio_code_credential=True,
            exclude_cli_credential=False,  # Allow CLI for local dev
            exclude_powershell_credential=True,
            exclude_interactive_browser_credential=True,
        )

    # "prod-safe" DAC (only env + MI)
    return DefaultAzureCredential(
        exclude_environment_credential=False,
        exclude_managed_identity_credential=False,
        exclude_workload_identity_credential=True,
        exclude_shared_token_cache_credential=True,
        exclude_visual_studio_code_credential=True,
        exclude_cli_credential=True,
        exclude_powershell_credential=True,
        exclude_interactive_browser_credential=True,
    )


@lru_cache(maxsize=1)
def get_credential():
    """
    Get Azure credential based on environment.

    - Managed Identity: Used when AZURE_CLIENT_ID/MSI_ENDPOINT/IDENTITY_ENDPOINT is set
    - Local Dev: Uses CLI credential (requires `az login`)
    - Production: Uses only environment + managed identity credentials
    
    Note: Credential creation is fast, but token acquisition (which happens
    on first use) can be slow. The credential object is cached for reuse.
    """
    return _create_credential_internal()
