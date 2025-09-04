from __future__ import annotations

"""
Policy-lookup helper for XYMZ Insurance’s ARTAgent.

Given a `policy_id` and a free-form `question`, returns a grounded,
structured answer drawn from an in-memory mock database.

Usage pattern (LLM function-calling):

    {
      "policy_id": "POL-A10001",
      "question": "Do I have roadside assistance?"
    }

The helper performs *very* light intent matching (keyword scan) so it can
demonstrate grounding; in production you’d replace this with a proper
retriever or vector search.
"""

from typing import Dict, List, Optional, TypedDict

from rapidfuzz import fuzz, process

from utils.ml_logging import get_logger

logger = get_logger("policy_lookup")

# ────────────────────────────────────────────────────────────────
# Mock database
# ────────────────────────────────────────────────────────────────
policy_db: Dict[str, Dict[str, str | int | bool]] = {
    "POL-A10001": {
        "policyholder": "Alice Brown",
        "zip": "60601",
        "deductible": 500,
        "coverage": "comprehensive",
        "roadside_assistance": True,
        "glass_coverage": True,
        "rental_reimbursement": 40,
        "tow_limit_miles": 100,
    },
    "POL-B20417": {
        "policyholder": "Amelia Johnson",
        "zip": "60601",
        "deductible": 250,
        "coverage": "liability_only",
        "roadside_assistance": False,
        "glass_coverage": False,
        "rental_reimbursement": 0,
        "tow_limit_miles": 0,
    },
    "POL-C88230": {
        "policyholder": "Carlos Rivera",
        "zip": "60601",
        "deductible": 1_000,
        "coverage": "collision",
        "roadside_assistance": True,
        "glass_coverage": False,
        "rental_reimbursement": 30,
        "tow_limit_miles": 50,
    },
}

# ────────────────────────────────────────────────────────────────
# Synonyms and canonical keys
# ────────────────────────────────────────────────────────────────
ATTR_MAP: Dict[str, str] = {
    "deductible": "deductible",
    "excess": "deductible",
    "roadside": "roadside_assistance",
    "tow": "roadside_assistance",
    "towing": "roadside_assistance",
    "breakdown": "roadside_assistance",
    "glass": "glass_coverage",
    "windshield": "glass_coverage",
    "windows": "glass_coverage",
    "rental": "rental_reimbursement",
    "loaner": "rental_reimbursement",
    "courtesy car": "rental_reimbursement",
    "coverage": "coverage",
}
_CANONICAL_KEYS: List[str] = [
    "deductible",
    "roadside",
    "glass",
    "rental",
    "coverage",
]


# ────────────────────────────────────────────────────────────────
# Payload/return typing
# ────────────────────────────────────────────────────────────────
class PolicyQueryArgs(TypedDict):
    policy_id: str
    question: str


class PolicyQueryResult(TypedDict):
    found: bool
    answer: str
    policy_id: str
    caller_name: Optional[str]
    raw_data: Optional[Dict[str, str | int | bool]]


# ────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────
def _best_attr(question: str) -> Optional[str]:
    q = question.lower()
    for syn, canon in ATTR_MAP.items():
        if syn in q:
            return canon
    match, score = process.extractOne(
        q, _CANONICAL_KEYS, scorer=fuzz.WRatio, score_cutoff=80
    )
    return match if score else None


def _render(rec: Dict[str, str | int | bool], key: str) -> Optional[str]:
    if key == "deductible":
        return f"Your deductible is **${rec['deductible']:,}**."
    if key == "roadside_assistance":
        miles = rec["tow_limit_miles"]
        return (
            f"Yes — covered for up to {miles} miles of towing."
            if rec[key]
            else "Roadside assistance is not included in your policy."
        )
    if key == "glass_coverage":
        return (
            "Yes, full glass coverage with no deductible."
            if rec[key]
            else "You do not have separate glass coverage."
        )
    if key == "rental_reimbursement":
        daily = rec[key]
        return (
            f"Your policy reimburses up to **${daily}/day** for a rental car."
            if daily
            else "Rental-car reimbursement is not included."
        )
    if key == "coverage":
        return f"Your primary coverage type is **{str(rec[key]).title()}**."
    return None


async def _semantic_search(question: str, rec: Dict[str, str | int | bool]) -> str:
    logger.debug("Semantic lookup stub - Q=%s", question)
    return (
        "I don’t have that information on file. "
        "Let me transfer you to a human agent for assistance."
    )


# ────────────────────────────────────────────────────────────────
# Public entry-point
# ────────────────────────────────────────────────────────────────
async def find_information_for_policy(
    args: PolicyQueryArgs,
) -> PolicyQueryResult:
    """
    This function is wrapped to prevent all exceptions
    that could cause 400 errors and conversation corruption.
    """
    try:
        # Input validation without raising exceptions
        if not isinstance(args, dict):
            logger.error("Invalid args type: %s. Expected dict.", type(args))
            return {
                "found": False,
                "answer": "Invalid request format. Please try again.",
                "policy_id": "unknown",
                "caller_name": None,
                "raw_data": None,
            }

        pid = args.get("policy_id", "").strip().upper() if args.get("policy_id") else ""
        q = args.get("question", "").strip() if args.get("question") else ""

        if not pid:
            logger.error("policy_id is required and cannot be empty")
            return {
                "found": False,
                "answer": "Policy ID is required. Please provide your policy number.",
                "policy_id": "",
                "caller_name": None,
                "raw_data": None,
            }

        if not q:
            logger.error("question is required and cannot be empty")
            return {
                "found": False,
                "answer": "Please ask a specific question about your policy.",
                "policy_id": pid,
                "caller_name": None,
                "raw_data": None,
            }

        rec = policy_db.get(pid)
        if rec is None:
            logger.warning("Policy not found: %s", pid)
            return {
                "found": False,
                "answer": f"Policy '{pid}' not found. Please verify your policy number.",
                "policy_id": pid,
                "caller_name": None,
                "raw_data": None,
            }

        key = _best_attr(q)
        answer = _render(rec, key) if key else None
        if answer is None:
            answer = await _semantic_search(q, rec)

        logger.info("Answer for %s: %s", pid, answer)
        return {
            "found": True,
            "answer": answer,
            "policy_id": pid,
            "caller_name": rec["policyholder"],
            "raw_data": rec,
        }

    except Exception as exc:
        # Catch all exceptions to prevent 400 errors
        logger.error(
            "Policy query failed: policy_id=%s, question=%s, error=%s",
            args.get("policy_id", "unknown")
            if isinstance(args, dict)
            else "invalid_args",
            args.get("question", "unknown")[:100]
            if isinstance(args, dict)
            else "invalid_args",
            exc,
            exc_info=True,
        )
        return {
            "found": False,
            "answer": "I'm experiencing technical difficulties. Please try again or contact customer service for assistance.",
            "policy_id": args.get("policy_id", "unknown")
            if isinstance(args, dict)
            else "unknown",
            "caller_name": None,
            "raw_data": None,
        }
