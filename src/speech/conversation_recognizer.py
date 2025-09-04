from azure.cognitiveservices.speech import (
    SpeechConfig,
    AutoDetectSourceLanguageConfig,
    PropertyId,
    AudioConfig,
)
from azure.cognitiveservices.speech.transcription import ConversationTranscriber
from azure.cognitiveservices.speech.audio import (
    AudioStreamFormat,
    PushAudioInputStream,
    AudioStreamContainerFormat,
)
import json
import os
from typing import Callable, List, Optional, Final

from utils.azure_auth import get_credential
from dotenv import load_dotenv

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.enums.monitoring import SpanAttr
from utils.ml_logging import get_logger

logger = get_logger(__name__)
load_dotenv()


class StreamingConversationTranscriberFromBytes:
    _DEFAULT_LANGS: Final[List[str]] = ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT"]

    def __init__(
        self,
        *,
        key: Optional[str] = None,
        region: Optional[str] = None,
        candidate_languages: List[str] | None = None,
        vad_silence_timeout_ms: int = 800,
        audio_format: str = "pcm",
        enable_neural_fe: bool = False,
        enable_diarisation: bool = True,
        speaker_count_hint: int = 2,
        call_connection_id: str | None = None,
        enable_tracing: bool = True,
    ):
        self.key = key or os.getenv("AZURE_SPEECH_KEY")
        self.region = region or os.getenv("AZURE_SPEECH_REGION")
        self.candidate_languages = candidate_languages or self._DEFAULT_LANGS
        self.vad_silence_timeout_ms = vad_silence_timeout_ms
        self.audio_format = audio_format
        self.call_connection_id = call_connection_id or "unknown"
        self.enable_tracing = enable_tracing

        self.partial_callback: Optional[Callable[[str, str, str | None], None]] = None
        self.final_callback: Optional[Callable[[str, str, str | None], None]] = None
        self.cancel_callback: Optional[Callable[[any], None]] = None

        self._enable_neural_fe = enable_neural_fe
        self._enable_diarisation = enable_diarisation
        self._speaker_hint = max(0, min(speaker_count_hint, 16))

        self.push_stream = None
        self.transcriber = None

        self.tracer = trace.get_tracer(__name__) if enable_tracing else None
        self._session_span = None

        self.cfg = self._create_speech_config()

    def _create_speech_config(self) -> SpeechConfig:
        if self.key:
            return SpeechConfig(subscription=self.key, region=self.region)
        credential = get_credential()
        token_result = credential.get_token(
            "https://cognitiveservices.azure.com/.default"
        )
        speech_config = SpeechConfig(region=self.region)
        speech_config.authorization_token = token_result.token
        return speech_config

    def set_partial_result_callback(
        self, callback: Callable[[str, str, str | None], None]
    ) -> None:
        self.partial_callback = callback

    def set_final_result_callback(
        self, callback: Callable[[str, str, str | None], None]
    ) -> None:
        self.final_callback = callback

    def set_cancel_callback(self, callback: Callable[[any], None]) -> None:
        self.cancel_callback = callback

    def prepare_stream(self) -> None:
        if self.audio_format == "pcm":
            stream_format = AudioStreamFormat(
                samples_per_second=16000, bits_per_sample=16, channels=1
            )
        elif self.audio_format == "any":
            stream_format = AudioStreamFormat(
                compressed_stream_format=AudioStreamContainerFormat.ANY
            )
        else:
            raise ValueError(f"Unsupported audio_format: {self.audio_format}")
        self.push_stream = PushAudioInputStream(stream_format=stream_format)

    def start(self) -> None:
        if self.enable_tracing and self.tracer:
            self._session_span = self.tracer.start_span(
                "conversation_transcription_session", kind=SpanKind.CLIENT
            )
            self._session_span.set_attribute("ai.operation.id", self.call_connection_id)
            self._session_span.set_attribute("speech.region", self.region)
            self._session_span.set_attribute("speech.audio_format", self.audio_format)
            self._session_span.set_attribute(
                "speech.candidate_languages", ",".join(self.candidate_languages)
            )
            self._session_span.set_attribute(
                SpanAttr.SERVICE_NAME, "azure-conversation-transcriber"
            )
            self._session_span.set_attribute(SpanAttr.SERVICE_VERSION, "1.0.0")
            with trace.use_span(self._session_span):
                self._start_transcriber()
        else:
            self._start_transcriber()

    def _start_transcriber(self) -> None:
        self.prepare_stream()

        speech_config = self.cfg
        if self._enable_diarisation:
            speech_config.set_property(
                PropertyId.SpeechServiceResponse_DiarizeIntermediateResults, "true"
            )

        if self.audio_format == "pcm":
            stream_format = AudioStreamFormat(
                samples_per_second=16000, bits_per_sample=16, channels=1
            )
        else:
            stream_format = AudioStreamFormat(
                compressed_stream_format=AudioStreamContainerFormat.ANY
            )

        if self._enable_neural_fe:
            # Enable neural audio front-end processing
            # proc_opts = AudioProcessingOptions(
            #     AudioProcessingConstants.AUDIO_INPUT_PROCESSING_ENABLE_DEFAULT,
            #     AudioProcessingConstants.AUDIO_INPUT_PROCESSING_MODE_VOICE,
            # )
            # audio_config = AudioConfig(stream=self.push_stream, audio_processing_options=proc_opts)
            audio_config = AudioConfig(stream=self.push_stream)
        else:
            audio_config = AudioConfig(stream=self.push_stream)

        lid_cfg = AutoDetectSourceLanguageConfig(languages=self.candidate_languages)

        self.transcriber = ConversationTranscriber(
            speech_config=speech_config, audio_config=audio_config
        )

        self.transcriber.transcribing.connect(self._on_partial)
        self.transcriber.transcribed.connect(self._on_final)
        self.transcriber.session_stopped.connect(self._on_stopped)
        self.transcriber.canceled.connect(self._on_canceled)

        if self.cancel_callback:
            self.transcriber.canceled.connect(self.cancel_callback)

        self.transcriber.start_transcribing_async().get()

    def write_bytes(self, audio_chunk: bytes) -> None:
        if self.push_stream:
            if self.enable_tracing and self.tracer:
                with self.tracer.start_as_current_span(
                    "audio_write", kind=SpanKind.CLIENT
                ):
                    self.push_stream.write(audio_chunk)
            else:
                self.push_stream.write(audio_chunk)

    def stop(self) -> None:
        if self.transcriber:
            if self._session_span:
                self._session_span.add_event("transcription_stopping")
            self.transcriber.stop_transcribing_async().get()
            if self._session_span:
                self._session_span.set_status(Status(StatusCode.OK))
                self._session_span.end()

    def close_stream(self) -> None:
        if self.push_stream:
            self.push_stream.close()
        if self._session_span:
            self._session_span.add_event("audio_stream_closed")
            self._session_span.end()

    def _on_partial(self, evt):
        text = evt.result.text
        speaker_id = self._extract_speaker_id(evt)
        detected_lang = self._extract_lang(evt)
        if self.partial_callback:
            self.partial_callback(text, detected_lang, speaker_id)

    def _on_final(self, evt):
        text = evt.result.text
        speaker_id = self._extract_speaker_id(evt)
        detected_lang = self._extract_lang(evt)
        if self.final_callback:
            self.final_callback(text, detected_lang, speaker_id)

    def _on_stopped(self, evt):
        logger.info("Conversation session stopped.")
        if self._session_span:
            self._session_span.add_event("session_stopped")

    def _on_canceled(self, evt):
        logger.warning(f"Conversation canceled: {evt}")
        if self._session_span:
            self._session_span.set_status(Status(StatusCode.ERROR, "Canceled"))
            self._session_span.add_event("canceled", {"reason": str(evt)})

    @staticmethod
    def _extract_speaker_id(evt) -> Optional[str]:
        blob = evt.result.properties.get(
            PropertyId.SpeechServiceResponse_JsonResult, ""
        )
        if blob:
            try:
                return str(json.loads(blob).get("SpeakerId"))
            except Exception:
                return None
        return None

    @staticmethod
    def _extract_lang(evt) -> str:
        if getattr(evt.result, "language", None):
            return evt.result.language
        prop = evt.result.properties.get(
            PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult, ""
        )
        return prop or "en-US"
