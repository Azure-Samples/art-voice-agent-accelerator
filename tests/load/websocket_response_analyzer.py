#!/usr/bin/env python3
"""
WebSocket Response Analyzer

Connects to the backend WebSocket to capture and analyze real-time responses
to understand what text and audio the agent is actually producing.
"""

import asyncio
import base64
import json
import time
import uuid

import websockets


class WebSocketResponseAnalyzer:
    """Analyzes WebSocket responses from the voice agent backend."""

    def __init__(self, ws_url: str = "ws://localhost:8010/api/v1/media/stream"):
        self.ws_url = ws_url
        self.session_id = f"analyzer-{uuid.uuid4().hex[:8]}"
        self.responses_captured = []
        self.audio_chunks_received = 0
        self.text_responses = []
        self.speech_recognitions = []

    async def analyze_responses(self, test_duration: int = 30):
        """Connect and analyze responses for a specified duration."""

        print(f"🔍 Connecting to WebSocket: {self.ws_url}")
        print(f"📝 Session ID: {self.session_id}")
        print(f"⏱️  Analysis Duration: {test_duration} seconds")

        try:
            async with websockets.connect(self.ws_url) as websocket:
                print("✅ Connected to WebSocket")

                # Send initial metadata
                await self.send_initial_metadata(websocket)

                # Send some audio data to trigger responses
                await self.send_test_audio(websocket)

                # Listen for responses
                start_time = time.time()
                timeout_time = start_time + test_duration

                print("👂 Listening for responses...")

                while time.time() < timeout_time:
                    try:
                        # Wait for message with timeout
                        remaining_time = timeout_time - time.time()
                        if remaining_time <= 0:
                            break

                        message = await asyncio.wait_for(
                            websocket.recv(), timeout=min(remaining_time, 5.0)
                        )

                        await self.analyze_message(message)

                    except TimeoutError:
                        # No message received in timeout period
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        print("❌ WebSocket connection closed")
                        break

                print("⏹️  Analysis complete")
                await self.print_analysis_results()

        except Exception as e:
            print(f"❌ Error during analysis: {e}")

    async def send_initial_metadata(self, websocket):
        """Send initial session metadata."""
        metadata = {
            "kind": "SessionMetadata",
            "sessionId": self.session_id,
            "subscriptionId": "test-subscription",
            "callConnectionId": f"test-call-{self.session_id}",
            "participantId": "test-participant",
            "format": {
                "encoding": "pcm",
                "sampleRate": 16000,
                "channels": 1,
                "bitsPerSample": 16,
            },
        }

        await websocket.send(json.dumps(metadata))
        print("📤 Sent session metadata")

    async def send_test_audio(self, websocket):
        """Send some test audio to trigger agent responses."""

        # Generate simple test audio (silence with slight variation to simulate speech)
        sample_rate = 16000
        duration_seconds = 2
        samples = sample_rate * duration_seconds

        # Create simple audio pattern
        audio_data = bytearray()
        for i in range(samples):
            # Simple sine wave pattern to simulate audio
            value = int(1000 * (i % 100) / 100)
            audio_data.extend(value.to_bytes(2, byteorder="little", signed=True))

        # Encode as base64
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        # Send audio message
        audio_message = {"kind": "AudioData", "audioData": {"data": audio_b64}}

        await websocket.send(json.dumps(audio_message))
        print(f"📤 Sent test audio ({len(audio_data)} bytes)")

        # Send stop message after a delay
        await asyncio.sleep(1)

        stop_message = {"kind": "StopAudio"}

        await websocket.send(json.dumps(stop_message))
        print("📤 Sent stop audio signal")

    async def analyze_message(self, message: str):
        """Analyze a received WebSocket message."""

        try:
            response_data = json.loads(message)
            self.responses_captured.append(response_data)

            response_kind = response_data.get("kind", "Unknown")

            # Count audio chunks
            if response_kind == "AudioData":
                self.audio_chunks_received += 1

                if self.audio_chunks_received <= 5:
                    print(f"  📨 Audio chunk {self.audio_chunks_received} received")
                elif self.audio_chunks_received % 20 == 0:
                    print(f"  📨 {self.audio_chunks_received} audio chunks received...")

            # Look for text responses
            elif "text" in response_data or "message" in response_data:
                text_content = response_data.get("text", response_data.get("message", ""))
                if text_content and text_content not in self.text_responses:
                    self.text_responses.append(text_content)
                    print(f"  💬 Text response: '{text_content}'")

            # Look for speech recognition
            elif (
                "speech" in response_kind.lower()
                or "recognition" in response_kind.lower()
                or "recognized" in response_data
            ):
                recognized_text = ""
                if "recognizedSpeech" in response_data:
                    recognized_text = response_data["recognizedSpeech"]
                elif "text" in response_data:
                    recognized_text = response_data["text"]
                elif "speech" in response_data:
                    recognized_text = response_data["speech"]

                if recognized_text and recognized_text not in self.speech_recognitions:
                    self.speech_recognitions.append(recognized_text)
                    print(f"  🎤 Speech recognized: '{recognized_text}'")

            # Look for any response with interesting content
            elif response_kind not in ["AudioData", "KeepAlive", "Heartbeat"]:
                # Print interesting responses for debugging
                print(
                    f"  🔍 Response type '{response_kind}': {json.dumps(response_data, indent=2)[:200]}..."
                )

        except json.JSONDecodeError:
            print(f"  ⚠️  Failed to parse message as JSON: {message[:100]}...")
        except Exception as e:
            print(f"  ⚠️  Error analyzing message: {e}")

    async def print_analysis_results(self):
        """Print summary of analysis results."""

        print("\n" + "=" * 60)
        print("WEBSOCKET RESPONSE ANALYSIS RESULTS")
        print("=" * 60)

        print(f"Session ID: {self.session_id}")
        print(f"Total responses captured: {len(self.responses_captured)}")
        print(f"Audio chunks received: {self.audio_chunks_received}")
        print(f"Text responses found: {len(self.text_responses)}")
        print(f"Speech recognitions found: {len(self.speech_recognitions)}")

        if self.text_responses:
            print("\n📝 AGENT TEXT RESPONSES:")
            for i, text in enumerate(self.text_responses, 1):
                print(f"  {i}. {text}")
        else:
            print("\n📝 No agent text responses captured")

        if self.speech_recognitions:
            print("\n🎤 SPEECH RECOGNITIONS:")
            for i, speech in enumerate(self.speech_recognitions, 1):
                print(f"  {i}. {speech}")
        else:
            print("\n🎤 No speech recognitions captured")

        # Show unique response types
        response_types = {}
        for response in self.responses_captured:
            kind = response.get("kind", "Unknown")
            response_types[kind] = response_types.get(kind, 0) + 1

        print("\n📊 RESPONSE TYPES:")
        for kind, count in sorted(response_types.items()):
            print(f"  {kind}: {count}")

        # Save detailed results
        results = {
            "session_id": self.session_id,
            "analysis_timestamp": time.time(),
            "total_responses": len(self.responses_captured),
            "audio_chunks_received": self.audio_chunks_received,
            "text_responses": self.text_responses,
            "speech_recognitions": self.speech_recognitions,
            "response_types": response_types,
            "sample_responses": self.responses_captured[:10],  # First 10 responses as samples
        }

        output_file = f"tests/load/results/websocket_analysis_{int(time.time())}.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n💾 Detailed results saved to: {output_file}")


async def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze WebSocket responses from voice agent")
    parser.add_argument(
        "--url",
        "-u",
        default="ws://localhost:8010/api/v1/media/stream",
        help="WebSocket URL to connect to",
    )
    parser.add_argument(
        "--duration", "-d", type=int, default=30, help="Analysis duration in seconds"
    )

    args = parser.parse_args()

    analyzer = WebSocketResponseAnalyzer(args.url)
    await analyzer.analyze_responses(args.duration)


if __name__ == "__main__":
    asyncio.run(main())
