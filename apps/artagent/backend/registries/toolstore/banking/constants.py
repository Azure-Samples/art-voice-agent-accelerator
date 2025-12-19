"""
Banking Constants & Synthetic Data Configuration
================================================

Central repository for all banking-related constants, mock data, and configuration.
Edit this file to customize the demo experience for different institutions or scenarios.

Architecture:
- All hardcoded demo data is centralized here
- Tool modules import from this file instead of inline definitions
- Enables easy A/B testing of different demo scenarios
- Supports multi-tenant customization via environment overrides

Usage:
    from .constants.banking_constants import (
        INSTITUTION_CONFIG,
        CARD_PRODUCTS,
        MOCK_CUSTOMER_PROFILE,
    )
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: INSTITUTION CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class InstitutionConfig:
    """Financial institution branding and contact configuration."""
    name: str = "Contoso Bank"
    routing_number: str = "021000021"
    swift_code: str = "CONTOSOXX"
    support_phone: str = "1-800-555-0100"
    support_phone_display: str = "1-800-555-0100"
    website_domain: str = "contosobank.com"
    secure_domain: str = "secure.contosobank.com"
    atm_network_count: str = "30,000+"
    # NOTE: ATM fee waivers apply to DEBIT/ATM cards only, NOT credit cards
    debit_atm_message: str = "With your Contoso Bank debit card: No fees at 30,000+ Contoso Bank ATMs nationwide. Preferred Rewards members may have additional non-network ATM fee waivers."
    global_atm_alliance_message: str = "Global ATM Alliance: Use your Contoso Bank debit card at partner banks abroad (Barclays, BNP Paribas, Deutsche Bank) to avoid some ATM fees."


# Allow environment override for multi-tenant demos
INSTITUTION_CONFIG = InstitutionConfig(
    name=os.getenv("INSTITUTION_NAME", "Contoso Bank"),
    support_phone=os.getenv("INSTITUTION_SUPPORT_PHONE", "1-800-555-0100"),
)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: CUSTOMER TIERS & INCOME BANDS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CustomerTierConfig:
    """Customer tier definitions and benefits including ATM fee waivers."""
    name: str
    rewards_bonus_pct: int  # e.g., 75 for 75% bonus
    annual_fee_waived: bool
    description: str
    # ATM fee waiver benefits (for DEBIT CARD only - NOT credit cards)
    debit_atm_fee_waivers_per_cycle: int  # -1 = unlimited, 0 = none
    international_atm_fee_waived: bool
    atm_benefit_description: str


CUSTOMER_TIERS: Dict[str, CustomerTierConfig] = {
    "diamond_honors": CustomerTierConfig(
        name="Preferred Rewards Diamond Honors",
        rewards_bonus_pct=75,
        annual_fee_waived=True,
        description="Preferred Rewards Diamond Honors: 75% rewards bonus + all premium benefits",
        debit_atm_fee_waivers_per_cycle=-1,  # Unlimited
        international_atm_fee_waived=True,
        atm_benefit_description="Unlimited non-network ATM fee waivers + international ATM fees waived on your debit card"
    ),
    "platinum_honors": CustomerTierConfig(
        name="Preferred Rewards Platinum Honors",
        rewards_bonus_pct=75,
        annual_fee_waived=True,
        description="Preferred Rewards Platinum Honors: 75% rewards bonus + expedited benefits",
        debit_atm_fee_waivers_per_cycle=-1,  # Unlimited
        international_atm_fee_waived=False,
        atm_benefit_description="Unlimited non-network ATM fee waivers on your debit card (ATM owner surcharge may still apply)"
    ),
    "platinum": CustomerTierConfig(
        name="Preferred Rewards Platinum",
        rewards_bonus_pct=75,
        annual_fee_waived=True,
        description="Preferred Rewards Platinum: 75% rewards bonus + expedited benefits",
        debit_atm_fee_waivers_per_cycle=1,  # 1 per cycle
        international_atm_fee_waived=False,
        atm_benefit_description="1 non-network ATM fee waiver per statement cycle on your debit card (ATM owner surcharge may still apply)"
    ),
    "gold": CustomerTierConfig(
        name="Preferred Rewards Gold",
        rewards_bonus_pct=50,
        annual_fee_waived=False,
        description="Preferred Rewards Gold: 50% rewards bonus",
        debit_atm_fee_waivers_per_cycle=0,
        international_atm_fee_waived=False,
        atm_benefit_description="No ATM fee waivers - use Contoso Bank ATMs or Global ATM Alliance partners abroad to avoid fees"
    ),
    "standard": CustomerTierConfig(
        name="Standard",
        rewards_bonus_pct=0,
        annual_fee_waived=False,
        description="Standard rewards earning",
        debit_atm_fee_waivers_per_cycle=0,
        international_atm_fee_waived=False,
        atm_benefit_description="No ATM fee waivers - use Contoso Bank ATMs to avoid fees"
    ),
}


def get_tier_atm_benefits(tier_name: str) -> str:
    """Get ATM benefit description for a customer tier (for DEBIT cards only)."""
    tier_key = tier_name.lower().replace(" ", "_").replace("preferred_rewards_", "")
    # Handle common variations
    if "diamond" in tier_key:
        tier_key = "diamond_honors"
    elif "platinum" in tier_key and "honors" in tier_key:
        tier_key = "platinum_honors"
    elif "platinum" in tier_key:
        tier_key = "platinum"
    elif "gold" in tier_key:
        tier_key = "gold"
    else:
        tier_key = "standard"
    
    tier_config = CUSTOMER_TIERS.get(tier_key)
    if tier_config:
        return tier_config.atm_benefit_description
    return "Use Contoso Bank ATMs to avoid fees"

# Credit limits by income band (used in card approval)
CREDIT_LIMITS_BY_INCOME: Dict[str, int] = {
    "high": 15000,
    "medium": 8500,
    "low": 5000,
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: CREDIT CARD PRODUCT CATALOG
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CardProduct:
    """Credit card product definition."""
    product_id: str
    name: str
    annual_fee: int
    foreign_transaction_fee: float  # as percentage (0, 3, etc.)
    rewards_rate: str
    intro_apr: str
    regular_apr: str
    sign_up_bonus: str
    best_for: List[str]
    tier_requirement: str
    tier_benefits: Dict[str, str]
    highlights: List[str]
    atm_benefits: str
    # Optional extended attributes
    roi_example: Optional[str] = None


# Complete card product catalog
CARD_PRODUCTS: Dict[str, CardProduct] = {
    "travel-rewards-001": CardProduct(
        product_id="travel-rewards-001",
        name="Travel Rewards Credit Card",
        annual_fee=0,
        foreign_transaction_fee=0,
        rewards_rate="1.5 points per $1 on all purchases",
        intro_apr="0% for 12 months on purchases",
        regular_apr="19.24% - 29.24% variable APR",
        sign_up_bonus="25,000 bonus points after $1,000 spend in 90 days",
        best_for=["travel", "international", "no_annual_fee", "foreign_fee_avoidance"],
        tier_requirement="All tiers (Gold, Platinum, Standard)",
        tier_benefits={
            "platinum": "Preferred Rewards members earn 25%-75% more points",
            "gold": "Gold members earn 25%-50% more points",
            "standard": "Standard rewards earning"
        },
        highlights=[
            "No annual fee",
            "No foreign transaction fees ON PURCHASES - ideal for international travelers",
            "Unlimited 1.5 points per $1 on all purchases",
            "Redeem points for travel, dining, or cash back with no blackout dates",
            "Travel insurance included (trip delay, baggage delay)",
            "IMPORTANT: For cash abroad, use your Contoso Bank debit card at partner ATMs to minimize fees"
        ],
        atm_benefits="Credit card ATM use = cash advance with fees and immediate interest. For travel cash, use your Contoso Bank debit card at Contoso Bank or Global ATM Alliance partner ATMs."
    ),
    "premium-rewards-001": CardProduct(
        product_id="premium-rewards-001",
        name="Premium Rewards Credit Card",
        annual_fee=95,
        foreign_transaction_fee=0,
        rewards_rate="2 points per $1 on travel & dining, 1.5 points per $1 on everything else",
        intro_apr="0% for 15 months on purchases and balance transfers",
        regular_apr="19.24% - 29.24% variable APR",
        sign_up_bonus="60,000 bonus points after $4,000 spend in 90 days",
        best_for=["travel", "dining", "balance_transfer", "premium_benefits", "international"],
        tier_requirement="Preferred Rewards Platinum or Gold (income verification required)",
        tier_benefits={
            "platinum": "Preferred Rewards Platinum: 75% rewards bonus + expedited benefits",
            "gold": "Preferred Rewards Gold: 50% rewards bonus",
            "standard": "Not recommended - consider Travel Rewards card instead"
        },
        highlights=[
            "$95 annual fee (waived first year for Platinum tier)",
            "2x points on travel and dining - ideal for high spenders",
            "$100 airline fee credit (reimbursement for baggage fees, seat selection)",
            "$100 TSA PreCheck/Global Entry credit every 4 years",
            "Comprehensive travel insurance (trip cancellation, interruption, delay)",
            "No foreign transaction fees ON PURCHASES",
            "Priority airport lounge access (4 free visits annually)",
            "IMPORTANT: For cash abroad, use your Contoso Bank debit card - credit card ATM use incurs cash advance fees"
        ],
        atm_benefits="Credit card ATM use = cash advance (typically 4-5% fee + higher APR from day one, no grace period). For travel cash, use your Contoso Bank debit card at Contoso Bank or Global ATM Alliance partner ATMs.",
        roi_example="Customer spending $4,000/month on travel & dining earns ~$1,200/year in rewards, offsetting annual fee"
    ),
    "cash-rewards-002": CardProduct(
        product_id="cash-rewards-002",
        name="Customized Cash Rewards Credit Card",
        annual_fee=0,
        foreign_transaction_fee=3,
        rewards_rate="3% cash back on choice category, 2% at grocery stores and wholesale clubs, 1% on everything else",
        intro_apr="0% for 15 months on purchases and balance transfers",
        regular_apr="19.24% - 29.24% variable APR",
        sign_up_bonus="$200 online cash rewards bonus after $1,000 in purchases in first 90 days",
        best_for=["groceries", "gas", "online_shopping", "everyday", "balance_transfer", "domestic"],
        tier_requirement="All tiers",
        tier_benefits={
            "platinum": "Preferred Rewards Platinum: 75% cash back bonus (up to 5.25% on choice category)",
            "gold": "Preferred Rewards Gold: 50% cash back bonus (up to 4.5% on choice category)",
            "standard": "Standard 3% cash back on choice category"
        },
        highlights=[
            "No annual fee",
            "3% cash back on your choice category (gas, online shopping, dining, travel, drugstores, or home improvement)",
            "2% at grocery stores and wholesale clubs (up to $2,500 in combined quarterly purchases)",
            "1% cash back on all other purchases",
            "Not ideal for international travelers - 3% foreign transaction fee"
        ],
        atm_benefits="Standard Contoso Bank ATM access"
    ),
    "unlimited-cash-003": CardProduct(
        product_id="unlimited-cash-003",
        name="Unlimited Cash Rewards Credit Card",
        annual_fee=0,
        foreign_transaction_fee=3,
        rewards_rate="1.5% cash back on all purchases",
        intro_apr="0% for 18 months on purchases and balance transfers",
        regular_apr="19.24% - 29.24% variable APR",
        sign_up_bonus="$200 online cash rewards bonus",
        best_for=["balance_transfer", "everyday", "simple_rewards", "domestic"],
        tier_requirement="All tiers",
        tier_benefits={
            "platinum": "Preferred Rewards Platinum: 75% cash back bonus (2.625% on everything)",
            "gold": "Preferred Rewards Gold: 50% cash back bonus (2.25% on everything)",
            "standard": "Standard 1.5% cash back"
        },
        highlights=[
            "No annual fee",
            "Unlimited 1.5% cash back on all purchases",
            "0% intro APR for 18 months - longest intro period for balance transfers",
            "No categories to track - simple flat-rate rewards",
            "Not ideal for international travelers - 3% foreign transaction fee"
        ],
        atm_benefits="Standard Contoso Bank ATM access"
    ),
}


def get_card_product(product_id: str) -> Optional[CardProduct]:
    """Get card product by ID."""
    return CARD_PRODUCTS.get(product_id)


def get_all_card_products() -> List[CardProduct]:
    """Get all card products as a list."""
    return list(CARD_PRODUCTS.values())


def card_product_to_dict(card: CardProduct) -> Dict[str, Any]:
    """Convert CardProduct dataclass to dict for JSON serialization."""
    return {
        "product_id": card.product_id,
        "name": card.name,
        "annual_fee": card.annual_fee,
        "foreign_transaction_fee": card.foreign_transaction_fee,
        "rewards_rate": card.rewards_rate,
        "intro_apr": card.intro_apr,
        "regular_apr": card.regular_apr,
        "sign_up_bonus": card.sign_up_bonus,
        "best_for": card.best_for,
        "tier_requirement": card.tier_requirement,
        "tier_benefits": card.tier_benefits,
        "highlights": card.highlights,
        "atm_benefits": card.atm_benefits,
        "roi_example": card.roi_example,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: CARD KNOWLEDGE BASE (RAG Fallback)
# ═══════════════════════════════════════════════════════════════════════════════

# Card-specific FAQ answers when Azure AI Search is unavailable
CARD_KNOWLEDGE_BASE: Dict[str, Dict[str, str]] = {
    "travel-rewards-001": {
        "apr": "Variable APR of 19.24% - 29.24% after intro period",
        "foreign_fees": "No foreign transaction fees on PURCHASES made outside the US. This does NOT apply to ATM cash withdrawals.",
        "atm_cash_advance": "IMPORTANT: Using any credit card at an ATM is a CASH ADVANCE, not a purchase. Cash advances have: (1) a fee of 4-5% of the amount, (2) a higher APR than purchases, and (3) interest starts immediately with no grace period. For travel cash, use your Contoso Bank debit card at partner ATMs instead.",
        "eligibility": "Good to excellent credit (FICO 670+). Must be 18+ and US resident.",
        "benefits": "No annual fee, travel insurance up to $250,000, baggage delay insurance, rental car coverage",
        "rewards": "Earn 1.5 points per $1 on all purchases with no category restrictions or caps",
        "balance_transfer": "0% intro APR for 12 months, then variable APR. 3% balance transfer fee",
        "best_for_travel": "Ideal for purchases abroad - no foreign transaction fee on purchases. For cash needs while traveling, use your Contoso Bank debit card at Global ATM Alliance partners (Barclays, BNP Paribas, Deutsche Bank) to reduce fees."
    },
    "premium-rewards-001": {
        "apr": "Variable APR of 18.24% - 28.24% after intro period",
        "foreign_fees": "No foreign transaction fees on PURCHASES. This does NOT apply to ATM cash withdrawals.",
        "atm_cash_advance": "IMPORTANT: Using any credit card at an ATM is a CASH ADVANCE, not a purchase. Cash advances have: (1) a fee of 4-5% of the amount, (2) a higher APR than purchases, and (3) interest starts immediately with no grace period. For travel cash, use your Contoso Bank debit card at partner ATMs instead.",
        "eligibility": "Excellent credit (FICO 750+). Preferred Rewards tier recommended for maximum benefits.",
        "benefits": "$95 annual fee. $100 airline fee credit, $100 TSA PreCheck/Global Entry credit, travel insurance up to $500,000, trip cancellation coverage, lost luggage reimbursement",
        "rewards": "Earn 2 points per $1 on travel and dining, 1.5 points per $1 on all other purchases. Points value increases with Preferred Rewards tier: up to 75% bonus",
        "balance_transfer": "0% intro APR for 15 months, then variable APR. 3% balance transfer fee ($10 minimum)",
        "best_for_travel": "Premium travel card - no foreign transaction fee on purchases, extensive travel insurance. For cash needs abroad, use your Contoso Bank debit card at Global ATM Alliance partners."
    },
    "cash-rewards-002": {
        "apr": "Variable APR of 19.24% - 29.24% after intro period",
        "foreign_fees": "3% foreign transaction fee on purchases made outside the US",
        "eligibility": "Good to excellent credit (FICO 670+)",
        "benefits": "No annual fee, choose your 3% cash back category each month (gas, online shopping, dining, travel, drugstores, home improvement)",
        "rewards": "3% cash back in your choice category (up to $2,500 per quarter), 2% at grocery stores and wholesale clubs (up to $2,500 per quarter), 1% on all other purchases",
        "balance_transfer": "0% intro APR for 15 months on purchases and balance transfers, then variable APR. 3% balance transfer fee"
    },
    "unlimited-cash-003": {
        "apr": "Variable APR of 18.24% - 28.24% after intro period",
        "foreign_fees": "3% foreign transaction fee",
        "eligibility": "Good credit (FICO 670+)",
        "benefits": "No annual fee, simple unlimited cash back structure with no categories to track",
        "rewards": "Flat 1.5% cash back on all purchases with no limits or caps",
        "balance_transfer": "0% intro APR for 18 months on purchases and balance transfers, then variable APR. 3% balance transfer fee ($10 minimum)"
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: MOCK CUSTOMER DATA (Demo Profiles)
# ═══════════════════════════════════════════════════════════════════════════════

def _utc_now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# Default mock customer profile (used when Cosmos DB is unavailable)
MOCK_CUSTOMER_PROFILE: Dict[str, Any] = {
    "client_id": "demo-001",
    "name": "Alex Thompson",
    "tier": "Platinum",
    "financial_goals": ["Save for home down payment", "Reduce credit card fees"],
    "alerts": [
        {
            "type": "promotional",
            "message": "You qualify for 0% APR balance transfer on Premium Rewards card",
        }
    ],
    "preferred_contact": "mobile",
}

# Default mock account summary
MOCK_ACCOUNT_SUMMARY: Dict[str, Any] = {
    "checking": {
        "account_number": "****1234",
        "balance": 2450.67,
        "available": 2450.67
    },
    "savings": {
        "account_number": "****5678",
        "balance": 15230.00,
        "available": 15230.00
    },
    "credit_cards": [
        {
            "product_name": "Cash Rewards",
            "last_four": "9012",
            "balance": 450.00,
            "credit_limit": 5000.00,
            "available_credit": 4550.00
        }
    ],
}

# Default mock transaction history
# Designed to showcase ATM fees, foreign transaction fees, and various categories
MOCK_TRANSACTIONS: List[Dict[str, Any]] = [
    {
        "date": "2025-11-20",
        "merchant": "ATM Withdrawal - Non-Network ATM",
        "amount": -18.00,
        "account": "****1234",
        "type": "fee",
        "category": "atm_fee",
        "location": "Paris, France",
        "fee_breakdown": {
            "bank_fee": 10.00,
            "foreign_atm_surcharge": 8.00,
            "description": "Non-network ATM withdrawal outside our partner network. Foreign ATM surcharge set by ATM owner."
        },
        "is_foreign_transaction": True,
        "network_status": "non-network"
    },
    {
        "date": "2025-11-20",
        "merchant": "ATM Cash Withdrawal",
        "amount": -200.00,
        "account": "****1234",
        "type": "debit",
        "category": "cash_withdrawal",
        "location": "Paris, France",
        "is_foreign_transaction": True
    },
    {
        "date": "2025-11-19",
        "merchant": "Hotel Le Royal",
        "amount": -385.00,
        "account": "****9012",
        "type": "credit",
        "category": "travel",
        "location": "Paris, France",
        "foreign_transaction_fee": 11.55,
        "is_foreign_transaction": True
    },
    {
        "date": "2025-11-19",
        "merchant": "Foreign Transaction Fee",
        "amount": -11.55,
        "account": "****9012",
        "type": "fee",
        "category": "foreign_transaction_fee",
        "fee_breakdown": {
            "description": "3% foreign transaction fee on $385.00 purchase",
            "base_transaction": 385.00,
            "fee_percentage": 3.0
        },
        "is_foreign_transaction": True
    },
    {
        "date": "2025-11-18",
        "merchant": "Restaurant Le Bistro",
        "amount": -125.00,
        "account": "****9012",
        "type": "credit",
        "category": "dining",
        "location": "Paris, France",
        "is_foreign_transaction": True
    },
    {
        "date": "2025-11-17",
        "merchant": "Airline - International Flight",
        "amount": -850.00,
        "account": "****9012",
        "type": "credit",
        "category": "travel"
    },
    {
        "date": "2025-11-16",
        "merchant": "Grocery Store",
        "amount": -123.45,
        "account": "****1234",
        "type": "debit",
        "category": "groceries"
    },
    {
        "date": "2025-11-15",
        "merchant": "Payroll Deposit - Employer",
        "amount": 2850.00,
        "account": "****1234",
        "type": "credit",
        "category": "income"
    },
    {
        "date": "2025-11-14",
        "merchant": "Gas Station",
        "amount": -65.00,
        "account": "****9012",
        "type": "credit",
        "category": "transportation"
    },
    {
        "date": "2025-11-13",
        "merchant": "Coffee Shop",
        "amount": -5.75,
        "account": "****9012",
        "type": "credit",
        "category": "dining"
    },
    {
        "date": "2025-11-12",
        "merchant": "Online Retailer",
        "amount": -89.99,
        "account": "****9012",
        "type": "credit",
        "category": "shopping"
    },
    {
        "date": "2025-11-11",
        "merchant": "Streaming Service",
        "amount": -14.99,
        "account": "****1234",
        "type": "debit",
        "category": "entertainment"
    }
]

# Default mock retirement data
MOCK_RETIREMENT_DATA: Dict[str, Any] = {
    "has_401k": True,
    "former_employer_401k": {
        "provider": "Fidelity",
        "balance": 45000.00,
        "eligible_for_rollover": True
    },
    "current_ira": {
        "type": "Traditional IRA",
        "balance": 12000.00,
        "account_number": "****7890"
    },
    "retirement_readiness_score": 6.5,
    "suggested_actions": [
        "Consider rolling over former 401(k) to IRA for lower fees",
        "Increase contribution rate to meet retirement goals"
    ]
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: AI SEARCH CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Known card names for fuzzy matching in AI Search queries
KNOWN_CARD_NAMES: List[str] = [
    "Premium Rewards",
    "Travel Rewards",
    "Unlimited Cash Rewards",
    "Customized Cash Rewards",
    "Contoso Classic",
    "Elite",
]

# Card name abbreviation mappings for normalization
CARD_NAME_ABBREVIATIONS: Dict[str, str] = {
    "premium": "Premium Rewards",
    "travel": "Travel Rewards",
    "unlimited": "Unlimited Cash Rewards",
    "unlimited cash": "Unlimited Cash Rewards",
    "customized": "Customized Cash Rewards",
    "customized cash": "Customized Cash Rewards",
    "classic": "Contoso Classic",
    "elite": "Elite",
}

# Default embedding model dimensions
DEFAULT_EMBEDDING_DIMENSIONS: int = 3072


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: AGENT NAMES & HANDOFF CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class AgentNames:
    """Agent identifiers for handoff orchestration."""
    BANKING_CONCIERGE = "BankingConcierge"
    CARD_RECOMMENDATION = "CardRecommendation"
    INVESTMENT_ADVISOR = "InvestmentAdvisor"
    TRANSFER_AGENCY = "TransferAgencyAgent"
    FRAUD_AGENT = "FraudAgent"
    FINANCIAL_ADVISOR = "financial_advisor"  # Human escalation target


# Handoff transition messages
HANDOFF_MESSAGES: Dict[str, str] = {
    "card_recommendation": "Let me find the best card options for you.",
    "investment_advisor": "Let me look at your retirement accounts and options.",
    "transfer_agency": "Let me connect you with our Transfer Agency specialist.",
    "financial_advisor": "Connecting you with a financial advisor. Please hold.",
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: EMAIL & DELIVERY CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Card delivery timeframes
CARD_DELIVERY_TIMEFRAME: str = "3-5 business days"
CARD_DELIVERY_DAYS_MIN: int = 3
CARD_DELIVERY_DAYS_MAX: int = 7

# MFA code configuration
MFA_CODE_LENGTH: int = 6
MFA_CODE_EXPIRY_HOURS: int = 24

# Email configuration
EMAIL_VERIFICATION_EXPIRY_HOURS: int = 24


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9: ROLLOVER & TAX CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Tax withholding rates for retirement account operations
TAX_WITHHOLDING_INDIRECT_ROLLOVER: float = 0.20  # 20% mandatory withholding
EARLY_WITHDRAWAL_PENALTY: float = 0.10  # 10% penalty if under 59½
ESTIMATED_TAX_BRACKET: float = 0.25  # Default 25% estimate for Roth conversions

# Rollover option identifiers
ROLLOVER_OPTIONS: Dict[str, str] = {
    "leave_in_old_plan": "Leave it in your old employer's plan",
    "roll_to_new_401k": "Roll over to new employer's 401(k)",
    "roll_to_ira": "Roll over to an IRA (Individual Retirement Account)",
    "cash_out": "Cash out (not recommended)",
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10: FEE REFUND CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Fee types that can be refunded
REFUNDABLE_FEE_TYPES: List[str] = [
    "atm_fee",
    "foreign_transaction_fee",
    "overdraft_fee",
    "late_payment_fee",
    "annual_fee",
]

# Refund processing time
REFUND_PROCESSING_DAYS: str = "2 business days"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 11: FEE POLICY KNOWLEDGE BASE (Anti-Hallucination Guardrails)
# ═══════════════════════════════════════════════════════════════════════════════
# This section provides accurate, grounded information about fees to prevent
# the AI from making incorrect claims about ATM fees, foreign transaction fees,
# and the critical difference between debit cards and credit cards.

FEE_POLICY_KB: Dict[str, str] = {
    # CRITICAL: Credit Card ATM = Cash Advance
    "credit_card_atm_usage": """
