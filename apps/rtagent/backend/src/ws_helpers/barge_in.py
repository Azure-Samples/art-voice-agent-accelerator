from __future__ import annotations

import asyncio
import time
from asyncio import run_coroutine_threadsafe
from typing import Callable, Optional

from fastapi import WebSocket

from apps.rtagent.backend.src.ws_helpers.shared_ws import send_session_envelope
from utils.ml_logging import get_logger

logger = get_logger("ws_helpers.barge_in")


class BargeInController:
    """Coordinates barge-in cancellation across TTS and orchestration."""

    def __init__(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        conn_id: str,
        get_metadata: Callable[[str, Optional[object]], object],
        set_metadata: Callable[[str, object], None],
        signal_tts_cancel: Callable[[], None],
        logger=logger,
    ) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.conn_id = conn_id
        self.get_metadata = get_metadata
        self.set_metadata = set_metadata
        self.signal_tts_cancel = signal_tts_cancel
        self.logger = logger
        self._loop = getattr(websocket.state, "_loop", None)

    async def _perform(
        self,
        trigger: str,
        stage: str,
        *,
        energy_level: float | None = None,
    ) -> None:
        is_synthesizing = self.get_metadata("is_synthesizing", False)
        audio_playing = self.get_metadata("audio_playing", False)
        cancel_requested = self.get_metadata("tts_cancel_requested", False)

        if not (is_synthesizing or audio_playing or cancel_requested):
            return

        if self.get_metadata("barge_in_inflight", False):
            return

        self.set_metadata("barge_in_inflight", True)
        now = time.monotonic()


        try:
            last_trigger = self.get_metadata("last_barge_in_trigger", None)
            last_ts = self.get_metadata("last_barge_in_ts", 0.0) or 0.0
            if last_trigger == trigger and (now - last_ts) < 0.05:
                return

            self.set_metadata("last_barge_in_ts", now)
            self.set_metadata("last_barge_in_trigger", trigger)
            self.set_metadata("is_synthesizing", False)
            self.set_metadata("audio_playing", False)
            self.set_metadata("tts_cancel_requested", True)

            self.logger.info(
                "[%s] Barge-in triggered (trigger=%s, stage=%s, energy=%.2f, was_syn=%s, was_playing=%s)",
                self.session_id,
                trigger,
                stage,
                energy_level or 0.0,
                is_synthesizing,
                audio_playing,
            )

            tts_client = self.get_metadata("tts_client")
            if tts_client:
                try:
                    tts_client.stop_speaking()
                except Exception as stop_exc:  # noqa: BLE001
                    self.logger.debug(
                        "[%s] TTS stop_speaking error during barge-in: %s",
                        self.session_id,
                        stop_exc,
                    )

            self.signal_tts_cancel()

            tasks = getattr(self.websocket.state, "orchestration_tasks", set())
            active_tasks = [task for task in list(tasks) if task and not task.done()]
            if active_tasks:
                self.logger.info(
                    "[%s] Cancelling %s orchestration task(s) due to barge-in",
                    self.session_id,
                    len(active_tasks),
                )
                for task in active_tasks:
                    task.cancel()
                for task in active_tasks:
                    try:
                        await asyncio.wait_for(task, timeout=0.3)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                    except Exception as cancel_exc:  # noqa: BLE001
                        self.logger.debug(
                            "[%s] Orchestration cancel error during barge-in: %s",
                            self.session_id,
                            cancel_exc,
                        )
                    finally:
                        tasks.discard(task)

            cancel_msg = {
                "type": "control",
                "action": "tts_cancelled",
                "reason": "barge_in",
                "trigger": trigger,
                "at": stage,
                "session_id": self.session_id,
            }
            if energy_level is not None:
                cancel_msg["energy"] = round(float(energy_level), 2)

            stop_audio_msg = {
                "type": "control",
                "action": "audio_stop",
                "reason": "barge_in",
                "trigger": trigger,
                "at": stage,
                "session_id": self.session_id,
            }

            try:
                await send_session_envelope(
                    self.websocket,
                    cancel_msg,
                    session_id=self.session_id,
                    conn_id=self.conn_id,
                    event_label="barge_in_cancel",
                )
                await send_session_envelope(
                    self.websocket,
                    stop_audio_msg,
                    session_id=self.session_id,
                    conn_id=self.conn_id,
                    event_label="barge_in_audio_stop",
                )
            except Exception as send_exc:  # noqa: BLE001
                self.logger.debug(
                    "[%s] Failed to dispatch barge-in control message: %s",
                    self.session_id,
                    send_exc,
                )

        finally:
            self.set_metadata("barge_in_inflight", False)

    def request(
        self,
        trigger: str,
        stage: str,
        *,
        energy_level: float | None = None,
    ) -> None:
        coroutine = self._perform(trigger, stage, energy_level=energy_level)
        if self._loop and self._loop.is_running():
            try:
                run_coroutine_threadsafe(coroutine, self._loop)
            except Exception as exc:  # noqa: BLE001
                self.logger.debug(
                    "[%s] Failed to schedule barge-in coroutine on loop: %s",
                    self.session_id,
                    exc,
                )
        else:
            try:
                asyncio.create_task(coroutine)
            except RuntimeError as exc:
                self.logger.warning(
                    "[%s] Unable to schedule barge-in coroutine: %s",
                    self.session_id,
                    exc,
                )
