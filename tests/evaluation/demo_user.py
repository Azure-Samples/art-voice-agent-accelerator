"""
Demo User Helper for Evaluations
=================================

Creates demo user profiles for evaluation scenarios using the demo_env API functions.
This ensures tools like get_user_profile, verify_client_identity have realistic data.

Usage in scenario YAML:
    demo_user:
      full_name: "Sarah Johnson"
      email: "sarah.johnson@example.com"
      scenario: banking  # or insurance
      # Optional banking-specific:
      phone_number: "+18885551234"

The demo user will be created before the scenario runs and cleaned up after.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from random import Random
from typing import Any

from utils.ml_logging import get_logger

logger = get_logger(__name__)


# Lazy imports to avoid circular dependencies
_demo_env_loaded = False
_DemoUserRequest = None
_DemoUserResponse = None
_DemoUserProfile = None
_build_profile = None
_build_transactions = None
_build_interaction_plan = None
_build_insurance_profile = None
_build_policies = None
_build_claims = None
_persist_demo_user = None


def _lazy_load_demo_env():
    """Lazy load demo_env functions to avoid import issues."""
    global _demo_env_loaded, _DemoUserRequest, _DemoUserResponse, _DemoUserProfile
    global _build_profile, _build_transactions, _build_interaction_plan
    global _build_insurance_profile, _build_policies, _build_claims, _persist_demo_user
    
    if _demo_env_loaded:
        return True
    
    try:
        from apps.artagent.backend.api.v1.endpoints.demo_env import (
            DemoUserRequest as _Req,
            DemoUserResponse as _Resp,
            DemoUserProfile as _Prof,
            _build_profile as _bp,
            _build_transactions as _bt,
            _build_interaction_plan as _bip,
            _build_insurance_profile as _binsP,
            _build_policies as _bpol,
            _build_claims as _bc,
            _persist_demo_user as _pdu,
        )
        _DemoUserRequest = _Req
        _DemoUserResponse = _Resp
        _DemoUserProfile = _Prof
        _build_profile = _bp
        _build_transactions = _bt
        _build_interaction_plan = _bip
        _build_insurance_profile = _binsP
        _build_policies = _bpol
        _build_claims = _bc
        _persist_demo_user = _pdu
        _demo_env_loaded = True
        return True
    except ImportError as e:
        logger.warning(f"Could not import demo_env functions: {e}")
        return False


def create_demo_user_sync(
    full_name: str = "Sarah Johnson",
    email: str = "sarah.johnson@example.com",
    phone_number: str | None = None,
    scenario: str = "banking",
    session_id: str | None = None,
    seed: int | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """
    Create a demo user profile synchronously.
    
    Args:
        full_name: User's full name
        email: User's email address
        phone_number: Optional phone number in E.164 format
        scenario: "banking" or "insurance"
        session_id: Optional session ID to associate with
        seed: Optional random seed for reproducible profiles
        **kwargs: Additional fields for DemoUserRequest
    
    Returns:
        Dict with demo user data (profile, transactions, etc.) or None if failed
    """
    if not _lazy_load_demo_env():
        logger.error("Demo env functions not available")
        return None
    
    # Create RNG with optional seed for reproducibility
    rng = Random(seed) if seed is not None else Random()
    anchor = datetime.now(tz=UTC)
    expires_at = anchor + timedelta(hours=24)
    
    # Build the request payload
    payload = _DemoUserRequest(
        full_name=full_name,
        email=email,
        phone_number=phone_number,
        session_id=session_id,
        scenario=scenario,
        **kwargs,
    )
    
    try:
        if scenario == "insurance":
            profile = _build_insurance_profile(payload, rng, anchor)
            policies = _build_policies(profile.client_id, profile.full_name, rng, anchor)
            claims = _build_claims(
                profile.client_id,
                profile.full_name,
                policies,
                rng,
                anchor,
                is_cc_rep=(kwargs.get("insurance_role") == "cc_rep"),
                cc_company_name=kwargs.get("insurance_company_name"),
                test_scenario=kwargs.get("test_scenario"),
            )
            transactions = []
            
            response_data = {
                "entry_id": f"demo-entry-{rng.randint(100000, 999999)}",
                "expires_at": expires_at.isoformat(),
                "profile": profile.model_dump(mode='json'),
                "transactions": transactions,
                "interaction_plan": _build_interaction_plan(payload, rng).model_dump(mode='json'),
                "session_id": session_id,
                "scenario": "insurance",
                "policies": [p.model_dump(mode='json') for p in policies],
                "claims": [c.model_dump(mode='json') for c in claims],
            }
        else:
            # Banking scenario
            profile = _build_profile(payload, rng, anchor)
            
            # Extract card last4 from profile for transaction generation
            bank_profile = profile.customer_intelligence.get("bank_profile", {})
            cards = bank_profile.get("cards", [])
            card_last4 = cards[0].get("last4", "4242") if cards else f"{rng.randint(1000, 9999)}"
            
            transactions = _build_transactions(profile.client_id, rng, anchor, card_last4=card_last4)
            
            response_data = {
                "entry_id": f"demo-entry-{rng.randint(100000, 999999)}",
                "expires_at": expires_at.isoformat(),
                "profile": profile.model_dump(mode='json'),
                "transactions": [t.model_dump(mode='json') for t in transactions],
                "interaction_plan": _build_interaction_plan(payload, rng).model_dump(mode='json'),
                "session_id": session_id,
                "scenario": "banking",
                "policies": None,
                "claims": None,
            }
        
        logger.info(
            f"Created demo user | name={full_name} scenario={scenario} "
            f"client_id={profile.client_id}"
        )
        
        return response_data
        
    except Exception as e:
        logger.exception(f"Failed to create demo user: {e}")
        return None


async def create_demo_user(
    full_name: str = "Sarah Johnson",
    email: str = "sarah.johnson@example.com",
    phone_number: str | None = None,
    scenario: str = "banking",
    session_id: str | None = None,
    seed: int | None = None,
    persist: bool = True,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """
    Create a demo user profile (async version with optional persistence).
    
    Args:
        full_name: User's full name
        email: User's email address
        phone_number: Optional phone number in E.164 format
        scenario: "banking" or "insurance"
        session_id: Optional session ID to associate with
        seed: Optional random seed for reproducible profiles
        persist: Whether to persist to CosmosDB (default True)
        **kwargs: Additional fields for DemoUserRequest
    
    Returns:
        Dict with demo user data or None if failed
    """
    # Create the user synchronously (pure CPU work)
    response_data = create_demo_user_sync(
        full_name=full_name,
        email=email,
        phone_number=phone_number,
        scenario=scenario,
        session_id=session_id,
        seed=seed,
        **kwargs,
    )
    
    if response_data is None:
        return None
    
    # Optionally persist to database
    if persist and _persist_demo_user is not None:
        try:
            # Reconstruct response object for persistence
            response = _DemoUserResponse.model_validate(response_data)
            await _persist_demo_user(response)
            logger.debug(f"Persisted demo user to database: {response.profile.client_id}")
        except Exception as e:
            logger.warning(f"Failed to persist demo user (non-fatal): {e}")
    
    return response_data


def extract_user_context(demo_data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract relevant context from demo user data for use in evaluations.
    
    This creates a dict that can be merged into the scenario's context/metadata
    so that tools like get_user_profile and verify_client_identity can work.
    
    Args:
        demo_data: Demo user response data from create_demo_user
    
    Returns:
        Dict with context variables for evaluation
    """
    if not demo_data:
        return {}
    
    profile = demo_data.get("profile", {})
    
    context = {
        # Core identifiers
        "demo_client_id": profile.get("client_id"),
        "demo_full_name": profile.get("full_name"),
        "demo_email": profile.get("email"),
        "demo_phone": profile.get("phone_number"),
        
        # Verification codes (for MFA testing)
        "demo_verification_codes": profile.get("verification_codes", {}),
        
        # SSN last 4 for identity verification
        "demo_ssn_last4": profile.get("company_code_last4"),
        
        # Institution info
        "demo_institution": profile.get("institution_name"),
        
        # Full profile for tools that need it
        "demo_user_profile": profile,
        
        # Transactions (banking)
        "demo_transactions": demo_data.get("transactions", []),
        
        # Insurance data
        "demo_policies": demo_data.get("policies"),
        "demo_claims": demo_data.get("claims"),
        
        # Scenario type
        "demo_scenario": demo_data.get("scenario", "banking"),
    }
    
    # Add card info if banking
    if profile.get("customer_intelligence"):
        bank_profile = profile["customer_intelligence"].get("bank_profile", {})
        cards = bank_profile.get("cards", [])
        if cards:
            context["demo_cards"] = cards
            context["demo_primary_card_last4"] = cards[0].get("last4")
    
    return context


