"""
Banking Tools
=============

Core banking tools for account info, transactions, cards, and user profiles.
"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

from .constants import (
    CARD_KNOWLEDGE_BASE,
    CARD_PRODUCTS,
    CREDIT_LIMITS_BY_INCOME,
    card_product_to_dict,
    get_card_product,
)

try:  # pragma: no cover - optional dependency during tests
    from src.cosmosdb.manager import CosmosDBMongoCoreManager as _CosmosManagerImpl
    from src.cosmosdb.config import get_database_name, get_users_collection_name
except Exception:  # pragma: no cover - handled at runtime
    _CosmosManagerImpl = None
    # Fallback if config import fails
    def get_database_name() -> str:
        return os.getenv("AZURE_COSMOS_DATABASE_NAME", "audioagentdb")
    def get_users_collection_name() -> str:
        return os.getenv("AZURE_COSMOS_USERS_COLLECTION_NAME", "users")

# Email service for sending card agreements
try:
    from src.acs.email_service import send_email as send_email_async, is_email_configured
except ImportError:
    send_email_async = None
    is_email_configured = lambda: False

# Redis for MFA code storage
try:
    from src.redis.manager import AzureRedisManager
    _REDIS_MANAGER: AzureRedisManager | None = None
    
    def _get_redis_manager() -> AzureRedisManager | None:
        """Get or create Redis manager for MFA code storage."""
        global _REDIS_MANAGER
        if _REDIS_MANAGER is None:
            try:
                _REDIS_MANAGER = AzureRedisManager()
            except Exception as exc:
                logger.warning("Could not initialize Redis manager: %s", exc)
        return _REDIS_MANAGER
except ImportError:
    _get_redis_manager = lambda: None

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.cosmosdb.manager import CosmosDBMongoCoreManager

logger = get_logger("agents.tools.banking")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

get_user_profile_schema: dict[str, Any] = {
    "name": "get_user_profile",
    "description": (
        "Retrieve customer profile including account info, preferences, and relationship tier. "
        "Call this immediately after identity verification."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
        },
        "required": ["client_id"],
    },
}

get_account_summary_schema: dict[str, Any] = {
    "name": "get_account_summary",
    "description": (
        "Get summary of customer's accounts including balances, account numbers, and routing info. "
        "Useful for direct deposit setup or balance inquiries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
        },
        "required": ["client_id"],
    },
}

get_recent_transactions_schema: dict[str, Any] = {
    "name": "get_recent_transactions",
    "description": (
        "Get recent transactions for customer's primary account. "
        "Includes merchant, amount, date, and fee breakdowns."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "limit": {"type": "integer", "description": "Max transactions to return (default 10)"},
        },
        "required": ["client_id"],
    },
}

search_card_products_schema: dict[str, Any] = {
    "name": "search_card_products",
    "description": (
        "Search available credit card products based on customer profile and preferences. "
        "Returns personalized card recommendations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "customer_profile": {
                "type": "string",
                "description": "Customer tier and spending info",
            },
            "preferences": {
                "type": "string",
                "description": "What they want (travel, cash back, etc.)",
            },
            "spending_categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Categories like travel, dining, groceries",
            },
        },
        "required": ["preferences"],
    },
}

get_card_details_schema: dict[str, Any] = {
    "name": "get_card_details",
    "description": "Get detailed information about a specific card product.",
    "parameters": {
        "type": "object",
        "properties": {
            "product_id": {"type": "string", "description": "Card product ID"},
            "query": {"type": "string", "description": "Specific question about the card"},
        },
        "required": ["product_id"],
    },
}

refund_fee_schema: dict[str, Any] = {
    "name": "refund_fee",
    "description": (
        "Process a fee refund for the customer as a courtesy. "
        "Only call after customer explicitly approves the refund."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "transaction_id": {"type": "string", "description": "ID of the fee transaction"},
            "amount": {"type": "number", "description": "Amount to refund"},
            "reason": {"type": "string", "description": "Reason for refund"},
        },
        "required": ["client_id", "amount"],
    },
}

send_card_agreement_schema: dict[str, Any] = {
    "name": "send_card_agreement",
    "description": "Send cardholder agreement email with verification code for e-signature.",
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "card_product_id": {"type": "string", "description": "Card product ID"},
        },
        "required": ["client_id", "card_product_id"],
    },
}

verify_esignature_schema: dict[str, Any] = {
    "name": "verify_esignature",
    "description": "Verify the e-signature code provided by customer.",
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "verification_code": {"type": "string", "description": "6-digit code from email"},
        },
        "required": ["client_id", "verification_code"],
    },
}

finalize_card_application_schema: dict[str, Any] = {
    "name": "finalize_card_application",
    "description": "Complete card application after e-signature verification.",
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "card_product_id": {"type": "string", "description": "Card product ID"},
            "card_name": {"type": "string", "description": "Full card product name"},
        },
        "required": ["client_id", "card_product_id"],
    },
}

search_credit_card_faqs_schema: dict[str, Any] = {
    "name": "search_credit_card_faqs",
    "description": "Search credit card FAQ knowledge base for information about APR, fees, benefits, eligibility, and rewards. Returns relevant FAQ entries matching the query.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g., 'APR', 'foreign transaction fees', 'travel insurance')",
            },
            "card_name": {
                "type": "string",
                "description": "Optional card name to filter results (e.g., 'Travel Rewards', 'Premium Rewards')",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 3)",
            },
        },
        "required": ["query"],
    },
}

evaluate_card_eligibility_schema: dict[str, Any] = {
    "name": "evaluate_card_eligibility",
    "description": (
        "Evaluate if a customer is pre-approved or eligible for a specific credit card. "
        "Returns eligibility status, credit limit estimate, and next steps."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "card_product_id": {"type": "string", "description": "Card product to evaluate eligibility for"},
        },
        "required": ["client_id", "card_product_id"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# COSMOS DB HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

_COSMOS_USERS_MANAGER: CosmosDBMongoCoreManager | None = None

# User profiles config imported from src.cosmosdb.config (get_database_name, get_users_collection_name)


def _manager_targets_collection(
    manager: CosmosDBMongoCoreManager,
    database_name: str,
    collection_name: str,
) -> bool:
    """Return True when the manager already points to the requested db/collection."""
    try:
        db_name = getattr(getattr(manager, "database", None), "name", None)
        coll_name = getattr(getattr(manager, "collection", None), "name", None)
    except Exception:
        return False
    return db_name == database_name and coll_name == collection_name


def _get_cosmos_manager() -> CosmosDBMongoCoreManager | None:
    """Resolve the shared Cosmos DB client from FastAPI app state."""
    try:
        from apps.artagent.backend import main as backend_main
    except Exception:
        return None

    app = getattr(backend_main, "app", None)
    state = getattr(app, "state", None) if app else None
    return getattr(state, "cosmos", None)


def _get_demo_users_manager() -> CosmosDBMongoCoreManager | None:
    """Return a Cosmos DB manager pointed at the demo users collection."""
    global _COSMOS_USERS_MANAGER
    database_name = get_database_name()
    container_name = get_users_collection_name()

    if _COSMOS_USERS_MANAGER is not None:
        if _manager_targets_collection(_COSMOS_USERS_MANAGER, database_name, container_name):
            return _COSMOS_USERS_MANAGER
        logger.warning("Cached Cosmos users manager pointed to different collection; refreshing")
        _COSMOS_USERS_MANAGER = None

    base_manager = _get_cosmos_manager()
    if base_manager is not None:
        if _manager_targets_collection(base_manager, database_name, container_name):
            _COSMOS_USERS_MANAGER = base_manager
            return _COSMOS_USERS_MANAGER
        logger.info("Base Cosmos manager uses different collection; creating scoped users manager")

    if _CosmosManagerImpl is None:
        logger.warning("Cosmos manager implementation unavailable; cannot query users collection")
        return None

    try:
        _COSMOS_USERS_MANAGER = _CosmosManagerImpl(
            database_name=database_name,
            collection_name=container_name,
        )
        logger.info(
            "Banking tools connected to Cosmos users collection | db=%s collection=%s",
            database_name,
            container_name,
        )
        return _COSMOS_USERS_MANAGER
    except Exception as exc:
        logger.warning("Unable to initialize Cosmos users manager: %s", exc)
        return None


def _sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize a value to be JSON-serializable.

    Handles:
    - BSON ObjectId → str
    - datetime → ISO string
    - MongoDB extended JSON ({"$date": ...}) → ISO string
    - bytes → base64 string
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, dict):
        # Handle MongoDB extended JSON date format
        if "$date" in obj and len(obj) == 1:
            date_val = obj["$date"]
            if isinstance(date_val, str):
                return date_val
            return str(date_val)
        # Handle MongoDB ObjectId format
        if "$oid" in obj and len(obj) == 1:
            return str(obj["$oid"])
        # Recursively process dict
        return {k: _sanitize_for_json(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(item) for item in obj]

    # Handle datetime
    if hasattr(obj, "isoformat"):
        return obj.isoformat()

    # Handle bytes
    if isinstance(obj, bytes):
        import base64

        return base64.b64encode(obj).decode("utf-8")

    # Fallback: convert to string
    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


async def _lookup_user_by_client_id(client_id: str) -> dict[str, Any] | None:
    """Query Cosmos DB for user by client_id or _id."""
    cosmos = _get_demo_users_manager()
    if cosmos is None:
        return None

    # Try both client_id field and _id (MongoDB document ID)
    queries = [
        {"client_id": client_id},
        {"_id": client_id},
    ]

    for query in queries:
        try:
            document = await asyncio.to_thread(cosmos.read_document, query)
            if document:
                logger.info("📋 User profile loaded from Cosmos: %s", client_id)
                # Sanitize document for JSON serialization
                return _sanitize_for_json(document)
        except Exception as exc:
            logger.debug("Cosmos lookup failed for query %s: %s", query, exc)
            continue

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# E-SIGN STATE (Session-scoped in Redis)
# ═══════════════════════════════════════════════════════════════════════════════

# Session-scoped TTL for card application data (24 hours)
_CARD_APP_TTL_SECONDS = 86400


def _build_card_app_redis_key(session_id: str, client_id: str) -> str:
    """Build a session-scoped Redis key for card application context."""
    return f"session:{session_id}:card_application:{client_id}"


async def _store_card_application(
    session_id: str,
    client_id: str,
    card_product_id: str,
    credit_limit: int,
    eligibility_status: str,
    customer_tier: str,
    card_name: str,
    **extra_data: Any,
) -> bool:
    """Store card application context in session-scoped Redis."""
    redis_mgr = _get_redis_manager()
    if not redis_mgr:
        logger.warning("Redis not available for card application storage")
        return False
    
    import json
    key = _build_card_app_redis_key(session_id, client_id)
    value = json.dumps({
        "card_product_id": card_product_id,
        "credit_limit": credit_limit,
        "eligibility_status": eligibility_status,
        "customer_tier": customer_tier,
        "card_name": card_name,
        "created_at": datetime.now(UTC).isoformat(),
        "verified": False,
        "finalized": False,
        **extra_data,
    })
    
    try:
        await redis_mgr.set_value_async(key, value, ttl_seconds=_CARD_APP_TTL_SECONDS)
        logger.info("📋 Card application stored: session=%s client=%s product=%s limit=$%d",
                   session_id, client_id, card_product_id, credit_limit)
        return True
    except Exception as exc:
        logger.warning("Could not store card application in Redis: %s", exc)
        return False


async def _get_card_application(session_id: str, client_id: str) -> dict[str, Any] | None:
    """Retrieve card application context from Redis."""
    redis_mgr = _get_redis_manager()
    if not redis_mgr:
        return None
    
    import json
    key = _build_card_app_redis_key(session_id, client_id)
    
    try:
        value = await asyncio.to_thread(redis_mgr.get_value, key)
        if value:
            return json.loads(value)
    except Exception as exc:
        logger.warning("Could not read card application from Redis: %s", exc)
    return None


async def _update_card_application(session_id: str, client_id: str, **updates: Any) -> bool:
    """Update card application context in Redis."""
    existing = await _get_card_application(session_id, client_id)
    if not existing:
        return False
    
    redis_mgr = _get_redis_manager()
    if not redis_mgr:
        return False
    
    import json
    existing.update(updates)
    existing["updated_at"] = datetime.now(UTC).isoformat()
    
    key = _build_card_app_redis_key(session_id, client_id)
    try:
        await redis_mgr.set_value_async(key, json.dumps(existing), ttl_seconds=_CARD_APP_TTL_SECONDS)
        logger.info("📋 Card application updated: session=%s client=%s", session_id, client_id)
        return True
    except Exception as exc:
        logger.warning("Could not update card application in Redis: %s", exc)
        return False


async def _delete_card_application(session_id: str, client_id: str) -> None:
    """Delete card application context from Redis after finalization."""
    redis_mgr = _get_redis_manager()
    if not redis_mgr:
        return
    
    key = _build_card_app_redis_key(session_id, client_id)
    
    try:
        await asyncio.to_thread(redis_mgr.delete_key, key)
        logger.info("🗑️ Card application deleted: session=%s client=%s", session_id, client_id)
    except Exception as exc:
        logger.debug("Could not delete card application from Redis: %s", exc)


# Session-scoped TTL for e-sign codes (24 hours)
_ESIGN_CODE_TTL_SECONDS = 86400


def _build_esign_redis_key(session_id: str, client_id: str) -> str:
    """Build a session-scoped Redis key for e-sign verification codes."""
    return f"session:{session_id}:esign_code:{client_id}"


async def _store_esign_code(
    session_id: str, client_id: str, code: str, card_product_id: str
) -> bool:
    """Store e-sign verification code in Redis with session scope."""
    redis_mgr = _get_redis_manager()
    if not redis_mgr:
        logger.warning("Redis not available for e-sign code storage")
        return False
    
    import json
    key = _build_esign_redis_key(session_id, client_id)
    value = json.dumps({"code": code, "card_product_id": card_product_id})
    
    try:
        await redis_mgr.set_value_async(key, value, ttl_seconds=_ESIGN_CODE_TTL_SECONDS)
        logger.info("🔑 E-sign code stored: session=%s client=%s", session_id, client_id)
        return True
    except Exception as exc:
        logger.warning("Could not store e-sign code in Redis: %s", exc)
        return False


async def _get_esign_code(session_id: str, client_id: str) -> dict[str, str] | None:
    """Retrieve e-sign verification code from Redis."""
    redis_mgr = _get_redis_manager()
    if not redis_mgr:
        return None
    
    import json
    key = _build_esign_redis_key(session_id, client_id)
    
    try:
        value = await asyncio.to_thread(redis_mgr.get_value, key)
        if value:
            return json.loads(value)
    except Exception as exc:
        logger.warning("Could not read e-sign code from Redis: %s", exc)
    return None


async def _delete_esign_code(session_id: str, client_id: str) -> None:
    """Delete e-sign verification code from Redis after successful verification."""
    redis_mgr = _get_redis_manager()
    if not redis_mgr:
        return
    
    key = _build_esign_redis_key(session_id, client_id)
    
    try:
        await asyncio.to_thread(redis_mgr.delete_key, key)
        logger.info("🗑️ E-sign code deleted: session=%s client=%s", session_id, client_id)
    except Exception as exc:
        logger.debug("Could not delete e-sign code from Redis: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def get_user_profile(args: dict[str, Any]) -> dict[str, Any]:
    """Get customer profile from Cosmos DB."""
    client_id = (args.get("client_id") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    # Get profile from Cosmos DB
    profile = await _lookup_user_by_client_id(client_id)
    if profile:
        return {"success": True, "profile": profile, "data_source": "cosmos"}

    return {"success": False, "message": f"Profile not found for {client_id}. Please create a profile first."}


async def get_account_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get account summary with balances and routing info."""
    client_id = (args.get("client_id") or "").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    # First, check if session profile was injected by the orchestrator
    profile = args.get("_session_profile")
    data_source = "session"
    
    # Fallback to Cosmos DB lookup if no session profile
    if not profile:
        profile = await _lookup_user_by_client_id(client_id)
        data_source = "cosmos"

    if not profile:
        return {"success": False, "message": f"Account not found for {client_id}. Please create a profile first."}

    # Extract account data from customer_intelligence
    customer_intel = profile.get("customer_intelligence", {})
    bank_profile = customer_intel.get("bank_profile", {})
    accounts_data = customer_intel.get("accounts", {})
    
    # Build accounts list from actual data
    accounts = []
    
    # Checking account
    checking = accounts_data.get("checking", {})
    if checking:
        accounts.append({
            "type": "checking",
            "balance": checking.get("balance", 0),
            "available": checking.get("available", checking.get("balance", 0)),
            "account_number_last4": checking.get("account_number_last4", bank_profile.get("account_number_last4", "----")),
            "routing_number": bank_profile.get("routing_number", "021000021"),
        })
    
    # Savings account
    savings = accounts_data.get("savings", {})
    if savings:
        accounts.append({
            "type": "savings",
            "balance": savings.get("balance", 0),
            "available": savings.get("available", savings.get("balance", 0)),
            "account_number_last4": savings.get("account_number_last4", "----"),
            "routing_number": bank_profile.get("routing_number", "021000021"),
        })
    
    # Fallback if no accounts data available
    if not accounts:
        balance = (
            customer_intel.get("account_status", {}).get("current_balance")
            or bank_profile.get("current_balance")
            or 0
        )
        accounts = [
            {
                "type": "checking",
                "balance": balance,
                "available": balance,
                "account_number_last4": bank_profile.get("account_number_last4", "----"),
                "routing_number": bank_profile.get("routing_number", "021000021"),
            },
        ]

    return {
        "success": True,
        "accounts": accounts,
    }


