"""
tools.py

Defines the function-calling tools exposed to the Insurance Voice Agent.

Tools:
- record_fnol
- authenticate_caller
- escalate_emergency
- handoff_general_agent
- handoff_claim_agent
- escalate_human
- detect_voicemail_and_end_call
"""

from __future__ import annotations

from typing import Any, Dict, List

record_fnol_schema: Dict[str, Any] = {
    "name": "record_fnol",
    "description": (
        "Create a First-Notice-of-Loss (FNOL) claim in the insurance system. "
        "This tool collects all required details about the incident, vehicle, and involved parties, "
        "and returns a structured response indicating claim success, claim ID, and any missing data. "
        "Use this to initiate a new claim after a loss event. "
        "Returns: {claim_success: bool, claim_id?: str, missing_data?: str}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "caller_name": {
                "type": "string",
                "description": "Full legal name of the caller reporting the loss.",
            },
            "driver_name": {
                "type": "string",
                "description": "Name of the driver involved in the incident.",
            },
            "driver_relationship": {
                "type": "string",
                "description": "Relationship of the driver to the policyholder (e.g., self, spouse, child, other).",
            },
            "vehicle_details": {
                "type": "object",
                "description": "Detailed information about the vehicle involved in the incident.",
                "properties": {
                    "make": {
                        "type": "string",
                        "description": "Vehicle manufacturer (e.g., Toyota).",
                    },
                    "model": {
                        "type": "string",
                        "description": "Vehicle model (e.g., Camry).",
                    },
                    "year": {
                        "type": "string",
                        "description": "Year of manufacture (e.g., 2022).",
                    },
                    "policy_id": {
                        "type": "string",
                        "description": "Unique policy identifier for the vehicle.",
                    },
                },
                "required": ["make", "model", "year", "policy_id"],
            },
            "number_of_vehicles_involved": {
                "type": "integer",
                "description": "Total number of vehicles involved in the incident (including caller's vehicle).",
            },
            "incident_description": {
                "type": "string",
                "description": "Brief summary of the incident (e.g., collision, theft, vandalism, fire, etc.).",
            },
            "loss_date": {
                "type": "string",
                "description": "Date the loss occurred in YYYY-MM-DD format.",
            },
            "loss_time": {
                "type": "string",
                "description": "Approximate time of loss in HH:MM (24-hour) format, or blank if unknown.",
            },
            "loss_location": {
                "type": "object",
                "description": "Street-level location where the loss occurred.",
                "properties": {
                    "street": {
                        "type": "string",
                        "description": "Street address of the incident.",
                    },
                    "city": {
                        "type": "string",
                        "description": "City where the incident occurred.",
                    },
                    "state": {
                        "type": "string",
                        "description": "State abbreviation (e.g., CA, NY).",
                    },
                    "zipcode": {"type": "string", "description": "5-digit ZIP code."},
                },
                "required": ["street", "city", "state", "zipcode"],
            },
            "vehicle_drivable": {
                "type": "boolean",
                "description": "Indicates whether the vehicle was drivable after the incident.",
            },
            "passenger_information": {
                "type": ["array", "null"],
                "nullable": True,
                "description": (
                    "List of passengers in the vehicle at the time of the incident. "
                    "Each passenger includes name and relationship to the policyholder. "
                    "Send null or omit if caller confirms no passengers."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Passenger's full name.",
                        },
                        "relationship": {
                            "type": "string",
                            "description": "Relationship to policyholder.",
                        },
                    },
                    "required": ["name", "relationship"],
                },
            },
            "injury_assessment": {
                "type": "object",
                "description": "Assessment of any injuries sustained in the incident.",
                "properties": {
                    "injured": {
                        "type": "boolean",
                        "description": "Was anyone injured in the incident?",
                    },
                    "details": {
                        "type": "string",
                        "description": "Details of injury, or 'None' if no injuries.",
                    },
                },
                "required": ["injured", "details"],
            },
            "trip_purpose": {
                "type": "string",
                "enum": ["commuting", "work", "personal", "other"],
                "description": "Purpose of the trip at the time of the incident.",
            },
            "date_reported": {
                "type": "string",
                "description": "Date the claim is reported (YYYY-MM-DD). Optional—auto-filled if omitted.",
            },
            "location_description": {
                "type": "string",
                "description": "Optional free-text notes about the location or context.",
            },
        },
        "required": [
            "caller_name",
            "driver_name",
            "driver_relationship",
            "vehicle_details",
            "number_of_vehicles_involved",
            "incident_description",
            "loss_date",
            "loss_time",
            "loss_location",
            "vehicle_drivable",
            "injury_assessment",
            "trip_purpose",
        ],
        "additionalProperties": False,
    },
}


