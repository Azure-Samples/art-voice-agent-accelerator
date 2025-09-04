from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any, Dict, Optional

import websocket  # websocket-client
from utils.ml_logging import get_logger

logger = get_logger(__name__)


class WebSocketTransport:
    """
    Thin, production-safe wrapper around websocket-client's WebSocketApp.

    Designed for low-latency, duplex streaming with a background receiver thread.
    Messages are placed on an internal queue for the caller to drain.

    Usage:
        ws = WebSocketTransport(url, headers)
        ws.connect()
        ws.send_dict({"type": "session.update", "session": {...}})
        msg = ws.recv(timeout_s=0.01)
        ws.close()

    :param url: Fully-qualified WS(S) URL.
    :param headers: HTTP headers to include during the WebSocket upgrade.
    :param ping_interval_s: Interval for automatic pings to keep the socket alive.
    :param ping_timeout_s: Timeout before considering a ping failed.
    :param max_queue: Max number of inbound messages to buffer.
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        *,
        ping_interval_s: float = 20.0,
        ping_timeout_s: float = 10.0,
        max_queue: int = 2000,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._ping_interval_s = ping_interval_s
        self._ping_timeout_s = ping_timeout_s
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=max_queue)
        self._connected = threading.Event()
        self._closed = threading.Event()
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[str] = None

    # --------------------------------------------------------------------- #
    # Lifecycle
    # --------------------------------------------------------------------- #
    def connect(self, timeout_s: float = 10.0) -> None:
        """
        Establish the WebSocket connection and start the background receiver.

        :param timeout_s: Time to wait for the connection to open.
        :raises ConnectionError: If the socket doesn't open within the timeout.
        """
        if self._thread and self._thread.is_alive():
            logger.warning("WebSocket already connected; ignoring connect().")
            return

        def _on_open(_: websocket.WebSocketApp) -> None:
            logger.info("WebSocket opened.")
            self._connected.set()

        def _on_message(_: websocket.WebSocketApp, message: str) -> None:
            try:
                self._queue.put_nowait(message)
            except queue.Full:
                # Drop oldest to favor fresh, low-latency traffic
                try:
                    _ = self._queue.get_nowait()
                    self._queue.put_nowait(message)
                    logger.warning("Inbound queue full; dropped oldest message.")
                except queue.Empty:
                    logger.error("Inbound queue unexpectedly empty while full.")
            except Exception:  # noqa: BLE001
                logger.exception("Failed to enqueue inbound message.")

        def _on_error(_: websocket.WebSocketApp, error: Any) -> None:
            self._last_error = str(error)
            logger.error("WebSocket error: %s", self._last_error)

        def _on_close(_: websocket.WebSocketApp, status_code: Any, msg: Any) -> None:
            logger.info("WebSocket closed: code=%s, msg=%s", status_code, msg)
            self._closed.set()
            self._connected.clear()

        headers = [f"{k}: {v}" for k, v in self._headers.items()]
        self._ws = websocket.WebSocketApp(
            self._url,
            header=headers,
            on_open=_on_open,
            on_message=_on_message,
            on_error=_on_error,
            on_close=_on_close,
        )

        def _runner() -> None:
            try:
                self._ws.run_forever(  # type: ignore[union-attr]
                    ping_interval=self._ping_interval_s,
                    ping_timeout=self._ping_timeout_s,
                    ping_payload=str(uuid.uuid4()),
                    origin=None,
                )
            except Exception:  # noqa: BLE001
                logger.exception("WebSocket run_forever crashed.")
            finally:
                self._closed.set()
                self._connected.clear()

        self._thread = threading.Thread(
            target=_runner, name=f"ws-{uuid.uuid4().hex[:8]}", daemon=True
        )
        self._thread.start()

        # Wait for open or timeout
        start = time.time()
        while not self._connected.is_set() and time.time() - start < timeout_s:
            time.sleep(0.01)

        if not self._connected.is_set():
            self.close()
            raise ConnectionError(
                f"WebSocket did not open within {timeout_s:.1f}s (last_error={self._last_error})"
            )

    def close(self) -> None:
        """
        Close the WebSocket and stop the background thread gracefully.
        """
        try:
            if self._ws:
                self._ws.close()  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.exception("Error while closing WebSocket.")
        finally:
            self._connected.clear()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3.0)
                if self._thread.is_alive():
                    logger.warning("WebSocket thread did not stop within 3s.")

    # --------------------------------------------------------------------- #
    # I/O
    # --------------------------------------------------------------------- #
    def send_text(self, data: str) -> None:
        """
        Send a raw text frame.

        :param data: Text payload to send.
        :raises RuntimeError: If the socket is not connected.
        """
        if not self._connected.is_set() or not self._ws:
            raise RuntimeError("WebSocket is not connected.")
        try:
            self._ws.send(data)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send text frame.")

    def send_dict(self, payload: Dict[str, Any]) -> None:
        """
        Serialize a dict to JSON and send as a text frame.

        :param payload: Dict payload to JSON-encode and send.
        """
        try:
            data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to serialize payload to JSON.")
            return
        self.send_text(data)

    def recv(self, *, timeout_s: float = 0.0) -> Optional[str]:
        """
        Receive the next message from the inbound queue.

        :param timeout_s: Max time to wait for a message.
        :return: Raw JSON string if available; otherwise None.
        """
        try:
            return self._queue.get(timeout=timeout_s) if timeout_s > 0 else self._queue.get_nowait()
        except queue.Empty:
            return None

    # --------------------------------------------------------------------- #
    # Introspection
    # --------------------------------------------------------------------- #
    @property
    def is_connected(self) -> bool:
        """True if the socket is currently open."""
        return self._connected.is_set()
