"""
Insurance Policy Tools - Query User's Policy Data
==================================================

Tools for querying policy information from the user's loaded demo profile.
These tools query Cosmos DB directly to get policy data.

Data Source:
- Tools query Cosmos DB directly to find policies by client_id or policy_number
- Falls back to _session_profile if available
- Policies are stored in demo_metadata.policies
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, Dict, List

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

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

logger = get_logger("agents.tools.policy")

# Cached Cosmos manager for policy tools
_COSMOS_USERS_MANAGER: CosmosDBMongoCoreManager | None = None


def _json(data: Any) -> Dict[str, Any]:
    """Wrap response data for consistent JSON output."""
    return data if isinstance(data, dict) else {"result": data}


# ═══════════════════════════════════════════════════════════════════════════════
# COSMOS DB HELPERS: Query policies directly from database
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
        try:
            db_name = getattr(getattr(base_manager, "database", None), "name", None)
            coll_name = getattr(getattr(base_manager, "collection", None), "name", None)
            if db_name == database_name and coll_name == container_name:
                _COSMOS_USERS_MANAGER = base_manager
                return _COSMOS_USERS_MANAGER
        except Exception:
            pass

    if _CosmosManagerImpl is None:
        logger.debug("Cosmos manager implementation unavailable for policy tools")
        return None

    try:
        _COSMOS_USERS_MANAGER = _CosmosManagerImpl(
            database_name=database_name,
            collection_name=container_name,
        )
        logger.info(
            "Policy tools connected to Cosmos demo users collection",
            extra={"database": database_name, "collection": container_name},
        )
        return _COSMOS_USERS_MANAGER
    except Exception as exc:  # pragma: no cover
        logger.warning("Unable to initialize Cosmos manager for policy tools: %s", exc)
        return None


def _lookup_user_policies_in_cosmos(client_id: str) -> List[Dict[str, Any]]:
    """
    Look up a user's policies by client_id in Cosmos DB.
    
    Returns list of policy dicts, or empty list if not found.
    """
    cosmos = _get_demo_users_manager()
    if cosmos is None:
        return []

    query: Dict[str, Any] = {"_id": client_id}
    
    logger.info("🔍 Cosmos policy lookup by client_id | client_id=%s", client_id)

    try:
        document = cosmos.read_document(query)
        if document:
            policies = document.get("demo_metadata", {}).get("policies", [])
            logger.info("✓ Found %d policies for client %s in Cosmos", len(policies), client_id)
            return policies
    except Exception as exc:  # pragma: no cover
        logger.warning("Cosmos policy lookup failed: %s", exc)

    return []


def _lookup_user_claims_in_cosmos(client_id: str) -> List[Dict[str, Any]]:
    """
    Look up a user's claims by client_id in Cosmos DB.
    
    Returns list of claim dicts, or empty list if not found.
    """
    cosmos = _get_demo_users_manager()
    if cosmos is None:
        return []

    query: Dict[str, Any] = {"_id": client_id}
    
    logger.info("🔍 Cosmos claims lookup by client_id | client_id=%s", client_id)

    try:
        document = cosmos.read_document(query)
        if document:
            claims = document.get("demo_metadata", {}).get("claims", [])
            logger.info("✓ Found %d claims for client %s in Cosmos", len(claims), client_id)
            return claims
    except Exception as exc:  # pragma: no cover
        logger.warning("Cosmos claims lookup failed: %s", exc)

    return []


def _lookup_policy_by_number_in_cosmos(policy_number: str) -> tuple[Dict[str, Any] | None, List[Dict[str, Any]]]:
    """
    Look up a policy by policy number in Cosmos DB.
    
    Returns (policy_dict, all_user_policies) or (None, []) if not found.
    """
    cosmos = _get_demo_users_manager()
    if cosmos is None:
        return None, []

    query: Dict[str, Any] = {
        "demo_metadata.policies.policy_number": {"$regex": f"^{re.escape(policy_number)}$", "$options": "i"}
    }
    
    logger.info("🔍 Cosmos policy lookup by number | policy_number=%s", policy_number)

    try:
        document = cosmos.read_document(query)
        if document:
            policies = document.get("demo_metadata", {}).get("policies", [])
            policy_upper = policy_number.upper()
            for policy in policies:
                if policy.get("policy_number", "").upper() == policy_upper:
                    logger.info("✓ Found policy %s in Cosmos", policy_number)
                    return policy, policies
    except Exception as exc:  # pragma: no cover
        logger.warning("Cosmos policy lookup failed: %s", exc)

    return None, []


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Get policies from session profile
# ═══════════════════════════════════════════════════════════════════════════════

def _get_policies_from_profile(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract policies list from session profile or Cosmos DB.
    
    Lookup order:
    1. Cosmos DB by client_id (from args directly or session profile)
    2. _session_profile.demo_metadata.policies
    3. _session_profile.policies
    
    Returns empty list if no policies found.
    """
    session_profile = args.get("_session_profile", {}) or {}
    
    # Try client_id from direct args first (passed from auth response)
    client_id = args.get("client_id")
    
    # Fallback to session_profile.client_id
    if not client_id:
        client_id = session_profile.get("client_id")
    
    # Try Cosmos DB lookup by client_id
    if client_id:
        cosmos_policies = _lookup_user_policies_in_cosmos(client_id)
        if cosmos_policies:
            return cosmos_policies
    
    if not session_profile:
        logger.warning("No session profile available for policy lookup")
        return []
    
    # Fallback: Try demo_metadata.policies
    demo_meta = session_profile.get("demo_metadata", {})
    policies = demo_meta.get("policies", [])
    if policies:
        logger.info("📋 Found %d policies in session profile", len(policies))
        return policies
    
    # Fallback: Try top-level policies
    policies = session_profile.get("policies", [])
    if policies:
        logger.info("📋 Found %d policies at top level", len(policies))
        return policies
    
    logger.warning("No policies found in session profile or Cosmos")
    return []


