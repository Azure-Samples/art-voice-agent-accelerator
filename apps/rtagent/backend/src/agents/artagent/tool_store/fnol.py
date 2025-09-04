from __future__ import annotations

import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from apps.rtagent.backend.src.agents.artagent.tool_store.functions_helper import _json
from utils.ml_logging import get_logger

log = get_logger("fnol_tools_min")

# ──────────────────────────────────────────────────────────────────────────────
# Mock DBs
# ──────────────────────────────────────────────────────────────────────────────
policyholders_db: Dict[str, Dict[str, str]] = {
    "Alice Brown": {"policy_id": "POL-A10001", "zip": "60601"},
    "Amelia Johnson": {"policy_id": "POL-B20417", "zip": "60601"},
    "Carlos Rivera": {"policy_id": "POL-C88230", "zip": "77002"},
}

claims_db: List[Dict[str, Any]] = []


# ──────────────────────────────────────────────────────────────────────────────
# TypedDict models
# ──────────────────────────────────────────────────────────────────────────────
class LossLocation(TypedDict, total=False):
    street: str
    city: str
    state: str
    zipcode: str


class PassengerInfo(TypedDict, total=False):
    name: str
    relationship: str


class InjuryAssessment(TypedDict, total=False):
    injured: bool
    details: Optional[str]


class VehicleDetails(TypedDict, total=False):
    make: str
    model: str
    year: str
    policy_id: str


class ClaimIntakeFull(TypedDict, total=False):
    caller_name: str
    driver_name: str
    driver_relationship: str
    vehicle_details: VehicleDetails
    number_of_vehicles_involved: int
    incident_description: str
    loss_date: str
    loss_time: str
    loss_location: LossLocation
    vehicle_drivable: bool
    passenger_information: Optional[List[PassengerInfo]]  # ← now Optional
    injury_assessment: InjuryAssessment
    trip_purpose: str
    date_reported: str  # YYYY-MM-DD (auto-filled)
    location_description: Optional[str]


class EscalateArgs(TypedDict):
    reason: str
    caller_name: str
    policy_id: str


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _new_claim_id() -> str:
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"CLA-{datetime.utcnow().year}-{rand}"


_REQUIRED_SLOTS = [
    "caller_name",
    "driver_name",
    "driver_relationship",
    "vehicle_details.make",
    "vehicle_details.model",
    "vehicle_details.year",
    "vehicle_details.policy_id",
    "number_of_vehicles_involved",
    "incident_description",
    "loss_date",
    "loss_time",
    "loss_location.street",
    "loss_location.city",
    "loss_location.state",
    "loss_location.zipcode",
    "vehicle_drivable",
    "injury_assessment.injured",
    "injury_assessment.details",
    "trip_purpose",
]


def _validate(data: ClaimIntakeFull) -> tuple[bool, str]:
    """Return (ok, message).  Message lists missing fields if any."""
    missing: List[str] = []

    # Field-presence walk
    for field in _REQUIRED_SLOTS:
        ptr = data
        for part in field.split("."):
            if isinstance(ptr, dict) and part in ptr:
                ptr = ptr[part]
            else:
                missing.append(field)
                break

    if "passenger_information" not in data or data["passenger_information"] in (
        None,
        [],
    ):
        data["passenger_information"] = []
    else:
        for i, pax in enumerate(data["passenger_information"]):
            if not pax.get("name") or not pax.get("relationship"):
                missing.append(f"passenger_information[{i}]")

    if missing:
        return False, "Missing: " + ", ".join(sorted(set(missing)))

    return True, ""


async def record_fnol(args: ClaimIntakeFull) -> Dict[str, Any]:
    """Store the claim if validation passes; else enumerate missing fields."""
    # Input type validation to prevent 400 errors
    if not isinstance(args, dict):
        log.error("Invalid args type: %s. Expected dict.", type(args))
        return {
            "claim_success": False,
            "missing_data": "Invalid request format. Please provide claim details as a structured object.",
        }

    try:
        args.setdefault("date_reported", datetime.now(timezone.utc).date().isoformat())

        ok, msg = _validate(args)
        if not ok:
            return {
                "claim_success": False,
                "missing_data": f"{msg}.",
            }

        claim_id = _new_claim_id()
        claims_db.append({**args, "claim_id": claim_id, "status": "OPEN"})
        log.info(
            "📄 FNOL recorded (%s) for %s", claim_id, args.get("caller_name", "unknown")
        )

        return {
            "claim_success": True,
            "claim_id": claim_id,
            "claim_data": {**args},
        }
    except Exception as exc:
        # Catch all exceptions to prevent 400 errors
        log.error("FNOL recording failed: %s", exc, exc_info=True)
        return {
            "claim_success": False,
            "missing_data": "Technical error occurred. Please try again or contact support.",
        }
