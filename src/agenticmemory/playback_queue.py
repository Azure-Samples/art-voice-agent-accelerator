import asyncio
from collections import deque
from typing import Any, Deque, Dict, Optional

from utils.ml_logging import get_logger

logger = get_logger("orchestration.playback_messages_tts")


class MessageQueue:
    """
    Handles sequential playback message queue for TTS responses.
    """

    def __init__(self) -> None:
        """
        Initialize an empty message queue with a lock for thread safety, and booleans
        for tracking if the queue is currently being processed and if media playback has
        been cancelled.
        """
        self.queue: Deque[Dict[str, Any]] = deque()
        self.lock = asyncio.Lock()
        self.is_processing: bool = False
        self.media_cancelled: bool = False

    async def enqueue(self, message: Dict[str, Any]) -> None:
        """
        Enqueue a message for sequential playback.

        Args:
            message (Dict[str, Any]): The message data to enqueue.

        Returns:
            None
        """
        async with self.lock:
            self.queue.append(message)
            logger.info(f"📝 Enqueued message. Queue size: {len(self.queue)}")

    async def dequeue(self) -> Optional[Dict[str, Any]]:
        """
        Dequeue the next message for playback.

        Returns:
            Optional[Dict[str, Any]]: The dequeued message data, or None if the queue is empty.
        """
        async with self.lock:
            if self.queue:
                return self.queue.popleft()
            return None

    async def clear(self) -> None:
        """
        Clear all messages from the queue.

        Returns:
            None
        """
        async with self.lock:
            self.queue.clear()
            logger.info("🗑️ Cleared message queue.")

    def size(self) -> int:
        """
        Get the number of messages currently in the queue.

        Returns:
            int: The number of messages in the queue.
        """
        return len(self.queue)

    async def set_processing(self, is_processing: bool) -> None:
        """
        Set the queue processing status.

        Args:
            is_processing (bool): True if queue is being processed, else False.

        Returns:
            None
        """
        async with self.lock:
            self.is_processing = is_processing
            logger.debug(f"🔄 Queue processing status: {is_processing}")

    def is_processing_queue(self) -> bool:
        """
        Check if the queue is currently being processed.

        Returns:
            bool: True if processing, else False.
        """
        return self.is_processing

    async def set_media_cancelled(self, cancelled: bool) -> None:
        """
        Set the media cancellation flag.

        Args:
            cancelled (bool): True if media playback was cancelled.

        Returns:
            None
        """
        async with self.lock:
            self.media_cancelled = cancelled
            logger.debug(f"📵 Media cancellation flag: {cancelled}")

    def is_media_cancelled(self) -> bool:
        """
        Check if media playback was cancelled due to interrupt.

        Returns:
            bool: True if cancelled, else False.
        """
        return self.media_cancelled

    async def reset_on_interrupt(self) -> None:
        """
        Reset the queue state when an interrupt is detected.

        Clears the queue, stops processing, and resets cancellation flag.

        Returns:
            None
        """
        async with self.lock:
            queue_size_before = len(self.queue)
            self.queue.clear()
            self.is_processing = False
            self.media_cancelled = False
            logger.info(
                f"🔄 Reset queue on interrupt. Cleared {queue_size_before} messages."
            )
