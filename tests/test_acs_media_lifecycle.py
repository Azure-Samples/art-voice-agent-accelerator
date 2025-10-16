"""
Tests for ACS Media Lifecycle Three-Thread Architecture
======================================================

Tests the complete V1 ACS Media Handler implementation including:
- Three-thread architecture (Speech SDK, Route Turn, Main Event Loop)
- Cross-thread communication via ThreadBridge
- Barge-in detection and cancellation
- Speech recognition callback handling
- Media message processing
- Handler lifecycle management

"""

import pytest
import asyncio
import json
import base64
import threading
import time
from unittest.mock import Mock, AsyncMock, MagicMock, patch, call
from typing import Optional, Dict, Any
from types import SimpleNamespace

from fastapi.websockets import WebSocketState

# Import the classes under test
from apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle import (
    ACSMediaHandler,
    ThreadBridge,
    SpeechSDKThread,
    RouteTurnThread,
    MainEventLoop,
    SpeechEvent,
    SpeechEventType,
)


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.sent_messages = []
        self.closed = False
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.state = SimpleNamespace()
        class _ConnManager:
            def __init__(self):
                self.broadcasts = []

            async def broadcast_session(self, session_id, envelope):
                self.broadcasts.append((session_id, envelope))
                return 1

        self._conn_manager = _ConnManager()
        self.app = SimpleNamespace(
            state=SimpleNamespace(conn_manager=self._conn_manager, redis=None)
        )

    async def send_text(self, message: str):
        """Mock send_text method."""
        self.sent_messages.append(message)

    async def send_json(self, payload):
        """Mock send_json method matching FastAPI interface."""
        self.sent_messages.append(payload)

    async def close(self):
        """Mock close method."""
        self.closed = True
        self.client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED

    def mark_closing(self):
        """Mark the websocket as closing without delivering more messages."""
        self.client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED


class MockRecognizer:
    """Mock speech recognizer for testing."""

    def __init__(self):
        self.started = False
        self.stopped = False
        self.callbacks = {}
        self.write_bytes_calls = []
        self.push_stream = object()

    def set_partial_result_callback(self, callback):
        """Mock partial result callback setter."""
        self.callbacks["partial"] = callback

    def set_final_result_callback(self, callback):
        """Mock final result callback setter."""
        self.callbacks["final"] = callback

    def set_cancel_callback(self, callback):
        """Mock cancel callback setter."""
        self.callbacks["cancel"] = callback

    def start(self):
        """Mock start method."""
        self.started = True

    def stop(self):
        """Mock stop method."""
        self.stopped = True

    def write_bytes(self, audio_bytes: bytes):
        """Mock write_bytes method."""
        self.write_bytes_calls.append(len(audio_bytes))

    def trigger_partial(self, text: str, lang: str = "en-US"):
        """Helper method to trigger partial callback."""
        if "partial" in self.callbacks:
            self.callbacks["partial"](text, lang)

    def trigger_final(self, text: str, lang: str = "en-US"):
        """Helper method to trigger final callback."""
        if "final" in self.callbacks:
            self.callbacks["final"](text, lang)

    def trigger_error(self, error: str):
        """Helper method to trigger error callback."""
        if "cancel" in self.callbacks:
            self.callbacks["cancel"](error)


class MockOrchestrator:
    """Mock orchestrator function for testing."""

    def __init__(self):
        self.calls = []
        self.responses = ["Hello, how can I help you?"]
        self.call_index = 0

    async def __call__(self, cm, transcript: str, ws, **kwargs):
        """Mock orchestrator call."""
        self.calls.append(
            {
                "transcript": transcript,
                "timestamp": time.time(),
                "kwargs": kwargs,
            }
        )

        # Return mock response
        response = self.responses[self.call_index % len(self.responses)]
        self.call_index += 1
        return response


