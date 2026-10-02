from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from apps.artagent.backend.registries.agentstore.base import ModelConfig
from apps.artagent.backend.voice.genesys.handler import (
    GenesysVoiceLiveHandler,
    _OutboundAudioFrame,
)
from azure.ai.voicelive.models import ServerEventType
from fastapi.websockets import WebSocketState


class _FakeWebSocket:
    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.client_state = WebSocketState.CONNECTED
        self.state = SimpleNamespace()
        self.app = SimpleNamespace(state=SimpleNamespace(redis=None))
        self.sent_text: list[str] = []
        self.sent_bytes: list[bytes] = []

    async def send_text(self, data: str) -> None:
        self.sent_text.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.sent_bytes.append(data)


def _make_handler() -> tuple[GenesysVoiceLiveHandler, _FakeWebSocket]:
    ws = _FakeWebSocket()
    handler = GenesysVoiceLiveHandler(websocket=ws, session_id="genesys-session")
    handler._running = True
    handler._AUDIO_CHUNK_SIZE = 4
    handler._AUDIO_PACE_MS = 0
    handler._MAX_OUTBOUND_AUDIO_BYTES = 64
    return handler, ws


def _drain_queue(handler: GenesysVoiceLiveHandler) -> list[object]:
    items: list[object] = []
    while True:
        try:
            items.append(handler._outbound_queue.get_nowait())
        except asyncio.QueueEmpty:
            return items


def _sent_types(ws: _FakeWebSocket) -> list[str]:
    return [json.loads(payload)["type"] for payload in ws.sent_text]


