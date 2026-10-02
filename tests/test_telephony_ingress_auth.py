"""Front Door's exact telephony exceptions authenticate before any side effects."""

import ast
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from apps.artagent.backend.src.utils import telephony_auth as auth
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

AUDIENCE = "11111111-2222-3333-4444-555555555555"
RESOURCE_ID = (
    "/subscriptions/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/resourceGroups/voice"
    "/providers/Microsoft.Communication/communicationServices/voice-acs"
)
SECRET = "test-only-strong-webhook-secret-123456789"


@pytest.fixture(scope="module")
def signing_keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


def jwk(key, kid="key-1"):
    result = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {**result, "kid": kid, "use": "sig", "alg": "RS256"}


def token(key, *, kid="key-1", claims=None, omit=()):
    payload = {
        "iss": auth.ACS_ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        **(claims or {}),
    }
    for name in omit:
        payload.pop(name, None)
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
async def verifier(signing_keys):
    requests = []
    response = {"keys": [jwk(signing_keys[0])]}

    async def respond(request):
        requests.append(request)
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        validator = auth.ACSJWTValidator(AUDIENCE, client=client)
        yield validator, requests, response


def gate(app, *, enabled=True, validator=None, **overrides):
    return auth.TelephonyAuthMiddleware(
        app,
        enabled=enabled,
        validator=validator,
        **{
            "audience": AUDIENCE,
            "resource_id": RESOURCE_ID,
            "webhook_secret": SECRET,
            **overrides,
        },
    )


def event(*, validation=False, **overrides):
    return {
        "id": "event-1",
        "topic": RESOURCE_ID,
        "eventTime": "2026-09-20T18:00:00Z",
        "eventType": (
            "Microsoft.EventGrid.SubscriptionValidationEvent"
            if validation
            else "Microsoft.Communication.IncomingCall"
        ),
        "data": (
            {"validationCode": "validation-123"}
            if validation
            else {"incomingCallContext": "incoming-context", "from": {"kind": "phoneNumber"}}
        ),
        **overrides,
    }


@pytest.mark.asyncio
async def test_rs256_issuer_audience_expiry_and_cache(verifier, signing_keys):
    validator, requests, _ = verifier
    signed = token(signing_keys[0])
    results = await asyncio.gather(*(validator.validate(signed) for _ in range(8)))
    assert all(result["aud"] == AUDIENCE for result in results)
    assert len(requests) == 1
    assert str(requests[0].url) == auth.ACS_JWKS_URL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claims,omit",
    [
        ({"iss": "https://attacker.example"}, ()),
        ({"aud": "another-resource"}, ()),
        ({"aud": RESOURCE_ID}, ()),
        ({"exp": int(time.time()) - 60}, ()),
        ({"nbf": int(time.time()) + 3600}, ()),
        ({}, ("exp",)),
        ({}, ("iss",)),
        ({}, ("aud",)),
        ({"exp": None}, ()),
        ({"exp": "invalid"}, ()),
    ],
)
async def test_reject_invalid_or_missing_claims(verifier, signing_keys, claims, omit):
    with pytest.raises(auth.TelephonyAuthError):
        await verifier[0].validate(token(signing_keys[0], claims=claims, omit=omit))


@pytest.mark.asyncio
async def test_wrong_signature_and_token_supplied_jwks_are_rejected(verifier, signing_keys):
    validator, requests, _ = verifier
    with pytest.raises(auth.TelephonyAuthError):
        await validator.validate(token(signing_keys[1]))
    forged = jwt.encode(
        {"iss": auth.ACS_ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300},
        signing_keys[1],
        algorithm="RS256",
        headers={
            "kid": "key-1",
            "jku": "https://attacker.example/keys",
            "jwk": jwk(signing_keys[1]),
        },
    )
    with pytest.raises(auth.TelephonyAuthError):
        await validator.validate(forged)
    assert len(requests) == 1
    assert str(requests[0].url) == auth.ACS_JWKS_URL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "not.a.jwt",
        jwt.encode(
            {"aud": AUDIENCE}, "not-an-rsa-key", algorithm="HS256", headers={"kid": "key-1"}
        ),
        jwt.encode({"aud": AUDIENCE}, "", algorithm="none", headers={"kid": "key-1"}),
    ],
)
async def test_malformed_and_non_rs256_tokens_do_not_fetch_keys(verifier, invalid):
    with pytest.raises(auth.TelephonyAuthError):
        await verifier[0].validate(invalid)
    assert not verifier[1]


