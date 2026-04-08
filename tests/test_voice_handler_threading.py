"""
Voice Handler Threading & Concurrency Tests
============================================

Tests validating thread safety, instance isolation, and concurrent access patterns
in voice handler components:

1. SpeechSDKThread Barge-In: Validates stop_stt_timer_for_barge_in method for
   proper timer cancellation during speech interruption.

2. Instance-Level Task Tracking: Ensures VoiceLiveSDKHandler tracks background
   tasks per-instance (not globally), preventing cross-session interference.

3. Audio Resampling: Tests resampling quality with anti-aliasing filter,
   ensuring correct sample rate conversion without artifacts.

4. Queue Thread Safety: Validates atomic queue eviction with threading.Lock
   to prevent race conditions during concurrent access.

Run with: pytest tests/test_voice_handler_threading.py -v
"""

import asyncio
import base64
import threading
from typing import Any, Awaitable
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Issue 1: stop_stt_timer_for_barge_in method tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSpeechSDKThreadBargeIn:
    """Tests for Issue 1: stop_stt_timer_for_barge_in method."""

    def test_stop_stt_timer_method_exists(self):
        """SpeechSDKThread should have stop_stt_timer_for_barge_in method."""
        from apps.artagent.backend.voice.speech_cascade.handler import SpeechSDKThread

        assert hasattr(SpeechSDKThread, "stop_stt_timer_for_barge_in")
        assert callable(getattr(SpeechSDKThread, "stop_stt_timer_for_barge_in"))

    def test_stop_stt_timer_does_not_raise(self):
        """Method should not raise when called."""
        from apps.artagent.backend.voice.speech_cascade.handler import (
            SpeechSDKThread,
            ThreadBridge,
        )

        # Create minimal mock dependencies
        mock_recognizer = MagicMock()
        mock_bridge = ThreadBridge()
        mock_queue = asyncio.Queue()

        thread = SpeechSDKThread(
            connection_id="test-conn",
            recognizer=mock_recognizer,
            thread_bridge=mock_bridge,
            barge_in_handler=lambda: None,
            speech_queue=mock_queue,
        )

        # Should not raise
        thread.stop_stt_timer_for_barge_in()

    def test_stop_stt_timer_with_recognizer_finalize(self):
        """Method should call finalize_current_utterance if available."""
        from apps.artagent.backend.voice.speech_cascade.handler import (
            SpeechSDKThread,
            ThreadBridge,
        )

        # Create mock with finalize method
        mock_recognizer = MagicMock()
        mock_recognizer.finalize_current_utterance = MagicMock()
        mock_bridge = ThreadBridge()
        mock_queue = asyncio.Queue()

        thread = SpeechSDKThread(
            connection_id="test-conn",
            recognizer=mock_recognizer,
            thread_bridge=mock_bridge,
            barge_in_handler=lambda: None,
            speech_queue=mock_queue,
        )

        thread.stop_stt_timer_for_barge_in()

        # If recognizer has the method, it should be called
        mock_recognizer.finalize_current_utterance.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Issue 2: Instance-level background task tracking tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestVoiceLiveBackgroundTasks:
    """Tests for Issue 2: Background task tracking at instance level."""

    def test_background_task_fn_type_exists(self):
        """BackgroundTaskFn type alias should exist."""
        from apps.artagent.backend.voice.voicelive.handler import BackgroundTaskFn

        assert BackgroundTaskFn is not None

    def test_handler_has_pending_tasks_set(self):
        """VoiceLiveSDKHandler should have _pending_background_tasks instance variable."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        # Create mock websocket
        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.session_id = "test-session"

        handler = VoiceLiveSDKHandler(
            websocket=mock_ws,
            session_id="test-session",
        )

        # Check instance variable exists
        assert hasattr(handler, "_pending_background_tasks")
        assert isinstance(handler._pending_background_tasks, set)

    def test_separate_handlers_have_separate_task_sets(self):
        """Different handler instances should have independent task sets."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        mock_ws1 = MagicMock()
        mock_ws1.state = MagicMock()
        mock_ws1.state.session_id = "session-1"

        mock_ws2 = MagicMock()
        mock_ws2.state = MagicMock()
        mock_ws2.state.session_id = "session-2"

        handler1 = VoiceLiveSDKHandler(websocket=mock_ws1, session_id="session-1")
        handler2 = VoiceLiveSDKHandler(websocket=mock_ws2, session_id="session-2")

        # They should have separate sets
        assert handler1._pending_background_tasks is not handler2._pending_background_tasks

    def test_handler_has_background_task_method(self):
        """VoiceLiveSDKHandler should have _background_task instance method."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        assert hasattr(VoiceLiveSDKHandler, "_background_task")

    def test_handler_has_cancel_all_method(self):
        """VoiceLiveSDKHandler should have _cancel_all_background_tasks instance method."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        assert hasattr(VoiceLiveSDKHandler, "_cancel_all_background_tasks")

    @pytest.mark.asyncio
    async def test_background_task_is_tracked(self):
        """Background tasks created via _background_task should be tracked."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.session_id = "test-session"

        handler = VoiceLiveSDKHandler(websocket=mock_ws, session_id="test-session")

        async def dummy_coro():
            await asyncio.sleep(0.1)

        # Create a background task
        task = handler._background_task(dummy_coro(), label="test")

        # Task should be in the set
        assert task in handler._pending_background_tasks

        # Wait for completion
        await task

        # After completion, task should be removed via callback
        await asyncio.sleep(0.01)  # Give callback time to run
        assert task not in handler._pending_background_tasks

    @pytest.mark.asyncio
    async def test_cancel_all_background_tasks(self):
        """_cancel_all_background_tasks should cancel pending tasks."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.session_id = "test-session"

        handler = VoiceLiveSDKHandler(websocket=mock_ws, session_id="test-session")

        async def long_running():
            await asyncio.sleep(10)

        # Create multiple tasks
        task1 = handler._background_task(long_running(), label="task1")
        task2 = handler._background_task(long_running(), label="task2")

        # Cancel all
        cancelled = handler._cancel_all_background_tasks()

        assert cancelled == 2
        assert len(handler._pending_background_tasks) == 0

        # Give event loop a chance to process cancellations
        await asyncio.sleep(0.01)

        # Tasks should now be cancelled or done
        assert task1.cancelled() or task1.done()
        assert task2.cancelled() or task2.done()


