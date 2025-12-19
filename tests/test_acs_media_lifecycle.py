import asyncio
import base64
import gc
import importlib.util
import json
import sys
import weakref
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.websockets import WebSocketState
from src.enums.stream_modes import StreamMode

openai_stub = ModuleType("apps.artagent.backend.src.services.openai_services")
openai_stub.client = Mock()
sys.modules.setdefault("apps.artagent.backend.src.services.openai_services", openai_stub)

acs_helpers_stub = ModuleType("apps.artagent.backend.src.services.acs.acs_helpers")


async def _play_response_with_queue(*_args, **_kwargs):
    return None


acs_helpers_stub.play_response_with_queue = _play_response_with_queue
sys.modules.setdefault("apps.artagent.backend.src.services.acs.acs_helpers", acs_helpers_stub)

speech_services_stub = ModuleType("apps.artagent.backend.src.services.speech_services")


class _SpeechSynthesizerStub:
    @staticmethod
    def split_pcm_to_base64_frames(pcm_bytes: bytes, sample_rate: int) -> list[str]:
        return [base64.b64encode(pcm_bytes).decode("ascii")] if pcm_bytes else []


speech_services_stub.SpeechSynthesizer = _SpeechSynthesizerStub


# Mock StreamingSpeechRecognizerFromBytes to avoid Azure Speech SDK dependencies
class _MockStreamingSpeechRecognizer:
    def __init__(self, *args, **kwargs):
        self.is_recognizing = False
        self.recognition_result = None

    async def start_continuous_recognition_async(self):
        self.is_recognizing = True

    async def stop_continuous_recognition_async(self):
        self.is_recognizing = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


speech_services_stub.StreamingSpeechRecognizerFromBytes = _MockStreamingSpeechRecognizer
sys.modules.setdefault("apps.artagent.backend.src.services.speech_services", speech_services_stub)

config_stub = ModuleType("config")
config_stub.GREETING = "Hello"
config_stub.STT_PROCESSING_TIMEOUT = 5.0
config_stub.ACS_STREAMING_MODE = StreamMode.MEDIA
config_stub.DEFAULT_VOICE_RATE = "+0%"
config_stub.DEFAULT_VOICE_STYLE = "chat"
config_stub.GREETING_VOICE_TTS = "en-US-JennyNeural"
config_stub.TTS_SAMPLE_RATE_ACS = 24000
config_stub.TTS_SAMPLE_RATE_UI = 24000
config_stub.AZURE_CLIENT_ID = "stub-client-id"
config_stub.AZURE_CLIENT_SECRET = "stub-secret"
config_stub.AZURE_TENANT_ID = "stub-tenant"
config_stub.AZURE_OPENAI_ENDPOINT = "https://example.openai.azure.com"
config_stub.AZURE_OPENAI_CHAT_DEPLOYMENT_ID = "stub-deployment"
config_stub.AZURE_OPENAI_API_VERSION = "2024-05-01"
config_stub.AZURE_OPENAI_API_KEY = "stub-key"
config_stub.TTS_END = ["."]
sys.modules.setdefault("config", config_stub)

# Skip entire module - the file acs_media_lifecycle.py was renamed to media_handler.py
# and the classes were refactored. These tests need complete rewrite.
pytest.skip(
    "Test module depends on removed acs_media_lifecycle.py - file renamed to media_handler.py",
    allow_module_level=True,
)

module_path = next(
    (
        parent / "apps/artagent/backend/api/v1/handlers/acs_media_lifecycle.py"
        for parent in Path(__file__).resolve().parents
        if (parent / "apps/artagent/backend/api/v1/handlers/acs_media_lifecycle.py").exists()
    ),
    None,
)
if module_path is None:
    raise RuntimeError("acs_media_lifecycle.py not found")

spec = importlib.util.spec_from_file_location("acs_media_lifecycle_under_test", module_path)
acs_media = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(acs_media)

ACSMediaHandler = acs_media.ACSMediaHandler
SpeechEvent = acs_media.SpeechEvent
SpeechEventType = acs_media.SpeechEventType
ThreadBridge = acs_media.ThreadBridge
SpeechSDKThread = acs_media.SpeechSDKThread
RouteTurnThread = acs_media.RouteTurnThread
MainEventLoop = acs_media.MainEventLoop