CRITICAL POLICY: Using a CREDIT CARD at an ATM is a CASH ADVANCE, not a regular transaction.
Cash advances have THREE penalties:
1. Cash advance fee: typically 4-5% of the amount (minimum $10)
2. Higher APR: cash advance APR is often 25-29%, higher than purchase APR
3. NO grace period: interest accrues immediately from the day of withdrawal, unlike purchases

NEVER claim that credit cards have "no ATM fees" or "free ATM access" - this is incorrect.
Credit cards are designed for PURCHASES, not cash withdrawals.
""",

    # Foreign Transaction Fees - Purchases vs ATM
    "foreign_transaction_fee_scope": """
"No foreign transaction fee" on credit cards applies ONLY to PURCHASES made in foreign currencies.
This benefit does NOT apply to:
- ATM cash withdrawals (which are cash advances with separate fees)
- Cash equivalents (wire transfers, money orders, etc.)

Example: Travel Rewards card has 0% foreign transaction fee on a €100 dinner in Paris.
But using that same card at a Paris ATM for €100 cash = cash advance fee + cash advance APR.
""",

    # Debit Card ATM Benefits (Preferred Rewards)
    "debit_atm_preferred_rewards": """
ATM fee waivers are primarily for DEBIT/ATM CARDS through Preferred Rewards program:
- Platinum tier: 1 non-network ATM fee waiver per statement cycle
- Platinum Honors: Unlimited non-network ATM fee waivers
- Diamond Honors: Unlimited waivers + international ATM fee waivers

