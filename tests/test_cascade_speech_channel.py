"""
Cascade Speech-Channel Control-Flow Tests
=========================================

These tests exercise the *real* SpeechCascade control logic that drives the
end-to-end speech channel, without mocking the handler away:

    STT recognizer callbacks  ->  ThreadBridge  ->  speech queue / barge-in

Specifically they cover the behaviour that the higher-level
``test_acs_speech_channel_e2e.py`` cannot reach because it substitutes a
``FakeSpeechHandler``:

1. ThreadBridge turn guard — trailing partials of the utterance that spawned a
   turn must not cancel that turn; the guard auto-expires on a monotonic
   deadline backstop.
2. ThreadBridge barge-in suppression — handoffs/greetings suppress barge-in.
3. ThreadBridge.schedule_barge_in gating — kill switch, suppression, missing
   main loop, and detection timestamping.
4. SpeechSDKThread STT callbacks — on_partial / on_final / on_error map raw
   recognizer events onto barge-in scheduling, the turn guard, and the queue.

Run with: pytest tests/test_cascade_speech_channel.py -v
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import Mock

import pytest

from apps.artagent.backend.voice.speech_cascade.handler import (
    SpeechEvent,
    SpeechEventType,
    SpeechSDKThread,
    ThreadBridge,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fakes
# ═══════════════════════════════════════════════════════════════════════════════


class FakeRecognizer:
    """Captures the SpeechSDK callbacks so tests can drive them directly."""

    def __init__(self) -> None:
        # Non-None push_stream so SpeechSDKThread pre-init is a no-op.
        self.push_stream = object()
        self.on_partial = None
        self.on_final = None
        self.on_cancel = None
        self.started = False
        self.write_calls: list[bytes] = []
        self.finalized = 0

    def set_partial_result_callback(self, cb) -> None:
        self.on_partial = cb

    def set_final_result_callback(self, cb) -> None:
        self.on_final = cb

    def set_cancel_callback(self, cb) -> None:
        self.on_cancel = cb

    def write_bytes(self, data: bytes) -> None:
        self.write_calls.append(data)

    def start(self) -> None:
        self.started = True

    def finalize_current_utterance(self) -> None:
        self.finalized += 1


def _make_thread(
    *,
    on_partial_transcript=None,
    queue: asyncio.Queue | None = None,
) -> tuple[SpeechSDKThread, FakeRecognizer, ThreadBridge]:
    recognizer = FakeRecognizer()
    bridge = ThreadBridge()
    thread = SpeechSDKThread(
        connection_id="conn-speech-channel",
        recognizer=recognizer,
        thread_bridge=bridge,
        barge_in_handler=Mock(name="barge_in_handler"),
        speech_queue=queue if queue is not None else asyncio.Queue(maxsize=32),
        on_partial_transcript=on_partial_transcript,
    )
    return thread, recognizer, bridge


# ═══════════════════════════════════════════════════════════════════════════════
# ThreadBridge: turn guard
# ═══════════════════════════════════════════════════════════════════════════════


class TestTurnGuard:
    """Pre-speech turn guard: suppress trailing partials until the agent speaks."""

    def test_inactive_by_default(self):
        assert ThreadBridge().turn_guard_active is False

    def test_arm_activates_guard(self):
        bridge = ThreadBridge()
        bridge.arm_turn_guard()
        assert bridge.turn_guard_active is True

    def test_disarm_deactivates_guard(self):
        bridge = ThreadBridge()
        bridge.arm_turn_guard()
        bridge.disarm_turn_guard()
        assert bridge.turn_guard_active is False

    def test_guard_expires_after_deadline(self):
        """The monotonic deadline backstop releases the guard even without disarm."""
        bridge = ThreadBridge()
        bridge.arm_turn_guard(max_duration_s=0.05)
        assert bridge.turn_guard_active is True
        time.sleep(0.06)
        # Still 'set' as an Event, but the deadline has passed -> inactive.
        assert bridge.turn_guard_active is False


# ═══════════════════════════════════════════════════════════════════════════════
# ThreadBridge: barge-in suppression
# ═══════════════════════════════════════════════════════════════════════════════


class TestBargeInSuppression:
    def test_not_suppressed_by_default(self):
        assert ThreadBridge().barge_in_suppressed is False

    def test_suppress_then_allow(self):
        bridge = ThreadBridge()
        bridge.suppress_barge_in()
        assert bridge.barge_in_suppressed is True
        bridge.allow_barge_in()
        assert bridge.barge_in_suppressed is False


# ═══════════════════════════════════════════════════════════════════════════════
# ThreadBridge: schedule_barge_in gating
# ═══════════════════════════════════════════════════════════════════════════════


class TestScheduleBargeInGating:
    @pytest.mark.asyncio
    async def test_schedules_handler_on_main_loop(self):
        bridge = ThreadBridge()
        bridge.set_main_loop(asyncio.get_running_loop(), "conn")
        ran = asyncio.Event()

        async def handler():
            ran.set()

        bridge.schedule_barge_in(handler)
        await asyncio.wait_for(ran.wait(), timeout=1.0)
        assert bridge.last_barge_in_detected_ts is not None

    def test_skipped_when_suppressed(self):
        """Suppressed barge-in returns before stamping a detection timestamp."""
        bridge = ThreadBridge()
        bridge.suppress_barge_in()
        handler = Mock()

        bridge.schedule_barge_in(handler)

        handler.assert_not_called()
        assert bridge.last_barge_in_detected_ts is None

    def test_skipped_by_kill_switch(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CASCADE_DISABLE_BARGE_IN", "true")
        bridge = ThreadBridge()
        bridge.set_main_loop(asyncio.new_event_loop(), "conn")
        handler = Mock()

        bridge.schedule_barge_in(handler)

        handler.assert_not_called()
        assert bridge.last_barge_in_detected_ts is None

    def test_no_main_loop_does_not_raise(self):
        """Missing main loop is logged and swallowed, never raised to the STT thread."""
        bridge = ThreadBridge()
        handler = Mock()

        # Detection is stamped before the loop check; the point is no exception.
        bridge.schedule_barge_in(handler)

        handler.assert_not_called()
        assert bridge.last_barge_in_detected_ts is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SpeechSDKThread: STT callback -> bridge control flow
# ═══════════════════════════════════════════════════════════════════════════════


class TestSpeechSDKCallbacks:
    def test_callbacks_registered_on_recognizer(self):
        _thread, recognizer, _bridge = _make_thread()
        assert callable(recognizer.on_partial)
        assert callable(recognizer.on_final)
        assert callable(recognizer.on_cancel)

    def test_short_partial_does_not_schedule_barge_in(self):
        """Partials <= 3 chars are interim noise: no barge-in, no transcript."""
        on_partial_transcript = Mock()
        thread, recognizer, bridge = _make_thread(on_partial_transcript=on_partial_transcript)
        bridge.schedule_barge_in = Mock()

        recognizer.on_partial("hi", "en-US", None)

        bridge.schedule_barge_in.assert_not_called()
        on_partial_transcript.assert_not_called()

    def test_meaningful_partial_schedules_barge_in_and_emits(self):
        on_partial_transcript = Mock()
        thread, recognizer, bridge = _make_thread(on_partial_transcript=on_partial_transcript)
        bridge.schedule_barge_in = Mock()

        recognizer.on_partial("hello there", "en-US", "spk-1")

        bridge.schedule_barge_in.assert_called_once_with(thread.barge_in_handler)
        on_partial_transcript.assert_called_once_with("hello there", "en-US", "spk-1")

    def test_partial_ignored_during_turn_guard(self):
        """Trailing partials are suppressed while the pre-speech guard is armed."""
        on_partial_transcript = Mock()
        thread, recognizer, bridge = _make_thread(on_partial_transcript=on_partial_transcript)
        bridge.schedule_barge_in = Mock()
        bridge.arm_turn_guard()

        recognizer.on_partial("hello there", "en-US", None)

        bridge.schedule_barge_in.assert_not_called()
        on_partial_transcript.assert_not_called()

    def test_first_partial_stamps_utterance_start(self):
        thread, recognizer, _bridge = _make_thread()
        assert thread._utterance_start_ts is None

        recognizer.on_partial("hi", "en-US", None)

        assert thread._utterance_start_ts is not None

    def test_final_arms_turn_guard_and_queues_event(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        thread, recognizer, bridge = _make_thread(queue=queue)

        # Establish an utterance start via a partial first.
        recognizer.on_partial("hello", "en-US", None)
        recognizer.on_final("hello there", "en-US", "spk-1")

        assert bridge.turn_guard_active is True
        assert queue.qsize() == 1
        event = queue.get_nowait()
        assert event.event_type == SpeechEventType.FINAL
        assert event.text == "hello there"
        assert event.recognition_end_perf is not None
        # Utterance start is reset for the next utterance.
        assert thread._utterance_start_ts is None

    def test_short_final_is_not_queued(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        thread, recognizer, bridge = _make_thread(queue=queue)
        thread._utterance_start_ts = time.time()

        recognizer.on_final("a", "en-US", None)

        assert queue.qsize() == 0
        assert bridge.turn_guard_active is False
        assert thread._utterance_start_ts is None

    def test_error_callback_queues_error_event(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        _thread, recognizer, _bridge = _make_thread(queue=queue)

        recognizer.on_cancel("recognizer cancelled")

        assert queue.qsize() == 1
        event = queue.get_nowait()
        assert event.event_type == SpeechEventType.ERROR
        assert event.text == "recognizer cancelled"

    def test_stop_stt_timer_finalizes_utterance(self):
        thread, recognizer, _bridge = _make_thread()

        thread.stop_stt_timer_for_barge_in()

        assert recognizer.finalized == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SpeechSDKThread: full partial -> final turn cycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestTurnCycle:
    def test_partial_then_final_then_next_partial_barges_in(self):
        """End-to-end guard lifecycle across a turn boundary.

        1. Meaningful partial -> barge-in scheduled (user starts speaking).
        2. Final -> turn guard armed (turn is about to be spawned).
        3. Trailing partial -> suppressed by the guard.
        4. Guard disarmed (agent started speaking) -> next partial barges in again.
        """
        on_partial_transcript = Mock()
        thread, recognizer, bridge = _make_thread(on_partial_transcript=on_partial_transcript)
        bridge.schedule_barge_in = Mock()

        # 1. User starts speaking.
        recognizer.on_partial("what is my", "en-US", None)
        assert bridge.schedule_barge_in.call_count == 1

        # 2. Utterance finalized -> guard armed.
        recognizer.on_final("what is my balance", "en-US", None)
        assert bridge.turn_guard_active is True

        # 3. Trailing partial while guard is armed is ignored.
        recognizer.on_partial("balance please", "en-US", None)
        assert bridge.schedule_barge_in.call_count == 1  # unchanged

        # 4. Agent starts speaking -> guard released, next partial barges in.
        bridge.disarm_turn_guard()
        recognizer.on_partial("actually wait", "en-US", None)
        assert bridge.schedule_barge_in.call_count == 2
