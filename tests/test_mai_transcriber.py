"""MAI input tests using the real VoiceLive SDK above an offline WebSocket boundary."""

from __future__ import annotations

import asyncio
import base64
import copy
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import aiohttp
import pytest
import pytest_asyncio
from apps.artagent.backend.registries.agentstore.base import SpeechConfig, UnifiedAgent
from apps.artagent.backend.voice import handler as cascade
from apps.artagent.backend.voice.shared.config_resolver import OrchestratorConfigResult
from apps.artagent.backend.voice.shared.context import TransportType, VoiceSessionContext
from apps.artagent.backend.voice.shared.errors import WS_CLOSE_CODE_VOICE_ERROR, emit_voice_error
from apps.artagent.backend.voice.speech_cascade import mai_transcriber as mai
from apps.artagent.backend.voice.speech_cascade.handler import (
    SpeechEvent,
    SpeechEventType,
    ThreadBridge,
)
from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ClientAuthenticationError
from fastapi import WebSocketDisconnect
from fastapi.websockets import WebSocketState
from src.stateful.state_managment import MemoManager


class FakeSocket:
    """Only the wire is fake: SDK request serialization and event decoding run normally."""

    def __init__(self) -> None:
        self.incoming = asyncio.Queue()
        self.sent: list[dict] = []
        self.closed = False
        self.close_code = 1000
        self.ack = True
        self.ack_overrides: dict = {}
        self.handshake_started = asyncio.Event()
        self.handshake_gate: asyncio.Event | None = None
        self.handshake_error: Exception | None = None
        self.upload_started = asyncio.Event()
        self.upload_gate: asyncio.Event | None = None
        self.close_started = asyncio.Event()
        self.close_gate: asyncio.Event | None = None

    async def __aenter__(self):
        self.handshake_started.set()
        if self.handshake_gate is not None:
            await self.handshake_gate.wait()
        if self.handshake_error is not None:
            raise self.handshake_error
        return self

    async def __aexit__(self, *args):
        self.close_started.set()
        if self.close_gate is not None:
            await self.close_gate.wait()
        self.closed = True

    async def send_str(self, data: str) -> None:
        payload = json.loads(data)
        if payload["type"] == "input_audio_buffer.append":
            self.upload_started.set()
            if self.upload_gate is not None:
                await self.upload_gate.wait()
        self.sent.append(payload)
        if payload["type"] == "session.update" and self.ack:
            session = copy.deepcopy(payload["session"])
            session.update(self.ack_overrides)
            self.push({"type": "session.updated", "session": session})

    async def receive(self):
        return await self.incoming.get()

    def push(self, event: dict) -> None:
        self.incoming.put_nowait(
            aiohttp.WSMessage(
                aiohttp.WSMsgType.TEXT,
                json.dumps({"event_id": "test-event", **event}),
                "",
            )
        )

    def disconnect(self) -> None:
        self.incoming.put_nowait(aiohttp.WSMessage(aiohttp.WSMsgType.CLOSE, "", ""))


class FakeHTTP:
    def __init__(self, socket: FakeSocket) -> None:
        self.socket = socket
        self.closed = False
        self.url: str | None = None
        self.options: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def ws_connect(self, url: str, **kwargs):
        self.url = url
        self.options = kwargs
        return self.socket


