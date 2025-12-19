"""
Authentication & MFA Tools
==========================

Tools for identity verification, MFA, and authentication.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import string
from typing import TYPE_CHECKING, Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

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

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.cosmosdb.manager import CosmosDBMongoCoreManager

logger = get_logger("agents.tools.auth")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

verify_client_identity_schema: dict[str, Any] = {
    "name": "verify_client_identity",
    "description": (
        "Verify caller's identity using name and last 4 digits of SSN. "
        "Returns client_id if verified, otherwise returns authentication failure."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "full_name": {"type": "string", "description": "Caller's full legal name"},
            "ssn_last_4": {"type": "string", "description": "Last 4 digits of SSN"},
        },
        "required": ["full_name", "ssn_last_4"],
    },
}

send_mfa_code_schema: dict[str, Any] = {
    "name": "send_mfa_code",
    "description": (
        "Send MFA verification code to customer's registered phone. "
        "Returns confirmation that code was sent."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "method": {
                "type": "string",
                "enum": ["sms", "voice", "email"],
                "description": "Delivery method for code",
            },
        },
        "required": ["client_id"],
    },
}

verify_mfa_code_schema: dict[str, Any] = {
    "name": "verify_mfa_code",
    "description": (
        "Verify the MFA code provided by customer. "
        "Returns success if code matches, failure otherwise."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "code": {"type": "string", "description": "6-digit verification code"},
        },
        "required": ["client_id", "code"],
    },
}

resend_mfa_code_schema: dict[str, Any] = {
    "name": "resend_mfa_code",
    "description": "Resend MFA code to customer if they didn't receive it.",
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "method": {
                "type": "string",
                "enum": ["sms", "voice", "email"],
                "description": "Delivery method",
            },
        },
        "required": ["client_id"],
    },
}

verify_cc_caller_schema: dict[str, Any] = {
    "name": "verify_cc_caller",
    "description": (
        "Verify a Claimant Carrier (CC) representative's access to claim information. "
        "Use this for B2B subrogation calls to authenticate the caller represents "
        "the claimant carrier on record for the specified claim. "
        "Required: claim_number, company_name, caller_name. "
        "Returns retry_allowed=true on failure - retry up to 3 times before escalating."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number the CC rep is calling about (e.g., CLM-2024-001234)",
            },
            "company_name": {
                "type": "string",
                "description": "The insurance company the caller represents (e.g., Contoso Insurance)",
            },
            "caller_name": {
                "type": "string",
                "description": "The name of the caller (CC representative)",
            },
        },
        "required": ["claim_number", "company_name", "caller_name"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK DATA (for demo purposes)
# ═══════════════════════════════════════════════════════════════════════════════

_MOCK_USERS = {
    ("john smith", "1234"): {
        "client_id": "CLT-001-JS",
        "full_name": "John Smith",
        "phone_last_4": "5678",
        "email": "john.smith@email.com",
    },
    ("jane doe", "5678"): {
        "client_id": "CLT-002-JD",
        "full_name": "Jane Doe",
        "phone_last_4": "9012",
        "email": "jane.doe@email.com",
    },
    ("michael chen", "9999"): {
        "client_id": "CLT-003-MC",
        "full_name": "Michael Chen",
        "phone_last_4": "3456",
        "email": "m.chen@email.com",
    },
    # Common test users (seed data profiles)
    ("alice brown", "1234"): {
        "client_id": "alice_brown_ab",
        "full_name": "Alice Brown",
        "phone_last_4": "9907",
        "email": "alice.brown@example.com",
    },
    ("bob williams", "5432"): {
        "client_id": "bob_williams_bw",
        "full_name": "Bob Williams",
        "phone_last_4": "4441",
        "email": "bob.williams@example.com",
    },
}

_PENDING_MFA: dict[str, str] = {}  # client_id -> code
_COSMOS_MANAGER: CosmosDBMongoCoreManager | None = None
_COSMOS_USERS_MANAGER: CosmosDBMongoCoreManager | None = None

# User profiles are stored in the shared Cosmos DB config (see src.cosmosdb.config)
# Functions get_database_name() and get_users_collection_name() imported above


def _manager_targets_collection(
    manager: CosmosDBMongoCoreManager,
    database_name: str,
    collection_name: str,
) -> bool:
    """Return True when the manager already points to the requested db/collection."""
    try:
        db_name = getattr(getattr(manager, "database", None), "name", None)
        coll_name = getattr(getattr(manager, "collection", None), "name", None)
    except Exception:  # pragma: no cover - inspecting defensive attributes
        logger.debug("Failed to introspect Cosmos manager target", exc_info=True)
        return False
    return db_name == database_name and coll_name == collection_name


def _describe_manager_target(manager: CosmosDBMongoCoreManager) -> dict[str, str | None]:
    """Provide db/collection names for logging."""
    db_name = getattr(getattr(manager, "database", None), "name", None)
    coll_name = getattr(getattr(manager, "collection", None), "name", None)
    return {
        "database": db_name or "unknown",
        "collection": coll_name or "unknown",
    }


def _get_cosmos_manager() -> CosmosDBMongoCoreManager | None:
    """Resolve the shared Cosmos DB client from FastAPI app state."""
    global _COSMOS_MANAGER
    if _COSMOS_MANAGER is not None:
        return _COSMOS_MANAGER

    try:
        from apps.artagent.backend import main as backend_main  # local import to avoid cycles
    except Exception:  # pragma: no cover - best-effort resolution
        return None

    app = getattr(backend_main, "app", None)
    state = getattr(app, "state", None) if app else None
    cosmos = getattr(state, "cosmos", None)
    if cosmos is not None:
        _COSMOS_MANAGER = cosmos
    return cosmos


def _get_demo_users_manager() -> CosmosDBMongoCoreManager | None:
    """Return a Cosmos DB manager pointed at the demo users collection."""
    global _COSMOS_USERS_MANAGER
    database_name = get_database_name()
    container_name = get_users_collection_name()

    if _COSMOS_USERS_MANAGER is not None:
        if _manager_targets_collection(_COSMOS_USERS_MANAGER, database_name, container_name):
            return _COSMOS_USERS_MANAGER
        logger.warning(
            "Cached Cosmos demo-users manager pointed to different collection; refreshing",
            extra=_describe_manager_target(_COSMOS_USERS_MANAGER),
        )
        _COSMOS_USERS_MANAGER = None

    base_manager = _get_cosmos_manager()
    if base_manager is not None:
        if _manager_targets_collection(base_manager, database_name, container_name):
            _COSMOS_USERS_MANAGER = base_manager
            return _COSMOS_USERS_MANAGER
        logger.info(
            "Base Cosmos manager uses different collection; creating scoped users manager",
            extra=_describe_manager_target(base_manager),
        )

    if _CosmosManagerImpl is None:
        logger.warning(
            "Cosmos manager implementation unavailable; cannot query demo users collection"
        )
        return None

    try:
        _COSMOS_USERS_MANAGER = _CosmosManagerImpl(
            database_name=database_name,
            collection_name=container_name,
        )
        logger.info(
            "Auth tools connected to Cosmos demo users collection",
            extra={
                "database": database_name,
                "collection": container_name,
            },
        )
        return _COSMOS_USERS_MANAGER
    except Exception as exc:  # pragma: no cover - connection issues
        logger.warning("Unable to initialize Cosmos demo users manager: %s", exc)
        return None


async def _lookup_user_in_cosmos(
    full_name: str, ssn_last_4: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Query Cosmos DB for the caller. Returns (record, failure_reason)."""
    cosmos = _get_demo_users_manager()
    if cosmos is None:
        logger.warning(
            "⚠️ Cosmos manager unavailable for identity lookup: %s / %s",
            full_name, ssn_last_4
        )
        return None, "unavailable"

    # First try: exact match on name + SSN
    name_pattern = f"^{re.escape(full_name)}$"
    query: dict[str, Any] = {
        "verification_codes.ssn4": ssn_last_4,
        "full_name": {"$regex": name_pattern, "$options": "i"},
    }

    logger.info(
        "🔍 Cosmos identity lookup | full_name=%s | ssn_last_4=%s",
        full_name, ssn_last_4
    )

    try:
        document = await asyncio.to_thread(cosmos.read_document, query)
        if document:
            logger.info(
                "✓ Identity verified via Cosmos (exact match): %s",
                document.get("client_id") or document.get("_id")
            )
            return document, None

        # Second try: SSN-only lookup (in case speech-to-text misheard the name)
        ssn_only_query: dict[str, Any] = {"verification_codes.ssn4": ssn_last_4}
        document = await asyncio.to_thread(cosmos.read_document, ssn_only_query)
        if document:
            actual_name = document.get("full_name", "unknown")
            logger.warning(
                "⚠️ SSN matched but name mismatch | input_name=%s | db_name=%s | client_id=%s",
                full_name, actual_name, document.get("client_id")
            )
            # Return the document - the LLM can confirm with user
            return document, None

    except Exception as exc:  # pragma: no cover - network/driver failures
        logger.warning("Cosmos identity lookup failed: %s", exc)
        return None, "error"

    logger.warning(
        "✗ No user found in Cosmos | full_name=%s | ssn_last_4=%s",
        full_name, ssn_last_4
    )
    return None, "not_found"