async def get_recent_transactions(args: dict[str, Any]) -> dict[str, Any]:
    """Get recent transactions from user profile or fallback to mock data."""
    client_id = (args.get("client_id") or "").strip()
    limit = args.get("limit", 10)

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    # First, check if session profile was injected by the orchestrator
    # This avoids redundant Cosmos DB lookups for already-loaded profiles
    session_profile = args.get("_session_profile")
    if session_profile:
        customer_intel = session_profile.get("demo_metadata", {})
        transactions = customer_intel.get("transactions", [])
        if transactions:
            logger.info("📋 Loaded %d transactions from session profile: %s", len(transactions), client_id)
            return {
                "success": True,
                "transactions": transactions[:limit],
                "data_source": "session",
            }

    # Fallback: Try to get transactions from Cosmos DB
    profile = await _lookup_user_by_client_id(client_id)
    if profile:
        customer_intel = profile.get("demo_metadata", {})
        transactions = customer_intel.get("transactions", [])
        if transactions:
            logger.info("📋 Loaded %d transactions from Cosmos: %s", len(transactions), client_id)
            return {
                "success": True,
                "transactions": transactions[:limit],
                "data_source": "cosmos",
            }

    # No transactions found - require profile creation first
    logger.warning("⚠️ No transactions found for: %s", client_id)
    return {
        "success": False,
        "message": f"No transactions found for {client_id}. Please create a demo profile first.",
        "transactions": [],
    }