@pytest.fixture(autouse=True)
def disable_tracer_autouse():
    with patch("opentelemetry.trace.get_tracer") as mock_tracer:
        mock_span = Mock()
        mock_span.__enter__ = lambda self: None  # type: ignore[assignment]
        mock_span.__exit__ = lambda *args: None
        mock_tracer.return_value.start_span.return_value = mock_span
        mock_tracer.return_value.start_as_current_span.return_value.__enter__ = lambda self: None  # type: ignore[assignment]
        mock_tracer.return_value.start_as_current_span.return_value.__exit__ = lambda *args: None
        yield


@pytest.mark.asyncio
async def test_queue_speech_result_evicts_oldest_when_queue_full():
    queue = asyncio.Queue(maxsize=1)
    bridge = ThreadBridge()
    queue.put_nowait(SpeechEvent(event_type=SpeechEventType.FINAL, text="first"))
    incoming = SpeechEvent(event_type=SpeechEventType.FINAL, text="second")

    bridge.queue_speech_result(queue, incoming)

    assert queue.qsize() == 1
    assert queue.get_nowait() is incoming


class DummyRecognizer:
    def __init__(self):
        self.push_stream = object()
        self.started = False
        self.callbacks = {}

    def create_push_stream(self):
        self.push_stream = object()

    def set_partial_result_callback(self, cb):
        self.callbacks["partial"] = cb

    def set_final_result_callback(self, cb):
        self.callbacks["final"] = cb

    def set_cancel_callback(self, cb):
        self.callbacks["cancel"] = cb

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def write_bytes(self, payload):
        if not self.started:
            raise RuntimeError("Recognizer not started")

    def trigger_partial(self, text, lang="en-US"):
        self.callbacks.get("partial", lambda *_: None)(text, lang)

    def trigger_final(self, text, lang="en-US"):
        self.callbacks.get("final", lambda *_: None)(text, lang)

    def trigger_error(self, error_text):
        self.callbacks.get("cancel", lambda *_: None)(error_text)


class _TrackedAsyncCallable:
    def __init__(self, return_value=None):
        self.return_value = return_value
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.return_value


class _DummyTTSPool:
    def __init__(self):
        self.session_awareness_enabled = False
        self.acquire_calls = []
        self.release_calls = []

    async def acquire_for_session(self, session_id):
        self.acquire_calls.append(session_id)
        return None, SimpleNamespace(value="standard")

    async def release_for_session(self, session_id, client=None):
        self.release_calls.append((session_id, client))
        return True

    async def acquire(self):
        self.acquire_calls.append(None)
        return None, None

    async def release(self, client=None):
        self.release_calls.append(("release", client))
        return True

    def snapshot(self):
        return {}


class _DummySTTPool:
    def __init__(self):
        self.release_calls = []

    async def acquire_for_session(self, session_id):
        client = DummyRecognizer()
        tier = SimpleNamespace(value="standard")
        return client, tier

    async def release_for_session(self, session_id, client):
        self.release_calls.append((session_id, client))
        return True

    def snapshot(self):
        return {}


class DummyWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.state = SimpleNamespace(conn_id=None, session_id=None, lt=None)
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                conn_manager=SimpleNamespace(
                    broadcast_session=_TrackedAsyncCallable(return_value=1),
                    send_to_connection=_TrackedAsyncCallable(),
                ),
                redis=None,
                tts_pool=_DummyTTSPool(),
                stt_pool=_DummySTTPool(),
                auth_agent=SimpleNamespace(name="assistant"),
            )
        )

    async def send_text(self, data: str):
        self.sent_messages.append(data)

    async def send_json(self, payload: Any):
        self.sent_messages.append(payload)


@pytest.fixture
def dummy_websocket():
    return DummyWebSocket()


@pytest.fixture
def dummy_recognizer():
    return DummyRecognizer()


@pytest.fixture
def dummy_memory_manager():
    manager = Mock()
    manager.session_id = "session-123"
    manager.get_history.return_value = []
    manager.get_value_from_corememory.side_effect = lambda key, default=None: default
    return manager


