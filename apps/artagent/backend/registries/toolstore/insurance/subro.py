"""
Subrogation (Subro) Tools - B2B Claimant Carrier Hotline
=========================================================

Tools for handling inbound calls from Claimant Carriers (other insurance
companies) inquiring about subrogation demand status on claims.

B2B Context:
- Callers are representatives from OTHER insurance companies
- They represent claimants who were hit by OUR insureds
- They call to check demand status, liability, coverage, limits, etc.

Data Source:
- Tools query Cosmos DB directly to find claims by claim_number
- Falls back to _session_profile if available
- Falls back to MOCK_CLAIMS for testing if no other source is available
"""

from __future__ import annotations

import asyncio
import os
import random
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List

from apps.artagent.backend.registries.toolstore.registry import register_tool
from apps.artagent.backend.registries.toolstore.insurance.constants import (
    SUBRO_FAX_NUMBER,
    SUBRO_PHONE_NUMBER,
    KNOWN_CC_COMPANIES,
    RUSH_CRITERIA,
    MOCK_CLAIMS,
)
from utils.ml_logging import get_logger

# Email service import for call summary emails
try:
    from src.acs.email_service import send_email as send_email_async, is_email_configured
except ImportError:
    send_email_async = None
    def is_email_configured() -> bool:
        return False

try:  # pragma: no cover - optional dependency during tests
    from src.cosmosdb.manager import CosmosDBMongoCoreManager as _CosmosManagerImpl
    from src.cosmosdb.config import get_database_name, get_users_collection_name
except Exception:  # pragma: no cover - handled at runtime
    _CosmosManagerImpl = None
    def get_database_name() -> str:
        return os.getenv("AZURE_COSMOS_DATABASE_NAME", "audioagentdb")
    def get_users_collection_name() -> str:
        return os.getenv("AZURE_COSMOS_USERS_COLLECTION_NAME", "users")

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.cosmosdb.manager import CosmosDBMongoCoreManager

logger = get_logger("agents.tools.subro")

# Cached Cosmos manager for subro tools
_COSMOS_USERS_MANAGER: CosmosDBMongoCoreManager | None = None


def _json(data: Any) -> Dict[str, Any]:
    """Wrap response data for consistent JSON output."""
    return data if isinstance(data, dict) else {"result": data}


# ═══════════════════════════════════════════════════════════════════════════════
# COSMOS DB HELPERS: Query claims directly from database
# ═══════════════════════════════════════════════════════════════════════════════

def _get_cosmos_manager() -> CosmosDBMongoCoreManager | None:
    """Resolve the shared Cosmos DB client from FastAPI app state."""
    try:
        from apps.artagent.backend import main as backend_main
    except Exception:  # pragma: no cover
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
        return _COSMOS_USERS_MANAGER

    base_manager = _get_cosmos_manager()
    if base_manager is not None:
        # Check if base manager targets our collection
        try:
            db_name = getattr(getattr(base_manager, "database", None), "name", None)
            coll_name = getattr(getattr(base_manager, "collection", None), "name", None)
            if db_name == database_name and coll_name == container_name:
                _COSMOS_USERS_MANAGER = base_manager
                return _COSMOS_USERS_MANAGER
        except Exception:
            pass

    if _CosmosManagerImpl is None:
        logger.debug("Cosmos manager implementation unavailable for subro tools")
        return None

    try:
        _COSMOS_USERS_MANAGER = _CosmosManagerImpl(
            database_name=database_name,
            collection_name=container_name,
        )
        logger.info(
            "Subro tools connected to Cosmos demo users collection",
            extra={"database": database_name, "collection": container_name},
        )
        return _COSMOS_USERS_MANAGER
    except Exception as exc:  # pragma: no cover
        logger.warning("Unable to initialize Cosmos manager for subro tools: %s", exc)
        return None