These benefits apply to the DEBIT CARD linked to the checking account, NOT credit cards.
The ATM owner may still charge their own surcharge even if Contoso Bank waives its fee.
""",

    # Global ATM Alliance
    "global_atm_alliance": """
Global ATM Alliance is for DEBIT/ATM CARDS only:
- Partner banks: Barclays (UK), BNP Paribas (France), Deutsche Bank (Germany), and others
- Using your Contoso Bank debit card at these ATMs avoids Contoso Bank's non-network ATM fee
- The ATM owner's surcharge is typically waived at alliance partners
- A 3% international transaction fee may still apply for currency conversion

This alliance does NOT apply to credit cards.
""",

    # How to Advise Travelers About Cash
    "travel_cash_advice": """
For customers traveling internationally who need cash:

BEST OPTIONS (in order):
1. Contoso Bank ATM if available abroad
2. Global ATM Alliance partner ATMs with your Contoso Bank DEBIT card
3. Non-partner ATM with your Contoso Bank DEBIT card (bank fee + possible ATM surcharge)

AVOID: Using credit card for ATM cash - cash advance fees and immediate interest apply.

RECOMMENDED APPROACH: "For purchases abroad, your travel credit card eliminates foreign 
transaction fees. For cash needs, your Contoso Bank debit card at partner ATMs is the 
most cost-effective option. Using a credit card at an ATM is treated as a cash advance 
with fees and immediate interest, so it's best avoided."
"""
}


# Helper function to get fee policy information
def get_fee_policy(topic: str) -> Optional[str]:
    """Get accurate fee policy information by topic."""
    return FEE_POLICY_KB.get(topic)


def get_all_fee_policies() -> Dict[str, str]:
    """Get all fee policies for agent grounding."""
    return FEE_POLICY_KB.copy()


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Institution
    "INSTITUTION_CONFIG",
    "InstitutionConfig",
    # Tiers
    "CUSTOMER_TIERS",
    "CustomerTierConfig",
    "CREDIT_LIMITS_BY_INCOME",
    "get_tier_atm_benefits",
    # Card Products
    "CARD_PRODUCTS",
    "CardProduct",
    "get_card_product",
    "get_all_card_products",
    "card_product_to_dict",
    "CARD_KNOWLEDGE_BASE",
    # Mock Data
    "MOCK_CUSTOMER_PROFILE",
    "MOCK_ACCOUNT_SUMMARY",
    "MOCK_TRANSACTIONS",
    "MOCK_RETIREMENT_DATA",
    # AI Search
    "KNOWN_CARD_NAMES",
    "CARD_NAME_ABBREVIATIONS",
    "DEFAULT_EMBEDDING_DIMENSIONS",
    # Agents
    "AgentNames",
    "HANDOFF_MESSAGES",
    # Email/Delivery
    "CARD_DELIVERY_TIMEFRAME",
    "CARD_DELIVERY_DAYS_MIN",
    "CARD_DELIVERY_DAYS_MAX",
    "MFA_CODE_LENGTH",
    "MFA_CODE_EXPIRY_HOURS",
    "EMAIL_VERIFICATION_EXPIRY_HOURS",
    # Rollover/Tax
    "TAX_WITHHOLDING_INDIRECT_ROLLOVER",
    "EARLY_WITHDRAWAL_PENALTY",
    "ESTIMATED_TAX_BRACKET",
    "ROLLOVER_OPTIONS",
    # Fees
    "REFUNDABLE_FEE_TYPES",
    "REFUND_PROCESSING_DAYS",
    # Fee Policies (Anti-Hallucination)
    "FEE_POLICY_KB",
    "get_fee_policy",
    "get_all_fee_policies",
]