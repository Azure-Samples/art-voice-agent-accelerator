import asyncio
import base64
import json
import os
import wave
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import pyaudio
import websockets
from dotenv import load_dotenv

from src.aoai.audio_util import choose_audio_device

load_dotenv()


class AudioRecorder:
    """
    Async audio recorder using PyAudio.
    Allows independent recording (to memory and .wav) and streaming (for STT).
    """

    def __init__(
        self,
        rate: int,
        channels: int,
        format_: int,
        chunk: int,
        device_index: Optional[int] = None,
    ):
        self.rate = rate
        self.channels = channels
        self.format = format_
        self.chunk = chunk
        self.device_index = (
            device_index if device_index is not None else choose_audio_device()
        )
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.frames = []
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._loop = asyncio.get_event_loop()
        self._running = False

    def start(self) -> None:
        """
        Start the audio stream and begin capturing to the queue.
        """

        def callback(in_data, frame_count, time_info, status):
            self.frames.append(in_data)
            self._loop.call_soon_threadsafe(self.audio_queue.put_nowait, in_data)
            return (None, pyaudio.paContinue)

        self.stream = self.p.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.chunk,
            stream_callback=callback,
        )
        self._running = True
        self.stream.start_stream()

    def stop(self) -> None:
        """
        Stop and close the stream, release audio resources.
        """
        self._running = False
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()

    def save_wav(self, filename: str) -> None:
        """
        Save the recorded audio to a .wav file.
        Ensures there is audio data before saving.
        Creates the output directory if it does not exist.
        """
        if not self.frames:
            print("⚠️ No audio recorded. Nothing to save.")
            return
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        wf = wave.open(filename, "wb")
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.p.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b"".join(self.frames))
        wf.close()
        print(f"🎙️ Audio saved to {filename}")


