#!/usr/bin/env python3
"""
Realistic Conversation Simulator for Agent Flow Testing
=======================================================

Simulates realistic human-AI conversations based on actual speech patterns
observed in the server logs to enable proper load testing and agent evaluation.
"""

import asyncio
import base64
import json
import random
import ssl
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import websockets

# No longer need audio generator - using pre-cached PCM files


def generate_silence_chunk(duration_ms: float = 100.0, sample_rate: int = 16000) -> bytes:
    """Generate a silent audio chunk with very low-level noise for VAD continuity."""
    samples = int((duration_ms / 1000.0) * sample_rate)
    # Generate very quiet background noise instead of pure silence
    # This is more realistic and helps trigger final speech recognition

    audio_data = bytearray()
    for _ in range(samples):
        # Add very quiet random noise (-10 to +10 amplitude in 16-bit range)
        noise = random.randint(-10, 10)
        audio_data.extend(struct.pack("<h", noise))
    return bytes(audio_data)


class ConversationPhase(Enum):
    GREETING = "greeting"
    AUTHENTICATION = "authentication"
    INQUIRY = "inquiry"
    CLARIFICATION = "clarification"
    RESOLUTION = "resolution"
    FAREWELL = "farewell"


@dataclass
class ConversationTurn:
    """Represents a single turn in a conversation."""

    speaker: str  # "user" or "agent"
    text: str
    phase: ConversationPhase
    delay_before_ms: int = 500  # Pause before speaking
    speech_duration_ms: int | None = None  # Override calculated duration
    interruption_likely: bool = False  # Whether agent might interrupt


@dataclass
class ConversationTemplate:
    """Template for a complete conversation flow."""

    name: str
    description: str
    turns: list[ConversationTurn]
    expected_agent: str = "AuthAgent"
    success_indicators: list[str] = field(default_factory=list)


@dataclass
class TurnMetrics:
    """Detailed metrics for a single conversation turn."""

    turn_number: int
    turn_text: str
    audio_send_start_time: float
    audio_send_complete_time: float
    first_response_time: float
    last_audio_chunk_time: float
    turn_complete_time: float

    # Calculated metrics
    audio_send_duration_ms: float = 0
    speech_recognition_latency_ms: float = 0  # Time from audio end to first response
    agent_processing_latency_ms: float = 0  # Time from first to last response
    end_to_end_latency_ms: float = 0  # Total turn time

    # Audio metrics
    audio_chunks_sent: int = 0
    audio_chunks_received: int = 0
    audio_bytes_sent: int = 0

    # Success metrics
    turn_successful: bool = False
    error_message: str = ""

    # NEW: Text and audio capture for conversation analysis
    user_speech_recognized: str = ""  # What the system heard from user
    agent_text_responses: list[str] = field(default_factory=list)  # Agent text responses
    agent_audio_responses: list[bytes] = field(default_factory=list)  # Agent audio data
    full_responses_received: list[dict[str, Any]] = field(default_factory=list)  # All raw responses

    def calculate_metrics(self):
        """Calculate derived metrics from timestamps."""
        self.audio_send_duration_ms = (
            self.audio_send_complete_time - self.audio_send_start_time
        ) * 1000

        if self.first_response_time > 0:
            self.speech_recognition_latency_ms = (
                self.first_response_time - self.audio_send_complete_time
            ) * 1000

        if self.last_audio_chunk_time > 0 and self.first_response_time > 0:
            self.agent_processing_latency_ms = (
                self.last_audio_chunk_time - self.first_response_time
            ) * 1000

        self.end_to_end_latency_ms = (self.turn_complete_time - self.audio_send_start_time) * 1000


