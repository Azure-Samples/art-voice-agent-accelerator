"""
Session Loading Services
------------------------

Lightweight helpers for resolving session-scoped user context.
These functions are intentionally in the shared services layer so both
VoiceLive and other entrypoints can reuse the same lookup logic.

Provides:
- load_user_profile_by_email: Fast in-memory lookup by email
- load_user_profile_by_client_id: Cosmos DB lookup by client_id with mock fallback
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from src.cosmosdb.manager import CosmosDBMongoCoreManager

logger = get_logger("services.session_loader")


# ═══════════════════════════════════════════════════════════════════════════════
# COSMOS DB HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

_COSMOS_USERS_MANAGER: CosmosDBMongoCoreManager | None = None


def _get_cosmos_manager() -> CosmosDBMongoCoreManager | None:
    """Get Cosmos manager from app.state if available."""
    try:
        from apps.artagent.backend import main as backend_main
    except Exception:
        return None

    app = getattr(backend_main, "app", None)
    state = getattr(app, "state", None) if app else None
    return getattr(state, "cosmos", None)


def _sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize a value to be JSON-serializable.
    Handles MongoDB extended JSON formats.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, dict):
        if "$date" in obj and len(obj) == 1:
            date_val = obj["$date"]
            return date_val if isinstance(date_val, str) else str(date_val)
        if "$oid" in obj and len(obj) == 1:
            return str(obj["$oid"])
        return {k: _sanitize_for_json(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(item) for item in obj]

    if hasattr(obj, "isoformat"):
        return obj.isoformat()

    if isinstance(obj, bytes):
        import base64

        return base64.b64encode(obj).decode("utf-8")

    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK PROFILES (Single Source of Truth)
# ═══════════════════════════════════════════════════════════════════════════════

# All mock profiles defined once - indexes built at module load
_MOCK_PROFILES = [
    {
        "full_name": "John Smith",
        "client_id": "CLT-001-JS",
        "email": "john.smith@email.com",
        "institution_name": "Contoso Bank",
        "contact_info": {"email": "john.smith@email.com", "phone_last_4": "5678"},
        "customer_intelligence": {
            "relationship_context": {
                "relationship_tier": "Platinum",
                "relationship_duration_years": 8,
            },
            "bank_profile": {
                "current_balance": 45230.50,
                "accountTenureYears": 8,
                "cards": [{"productName": "Cash Rewards"}],
                "behavior_summary": {
                    "travelSpendShare": 0.25,
                    "diningSpendShare": 0.15,
                    "foreignTransactionCount": 4,
                },
            },
            "spending_patterns": {"avg_monthly_spend": 4500},
            "preferences": {"preferredContactMethod": "mobile"},
        },
    },
    {
        "full_name": "Jane Doe",
        "client_id": "CLT-002-JD",
        "email": "jane.doe@email.com",
        "institution_name": "Contoso Bank",
        "contact_info": {"email": "jane.doe@email.com", "phone_last_4": "9012"},
        "customer_intelligence": {
            "relationship_context": {"relationship_tier": "Gold", "relationship_duration_years": 3},
            "bank_profile": {
                "current_balance": 12500.00,
                "accountTenureYears": 3,
                "cards": [{"productName": "Travel Rewards"}],
                "behavior_summary": {
                    "travelSpendShare": 0.40,
                    "diningSpendShare": 0.20,
                    "foreignTransactionCount": 8,
                },
            },
            "spending_patterns": {"avg_monthly_spend": 3200},
            "preferences": {"preferredContactMethod": "email"},
        },
    },
]

# Build lookup indexes at module load
_EMAIL_INDEX: dict[str, dict[str, Any]] = {p["email"].lower(): p for p in _MOCK_PROFILES}
_CLIENT_ID_INDEX: dict[str, dict[str, Any]] = {p["client_id"]: p for p in _MOCK_PROFILES}


@lru_cache(maxsize=64)
def _get_profile_by_email(normalized_email: str) -> dict[str, Any] | None:
    """Return profile if available from the email index."""
    return _EMAIL_INDEX.get(normalized_email)


async def load_user_profile_by_email(email: str) -> dict[str, Any] | None:
    """
    Fetch a user profile by email.

    For now this is a fast in-memory lookup optimized for demo flows. Returns
    None when no profile is available.
    """
    if not email:
        return None

    normalized_email = email.strip().lower()
    profile = _get_profile_by_email(normalized_email)
    if profile:
        return profile

    logger.info("User profile not found for email=%s", email)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT ID LOOKUP (with Cosmos DB support)
# ═══════════════════════════════════════════════════════════════════════════════


async def _lookup_cosmos_by_client_id(client_id: str) -> dict[str, Any] | None:
    """Query Cosmos DB for user by client_id or _id."""
    try:
        from src.cosmosdb.manager import CosmosDBMongoCoreManager
        from src.cosmosdb.config import get_database_name, get_users_collection_name
    except ImportError:
        logger.debug("CosmosDBMongoCoreManager not available")
        return None

    # Use shared config to ensure consistency across all modules
    database_name = get_database_name()
    collection_name = get_users_collection_name()

    try:
        cosmos = CosmosDBMongoCoreManager(
            database_name=database_name,
            collection_name=collection_name,
        )
    except Exception as exc:
        logger.debug("Failed to initialize Cosmos manager: %s", exc)
        return None

    for query in [{"client_id": client_id}, {"_id": client_id}]:
        try:
            document = await asyncio.to_thread(cosmos.read_document, query)
            if document:
                logger.info("📋 Profile loaded from Cosmos by client_id: %s", client_id)
                return _sanitize_for_json(document)
        except Exception as exc:
            logger.debug("Cosmos lookup failed for query %s: %s", query, exc)
            continue

    return None


async def load_user_profile_by_client_id(client_id: str) -> dict[str, Any] | None:
    """
    Fetch a user profile by client_id.

    Attempts Cosmos DB lookup first, then falls back to in-memory mock data.
    This is used by the orchestrator to auto-load user context on agent handoffs.

    Args:
        client_id: Customer identifier (e.g., "CLT-001-JS")

    Returns:
        User profile dict or None if not found
    """
    if not client_id:
        return None

    normalized_id = client_id.strip()

    # Try Cosmos DB first
    cosmos_profile = await _lookup_cosmos_by_client_id(normalized_id)
    if cosmos_profile:
        return cosmos_profile

    # Fall back to mock data using the consolidated index
    mock_profile = _CLIENT_ID_INDEX.get(normalized_id)
    if mock_profile:
        logger.info("📋 Profile loaded from mock data: %s", normalized_id)
        return mock_profile

    logger.debug("User profile not found for client_id=%s", normalized_id)
    return None


__all__ = ["load_user_profile_by_email", "load_user_profile_by_client_id"]