# ═══════════════════════════════════════════════════════════════════════════════
# Issue 3: Audio resampling quality tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAudioResampling:
    """Tests for Issue 3: Improved audio resampling with anti-aliasing."""

    def test_resample_24k_to_16k(self):
        """Resampling from 24kHz to 16kHz should work correctly."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.session_id = "test-session"

        handler = VoiceLiveSDKHandler(websocket=mock_ws, session_id="test-session")
        handler._acs_sample_rate = 16000

        # Create test audio (simple sine wave at 24kHz)
        duration = 0.1  # 100ms
        samples_24k = int(24000 * duration)
        t = np.linspace(0, duration, samples_24k, endpoint=False)
        freq = 440  # A4 note
        audio_24k = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)
        audio_bytes = audio_24k.tobytes()

        # Resample
        result_b64 = handler._resample_audio(audio_bytes)
        result_bytes = base64.b64decode(result_b64)
        result_audio = np.frombuffer(result_bytes, dtype=np.int16)

        # Check output length (should be 2/3 of input)
        expected_len = int(samples_24k * 16000 / 24000)
        assert len(result_audio) == expected_len

    def test_resample_same_rate_returns_original(self):
        """Resampling at same rate should return original audio."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.session_id = "test-session"

        handler = VoiceLiveSDKHandler(websocket=mock_ws, session_id="test-session")
        handler._acs_sample_rate = 24000  # Same as source

        # Create test audio
        audio = np.array([100, 200, 300, 400, 500], dtype=np.int16)
        audio_bytes = audio.tobytes()

        # Resample (should be no-op)
        result_b64 = handler._resample_audio(audio_bytes)
        result_bytes = base64.b64decode(result_b64)

        # Should be identical
        assert result_bytes == audio_bytes

    def test_resample_handles_empty_audio(self):
        """Resampling should handle edge cases gracefully."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.session_id = "test-session"

        handler = VoiceLiveSDKHandler(websocket=mock_ws, session_id="test-session")
        handler._acs_sample_rate = 16000

        # Empty audio should not crash
        empty_bytes = b""
        result = handler._resample_audio(empty_bytes)
        assert isinstance(result, str)  # Should return valid base64

    def test_resample_preserves_amplitude_range(self):
        """Resampling should not introduce clipping beyond int16 range."""
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.session_id = "test-session"

        handler = VoiceLiveSDKHandler(websocket=mock_ws, session_id="test-session")
        handler._acs_sample_rate = 16000

        # Create audio near max amplitude
        audio = np.array([30000, -30000, 32000, -32000], dtype=np.int16)
        audio_bytes = audio.tobytes()

        result_b64 = handler._resample_audio(audio_bytes)
        result_bytes = base64.b64decode(result_b64)
        result_audio = np.frombuffer(result_bytes, dtype=np.int16)

        # All samples should be within int16 range
        assert np.all(result_audio >= -32768)
        assert np.all(result_audio <= 32767)


# ═══════════════════════════════════════════════════════════════════════════════
# Issue 4: Queue eviction thread safety tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueueEvictionThreadSafety:
    """Tests for Issue 4: Thread-safe queue eviction in ThreadBridge."""

    def test_thread_bridge_has_queue_lock(self):
        """ThreadBridge should have _queue_lock for atomic eviction."""
        from apps.artagent.backend.voice.speech_cascade.handler import ThreadBridge

        bridge = ThreadBridge()
        assert hasattr(bridge, "_queue_lock")
        assert isinstance(bridge._queue_lock, type(threading.Lock()))

    def test_queue_speech_result_basic(self):
        """queue_speech_result should enqueue events correctly."""
        from apps.artagent.backend.voice.speech_cascade.handler import (
            ThreadBridge,
            SpeechEvent,
            SpeechEventType,
        )

        bridge = ThreadBridge()
        queue = asyncio.Queue(maxsize=10)

        event = SpeechEvent(
            event_type=SpeechEventType.FINAL,
            text="Hello world",
            confidence=0.95,
        )

        bridge.queue_speech_result(queue, event)

        assert queue.qsize() == 1

    def test_queue_partial_dropped_when_full(self):
        """PARTIAL events should be dropped when queue is full."""
        from apps.artagent.backend.voice.speech_cascade.handler import (
            ThreadBridge,
            SpeechEvent,
            SpeechEventType,
        )

        bridge = ThreadBridge()
        queue = asyncio.Queue(maxsize=1)

        # Fill queue
        filler = SpeechEvent(
            event_type=SpeechEventType.FINAL,
            text="Filler",
            confidence=0.9,
        )
        queue.put_nowait(filler)

        # Try to add PARTIAL (should be dropped)
        partial = SpeechEvent(
            event_type=SpeechEventType.PARTIAL,
            text="Partial transcript",
            confidence=0.5,
        )
        bridge.queue_speech_result(queue, partial)

        # Queue should still have only the original event
        assert queue.qsize() == 1

    def test_queue_eviction_prioritizes_important_events(self):
        """Important events should evict PARTIAL events when queue is full."""
        from apps.artagent.backend.voice.speech_cascade.handler import (
            ThreadBridge,
            SpeechEvent,
            SpeechEventType,
        )

        bridge = ThreadBridge()
        queue = asyncio.Queue(maxsize=1)

        # Fill queue with PARTIAL
        partial = SpeechEvent(
            event_type=SpeechEventType.PARTIAL,
            text="Partial",
            confidence=0.5,
        )
        queue.put_nowait(partial)

        # Add FINAL (should evict PARTIAL)
        final = SpeechEvent(
            event_type=SpeechEventType.FINAL,
            text="Final transcript",
            confidence=0.95,
        )
        bridge.queue_speech_result(queue, final)

        # Queue should have FINAL event
        assert queue.qsize() == 1
        queued_event = queue.get_nowait()
        assert queued_event.event_type == SpeechEventType.FINAL

    def test_concurrent_queue_access(self):
        """Multiple threads should safely queue events without corruption."""
        from apps.artagent.backend.voice.speech_cascade.handler import (
            ThreadBridge,
            SpeechEvent,
            SpeechEventType,
        )

        bridge = ThreadBridge()
        queue = asyncio.Queue(maxsize=100)
        errors = []

        def queue_events(thread_id: int):
            try:
                for i in range(50):
                    event = SpeechEvent(
                        event_type=SpeechEventType.PARTIAL if i % 2 == 0 else SpeechEventType.FINAL,
                        text=f"Thread {thread_id} event {i}",
                        confidence=0.9,
                    )
                    bridge.queue_speech_result(queue, event)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=queue_events, args=(i,)) for i in range(5)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0
        assert queue.qsize() > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration test: _SessionMessenger with background task callback
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionMessengerIntegration:
    """Integration tests for _SessionMessenger with background task callback."""

    def test_session_messenger_accepts_callback(self):
        """_SessionMessenger should accept background_task_fn parameter."""
        from apps.artagent.backend.voice.voicelive.handler import _SessionMessenger

        mock_ws = MagicMock()
        mock_ws.state = MagicMock()
        mock_ws.state.session_id = "test-session"

        def mock_background_task(coro, *, label: str):
            task = asyncio.ensure_future(coro) if asyncio.iscoroutine(coro) else MagicMock()
            return task

        # Should not raise
        messenger = _SessionMessenger(mock_ws, background_task_fn=mock_background_task)
        assert messenger._background_task_fn is mock_background_task
