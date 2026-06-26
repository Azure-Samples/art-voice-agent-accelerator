from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _clear_voicelive_credential_cache() -> None:
    from apps.artagent.backend.voice.voicelive import handler as voicelive_handler

    voicelive_handler._CACHED_CREDENTIAL = None


def test_shared_credential_helper_treats_local_azd_client_id_as_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from utils import azure_auth

    captured = {}

    class FakeDefaultAzureCredential:
        def __init__(self, **kwargs):
            captured["default"] = kwargs

    class FakeManagedIdentityCredential:
        def __init__(self, **kwargs):
            captured["managed"] = kwargs

    monkeypatch.setattr(azure_auth, "DefaultAzureCredential", FakeDefaultAzureCredential)
    monkeypatch.setattr(azure_auth, "ManagedIdentityCredential", FakeManagedIdentityCredential)
    monkeypatch.setenv("AZURE_CLIENT_ID", "local-azd-client-id")
    monkeypatch.setenv("ENVIRONMENT", "jinlocal")
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)
    monkeypatch.delenv("MSI_ENDPOINT", raising=False)
    monkeypatch.delenv("CONTAINER_APP_NAME", raising=False)
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    azure_auth.get_credential.cache_clear()

    try:
        azure_auth.get_credential()
    finally:
        azure_auth.get_credential.cache_clear()

    assert "managed" not in captured
    assert captured["default"]["exclude_managed_identity_credential"] is True
    assert captured["default"]["exclude_cli_credential"] is False


@pytest.mark.asyncio
async def test_voicelive_credential_skips_managed_identity_in_local_azd_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.artagent.backend.voice.voicelive import handler as voicelive_handler
    from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

    captured = {}

    class FakeDefaultAzureCredential:
        def __init__(self, **kwargs):
            captured["default"] = kwargs

    class FakeManagedIdentityCredential:
        def __init__(self, **kwargs):
            captured["managed"] = kwargs

    monkeypatch.setattr(
        voicelive_handler,
        "DefaultAzureCredential",
        FakeDefaultAzureCredential,
    )
    monkeypatch.setattr(
        voicelive_handler,
        "ManagedIdentityCredential",
        FakeManagedIdentityCredential,
    )
    monkeypatch.setenv("AZURE_CLIENT_ID", "local-azd-client-id")
    monkeypatch.setenv("ENVIRONMENT", "jinlocal")
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)
    monkeypatch.delenv("MSI_ENDPOINT", raising=False)
    monkeypatch.delenv("CONTAINER_APP_NAME", raising=False)
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    _clear_voicelive_credential_cache()

    try:
        credential = await VoiceLiveSDKHandler._build_credential(
            SimpleNamespace(has_api_key_auth=False, azure_client_id="local-azd-client-id")
        )
    finally:
        _clear_voicelive_credential_cache()

    assert isinstance(credential, FakeDefaultAzureCredential)
    assert "managed" not in captured
    assert captured["default"]["exclude_managed_identity_credential"] is True
    assert captured["default"]["exclude_cli_credential"] is False


@pytest.mark.asyncio
async def test_voicelive_credential_uses_managed_identity_when_hosted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.artagent.backend.voice.voicelive import handler as voicelive_handler
    from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

    captured = {}

    class FakeDefaultAzureCredential:
        def __init__(self, **kwargs):
            captured["default"] = kwargs

    class FakeManagedIdentityCredential:
        def __init__(self, **kwargs):
            captured["managed"] = kwargs

    monkeypatch.setattr(
        voicelive_handler,
        "DefaultAzureCredential",
        FakeDefaultAzureCredential,
    )
    monkeypatch.setattr(
        voicelive_handler,
        "ManagedIdentityCredential",
        FakeManagedIdentityCredential,
    )
    monkeypatch.setenv("AZURE_CLIENT_ID", "hosted-client-id")
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://localhost/identity")
    _clear_voicelive_credential_cache()

    try:
        credential = await VoiceLiveSDKHandler._build_credential(
            SimpleNamespace(has_api_key_auth=False, azure_client_id="hosted-client-id")
        )
    finally:
        _clear_voicelive_credential_cache()

    assert isinstance(credential, FakeManagedIdentityCredential)
    assert captured["managed"] == {"client_id": "hosted-client-id"}
    assert "default" not in captured