def get_demo_user_prompt_context(demo_data: dict[str, Any]) -> str:
    """
    Generate prompt context about the demo user for agent system prompts.
    
    This can be injected into prompts so agents know the user's identity.
    
    Args:
        demo_data: Demo user response data
    
    Returns:
        String with user context for prompts
    """
    if not demo_data:
        return ""
    
    profile = demo_data.get("profile", {})
    scenario = demo_data.get("scenario", "banking")
    
    lines = [
        f"Current caller: {profile.get('full_name', 'Unknown')}",
        f"Client ID: {profile.get('client_id', 'Unknown')}",
        f"Relationship tier: {profile.get('relationship_tier', 'Standard')}",
        f"Institution: {profile.get('institution_name', 'Unknown')}",
    ]
    
    if scenario == "banking":
        bank_profile = profile.get("customer_intelligence", {}).get("bank_profile", {})
        cards = bank_profile.get("cards", [])
        if cards:
            card_names = [c.get("name", "Card") for c in cards]
            lines.append(f"Cards on file: {', '.join(card_names)}")
    
    elif scenario == "insurance":
        policies = demo_data.get("policies", [])
        if policies:
            policy_types = [p.get("policy_type", "policy") for p in policies]
            lines.append(f"Policies: {', '.join(policy_types)}")
    
    return "\n".join(lines)


__all__ = [
    "create_demo_user",
    "create_demo_user_sync",
    "extract_user_context",
    "get_demo_user_prompt_context",
]