authenticate_caller_schema: Dict[str, Any] = {
    "name": "authenticate_caller",
    "description": (
        "Verify the caller’s identity by matching their full legal name, ZIP code, "
        "and the last 4 digits of a key identifier (SSN, policy number, claim "
        "number, or phone number). "
        "Returns: {authenticated: bool, message: str, policy_id: str | null, "
        "caller_name: str | null, attempt: int, intent: str | null, "
        "claim_intent: str | null}. "
        "At least one of ZIP code or last‑4 must be provided."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "full_name": {
                "type": "string",
                "description": "Caller’s full legal name (e.g., 'Alice Brown').",
            },
            "zip_code": {
                "type": "string",
                "description": "Caller’s 5‑digit ZIP code. May be blank if last4_id is provided.",
            },
            "last4_id": {
                "type": "string",
                "description": (
                    "Last 4 digits of SSN, policy number, claim number, or phone "
                    "number. May be blank if zip_code is provided."
                ),
            },
            "intent": {
                "type": "string",
                "enum": ["claims", "general"],
                "description": "High‑level reason for the call.",
            },
            "claim_intent": {
                "type": ["string", "null"],
                "enum": ["new_claim", "existing_claim", "unknown", None],
                "description": "Sub‑intent when intent == 'claims'. Null for general inquiries.",
            },
            "attempt": {
                "type": "integer",
                "minimum": 1,
                "description": "Nth authentication attempt within the current call (starts at 1).",
            },
        },
        "required": [
            "full_name",
            "zip_code",
            "last4_id",
            "intent",
            "claim_intent",
        ],
        "additionalProperties": False,
    },
}

escalate_emergency_schema: Dict[str, Any] = {
    "name": "escalate_emergency",
    "description": (
        "Immediately escalate an urgent or life-threatening situation (such as injury, fire, or medical crisis) to emergency dispatch. "
        "Use this tool when the caller reports a scenario requiring immediate emergency response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Concise reason for escalation (e.g., 'injury', 'fire', 'medical emergency').",
            },
            "caller_name": {
                "type": "string",
                "description": "Full legal name of the caller.",
            },
            "policy_id": {
                "type": "string",
                "description": "Unique policy identifier for the caller.",
            },
        },
        "required": ["reason", "caller_name", "policy_id"],
        "additionalProperties": False,
    },
}

handoff_general_schema: Dict[str, Any] = {
    "name": "handoff_general_agent",
    "description": (
        "Route the call to the General Insurance Questions AI agent when the "
        "caller requests broad information not tied to a specific claim."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "caller_name": {
                "type": "string",
                "description": "Full legal name of the caller.",
            },
            "topic": {
                "type": "string",
                "description": "Short keyword describing the caller’s question "
                "(e.g., 'coverage', 'billing').",
            },
        },
        "required": ["caller_name", "topic"],
        "additionalProperties": False,
    },
}

handoff_claim_schema: Dict[str, Any] = {
    "name": "handoff_claim_agent",
    "description": (
        "Route the call to the Claims Intake AI agent when the caller needs to "
        "start or update a claim."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "caller_name": {
                "type": "string",
                "description": "Full legal name of the caller.",
            },
            "policy_id": {
                "type": "string",
                "description": "Unique policy identifier for the caller.",
            },
            "claim_intent": {
                "type": "string",
                "description": (
                    "Brief intent string (e.g., 'new_claim', 'update_claim')."
                ),
            },
        },
        "required": ["caller_name", "policy_id", "claim_intent"],
        "additionalProperties": False,
    },
}

find_information_schema: Dict[str, Any] = {
    "name": "find_information_for_policy",
    "description": (
        "Retrieve grounded, caller-specific details from a policy record. "
        "Use this tool for any question that depends on the caller’s actual "
        "coverage (deductible amount, roadside assistance, glass coverage, "
        "rental reimbursement, etc.)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "policy_id": {
                "type": "string",
                "description": "Unique policy identifier (e.g., 'POL-A10001').",
            },
            "question": {
                "type": "string",
                "description": "Exact caller question to ground (e.g., "
                "'Do I have roadside assistance?').",
            },
        },
        "required": ["policy_id", "question"],
        "additionalProperties": False,
    },
}


escalate_human_schema: Dict[str, Any] = {
    "name": "escalate_human",
    "description": (
        "Escalate the call to a live human adjuster for non-emergency but complex scenarios. "
        "Use this tool for backend errors, repeated validation failures, suspected fraud, or caller requests for human assistance."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "route_reason": {
                "type": "string",
                "description": "Reason for escalation to a human adjuster (e.g., 'fraud flag', 'validation loop', 'caller request').",
            },
            "caller_name": {
                "type": "string",
                "description": "Full legal name of the caller.",
            },
            "policy_id": {
                "type": "string",
                "description": "Unique policy identifier for the caller.",
            },
        },
        "required": ["route_reason", "caller_name", "policy_id"],
        "additionalProperties": False,
    },
}


detect_voicemail_schema: Dict[str, Any] = {
    "name": "detect_voicemail_and_end_call",
    "description": (
        "Use when you are confident the caller is a voicemail or answering machine. "
        "Provide the cues that informed the decision so the system can gracefully terminate the call."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "voicemail_cues": {
                "type": "string",
                "description": (
                    "Brief note describing the audio/text cues indicating voicemail "
                    "(e.g., 'automated greeting', 'beep', 'no live response')."
                ),
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Optional confidence score between 0 and 1.",
            },
        },
        "required": ["voicemail_cues"],
        "additionalProperties": False,
    },
}