def _get_claims_from_profile(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract claims list from session profile or Cosmos DB.
    
    Lookup order:
    1. Cosmos DB by client_id (from args directly or session profile)
    2. _session_profile.demo_metadata.claims
    3. _session_profile.claims
    
    Returns empty list if no claims found.
    """
    session_profile = args.get("_session_profile", {}) or {}
    
    # Try client_id from direct args first (passed from auth response)
    client_id = args.get("client_id")
    
    # Fallback to session_profile.client_id
    if not client_id:
        client_id = session_profile.get("client_id")
    
    # Try Cosmos DB lookup by client_id
    if client_id:
        cosmos_claims = _lookup_user_claims_in_cosmos(client_id)
        if cosmos_claims:
            return cosmos_claims
    
    # Fallback: Try demo_metadata.claims
    demo_meta = session_profile.get("demo_metadata", {})
    claims = demo_meta.get("claims", [])
    if claims:
        return claims
    
    return session_profile.get("claims", [])


def _find_policy_by_number(args: Dict[str, Any], policy_number: str) -> Dict[str, Any] | None:
    """
    Find a policy by policy number.
    
    Lookup order:
    1. Cosmos DB direct lookup by policy_number
    2. Session profile policies
    """
    policy_number_upper = policy_number.upper()
    
    # First try Cosmos DB direct lookup
    cosmos_policy, _ = _lookup_policy_by_number_in_cosmos(policy_number_upper)
    if cosmos_policy:
        return cosmos_policy
    
    # Fallback to session profile
    policies = _get_policies_from_profile(args)
    for policy in policies:
        if policy.get("policy_number", "").upper() == policy_number_upper:
            return policy
    
    logger.warning("❌ Policy %s not found in any source", policy_number_upper)
    return None


def _format_currency(amount: float | None) -> str:
    """Format a number as currency."""
    if amount is None:
        return "N/A"
    return f"${amount:,.2f}"


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: search_policy_info
# ═══════════════════════════════════════════════════════════════════════════════

search_policy_info_schema: Dict[str, Any] = {
    "name": "search_policy_info",
    "description": (
        "Search the user's insurance policies for specific information. "
        "Queries the loaded profile data to answer questions about coverage, "
        "deductibles, limits, vehicles, property, premiums, and policy status. "
        "Use this instead of search_knowledge_base for policy-specific questions. "
        "Pass the client_id from the authentication response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language query about the user's policy (e.g., 'do I have roadside assistance', 'what is my deductible', 'what cars are covered')",
            },
            "policy_type": {
                "type": "string",
                "enum": ["auto", "home", "umbrella", "all"],
                "description": "Filter by policy type, or 'all' for all policies",
                "default": "all",
            },
            "client_id": {
                "type": "string",
                "description": "The client_id returned from verify_client_identity. Required for policy lookup.",
            },
        },
        "required": ["query", "client_id"],
    },
}


async def search_policy_info(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search user's policies based on a natural language query.
    
    This grounded search looks at the actual policy data from the user's
    loaded demo profile and returns relevant information.
    """
    query = (args.get("query") or "").strip().lower()
    policy_type_filter = (args.get("policy_type") or "all").lower()
    
    if not query:
        return _json({
            "success": False,
            "message": "Please provide a query about what policy information you need.",
        })
    
    policies = _get_policies_from_profile(args)
    
    if not policies:
        return _json({
            "success": False,
            "message": "No policies found. Please ensure your profile is loaded.",
            "policies_found": 0,
        })
    
    # Filter by policy type if specified
    if policy_type_filter != "all":
        policies = [p for p in policies if p.get("policy_type") == policy_type_filter]
    
    if not policies:
        return _json({
            "success": False,
            "message": f"No {policy_type_filter} policies found in your profile.",
            "policies_found": 0,
        })
    
    # Build comprehensive policy summary for grounding
    results = []
    for policy in policies:
        policy_info = {
            "policy_number": policy.get("policy_number"),
            "type": policy.get("policy_type"),
            "status": policy.get("status"),
            "effective_date": policy.get("effective_date"),
            "expiration_date": policy.get("expiration_date"),
            "premium": _format_currency(policy.get("premium_amount")),
            "deductible": _format_currency(policy.get("deductible")),
        }
        
        # Add coverage limits
        coverage = policy.get("coverage_limits", {})
        if coverage:
            policy_info["coverage_limits"] = {
                k: _format_currency(v) if isinstance(v, (int, float)) else v
                for k, v in coverage.items()
            }
        
        # Add vehicle info for auto policies
        vehicles = policy.get("vehicles", [])
        if vehicles:
            policy_info["vehicles"] = [
                f"{v.get('year')} {v.get('make')} {v.get('model')} ({v.get('color', 'N/A')})"
                for v in vehicles
            ]
        
        # Add property info for home policies
        property_addr = policy.get("property_address")
        if property_addr:
            policy_info["property_address"] = property_addr
        
        results.append(policy_info)
    
    # Generate a natural language summary based on the query
    summary = _generate_policy_summary(query, results)
    
    return _json({
        "success": True,
        "query": query,
        "policies_found": len(results),
        "policies": results,
        "summary": summary,
    })


def _generate_policy_summary(query: str, policies: List[Dict[str, Any]]) -> str:
    """Generate a natural language summary based on the query and policy data."""
    
    # Keywords for different types of queries
    deductible_keywords = ["deductible", "out of pocket", "pay first"]
    coverage_keywords = ["coverage", "covered", "limit", "limits", "maximum", "how much"]
    premium_keywords = ["premium", "cost", "payment", "pay", "price", "monthly"]
    vehicle_keywords = ["car", "vehicle", "auto", "truck", "insured vehicle"]
    home_keywords = ["home", "house", "property", "dwelling", "address"]
    status_keywords = ["active", "status", "expired", "current", "valid"]
    roadside_keywords = ["roadside", "tow", "towing", "breakdown", "assistance"]
    
    summary_parts = []
    
    # Check query intent and build summary
    if any(kw in query for kw in deductible_keywords):
        for p in policies:
            deductible = p.get("deductible", "N/A")
            policy_type = p.get("type", "unknown")
            summary_parts.append(f"Your {policy_type} policy has a {deductible} deductible.")
    
    elif any(kw in query for kw in roadside_keywords):
        # Check comprehensive coverage which typically includes roadside
        for p in policies:
            if p.get("type") == "auto":
                coverage = p.get("coverage_limits", {})
                if coverage.get("comprehensive"):
                    summary_parts.append(
                        f"Your auto policy includes comprehensive coverage at {coverage['comprehensive']}, "
                        "which typically includes roadside assistance. Check your policy documents for specific roadside benefits."
                    )
                else:
                    summary_parts.append("Your auto policy does not appear to include comprehensive coverage.")
    
    elif any(kw in query for kw in coverage_keywords):
        for p in policies:
            policy_type = p.get("type", "unknown")
            coverage = p.get("coverage_limits", {})
            if coverage:
                limits_str = ", ".join([f"{k.replace('_', ' ')}: {v}" for k, v in coverage.items()])
                summary_parts.append(f"Your {policy_type} policy coverage limits: {limits_str}.")
    
    elif any(kw in query for kw in premium_keywords):
        for p in policies:
            premium = p.get("premium", "N/A")
            policy_type = p.get("type", "unknown")
            summary_parts.append(f"Your {policy_type} policy premium is {premium}.")
    
    elif any(kw in query for kw in vehicle_keywords):
        for p in policies:
            if p.get("type") == "auto":
                vehicles = p.get("vehicles", [])
                if vehicles:
                    summary_parts.append(f"Insured vehicles: {', '.join(vehicles)}.")
    
    elif any(kw in query for kw in home_keywords):
        for p in policies:
            if p.get("type") == "home":
                addr = p.get("property_address", "N/A")
                summary_parts.append(f"Your home policy covers property at: {addr}.")
                coverage = p.get("coverage_limits", {})
                if "dwelling" in coverage:
                    summary_parts.append(f"Dwelling coverage: {coverage['dwelling']}.")
    
    elif any(kw in query for kw in status_keywords):
        for p in policies:
            policy_type = p.get("type", "unknown")
            status = p.get("status", "unknown")
            exp_date = p.get("expiration_date", "N/A")
            summary_parts.append(f"Your {policy_type} policy is {status}, expires {exp_date}.")
    
    else:
        # General summary
        policy_types = [p.get("type") for p in policies]
        summary_parts.append(f"You have {len(policies)} policy(ies): {', '.join(policy_types)}.")
        for p in policies:
            summary_parts.append(
                f"{p.get('type').title()} policy {p.get('policy_number')}: "
                f"Status {p.get('status')}, deductible {p.get('deductible')}, premium {p.get('premium')}."
            )
    
    return " ".join(summary_parts) if summary_parts else "Policy information retrieved."


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_policy_details
# ═══════════════════════════════════════════════════════════════════════════════

get_policy_details_schema: Dict[str, Any] = {
    "name": "get_policy_details",
    "description": (
        "Get detailed information about a specific policy by policy number. "
        "Returns complete policy information including coverage, vehicles, property, etc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "policy_number": {
                "type": "string",
                "description": "The policy number to look up (e.g., AUTO-ABC123-4567)",
            },
        },
        "required": ["policy_number"],
    },
}


