"""
Transfer Agency Tools
=====================

Tools for institutional transfer agency services, DRIP liquidations,
and compliance checks for institutional clients.
"""

from __future__ import annotations

from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.transfer_agency")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

get_drip_positions_schema: dict[str, Any] = {
    "name": "get_drip_positions",
    "description": (
        "Get dividend reinvestment plan (DRIP) positions for an institutional client. "
        "Returns holdings, share counts, and current values."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_code": {
                "type": "string",
                "description": "Institutional client code (e.g., GCA-48273)",
            },
        },
        "required": ["client_code"],
    },
}

calculate_liquidation_proceeds_schema: dict[str, Any] = {
    "name": "calculate_liquidation_proceeds",
    "description": (
        "Calculate estimated proceeds from liquidating DRIP positions. "
        "Includes tax estimates and net proceeds."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_code": {
                "type": "string",
                "description": "Institutional client code",
            },
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Stock symbols to liquidate",
            },
            "shares": {
                "type": "object",
                "description": "Dict of symbol -> share count to liquidate",
            },
        },
        "required": ["client_code", "symbols"],
    },
}

verify_institutional_identity_schema: dict[str, Any] = {
    "name": "verify_institutional_identity",
    "description": (
        "Verify institutional client identity using client code and authorization. "
        "Required before processing liquidation requests."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_code": {
                "type": "string",
                "description": "Institutional client code",
            },
            "authorization_code": {
                "type": "string",
                "description": "Authorization or PIN code",
            },
            "caller_name": {
                "type": "string",
                "description": "Name of authorized caller",
            },
        },
        "required": ["client_code"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK DATA
# ═══════════════════════════════════════════════════════════════════════════════

_MOCK_DRIP_POSITIONS = {
    "GCA-48273": [
        {
            "symbol": "AAPL",
            "company": "Apple Inc.",
            "shares": 125.5,
            "current_price": 178.50,
            "market_value": 22392.75,
            "cost_basis": 15000.00,
            "acquisition_date": "2019-03-15",
        },
        {
            "symbol": "MSFT",
            "company": "Microsoft Corporation",
            "shares": 85.25,
            "current_price": 375.00,
            "market_value": 31968.75,
            "cost_basis": 20000.00,
            "acquisition_date": "2020-06-01",
        },
        {
            "symbol": "JNJ",
            "company": "Johnson & Johnson",
            "shares": 200.0,
            "current_price": 155.25,
            "market_value": 31050.00,
            "cost_basis": 28000.00,
            "acquisition_date": "2018-01-20",
        },
    ],
    "GCA-55912": [
        {
            "symbol": "PG",
            "company": "Procter & Gamble",
            "shares": 150.0,
            "current_price": 148.00,
            "market_value": 22200.00,
            "cost_basis": 18500.00,
            "acquisition_date": "2019-09-10",
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def get_drip_positions(args: dict[str, Any]) -> dict[str, Any]:
    """Get DRIP positions for institutional client."""
    client_code = (args.get("client_code") or "").strip().upper()

    if not client_code:
        return {"success": False, "message": "client_code is required."}

    positions = _MOCK_DRIP_POSITIONS.get(client_code)
    if not positions:
        return {
            "success": False,
            "message": f"No positions found for client code {client_code}",
        }

    total_value = sum(p["market_value"] for p in positions)
    total_cost = sum(p["cost_basis"] for p in positions)

    logger.info("📊 DRIP positions retrieved: %s - %d positions", client_code, len(positions))

    return {
        "success": True,
        "client_code": client_code,
        "positions": positions,
        "total_market_value": total_value,
        "total_cost_basis": total_cost,
        "unrealized_gain": total_value - total_cost,
    }


async def calculate_liquidation_proceeds(args: dict[str, Any]) -> dict[str, Any]:
    """Calculate liquidation proceeds for DRIP positions."""
    client_code = (args.get("client_code") or "").strip().upper()
    symbols = args.get("symbols", [])
    shares_dict = args.get("shares", {})

    if not client_code:
        return {"success": False, "message": "client_code is required."}
    if not symbols:
        return {"success": False, "message": "symbols list is required."}

    positions = _MOCK_DRIP_POSITIONS.get(client_code, [])
    if not positions:
        return {"success": False, "message": f"No positions for {client_code}"}

    # Calculate proceeds for each symbol
    liquidation_details = []
    total_proceeds = 0.0
    total_gain = 0.0

    for pos in positions:
        if pos["symbol"] in [s.upper() for s in symbols]:
            shares_to_sell = shares_dict.get(pos["symbol"], pos["shares"])
            proceeds = shares_to_sell * pos["current_price"]
            cost = shares_to_sell * (pos["cost_basis"] / pos["shares"])
            gain = proceeds - cost

            liquidation_details.append(
                {
                    "symbol": pos["symbol"],
                    "shares": shares_to_sell,
                    "price": pos["current_price"],
                    "gross_proceeds": proceeds,
                    "cost_basis": cost,
                    "estimated_gain": gain,
                    "estimated_tax": gain * 0.15 if gain > 0 else 0,  # Simplified LTCG
                }
            )

            total_proceeds += proceeds
            total_gain += gain

    estimated_tax = total_gain * 0.15 if total_gain > 0 else 0

    logger.info("💰 Liquidation calculated: %s - $%.2f gross", client_code, total_proceeds)

    return {
        "success": True,
        "client_code": client_code,
        "details": liquidation_details,
        "summary": {
            "gross_proceeds": total_proceeds,
            "total_gain": total_gain,
            "estimated_tax": estimated_tax,
            "net_proceeds": total_proceeds - estimated_tax,
        },
        "note": "Actual proceeds may vary based on execution price and final tax calculation.",
    }


async def verify_institutional_identity(args: dict[str, Any]) -> dict[str, Any]:
    """Verify institutional client identity."""
    client_code = (args.get("client_code") or "").strip().upper()
    auth_code = (args.get("authorization_code") or "").strip()
    caller_name = (args.get("caller_name") or "").strip()

    if not client_code:
        return {"success": False, "message": "client_code is required."}

    # Simulate verification
    is_valid = client_code in _MOCK_DRIP_POSITIONS

    if is_valid:
        logger.info("✓ Institutional identity verified: %s", client_code)
        return {
            "success": True,
            "verified": True,
            "client_code": client_code,
            "account_type": "Institutional DRIP",
            "caller_name": caller_name or "Authorized Representative",
            "authorization_level": "full",
        }

    logger.warning("✗ Institutional verification failed: %s", client_code)
    return {
        "success": False,
        "verified": False,
        "message": f"Unable to verify client code {client_code}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "get_drip_positions",
    get_drip_positions_schema,
    get_drip_positions,
    tags={"transfer_agency", "drip"},
)
register_tool(
    "calculate_liquidation_proceeds",
    calculate_liquidation_proceeds_schema,
    calculate_liquidation_proceeds,
    tags={"transfer_agency", "liquidation"},
)
register_tool(
    "verify_institutional_identity",
    verify_institutional_identity_schema,
    verify_institutional_identity,
    tags={"transfer_agency", "auth"},
)
