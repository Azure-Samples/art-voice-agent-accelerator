"""
`azure_openai.py` is a module for managing interactions with the Azure OpenAI API within our application.

"""

import base64
import json
import mimetypes
import os
import time
import traceback
from typing import Any, Literal

import openai
from dotenv import load_dotenv
from openai import AzureOpenAI
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from utils.azure_auth import get_bearer_token_provider, get_credential
from utils.ml_logging import get_logger
from utils.trace_context import TraceContext

from src.enums.monitoring import GenAIOperation, GenAIProvider, PeerService, SpanAttr

# Load environment variables from .env file
load_dotenv()

# Set up logger
logger = get_logger(__name__)

# # Exports traces to local
# span_exporter = ConsoleSpanExporter()
# tracer_provider = TracerProvider()
# tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
# trace.set_tracer_provider(tracer_provider)

# Get tracer instance
tracer = trace.get_tracer(__name__)


class NoOpTraceContext:
    """
    No-operation context manager that provides the same interface as TraceContext
    but performs no actual tracing operations.
    """

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def set_attribute(self, key, value):
        pass

    def add_event(self, name, attributes=None):
        pass

    def record_exception(self, exception):
        pass


def _is_aoai_tracing_enabled() -> bool:
    """Check if Azure OpenAI tracing is enabled."""
    return os.getenv("AOAI_TRACING", os.getenv("ENABLE_TRACING", "false")).lower() == "true"


def _create_aoai_trace_context(
    name: str, call_connection_id: str = None, session_id: str = None, **kwargs
):
    """
    Create a TraceContext or NoOpTraceContext based on environment configuration.

    Args:
        name: The name of the span
        call_connection_id: Optional call connection ID for correlation
        session_id: Optional session ID for correlation
        **kwargs: Additional parameters for TraceContext

    Returns:
        TraceContext or NoOpTraceContext instance
    """
    if _is_aoai_tracing_enabled():
        return TraceContext(
            name=name,
            component="src.aoai.manager",
            call_connection_id=call_connection_id,
            session_id=session_id,
            **kwargs,
        )
    else:
        return NoOpTraceContext()