@pytest.mark.asyncio
async def test_key_rotation_refreshes_unknown_kid_once(verifier, signing_keys):
    validator, requests, response = verifier
    await validator.validate(token(signing_keys[0]))
    response["keys"].append(jwk(signing_keys[1], "rotated"))
    await validator.validate(token(signing_keys[1], kid="rotated"))
    assert len(requests) == 2
    for kid in ("unknown-1", "unknown-2", "unknown-3"):
        with pytest.raises(auth.TelephonyAuthError):
            await validator.validate(token(signing_keys[0], kid=kid))
    assert len(requests) == 2
    await validator.validate(token(signing_keys[0]))


@pytest.mark.asyncio
async def test_expired_cache_refreshes_and_never_falls_back_to_stale_keys(
    verifier, signing_keys, monkeypatch
):
    validator, requests, response = verifier
    await validator.validate(token(signing_keys[0]))
    future = auth.monotonic() + 3601
    monkeypatch.setattr(auth, "monotonic", lambda: future)
    response["keys"] = []
    with pytest.raises(auth.TelephonyAuthError):
        await validator.validate(token(signing_keys[0]))
    with pytest.raises(auth.TelephonyAuthError):
        await validator.validate(token(signing_keys[0]))
    assert len(requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,payload",
    [
        (503, {}),
        (302, {}),
        (200, []),
        (200, {}),
        (200, {"keys": []}),
        (200, {"keys": [None]}),
        (200, {"keys": [{"kid": "key-1", "kty": "RSA", "n": "invalid"}]}),
        (200, {"keys": [{"kid": "key-1", "kty": "oct", "k": "eA"}]}),
    ],
)
async def test_jwks_http_and_schema_failures_fail_closed(signing_keys, status, payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=payload))
    ) as client:
        with pytest.raises(auth.TelephonyAuthError):
            await auth.ACSJWTValidator(AUDIENCE, client=client).validate(token(signing_keys[0]))


@pytest.mark.asyncio
async def test_jwks_network_failure_is_bounded_and_throttled(signing_keys):
    calls = 0

    async def failed(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("test timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(failed)) as client:
        validator = auth.ACSJWTValidator(AUDIENCE, client=client)
        for _ in range(3):
            with pytest.raises(auth.TelephonyAuthError):
                await validator.validate(token(signing_keys[0]))
    assert calls == 1


@pytest.mark.asyncio
async def test_jwks_response_size_is_bounded(signing_keys):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b" " * 65537))
    ) as client:
        with pytest.raises(auth.TelephonyAuthError):
            await auth.ACSJWTValidator(AUDIENCE, client=client).validate(token(signing_keys[0]))


@pytest.mark.parametrize(
    "overrides,name",
    [
        ({"audience": ""}, "ACS_AUDIENCE"),
        ({"audience": RESOURCE_ID}, "ACS_AUDIENCE"),
        ({"audience": "00000000-0000-0000-0000-000000000000"}, "ACS_AUDIENCE"),
        ({"resource_id": ""}, "ACS_ARM_RESOURCE_ID"),
        ({"resource_id": AUDIENCE}, "ACS_ARM_RESOURCE_ID"),
        ({"webhook_secret": ""}, "EVENT_GRID_WEBHOOK_SECRET"),
        ({"webhook_secret": "too-short"}, "EVENT_GRID_WEBHOOK_SECRET"),
        ({"webhook_secret": " " * 32}, "EVENT_GRID_WEBHOOK_SECRET"),
        ({"webhook_secret": "é" * 32}, "EVENT_GRID_WEBHOOK_SECRET"),
        ({"webhook_secret": "x" * 4097}, "EVENT_GRID_WEBHOOK_SECRET"),
    ],
)
def test_missing_or_invalid_config_fails_before_serving(overrides, name):
    with pytest.raises(ValueError, match=name):
        gate(AsyncMock(), **overrides)


def http_scope(path, headers=(), *, method="POST"):
    return {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": list(headers),
        "query_string": b"",
        "scheme": "https",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [auth.ACS_CALLBACK_PATH, auth.EVENT_GRID_PATH])
@pytest.mark.parametrize("headers", [[], [(b"authorization", b"Bearer")]])
async def test_unauthenticated_http_is_rejected_before_reading_body(path, headers):
    handler, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
    await gate(handler)(http_scope(path, headers), receive, send)
    handler.assert_not_awaited()
    receive.assert_not_awaited()
    assert send.call_args_list[0].args[0]["status"] == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("credential", [None, "Bearer", "Bearer not.a.jwt"])
async def test_websocket_rejected_before_receive_accept_or_session(credential):
    handler, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
    scope = {
        "type": "websocket",
        "path": auth.ACS_MEDIA_PATH,
        "headers": [] if credential is None else [(b"authorization", credential.encode())],
    }
    await gate(handler)(scope, receive, send)
    handler.assert_not_awaited()
    receive.assert_not_awaited()
    send.assert_awaited_once_with({"type": "websocket.close", "code": 1008})