@dataclass
class ConversationMetrics:
    """Enhanced metrics collected during conversation simulation with detailed per-turn tracking."""

    session_id: str
    template_name: str
    start_time: float
    end_time: float
    connection_time_ms: float

    # Per-turn detailed metrics
    turn_metrics: list[TurnMetrics] = field(default_factory=list)

    # Legacy aggregate metrics (for backward compatibility)
    user_turns: int = 0
    agent_turns: int = 0
    total_speech_recognition_time_ms: float = 0
    total_agent_processing_time_ms: float = 0
    total_tts_time_ms: float = 0

    # Quality metrics
    successful_turns: int = 0
    failed_turns: int = 0
    interruptions_detected: int = 0
    barge_ins_detected: int = 0

    # Server responses
    server_responses: list[dict[str, Any]] = field(default_factory=list)
    audio_chunks_received: int = 0
    errors: list[str] = field(default_factory=list)

    def get_turn_statistics(self) -> dict[str, Any]:
        """Calculate detailed per-turn statistics."""
        if not self.turn_metrics:
            return {}

        # Extract metrics for successful turns only
        successful_turns = [t for t in self.turn_metrics if t.turn_successful]

        if not successful_turns:
            return {"error": "No successful turns to analyze"}

        # Per-turn latency arrays
        speech_recognition_latencies = [
            t.speech_recognition_latency_ms
            for t in successful_turns
            if t.speech_recognition_latency_ms > 0
        ]
        agent_processing_latencies = [
            t.agent_processing_latency_ms
            for t in successful_turns
            if t.agent_processing_latency_ms > 0
        ]
        end_to_end_latencies = [t.end_to_end_latency_ms for t in successful_turns]
        audio_send_durations = [t.audio_send_duration_ms for t in successful_turns]

        import statistics

        def calculate_percentiles(data: list[float]) -> dict[str, float]:
            """Calculate comprehensive percentile statistics."""
            if not data:
                return {}

            sorted_data = sorted(data)
            n = len(sorted_data)

            return {
                "count": n,
                "min": min(sorted_data),
                "max": max(sorted_data),
                "mean": statistics.mean(sorted_data),
                "median": statistics.median(sorted_data),
                "p75": sorted_data[int(0.75 * n)] if n > 0 else 0,
                "p90": sorted_data[int(0.90 * n)] if n > 0 else 0,
                "p95": sorted_data[int(0.95 * n)] if n > 0 else 0,
                "p99": sorted_data[int(0.99 * n)] if n > 0 else 0,
                "stddev": statistics.stdev(sorted_data) if n > 1 else 0,
            }

        return {
            "total_turns": len(self.turn_metrics),
            "successful_turns": len(successful_turns),
            "failed_turns": len(self.turn_metrics) - len(successful_turns),
            "success_rate_percent": (len(successful_turns) / len(self.turn_metrics)) * 100,
            # Detailed latency statistics
            "speech_recognition_latency_ms": calculate_percentiles(speech_recognition_latencies),
            "agent_processing_latency_ms": calculate_percentiles(agent_processing_latencies),
            "end_to_end_latency_ms": calculate_percentiles(end_to_end_latencies),
            "audio_send_duration_ms": calculate_percentiles(audio_send_durations),
            # Per-turn breakdown
            "per_turn_details": [
                {
                    "turn": t.turn_number,
                    "text": t.turn_text[:50] + "..." if len(t.turn_text) > 50 else t.turn_text,
                    "successful": t.turn_successful,
                    "speech_recognition_ms": round(t.speech_recognition_latency_ms, 1),
                    "agent_processing_ms": round(t.agent_processing_latency_ms, 1),
                    "end_to_end_ms": round(t.end_to_end_latency_ms, 1),
                    "audio_chunks_received": t.audio_chunks_received,
                    "error": t.error_message,
                }
                for t in self.turn_metrics
            ],
        }


