"""
services/openai_client.py
-------------------------
Consolidated Azure OpenAI client with manager capabilities and telemetry.
Provides both simple client access and advanced management features including
tracing, error handling, and performance monitoring.
"""

import os
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

import openai
from azure.identity import (
    DefaultAzureCredential,
    ManagedIdentityCredential,
    get_bearer_token_provider,
)
from openai import AzureOpenAI
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from src.enums.monitoring import SpanAttr
from utils.azure_auth import get_credential
from utils.ml_logging import get_logger
from utils.trace_context import TraceContext
from dotenv import load_dotenv
import argparse
import json
import sys

logger = get_logger(__name__)
load_dotenv()

# Get tracer instance for telemetry
tracer = trace.get_tracer(__name__)

class NoOpTraceContext:
    """No-operation context manager for when tracing is disabled."""
    
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
    return (
        os.getenv("AOAI_TRACING", os.getenv("ENABLE_TRACING", "false")).lower()
        == "true"
    )

def _create_aoai_trace_context(
    name: str, call_connection_id: str = None, session_id: str = None, **kwargs
):
    """Create a TraceContext or NoOpTraceContext based on environment configuration."""
    if _is_aoai_tracing_enabled():
        return TraceContext(
            name=name,
            component="src.aoai.client",
            call_connection_id=call_connection_id,
            session_id=session_id,
            **kwargs,
        )
    else:
        return NoOpTraceContext()

def create_azure_openai_client(
    *,
    azure_endpoint: str | None = None,
    azure_api_key: str | None = None,
    azure_client_id: str | None = None,
    credential: DefaultAzureCredential | ManagedIdentityCredential | None = None,
    api_version: str = "2025-01-01-preview",
):
    """
    Create and configure Azure OpenAI client with optional overrides for configuration.

    Parameters default to environment variables when not provided.
    """
    azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_api_key = azure_api_key or os.getenv("AZURE_OPENAI_KEY")
    azure_client_id = azure_client_id or os.getenv("AZURE_CLIENT_ID")

    if not azure_endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT must be provided via argument or environment.")

    if azure_api_key:
        logger.info("Using API key authentication for Azure OpenAI")
        return AzureOpenAI(
            api_version=api_version,
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
        )

    logger.info("Using Azure AD authentication for Azure OpenAI")

    resolved_credential = credential
    if not resolved_credential:
        if azure_client_id:
            logger.info("Using user-assigned managed identity with client ID: %s", azure_client_id)
            resolved_credential = ManagedIdentityCredential(client_id=azure_client_id)
        else:
            logger.info("Using DefaultAzureCredential for Azure OpenAI authentication")
            resolved_credential = get_credential()

    try:
        azure_ad_token_provider = get_bearer_token_provider(
            resolved_credential, "https://cognitiveservices.azure.com/.default"
        )
        client = AzureOpenAI(
            api_version=api_version,
            azure_endpoint=azure_endpoint,
            azure_ad_token_provider=azure_ad_token_provider,
        )
        logger.info("Azure OpenAI client created successfully with Azure AD authentication")
        return client
    except Exception as exc:
        logger.error("Failed to create Azure OpenAI client with Azure AD: %s", exc)
        logger.info("Falling back to DefaultAzureCredential")
        fallback_credential = get_credential()
        azure_ad_token_provider = get_bearer_token_provider(
            fallback_credential, "https://cognitiveservices.azure.com/.default"
        )
        return AzureOpenAI(
            api_version=api_version,
            azure_endpoint=azure_endpoint,
            azure_ad_token_provider=azure_ad_token_provider,
        )