@pytest.mark.asyncio
async def test_media_accepts_documented_24_hour_token(verifier, signing_keys):
    validator, _, _ = verifier
    signed = token(
        signing_keys[0],
        claims={"iat": int(time.time()) - 3600, "exp": int(time.time()) + 23 * 3600},
    )
    scope = {
        "type": "websocket",
        "path": auth.ACS_MEDIA_PATH,
        "headers": [(b"authorization", f"Bearer {signed}".encode())],
    }
    handler = AsyncMock()
    await gate(handler, validator=validator)(scope, AsyncMock(), AsyncMock())
    handler.assert_awaited_once()
    assert auth.is_authenticated_telephony_request(scope)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_type,path",
    [
        ("http", auth.ACS_CALLBACK_PATH),
        ("http", auth.EVENT_GRID_PATH),
        ("websocket", auth.ACS_MEDIA_PATH),
    ],
)
async def test_disabled_flag_preserves_legacy_behavior_without_configuration(scope_type, path):
    scope = {**http_scope(path), "type": scope_type}
    handler = AsyncMock()
    await gate(handler, enabled=False, audience="", resource_id="", webhook_secret="")(
        scope, AsyncMock(), AsyncMock()
    )
    handler.assert_awaited_once()
    assert not auth.is_authenticated_telephony_request(scope)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,method",
    [
        (auth.ACS_CALLBACK_PATH, "GET"),
        (auth.EVENT_GRID_PATH, "PUT"),
        (auth.ACS_MEDIA_PATH, "POST"),
    ],
)
async def test_protected_paths_reject_wrong_http_method_or_transport(path, method):
    handler, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
    await gate(handler)(http_scope(path, method=method), receive, send)
    assert send.call_args_list[0].args[0]["status"] == 405
    handler.assert_not_awaited()
    receive.assert_not_awaited()


@pytest.fixture
def integration_app(verifier):
    """Execute the real middleware wiring without cloud/service startup imports."""
    source = Path("apps/artagent/backend/main.py").read_text()
    setup = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "setup_middleware_and_routes"
    )
    routes = APIRouter()

    @routes.post(auth.ACS_CALLBACK_PATH)
    @routes.post(auth.EVENT_GRID_PATH)
    async def callback(request: Request):
        return {
            "body": await request.json(),
            "authenticated": auth.is_authenticated_telephony_request(request.scope),
        }

    @routes.get("/api/private")
    @routes.post(auth.ACS_CALLBACK_PATH + "/suffix")
    @routes.post(auth.EVENT_GRID_PATH + "/suffix")
    async def private():
        return {"ok": True}

    validate_entra = AsyncMock(side_effect=HTTPException(401, "Entra required"))

    class GateWithMockKeys(auth.TelephonyAuthMiddleware):
        def __init__(self, app, **kwargs):
            super().__init__(app, validator=verifier[0], **kwargs)

    namespace = {
        "FastAPI": FastAPI,
        "Request": Request,
        "HTTPException": HTTPException,
        "CORSMiddleware": CORSMiddleware,
        "JSONResponse": JSONResponse,
        "ACS_ARM_RESOURCE_ID": RESOURCE_ID,
        "ACS_AUDIENCE": AUDIENCE,
        "EVENT_GRID_WEBHOOK_SECRET": SECRET,
        "ACS_CALLBACK_PATH": auth.ACS_CALLBACK_PATH,
        "ACS_MEDIA_PATH": auth.ACS_MEDIA_PATH,
        "EVENT_GRID_PATH": auth.EVENT_GRID_PATH,
        "ENABLE_FRONT_DOOR": True,
        "ENABLE_AUTH_VALIDATION": True,
        "ENABLE_DOCS": False,
        "ALLOWED_ORIGINS": [],
        "ENTRA_EXEMPT_PATHS": [
            auth.ACS_CALLBACK_PATH,
            auth.ACS_MEDIA_PATH,
            auth.EVENT_GRID_PATH,
            "/health",
        ],
        "validate_front_door_auth_config": auth.validate_front_door_auth_config,
        "is_authenticated_telephony_request": auth.is_authenticated_telephony_request,
        "TelephonyAuthMiddleware": GateWithMockKeys,
        "validate_entraid_token": validate_entra,
        "v1_router": routes,
        "demo_env": type("Demo", (), {"router": APIRouter()}),
    }
    exec(compile(ast.Module(body=[setup], type_ignores=[]), "main.py", "exec"), namespace)
    app = FastAPI()
    namespace["setup_middleware_and_routes"](app)
    return app, validate_entra


