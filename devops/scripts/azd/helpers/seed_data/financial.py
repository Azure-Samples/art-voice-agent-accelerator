from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from . import SeedTask

DATASET_NAME = "financial"
DATABASE_NAME = "financial_services_db"

MERCHANT_PATTERNS = {
    "pablo_salvador_cfs": {
        "common_merchants": [
            "Microsoft Store",
            "Amazon Business",
            "Delta Airlines",
            "Uber",
            "Starbucks",
            "Best Buy Business",
            "Office Depot",
            "LinkedIn Sales",
            "DocuSign",
            "Zoom",
        ],
        "amounts": (50, 5000),
        "locations": ["Seattle, WA", "Redmond, WA", "San Francisco, CA", "New York, NY"],
    },
    "alice_brown_cfs": {
        "common_merchants": [
            "Microsoft Store",
            "Amazon Business",
            "Delta Airlines",
            "Uber",
            "Starbucks",
            "Best Buy Business",
            "Office Depot",
            "LinkedIn Sales",
            "DocuSign",
            "Zoom",
        ],
        "amounts": (25, 2500),
        "locations": ["Seattle, WA", "Redmond, WA", "San Francisco, CA", "New York, NY"],
    },
    "emily_rivera_gca": {
        "common_merchants": [
            "Charles Schwab",
            "Goldman Sachs",
            "Bloomberg Terminal",
            "American Express Travel",
            "Four Seasons",
            "Whole Foods",
            "Tesla Supercharger",
            "Apple Store",
            "Nordstrom",
        ],
        "amounts": (25, 3000),
        "locations": ["New York, NY", "Boston, MA", "Miami, FL", "Chicago, IL"],
    },
    "jin_lee_cfs": {
        "common_merchants": [
            "Microsoft Store",
            "Amazon Web Services",
            "GitHub",
            "Azure",
            "Starbucks",
            "REI",
            "Alaska Airlines",
            "Costco",
            "Trader Joe's",
            "Steam",
        ],
        "amounts": (25, 2000),
        "locations": ["Seattle, WA", "Bellevue, WA", "Portland, OR", "Vancouver, WA"],
    },
}


def _iso(dt: datetime) -> str:
    """Format a datetime as an ISO-8601 string without microseconds."""
    return dt.replace(microsecond=0).isoformat() + "Z"


