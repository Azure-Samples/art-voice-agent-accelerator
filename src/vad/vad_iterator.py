import copy
import numpy as np
import torch

from pipecat.audio.filters.noisereduce_filter import NoisereduceFilter
from pipecat.frames.frames import FilterEnableFrame


class VADIteratorWithDenoiseAndToggle:
    def __init__(
        self,
        model,
        threshold: float = 0.5,
        sampling_rate: int = 16000,
        min_silence_duration_ms: int = 100,
        speech_pad_ms: int = 30,
        enable_denoise: bool = True,
    ):
        self.model = model
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.buffer = []
        self.start_pad_buffer = []

        self.min_silence_samples = int(sampling_rate * min_silence_duration_ms / 1000)
        self.speech_pad_samples = int(sampling_rate * speech_pad_ms / 1000)

        # Initialize the denoiser
        self.denoiser = NoisereduceFilter() if enable_denoise else None
        self.denoising_enabled = enable_denoise  # Flag to control it dynamically

        self.reset_states()

    async def start(self):
        if self.denoiser:
            await self.denoiser.start(self.sampling_rate)

    async def stop(self):
        if self.denoiser:
            await self.denoiser.stop()

    def reset_states(self):
        self.model.reset_states()
        self.triggered = False
        self.temp_end = 0
        self.current_sample = 0

    async def process(self, audio_bytes: bytes):
        # Apply noise reduction if enabled
        if self.denoiser and self.denoising_enabled:
            audio_bytes = await self.denoiser.filter(audio_bytes)

        # Convert PCM16 bytes to float32
        audio_np = (
            np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )
        audio_tensor = torch.from_numpy(audio_np).unsqueeze(0)

        window_size_samples = len(audio_tensor[0])
        self.current_sample += window_size_samples

        # Run VAD
        speech_prob = self.model(audio_tensor, self.sampling_rate).item()

        if (speech_prob >= self.threshold) and self.temp_end:
            self.temp_end = 0

        if (speech_prob >= self.threshold) and not self.triggered:
            self.triggered = True
            self.buffer = copy.deepcopy(self.start_pad_buffer)
            self.buffer.append(audio_tensor)
            return None

        if (speech_prob < self.threshold - 0.15) and self.triggered:
            if not self.temp_end:
                self.temp_end = self.current_sample
            if self.current_sample - self.temp_end >= self.min_silence_samples:
                self.temp_end = 0
                self.triggered = False
                spoken_utterance = self.buffer
                self.buffer = []
                return spoken_utterance

        if self.triggered:
            self.buffer.append(audio_tensor)

        self.start_pad_buffer.append(audio_tensor)
        self.start_pad_buffer = self.start_pad_buffer[
            -int(self.speech_pad_samples // window_size_samples) :
        ]

        return None

    async def queue_frame(self, frame):
        """Handle FilterEnableFrame dynamically."""
        if isinstance(frame, FilterEnableFrame):
            self.denoising_enabled = frame.enabled