@pytest_asyncio.fixture
async def mai_input(monkeypatch: pytest.MonkeyPatch):
    bundles = []
    pending_http = []
    monkeypatch.setattr(mai, "load_default_phrases_from_env", lambda: set())
    monkeypatch.setattr(
        mai,
        "get_settings",
        lambda: SimpleNamespace(
            azure_voicelive_endpoint="https://resource.services.ai.azure.com/",
            ws_heartbeat=20,
            ws_max_msg_size=1024 * 1024,
        ),
    )
    monkeypatch.setattr(
        VoiceLiveSDKHandler,
        "_build_credential",
        AsyncMock(return_value=AzureKeyCredential("offline-test-key")),
    )
    monkeypatch.setattr(
        mai.aiohttp, "ClientSession", Mock(side_effect=lambda **kwargs: pending_http.pop(0))
    )

    def make(
        *,
        transport=TransportType.BROWSER,
        speech=None,
        sample_rate=None,
        queue_size=50,
    ):
        socket = FakeSocket()
        http = FakeHTTP(socket)
        context = VoiceSessionContext(session_id=f"mai-test-{len(bundles)}", transport=transport)
        queue = asyncio.Queue(maxsize=queue_size)
        bridge = ThreadBridge()
        bridge.set_main_loop(asyncio.get_running_loop(), context.session_id)
        errors = AsyncMock()
        partials = AsyncMock()
        barge_in = AsyncMock()
        provider = mai.MAITranscriber(
            context,
            speech=speech
            or SpeechConfig(transcription_model="mai-transcribe", candidate_languages=["en-US"]),
            speech_queue=queue,
            thread_bridge=bridge,
            barge_in_handler=barge_in,
            on_error=errors,
            on_partial=partials,
            sample_rate=sample_rate,
        )
        bundle = SimpleNamespace(
            provider=provider,
            socket=socket,
            http=http,
            context=context,
            queue=queue,
            bridge=bridge,
            errors=errors,
            partials=partials,
            barge_in=barge_in,
        )
        pending_http.append(http)
        bundles.append(bundle)
        return bundle

    yield make
    for bundle in bundles:
        await bundle.provider.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transport,sample_rate,expected",
    [
        (TransportType.BROWSER, None, 24000),
        (TransportType.ACS, None, 16000),
        (TransportType.ACS, 24000, 24000),
    ],
)
async def test_real_session_contract_and_ordered_audio(
    mai_input, transport, sample_rate, expected
) -> None:
    bundle = mai_input(transport=transport, sample_rate=sample_rate)
    await bundle.provider.start()
    query = parse_qs(urlsplit(bundle.http.url).query)
    assert query == {"api-version": ["2026-04-10"], "model": ["gpt-4.1"]}
    assert urlsplit(bundle.http.url).path == "/voice-live/realtime"
    session = bundle.socket.sent[0]["session"]
    assert session == {
        "modalities": ["text"],
        "input_audio_format": "pcm16",
        "input_audio_sampling_rate": expected,
        "input_audio_transcription": {"model": "mai-transcribe", "language": "en"},
        "turn_detection": {
            "type": "server_vad",
            "create_response": False,
            "silence_duration_ms": 800,
        },
    }
    await bundle.provider.send_audio(b"\x01\x00" * 100)
    await bundle.provider.send_audio(b"\x02\x00" * 100)
    await asyncio.wait_for(bundle.provider._audio_queue.join(), 1)
    sent_audio = [base64.b64decode(event["audio"]) for event in bundle.socket.sent[1:]]
    assert sent_audio == [b"\x01\x00" * 100, b"\x02\x00" * 100]
    assert {event["type"] for event in bundle.socket.sent} == {
        "session.update",
        "input_audio_buffer.append",
    }
    await bundle.provider.stop()
    assert bundle.http.closed and bundle.socket.closed


@pytest.mark.asyncio
async def test_default_mai_2_is_sent_verbatim_and_rejects_alias_acknowledgement(mai_input) -> None:
    bundle = mai_input(speech=SpeechConfig())
    bundle.socket.ack_overrides = {"input_audio_transcription": {"model": "mai-transcribe"}}
    with pytest.raises(mai.MAITranscriptionError, match="did not acknowledge mai-transcribe-2"):
        await bundle.provider.start()
    assert bundle.socket.sent[0]["session"]["input_audio_transcription"] == {
        "model": "mai-transcribe-2"
    }
    assert bundle.http.closed and bundle.socket.closed
    assert [event["type"] for event in bundle.socket.sent] == ["session.update"]


@pytest.mark.asyncio
async def test_async_auth_reuses_selected_credential_without_closing_it(
    mai_input, monkeypatch
) -> None:
    bundle = mai_input()
    credential = SimpleNamespace(
        get_token=AsyncMock(return_value=SimpleNamespace(token="offline-token")),
        close=AsyncMock(),
    )
    monkeypatch.setattr(
        VoiceLiveSDKHandler, "_build_credential", AsyncMock(return_value=credential)
    )
    await bundle.provider.start()
    assert bundle.http.options["headers"] == {"Authorization": "Bearer offline-token"}
    credential.get_token.assert_awaited_once_with("https://cognitiveservices.azure.com/.default")
    await bundle.provider.stop()
    credential.close.assert_not_called()


@pytest.mark.asyncio
async def test_semantic_vad_is_still_response_disabled(mai_input) -> None:
    bundle = mai_input(
        speech=SpeechConfig(
            transcription_model="mai-transcribe",
            use_semantic_segmentation=True,
            vad_silence_timeout_ms=1250,
            candidate_languages=["fr-FR"],
        )
    )
    await bundle.provider.start()
    session = bundle.socket.sent[0]["session"]
    assert session["turn_detection"] == {
        "type": "azure_semantic_vad_multilingual",
        "create_response": False,
        "silence_duration_ms": 1250,
    }
    assert session["input_audio_transcription"]["language"] == "fr"