def _lookup_claim_in_cosmos_sync(claim_number: str) -> Dict[str, Any] | None:
    """
    Synchronously query Cosmos DB for a claim by claim number.
    
    Returns the claim dict if found, None otherwise.
    """
    cosmos = _get_demo_users_manager()
    if cosmos is None:
        return None

    # Query for user with matching claim in demo_metadata.claims
    query: Dict[str, Any] = {
        "demo_metadata.claims.claim_number": {"$regex": f"^{re.escape(claim_number)}$", "$options": "i"}
    }

    logger.info("🔍 Cosmos claim lookup (subro) | claim_number=%s", claim_number)

    try:
        document = cosmos.read_document(query)
        if document:
            # Extract the matching claim from the document
            claims = document.get("demo_metadata", {}).get("claims", [])
            claim_upper = claim_number.upper()
            for claim in claims:
                if claim.get("claim_number", "").upper() == claim_upper:
                    logger.info("✓ Claim found in Cosmos (subro): %s", claim_number)
                    return claim
    except Exception as exc:  # pragma: no cover
        logger.warning("Cosmos claim lookup failed (subro): %s", exc)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Get claims from session profile or fallback to MOCK_CLAIMS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_claims_from_profile(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract claims list from session profile.
    
    Looks in:
    1. _session_profile.demo_metadata.claims
    2. _session_profile.claims
    
    Returns empty list if no claims found.
    Ensures claims are converted to dicts (handles Pydantic objects).
    """
    session_profile = args.get("_session_profile")
    if not session_profile:
        return []
    
    # Try demo_metadata.claims first
    demo_meta = session_profile.get("demo_metadata", {})
    claims = demo_meta.get("claims", [])
    if not claims:
        # Try top-level claims
        claims = session_profile.get("claims", [])
    
    if not claims:
        return []
    
    # Convert Pydantic models to dicts if needed
    result = []
    for claim in claims:
        if hasattr(claim, "model_dump"):
            # Pydantic v2
            result.append(claim.model_dump())
        elif hasattr(claim, "dict"):
            # Pydantic v1
            result.append(claim.dict())
        elif isinstance(claim, dict):
            result.append(claim)
        else:
            # Try to convert to dict
            result.append(dict(claim) if hasattr(claim, "__iter__") else {})
    
    return result


def _find_claim_by_number(args: Dict[str, Any], claim_number: str) -> Dict[str, Any] | None:
    """
    Find a claim by claim number.
    
    Lookup order (session profile first for consistency with UI):
    1. Session profile (_session_profile.demo_metadata.claims) - matches UI data
    2. Cosmos DB (direct query) - for profiles without session context
    3. MOCK_CLAIMS fallback for testing
    
    Args:
        args: Tool arguments (may contain _session_profile)
        claim_number: The claim number to look up (case-insensitive)
    
    Returns:
        Claim dict if found, None otherwise
    """
    claim_number_upper = claim_number.upper()
    
    # First, try session profile (matches what UI displays)
    claims = _get_claims_from_profile(args)
    if claims:
        for claim in claims:
            if claim.get("claim_number", "").upper() == claim_number_upper:
                logger.info("📋 Found claim %s in session profile", claim_number_upper)
                return claim
    
    # Second, try Cosmos DB direct lookup
    cosmos_claim = _lookup_claim_in_cosmos_sync(claim_number_upper)
    if cosmos_claim:
        return cosmos_claim
    
    # Fallback to MOCK_CLAIMS for testing
    claim = MOCK_CLAIMS.get(claim_number_upper)
    if claim:
        logger.info("📋 Found claim %s in MOCK_CLAIMS (fallback)", claim_number_upper)
        return claim
    
    logger.warning("❌ Claim %s not found in any source", claim_number_upper)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_claim_summary
# ═══════════════════════════════════════════════════════════════════════════════

get_claim_summary_schema: Dict[str, Any] = {
    "name": "get_claim_summary",
    "description": (
        "Retrieve claim summary information for a verified Claimant Carrier. "
        "Returns basic claim details including parties, dates, and current status. "
        "Use after verify_cc_caller succeeds."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number to look up",
            },
        },
        "required": ["claim_number"],
    },
}


async def get_claim_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get basic claim summary for CC rep."""
    claim_number = (args.get("claim_number") or "").strip().upper()

    claim = _find_claim_by_number(args, claim_number)
    if not claim:
        return _json({"success": False, "message": f"Claim {claim_number} not found."})

    return _json({
        "success": True,
        "claim_number": claim_number,
        "insured_name": claim.get("insured_name", "Unknown"),
        "claimant_name": claim.get("claimant_name", "Unknown"),
        "claimant_carrier": claim.get("claimant_carrier", "Unknown"),
        "loss_date": claim.get("loss_date", "Unknown"),
        "status": claim.get("status", "unknown"),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_subro_demand_status
# ═══════════════════════════════════════════════════════════════════════════════

get_subro_demand_status_schema: Dict[str, Any] = {
    "name": "get_subro_demand_status",
    "description": (
        "Check subrogation demand status for a claim. Returns whether demand "
        "was received, when, amount, assignment status, and current handler."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number to check demand status for",
            },
        },
        "required": ["claim_number"],
    },
}


async def get_subro_demand_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get subrogation demand status with defensive null handling."""
    claim_number = (args.get("claim_number") or "").strip().upper()

    if not claim_number:
        return _json({"success": False, "message": "Claim number is required."})

    claim = _find_claim_by_number(args, claim_number)
    if not claim:
        return _json({"success": False, "message": f"Claim {claim_number} not found in our system."})

    # Defensive: subro_demand could be None, {}, dict, or Pydantic object
    demand = claim.get("subro_demand") or {}
    
    # Convert Pydantic model to dict if needed
    if hasattr(demand, "model_dump"):
        demand = demand.model_dump()
    elif hasattr(demand, "dict"):
        demand = demand.dict()
    elif not isinstance(demand, dict):
        demand = {}

    # Normalize boolean for received status
    demand_received = bool(demand.get("received"))

    return _json({
        "success": True,
        "claim_number": claim_number,
        "demand_received": demand_received,
        "received_date": demand.get("received_date") if demand_received else None,
        "demand_amount": demand.get("amount") if demand_received else None,
        "assigned_to": demand.get("assigned_to"),
        "assigned_date": demand.get("assigned_date"),
        "status": demand.get("status") or ("not_received" if not demand_received else "unknown"),
        "fax_number": SUBRO_FAX_NUMBER if not demand_received else None,
        "message": _format_demand_status_message(demand),
    })


def _format_demand_status_message(demand: Dict[str, Any] | None) -> str:
    """Format human-readable demand status message with business process language.
    
    Handles None, empty dict, and partial demand objects defensively.
    """
    # Defensive: handle None or non-dict
    if not demand or not isinstance(demand, dict):
        return (
            f"No demand received on this claim. You can fax demands to {SUBRO_FAX_NUMBER}. "
            "Once received, demands are assigned on a first-come, first-served basis."
        )
    
    if not demand.get("received"):
        return (
            f"No demand received on this claim. You can fax demands to {SUBRO_FAX_NUMBER}. "
            "Once received, demands are assigned on a first-come, first-served basis."
        )

    status = demand.get("status") or "unknown"
    assigned = demand.get("assigned_to")
    amount = demand.get("amount")
    received_date = demand.get("received_date")
    
    # Build base message with received info (handle None amount gracefully)
    try:
        amount_str = f" for ${float(amount):,.2f}" if amount is not None else ""
    except (ValueError, TypeError):
        amount_str = f" for ${amount}" if amount else ""
    date_str = f" on {received_date}" if received_date else ""
    base_msg = f"Demand received{date_str}{amount_str}."

    if status == "paid":
        return f"{base_msg} Demand has been paid."
    elif status == "denied_no_coverage":
        return f"{base_msg} Demand denied due to no coverage."
    elif status == "denied_liability":
        return f"{base_msg} Demand denied due to liability denial."
    elif status == "under_review" and assigned:
        return f"{base_msg} Currently under review by {assigned}."
    elif status == "pending" and not assigned:
        return (
            f"{base_msg} Pending assignment. "
            "Demands are processed first-come, first-served. Expect assignment within 5-7 business days."
        )
    elif assigned:
        return f"{base_msg} Assigned to {assigned}. Status: {status}."
    else:
        return f"{base_msg} Status: {status}."


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_coverage_status
# ═══════════════════════════════════════════════════════════════════════════════

get_coverage_status_schema: Dict[str, Any] = {
    "name": "get_coverage_status",
    "description": (
        "Check coverage status for a claim. Returns whether coverage is "
        "confirmed, pending, or denied, plus any coverage question (CVQ) status."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number to check coverage for",
            },
        },
        "required": ["claim_number"],
    },
}


async def get_coverage_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get coverage status for claim with enhanced messaging for CVQ scenarios."""
    claim_number = (args.get("claim_number") or "").strip().upper()

    if not claim_number:
        return _json({"success": False, "message": "Claim number is required."})

    claim = _find_claim_by_number(args, claim_number)
    if not claim:
        return _json({"success": False, "message": f"Claim {claim_number} not found in our system."})

    coverage_status = claim.get("coverage_status") or "unknown"
    cvq_status = claim.get("cvq_status")

    # Build message based on coverage status
    if coverage_status == "confirmed":
        message = "Coverage is confirmed on this claim."
    elif coverage_status == "pending":
        message = "Coverage verification is still pending."
    elif coverage_status == "denied":
        reason = cvq_status or "coverage issue"
        message = f"Coverage has been denied on this claim."
    elif coverage_status == "cvq" or cvq_status:
        message = "There's an open coverage question on this claim. The file owner can discuss details."
    else:
        message = f"Coverage status: {coverage_status}."
    
    # Add CVQ detail if present and not already covered
    if cvq_status and coverage_status not in ("cvq", "denied"):
        message += f" Note: CVQ status is {cvq_status}."

    return _json({
        "success": True,
        "claim_number": claim_number,
        "coverage_status": coverage_status,
        "cvq_status": cvq_status,
        "has_cvq": bool(cvq_status) or coverage_status == "cvq",
        "message": message,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_liability_decision
# ═══════════════════════════════════════════════════════════════════════════════

get_liability_decision_schema: Dict[str, Any] = {
    "name": "get_liability_decision",
    "description": (
        "Get liability decision and range for a claim. Returns liability "
        "status (pending/accepted/denied) and if accepted, the liability "
        "percentage range (always disclose lower end only)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number to check liability for",
            },
        },
        "required": ["claim_number"],
    },
}


async def get_liability_decision(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get liability decision for claim with edge case handling.
    
    Edge cases handled:
    - liability_percentage = 0 (valid but falsy - means 0% liability)
    - liability_percentage = None with decision = accepted (partial data)
    - Unknown decision values
    """
    claim_number = (args.get("claim_number") or "").strip().upper()

    if not claim_number:
        return _json({"success": False, "message": "Claim number is required."})

    claim = _find_claim_by_number(args, claim_number)
    if not claim:
        return _json({"success": False, "message": f"Claim {claim_number} not found in our system."})

    decision = claim.get("liability_decision") or "unknown"
    # Support both liability_percentage (from demo_env) and liability_range_low (legacy)
    # Use 'is not None' to preserve 0 as a valid value
    percentage = claim.get("liability_percentage")
    if percentage is None:
        percentage = claim.get("liability_range_low")

    result: Dict[str, Any] = {
        "success": True,
        "claim_number": claim_number,
        "liability_decision": decision,
        "liability_percentage": percentage,
        "can_disclose_limits": False,  # Help SubroAgent know if limits can be disclosed
    }

    if decision == "pending":
        result["message"] = "Liability decision is still pending on this claim."
    elif decision == "accepted":
        if percentage is not None and percentage > 0:
            result["message"] = f"Liability has been accepted at {percentage}%."
            result["can_disclose_limits"] = True
        elif percentage == 0:
            # Edge case: accepted at 0% (unusual but possible)
            result["message"] = "Liability decision shows accepted but at 0%."
            result["can_disclose_limits"] = False
        else:
            # Accepted but no percentage - partial data
            result["message"] = "Liability has been accepted on this claim."
            result["can_disclose_limits"] = True
    elif decision == "denied":
        result["message"] = "Liability has been denied on this claim."
    elif decision == "not_applicable":
        result["message"] = "Liability is not applicable on this claim (typically due to coverage issues)."
    else:
        result["message"] = f"Liability status: {decision}."

    return _json(result)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_pd_policy_limits
# ═══════════════════════════════════════════════════════════════════════════════

get_pd_policy_limits_schema: Dict[str, Any] = {
    "name": "get_pd_policy_limits",
    "description": (
        "Get property damage policy limits for a claim and compare against demand. "
        "IMPORTANT: Only disclose limits if liability has been accepted (> 0%). "
        "The demand_amount will be AUTO-FETCHED from the claim's subro_demand record. "
        "Only pass demand_amount if you have a DIFFERENT amount from the caller."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number to check PD limits for",
            },
            "demand_amount": {
                "type": "number",
                "description": "OPTIONAL - Only provide if caller gives a different amount than what's on file. Tool will auto-fetch demand from claim record.",
            },
        },
        "required": ["claim_number"],
    },
}


async def get_pd_policy_limits(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get PD limits and compare against demand amount - only if liability accepted.
    
    Edge cases handled:
    - Demand amount not provided: AUTO-FETCH from subro_demand.amount
    - Demand equals limits exactly: not exceeding (borderline case)
    - Limits is 0 or None: handle gracefully
    - Liability accepted but percentage is None or 0
    """
    claim_number = (args.get("claim_number") or "").strip().upper()
    demand_amount = args.get("demand_amount")  # Optional - for limits comparison

    if not claim_number:
        return _json({"success": False, "message": "Claim number is required."})

    claim = _find_claim_by_number(args, claim_number)
    if not claim:
        return _json({"success": False, "message": f"Claim {claim_number} not found in our system."})

    decision = claim.get("liability_decision")
    # Use 'is not None' to preserve 0 as valid value
    percentage = claim.get("liability_percentage")
    if percentage is None:
        percentage = claim.get("liability_range_low")
    
    limits = claim.get("pd_limits") or 0
    
    # AUTO-FETCH demand from subro_demand if not explicitly provided
    if demand_amount is None:
        subro_demand = claim.get("subro_demand") or {}
        # Convert Pydantic model to dict if needed
        if hasattr(subro_demand, "model_dump"):
            subro_demand = subro_demand.model_dump()
        elif hasattr(subro_demand, "dict"):
            subro_demand = subro_demand.dict()
        elif not isinstance(subro_demand, dict):
            subro_demand = {}
        
        if subro_demand.get("received") and subro_demand.get("amount"):
            demand_amount = subro_demand.get("amount")

    # Determine if we can disclose limits:
    # Liability must be accepted AND percentage > 0
    can_disclose = (
        decision == "accepted" and 
        percentage is not None and 
        percentage > 0
    )

    if can_disclose:
        # Check if demand exceeds limits (>= means at limit, not exceeding)
        demand_exceeds_limits = False
        
        if demand_amount is not None:
            try:
                demand_float = float(demand_amount)
                if limits > 0:
                    demand_exceeds_limits = demand_float > limits
                    if demand_exceeds_limits:
                        limits_message = f"The property damage limit is ${limits:,}. Your demand of ${demand_float:,.2f} exceeds policy limits."
                    elif demand_float == limits:
                        limits_message = f"The property damage limit is ${limits:,}. Your demand matches the policy limit exactly."
                    else:
                        limits_message = f"No limits issue. Your demand (${demand_float:,.2f}) is within the ${limits:,} PD limit."
                else:
                    limits_message = f"Property damage limits show as ${limits:,}. Please verify with the handler."
            except (ValueError, TypeError):
                limits_message = f"Property damage limits: ${limits:,}. Unable to compare with demand amount."
        else:
            # No demand amount provided - SubroAgent should ask for it first
            limits_message = f"Property damage limits: ${limits:,}."
        
        return _json({
            "success": True,
            "claim_number": claim_number,
            "can_disclose": True,
            "pd_limits": limits,
            "demand_amount": demand_amount,
            "demand_exceeds_limits": demand_exceeds_limits,
            "ask_for_demand": demand_amount is None,  # Hint to SubroAgent
            "message": limits_message,
        })
    else:
        # Cannot disclose - build appropriate message
        if decision == "pending":
            msg = "Cannot disclose policy limits. Liability is still pending on this claim."
        elif decision == "denied":
            msg = "Cannot disclose policy limits. Liability has been denied on this claim."
        elif decision == "accepted" and (percentage is None or percentage == 0):
            msg = "Cannot disclose policy limits. Liability percentage is not established."
        else:
            msg = "Cannot disclose policy limits until liability has been accepted."
        
        return _json({
            "success": True,
            "claim_number": claim_number,
            "can_disclose": False,
            "pd_limits": None,
            "liability_status": decision,
            "liability_percentage": percentage,
            "message": msg,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_pd_payments
# ═══════════════════════════════════════════════════════════════════════════════

get_pd_payments_schema: Dict[str, Any] = {
    "name": "get_pd_payments",
    "description": (
        "Check payments made on the property damage (PD) feature of a claim. "
        "Returns payment history including dates, amounts, and payees."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number to check PD payments for",
            },
        },
        "required": ["claim_number"],
    },
}


async def get_pd_payments(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get PD payment history."""
    claim_number = (args.get("claim_number") or "").strip().upper()

    claim = _find_claim_by_number(args, claim_number)
    if not claim:
        return _json({"success": False, "message": f"Claim {claim_number} not found."})

    # Support both 'payments' (from demo_env) and 'pd_payments' (legacy)
    payments = claim.get("payments") or claim.get("pd_payments") or []
    total = sum(p.get("amount", 0) for p in payments)

    return _json({
        "success": True,
        "claim_number": claim_number,
        "payments": payments,
        "payment_count": len(payments),
        "total_paid": total,
        "message": f"{len(payments)} payment(s) totaling ${total:,.2f}." if payments else "No payments made.",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: resolve_feature_owner
# ═══════════════════════════════════════════════════════════════════════════════

resolve_feature_owner_schema: Dict[str, Any] = {
    "name": "resolve_feature_owner",
    "description": (
        "Find the owner/handler for a specific claim feature (PD, BI, SUBRO). "
        "Use when caller has questions outside subrogation scope that need "
        "to be routed to the correct handler."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number",
            },
            "feature": {
                "type": "string",
                "enum": ["PD", "BI", "SUBRO"],
                "description": "The feature type (PD=Property Damage, BI=Bodily Injury, SUBRO=Subrogation)",
            },
        },
        "required": ["claim_number", "feature"],
    },
}


async def resolve_feature_owner(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get the handler for a specific feature."""
    claim_number = (args.get("claim_number") or "").strip().upper()
    feature = (args.get("feature") or "").strip().upper()

    claim = _find_claim_by_number(args, claim_number)
    if not claim:
        return _json({"success": False, "message": f"Claim {claim_number} not found."})

    owners = claim.get("feature_owners", {})
    owner = owners.get(feature)

    if owner:
        return _json({
            "success": True,
            "claim_number": claim_number,
            "feature": feature,
            "owner": owner,
            "message": f"{feature} feature is handled by {owner}.",
        })
    else:
        return _json({
            "success": True,
            "claim_number": claim_number,
            "feature": feature,
            "owner": None,
            "message": f"No handler assigned to {feature} feature.",
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: evaluate_rush_criteria
# ═══════════════════════════════════════════════════════════════════════════════

evaluate_rush_criteria_schema: Dict[str, Any] = {
    "name": "evaluate_rush_criteria",
    "description": (
        "Evaluate if a subrogation demand qualifies for rush (ISRUSH) assignment. "
        "BUSINESS RULE: At least TWO criteria must be met to qualify. "
        "Criteria: 1) OOP expenses (rental/deductible), 2) Attorney involvement or suit filed, "
        "3) DOI complaint, 4) Statute of limitations near. "
        "NOTE: 'Third call' criterion is AUTO-CHECKED from system records - do NOT ask caller. "
        "You must ask the caller about the OTHER criteria before calling this tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number",
            },
            "oop_expenses": {
                "type": "boolean",
                "description": "Are there out-of-pocket expenses (rental car, deductible paid by claimant)?",
            },
            "attorney_represented": {
                "type": "boolean",
                "description": "Is there attorney involvement or has a suit been filed?",
            },
            "doi_complaint": {
                "type": "boolean",
                "description": "Has a Department of Insurance complaint been filed?",
            },
            "statute_near": {
                "type": "boolean",
                "description": "Is statute of limitations within 60 days?",
            },
            "escalation_request": {
                "type": "boolean",
                "description": "Is caller explicitly requesting escalation? (Does NOT count toward the 2-criteria minimum)",
            },
        },
        "required": ["claim_number", "attorney_represented", "statute_near"],
    },
}


async def evaluate_rush_criteria(args: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate if demand qualifies for rush assignment based on business criteria.
    
    BUSINESS RULE: At least TWO substantive criteria must be met to qualify for ISRUSH:
    - oop_expenses: Out-of-pocket expenses (rental, deductible) involved
    - prior_demands_unanswered: Third call for same demand (AUTO-CHECKED from system)
    - attorney_represented: Attorney involvement or suit filed
    - doi_complaint: DOI complaint filed
    - statute_near: Statute of limitations within 60 days
    
    Note: escalation_request alone does NOT count toward the minimum.
    
    CALL HISTORY: Automatically checked from claim records - SYSTEM DATA IS SOURCE OF TRUTH.
    Agent does NOT need to ask caller about call history. If system shows 2+ prior calls,
    the "third call" criterion is automatically met.
    """
    claim_number = (args.get("claim_number") or "").strip().upper()

    # AUTO-CHECK call history from claim records (SYSTEM IS SOURCE OF TRUTH)
    claim = _find_claim_by_number(args, claim_number)
    actual_prior_calls = 0
    if claim:
        call_history = claim.get("call_history", [])
        actual_prior_calls = len(call_history) if isinstance(call_history, list) else 0
        # Also check prior_call_count if set directly
        prior_count = claim.get("prior_call_count")
        if isinstance(prior_count, int) and prior_count > actual_prior_calls:
            actual_prior_calls = prior_count
    
    # System determines "third call" criterion - 2+ prior calls = this is 3rd+ call
    system_third_call_met = actual_prior_calls >= 2

    # Criteria that require caller input (agent must ask about these)
    caller_input_criteria = {
        "oop_expenses": "Out-of-pocket expenses (rental/deductible)",
        "attorney_represented": "Attorney involvement or suit filed",
        "doi_complaint": "DOI complaint filed",
        "statute_near": "Statute of limitations within 60 days",
    }
    
    # Count how many caller-input criteria were provided
    criteria_provided = sum(
        1 for key in caller_input_criteria.keys() 
        if key in args and args.get(key) is not None
    )
    
    # Need at least 2 caller-input criteria answers to proceed
    # (unless system already has third-call + 1 other)
    if criteria_provided < 2 and not system_third_call_met:
        return _json({
            "success": False,
            "claim_number": claim_number,
            "qualifies_for_rush": False,
            "criteria_met": [],
            "criteria_descriptions": [],
            "missing_criteria": True,
            "system_call_count": actual_prior_calls,
            "message": (
                "I need to gather more information. Please ask about: "
                "1) Attorney involvement or suit filed? "
                "2) Statute of limitations within 60 days? "
                "3) Out-of-pocket expenses (rental/deductible)? "
                "4) DOI complaint filed?"
            ),
        })

    criteria_met = []
    criteria_descriptions = []
    
    # Auto-add third-call criterion if system confirms it (NO CALLER INPUT NEEDED)
    if system_third_call_met:
        criteria_met.append("prior_demands_unanswered")
        criteria_descriptions.append(f"Multiple prior calls ({actual_prior_calls} on record)")
    
    # Check caller-input criteria
    for key, description in caller_input_criteria.items():
        if args.get(key):
            criteria_met.append(key)
            criteria_descriptions.append(description)
    
    # Also track escalation_request if present (informational only)
    if args.get("escalation_request"):
        criteria_met.append("escalation_request")
        criteria_descriptions.append("Explicit escalation request")

    # Count only substantive criteria (not escalation_request)
    substantive_met = [c for c in criteria_met if c != "escalation_request"]
    
    # BUSINESS RULE: At least TWO substantive criteria required
    qualifies = len(substantive_met) >= 2

    if qualifies:
        return _json({
            "success": True,
            "claim_number": claim_number,
            "qualifies_for_rush": True,
            "criteria_met": criteria_met,
            "criteria_count": len(substantive_met),
            "criteria_descriptions": criteria_descriptions,
            "message": (
                f"Qualifies for ISRUSH assignment. {len(substantive_met)} criteria met: "
                f"{'; '.join([d for d in criteria_descriptions if d != 'Explicit escalation request'])}. "
                "Will document with ISRUSH diary and notify assignment within 2 business days."
            ),
        })
    else:
        return _json({
            "success": True,
            "claim_number": claim_number,
            "qualifies_for_rush": False,
            "criteria_met": criteria_met,
            "criteria_count": len(substantive_met),
            "criteria_descriptions": criteria_descriptions,
            "message": (
                f"Does not meet rush criteria. Only {len(substantive_met)} criterion met (need at least 2). "
                "Qualifying factors: OOP expenses, third call, attorney/suit, DOI complaint, or statute near. "
                "Your request has been documented on the file."
            ),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: create_isrush_diary
# ═══════════════════════════════════════════════════════════════════════════════

create_isrush_diary_schema: Dict[str, Any] = {
    "name": "create_isrush_diary",
    "description": (
        "Create an ISRUSH diary entry for expedited subrogation demand handling. "
        "Use after evaluate_rush_criteria confirms qualification."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number",
            },
            "reason": {
                "type": "string",
                "description": "Reason for rush assignment (from rush criteria)",
            },
            "cc_company": {
                "type": "string",
                "description": "Claimant Carrier company name",
            },
            "caller_name": {
                "type": "string",
                "description": "Name of the CC representative who called",
            },
        },
        "required": ["claim_number", "reason"],
    },
}


async def create_isrush_diary(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create ISRUSH diary entry."""
    claim_number = (args.get("claim_number") or "").strip().upper()
    reason = (args.get("reason") or "").strip()
    cc_company = (args.get("cc_company") or "").strip()
    caller_name = (args.get("caller_name") or "").strip()

    if not claim_number or not reason:
        return _json({
            "success": False,
            "message": "Claim number and reason are required.",
        })

    # Generate diary ID
    diary_id = f"ISRUSH-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"

    logger.info(
        "📋 ISRUSH Diary Created | claim=%s diary=%s reason=%s",
        claim_number, diary_id, reason
    )

    return _json({
        "success": True,
        "claim_number": claim_number,
        "diary_id": diary_id,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message": f"ISRUSH diary {diary_id} created for rush handling. Reason: {reason}.",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: append_claim_note
# ═══════════════════════════════════════════════════════════════════════════════

append_claim_note_schema: Dict[str, Any] = {
    "name": "append_claim_note",
    "description": (
        "Document the Claimant Carrier call interaction in CLAIMPRO under the Subrogation category. "
        "MUST be called at the end of every subrogation call to record "
        "who called, what was discussed, and any actions taken."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number",
            },
            "cc_company": {
                "type": "string",
                "description": "Claimant Carrier company name",
            },
            "caller_name": {
                "type": "string",
                "description": "Name of the CC representative",
            },
            "inquiry_type": {
                "type": "string",
                "enum": ["demand_status", "liability", "coverage", "limits", "payment", "rush_request", "handler_callback", "general"],
                "description": "Type of inquiry: demand_status (demand receipt/assignment), liability (liability decision), coverage (coverage status/CVQ), limits (policy limits), payment (payments made), rush_request (expedite request), handler_callback (callback requested), general (multiple topics)",
            },
            "summary": {
                "type": "string",
                "description": "Brief summary including request made and response given (e.g., 'CC inquired about demand status. Confirmed demand received 11/20 for $12,500, under review by Sarah Johnson.')",
            },
            "actions_taken": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of actions taken (e.g., 'Provided demand status', 'Created ISRUSH diary', 'Noted callback request')",
            },
        },
        "required": ["claim_number", "cc_company", "caller_name", "inquiry_type", "summary"],
    },
}


async def append_claim_note(args: Dict[str, Any]) -> Dict[str, Any]:
    """Append note to claim documenting the CC call in Subrogation category."""
    claim_number = (args.get("claim_number") or "").strip().upper()
    cc_company = (args.get("cc_company") or "").strip()
    caller_name = (args.get("caller_name") or "").strip()
    inquiry_type = (args.get("inquiry_type") or "general").strip()
    summary = (args.get("summary") or "").strip()
    actions = args.get("actions_taken") or []

    if not claim_number or not summary:
        return _json({
            "success": False,
            "message": "Claim number and summary are required.",
        })

    # Generate note ID
    note_id = f"SUBRO-NOTE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"

    # Map inquiry types to human-readable categories
    inquiry_labels = {
        "demand_status": "Demand Status Inquiry",
        "liability": "Liability Inquiry",
        "coverage": "Coverage Inquiry",
        "limits": "Policy Limits Inquiry",
        "payment": "Payment Inquiry",
        "rush_request": "Rush/Expedite Request",
        "handler_callback": "Handler Callback Request",
        "general": "General Inquiry",
    }
    inquiry_label = inquiry_labels.get(inquiry_type, inquiry_type.replace("_", " ").title())

    note_content = (
        f"═══════════════════════════════════════\n"
        f"CC HOTLINE CALL - {inquiry_label}\n"
        f"═══════════════════════════════════════\n"
        f"Caller: {caller_name}\n"
        f"Company: {cc_company}\n"
        f"Category: Subrogation\n"
        f"───────────────────────────────────────\n"
        f"Request/Response:\n{summary}\n"
    )
    if actions:
        note_content += f"───────────────────────────────────────\n"
        note_content += f"Actions Taken:\n• " + "\n• ".join(actions) + "\n"
    note_content += f"═══════════════════════════════════════\n"

    logger.info(
        "📝 Claim Note Added | claim=%s note=%s type=%s cc=%s",
        claim_number, note_id, inquiry_type, cc_company
    )

    return _json({
        "success": True,
        "claim_number": claim_number,
        "note_id": note_id,
        "inquiry_type": inquiry_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message": f"Call documented in Subrogation notes. Note ID: {note_id}.",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: close_and_document_call
# ═══════════════════════════════════════════════════════════════════════════════

close_and_document_call_schema: Dict[str, Any] = {
    "name": "close_and_document_call",
    "description": (
        "Close the call and document the interaction. Creates a detailed claim note "
        "summarizing the entire conversation and optionally sends a confirmation email "
        "to the Claimant Carrier representative. MUST be called at the end of every "
        "subrogation call before saying goodbye."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim_number": {
                "type": "string",
                "description": "The claim number discussed",
            },
            "cc_company": {
                "type": "string",
                "description": "Claimant Carrier company name",
            },
            "caller_name": {
                "type": "string",
                "description": "Name of the CC representative",
            },
            "caller_email": {
                "type": "string",
                "description": "Email address for the CC rep to send confirmation (optional - ask if they want email confirmation)",
            },
            "topics_discussed": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["demand_status", "liability", "coverage", "limits", "payment", "rush_request", "handler_callback"],
                },
                "description": "List of topics discussed during the call",
            },
            "key_responses": {
                "type": "object",
                "description": "Key information provided during the call",
                "properties": {
                    "demand_status": {
                        "type": "string",
                        "description": "Demand status provided (e.g., 'Received 11/20, under review by Sarah Johnson')",
                    },
                    "liability_decision": {
                        "type": "string",
                        "description": "Liability decision provided (e.g., 'Accepted at 80%', 'Pending', 'Denied')",
                    },
                    "coverage_status": {
                        "type": "string",
                        "description": "Coverage status provided (e.g., 'Confirmed', 'CVQ open', 'Denied')",
                    },
                    "limits_info": {
                        "type": "string",
                        "description": "Limits info provided (e.g., 'No limits issue', 'PD limit $25,000')",
                    },
                    "payment_info": {
                        "type": "string",
                        "description": "Payment info provided (e.g., 'No payments', '$8,500 paid to Fabrikam')",
                    },
                    "rush_status": {
                        "type": "string",
                        "description": "Rush handling status (e.g., 'Flagged for rush - attorney represented', 'Does not qualify')",
                    },
                    "handler_info": {
                        "type": "string",
                        "description": "Handler/callback info (e.g., 'Callback requested from Sarah Johnson')",
                    },
                },
            },
            "actions_taken": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of actions taken (e.g., 'Created ISRUSH diary', 'Noted callback request')",
            },
            "send_email_confirmation": {
                "type": "boolean",
                "description": "Whether to send email confirmation to the CC rep (default: false, only if they requested it)",
            },
        },
        "required": ["claim_number", "cc_company", "caller_name", "topics_discussed", "key_responses"],
    },
}