class _RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    async def handler(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return "assistant-response"


@pytest.fixture
def dummy_orchestrator(monkeypatch):
    recorder = _RecordingOrchestrator()
    monkeypatch.setattr(acs_media, "route_turn", recorder.handler)
    return recorder


@pytest.mark.asyncio
async def test_thread_bridge_puts_event(dummy_recognizer):
    bridge = ThreadBridge()
    queue = asyncio.Queue()
    event = SpeechEvent(event_type=SpeechEventType.FINAL, text="hi")
    bridge.queue_speech_result(queue, event)
    stored = await queue.get()
    assert stored.text == "hi"


@pytest.mark.asyncio
async def test_route_turn_processes_final_speech(
    dummy_websocket, dummy_recognizer, dummy_memory_manager, dummy_orchestrator
):
    queue = asyncio.Queue()
    route_thread = RouteTurnThread(
        call_connection_id="call-1",
        speech_queue=queue,
        orchestrator_func=dummy_orchestrator.handler,
        memory_manager=dummy_memory_manager,
        websocket=dummy_websocket,
    )
    event = SpeechEvent(event_type=SpeechEventType.FINAL, text="hello", language="en-US")
    await route_thread._process_final_speech(event)
    assert len(dummy_orchestrator.calls) == 1


@pytest.fixture
async def media_handler(
    dummy_websocket, dummy_recognizer, dummy_orchestrator, dummy_memory_manager
):
    handler = ACSMediaHandler(
        websocket=dummy_websocket,
        orchestrator_func=dummy_orchestrator.handler,
        call_connection_id="call-abc",
        recognizer=dummy_recognizer,
        memory_manager=dummy_memory_manager,
        session_id="session-abc",
        greeting_text="Welcome!",
    )
    await handler.start()
    yield handler
    await handler.stop()


@pytest.mark.asyncio
async def test_media_handler_lifecycle(media_handler, dummy_recognizer):
    assert media_handler.running
    assert media_handler.speech_sdk_thread.thread_running
    await media_handler.stop()
    assert not media_handler.running


@pytest.mark.asyncio
async def test_media_handler_audio_metadata(media_handler, dummy_recognizer):
    payload = json.dumps({"kind": "AudioMetadata", "audioMetadata": {"subscriptionId": "sub"}})
    await media_handler.handle_media_message(payload)
    assert dummy_recognizer.started


@pytest.mark.asyncio
async def test_media_handler_audio_data(media_handler, dummy_recognizer):
    audio_b64 = base64.b64encode(b"\0" * 320).decode()
    payload = json.dumps({"kind": "AudioData", "audioData": {"data": audio_b64, "silent": False}})
    await media_handler.handle_media_message(payload)
    await asyncio.sleep(0.05)  # let background task run
    dummy_recognizer.write_bytes(b"\0")  # should not raise


@pytest.mark.asyncio
async def test_barge_in_flow(media_handler, dummy_recognizer):
    metadata = json.dumps({"kind": "AudioMetadata", "audioMetadata": {"subscriptionId": "sub"}})
    await media_handler.handle_media_message(metadata)
    dummy_recognizer.trigger_partial("hello there")
    await asyncio.sleep(0.05)
    stop_messages = [
        msg
        for msg in media_handler.websocket.sent_messages
        if (isinstance(msg, str) and "StopAudio" in msg)
        or (isinstance(msg, dict) and msg.get("kind") == "StopAudio")
    ]
    assert stop_messages


@pytest.mark.asyncio
async def test_speech_error_handling(media_handler, dummy_recognizer):
    metadata = json.dumps({"kind": "AudioMetadata", "audioMetadata": {"subscriptionId": "sub"}})
    await media_handler.handle_media_message(metadata)
    dummy_recognizer.trigger_error("failure")
    await asyncio.sleep(0.05)
    assert media_handler.running


@pytest.mark.asyncio
async def test_queue_cleanup_and_gc(media_handler):
    event = SpeechEvent(event_type=SpeechEventType.FINAL, text="cleanup")
    media_handler.thread_bridge.queue_speech_result(media_handler.speech_queue, event)
    ref = weakref.ref(event)
    del event
    await media_handler.stop()
    gc.collect()
    assert ref() is None
    assert media_handler.speech_queue.qsize() == 0


@pytest.mark.asyncio
async def test_route_turn_cancel_current_processing_clears_queue(
    dummy_websocket, dummy_recognizer, dummy_memory_manager, dummy_orchestrator
):
    queue = asyncio.Queue()
    route_thread = RouteTurnThread(
        call_connection_id="call-2",
        speech_queue=queue,
        orchestrator_func=dummy_orchestrator.handler,
        memory_manager=dummy_memory_manager,
        websocket=dummy_websocket,
    )
    await queue.put(SpeechEvent(event_type=SpeechEventType.FINAL, text="pending"))
    pending_task = asyncio.create_task(asyncio.sleep(10))
    route_thread.current_response_task = pending_task

    await route_thread.cancel_current_processing()

    assert queue.empty()
    assert pending_task.cancelled()
    assert route_thread.current_response_task is None


@pytest.mark.asyncio
async def test_queue_direct_text_playback_success(media_handler):
    queued = media_handler.queue_direct_text_playback("System notice", SpeechEventType.ANNOUNCEMENT)
    assert queued
    event = await asyncio.wait_for(media_handler.speech_queue.get(), timeout=0.1)
    assert event.text == "System notice"
    assert event.event_type == SpeechEventType.ANNOUNCEMENT


@pytest.mark.asyncio
async def test_queue_direct_text_playback_returns_false_when_stopped(media_handler):
    await media_handler.stop()
    assert not media_handler.queue_direct_text_playback("Should not enqueue")


@pytest.mark.asyncio
async def test_thread_bridge_schedule_barge_in_with_loop():
    bridge = ThreadBridge()
    calls = {"cancel": 0, "handler": 0}

    class _RouteThread:
        async def cancel_current_processing(self):
            calls["cancel"] += 1

    async def handler():
        calls["handler"] += 1

    route_thread = _RouteThread()
    bridge.set_route_turn_thread(route_thread)
    bridge.set_main_loop(asyncio.get_running_loop(), "call-bridge")
    bridge.schedule_barge_in(handler)
    await asyncio.sleep(0.05)
    assert calls["cancel"] == 1
    assert calls["handler"] == 1


def test_thread_bridge_schedule_barge_in_without_loop():
    bridge = ThreadBridge()

    async def handler():
        return None

    bridge.schedule_barge_in(handler)


@pytest.mark.asyncio
async def test_process_direct_text_playback_skips_empty_text(
    dummy_websocket, dummy_recognizer, dummy_memory_manager, dummy_orchestrator
):
    queue = asyncio.Queue()
    route_thread = RouteTurnThread(
        call_connection_id="call-3",
        speech_queue=queue,
        orchestrator_func=dummy_orchestrator.handler,
        memory_manager=dummy_memory_manager,
        websocket=dummy_websocket,
    )
    with patch(
        "apps.artagent.backend.api.v1.handlers.acs_media_lifecycle.send_response_to_acs",
        new=AsyncMock(),
    ) as mock_send:
        event = SpeechEvent(event_type=SpeechEventType.GREETING, text="")
        await route_thread._process_direct_text_playback(event)
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_main_event_loop_handles_metadata_and_dtmf(media_handler, dummy_recognizer):
    meta_payload = json.dumps({"kind": "AudioMetadata", "audioMetadata": {"subscriptionId": "sub"}})
    await media_handler.main_event_loop.handle_media_message(
        meta_payload, dummy_recognizer, media_handler
    )
    await media_handler.main_event_loop.handle_media_message(
        meta_payload, dummy_recognizer, media_handler
    )

    dtmf_payload = json.dumps({"kind": "DtmfData", "dtmfData": {"data": "*"}})
    await media_handler.main_event_loop.handle_media_message(
        dtmf_payload, dummy_recognizer, media_handler
    )

    greeting_events = []
    while not media_handler.speech_queue.empty():
        greeting_events.append(await media_handler.speech_queue.get())
    assert sum(e.event_type == SpeechEventType.GREETING for e in greeting_events) == 1


@pytest.mark.asyncio
async def test_main_event_loop_handles_silent_and_invalid_audio(media_handler, dummy_recognizer):
    await media_handler.main_event_loop.handle_media_message(
        "not-json", dummy_recognizer, media_handler
    )
    silent_payload = json.dumps({"kind": "AudioData", "audioData": {"data": "", "silent": True}})
    await media_handler.main_event_loop.handle_media_message(
        silent_payload, dummy_recognizer, media_handler
    )
    assert not media_handler.main_event_loop.active_audio_tasks


@pytest.mark.asyncio
async def test_queue_direct_text_playback_rejects_invalid_type(media_handler):
    assert not media_handler.queue_direct_text_playback("invalid", SpeechEventType.FINAL)
