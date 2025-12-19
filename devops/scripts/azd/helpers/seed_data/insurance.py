from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from . import SeedTask

DATASET_NAME = "insurance"
DATABASE_NAME = "voice_agent_db"


def _utc_iso(dt: datetime | None = None) -> str:
    """Convert the supplied timestamp (or now) into an ISO-8601 string."""
    dt = dt or datetime.utcnow()
    return dt.replace(microsecond=0).isoformat() + "Z"


def _policyholder_documents(include_duplicates: bool) -> Sequence[dict]:
    """Assemble policyholder documents, optionally adding duplicate fixtures."""
    documents = [
        {
            "_id": "jane_smith",
            "full_name": "Jane Smith",
            "zip": "60601",
            "ssn4": "5678",
            "policy4": "0001",
            "claim4": "9876",
            "phone4": "1078",
            "policy_id": "POL-A10001",
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
        },
        {
            "_id": "alice_brown",
            "full_name": "Alice Brown",
            "zip": "60601",
            "ssn4": "1234",
            "policy4": "0002",
            "claim4": "3344",
            "phone4": "4555",
            "policy_id": "POL-A20002",
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
        },
        {
            "_id": "carlos_rivera",
            "full_name": "Carlos Rivera",
            "zip": "60601",
            "ssn4": "7890",
            "policy4": "4455",
            "claim4": "1122",
            "phone4": "9200",
            "policy_id": "POL-C88230",
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
        },
    ]
    duplicates = [
        {
            "_id": "alice_brown_chicago",
            "full_name": "Alice Brown",
            "zip": "60622",
            "ssn4": "5678",
            "policy4": "0002",
            "claim4": "4321",
            "phone4": "2468",
            "policy_id": "POL-A20002",
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
        },
        {
            "_id": "alice_brown_milwaukee",
            "full_name": "Alice Brown",
            "zip": "53201",
            "ssn4": "9999",
            "policy4": "0003",
            "claim4": "2222",
            "phone4": "3333",
            "policy_id": "POL-A30003",
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
        },
    ]
    if include_duplicates:
        return (*documents, *duplicates)
    return tuple(documents)


def _policy_documents() -> Sequence[dict]:
    """Build policy documents for the insurance dataset."""
    return (
        {
            "_id": "POL-A10001",
            "policy_id": "POL-A10001",
            "policyholder_name": "Jane Smith",
            "policy_type": "Auto Insurance",
            "coverage": {
                "liability": "$100,000/$300,000",
                "collision": "$1,000 deductible",
                "comprehensive": "$500 deductible",
                "personal_injury_protection": "$50,000",
            },
            "vehicles": [
                {
                    "year": 2019,
                    "make": "Honda",
                    "model": "Civic",
                    "vin": "1HGBH41JXMN109186",
                }
            ],
            "premium": {"monthly": 125.50, "annual": 1506.00},
            "status": "active",
            "effective_date": "2023-01-15",
            "expiration_date": "2024-01-15",
            "claims_history": [
                {
                    "claim_id": "CLM-A10001-9876",
                    "date": "2023-06-15",
                    "type": "collision",
                    "amount": 3200.00,
                    "status": "closed",
                }
            ],
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
        },
        {
            "_id": "POL-A20002",
            "policy_id": "POL-A20002",
            "policyholder_name": "Alice Brown",
            "policy_type": "Home Insurance",
            "coverage": {
                "dwelling": "$350,000",
                "personal_property": "$175,000",
                "liability": "$300,000",
                "medical_payments": "$5,000",
                "loss_of_use": "$70,000",
            },
            "property": {
                "address": "123 Oak Street, Chicago, IL 60601",
                "type": "Single Family Home",
                "year_built": 1995,
                "square_feet": 2200,
            },
            "premium": {"monthly": 183.33, "annual": 2200.00},
            "deductible": 1000,
            "status": "active",
            "effective_date": "2023-03-01",
            "expiration_date": "2024-03-01",
            "claims_history": [
                {
                    "claim_id": "CLM-A20002-3344",
                    "date": "2023-08-20",
                    "type": "water damage",
                    "amount": 5800.00,
                    "status": "closed",
                }
            ],
            "coverage_details": {
                "rental_reimbursement": {
                    "coverage": "$100/day for up to 24 months",
                    "description": "Coverage for temporary housing expenses if your home becomes uninhabitable due to a covered loss",
                }
            },
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
        },
        {
            "_id": "POL-A30003",
            "policy_id": "POL-A30003",
            "policyholder_name": "Alice Brown",
            "policy_type": "Life Insurance",
            "coverage": {
                "death_benefit": "$500,000",
                "type": "Term Life",
                "term_length": "20 years",
            },
            "premium": {"monthly": 45.00, "annual": 540.00},
            "beneficiaries": [{"name": "John Brown", "relationship": "Spouse", "percentage": 100}],
            "status": "active",
            "effective_date": "2022-03-10",
            "expiration_date": "2042-03-10",
            "claims_history": [],
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
        },
    )


def get_seed_tasks(options: Mapping[str, object]) -> Sequence[SeedTask]:
    """Return seeding tasks for the insurance dataset."""
    include_duplicates = bool(options.get("include_duplicates", False))
    policyholders = _policyholder_documents(include_duplicates=include_duplicates)
    policies = _policy_documents()
    return (
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="policyholders",
            documents=policyholders,
            id_field="_id",
        ),
        SeedTask(
            dataset=DATASET_NAME,
            database=DATABASE_NAME,
            collection="policies",
            documents=policies,
            id_field="_id",
        ),
    )