@pytest.mark.asyncio
async def test_multilanguage_allowlist_not_silently_claimed(mai_input, monkeypatch) -> None:
    warning = Mock()
    monkeypatch.setattr(mai.logger, "warning", warning)
    bundle = mai_input(speech=SpeechConfig(transcription_model="mai-transcribe"))
    await bundle.provider.start()
    assert bundle.socket.sent[0]["session"]["input_audio_transcription"] == {
        "model": "mai-transcribe"
    }
    assert "allowlist is not applied" in warning.call_args.args[0]


@pytest.mark.asyncio
async def test_partial_barge_in_guard_and_ordered_final_events(mai_input) -> None:
    bundle = mai_input()
    await bundle.provider.start()
    bundle.socket.push({"type": "input_audio_buffer.speech_started", "item_id": "first"})
    bundle.socket.push(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "item_id": "first",
            "delta": "Hello",
        }
    )
    bundle.socket.push({"type": "input_audio_buffer.committed", "item_id": "first"})
    bundle.socket.push(
        {"type": "input_audio_buffer.committed", "item_id": "second", "previous_item_id": "first"}
    )
    bundle.socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "second",
            "transcript": "Second turn",
        }
    )
    bundle.socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "first",
            "transcript": "First turn",
        }
    )
    first = await asyncio.wait_for(bundle.queue.get(), 1)
    second = await asyncio.wait_for(bundle.queue.get(), 1)
    assert [first.text, second.text] == ["First turn", "Second turn"]
    assert first.event_type == second.event_type == SpeechEventType.FINAL
    assert first.recognition_start_ts and first.recognition_end_perf
    bundle.partials.assert_awaited_once_with("Hello", "", None, "first", 1)
    assert first.turn_id == "first" and first.sequence == 2
    assert second.turn_id == "second" and second.sequence == 1
    bundle.barge_in.assert_awaited_once()
    assert bundle.bridge.turn_guard_active
    await bundle.provider._handle_event(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "item_id": "third",
            "delta": "Guarded partial",
        }
    )
    await bundle.provider._handle_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "first",
            "transcript": "Duplicate turn",
        }
    )
    assert bundle.queue.empty()
    bundle.partials.assert_awaited_once()
    bundle.barge_in.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_waits_for_ack_and_rejects_audio_before_ready(mai_input) -> None:
    bundle = mai_input()
    bundle.socket.ack = False
    start = asyncio.create_task(bundle.provider.start())
    await bundle.socket.handshake_started.wait()
    with pytest.raises(mai.MAITranscriptionError, match="not ready"):
        await bundle.provider.send_audio(b"\x00\x00")
    assert not start.done()
    bundle.socket.push({"type": "session.updated", "session": bundle.provider._session().as_dict()})
    await asyncio.wait_for(start, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"input_audio_transcription": {"model": "azure-speech"}},
        {"turn_detection": {"create_response": True}},
        {"input_audio_sampling_rate": 16000},
        {"modalities": ["text", "audio"]},
    ],
)
async def test_unacknowledged_contract_fails_without_substitution(mai_input, overrides) -> None:
    bundle = mai_input()
    bundle.socket.ack_overrides = overrides
    with pytest.raises(mai.MAITranscriptionError, match="did not acknowledge"):
        await bundle.provider.start()
    assert bundle.http.closed and bundle.socket.closed
    assert [event["type"] for event in bundle.socket.sent] == ["session.update"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type", ["error", "conversation.item.input_audio_transcription.failed"]
)
async def test_runtime_error_emits_speech_error_and_closes_input(mai_input, event_type) -> None:
    bundle = mai_input()
    await bundle.provider.start()
    bundle.socket.push(
        {
            "type": event_type,
            "item_id": "first",
            "error": {"code": "unsupported_region", "message": "MAI is unavailable in this region"},
        }
    )
    await asyncio.wait_for(bundle.provider._task, 1)
    error = bundle.errors.await_args.args[0]
    assert "unsupported_region" in error
    assert "No other transcription model was substituted" in error
    bundle.errors.assert_awaited_once_with(error)
    assert bundle.queue.empty()
    assert bundle.http.closed and bundle.socket.closed
    with pytest.raises(mai.MAITranscriptionError, match="unsupported_region"):
        await bundle.provider.send_audio(b"\x00\x00")
    with pytest.raises(mai.MAITranscriptionError, match="unsupported_region"):
        await bundle.provider.start()


@pytest.mark.asyncio
async def test_service_disconnect_is_an_error_not_a_successful_silent_iterator(mai_input) -> None:
    bundle = mai_input()
    await bundle.provider.start()
    bundle.socket.disconnect()
    await asyncio.wait_for(bundle.provider._task, 1)
    bundle.errors.assert_awaited_once()
    assert bundle.http.closed and bundle.socket.closed
    with pytest.raises(mai.MAITranscriptionError):
        await bundle.provider.send_audio(b"\x00\x00")


