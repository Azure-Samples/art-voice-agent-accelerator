from typing import Any, Callable, Dict, List

from apps.rtagent.backend.src.agents.artagent.tool_store.auth import authenticate_caller
from apps.rtagent.backend.src.agents.artagent.tool_store.emergency import escalate_emergency
from apps.rtagent.backend.src.agents.artagent.tool_store.fnol import record_fnol
from apps.rtagent.backend.src.agents.artagent.tool_store.handoffs import (
    escalate_human,
    handoff_claim_agent,
    handoff_general_agent,
)
from apps.rtagent.backend.src.agents.artagent.tool_store.policies import (
    find_information_for_policy,
)
from apps.rtagent.backend.src.agents.artagent.tool_store.voicemail import (
    detect_voicemail_and_end_call,
)
from utils.ml_logging import get_logger

log = get_logger("tools_helper")

from apps.rtagent.backend.src.agents.artagent.tool_store.schemas import (
    authenticate_caller_schema,
    escalate_emergency_schema,
    escalate_human_schema,
    find_information_schema,
    handoff_claim_schema,
    handoff_general_schema,
    record_fnol_schema,
    detect_voicemail_schema,
)

function_mapping: Dict[str, Callable[..., Any]] = {
    "record_fnol": record_fnol,
    "escalate_emergency": escalate_emergency,
    "authenticate_caller": authenticate_caller,
    "handoff_general_agent": handoff_general_agent,
    "escalate_human": escalate_human,
    "handoff_claim_agent": handoff_claim_agent,
    "find_information_for_policy": find_information_for_policy,
    "detect_voicemail_and_end_call": detect_voicemail_and_end_call,
}


available_tools: List[Dict[str, Any]] = [
    {"type": "function", "function": record_fnol_schema},
    {"type": "function", "function": authenticate_caller_schema},
    {"type": "function", "function": escalate_emergency_schema},
    {"type": "function", "function": handoff_general_schema},
    {"type": "function", "function": escalate_human_schema},
    {"type": "function", "function": handoff_claim_schema},
    {"type": "function", "function": find_information_schema},
    {"type": "function", "function": detect_voicemail_schema},
]

TOOL_REGISTRY: dict[str, dict] = {t["function"]["name"]: t for t in available_tools}
