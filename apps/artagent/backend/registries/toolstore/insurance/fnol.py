"""
FNOL (First Notice of Loss) Tools
==================================

Tools for insurance claim intake, recording FNOL claims, and routing
non-claim inquiries to appropriate departments.
"""

from __future__ import annotations

import os
import random
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict

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

logger = get_logger("agents.tools.fnol")

# Cached Cosmos manager for fnol tools
_COSMOS_USERS_MANAGER: CosmosDBMongoCoreManager | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

record_fnol_schema: Dict[str, Any] = {
    "name": "record_fnol",
    "description": (
        "Record a First Notice of Loss (FNOL) claim after collecting all required information. "
        "Use this after confirming all 10 claim fields with the caller: driver identification, "
        "vehicle details, number of vehicles involved, incident description, loss date/time, "
        "loss location, vehicle drivable status, passenger information, injury assessment, and trip purpose."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "policy_id": {
                "type": "string",
                "description": "Policy ID of the insured"
            },
            "caller_name": {
                "type": "string",
                "description": "Name of the caller/policyholder"
            },
            "driver_name": {
                "type": "string",
                "description": "Name of the person driving at time of incident"
            },
            "driver_relationship": {
                "type": "string",
                "description": "Driver's relationship to policyholder (e.g., 'policyholder', 'spouse', 'child')"
            },
            "vehicle_year": {
                "type": "string",
                "description": "Year of the vehicle"
            },
            "vehicle_make": {
                "type": "string",
                "description": "Make of the vehicle (e.g., 'Honda', 'Ford')"
            },
            "vehicle_model": {
                "type": "string",
                "description": "Model of the vehicle (e.g., 'Accord', 'F-150')"
            },
            "num_vehicles_involved": {
                "type": "integer",
                "description": "Number of vehicles involved in the incident"
            },
            "incident_description": {
                "type": "string",
                "description": "Brief description of what happened"
            },
            "loss_date": {
                "type": "string",
                "description": "Date of the incident (e.g., '2025-01-15' or 'yesterday')"
            },
            "loss_time": {
                "type": "string",
                "description": "Approximate time of the incident (e.g., '7:00 AM', 'around noon')"
            },
            "loss_location": {
                "type": "string",
                "description": "Location where the incident occurred (street, city, state, zip)"
            },
            "vehicle_drivable": {
                "type": "boolean",
                "description": "Whether the vehicle was drivable after the incident"
            },
            "passengers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of passenger names (empty array if none)"
            },
            "injuries_reported": {
                "type": "boolean",
                "description": "Whether any injuries were reported"
            },
            "injury_details": {
                "type": "string",
                "description": "Description of injuries if any (empty string if none)"
            },
            "trip_purpose": {
                "type": "string",
                "description": "Purpose of the trip (e.g., 'work commute', 'personal', 'errands')"
            },
        },
        "required": [
            "policy_id",
            "caller_name",
            "driver_name",
            "vehicle_make",
            "vehicle_model",
            "incident_description",
            "loss_date",
            "loss_location",
        ],
    },
}

