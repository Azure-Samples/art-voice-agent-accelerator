"""Exercise production turn queues, SDK bridges and pool rollback without Azure."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from apps.artagent.backend.registries.agentstore.base import SpeechConfig, UnifiedAgent
from apps.artagent.backend.voice.handler import VoiceHandler, VoiceHandlerConfig
from apps.artagent.backend.voice.shared.context import TransportType, VoiceSessionContext
from apps.artagent.backend.voice.speech_cascade.handler import (
    SpeechEvent,
    SpeechEventType,
    ThreadBridge,
)
from apps.artagent.backend.voice.tts.playback import TTSPlayback
from fastapi import WebSocketDisconnect

from tests.test_voice_handler_compat import MockMemoManager, MockWebSocket


class LeasePool:
    def __init__(self, client, *, error=None):
        self.client = client
        self.error = error
        self.leased = False
        self.released = 0

    async def acquire_for_session(self, session_id):
        if self.error is not None:
            raise self.error
        assert not self.leased
        self.leased = True
        return self.client, "session"

    async def release_for_session(self, session_id, client):
        assert client is self.client
        assert self.leased
        assert not getattr(client, "active", False)
        self.leased = False
        self.released += 1


class Recognizer:
    push_stream = object()

    def __init__(self, *, fail_start=False):
        self.fail_start = fail_start
        self.active = False
        self.audio = []

    def set_partial_result_callback(self, callback):
        self.partial = callback

    def set_final_result_callback(self, callback):
        self.final = callback

    def set_cancel_callback(self, callback):
        self.error = callback

    def start(self):
        self.active = True
        if self.fail_start:
            raise RuntimeError("start failed after allocating SDK resources")

    def stop(self):
        self.active = False

    def write_bytes(self, data):
        self.audio.append(data)


class Synth:
    is_ready = True

    def __init__(self):
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.finished = threading.Event()
        self.active = False
        self.produced = 0

    def stop_speaking(self):
        self.stopped.set()

    def synthesize_to_pcm_stream(self, *, cancel_event, **kwargs):
        self.active = True
        self.started.set()
        try:
            while not cancel_event.is_set():
                self.produced += 1
                yield b"\x01\x00" * 1600
        finally:
            self.active = False
            self.finished.set()

    def warm_connection(self, *, cancel_event, **kwargs):
        self.active = True
        self.started.set()
        try:
            cancel_event.wait(2)
            return False
        finally:
            self.active = False
            self.finished.set()


def app_state(tts=None, stt=None):
    return SimpleNamespace(
        redis=object(),
        tts_pool=LeasePool(tts or Synth()),
        stt_pool=LeasePool(stt or Recognizer()),
        speech_executor=None,
        unified_agents={
            "Concierge": UnifiedAgent(
                name="Concierge", speech=SpeechConfig(transcription_model="azure-speech")
            )
        },
        start_agent="Concierge",
        auth_agent=None,
    )


async def make_handler(app):
    with (
        patch.object(VoiceHandler, "_load_memory_manager", return_value=MockMemoManager()),
        patch.object(VoiceHandler, "_initialize_active_agent", new=AsyncMock()),
        patch.object(VoiceHandler, "_derive_greeting", new=AsyncMock(return_value="")),
    ):
        return await VoiceHandler.create(
            VoiceHandlerConfig(websocket=MockWebSocket(), session_id="owned-session"), app
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [TimeoutError("full"), RuntimeError("failed"), asyncio.CancelledError()]
)
async def test_stt_acquisition_failure_returns_exact_tts_lease(error):
    app = app_state()
    app.stt_pool.error = error
    expected = WebSocketDisconnect if isinstance(error, TimeoutError) else type(error)
    with pytest.raises(expected):
        await make_handler(app)
    assert app.tts_pool.released == 1
    assert app.stt_pool.released == 0


@pytest.mark.asyncio
async def test_configuration_failure_after_both_acquisitions_releases_both():
    app = app_state()
    with (
        patch.object(VoiceHandler, "_load_memory_manager", return_value=MockMemoManager()),
        patch.object(VoiceHandler, "_initialize_active_agent", new=AsyncMock()),
        patch.object(
            VoiceHandler,
            "_derive_greeting",
            new=AsyncMock(side_effect=ValueError("bad prompt")),
        ),
        pytest.raises(ValueError, match="bad prompt"),
    ):
        await VoiceHandler.create(
            VoiceHandlerConfig(websocket=MockWebSocket(), session_id="owned-session"), app
        )
    assert app.tts_pool.released == app.stt_pool.released == 1


@pytest.mark.asyncio
async def test_agent_resolution_failure_does_not_acquire_either_provider():
    app = app_state()
    with (
        patch.object(VoiceHandler, "_load_memory_manager", return_value=MockMemoManager()),
        patch.object(
            VoiceHandler,
            "_initialize_active_agent",
            new=AsyncMock(side_effect=ValueError("bad agent")),
        ),
        pytest.raises(ValueError, match="bad agent"),
    ):
        await VoiceHandler.create(
            VoiceHandlerConfig(websocket=MockWebSocket(), session_id="owned-session"), app
        )
    assert not app.tts_pool.leased and not app.stt_pool.leased
    assert app.tts_pool.released == app.stt_pool.released == 0


@pytest.mark.asyncio
async def test_partial_start_failure_stops_sdk_worker_and_releases_once():
    app = app_state(stt=Recognizer(fail_start=True))
    handler = await make_handler(app)
    with pytest.raises(RuntimeError, match="start failed"):
        await handler.start()
    assert handler._route_turn_thread.processing_task.done()
    assert handler._stt_thread.thread_obj is None
    assert handler._thread_bridge._closed
    assert app.tts_pool.released == app.stt_pool.released == 1
    await handler.stop()
    assert app.tts_pool.released == 1


@pytest.mark.asyncio
async def test_cancelled_start_joins_native_start_before_returning_lease():
    entered = threading.Event()
    finish = threading.Event()

    class SlowRecognizer(Recognizer):
        def start(self):
            entered.set()
            assert finish.wait(2)
            self.active = True

    app = app_state(stt=SlowRecognizer())
    handler = await make_handler(app)
    start = asyncio.create_task(handler.start())
    assert await asyncio.to_thread(entered.wait, 1)
    start.cancel()
    await asyncio.sleep(0)
    assert app.stt_pool.released == 0
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(start, 1)
    assert app.tts_pool.released == app.stt_pool.released == 1


@pytest.mark.asyncio
async def test_failed_sdk_stop_quiesces_other_tasks_without_reusing_live_lease():
    class FaultedStopRecognizer(Recognizer):
        def stop(self):
            raise RuntimeError("SDK stop failed")

    app = app_state(stt=FaultedStopRecognizer())
    handler = await make_handler(app)
    await handler.start()
    with pytest.raises(ExceptionGroup, match="could not be quiesced"):
        await handler.stop()
    assert handler._route_turn_thread.processing_task.done()
    assert handler.tts._closed
    assert app.stt_pool.released == app.tts_pool.released == 0


@pytest.mark.asyncio
async def test_browser_receive_loop_handles_audio_and_stop_during_typed_turn():
    app = app_state()
    handler = await make_handler(app)
    started = asyncio.Event()
    finished = asyncio.Event()
    messages = asyncio.Queue()

    async def orchestrate(cm, transcript):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    handler._route_turn_thread.orchestrator_func = orchestrate
    handler.websocket.receive = messages.get
    await handler.start()
    running = asyncio.create_task(handler.run())
    messages.put_nowait({"type": "websocket.receive", "text": "typed turn"})
    await asyncio.wait_for(started.wait(), 1)
    messages.put_nowait({"type": "websocket.receive", "bytes": b"\x00\x00" * 160})
    messages.put_nowait({"type": "websocket.receive", "text": '{"type":"stop"}'})
    await asyncio.wait_for(running, 1)
    assert app.stt_pool.client.audio
    assert finished.is_set()
    assert app.tts_pool.released == app.stt_pool.released == 1


@pytest.mark.asyncio
async def test_concurrent_stop_callers_share_cleanup_and_release_once():
    app = app_state()
    handler = await make_handler(app)
    await handler.start()
    await asyncio.gather(handler.stop(), handler.stop(), handler.stop())
    assert handler._shutdown_task.done()
    assert app.tts_pool.released == app.stt_pool.released == 1


@pytest.mark.asyncio
async def test_typed_and_sdk_turns_share_worker_and_browser_remains_responsive():
    app = app_state()
    handler = await make_handler(app)
    started = asyncio.Event()
    cancelled = asyncio.Event()
    transcripts = []
    turns = []

    async def orchestrate(cm, transcript):
        turns.append((transcript, cm.get_value_from_corememory("current_turn_id")))
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def transcript(text, turn_id, sequence):
        transcripts.append((text, turn_id, sequence))

    handler._route_turn_thread.orchestrator_func = orchestrate
    handler._route_turn_thread.on_user_transcript = transcript
    await handler.start()
    await asyncio.wait_for(handler.send_text_message("typed input"), 0.2)
    await asyncio.wait_for(started.wait(), 1)
    assert handler._route_turn_thread.has_active_response
    assert transcripts[0][1] == turns[0][1]
    assert transcripts[0][2] == 1

    # A second typed turn can be waiting on cancellation without blocking receive.
    await asyncio.wait_for(handler.send_text_message("replacement"), 0.2)
    await asyncio.wait_for(handler._handle_browser_audio(b"\x00\x00" * 160), 0.2)
    assert app.stt_pool.client.audio
    await asyncio.wait_for(handler._handle_browser_message('{"type":"stop"}'), 0.2)
    await handler.stop()
    assert cancelled.is_set()
    assert not handler._thread_bridge._tasks
    assert app.tts_pool.released == app.stt_pool.released == 1

    # The same production worker consumes an SDK final with its allocated ID.
    app = app_state()
    handler = await make_handler(app)
    started.clear()
    handler._route_turn_thread.orchestrator_func = orchestrate
    handler._route_turn_thread.on_user_transcript = transcript
    await handler.start()
    await asyncio.to_thread(app.stt_pool.client.final, "spoken input", "en-US")
    await asyncio.wait_for(started.wait(), 1)
    assert turns[-1][0] == "spoken input"
    assert transcripts[-1][1] == turns[-1][1]
    await handler.stop()


@pytest.mark.asyncio
async def test_sdk_queue_wakes_real_getter_on_debug_loop_and_closes():
    loop = asyncio.get_running_loop()
    previous_debug = loop.get_debug()
    loop.set_debug(True)
    bridge = ThreadBridge()
    bridge.set_main_loop(loop)
    queue = asyncio.Queue(maxsize=1)
    event = SpeechEvent(SpeechEventType.FINAL, "hello")
    try:
        getter = asyncio.create_task(queue.get())
        await asyncio.sleep(0)
        await asyncio.to_thread(bridge.queue_speech_result, queue, event)
        assert await asyncio.wait_for(getter, 1) is event
        queue.task_done()
        assert bridge.queue_speech_result(queue, event)
        assert not bridge.queue_speech_result(
            queue, SpeechEvent(SpeechEventType.TTS_RESPONSE, "full")
        )
        queue.get_nowait()
        queue.task_done()
        await asyncio.wait_for(queue.join(), 0.2)
        await bridge.close()
        assert not await asyncio.to_thread(bridge.queue_speech_result, queue, event)
        assert queue.empty()
    finally:
        loop.set_debug(previous_debug)


@pytest.mark.asyncio
async def test_full_tts_buffer_stops_and_joins_actual_generator():
    synth = Synth()
    playback = TTSPlayback(VoiceSessionContext(session_id="bounded", tts_client=synth), app_state())
    chunks = playback._iter_synth_chunks(synth, "text", "voice", "chat", "medium", 16000)
    assert await anext(chunks)
    await asyncio.sleep(0.05)
    assert synth.produced <= 10
    await asyncio.wait_for(chunks.aclose(), 1)
    assert synth.finished.is_set()
    assert not playback._producers


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
async def test_completed_tts_producer_without_sentinel_is_joined(monkeypatch, outcome):
    synth = Synth()
    playback = TTSPlayback(
        VoiceSessionContext(session_id="finished", tts_client=synth), app_state()
    )
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    if outcome == "failure":
        future.set_exception(RuntimeError("producer failed before sentinel"))
        expected = RuntimeError
    elif outcome == "cancelled":
        future.cancel()
        expected = asyncio.CancelledError
    else:
        future.set_result(None)
        expected = StopAsyncIteration

    # Exercise an empty bridge after executor completion, without a queued sentinel.
    monkeypatch.setattr(loop, "run_in_executor", lambda *args: future)
    chunks = playback._iter_synth_chunks(synth, "text", "voice", "chat", "medium", 16000)
    with pytest.raises(expected):
        await anext(chunks)
    assert not playback._producers


@pytest.mark.asyncio
async def test_signal_only_cancel_wakes_consumer_waiting_for_first_frame():
    class WaitingSynth(Synth):
        def synthesize_to_pcm_stream(self, *, cancel_event, **kwargs):
            self.active = True
            self.started.set()
            try:
                assert self.stopped.wait(2)
                if not cancel_event.is_set():
                    yield b"late"
            finally:
                self.active = False
                self.finished.set()

    synth = WaitingSynth()
    context = VoiceSessionContext(session_id="waiting", tts_client=synth)
    playback = TTSPlayback(context, app_state())
    chunks = playback._iter_synth_chunks(synth, "text", "voice", "chat", "medium", 16000)
    pending = asyncio.create_task(anext(chunks))
    assert await asyncio.to_thread(synth.started.wait, 1)
    playback.cancel()
    context.cancel_event.clear()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(pending, 1)
    assert synth.finished.is_set()
    assert not playback._producers


@pytest.mark.asyncio
async def test_warmup_cancellation_joins_before_pool_release():
    app = app_state()
    handler = await make_handler(app)
    synth = app.tts_pool.client
    handler._greeting_warmup_task = asyncio.create_task(
        handler.tts.prepare_voice(voice_name="voice", timeout_sec=2)
    )
    assert await asyncio.to_thread(synth.started.wait, 1)
    await asyncio.wait_for(handler.stop(), 1)
    assert synth.finished.is_set()
    assert app.tts_pool.released == 1


@pytest.mark.asyncio
async def test_factory_failure_after_warmup_started_joins_before_rollback():
    app = app_state()
    synth = app.tts_pool.client

    class FailingMemo(MockMemoManager):
        async def persist_to_redis_async(self, redis_mgr, *, raise_on_failure=False):
            assert await asyncio.to_thread(synth.started.wait, 1)
            raise RuntimeError("initial persistence failed")

    with (
        patch.object(VoiceHandler, "_load_memory_manager", return_value=FailingMemo()),
        patch.object(VoiceHandler, "_initialize_active_agent", new=AsyncMock()),
        patch.object(VoiceHandler, "_derive_greeting", new=AsyncMock(return_value="Welcome")),
        pytest.raises(RuntimeError, match="initial persistence failed"),
    ):
        await VoiceHandler.create(
            VoiceHandlerConfig(
                websocket=MockWebSocket(), session_id="rollback", transport=TransportType.ACS
            ),
            app,
        )
    assert synth.finished.is_set()
    assert app.tts_pool.released == app.stt_pool.released == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", [TransportType.ACS, TransportType.BROWSER])
async def test_cancelled_generation_cannot_emit_after_shared_cancel_resets(transport):
    synth = Synth()
    context = VoiceSessionContext(session_id="stale", transport=transport, tts_client=synth)
    ws = MockWebSocket()
    context._websocket = ws
    playback = TTSPlayback(context, app_state())

    def interrupt():
        playback.cancel()
        context.cancel_event.clear()

    result = await playback.speak("response", voice_name="voice", on_first_audio=interrupt)
    assert result is False
    assert len(ws.sent_json) == 1
    assert synth.finished.is_set()
    assert not playback._producers


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_fails", [False, True])
async def test_real_provider_stop_unblocks_read_and_unregisters_synthesizer(
    monkeypatch, stop_fails
):
    from src.speech import text_to_speech as provider

    entered_read = threading.Event()
    stopped = threading.Event()
    instances = []

    class ResultFuture:
        def __init__(self, value=None, error=None):
            self.value = value
            self.error = error

        def get(self):
            if self.error is not None:
                raise self.error
            return self.value

    class SDK:
        def __init__(self, **kwargs):
            instances.append(self)
            self.stop_count = 0

        def start_speaking_ssml_async(self, ssml):
            return ResultFuture(self)

        def stop_speaking_async(self):
            self.stop_count += 1
            stopped.set()
            return ResultFuture(
                error=RuntimeError("stop acknowledgement failed") if stop_fails else None
            )

    class AudioStream:
        def __init__(self, result):
            self.status = provider.speechsdk.StreamStatus.AllData

        def read_data(self, buffer):
            entered_read.set()
            assert stopped.wait(2), "actual producer was not stopped"
            return 0

    class SpeechConfig:
        def set_speech_synthesis_output_format(self, value):
            pass

    monkeypatch.setattr(
        provider.SpeechSynthesizer, "_create_speech_config", lambda self: SpeechConfig()
    )
    monkeypatch.setattr(provider.speechsdk, "SpeechSynthesizer", SDK)
    monkeypatch.setattr(provider.speechsdk, "AudioDataStream", AudioStream)
    synth = provider.SpeechSynthesizer(key="test", region="test", enable_tracing=False)
    playback = TTSPlayback(
        VoiceSessionContext(session_id="provider", tts_client=synth), app_state()
    )
    chunks = playback._iter_synth_chunks(synth, "text", "voice", "chat", "medium", 16000)
    pending = asyncio.create_task(anext(chunks))
    assert await asyncio.to_thread(entered_read.wait, 1)
    assert len(synth._active_synthesizers) == 1
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pending, 1)
    assert instances[0].stop_count >= 1
    assert not playback._producers
    if stop_fails:
        assert synth.has_active_synthesis
        with pytest.raises(RuntimeError, match="not acknowledged"):
            await playback.aclose()
    else:
        assert not synth.has_active_synthesis
        await playback.aclose()
