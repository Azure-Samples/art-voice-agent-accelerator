from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.websockets import WebSocketState

from apps.artagent.backend.api.v1.endpoints import media
from apps.artagent.backend.voice import TransportType
from src.enums.stream_modes import StreamMode


class FakeRedis:
    def __init__(self, values: dict[str, str | bytes] | None = None) -> None:
        self.values = values or {}
        self.requests: list[str] = []

    async def get_value_async(self, key: str):
        self.requests.append(key)
        return self.values.get(key)


class FakeConnectionManager:
    def __init__(self) -> None:
        self.meta = SimpleNamespace(handler=None)
        self.register = AsyncMock(return_value="conn-1")
        self.unregister = AsyncMock()
        self.get_connection_meta = AsyncMock(return_value=self.meta)
        self.get_call_context = AsyncMock(return_value=None)


class FakeSessionMetrics:
    def __init__(self) -> None:
        self.increment_connected = AsyncMock()
        self.increment_disconnected = AsyncMock()


class FakeWebSocket:
    def __init__(
        self,
        *,
        messages: list[dict] | None = None,
        call_connection_id: str = "call-123",
        redis_values: dict[str, str | bytes] | None = None,
    ) -> None:
        self.query_params = {"call_connection_id": call_connection_id}
        self.headers = {}
        self.state = SimpleNamespace()
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.closed = False
        self.close_code: int | None = None
        self.messages = list(messages or [])
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                redis=FakeRedis(redis_values),
                conn_manager=FakeConnectionManager(),
                session_metrics=FakeSessionMetrics(),
            )
        )

    async def receive(self):
        if self.messages:
            return self.messages.pop(0)
        return {"type": "websocket.close", "code": 1000}

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED


class FakeSpeechHandler:
    def __init__(self) -> None:
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.handle_media_message = AsyncMock()
        self.handle_audio_data = AsyncMock()
        self.handle_transcription_message = AsyncMock()


@pytest.mark.asyncio
async def test_create_media_handler_uses_speech_channel_for_acs_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACS MEDIA mode must create VoiceHandler, not a VoiceLive warm connection."""
    websocket = FakeWebSocket()
    fake_handler = FakeSpeechHandler()
    captured = {}

    async def fake_create(config, app_state):
        captured["config"] = config
        captured["app_state"] = app_state
        return fake_handler

    async def fail_if_voicelive_warmup_is_used(*args, **kwargs):
        raise AssertionError("ACS speech channel should not consume VoiceLive warmup")

    monkeypatch.setattr(media.VoiceHandler, "create", fake_create)
    monkeypatch.setattr(
        media,
        "consume_voicelive_call_warmup",
        fail_if_voicelive_warmup_is_used,
    )

    handler = await media._create_media_handler(
        websocket=websocket,
        call_connection_id="call-123",
        session_id="session-123",
        stream_mode=StreamMode.MEDIA,
    )

    assert handler is fake_handler
    assert captured["app_state"] is websocket.app.state
    assert captured["config"].transport == TransportType.ACS
    assert captured["config"].stream_mode == StreamMode.MEDIA
    assert captured["config"].call_connection_id == "call-123"
    assert captured["config"].session_id == "session-123"


@pytest.mark.asyncio
async def test_process_media_stream_dispatches_acs_json_to_speech_handler() -> None:
    payload = {
        "kind": "AudioData",
        "audioData": {"data": "AAAA", "timestamp": "2026-06-25T00:00:00Z"},
    }
    websocket = FakeWebSocket(
        messages=[
            {"type": "websocket.receive", "text": json.dumps(payload)},
            {"type": "websocket.close", "code": 1000},
        ]
    )
    handler = FakeSpeechHandler()

    await media._process_media_stream(
        websocket,
        handler,
        call_connection_id="call-123",
        stream_mode=StreamMode.MEDIA,
    )

    handler.handle_media_message.assert_awaited_once_with(payload)
    handler.handle_audio_data.assert_not_called()
    handler.handle_transcription_message.assert_not_called()


@pytest.mark.asyncio
async def test_acs_media_stream_speech_channel_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise ACS media websocket flow through speech-channel handler lifecycle."""
    payload = {"kind": "AudioData", "audioData": {"data": "AAAA"}}
    websocket = FakeWebSocket(
        messages=[
            {"type": "websocket.receive", "text": json.dumps(payload)},
            {"type": "websocket.close", "code": 1000},
        ],
        call_connection_id="call-acs-speech",
        redis_values={
            "call_stream_mode:call-acs-speech": b"media",
            "call_session_map:call-acs-speech": b"browser-session-1",
        },
    )
    handler = FakeSpeechHandler()
    captured = {}

    async def fake_send_agent_inventory(*args, **kwargs):
        return None

    async def fake_create(config, app_state):
        captured["config"] = config
        captured["app_state"] = app_state
        return handler

    async def fail_if_voicelive_warmup_is_used(*args, **kwargs):
        raise AssertionError("ACS speech channel should not consume VoiceLive warmup")

    monkeypatch.setattr(media, "send_agent_inventory", fake_send_agent_inventory)
    monkeypatch.setattr(media.VoiceHandler, "create", fake_create)
    monkeypatch.setattr(
        media,
        "consume_voicelive_call_warmup",
        fail_if_voicelive_warmup_is_used,
    )

    await media.acs_media_stream(websocket)

    websocket.app.state.conn_manager.register.assert_awaited_once()
    websocket.app.state.conn_manager.get_connection_meta.assert_awaited_once_with("conn-1")
    websocket.app.state.conn_manager.unregister.assert_awaited_once_with("conn-1")
    websocket.app.state.session_metrics.increment_connected.assert_awaited_once()
    websocket.app.state.session_metrics.increment_disconnected.assert_awaited_once()

    assert websocket.state.stream_mode == StreamMode.MEDIA
    assert websocket.state.session_id == "browser-session-1"
    assert websocket.state.call_connection_id == "call-acs-speech"
    assert websocket.app.state.conn_manager.meta.handler["media_handler"] is handler

    assert captured["app_state"] is websocket.app.state
    assert captured["config"].transport == TransportType.ACS
    assert captured["config"].stream_mode == StreamMode.MEDIA
    assert captured["config"].session_id == "browser-session-1"
    assert captured["config"].call_connection_id == "call-acs-speech"

    handler.start.assert_awaited_once()
    handler.handle_media_message.assert_awaited_once_with(payload)
    handler.handle_audio_data.assert_not_called()
    handler.stop.assert_awaited_once()
    assert websocket.closed is True
