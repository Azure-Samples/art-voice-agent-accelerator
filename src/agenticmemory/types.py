"""
Memory types for real-time voice agent applications.

This module defines a small, composable memory layer for real‑time voice‑agent
applications. It exposes four public classes:

1. **CoreMemory** – A type‑safe, lightweight key‑value store for shared state.
2. **ChatHistory** – An ordered list of user/assistant messages (single thread).
                        a TTS playback queue, latency tracking, and live-refresh utilities.
3. **EphemeralMemoManager** – An in‑memory variant of MemoManager for App‑layer
                              components that *must not* persist to Redis.
"""

import json
from typing import Any, Dict, List, Optional

from utils.ml_logging import get_logger

logger = get_logger("agenticmemory.types")


class MemoryError(RuntimeError):
    """Raised when persistence or retrieval of memory fails."""


class CoreMemory:
    """A lightweight, type-safe key-value store.

    This class is intentionally minimal. All mutating operations are logged so
    that external observers (e.g. dashboards) can replay state transitions.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        logger.debug("CoreMemory initialised with empty store.")

    def set(self, key: str, value: Any) -> None:  # noqa: D401, PLR0913
        """Insert or update a value.

        Args:
            key: The dictionary key.
            value: The value to store.
        """
        self._store[key] = value
        logger.debug("CoreMemory.set – key=%s, value=%r", key, value)

    def get(self, key: str, default: Any | None = None) -> Any:
        """Retrieve a value.

        Args:
            key: The dictionary key.
            default: Value returned if *key* is missing.

        Returns:
            The stored value or *default*.
        """
        value = self._store.get(key, default)
        logger.debug("CoreMemory.get – key=%s, value=%r", key, value)
        return value

    def update(self, updates: Dict[str, Any]) -> None:
        """Bulk-update the store.

        Args:
            updates: Dictionary containing updates.
        """
        self._store.update(updates)
        logger.debug("CoreMemory.update – %d keys", len(updates))

    def to_json(self) -> str:
        """Serialise to JSON."""
        json_str = json.dumps(self._store, ensure_ascii=False)
        logger.debug("CoreMemory.to_json – %d bytes", len(json_str))
        return json_str

    def from_json(self, json_str: str) -> None:
        """Load state from JSON.

        Args:
            json_str: JSON string produced by :py:meth:`to_json`.
        """
        self._store = json.loads(json_str)
        logger.debug("CoreMemory.from_json – loaded %d keys", len(self._store))

    def __repr__(self) -> str:  # noqa: D401
        return f"CoreMemory(keys={len(self._store)})"


class ChatHistory:
    """Ordered, append‑only list of chat messages *per agent*.

    Backwards compatibility:
    * ``append(role, content)`` – writes to *default* agent thread.
    * ``get_all()`` – returns the entire ``dict(agent → turns)``.
    """

    def __init__(self) -> None:  # noqa: D401
        self._threads: Dict[str, List[Dict[str, str]]] = {}
        logger.debug("ChatHistory initialised with empty mapping.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def append(self, role: str, content: str, agent: str = "default") -> None:
        """Append a message to *agent*'s timeline."""
        self._threads.setdefault(agent, []).append({"role": role, "content": content})
        logger.debug(
            "ChatHistory.append – agent=%s, role=%s, len=%d",
            agent,
            role,
            len(self._threads[agent]),
        )

    def get_agent(self, agent: str = "default") -> List[Dict[str, str]]:  # noqa: D401
        """Return the turn list for *agent* (creates if missing)."""
        return self._threads.setdefault(agent, [])

    def get_all(self) -> Dict[str, List[Dict[str, str]]]:  # noqa: D401
        """Return the full mapping *shallow* copy."""
        return dict(self._threads)

    def clear(self, agent: Optional[str] = None) -> None:  # noqa: D401
        """Reset history – either all agents or a single thread."""
        if agent is None:
            self._threads.clear()
            logger.debug("ChatHistory.clear – all agents cleared")
        else:
            self._threads[agent] = []
            logger.debug("ChatHistory.clear – agent=%s", agent)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def to_json(self) -> str:  # noqa: D401
        blob = json.dumps(self._threads, ensure_ascii=False)
        logger.debug("ChatHistory.to_json – %d bytes", len(blob))
        return blob

    def from_json(self, json_str: str) -> None:  # noqa: D401
        data = json.loads(json_str)
        # Auto‑migrate legacy list payloads to {"default": [...]}
        if isinstance(data, list):
            self._threads = {"default": data}
        elif isinstance(data, dict):
            self._threads = data
        else:  # pragma: no cover – corrupt data
            raise ValueError("ChatHistory JSON must be list or dict")
        logger.debug(
            "ChatHistory.from_json – %d agents, %d total msgs",
            len(self._threads),
            sum(len(t) for t in self._threads.values()),
        )

    def __repr__(self) -> str:  # noqa: D401
        total = sum(len(t) for t in self._threads.values())
        return f"ChatHistory(agents={len(self._threads)}, messages={total})"


# TODO: Implement EphemeralMemoManager
# class EphemeralMemoManager():