async def search_card_products(args: dict[str, Any]) -> dict[str, Any]:
    """Search for card products based on preferences using CARD_PRODUCTS from constants."""
    preferences = (args.get("preferences") or "").strip().lower()
    categories = args.get("spending_categories", [])

    results = []
    for card in CARD_PRODUCTS.values():
        score = 0
        card_name_lower = card.name.lower()
        best_for_str = " ".join(card.best_for).lower()
        
        # Score based on preferences - more flexible keyword matching
        pref_words = preferences.split()
        
        # Travel-related
        if any(w in preferences for w in ["travel", "international", "abroad", "overseas"]):
            if "travel" in card_name_lower or "travel" in best_for_str:
                score += 3
            if card.foreign_transaction_fee == 0:
                score += 4  # Strong match for international
        
        # Cash back related
        if any(w in preferences for w in ["cash", "cashback", "cash back"]):
            if "cash" in card_name_lower:
                score += 3
        
        # Fee-related preferences
        if any(w in preferences for w in ["foreign", "forex", "ftf", "international fee"]):
            if card.foreign_transaction_fee == 0:
                score += 5  # Very strong match
            else:
                score -= 2  # Penalize cards with foreign fees
        
        if any(w in preferences for w in ["no fee", "no annual", "free"]):
            if card.annual_fee == 0:
                score += 2
        
        # Premium/rewards preferences
        if any(w in preferences for w in ["premium", "rewards", "points", "bonus"]):
            if "premium" in card_name_lower or "rewards" in card_name_lower:
                score += 2
        
        # Score based on spending categories
        for cat in categories:
            cat_lower = cat.lower()
            if cat_lower in best_for_str:
                score += 2
            # Check for travel/international in categories
            if cat_lower in ["international travel", "travel", "international"]:
                if card.foreign_transaction_fee == 0:
                    score += 3
        
        # Build result with score
        card_dict = card_product_to_dict(card)
        card_dict["_score"] = score
        card_dict["_foreign_fee_free"] = card.foreign_transaction_fee == 0
        results.append(card_dict)

    # Sort by score (highest first)
    results.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # Always return all cards so agent can recommend
    return {
        "success": True,
        "cards": results,
        "available_product_ids": list(CARD_PRODUCTS.keys()),
        "best_match": results[0]["product_id"] if results else None,
        "no_foreign_fee_cards": [c["product_id"] for c in results if c.get("_foreign_fee_free")],
        "message": f"Found {len(results)} cards. Best matches listed first. Cards with no foreign transaction fees: travel-rewards-001, premium-rewards-001. IMPORTANT: Use exact 'product_id' values when calling other tools.",
    }


