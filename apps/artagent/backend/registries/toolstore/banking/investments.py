"""
Investment and Retirement Planning Tools
=========================================

Tools for 401(k) rollovers, retirement guidance, direct deposit setup,
and tax impact calculations for the Investment Advisor agent.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

# Import centralized constants (local import)
from .constants import (
    INSTITUTION_CONFIG,
    TAX_WITHHOLDING_INDIRECT_ROLLOVER,
    EARLY_WITHDRAWAL_PENALTY,
    ESTIMATED_TAX_BRACKET,
    ROLLOVER_OPTIONS,
)

logger = get_logger("agents.tools.investments")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

get_account_routing_info_schema: dict[str, Any] = {
    "name": "get_account_routing_info",
    "description": (
        "Retrieve account and routing numbers for direct deposit setup. "
        "Returns primary checking account details needed for employer payroll forms."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
        },
        "required": ["client_id"],
    },
}

get_401k_details_schema: dict[str, Any] = {
    "name": "get_401k_details",
    "description": (
        "Retrieve customer's 401(k) and retirement account details including balances, "
        "contribution rates, employer match, and vesting status."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
        },
        "required": ["client_id"],
    },
}

get_retirement_accounts_schema: dict[str, Any] = {
    "name": "get_retirement_accounts",
    "description": (
        "Get summary of all retirement accounts (401k, IRA, Roth IRA) for the customer. "
        "Includes current and previous employer plans."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
        },
        "required": ["client_id"],
    },
}

get_rollover_options_schema: dict[str, Any] = {
    "name": "get_rollover_options",
    "description": (
        "Present 401(k) rollover options with pros/cons for handling a previous employer's plan. "
        "Options include: leave in old plan, roll to new 401k, roll to IRA, or cash out."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "previous_employer": {"type": "string", "description": "Name of previous employer (optional)"},
        },
        "required": ["client_id"],
    },
}

calculate_tax_impact_schema: dict[str, Any] = {
    "name": "calculate_tax_impact",
    "description": (
        "Calculate tax implications of different 401(k) rollover strategies. "
        "Covers direct rollover, indirect rollover, Roth conversion, and cash out scenarios."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Customer identifier"},
            "rollover_type": {
                "type": "string",
                "enum": ["direct_rollover", "indirect_rollover", "roth_conversion", "cash_out"],
                "description": "Type of rollover to calculate taxes for",
            },
            "amount": {"type": "number", "description": "401(k) balance amount (optional)"},
        },
        "required": ["client_id", "rollover_type"],
    },
}

search_rollover_guidance_schema: dict[str, Any] = {
    "name": "search_rollover_guidance",
    "description": (
        "Search knowledge base for IRS rules, rollover guidance, and retirement planning information. "
        "Use for questions about contribution limits, early withdrawal penalties, RMDs, etc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Question about retirement rules or guidance"},
            "topic": {
                "type": "string",
                "enum": ["rollover", "contribution_limits", "early_withdrawal", "rmd", "roth_conversion", "general"],
                "description": "Topic category for the search",
            },
        },
        "required": ["query"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# COSMOS DB HELPERS - Import from banking.py for consistency
# ═══════════════════════════════════════════════════════════════════════════════

# Import shared Cosmos helpers from banking.py to ensure consistent DB access
from apps.artagent.backend.registries.toolstore.banking.banking import (
    _lookup_user_by_client_id,
    _sanitize_for_json,
)


def _json(
    success: bool,
    message: str,
    **extras: Any,
) -> Dict[str, Any]:
    """Helper to build consistent JSON responses."""
    result = {"success": success, "message": message}
    result.update(extras)
    return result


# ═══════════════════════════════════════════════════════════════════
# ACCOUNT & DIRECT DEPOSIT TOOLS
# ═══════════════════════════════════════════════════════════════════


class GetAccountRoutingInfoArgs(TypedDict, total=False):
    """Input schema for get_account_routing_info."""
    client_id: str


async def get_account_routing_info(args: GetAccountRoutingInfoArgs) -> Dict[str, Any]:
    """
    Retrieve account and routing numbers for direct deposit setup.
    
    Returns primary checking account details needed for employer direct deposit forms.
    Customer can use this information to set up payroll with new employer.
    
    Args:
        client_id: Unique customer identifier
    
    Returns:
        Dict with account_number_last4, routing_number, account_type, and bank details
    """
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format.")
    
    try:
        client_id = (args.get("client_id") or "").strip()
        if not client_id:
            return _json(False, "client_id is required.")
        
        logger.info("🏦 Fetching account routing info | client_id=%s", client_id)
        
        # First check if session profile was injected by orchestrator
        customer = args.get("_session_profile")
        if customer:
            logger.info("📋 Using session profile for routing info: %s", client_id)
        else:
            # Fallback: Fetch customer profile from Cosmos DB
            customer = await _lookup_user_by_client_id(client_id)
        
        if not customer:
            logger.warning(f"❌ Customer not found: {client_id}")
            return _json(False, "Customer profile not found.")
        
        # Extract bank profile data
        bank_profile = customer.get("customer_intelligence", {}).get("bank_profile", {})
        routing = bank_profile.get("routing_number", INSTITUTION_CONFIG.routing_number)
        acct_last4 = bank_profile.get("account_number_last4", "****")
        acct_id = bank_profile.get("primaryCheckingAccountId", "unknown")
        
        logger.info(
            "✅ Account info retrieved | client=%s acct=****%s routing=%s",
            client_id, acct_last4, routing
        )
        
        return _json(
            True,
            "Retrieved account and routing information for direct deposit.",
            account_number_last4=acct_last4,
            routing_number=routing,
            account_id=acct_id,
            account_type="checking",
            bank_name=INSTITUTION_CONFIG.name,
            swift_code=INSTITUTION_CONFIG.swift_code,
            note="Provide these details to your employer for direct deposit setup."
        )
    
    except Exception as error:
        logger.error(f"❌ Failed to retrieve account routing info: {error}", exc_info=True)
        return _json(False, "Unable to retrieve account information at this time.")


# ═══════════════════════════════════════════════════════════════════
# 401(K) & RETIREMENT TOOLS
# ═══════════════════════════════════════════════════════════════════


class Get401kDetailsArgs(TypedDict, total=False):
    """Input schema for get_401k_details."""
    client_id: str


async def get_401k_details(args: Get401kDetailsArgs) -> Dict[str, Any]:
    """
    Retrieve customer's current 401(k) details and retirement accounts.
    
    Returns information about current employer 401(k), previous employer 401(k)s,
    IRAs, contribution rates, employer match, and vesting status.
    
    Args:
        client_id: Unique customer identifier
    
    Returns:
        Dict with retirement account details, balances, contributions, and rollover opportunities
    """
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format.")
    
    try:
        client_id = (args.get("client_id") or "").strip()
        if not client_id:
            return _json(False, "client_id is required.")
        
        logger.info("💼 Fetching 401(k) details | client_id=%s", client_id)
        
        # First check if session profile was injected by orchestrator (avoids redundant Cosmos lookups)
        customer = args.get("_session_profile")
        if customer:
            logger.info("📋 Using session profile for 401(k) details: %s", client_id)
        else:
            # Fallback: Fetch customer profile from Cosmos DB
            customer = await _lookup_user_by_client_id(client_id)
        
        if not customer:
            logger.warning(f"❌ Customer not found: {client_id}")
            return _json(False, "Customer profile not found.")
        
        # Extract retirement profile
        retirement = customer.get("customer_intelligence", {}).get("retirement_profile", {})
        employment = customer.get("customer_intelligence", {}).get("employment", {})
        
        accounts = retirement.get("retirement_accounts", [])
        merrill_accounts = retirement.get("merrill_accounts", [])
        plan_features = retirement.get("plan_features", {})
        
        current_employer = employment.get("currentEmployerName", "your current employer")
        uses_contoso_401k = employment.get("usesContosoFor401k", False)
        
        # Calculate total retirement balance
        total_401k_balance = sum(a.get("balance", 0) for a in accounts)
        total_ira_balance = sum(a.get("balance", 0) for a in merrill_accounts)
        total_retirement_balance = total_401k_balance + total_ira_balance
        
        # Build detailed response
        has_retirement_accounts = len(accounts) > 0 or len(merrill_accounts) > 0
        
        if not has_retirement_accounts:
            logger.info("⚠️ No retirement accounts found | client=%s", client_id)
            return _json(
                True,
                "No retirement accounts currently on file.",
                retirement_accounts=[],
                merrill_accounts=[],
                current_employer=current_employer,
                has_accounts=False,
                suggestion="Would you like to learn about opening an IRA or setting up a 401(k) with your current employer?"
            )
        
        logger.info(
            "✅ 401(k) details retrieved | client=%s accounts=%d merrill=%d total=$%,.2f",
            client_id, len(accounts), len(merrill_accounts), total_retirement_balance
        )
        
        return _json(
            True,
            f"Retrieved retirement account details for {current_employer} and any previous accounts.",
            retirement_accounts=accounts,
            merrill_accounts=merrill_accounts,
            current_employer=current_employer,
            uses_contoso_for_401k=uses_contoso_401k,
            employer_match_pct=plan_features.get("currentEmployerMatchPct", 0),
            has_401k_pay=plan_features.get("has401kPayOnCurrentPlan", False),
            rollover_eligible=plan_features.get("rolloverEligible", False),
            risk_profile=retirement.get("risk_profile", "moderate"),
            investment_knowledge=retirement.get("investmentKnowledgeLevel", "beginner")
        )
    
    except Exception as error:
        logger.error(f"❌ Failed to retrieve 401(k) details: {error}", exc_info=True)
        return _json(False, "Unable to retrieve retirement account information at this time.")


class GetRolloverOptionsArgs(TypedDict, total=False):
    """Input schema for get_rollover_options."""
    client_id: str
    previous_employer: Optional[str]


async def get_rollover_options(args: GetRolloverOptionsArgs) -> Dict[str, Any]:
    """
    Present 401(k) rollover options with pros/cons for each choice.
    
    Explains the 4 main options for handling a previous employer's 401(k):
    1. Leave it in old employer's plan
    2. Roll over to new employer's 401(k)
    3. Roll over to an IRA
    4. Cash out (not recommended)
    
    Args:
        client_id: Unique customer identifier
        previous_employer: Name of previous employer (optional, for context)
    
    Returns:
        Dict with detailed rollover options tailored to customer's situation
    """
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format.")
    
    try:
        client_id = (args.get("client_id") or "").strip()
        previous_employer = (args.get("previous_employer") or "").strip()
        
        if not client_id:
            return _json(False, "client_id is required.")
        
        logger.info(
            "📊 Presenting rollover options | client=%s prev_employer=%s",
            client_id, previous_employer or "unspecified"
        )
        
        # First check if session profile was injected by orchestrator
        customer = args.get("_session_profile")
        if customer:
            logger.info("📋 Using session profile for rollover options: %s", client_id)
        else:
            # Fallback: Fetch customer profile from Cosmos DB
            customer = await _lookup_user_by_client_id(client_id)
        
        if not customer:
            logger.warning(f"❌ Customer not found: {client_id}")
            return _json(False, "Customer profile not found.")
        
        # Extract context for personalization
        employment = customer.get("customer_intelligence", {}).get("employment", {})
        retirement = customer.get("customer_intelligence", {}).get("retirement_profile", {})
        
        current_employer = employment.get("currentEmployerName", "your new employer")
        uses_contoso_401k = employment.get("usesContosoFor401k", False)
        plan_features = retirement.get("plan_features", {})
        has_401k_pay = plan_features.get("has401kPayOnCurrentPlan", False)
        
        # Build rollover options
        options = [
            {
                "option_id": "leave_in_old_plan",
                "name": "Leave it in your old employer's plan",
                "description": "Your money continues to grow tax-deferred with no action required.",
                "pros": [
                    "No immediate action needed",
                    "Funds remain tax-deferred",
                    "May have access to institutional investment options"
                ],
                "cons": [
                    "Cannot make new contributions",
                    "May have limited investment choices",
                    "Could face higher fees",
                    "Multiple accounts to track if you change jobs again"
                ],
                "best_for": "Those who like their current plan's investment options and fees",
                "recommended": False
            },
            {
                "option_id": "roll_to_new_401k",
                "name": f"Roll over to {current_employer}'s 401(k)",
                "description": "Consolidate your retirement savings in one place with your new employer.",
                "pros": [
                    "Consolidates retirement savings in one account",
                    "May offer lower fees and better investment options",
                    "Easier to manage and track",
                    "Continues tax-deferred growth",
                    "Access to employer match on future contributions"
                ],
                "cons": [
                    "Investment options limited to new plan's offerings",
                    "May have to wait for new plan's enrollment period"
                ],
                "best_for": "Those who want simplicity and their new employer has a good plan",
                "recommended": uses_contoso_401k,  # Recommend if new employer uses Contoso
                "special_features": [
                    "401(k) Pay available - converts savings to steady paycheck in retirement"
                ] if has_401k_pay else []
            },
            {
                "option_id": "roll_to_ira",
                "name": "Roll over to an IRA (Individual Retirement Account)",
                "description": "Move funds to an IRA for maximum control and investment flexibility.",
                "pros": [
                    "Widest range of investment options",
                    "More control over your money",
                    "Can choose between Traditional IRA or Roth IRA",
                    "No employer plan restrictions",
                    "Potential for lower fees"
                ],
                "cons": [
                    "Must actively manage investments",
                    "Roth conversion triggers immediate taxes on converted amount",
                    "No employer match (personal savings only)"
                ],
                "best_for": "Those who want maximum investment flexibility and control",
                "recommended": not uses_contoso_401k,  # Recommend if new employer doesn't use BofA
                "tax_note": "Traditional IRA rollover is tax-free. Roth IRA conversion is taxable but offers tax-free withdrawals in retirement."
            },
            {
                "option_id": "cash_out",
                "name": "Cash out (not recommended)",
                "description": "Withdraw funds now, but face significant tax consequences.",
                "pros": [
                    "Immediate access to cash"
                ],
                "cons": [
                    "Full amount added to taxable income for the year",
                    "10% early withdrawal penalty if under age 59½",
                    "Loses years of tax-deferred growth",
                    "Significantly reduces retirement savings"
                ],
                "best_for": "Emergency situations only - strongly discouraged",
                "recommended": False,
                "warning": "This option typically results in losing 30-40% of your balance to taxes and penalties."
            }
        ]
        
        logger.info("✅ Rollover options presented | client=%s options=%d", client_id, len(options))
        
        return _json(
            True,
            "Here are your rollover options for your previous employer's 401(k).",
            options=options,
            current_employer=current_employer,
            previous_employer=previous_employer or "your previous employer",
            uses_contoso_for_new_401k=uses_contoso_401k,
            has_401k_pay_benefit=has_401k_pay,
            next_steps="Choose the option that best fits your financial goals. I can explain any of these in more detail or connect you with a financial advisor."
        )
    
    except Exception as error:
        logger.error(f"❌ Failed to present rollover options: {error}", exc_info=True)
        return _json(False, "Unable to present rollover options at this time.")


class CalculateTaxImpactArgs(TypedDict, total=False):
    """Input schema for calculate_tax_impact."""
    client_id: str
    rollover_type: str  # "direct_rollover", "indirect_rollover", "roth_conversion", "cash_out"
    amount: Optional[float]


async def calculate_tax_impact(args: CalculateTaxImpactArgs) -> Dict[str, Any]:
    """
    Calculate tax implications of different 401(k) rollover strategies.
    
    Explains tax consequences for:
    - Direct rollover (no taxes)
    - Indirect rollover (20% withholding, 60-day rule)
    - Roth conversion (taxable as income)
    - Cash out (taxes + 10% penalty)
    
    Args:
        client_id: Unique customer identifier
        rollover_type: Type of rollover (direct_rollover, indirect_rollover, roth_conversion, cash_out)
        amount: 401(k) balance amount (optional, for precise calculations)
    
    Returns:
        Dict with tax impact details, withholding amounts, and recommendations
    """
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format.")
    
    try:
        client_id = (args.get("client_id") or "").strip()
        rollover_type = (args.get("rollover_type") or "").strip().lower()
        amount = args.get("amount")
        
        if not client_id:
            return _json(False, "client_id is required.")
        if not rollover_type:
            return _json(False, "rollover_type is required.")
        
        logger.info(
            "💰 Calculating tax impact | client=%s type=%s amount=%s",
            client_id, rollover_type, amount
        )
        
        # First check if session profile was injected by orchestrator
        customer = args.get("_session_profile")
        if customer:
            logger.info("📋 Using session profile for tax impact: %s", client_id)
        else:
            # Fallback: Fetch customer profile from Cosmos DB
            customer = await _lookup_user_by_client_id(client_id)
        
        if not customer:
            logger.warning(f"❌ Customer not found: {client_id}")
            return _json(False, "Customer profile not found.")
        
        # Get 401(k) balance if not provided
        if amount is None:
            retirement = customer.get("customer_intelligence", {}).get("retirement_profile", {})
            accounts = retirement.get("retirement_accounts", [])
            # Find previous employer 401(k) (status != "current_employer_plan")
            prev_accounts = [a for a in accounts if a.get("status") != "current_employer_plan"]
            if prev_accounts:
                amount = prev_accounts[0].get("estimatedBalance", 50000)
            else:
                amount = 50000  # Default estimate
        
        # Calculate tax impact based on rollover type using constants
        indirect_withholding = TAX_WITHHOLDING_INDIRECT_ROLLOVER
        early_penalty = EARLY_WITHDRAWAL_PENALTY
        tax_bracket = ESTIMATED_TAX_BRACKET
        
        tax_scenarios = {
            "direct_rollover": {
                "name": "Direct Rollover",
                "description": "Funds transfer directly from old 401(k) to new 401(k) or IRA.",
                "tax_withholding": 0,
                "penalty": 0,
                "total_taxes": 0,
                "net_amount": amount,
                "timeline": "No tax deadline - funds remain tax-deferred",
                "recommendation": "Highly recommended - avoids all taxes and penalties",
                "steps": [
                    "Contact your previous plan administrator",
                    "Request a direct rollover to your new account",
                    "Funds transfer directly - you never touch the money",
                    "No taxes owed, no forms to file"
                ]
            },
            "indirect_rollover": {
                "name": "Indirect Rollover",
                "description": "Check issued to you, then you deposit into new account within 60 days.",
                "tax_withholding": amount * indirect_withholding,
                "penalty": 0,
                "total_taxes": 0,
                "net_amount": amount * (1 - indirect_withholding),  # You receive 80%, need to deposit full 100%
                "timeline": "60 days to complete rollover or face taxes + penalty",
                "recommendation": "Not recommended - complicated and risky",
                "warning": f"You'll receive ${amount * (1 - indirect_withholding):,.2f} ({int((1 - indirect_withholding) * 100)}% of ${amount:,.2f}) but must deposit the full ${amount:,.2f} within 60 days to avoid taxes. You need to come up with the missing ${amount * indirect_withholding:,.2f} from other sources.",
                "steps": [
                    f"Old plan sends you a check for {int((1 - indirect_withholding) * 100)}% of balance",
                    "You have 60 days to deposit FULL amount into new account",
                    "If you miss deadline or deposit less, IRS treats it as withdrawal",
                    f"Withheld {int(indirect_withholding * 100)}% refunded when you file taxes next year"
                ]
            },
            "roth_conversion": {
                "name": "Roth IRA Conversion",
                "description": "Convert traditional 401(k) to Roth IRA (after-tax account).",
                "tax_withholding": 0,
                "penalty": 0,
                "total_taxes": amount * tax_bracket,
                "net_amount": amount,  # Full amount goes to Roth, but taxes owed
                "timeline": "Taxes due when you file next year's tax return",
                "recommendation": "Consider if you expect higher tax bracket in retirement",
                "benefit": "Qualified withdrawals in retirement are completely tax-free",
                "steps": [
                    "Roll over to Roth IRA",
                    f"Entire ${amount:,.2f} added to your taxable income",
                    f"Estimated tax bill: ${amount * tax_bracket:,.2f} (depends on your tax bracket)",
                    "Pay taxes when filing next year",
                    "Future qualified withdrawals are tax-free"
                ],
                "note": "Best for younger investors with time for tax-free growth"
            },
            "cash_out": {
                "name": "Cash Out (Withdrawal)",
                "description": "Withdraw funds now - not recommended due to high tax cost.",
                "tax_withholding": amount * indirect_withholding,
                "penalty": amount * early_penalty,
                "total_taxes": amount * (tax_bracket + early_penalty),
                "net_amount": amount * (1 - tax_bracket - early_penalty),
                "timeline": "Immediate",
                "recommendation": "Strongly discouraged - loses 30-40% to taxes and penalties",
                "warning": f"You'll receive only ~${amount * (1 - tax_bracket - early_penalty):,.2f} from your ${amount:,.2f} balance. You lose ${amount * (tax_bracket + early_penalty):,.2f} to taxes and penalties.",
                "consequences": [
                    f"${amount * tax_bracket:,.2f} in income taxes ({int(tax_bracket * 100)}% bracket estimate)",
                    f"${amount * early_penalty:,.2f} early withdrawal penalty ({int(early_penalty * 100)}%)",
                    "Permanently reduces retirement savings",
                    "Loses years of tax-deferred compound growth"
                ],
                "alternative": "Consider a 401(k) loan if you need emergency funds"
            }
        }
        
        if rollover_type not in tax_scenarios:
            return _json(
                False,
                f"Unknown rollover type: {rollover_type}. Valid options: direct_rollover, indirect_rollover, roth_conversion, cash_out"
            )
        
        scenario = tax_scenarios[rollover_type]
        
        logger.info(
            "✅ Tax impact calculated | client=%s type=%s net=${:,.2f}",
            client_id, rollover_type, scenario["net_amount"]
        )
        
        return _json(
            True,
            f"Tax impact for {scenario['name']}",
            rollover_type=rollover_type,
            balance_amount=amount,
            **scenario
        )
    
    except Exception as error:
        logger.error(f"❌ Failed to calculate tax impact: {error}", exc_info=True)
        return _json(False, "Unable to calculate tax impact at this time.")


# ═══════════════════════════════════════════════════════════════════
# ADVISOR HANDOFF
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE / RAG TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

# Retirement guidance knowledge base (mock data for demo)
_ROLLOVER_GUIDANCE_KB = {
    "rollover": {
        "60_day_rule": "You have 60 days to complete an indirect rollover. If you miss this deadline, the distribution becomes taxable income and may be subject to a 10% early withdrawal penalty if under age 59½.",
        "one_rollover_per_year": "The IRS limits you to one indirect (60-day) IRA-to-IRA rollover per 12-month period. This does NOT apply to direct trustee-to-trustee transfers or 401(k) rollovers.",
        "direct_vs_indirect": "Direct rollover: Funds go straight from old plan to new plan - no taxes withheld, no deadline. Indirect rollover: Check made out to you, 20% withheld, 60-day deadline to redeposit full amount.",
    },
    "contribution_limits": {
        "401k_2024": "For 2024, the 401(k) contribution limit is $23,000 ($30,500 if age 50+). Employer match does not count toward this limit.",
        "ira_2024": "For 2024, the IRA contribution limit is $7,000 ($8,000 if age 50+). Income limits apply for Roth IRA and deductible Traditional IRA contributions.",
        "catch_up": "If you're 50 or older, you can make catch-up contributions: $7,500 extra to 401(k), $1,000 extra to IRA.",
    },
    "early_withdrawal": {
        "penalty": "Early withdrawal (before age 59½) typically incurs a 10% penalty plus income taxes on the withdrawn amount.",
        "exceptions": "Penalty-free early withdrawal allowed for: disability, medical expenses >7.5% of AGI, first home purchase ($10k IRA), higher education, substantially equal periodic payments (SEPP/72t).",
        "roth_contributions": "Roth IRA contributions (not earnings) can be withdrawn tax-free and penalty-free at any time since you already paid taxes on them.",
    },
    "rmd": {
        "age_requirement": "Required Minimum Distributions (RMDs) must begin by April 1 of the year after you turn 73 (as of 2023 SECURE 2.0 Act).",
        "calculation": "RMD amount is calculated by dividing your account balance by your life expectancy factor from IRS tables.",
        "roth_ira_exception": "Roth IRAs are NOT subject to RMDs during the owner's lifetime. This is a key advantage for estate planning.",
    },
    "roth_conversion": {
        "tax_impact": "Converting Traditional 401(k)/IRA to Roth means paying income tax on the converted amount NOW, but qualified withdrawals in retirement are tax-free.",
        "when_to_convert": "Roth conversion makes sense when: you expect higher tax bracket in retirement, you have time for tax-free growth, you want to avoid RMDs, or you can pay conversion taxes from non-retirement funds.",
        "partial_conversion": "You can do partial conversions - convert only what keeps you in your current tax bracket each year.",
    },
    "general": {
        "beneficiaries": "Always keep your retirement account beneficiaries up to date. Beneficiary designations override your will.",
        "loans": "401(k) loans let you borrow up to 50% of your balance (max $50,000). Must repay within 5 years with interest. If you leave your job, loan may become due immediately.",
        "vesting": "Employer 401(k) match may have a vesting schedule - you may not own 100% of the match until you've worked there for 3-6 years.",
    },
}


async def search_rollover_guidance(args: dict[str, Any]) -> dict[str, Any]:
    """Search the retirement guidance knowledge base for IRS rules and best practices."""
    query = (args.get("query") or "").strip().lower()
    topic = (args.get("topic") or "general").strip().lower()

    if not query:
        return {"success": False, "message": "query is required."}

    logger.info("📚 Searching rollover guidance | query=%s topic=%s", query, topic)

    # Search within the specified topic first, then broader
    results = []
    topic_kb = _ROLLOVER_GUIDANCE_KB.get(topic, {})
    
    # Simple keyword matching (in production, use Azure AI Search)
    for key, content in topic_kb.items():
        if any(word in content.lower() for word in query.split()):
            results.append({"topic": topic, "key": key, "content": content})

    # If no results in specific topic, search all topics
    if not results:
        for t, entries in _ROLLOVER_GUIDANCE_KB.items():
            for key, content in entries.items():
                if any(word in content.lower() for word in query.split()):
                    results.append({"topic": t, "key": key, "content": content})

    if results:
        return {
            "success": True,
            "results": results[:3],  # Top 3 results
            "message": f"Found {len(results)} relevant guidance entries.",
        }

    return {
        "success": True,
        "results": [],
        "message": "No specific guidance found. Consider consulting a financial advisor for personalized advice.",
    }


async def get_retirement_accounts(args: dict[str, Any]) -> dict[str, Any]:
    """Get summary of all retirement accounts - delegates to get_401k_details."""
    # This is essentially an alias for get_401k_details with broader framing
    return await get_401k_details(args)


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULE ADVISOR CONSULTATION
# ═══════════════════════════════════════════════════════════════════════════════

schedule_advisor_consultation_schema: Dict[str, Any] = {
    "name": "schedule_advisor_consultation",
    "description": (
        "Schedule a consultation with a licensed financial advisor for complex investment decisions, "
        "retirement planning, tax optimization, or estate planning. The consultation will be "
        "personalized based on the customer's financial profile and retirement accounts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {
                "type": "string",
                "description": "Unique customer identifier"
            },
            "topic": {
                "type": "string",
                "description": "Primary topic for consultation (e.g., '401k rollover', 'retirement planning', 'tax optimization')"
            },
            "preferred_time": {
                "type": "string",
                "description": "Preferred consultation time (e.g., 'morning', 'afternoon', 'specific date/time')"
            },
            "advisor_type": {
                "type": "string",
                "enum": ["general", "retirement", "tax", "estate"],
                "description": "Type of advisor specialization needed"
            },
            "urgency": {
                "type": "string",
                "enum": ["low", "normal", "high"],
                "description": "How soon the customer needs the consultation"
            },
        },
        "required": ["client_id", "topic"],
    },
}


class ScheduleAdvisorConsultationArgs(TypedDict, total=False):
    """Input schema for schedule_advisor_consultation."""
    client_id: str
    topic: str
    preferred_time: Optional[str]
    advisor_type: Optional[str]
    urgency: Optional[str]


async def schedule_advisor_consultation(args: ScheduleAdvisorConsultationArgs) -> Dict[str, Any]:
    """
    Schedule a consultation with a licensed financial advisor.
    
    Retrieves customer's retirement profile to provide context for the advisor
    and schedules an appropriate consultation based on the topic and urgency.
    
    Args:
        client_id: Unique customer identifier
        topic: Primary topic for consultation
        preferred_time: Preferred consultation time
        advisor_type: Type of advisor specialization needed
        urgency: How soon the customer needs the consultation
    
    Returns:
        Dict with appointment confirmation and preparation tips
    """
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format.")
    
    try:
        client_id = (args.get("client_id") or "").strip()
        topic = (args.get("topic") or "").strip()
        preferred_time = (args.get("preferred_time") or "").strip()
        advisor_type = (args.get("advisor_type") or "general").strip().lower()
        urgency = (args.get("urgency") or "normal").strip().lower()
        
        if not client_id:
            return _json(False, "client_id is required to schedule a consultation.")
        
        if not topic:
            return _json(False, "Please specify a topic for the consultation.")
        
        # First check if session profile was injected by orchestrator
        customer = args.get("_session_profile")
        if customer:
            logger.info("📋 Using session profile for advisor consultation: %s", client_id)
        else:
            # Fallback: Retrieve customer data from Cosmos (optional - can proceed without)
            customer = await _lookup_user_by_client_id(client_id)
        
        # Extract relevant profile info for advisor context
        profile_context = {}
        if customer:
            customer_intel = customer.get("customer_intelligence", {})
            retirement = customer_intel.get("retirement_profile", {})
            employment = customer_intel.get("employment", {})
            
            # Calculate total retirement assets
            accounts = retirement.get("retirement_accounts", [])
            merrill_accounts = retirement.get("merrill_accounts", [])
            total_balance = sum(a.get("balance", 0) for a in accounts + merrill_accounts)
            
            profile_context = {
                "has_retirement_accounts": len(accounts) > 0,
                "has_ira_accounts": len(merrill_accounts) > 0,
                "total_retirement_assets": total_balance,
                "current_employer": employment.get("currentEmployerName", "Unknown"),
                "risk_profile": retirement.get("risk_profile", "moderate"),
            }
        
        # Generate appointment details
        from datetime import datetime, timedelta
        import random
        
        appointment_id = f"APT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
        
        # Determine scheduling based on urgency
        if urgency == "high":
            availability_message = "within 24 hours"
            next_available = datetime.now() + timedelta(hours=24)
        elif urgency == "low":
            availability_message = "within 1 week"
            next_available = datetime.now() + timedelta(days=7)
        else:
            availability_message = "within 48 hours"
            next_available = datetime.now() + timedelta(hours=48)
        
        scheduled_time = preferred_time if preferred_time else f"Next available - {availability_message}"
        
        # Map advisor type to specialist description
        advisor_descriptions = {
            "general": "Certified Financial Planner (CFP)",
            "retirement": "Retirement Planning Specialist",
            "tax": "Tax-Advantaged Investment Specialist",
            "estate": "Estate & Wealth Transfer Advisor",
        }
        
        # Topic-specific preparation tips
        preparation_tips = [
            "Have recent account statements ready for review",
            "Note any specific questions you want to address",
        ]
        
        if "rollover" in topic.lower() or "401k" in topic.lower():
            preparation_tips.extend([
                "Gather your previous employer 401(k) statements",
                "Know the balance and vesting status of accounts to roll over",
            ])
        elif "tax" in topic.lower():
            preparation_tips.extend([
                "Have your most recent tax return available",
                "Know your current and expected tax bracket",
            ])
        elif "retirement" in topic.lower():
            preparation_tips.extend([
                "Consider your target retirement age",
                "Think about your desired retirement lifestyle",
            ])
        
        logger.info(
            "📅 Advisor consultation scheduled | client=%s topic=%s advisor=%s urgency=%s appt=%s",
            client_id, topic, advisor_type, urgency, appointment_id
        )
        
        return _json(
            True,
            f"Consultation scheduled with a {advisor_descriptions.get(advisor_type, 'financial advisor')}.",
            appointment_id=appointment_id,
            topic=topic,
            advisor_type=advisor_type,
            advisor_description=advisor_descriptions.get(advisor_type, "Certified Financial Planner"),
            scheduled_time=scheduled_time,
            urgency=urgency,
            confirmation_sent=True,
            preparation_tips=preparation_tips,
            profile_context=profile_context if profile_context else None,
            next_steps=[
                "You will receive a confirmation email with dial-in details",
                "A calendar invite will be sent to your registered email",
                "You can reschedule up to 4 hours before the appointment",
            ]
        )
    
    except Exception as error:
        logger.error(f"❌ Failed to schedule advisor consultation: {error}", exc_info=True)
        return _json(False, "Unable to schedule consultation at this time. Please try again or call our service line.")


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "get_account_routing_info",
    get_account_routing_info_schema,
    get_account_routing_info,
    tags={"banking", "account", "direct_deposit"},
)
register_tool(
    "get_401k_details",
    get_401k_details_schema,
    get_401k_details,
    tags={"investments", "retirement", "401k"},
)
register_tool(
    "get_retirement_accounts",
    get_retirement_accounts_schema,
    get_retirement_accounts,
    tags={"investments", "retirement"},
)
register_tool(
    "get_rollover_options",
    get_rollover_options_schema,
    get_rollover_options,
    tags={"investments", "retirement", "rollover"},
)
register_tool(
    "calculate_tax_impact",
    calculate_tax_impact_schema,
    calculate_tax_impact,
    tags={"investments", "retirement", "tax"},
)
register_tool(
    "search_rollover_guidance",
    search_rollover_guidance_schema,
    search_rollover_guidance,
    tags={"investments", "retirement", "knowledge_base"},
)
# NOTE: schedule_advisor_consultation is NOT registered here because
# handoff_bank_advisor in handoffs.py handles Merrill advisor callbacks.
# The function is kept for reference but the prompt uses handoff_bank_advisor.
# register_tool(
#     "schedule_advisor_consultation",
#     schedule_advisor_consultation_schema,
#     schedule_advisor_consultation,
#     tags={"investments", "retirement", "advisor", "scheduling"},
# )