def _build_users(anchor: datetime) -> Sequence[dict]:
    """Create 360° financial user profiles."""
    timestamp = _iso(anchor)
    return (
        {
            "_id": "pablo_salvador_cfs",
            "client_id": "pablo_salvador_cfs",
            "full_name": "Pablo Salvador",
            "institution_name": "Contoso Financial Services",
            "company_code": "CFS-12345",
            "company_code_last4": "2345",
            "client_type": "institutional",
            "authorization_level": "senior_advisor",
            "max_transaction_limit": 50_000_000,
            "mfa_required_threshold": 10_000,
            "contact_info": {
                "email": "pablosal@microsoft.com",
                "phone": "+18881231234",
                "preferred_mfa_method": "email",
            },
            "verification_codes": {"ssn4": "1234", "employee_id4": "5678", "phone4": "9907"},
            "mfa_settings": {
                "enabled": True,
                "secret_key": "PHGvTO14Xj_wC79LEWMSrGWuVN5K4HdE_Dzy3S1_0Tc",
                "code_expiry_minutes": 5,
                "max_attempts": 3,
            },
            "compliance": {
                "kyc_verified": True,
                "aml_cleared": True,
                "last_review_date": "2024-10-25",
                "risk_rating": "low",
            },
            "customer_intelligence": {
                "relationship_context": {
                    "relationship_tier": "Platinum",
                    "client_since": "2019-03-15",
                    "relationship_duration_years": 5.7,
                    "lifetime_value": 2_500_000,
                    "satisfaction_score": 96,
                    "previous_interactions": 47,
                },
                "account_status": {
                    "current_balance": 875_000,
                    "ytd_transaction_volume": 12_500_000,
                    "account_health_score": 98,
                    "last_login": "2025-10-26",
                    "login_frequency": "daily",
                },
                "spending_patterns": {
                    "avg_monthly_spend": 125_000,
                    "common_merchants": ["Microsoft Store", "Business Travel", "Tech Vendors"],
                    "preferred_transaction_times": ["9-11 AM", "2-4 PM"],
                    "risk_tolerance": "Conservative",
                    "usual_spending_range": "$1,000 - $25,000",
                },
                "memory_score": {
                    "communication_style": "Direct/Business-focused",
                    "personality_traits": {
                        "patience_level": "Medium",
                        "detail_preference": "High-level summaries",
                        "urgency_style": "Immediate action",
                    },
                    "preferred_resolution_style": "Fast, efficient solutions",
                },
                "fraud_context": {
                    "risk_profile": "Low Risk",
                    "typical_transaction_behavior": {
                        "usual_spending_range": "$1,000 - $25,000",
                        "common_locations": ["Seattle", "Redmond", "San Francisco"],
                        "typical_merchants": ["Tech vendors", "Business services", "Travel"],
                    },
                    "security_preferences": {
                        "preferred_verification": "Email + SMS",
                        "notification_urgency": "Immediate",
                        "card_replacement_speed": "Expedited",
                    },
                    "fraud_history": {
                        "previous_cases": 0,
                        "false_positive_rate": 5,
                        "security_awareness_score": 92,
                    },
                },
                "conversation_context": {
                    "known_preferences": [
                        "Prefers quick summaries over detailed explanations",
                        "Values immediate action on security issues",
                        "Appreciates proactive service",
                    ],
                    "suggested_talking_points": [
                        "Your account shows excellent security practices",
                        "As a platinum client, you receive our fastest service",
                        "Your 5+ year relationship demonstrates our commitment",
                    ],
                },
                "active_alerts": [
                    {
                        "type": "positive_behavior",
                        "message": "Consistent login patterns - excellent security hygiene",
                        "priority": "info",
                    }
                ],
            },
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_login": None,
            "login_attempts": 0,
        },
        {
            "_id": "alice_brown_cfs",
            "client_id": "alice_brown_cfs",
            "full_name": "Alice Brown",
            "institution_name": "Contoso Financial Services",
            "company_code": "CFS-12345",
            "company_code_last4": "1234",
            "client_type": "institutional",
            "authorization_level": "advisor",
            "max_transaction_limit": 10_000_000,
            "mfa_required_threshold": 5_000,
            "contact_info": {},
            "verification_codes": {"ssn4": "5432", "employee_id4": "9876", "phone4": "4441"},
            "mfa_settings": {
                "enabled": True,
                "secret_key": "KL9mR3tP5xY8wQ1aZ7vN2bC6dF4gH0jK",
                "code_expiry_minutes": 5,
                "max_attempts": 3,
            },
            "compliance": {
                "kyc_verified": True,
                "aml_cleared": True,
                "last_review_date": "2024-08-15",
                "risk_rating": "low",
            },
            "customer_intelligence": {
                "relationship_context": {
                    "relationship_tier": "Silver",
                    "client_since": "2022-06-01",
                    "relationship_duration_years": 2.4,
                    "lifetime_value": 450_000,
                    "satisfaction_score": 88,
                    "previous_interactions": 18,
                },
                "account_status": {
                    "current_balance": 285_000,
                    "ytd_transaction_volume": 3_200_000,
                    "account_health_score": 91,
                    "last_login": "2025-10-24",
                    "login_frequency": "3x per week",
                },
                "spending_patterns": {
                    "avg_monthly_spend": 35_000,
                    "common_merchants": [
                        "Microsoft Store",
                        "Amazon Business",
                        "Starbucks",
                        "Office Depot",
                    ],
                    "preferred_transaction_times": ["10-12 PM", "3-5 PM"],
                    "risk_tolerance": "Moderate",
                    "usual_spending_range": "$500 - $8,000",
                },
                "memory_score": {
                    "communication_style": "Analytical/Detail-oriented",
                    "personality_traits": {
                        "patience_level": "High",
                        "detail_preference": "Comprehensive explanations",
                        "urgency_style": "Methodical planning",
                    },
                    "preferred_resolution_style": "Step-by-step with documentation",
                },
                "fraud_context": {
                    "risk_profile": "Low Risk",
                    "typical_transaction_behavior": {
                        "usual_spending_range": "$500 - $8,000",
                        "common_locations": ["Seattle", "Bellevue", "Portland"],
                        "typical_merchants": [
                            "Tech vendors",
                            "Office supplies",
                            "Corporate dining",
                        ],
                    },
                    "security_preferences": {
                        "preferred_verification": "SMS + Security questions",
                        "notification_urgency": "Standard",
                        "card_replacement_speed": "Standard",
                    },
                    "fraud_history": {
                        "previous_cases": 0,
                        "false_positive_rate": 8,
                        "security_awareness_score": 89,
                    },
                },
                "conversation_context": {
                    "known_preferences": [
                        "Appreciates detailed explanations and documentation",
                        "Prefers to understand security processes thoroughly",
                        "Values educational approach to financial services",
                    ],
                    "suggested_talking_points": [
                        "Your methodical approach to security is commendable",
                        "As a growing client, we're here to support your expanding needs",
                        "Your attention to detail helps us provide better service",
                    ],
                },
                "active_alerts": [
                    {
                        "type": "account_growth",
                        "message": "Account shows steady growth - consider gold tier benefits",
                        "priority": "low",
                    }
                ],
            },
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_login": None,
            "login_attempts": 0,
        },
        {
            "_id": "emily_rivera_gca",
            "client_id": "emily_rivera_gca",
            "full_name": "Emily Rivera",
            "institution_name": "Global Capital Advisors",
            "company_code": "GCA-67890",
            "company_code_last4": "7890",
            "client_type": "institutional",
            "authorization_level": "senior_advisor",
            "max_transaction_limit": 25_000_000,
            "mfa_required_threshold": 5_000,
            "contact_info": {
                "email": "emily.rivera@globalcapital.com",
                "phone": "+15551234567",
                "preferred_mfa_method": "sms",
            },
            "verification_codes": {"ssn4": "9876", "employee_id4": "4321", "phone4": "4567"},
            "mfa_settings": {
                "enabled": True,
                "secret_key": "QF8mK2vWd1Xj9BcN7RtY6Lp3Hs4Zq8Uv5Aw0Er2Ty7",
                "code_expiry_minutes": 5,
                "max_attempts": 3,
            },
            "compliance": {
                "kyc_verified": True,
                "aml_cleared": True,
                "last_review_date": "2024-09-30",
                "risk_rating": "low",
            },
            "customer_intelligence": {
                "relationship_context": {
                    "relationship_tier": "Gold",
                    "client_since": "2021-01-20",
                    "relationship_duration_years": 3.8,
                    "lifetime_value": 950_000,
                    "satisfaction_score": 89,
                    "previous_interactions": 23,
                },
                "account_status": {
                    "current_balance": 340_000,
                    "ytd_transaction_volume": 5_800_000,
                    "account_health_score": 94,
                    "last_login": "2025-10-25",
                    "login_frequency": "weekly",
                },
                "spending_patterns": {
                    "avg_monthly_spend": 65_000,
                    "common_merchants": [
                        "Charles Schwab",
                        "Goldman Sachs",
                        "Bloomberg Terminal",
                        "American Express Travel",
                        "Four Seasons",
                        "Whole Foods",
                        "Tesla Supercharger",
                        "Apple Store",
                        "Nordstrom",
                    ],
                    "preferred_transaction_times": ["8-10 AM", "1-3 PM"],
                    "risk_tolerance": "Moderate",
                    "usual_spending_range": "$500 - $15,000",
                },
                "memory_score": {
                    "communication_style": "Relationship-oriented",
                    "personality_traits": {
                        "patience_level": "High",
                        "detail_preference": "Moderate detail with examples",
                        "urgency_style": "Collaborative discussion",
                    },
                    "preferred_resolution_style": "Thorough explanation with options",
                },
                "fraud_context": {
                    "risk_profile": "Low Risk",
                    "typical_transaction_behavior": {
                        "usual_spending_range": "$500 - $15,000",
                        "common_locations": ["New York", "Boston", "Miami"],
                        "typical_merchants": [
                            "Financial services",
                            "Investment platforms",
                            "Business travel",
                        ],
                    },
                    "security_preferences": {
                        "preferred_verification": "SMS + Email backup",
                        "notification_urgency": "Standard",
                        "card_replacement_speed": "Standard",
                    },
                    "fraud_history": {
                        "previous_cases": 1,
                        "false_positive_rate": 12,
                        "security_awareness_score": 87,
                    },
                },
                "conversation_context": {
                    "known_preferences": [
                        "Appreciates being walked through processes step-by-step",
                        "Values relationship-building in conversations",
                        "Prefers understanding 'why' behind security measures",
                    ],
                    "suggested_talking_points": [
                        "Your diligent monitoring helps us serve you better",
                        "As a gold client, we value your partnership",
                        "Your previous fraud case was resolved quickly thanks to your cooperation",
                    ],
                },
                "active_alerts": [
                    {
                        "type": "account_optimization",
                        "message": "Account eligible for platinum tier upgrade",
                        "priority": "medium",
                    }
                ],
            },
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_login": None,
            "login_attempts": 0,
        },
        {
            "_id": "jin_lee_cfs",
            "client_id": "jin_lee_cfs",
            "full_name": "Jin Lee",
            "institution_name": "Contoso Financial Services",
            "company_code": "CFS-83601",
            "company_code_last4": "3601",
            "client_type": "individual",
            "authorization_level": "primary",
            "max_transaction_limit": 5_000_000,
            "mfa_required_threshold": 2_500,
            "contact_info": {
                "email": "jinle@microsoft.com",
                "phone": "+14258360123",
                "preferred_mfa_method": "sms",
            },
            "verification_codes": {"ssn4": "8360", "employee_id4": "7942", "phone4": "0123"},
            "mfa_settings": {
                "enabled": True,
                "secret_key": "JL8xR3tP5xY8wQ1aZ7vN2bC6dF4gH0jKm9Yz2Wq",
                "code_expiry_minutes": 5,
                "max_attempts": 3,
            },
            "compliance": {
                "kyc_verified": True,
                "aml_cleared": True,
                "last_review_date": "2024-11-01",
                "risk_rating": "low",
            },
            "customer_intelligence": {
                "relationship_context": {
                    "relationship_tier": "Gold",
                    "client_since": "2022-06-15",
                    "relationship_duration_years": 2.5,
                    "lifetime_value": 450_000,
                    "satisfaction_score": 92,
                    "previous_interactions": 18,
                },
                "account_status": {
                    "current_balance": 125_000,
                    "ytd_transaction_volume": 850_000,
                    "account_health_score": 94,
                    "last_login": "2025-01-10",
                    "login_frequency": "weekly",
                },
                "spending_patterns": {
                    "avg_monthly_spend": 15_000,
                    "common_merchants": ["Tech Stores", "Travel", "Software Services"],
                    "preferred_transaction_times": ["10-12 PM", "3-5 PM"],
                    "risk_tolerance": "Moderate",
                    "usual_spending_range": "$500 - $5,000",
                },
                "memory_score": {
                    "communication_style": "Clear/Technical",
                    "personality_traits": {
                        "patience_level": "High",
                        "detail_preference": "Technical details appreciated",
                        "urgency_style": "Methodical approach",
                    },
                    "preferred_resolution_style": "Thorough explanation with options",
                },
                "fraud_context": {
                    "risk_profile": "Low Risk",
                    "typical_transaction_behavior": {
                        "usual_spending_range": "$500 - $5,000",
                        "common_locations": ["Seattle", "Bellevue", "Portland"],
                        "typical_merchants": ["Tech vendors", "Cloud services", "Travel"],
                    },
                    "security_preferences": {
                        "preferred_verification": "SMS",
                        "notification_urgency": "Standard",
                        "card_replacement_speed": "Standard",
                    },
                    "fraud_history": {
                        "previous_cases": 0,
                        "false_positive_rate": 3,
                        "security_awareness_score": 95,
                    },
                },
                "conversation_context": {
                    "known_preferences": [
                        "Appreciates technical accuracy",
                        "Values clear step-by-step guidance",
                        "Prefers self-service options when available",
                    ],
                    "suggested_talking_points": [
                        "Your account security practices are excellent",
                        "As a gold member, you have access to priority support",
                        "Your technical background means we can provide detailed explanations",
                    ],
                },
                "active_alerts": [],
            },
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_login": None,
            "login_attempts": 0,
        },
    )