def _build_call_summary_email(
    claim_number: str,
    cc_company: str,
    caller_name: str,
    topics: List[str],
    responses: Dict[str, str],
    actions: List[str],
    institution_name: str = "XYMZ Insurance",
) -> tuple[str, str, str]:
    """
    Build email content for call summary confirmation.
    
    Returns:
        Tuple of (subject, plain_text_body, html_body)
    """
    subject = f"Call Summary - Claim {claim_number} | {institution_name} Subrogation"
    
    # Topic labels for display
    topic_labels = {
        "demand_status": "Demand Status",
        "liability": "Liability Decision",
        "coverage": "Coverage Status",
        "limits": "Policy Limits",
        "payment": "Payment Information",
        "rush_request": "Rush Handling",
        "handler_callback": "Handler Callback",
    }
    
    # Build response details
    response_lines = []
    if responses.get("demand_status"):
        response_lines.append(f"• Demand Status: {responses['demand_status']}")
    if responses.get("liability_decision"):
        response_lines.append(f"• Liability: {responses['liability_decision']}")
    if responses.get("coverage_status"):
        response_lines.append(f"• Coverage: {responses['coverage_status']}")
    if responses.get("limits_info"):
        response_lines.append(f"• Limits: {responses['limits_info']}")
    if responses.get("payment_info"):
        response_lines.append(f"• Payments: {responses['payment_info']}")
    if responses.get("rush_status"):
        response_lines.append(f"• Rush Handling: {responses['rush_status']}")
    if responses.get("handler_info"):
        response_lines.append(f"• Handler: {responses['handler_info']}")
    
    response_text = "\n".join(response_lines) if response_lines else "No specific information provided."
    actions_text = "\n".join(f"• {a}" for a in actions) if actions else "No specific actions taken."
    topics_text = ", ".join(topic_labels.get(t, t) for t in topics)
    
    # Plain text version
    plain_text_body = f"""Hi {caller_name},

Thank you for calling {institution_name} Subrogation.

CALL SUMMARY
============
Claim Number: {claim_number}
Your Company: {cc_company}
Topics Discussed: {topics_text}

INFORMATION PROVIDED
====================
{response_text}

ACTIONS TAKEN
=============
{actions_text}

CONTACT INFORMATION
===================
Subro Fax (for demands): {SUBRO_FAX_NUMBER}
Subro Phone (for inquiries): {SUBRO_PHONE_NUMBER}

If you have any questions, please call us at {SUBRO_PHONE_NUMBER}.

Thank you for your business.

{institution_name} Subrogation Department
"""

    # HTML version
    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" style="width: 100%; border-collapse: collapse;">
        <tr>
            <td align="center" style="padding: 40px 0;">
                <table role="presentation" style="width: 600px; max-width: 100%; border-collapse: collapse;">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #1e3a5f, #2d5a87); padding: 30px; border-radius: 8px 8px 0 0; text-align: center;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">Call Summary</h1>
                            <p style="margin: 10px 0 0 0; color: #a0c4e8; font-size: 14px;">{institution_name} Subrogation</p>
                        </td>
                    </tr>
                    <!-- Body -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 30px;">
                            <p style="margin: 0 0 20px 0; color: #333333; font-size: 16px;">Hi {caller_name},</p>
                            <p style="margin: 0 0 25px 0; color: #666666; font-size: 14px;">
                                Thank you for calling {institution_name} Subrogation. Below is a summary of our conversation.
                            </p>
                            
                            <!-- Claim Info Box -->
                            <div style="background-color: #f8fafc; border-left: 4px solid #2d5a87; padding: 15px; margin-bottom: 25px; border-radius: 0 4px 4px 0;">
                                <table style="width: 100%; border-collapse: collapse;">
                                    <tr>
                                        <td style="padding: 5px 0; color: #666666; font-size: 14px;">Claim Number:</td>
                                        <td style="padding: 5px 0; color: #1e3a5f; font-size: 14px; font-weight: 600; text-align: right;">{claim_number}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 5px 0; color: #666666; font-size: 14px;">Your Company:</td>
                                        <td style="padding: 5px 0; color: #333333; font-size: 14px; text-align: right;">{cc_company}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 5px 0; color: #666666; font-size: 14px;">Topics Discussed:</td>
                                        <td style="padding: 5px 0; color: #333333; font-size: 14px; text-align: right;">{topics_text}</td>
                                    </tr>
                                </table>
                            </div>
                            
                            <!-- Information Provided -->
                            <h3 style="margin: 0 0 15px 0; color: #1e3a5f; font-size: 16px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px;">Information Provided</h3>
                            <div style="margin-bottom: 25px; color: #333333; font-size: 14px; line-height: 1.8;">
                                {response_text.replace(chr(10), '<br>').replace('• ', '&#8226; ')}
                            </div>
                            
                            <!-- Actions Taken -->
                            <h3 style="margin: 0 0 15px 0; color: #1e3a5f; font-size: 16px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px;">Actions Taken</h3>
                            <div style="margin-bottom: 25px; color: #333333; font-size: 14px; line-height: 1.8;">
                                {actions_text.replace(chr(10), '<br>').replace('• ', '&#8226; ')}
                            </div>
                            
                            <!-- Contact Box -->
                            <div style="background-color: #e8f4fd; padding: 20px; border-radius: 4px; margin-top: 25px;">
                                <h4 style="margin: 0 0 10px 0; color: #1e3a5f; font-size: 14px;">Contact Information</h4>
                                <p style="margin: 0; color: #666666; font-size: 13px;">
                                    <strong>Fax (for demands):</strong> {SUBRO_FAX_NUMBER}<br>
                                    <strong>Phone (for inquiries):</strong> {SUBRO_PHONE_NUMBER}
                                </p>
                            </div>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8fafc; padding: 20px; border-radius: 0 0 8px 8px; text-align: center;">
                            <p style="margin: 0 0 5px 0; color: #666666; font-size: 12px;">Questions? Call us at {SUBRO_PHONE_NUMBER}</p>
                            <p style="margin: 0; color: #999999; font-size: 11px;">© 2025 {institution_name}. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    return subject, plain_text_body, html_body


