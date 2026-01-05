"""
DTMF Processor
==============

Handles DTMF (Dual-Tone Multi-Frequency) tone detection, buffering, and processing.

Features:
- Tone normalization (handles various input formats)
- Buffer management with configurable flush delay
- Special key handling (# for submit, * for clear)
- Thread-safe async operations

Extracted from VoiceLiveSDKHandler to reduce handler complexity.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from utils.ml_logging import get_logger

logger = get_logger("voicelive.dtmf")

# Default delay before auto-flushing DTMF buffer (seconds)
DEFAULT_FLUSH_DELAY_SECONDS = 1.5

# Tone normalization map - handles various input formats
_TONE_MAP = {
    "0": "0", "zero": "0",
    "1": "1", "one": "1",
    "2": "2", "two": "2",
    "3": "3", "three": "3",
    "4": "4", "four": "4",
    "5": "5", "five": "5",
    "6": "6", "six": "6",
    "7": "7", "seven": "7",
    "8": "8", "eight": "8",
    "9": "9", "nine": "9",
    "*": "*", "star": "*", "asterisk": "*",
    "#": "#", "pound": "#", "hash": "#",
}


def normalize_dtmf_tone(raw_tone: Any) -> str | None:
    """
    Normalize a DTMF tone from various input formats.
    
    Args:
        raw_tone: Raw tone value (could be int, string, or word form)
        
    Returns:
        Normalized single character (0-9, *, #) or None if invalid
    """
    if raw_tone is None:
        return None
    tone = str(raw_tone).strip().lower()
    return _TONE_MAP.get(tone)


class DTMFProcessor:
    """
    Manages DTMF tone buffering and processing.
    
    Collects DTMF digits into a buffer and flushes them:
    - On timeout (configurable delay after last digit)
    - On # (terminator key)
    - Clears buffer on * (cancel key)
    
    Usage:
        processor = DTMFProcessor(
            session_id="session-123",
            on_sequence=lambda seq, reason: send_to_llm(seq),
            flush_delay=1.5,
        )
        
        # In event handler:
        await processor.handle_tone(raw_tone)
        
        # On cleanup:
        await processor.cleanup()
    """
    
    def __init__(
        self,
        *,
        session_id: str,
        on_sequence: Callable[[str, str], Awaitable[None]],
        flush_delay: float = DEFAULT_FLUSH_DELAY_SECONDS,
    ) -> None:
        """
        Initialize the DTMF processor.
        
        Args:
            session_id: Session identifier for logging
            on_sequence: Async callback when a complete sequence is ready.
                         Called with (sequence: str, reason: str).
                         Reason is "timeout" or "terminator".
            flush_delay: Seconds to wait before auto-flushing buffer
        """
        self._session_id = session_id
        self._on_sequence = on_sequence
        self._flush_delay = flush_delay
        
        self._digits: list[str] = []
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
    
    @property
    def session_id(self) -> str:
        return self._session_id
    
    @property
    def buffer_length(self) -> int:
        """Current number of digits in buffer (not thread-safe for display only)."""
        return len(self._digits)
    
    async def handle_tone(self, raw_tone: Any) -> None:
        """
        Process an incoming DTMF tone.
        
        Args:
            raw_tone: Raw tone value from ACS or other source
        """
        normalized = normalize_dtmf_tone(raw_tone)
        if not normalized:
            logger.debug(
                "Ignoring invalid DTMF tone %s | session=%s",
                raw_tone, self._session_id
            )
            return
        
        # # = Submit/flush the current buffer
        if normalized == "#":
            self._cancel_flush_timer()
            await self._flush_buffer(reason="terminator")
            return
        
        # * = Clear/cancel the current buffer
        if normalized == "*":
            await self.clear()
            return
        
        # Regular digit - add to buffer
        async with self._lock:
            self._digits.append(normalized)
            buffer_len = len(self._digits)
        
        logger.info(
            "Received DTMF tone %s (buffer_len=%s) | session=%s",
            normalized, buffer_len, self._session_id
        )
        
        # Schedule auto-flush after delay
        self._schedule_flush()
    
    async def clear(self) -> None:
        """Clear the buffer without flushing (e.g., user pressed *)."""
        self._cancel_flush_timer()
        async with self._lock:
            if self._digits:
                logger.info(
                    "Clearing DTMF buffer without forwarding (buffer_len=%s) | session=%s",
                    len(self._digits), self._session_id
                )
            self._digits.clear()
    
    async def flush_now(self, *, reason: str = "manual") -> None:
        """Force immediate flush of the buffer."""
        self._cancel_flush_timer()
        await self._flush_buffer(reason=reason)
    
    async def cleanup(self) -> None:
        """Clean up resources (call on session end)."""
        self._cancel_flush_timer()
        # Wait for any pending flush task to complete
        if self._flush_task:
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            self._digits.clear()
    
    def _schedule_flush(self) -> None:
        """Schedule a delayed flush of the buffer."""
        self._cancel_flush_timer()
        self._flush_task = asyncio.create_task(self._delayed_flush())
    
    def _cancel_flush_timer(self) -> None:
        """Cancel any pending flush task."""
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
    
    async def _delayed_flush(self) -> None:
        """Wait for delay then flush buffer."""
        try:
            await asyncio.sleep(self._flush_delay)
            await self._flush_buffer(reason="timeout")
        except asyncio.CancelledError:
            return
        finally:
            self._flush_task = None
    
    async def _flush_buffer(self, *, reason: str) -> None:
        """Flush the buffer and invoke callback with the sequence."""
        async with self._lock:
            if not self._digits:
                return
            sequence = "".join(self._digits)
            self._digits.clear()
        
        logger.info(
            "Flushing DTMF sequence (%s digits) via %s | session=%s",
            len(sequence), reason, self._session_id
        )
        
        try:
            await self._on_sequence(sequence, reason)
        except Exception:
            logger.exception(
                "DTMF sequence callback failed | session=%s sequence=%s",
                self._session_id, sequence
            )
