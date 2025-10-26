import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketState
from config import GREETING

from apps.rtagent.backend.api.v1.endpoints import realtime


class DummySessionManager:
    def __init__(self) -> None:
        self.count = 0
        self.added: list[tuple[str, object]] = []
        self.removed: list[str] = []

    async def get_session_count(self) -> int:
        return self.count

    async def add_session(self, session_id: str, memo: object, websocket: object) -> None:
        self.added.append((session_id, memo))
        self.count += 1

    async def remove_session(self, session_id: str) -> bool:
        self.removed.append(session_id)
        if self.count:
            self.count -= 1
        return True


class DummyConnManager:
    def __init__(self) -> None:
        self.registered: list[tuple[str, str | None, set[str]]] = []
        self.unregistered: list[str] = []
        self.sent: list[tuple[str, object]] = []
        self.broadcasts: list[tuple[str, object]] = []
        self._stats: dict[str, object] = {"connections": 0, "by_topic": {}}
        self._conns: dict[str, SimpleNamespace] = {}

    def set_stats(self, stats: dict[str, object]) -> None:
        self._stats = stats

    async def register(
        self,
        websocket,
        *,
        client_type: str,
        topics: set[str],
        session_id: str | None = None,
        accept_already_done: bool = False,
    ) -> str:
        if not accept_already_done:
            await websocket.accept()
        conn_id = f"conn-{len(self.registered) + 1}"
        self.registered.append((client_type, session_id, topics))
        self._conns[conn_id] = SimpleNamespace(meta=SimpleNamespace(handler={}))
        return conn_id

    async def stats(self) -> dict[str, object]:
        return self._stats

    async def unregister(self, conn_id: str) -> None:
        self.unregistered.append(conn_id)
        self._conns.pop(conn_id, None)

    async def send_to_connection(self, conn_id: str, payload: object) -> None:
        self.sent.append((conn_id, payload))

    async def broadcast_session(self, session_id: str, payload: object) -> None:
        self.broadcasts.append((session_id, payload))


class DummyMetrics:
    def __init__(self) -> None:
        self.connected = 0
        self.disconnected = 0

    async def increment_connected(self) -> None:
        self.connected += 1

    async def increment_disconnected(self) -> None:
        self.disconnected += 1


@pytest.fixture()
def realtime_app():
    app = FastAPI()
    conn_manager = DummyConnManager()
    session_manager = DummySessionManager()
    metrics = DummyMetrics()
    app.state.conn_manager = conn_manager
    app.state.session_manager = session_manager
    app.state.session_metrics = metrics
    app.include_router(realtime.router, prefix="/api/v1/realtime")
    return app, conn_manager, session_manager, metrics


