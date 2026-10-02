"""Fail-closed authentication for the public telephony exceptions at Front Door."""

import asyncio
import hmac
import json
import re
from time import monotonic
from typing import Any
from uuid import UUID

import httpx
import jwt
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from utils.ml_logging import get_logger

logger = get_logger(__name__)

ACS_ISSUER = "https://acscallautomation.communication.azure.com"
ACS_JWKS_URL = f"{ACS_ISSUER}/calling/keys"
ACS_CALLBACK_PATH = "/api/v1/calls/callbacks"
ACS_MEDIA_PATH = "/api/v1/media/stream"
EVENT_GRID_PATH = "/api/v1/calls/answer"
EVENT_GRID_SECRET_HEADER = "X-EventGrid-Webhook-Secret"
_VALIDATION_EVENT = "Microsoft.EventGrid.SubscriptionValidationEvent"
_INCOMING_CALL_EVENT = "Microsoft.Communication.IncomingCall"
_AUTHENTICATED = object()
_AUTH_SCOPE_KEY = "artagent.authenticated_telephony"
_MAX_BODY_BYTES = 1024 * 1024
_MAX_JWKS_BYTES = 64 * 1024
_JWKS_TIMEOUT_SECONDS = 5.0
_BODY_TIMEOUT_SECONDS = 5.0


class TelephonyAuthError(Exception):
    """The telephony credential or payload could not be authenticated."""


def validate_front_door_auth_config(audience: str, resource_id: str, webhook_secret: str) -> None:
    """Reject missing or invalid security configuration before serving requests."""
    try:
        if UUID(audience).int == 0:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValueError("ACS_AUDIENCE must be the ACS immutable resource UUID") from exc
    if not re.fullmatch(
        r"/subscriptions/[0-9a-f-]{36}/resourcegroups/[^/]+"
        r"/providers/microsoft\.communication/communicationservices/[^/]+",
        resource_id,
        flags=re.IGNORECASE,
    ):
        raise ValueError("ACS_ARM_RESOURCE_ID must be the full ACS ARM resource ID")
    if (
        not 32 <= len(webhook_secret) <= 4096
        or not webhook_secret.isascii()
        or not all(33 <= ord(char) <= 126 for char in webhook_secret)
    ):
        raise ValueError(
            "EVENT_GRID_WEBHOOK_SECRET must contain 32-4096 printable non-space ASCII characters"
        )