@pytest.mark.asyncio
async def test_unexpected_host_response_is_fatal_and_never_played(mai_input) -> None:
    bundle = mai_input()
    await bundle.provider.start()
    bundle.socket.push({"type": "response.created", "response": {"id": "unwanted"}})
    await asyncio.wait_for(bundle.provider._task, 1)
    assert "input-only connection" in bundle.errors.call_args.args[0]
    assert [event["type"] for event in bundle.socket.sent] == ["session.update"]


@pytest.mark.asyncio
async def test_audio_queue_is_byte_bounded_and_backpressures_without_loss(mai_input) -> None:
    bundle = mai_input()
    bundle.socket.upload_gate = asyncio.Event()
    await bundle.provider.start()
    audio = b"\x01\x00" * (mai.MAX_AUDIO_CHUNK_BYTES * 60 // 2)
    write = asyncio.create_task(bundle.provider.send_audio(audio))
    await bundle.socket.upload_started.wait()
    await asyncio.sleep(0)
    assert not write.done()
    assert bundle.provider._audio_queue.qsize() == 50
    assert all(
        len(chunk) <= mai.MAX_AUDIO_CHUNK_BYTES for chunk in bundle.provider._audio_queue._queue
    )
    bundle.socket.upload_gate.set()
    await asyncio.wait_for(write, 1)
    await asyncio.wait_for(bundle.provider._audio_queue.join(), 1)
    assert b"".join(base64.b64decode(event["audio"]) for event in bundle.socket.sent[1:]) == audio


@pytest.mark.asyncio
async def test_audio_upload_stall_is_explicit_and_cleans_up(mai_input, monkeypatch) -> None:
    monkeypatch.setattr(mai, "IO_TIMEOUT_S", 0.03)
    bundle = mai_input()
    bundle.socket.upload_gate = asyncio.Event()
    await bundle.provider.start()
    await bundle.provider.send_audio(b"\x01\x00" * 100)
    await asyncio.wait_for(bundle.provider._task, 1)
    assert "audio upload stalled" in bundle.errors.call_args.args[0]
    assert bundle.http.closed and bundle.socket.closed


@pytest.mark.asyncio
async def test_full_final_queue_fails_explicitly_instead_of_evicting_turns(
    mai_input, monkeypatch
) -> None:
    monkeypatch.setattr(mai, "IO_TIMEOUT_S", 0.03)
    bundle = mai_input(queue_size=1)
    existing = SpeechEvent(SpeechEventType.GREETING, "Keep this event")
    bundle.queue.put_nowait(existing)
    await bundle.provider.start()
    bundle.socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "full",
            "transcript": "Must not silently disappear",
        }
    )
    await asyncio.wait_for(bundle.provider._task, 1)
    assert "final speech queue stalled" in bundle.errors.call_args.args[0]
    assert bundle.queue.get_nowait() is existing
    assert bundle.http.closed and bundle.socket.closed


@pytest.mark.asyncio
async def test_pending_turn_storage_is_bounded(mai_input, monkeypatch) -> None:
    monkeypatch.setattr(mai, "MAX_PENDING_TURNS", 2)
    bundle = mai_input()
    await bundle.provider.start()
    for item_id in ("first", "second", "overflow"):
        bundle.socket.push({"type": "input_audio_buffer.committed", "item_id": item_id})
    await asyncio.wait_for(bundle.provider._task, 1)
    assert "bounded pending transcription queue" in bundle.errors.call_args.args[0]


@pytest.mark.asyncio
async def test_startup_cancellation_closes_http_during_handshake(mai_input) -> None:
    bundle = mai_input()
    bundle.socket.handshake_gate = asyncio.Event()
    start = asyncio.create_task(bundle.provider.start())
    await bundle.socket.handshake_started.wait()
    start.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start
    assert bundle.http.closed
    assert bundle.provider._task.done()
    assert bundle.provider._connection is None


@pytest.mark.asyncio
async def test_startup_timeout_includes_auth_and_handshake(mai_input, monkeypatch) -> None:
    monkeypatch.setattr(mai, "START_TIMEOUT_S", 0.03)
    bundle = mai_input()
    bundle.socket.handshake_gate = asyncio.Event()
    with pytest.raises(mai.MAITranscriptionError, match="TimeoutError"):
        await bundle.provider.start()
    assert bundle.http.closed
    assert bundle.provider._task.done()


@pytest.mark.asyncio
async def test_auth_failure_surfaces_without_azure_stt_fallback(mai_input, monkeypatch) -> None:
    bundle = mai_input()
    monkeypatch.setattr(
        VoiceLiveSDKHandler,
        "_build_credential",
        AsyncMock(side_effect=ClientAuthenticationError("Credential unavailable")),
    )
    with pytest.raises(mai.MAITranscriptionError, match="Credential unavailable"):
        await bundle.provider.start()
    assert bundle.socket.sent == []
    assert bundle.provider._task.done()