async def get_card_details(args: dict[str, Any]) -> dict[str, Any]:
    """Get details for a specific card from CARD_PRODUCTS."""
    product_id = (args.get("product_id") or "").strip()
    query = (args.get("query") or "").strip()

    card = get_card_product(product_id)
    if not card:
        return {"success": False, "message": f"Card {product_id} not found"}

    return {"success": True, "card": card_product_to_dict(card)}


async def refund_fee(args: dict[str, Any]) -> dict[str, Any]:
    """Process fee refund."""
    client_id = (args.get("client_id") or "").strip()
    amount = args.get("amount", 0)
    reason = (args.get("reason") or "courtesy refund").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    logger.info("💰 Fee refund processed: %s - $%.2f", client_id, amount)

    return {
        "success": True,
        "refunded": True,
        "amount": amount,
        "message": f"Refund of ${amount:.2f} processed. Credit in 2 business days.",
    }


async def send_card_agreement(args: dict[str, Any]) -> dict[str, Any]:
    """Send card agreement email with verification code and store in session-scoped Redis for MFA."""
    client_id = (args.get("client_id") or "").strip()
    product_id = (args.get("card_product_id") or "").strip()
    session_id = args.get("session_id", "default")

    if not client_id or not product_id:
        return {"success": False, "message": "client_id and card_product_id required."}

    card = get_card_product(product_id)
    if not card:
        return {"success": False, "message": f"Card {product_id} not found"}

    # Generate verification code
    import string
    code = "".join(random.choices(string.digits, k=6))

    # Store verification code in session-scoped Redis for MFA verification
    redis_stored = await _store_esign_code(session_id, client_id, code, product_id)

    # Get customer email from Cosmos DB
    profile = await _lookup_user_by_client_id(client_id)
    email = profile.get("contact_info", {}).get("email", "customer@email.com") if profile else "customer@email.com"
    full_name = profile.get("full_name", "Valued Customer") if profile else "Valued Customer"

    # Build email content
    subject = f"Your {card.name} Verification Code"
    plain_text_body = f"""Dear {full_name},

Thank you for choosing the {card.name}.

Your verification code is: {code}

This code expires in 24 hours.

Card Highlights:
• Annual Fee: ${card.annual_fee}
• Rewards: {card.rewards_rate}
• Foreign Transaction Fee: {card.foreign_transaction_fee}%

If you did not request this, please contact us at 1-800-555-0100.

Contoso Bank
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #0f172a;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="100%" style="max-width: 520px;" cellpadding="0" cellspacing="0">
                    <!-- Logo -->
                    <tr>
                        <td style="padding-bottom: 32px; text-align: center;">
                            <span style="font-size: 28px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">Contoso</span>
                            <span style="font-size: 28px; font-weight: 300; color: #60a5fa;">Bank</span>
                        </td>
                    </tr>
                    <!-- Main Card -->
                    <tr>
                        <td style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 40px;">
                            <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 600; color: #ffffff;">Verify Your Identity</h1>
                            <p style="margin: 0 0 32px 0; font-size: 15px; color: #94a3b8; line-height: 1.5;">Hi {full_name}, enter this code to complete your {card.name} application.</p>
                            
                            <!-- Code Box -->
                            <div style="background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); border-radius: 12px; padding: 28px; text-align: center; margin-bottom: 32px;">
                                <span style="font-size: 36px; font-weight: 700; font-family: 'SF Mono', Monaco, 'Courier New', monospace; letter-spacing: 8px; color: #ffffff;">{code}</span>
                            </div>
                            
                            <p style="margin: 0 0 32px 0; font-size: 13px; color: #64748b; text-align: center;">Code expires in 24 hours</p>
                            
                            <!-- Card Info -->
                            <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 20px;">
                                <p style="margin: 0 0 16px 0; font-size: 12px; font-weight: 600; color: #60a5fa; text-transform: uppercase; letter-spacing: 1px;">Card Details</p>
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="padding: 8px 0; font-size: 14px; color: #94a3b8;">Annual Fee</td>
                                        <td style="padding: 8px 0; font-size: 14px; color: #ffffff; text-align: right; font-weight: 500;">${card.annual_fee}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; font-size: 14px; color: #94a3b8;">Rewards</td>
                                        <td style="padding: 8px 0; font-size: 14px; color: #ffffff; text-align: right; font-weight: 500;">{card.rewards_rate}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; font-size: 14px; color: #94a3b8;">Foreign Transaction Fee</td>
                                        <td style="padding: 8px 0; font-size: 14px; color: #ffffff; text-align: right; font-weight: 500;">{card.foreign_transaction_fee}%</td>
                                    </tr>
                                </table>
                            </div>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding-top: 32px; text-align: center;">
                            <p style="margin: 0 0 8px 0; font-size: 12px; color: #475569;">Didn't request this? Contact us at 1-800-555-0100</p>
                            <p style="margin: 0; font-size: 12px; color: #334155;">© 2025 Contoso Bank. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
    """

    # Send the email
    email_sent = False
    email_error = None
    if send_email_async and is_email_configured():
        try:
            result = await send_email_async(email, subject, plain_text_body, html_body)
            email_sent = result.get("success", False)
            if not email_sent:
                email_error = result.get("error")
            logger.info("📧 Card agreement email sent: %s - %s", client_id, "success" if email_sent else email_error)
        except Exception as exc:
            email_error = str(exc)
            logger.warning("📧 Email send failed: %s", exc)
    else:
        logger.info("📧 Email service not configured, code stored for verification: %s", code)

    return {
        "success": True,
        "email_sent": email_sent,
        "email_error": email_error,
        "verification_code": code,
        "email": email,
        "card_name": card.name,
        "expires_in_hours": 24,
        "redis_stored": redis_stored,
        "message": f"Verification code sent to {email}. Please ask the customer to check their email and provide the 6-digit code.",
    }


