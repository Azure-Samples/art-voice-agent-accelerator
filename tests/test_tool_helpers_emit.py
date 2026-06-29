"""Regression tests for tool frame emission to the frontend.

Covers the cross-worker delivery path for ACS (outbound call) tool frames.
On an outbound call the call's media WebSocket and the browser dashboard relay
frequently live on different worker processes, so a local-only broadcast never
reaches the UI. Tool frames must also be published to the distributed session
channel (mirroring assistant/status envelopes).
"""

import asyncio
from types import SimpleNamespace

import pytest

from apps.artagent.backend.voice.voicelive.tool_helpers import (
    push_tool_end,
    push_tool_start,
)


class _RecordingConnManager:
    def __init__(self) -> None:
        self.broadcast_session_calls: list[tuple[str, dict]] = []
        self.publish_calls: list[tuple[str, dict, str]] = []
        self.broadcast_calls: list[dict] = []

    async def broadcast_session(self, session_id: str, payload: dict) -> int:
        self.broadcast_session_calls.append((session_id, payload))
        return 1

    async def publish_session_envelope(
        self, session_id: str, payload: dict, *, event_label: str = "unspecified"
    ) -> bool:
        self.publish_calls.append((session_id, payload, event_label))
        return True

    async def broadcast(self, payload: dict) -> int:
        self.broadcast_calls.append(payload)
        return 0


def _make_ws(conn_manager: _RecordingConnManager) -> SimpleNamespace:
    app = SimpleNamespace(state=SimpleNamespace(conn_manager=conn_manager))
    return SimpleNamespace(app=app)


async def _drain_tasks() -> None:
    # _emit schedules delivery via asyncio.create_task; let those run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_acs_tool_start_publishes_cross_worker():
    cm = _RecordingConnManager()
    ws = _make_ws(cm)

    await push_tool_start(
        ws,
        tool_name="verify_identity",
        call_id="abc123",
        arguments={"name": "Jin Lee"},
        is_acs=True,
        session_id="session-1",
    )
    await _drain_tasks()

    # Local-worker broadcast happened.
    assert cm.broadcast_session_calls, "expected local session broadcast"
    # Cross-worker publish also happened so the relay on another worker gets it.
    assert cm.publish_calls, "expected distributed session publish"

    session_id, payload, event_label = cm.publish_calls[0]
    assert session_id == "session-1"
    assert payload["type"] == "tool_start"
    assert payload["tool"] == "verify_identity"
    assert event_label == "tool_start"


@pytest.mark.asyncio
async def test_acs_tool_end_publishes_cross_worker():
    cm = _RecordingConnManager()
    ws = _make_ws(cm)

    await push_tool_end(
        ws,
        tool_name="verify_identity",
        call_id="abc123",
        result={"success": False},
        is_acs=True,
        session_id="session-1",
    )
    await _drain_tasks()

    assert cm.broadcast_session_calls, "expected local session broadcast"
    assert cm.publish_calls, "expected distributed session publish"
    _, payload, _ = cm.publish_calls[0]
    assert payload["type"] == "tool_end"
    assert payload["tool"] == "verify_identity"