@pytest.mark.asyncio
async def test_two_sessions_have_isolated_audio_events_and_cleanup(mai_input) -> None:
    first, second = mai_input(), mai_input()
    await first.provider.start()
    await second.provider.start()
    await first.provider.send_audio(b"\x01\x00")
    await asyncio.wait_for(first.provider._audio_queue.join(), 1)
    assert len(second.socket.sent) == 1
    await first.provider.stop()
    assert not second.http.closed
    second.socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "second",
            "transcript": "Still listening",
        }
    )
    assert (await asyncio.wait_for(second.queue.get(), 1)).text == "Still listening"
    assert first.queue.empty()


@pytest.mark.asyncio
async def test_stop_unblocks_queued_audio_without_reporting_success(mai_input) -> None:
    bundle = mai_input()
    bundle.socket.upload_gate = asyncio.Event()
    await bundle.provider.start()
    write = asyncio.create_task(
        bundle.provider.send_audio(b"\x00\x00" * mai.MAX_AUDIO_CHUNK_BYTES * 60)
    )
    await bundle.socket.upload_started.wait()
    await bundle.provider.stop()
    with pytest.raises(mai.MAITranscriptionError, match="closed while queuing"):
        await asyncio.wait_for(write, 1)
    assert bundle.provider._audio_queue.empty()
    assert bundle.http.closed and bundle.socket.closed


@pytest.mark.asyncio
async def test_invalid_pcm_and_unsupported_sdk_options_are_explicit(mai_input, monkeypatch) -> None:
    bundle = mai_input()
    await bundle.provider.start()
    with pytest.raises(ValueError, match="even byte count"):
        await bundle.provider.send_audio(b"\x00")
    with pytest.raises(ValueError, match="16000 or 24000"):
        mai_input(sample_rate=48000)
    with pytest.raises(ValueError, match="enable_diarization"):
        mai_input(
            speech=SpeechConfig(transcription_model="mai-transcribe", enable_diarization=True)
        )
    monkeypatch.setattr(mai, "load_default_phrases_from_env", lambda: {"Contoso"})
    with pytest.raises(ValueError, match="SPEECH_RECOGNIZER_DEFAULT_PHRASES"):
        mai_input()


@pytest_asyncio.fixture
async def cascade_input(mai_input, monkeypatch):
    from apps.artagent.backend.voice.shared import errors

    handlers = []
    monkeypatch.setattr(cascade, "INACTIVITY_TIMEOUT_S", 0)
    monkeypatch.setattr(cascade, "send_session_envelope", AsyncMock())
    monkeypatch.setattr(cascade, "send_user_transcript", AsyncMock())
    monkeypatch.setattr(cascade, "send_user_partial_transcript", AsyncMock())
    monkeypatch.setattr(errors, "emit_voice_error", AsyncMock())
    monkeypatch.setattr(cascade.VoiceHandler, "_derive_greeting", AsyncMock(return_value=""))
    monkeypatch.setattr(cascade.VoiceHandler, "_log_connection_banner", Mock())

    async def make(
        *,
        provider=None,
        transport=TransportType.BROWSER,
        scenario=None,
        scoped_agents=None,
        session_agents=None,
        last_session_agent=None,
        active_agent=None,
        fail_stt=False,
    ):
        bundle = mai_input(transport=transport)
        memo = MemoManager(session_id=bundle.context.session_id)
        memo.persist_to_redis_async = AsyncMock()
        if active_agent:
            memo.set_corememory("active_agent", active_agent)
        agent = UnifiedAgent(
            name="Start",
            speech=SpeechConfig(
                candidate_languages=["en-US"],
                **({"transcription_model": provider} if provider is not None else {}),
            ),
        )
        app_state = SimpleNamespace(
            redis=object(),
            start_agent="Start",
            unified_agents={"Start": agent},
            speech_executor=None,
        )
        stt_client = SimpleNamespace(
            push_stream=object(),
            set_partial_result_callback=Mock(),
            set_final_result_callback=Mock(),
            set_cancel_callback=Mock(),
            start=Mock(),
            stop=Mock(),
            write_bytes=Mock(),
            vad_silence_timeout_ms=800,
            use_semantic=False,
            candidate_languages=["en-US"],
        )
        tts_client = Mock()
        app_state.tts_pool = SimpleNamespace(
            acquire_for_session=AsyncMock(return_value=(tts_client, "base")),
            release_for_session=AsyncMock(),
        )
        app_state.stt_pool = SimpleNamespace(
            acquire_for_session=AsyncMock(return_value=(stt_client, "base")),
            release_for_session=AsyncMock(),
        )
        if fail_stt:
            app_state.stt_pool.acquire_for_session.side_effect = TimeoutError("pool full")
        websocket = SimpleNamespace(
            state=SimpleNamespace(),
            client_state=WebSocketState.CONNECTED,
            application_state=WebSocketState.CONNECTED,
            close=AsyncMock(),
        )
        config = cascade.VoiceHandlerConfig(
            websocket=websocket,
            session_id=bundle.context.session_id,
            call_connection_id="acs-call" if transport == TransportType.ACS else None,
            transport=transport,
            scenario=scenario,
        )
        monkeypatch.setattr(
            cascade.VoiceHandler, "_load_memory_manager", AsyncMock(return_value=memo)
        )
        monkeypatch.setattr(
            cascade,
            "get_session_agent",
            lambda sid, name=None: (session_agents or {}).get(name) if name else last_session_agent,
        )
        resolved = OrchestratorConfigResult(
            start_agent="ScopedStart",
            agents=scoped_agents or {},
            scenario=SimpleNamespace(name=scenario) if scenario else None,
            scenario_name=scenario,
        )
        monkeypatch.setattr(cascade, "resolve_orchestrator_config", Mock(return_value=resolved))
        processed = asyncio.Event()

        async def route(cm, transcript):
            processed.set()
            return ""

        route_mock = AsyncMock(side_effect=route)
        monkeypatch.setattr(
            cascade.VoiceHandler, "_create_orchestrator_wrapper", Mock(return_value=route_mock)
        )
        bundle.state = app_state
        bundle.websocket = websocket
        bundle.memo = memo
        bundle.stt_client = stt_client
        bundle.tts_client = tts_client
        bundle.route = route_mock
        bundle.processed = processed
        bundle.config = config
        bundle.error_emitter = errors.emit_voice_error
        if fail_stt:
            return bundle
        handler = await cascade.VoiceHandler.create(config, app_state)
        handlers.append(handler)
        bundle.handler = handler
        if handler._mai_transcriber:
            bundle.provider = handler._mai_transcriber
        return bundle

    yield make
    for handler in handlers:
        await handler.stop()