def _build_transactions(
    users: Sequence[dict],
    anchor: datetime,
    rng: random.Random,
    per_user: int,
) -> Sequence[dict]:
    """Generate synthetic transaction history for each client."""
    documents: list[dict] = []
    for user in users:
        client_id = user["client_id"]
        client_name = user["full_name"]
        pattern = MERCHANT_PATTERNS.get(client_id, MERCHANT_PATTERNS["pablo_salvador_cfs"])
        end_date = anchor
        for index in range(per_user):
            days_ago = rng.randint(1, 90)
            transaction_date = end_date - timedelta(days=days_ago)
            if rng.random() < 0.8:
                hour = rng.choice([9, 10, 11, 14, 15, 16])
            else:
                hour = rng.randint(0, 23)
            transaction_date = transaction_date.replace(
                hour=hour,
                minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
            )
            merchant = rng.choice(pattern["common_merchants"])
            amount = round(rng.uniform(*pattern["amounts"]), 2)
            transaction_type = rng.choices(
                ["purchase", "transfer", "payment", "withdrawal"],
                weights=[70, 15, 10, 5],
            )[0]
            risk_score = rng.choices([10, 25, 45, 75, 90], weights=[60, 25, 10, 4, 1])[0]
            document = {
                "_id": f"txn_{client_id}_{index + 1:03d}",
                "transaction_id": f"TXN_{rng.randint(100000, 999999)}",
                "client_id": client_id,
                "client_name": client_name,
                "amount": amount,
                "currency": "USD",
                "merchant_name": merchant,
                "merchant_category": "retail" if "Store" in merchant else "services",
                "transaction_type": transaction_type,
                "transaction_date": _iso(transaction_date),
                "location": rng.choice(pattern["locations"]),
                "card_last_4": rng.choice(["2401", "7890", "1234"]),
                "status": rng.choices(["completed", "pending", "failed"], weights=[85, 10, 5])[0],
                "risk_score": risk_score,
                "risk_factors": [],
                "fraud_flags": [],
                "created_at": _iso(anchor),
            }
            if risk_score > 70:
                document["risk_factors"] = ["unusual_amount", "new_merchant"]
                document["fraud_flags"] = ["requires_review"]
            elif risk_score > 40:
                document["risk_factors"] = ["off_hours_transaction"]
            documents.append(document)
    documents.sort(key=lambda item: item["transaction_date"], reverse=True)
    return tuple(documents)