class AzureOpenAIManager:
    """Enhanced Azure OpenAI manager with telemetry and advanced features."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        completion_model_name: Optional[str] = None,
        chat_model_name: Optional[str] = None,
        embedding_model_name: Optional[str] = None,
        dalle_model_name: Optional[str] = None,
        whisper_model_name: Optional[str] = None,
        call_connection_id: Optional[str] = None,
        session_id: Optional[str] = None,
        enable_tracing: Optional[bool] = None,
    ):
        """Initialize the Azure OpenAI Manager with telemetry capabilities."""
        self.api_key = api_key or os.getenv("AZURE_OPENAI_KEY")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION") or "2025-01-01-preview"
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        
        self.completion_model_name = completion_model_name or os.getenv("AZURE_AOAI_COMPLETION_MODEL_DEPLOYMENT_ID")
        self.chat_model_name = chat_model_name or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_ID")
        self.embedding_model_name = embedding_model_name or os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        self.dalle_model_name = dalle_model_name or os.getenv("AZURE_AOAI_DALLE_MODEL_DEPLOYMENT_ID")
        self.whisper_model_name = whisper_model_name or os.getenv("AZURE_AOAI_WHISPER_MODEL_DEPLOYMENT_ID")
        
        # Tracing context
        self.call_connection_id = call_connection_id
        self.session_id = session_id
        self.enable_tracing = enable_tracing if enable_tracing is not None else _is_aoai_tracing_enabled()
        
        # Initialize client
        self.openai_client = create_azure_openai_client(
            azure_endpoint=self.azure_endpoint,
            azure_api_key=self.api_key,
            api_version=self.api_version
        )
        
        self._validate_api_configurations()
    
    def _create_trace_context(self, name: str, **kwargs):
        """Create trace context for operations."""
        if self.enable_tracing:
            return TraceContext(
                name=name,
                component="src.aoai.client",
                call_connection_id=self.call_connection_id,
                session_id=self.session_id,
                **kwargs,
            )
        else:
            return NoOpTraceContext()
    
    def _validate_api_configurations(self):
        """Validate API configurations."""
        if not self.azure_endpoint:
            raise ValueError("Azure OpenAI endpoint must be configured")
    
    def get_azure_openai_client(self):
        """Get the underlying OpenAI client."""
        return self.openai_client
    
    @tracer.start_as_current_span("azure_openai.generate_chat_response")
    async def generate_chat_response(
        self,
        query: str,
        conversation_history: List[Dict[str, str]] = None,
        system_message_content: str = "You are an AI assistant that helps people find information. Please be precise, polite, and concise.",
        temperature: float = 0.7,
        max_tokens: int = 150,
        seed: int = 42,
        top_p: float = 1.0,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Union[str, Dict[str, Any]] = "text",
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[Union[str, Dict[str, Any]]]:
        """Generate chat response with telemetry and error handling."""
        start_time = time.time()
        conversation_history = conversation_history or []
        model = model or self.chat_model_name
        
        with self._create_trace_context(
            "azure_openai.generate_chat_response",
            metadata={
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream,
            }
        ) as trace_ctx:
            try:
                messages_for_api = [
                    {"role": "system", "content": system_message_content}
                ] + conversation_history + [
                    {"role": "user", "content": query}
                ]
                
                trace_ctx.set_attribute("messages.count", len(messages_for_api))
                
                response = self.openai_client.chat.completions.create(
                    model=model,
                    messages=messages_for_api,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    seed=seed,
                    top_p=top_p,
                    stream=stream,
                    tools=tools,
                    tool_choice=tool_choice,
                    response_format=response_format,
                    **kwargs
                )
                
                duration = time.time() - start_time
                trace_ctx.set_attribute("duration_ms", duration * 1000)
                
                if stream:
                    return response
                else:
                    response_content = response.choices[0].message.content
                    trace_ctx.set_attribute("response.tokens", response.usage.total_tokens if response.usage else 0)
                    
                    logger.info(
                        "Chat completion generated successfully",
                        extra={
                            "model": model,
                            "duration_ms": duration * 1000,
                            "tokens": response.usage.total_tokens if response.usage else 0,
                            "session_id": self.session_id,
                            "call_connection_id": self.call_connection_id,
                        }
                    )
                    
                    return response_content
                    
            except openai.RateLimitError as e:
                duration = time.time() - start_time
                trace_ctx.record_exception(e)
                trace_ctx.set_attribute("error.type", "rate_limit")
                trace_ctx.set_attribute("duration_ms", duration * 1000)
                
                logger.warning(
                    "Azure OpenAI rate limit exceeded (429)",
                    extra={
                        "error": str(e),
                        "model": model,
                        "duration_ms": duration * 1000,
                        "session_id": self.session_id,
                        "call_connection_id": self.call_connection_id,
                    }
                )
                raise
                
            except openai.APIConnectionError as e:
                duration = time.time() - start_time
                trace_ctx.record_exception(e)
                trace_ctx.set_attribute("error.type", "connection")
                trace_ctx.set_attribute("duration_ms", duration * 1000)
                
                logger.error(
                    "Azure OpenAI API connection error",
                    extra={
                        "error": str(e),
                        "model": model,
                        "duration_ms": duration * 1000,
                        "session_id": self.session_id,
                        "call_connection_id": self.call_connection_id,
                    }
                )
                raise
                
            except Exception as e:
                duration = time.time() - start_time
                trace_ctx.record_exception(e)
                trace_ctx.set_attribute("error.type", "unexpected")
                trace_ctx.set_attribute("duration_ms", duration * 1000)
                
                logger.error(
                    "Unexpected error in Azure OpenAI chat completion",
                    extra={
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "model": model,
                        "duration_ms": duration * 1000,
                        "session_id": self.session_id,
                        "call_connection_id": self.call_connection_id,
                    }
                )
                raise
    
    @tracer.start_as_current_span("azure_openai.generate_embedding")
    def generate_embedding(
        self, 
        input_text: str, 
        model_name: Optional[str] = None, 
        **kwargs
    ) -> Optional[List[float]]:
        """Generate embedding with telemetry."""
        start_time = time.time()
        model_name = model_name or self.embedding_model_name
        
        with self._create_trace_context(
            "azure_openai.generate_embedding",
            metadata={"model": model_name, "input_length": len(input_text)}
        ) as trace_ctx:
            try:
                response = self.openai_client.embeddings.create(
                    input=input_text,
                    model=model_name,
                    **kwargs
                )
                
                duration = time.time() - start_time
                trace_ctx.set_attribute("duration_ms", duration * 1000)
                trace_ctx.set_attribute("embedding.dimension", len(response.data[0].embedding))
                
                logger.info(
                    "Embedding generated successfully",
                    extra={
                        "model": model_name,
                        "duration_ms": duration * 1000,
                        "input_length": len(input_text),
                        "session_id": self.session_id,
                        "call_connection_id": self.call_connection_id,
                    }
                )
                
                return response.data[0].embedding
                
            except Exception as e:
                duration = time.time() - start_time
                trace_ctx.record_exception(e)
                trace_ctx.set_attribute("duration_ms", duration * 1000)
                
                logger.error(
                    "Error generating embedding",
                    extra={
                        "error": str(e),
                        "model": model_name,
                        "duration_ms": duration * 1000,
                        "session_id": self.session_id,
                        "call_connection_id": self.call_connection_id,
                    }
                )
                raise
    
    @tracer.start_as_current_span("azure_openai.transcribe_audio")
    def transcribe_audio_with_whisper(
        self,
        audio_file_path: str,
        language: str = "en",
        prompt: str = "Transcribe the following audio file to text.",
        response_format: Literal["json", "text", "srt", "verbose_json", "vtt"] = "text",
        temperature: float = 0.5,
        timestamp_granularities: List[Literal["word", "segment"]] = None,
        **kwargs
    ):
        """Transcribe audio with Whisper model and telemetry."""
        start_time = time.time()
        timestamp_granularities = timestamp_granularities or []
        model = self.whisper_model_name
        
        with self._create_trace_context(
            "azure_openai.transcribe_audio",
            metadata={
                "model": model,
                "language": language,
                "response_format": response_format,
            }
        ) as trace_ctx:
            try:
                with open(audio_file_path, "rb") as audio_file:
                    response = self.openai_client.audio.transcriptions.create(
                        file=audio_file,
                        model=model,
                        language=language,
                        prompt=prompt,
                        response_format=response_format,
                        temperature=temperature,
                        timestamp_granularities=timestamp_granularities,
                        **kwargs
                    )
                
                duration = time.time() - start_time
                trace_ctx.set_attribute("duration_ms", duration * 1000)
                
                logger.info(
                    "Audio transcription completed successfully",
                    extra={
                        "model": model,
                        "duration_ms": duration * 1000,
                        "language": language,
                        "response_format": response_format,
                        "session_id": self.session_id,
                        "call_connection_id": self.call_connection_id,
                    }
                )
                
                return response
                
            except Exception as e:
                duration = time.time() - start_time
                trace_ctx.record_exception(e)
                trace_ctx.set_attribute("duration_ms", duration * 1000)
                
                logger.error(
                    "Error transcribing audio",
                    extra={
                        "error": str(e),
                        "model": model,
                        "duration_ms": duration * 1000,
                        "audio_file": audio_file_path,
                        "session_id": self.session_id,
                        "call_connection_id": self.call_connection_id,
                    }
                )
                raise

def main() -> None:
    """
    Execute a synchronous smoke test to confirm Azure OpenAI access and optionally run a prompt.

    Inputs:
        Optional CLI --prompt for test content and --deployment override.

    Outputs:
        Logs discovered deployments or prompt response; writes prompt response to stdout.

    Latency:
        Bounded by one control-plane list request or a single prompt inference round trip.
    """

    parser = argparse.ArgumentParser(description="Azure OpenAI client smoke test utility.")
    parser.add_argument(
        "--prompt",
        type=str,
        help="Optional prompt to send to the Azure OpenAI deployment for validation.",
    )
    parser.add_argument(
        "--deployment",
        type=str,
        default=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        help="Azure OpenAI deployment name; defaults to AZURE_OPENAI_DEPLOYMENT.",
    )
    args = parser.parse_args()

    local_client = create_azure_openai_client()
    if not args.prompt:
        try:
            response = local_client.models.list()
            deployments = [model.id for model in getattr(response, "data", [])]
            logger.info("Azure OpenAI deployments discovered", extra={"deployments": deployments})
        except Exception as exc:
            logger.error("Azure OpenAI smoke test failed", extra={"error": str(exc)})
            raise
        return

    if not args.deployment:
        raise ValueError(
            "A deployment name must be supplied via --deployment or AZURE_OPENAI_DEPLOYMENT."
        )

    try:
        response = local_client.responses.create(
            model=args.deployment,
            input=args.prompt,
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            output_segments = []
            for item in getattr(response, "output", []):
                for segment in getattr(item, "content", []):
                    text = getattr(segment, "text", None)
                    if text:
                        output_segments.append(text)
            output_text = " ".join(output_segments)
        logger.info(
            "Azure OpenAI prompt test succeeded",
            extra={"deployment": args.deployment, "response": output_text},
        )
        print(output_text or json.dumps(response.model_dump(), default=str), file=sys.stdout)
    except Exception as exc:
        logger.error(
            "Azure OpenAI prompt test failed",
            extra={"deployment": args.deployment, "error": str(exc)},
        )
        raise

# Create default client instance
client = create_azure_openai_client()

# Create default manager instance
default_manager = AzureOpenAIManager()

__all__ = [
    "client", 
    "create_azure_openai_client", 
    "AzureOpenAIManager", 
    "default_manager",
    "_is_aoai_tracing_enabled",
    "_create_aoai_trace_context"
]