class ProductionSpeechGenerator:
    """Streams pre-cached PCM audio files for load testing with configurable conversation depth."""

    def __init__(self, cache_dir: str = "audio_cache", conversation_turns: int = 5):
        """Initialize with cached PCM files directory and conversation depth."""
        import os
        from pathlib import Path

        # Handle relative paths by making them relative to the script location
        if not os.path.isabs(cache_dir):
            script_dir = Path(__file__).parent
            self.cache_dir = script_dir / cache_dir.replace("tests/load/", "")
        else:
            self.cache_dir = Path(cache_dir)

        self.conversation_turns = conversation_turns

        # Load all available PCM files
        self.pcm_files = list(self.cache_dir.glob("*.pcm"))
        self.current_file_index = 0

        # Organize files by scenario if they follow naming convention
        self.scenario_files = {}
        self.generic_files = []

        for pcm_file in self.pcm_files:
            if "_turn_" in pcm_file.name:
                # Parse scenario-based filename: scenario_turn_X_of_Y_hash.pcm
                parts = pcm_file.name.split("_")
                if len(parts) >= 4:
                    scenario = "_".join(parts[:-4])  # Everything before _turn_X_of_Y
                    if scenario not in self.scenario_files:
                        self.scenario_files[scenario] = []
                    self.scenario_files[scenario].append(pcm_file)
                else:
                    self.generic_files.append(pcm_file)
            else:
                self.generic_files.append(pcm_file)

        # Sort scenario files by turn number
        for scenario in self.scenario_files:
            self.scenario_files[scenario].sort(key=lambda f: self._extract_turn_number(f.name))

        print(f"📁 Found {len(self.pcm_files)} cached PCM files")
        print(
            f"📋 Scenarios available: {list(self.scenario_files.keys()) if self.scenario_files else 'None (using generic files)'}"
        )
        print(f"🔄 Conversation turns configured: {conversation_turns}")

        if not self.pcm_files:
            print("⚠️  Warning: No PCM files found in audio cache directory")

    def _extract_turn_number(self, filename: str) -> int:
        """Extract turn number from filename like 'scenario_turn_3_of_5_hash.pcm'."""
        try:
            parts = filename.split("_")
            for i, part in enumerate(parts):
                if part == "turn" and i + 1 < len(parts):
                    return int(parts[i + 1])
        except (ValueError, IndexError):
            pass
        return 0

    def get_conversation_audio_sequence(
        self, scenario: str = None, max_turns: int = None
    ) -> list[bytes]:
        """Get a sequence of audio files for a complete conversation."""
        max_turns = max_turns or self.conversation_turns
        audio_sequence = []

        if scenario and scenario in self.scenario_files:
            # Use scenario-specific files
            available_files = self.scenario_files[scenario][:max_turns]
            print(f"📋 Using {len(available_files)} files from scenario: {scenario}")

            for pcm_file in available_files:
                try:
                    audio_bytes = pcm_file.read_bytes()
                    audio_sequence.append(audio_bytes)
                    duration_s = len(audio_bytes) / (16000 * 2)
                    print(f"    📄 {pcm_file.name}: {len(audio_bytes)} bytes ({duration_s:.2f}s)")
                except Exception as e:
                    print(f"    ❌ Failed to read {pcm_file}: {e}")
        else:
            # Use generic files, cycling if needed
            files_to_use = min(max_turns, len(self.generic_files)) if self.generic_files else 0

            if files_to_use == 0:
                print("❌ No audio files available")
                return []

            print(f"📄 Using {files_to_use} generic files (cycling if needed)")

            for i in range(max_turns):
                file_index = i % len(self.generic_files)
                pcm_file = self.generic_files[file_index]

                try:
                    audio_bytes = pcm_file.read_bytes()
                    audio_sequence.append(audio_bytes)
                    duration_s = len(audio_bytes) / (16000 * 2)
                    print(f"    📄 Turn {i+1}: {pcm_file.name} ({duration_s:.2f}s)")
                except Exception as e:
                    print(f"    ❌ Failed to read {pcm_file}: {e}")
                    break

        return audio_sequence

    def get_next_audio(self) -> bytes:
        """Get the next available PCM audio file, cycling through available files."""
        if not self.pcm_files:
            print("❌ No PCM files available")
            return b""

        # Get current file and advance index (cycle through files)
        pcm_file = self.pcm_files[self.current_file_index]
        self.current_file_index = (self.current_file_index + 1) % len(self.pcm_files)

        try:
            audio_bytes = pcm_file.read_bytes()
            duration_s = len(audio_bytes) / (16000 * 2)  # 16kHz, 16-bit
            print(
                f"📄 Using cached audio: {pcm_file.name} ({len(audio_bytes)} bytes, {duration_s:.2f}s)"
            )
            return audio_bytes
        except Exception as e:
            print(f"❌ Failed to read PCM file {pcm_file}: {e}")
            return b""


class ConversationTemplates:
    """Simplified conversation templates - 2 core scenarios for detailed analysis."""

    @staticmethod
    def get_insurance_inquiry() -> ConversationTemplate:
        """Standard insurance inquiry conversation - 5 turns."""
        return ConversationTemplate(
            name="insurance_inquiry",
            description="Customer calling to ask about insurance coverage - 5 turns",
            turns=[
                ConversationTurn(
                    "user",
                    "Hello, my name is Alice Brown, my social is 1234, and my zip code is 60601",
                    ConversationPhase.GREETING,
                    delay_before_ms=1000,
                ),
                ConversationTurn(
                    "user",
                    "I'm calling about my auto insurance policy",
                    ConversationPhase.INQUIRY,
                    delay_before_ms=2000,
                ),
                ConversationTurn(
                    "user",
                    "I need to understand what's covered under my current plan",
                    ConversationPhase.CLARIFICATION,
                    delay_before_ms=1500,
                ),
                ConversationTurn(
                    "user",
                    "What happens if I get into an accident?",
                    ConversationPhase.INQUIRY,
                    delay_before_ms=800,
                ),
                ConversationTurn(
                    "user",
                    "Thank you for all the information, that's very helpful",
                    ConversationPhase.FAREWELL,
                    delay_before_ms=1200,
                ),
            ],
            expected_agent="AuthAgent",
            success_indicators=["insurance", "policy", "coverage", "help"],
        )

    @staticmethod
    def get_quick_question() -> ConversationTemplate:
        """Short, quick question scenario - 3 turns."""
        return ConversationTemplate(
            name="quick_question",
            description="Brief customer inquiry - 3 turns",
            turns=[
                ConversationTurn(
                    "user",
                    "Hi there, I have a quick question",
                    ConversationPhase.GREETING,
                    delay_before_ms=500,
                ),
                ConversationTurn(
                    "user",
                    "Can you help me check my account balance?",
                    ConversationPhase.INQUIRY,
                    delay_before_ms=800,
                ),
                ConversationTurn(
                    "user",
                    "Thanks, that's all I needed to know",
                    ConversationPhase.FAREWELL,
                    delay_before_ms=1000,
                ),
            ],
            expected_agent="AuthAgent",
            success_indicators=["account", "help"],
        )

    @staticmethod
    def get_all_templates() -> list[ConversationTemplate]:
        """Get all available conversation templates - simplified to 2 scenarios."""
        return [
            ConversationTemplates.get_insurance_inquiry(),
            ConversationTemplates.get_quick_question(),
        ]