def _build_fraud_cases(anchor: datetime) -> Sequence[dict]:
    """Provide fraud case fixtures aligned with the notebook dataset."""
    reported = anchor - timedelta(days=45)
    resolved = anchor - timedelta(days=30)
    return (
        {
            "_id": "FRAUD-001-2024",
            "case_id": "FRAUD-001-2024",
            "client_id": "emily_rivera_gca",
            "client_name": "Emily Rivera",
            "fraud_type": "card_fraud",
            "status": "resolved",
            "priority": "high",
            "description": "Suspicious transactions detected at gas stations in different states",
            "reported_date": _iso(reported),
            "resolution_date": _iso(resolved),
            "estimated_loss": 456.78,
            "actual_loss": 0.00,
            "affected_transactions": ["TXN_123456", "TXN_123457"],
            "actions_taken": [
                "Card blocked immediately",
                "Replacement card shipped expedited",
                "Transactions disputed and reversed",
                "Enhanced monitoring enabled",
            ],
            "investigator": "Sarah Johnson",
            "resolution_notes": (
                "Confirmed fraudulent transactions. Card skimming device detected at affected gas stations. "
                "Customer fully reimbursed."
            ),
            "created_at": _iso(reported),
            "updated_at": _iso(resolved),
        },
    )


def _build_card_orders(anchor: datetime) -> Sequence[dict]:
    """Create card replacement order fixtures."""
    created = anchor - timedelta(days=35)
    shipped = anchor - timedelta(days=33)
    delivered = anchor - timedelta(days=31)
    return (
        {
            "_id": "CARD-ORD-001",
            "order_id": "CARD-ORD-001",
            "client_id": "emily_rivera_gca",
            "client_name": "Emily Rivera",
            "reason": "fraud_detected",
            "card_type": "business_credit",
            "card_last_4": "7890",
            "replacement_card_last_4": "3456",
            "shipping_priority": "expedited",
            "shipping_address": {
                "street": "456 Wall Street",
                "city": "New York",
                "state": "NY",
                "zip_code": "10005",
                "country": "USA",
            },
            "tracking_number": "1Z999AA1234567890",
            "carrier": "UPS",
            "order_date": _iso(created),
            "shipped_date": _iso(shipped),
            "estimated_delivery": _iso(delivered),
            "actual_delivery": _iso(delivered),
            "status": "delivered",
            "fraud_case_id": "FRAUD-001-2024",
            "cost": 25.00,
            "created_at": _iso(created),
            "updated_at": _iso(anchor - timedelta(days=30)),
        },
    )