@pytest.mark.asyncio
async def test_explicit_azure_cascade_uses_and_releases_only_azure_pools(cascade_input) -> None:
    bundle = await cascade_input(provider="azure-speech")
    await bundle.handler.start()
    await bundle.handler._handle_browser_audio(b"\x00\x00" * 100)
    assert bundle.handler._mai_transcriber is None
    bundle.state.stt_pool.acquire_for_session.assert_awaited_once()
    bundle.stt_client.start.assert_called_once()
    bundle.stt_client.write_bytes.assert_called_once_with(b"\x00\x00" * 100)
    assert bundle.http.url is None
    await bundle.handler.stop()
    bundle.state.stt_pool.release_for_session.assert_awaited_once_with(
        bundle.config.session_id, bundle.stt_client
    )
    bundle.state.tts_pool.release_for_session.assert_awaited_once_with(
        bundle.config.session_id, bundle.tts_client
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", [TransportType.BROWSER, TransportType.ACS])
async def test_unified_cascade_routes_real_mai_input_without_acquiring_stt(
    cascade_input, transport
) -> None:
    bundle = await cascade_input(transport=transport)
    await bundle.handler.start()
    assert bundle.socket.sent[0]["session"]["input_audio_transcription"]["model"] == (
        "mai-transcribe-2"
    )
    audio = b"\x01\x00" * 100
    if transport == TransportType.BROWSER:
        await bundle.handler._handle_browser_audio(audio)
    else:
        await bundle.handler.handle_media_message(
            {"kind": "AudioMetadata", "audioMetadata": {"sampleRate": 16000, "channels": 1}}
        )
        await bundle.handler.handle_media_message(
            {"kind": "AudioData", "audioData": {"data": base64.b64encode(audio).decode("ascii")}}
        )
    await asyncio.wait_for(bundle.provider._audio_queue.join(), 1)
    assert base64.b64decode(bundle.socket.sent[-1]["audio"]) == audio
    bundle.socket.push(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "turn",
            "transcript": "Check my balance",
        }
    )
    await asyncio.wait_for(bundle.processed.wait(), 1)
    bundle.route.assert_awaited_once_with(cm=bundle.memo, transcript="Check my balance")
    assert bundle.handler._stt_thread is None
    assert bundle.handler.context.stt_client is None
    bundle.state.stt_pool.acquire_for_session.assert_not_called()
    with pytest.raises(RuntimeError, match="write_audio_async"):
        bundle.handler.write_audio(audio)
    await bundle.handler.stop()
    await bundle.handler.stop()
    assert bundle.http.closed and bundle.socket.closed
    bundle.state.stt_pool.release_for_session.assert_not_called()
    bundle.state.tts_pool.release_for_session.assert_awaited_once_with(
        bundle.config.call_connection_id or bundle.config.session_id, bundle.tts_client
    )