def _format_identity_success(user: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Normalize successful identity responses."""
    client_id = user.get("client_id") or user.get("_id") or "unknown"
    caller_name = user.get("full_name") or user.get("caller_name") or user.get("name") or "caller"
    suffix = " (mock data)" if source == "mock" else ""
    return {
        "success": True,
        "authenticated": True,
        "client_id": client_id,
        "caller_name": caller_name,
        "message": f"Identity verified for {caller_name}{suffix}",
        "data_source": source,
    }


def _log_mock_usage(full_name: str, ssn_last_4: str, reason: str | None) -> None:
    reason_text = f"reason={reason}" if reason else "no cosmos access"
    logger.warning(
        "⚠️ verify_client_identity using mock dataset (%s) for %s / %s",
        reason_text,
        full_name,
        ssn_last_4,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def _lookup_claim_in_cosmos(
    claim_number: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """
    Query Cosmos DB for a user profile containing the given claim number.
    
    Returns:
        (user_profile, claim, failure_reason)
        - user_profile: Full user document if found
        - claim: The matching claim dict from demo_metadata.claims
        - failure_reason: None if found, or 'unavailable'/'not_found'/'error'
    """
    cosmos = _get_demo_users_manager()
    if cosmos is None:
        logger.warning(
            "⚠️ Cosmos manager unavailable for claim lookup: %s",
            claim_number
        )
        return None, None, "unavailable"

    # Query for user with matching claim in demo_metadata.claims
    query: dict[str, Any] = {
        "demo_metadata.claims.claim_number": {"$regex": f"^{re.escape(claim_number)}$", "$options": "i"}
    }

    logger.info("🔍 Cosmos claim lookup | claim_number=%s", claim_number)

    try:
        document = await asyncio.to_thread(cosmos.read_document, query)
        if document:
            # Extract the matching claim from the document
            claims = document.get("demo_metadata", {}).get("claims", [])
            claim_upper = claim_number.upper()
            for claim in claims:
                if claim.get("claim_number", "").upper() == claim_upper:
                    logger.info(
                        "✓ Claim found in Cosmos: %s (user: %s)",
                        claim_number,
                        document.get("client_id") or document.get("_id")
                    )
                    return document, claim, None
            # Document matched but claim not in expected location
            logger.warning(
                "⚠️ Document matched query but claim not found in demo_metadata.claims: %s",
                claim_number
            )
            return document, None, "not_found"
    except Exception as exc:  # pragma: no cover - network/driver failures
        logger.warning("Cosmos claim lookup failed: %s", exc)
        return None, None, "error"

    logger.warning("✗ No user found with claim: %s", claim_number)
    return None, None, "not_found"


async def verify_cc_caller(args: dict[str, Any]) -> dict[str, Any]:
    """
    Verify Claimant Carrier representative access to claim.

    Checks:
    1. Claim exists in our system (queries Cosmos DB directly)
    2. Caller's company matches the claimant carrier on record

    Returns:
        success: bool - whether verification passed
        claim_exists: bool - whether the claim was found
        cc_verified: bool - whether the company matches
        claim_number: str - the verified claim number
        cc_company: str - the verified company name
        caller_name: str - the caller's name
        retry_allowed: bool - whether the agent should retry (max 3 attempts)
        message: str - human-readable status
    """
    claim_number = (args.get("claim_number") or "").strip().upper()
    company_name = (args.get("company_name") or "").strip()
    caller_name = (args.get("caller_name") or "").strip()

    logger.info(
        "🔐 CC Verification | claim=%s company=%s caller=%s",
        claim_number, company_name, caller_name
    )

    # Validate required fields
    if not claim_number:
        return {
            "success": False,
            "claim_exists": False,
            "cc_verified": False,
            "retry_allowed": True,
            "message": "Claim number is required. Please ask for the claim number.",
        }

    if not company_name:
        return {
            "success": False,
            "claim_exists": False,
            "cc_verified": False,
            "retry_allowed": True,
            "message": "Company name is required. Please ask which company the caller represents.",
        }

    if not caller_name:
        return {
            "success": False,
            "claim_exists": False,
            "cc_verified": False,
            "retry_allowed": True,
            "message": "Caller name is required. Please ask for the caller's name.",
        }

    # Look up claim from Cosmos DB
    user_profile, claim, failure_reason = await _lookup_claim_in_cosmos(claim_number)
    
    if not claim:
        logger.warning("❌ Claim not found: %s (reason: %s)", claim_number, failure_reason)
        return {
            "success": False,
            "claim_exists": False,
            "cc_verified": False,
            "claim_number": claim_number,
            "retry_allowed": True,
            "message": f"Claim {claim_number} not found in our system. Please verify the claim number.",
        }

    # Check if company matches the claimant carrier on record
    cc_on_record = (claim.get("claimant_carrier") or "").lower()
    company_normalized = company_name.lower()
    
    # Normalize common variations
    cc_on_record_clean = cc_on_record.replace(" insurance", "").strip()
    company_clean = company_normalized.replace(" insurance", "").strip()

    # Allow partial matching for better UX (e.g., "Contoso" matches "Contoso Insurance")
    cc_matches = (
        cc_on_record == company_normalized or
        cc_on_record_clean == company_clean or
        cc_on_record.startswith(company_clean) or
        company_normalized.startswith(cc_on_record_clean)
    )

    if not cc_matches:
        logger.warning(
            "❌ CC mismatch | claim=%s expected=%s got=%s",
            claim_number, cc_on_record, company_normalized
        )
        return {
            "success": False,
            "claim_exists": True,
            "cc_verified": False,
            "claim_number": claim_number,
            "cc_company": company_name,
            "caller_name": caller_name,
            "retry_allowed": True,
            "message": (
                f"Unable to verify. The claimant carrier on record for claim "
                f"{claim_number} does not match {company_name}."
            ),
        }

    # Verification successful
    logger.info(
        "✅ CC Verified | claim=%s company=%s caller=%s",
        claim_number, company_name, caller_name
    )
    return {
        "success": True,
        "claim_exists": True,
        "cc_verified": True,
        "claim_number": claim_number,
        "cc_company": company_name,
        "caller_name": caller_name,
        "claimant_name": claim.get("claimant_name"),
        "loss_date": claim.get("loss_date"),
        "message": f"Verified. {caller_name} from {company_name} accessing claim {claim_number}.",
    }


async def verify_client_identity(args: dict[str, Any]) -> dict[str, Any]:
    """Verify caller identity using Cosmos DB first, then fall back to mock data."""
    raw_full_name = (args.get("full_name") or "").strip()
    normalized_full_name = raw_full_name.lower()
    ssn_last_4 = (args.get("ssn_last_4") or "").strip()

    if not raw_full_name or not ssn_last_4:
        return {
            "success": False,
            "authenticated": False,
            "message": "Both full_name and ssn_last_4 are required.",
        }

    cosmos_user, cosmos_failure = await _lookup_user_in_cosmos(raw_full_name, ssn_last_4)
    if cosmos_user:
        return _format_identity_success(cosmos_user, source="cosmos")

    user = _MOCK_USERS.get((normalized_full_name, ssn_last_4))
    if user:
        _log_mock_usage(raw_full_name, ssn_last_4, cosmos_failure)
        return _format_identity_success(user, source="mock")

    logger.warning(
        "✗ Identity verification failed after Cosmos lookup (%s): %s / %s",
        cosmos_failure or "no_match",
        raw_full_name,
        ssn_last_4,
    )
    return {
        "success": False,
        "authenticated": False,
        "message": "Could not verify identity. Please check your information.",
        "data_source": "cosmos",
    }


async def send_mfa_code(args: dict[str, Any]) -> dict[str, Any]:
    """Send MFA code to customer."""
    client_id = (args.get("client_id") or "").strip()
    method = (args.get("method") or "sms").strip()

    if not client_id:
        return {"success": False, "message": "client_id is required."}

    # Generate 6-digit code
    code = "".join(random.choices(string.digits, k=6))
    _PENDING_MFA[client_id] = code

    logger.info("📱 MFA code sent to %s via %s: %s", client_id, method, code)

    return {
        "success": True,
        "code_sent": True,
        "method": method,
        "message": f"Verification code sent via {method}.",
        # For demo: include code in response
        "_demo_code": code,
    }


async def verify_mfa_code(args: dict[str, Any]) -> dict[str, Any]:
    """Verify MFA code provided by customer."""
    client_id = (args.get("client_id") or "").strip()
    code = (args.get("code") or "").strip()

    if not client_id or not code:
        return {"success": False, "message": "client_id and code are required."}

    expected = _PENDING_MFA.get(client_id)

    if expected and code == expected:
        del _PENDING_MFA[client_id]
        logger.info("✓ MFA verified for %s", client_id)
        return {
            "success": True,
            "verified": True,
            "message": "Verification successful. You're now authenticated.",
        }

    logger.warning("✗ MFA verification failed for %s", client_id)
    return {
        "success": False,
        "verified": False,
        "message": "Invalid code. Please try again.",
    }


async def resend_mfa_code(args: dict[str, Any]) -> dict[str, Any]:
    """Resend MFA code."""
    return await send_mfa_code(args)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "verify_client_identity", verify_client_identity_schema, verify_client_identity, tags={"auth"}
)
register_tool("send_mfa_code", send_mfa_code_schema, send_mfa_code, tags={"auth", "mfa"})
register_tool("verify_mfa_code", verify_mfa_code_schema, verify_mfa_code, tags={"auth", "mfa"})
register_tool("resend_mfa_code", resend_mfa_code_schema, resend_mfa_code, tags={"auth", "mfa"})
register_tool(
    "verify_cc_caller",
    verify_cc_caller_schema,
    verify_cc_caller,
    tags={"auth", "insurance", "b2b"},
)