def _build_mfa_sessions(anchor: datetime) -> Sequence[dict]:
    """Create MFA session fixtures supporting auth flows."""
    sent_at = anchor - timedelta(minutes=10)
    verified_at = anchor - timedelta(minutes=8)
    return (
        {
            "_id": "MFA-SESSION-001",
            "session_id": "MFA-SESSION-001",
            "client_id": "pablo_salvador_cfs",
            "client_name": "Pablo Salvador",
            "auth_method": "email",
            "verification_code": "123456",
            "code_sent_at": _iso(sent_at),
            "code_expires_at": _iso(anchor + timedelta(minutes=5)),
            "attempts_made": 1,
            "max_attempts": 3,
            "status": "verified",
            "verified_at": _iso(verified_at),
            "ip_address": "192.168.1.100",
            "user_agent": "VoiceAgent/1.0",
            "created_at": _iso(sent_at),
            "updated_at": _iso(verified_at),
        },
        {
            "_id": "MFA-SESSION-002",
            "session_id": "MFA-SESSION-002",
            "client_id": "alice_brown_cfs",
            "client_name": "Alice Brown",
            "auth_method": "sms",
            "verification_code": "789012",
            "code_sent_at": _iso(anchor - timedelta(minutes=3)),
            "code_expires_at": _iso(anchor + timedelta(minutes=2)),
            "attempts_made": 1,
            "max_attempts": 3,
            "status": "pending",
            "verified_at": None,
            "ip_address": "10.0.0.25",
            "user_agent": "VoiceAgent/1.0",
            "created_at": _iso(anchor - timedelta(minutes=3)),
            "updated_at": _iso(anchor - timedelta(minutes=3)),
        },
    )


