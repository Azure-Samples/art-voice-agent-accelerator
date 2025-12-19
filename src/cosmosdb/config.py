"""
Cosmos DB Configuration Constants
==================================

Single source of truth for Cosmos DB database and collection names.
All modules should import from here to ensure consistency.

Environment variables override these defaults:
- AZURE_COSMOS_DATABASE_NAME -> database name
- AZURE_COSMOS_USERS_COLLECTION_NAME -> users collection name
"""

from __future__ import annotations

import os

# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT VALUES
# ═══════════════════════════════════════════════════════════════════════════════

# The canonical default database for user profiles and demo data.
# All modules (auth, banking, demo_env) should use this same default.
DEFAULT_DATABASE_NAME = "audioagentdb"

# The canonical default collection for user profiles.
DEFAULT_USERS_COLLECTION_NAME = "users"


# ═══════════════════════════════════════════════════════════════════════════════
# GETTERS (with environment variable override)
# ═══════════════════════════════════════════════════════════════════════════════


def get_database_name() -> str:
    """
    Get the Cosmos DB database name.

    Returns:
        Environment variable AZURE_COSMOS_DATABASE_NAME if set,
        otherwise DEFAULT_DATABASE_NAME.
    """
    value = os.getenv("AZURE_COSMOS_DATABASE_NAME")
    if value:
        stripped = value.strip()
        if stripped:
            return stripped
    return DEFAULT_DATABASE_NAME


def get_users_collection_name() -> str:
    """
    Get the users collection name.

    Returns:
        Environment variable AZURE_COSMOS_USERS_COLLECTION_NAME if set,
        otherwise DEFAULT_USERS_COLLECTION_NAME.
    """
    value = os.getenv("AZURE_COSMOS_USERS_COLLECTION_NAME")
    if value:
        stripped = value.strip()
        if stripped:
            return stripped
    return DEFAULT_USERS_COLLECTION_NAME