handoff_to_general_info_agent_schema: Dict[str, Any] = {
    "name": "handoff_to_general_info_agent",
    "description": (
        "Transfer caller to General Info Agent for non-claim inquiries. "
        "Use when caller asks about billing, policy renewal, coverage questions, "
        "or any topic unrelated to filing an insurance claim."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "policy_id": {
                "type": "string",
                "description": "Policy ID of the caller"
            },
            "caller_name": {
                "type": "string",
                "description": "Name of the caller"
            },
            "inquiry_type": {
                "type": "string",
                "description": "Type of inquiry (e.g., 'billing', 'renewal', 'coverage', 'general')"
            },
            "context": {
                "type": "string",
                "description": "Brief summary of caller's question or request"
            },
        },
        "required": ["inquiry_type"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
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
        logger.debug("Cosmos manager implementation unavailable for fnol tools")
        return None

    try:
        _COSMOS_USERS_MANAGER = _CosmosManagerImpl(
            database_name=database_name,
            collection_name=container_name,
        )
        logger.info(
            "FNOL tools connected to Cosmos demo users collection",
            extra={"database": database_name, "collection": container_name},
        )
        return _COSMOS_USERS_MANAGER
    except Exception as exc:  # pragma: no cover
        logger.warning("Unable to initialize Cosmos manager for fnol tools: %s", exc)
        return None


def _lookup_user_by_client_id(client_id: str) -> Dict[str, Any] | None:
    """Look up a user profile by client_id in Cosmos DB."""
    cosmos = _get_demo_users_manager()
    if cosmos is None:
        return None

    try:
        document = cosmos.read_document({"_id": client_id})
        if document:
            logger.info("✓ Found user %s in Cosmos", client_id)
            return document
    except Exception as exc:  # pragma: no cover
        logger.warning("Cosmos user lookup failed: %s", exc)

    return None


def _get_user_policies_from_cosmos(client_id: str) -> List[Dict[str, Any]]:
    """Get user's policies from Cosmos DB."""
    document = _lookup_user_by_client_id(client_id)
    if document:
        return document.get("demo_metadata", {}).get("policies", [])
    return []


def _json(success: bool, message: str, **kwargs) -> Dict[str, Any]:
    """Build standardized JSON response."""
    result = {"success": success, "message": message}
    result.update(kwargs)
    return result


def _generate_claim_id() -> str:
    """Generate a unique claim ID."""
    now = datetime.now(timezone.utc)
    year = now.strftime("%Y")
    # Generate random 3-letter location code and 3-digit sequence
    location_codes = ["POR", "AUS", "CAN", "NYC", "LAX", "CHI", "DEN", "SEA", "MIA", "ATL"]
    location = random.choice(location_codes)
    sequence = random.randint(100, 999)
    return f"{year}-CLA-{location}{sequence}"


def _utc_now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════

class RecordFNOLArgs(TypedDict, total=False):
    """Input schema for record_fnol."""
    policy_id: str
    caller_name: str
    driver_name: str
    driver_relationship: Optional[str]
    vehicle_year: Optional[str]
    vehicle_make: str
    vehicle_model: str
    num_vehicles_involved: Optional[int]
    incident_description: str
    loss_date: str
    loss_time: Optional[str]
    loss_location: str
    vehicle_drivable: Optional[bool]
    passengers: Optional[list]
    injuries_reported: Optional[bool]
    injury_details: Optional[str]
    trip_purpose: Optional[str]


async def record_fnol(args: RecordFNOLArgs) -> Dict[str, Any]:
    """
    Record a First Notice of Loss (FNOL) claim.
    
    Creates a new insurance claim record with all collected information
    from the caller. Generates a unique claim ID and confirms the filing.
    
    Args:
        _session_profile: Optional session profile injected by orchestrator
        policy_id: Policy ID of the insured (falls back to session profile)
        caller_name: Name of the caller (falls back to session profile)
        driver_name: Name of the driver at time of incident
        driver_relationship: Driver's relationship to policyholder
        vehicle_year: Year of the vehicle
        vehicle_make: Make of the vehicle
        vehicle_model: Model of the vehicle
        num_vehicles_involved: Number of vehicles involved
        incident_description: What happened
        loss_date: Date of incident
        loss_time: Time of incident
        loss_location: Where it happened
        vehicle_drivable: Whether vehicle was drivable
        passengers: List of passenger names
        injuries_reported: Whether injuries were reported
        injury_details: Description of injuries
        trip_purpose: Purpose of the trip
    
    Returns:
        Dict with claim_id, confirmation status, and next steps
    """
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format.")
    
    try:
        # Check for session profile first (injected by orchestrator after auth)
        session_profile = args.get("_session_profile")
        
        # Extract required fields - use session profile if available
        policy_id = args.get("policy_id", "").strip()
        caller_name = ""
        policies = []
        
        if session_profile:
            # Get caller name from profile
            caller_name = session_profile.get("caller_name") or session_profile.get("full_name", "")
            client_id = session_profile.get("client_id")
            
            # Try to get policies from Cosmos DB first
            if client_id and not policy_id:
                cosmos_policies = _get_user_policies_from_cosmos(client_id)
                if cosmos_policies:
                    policies = cosmos_policies
                    logger.info("📋 Found %d policies from Cosmos for client %s", len(policies), client_id)
            
            # Fallback to session profile policies
            if not policies:
                demo_metadata = session_profile.get("demo_metadata", {})
                policies = demo_metadata.get("policies") or session_profile.get("policies") or []
            
            # If we have policies and no explicit policy_id, use the first auto policy or first policy
            if not policy_id and policies:
                for p in policies:
                    if p.get("policy_type") == "auto":
                        policy_id = p.get("policy_number", "")
                        break
                if not policy_id and policies:
                    policy_id = policies[0].get("policy_number", "")
                # Final fallback to client_id
                if not policy_id:
                    policy_id = session_profile.get("client_id", "")
        else:
            policy_id = (args.get("policy_id") or "").strip()
            caller_name = (args.get("caller_name") or "").strip()
        
        driver_name = (args.get("driver_name") or caller_name).strip()
        vehicle_make = (args.get("vehicle_make") or "").strip()
        vehicle_model = (args.get("vehicle_model") or "").strip()
        incident_description = (args.get("incident_description") or "").strip()
        loss_date = (args.get("loss_date") or "").strip()
        loss_location = (args.get("loss_location") or "").strip()
        
        # Validate required fields
        missing_fields = []
        if not policy_id:
            missing_fields.append("policy_id")
        if not caller_name:
            missing_fields.append("caller_name")
        if not vehicle_make or not vehicle_model:
            missing_fields.append("vehicle details")
        if not incident_description:
            missing_fields.append("incident_description")
        if not loss_date:
            missing_fields.append("loss_date")
        if not loss_location:
            missing_fields.append("loss_location")
        
        if missing_fields:
            logger.warning(
                "⚠️ FNOL missing fields | policy=%s missing=%s",
                policy_id, missing_fields
            )
            return _json(
                False,
                f"Missing required information: {', '.join(missing_fields)}. Please collect these details before filing the claim.",
                missing_fields=missing_fields
            )
        
        # Generate claim ID
        claim_id = _generate_claim_id()
        
        # Extract optional fields with defaults
        driver_relationship = args.get("driver_relationship", "policyholder")
        vehicle_year = args.get("vehicle_year", "")
        num_vehicles = args.get("num_vehicles_involved", 1)
        loss_time = args.get("loss_time", "")
        vehicle_drivable = args.get("vehicle_drivable", True)
        passengers = args.get("passengers", [])
        injuries_reported = args.get("injuries_reported", False)
        injury_details = args.get("injury_details", "")
        trip_purpose = args.get("trip_purpose", "personal")
        
        # Build claim record
        claim_record = {
            "claim_id": claim_id,
            "policy_id": policy_id,
            "status": "filed",
            "filed_at": _utc_now(),
            "caller": {
                "name": caller_name,
            },
            "driver": {
                "name": driver_name,
                "relationship": driver_relationship,
            },
            "vehicle": {
                "year": vehicle_year,
                "make": vehicle_make,
                "model": vehicle_model,
                "drivable_after_incident": vehicle_drivable,
            },
            "incident": {
                "description": incident_description,
                "date": loss_date,
                "time": loss_time,
                "location": loss_location,
                "vehicles_involved": num_vehicles,
                "trip_purpose": trip_purpose,
            },
            "passengers": passengers,
            "injuries": {
                "reported": injuries_reported,
                "details": injury_details,
            },
        }
        
        # In production, this would save to Cosmos DB
        # For now, we just log and return success
        logger.info(
            "✅ FNOL claim filed | claim=%s policy=%s caller=%s vehicle=%s %s",
            claim_id, policy_id, caller_name, vehicle_make, vehicle_model
        )
        
        # Determine next steps based on claim details
        next_steps = [
            f"Claim {claim_id} has been filed and assigned to an adjuster.",
            "You will receive a confirmation email within the hour.",
            "An adjuster will contact you within 1-2 business days.",
        ]
        
        if injuries_reported:
            next_steps.insert(1, "Our medical liaison team will reach out regarding any injury claims.")
        
        if not vehicle_drivable:
            next_steps.insert(1, "We can arrange a tow or rental vehicle if needed.")
        
        return _json(
            True,
            f"Your claim has been filed successfully. Your claim number is {claim_id}.",
            claim_id=claim_id,
            claim_record=claim_record,
            next_steps=next_steps,
            adjuster_contact_window="1-2 business days"
        )
    
    except Exception as error:
        logger.error(f"❌ Failed to record FNOL: {error}", exc_info=True)
        return _json(False, "Unable to file the claim at this time. Please try again or speak to an agent.")


class HandoffToGeneralInfoArgs(TypedDict, total=False):
    """Input schema for handoff_to_general_info_agent."""
    policy_id: Optional[str]
    caller_name: Optional[str]
    inquiry_type: str
    context: Optional[str]


async def handoff_to_general_info_agent(args: HandoffToGeneralInfoArgs) -> Dict[str, Any]:
    """
    Transfer caller to General Info Agent for non-claim inquiries.
    
    Handles billing questions, policy renewals, coverage inquiries,
    and other general insurance questions.
    
    Args:
        policy_id: Policy ID of the caller (optional)
        caller_name: Name of the caller (optional)
        inquiry_type: Type of inquiry (billing, renewal, coverage, general)
        context: Brief summary of the request
    
    Returns:
        Dict with handoff confirmation and target agent
    """
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format.")
    
    try:
        policy_id = (args.get("policy_id") or "").strip()
        caller_name = (args.get("caller_name") or "").strip()
        inquiry_type = (args.get("inquiry_type") or "general").strip().lower()
        context = (args.get("context") or "").strip()
        
        logger.info(
            "🔄 Handoff to GeneralInfoAgent | policy=%s type=%s",
            policy_id or "unknown", inquiry_type
        )
        
        # Map inquiry type to department
        department_map = {
            "billing": "Billing Department",
            "renewal": "Policy Services",
            "coverage": "Coverage Specialist",
            "general": "Customer Service",
        }
        
        target_department = department_map.get(inquiry_type, "Customer Service")
        
        return {
            "success": True,
            "handoff": True,
            "target_agent": "GeneralInfoAgent",
            "message": f"Connecting you with our {target_department}.",
            "handoff_summary": f"{inquiry_type.title()} inquiry",
            "handoff_context": {
                "policy_id": policy_id,
                "caller_name": caller_name,
                "inquiry_type": inquiry_type,
                "context": context,
                "handoff_timestamp": _utc_now(),
                "previous_agent": "FNOLAgent",
            },
            "should_interrupt_playback": True,
        }
    
    except Exception as error:
        logger.error(f"❌ Failed to handoff: {error}", exc_info=True)
        return _json(False, "Unable to transfer at this time.")


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "record_fnol",
    record_fnol_schema,
    record_fnol,
    tags={"insurance", "fnol", "claims"},
)

register_tool(
    "handoff_to_general_info_agent",
    handoff_to_general_info_agent_schema,
    handoff_to_general_info_agent,
    is_handoff=True,
    tags={"handoff", "insurance"},
)