class _FakeVoiceLiveConnection:
    def __init__(self) -> None:
        self.input_audio_buffer = SimpleNamespace(append=AsyncMock())

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _EventVoiceLiveConnection(_FakeVoiceLiveConnection):
    def __init__(self, events: list[object]) -> None:
        super().__init__()
        self._events = iter(events)

    async def __anext__(self):
        try:
            event = next(self._events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc
        await asyncio.sleep(0)
        return event


class _FakeConnectionManager:
    def __init__(self, connection: _FakeVoiceLiveConnection) -> None:
        self.connection = connection
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True


class _FakeLiveOrchestrator:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.start = AsyncMock()
        self.cleanup = Mock()
        self.cancel_and_join_tasks = AsyncMock()
        self._sync_to_memo_manager = Mock()
        self.handle_event = AsyncMock()


@pytest.mark.asyncio
async def test_barge_in_invalidates_queued_audio_and_drops_late_delta() -> None:
    handler, _ = _make_handler()

    await handler._enqueue_binary(b"abcdefgh", response_id="resp-old")
    await handler._flush_audio_buffer(response_id="resp-old")
    handler._active_response_ids.add("resp-old")
    handler._current_response_id = "resp-old"

    await handler._handle_voicelive_event(
        SimpleNamespace(type=ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED),
        ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED,
    )

    queued = _drain_queue(handler)
    assert all(not isinstance(item, _OutboundAudioFrame) for item in queued)
    assert [
        item["parameters"]["entities"][0]["type"] for item in queued if isinstance(item, dict)
    ] == ["barge_in"]
    assert "resp-old" in handler._cancelled_response_ids

    await handler._handle_voicelive_event(
        SimpleNamespace(
            type=ServerEventType.RESPONSE_AUDIO_DELTA,
            response_id="resp-old",
            delta=b"\x00\x00\x01\x00\x02\x00",
        ),
        ServerEventType.RESPONSE_AUDIO_DELTA,
    )

    assert handler._pending_audio_bytes == 0
    assert handler._response_audio_buffers == {}

    await handler._handle_voicelive_event(
        SimpleNamespace(
            type=ServerEventType.RESPONSE_AUDIO_DELTA,
            response_id="resp-new",
            delta=b"\x00\x00\x01\x00\x02\x00",
        ),
        ServerEventType.RESPONSE_AUDIO_DELTA,
    )

    assert "resp-new" in handler._response_audio_buffers
    assert handler._pending_audio_bytes > 0


@pytest.mark.asyncio
async def test_unidentified_audio_delta_is_dropped_instead_of_reusing_current_response() -> None:
    handler, _ = _make_handler()
    handler._current_response_id = "resp-known"

    await handler._handle_voicelive_event(
        SimpleNamespace(
            type=ServerEventType.RESPONSE_AUDIO_DELTA,
            delta=b"\x00\x00\x01\x00\x02\x00",
        ),
        ServerEventType.RESPONSE_AUDIO_DELTA,
    )

    assert handler._pending_audio_bytes == 0
    assert handler._response_audio_buffers == {}


@pytest.mark.asyncio
async def test_control_messages_keep_monotonic_seq_after_audio_invalidation() -> None:
    handler, _ = _make_handler()

    await handler._enqueue_message(
        handler._protocol.create_opened({"format": "PCMU", "rate": 8000})
    )
    await handler._enqueue_binary(b"abcdefgh", response_id="resp-old")
    await handler._flush_audio_buffer(response_id="resp-old")
    handler._active_response_ids.add("resp-old")
    handler._current_response_id = "resp-old"

    await handler._handle_voicelive_event(
        SimpleNamespace(type=ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED),
        ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED,
    )
    await handler._handle_close()

    queued = _drain_queue(handler)
    messages = [item for item in queued if isinstance(item, dict)]

    assert all(not isinstance(item, _OutboundAudioFrame) for item in queued)
    assert [message["type"] for message in messages] == ["opened", "event", "closed"]
    assert [message["seq"] for message in messages] == [1, 2, 3]


@pytest.mark.asyncio
async def test_event_loop_reads_speech_started_before_done_audio_drain() -> None:
    handler, ws = _make_handler()
    handler._AUDIO_PACE_MS = 60_000
    await handler.start()

    handler._connection = _EventVoiceLiveConnection(
        [
            SimpleNamespace(
                type=ServerEventType.RESPONSE_AUDIO_DELTA,
                response_id="resp-old",
                delta=b"\x00\x00\x01\x00\x02\x00",
            ),
            SimpleNamespace(
                type=ServerEventType.RESPONSE_AUDIO_DONE,
                response_id="resp-old",
            ),
            SimpleNamespace(type=ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED),
            SimpleNamespace(
                type=ServerEventType.RESPONSE_AUDIO_DELTA,
                response_id="resp-old",
                delta=b"\x03\x00\x04\x00\x05\x00",
            ),
        ]
    )
    handler._orchestrator = _FakeLiveOrchestrator()

    await handler._event_loop()
    await asyncio.sleep(0)
    await handler.stop()

    assert "resp-old" in handler._cancelled_response_ids or handler._cancelled_response_ids == set()
    assert ws.sent_bytes == []
    assert "event" in _sent_types(ws)
    assert handler._pending_audio_bytes == 0
    assert handler._response_audio_buffers == {}


@pytest.mark.asyncio
async def test_stop_cleans_up_pacer_writer_and_partial_runtime() -> None:
    handler, ws = _make_handler()
    await handler.start()
    handler._connection_cm = _FakeConnectionManager(_FakeVoiceLiveConnection())
    handler._connection = handler._connection_cm.connection
    handler._orchestrator = _FakeLiveOrchestrator()
    handler._event_task = asyncio.create_task(asyncio.sleep(60))

    await handler._enqueue_binary(b"abcdefgh", response_id="resp-stop")

    await handler.stop()

    assert handler._pacer_task is None
    assert handler._writer_task is None
    assert handler._event_task is None
    assert handler._connection is None
    assert handler._connection_cm is None
    assert handler._orchestrator is None
    assert handler._pending_audio_bytes == 0
    assert ws.sent_bytes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deployment_id", "profile"),
    [
        ("gpt-realtime", "byom-azure-openai-chat-completion"),
        ("gpt-realtime-mini", "byom-azure-openai-chat-completion"),
        ("phi4-mm-realtime", "byom-azure-openai-chat-completion"),
    ],
)
async def test_connect_drops_conflicting_byom_query_before_connect(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    deployment_id: str,
    profile: str,
) -> None:
    from apps.artagent.backend.voice.genesys import handler as genesys_handler
    from apps.artagent.backend.voice.voicelive import handler as voicelive_handler

    handler, _ = _make_handler()
    captured: dict[str, object] = {}
    fake_connection = _FakeVoiceLiveConnection()
    fake_cm = _FakeConnectionManager(fake_connection)
    fake_orchestrator = _FakeLiveOrchestrator()

    class _Agent:
        session = {}

        def get_model_for_mode(self, mode: str) -> ModelConfig:
            assert mode == "voicelive"
            return ModelConfig(deployment_id=deployment_id)

        def get_byom_query(self) -> dict[str, str]:
            return {"profile": profile}

    monkeypatch.setattr(
        genesys_handler,
        "get_settings",
        lambda: SimpleNamespace(
            ws_max_msg_size=1024,
            ws_heartbeat=30,
            ws_timeout=10,
            azure_voicelive_endpoint="wss://voice.example",
            azure_voicelive_model="gpt-realtime",
            has_api_key_auth=False,
        ),
    )
    monkeypatch.setattr(
        handler,
        "_resolve_agents",
        AsyncMock(return_value=({"StartAgent": _Agent()}, SimpleNamespace(), "StartAgent", {})),
    )
    monkeypatch.setattr(
        voicelive_handler.VoiceLiveSDKHandler,
        "_build_credential",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        genesys_handler, "connect", lambda **kwargs: captured.update(kwargs) or fake_cm
    )
    monkeypatch.setattr(
        genesys_handler, "LiveOrchestrator", lambda *args, **kwargs: fake_orchestrator
    )
    monkeypatch.setattr(genesys_handler, "register_voicelive_orchestrator", Mock())
    monkeypatch.setattr(genesys_handler, "unregister_voicelive_orchestrator", Mock())

    await handler._connect_voicelive()
    await handler.stop()

    assert captured.get("query") is None
    assert "api_version" not in captured
    assert "byom_profile_model_conflict" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("transcription", [None, "mai-transcribe-2", "azure-speech"])
