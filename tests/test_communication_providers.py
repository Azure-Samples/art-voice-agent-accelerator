"""Opt-in Teams identity must never change or silently replace standalone ACS calls."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from apps.artagent.backend.api.v1.endpoints import calls, health
from apps.artagent.backend.api.v1.handlers.acs_call_lifecycle import ACSLifecycleHandler
from apps.artagent.backend.api.v1.schemas.call import CallInitiateRequest
from apps.artagent.backend.config.settings import get_communication_provider_settings
from apps.artagent.backend.src.services import communication_providers as providers
from apps.artagent.backend.src.services.acs import acs_caller as initialization
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from src.acs import acs_helper
from src.enums.stream_modes import StreamMode

ACCOUNT_ID = "11111111-2222-3333-4444-555555555555"
PHONE = "+15551234567"


@pytest.fixture(autouse=True)
def provider_environment(monkeypatch):
    for key in (
        "TEAMS_PHONE_ENABLED",
        "TEAMS_PHONE_RESOURCE_ACCOUNT_ID",
        "AZURE_EMAIL_SENDER_ADDRESS",
        "AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING",
        "AZURE_COMMUNICATION_SMS_CONNECTION_STRING",
        "AZURE_SMS_FROM_PHONE_NUMBER",
        "ACS_CONNECTION_STRING",
        "ACS_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(providers, "teams_phone_supported", lambda: True)
    monkeypatch.setattr(acs_helper, "teams_phone_supported", lambda: True)
    monkeypatch.setattr(initialization, "teams_phone_supported", lambda: True)
    monkeypatch.setattr(initialization, "_instance", None)


def enable_teams(monkeypatch):
    monkeypatch.setenv("TEAMS_PHONE_ENABLED", "true")
    monkeypatch.setenv("TEAMS_PHONE_RESOURCE_ACCOUNT_ID", ACCOUNT_ID)


def caller_state(*, source_number=PHONE, teams_id=None):
    return SimpleNamespace(
        client=MagicMock(),
        source_number=source_number,
        teams_resource_account_id=teams_id,
    )


def option(catalog, provider, service="telephony"):
    return next(item for item in getattr(catalog, service).options if item.id == provider)


def test_default_is_acs_and_other_services_are_not_teams():
    catalog = providers.communication_providers(caller_state())
    assert catalog.telephony.default == "acs"
    assert option(catalog, "acs").available
    assert not option(catalog, "teams").available
    for service in ("email", "sms"):
        assert getattr(catalog, service).default == "acs"
        assert not option(catalog, "acs", service).available
        assert not option(catalog, "external", service).available
        assert option(catalog, "external", service).status == "unavailable"


def test_configured_teams_does_not_require_acs_phone_number(monkeypatch):
    enable_teams(monkeypatch)
    catalog = providers.communication_providers(caller_state(source_number="", teams_id=ACCOUNT_ID))
    assert option(catalog, "teams").available
    assert option(catalog, "teams").status == "configured"
    assert not option(catalog, "acs").available
    assert "not verified" in option(catalog, "teams").detail


@pytest.mark.parametrize("account_id", ["", "not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_invalid_teams_settings_do_not_disable_acs(monkeypatch, account_id):
    monkeypatch.setenv("TEAMS_PHONE_ENABLED", "true")
    monkeypatch.setenv("TEAMS_PHONE_RESOURCE_ACCOUNT_ID", account_id)
    catalog = providers.communication_providers(caller_state())
    assert not option(catalog, "teams").available
    assert option(catalog, "acs").available


def test_flag_and_restart_are_required(monkeypatch):
    monkeypatch.setenv("TEAMS_PHONE_RESOURCE_ACCOUNT_ID", ACCOUNT_ID)
    assert get_communication_provider_settings().teams_missing_settings == ["TEAMS_PHONE_ENABLED"]
    enable_teams(monkeypatch)
    catalog = providers.communication_providers(caller_state())
    assert not option(catalog, "teams").available
    assert any("restart" in setting for setting in option(catalog, "teams").missing_settings)


def test_old_sdk_is_unavailable_without_breaking_acs(monkeypatch):
    enable_teams(monkeypatch)
    monkeypatch.setattr(providers, "teams_phone_supported", lambda: False)
    catalog = providers.communication_providers(caller_state(teams_id=ACCOUNT_ID))
    assert option(catalog, "teams").status == "unavailable"
    assert not option(catalog, "teams").available
    assert option(catalog, "acs").available


def test_catalog_never_exposes_credentials_or_resource_account(monkeypatch):
    enable_teams(monkeypatch)
    monkeypatch.setenv("AZURE_EMAIL_SENDER_ADDRESS", "private@example.com")
    monkeypatch.setenv("AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING", "private-email-key")
    monkeypatch.setenv("AZURE_COMMUNICATION_SMS_CONNECTION_STRING", "private-sms-key")
    monkeypatch.setenv("AZURE_SMS_FROM_PHONE_NUMBER", PHONE)
    catalog = providers.communication_providers(caller_state(teams_id=ACCOUNT_ID))
    assert option(catalog, "acs", "email").available
    assert option(catalog, "acs", "sms").available
    serialized = catalog.model_dump_json()
    for secret in (ACCOUNT_ID, PHONE, "private@example.com", "private-email-key", "private-sms-key"):
        assert secret not in serialized


@pytest.fixture
def sdk_caller(monkeypatch):
    sdk = MagicMock()
    sdk.create_call.return_value = SimpleNamespace(call_connection_id="call-1")
    monkeypatch.setattr(acs_helper.CallAutomationClient, "from_connection_string", lambda _: sdk)
    return acs_helper.AcsCaller(
        source_number=PHONE,
        callback_url="https://example.com/api/v1/calls/callbacks",
        websocket_url="wss://example.com/api/v1/media/stream",
        acs_connection_string="fake",
        teams_resource_account_id=ACCOUNT_ID,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [StreamMode.MEDIA, StreamMode.VOICE_LIVE, StreamMode.TRANSCRIPTION])
@pytest.mark.parametrize("provider", ["acs", "teams"])
async def test_sdk_uses_selected_identity_and_preserves_media(sdk_caller, mode, provider):
    result = await sdk_caller.initiate_call(PHONE, mode, telephony_provider=provider)
    assert result == {"status": "created", "call_id": "call-1"}
    kwargs = sdk_caller.client.create_call.call_args.kwargs
    assert kwargs["callback_url"] == sdk_caller.callback_url
    assert kwargs["target_participant"].properties["value"] == PHONE
    if provider == "teams":
        assert kwargs["teams_app_source"].properties["app_id"] == ACCOUNT_ID
        assert "source_caller_id_number" not in kwargs
    else:
        assert kwargs["source_caller_id_number"].properties["value"] == PHONE
        assert "teams_app_source" not in kwargs
    if mode == StreamMode.TRANSCRIPTION:
        assert kwargs["transcription"] is sdk_caller.transcription_opts
        assert kwargs["media_streaming"] is None
    else:
        assert kwargs["media_streaming"] is sdk_caller.media_streaming_options
        assert kwargs["transcription"] is None


@pytest.mark.asyncio
async def test_simultaneous_calls_do_not_mutate_shared_identity(sdk_caller):
    await asyncio.gather(
        sdk_caller.initiate_call(PHONE, telephony_provider="teams"),
        sdk_caller.initiate_call(PHONE),
    )
    requests = [call.kwargs for call in sdk_caller.client.create_call.call_args_list]
    assert sum("teams_app_source" in request for request in requests) == 1
    assert sum("source_caller_id_number" in request for request in requests) == 1
    assert sdk_caller.source_number == PHONE
    assert sdk_caller.teams_resource_account_id == ACCOUNT_ID


@pytest.mark.asyncio
async def test_sdk_rejects_unconfigured_teams_without_fallback(sdk_caller):
    sdk_caller.teams_resource_account_id = None
    with pytest.raises(ValueError, match="Teams Phone is not configured"):
        await sdk_caller.initiate_call(PHONE, telephony_provider="teams")
    sdk_caller.client.create_call.assert_not_called()


@pytest.mark.asyncio
async def test_teams_only_caller_rejects_default_acs_without_fallback(sdk_caller):
    sdk_caller.source_number = ""
    with pytest.raises(ValueError, match="ACS_SOURCE_PHONE_NUMBER"):
        await sdk_caller.initiate_call(PHONE)
    sdk_caller.client.create_call.assert_not_called()


@pytest.mark.asyncio
async def test_teams_inbound_keeps_existing_answer_protocol(sdk_caller):
    sdk_caller.source_number = ""
    await sdk_caller.answer_incoming_call("incoming-context", stream_mode=StreamMode.VOICE_LIVE)
    kwargs = sdk_caller.client.answer_call.call_args.kwargs
    assert kwargs["incoming_call_context"] == "incoming-context"
    assert kwargs["media_streaming"] is sdk_caller.media_streaming_options
    assert "teams_app_source" not in kwargs
    assert "source_caller_id_number" not in kwargs


@pytest.mark.parametrize("source_number", ["", PHONE])
def test_initialization_supports_teams_alongside_acs(monkeypatch, source_number):
    enable_teams(monkeypatch)
    constructor = MagicMock()
    monkeypatch.setattr(initialization, "AcsCaller", constructor)
    monkeypatch.setattr(initialization, "_get_config_dynamic", lambda: {
        "ACS_SOURCE_PHONE_NUMBER": source_number,
        "ACS_CONNECTION_STRING": "fake",
        "ACS_ENDPOINT": "",
        "ACS_AUTH_MODE": "auto",
        "BASE_URL": "https://example.com",
        "AZURE_SPEECH_ENDPOINT": "",
        "AZURE_STORAGE_CONTAINER_URL": "",
    })
    assert initialization.initialize_acs_caller_instance() is constructor.return_value
    assert constructor.call_args.kwargs["teams_resource_account_id"] == ACCOUNT_ID
    assert constructor.call_args.kwargs["source_number"] == source_number


@pytest.mark.parametrize("failure", ["disabled", "invalid_id", "old_sdk"])
def test_optional_teams_failure_preserves_acs_initialization(monkeypatch, failure):
    enable_teams(monkeypatch)
    if failure == "disabled":
        monkeypatch.setenv("TEAMS_PHONE_ENABLED", "false")
    elif failure == "invalid_id":
        monkeypatch.setenv("TEAMS_PHONE_RESOURCE_ACCOUNT_ID", "invalid")
    else:
        monkeypatch.setattr(initialization, "teams_phone_supported", lambda: False)
    constructor = MagicMock()
    monkeypatch.setattr(initialization, "AcsCaller", constructor)
    monkeypatch.setattr(initialization, "_get_config_dynamic", lambda: {
        "ACS_SOURCE_PHONE_NUMBER": PHONE,
        "ACS_CONNECTION_STRING": "fake",
        "ACS_ENDPOINT": "",
        "ACS_AUTH_MODE": "auto",
        "BASE_URL": "https://example.com",
        "AZURE_SPEECH_ENDPOINT": "",
        "AZURE_STORAGE_CONTAINER_URL": "",
    })
    assert initialization.initialize_acs_caller_instance() is constructor.return_value
    assert constructor.call_args.kwargs["teams_resource_account_id"] is None
    assert constructor.call_args.kwargs["source_number"] == PHONE


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["acs", "teams"])
async def test_lifecycle_dispatches_and_records_selected_provider(provider):
    caller = SimpleNamespace(
        initiate_call=AsyncMock(return_value={"status": "created", "call_id": "call-1"})
    )
    handler = ACSLifecycleHandler()
    handler._emit_call_event = AsyncMock()
    result = await handler.start_outbound_call(
        caller, PHONE, None, telephony_provider=provider, stream_mode=StreamMode.MEDIA
    )
    assert result["telephony_provider"] == provider
    assert handler._emit_call_event.call_args.args[2]["telephony_provider"] == provider
    kwargs = caller.initiate_call.call_args.kwargs
    assert kwargs.get("telephony_provider", "acs") == provider


@pytest.fixture
def app(monkeypatch):
    app = FastAPI()
    app.include_router(calls.router, prefix="/api/v1/calls")
    app.state.acs_caller = caller_state(teams_id=ACCOUNT_ID)
    app.state.redis = None
    app.state.conn_manager = SimpleNamespace(set_call_context=AsyncMock())
    processor = SimpleNamespace(process_events=AsyncMock())
    from apps.artagent.backend.api.v1 import events
    monkeypatch.setattr(events, "get_call_event_processor", lambda: processor)
    return app


@pytest.mark.asyncio
async def test_catalog_endpoint_with_no_configured_caller(app):
    app.state.acs_caller = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/calls/providers")
    assert response.status_code == 200
    assert response.json()["telephony"]["default"] == "acs"
    assert all(not provider["available"] for provider in response.json()["telephony"]["options"])


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [None, "acs", "teams"])
async def test_initiate_endpoint_uses_request_scoped_provider(app, monkeypatch, provider):
    enable_teams(monkeypatch)
    dispatch = AsyncMock(return_value={
        "status": "success", "callId": "call-1", "recording_enabled": False,
    })
    monkeypatch.setattr(ACSLifecycleHandler, "start_outbound_call", dispatch)
    payload = {"target_number": PHONE, "streaming_mode": "media"}
    if provider:
        payload["telephony_provider"] = provider
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/calls/initiate", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["telephony_provider"] == (provider or "acs")
    assert dispatch.call_args.kwargs["telephony_provider"] == (provider or "acs")
    context = app.state.conn_manager.set_call_context.call_args.args[1]
    assert context["telephony_provider"] == (provider or "acs")


@pytest.mark.asyncio
async def test_api_rejects_unavailable_teams_without_dispatch(app, monkeypatch):
    dispatch = AsyncMock()
    monkeypatch.setattr(ACSLifecycleHandler, "start_outbound_call", dispatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/calls/initiate",
            json={"target_number": PHONE, "telephony_provider": "teams"},
        )
    assert response.status_code == 503
    assert "TEAMS_PHONE_ENABLED" in response.json()["detail"]
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_api_rejects_unknown_provider(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/calls/initiate",
            json={"target_number": PHONE, "telephony_provider": "sip"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_teams_failure_never_retries_using_acs(app, monkeypatch):
    from fastapi import HTTPException

    enable_teams(monkeypatch)
    dispatch = AsyncMock(side_effect=HTTPException(502, "Teams carrier rejected the call"))
    monkeypatch.setattr(ACSLifecycleHandler, "start_outbound_call", dispatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/calls/initiate",
            json={"target_number": PHONE, "telephony_provider": "teams"},
        )
    assert response.status_code == 502
    dispatch.assert_awaited_once()
    assert dispatch.call_args.kwargs["telephony_provider"] == "teams"


def test_request_default_does_not_follow_teams_flag(monkeypatch):
    enable_teams(monkeypatch)
    assert CallInitiateRequest(target_number=PHONE).telephony_provider == "acs"


@pytest.mark.asyncio
async def test_health_supports_teams_only_configuration(monkeypatch):
    enable_teams(monkeypatch)
    result = await health._check_acs_caller_fast(caller_state(source_number="", teams_id=ACCOUNT_ID))
    assert result.status == "healthy"
    assert "not verified" in result.details
