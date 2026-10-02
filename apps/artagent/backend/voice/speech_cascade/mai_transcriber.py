"""MAI input for Cascade; the local LLM and pooled Speech TTS stay in charge."""

from __future__ import annotations

import asyncio
import base64
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp
from apps.artagent.backend.registries.agentstore.base import (
    MAI_TRANSCRIPTION_MODELS,
    MAI_VOICELIVE_API_VERSION,
    SpeechConfig,
    normalize_transcription_model,
)
from apps.artagent.backend.voice.shared.close import cancel_and_join
from apps.artagent.backend.voice.shared.context import TransportType, VoiceSessionContext
from apps.artagent.backend.voice.shared.metrics_factory import LazyMeter, build_session_attributes
from apps.artagent.backend.voice.speech_cascade.handler import (
    SpeechEvent,
    SpeechEventType,
    ThreadBridge,
)
from apps.artagent.backend.voice.voicelive.settings import get_settings
from azure.ai.voicelive.aio import VoiceLiveConnection
from azure.ai.voicelive.models import (
    AudioInputTranscriptionOptions,
    AzureSemanticVadMultilingual,
    RequestSession,
    ServerVad,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError
from src.speech.phrase_list_manager import load_default_phrases_from_env
from utils.ml_logging import get_logger

logger = get_logger(__name__)
_meter = LazyMeter("voice.mai_transcription")
_startup_latency = _meter.histogram("voice.mai_transcription.startup", "MAI input startup", "ms")
_failures = _meter.counter("voice.mai_transcription.errors", "MAI input failures")

MAI_HOST_MODEL = "gpt-4.1"
START_TIMEOUT_S = 20.0
IO_TIMEOUT_S = 5.0
MAX_AUDIO_CHUNK_BYTES = 4800
MAX_PENDING_TURNS = 50
MAX_TRANSCRIPT_CHARS = 65536


class MAITranscriptionError(RuntimeError):
    """MAI input failed; this session must not substitute Azure Speech recognition."""


@dataclass
class _InputTurn:
    partial: str = ""
    sequence: int = 0
    start_ts: float | None = None
    final: SpeechEvent | None = None


class MAITranscriber:
    """Session-owned, bounded async MAI input connection for browser/ACS PCM16.

    Uses a managed text host with create_response=False, not a transcription-only
    intent or BYOM profile. This connection never requests responses or plays
    audio. Service errors terminate the input leg rather than selecting another STT.
    """

    def __init__(
        self,
        context: VoiceSessionContext,
        *,
        speech: SpeechConfig,
        speech_queue: asyncio.Queue,
        thread_bridge: ThreadBridge,
        barge_in_handler: Callable[[], Awaitable[None]],
        on_error: Callable[[str], Awaitable[None]],
        on_partial: Callable[[str, str, str | None, str, int], Awaitable[None]] | None = None,
        sample_rate: int | None = None,
    ) -> None:
        self.transcription_model = normalize_transcription_model(speech.transcription_model)
        if self.transcription_model not in MAI_TRANSCRIPTION_MODELS:
            raise ValueError(f"Unsupported MAI transcription model '{self.transcription_model}'.")
        if context.transport not in (TransportType.BROWSER, TransportType.ACS):
            raise ValueError("MAI Cascade input supports only browser and ACS transports.")
        if speech.enable_diarization:
            raise ValueError("MAI Cascade input does not support speech.enable_diarization.")
        if load_default_phrases_from_env():
            raise ValueError(
                f"{self.transcription_model} does not support SPEECH_RECOGNIZER_DEFAULT_PHRASES. "
                "Remove the Azure Speech phrase biases or select azure-speech."
            )
        self.context = context
        self.sample_rate = (
            sample_rate if sample_rate is not None else (24000 if context.is_browser else 16000)
        )
        if self.sample_rate not in (16000, 24000):
            raise ValueError("MAI input requires mono PCM16 at 16000 or 24000 Hz.")
        self._speech = speech
        self._speech_queue = speech_queue
        self._bridge = thread_bridge
        self._barge_in_handler = barge_in_handler
        self._on_error = on_error
        self._on_partial = on_partial
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        self._audio_lock = asyncio.Lock()
        self._turns: dict[str, _InputTurn] = {}
        self._turn_order: deque[str] = deque()
        self._finished_items: deque[str] = deque(maxlen=128)
        self._connection: VoiceLiveConnection | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[None] | None = None
        self._closed = False
        self._failure: MAITranscriptionError | None = None
        self._attributes = build_session_attributes(
            context.session_id, call_connection_id=context.call_connection_id
        )

    def _session(self) -> RequestSession:
        languages = list(
            dict.fromkeys(lang.split("-")[0] for lang in self._speech.candidate_languages)
        )
        transcription = AudioInputTranscriptionOptions(model=self.transcription_model)
        if len(languages) == 1:
            transcription.language = languages[0]
        elif languages:
            logger.warning(
                "[%s] MAI uses automatic language detection; the Azure Speech "
                "candidate_languages allowlist is not applied.",
                self.context.session_short,
            )
        vad_type = (
            AzureSemanticVadMultilingual if self._speech.use_semantic_segmentation else ServerVad
        )
        return RequestSession(
            modalities=["text"],
            input_audio_format="pcm16",
            input_audio_sampling_rate=self.sample_rate,
            input_audio_transcription=transcription,
            turn_detection=vad_type(
                create_response=False,
                silence_duration_ms=self._speech.vad_silence_timeout_ms,
            ),
        )

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[VoiceLiveConnection]:
        from apps.artagent.backend.voice.voicelive.handler import VoiceLiveSDKHandler

        settings = get_settings()
        endpoint = urlsplit(settings.azure_voicelive_endpoint)
        if endpoint.scheme not in ("https", "wss") or not endpoint.hostname:
            raise ValueError("MAI input requires an HTTPS/WSS Azure VoiceLive endpoint.")
        if endpoint.query or endpoint.fragment or endpoint.username or endpoint.password:
            raise ValueError(
                "MAI input requires a base VoiceLive endpoint without query parameters or credentials."
            )
        path = endpoint.path.rstrip("/")
        if not path.endswith("/voice-live/realtime"):
            path += "/voice-live/realtime"
        url = urlunsplit(
            (
                "wss",
                endpoint.netloc,
                path,
                urlencode({"api-version": MAI_VOICELIVE_API_VERSION, "model": MAI_HOST_MODEL}),
                "",
            )
        )
        credential = await VoiceLiveSDKHandler._build_credential(settings)
        if isinstance(credential, AzureKeyCredential):
            headers = {"api-key": credential.key}
        else:
            token = await credential.get_token("https://cognitiveservices.azure.com/.default")
            headers = {"Authorization": f"Bearer {token.token}"}

        # Own the HTTP session so a cancelled WebSocket handshake closes it too.
        # The installed SDK connect() only closes a failed handshake on ClientError.
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=START_TIMEOUT_S)
        ) as http:
            async with http.ws_connect(
                url,
                headers=headers,
                heartbeat=settings.ws_heartbeat,
                max_msg_size=settings.ws_max_msg_size,
                timeout=aiohttp.ClientWSTimeout(ws_close=IO_TIMEOUT_S),
            ) as websocket:
                yield VoiceLiveConnection(http, websocket)

    async def start(self) -> None:
        """Wait for an acknowledged MAI/no-response session before accepting audio."""
        if self._failure:
            raise self._failure
        if self._closed:
            raise MAITranscriptionError("MAI input has already been closed.")
        if self._task is None:
            self._ready = asyncio.get_running_loop().create_future()
            self._task = asyncio.create_task(
                self._run(), name=f"mai-input-{self.context.session_short}"
            )
        try:
            await asyncio.shield(self._ready)
        except (asyncio.CancelledError, MAITranscriptionError):
            await self.stop()
            raise

    async def _run(self) -> None:
        started = time.perf_counter()
        try:
            async with AsyncExitStack() as resources:
                async with asyncio.timeout(START_TIMEOUT_S):
                    connection = await resources.enter_async_context(self._connect())
                    self._connection = connection
                    await connection.session.update(session=self._session())
                    while True:
                        event = await connection.recv()
                        if event.get("type") == "session.updated":
                            self._check_session(event.get("session") or {})
                            break
                        await self._handle_event(event)
                self._ready.set_result(None)
                _startup_latency.record((time.perf_counter() - started) * 1000, self._attributes)
                sender = asyncio.create_task(self._send_audio(), name="mai-audio-send")
                receiver = asyncio.create_task(
                    self._receive_events(), name="mai-transcript-receive"
                )
                try:
                    done, _ = await asyncio.wait(
                        (sender, receiver), return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()
                    raise MAITranscriptionError("MAI input disconnected unexpectedly.")
                finally:
                    sender.cancel()
                    receiver.cancel()
                    await asyncio.gather(sender, receiver, return_exceptions=True)
        except asyncio.CancelledError:
            if not self._ready.done():
                self._ready.cancel()
            raise
        except (
            AzureError,
            aiohttp.ClientError,
            OSError,
            ValueError,
            TypeError,
            RuntimeError,
        ) as exc:
            detail = str(exc) or type(exc).__name__
            self._failure = MAITranscriptionError(
                f"MAI transcription unavailable ({self.transcription_model}): {detail}. "
                "Check VoiceLive endpoint, region/model availability and authentication. "
                "No other transcription model was substituted."
            )
            logger.error("[%s] %s", self.context.session_short, self._failure)
            _failures.add(1, self._attributes)
            if not self._ready.done():
                self._ready.set_exception(self._failure)
            else:
                await self._report_failure()
        finally:
            self._connection = None
            self._drain_audio()

    def _check_session(self, session: Mapping[str, Any]) -> None:
        if not isinstance(session, Mapping):
            raise MAITranscriptionError("VoiceLive returned an invalid session acknowledgement.")
        transcription = session.get("input_audio_transcription") or {}
        vad = session.get("turn_detection") or {}
        if (
            not isinstance(transcription, Mapping)
            or not isinstance(vad, Mapping)
            or transcription.get("model") != self.transcription_model
            or vad.get("create_response") is not False
            or session.get("input_audio_sampling_rate") != self.sample_rate
            or session.get("modalities") != ["text"]
        ):
            raise MAITranscriptionError(
                f"VoiceLive did not acknowledge {self.transcription_model}, create_response=False, "
                "text-only output and the requested PCM sampling rate."
            )

    async def send_audio(self, audio: bytes) -> None:
        """Feed ordered PCM16 with bounded backpressure; never silently drop audio."""
        if self._failure:
            raise self._failure
        if (
            self._closed
            or self._ready is None
            or not self._ready.done()
            or self._task is None
            or self._task.done()
        ):
            raise MAITranscriptionError("MAI input is not ready for audio.")
        self._ready.result()
        if len(audio) % 2:
            raise ValueError("MAI input requires complete PCM16 samples (an even byte count).")
        try:
            async with asyncio.timeout(IO_TIMEOUT_S):
                async with self._audio_lock:
                    for offset in range(0, len(audio), MAX_AUDIO_CHUNK_BYTES):
                        await self._audio_queue.put(audio[offset : offset + MAX_AUDIO_CHUNK_BYTES])
                        if self._failure or self._closed:
                            self._drain_audio()
                            raise self._failure or MAITranscriptionError(
                                "MAI input closed while queuing audio."
                            )
        except TimeoutError as exc:
            self._failure = MAITranscriptionError(
                "MAI audio queue stalled; the input connection was stopped instead of dropping audio."
            )
            await self.stop()
            await self._report_failure()
            raise self._failure from exc

    async def _send_audio(self) -> None:
        while True:
            audio = await self._audio_queue.get()
            try:
                await asyncio.wait_for(
                    self._connection.input_audio_buffer.append(
                        audio=base64.b64encode(audio).decode("ascii")
                    ),
                    timeout=IO_TIMEOUT_S,
                )
            except TimeoutError as exc:
                raise MAITranscriptionError("MAI audio upload stalled; input was stopped.") from exc
            finally:
                self._audio_queue.task_done()

    async def _receive_events(self) -> None:
        while True:
            # SDK recv() propagates disconnects; its async iterator swallows them.
            await self._handle_event(await self._connection.recv())

    def _turn(self, item_id: str) -> _InputTurn:
        if item_id not in self._turns:
            if len(self._turns) >= MAX_PENDING_TURNS:
                raise MAITranscriptionError("MAI exceeded the bounded pending transcription queue.")
            self._turns[item_id] = _InputTurn()
            self._turn_order.append(item_id)
        return self._turns[item_id]

    async def _handle_event(self, event: Mapping[str, Any]) -> None:
        event_type = event.get("type", "")
        if not isinstance(event_type, str):
            raise MAITranscriptionError("VoiceLive returned an invalid transcription event type.")
        if event_type in ("error", "conversation.item.input_audio_transcription.failed"):
            error = event.get("error") or {}
            if not isinstance(error, Mapping):
                raise MAITranscriptionError("VoiceLive returned an invalid transcription error.")
            raise MAITranscriptionError(
                f"{error.get('code', 'transcription_failed')}: "
                f"{error.get('message', 'VoiceLive transcription failed')}"
            )
        if event_type.startswith("response."):
            raise MAITranscriptionError(
                "VoiceLive generated a response on an input-only connection."
            )
        if event_type == "session.updated":
            self._check_session(event.get("session") or {})
            return
        tracked = {
            "input_audio_buffer.speech_started",
            "input_audio_buffer.committed",
            "conversation.item.input_audio_transcription.delta",
            "conversation.item.input_audio_transcription.completed",
        }
        if event_type not in tracked:
            return
        item_id = event.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            raise MAITranscriptionError("VoiceLive transcription event is missing its item_id.")
        if item_id in self._finished_items:
            return
        turn = self._turn(item_id)
        if event_type in ("input_audio_buffer.speech_started", "input_audio_buffer.committed"):
            if item_id not in self._turn_order:
                self._turn_order.append(item_id)
            if turn.start_ts is None:
                turn.start_ts = time.time()
        elif event_type == "conversation.item.input_audio_transcription.delta":
            if turn.final is not None:
                return
            delta = event.get("delta")
            if not isinstance(delta, str):
                raise MAITranscriptionError("VoiceLive returned an invalid MAI partial transcript.")
            turn.partial += delta
            if len(turn.partial) > MAX_TRANSCRIPT_CHARS:
                raise MAITranscriptionError("MAI partial transcript exceeded the input size limit.")
            turn.start_ts = turn.start_ts or time.time()
            if len(turn.partial.strip()) > 3 and not self._bridge.turn_guard_active:
                self._bridge.schedule_barge_in(self._barge_in_handler)
                if self._on_partial:
                    turn.sequence += 1
                    await asyncio.wait_for(
                        self._on_partial(turn.partial.strip(), "", None, item_id, turn.sequence),
                        timeout=IO_TIMEOUT_S,
                    )
        else:
            text = event.get("transcript")
            if not isinstance(text, str) or len(text) > MAX_TRANSCRIPT_CHARS:
                raise MAITranscriptionError("VoiceLive returned an invalid MAI final transcript.")
            turn.final = SpeechEvent(
                event_type=SpeechEventType.FINAL,
                text=text,
                language=event.get("language"),
                turn_id=item_id,
                sequence=turn.sequence + 1,
                recognition_start_ts=turn.start_ts,
                recognition_end_perf=time.perf_counter(),
            )
            if item_id not in self._turn_order:
                self._turn_order.append(item_id)
            # Finalization may complete out of order; commit/VAD order owns turn order.
            while self._turn_order and self._turns[self._turn_order[0]].final is not None:
                final_id = self._turn_order[0]
                final = self._turns[final_id].final
                if len(final.text.strip()) > 1:
                    self._bridge.arm_turn_guard()
                    try:
                        await self._bridge.queue_speech_result_async(
                            self._speech_queue, final, timeout=IO_TIMEOUT_S
                        )
                    except TimeoutError as exc:
                        raise MAITranscriptionError(
                            "The final speech queue stalled; MAI input was stopped, not silently dropped."
                        ) from exc
                self._turn_order.popleft()
                del self._turns[final_id]
                self._finished_items.append(final_id)

    async def _report_failure(self) -> None:
        # Terminal provider errors bypass the turn queue: a busy/full queue must
        # not delay close or emit the same failure a second time as an SDK error.
        await self._on_error(str(self._failure))

    async def stop(self) -> None:
        """Retain strict, bounded stop acknowledgement for this input connection."""
        self._closed = True
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(
                self._stop(), name=f"mai-stop-{self.context.session_short}"
            )
        await asyncio.shield(self._stop_task)

    async def _stop(self) -> None:
        await cancel_and_join([self._task] if self._task else [], timeout=IO_TIMEOUT_S)
        self._turns.clear()
        self._turn_order.clear()
        self._finished_items.clear()
        self._drain_audio()

    def _drain_audio(self) -> None:
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()
            self._audio_queue.task_done()
