"""Full regional catalogs, resource-scoped caching, and explicit offline fallbacks."""

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from apps.artagent.backend.api.v1.endpoints import agent_builder as api
from apps.artagent.backend.api.v1.schemas.voices import VoiceInfo
from apps.artagent.backend.src.services import voice_catalog as service
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def scope():
    return service.SpeechVoiceScope("westus2", "https://speech.example.invalid", "resource-one", "")


@pytest.fixture
def voices():
    return (
        VoiceInfo(
            name="fr-FR-DeniseNeural",
            display_name="Denise",
            category="standard",
            language="fr-FR",
            gender="Female",
            styles=["cheerful"],
            status="GA",
        ),
        VoiceInfo(
            name="ja-JP-NanamiNeural",
            display_name="Nanami",
            category="standard",
            language="ja-JP",
            gender="Female",
        ),
        VoiceInfo(
            name="fr-FR-Vivienne:DragonHDLatestNeural",
            display_name="Vivienne HD",
            category="hd",
            language="fr-FR",
            status="Preview",
        ),
    )


@pytest_asyncio.fixture(autouse=True)
async def clear_catalog():
    service._cache.clear()
    service._failures.clear()
    service._pending.clear()
    yield
    pending = list(service._pending.values())
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=3)
    service._cache.clear()
    service._failures.clear()
    service._pending.clear()


@pytest.mark.asyncio
async def test_endpoint_returns_voices_outside_the_curated_list(monkeypatch, scope, voices):
    discover = AsyncMock(
        return_value=service.VoiceDiscovery(scope, service.VoiceSnapshot(voices, time.time()))
    )
    monkeypatch.setattr(api, "discover_voice_catalog", discover)
    result = await api.list_available_voices(use_cache=False)
    discover.assert_awaited_once_with(use_cache=False)
    assert {voice.name for voice in result.voices} == {voice.name for voice in voices}
    assert result.catalog_complete and result.verified_against_region
    assert result.region == "westus2"
    assert result.total == result.total_available == 3
    denise = next(voice for voice in result.voices if voice.name == "fr-FR-DeniseNeural")
    assert denise.styles == ["cheerful"]
    assert "id" not in result.model_dump()
    assert all("id" not in voice.model_dump() for voice in result.voices)


@pytest.mark.asyncio
async def test_full_568_voice_snapshot_is_never_truncated_to_builder_presets(monkeypatch, scope):
    snapshot = service.VoiceSnapshot(
        tuple(
            VoiceInfo(
                name=f"fr-FR-Test{index}Neural",
                display_name=f"Test {index}",
                category="standard",
                language="fr-FR",
            )
            for index in range(567)
        )
        + (
            VoiceInfo(
                name="fr-FR-Vivienne:DragonHDLatestNeural",
                display_name="Vivienne",
                category="hd",
                language="fr-FR",
            ),
        ),
        time.time(),
    )
    monkeypatch.setattr(
        api,
        "discover_voice_catalog",
        AsyncMock(return_value=service.VoiceDiscovery(scope, snapshot)),
    )
    result = await api.list_available_voices()
    assert result.catalog_complete and result.verified_against_region
    assert result.total == result.total_available == 568
    assert {voice.name for voice in result.voices} == {voice.name for voice in snapshot.voices}


@pytest.mark.asyncio
@pytest.mark.parametrize("catalog_state", ["regional", "empty", "unavailable"])
async def test_routing_capabilities_do_not_claim_regional_mai_availability(
    monkeypatch, voices, catalog_state
):
    scope = service.SpeechVoiceScope(
        "northcentralus", "https://speech.example.invalid", "resource-one", ""
    )
    snapshot = (
        None
        if catalog_state == "unavailable"
        else service.VoiceSnapshot(voices if catalog_state == "regional" else (), time.time())
    )
    monkeypatch.setattr(
        api,
        "discover_voice_catalog",
        AsyncMock(return_value=service.VoiceDiscovery(scope, snapshot)),
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/agent-builder")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/agent-builder/voices")

    assert response.status_code == 200
    data = response.json()
    assert data["runtime_transcription_models"] == {
        "cascade": ["mai-transcribe-2", "azure-speech", "mai-transcribe"],
        "voicelive": [
            "mai-transcribe-2",
            "mai-transcribe",
            "azure-speech",
            "gpt-4o-transcribe",
            "gpt-4o-mini-transcribe",
            "whisper-1",
        ],
    }
    assert data["region"] == "northcentralus"
    assert all(voice["category"] != "mai" for voice in data["voices"])
    assert data["verified_against_region"] is (snapshot is not None)
    assert data["catalog_complete"] is (snapshot is not None)
    if catalog_state == "empty":
        assert data["voices"] == []