class ConversationSimulator:
    """Simulates realistic conversations for load testing and agent evaluation with configurable turn depth."""

    def __init__(
        self,
        ws_url: str = "ws://localhost:8010/api/v1/media/stream",
        conversation_turns: int = 5,
    ):
        self.ws_url = ws_url
        self.conversation_turns = conversation_turns
        self.speech_generator = ProductionSpeechGenerator(conversation_turns=conversation_turns)

    def preload_conversation_audio(self, template: ConversationTemplate):
        """No-op since we're using pre-cached files."""
        print("ℹ️  Using pre-cached PCM files, no preloading needed")

    async def simulate_conversation(
        self,
        template: ConversationTemplate,
        session_id: str | None = None,
        on_turn_complete: Callable[[ConversationTurn, list[dict]], None] | None = None,
        on_agent_response: Callable[[str, list[dict]], None] | None = None,
        preload_audio: bool = True,
        max_turns: int | None = None,
    ) -> ConversationMetrics:
        """Simulate a complete conversation using the given template with configurable turn depth."""

        if session_id is None:
            session_id = f"{template.name}-{int(time.time())}-{random.randint(1000, 9999)}"

        # Use max_turns parameter or default to configured conversation_turns
        effective_max_turns = max_turns or self.conversation_turns

        metrics = ConversationMetrics(
            session_id=session_id,
            template_name=template.name,
            start_time=time.time(),
            end_time=0,
            connection_time_ms=0,
        )

        print(f"🎭 Starting conversation simulation: {template.name}")
        print(f"📞 Session ID: {session_id}")
        print(f"🔄 Max turns configured: {effective_max_turns}")

        # Preload audio sequence for the conversation
        if preload_audio:
            print(f"🔄 Loading audio sequence for {effective_max_turns} turns...")
            audio_sequence = self.speech_generator.get_conversation_audio_sequence(
                scenario=template.name, max_turns=effective_max_turns
            )

            if not audio_sequence:
                print("❌ No audio sequence available, falling back to individual file selection")
                audio_sequence = None
        else:
            audio_sequence = None

        try:
            # Connect to WebSocket
            connect_start = time.time()
            # Configure connection parameters based on URL scheme
            connect_kwargs = {
                "additional_headers": {
                    "x-call-connection-id": session_id,
                    "x-session-id": session_id,
                }
            }

            # Explicitly handle SSL based on URL scheme
            if self.ws_url.startswith("ws://"):
                # For plain WebSocket, explicitly disable SSL
                connect_kwargs["ssl"] = None
            elif self.ws_url.startswith("wss://"):
                # For secure WebSocket, create SSL context
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connect_kwargs["ssl"] = ssl_context

            async with websockets.connect(
                f"{self.ws_url}?call_connection_id={session_id}", **connect_kwargs
            ) as websocket:
                metrics.connection_time_ms = (time.time() - connect_start) * 1000
                print(f"✅ Connected in {metrics.connection_time_ms:.1f}ms")

                # Send audio metadata
                metadata = {
                    "kind": "AudioMetadata",
                    "payload": {"format": "pcm", "rate": 16000},
                }
                await websocket.send(json.dumps(metadata))

                # Wait for system initialization
                await asyncio.sleep(1.0)

                # Process each conversation turn (limited by effective_max_turns)
                turns_to_process = template.turns[:effective_max_turns] if template.turns else []
                audio_turn_index = 0  # Track position in audio sequence

                for turn_idx, turn in enumerate(turns_to_process):
                    if turn.speaker == "user":
                        print(
                            f"\n👤 User turn {turn_idx + 1}/{len(turns_to_process)}: '{turn.text}' ({turn.phase.value})"
                        )

                        # Initialize turn metrics
                        turn_metrics = TurnMetrics(
                            turn_number=turn_idx + 1,
                            turn_text=turn.text,
                            audio_send_start_time=0,
                            audio_send_complete_time=0,
                            first_response_time=0,
                            last_audio_chunk_time=0,
                            turn_complete_time=0,
                        )

                        # Wait before speaking (natural pause) - let previous response finish
                        pause_time = max(turn.delay_before_ms / 1000.0, 2.0)  # At least 2 seconds
                        print(f"    ⏸️  Waiting {pause_time:.1f}s for agent to finish speaking...")
                        await asyncio.sleep(pause_time)

                        # Start turn timing
                        turn_metrics.audio_send_start_time = time.time()

                        # Get audio for this turn
                        # Use pre-loaded audio sequence if available, otherwise get next available file
                        if audio_sequence and audio_turn_index < len(audio_sequence):
                            speech_audio = audio_sequence[audio_turn_index]
                            print(
                                f"    🎵 Using pre-loaded audio {audio_turn_index + 1}/{len(audio_sequence)}"
                            )
                            audio_turn_index += 1
                        else:
                            # Fallback to individual file selection
                            speech_audio = self.speech_generator.get_next_audio()
                            print("    🎵 Using fallback audio selection")

                        if not speech_audio:
                            print("    ❌ No audio available, skipping turn")
                            turn_metrics.turn_successful = False
                            turn_metrics.error_message = "No audio available"
                            turn_metrics.turn_complete_time = time.time()
                            turn_metrics.calculate_metrics()
                            metrics.turn_metrics.append(turn_metrics)
                            metrics.failed_turns += 1
                            continue

                        turn_metrics.audio_bytes_sent = len(speech_audio)

                        # Send audio more quickly to simulate natural speech timing
                        chunk_size = int(16000 * 0.1 * 2)  # Back to 100ms chunks for natural flow
                        audio_chunks_sent = 0

                        print(f"    🎤 Streaming cached audio for turn: '{turn.text}'")

                        for i in range(0, len(speech_audio), chunk_size):
                            chunk = speech_audio[i : i + chunk_size]
                            chunk_b64 = base64.b64encode(chunk).decode("utf-8")

                            audio_msg = {
                                "kind": "AudioData",
                                "audioData": {
                                    "data": chunk_b64,
                                    "silent": False,
                                    "timestamp": time.time(),
                                },
                            }

                            await websocket.send(json.dumps(audio_msg))
                            audio_chunks_sent += 1

                            # Natural speech timing
                            await asyncio.sleep(0.08)  # 80ms between chunks - more natural

                        # Record audio send completion
                        turn_metrics.audio_send_complete_time = time.time()
                        turn_metrics.audio_chunks_sent = audio_chunks_sent

                        # Add a short pause after speech (critical for speech recognition finalization)
                        print("    🤫 Adding end-of-utterance silence...")

                        for _ in range(5):  # Send 5 chunks of 100ms silence each
                            silence_msg = {
                                "kind": "AudioData",
                                "audioData": {
                                    "data": base64.b64encode(generate_silence_chunk(100)).decode(
                                        "utf-8"
                                    ),
                                    "silent": False,  # Mark as non-silent to ensure VAD processes it
                                    "timestamp": time.time(),
                                },
                            }
                            await websocket.send(json.dumps(silence_msg))
                            audio_chunks_sent += 1
                            await asyncio.sleep(0.1)  # 100ms between silence chunks

                        print(
                            f"    📤 Sent {audio_chunks_sent} audio chunks ({len(speech_audio)} bytes total)"
                        )
                        print(f"    🎵 Audio duration: {len(speech_audio)/(16000*2):.2f}s")
                        print(
                            f"    ⏱️  Audio send time: {(turn_metrics.audio_send_complete_time - turn_metrics.audio_send_start_time)*1000:.1f}ms"
                        )

                        # Wait for complete agent response with proper timeout and latency measurement
                        response_start = time.time()
                        responses = []
                        agent_audio_chunks_this_turn = 0
                        last_audio_chunk_time = None
                        response_complete = False
                        turn_failed = False
                        first_response_received = False

                        # Start streaming silence to maintain VAD continuity
                        silence_streaming_active = True

                        async def stream_silence():
                            """Stream silent audio chunks during response wait to maintain VAD."""
                            silence_chunk = generate_silence_chunk(100)  # 100ms silence chunks
                            silence_chunk_b64 = base64.b64encode(silence_chunk).decode("utf-8")

                            while silence_streaming_active:
                                try:
                                    # Send silence as non-silent to ensure VAD processes it
                                    # This mimics ambient/background noise during conversation pauses
                                    silence_msg = {
                                        "kind": "AudioData",
                                        "audioData": {
                                            "data": silence_chunk_b64,
                                            "silent": False,  # Mark as non-silent to keep VAD active
                                            "timestamp": time.time(),
                                        },
                                    }
                                    await websocket.send(json.dumps(silence_msg))
                                    await asyncio.sleep(0.1)  # Send every 100ms
                                except Exception:
                                    break  # Exit if websocket is closed

                        # Start background silence streaming task
                        silence_task = asyncio.create_task(stream_silence())

                        try:
                            # Listen for the complete agent response with 20-second timeout
                            timeout_deadline = response_start + 20.0  # 20 second absolute timeout
                            audio_silence_timeout = (
                                2.0  # Consider response complete after 2s of no audio chunks
                            )

                            while time.time() < timeout_deadline and not response_complete:
                                try:
                                    # Dynamic timeout: shorter if we've received audio, longer initially
                                    if last_audio_chunk_time:
                                        # If we've been getting audio, use shorter timeout to detect end
                                        remaining_silence_time = audio_silence_timeout - (
                                            time.time() - last_audio_chunk_time
                                        )
                                        current_timeout = max(0.5, remaining_silence_time)
                                    else:
                                        # Initially, wait longer for first response
                                        current_timeout = min(3.0, timeout_deadline - time.time())

                                    if current_timeout <= 0:
                                        # We've waited long enough since last audio chunk
                                        if agent_audio_chunks_this_turn > 0:
                                            response_complete = True
                                            break
                                        else:
                                            # No audio received at all
                                            current_timeout = 0.5

                                    response = await asyncio.wait_for(
                                        websocket.recv(), timeout=current_timeout
                                    )
                                    response_data = json.loads(response)
                                    responses.append(response_data)
                                    metrics.server_responses.append(response_data)

                                    # Record the response for detailed analysis
                                    turn_metrics.full_responses_received.append(response_data)

                                    # Process different response types for conversation recording
                                    response_kind = response_data.get(
                                        "kind", response_data.get("type", "unknown")
                                    )

                                    # Track audio responses (agent speech)
                                    if response_kind == "AudioData":
                                        # Record first response time for turn metrics
                                        if not first_response_received:
                                            turn_metrics.first_response_time = time.time()
                                            first_response_received = True

                                        metrics.audio_chunks_received += 1
                                        agent_audio_chunks_this_turn += 1
                                        turn_metrics.audio_chunks_received = (
                                            agent_audio_chunks_this_turn
                                        )
                                        last_audio_chunk_time = time.time()
                                        turn_metrics.last_audio_chunk_time = last_audio_chunk_time

                                        # Extract and store audio data for playback analysis
                                        audio_payload = response_data.get("audioData", {})
                                        if "data" in audio_payload:
                                            try:
                                                audio_bytes = base64.b64decode(
                                                    audio_payload["data"]
                                                )
                                                turn_metrics.agent_audio_responses.append(
                                                    audio_bytes
                                                )
                                            except Exception as e:
                                                print(f"      ⚠️  Failed to decode audio data: {e}")

                                        # Print progress for first few chunks
                                        if agent_audio_chunks_this_turn <= 3:
                                            print(
                                                f"      📨 Audio chunk {agent_audio_chunks_this_turn} received"
                                            )
                                        elif agent_audio_chunks_this_turn == 10:
                                            print(
                                                f"      📨 {agent_audio_chunks_this_turn} audio chunks received..."
                                            )
                                        elif agent_audio_chunks_this_turn % 50 == 0:
                                            print(
                                                f"      📨 {agent_audio_chunks_this_turn} audio chunks received..."
                                            )

                                    # Capture speech recognition results - expand the search
                                    elif (
                                        response_kind.lower()
                                        in [
                                            "speechrecognitionresult",
                                            "speech_recognition",
                                            "recognitionresult",
                                            "speechresult",
                                            "recognition",
                                        ]
                                        or "speech" in response_kind.lower()
                                        or "recognition" in response_kind.lower()
                                    ):
                                        # Try multiple possible text fields
                                        text_result = (
                                            response_data.get("text")
                                            or response_data.get("recognizedText")
                                            or response_data.get("result")
                                            or response_data.get("transcript")
                                            or response_data.get("speechText")
                                            or response_data.get("displayText")
                                            or ""
                                        )
                                        if text_result:
                                            turn_metrics.user_speech_recognized = text_result
                                            print(f"      🎯 Speech recognized: '{text_result}'")

                                    # Capture agent text responses - expand the search
                                    elif (
                                        response_kind.lower()
                                        in [
                                            "textresponse",
                                            "agentresponse",
                                            "text",
                                            "message",
                                            "chatresponse",
                                        ]
                                        or "text" in response_kind.lower()
                                        or "message" in response_kind.lower()
                                        or "response" in response_kind.lower()
                                    ):
                                        # Try multiple possible text fields
                                        text_response = (
                                            response_data.get("text")
                                            or response_data.get("message")
                                            or response_data.get("content")
                                            or response_data.get("response")
                                            or response_data.get("agentMessage")
                                            or ""
                                        )
                                        if text_response:
                                            turn_metrics.agent_text_responses.append(text_response)
                                            print(
                                                f"      💬 Agent text: '{text_response[:100]}{'...' if len(text_response) > 100 else ''}'"
                                            )

                                    # Log ALL non-audio response types for debugging (first 10 responses only)
                                    elif len(responses) <= 10:
                                        resp_type = response_data.get(
                                            "kind", response_data.get("type", "unknown")
                                        )
                                        print(f"      📨 {resp_type} response received")

                                        # Also check if this response contains any text-like fields we missed
                                        text_fields = {}
                                        for key, value in response_data.items():
                                            if (
                                                isinstance(value, str)
                                                and len(value) > 5
                                                and len(value) < 500
                                            ):
                                                if any(
                                                    word in key.lower()
                                                    for word in [
                                                        "text",
                                                        "message",
                                                        "content",
                                                        "speech",
                                                        "recognition",
                                                    ]
                                                ):
                                                    text_fields[key] = value[:50] + (
                                                        "..." if len(value) > 50 else ""
                                                    )

                                        if text_fields:
                                            print(f"      🔍 Text fields found: {text_fields}")

                                except TimeoutError:
                                    if (
                                        last_audio_chunk_time
                                        and (time.time() - last_audio_chunk_time)
                                        >= audio_silence_timeout
                                    ):
                                        # We've had enough silence after receiving audio - response is complete
                                        if agent_audio_chunks_this_turn > 0:
                                            response_complete = True
                                            break
                                    elif time.time() >= timeout_deadline:
                                        # Absolute timeout reached
                                        break
                                    # Otherwise continue waiting

                            # Finalize turn metrics
                            turn_metrics.turn_complete_time = time.time()
                            response_end = turn_metrics.turn_complete_time
                            total_response_time_ms = (response_end - response_start) * 1000
                            end_to_end_latency_ms = (
                                response_end - turn_metrics.audio_send_start_time
                            ) * 1000

                            if agent_audio_chunks_this_turn == 0:
                                # No audio received - mark as failure
                                turn_failed = True
                                turn_metrics.turn_successful = False
                                turn_metrics.error_message = f"No audio response received within {audio_silence_timeout}s timeout"
                                error_msg = f"Turn {turn_idx + 1}: No audio response received within {audio_silence_timeout}s timeout"
                                metrics.errors.append(error_msg)
                                print(f"      ❌ {error_msg}")
                                metrics.failed_turns += 1
                            else:
                                # Success - we got audio response
                                turn_metrics.turn_successful = True
                                metrics.agent_turns += 1
                                metrics.successful_turns += 1
                                response_complete = True
                                print(
                                    f"      ✅ Complete audio response received: {agent_audio_chunks_this_turn} chunks"
                                )

                            # Calculate and display detailed turn metrics
                            turn_metrics.calculate_metrics()

                            # Record timing metrics for backward compatibility
                            metrics.total_agent_processing_time_ms += total_response_time_ms
                            speech_recognition_time = turn_metrics.speech_recognition_latency_ms
                            metrics.total_speech_recognition_time_ms += speech_recognition_time

                            print(f"      ⏱️  Turn Response time: {total_response_time_ms:.1f}ms")
                            print(f"      ⏱️  End-to-end latency: {end_to_end_latency_ms:.1f}ms")
                            print(f"      ⏱️  Speech recognition: {speech_recognition_time:.1f}ms")
                            print(
                                f"      ⏱️  Agent processing: {turn_metrics.agent_processing_latency_ms:.1f}ms"
                            )

                        except Exception as e:
                            turn_failed = True
                            turn_metrics.turn_successful = False
                            turn_metrics.turn_complete_time = time.time()
                            turn_metrics.error_message = str(e)
                            error_msg = f"Turn {turn_idx + 1}: {str(e)}"
                            metrics.errors.append(error_msg)
                            print(f"      ❌ Turn error: {error_msg}")
                            metrics.failed_turns += 1
                        finally:
                            # Stop silence streaming
                            silence_streaming_active = False
                            silence_task.cancel()
                            try:
                                await silence_task
                            except asyncio.CancelledError:
                                pass

                        # Add turn metrics to conversation metrics (always, even if failed)
                        metrics.turn_metrics.append(turn_metrics)
                        metrics.user_turns += 1

                        print(
                            f"  🤖 Turn completed: {'✅ Success' if not turn_failed else '❌ Failed'}"
                        )
                        print(
                            f"  📊 Audio chunks: {agent_audio_chunks_this_turn}, Total responses: {len(responses)}"
                        )

                        # Callback for turn completion
                        if on_turn_complete:
                            try:
                                on_turn_complete(turn, responses)
                            except Exception as e:
                                print(f"  ⚠️ Turn callback error: {e}")

                        # Callback for agent responses
                        if on_agent_response and responses:
                            try:
                                on_agent_response(turn.text, responses)
                            except Exception as e:
                                print(f"  ⚠️ Agent callback error: {e}")

                        # Brief pause before next turn (only if not failed)
                        if not turn_failed:
                            await asyncio.sleep(
                                1.0
                            )  # Slightly longer pause for more realistic conversation

                print("\n✅ Conversation completed successfully")
                metrics.end_time = time.time()

        except Exception as e:
            print(f"❌ Conversation failed: {e}")
            metrics.errors.append(f"Conversation error: {str(e)}")
            metrics.end_time = time.time()

        return metrics

    def analyze_metrics(self, metrics: ConversationMetrics) -> dict[str, Any]:
        """Analyze conversation metrics and return insights."""
        duration_s = metrics.end_time - metrics.start_time

        analysis = {
            "session_id": metrics.session_id,
            "template": metrics.template_name,
            "success": len(metrics.errors) == 0,
            "duration_s": duration_s,
            "connection_time_ms": metrics.connection_time_ms,
            # Turn metrics
            "user_turns": metrics.user_turns,
            "agent_turns": len(
                [r for r in metrics.server_responses if r.get("kind") == "AudioData"]
            ),
            "total_responses": len(metrics.server_responses),
            # Performance metrics
            "avg_speech_recognition_ms": metrics.total_speech_recognition_time_ms
            / max(1, metrics.user_turns),
            "avg_agent_processing_ms": metrics.total_agent_processing_time_ms
            / max(1, metrics.user_turns),
            "audio_chunks_received": metrics.audio_chunks_received,
            # Quality metrics
            "error_count": len(metrics.errors),
            "failed_turns": metrics.failed_turns,
            "errors": metrics.errors,
            # Response analysis
            "response_types": {},
        }

        # Analyze response types
        for response in metrics.server_responses:
            resp_type = response.get("kind", response.get("type", "unknown"))
            analysis["response_types"][resp_type] = analysis["response_types"].get(resp_type, 0) + 1

        return analysis