async def verify_esignature(args: dict[str, Any]) -> dict[str, Any]:
    """Verify e-signature code from session-scoped Redis storage."""
    client_id = (args.get("client_id") or "").strip()
    code = (args.get("verification_code") or "").strip()
    session_id = args.get("session_id", "default")

    if not client_id or not code:
        return {"success": False, "message": "client_id and code required."}

    # Retrieve from session-scoped Redis
    pending = await _get_esign_code(session_id, client_id)
    if not pending:
        return {"success": False, "message": "No pending agreement found. Please request a new code."}

    expected_code = pending.get("code")
    if code == expected_code:
        # Clean up e-sign code from Redis
        await _delete_esign_code(session_id, client_id)
        
        # Mark application as verified in Redis
        verified_at = datetime.now(UTC).isoformat()
        await _update_card_application(
            session_id, client_id,
            verified=True,
            verified_at=verified_at,
        )
        
        # Get stored application for consistent data
        app_context = await _get_card_application(session_id, client_id)
        
        logger.info("✓ E-signature verified for session=%s client=%s", session_id, client_id)
        return {
            "success": True,
            "verified": True,
            "verified_at": verified_at,
            "card_product_id": app_context.get("card_product_id") if app_context else pending.get("card_product_id"),
            "credit_limit": app_context.get("credit_limit") if app_context else None,
            "card_last4": app_context.get("card_last4") if app_context else None,
            "next_step": "finalize_card_application",
        }

    logger.warning("✗ E-signature verification failed for session=%s client=%s", session_id, client_id)
    return {"success": False, "verified": False, "message": "Invalid code. Please try again."}