@pytest.mark.asyncio
async def test_filters_do_not_turn_a_regional_catalog_into_a_preset_allowlist(
    monkeypatch, scope, voices
):
    monkeypatch.setattr(
        api,
        "discover_voice_catalog",
        AsyncMock(
            return_value=service.VoiceDiscovery(scope, service.VoiceSnapshot(voices, time.time()))
        ),
    )
    result = await api.list_available_voices(language="fr", category="hd")
    assert [voice.name for voice in result.voices] == ["fr-FR-Vivienne:DragonHDLatestNeural"]
    assert result.total_available == 3
    assert not result.catalog_complete
    assert result.verified_against_region


@pytest.mark.asyncio
async def test_authoritative_empty_result_does_not_invent_available_voices(monkeypatch, scope):
    monkeypatch.setattr(
        api,
        "discover_voice_catalog",
        AsyncMock(
            return_value=service.VoiceDiscovery(scope, service.VoiceSnapshot((), time.time()))
        ),
    )
    result = await api.list_available_voices()
    assert result.voices == []
    assert result.catalog_complete
    assert result.verified_against_region


@pytest.mark.asyncio
async def test_failed_discovery_is_an_explicit_limited_fallback(monkeypatch, scope):
    monkeypatch.setattr(
        api,
        "discover_voice_catalog",
        AsyncMock(
            return_value=service.VoiceDiscovery(scope, None, warning="Speech is unavailable.")
        ),
    )
    result = await api.list_available_voices()
    assert result.status == "degraded"
    assert result.source == "static-catalog"
    assert not result.catalog_complete
    assert not result.verified_against_region
    assert result.warnings
    assert all(voice.category != "mai" for voice in result.voices)


@pytest.mark.asyncio
async def test_explicit_offline_presets_do_not_contact_azure(monkeypatch, scope):
    discover = AsyncMock()
    monkeypatch.setattr(api, "discover_voice_catalog", discover)
    monkeypatch.setattr(api, "speech_voice_scope", lambda: scope)
    # include_unverified now supplements the regional list, as in upstream.
    result = await api.list_available_voices(presets_only=True)
    discover.assert_not_awaited()
    assert any(voice.category == "mai" for voice in result.voices)
    assert not result.verified_against_region
    assert not result.catalog_complete


def test_sdk_query_keeps_locale_style_and_gender_without_synthesizing(monkeypatch):
    import azure.cognitiveservices.speech as speechsdk

    config = Mock()
    make_config = Mock(return_value=config)
    native_voice = SimpleNamespace(
        short_name="de-DE-KatjaNeural",
        local_name="Katja",
        locale="de-DE",
        gender=SimpleNamespace(name="Female"),
        voice_type=SimpleNamespace(name="OnlineNeural"),
        style_list=["cheerful"],
        status=speechsdk.SynthesisVoiceStatus(1),
    )
    synth = Mock()
    synth.get_voices_async.return_value.get.return_value = SimpleNamespace(
        reason=speechsdk.ResultReason.VoicesListRetrieved,
        voices=[native_voice],
    )
    factory = Mock(return_value=synth)
    monkeypatch.setattr(speechsdk, "SpeechConfig", make_config)
    monkeypatch.setattr(speechsdk, "SpeechSynthesizer", factory)
    snapshot = service._query_voice_snapshot(
        service.SpeechVoiceScope("westus2", "https://speech.example.invalid", "", "test-key")
    )
    make_config.assert_called_once_with(
        subscription="test-key", endpoint="https://speech.example.invalid"
    )
    factory.assert_called_once_with(speech_config=config, audio_config=None)
    synth.get_voices_async.assert_called_once_with()
    synth.speak_text_async.assert_not_called()
    assert snapshot.voices[0].language == "de-DE"
    assert snapshot.voices[0].gender == "Female"
    assert snapshot.voices[0].styles == ["cheerful"]
    assert snapshot.voices[0].status == native_voice.status.name


