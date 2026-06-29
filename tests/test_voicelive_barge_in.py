"""
VoiceLive Barge-In / StopAudio Coverage
=======================================

VoiceLive is a managed pipeline, but trailing ``response.audio.delta`` events
from a response that was cancelled by barge-in could still be relayed to the
transport *after* a StopAudio (ACS replays them, so playback would not stop).

These tests pin the consistency guarantee shared with the cascade path:

  Once barge-in fires, no ``AudioData`` may reach the transport after StopAudio.

The handler drops trailing audio whose ``response_id`` was captured as
cancelled on ``INPUT_AUDIO_BUFFER_SPEECH_STARTED``; a fresh response clears the
stale cancellation set.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.websockets import WebSocketState

from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler
from azure.ai.voicelive.models import ServerEventType


class FakeWebSocket:
    """Minimal websocket capturing JSON sends with ordered history."""

    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.client_state = WebSocketState.CONNECTED
        self.state = SimpleNamespace()
        self.sent: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)


def _make_handler() -> tuple[VoiceLiveSDKHandler, FakeWebSocket]:
    ws = FakeWebSocket()
    handler = VoiceLiveSDKHandler(websocket=ws, session_id="sess", transport="acs")
    return handler, ws


def _audio_delta(response_id: str | None, data: bytes = b"\x00\x00") -> SimpleNamespace:
    return SimpleNamespace(
        type=ServerEventType.RESPONSE_AUDIO_DELTA,
        response_id=response_id,
        delta=data,
    )


def _kinds(ws: FakeWebSocket) -> list[str]:
    return [m.get("kind") for m in ws.sent if isinstance(m, dict)]


@pytest.mark.asyncio
async def test_drops_audio_from_cancelled_response():
    """A trailing delta from a cancelled response is not relayed to ACS."""
    handler, ws = _make_handler()
    handler._cancelled_response_ids.add("resp-old")

    await handler._forward_event_to_acs(_audio_delta("resp-old"))

    assert "AudioData" not in _kinds(ws)


@pytest.mark.asyncio
async def test_relays_fresh_response_and_clears_cancelled():
    """A fresh response is relayed and clears the stale cancellation set."""
    handler, ws = _make_handler()
    handler._cancelled_response_ids.add("resp-old")

    await handler._forward_event_to_acs(_audio_delta("resp-new"))

    assert "AudioData" in _kinds(ws)
    assert handler._cancelled_response_ids == set()


@pytest.mark.asyncio
async def test_no_audio_after_stopaudio_on_barge_in(monkeypatch):
    """End-to-end: barge-in sends StopAudio and drops the cancelled response's tail.

    The trailing audio delta from the interrupted response must not appear
    after the StopAudio on the wire.
    """
    handler, ws = _make_handler()

    # An assistant response is currently playing.
    handler._active_response_ids.add("resp-1")
    handler._current_response_id = "resp-1"

    # Avoid the heavier turn/metric machinery for this focused test.
    handler._finalize_turn_metrics = AsyncMock()
    handler._start_turn_span = AsyncMock()
    handler._messenger.begin_user_turn = Mock(return_value=None)

    # User starts speaking -> barge-in -> StopAudio.
    await handler._forward_event_to_acs(
        SimpleNamespace(type=ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED)
    )

    # A late delta from the interrupted response arrives after the stop.
    await handler._forward_event_to_acs(_audio_delta("resp-1"))

    kinds = _kinds(ws)
    assert "StopAudio" in kinds
    stop_idx = kinds.index("StopAudio")
    assert "AudioData" not in kinds[stop_idx + 1 :]


@pytest.mark.asyncio
async def test_barge_in_sends_stop_audio_for_acs():
    """Barge-in dispatches a strict StopAudio control message on the ACS transport."""
    handler, ws = _make_handler()
    handler._active_response_ids.add("resp-1")
    handler._current_response_id = "resp-1"
    handler._finalize_turn_metrics = AsyncMock()
    handler._start_turn_span = AsyncMock()
    handler._messenger.begin_user_turn = Mock(return_value=None)

    await handler._forward_event_to_acs(
        SimpleNamespace(type=ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED)
    )

    stop_messages = [m for m in ws.sent if m.get("kind") == "StopAudio"]
    assert stop_messages
    assert stop_messages[-1]["StopAudio"] == {}
    assert stop_messages[-1]["AudioData"] is None


@pytest.mark.asyncio
async def test_response_done_prunes_cancelled_set():
    """RESPONSE_DONE discards the response from the cancellation set."""
    handler, ws = _make_handler()
    handler._cancelled_response_ids.add("resp-1")

    handler._extract_response_id = Mock(return_value="resp-1")
    handler._should_stop_for_response = Mock(return_value=False)

    await handler._forward_event_to_acs(
        SimpleNamespace(type=ServerEventType.RESPONSE_DONE)
    )

    assert "resp-1" not in handler._cancelled_response_ids