async def finalize_card_application(args: dict[str, Any]) -> dict[str, Any]:
    """Finalize card application using stored context from session-scoped Redis."""
    client_id = (args.get("client_id") or "").strip()
    product_id = (args.get("card_product_id") or "").strip()
    session_id = args.get("session_id", "default")

    if not client_id:
        return {"success": False, "message": "client_id required."}

    # Get stored application context for consistent values
    app_context = await _get_card_application(session_id, client_id)
    
    # Use stored values if available, otherwise use args or generate new
    if app_context:
        product_id = app_context.get("card_product_id", product_id)
        credit_limit = app_context.get("credit_limit", 10000)
        card_last4 = app_context.get("card_last4", "".join(random.choices("0123456789", k=4)))
        card_display_name = app_context.get("card_name", "Credit Card")
        customer_tier = app_context.get("customer_tier", "Standard")
        verified = app_context.get("verified", False)
        
        if not verified:
            logger.warning("⚠️ Finalizing unverified application: session=%s client=%s", session_id, client_id)
    else:
        # Fallback if no stored context (shouldn't happen in normal flow)
        logger.warning("⚠️ No stored application context: session=%s client=%s", session_id, client_id)
        card = get_card_product(product_id)
        card_display_name = card.name if card else "Credit Card"
        credit_limit = random.choice([5000, 7500, 10000, 15000, 20000])
        card_last4 = "".join(random.choices("0123456789", k=4))
        customer_tier = "Standard"

    logger.info("✅ Card application approved: %s - %s", client_id, card_display_name)

    # Get customer profile for email
    profile = await _lookup_user_by_client_id(client_id)
    email = profile.get("contact_info", {}).get("email", "customer@email.com") if profile else "customer@email.com"
    full_name = profile.get("full_name", "Valued Customer") if profile else "Valued Customer"

    # Build confirmation email
    subject = f"Congratulations! Your {card_display_name} is Approved"
    plain_text_body = f"""Dear {full_name},

Great news! Your {card_display_name} has been approved.

Your Card Details:
• Card ending in: ****{card_last4}
• Credit Limit: ${credit_limit:,}
• Delivery: 3-5 business days

Your digital card is ready now - add it to Apple Pay or Google Pay in the Contoso Bank app.

Questions? Call us at 1-800-555-0100.

Contoso Bank
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #0f172a;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="100%" style="max-width: 520px;" cellpadding="0" cellspacing="0">
                    <!-- Logo -->
                    <tr>
                        <td style="padding-bottom: 32px; text-align: center;">
                            <span style="font-size: 28px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">Contoso</span>
                            <span style="font-size: 28px; font-weight: 300; color: #60a5fa;">Bank</span>
                        </td>
                    </tr>
                    <!-- Main Card -->
                    <tr>
                        <td style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 40px;">
                            <!-- Success Icon -->
                            <div style="text-align: center; margin-bottom: 24px;">
                                <div style="display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); width: 64px; height: 64px; border-radius: 50%; line-height: 64px; font-size: 32px;">✓</div>
                            </div>
                            
                            <h1 style="margin: 0 0 8px 0; font-size: 26px; font-weight: 600; color: #ffffff; text-align: center;">You're Approved!</h1>
                            <p style="margin: 0 0 32px 0; font-size: 15px; color: #94a3b8; line-height: 1.5; text-align: center;">Congratulations {full_name}, your {card_display_name} is ready.</p>
                            
                            <!-- Virtual Card Preview -->
                            <div style="background: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%); border-radius: 16px; padding: 28px; margin-bottom: 32px; position: relative; overflow: hidden;">
                                <div style="position: absolute; top: -30px; right: -30px; width: 120px; height: 120px; background: rgba(255,255,255,0.1); border-radius: 50%;"></div>
                                <p style="margin: 0 0 24px 0; font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.7); text-transform: uppercase; letter-spacing: 2px;">Contoso Bank</p>
                                <p style="margin: 0 0 8px 0; font-size: 22px; font-weight: 500; color: #ffffff; font-family: 'SF Mono', Monaco, monospace; letter-spacing: 3px;">•••• •••• •••• {card_last4}</p>
                                <p style="margin: 0; font-size: 13px; color: rgba(255,255,255,0.8);">{card_display_name}</p>
                            </div>
                            
                            <!-- Card Info -->
                            <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; margin-bottom: 24px;">
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="padding: 10px 0; font-size: 14px; color: #94a3b8;">Credit Limit</td>
                                        <td style="padding: 10px 0; font-size: 18px; color: #10b981; text-align: right; font-weight: 600;">${credit_limit:,}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px 0; font-size: 14px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.05);">Physical Card</td>
                                        <td style="padding: 10px 0; font-size: 14px; color: #ffffff; text-align: right; font-weight: 500; border-top: 1px solid rgba(255,255,255,0.05);">Arrives in 3-5 days</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px 0; font-size: 14px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.05);">Digital Wallet</td>
                                        <td style="padding: 10px 0; font-size: 14px; color: #10b981; text-align: right; font-weight: 500; border-top: 1px solid rgba(255,255,255,0.05);">Ready Now ✓</td>
                                    </tr>
                                </table>
                            </div>
                            
                            <!-- CTA -->
                            <div style="text-align: center;">
                                <p style="margin: 0; font-size: 14px; color: #94a3b8;">Add to Apple Pay or Google Pay in the Contoso Bank app</p>
                            </div>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding-top: 32px; text-align: center;">
                            <p style="margin: 0 0 8px 0; font-size: 12px; color: #475569;">Questions? Call 1-800-555-0100</p>
                            <p style="margin: 0; font-size: 12px; color: #334155;">© 2025 Contoso Bank. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
    """

    # Send the confirmation email
    email_sent = False
    email_error = None
    if send_email_async and is_email_configured():
        try:
            result = await send_email_async(email, subject, plain_text_body, html_body)
            email_sent = result.get("success", False)
            if not email_sent:
                email_error = result.get("error")
            logger.info("📧 Card approval email sent: %s - %s", client_id, "success" if email_sent else email_error)
        except Exception as exc:
            email_error = str(exc)
            logger.warning("📧 Approval email send failed: %s", exc)
    else:
        logger.info("📧 Email service not configured for approval confirmation")

    # Mark application as finalized and clean up from Redis
    finalized_at = datetime.now(UTC).isoformat()
    await _update_card_application(
        session_id, client_id,
        finalized=True,
        finalized_at=finalized_at,
        email_sent=email_sent,
    )
    
    logger.info("✅ Card application finalized: session=%s client=%s card=%s limit=$%d",
               session_id, client_id, product_id, credit_limit)

    return {
        "success": True,
        "approved": True,
        "card_number_last4": card_last4,
        "card_product_id": product_id,
        "card_name": card_display_name,
        "credit_limit": credit_limit,
        "physical_delivery": "3-5 business days",
        "digital_wallet_ready": True,
        "confirmation_email_sent": email_sent,
        "email_error": email_error,
        "email": email,
        "finalized_at": finalized_at,
    }


