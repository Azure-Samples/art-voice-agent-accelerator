"""
Usage examples and integration helpers for LatencyToolV2.

This module demonstrates how to integrate the v2 latency tool with existing
voice agent code and provides practical examples for different scenarios.
"""

from __future__ import annotations

import asyncio
from typing import Any

from opentelemetry import trace
from utils.ml_logging import get_logger

from src.tools.latency_tool_v2 import LatencyToolV2

logger = get_logger("tools.latency_v2_examples")


class VoiceAgentLatencyIntegration:
    """
    Example integration of LatencyToolV2 with a voice agent.

    Shows how to instrument a complete voice interaction flow
    with detailed latency tracking.
    """

    def __init__(self, tracer: trace.Tracer):
        self.latency_tool = LatencyToolV2(tracer)

    async def handle_voice_interaction(
        self,
        call_connection_id: str,
        session_id: str,
        audio_data: bytes,
        user_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Example of handling a complete voice interaction with latency tracking.

        This demonstrates the full flow:
        1. Process user speech input
        2. Generate LLM response
        3. Synthesize speech
        4. Deliver to client
        """

        # Create a conversation turn tracker
        with self.latency_tool.track_conversation_turn(
            call_connection_id=call_connection_id,
            session_id=session_id,
        ) as tracker:

            # Add custom metadata
            tracker.add_metadata("user_context_keys", list(user_context.keys()))
            tracker.add_metadata("audio_size_bytes", len(audio_data))

            # 1. Process user speech input (STT)
            with tracker.track_user_input("speech") as input_span:
                input_span.add_event("stt.processing_started", {"audio_size": len(audio_data)})

                # Simulate STT processing
                user_text = await self._process_speech_to_text(audio_data)

                input_span.add_event("stt.processing_completed", {"text_length": len(user_text)})
                input_span.set_attribute("stt.text_length", len(user_text))

            # 2. Generate LLM response
            prompt_tokens = self._estimate_prompt_tokens(user_text, user_context)

            with tracker.track_llm_inference("gpt-4-turbo", prompt_tokens) as (
                llm_span,
                mark_first_token,
            ):
                llm_span.add_event("llm.request_started", {"prompt_tokens": prompt_tokens})

                # Simulate LLM call with streaming
                response_text = ""
                first_token_received = False

                async for chunk in self._generate_llm_response(user_text, user_context):
                    if not first_token_received:
                        mark_first_token()
                        first_token_received = True
                        llm_span.add_event("llm.first_token_received")

                    response_text += chunk
                    llm_span.add_event("llm.token_chunk_received", {"chunk_length": len(chunk)})

                # Set completion tokens
                completion_tokens = self._estimate_completion_tokens(response_text)
                tracker.set_llm_completion_tokens(completion_tokens)

                llm_span.add_event(
                    "llm.request_completed",
                    {"completion_tokens": completion_tokens, "response_length": len(response_text)},
                )

            # 3. Synthesize speech (TTS)
            with tracker.track_tts_synthesis(len(response_text), "en-US-EmmaNeural") as (
                tts_span,
                mark_chunk,
            ):
                tts_span.add_event("tts.synthesis_started", {"text_length": len(response_text)})

                audio_chunks = []
                total_audio_duration = 0.0

                # Simulate TTS streaming
                async for audio_chunk, chunk_duration in self._synthesize_text_to_speech(
                    response_text
                ):
                    audio_chunks.append(audio_chunk)
                    total_audio_duration += chunk_duration

                    mark_chunk(chunk_duration)
                    tts_span.add_event(
                        "tts.chunk_synthesized",
                        {
                            "chunk_size": len(audio_chunk),
                            "chunk_duration_ms": chunk_duration * 1000,
                        },
                    )

                # Set total audio duration
                tracker.set_tts_audio_duration(total_audio_duration)

                tts_span.add_event(
                    "tts.synthesis_completed",
                    {
                        "total_chunks": len(audio_chunks),
                        "total_audio_duration_ms": total_audio_duration * 1000,
                    },
                )

            # 4. Deliver to client
            with tracker.track_network_delivery("websocket") as delivery_span:
                delivery_span.add_event("delivery.started", {"chunk_count": len(audio_chunks)})

                # Simulate network delivery
                await self._deliver_audio_to_client(audio_chunks, call_connection_id)

                delivery_span.add_event("delivery.completed")

            # Get final metrics summary
            metrics = tracker.get_metrics_summary()

            logger.info(
                "Voice interaction completed",
                extra={
                    "turn_id": metrics["turn_id"],
                    "total_duration_ms": metrics["durations"]["total_turn_ms"],
                    "llm_tokens_per_second": metrics["llm_metrics"]["tokens_per_second"],
                    "tts_chars_per_second": metrics["tts_metrics"]["synthesis_chars_per_second"],
                },
            )

            return {
                "response_text": response_text,
                "audio_chunks": audio_chunks,
                "metrics": metrics,
            }

    async def _process_speech_to_text(self, audio_data: bytes) -> str:
        """Simulate STT processing with realistic delay."""
        await asyncio.sleep(0.5)  # Simulate STT latency
        return "Hello, I need help with my insurance claim."

    async def _generate_llm_response(self, user_text: str, context: dict[str, Any]):
        """Simulate streaming LLM response generation."""
        response = "I'd be happy to help you with your insurance claim. Let me gather some information first."

        # Simulate streaming with chunks
        words = response.split()
        for i in range(0, len(words), 3):  # 3 words per chunk
            chunk = " ".join(words[i : i + 3]) + " "
            await asyncio.sleep(0.1)  # Simulate token generation delay
            yield chunk

    async def _synthesize_text_to_speech(self, text: str):
        """Simulate streaming TTS synthesis."""
        # Simulate breaking text into sentences
        sentences = text.split(". ")

        for sentence in sentences:
            if not sentence.strip():
                continue

            # Simulate TTS processing time
            await asyncio.sleep(0.3)

            # Simulate audio chunk (would be actual audio bytes in real implementation)
            audio_chunk = f"audio_for_{sentence}".encode()
            chunk_duration = len(sentence) * 0.05  # ~50ms per character

            yield audio_chunk, chunk_duration

    async def _deliver_audio_to_client(self, audio_chunks: list, call_connection_id: str):
        """Simulate network delivery of audio chunks."""
        for chunk in audio_chunks:
            await asyncio.sleep(0.02)  # Simulate network latency per chunk

    def _estimate_prompt_tokens(self, user_text: str, context: dict[str, Any]) -> int:
        """Rough estimation of prompt tokens."""
        # Simple estimation: ~1 token per 4 characters
        context_size = sum(len(str(v)) for v in context.values())
        return (len(user_text) + context_size) // 4

    def _estimate_completion_tokens(self, response_text: str) -> int:
        """Rough estimation of completion tokens."""
        return len(response_text) // 4


class BatchLatencyAnalyzer:
    """
    Example utility for analyzing latency patterns across multiple turns.

    This would typically integrate with your monitoring/analytics system
    to provide insights into performance trends and bottlenecks.
    """

    def __init__(self):
        self.turn_metrics: list[dict[str, Any]] = []

    def record_turn_metrics(self, metrics: dict[str, Any]):
        """Record metrics from a conversation turn."""
        self.turn_metrics.append(metrics)

    def analyze_latency_patterns(self) -> dict[str, Any]:
        """Analyze collected metrics to identify patterns and bottlenecks."""
        if not self.turn_metrics:
            return {"error": "No metrics available"}

        # Calculate averages and percentiles
        total_durations = [
            m["durations"]["total_turn_ms"]
            for m in self.turn_metrics
            if m["durations"]["total_turn_ms"]
        ]
        llm_durations = [
            m["durations"]["llm_inference_ms"]
            for m in self.turn_metrics
            if m["durations"]["llm_inference_ms"]
        ]
        tts_durations = [
            m["durations"]["tts_synthesis_ms"]
            for m in self.turn_metrics
            if m["durations"]["tts_synthesis_ms"]
        ]

        analysis = {
            "total_turns": len(self.turn_metrics),
            "avg_total_duration_ms": (
                sum(total_durations) / len(total_durations) if total_durations else 0
            ),
            "avg_llm_duration_ms": sum(llm_durations) / len(llm_durations) if llm_durations else 0,
            "avg_tts_duration_ms": sum(tts_durations) / len(tts_durations) if tts_durations else 0,
        }

        # Calculate percentiles if we have enough data
        if len(total_durations) >= 10:
            sorted_total = sorted(total_durations)
            analysis["p50_total_duration_ms"] = sorted_total[len(sorted_total) // 2]
            analysis["p95_total_duration_ms"] = sorted_total[int(len(sorted_total) * 0.95)]

        # Identify potential bottlenecks
        bottlenecks = []
        if analysis["avg_llm_duration_ms"] > analysis["avg_total_duration_ms"] * 0.6:
            bottlenecks.append("LLM inference is taking >60% of total turn time")
        if analysis["avg_tts_duration_ms"] > analysis["avg_total_duration_ms"] * 0.4:
            bottlenecks.append("TTS synthesis is taking >40% of total turn time")

        analysis["potential_bottlenecks"] = bottlenecks

        return analysis


# Example usage in a FastAPI WebSocket handler
async def example_websocket_handler_with_latency_tracking(websocket, tracer: trace.Tracer):
    """
    Example of how to integrate v2 latency tracking in a WebSocket handler.
    """
    integration = VoiceAgentLatencyIntegration(tracer)

    while True:
        try:
            # Receive audio data from client
            audio_data = await websocket.receive_bytes()

            # Extract correlation IDs (would come from your session management)
            call_connection_id = "example_call_123"
            session_id = "example_session_456"
            user_context = {"user_id": "user_789", "intent": "claim_help"}

            # Process with latency tracking
            result = await integration.handle_voice_interaction(
                call_connection_id=call_connection_id,
                session_id=session_id,
                audio_data=audio_data,
                user_context=user_context,
            )

            # Send response back to client
            for audio_chunk in result["audio_chunks"]:
                await websocket.send_bytes(audio_chunk)

            # Log performance metrics
            metrics = result["metrics"]
            logger.info(
                f"Turn completed - Total: {metrics['durations']['total_turn_ms']:.1f}ms, "
                f"LLM: {metrics['durations']['llm_inference_ms']:.1f}ms, "
                f"TTS: {metrics['durations']['tts_synthesis_ms']:.1f}ms"
            )

        except Exception as e:
            logger.error(f"Error in voice interaction: {e}")
            break


# Example of how to set up the latency tool with existing tracer
def setup_latency_tool_v2(existing_tracer: trace.Tracer) -> LatencyToolV2:
    """
    Set up the v2 latency tool with an existing OpenTelemetry tracer.

    This should be called during application startup after the tracer
    is configured with proper Resource settings.
    """
    latency_tool = LatencyToolV2(existing_tracer)

    logger.info("LatencyToolV2 initialized with OpenTelemetry integration")

    return latency_tool
