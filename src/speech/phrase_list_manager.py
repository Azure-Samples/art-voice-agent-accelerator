"""Runtime phrase-bias manager for speech recognition."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable

from utils.ml_logging import get_logger

logger = get_logger(__name__)

DEFAULT_PHRASE_LIST_ENV = "SPEECH_RECOGNIZER_DEFAULT_PHRASES"


def parse_phrase_entries(source: Iterable[str] | str) -> set[str]:
    """Normalize phrases into a trimmed, de-duplicated set."""

    if isinstance(source, str):
        candidates = source.split(",")
    else:
        candidates = list(source)

    normalized = {
        (candidate or "").strip() for candidate in candidates if candidate and candidate.strip()
    }
    return normalized


def load_default_phrases_from_env() -> set[str]:
    """Load and normalize phrase entries from the default environment variable."""

    raw_values = os.getenv(DEFAULT_PHRASE_LIST_ENV, "")
    phrases = parse_phrase_entries(raw_values)
    if phrases:
        logger.debug("Loaded %s phrases from %s", len(phrases), DEFAULT_PHRASE_LIST_ENV)
    return phrases


_GLOBAL_MANAGER: PhraseListManager | None = None


class PhraseListManager:
    """Manage phrase bias entries shared across recognizer instances."""

    def __init__(self, *, initial_phrases: Iterable[str] | None = None) -> None:
        self._lock = asyncio.Lock()
        self._phrases: set[str] = set()
        if initial_phrases:
            self._phrases.update(parse_phrase_entries(initial_phrases))

    async def add_phrase(self, phrase: str) -> bool:
        """Add a single phrase if it is new."""

        normalized = (phrase or "").strip()
        if not normalized:
            return False

        async with self._lock:
            if normalized in self._phrases:
                return False
            self._phrases.add(normalized)
            logger.debug("Phrase bias entry added", extra={"phrase": normalized})
            return True

    async def add_phrases(self, phrases: Iterable[str]) -> int:
        """Add multiple phrases, returning the number of new entries."""

        normalized = parse_phrase_entries(list(phrases))
        if not normalized:
            return 0

        async with self._lock:
            before = len(self._phrases)
            self._phrases.update(normalized)
            added = len(self._phrases) - before
            if added:
                logger.debug("Added %s phrase bias entries", added)
            return added

    async def snapshot(self) -> list[str]:
        """Return a sorted snapshot of current phrases."""

        async with self._lock:
            return sorted(self._phrases)

    async def contains(self, phrase: str) -> bool:
        """Check if a phrase is already tracked."""

        normalized = (phrase or "").strip()
        if not normalized:
            return False
        async with self._lock:
            return normalized in self._phrases


def set_global_phrase_manager(manager: PhraseListManager | None) -> None:
    """Register a process-wide phrase list manager instance for reuse."""

    global _GLOBAL_MANAGER
    _GLOBAL_MANAGER = manager


def get_global_phrase_manager() -> PhraseListManager:
    """Return the shared phrase list manager, creating one if needed."""

    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = PhraseListManager(initial_phrases=load_default_phrases_from_env())
    return _GLOBAL_MANAGER


async def get_global_phrase_snapshot() -> list[str]:
    """Convenience helper to return the current global phrase snapshot."""

    manager = get_global_phrase_manager()
    return await manager.snapshot()
