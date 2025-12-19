"""
auth/acs_auth.py
=========================
Unified authentication for Azure Communication Services (ACS) and Entra ID.
"""

import base64
import json
from functools import cache

import httpx
import jwt
from config import (
    ACS_AUDIENCE,
    ACS_ISSUER,
    ACS_JWKS_URL,
    ALLOWED_CLIENT_IDS,
    ENTRA_AUDIENCE,
    ENTRA_ISSUER,
    ENTRA_JWKS_URL,
)
from fastapi import HTTPException, Request, WebSocket
from fastapi.websockets import WebSocketState
from utils.ml_logging import get_logger

logger = get_logger("orchestration.acs_auth")


class AuthError(Exception):
    """Generic authentication error."""

    pass


@cache
def get_jwks(jwks_url: str) -> list[dict]:
    resp = httpx.get(jwks_url)
    return resp.json()["keys"]


def validate_jwt_token(token: str, jwks_url: str, issuer: str, audience: str) -> dict:
    """Validates JWT using provided JWKS, issuer, and audience."""
    try:
        jwks_client = jwt.PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
        )
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}")
    except Exception as e:
        raise AuthError(f"Token validation failed: {e}")


def extract_bearer_token(authorization_header: str) -> str:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    return authorization_header.split(" ")[1]


def get_easyauth_identity(request: Request) -> dict:
    encoded = request.headers.get("x-ms-client-principal")
    if not encoded:
        raise HTTPException(status_code=401, detail="Missing EasyAuth headers")
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        principal = json.loads(decoded)
        return principal
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid EasyAuth header encoding")


async def validate_entraid_token(request: Request) -> dict:
    """Validates bearer token for Entra ID."""
    auth_header = request.headers.get("Authorization")
    token = extract_bearer_token(auth_header)
    try:
        decoded = validate_jwt_token(
            token, jwks_url=ENTRA_JWKS_URL, issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE
        )
        client_id = decoded.get("azp") or decoded.get("appid")
        if client_id not in ALLOWED_CLIENT_IDS:
            raise HTTPException(status_code=403, detail="Unauthorized client_id")
        logger.info("EntraID request authenticated")
        return decoded
    except AuthError as e:
        logger.warning(f"EntraID validation failed: {e}")
        raise HTTPException(status_code=401, detail=str(e))


def validate_acs_http_auth(request: Request) -> dict:
    """Validates bearer token for ACS HTTP callbacks."""
    auth_header = request.headers.get("Authorization")
    token = extract_bearer_token(auth_header)
    try:
        decoded = validate_jwt_token(
            token, jwks_url=ACS_JWKS_URL, issuer=ACS_ISSUER, audience=ACS_AUDIENCE
        )
        logger.info("ACS HTTP request authenticated")
        return decoded
    except AuthError as e:
        logger.warning(f"ACS HTTP auth failed: {e}")
        raise HTTPException(status_code=401, detail=str(e))


async def validate_acs_ws_auth(ws: WebSocket) -> dict:
    """Validates bearer token for ACS WebSocket handshake."""
    auth_header = ws.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Missing or invalid WebSocket auth header")
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close(code=1008)
        raise AuthError("Missing or invalid WebSocket auth header")

    token = extract_bearer_token(auth_header)
    try:
        decoded = validate_jwt_token(
            token, jwks_url=ACS_JWKS_URL, issuer=ACS_ISSUER, audience=ACS_AUDIENCE
        )
        logger.info("ACS WebSocket authenticated")
        return decoded
    except AuthError as e:
        logger.error(f"WebSocket auth failed: {e}")
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close(code=1011)
        raise
