import asyncio
import gc
import tracemalloc
import time
import threading

import pytest

from apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle import (
    ACSMediaHandler,
    get_active_handlers_count,
)


class FakeState:
    def __init__(self):
        self.lt = None


class FakeWebSocket:
    """Minimal fake WebSocket supporting the bits used by the media handler."""

    def __init__(self):
        self.sent = []
        self.state = FakeState()
        # allow handlers to set this attribute
        self._acs_media_handler = None

    async def send_text(self, text: str):
        # simulate a tiny send latency
        await asyncio.sleep(0)
        self.sent.append(text)


class FakeRecognizer:
    """Lightweight fake recognizer used to avoid heavy external deps in tests."""

    def __init__(self):
        self.push_stream = None
        self._partial_cb = None
        self._final_cb = None
        self._cancel_cb = None
        self.started = False

    def create_push_stream(self):
        self.push_stream = object()

    def set_partial_result_callback(self, cb):
        self._partial_cb = cb

    def set_final_result_callback(self, cb):
        self._final_cb = cb

    def set_cancel_callback(self, cb):
        self._cancel_cb = cb

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def write_bytes(self, data: bytes):
        # synchronous write used from executor in main loop
        return len(data)


async def _create_start_stop_handler(loop: asyncio.AbstractEventLoop):
    ws = FakeWebSocket()
    recog = FakeRecognizer()

    async def dummy_orchestrator(*args, **kwargs):
        await asyncio.sleep(0)
        return None

    handler = ACSMediaHandler(
        websocket=ws,
        orchestrator_func=dummy_orchestrator,
        call_connection_id=f"call-{int(time.time()*1000)}",
        recognizer=recog,
        memory_manager=None,
        session_id="s1",
        greeting_text="hello",
    )

    await handler.start()
    # allow background tasks/threads to spin up
    await asyncio.sleep(0.05)
    await handler.stop()
    # small grace to ensure threads joined
    await asyncio.sleep(0.02)
    return handler, ws, recog


@pytest.mark.asyncio
async def test_handler_registers_and_cleans_up():
    """Start a handler and ensure it's registered then cleaned up on stop."""
    before = get_active_handlers_count()
    handler, ws, recog = await _create_start_stop_handler(asyncio.get_running_loop())

    after = get_active_handlers_count()
    # Should be same as before after full stop
    assert (
        after == before
    ), f"active handlers should be cleaned up (before={before}, after={after})"
    # websocket attribute should be removed/cleared or not reference running handler
    # The implementation sets _acs_media_handler during start; after stop it may remain but handler.is_running must be False
    assert not handler.is_running


@pytest.mark.asyncio
async def test_threads_terminated_on_stop():
    """Ensure SpeechSDKThread thread is not alive after stop."""
    handler, ws, recog = await _create_start_stop_handler(asyncio.get_running_loop())

    # Access speech_sdk_thread and ensure any thread object is not alive
    sdk_thread = getattr(handler, "speech_sdk_thread", None)
    if sdk_thread is None:
        pytest.skip("No speech_sdk_thread present in handler implementation")

    # Give a short time for thread to join
    await asyncio.sleep(0.02)
    # thread_obj may be None or not alive
    t = getattr(sdk_thread, "thread_obj", None)
    if t is None:
        assert True
    else:
        assert not t.is_alive(), "Speech SDK thread should not be alive after stop"


@pytest.mark.asyncio
async def test_no_unbounded_memory_growth_on_repeated_start_stop():
    """Run repeated start/stop cycles and assert total memory usage does not grow unboundedly."""
    tracemalloc.start()
    gc.collect()
    snapshot1 = tracemalloc.take_snapshot()

    cycles = 8
    for _ in range(cycles):
        handler, ws, recog = await _create_start_stop_handler(
            asyncio.get_running_loop()
        )
        # explicit collect between cycles
        await asyncio.sleep(0)
        gc.collect()

    snapshot2 = tracemalloc.take_snapshot()
    stats1 = snapshot1.statistics("filename")
    stats2 = snapshot2.statistics("filename")

    total1 = sum(s.size for s in stats1)
    total2 = sum(s.size for s in stats2)
    growth = total2 - total1

    # Allow some tolerance for variations; assert growth is bounded (1MB)
    assert (
        growth <= 1_000_000
    ), f"Memory growth too large after repeated cycles: {growth} bytes"

    tracemalloc.stop()