class ACSJWTValidator:
    """Cache pinned ACS signing keys with bounded asynchronous refreshes."""

    def __init__(self, audience: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.audience = audience
        self._client = client
        self._owns_client = client is None
        self._keys: dict[str, Any] = {}
        self._expires_at = 0.0
        self._retry_after = 0.0
        self._unknown_refresh_after = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        """Close only the HTTP client owned by this validator."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def _refresh_keys(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=5.0, follow_redirects=False)
        async with self._client.stream("GET", ACS_JWKS_URL) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > _MAX_JWKS_BYTES:
                    raise TelephonyAuthError("ACS signing key response too large")
        payload = json.loads(body)
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise TelephonyAuthError("Invalid ACS signing key response")
        keys = {}
        for key in payload["keys"]:
            if not isinstance(key, dict):
                raise TelephonyAuthError("Invalid ACS signing key")
            if (
                key.get("kty") != "RSA"
                or key.get("use", "sig") != "sig"
                or key.get("alg", "RS256") != "RS256"
                or "verify" not in key.get("key_ops", ["verify"])
            ):
                continue
            kid = key.get("kid")
            if not isinstance(kid, str) or not kid or kid in keys:
                raise TelephonyAuthError("Invalid ACS signing key identifier")
            keys[kid] = jwt.PyJWK.from_dict(key, algorithm="RS256").key
        if not keys:
            raise TelephonyAuthError("No ACS signing keys available")
        self._keys = keys
        self._expires_at = monotonic() + 3600

    async def _signing_key(self, kid: str) -> Any:
        async with self._lock:
            now = monotonic()
            if now < self._expires_at and kid in self._keys:
                return self._keys[kid]
            unknown_key = now < self._expires_at
            if now < self._retry_after or (unknown_key and now < self._unknown_refresh_after):
                raise TelephonyAuthError("ACS signing key unavailable")
            # Rate-limit unknown-kid refreshes and failed fetches, not valid cached keys.
            if unknown_key:
                self._unknown_refresh_after = now + 30
            self._retry_after = now + 30
            await self._refresh_keys()
            self._retry_after = 0.0
            if kid not in self._keys:
                self._unknown_refresh_after = now + 30
                raise TelephonyAuthError("Unknown ACS signing key")
            return self._keys[kid]

    async def validate(self, token: str) -> dict[str, Any]:
        """Verify signature, RS256 algorithm, issuer, audience and required expiry."""
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
                raise TelephonyAuthError("Invalid ACS token header")
            # Includes lock wait, DNS, connect and response streaming in the time budget.
            async with asyncio.timeout(_JWKS_TIMEOUT_SECONDS):
                key = await self._signing_key(kid)
            return jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=ACS_ISSUER,
                options={"require": ["exp", "iss", "aud"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError, TimeoutError, ValueError, TypeError) as exc:
            raise TelephonyAuthError("ACS token validation failed") from exc


def is_authenticated_telephony_request(scope: Scope) -> bool:
    """Recognize only an exact route authenticated by our outer ASGI gate."""
    route = (scope["type"], scope.get("method"), scope.get("path"))
    return scope.get(_AUTH_SCOPE_KEY) is _AUTHENTICATED and route in {
        ("http", "POST", ACS_CALLBACK_PATH),
        ("http", "POST", EVENT_GRID_PATH),
        ("websocket", None, ACS_MEDIA_PATH),
    }


def _single_header(headers: Headers, name: str) -> str:
    values = headers.getlist(name)
    if len(values) != 1:
        raise TelephonyAuthError("Missing or duplicate authentication header")
    return values[0]


def _validate_event_grid_payload(payload: Any, resource_id: str) -> str | None:
    if not isinstance(payload, list) or not payload:
        raise TelephonyAuthError("Expected a non-empty Event Grid event array")
    validation_code = None
    for event in payload:
        if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
            raise TelephonyAuthError("Invalid Event Grid event")
        topic = event.get("topic")
        if not isinstance(topic, str) or topic.casefold() != resource_id.casefold():
            raise TelephonyAuthError("Unexpected Event Grid topic")
        # CloudEvents are not the configured delivery schema. Reject contradictory
        # source/type fields rather than allowing a second interpretation downstream.
        if "source" in event or "type" in event:
            raise TelephonyAuthError("Expected Event Grid schema")
        data = event["data"]
        if event.get("eventType") == _VALIDATION_EVENT:
            validation_code = data.get("validationCode")
            if len(payload) != 1 or not isinstance(validation_code, str) or not validation_code:
                raise TelephonyAuthError("Invalid Event Grid validation event")
        elif event.get("eventType") == _INCOMING_CALL_EVENT:
            context = data.get("incomingCallContext")
            if not isinstance(context, str) or not context:
                raise TelephonyAuthError("Invalid incoming call context")
            if "from" in data and not isinstance(data["from"], dict):
                raise TelephonyAuthError("Invalid incoming caller")
        else:
            raise TelephonyAuthError("Unexpected Event Grid event type")
    return validation_code


class TelephonyAuthMiddleware:
    """Authenticate only opt-in telephony ingress, before handlers or Entra auth."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        audience: str,
        resource_id: str,
        webhook_secret: str,
        validator: ACSJWTValidator | None = None,
    ) -> None:
        self.app = app
        self.enabled = enabled
        self.resource_id = resource_id
        self._webhook_secret = webhook_secret.encode("utf-8")
        self._validator = validator or ACSJWTValidator(audience)
        if enabled:
            validate_front_door_auth_config(audience, resource_id, webhook_secret)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, status: int) -> None:
        logger.warning(
            "Rejected telephony ingress: transport=%s path=%s status=%s",
            scope["type"],
            scope.get("path"),
            status,
        )
        if scope["type"] == "websocket":
            # Sending close before accept rejects the handshake (HTTP 403 in Uvicorn).
            await send({"type": "websocket.close", "code": 1008})
        else:
            await JSONResponse({"detail": "Telephony request rejected"}, status_code=status)(
                scope, receive, send
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "lifespan":
            try:
                await self.app(scope, receive, send)
            finally:
                await self._validator.aclose()
            return
        path = scope.get("path")
        if scope["type"] not in {"http", "websocket"} or path not in {
            ACS_CALLBACK_PATH,
            ACS_MEDIA_PATH,
            EVENT_GRID_PATH,
        }:
            await self.app(scope, receive, send)
            return
        if (path == ACS_MEDIA_PATH and scope["type"] != "websocket") or (
            path != ACS_MEDIA_PATH and (scope["type"] != "http" or scope.get("method") != "POST")
        ):
            await self._reject(scope, receive, send, 405)
            return
        headers = Headers(scope=scope)
        try:
            if path == EVENT_GRID_PATH:
                supplied_secret = _single_header(headers, EVENT_GRID_SECRET_HEADER).encode("utf-8")
                if not hmac.compare_digest(supplied_secret, self._webhook_secret):
                    raise TelephonyAuthError("Invalid Event Grid secret")
            else:
                authorization = _single_header(headers, "Authorization").split()
                if len(authorization) != 2 or authorization[0].lower() != "bearer":
                    raise TelephonyAuthError("Invalid bearer token")
                await self._validator.validate(authorization[1])
        except TelephonyAuthError:
            await self._reject(scope, receive, send, 401)
            return

        downstream_receive = receive
        if path == EVENT_GRID_PATH:
            body = bytearray()
            try:
                async with asyncio.timeout(_BODY_TIMEOUT_SECONDS):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        body.extend(message.get("body", b""))
                        if len(body) > _MAX_BODY_BYTES:
                            await self._reject(scope, receive, send, 413)
                            return
                        if not message.get("more_body", False):
                            break
                validation_code = _validate_event_grid_payload(json.loads(body), self.resource_id)
            except (TelephonyAuthError, ValueError, UnicodeError, RecursionError):
                await self._reject(scope, receive, send, 400)
                return
            except TimeoutError:
                await self._reject(scope, receive, send, 408)
                return
            if validation_code is not None:
                await JSONResponse({"validationResponse": validation_code})(scope, receive, send)
                return
            replayed = False

            async def replay_body() -> dict[str, Any]:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            downstream_receive = replay_body
        scope[_AUTH_SCOPE_KEY] = _AUTHENTICATED
        await self.app(scope, downstream_receive, send)