async def search_credit_card_faqs(args: dict[str, Any]) -> dict[str, Any]:
    """
    Search credit card FAQ knowledge base.
    
    Uses local CARD_KNOWLEDGE_BASE for RAG fallback when Azure AI Search is unavailable.
    Returns matching FAQ entries for card-specific questions about APR, fees, benefits, etc.
    
    Args:
        args: Dict with 'query', optional 'card_name' and 'top_k'
        
    Returns:
        Dict with 'success', 'results' list, and 'source' indicator
    """
    query = (args.get("query") or "").strip().lower()
    card_name_filter = (args.get("card_name") or "").strip().lower()
    top_k = args.get("top_k", 3)
    
    if not query:
        return {"success": False, "message": "Query is required.", "results": []}
    
    # Map card names to product IDs
    card_name_to_id = {
        "travel rewards": "travel-rewards-001",
        "premium rewards": "premium-rewards-001",
        "cash rewards": "cash-rewards-002",
        "unlimited cash": "unlimited-cash-003",
    }
    
    # Map query keywords to knowledge base keys
    query_key_mapping = {
        "apr": "apr",
        "interest": "apr",
        "rate": "apr",
        "foreign": "foreign_fees",
        "international": "foreign_fees",
        "transaction fee": "foreign_fees",
        "atm": "atm_cash_advance",
        "cash advance": "atm_cash_advance",
        "withdraw": "atm_cash_advance",
        "eligible": "eligibility",
        "qualify": "eligibility",
        "credit score": "eligibility",
        "fico": "eligibility",
        "benefit": "benefits",
        "perk": "benefits",
        "annual fee": "benefits",
        "insurance": "benefits",
        "reward": "rewards",
        "point": "rewards",
        "cash back": "rewards",
        "earn": "rewards",
        "balance transfer": "balance_transfer",
        "transfer": "balance_transfer",
        "travel": "best_for_travel",
        "abroad": "best_for_travel",
    }
    
    results = []
    
    # Determine which cards to search
    if card_name_filter and card_name_filter in card_name_to_id:
        cards_to_search = {card_name_to_id[card_name_filter]: CARD_KNOWLEDGE_BASE.get(card_name_to_id[card_name_filter], {})}
    else:
        cards_to_search = CARD_KNOWLEDGE_BASE
    
    # Find matching knowledge base key
    matched_key = None
    for keyword, kb_key in query_key_mapping.items():
        if keyword in query:
            matched_key = kb_key
            break
    
    # Search through cards
    for card_id, card_kb in cards_to_search.items():
        if not card_kb:
            continue
            
        # Format card name from ID
        card_display_name = card_id.replace("-", " ").replace("001", "").replace("002", "").replace("003", "").strip().title()
        
        if matched_key and matched_key in card_kb:
            results.append({
                "card_name": card_display_name,
                "card_id": card_id,
                "topic": matched_key,
                "answer": card_kb[matched_key],
            })
        else:
            # Fallback: search all entries for query terms
            for topic, answer in card_kb.items():
                if query in answer.lower() or query in topic.lower():
                    results.append({
                        "card_name": card_display_name,
                        "card_id": card_id,
                        "topic": topic,
                        "answer": answer,
                    })
    
    # Limit results
    results = results[:top_k]
    
    logger.info("🔍 FAQ search: query='%s', card_filter='%s', results=%d", query, card_name_filter, len(results))
    
    return {
        "success": True,
        "query": query,
        "card_filter": card_name_filter or None,
        "results": results,
        "source": "CARD_KNOWLEDGE_BASE",
        "note": "Results from local FAQ knowledge base. For real-time data, Azure AI Search integration recommended.",
    }