@pytest.mark.asyncio
async def test_only_authenticated_exact_telephony_routes_bypass_entra(
    integration_app, signing_keys
):
    app, entra = integration_app
    signed_headers = {"Authorization": f"Bearer {token(signing_keys[0])}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        accepted = await client.post(
            auth.ACS_CALLBACK_PATH, headers=signed_headers, json={"event": 1}
        )
        assert accepted.status_code == 200
        assert accepted.json() == {"body": {"event": 1}, "authenticated": True}
        entra.assert_not_awaited()
        assert (await client.post(auth.ACS_CALLBACK_PATH, json={})).status_code == 401
        entra.assert_not_awaited()
        assert (
            await client.post(auth.ACS_CALLBACK_PATH + "/suffix", headers=signed_headers, json={})
        ).status_code == 401
        assert (await client.post(auth.EVENT_GRID_PATH + "/suffix", json={})).status_code == 401
        assert (await client.get("/api/private", headers=signed_headers)).status_code == 401
    assert entra.await_count == 3


@pytest.mark.asyncio
async def test_event_grid_validation_precedes_acs_startup_and_entra(integration_app):
    app, entra = integration_app
    # Deliberately no acs_caller on app.state; validation must never reach a handler.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        result = await client.post(
            auth.EVENT_GRID_PATH,
            headers={auth.EVENT_GRID_SECRET_HEADER: SECRET},
            json=[event(validation=True)],
        )
    assert result.status_code == 200
    assert result.json() == {"validationResponse": "validation-123"}
    entra.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticated_incoming_call_body_is_replayed_to_handler(integration_app):
    app, entra = integration_app
    payload = [event(topic=RESOURCE_ID.upper())]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        result = await client.post(
            auth.EVENT_GRID_PATH,
            headers={auth.EVENT_GRID_SECRET_HEADER: SECRET},
            json=payload,
        )
    assert result.status_code == 200
    assert result.json() == {"body": payload, "authenticated": True}
    entra.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [],
        ["bad"],
        [None],
        [event(topic="/subscriptions/another-resource")],
        [event(topic=None)],
        [event(eventType="Microsoft.Communication.CallConnected")],
        [event(data=None)],
        [event(data={})],
        [event(data={"incomingCallContext": 123})],
        [event(data={"incomingCallContext": "context", "from": "malformed"})],
        [event(source=RESOURCE_ID)],
        [event(type="Microsoft.Communication.IncomingCall")],
        [event(validation=True, data={})],
        [event(validation=True, data={"validationCode": 123})],
        [event(validation=True), event()],
        [event(), event(topic="forged")],
        [event(validation=True, topic="forged")],
    ],
)
async def test_event_grid_rejects_forged_and_malformed_events_before_handler(payload):
    handler = AsyncMock()
    app = gate(handler)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        result = await client.post(
            auth.EVENT_GRID_PATH,
            headers={auth.EVENT_GRID_SECRET_HEADER: SECRET},
            content=json.dumps(payload),
        )
    assert result.status_code == 400
    handler.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,status",
    [(b"{invalid", 400), (b"\xff", 400), (b"[" * 1100, 400), (b" " * (1024 * 1024 + 1), 413)],
    ids=["invalid-json", "invalid-utf8", "excessive-depth", "oversized-body"],
)
async def test_event_grid_invalid_json_and_size_limits(body, status):
    handler = AsyncMock()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gate(handler)), base_url="https://test"
    ) as client:
        result = await client.post(
            auth.EVENT_GRID_PATH, headers={auth.EVENT_GRID_SECRET_HEADER: SECRET}, content=body
        )
    assert result.status_code == status
    handler.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {auth.EVENT_GRID_SECRET_HEADER: "wrong"},
        {auth.EVENT_GRID_SECRET_HEADER: "x" * len(SECRET)},
        {"Authorization": f"Bearer {SECRET}"},
        [(auth.EVENT_GRID_SECRET_HEADER, SECRET), (auth.EVENT_GRID_SECRET_HEADER, SECRET)],
    ],
)
async def test_event_grid_validation_requires_unique_secret_header_not_query(headers):
    handler = AsyncMock()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gate(handler)), base_url="https://test"
    ) as client:
        result = await client.post(
            f"{auth.EVENT_GRID_PATH}?token={SECRET}",
            headers=headers,
            json=[event(validation=True)],
        )
    assert result.status_code == 401
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate_closes_jwks_client_on_lifespan_exit():
    validator = AsyncMock()
    await gate(AsyncMock(), validator=validator)({"type": "lifespan"}, AsyncMock(), AsyncMock())
    validator.aclose.assert_awaited_once()
