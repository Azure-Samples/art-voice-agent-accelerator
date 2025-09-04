from __future__ import annotations

import base64
import threading
from collections import deque
from typing import Optional

import numpy as np
import sounddevice as sd  # type: ignore[import-untyped]
from utils.ml_logging import get_logger

logger = get_logger(__name__)


def pcm_to_base64(pcm: np.ndarray) -> str:
    """
    Encode mono int16 PCM to base64 string.

    :param pcm: 1-D numpy array of dtype=int16.
    :return: Base64-encoded string.
    """
    try:
        if pcm.dtype != np.int16:
            pcm = pcm.astype(np.int16, copy=False)
        return base64.b64encode(pcm.tobytes(order="C")).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to encode PCM to base64: %s", exc)
        return ""


class MicSource:
    """
    Non-blocking microphone reader using sounddevice.InputStream.

    Call `start()` once, then poll `read(frames)` each loop. If enough frames
    aren't available, returns None immediately (no blocking).

    :param sample_rate: Input sample rate in Hz (e.g., 24000).
    :param channels: Number of channels (1 recommended).
    :param device: Optional device index/name for sounddevice.
    :param dtype: Numpy dtype (np.int16 recommended).
    :param block_ms: Preferred hardware block size in milliseconds.
    """

    def __init__(
        self,
        *,
        sample_rate: int,
        channels: int = 1,
        device: Optional[int | str] = None,
        dtype: np.dtype = np.int16,
        block_ms: int = 20,
    ) -> None:
        self._sr = sample_rate
        self._channels = channels
        self._device = device
        self._dtype = dtype
        self._blocksize = max(1, int((sample_rate * block_ms) / 1000))
        self._stream: Optional[sd.InputStream] = None

    def start(self) -> None:
        """Open and start the microphone stream."""
        if self._stream is not None:
            logger.warning("MicSource already started.")
            return
        try:
            self._stream = sd.InputStream(
                samplerate=self._sr,
                channels=self._channels,
                dtype="int16",  # device native; we'll present int16 outward
                blocksize=self._blocksize,
                device=self._device,
            )
            self._stream.start()
            logger.info("MicSource started at %s Hz, blocksize=%s.", self._sr, self._blocksize)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to start microphone stream.")
            self._stream = None
            raise

    def read(self, frames: int) -> Optional[np.ndarray]:
        """
        Attempt to read `frames` samples; return None if not yet available.

        :param frames: Number of samples to read (per channel).
        :return: Mono int16 PCM array or None.
        """
        if self._stream is None:
            logger.error("MicSource.read() called before start().")
            return None
        try:
            if self._stream.read_available < frames:
                return None
            data, _ = self._stream.read(frames)
            # data shape: (frames, channels)
            if self._channels > 1:
                data = np.mean(data, axis=1, dtype=np.int16)  # downmix
            else:
                data = data.reshape(-1).astype(np.int16, copy=False)
            return data
        except Exception:  # noqa: BLE001
            logger.exception("Microphone read failed.")
            return None

    def stop(self) -> None:
        """Stop and close the microphone stream."""
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
            logger.info("MicSource stopped.")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to stop MicSource.")
        finally:
            self._stream = None


class SpeakerSink:
    """
    Low-latency speaker sink with an internal buffer and callback mixer.

    Producer (your code) calls `write(pcm)` with mono int16 arrays.
    The audio callback pulls from the buffer and feeds the device.

    :param sample_rate: Output sample rate in Hz (e.g., 24000).
    :param channels: Number of channels (1 recommended).
    :param device: Optional device index/name for sounddevice.
    :param block_ms: Preferred hardware block size in milliseconds.
    :param max_queue_samples: Upper bound of buffered samples to limit latency.
    """

    def __init__(
        self,
        *,
        sample_rate: int,
        channels: int = 1,
        device: Optional[int | str] = None,
        block_ms: int = 20,
        max_queue_samples: int = 24000 * 2,  # ~2s at 24 kHz
    ) -> None:
        self._sr = sample_rate
        self._channels = channels
        self._device = device
        self._blocksize = max(1, int((sample_rate * block_ms) / 1000))
        self._maxq = max_queue_samples

        self._buf = deque()  # type: deque[np.ndarray]
        self._buf_len = 0
        self._lock = threading.Lock()

        def _cb(outdata, frames, time_info, status) -> None:  # noqa: ANN001, D401
            """sounddevice callback: fill device buffer from internal queue."""
            if status:
                logger.debug("SpeakerSink status: %s", status)
            with self._lock:
                # Assemble exactly `frames` samples
                out = np.empty(frames, dtype=np.int16)
                n = 0
                while n < frames and self._buf_len > 0:
                    chunk = self._buf.popleft()
                    take = min(len(chunk), frames - n)
                    out[n : n + take] = chunk[:take]
                    n += take
                    if take < len(chunk):
                        # Put back remainder
                        self._buf.appendleft(chunk[take:])
                    else:
                        self._buf_len -= len(chunk)
                if n < frames:
                    out[n:] = 0  # pad with silence
            # Expand to channels
            if self._channels == 1:
                outdata[:frames, 0] = out
            else:
                out_stereo = np.repeat(out[:, None], self._channels, axis=1)
                outdata[:frames, : self._channels] = out_stereo

        try:
            self._stream = sd.OutputStream(
                samplerate=self._sr,
                channels=self._channels,
                dtype="int16",
                blocksize=self._blocksize,
                device=self._device,
                callback=_cb,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to create speaker OutputStream.")
            raise

    def start(self) -> None:
        """Start the speaker stream."""
        try:
            self._stream.start()
            logger.info("SpeakerSink started at %s Hz, blocksize=%s.", self._sr, self._blocksize)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to start SpeakerSink.")
            raise

    def write(self, pcm: np.ndarray) -> None:
        """
        Enqueue mono int16 PCM for playback.

        :param pcm: 1-D numpy array of dtype=int16.
        """
        try:
            if pcm.dtype != np.int16:
                pcm = pcm.astype(np.int16, copy=False)
            with self._lock:
                # Bound the queue to avoid runaway latency
                if self._buf_len + len(pcm) > self._maxq:
                    # Drop oldest until there is room
                    while self._buf and self._buf_len + len(pcm) > self._maxq:
                        dropped = self._buf.popleft()
                        self._buf_len -= len(dropped)
                        logger.debug("Speaker buffer full; dropped %d samples.", len(dropped))
                self._buf.append(pcm)
                self._buf_len += len(pcm)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to enqueue audio to SpeakerSink.")

    def stop(self) -> None:
        """Stop and close the speaker stream."""
        try:
            self._stream.stop()
            self._stream.close()
            logger.info("SpeakerSink stopped.")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to stop SpeakerSink.")
