"""
Simple Tests for ACS Media Lifecycle (Without OpenTelemetry Issues)
===================================================================

Simplified tests that avoid OpenTelemetry logging conflicts.
"""

import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import asyncio
import json
import base64
import threading
import time
from unittest.mock import Mock, AsyncMock, patch


# Test the basic functionality without complex logging
def test_thread_bridge_basic():
    """Test basic ThreadBridge functionality."""
    from apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle import ThreadBridge

    bridge = ThreadBridge()
    assert bridge.main_loop is None

    # Test setting event loop
    loop = asyncio.new_event_loop()
    bridge.set_main_loop(loop)
    assert bridge.main_loop is loop
    print("✅ ThreadBridge basic test passed")


def test_speech_event_creation():
    """Test SpeechEvent creation."""
    from apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle import (
        SpeechEvent,
        SpeechEventType,
    )

    event = SpeechEvent(
        event_type=SpeechEventType.FINAL, text="Hello world", language="en-US"
    )

    assert event.event_type == SpeechEventType.FINAL
    assert event.text == "Hello world"
    assert event.language == "en-US"
    assert isinstance(event.timestamp, float)
    print("✅ SpeechEvent creation test passed")


@pytest.mark.asyncio
async def test_main_event_loop_basic():
    """Test basic MainEventLoop functionality."""
    from apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle import MainEventLoop

    # Mock websocket and route turn thread
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()

    mock_route_turn_thread = Mock()
    mock_route_turn_thread.cancel_current_processing = AsyncMock()

    main_loop = MainEventLoop(mock_websocket, "test-call", mock_route_turn_thread)

    # Test barge-in handling
    await main_loop.handle_barge_in()

    # Verify cancel_current_processing was called instead of send_text
    mock_route_turn_thread.cancel_current_processing.assert_called()
    print("✅ MainEventLoop basic test passed")


class MockRecognizer:
    """Simple mock recognizer."""

    def __init__(self):
        self.started = False
        self.callbacks = {}
        self.push_stream = Mock()  # Add mock push stream

    def set_partial_result_callback(self, callback):
        self.callbacks["partial"] = callback

    def set_final_result_callback(self, callback):
        self.callbacks["final"] = callback

    def set_cancel_callback(self, callback):
        self.callbacks["cancel"] = callback

    def start(self):
        self.started = True

    def write_bytes(self, data):
        pass


def test_speech_sdk_thread_basic():
    """Test basic SpeechSDKThread functionality."""
    from apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle import (
        SpeechSDKThread,
        ThreadBridge,
    )

    recognizer = MockRecognizer()
    bridge = ThreadBridge()
    speech_queue = asyncio.Queue()
    barge_in_handler = AsyncMock()

    # Mock logging to avoid OpenTelemetry issues
    with patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger"):
        thread = SpeechSDKThread(
            call_connection_id="test-call",
            recognizer=recognizer,
            thread_bridge=bridge,
            barge_in_handler=barge_in_handler,
            speech_queue=speech_queue,
        )

        # Test callbacks were set
        assert "partial" in recognizer.callbacks
        assert "final" in recognizer.callbacks
        assert "cancel" in recognizer.callbacks

        # Test thread preparation
        thread.prepare_thread()
        assert thread.thread_running

        # Test recognizer start
        thread.start_recognizer()
        assert recognizer.started

        # Cleanup
        thread.stop()

    print("✅ SpeechSDKThread basic test passed")


@pytest.mark.asyncio
async def test_simple_media_processing():
    """Test simple media message processing."""
    from apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle import MainEventLoop

    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_route_turn_thread = Mock()

    main_loop = MainEventLoop(mock_websocket, "test-call", mock_route_turn_thread)

    # Test AudioMetadata handling
    metadata_json = json.dumps(
        {
            "kind": "AudioMetadata",
            "audioMetadata": {
                "subscriptionId": "test",
                "encoding": "PCM",
                "sampleRate": 16000,
            },
        }
    )

    mock_recognizer = MockRecognizer()
    mock_acs_handler = Mock()
    mock_acs_handler.speech_sdk_thread = Mock()
    mock_acs_handler.speech_sdk_thread.start_recognizer = Mock()

    with patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger"):
        await main_loop.handle_media_message(
            metadata_json, mock_recognizer, mock_acs_handler
        )

    # Verify recognizer was started
    mock_acs_handler.speech_sdk_thread.start_recognizer.assert_called_once()
    print("✅ Simple media processing test passed")


def test_callback_triggering():
    """Test speech recognition callback triggering."""
    from apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle import (
        SpeechSDKThread,
        ThreadBridge,
    )

    recognizer = MockRecognizer()
    bridge = ThreadBridge()
    speech_queue = asyncio.Queue()
    barge_in_handler = Mock()

    # Track callback calls
    callback_calls = []

    def mock_schedule_barge_in(handler):
        callback_calls.append("barge_in")

    def mock_queue_speech_result(queue, event):
        callback_calls.append(f"speech_result_{event.event_type.value}")

    bridge.schedule_barge_in = mock_schedule_barge_in
    bridge.queue_speech_result = mock_queue_speech_result

    with patch("apps.rtagent.backend.api.v1.handlers.acs_media_lifecycle.logger"):
        thread = SpeechSDKThread(
            call_connection_id="test-call",
            recognizer=recognizer,
            thread_bridge=bridge,
            barge_in_handler=barge_in_handler,
            speech_queue=speech_queue,
        )

        # Trigger partial callback (should trigger barge-in)
        recognizer.callbacks["partial"]("Hello", "en-US")
        assert "barge_in" in callback_calls

        # Trigger final callback (should queue speech result)
        recognizer.callbacks["final"]("Hello world", "en-US")
        assert "speech_result_final" in callback_calls

    print("✅ Callback triggering test passed")


if __name__ == "__main__":
    # Run tests individually to avoid logging issues
    test_thread_bridge_basic()
    test_speech_event_creation()
    test_speech_sdk_thread_basic()
    test_callback_triggering()

    # Run async tests
    asyncio.run(test_main_event_loop_basic())
    asyncio.run(test_simple_media_processing())

    print("🎉 All simplified tests passed!")