async def test_connect_passes_byom_query_and_shared_credential_helper(
    monkeypatch: pytest.MonkeyPatch,
    transcription: str | None,
) -> None:
    from apps.artagent.backend.voice.genesys import handler as genesys_handler
    from apps.artagent.backend.voice.voicelive import handler as voicelive_handler

    handler, _ = _make_handler()
    captured: dict[str, object] = {}
    fake_connection = _FakeVoiceLiveConnection()
    fake_cm = _FakeConnectionManager(fake_connection)
    fake_orchestrator = _FakeLiveOrchestrator()
    credential = object()

    class _Agent:
        session = {"input_audio_transcription_settings": {"model": transcription}}

        def get_model_for_mode(self, mode: str) -> ModelConfig:
            assert mode == "voicelive"
            return ModelConfig(deployment_id="o3-mini")

        def get_byom_query(self) -> dict[str, str]:
            return {
                "profile": "byom-azure-openai-chat-completion",
                "foundry-resource-override": "resource-1",
            }

    monkeypatch.setattr(
        genesys_handler,
        "get_settings",
        lambda: SimpleNamespace(
            ws_max_msg_size=1024,
            ws_heartbeat=30,
            ws_timeout=10,
            azure_voicelive_endpoint="wss://voice.example",
            azure_voicelive_model="gpt-realtime",
            has_api_key_auth=False,
        ),
    )
    monkeypatch.setattr(
        handler,
        "_resolve_agents",
        AsyncMock(
            return_value=(
                {"StartAgent": _Agent()},
                SimpleNamespace(),
                "StartAgent",
                {},
            )
        ),
    )
    monkeypatch.setattr(
        voicelive_handler.VoiceLiveSDKHandler,
        "_build_credential",
        AsyncMock(return_value=credential),
    )

    def _fake_connect(**kwargs):
        captured.update(kwargs)
        return fake_cm

    monkeypatch.setattr(genesys_handler, "connect", _fake_connect)
    orchestrator_factory = Mock(return_value=fake_orchestrator)
    monkeypatch.setattr(genesys_handler, "LiveOrchestrator", orchestrator_factory)
    monkeypatch.setattr(genesys_handler, "register_voicelive_orchestrator", Mock())
    monkeypatch.setattr(genesys_handler, "unregister_voicelive_orchestrator", Mock())

    await handler._connect_voicelive()
    await handler.stop()

    assert captured["credential"] is credential
    assert captured["model"] == "o3-mini"
    assert captured.get("api_version") == (
        None if transcription == "azure-speech" else "2026-04-10"
    )
    assert orchestrator_factory.call_args.kwargs["byom_profile"] == (
        "byom-azure-openai-chat-completion"
    )
    assert captured["query"] == {
        "profile": "byom-azure-openai-chat-completion",
        "foundry-resource-override": "resource-1",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "done_event_type", [ServerEventType.RESPONSE_AUDIO_DONE, ServerEventType.RESPONSE_DONE]
)
async def test_done_flush_failure_sends_single_disconnect_and_cleans_up(
    done_event_type: ServerEventType,
) -> None:
    handler, ws = _make_handler()
    await handler.start()
    handler._session_opened = True
    handler._outbound_audio_response_id = "resp-bad"
    handler._outbound_audio_encoder = SimpleNamespace(
        flush=Mock(side_effect=ValueError("incomplete sample byte pair"))
    )
    handler._active_response_ids.add("resp-bad")
    handler._current_response_id = "resp-bad"

    event = SimpleNamespace(type=done_event_type, response_id="resp-bad")
    if done_event_type == ServerEventType.RESPONSE_DONE:
        event = SimpleNamespace(
            type=done_event_type,
            response=SimpleNamespace(id="resp-bad"),
        )

    await handler._handle_voicelive_event(event, done_event_type)
    assert handler._terminal_shutdown_task is not None
    await asyncio.wait_for(handler._terminal_shutdown_task, timeout=1.0)

    disconnects = [
        json.loads(payload)
        for payload in ws.sent_text
        if json.loads(payload)["type"] == "disconnect"
    ]
    assert len(disconnects) == 1
    assert handler._writer_task is None
    assert handler._outbound_audio_response_id is None
    assert handler._connection is None
    assert handler._pending_audio_bytes == 0


