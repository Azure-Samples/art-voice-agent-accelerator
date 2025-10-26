import asyncio
import importlib
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

envelopes = importlib.import_module(
    "apps.rtagent.backend.src.ws_helpers.envelopes"
)
shared_ws = importlib.import_module(
    "apps.rtagent.backend.src.ws_helpers.shared_ws"
)
orchestrator = importlib.import_module(
    "apps.rtagent.backend.src.orchestration.artagent.orchestrator"
)


def test_make_envelope_family_shapes_payloads():
    session_id = "sess-1"
    base = envelopes.make_envelope(
        etype="event",
        sender="Tester",
        payload={"message": "hello"},
        topic="session",
        session_id=session_id,
    )

    status = envelopes.make_status_envelope(
        "ready", sender="System", topic="session", session_id=session_id
    )
    stream = envelopes.make_assistant_streaming_envelope(
        "hello", session_id=session_id
    )
    event = envelopes.make_event_envelope(
        "custom", {"foo": "bar"}, topic="session", session_id=session_id
    )

    for envelope in (base, status, stream, event):
        assert envelope["session_id"] == session_id
        assert "payload" in envelope
        assert envelope["type"]

    assert base["payload"]["message"] == "hello"
    assert status["payload"]["message"] == "ready"
    assert stream["payload"]["content"] == "hello"
    assert event["payload"]["data"]["foo"] == "bar"


def test_route_turn_signature_is_stable():
    signature = inspect.signature(orchestrator.route_turn)
    assert "cm" in signature.parameters
    assert "transcript" in signature.parameters
    assert "ws" in signature.parameters
    assert asyncio.iscoroutinefunction(orchestrator.route_turn)


@pytest.mark.asyncio
async def test_route_turn_completes_with_stubbed_dependencies(monkeypatch):
    class StubMemo:
        def __init__(self):
            self.session_id = "sess-rt"
            self.store = {}
            self.persist_calls = 0

        async def persist_background(self, _redis_mgr):
            self.persist_calls += 1

    memo = StubMemo()
    websocket = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            session_id="sess-rt",
            conn_id="conn-rt",
            orchestration_tasks=set(),
            lt=SimpleNamespace(record=lambda *a, **k: None),
            tts_client=MagicMock(),
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(
                conn_manager=SimpleNamespace(
                    send_to_connection=AsyncMock(),
                    broadcast_session=AsyncMock(),
                ),
                redis=MagicMock(),
                tts_pool=SimpleNamespace(
                    release_for_session=AsyncMock(), session_awareness_enabled=False
                ),
                stt_pool=SimpleNamespace(release_for_session=AsyncMock()),
                session_manager=MagicMock(),
            )
        ),
    )

    monkeypatch.setattr(orchestrator, "_build_turn_context", AsyncMock(return_value=SimpleNamespace()), raising=False)
    monkeypatch.setattr(orchestrator, "_execute_turn", AsyncMock(return_value={"assistant": "hi"}), raising=False)
    monkeypatch.setattr(orchestrator, "_finalize_turn", AsyncMock(), raising=False)
    monkeypatch.setattr(orchestrator, "send_tts_audio", AsyncMock(), raising=False)
    monkeypatch.setattr(orchestrator, "make_assistant_streaming_envelope", lambda *a, **k: {"payload": {"message": "hi"}}, raising=False)
    monkeypatch.setattr(orchestrator, "make_status_envelope", lambda *a, **k: {"payload": {"message": "ok"}}, raising=False)
    monkeypatch.setattr(orchestrator, "cm_get", lambda cm, key, default=None: cm.store.get(key, default), raising=False)
    monkeypatch.setattr(orchestrator, "cm_set", lambda cm, **kwargs: cm.store.update(kwargs), raising=False)
    monkeypatch.setattr(orchestrator, "maybe_terminate_if_escalated", AsyncMock(return_value=False), raising=False)

    async def specialist_handler(cm, transcript, ws, is_acs=False):
        cm.store["last_transcript"] = transcript

    monkeypatch.setattr(orchestrator, "get_specialist", lambda _name: specialist_handler, raising=False)
    monkeypatch.setattr(orchestrator, "create_service_handler_attrs", lambda **_: {}, raising=False)
    monkeypatch.setattr(orchestrator, "create_service_dependency_attrs", lambda **_: {}, raising=False)
    monkeypatch.setattr(orchestrator, "get_correlation_context", lambda ws, cm: (None, cm.session_id), raising=False)

    await orchestrator.route_turn(memo, "hello", websocket, is_acs=False)
    assert memo.persist_calls == 1
    assert memo.store["last_transcript"] == "hello"