class AzureOpenAIManager:
    """
    A manager class for interacting with the Azure OpenAI API.

    This class provides methods for generating text completions and chat responses using the Azure OpenAI API.
    It also provides methods for validating API configurations and getting the OpenAI client.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_version: str | None = None,
        azure_endpoint: str | None = None,
        completion_model_name: str | None = None,
        chat_model_name: str | None = None,
        embedding_model_name: str | None = None,
        dalle_model_name: str | None = None,
        whisper_model_name: str | None = None,
        call_connection_id: str | None = None,
        session_id: str | None = None,
        enable_tracing: bool | None = None,
    ):
        """
        Initializes the Azure OpenAI Manager with necessary configurations.

        :param api_key: The Azure OpenAI Key. If not provided, it will be fetched from the environment variable "AZURE_OPENAI_KEY".
        :param api_version: The Azure OpenAI API Version. If not provided, it will be fetched from the environment variable "AZURE_OPENAI_API_VERSION" or default to "2023-05-15".
        :param azure_endpoint: The Azure OpenAI API Endpoint. If not provided, it will be fetched from the environment variable "AZURE_OPENAI_ENDPOINT".
        :param completion_model_name: The Completion Model Deployment ID. If not provided, it will be fetched from the environment variable "AZURE_AOAI_COMPLETION_MODEL_DEPLOYMENT_ID".
        :param chat_model_name: The Chat Model Name. If not provided, it will be fetched from the environment variable "AZURE_AOAI_CHAT_MODEL_NAME".
        :param embedding_model_name: The Embedding Model Deployment ID. If not provided, it will be fetched from the environment variable "AZURE_AOAI_EMBEDDING_DEPLOYMENT_ID".
        :param dalle_model_name: The DALL-E Model Deployment ID. If not provided, it will be fetched from the environment variable "AZURE_AOAI_DALLE_MODEL_DEPLOYMENT_ID".
        :param call_connection_id: Call connection ID for tracing correlation
        :param session_id: Session ID for tracing correlation
        :param enable_tracing: Whether to enable tracing. If None, checks environment variables

        """
        self.api_key = api_key or os.getenv("AZURE_OPENAI_KEY")

        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION") or "2024-02-01"
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.completion_model_name = completion_model_name or os.getenv(
            "AZURE_AOAI_COMPLETION_MODEL_DEPLOYMENT_ID"
        )
        self.chat_model_name = chat_model_name or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_ID")
        self.embedding_model_name = embedding_model_name or os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
        )

        self.dalle_model_name = dalle_model_name or os.getenv(
            "AZURE_AOAI_DALLE_MODEL_DEPLOYMENT_ID"
        )

        self.whisper_model_name = whisper_model_name or os.getenv(
            "AZURE_AOAI_WHISPER_MODEL_DEPLOYMENT_ID"
        )

        # Store tracing context
        self.call_connection_id = call_connection_id
        self.session_id = session_id
        self.enable_tracing = (
            enable_tracing if enable_tracing is not None else _is_aoai_tracing_enabled()
        )

        if not self.api_key:
            token_provider = get_bearer_token_provider(
                get_credential(), "https://cognitiveservices.azure.com/.default"
            )
            self.openai_client = AzureOpenAI(
                api_version=self.api_version,
                azure_endpoint=self.azure_endpoint,
                azure_ad_token_provider=token_provider,
            )
        else:
            self.openai_client = AzureOpenAI(
                api_version=self.api_version,
                azure_endpoint=self.azure_endpoint,
                api_key=self.api_key,
            )

        self._validate_api_configurations()

    def _create_trace_context(self, name: str, **kwargs):
        """
        Create a TraceContext or NoOpTraceContext based on the enable_tracing setting.
        This provides consistent tracing behavior throughout the Azure OpenAI operations.
        """
        if self.enable_tracing:
            return TraceContext(
                name=name,
                component="src.aoai.manager",
                call_connection_id=self.call_connection_id,
                session_id=self.session_id,
                **kwargs,
            )
        else:
            return NoOpTraceContext()

    def _get_endpoint_host(self) -> str:
        """Extract hostname from Azure OpenAI endpoint."""
        return (
            (self.azure_endpoint or "").replace("https://", "").replace("http://", "").rstrip("/")
        )

    def _set_genai_span_attributes(
        self,
        span: trace.Span,
        operation: str,
        model: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        seed: int | None = None,
    ) -> None:
        """
        Set standardized GenAI semantic convention attributes on a span.

        Args:
            span: The OpenTelemetry span to add attributes to.
            operation: GenAI operation name (e.g., "chat", "embeddings").
            model: Model deployment name.
            max_tokens: Max tokens for the request.
            temperature: Temperature setting.
            top_p: Top-p sampling parameter.
            seed: Random seed.
        """
        endpoint_host = self._get_endpoint_host()

        # Application Map attributes (creates edge to azure.ai.openai node)
        span.set_attribute(SpanAttr.PEER_SERVICE.value, PeerService.AZURE_OPENAI)
        span.set_attribute(SpanAttr.SERVER_ADDRESS.value, endpoint_host)
        span.set_attribute(SpanAttr.SERVER_PORT.value, 443)

        # GenAI semantic convention attributes
        span.set_attribute(SpanAttr.GENAI_PROVIDER_NAME.value, GenAIProvider.AZURE_OPENAI)
        span.set_attribute(SpanAttr.GENAI_OPERATION_NAME.value, operation)
        span.set_attribute(SpanAttr.GENAI_REQUEST_MODEL.value, model)

        # Request parameters
        if max_tokens is not None:
            span.set_attribute(SpanAttr.GENAI_REQUEST_MAX_TOKENS.value, max_tokens)
        if temperature is not None:
            span.set_attribute(SpanAttr.GENAI_REQUEST_TEMPERATURE.value, temperature)
        if top_p is not None:
            span.set_attribute(SpanAttr.GENAI_REQUEST_TOP_P.value, top_p)
        if seed is not None:
            span.set_attribute(SpanAttr.GENAI_REQUEST_SEED.value, seed)

        # Correlation attributes
        if self.call_connection_id:
            span.set_attribute(SpanAttr.CALL_CONNECTION_ID.value, self.call_connection_id)
        if self.session_id:
            span.set_attribute(SpanAttr.SESSION_ID.value, self.session_id)

    def _set_genai_response_attributes(
        self,
        span: trace.Span,
        response: Any,
        start_time: float,
    ) -> None:
        """
        Set GenAI response attributes on a span after receiving API response.

        Args:
            span: The OpenTelemetry span to add attributes to.
            response: The API response object with usage information.
            start_time: The start time (from time.perf_counter()) for duration calculation.
        """
        duration_ms = (time.perf_counter() - start_time) * 1000
        span.set_attribute(SpanAttr.GENAI_CLIENT_OPERATION_DURATION.value, duration_ms)

        # Response model
        if hasattr(response, "model"):
            span.set_attribute(SpanAttr.GENAI_RESPONSE_MODEL.value, response.model)

        # Response ID
        if hasattr(response, "id"):
            span.set_attribute(SpanAttr.GENAI_RESPONSE_ID.value, response.id)

        # Token usage
        if hasattr(response, "usage") and response.usage:
            if hasattr(response.usage, "prompt_tokens"):
                span.set_attribute(
                    SpanAttr.GENAI_USAGE_INPUT_TOKENS.value, response.usage.prompt_tokens
                )
            if hasattr(response.usage, "completion_tokens"):
                span.set_attribute(
                    SpanAttr.GENAI_USAGE_OUTPUT_TOKENS.value, response.usage.completion_tokens
                )

        # Finish reasons
        if hasattr(response, "choices") and response.choices:
            finish_reasons = [
                c.finish_reason
                for c in response.choices
                if hasattr(c, "finish_reason") and c.finish_reason
            ]
            if finish_reasons:
                span.set_attribute(SpanAttr.GENAI_RESPONSE_FINISH_REASONS.value, finish_reasons)

        span.set_status(Status(StatusCode.OK))

    def get_azure_openai_client(self):
        """
        Returns the OpenAI client.

        This method is used to get the OpenAI client that is used to interact with the OpenAI API.
        The client is initialized with the API key and endpoint when the AzureOpenAIManager object is created.

        :return: The OpenAI client.
        """
        return self.openai_client

    def _validate_api_configurations(self):
        """
        Validates if all necessary configurations are set.

        This method checks if the API key and Azure endpoint are set in the OpenAI client.
        These configurations are necessary for making requests to the OpenAI API.
        If any of these configurations are not set, the method raises a ValueError.

        :raises ValueError: If the API key or Azure endpoint is not set.
        """
        if not all(
            [
                self.openai_client.api_key,
                self.azure_endpoint,
            ]
        ):
            raise ValueError(
                "One or more OpenAI API setup variables are empty. Please review your environment variables and `SETTINGS.md`"
            )

    @tracer.start_as_current_span("azure_openai.generate_text_completion")
    async def async_generate_chat_completion_response(
        self,
        conversation_history: list[dict[str, str]],
        query: str,
        system_message_content: str = """You are an AI assistant that
          helps people find information. Please be precise, polite, and concise.""",
        temperature: float = 0.7,
        deployment_name: str = None,
        max_tokens: int = 150,
        seed: int = 42,
        top_p: float = 1.0,
        **kwargs,
    ):
        """
        Asynchronously generates a text completion using Azure OpenAI's Foundation models.
        This method utilizes the chat completion API to respond to queries based on the conversation history.

        :param conversation_history: A list of past conversation messages formatted as dictionaries.
        :param query: The user's current query or message.
        :param system_message_content: Instructions for the AI on how to behave during the completion.
        :param temperature: Controls randomness in the generation, lower values mean less random completions.
        :param max_tokens: The maximum number of tokens to generate.
        :param seed: Seed for random number generator for reproducibility.
        :param top_p: Nucleus sampling parameter controlling the size of the probability mass considered for token generation.
        :return: The generated text completion or None if an error occurs.
        """

        messages_for_api = conversation_history + [
            {"role": "system", "content": system_message_content},
            {"role": "user", "content": query},
        ]

        model_name = deployment_name or self.chat_model_name
        response = None
        try:
            # Trace AOAI dependency as a CLIENT span with GenAI semantic conventions
            with tracer.start_as_current_span(
                f"{PeerService.AZURE_OPENAI}.{GenAIOperation.CHAT}",
                kind=SpanKind.CLIENT,
            ) as span:
                start_time = time.perf_counter()
                self._set_genai_span_attributes(
                    span,
                    operation=GenAIOperation.CHAT,
                    model=model_name,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    seed=seed,
                )

                response = self.openai_client.chat.completions.create(
                    model=model_name,
                    messages=messages_for_api,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    seed=seed,
                    top_p=top_p,
                    **kwargs,
                )

                self._set_genai_response_attributes(span, response, start_time)

                # Process and output the completion text
                for event in response:
                    if event.choices:
                        event_text = event.choices[0].delta
                        if event_text:
                            print(event_text.content, end="", flush=True)
                            time.sleep(0.01)  # Maintain minimal sleep to reduce latency
        except Exception as e:
            print(f"An error occurred: {str(e)}")

        return response

    def transcribe_audio_with_whisper(
        self,
        audio_file_path: str,
        language: str = "en",
        prompt: str = "Transcribe the following audio file to text.",
        response_format: Literal["json", "text", "srt", "verbose_json", "vtt"] = "text",
        temperature: float = 0.5,
        timestamp_granularities: list[Literal["word", "segment"]] = [],
        extra_headers=None,
        extra_query=None,
        extra_body=None,
        timeout: float | None = None,
    ):
        """
        Transcribes an audio file using the Whisper model and returns the transcription in the specified format.

        Args:
            audio_file_path: Path to the audio file to transcribe.
            model: ID of the model to use. Currently, only 'whisper-1' is available.
            language: The language of the input audio in ISO-639-1 format.
            prompt: Optional text to guide the model's style or continue a previous audio segment.
            response_format: Format of the transcript output ('json', 'text', 'srt', 'verbose_json', 'vtt').
            temperature: Sampling temperature between 0 and 1 for randomness in output.
            timestamp_granularities: Timestamp granularities ('word', 'segment') for 'verbose_json' format.
            extra_headers: Additional headers for the request.
            extra_query: Additional query parameters for the request.
            extra_body: Additional JSON properties for the request body.
            timeout: Request timeout in seconds.

        Returns:
            Transcription object with the audio transcription.
        """
        try:
            endpoint_host = (
                (self.azure_endpoint or "").replace("https://", "").replace("http://", "")
            )
            with tracer.start_as_current_span(
                "Azure.OpenAI.WhisperTranscription",
                kind=SpanKind.CLIENT,
                attributes={
                    "peer.service": "azure-openai",
                    "net.peer.name": endpoint_host,
                    "rt.call.connection_id": self.call_connection_id or "unknown",
                },
            ):
                result = self.openai_client.audio.transcriptions.create(
                    file=open(audio_file_path, "rb"),
                    model=self.whisper_model_name,
                    language=language,
                    prompt=prompt,
                    response_format=response_format,
                    temperature=temperature,
                    timestamp_granularities=timestamp_granularities,
                    extra_headers=extra_headers,
                    extra_query=extra_query,
                    extra_body=extra_body,
                    timeout=timeout,
                )
                return result
        except openai.APIConnectionError as e:
            logger.error("API Connection Error: The server could not be reached.")
            logger.error(f"Error details: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None, None
        except Exception as e:
            logger.error(
                "Unexpected Error: An unexpected error occurred during contextual response generation."
            )
            logger.error(f"Error details: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None, None

    async def generate_chat_response_o1(
        self,
        query: str,
        conversation_history: list[dict[str, str]] = [],
        max_completion_tokens: int = 5000,
        stream: bool = False,
        model: str = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_01", "o1-preview"),
        **kwargs,
    ) -> str | dict[str, Any] | None:
        """
        Generates a text response using the o1-preview or o1-mini models, considering the specific requirements and limitations of these models.

        :param query: The latest query to generate a response for.
        :param conversation_history: A list of message dictionaries representing the conversation history.
        :param max_completion_tokens: Maximum number of tokens to generate. Defaults to 5000.
        :param stream: Whether to stream the response. Defaults to False.
        :param model: The model to use for generating the response. Defaults to "o1-preview".
        :return: The generated text response as a string if response_format is "text", or a dictionary containing the response and conversation history if response_format is "json_object". Returns None if an error occurs.
        """
        start_time = time.time()
        logger.info(
            f"Function generate_chat_response_o1 started at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}"
        )

        try:
            user_message = {"role": "user", "content": query}

            messages_for_api = conversation_history + [user_message]
            logger.info(
                f"Sending request to Azure OpenAI at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
            )

            response = self.openai_client.chat.completions.create(
                model=model,
                messages=messages_for_api,
                # max_completion_tokens=max_completion_tokens,
                stream=stream,
                **kwargs,
            )

            if stream:
                response_content = ""
                for event in response:
                    if event.choices:
                        event_text = event.choices[0].delta
                        if event_text is None or event_text.content is None:
                            continue
                        print(event_text.content, end="", flush=True)
                        response_content += event_text.content
                        time.sleep(0.001)  # Maintain minimal sleep to reduce latency
            else:
                response_content = response.choices[0].message.content
                logger.info(f"Model_used: {response.model}")

            conversation_history.append(user_message)
            conversation_history.append({"role": "assistant", "content": response_content})

            end_time = time.time()
            duration = end_time - start_time
            logger.info(
                f"Function generate_chat_response_o1 finished at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))} (Duration: {duration:.2f} seconds)"
            )

            return {
                "response": response_content,
                "conversation_history": conversation_history,
            }

        except openai.APIConnectionError as e:
            logger.error("API Connection Error: The server could not be reached.")
            logger.error(f"Error details: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
        except Exception as e:
            error_message = str(e)
            if "maximum context length" in error_message:
                logger.warning(
                    "Context length exceeded, reducing conversation history and retrying."
                )
                logger.warning(f"Error details: {e}")
                return "maximum context length"
            logger.error(
                "Unexpected Error: An unexpected error occurred during contextual response generation."
            )
            logger.error(f"Error details: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    @tracer.start_as_current_span("azure_openai.generate_chat_response_no_history")
    async def generate_chat_response_no_history(
        self,
        query: str,
        system_message_content: str = "You are an AI assistant that helps people find information. Please be precise, polite, and concise.",
        temperature: float = 0.7,
        max_tokens: int = 150,
        seed: int = 42,
        top_p: float = 1.0,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: str | dict[str, Any] = "text",
        image_paths: list[str] | None = None,
        image_bytes: list[bytes] | None = None,
        **kwargs,
    ) -> str | dict[str, Any] | None:
        """
        Generates a chat response using Azure OpenAI without retaining any conversation history.

        :param query: The latest user query.
        :param system_message_content: The system message to prime the model.
        :param temperature: Controls randomness in the output.
        :param max_tokens: Maximum number of tokens to generate.
        :param seed: Random seed for deterministic output.
        :param top_p: The cumulative probability cutoff for token selection.
        :param stream: Whether to stream the response.
        :param tools: A list of tools for the model to use.
        :param tool_choice: Specifies which (if any) tool to call.
        :param response_format: Specifies the format of the response.
        :param image_paths: List of paths to images to include.
        :param image_bytes: List of bytes of images to include.
        :return: The generated response in the requested format.
        """
        with self._create_trace_context(
            name="aoai.chat_completion_no_history",
            metadata={
                "operation_type": "chat_completion",
                "has_tools": tools is not None,
                "has_images": bool(image_paths or image_bytes),
                "stream_mode": stream,
                "model": self.chat_model_name,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        ) as trace:
            try:
                if hasattr(trace, "set_attribute"):
                    trace.set_attribute(
                        SpanAttr.OPERATION_NAME.value, "aoai.chat_completion_no_history"
                    )
                    trace.set_attribute("aoai.model", self.chat_model_name)
                    trace.set_attribute("aoai.max_tokens", max_tokens)
                    trace.set_attribute("aoai.temperature", temperature)
                    trace.set_attribute("aoai.stream", stream)

                if tools is not None and tool_choice is None:
                    tool_choice = "auto"
                else:
                    # Log provided tools and tool choice for debugging if necessary.
                    pass

                # Create the system and user messages.
                system_message = {"role": "system", "content": system_message_content}
                user_message = {
                    "role": "user",
                    "content": [{"type": "text", "text": query}],
                }

                # Optionally add images if provided.
                if image_bytes:
                    for image in image_bytes:
                        encoded_image = base64.b64encode(image).decode("utf-8")
                        user_message["content"].append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_image}",
                                },
                            }
                        )
                elif image_paths:
                    if isinstance(image_paths, str):
                        image_paths = [image_paths]
                    for image_path in image_paths:
                        try:
                            with open(image_path, "rb") as image_file:
                                encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
                                mime_type, _ = mimetypes.guess_type(image_path)
                                mime_type = mime_type or "application/octet-stream"
                                user_message["content"].append(
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{mime_type};base64,{encoded_image}",
                                        },
                                    }
                                )
                        except Exception as e:
                            logger.error(f"Error processing image {image_path}: {e}")

                # Create a fresh messages list containing only the system and user messages.
                messages_for_api = [system_message, user_message]
                logger.info(
                    f"Sending request to Azure OpenAI at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
                )

                # Determine response_format parameter.
                if isinstance(response_format, str):
                    response_format_param = {"type": response_format}
                elif isinstance(response_format, dict):
                    if response_format.get("type") == "json_schema":
                        json_schema = response_format.get("json_schema", {})
                        if json_schema.get("strict", False):
                            if "name" not in json_schema or "schema" not in json_schema:
                                raise ValueError(
                                    "When 'strict' is True, 'name' and 'schema' must be provided in 'json_schema'."
                                )
                    response_format_param = response_format
                else:
                    raise ValueError("Invalid response_format. Must be a string or a dictionary.")

                # Call the Azure OpenAI client with CLIENT span for Application Map
                with tracer.start_as_current_span(
                    f"{PeerService.AZURE_OPENAI}.{GenAIOperation.CHAT}",
                    kind=SpanKind.CLIENT,
                ) as llm_span:
                    api_start_time = time.perf_counter()
                    self._set_genai_span_attributes(
                        llm_span,
                        operation=GenAIOperation.CHAT,
                        model=self.chat_model_name,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        seed=seed,
                    )

                    response = self.openai_client.chat.completions.create(
                        model=self.chat_model_name,
                        messages=messages_for_api,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        seed=seed,
                        top_p=top_p,
                        stream=stream,
                        tools=tools,
                        response_format=response_format_param,
                        tool_choice=tool_choice,
                        **kwargs,
                    )

                    # Set response attributes on the CLIENT span
                    if not stream and response:
                        self._set_genai_response_attributes(llm_span, response, api_start_time)

                # Process the response.
                if stream:
                    response_content = ""
                    for event in response:
                        if event.choices:
                            event_text = event.choices[0].delta
                            if event_text is None or event_text.content is None:
                                continue
                            print(event_text.content, end="", flush=True)
                            response_content += event_text.content
                            time.sleep(0.001)  # Minimal sleep to reduce latency
                else:
                    response_content = response.choices[0].message.content

                # Add response metrics to trace
                if hasattr(trace, "set_attribute"):
                    trace.set_attribute("aoai.response_length", len(response_content))
                    if hasattr(response, "usage") and response.usage:
                        trace.set_attribute(
                            "aoai.completion_tokens", response.usage.completion_tokens
                        )
                        trace.set_attribute("aoai.prompt_tokens", response.usage.prompt_tokens)
                        trace.set_attribute("aoai.total_tokens", response.usage.total_tokens)

                # If the desired format is a JSON object, try to parse it.
                if isinstance(response_format, str) and response_format == "json_object":
                    try:
                        parsed_response = json.loads(response_content)
                        return {"response": parsed_response}
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse response as JSON: {e}")
                        return {"response": response_content}
                else:
                    return {"response": response_content}

            except openai.APIConnectionError as e:
                if hasattr(trace, "set_attribute"):
                    trace.set_attribute(SpanAttr.ERROR_TYPE.value, "api_connection_error")
                    trace.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                logger.error("API Connection Error: The server could not be reached.")
                logger.error(f"Error details: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None
            except Exception as e:
                if hasattr(trace, "set_attribute"):
                    trace.set_attribute(SpanAttr.ERROR_TYPE.value, "unexpected_error")
                    trace.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                error_message = str(e)
                if "maximum context length" in error_message:
                    logger.warning("Context length exceeded. Consider reducing the input size.")
                    return "maximum context length"
                logger.error("Unexpected error occurred during response generation.")
                logger.error(f"Error details: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None

    @tracer.start_as_current_span("azure_openai.generate_chat_response")
    async def generate_chat_response(
        self,
        query: str,
        conversation_history: list[dict[str, str]] = [],
        image_paths: list[str] = None,
        image_bytes: list[bytes] = None,
        system_message_content: str = "You are an AI assistant that helps people find information. Please be precise, polite, and concise.",
        temperature: float = 0.7,
        max_tokens: int = 150,
        seed: int = 42,
        top_p: float = 1.0,
        stream: bool = False,
        tools: list[dict[str, Any]] = None,
        tool_choice: str | dict[str, Any] = None,
        response_format: str | dict[str, Any] = "text",
        **kwargs,
    ) -> str | dict[str, Any] | None:
        """
        Generates a text response considering the conversation history.

        :param query: The latest query to generate a response for.
        :param conversation_history: A list of message dictionaries representing the conversation history.
        :param image_paths: A list of paths to images to include in the query.
        :param image_bytes: A list of bytes of images to include in the query.
        :param system_message_content: The content of the system message. Defaults to a generic assistant message.
        :param temperature: Controls randomness in the output. Defaults to 0.7.
        :param max_tokens: Maximum number of tokens to generate. Defaults to 150.
        :param seed: Random seed for deterministic output. Defaults to 42.
        :param top_p: The cumulative probability cutoff for token selection. Defaults to 1.0.
        :param stream: Whether to stream the response. Defaults to False.
        :param tools: A list of tools the model can use.
        :param tool_choice: Controls which (if any) tool is called by the model. Can be "none", "auto", "required", or specify a particular tool.
        :param response_format: Specifies the format of the response. Can be:
            - A string: "text" or "json_object".
            - A dictionary specifying a custom response format, including a JSON schema when needed.
        :return: The generated text response as a string if response_format is "text", or a dictionary containing the response and conversation history if response_format is "json_object". Returns None if an error occurs.
        """
        start_time = time.time()
        logger.info(
            f"Function generate_chat_response started at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}"
        )

        with self._create_trace_context(
            name="aoai.chat_completion_with_history",
            metadata={
                "operation_type": "chat_completion_with_history",
                "conversation_length": len(conversation_history),
                "has_tools": tools is not None,
                "has_images": bool(image_paths or image_bytes),
                "stream_mode": stream,
                "model": self.chat_model_name,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        ) as trace:
            try:
                if hasattr(trace, "set_attribute"):
                    trace.set_attribute(
                        SpanAttr.OPERATION_NAME.value,
                        "aoai.chat_completion_with_history",
                    )
                    trace.set_attribute("aoai.model", self.chat_model_name)
                    trace.set_attribute("aoai.conversation_length", len(conversation_history))
                    trace.set_attribute("aoai.max_tokens", max_tokens)
                    trace.set_attribute("aoai.temperature", temperature)
                    trace.set_attribute("aoai.stream", stream)
                    trace.set_attribute("aoai.has_tools", tools is not None)
                    trace.set_attribute("aoai.has_images", bool(image_paths or image_bytes))

                if tools is not None and tool_choice is None:
                    logger.debug(
                        "Tools are provided but tool_choice is None. Setting tool_choice to 'auto'."
                    )
                    tool_choice = "auto"
                else:
                    logger.debug(f"Tools: {tools}, Tool Choice: {tool_choice}")

                system_message = {"role": "system", "content": system_message_content}
                if not conversation_history or conversation_history[0] != system_message:
                    conversation_history.insert(0, system_message)

                user_message = {
                    "role": "user",
                    "content": [{"type": "text", "text": query}],
                }

                if image_bytes:
                    for image in image_bytes:
                        encoded_image = base64.b64encode(image).decode("utf-8")
                        user_message["content"].append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_image}",
                                },
                            }
                        )
                elif image_paths:
                    if isinstance(image_paths, str):
                        image_paths = [image_paths]
                    for image_path in image_paths:
                        try:
                            with open(image_path, "rb") as image_file:
                                encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
                                mime_type, _ = mimetypes.guess_type(image_path)
                                logger.info(f"Image {image_path} type: {mime_type}")
                                mime_type = mime_type or "application/octet-stream"
                                user_message["content"].append(
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{mime_type};base64,{encoded_image}",
                                        },
                                    }
                                )
                        except Exception as e:
                            logger.error(f"Error processing image {image_path}: {e}")

                messages_for_api = conversation_history + [user_message]
                logger.info(
                    f"Sending request to Azure OpenAI at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
                )

                if isinstance(response_format, str):
                    response_format_param = {"type": response_format}
                elif isinstance(response_format, dict):
                    if response_format.get("type") == "json_schema":
                        json_schema = response_format.get("json_schema", {})
                        if json_schema.get("strict", False):
                            if "name" not in json_schema or "schema" not in json_schema:
                                raise ValueError(
                                    "When 'strict' is True, 'name' and 'schema' must be provided in 'json_schema'."
                                )
                    response_format_param = response_format
                else:
                    raise ValueError("Invalid response_format. Must be a string or a dictionary.")

                # Call the Azure OpenAI client with CLIENT span for Application Map
                with tracer.start_as_current_span(
                    f"{PeerService.AZURE_OPENAI}.{GenAIOperation.CHAT}",
                    kind=SpanKind.CLIENT,
                ) as llm_span:
                    api_start_time = time.perf_counter()
                    self._set_genai_span_attributes(
                        llm_span,
                        operation=GenAIOperation.CHAT,
                        model=self.chat_model_name,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        seed=seed,
                    )

                    response = self.openai_client.chat.completions.create(
                        model=self.chat_model_name,
                        messages=messages_for_api,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        seed=seed,
                        top_p=top_p,
                        stream=stream,
                        tools=tools,
                        response_format=response_format_param,
                        tool_choice=tool_choice,
                        **kwargs,
                    )

                    # Set response attributes on the CLIENT span (for non-streaming)
                    if not stream and response:
                        self._set_genai_response_attributes(llm_span, response, api_start_time)

                if stream:
                    response_content = ""
                    for event in response:
                        if event.choices:
                            event_text = event.choices[0].delta
                            if event_text is None or event_text.content is None:
                                continue
                            print(event_text.content, end="", flush=True)
                            response_content += event_text.content
                            time.sleep(0.001)  # Maintain minimal sleep to reduce latency
                else:
                    response_content = response.choices[0].message.content

                conversation_history.append(user_message)
                conversation_history.append({"role": "assistant", "content": response_content})

                end_time = time.time()
                duration = end_time - start_time
                logger.info(
                    f"Function generate_chat_response finished at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))} (Duration: {duration:.2f} seconds)"
                )

                if isinstance(response_format, str) and response_format == "json_object":
                    try:
                        parsed_response = json.loads(response_content)
                        return {
                            "response": parsed_response,
                            "conversation_history": conversation_history,
                        }
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse assistant's response as JSON: {e}")
                        return {
                            "response": response_content,
                            "conversation_history": conversation_history,
                        }
                else:
                    return {
                        "response": response_content,
                        "conversation_history": conversation_history,
                    }

            except openai.APIConnectionError as e:
                logger.error("API Connection Error: The server could not be reached.")
                logger.error(f"Error details: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None
            except Exception as e:
                error_message = str(e)
                if "maximum context length" in error_message:
                    logger.warning(
                        "Context length exceeded, reducing conversation history and retrying."
                    )
                    logger.warning(f"Error details: {e}")
                    return "maximum context length"
                logger.error(
                    "Unexpected Error: An unexpected error occurred during contextual response generation."
                )
                logger.error(f"Error details: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None

    @tracer.start_as_current_span("azure_openai.generate_embedding")
    def generate_embedding(
        self, input_text: str, model_name: str | None = None, **kwargs
    ) -> str | None:
        """
        Generates an embedding for the given input text using Azure OpenAI's Foundation models.

        :param input_text: The text to generate an embedding for.
        :param model_name: The name of the model to use for generating the embedding. If None, the default embedding model is used.
        :param kwargs: Additional parameters for the API request.
        :return: The embedding as a JSON string, or None if an error occurred.
        :raises Exception: If an error occurs while making the API request.
        """
        embedding_model = model_name or self.embedding_model_name

        with self._create_trace_context(
            name="aoai.generate_embedding",
            metadata={
                "operation_type": "embedding_generation",
                "input_length": len(input_text),
                "model": embedding_model,
            },
        ) as ctx:
            try:
                if hasattr(ctx, "set_attribute"):
                    ctx.set_attribute(SpanAttr.OPERATION_NAME.value, "aoai.generate_embedding")
                    ctx.set_attribute("aoai.model", embedding_model)
                    ctx.set_attribute("aoai.input_length", len(input_text))

                # Call the Azure OpenAI client with CLIENT span for Application Map
                with tracer.start_as_current_span(
                    f"{PeerService.AZURE_OPENAI}.{GenAIOperation.EMBEDDINGS}",
                    kind=SpanKind.CLIENT,
                ) as llm_span:
                    api_start_time = time.perf_counter()
                    self._set_genai_span_attributes(
                        llm_span,
                        operation=GenAIOperation.EMBEDDINGS,
                        model=embedding_model,
                    )

                    response = self.openai_client.embeddings.create(
                        input=input_text,
                        model=embedding_model,
                        **kwargs,
                    )

                    # Set response attributes
                    duration_ms = (time.perf_counter() - api_start_time) * 1000
                    llm_span.set_attribute(
                        SpanAttr.GENAI_CLIENT_OPERATION_DURATION.value, duration_ms
                    )

                    if hasattr(response, "usage") and response.usage:
                        llm_span.set_attribute(
                            SpanAttr.GENAI_USAGE_INPUT_TOKENS.value, response.usage.prompt_tokens
                        )
                        # Embeddings don't have output tokens, just set total
                        llm_span.set_attribute(
                            "gen_ai.usage.total_tokens", response.usage.total_tokens
                        )

                    llm_span.set_status(Status(StatusCode.OK))

                if hasattr(ctx, "set_attribute") and hasattr(response, "usage") and response.usage:
                    ctx.set_attribute("aoai.prompt_tokens", response.usage.prompt_tokens)
                    ctx.set_attribute("aoai.total_tokens", response.usage.total_tokens)

                return response
            except openai.APIConnectionError as e:
                if hasattr(ctx, "set_attribute"):
                    ctx.set_attribute(SpanAttr.ERROR_TYPE.value, "api_connection_error")
                    ctx.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                logger.error("API Connection Error: The server could not be reached.")
                logger.error(f"Error details: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None, None
            except Exception as e:
                if hasattr(ctx, "set_attribute"):
                    ctx.set_attribute(SpanAttr.ERROR_TYPE.value, "unexpected_error")
                    ctx.set_attribute(SpanAttr.ERROR_MESSAGE.value, str(e))
                logger.error(
                    "Unexpected Error: An unexpected error occurred during contextual response generation."
                )
                logger.error(f"Error details: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None, None
