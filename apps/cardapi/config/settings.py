"""
CardAPI Settings - Environment Configuration
=============================================

All configuration values loaded from environment variables or Azure App Configuration.
"""

import os

# =============================================================================
# Azure Cosmos DB
# =============================================================================
AZURE_COSMOS_CONNECTION_STRING = os.getenv(
    "AZURE_COSMOS_CONNECTION_STRING",
    "",
)
"""Cosmos DB connection string (OIDC-based for Azure Entra ID authentication)."""

AZURE_COSMOS_DATABASE_NAME = os.getenv(
    "AZURE_COSMOS_DATABASE_NAME",
    "cardapi",
)
"""Cosmos DB database name."""

AZURE_COSMOS_COLLECTION_NAME = os.getenv(
    "AZURE_COSMOS_COLLECTION_NAME",
    "declinecodes",
)
"""Cosmos DB collection name."""