@pytest.mark.asyncio
async def test_prepared_connection_matches_and_closes() -> None:
    from apps.artagent.backend.voice.voicelive.handler import VoiceLivePreparedConnection

    cm = MagicMock()
    cm.__aexit__ = AsyncMock()
    prepared = VoiceLivePreparedConnection(
        connection=object(),
        connection_cm=cm,
        credential=object(),
        settings=object(),
        model="gpt-realtime",
        byom_query={"profile": "byom-azure-openai-realtime"},
    )

    assert prepared.matches("gpt-realtime", {"profile": "byom-azure-openai-realtime"})
    assert not prepared.matches("gpt-4o", {"profile": "byom-azure-openai-realtime"})
    assert not prepared.matches("gpt-realtime", None)

    await prepared.close()
    cm.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
async def test_claimed_prepared_connection_is_not_closed_by_helper() -> None:
    from apps.artagent.backend.voice.voicelive.handler import VoiceLivePreparedConnection

    cm = MagicMock()
    cm.__aexit__ = AsyncMock()
    prepared = VoiceLivePreparedConnection(
        connection=object(),
        connection_cm=cm,
        credential=object(),
        settings=object(),
        model="gpt-realtime",
    )

    prepared.claim()
    await prepared.close()

    cm.__aexit__.assert_not_called()


@pytest.mark.asyncio
async def test_start_and_consume_voicelive_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.artagent.backend.voice.voicelive import handler as voicelive_handler
    from apps.artagent.backend.voice.voicelive.handler import VoiceLivePreparedConnection

    app_state = SimpleNamespace()
    prepared = VoiceLivePreparedConnection(
        connection=object(),
        connection_cm=MagicMock(),
        credential=object(),
        settings=object(),
        model="gpt-realtime",
    )

    async def fake_prepare(**kwargs):
        assert kwargs["call_connection_id"] == "call-123"
        assert kwargs["session_id"] == "session-123"
        assert kwargs["scenario_name"] == "retail"
        return prepared

    monkeypatch.setattr(voicelive_handler, "_prepare_voicelive_call_warmup", fake_prepare)

    voicelive_handler.start_voicelive_call_warmup(
        app_state,
        call_connection_id="call-123",
        session_id="session-123",
        scenario_name="retail",
    )

    consumed = await voicelive_handler.consume_voicelive_call_warmup(
        app_state,
        call_connection_id="call-123",
        timeout_sec=1.0,
    )

    assert consumed is prepared
    assert app_state.voicelive_warmups == {}


@pytest.mark.asyncio
async def test_consume_voicelive_warmup_timeout_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.artagent.backend.voice.voicelive import handler as voicelive_handler
    from apps.artagent.backend.voice.voicelive.handler import VoiceLivePreparedConnection

    app_state = SimpleNamespace()
    cm = MagicMock()
    cm.__aexit__ = AsyncMock()
    prepared = VoiceLivePreparedConnection(
        connection=object(),
        connection_cm=cm,
        credential=object(),
        settings=object(),
        model="gpt-realtime",
    )
    release_event = asyncio.Event()

    async def fake_prepare(**kwargs):
        await release_event.wait()
        return prepared

    monkeypatch.setattr(voicelive_handler, "_prepare_voicelive_call_warmup", fake_prepare)

    voicelive_handler.start_voicelive_call_warmup(
        app_state,
        call_connection_id="call-456",
        session_id="session-456",
    )

    consumed = await voicelive_handler.consume_voicelive_call_warmup(
        app_state,
        call_connection_id="call-456",
        timeout_sec=0.001,
    )

    assert consumed is None

    release_event.set()
    for _ in range(10):
        await asyncio.sleep(0)
        if cm.__aexit__.await_count:
            break
    cm.__aexit__.assert_awaited_once_with(None, None, None)
