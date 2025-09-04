"""
Infrastructure Configuration
============================

Azure services configuration including connection strings, endpoints, and resource IDs.
These are typically secrets and should be loaded from environment variables.
"""

import os
import sys
from typing import List
from pathlib import Path

# Add root directory to path for imports
root_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

# StreamMode enum import with fallback
try:
    from src.enums.stream_modes import StreamMode
except ImportError:
    # Define a minimal StreamMode if import fails
    class StreamMode:
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return self.value


# ==============================================================================
# AZURE IDENTITY / TENANT CONFIGURATION
# ==============================================================================

AZURE_CLIENT_ID: str = os.getenv("AZURE_CLIENT_ID", "")
AZURE_TENANT_ID: str = os.getenv("AZURE_TENANT_ID", "")
BACKEND_AUTH_CLIENT_ID: str = os.getenv("BACKEND_AUTH_CLIENT_ID", "")

# ==============================================================================
# AZURE OPENAI CONFIGURATION
# ==============================================================================

AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY: str = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_CHAT_DEPLOYMENT_ID: str = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_ID", "")

# ==============================================================================
# AZURE SPEECH SERVICES CONFIGURATION
# ==============================================================================

AZURE_SPEECH_REGION: str = os.getenv("AZURE_SPEECH_REGION", "")
AZURE_SPEECH_ENDPOINT: str = os.getenv("AZURE_SPEECH_ENDPOINT") or os.environ.get(
    "AZURE_OPENAI_STT_TTS_ENDPOINT", ""
)
AZURE_SPEECH_KEY: str = os.getenv("AZURE_SPEECH_KEY") or os.environ.get(
    "AZURE_OPENAI_STT_TTS_KEY", ""
)
AZURE_SPEECH_RESOURCE_ID: str = os.getenv("AZURE_SPEECH_RESOURCE_ID", "")

# ==============================================================================
# AZURE COMMUNICATION SERVICES (ACS) CONFIGURATION
# ==============================================================================

ACS_ENDPOINT: str = os.getenv("ACS_ENDPOINT", "")
ACS_CONNECTION_STRING: str = os.getenv("ACS_CONNECTION_STRING", "")
ACS_SOURCE_PHONE_NUMBER: str = os.getenv("ACS_SOURCE_PHONE_NUMBER", "")
BASE_URL: str = os.getenv("BASE_URL", "")

# ACS Streaming configuration
ACS_STREAMING_MODE: StreamMode = StreamMode(
    os.getenv("ACS_STREAMING_MODE", "media").lower()
)

# ACS Authentication configuration
ACS_JWKS_URL = "https://acscallautomation.communication.azure.com/calling/keys"
ACS_ISSUER = "https://acscallautomation.communication.azure.com"
ACS_AUDIENCE = os.getenv("ACS_AUDIENCE", "")  # ACS Immutable Resource ID

# ==============================================================================
# AZURE STORAGE CONFIGURATION
# ==============================================================================

# Blob Container URL for recording storage
AZURE_STORAGE_CONTAINER_URL: str = os.getenv("AZURE_STORAGE_CONTAINER_URL", "")

# Azure Cosmos DB configuration
AZURE_COSMOS_CONNECTION_STRING: str = os.getenv("AZURE_COSMOS_CONNECTION_STRING", "")
AZURE_COSMOS_DATABASE_NAME: str = os.getenv("AZURE_COSMOS_DATABASE_NAME", "")
AZURE_COSMOS_COLLECTION_NAME: str = os.getenv("AZURE_COSMOS_COLLECTION_NAME", "")

# ==============================================================================
# AUTHENTICATION CONFIGURATION
# ==============================================================================

# Entra ID configuration
ENTRA_JWKS_URL = (
    f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/discovery/v2.0/keys"
)
ENTRA_ISSUER = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/v2.0"
ENTRA_AUDIENCE = f"api://{BACKEND_AUTH_CLIENT_ID}"

# Allowed client IDs (GUIDs) from environment variable, comma-separated
ALLOWED_CLIENT_IDS: List[str] = [
    cid.strip() for cid in os.getenv("ALLOWED_CLIENT_IDS", "").split(",") if cid.strip()
]