def _build_transfer_agency_clients(anchor: datetime) -> Sequence[dict]:
    """Create institutional transfer-agency client fixtures."""
    timestamp = _iso(anchor)
    return ()


def _build_drip_positions(anchor: datetime) -> Sequence[dict]:
    """Create DRIP investment position fixtures."""
    timestamp = _iso(anchor)
    return (
        {
            "_id": "drip_pablo_msft",
            "client_id": "pablo_salvador_cfs",
            "client_code": "CFS-12345",
            "symbol": "MSFT",
            "company_name": "Microsoft Corporation",
            "shares": 542.0,
            "cost_basis_per_share": 280.15,
            "last_dividend": 3.00,
            "dividend_date": "2024-09-15",
            "current_price": 415.50,
            "market_value": 225_201.00,
            "dividend_yield": 0.72,
            "position_type": "drip",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        {
            "_id": "drip_pablo_aapl",
            "client_id": "pablo_salvador_cfs",
            "client_code": "CFS-12345",
            "symbol": "AAPL",
            "company_name": "Apple Inc",
            "shares": 890.25,
            "cost_basis_per_share": 145.30,
            "last_dividend": 0.25,
            "dividend_date": "2024-08-15",
            "current_price": 189.45,
            "market_value": 168_613.86,
            "dividend_yield": 0.53,
            "position_type": "drip",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        {
            "_id": "drip_alice_msft",
            "client_id": "alice_brown_cfs",
            "client_code": "CFS-12345",
            "symbol": "MSFT",
            "company_name": "Microsoft Corporation",
            "shares": 225.0,
            "cost_basis_per_share": 295.80,
            "last_dividend": 3.00,
            "dividend_date": "2024-09-15",
            "current_price": 415.50,
            "market_value": 93_487.50,
            "dividend_yield": 0.72,
            "position_type": "drip",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        {
            "_id": "drip_emily_pltr",
            "client_id": "emily_rivera_gca",
            "client_code": "GCA-48273",
            "symbol": "PLTR",
            "company_name": "Palantir Technologies",
            "shares": 1078.42,
            "cost_basis_per_share": 11.42,
            "last_dividend": 0.08,
            "dividend_date": "2024-08-30",
            "current_price": 12.85,
            "market_value": 13_857.70,
            "dividend_yield": 0.62,
            "position_type": "drip",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        {
            "_id": "drip_emily_msft",
            "client_id": "emily_rivera_gca",
            "client_code": "GCA-48273",
            "symbol": "MSFT",
            "company_name": "Microsoft Corporation",
            "shares": 542.0,
            "cost_basis_per_share": 280.15,
            "last_dividend": 3.00,
            "dividend_date": "2024-09-15",
            "current_price": 415.50,
            "market_value": 225_201.00,
            "dividend_yield": 0.72,
            "position_type": "drip",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        {
            "_id": "drip_emily_tsla",
            "client_id": "emily_rivera_gca",
            "client_code": "GCA-48273",
            "symbol": "TSLA",
            "company_name": "Tesla Inc",
            "shares": 12.75,
            "cost_basis_per_share": 195.80,
            "last_dividend": 0.0,
            "dividend_date": None,
            "current_price": 248.90,
            "market_value": 3_173.48,
            "dividend_yield": 0.0,
            "position_type": "growth_drip",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )


def _build_compliance_records(anchor: datetime) -> Sequence[dict]:
    """Create compliance tracking documents."""
    timestamp = _iso(anchor)
    return (
        {
            "_id": "compliance_pablo_2024",
            "client_id": "pablo_salvador_cfs",
            "client_code": "CFS-12345",
            "compliance_year": 2024,
            "aml_status": "compliant",
            "aml_last_review": "2024-06-15",
            "aml_expiry": "2025-12-31",
            "aml_reviewer": "Sarah Johnson",
            "fatca_status": "compliant",
            "fatca_last_update": "2024-01-10",
            "w8ben_status": "current",
            "w8ben_expiry": "2026-06-15",
            "kyc_verified": True,
            "kyc_last_update": "2024-05-20",
            "risk_assessment": "low",
            "sanctions_check": "clear",
            "pep_status": "no",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        {
            "_id": "compliance_alice_2024",
            "client_id": "alice_brown_cfs",
            "client_code": "CFS-12345",
            "compliance_year": 2024,
            "aml_status": "compliant",
            "aml_last_review": "2024-08-15",
            "aml_expiry": "2025-08-31",
            "aml_reviewer": "Robert Davis",
            "fatca_status": "compliant",
            "fatca_last_update": "2024-06-01",
            "w8ben_status": "current",
            "w8ben_expiry": "2026-02-15",
            "kyc_verified": True,
            "kyc_last_update": "2024-07-10",
            "risk_assessment": "low",
            "sanctions_check": "clear",
            "pep_status": "no",
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        {
            "_id": "compliance_emily_2024",
            "client_id": "emily_rivera_gca",
            "client_code": "GCA-48273",
            "compliance_year": 2024,
            "aml_status": "expiring_soon",
            "aml_last_review": "2024-10-01",
            "aml_expiry": "2025-10-31",
            "aml_reviewer": "Michael Chen",
            "fatca_status": "compliant",
            "fatca_last_update": "2024-03-01",
            "w8ben_status": "current",
            "w8ben_expiry": "2026-03-15",
            "kyc_verified": True,
            "kyc_last_update": "2024-02-28",
            "risk_assessment": "low",
            "sanctions_check": "clear",
            "pep_status": "no",
            "requires_review": True,
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )


def get_seed_tasks(options: Mapping[str, object]) -> Sequence[SeedTask]:
    """Return seed tasks for the financial dataset."""
    anchor = datetime.utcnow()
    rng = random.Random(int(options.get("seed", 42)))
    per_user = int(options.get("transactions_per_client", 75))
    users = _build_users(anchor)
    transactions = _build_transactions(users, anchor, rng, per_user)
    fraud_cases = _build_fraud_cases(anchor)
    card_orders = _build_card_orders(anchor)
    mfa_sessions = _build_mfa_sessions(anchor)
    drip_positions = _build_drip_positions(anchor)
    compliance_records = _build_compliance_records(anchor)
    return (
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="users",
            documents=users,
            id_field="_id",
        ),
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="transactions",
            documents=transactions,
            id_field="_id",
        ),
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="fraud_cases",
            documents=fraud_cases,
            id_field="_id",
        ),
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="card_orders",
            documents=card_orders,
            id_field="_id",
        ),
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="mfa_sessions",
            documents=mfa_sessions,
            id_field="_id",
        ),
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="drip_positions",
            documents=drip_positions,
            id_field="_id",
        ),
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="compliance_records",
            documents=compliance_records,
            id_field="_id",
        ),
    )