@pytest.mark.asyncio
async def test_yaml_scenario_start_not_last_created_agent_selects_provider(cascade_input) -> None:
    scoped = UnifiedAgent(
        name="ScopedStart", speech=SpeechConfig(transcription_model="mai-transcribe")
    )
    unrelated = UnifiedAgent(
        name="Unrelated", speech=SpeechConfig(transcription_model="azure-speech")
    )
    bundle = await cascade_input(
        provider="azure-speech",
        scenario="yaml-scenario",
        scoped_agents={"ScopedStart": scoped},
        last_session_agent=unrelated,
    )
    assert bundle.handler.context.current_agent is scoped
    assert bundle.memo.get_value_from_corememory("active_agent") == "ScopedStart"
    assert bundle.handler._mai_transcriber is not None
    bundle.state.stt_pool.acquire_for_session.assert_not_called()


@pytest.mark.asyncio
async def test_named_session_override_of_scenario_start_selects_provider(cascade_input) -> None:
    yaml_agent = UnifiedAgent(name="ScopedStart")
    edited = UnifiedAgent(
        name="ScopedStart", speech=SpeechConfig(transcription_model="mai-transcribe")
    )
    bundle = await cascade_input(
        provider="azure-speech",
        scenario="yaml-scenario",
        scoped_agents={"ScopedStart": yaml_agent},
        session_agents={"ScopedStart": edited},
        last_session_agent=UnifiedAgent(name="NotTheStart"),
    )
    assert bundle.handler.context.current_agent is edited
    assert bundle.handler._mai_transcriber is not None
    bundle.state.stt_pool.acquire_for_session.assert_not_called()


@pytest.mark.asyncio
async def test_persisted_active_agent_not_last_created_agent_selects_provider(
    cascade_input,
) -> None:
    active = UnifiedAgent(name="Active", speech=SpeechConfig(transcription_model="mai-transcribe"))
    bundle = await cascade_input(
        provider="azure-speech",
        session_agents={"Active": active},
        last_session_agent=UnifiedAgent(name="NotActive"),
        active_agent="Active",
    )
    assert bundle.handler.context.current_agent is active
    assert bundle.handler._mai_transcriber is not None
    bundle.state.stt_pool.acquire_for_session.assert_not_called()


@pytest.mark.asyncio
async def test_mai_startup_failure_is_not_announced_ready_and_releases_tts(cascade_input) -> None:
    bundle = await cascade_input()
    bundle.socket.ack_overrides = {"input_audio_transcription": {"model": "azure-speech"}}
    with pytest.raises(mai.MAITranscriptionError, match="No other transcription model"):
        await bundle.handler.start()
    labels = [call.kwargs["event_label"] for call in cascade.send_session_envelope.await_args_list]
    assert labels == []
    bundle.error_emitter.assert_awaited_once()
    error = bundle.error_emitter.await_args.args[1]
    assert error.code == "MAITranscriptionUnavailable"
    assert error.source == "stt" and error.fatal
    bundle.websocket.close.assert_awaited_once()
    assert bundle.handler._stopped
    assert bundle.http.closed and bundle.socket.closed
    bundle.state.tts_pool.release_for_session.assert_awaited_once()
    bundle.state.stt_pool.release_for_session.assert_not_called()


@pytest.mark.asyncio
async def test_mai_runtime_disconnect_stops_owner_and_releases_tts(cascade_input) -> None:
    bundle = await cascade_input()
    await bundle.handler.start()
    bundle.socket.disconnect()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(bundle.provider._task, 1)
    await asyncio.wait_for(bundle.handler.stop(), 1)
    assert bundle.handler._stopped
    bundle.state.tts_pool.release_for_session.assert_awaited_once()
    bundle.state.stt_pool.release_for_session.assert_not_called()
    bundle.websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_acs_mismatched_sample_rate_fails_instead_of_mislabeling_pcm(cascade_input) -> None:
    bundle = await cascade_input(transport=TransportType.ACS)
    await bundle.handler.start()
    with pytest.raises(ValueError, match="received 48000 Hz"):
        await bundle.handler.handle_media_message(
            {"kind": "AudioMetadata", "audioMetadata": {"sampleRate": 48000, "channels": 1}}
        )
    assert bundle.handler._stopped
    assert bundle.http.closed
    bundle.state.stt_pool.release_for_session.assert_not_called()