async def evaluate_card_eligibility(args: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate if a customer is pre-approved or eligible for a specific credit card.
    
    Stores eligibility results in session-scoped Redis so subsequent tools
    (send_card_agreement, verify_esignature, finalize_card_application) use
    consistent values (credit_limit, card_product_id, etc.).
    
    Args:
        args: Dict with 'client_id', 'card_product_id', and 'session_id'
        
    Returns:
        Dict with eligibility_status, credit_limit, and next_steps
    """
    client_id = (args.get("client_id") or "").strip()
    card_product_id = (args.get("card_product_id") or "").strip()
    session_id = args.get("session_id", "default")
    
    if not client_id or not card_product_id:
        return {"success": False, "message": "client_id and card_product_id are required."}
    
    logger.info("🔍 Evaluating card eligibility | session=%s client_id=%s card=%s",
               session_id, client_id, card_product_id)
    
    # Get card product details
    card_product = CARD_PRODUCTS.get(card_product_id)
    if not card_product:
        return {"success": False, "message": f"Unknown card product: {card_product_id}"}
    
    # Fetch customer data from Cosmos DB
    mgr = _get_demo_users_manager()
    customer_data = None
    if mgr:
        try:
            customer_data = await asyncio.to_thread(mgr.read_document, {"client_id": client_id})
        except Exception as exc:
            logger.warning("Could not fetch customer data: %s", exc)
    
    # Require customer data from Cosmos DB - no mock fallback
    if not customer_data:
        return {"success": False, "message": f"Customer profile not found for {client_id}. Please create a profile first."}
    
    # Extract customer profile
    customer_intelligence = customer_data.get("customer_intelligence", {})
    relationship_context = customer_intelligence.get("relationship_context", {})
    bank_profile = customer_intelligence.get("bank_profile", {})
    
    customer_tier = relationship_context.get("relationship_tier", customer_data.get("tier", "Standard"))
    existing_cards = bank_profile.get("cards", [])
    
    # Simple eligibility scoring
    tier_lower = customer_tier.lower()
    eligibility_score = 50  # Base score
    
    if "diamond" in tier_lower or "platinum" in tier_lower:
        eligibility_score += 30
    elif "gold" in tier_lower:
        eligibility_score += 15
    
    if len(existing_cards) > 0:
        eligibility_score += 15
    
    # Determine credit limit
    if eligibility_score >= 80:
        credit_limit = CREDIT_LIMITS_BY_INCOME.get("high", 15000)
    elif eligibility_score >= 60:
        credit_limit = CREDIT_LIMITS_BY_INCOME.get("medium", 8500)
    else:
        credit_limit = CREDIT_LIMITS_BY_INCOME.get("low", 5000)
    
    # Determine status
    if eligibility_score >= 75:
        eligibility_status = "PRE_APPROVED"
        status_message = "Great news! You're pre-approved for this card."
        next_step = "send_card_agreement"
        can_proceed = True
    elif eligibility_score >= 55:
        eligibility_status = "APPROVED_WITH_REVIEW"
        status_message = "You're approved! I'll send you the agreement to review and sign."
        next_step = "send_card_agreement"
        can_proceed = True
    else:
        eligibility_status = "PENDING_VERIFICATION"
        status_message = "We need a bit more information to complete your application."
        next_step = "request_more_info"
        can_proceed = False
    
    logger.info(
        "✅ Eligibility evaluated | client_id=%s card=%s score=%d status=%s limit=$%d",
        client_id, card_product_id, eligibility_score, eligibility_status, credit_limit
    )
    
    # Generate card last4 now so it's consistent throughout the flow
    card_last4 = "".join(random.choices("0123456789", k=4))
    
    # Store application context in session-scoped Redis for consistency
    await _store_card_application(
        session_id=session_id,
        client_id=client_id,
        card_product_id=card_product_id,
        credit_limit=credit_limit,
        eligibility_status=eligibility_status,
        customer_tier=customer_tier,
        card_name=card_product.name,
        eligibility_score=eligibility_score,
        card_last4=card_last4,
    )
    
    return {
        "success": True,
        "message": status_message,
        "eligibility_status": eligibility_status,
        "eligibility_score": eligibility_score,
        "credit_limit": credit_limit,
        "card_name": card_product.name,
        "card_product_id": card_product_id,
        "can_proceed_to_agreement": can_proceed,
        "next_step": next_step,
        "customer_tier": customer_tier,
        "card_last4": card_last4,
        "session_stored": True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "get_user_profile", get_user_profile_schema, get_user_profile, tags={"banking", "profile"}
)
register_tool(
    "get_account_summary",
    get_account_summary_schema,
    get_account_summary,
    tags={"banking", "account"},
)
register_tool(
    "get_recent_transactions",
    get_recent_transactions_schema,
    get_recent_transactions,
    tags={"banking", "transactions"},
)
register_tool(
    "search_card_products",
    search_card_products_schema,
    search_card_products,
    tags={"banking", "cards"},
)
register_tool(
    "get_card_details", get_card_details_schema, get_card_details, tags={"banking", "cards"}
)
register_tool("refund_fee", refund_fee_schema, refund_fee, tags={"banking", "fees"})
register_tool(
    "send_card_agreement",
    send_card_agreement_schema,
    send_card_agreement,
    tags={"banking", "cards", "esign"},
)
register_tool(
    "verify_esignature",
    verify_esignature_schema,
    verify_esignature,
    tags={"banking", "cards", "esign"},
)
register_tool(
    "finalize_card_application",
    finalize_card_application_schema,
    finalize_card_application,
    tags={"banking", "cards", "esign"},
)
register_tool(
    "search_credit_card_faqs",
    search_credit_card_faqs_schema,
    search_credit_card_faqs,
    tags={"banking", "cards", "faq"},
)
register_tool(
    "evaluate_card_eligibility",
    evaluate_card_eligibility_schema,
    evaluate_card_eligibility,
    tags={"banking", "cards", "eligibility"},
)
