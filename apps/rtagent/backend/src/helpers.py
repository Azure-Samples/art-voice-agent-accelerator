"""
helpers.py
===========

Utility helpers shared by the browser_RTAgent backend and the new
modular routers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import WebSocket

from config import STOP_WORDS
from utils.ml_logging import get_logger
import time
from collections import deque
from statistics import quantiles

logger = get_logger("helpers")

# Simple performance tracking for WebSocket operations
class SimplePerformanceTracker:
    def __init__(self, max_samples=100):
        self.samples = deque(maxlen=max_samples)
        self.p95_threshold = None
    
    def add_sample(self, duration_ms):
        self.samples.append(duration_ms)
        if len(self.samples) >= 20:  # Recalculate P95 when we have enough samples
            try:
                p95_values = quantiles(self.samples, n=20)
                self.p95_threshold = p95_values[18]  # 95th percentile
            except:
                self.p95_threshold = None
    
    def is_slow(self, duration_ms):
        return self.p95_threshold and duration_ms > self.p95_threshold

# Global performance tracker for WebSocket receives
ws_perf_tracker = SimplePerformanceTracker()


def check_for_stopwords(prompt: str) -> bool:
    """
    Check if the provided message contains any predefined exit keywords.

    This function examines the input prompt for the presence of stop words
    that indicate the user wants to end the conversation or exit the application.
    The comparison is case-insensitive for better user experience.

    :param prompt: The user input message to analyze for stop words.
    :return: True if any stop word is found in the prompt, False otherwise.
    :raises TypeError: If prompt is not a string.
    """
    if not isinstance(prompt, str):
        logger.error(f"Expected string prompt, got {type(prompt)}")
        raise TypeError("Prompt must be a string")

    try:
        result = any(stop in prompt.lower() for stop in STOP_WORDS)
        if result:
            logger.info(f"Stop word detected in prompt: {prompt[:50]}...")
        return result
    except Exception as e:
        logger.error(f"Error checking for stop words: {e}")
        raise


def check_for_interrupt(prompt: str) -> bool:
    """
    Determine if the provided message is an interrupt control frame.

    This function checks whether the input contains interrupt signals that
    should pause or stop ongoing operations such as TTS playback or audio
    processing. Used for real-time conversation flow control.

    :param prompt: The message text to examine for interrupt indicators.
    :return: True if the message contains interrupt signals, False otherwise.
    :raises TypeError: If prompt is not a string.
    """
    if not isinstance(prompt, str):
        logger.error(f"Expected string prompt, got {type(prompt)}")
        raise TypeError("Prompt must be a string")

    try:
        result = "interrupt" in prompt.lower()
        if result:
            logger.info("Interrupt signal detected in prompt")
        return result
    except Exception as e:
        logger.error(f"Error checking for interrupt: {e}")
        raise


def add_space(text: str) -> str:
    """
    Ensure the text chunk ends with appropriate whitespace for proper concatenation.

    This function prevents text fragments from being incorrectly joined together
    during streaming operations. It adds a single space if the text doesn't end
    with whitespace, preventing issues like "assistance.Could" appearing in output.

    :param text: The text string to process for proper spacing.
    :return: The text with guaranteed trailing space or the original text if already spaced.
    :raises TypeError: If text is not a string.
    """
    if not isinstance(text, str):
        logger.error(f"Expected string text, got {type(text)}")
        raise TypeError("Text must be a string")

    try:
        if text and text[-1] not in [" ", "\n"]:
            return text + " "
        return text
    except Exception as e:
        logger.error(f"Error adding space to text: {e}")
        raise


async def receive_and_filter(ws: WebSocket) -> Optional[str]:
    """
    Receive and process a single WebSocket frame with interrupt handling.

    This function reads one frame from the WebSocket connection and processes it
    according to the message type. It handles both plain text messages and JSON
    messages with special processing for interrupt signals that control TTS playback.

    :param ws: The active WebSocket connection to read from.
    :return: The processed message text, or None if an interrupt was received.
    :raises WebSocketError: If there are issues reading from the WebSocket.
    :raises JSONDecodeError: If JSON parsing fails for structured messages.
    """
    start_time = time.perf_counter()
    
    try:
        raw: str = await ws.receive_text()
        
        # Calculate duration and track performance
        duration_ms = (time.perf_counter() - start_time) * 1000
        ws_perf_tracker.add_sample(duration_ms)
        
        # Only log if it's slow (above P95) or if there's an error
        if ws_perf_tracker.is_slow(duration_ms):
            logger.warning(f"⚠️ SLOW WebSocket receive: {duration_ms:.2f}ms (P95: {ws_perf_tracker.p95_threshold:.2f}ms)")

        try:
            msg: Dict[str, Any] = json.loads(raw)
            if msg.get("type") == "interrupt":
                logger.info("🛑 interrupt received – stopping TTS playback")
                # Stop per-connection TTS synthesizer if available
                if hasattr(ws.state, "tts_client") and ws.state.tts_client:
                    ws.state.tts_client.stop_speaking()
                return None
            return msg.get("text", raw)
        except json.JSONDecodeError:
            # Only log JSON decode issues if it's a slow operation
            if ws_perf_tracker.is_slow(duration_ms):
                logger.debug(f"Received plain text message (not JSON) - took {duration_ms:.2f}ms")
            return raw.strip()

    except Exception as e:
        # Always log errors with duration
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"Error receiving and filtering WebSocket message (took {duration_ms:.2f}ms): {e}")
        raise