# Example usage and testing
async def main():
    """Example of how to use the conversation simulator."""
    simulator = ConversationSimulator()

    # Get a conversation template
    template = ConversationTemplates.get_insurance_inquiry()

    # Define callbacks for monitoring
    def on_turn_complete(turn: ConversationTurn, responses: list[dict]):
        print(f"  📋 Turn completed: '{turn.text}' -> {len(responses)} responses")

    def on_agent_response(user_text: str, responses: list[dict]):
        audio_responses = len([r for r in responses if r.get("kind") == "AudioData"])
        print(f"  🎤 Agent generated {audio_responses} audio responses to: '{user_text[:30]}...'")

    # Run simulation with production audio
    metrics = await simulator.simulate_conversation(
        template,
        on_turn_complete=on_turn_complete,
        on_agent_response=on_agent_response,
        preload_audio=True,  # Use production TTS for better recognition
    )

    # Analyze results
    analysis = simulator.analyze_metrics(metrics)

    print("\n📊 CONVERSATION ANALYSIS")
    print("=" * 50)
    print(f"Success: {'✅' if analysis['success'] else '❌'}")
    print(f"Duration: {analysis['duration_s']:.2f}s")
    print(f"Connection: {analysis['connection_time_ms']:.1f}ms")
    print(f"User turns: {analysis['user_turns']}")
    print(f"Failed turns: {analysis['failed_turns']}")
    print(f"Agent responses: {analysis['audio_chunks_received']}")
    print(f"Avg recognition time: {analysis['avg_speech_recognition_ms']:.1f}ms")
    print(f"Avg agent processing: {analysis['avg_agent_processing_ms']:.1f}ms")

    if analysis["errors"]:
        print(f"❌ Errors: {analysis['error_count']}")
        for error in analysis["errors"]:
            print(f"  - {error}")


if __name__ == "__main__":
    asyncio.run(main())