@pytest.mark.asyncio
async def test_cache_is_scoped_to_resource_and_supports_force_refresh(monkeypatch, scope, voices):
    monkeypatch.setattr(service, "speech_voice_scope", lambda: scope)
    query = Mock(side_effect=lambda _: service.VoiceSnapshot(voices, time.time()))
    monkeypatch.setattr(service, "_query_voice_snapshot", query)
    assert not (await service.discover_voice_catalog()).cached
    assert (await service.discover_voice_catalog()).cached
    assert query.call_count == 1
    await service.discover_voice_catalog(use_cache=False)
    assert query.call_count == 2
    other = service.SpeechVoiceScope("eastus", "https://other.example.invalid", "other", "")
    monkeypatch.setattr(service, "speech_voice_scope", lambda: other)
    assert not (await service.discover_voice_catalog()).cached
    assert query.call_count == 3


@pytest.mark.asyncio
async def test_sdk_work_is_off_the_event_loop_and_concurrent_reads_share_it(
    monkeypatch, scope, voices
):
    monkeypatch.setattr(service, "speech_voice_scope", lambda: scope)
    entered = threading.Event()
    release = threading.Event()
    main_thread = threading.get_ident()
    worker_threads = []

    def query(_):
        worker_threads.append(threading.get_ident())
        entered.set()
        release.wait(timeout=2)
        return service.VoiceSnapshot(voices, time.time())

    monkeypatch.setattr(service, "_query_voice_snapshot", query)
    tasks = [asyncio.create_task(service.discover_voice_catalog()) for _ in range(4)]
    try:
        await asyncio.to_thread(entered.wait, 1)
    finally:
        release.set()
    results = await asyncio.gather(*tasks)
    assert len(worker_threads) == 1
    assert worker_threads[0] != main_thread
    assert all(result.snapshot.voices == voices for result in results)


@pytest.mark.asyncio
async def test_timeouts_do_not_start_another_sdk_request(monkeypatch, scope, voices):
    monkeypatch.setattr(service, "speech_voice_scope", lambda: scope)
    monkeypatch.setattr(service, "DISCOVERY_TIMEOUT_SECONDS", 0.01)
    release = threading.Event()
    query = Mock(
        side_effect=lambda _: (release.wait(timeout=2), service.VoiceSnapshot(voices, time.time()))[
            1
        ]
    )
    monkeypatch.setattr(service, "_query_voice_snapshot", query)
    try:
        assert (await service.discover_voice_catalog()).snapshot is None
        assert (await service.discover_voice_catalog()).snapshot is None
        assert query.call_count == 1
    finally:
        release.set()


@pytest.mark.asyncio
async def test_same_resource_stale_cache_is_labelled_and_failures_are_throttled(
    monkeypatch, scope, voices
):
    monkeypatch.setattr(service, "speech_voice_scope", lambda: scope)
    old = service.VoiceSnapshot(voices, time.time() - service.CATALOG_TTL_SECONDS - 1)
    service._cache[scope.cache_key] = old
    query = Mock(side_effect=service.VoiceCatalogUnavailable("Speech is unavailable."))
    monkeypatch.setattr(service, "_query_voice_snapshot", query)
    result = await service.discover_voice_catalog()
    assert result.snapshot == old
    assert result.cached and result.stale and result.warning
    await service.discover_voice_catalog()
    assert query.call_count == 1
    await service.discover_voice_catalog(use_cache=False)
    assert query.call_count == 2
    other = service.SpeechVoiceScope("eastus", "", "other", "")
    monkeypatch.setattr(service, "speech_voice_scope", lambda: other)
    assert (await service.discover_voice_catalog()).snapshot is None