async def wait_for_condition(predicate, timeout: float = 0.5, interval: float = 0.05) -> bool:
    """Poll predicate until truthy or timeout reached."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


@pytest.fixture
def mock_websocket():
    """Fixture providing a mock WebSocket."""
    return MockWebSocket()


@pytest.fixture
def mock_recognizer():
    """Fixture providing a mock speech recognizer."""
    return MockRecognizer()


@pytest.fixture
def mock_orchestrator():
    """Fixture providing a mock orchestrator."""
    return MockOrchestrator()


@pytest.fixture
def mock_memory_manager():
    """Fixture providing a lightweight memory manager."""
    manager = Mock()
    manager.session_id = "session-123"
    return manager


@pytest.fixture
async def media_handler(
    mock_websocket, mock_recognizer, mock_orchestrator, mock_memory_manager
):
    """Fixture providing a configured ACS Media Handler."""
    with patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger"):
        handler = ACSMediaHandler(
            websocket=mock_websocket,
            call_connection_id="test-call-123",
            session_id="test-session-456",
            recognizer=mock_recognizer,
            orchestrator_func=mock_orchestrator,
            memory_manager=mock_memory_manager,
            greeting_text="Hello, welcome to our service!",
        )

        # Start the handler
        await handler.start()

        yield handler

        # Cleanup
        await handler.stop()


class TestThreadBridge:
    """Test ThreadBridge cross-thread communication."""

    def test_initialization(self):
        """Test ThreadBridge initialization."""
        bridge = ThreadBridge()
        assert bridge.main_loop is None

    def test_set_main_loop(self):
        """Test setting main event loop."""
        bridge = ThreadBridge()
        loop = asyncio.new_event_loop()

        try:
            bridge.set_main_loop(loop)
            assert bridge.main_loop is loop
        finally:
            loop.close()

    @pytest.mark.asyncio
    async def test_queue_speech_result_put_nowait(self):
        """Test queuing speech result using put_nowait."""
        bridge = ThreadBridge()
        queue = asyncio.Queue(maxsize=10)

        event = SpeechEvent(
            event_type=SpeechEventType.FINAL, text="Hello world", language="en-US"
        )

        bridge.queue_speech_result(queue, event)

        # Verify event was queued
        queued_event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert queued_event.text == "Hello world"
        assert queued_event.event_type == SpeechEventType.FINAL

    @pytest.mark.asyncio
    async def test_queue_speech_result_with_event_loop(self):
        """Test queuing speech result with event loop fallback."""
        bridge = ThreadBridge()
        loop = asyncio.get_running_loop()
        bridge.set_main_loop(loop)

        # Create a full queue to force fallback
        queue = asyncio.Queue(maxsize=1)
        await queue.put("dummy_item")  # Fill the queue

        event = SpeechEvent(
            event_type=SpeechEventType.PARTIAL, text="Test", language="en-US"
        )

        with patch.object(queue, "put_nowait", side_effect=asyncio.QueueFull):
            with patch(
                "apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.asyncio.run_coroutine_threadsafe"
            ) as mock_run:
                bridge.queue_speech_result(queue, event)
                mock_run.assert_not_called()

        # Queue should still only contain the dummy item (event dropped)
        assert await queue.get() == "dummy_item"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.05)


class TestSpeechSDKThread:
    """Test SpeechSDKThread functionality."""

    @pytest.mark.asyncio
    async def test_initialization(self, mock_recognizer):
        """Test SpeechSDKThread initialization."""
        bridge = ThreadBridge()
        speech_queue = asyncio.Queue()
        barge_in_handler = AsyncMock()

        thread = SpeechSDKThread(
            "call-123",
            mock_recognizer,
            bridge,
            barge_in_handler,
            speech_queue,
        )

        assert thread.recognizer is mock_recognizer
        assert thread.thread_bridge is bridge
        assert not thread.thread_running
        assert not thread.recognizer_started

    @pytest.mark.asyncio
    async def test_callback_setup(self, mock_recognizer):
        """Test speech recognition callback setup."""
        bridge = ThreadBridge()
        speech_queue = asyncio.Queue()
        barge_in_handler = AsyncMock()

        thread = SpeechSDKThread(
            "call-123",
            mock_recognizer,
            bridge,
            barge_in_handler,
            speech_queue,
        )

        # Verify callbacks were set
        assert "partial" in mock_recognizer.callbacks
        assert "final" in mock_recognizer.callbacks
        assert "cancel" in mock_recognizer.callbacks

    @pytest.mark.asyncio
    async def test_prepare_thread(self, mock_recognizer):
        """Test thread preparation."""
        bridge = ThreadBridge()
        speech_queue = asyncio.Queue()
        barge_in_handler = AsyncMock()

        thread = SpeechSDKThread(
            "call-123",
            mock_recognizer,
            bridge,
            barge_in_handler,
            speech_queue,
        )

        thread.prepare_thread()

        assert thread.thread_running
        assert thread.thread_obj is not None
        assert thread.thread_obj.is_alive()

        # Cleanup
        thread.stop()

    @pytest.mark.asyncio
    async def test_start_recognizer(self, mock_recognizer):
        """Test recognizer startup."""
        bridge = ThreadBridge()
        speech_queue = asyncio.Queue()
        barge_in_handler = AsyncMock()

        thread = SpeechSDKThread(
            "call-123",
            mock_recognizer,
            bridge,
            barge_in_handler,
            speech_queue,
        )

        thread.prepare_thread()
        thread.start_recognizer()

        assert mock_recognizer.started
        assert thread.recognizer_started

        # Cleanup
        thread.stop()


class TestMainEventLoop:
    """Test MainEventLoop media processing."""

    @pytest.fixture
    def main_event_loop(self, mock_websocket):
        """Fixture for MainEventLoop."""
        route_turn_thread = Mock()
        return MainEventLoop(mock_websocket, "test-call-123", route_turn_thread)

    @pytest.mark.asyncio
    async def test_handle_audio_metadata(self, main_event_loop, mock_recognizer):
        """Test AudioMetadata handling."""
        acs_handler = Mock()
        acs_handler.speech_sdk_thread = Mock()
        acs_handler.speech_sdk_thread.start_recognizer = Mock()

        stream_data = json.dumps(
            {
                "kind": "AudioMetadata",
                "audioMetadata": {
                    "subscriptionId": "test",
                    "encoding": "PCM",
                    "sampleRate": 16000,
                    "channels": 1,
                },
            }
        )

        await main_event_loop.handle_media_message(
            stream_data, mock_recognizer, acs_handler
        )

        # Verify recognizer was started
        acs_handler.speech_sdk_thread.start_recognizer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_audio_data(self, main_event_loop, mock_recognizer):
        """Test AudioData processing."""
        # Mock audio data (base64 encoded)
        audio_bytes = b"\x00" * 320  # 20ms of silence
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        stream_data = json.dumps(
            {"kind": "AudioData", "audioData": {"data": audio_b64, "silent": False}}
        )

        with patch.object(
            main_event_loop, "_process_audio_chunk_async"
        ) as mock_process:
            await main_event_loop.handle_media_message(
                stream_data, mock_recognizer, None
            )

            # Give async task time to start
            await asyncio.sleep(0.1)

            # Verify audio processing was scheduled
            mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_audio_chunk_async(self, main_event_loop, mock_recognizer):
        """Test audio chunk processing."""
        audio_bytes = b"\x00" * 320
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        await main_event_loop._process_audio_chunk_async(audio_b64, mock_recognizer)

        # Verify recognizer received audio
        assert len(mock_recognizer.write_bytes_calls) == 1
        assert mock_recognizer.write_bytes_calls[0] == 320

    @pytest.mark.asyncio
    async def test_barge_in_handling(self, main_event_loop):
        """Test barge-in interruption."""
        # Mock current playback task
        main_event_loop.current_playback_task = asyncio.create_task(asyncio.sleep(1))

        route_thread = SimpleNamespace(
            cancel_current_processing=AsyncMock()
        )
        main_event_loop.route_turn_thread = route_thread

        with patch.object(main_event_loop, "_send_stop_audio_command") as mock_stop:
            await main_event_loop.handle_barge_in()

            # Verify barge-in actions
            assert main_event_loop.current_playback_task.cancelled()
            route_thread.cancel_current_processing.assert_awaited_once()
            mock_stop.assert_called_once()


class TestRouteTurnThread:
    """Test RouteTurnThread conversation processing."""

    @pytest.mark.asyncio
    async def test_initialization(
        self, mock_orchestrator, mock_memory_manager, mock_websocket
    ):
        """Test RouteTurnThread initialization."""
        speech_queue = asyncio.Queue()

        thread = RouteTurnThread(
            call_connection_id="call-123",
            speech_queue=speech_queue,
            orchestrator_func=mock_orchestrator,
            memory_manager=mock_memory_manager,
            websocket=mock_websocket,
        )

        assert thread.speech_queue is speech_queue
        assert thread.orchestrator_func is mock_orchestrator
        assert not thread.running

    @pytest.mark.asyncio
    async def test_speech_event_processing(
        self, mock_orchestrator, mock_memory_manager, mock_websocket
    ):
        """Test processing speech events."""
        speech_queue = asyncio.Queue()

        thread = RouteTurnThread(
            call_connection_id="call-123",
            speech_queue=speech_queue,
            orchestrator_func=mock_orchestrator,
            memory_manager=mock_memory_manager,
            websocket=mock_websocket,
        )

        event = SpeechEvent(
            event_type=SpeechEventType.FINAL, text="Hello world", language="en-US"
        )

        await thread._process_final_speech(event)

        assert len(mock_orchestrator.calls) == 1
        assert mock_orchestrator.calls[0]["transcript"] == "Hello world"


class TestACSMediaHandler:
    """Test complete ACS Media Handler integration."""

    @pytest.mark.asyncio
    async def test_handler_lifecycle(self, media_handler, mock_recognizer):
        """Test complete handler lifecycle."""
        # Verify handler started correctly
        assert media_handler.running
        assert media_handler.speech_sdk_thread.thread_running

        # Test stopping
        await media_handler.stop()
        assert not media_handler.running
        assert media_handler._stopped

    @pytest.mark.asyncio
    @patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger")
    async def test_media_message_processing(
        self, mock_logger, media_handler, mock_recognizer
    ):
        """Test end-to-end media message processing."""
        # Send AudioMetadata
        metadata = json.dumps(
            {
                "kind": "AudioMetadata",
                "audioMetadata": {
                    "subscriptionId": "test",
                    "encoding": "PCM",
                    "sampleRate": 16000,
                },
            }
        )

        await media_handler.handle_media_message(metadata)

        # Verify recognizer was started
        assert mock_recognizer.started

        # Send AudioData
        audio_bytes = b"\x00" * 320
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        audio_data = json.dumps(
            {"kind": "AudioData", "audioData": {"data": audio_b64, "silent": False}}
        )

        await media_handler.handle_media_message(audio_data)

        # Give async processing time
        await asyncio.sleep(0.1)

        # Verify audio was processed
        assert len(mock_recognizer.write_bytes_calls) > 0

    @pytest.mark.asyncio
    @patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger")
    async def test_barge_in_flow(
        self, mock_logger, media_handler, mock_recognizer, mock_orchestrator
    ):
        """Test complete barge-in detection and cancellation flow."""
        # Start processing by triggering recognizer
        await media_handler.handle_media_message(
            json.dumps(
                {"kind": "AudioMetadata", "audioMetadata": {"subscriptionId": "test"}}
            )
        )

        # Simulate speech detection that should trigger barge-in
        mock_recognizer.trigger_partial("Hello", "en-US")

        # Give time for barge-in processing
        await asyncio.sleep(0.1)

        # Verify barge-in was triggered (check WebSocket for stop command)
        sent_messages = media_handler.websocket.sent_messages
        stop_commands = [
            msg
            for msg in sent_messages
            if (
                isinstance(msg, str)
                and "StopAudio" in msg
            )
            or (
                isinstance(msg, dict)
                and msg.get("kind") == "StopAudio"
            )
        ]
        assert len(stop_commands) > 0

    @pytest.mark.asyncio
    @patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger")
    async def test_speech_recognition_callbacks(
        self, mock_logger, media_handler, mock_recognizer, mock_orchestrator
    ):
        """Test speech recognition callback integration."""
        # Start recognizer
        await media_handler.handle_media_message(
            json.dumps(
                {"kind": "AudioMetadata", "audioMetadata": {"subscriptionId": "test"}}
            )
        )

        # Trigger final speech result
        handler_spy = AsyncMock()
        media_handler.route_turn_thread._process_final_speech = handler_spy
        mock_recognizer.trigger_final("How can you help me?", "en-US")

        assert await wait_for_condition(lambda: handler_spy.await_count >= 1)
        speech_event = handler_spy.await_args[0][0]
        assert isinstance(speech_event, SpeechEvent)
        assert speech_event.text == "How can you help me?"

    @pytest.mark.asyncio
    @patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger")
    async def test_error_handling(self, mock_logger, media_handler, mock_recognizer):
        """Test error handling in speech recognition."""
        # Start recognizer
        await media_handler.handle_media_message(
            json.dumps(
                {"kind": "AudioMetadata", "audioMetadata": {"subscriptionId": "test"}}
            )
        )

        # Trigger error
        mock_recognizer.trigger_error("Test error message")

        # Give time for processing
        await asyncio.sleep(0.1)

        # Verify error was handled (no exceptions raised)
        assert media_handler.running  # Handler should still be running

    @pytest.mark.asyncio
    @patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger")
    async def test_concurrent_audio_processing(
        self, mock_logger, media_handler, mock_recognizer
    ):
        """Test concurrent audio chunk processing with task limiting."""
        # Start recognizer
        await media_handler.handle_media_message(
            json.dumps(
                {"kind": "AudioMetadata", "audioMetadata": {"subscriptionId": "test"}}
            )
        )

        # Send multiple audio chunks rapidly
        audio_bytes = b"\x00" * 320
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        audio_data = json.dumps(
            {"kind": "AudioData", "audioData": {"data": audio_b64, "silent": False}}
        )

        # Send 10 audio chunks
        tasks = []
        for _ in range(10):
            task = asyncio.create_task(media_handler.handle_media_message(audio_data))
            tasks.append(task)

        # Wait for all processing
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.2)

        # Verify audio processing occurred (some may be dropped due to limiting)
        assert len(mock_recognizer.write_bytes_calls) > 0
        assert len(mock_recognizer.write_bytes_calls) <= 10


class TestSpeechEvent:
    """Test SpeechEvent data structure."""

    def test_speech_event_creation(self):
        """Test SpeechEvent creation and timing."""
        event = SpeechEvent(
            event_type=SpeechEventType.FINAL,
            text="Hello world",
            language="en-US",
            speaker_id="speaker1",
        )

        assert event.event_type == SpeechEventType.FINAL
        assert event.text == "Hello world"
        assert event.language == "en-US"
        assert event.speaker_id == "speaker1"
        assert isinstance(event.timestamp, float)
        assert event.timestamp > 0

    def test_speech_event_types(self):
        """Test all speech event types."""
        # Test all event types
        for event_type in SpeechEventType:
            event = SpeechEvent(event_type=event_type, text="test", language="en-US")
            assert event.event_type == event_type


# Integration test scenarios
class TestIntegrationScenarios:
    """Integration tests for realistic usage scenarios."""

    @pytest.mark.asyncio
    @patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger")
    async def test_call_flow_with_greeting(
        self,
        mock_logger,
        mock_websocket,
        mock_recognizer,
        mock_orchestrator,
        mock_memory_manager,
    ):
        """Test complete call flow including greeting."""
        # Create handler with greeting
        handler = ACSMediaHandler(
            websocket=mock_websocket,
            call_connection_id="test-call-integration",
            session_id="test-session-integration",
            recognizer=mock_recognizer,
            orchestrator_func=mock_orchestrator,
            memory_manager=mock_memory_manager,
            greeting_text="Welcome! How can I help you today?",
        )

        await handler.start()

        try:
            handler_spy = AsyncMock()
            handler.route_turn_thread._process_final_speech = handler_spy

            # Simulate call connection with AudioMetadata
            await handler.handle_media_message(
                json.dumps(
                    {
                        "kind": "AudioMetadata",
                        "audioMetadata": {
                            "subscriptionId": "test-integration",
                            "encoding": "PCM",
                            "sampleRate": 16000,
                            "channels": 1,
                        },
                    }
                )
            )

            # Give time for greeting to be processed
            await asyncio.sleep(0.3)
            assert handler.main_event_loop.greeting_played

            # Simulate customer speech
            mock_recognizer.trigger_final("I need help with my account", "en-US")

            assert await wait_for_condition(lambda: handler_spy.await_count >= 1)
            speech_event = handler_spy.await_args[0][0]
            assert "account" in speech_event.text.lower()

        finally:
            await handler.stop()

    @pytest.mark.asyncio
    @patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger")
    async def test_barge_in_during_response(
        self,
        mock_logger,
        mock_websocket,
        mock_recognizer,
        mock_orchestrator,
        mock_memory_manager,
    ):
        """Test barge-in interruption during AI response playback."""
        handler = ACSMediaHandler(
            websocket=mock_websocket,
            call_connection_id="test-barge-in",
            session_id="test-barge-in-session",
            recognizer=mock_recognizer,
            orchestrator_func=mock_orchestrator,
            memory_manager=mock_memory_manager,
        )

        await handler.start()

        try:
            # Start call
            await handler.handle_media_message(
                json.dumps(
                    {
                        "kind": "AudioMetadata",
                        "audioMetadata": {"subscriptionId": "test-barge-in"},
                    }
                )
            )

            # Customer asks question
            mock_recognizer.trigger_final("What are your hours?", "en-US")
            await asyncio.sleep(0.1)

            # While AI is responding, customer interrupts (barge-in)
            mock_recognizer.trigger_partial("Actually, I need to", "en-US")
            await asyncio.sleep(0.1)

            # Verify stop audio command was sent for barge-in
            sent_messages = handler.websocket.sent_messages
            stop_commands = [
                msg
                for msg in sent_messages
                if (
                    isinstance(msg, str)
                    and "StopAudio" in msg
                )
                or (
                    isinstance(msg, dict)
                    and msg.get("kind") == "StopAudio"
                )
            ]
            assert len(stop_commands) > 0

        finally:
            await handler.stop()


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