class TranscriptionClient:
    """
    Handles async websocket transcription session to Azure OpenAI STT.
    Can be used independently: just supply an async generator of audio chunks.
    """

    def __init__(
        self,
        url: str,
        headers: dict,
        session_config: Dict[str, Any],
        on_delta: Optional[Callable[[str], None]] = None,
        on_transcript: Optional[Callable[[str], None]] = None,
    ):
        self.url = url
        self.headers = headers
        self.session_config = session_config
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._on_delta = on_delta
        self._on_transcript = on_transcript
        self._running = False
        self._send_task = None
        self._recv_task = None

    async def __aenter__(self):
        try:
            self.ws = await websockets.connect(
                self.url, additional_headers=self.headers
            )
        except TypeError:
            self.ws = await websockets.connect(self.url, extra_headers=self.headers)
        self._running = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._running = False
        if self.ws:
            await self.ws.close()
        if self._send_task:
            self._send_task.cancel()
        if self._recv_task:
            self._recv_task.cancel()

    async def send_json(self, data: dict) -> None:
        if self.ws:
            await self.ws.send(json.dumps(data))

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        await self.send_json(
            {"type": "input_audio_buffer.append", "audio": audio_base64}
        )

    async def start_session(self, rate: int, channels: int) -> None:
        session_config = {
            "type": "transcription_session.update",
            "session": self.session_config,
        }
        await self.send_json(session_config)
        await self.send_json(
            {
                "type": "audio_start",
                "data": {"encoding": "pcm", "sample_rate": rate, "channels": channels},
            }
        )

    async def receive_loop(self) -> None:
        async for message in self.ws:
            try:
                data = json.loads(message)
                event_type = data.get("type", "")
                if event_type == "conversation.item.input_audio_transcription.delta":
                    delta = data.get("delta", "")
                    if delta and self._on_delta:
                        self._on_delta(delta)
                elif (
                    event_type
                    == "conversation.item.input_audio_transcription.completed"
                ):
                    transcript = data.get("transcript", "")
                    if transcript and self._on_transcript:
                        self._on_transcript(transcript)
                elif event_type == "conversation.item.created":
                    transcript = data.get("item", "")
                    if (
                        isinstance(transcript, dict)
                        and "content" in transcript
                        and transcript["content"]
                    ):
                        t = transcript["content"][0].get("transcript")
                        if t and self._on_transcript:
                            self._on_transcript(t)
                    elif transcript and self._on_transcript:
                        self._on_transcript(str(transcript))
            except Exception as e:
                print("❌ Error parsing message:", e)

    async def run(self, audio_chunk_iter: asyncio.Queue, rate: int, channels: int):
        """
        Main loop: configure session, send audio from queue, receive results.
        """
        await self.start_session(rate, channels)
        self._send_task = asyncio.create_task(self._send_audio_loop(audio_chunk_iter))
        self._recv_task = asyncio.create_task(self.receive_loop())
        done, pending = await asyncio.wait(
            [self._send_task, self._recv_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

    async def _send_audio_loop(self, audio_queue: asyncio.Queue):
        while self._running:
            try:
                audio_data = await audio_queue.get()
                if audio_data is None:
                    break
                await self.send_audio_chunk(audio_data)
            except asyncio.CancelledError:
                break


class AudioTranscriber:
    """
    High-level orchestrator for audio recording and real-time transcription.
    Use as: record only, transcribe only, or chain both (record+transcribe).
    """

    def __init__(
        self,
        url: str,
        headers: dict,
        rate: int,
        channels: int,
        format_: int,
        chunk: int,
        device_index: Optional[int] = None,
    ):
        self.url = url
        self.headers = headers
        self.rate = rate
        self.channels = channels
        self.format = format_
        self.chunk = chunk
        self.device_index = device_index

    async def record(
        self, duration: Optional[float] = None, output_file: Optional[str] = None
    ) -> AudioRecorder:
        """
        Record audio from mic. Returns AudioRecorder.
        Optionally, specify duration (seconds). Use output_file to auto-save.
        """
        recorder = AudioRecorder(
            rate=self.rate,
            channels=self.channels,
            format_=self.format,
            chunk=self.chunk,
            device_index=self.device_index,
        )
        recorder.start()
        print(
            f"Recording{' for ' + str(duration) + ' seconds' if duration else ' (Ctrl+C to stop)'}..."
        )
        try:
            if duration:
                await asyncio.sleep(duration)
            else:
                while True:
                    await asyncio.sleep(0.5)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            recorder.stop()
            if output_file:
                recorder.save_wav(output_file)
        return recorder

    async def transcribe(
        self,
        audio_queue: Optional[asyncio.Queue] = None,
        model: str = "gpt-4o-transcribe",
        prompt: Optional[str] = "Respond in English.",
        language: Optional[str] = None,
        noise_reduction: str = "near_field",
        vad_type: str = "server_vad",
        vad_config: Optional[dict] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        on_transcript: Optional[Callable[[str], None]] = None,
        output_wav_file: Optional[str] = None,
    ):
        """
        Run a transcription session with full model/config control.

        If audio_queue is None, creates and uses a live AudioRecorder.

        Args:
            audio_queue: Asyncio queue containing audio chunks to transcribe.
            model: Transcription model to use.
            prompt: Custom prompt for the model.
            language: Language hint for recognition.
            noise_reduction: Type of noise reduction.
            vad_type: Voice activity detection type.
            vad_config: Config dict for VAD.
            on_delta: Callback for interim results.
            on_transcript: Callback for final results.
            output_wav_file: Filename for saving raw microphone audio (if recording).
        """
        recorder = None
        if audio_queue is None:
            recorder = AudioRecorder(
                rate=self.rate,
                channels=self.channels,
                format_=self.format,
                chunk=self.chunk,
                device_index=self.device_index,
            )
            recorder.start()
            audio_queue = recorder.audio_queue

        session_config = {
            "input_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": model,
                "prompt": prompt,
            },
            "input_audio_noise_reduction": {"type": noise_reduction},
            "turn_detection": {"type": vad_type} if vad_type else None,
        }
        if vad_config:
            session_config["turn_detection"].update(vad_config)
        if language:
            session_config["input_audio_transcription"]["language"] = language

        async with TranscriptionClient(
            self.url, self.headers, session_config, on_delta, on_transcript
        ) as client:
            try:
                await client.run(audio_queue, self.rate, self.channels)
            except asyncio.CancelledError:
                print("Transcription cancelled.")
            finally:
                if recorder:
                    recorder.stop()
                    if output_wav_file is None:
                        # Default to timestamped file if not provided
                        output_wav_file = (
                            f"microphone_capture_{datetime.now():%Y%m%d_%H%M%S}.wav"
                        )
                    recorder.save_wav(output_wav_file)
