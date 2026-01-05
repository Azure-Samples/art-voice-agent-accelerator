"""
Unit tests for the DTMFProcessor component.

Tests cover:
- Tone normalization (various input formats)
- Buffer management (digit accumulation)
- Auto-flush on timeout
- Terminator key (#) immediate flush
- Cancel key (*) buffer clear
- Cleanup on session end
"""

import os

# Disable telemetry before imports
os.environ.setdefault("DISABLE_CLOUD_TELEMETRY", "true")
os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)

import asyncio
from unittest.mock import AsyncMock

import pytest

from apps.artagent.backend.voice.voicelive.dtmf_processor import (
    DTMFProcessor,
    normalize_dtmf_tone,
)


class TestNormalizeDTMFTone:
    """Tests for the normalize_dtmf_tone function."""

    @pytest.mark.parametrize("input_val,expected", [
        # Numeric digits
        ("0", "0"), ("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"),
        ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8"), ("9", "9"),
        # Word forms
        ("zero", "0"), ("one", "1"), ("two", "2"), ("three", "3"),
        ("four", "4"), ("five", "5"), ("six", "6"), ("seven", "7"),
        ("eight", "8"), ("nine", "9"),
        # Special keys
        ("*", "*"), ("star", "*"), ("asterisk", "*"),
        ("#", "#"), ("pound", "#"), ("hash", "#"),
        # Case insensitivity
        ("ZERO", "0"), ("ONE", "1"), ("STAR", "*"), ("POUND", "#"),
        # Whitespace handling
        ("  1  ", "1"), ("\n2\t", "2"),
        # Integer input
        (0, "0"), (1, "1"), (9, "9"),
    ])
    def test_valid_tones(self, input_val, expected):
        assert normalize_dtmf_tone(input_val) == expected

    @pytest.mark.parametrize("input_val", [
        None, "", "invalid", "ten", "A", "B", "C", "D", "abc", "100",
    ])
    def test_invalid_tones(self, input_val):
        assert normalize_dtmf_tone(input_val) is None


class TestDTMFProcessor:
    """Tests for the DTMFProcessor class."""

    @pytest.fixture
    def callback(self):
        """Create a mock async callback for sequence delivery."""
        return AsyncMock()

    @pytest.fixture
    def processor(self, callback):
        """Create a DTMFProcessor with short flush delay for testing."""
        return DTMFProcessor(
            session_id="test-session",
            on_sequence=callback,
            flush_delay=0.05,  # 50ms for fast tests
        )

    @pytest.mark.asyncio
    async def test_single_digit_flush_on_timeout(self, processor, callback):
        """Single digit flushes after timeout."""
        await processor.handle_tone("5")
        
        # Wait for flush
        await asyncio.sleep(0.1)
        
        callback.assert_called_once_with("5", "timeout")

    @pytest.mark.asyncio
    async def test_multiple_digits_accumulated(self, processor, callback):
        """Multiple digits accumulate before flush."""
        await processor.handle_tone("1")
        await processor.handle_tone("2")
        await processor.handle_tone("3")
        
        # Not flushed yet
        assert callback.call_count == 0
        
        # Wait for flush
        await asyncio.sleep(0.1)
        
        callback.assert_called_once_with("123", "timeout")

    @pytest.mark.asyncio
    async def test_terminator_key_immediate_flush(self, processor, callback):
        """# key immediately flushes the buffer."""
        await processor.handle_tone("4")
        await processor.handle_tone("5")
        await processor.handle_tone("#")
        
        # Should flush immediately without waiting
        callback.assert_called_once_with("45", "terminator")

    @pytest.mark.asyncio
    async def test_cancel_key_clears_buffer(self, processor, callback):
        """* key clears buffer without flushing."""
        await processor.handle_tone("7")
        await processor.handle_tone("8")
        await processor.handle_tone("*")
        
        # Wait past flush timeout
        await asyncio.sleep(0.1)
        
        # Callback should never be called
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_buffer_no_callback(self, processor, callback):
        """Empty buffer doesn't trigger callback."""
        await processor.handle_tone("#")
        
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_tone_ignored(self, processor, callback):
        """Invalid tones are ignored."""
        await processor.handle_tone("1")
        await processor.handle_tone("invalid")
        await processor.handle_tone("2")
        await processor.handle_tone("#")
        
        callback.assert_called_once_with("12", "terminator")

    @pytest.mark.asyncio
    async def test_cleanup_cancels_pending_flush(self, processor, callback):
        """Cleanup cancels pending flush task."""
        await processor.handle_tone("9")
        
        # Cleanup immediately
        await processor.cleanup()
        
        # Wait past flush time
        await asyncio.sleep(0.1)
        
        # Should not flush after cleanup
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_now_manual(self, processor, callback):
        """Manual flush_now works."""
        await processor.handle_tone("3")
        await processor.handle_tone("2")
        await processor.handle_tone("1")
        
        await processor.flush_now(reason="manual")
        
        callback.assert_called_once_with("321", "manual")

    @pytest.mark.asyncio
    async def test_buffer_length_property(self, processor, callback):
        """buffer_length reflects current state."""
        assert processor.buffer_length == 0
        
        await processor.handle_tone("1")
        assert processor.buffer_length == 1
        
        await processor.handle_tone("2")
        assert processor.buffer_length == 2
        
        await processor.handle_tone("#")
        assert processor.buffer_length == 0

    @pytest.mark.asyncio
    async def test_callback_exception_logged(self, processor, callback):
        """Exception in callback is caught and logged."""
        callback.side_effect = ValueError("Test error")
        
        await processor.handle_tone("1")
        await processor.handle_tone("#")
        
        # Should not raise
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_word_forms_work(self, processor, callback):
        """Word forms like 'one', 'two' work correctly."""
        await processor.handle_tone("one")
        await processor.handle_tone("two")
        await processor.handle_tone("three")
        await processor.handle_tone("hash")  # "#" word form
        
        callback.assert_called_once_with("123", "terminator")

    @pytest.mark.asyncio
    async def test_clear_after_partial_input(self, processor, callback):
        """Clear works after partial input."""
        await processor.handle_tone("5")
        await processor.handle_tone("5")
        await processor.handle_tone("5")
        
        await processor.clear()
        
        # New sequence
        await processor.handle_tone("1")
        await processor.handle_tone("#")
        
        callback.assert_called_once_with("1", "terminator")

    @pytest.mark.asyncio
    async def test_session_id_accessible(self, processor):
        """session_id property is accessible."""
        assert processor.session_id == "test-session"
