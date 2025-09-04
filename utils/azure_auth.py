# src/utils/azure_auth.py
import os, logging
from functools import lru_cache
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

logging.getLogger("azure.identity").setLevel(logging.WARNING)


def _using_managed_identity() -> bool:
    # Container Apps / Functions / App Service MI signals
    return bool(
        os.getenv("AZURE_CLIENT_ID")
        or os.getenv("MSI_ENDPOINT")
        or os.getenv("IDENTITY_ENDPOINT")
    )


@lru_cache(maxsize=1)
def get_credential():
    if _using_managed_identity():
        return ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))
    # “prod-safe” DAC (only env + MI)
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