async def get_policy_details(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get detailed information about a specific policy."""
    policy_number = (args.get("policy_number") or "").strip()
    
    if not policy_number:
        return _json({
            "success": False,
            "message": "Policy number is required.",
        })
    
    policy = _find_policy_by_number(args, policy_number)
    
    if not policy:
        return _json({
            "success": False,
            "message": f"Policy {policy_number} not found.",
        })
    
    return _json({
        "success": True,
        "policy_number": policy.get("policy_number"),
        "policy_type": policy.get("policy_type"),
        "status": policy.get("status"),
        "effective_date": policy.get("effective_date"),
        "expiration_date": policy.get("expiration_date"),
        "premium_amount": policy.get("premium_amount"),
        "deductible": policy.get("deductible"),
        "coverage_limits": policy.get("coverage_limits"),
        "vehicles": policy.get("vehicles"),
        "property_address": policy.get("property_address"),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: list_user_policies
# ═══════════════════════════════════════════════════════════════════════════════

list_user_policies_schema: Dict[str, Any] = {
    "name": "list_user_policies",
    "description": (
        "List all policies for the authenticated user. "
        "Returns a summary of each policy including type, status, and key details. "
        "Pass the client_id from the authentication response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {
                "type": "string",
                "description": "The client_id returned from verify_client_identity. Required for policy lookup.",
            },
            "policy_type": {
                "type": "string",
                "enum": ["auto", "home", "umbrella", "all"],
                "description": "Filter by policy type, or 'all' for all policies",
                "default": "all",
            },
            "status": {
                "type": "string",
                "enum": ["active", "cancelled", "expired", "all"],
                "description": "Filter by policy status",
                "default": "all",
            },
        },
        "required": ["client_id"],
    },
}


async def list_user_policies(args: Dict[str, Any]) -> Dict[str, Any]:
    """List all policies for the user with optional filtering."""
    policy_type_filter = (args.get("policy_type") or "all").lower()
    status_filter = (args.get("status") or "all").lower()
    
    policies = _get_policies_from_profile(args)
    
    if not policies:
        return _json({
            "success": False,
            "message": "No policies found. Please ensure your profile is loaded.",
            "policies": [],
        })
    
    # Apply filters
    filtered = policies
    if policy_type_filter != "all":
        filtered = [p for p in filtered if p.get("policy_type") == policy_type_filter]
    if status_filter != "all":
        filtered = [p for p in filtered if p.get("status") == status_filter]
    
    # Build summaries
    summaries = []
    for policy in filtered:
        summary = {
            "policy_number": policy.get("policy_number"),
            "type": policy.get("policy_type"),
            "status": policy.get("status"),
            "premium": _format_currency(policy.get("premium_amount")),
            "deductible": _format_currency(policy.get("deductible")),
            "effective_date": policy.get("effective_date"),
            "expiration_date": policy.get("expiration_date"),
        }
        
        # Add identifier based on type
        if policy.get("policy_type") == "auto" and policy.get("vehicles"):
            vehicles = policy.get("vehicles", [])
            if vehicles:
                v = vehicles[0]
                summary["insured_item"] = f"{v.get('year')} {v.get('make')} {v.get('model')}"
        elif policy.get("policy_type") == "home":
            summary["insured_item"] = policy.get("property_address", "Home")
        
        summaries.append(summary)
    
    return _json({
        "success": True,
        "total_policies": len(summaries),
        "policies": summaries,
        "message": f"Found {len(summaries)} policy(ies)." if summaries else "No matching policies found.",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: check_coverage
# ═══════════════════════════════════════════════════════════════════════════════

check_coverage_schema: Dict[str, Any] = {
    "name": "check_coverage",
    "description": (
        "Check if a specific type of coverage exists in the user's policies. "
        "Useful for questions like 'do I have comprehensive coverage' or 'am I covered for liability'. "
        "Pass the client_id from the authentication response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {
                "type": "string",
                "description": "The client_id returned from verify_client_identity. Required for policy lookup.",
            },
            "coverage_type": {
                "type": "string",
                "description": "The type of coverage to check for (e.g., 'comprehensive', 'collision', 'liability', 'bodily_injury', 'property_damage', 'dwelling', 'personal_property')",
            },
        },
        "required": ["client_id", "coverage_type"],
    },
}


async def check_coverage(args: Dict[str, Any]) -> Dict[str, Any]:
    """Check if a specific coverage type exists in user's policies."""
    coverage_type = (args.get("coverage_type") or "").strip().lower()
    
    if not coverage_type:
        return _json({
            "success": False,
            "message": "Please specify what type of coverage you want to check.",
        })
    
    policies = _get_policies_from_profile(args)
    
    if not policies:
        return _json({
            "success": False,
            "message": "No policies found. Please ensure your profile is loaded.",
        })
    
    # Normalize coverage type names
    coverage_aliases = {
        "comprehensive": ["comprehensive", "comp"],
        "collision": ["collision"],
        "liability": ["liability", "bodily_injury_per_person", "bodily_injury_per_accident"],
        "property_damage": ["property_damage", "pd"],
        "uninsured": ["uninsured_motorist", "uninsured", "um"],
        "dwelling": ["dwelling", "home", "house"],
        "personal_property": ["personal_property", "contents", "belongings"],
        "medical": ["medical_payments", "medical", "med_pay"],
        "roadside": ["comprehensive"],  # roadside typically included with comprehensive
    }
    
    # Find which aliases to search for
    search_keys = [coverage_type]
    for key, aliases in coverage_aliases.items():
        if coverage_type in aliases or coverage_type == key:
            search_keys = aliases
            break
    
    # Search policies for coverage
    found_coverage = []
    for policy in policies:
        coverage_limits = policy.get("coverage_limits", {})
        for key in search_keys:
            for coverage_key, limit in coverage_limits.items():
                if key in coverage_key.lower():
                    found_coverage.append({
                        "policy_number": policy.get("policy_number"),
                        "policy_type": policy.get("policy_type"),
                        "coverage_type": coverage_key,
                        "limit": _format_currency(limit) if isinstance(limit, (int, float)) else limit,
                    })
    
    if found_coverage:
        return _json({
            "success": True,
            "has_coverage": True,
            "coverage_found": found_coverage,
            "message": f"Yes, you have {coverage_type} coverage.",
        })
    else:
        return _json({
            "success": True,
            "has_coverage": False,
            "coverage_found": [],
            "message": f"No {coverage_type} coverage found in your policies.",
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA: get_claims_summary
# ═══════════════════════════════════════════════════════════════════════════════

get_claims_summary_schema: Dict[str, Any] = {
    "name": "get_claims_summary",
    "description": (
        "Get a summary of the user's insurance claims. "
        "Returns claim numbers, status, and basic details for all claims on file. "
        "Pass the client_id from the authentication response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {
                "type": "string",
                "description": "The client_id returned from verify_client_identity. Required for claims lookup.",
            },
            "status": {
                "type": "string",
                "enum": ["open", "closed", "denied", "under_investigation", "all"],
                "description": "Filter claims by status",
                "default": "all",
            },
        },
        "required": ["client_id"],
    },
}


async def get_claims_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get summary of user's claims."""
    status_filter = (args.get("status") or "all").lower()
    
    claims = _get_claims_from_profile(args)
    
    if not claims:
        return _json({
            "success": True,
            "total_claims": 0,
            "claims": [],
            "message": "No claims on file.",
        })
    
    # Apply filter
    if status_filter != "all":
        claims = [c for c in claims if c.get("status") == status_filter]
    
    summaries = []
    for claim in claims:
        summaries.append({
            "claim_number": claim.get("claim_number"),
            "policy_number": claim.get("policy_number"),
            "claim_type": claim.get("claim_type"),
            "status": claim.get("status"),
            "loss_date": claim.get("loss_date"),
            "description": claim.get("description"),
            "estimated_amount": _format_currency(claim.get("estimated_amount")),
            "paid_amount": _format_currency(claim.get("paid_amount")),
        })
    
    return _json({
        "success": True,
        "total_claims": len(summaries),
        "claims": summaries,
        "message": f"Found {len(summaries)} claim(s)." if summaries else "No matching claims.",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    name="search_policy_info",
    schema=search_policy_info_schema,
    executor=search_policy_info,
    tags={"scenario": "insurance", "category": "policy", "grounded": True},
)

register_tool(
    name="get_policy_details",
    schema=get_policy_details_schema,
    executor=get_policy_details,
    tags={"scenario": "insurance", "category": "policy"},
)

register_tool(
    name="list_user_policies",
    schema=list_user_policies_schema,
    executor=list_user_policies,
    tags={"scenario": "insurance", "category": "policy"},
)

register_tool(
    name="check_coverage",
    schema=check_coverage_schema,
    executor=check_coverage,
    tags={"scenario": "insurance", "category": "policy"},
)

register_tool(
    name="get_claims_summary",
    schema=get_claims_summary_schema,
    executor=get_claims_summary,
    tags={"scenario": "insurance", "category": "policy"},
)