def test_get_realtime_status_returns_expected_payload(realtime_app):
    app, conn_manager, session_manager, _metrics = realtime_app
    session_manager.count = 3
    conn_manager.set_stats({"connections": 5, "by_topic": {"dashboard": 2}})

    with TestClient(app) as client:
        response = client.get("/api/v1/realtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["active_connections"]["dashboard_clients"] == 2
    assert payload["active_connections"]["conversation_sessions"] == 3
    assert payload["active_connections"]["total_connections"] == 5
    assert "/api/v1/realtime/dashboard/relay" in payload["websocket_endpoints"].values()


def test_dashboard_relay_endpoint_registers_and_cleans_up(realtime_app):
    app, conn_manager, _session_manager, metrics = realtime_app
    conn_manager.set_stats({"connections": 1, "by_topic": {"dashboard": 1}})

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/realtime/dashboard/relay?session_id=demo") as ws:
            ws.send_text("ping")

    assert conn_manager.registered == [("dashboard", "demo", {"dashboard"})]
    assert conn_manager.unregistered == ["conn-1"]
    assert metrics.connected == 1
    assert metrics.disconnected == 1


def test_conversation_endpoint_uses_helpers(monkeypatch, realtime_app):
    app, conn_manager, session_manager, metrics = realtime_app
    init_calls: list[tuple[str, str]] = []
    process_calls: list[tuple[str, str]] = []
    cleanup_calls: list[tuple[str, str]] = []

    async def fake_initialize(websocket, session_id, conn_id, orchestrator):
        init_calls.append((session_id, conn_id))
        return object()

    async def fake_process(websocket, session_id, memory_manager, orchestrator, conn_id):
        process_calls.append((session_id, conn_id))
        await websocket.close()

    async def fake_cleanup(websocket, session_id, memory_manager, conn_id):
        cleanup_calls.append((session_id, conn_id))
        metrics_obj = getattr(websocket.app.state, "session_metrics", None)
        if metrics_obj:
            await metrics_obj.increment_disconnected()

    monkeypatch.setattr(realtime, "_initialize_conversation_session", fake_initialize)
    monkeypatch.setattr(realtime, "_process_conversation_messages", fake_process)
    monkeypatch.setattr(realtime, "_cleanup_conversation_session", fake_cleanup)

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/realtime/conversation?session_id=session-42"):
            pass

    assert init_calls and process_calls and cleanup_calls
    assert session_manager.added[0][0] == "session-42"
    assert metrics.connected == 1
    assert metrics.disconnected == 1


@pytest.mark.asyncio
async def test_cleanup_conversation_session_releases_resources(realtime_app):
    app, conn_manager, session_manager, metrics = realtime_app
    conn_id = "conn-42"
    tts_client = MagicMock()
    stt_client = MagicMock()
    latency_tool = SimpleNamespace(cleanup_timers=MagicMock())
    orchestration_task = asyncio.create_task(asyncio.sleep(10))

    conn_manager._conns[conn_id] = SimpleNamespace(
        meta=SimpleNamespace(
            handler={
                "tts_client": tts_client,
                "audio_playing": True,
                "tts_cancel_event": asyncio.Event(),
                "stt_client": stt_client,
                "tts_tasks": {asyncio.create_task(asyncio.sleep(10))},
                "latency_tool": latency_tool,
            }
        )
    )

    tts_pool = SimpleNamespace(
        release_for_session=AsyncMock(return_value=True),
        session_awareness_enabled=True,
        snapshot=lambda: {},
    )
    stt_pool = SimpleNamespace(release_for_session=AsyncMock(return_value=True))
    websocket = SimpleNamespace(
        client_state=WebSocketState.CONNECTED,
        application_state=WebSocketState.CONNECTED,
        state=SimpleNamespace(orchestration_tasks={orchestration_task}),
        app=SimpleNamespace(
            state=SimpleNamespace(
                conn_manager=conn_manager,
                session_manager=session_manager,
                session_metrics=metrics,
                tts_pool=tts_pool,
                stt_pool=stt_pool,
            )
        ),
        close=AsyncMock(),
    )

    await realtime._cleanup_conversation_session(
        websocket, session_id="session-123", memory_manager=MagicMock(), conn_id=conn_id
    )

    assert conn_manager.unregistered == [conn_id]
    assert session_manager.removed == ["session-123"]
    assert metrics.disconnected == 1
    tts_pool.release_for_session.assert_awaited_once()
    stt_pool.release_for_session.assert_awaited_once()
    assert latency_tool.cleanup_timers.called
    assert orchestration_task.cancelled()


class StubMemoManager:
    def __init__(self) -> None:
        self.history = []
        self.persist_calls = 0

    def append_to_history(self, *args):
        self.history.append(args)

    async def persist_to_redis_async(self, _redis):
        self.persist_calls += 1


@pytest.mark.asyncio
async def test_initialize_conversation_session_sets_metadata(monkeypatch):
    memo = StubMemoManager()
    latency_tool = SimpleNamespace(cleanup_timers=MagicMock())

    class StubTTSSynth:
        def __init__(self):
            self.stopped = False

        def stop_speaking(self):
            self.stopped = True

    class StubSTTClient:
        def __init__(self):
            self.partial_cb = None
            self.final_cb = None
            self.started = False

        def set_partial_result_callback(self, cb):
            self.partial_cb = cb

        def set_final_result_callback(self, cb):
            self.final_cb = cb

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    tts_client = StubTTSSynth()
    stt_client = StubSTTClient()

    conn_manager = DummyConnManager()
    conn_id = "conn-1"
    conn_manager._conns[conn_id] = SimpleNamespace(meta=SimpleNamespace(handler={}))

    metrics = DummyMetrics()

    class StubWebSocket:
        def __init__(self):
            self.client_state = WebSocketState.CONNECTED
            self.application_state = WebSocketState.CONNECTED
            self.state = SimpleNamespace(orchestration_tasks=set())
            self.app = SimpleNamespace(
                state=SimpleNamespace(
                    conn_manager=conn_manager,
                    session_manager=DummySessionManager(),
                    session_metrics=metrics,
                    redis=MagicMock(),
                    tts_pool=SimpleNamespace(
                        acquire_for_session=AsyncMock(
                            return_value=(tts_client, SimpleNamespace(value="standard"))
                        ),
                        release_for_session=AsyncMock(return_value=True),
                        session_awareness_enabled=True,
                        snapshot=lambda: {},
                    ),
                    stt_pool=SimpleNamespace(
                        acquire_for_session=AsyncMock(
                            return_value=(stt_client, SimpleNamespace(value="base"))
                        ),
                        release_for_session=AsyncMock(return_value=True),
                        snapshot=lambda: {},
                    ),
                    auth_agent=SimpleNamespace(name="assistant"),
                )
            )

        async def close(self, *_, **__):
            return None

    websocket = StubWebSocket()

    monkeypatch.setattr(
        realtime.MemoManager,
        "from_redis",
        classmethod(lambda cls, session_id, redis_mgr: memo),
    )
    monkeypatch.setattr(realtime, "LatencyTool", lambda *_args: latency_tool)
    send_tts = AsyncMock()
    monkeypatch.setattr(realtime, "send_tts_audio", send_tts)

    memory_manager = await realtime._initialize_conversation_session(
        websocket, "session-123", conn_id, orchestrator=None
    )

    assert memory_manager is memo
    assert len(conn_manager.sent) == 1
    sent_conn_id, sent_payload = conn_manager.sent[0]
    assert sent_conn_id == conn_id
    assert sent_payload["payload"]["message"] == GREETING
    assert send_tts.await_count == 1
    assert stt_client.started
    assert websocket.state.tts_client is tts_client
    assert websocket.state.lt is latency_tool
    assert memo.history
    assert memo.persist_calls == 1


@pytest.mark.asyncio
async def test_process_conversation_messages_handles_stopwords(monkeypatch):
    conn_manager = DummyConnManager()
    conn_id = "conn-2"
    conn_manager._conns[conn_id] = SimpleNamespace(
        meta=SimpleNamespace(
            handler={
                "stt_client": MagicMock(write_bytes=MagicMock()),
                "user_buffer": "stop please",
                "lt": SimpleNamespace(cleanup_timers=MagicMock()),
            }
        )
    )

    class SequenceWebSocket:
        def __init__(self):
            self.client_state = WebSocketState.CONNECTED
            self.application_state = WebSocketState.CONNECTED
            self.state = SimpleNamespace(orchestration_tasks=set())
            self._messages = [
                {"type": "websocket.receive", "bytes": b"\x00\x01"},
            ]
            self.app = SimpleNamespace(
                state=SimpleNamespace(
                    conn_manager=conn_manager,
                    session_manager=DummySessionManager(),
                    session_metrics=DummyMetrics(),
                    redis=MagicMock(),
                )
            )

        async def receive(self):
            if self._messages:
                return self._messages.pop(0)
            return {"type": "websocket.disconnect", "code": 1000}

    websocket = SequenceWebSocket()
    memo_manager = MagicMock()
    monkeypatch.setattr(
        realtime,
        "check_for_stopwords",
        lambda prompt: prompt.strip() == "stop please",
    )
    send_tts = AsyncMock()
    monkeypatch.setattr(realtime, "send_tts_audio", send_tts)

    await realtime._process_conversation_messages(
        websocket,
        session_id="session-xyz",
        memory_manager=memo_manager,
        orchestrator=None,
        conn_id=conn_id,
    )

    stt_client = conn_manager._conns[conn_id].meta.handler["stt_client"]
    stt_client.write_bytes.assert_called_once()
    assert len(conn_manager.broadcasts) >= 2
    goodbye_payload = conn_manager.broadcasts[-1][1]
    assert "Goodbye" in goodbye_payload["payload"]["message"]
    send_tts.assert_awaited()
    assert conn_manager._conns[conn_id].meta.handler["user_buffer"] == ""


@pytest.mark.asyncio
async def test_process_dashboard_messages_reads_until_disconnect():
    class StubWebSocket:
        def __init__(self):
            self.client_state = WebSocketState.CONNECTED
            self.application_state = WebSocketState.CONNECTED
            self._messages = ["ping", "pong"]

        async def receive_text(self):
            if not self._messages:
                raise WebSocketDisconnect(code=1000)
            return self._messages.pop(0)

    websocket = StubWebSocket()
    with pytest.raises(WebSocketDisconnect):
        await realtime._process_dashboard_messages(websocket, client_id="dash-1")


@pytest.mark.asyncio
async def test_cleanup_dashboard_connection_handles_connected_socket(monkeypatch):
    close_called = asyncio.Event()

    async def close():
        close_called.set()

    metrics = DummyMetrics()
    conn_manager = DummyConnManager()
    conn_id = "conn-clean"
    conn_manager._conns[conn_id] = SimpleNamespace(meta=SimpleNamespace(handler={}))
    websocket = SimpleNamespace(
        client_state=WebSocketState.CONNECTED,
        application_state=WebSocketState.CONNECTED,
        app=SimpleNamespace(
            state=SimpleNamespace(
                conn_manager=conn_manager,
                session_metrics=metrics,
            )
        ),
        close=close,
    )

    await realtime._cleanup_dashboard_connection(websocket, client_id="dash", conn_id=conn_id)

    assert conn_manager.unregistered == [conn_id]
    assert metrics.disconnected == 1
    assert close_called.is_set()


@pytest.mark.asyncio
async def test_cleanup_conversation_session_releases_resources(monkeypatch, realtime_app):
    app, conn_manager, session_manager, metrics = realtime_app
    conn_id = "conn-42"
    tts_client = MagicMock()
    stt_client = MagicMock()
    latency_tool = SimpleNamespace(cleanup_timers=MagicMock())
    orchestration_task = asyncio.create_task(asyncio.sleep(10))

    conn_manager._conns[conn_id] = SimpleNamespace(
        meta=SimpleNamespace(
            handler={
                "tts_client": tts_client,
                "audio_playing": True,
                "tts_cancel_event": asyncio.Event(),
                "stt_client": stt_client,
                "tts_tasks": {asyncio.create_task(asyncio.sleep(10))},
                "latency_tool": latency_tool,
            }
        )
    )
    fake_aoai = ModuleType("src.pools.aoai_pool")
    fake_release = AsyncMock(return_value=None)
    fake_aoai.release_session_client = fake_release
    monkeypatch.setitem(sys.modules, "src.pools.aoai_pool", fake_aoai)

    tts_pool = SimpleNamespace(
        release_for_session=AsyncMock(return_value=True),
        session_awareness_enabled=True,
        snapshot=lambda: {},
    )
    stt_pool = SimpleNamespace(release_for_session=AsyncMock(return_value=True))
    websocket = SimpleNamespace(
        client_state=WebSocketState.CONNECTED,
        application_state=WebSocketState.CONNECTED,
        state=SimpleNamespace(orchestration_tasks={orchestration_task}),
        app=SimpleNamespace(
            state=SimpleNamespace(
                conn_manager=conn_manager,
                session_manager=session_manager,
                session_metrics=metrics,
                tts_pool=tts_pool,
                stt_pool=stt_pool,
            )
        ),
        close=AsyncMock(),
    )

    await realtime._cleanup_conversation_session(
        websocket, session_id="session-123", memory_manager=MagicMock(), conn_id=conn_id
    )
    await asyncio.sleep(0)

    assert conn_manager.unregistered == [conn_id]
    assert session_manager.removed == ["session-123"]
    assert metrics.disconnected == 1
    tts_pool.release_for_session.assert_awaited_once()
    stt_pool.release_for_session.assert_awaited_once()
    assert latency_tool.cleanup_timers.called
    assert orchestration_task.cancelled()
    assert fake_release.await_count == 1