@pytest.mark.asyncio
async def test_aggressive_leak_detection_gc_counts():
    """Aggressively detect leaks by counting GC objects of key classes, threads and tasks."""
    # Import module to ensure class names are present in gc objects
    acs_mod = __import__(
        "apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle",
        fromlist=["*"],
    )

    monitor_names = [
        "ACSMediaHandler",
        "SpeechSDKThread",
        "RouteTurnThread",
        "MainEventLoop",
    ]

    def snapshot_counts():
        objs = gc.get_objects()
        counts = {name: 0 for name in monitor_names}
        for o in objs:
            try:
                cn = o.__class__.__name__
            except Exception:
                continue
            if cn in counts:
                counts[cn] += 1

        counts["threading.Thread"] = sum(1 for _ in threading.enumerate())
        # current asyncio tasks
        try:
            counts["asyncio.Task"] = len(asyncio.all_tasks())
        except Exception:
            counts["asyncio.Task"] = 0

        return counts

    # warm up GC and take baseline
    gc.collect()
    before = snapshot_counts()

    cycles = 10
    for _ in range(cycles):
        handler, ws, recog = await _create_start_stop_handler(
            asyncio.get_running_loop()
        )
        # small pause and collect to allow cleanup
        await asyncio.sleep(0)
        gc.collect()

    after = snapshot_counts()

    diffs = {k: after.get(k, 0) - before.get(k, 0) for k in before}

    # Tolerances: allow small fluctuations but fail on growing trends
    for name in monitor_names:
        assert (
            diffs.get(name, 0) <= 2
        ), f"{name} increased unexpectedly by {diffs.get(name,0)}"

    assert (
        diffs.get("threading.Thread", 0) <= 2
    ), f"Thread count increased unexpectedly by {diffs.get('threading.Thread',0)}"
    assert (
        diffs.get("asyncio.Task", 0) <= 3
    ), f"Asyncio tasks increased unexpectedly by {diffs.get('asyncio.Task',0)}"


@pytest.mark.asyncio
async def test_p0_registry_and_threadpool_no_leak():
    """P0-focused checks: ensure no RLock instances or handler-cleanup threads leak and recognizers don't accumulate."""
    # baseline counts
    gc.collect()

    def count_rlocks():
        # Some Python builds expose RLock in a way that makes isinstance checks fragile.
        # Count by class name instead to be robust across environments.
        return sum(
            1
            for o in gc.get_objects()
            if getattr(o.__class__, "__name__", "") == "RLock"
        )

    def count_cleanup_threads():
        return sum(
            1 for t in threading.enumerate() if "handler-cleanup" in (t.name or "")
        )

    def count_fake_recognizers():
        return sum(
            1 for o in gc.get_objects() if o.__class__.__name__ == "FakeRecognizer"
        )

    before_rlocks = count_rlocks()
    before_cleanup = count_cleanup_threads()
    before_recogs = count_fake_recognizers()

    cycles = 12
    for _ in range(cycles):
        handler, ws, recog = await _create_start_stop_handler(
            asyncio.get_running_loop()
        )
        await asyncio.sleep(0)
        gc.collect()

    after_rlocks = count_rlocks()
    after_cleanup = count_cleanup_threads()
    after_recogs = count_fake_recognizers()

    # RLock count should not increase notably (allow +1 tolerance)
    assert (
        after_rlocks - before_rlocks <= 1
    ), f"RLock instances increased: {before_rlocks} -> {after_rlocks}"

    # handler-cleanup thread count should remain stable (<=1 extra thread tolerated)
    assert (
        after_cleanup - before_cleanup <= 1
    ), f"handler-cleanup threads increased: {before_cleanup} -> {after_cleanup}"

    # Fake recognizers should be cleaned up
    assert (
        after_recogs - before_recogs <= 2
    ), f"FakeRecognizer instances increased unexpectedly: {before_recogs} -> {after_recogs}"