@pytest.mark.asyncio
async def test_partial_connect_failure_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.artagent.backend.voice.genesys import handler as genesys_handler
    from apps.artagent.backend.voice.voicelive import handler as voicelive_handler

    handler, _ = _make_handler()
    fake_connection = _FakeVoiceLiveConnection()
    fake_cm = _FakeConnectionManager(fake_connection)

    class _FailingOrchestrator(_FakeLiveOrchestrator):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.start = AsyncMock(side_effect=RuntimeError("start failed"))

    class _Agent:
        session = {}

        def get_model_for_mode(self, _mode: str) -> ModelConfig:
            return ModelConfig(deployment_id="gpt-realtime")

        def get_byom_query(self) -> None:
            return None

    monkeypatch.setattr(
        genesys_handler,
        "get_settings",
        lambda: SimpleNamespace(
            ws_max_msg_size=1024,
            ws_heartbeat=30,
            ws_timeout=10,
            azure_voicelive_endpoint="wss://voice.example",
            azure_voicelive_model="gpt-realtime",
            has_api_key_auth=False,
        ),
    )
    monkeypatch.setattr(
        handler,
        "_resolve_agents",
        AsyncMock(return_value=({"StartAgent": _Agent()}, SimpleNamespace(), "StartAgent", {})),
    )
    monkeypatch.setattr(
        voicelive_handler.VoiceLiveSDKHandler,
        "_build_credential",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(genesys_handler, "connect", lambda **kwargs: fake_cm)
    monkeypatch.setattr(genesys_handler, "LiveOrchestrator", _FailingOrchestrator)
    monkeypatch.setattr(genesys_handler, "register_voicelive_orchestrator", Mock())
    unregister = Mock()
    monkeypatch.setattr(genesys_handler, "unregister_voicelive_orchestrator", unregister)

    with pytest.raises(RuntimeError, match="start failed"):
        await handler._connect_voicelive()

    assert fake_cm.exited is True
    assert handler._connection is None
    assert handler._connection_cm is None
    unregister.assert_called_once()
    assert unregister.call_args.args == ("genesys-session",)
    assert isinstance(unregister.call_args.kwargs["expected"], _FailingOrchestrator)