async def close_and_document_call(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Close the call and document the interaction.
    
    Creates a detailed claim note and optionally sends email confirmation.
    """
    claim_number = (args.get("claim_number") or "").strip().upper()
    cc_company = (args.get("cc_company") or "").strip()
    caller_name = (args.get("caller_name") or "").strip()
    caller_email = (args.get("caller_email") or "").strip()
    topics = args.get("topics_discussed") or []
    responses = args.get("key_responses") or {}
    actions = args.get("actions_taken") or []
    send_email = args.get("send_email_confirmation", False)
    
    if not claim_number or not cc_company or not caller_name:
        return _json({
            "success": False,
            "message": "Claim number, CC company, and caller name are required.",
        })
    
    if not topics:
        return _json({
            "success": False,
            "message": "At least one topic discussed is required.",
        })
    
    # Generate note ID
    note_id = f"SUBRO-NOTE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
    
    # Topic labels
    topic_labels = {
        "demand_status": "Demand Status",
        "liability": "Liability Decision",
        "coverage": "Coverage Status",
        "limits": "Policy Limits",
        "payment": "Payment Information",
        "rush_request": "Rush Handling",
        "handler_callback": "Handler Callback",
    }
    topics_display = ", ".join(topic_labels.get(t, t) for t in topics)
    
    # Build comprehensive note
    note_lines = [
        "═══════════════════════════════════════",
        f"CC HOTLINE CALL - CALL SUMMARY",
        "═══════════════════════════════════════",
        f"Caller: {caller_name}",
        f"Company: {cc_company}",
        f"Category: Subrogation",
        f"Topics: {topics_display}",
        "───────────────────────────────────────",
        "Request/Response Details:",
    ]
    
    # Add each response detail
    if responses.get("demand_status"):
        note_lines.append(f"  • Demand Status: {responses['demand_status']}")
    if responses.get("liability_decision"):
        note_lines.append(f"  • Liability: {responses['liability_decision']}")
    if responses.get("coverage_status"):
        note_lines.append(f"  • Coverage: {responses['coverage_status']}")
    if responses.get("limits_info"):
        note_lines.append(f"  • Limits: {responses['limits_info']}")
    if responses.get("payment_info"):
        note_lines.append(f"  • Payments: {responses['payment_info']}")
    if responses.get("rush_status"):
        note_lines.append(f"  • Rush: {responses['rush_status']}")
    if responses.get("handler_info"):
        note_lines.append(f"  • Handler: {responses['handler_info']}")
    
    if actions:
        note_lines.append("───────────────────────────────────────")
        note_lines.append("Actions Taken:")
        for action in actions:
            note_lines.append(f"  • {action}")
    
    note_lines.append("═══════════════════════════════════════")
    note_content = "\n".join(note_lines)
    
    logger.info(
        "📝 Call Documented | claim=%s note=%s topics=%s cc=%s",
        claim_number, note_id, topics, cc_company
    )
    
    # Handle email confirmation
    email_sent = False
    email_error = None
    
    if send_email and caller_email:
        if send_email_async and is_email_configured():
            try:
                subject, plain_text, html_body = _build_call_summary_email(
                    claim_number=claim_number,
                    cc_company=cc_company,
                    caller_name=caller_name,
                    topics=topics,
                    responses=responses,
                    actions=actions,
                )
                result = await send_email_async(caller_email, subject, plain_text, html_body)
                email_sent = result.get("success", False)
                if not email_sent:
                    email_error = result.get("error")
                logger.info("📧 Call summary email sent: %s - %s", caller_email, "success" if email_sent else email_error)
            except Exception as exc:
                email_error = str(exc)
                logger.warning("📧 Call summary email failed: %s", exc)
        else:
            email_error = "Email service not configured"
            logger.info("📧 Email service not configured for call summary")
    elif send_email and not caller_email:
        email_error = "No email address provided"
    
    result = {
        "success": True,
        "claim_number": claim_number,
        "note_id": note_id,
        "topics_documented": topics,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message": f"Call documented in Subrogation notes. Note ID: {note_id}.",
    }
    
    if send_email:
        result["email_confirmation_sent"] = email_sent
        result["email_address"] = caller_email if caller_email else None
        if email_error:
            result["email_error"] = email_error
        if email_sent:
            result["message"] += f" Confirmation email sent to {caller_email}."
    
    return _json(result)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_subro_contact_info
# ═══════════════════════════════════════════════════════════════════════════════

get_subro_contact_info_schema: Dict[str, Any] = {
    "name": "get_subro_contact_info",
    "description": (
        "Get contact information for the subrogation department. "
        "Returns fax number for demands and phone number for inquiries."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def get_subro_contact_info(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get subro department contact info."""
    return _json({
        "success": True,
        "fax_number": SUBRO_FAX_NUMBER,
        "phone_number": SUBRO_PHONE_NUMBER,
        "message": (
            f"Subrogation demands can be faxed to {SUBRO_FAX_NUMBER}. "
            f"For inquiries, call {SUBRO_PHONE_NUMBER}."
        ),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: switch_claim
# ═══════════════════════════════════════════════════════════════════════════════

switch_claim_schema: Dict[str, Any] = {
    "name": "switch_claim",
    "description": (
        "Switch to a different claim during the call. "
        "Use when caller asks about a DIFFERENT claim number than the one they were verified for. "
        "Verifies the new claim belongs to the same claimant carrier before switching. "
        "If the new claim belongs to a different CC, informs caller they need separate verification."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "new_claim_number": {
                "type": "string",
                "description": "The new claim number the caller wants to discuss",
            },
            "current_cc_company": {
                "type": "string",
                "description": "The claimant carrier company from the original verification",
            },
        },
        "required": ["new_claim_number", "current_cc_company"],
    },
}


async def switch_claim(args: Dict[str, Any]) -> Dict[str, Any]:
    """Switch to a different claim, verifying same CC company.
    
    This allows a CC rep to ask about multiple claims in one call without
    full re-authentication, as long as the claims belong to the same CC.
    """
    new_claim_number = (args.get("new_claim_number") or "").strip().upper()
    current_cc_company = (args.get("current_cc_company") or "").strip()

    if not new_claim_number:
        return _json({
            "success": False,
            "message": "Please provide the new claim number you'd like to discuss.",
        })

    if not current_cc_company:
        return _json({
            "success": False,
            "message": "Current CC company context is required for claim switch.",
        })

    # Look up the new claim
    claim = _find_claim_by_number(args, new_claim_number)
    if not claim:
        return _json({
            "success": False,
            "claim_found": False,
            "message": f"Claim {new_claim_number} not found in our system. Please verify the claim number.",
        })

    # Check if the CC matches
    cc_on_record = (claim.get("claimant_carrier") or "").lower()
    current_cc_normalized = current_cc_company.lower()
    
    # Normalize for comparison
    cc_on_record_clean = cc_on_record.replace(" insurance", "").strip()
    current_cc_clean = current_cc_normalized.replace(" insurance", "").strip()

    cc_matches = (
        cc_on_record == current_cc_normalized or
        cc_on_record_clean == current_cc_clean or
        cc_on_record.startswith(current_cc_clean) or
        current_cc_normalized.startswith(cc_on_record_clean)
    )

    if not cc_matches:
        return _json({
            "success": False,
            "claim_found": True,
            "cc_matches": False,
            "message": (
                f"Claim {new_claim_number} is associated with a different claimant carrier. "
                "You would need to call back and verify separately for that claim."
            ),
        })

    # Success - return the new claim context
    logger.info(
        "🔄 Claim Switch | new_claim=%s cc=%s claimant=%s",
        new_claim_number, current_cc_company, claim.get("claimant_name")
    )

    return _json({
        "success": True,
        "claim_found": True,
        "cc_matches": True,
        "new_claim_number": new_claim_number,
        "claimant_name": claim.get("claimant_name"),
        "loss_date": claim.get("loss_date"),
        "insured_name": claim.get("insured_name"),
        "message": f"Switched to claim {new_claim_number}. How can I help you with this claim?",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

# NOTE: verify_cc_caller is registered in auth.py (it queries Cosmos DB directly)

# Claim Information Tools
register_tool(
    name="get_claim_summary",
    schema=get_claim_summary_schema,
    executor=get_claim_summary,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="get_subro_demand_status",
    schema=get_subro_demand_status_schema,
    executor=get_subro_demand_status,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="get_coverage_status",
    schema=get_coverage_status_schema,
    executor=get_coverage_status,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="get_liability_decision",
    schema=get_liability_decision_schema,
    executor=get_liability_decision,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="get_pd_policy_limits",
    schema=get_pd_policy_limits_schema,
    executor=get_pd_policy_limits,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="get_pd_payments",
    schema=get_pd_payments_schema,
    executor=get_pd_payments,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="resolve_feature_owner",
    schema=resolve_feature_owner_schema,
    executor=resolve_feature_owner,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="evaluate_rush_criteria",
    schema=evaluate_rush_criteria_schema,
    executor=evaluate_rush_criteria,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="create_isrush_diary",
    schema=create_isrush_diary_schema,
    executor=create_isrush_diary,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="append_claim_note",
    schema=append_claim_note_schema,
    executor=append_claim_note,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="close_and_document_call",
    schema=close_and_document_call_schema,
    executor=close_and_document_call,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="get_subro_contact_info",
    schema=get_subro_contact_info_schema,
    executor=get_subro_contact_info,
    tags={"scenario": "insurance", "category": "subro"},
)

register_tool(
    name="switch_claim",
    schema=switch_claim_schema,
    executor=switch_claim,
    tags={"scenario": "insurance", "category": "subro"},
)
