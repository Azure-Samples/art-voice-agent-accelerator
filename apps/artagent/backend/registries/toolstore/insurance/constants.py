"""
Insurance Constants - Shared Data for Insurance Tools
======================================================

Centralized constants, mock data, and configuration for insurance tooling.
All fictional company names use the "Contoso" pattern with "Insurance" suffix.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set


# ═══════════════════════════════════════════════════════════════════════════════
# CONTACT INFORMATION
# ═══════════════════════════════════════════════════════════════════════════════

SUBRO_FAX_NUMBER = "(888) 781-6947"
SUBRO_PHONE_NUMBER = "(855) 405-8645"


# ═══════════════════════════════════════════════════════════════════════════════
# FICTIONAL CLAIMANT CARRIER COMPANIES
# ═══════════════════════════════════════════════════════════════════════════════
# These are fictional insurance company names for demo/testing purposes.
# All names follow the pattern: [Name] Insurance

KNOWN_CC_COMPANIES: Set[str] = {
    "contoso insurance",
    "fabrikam insurance",
    "adventure works insurance",
    "northwind insurance",
    "tailspin insurance",
    "woodgrove insurance",
    "litware insurance",
    "proseware insurance",
    "fourthcoffee insurance",
    "wideworldimporters insurance",
    "alpineski insurance",
    "blueyonder insurance",
    "cohovineyard insurance",
    "margie insurance",
    "treyresearch insurance",
    "adatum insurance",
    "munson insurance",
    "lucerne insurance",
    "relecloud insurance",
    "wingtip insurance",
}

# Display-friendly list of CC company names (capitalized)
CC_COMPANY_DISPLAY_NAMES: List[str] = [
    "Contoso Insurance",
    "Fabrikam Insurance",
    "Adventure Works Insurance",
    "Northwind Insurance",
    "Tailspin Insurance",
    "Woodgrove Insurance",
    "Litware Insurance",
    "Proseware Insurance",
    "Fourth Coffee Insurance",
    "Wide World Importers Insurance",
    "Alpine Ski Insurance",
    "Blue Yonder Insurance",
    "Coho Vineyard Insurance",
    "Margie Insurance",
    "Trey Research Insurance",
    "Adatum Insurance",
    "Munson Insurance",
    "Lucerne Insurance",
    "Relecloud Insurance",
    "Wingtip Insurance",
]


# ═══════════════════════════════════════════════════════════════════════════════
# RUSH CRITERIA - Conditions that qualify for ISRUSH diary
# ═══════════════════════════════════════════════════════════════════════════════

RUSH_CRITERIA: Dict[str, bool] = {
    "attorney_represented": True,
    "demand_over_limits": True,
    "statute_of_limitations_near": True,  # < 60 days
    "prior_demands_unanswered": True,
    "escalation_request": True,
}


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS CODES
# ═══════════════════════════════════════════════════════════════════════════════

COVERAGE_STATUS_CODES = {
    "confirmed": "Coverage has been confirmed",
    "pending": "Coverage verification is pending",
    "denied": "Coverage has been denied",
    "cvq": "Coverage question under review",
}

LIABILITY_STATUS_CODES = {
    "pending": "Liability decision is pending",
    "accepted": "Liability has been accepted",
    "denied": "Liability has been denied",
    "not_applicable": "Liability not applicable (no coverage)",
}

DEMAND_STATUS_CODES = {
    "not_received": "No demand received",
    "received": "Demand received, pending assignment",
    "assigned": "Demand assigned to handler",
    "under_review": "Demand under review",
    "paid": "Demand has been paid",
    "denied_no_coverage": "Demand denied - no coverage",
    "denied_no_liability": "Demand denied - no liability",
}


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK DATA - Claims with subrogation info
# ═══════════════════════════════════════════════════════════════════════════════
# Comprehensive test scenarios covering all edge cases:
# - CLM-2024-001234: Demand received, under review, liability PENDING
# - CLM-2024-005678: Demand PAID, liability accepted 80%
# - CLM-2024-009012: NO demand received, coverage pending (CVQ)
# - CLM-2024-003456: Coverage DENIED (policy lapsed), demand denied
# - CLM-2024-007890: Demand received, PENDING assignment (not yet assigned)
# - CLM-2024-002468: Liability DENIED, demand denied
# - CLM-2024-013579: CVQ OPEN (active coverage question)
# - CLM-2024-024680: Liability accepted at 100%, demand exceeds limits

MOCK_CLAIMS: Dict[str, Dict[str, Any]] = {
    # ═══════════════════════════════════════════════════════════════════════════
    # GOLDEN PATH - Complete B2B workflow test claim
    # ═══════════════════════════════════════════════════════════════════════════
    # This claim has ALL data populated to allow testing the full inquiry flow:
    # 1. Coverage    → "Is coverage confirmed?" → YES (confirmed)
    # 2. Liability   → "Has liability been accepted?" → YES (80%)
    # 3. Limits      → "Does demand exceed limits?" → NO (demand: $43,847.52, limit: $100k)
    # 4. Payments    → "Any payments made?" → YES ($14,832.00 paid)
    # 5. Demand      → "What's the demand status?" → Under review, assigned
    # 6. Escalation  → "Can this be rushed?" → Qualifies (attorney involved, statute near)
    "CLM-2024-1234": {
        "claim_number": "CLM-2024-1234",
        "insured_name": "Michael Anderson",
        "loss_date": "2024-10-01",
        "claimant_carrier": "Contoso Insurance",
        "claimant_name": "Jennifer Martinez",
        "status": "open",
        # Coverage: CONFIRMED (allows all other inquiries)
        "coverage_status": "confirmed",
        "cvq_status": None,
        # Liability: ACCEPTED at 80% (allows limits disclosure)
        "liability_decision": "accepted",
        "liability_percentage": 80,
        "liability_range_low": 80,
        "liability_range_high": 100,
        # Limits: $100k (demand is below limits)
        "pd_limits": 100000,
        # Payments: YES - partial payment made
        "payments": [
            {"date": "2024-11-15", "amount": 14832.00, "payee": "Contoso Insurance", "type": "subro_partial"},
        ],
        "pd_payments": [
            {"date": "2024-11-15", "amount": 14832.00, "payee": "Contoso Insurance"},
        ],
        # Demand: Received, assigned, under review
        "subro_demand": {
            "received": True,
            "received_date": "2024-10-20",
            "amount": 43847.52,
            "assigned_to": "Sarah Johnson",
            "assigned_date": "2024-10-22",
            "status": "under_review",
        },
        # Feature owners: All assigned
        "feature_owners": {
            "PD": "Sarah Johnson",
            "BI": "David Chen",
            "SUBRO": "Sarah Johnson",
        },
        # Call history: Track prior calls for "third call" rush criterion
        # 3 prior calls = this would be their 4th call, qualifies for rush
        "call_history": [
            {"date": "2024-10-25", "caller": "Jennifer Martinez", "company": "Contoso Insurance", "topic": "demand_status"},
            {"date": "2024-11-05", "caller": "Jennifer Martinez", "company": "Contoso Insurance", "topic": "liability_status"},
            {"date": "2024-11-18", "caller": "Jennifer Martinez", "company": "Contoso Insurance", "topic": "demand_followup"},
        ],
        "prior_call_count": 3,  # This would be the 4th call - auto-qualifies for third-call criterion
    },
    # Scenario 1: Demand under review, liability still pending
    "CLM-2024-001234": {
        "claim_number": "CLM-2024-001234",
        "insured_name": "John Smith",
        "loss_date": "2024-10-15",
        "claimant_carrier": "Contoso Insurance",
        "claimant_name": "Jane Doe",
        "status": "open",
        "coverage_status": "confirmed",
        "cvq_status": None,
        "liability_decision": "pending",
        "liability_percentage": None,
        "liability_range_low": None,
        "liability_range_high": None,
        "pd_limits": 50000,
        "payments": [],
        "pd_payments": [],
        "subro_demand": {
            "received": True,
            "received_date": "2024-11-20",
            "amount": 12500.00,
            "assigned_to": "Sarah Johnson",
            "assigned_date": "2024-11-22",
            "status": "under_review",
        },
        "feature_owners": {
            "PD": "Sarah Johnson",
            "BI": "Mike Thompson",
            "SUBRO": "Sarah Johnson",
        },
    },
    # Scenario 2: Demand PAID, liability accepted 80%
    "CLM-2024-005678": {
        "claim_number": "CLM-2024-005678",
        "insured_name": "Robert Williams",
        "loss_date": "2024-09-01",
        "claimant_carrier": "Fabrikam Insurance",
        "claimant_name": "Emily Chen",
        "status": "open",
        "coverage_status": "confirmed",
        "cvq_status": None,
        "liability_decision": "accepted",
        "liability_percentage": 80,
        "liability_range_low": 80,
        "liability_range_high": 100,
        "pd_limits": 100000,
        "payments": [
            {"date": "2024-10-15", "amount": 8500.00, "payee": "Fabrikam Insurance", "type": "subro"},
        ],
        "pd_payments": [
            {"date": "2024-10-15", "amount": 8500.00, "payee": "Fabrikam Insurance"},
        ],
        "subro_demand": {
            "received": True,
            "received_date": "2024-09-15",
            "amount": 8500.00,
            "assigned_to": "David Brown",
            "assigned_date": "2024-09-16",
            "status": "paid",
        },
        "feature_owners": {
            "PD": "David Brown",
            "BI": None,
            "SUBRO": "David Brown",
        },
    },
    # Scenario 3: NO demand received, coverage pending verification
    "CLM-2024-009012": {
        "claim_number": "CLM-2024-009012",
        "insured_name": "Maria Garcia",
        "loss_date": "2024-11-28",
        "claimant_carrier": "Northwind Insurance",
        "claimant_name": "Tom Wilson",
        "status": "open",
        "coverage_status": "pending",
        "cvq_status": "coverage_verification_pending",
        "liability_decision": "pending",
        "liability_percentage": None,
        "liability_range_low": None,
        "liability_range_high": None,
        "pd_limits": 25000,
        "payments": [],
        "pd_payments": [],
        "subro_demand": {
            "received": False,
        },
        "feature_owners": {
            "PD": "Jennifer Lee",
            "BI": None,
            "SUBRO": None,
        },
    },
    # Scenario 4: Coverage DENIED (policy lapsed), demand denied
    "CLM-2024-003456": {
        "claim_number": "CLM-2024-003456",
        "insured_name": "Kevin O'Brien",
        "loss_date": "2024-08-10",
        "claimant_carrier": "Tailspin Insurance",
        "claimant_name": "Susan Martinez",
        "status": "open",
        "coverage_status": "denied",
        "cvq_status": "policy_lapsed",
        "liability_decision": "not_applicable",
        "liability_percentage": None,
        "liability_range_low": None,
        "liability_range_high": None,
        "pd_limits": 0,
        "payments": [],
        "pd_payments": [],
        "subro_demand": {
            "received": True,
            "received_date": "2024-09-01",
            "amount": 15000.00,
            "assigned_to": None,
            "assigned_date": None,
            "status": "denied_no_coverage",
        },
        "feature_owners": {
            "PD": None,
            "BI": None,
            "SUBRO": None,
        },
    },
    # Scenario 5: Demand received, PENDING assignment (first-come-first-served queue)
    "CLM-2024-007890": {
        "claim_number": "CLM-2024-007890",
        "insured_name": "Angela Torres",
        "loss_date": "2024-12-01",
        "claimant_carrier": "Woodgrove Insurance",
        "claimant_name": "Brian Miller",
        "status": "open",
        "coverage_status": "confirmed",
        "cvq_status": None,
        "liability_decision": "accepted",
        "liability_percentage": 70,
        "liability_range_low": 70,
        "liability_range_high": 80,
        "pd_limits": 50000,
        "payments": [],
        "pd_payments": [],
        "subro_demand": {
            "received": True,
            "received_date": "2024-12-10",
            "amount": 22500.00,
            "assigned_to": None,  # Not yet assigned!
            "assigned_date": None,
            "status": "pending",  # In queue
        },
        "feature_owners": {
            "PD": "Amanda Thompson",
            "BI": None,
            "SUBRO": None,  # No subro handler yet
        },
    },
    # Scenario 6: Liability DENIED, demand denied
    "CLM-2024-002468": {
        "claim_number": "CLM-2024-002468",
        "insured_name": "Christopher Davis",
        "loss_date": "2024-07-20",
        "claimant_carrier": "Litware Insurance",
        "claimant_name": "Diana Park",
        "status": "closed",
        "coverage_status": "confirmed",
        "cvq_status": None,
        "liability_decision": "denied",
        "liability_percentage": 0,
        "liability_range_low": 0,
        "liability_range_high": 0,
        "pd_limits": 75000,
        "payments": [],
        "pd_payments": [],
        "subro_demand": {
            "received": True,
            "received_date": "2024-08-15",
            "amount": 35000.00,
            "assigned_to": "Robert Taylor",
            "assigned_date": "2024-08-17",
            "status": "denied_liability",
        },
        "feature_owners": {
            "PD": "Robert Taylor",
            "BI": None,
            "SUBRO": "Robert Taylor",
        },
    },
    # Scenario 7: CVQ OPEN (active coverage question - need file owner)
    "CLM-2024-013579": {
        "claim_number": "CLM-2024-013579",
        "insured_name": "Patricia White",
        "loss_date": "2024-11-05",
        "claimant_carrier": "Proseware Insurance",
        "claimant_name": "Edward Green",
        "status": "open",
        "coverage_status": "cvq",
        "cvq_status": "named_driver_dispute",
        "liability_decision": "pending",
        "liability_percentage": None,
        "liability_range_low": None,
        "liability_range_high": None,
        "pd_limits": 100000,
        "payments": [],
        "pd_payments": [],
        "subro_demand": {
            "received": True,
            "received_date": "2024-11-25",
            "amount": 45000.00,
            "assigned_to": None,
            "assigned_date": None,
            "status": "pending",  # Held pending CVQ resolution
        },
        "feature_owners": {
            "PD": "Jennifer Martinez",
            "BI": "Michael Chen",
            "SUBRO": None,
        },
    },
    # Scenario 8: Liability accepted 100%, demand EXCEEDS limits
    "CLM-2024-024680": {
        "claim_number": "CLM-2024-024680",
        "insured_name": "Samuel Jackson",
        "loss_date": "2024-06-15",
        "claimant_carrier": "Lucerne Insurance",
        "claimant_name": "Rachel Kim",
        "status": "open",
        "coverage_status": "confirmed",
        "cvq_status": None,
        "liability_decision": "accepted",
        "liability_percentage": 100,
        "liability_range_low": 100,
        "liability_range_high": 100,
        "pd_limits": 25000,  # Low limits
        "payments": [
            {"date": "2024-08-01", "amount": 25000.00, "payee": "Lucerne Insurance", "type": "limits_payment"},
        ],
        "pd_payments": [
            {"date": "2024-08-01", "amount": 25000.00, "payee": "Lucerne Insurance"},
        ],
        "subro_demand": {
            "received": True,
            "received_date": "2024-07-01",
            "amount": 85000.00,  # Demand exceeds $25k limits!
            "assigned_to": "Emily Rodriguez",
            "assigned_date": "2024-07-03",
            "status": "under_review",  # Still open for BI or excess
        },
        "feature_owners": {
            "PD": "Emily Rodriguez",
            "BI": "James Wilson",
            "SUBRO": "Emily Rodriguez",
        },
    },
}