@pytest.mark.asyncio
async def test_azure_pool_startup_failure_releases_tts_with_correct_pool_api(cascade_input) -> None:
    bundle = await cascade_input(provider="azure-speech", fail_stt=True)
    with pytest.raises(WebSocketDisconnect):
        await cascade.VoiceHandler.create(bundle.config, bundle.state)
    bundle.state.tts_pool.release_for_session.assert_awaited_once_with(
        bundle.config.session_id, bundle.tts_client
    )
    bundle.state.stt_pool.release_for_session.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_stop_retains_provider_cleanup_after_first_caller_cancels(mai_input):
    bundle = mai_input()
    await bundle.provider.start()
    bundle.socket.close_gate = asyncio.Event()
    first = asyncio.create_task(bundle.provider.stop())
    await asyncio.wait_for(bundle.socket.close_started.wait(), 1)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(bundle.provider.stop())
    await asyncio.sleep(0)
    assert not second.done()
    assert not bundle.provider._stop_task.cancelled()
    bundle.socket.close_gate.set()
    await asyncio.wait_for(second, 1)
    assert bundle.socket.closed and bundle.http.closed
    assert bundle.provider._task.done()
    assert bundle.provider._stop_task.done()


@pytest.mark.asyncio
async def test_startup_failure_uses_real_shared_error_envelope(cascade_input, monkeypatch):
    from apps.artagent.backend.src.ws_helpers import shared_ws
    from apps.artagent.backend.voice.shared import errors

    bundle = await cascade_input()
    monkeypatch.setattr(errors, "emit_voice_error", emit_voice_error)
    monkeypatch.setattr(shared_ws, "send_session_envelope", AsyncMock(return_value=False))
    bundle.websocket.send_json = AsyncMock()
    bundle.socket.ack_overrides = {"turn_detection": {"create_response": True}}

    with pytest.raises(mai.MAITranscriptionError):
        await bundle.handler.start()

    envelope = bundle.websocket.send_json.await_args.args[0]
    assert envelope["type"] == "error"
    assert envelope["payload"]["code"] == "MAITranscriptionUnavailable"
    assert envelope["payload"]["source"] == "stt"
    assert envelope["payload"]["fatal"] is True
    assert "no other model was substituted" in envelope["payload"]["message"]
    bundle.websocket.close.assert_awaited_once_with(
        WS_CLOSE_CODE_VOICE_ERROR, "MAI transcription unavailable"
    )
    bundle.state.stt_pool.acquire_for_session.assert_not_called()
    bundle.state.tts_pool.release_for_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_mai_stop_timeout_withholds_owned_tts_lease_and_retains_failure(monkeypatch):
    from tests.test_cascade_runtime_ownership import app_state
    from tests.test_voice_handler_compat import MockWebSocket

    monkeypatch.setattr(mai, "load_default_phrases_from_env", lambda: set())
    monkeypatch.setattr(mai, "IO_TIMEOUT_S", 0.03)
    app = app_state()
    context = VoiceSessionContext(session_id="mai-stop-timeout")
    context.call_connection_id = context.session_id
    context.tts_client, context.tts_tier = await app.tts_pool.acquire_for_session(
        context.session_id
    )
    websocket = MockWebSocket()
    context._websocket = websocket
    handler = cascade.VoiceHandler(
        context,
        app,
        config=cascade.VoiceHandlerConfig(websocket=websocket, session_id=context.session_id),
    )
    provider = mai.MAITranscriber(
        context,
        speech=SpeechConfig(transcription_model="mai-transcribe"),
        speech_queue=handler._speech_queue,
        thread_bridge=handler._thread_bridge,
        barge_in_handler=AsyncMock(),
        on_error=AsyncMock(),
    )
    handler._mai_transcriber = provider
    gate = asyncio.Event()
    acknowledged = False

    async def recv():
        nonlocal acknowledged
        if not acknowledged:
            acknowledged = True
            return {"type": "session.updated", "session": provider._session().as_dict()}
        await asyncio.Event().wait()

    @asynccontextmanager
    async def connect():
        try:
            yield SimpleNamespace(session=SimpleNamespace(update=AsyncMock()), recv=recv)
        finally:
            await gate.wait()

    monkeypatch.setattr(provider, "_connect", connect)
    await provider.start()
    try:
        with pytest.raises(ExceptionGroup, match="could not be quiesced") as first:
            await asyncio.wait_for(handler.stop(), 1)
        assert not provider._task.done()
        assert app.tts_pool.released == app.stt_pool.released == 0
        with pytest.raises(ExceptionGroup) as repeated:
            await handler.stop()
        assert repeated.value is first.value
    finally:
        gate.set()
        await asyncio.gather(provider._task, return_exceptions=True)
