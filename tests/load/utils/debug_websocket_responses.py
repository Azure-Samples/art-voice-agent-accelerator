#!/usr/bin/env python3
"""
Debug WebSocket Response Types

This script performs a single conversation turn and logs all response types
to help us understand the actual format of WebSocket responses from the backend.
"""

import asyncio
import json
import time
import base64
import websockets
from pathlib import Path
from typing import Dict, Any, List


class WebSocketResponseDebugger:
    """Debug the actual WebSocket response formats."""

    def __init__(self):
        self.cache_dir = Path("audio_cache")  # Relative to current working directory
        print(f"Looking for PCM files in: {self.cache_dir.absolute()}")
        self.pcm_files = list(self.cache_dir.glob("*.pcm"))
        print(f"Found PCM files: {[f.name for f in self.pcm_files]}")
        if not self.pcm_files:
            raise RuntimeError(f"No PCM files found in {self.cache_dir.absolute()}")

    async def debug_single_turn(self, websocket_url: str = "ws://localhost:8000/ws"):
        """Run a single conversation turn and log all response types."""
        print(f"Connecting to {websocket_url}...")

        async with websockets.connect(websocket_url) as websocket:
            print("✅ Connected successfully")

            # Get first available PCM file
            pcm_file = self.pcm_files[0]
            audio_bytes = pcm_file.read_bytes()
            print(f"📄 Using audio file: {pcm_file.name} ({len(audio_bytes)} bytes)")

            # Stream the audio in chunks
            print("📤 Sending audio data...")
            chunk_size = 3200  # 100ms at 16kHz
            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i : i + chunk_size]

                message = {
                    "kind": "AudioData",
                    "audioData": {
                        "data": base64.b64encode(chunk).decode("utf-8"),
                        "timestamp": int(time.time() * 1000),
                        "participant": {"id": "debug-user"},
                    },
                }

                await websocket.send(json.dumps(message))
                await asyncio.sleep(0.1)  # 100ms delay between chunks

            # Send end-of-utterance silence
            print("📤 Sending end-of-utterance silence...")
            silence = b"\x00" * 3200  # 100ms of silence
            for _ in range(10):  # 1 second of silence
                message = {
                    "kind": "AudioData",
                    "audioData": {
                        "data": base64.b64encode(silence).decode("utf-8"),
                        "timestamp": int(time.time() * 1000),
                        "participant": {"id": "debug-user"},
                    },
                }
                await websocket.send(json.dumps(message))
                await asyncio.sleep(0.1)

            print("🎧 Listening for responses...")
            responses = []
            response_types = {}
            start_time = time.time()

            # Listen for responses for up to 15 seconds
            while time.time() - start_time < 15.0:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    response_data = json.loads(response)
                    responses.append(response_data)

                    # Track response types
                    response_kind = response_data.get(
                        "kind", response_data.get("type", "unknown")
                    )
                    response_types[response_kind] = (
                        response_types.get(response_kind, 0) + 1
                    )

                    # Log the first few responses of each type
                    if response_types[response_kind] <= 3:
                        print(f"\n📨 Response Type: {response_kind}")
                        print(
                            f"   Full Response: {json.dumps(response_data, indent=2)}"
                        )
                    elif response_types[response_kind] == 4:
                        print(
                            f"📨 {response_kind}: (continuing to receive, stopping detailed logs...)"
                        )

                except asyncio.TimeoutError:
                    print("⏰ Timeout waiting for more responses")
                    break
                except Exception as e:
                    print(f"❌ Error receiving response: {e}")
                    break

            print(f"\n📊 RESPONSE SUMMARY")
            print(f"Total responses received: {len(responses)}")
            print(f"Response type breakdown:")
            for resp_type, count in response_types.items():
                print(f"  {resp_type}: {count}")

            # Analyze specific response patterns
            print(f"\n🔍 RESPONSE ANALYSIS")

            # Look for speech recognition patterns
            speech_responses = [
                r
                for r in responses
                if "speech" in r.get("kind", "").lower()
                or "recognition" in r.get("kind", "").lower()
                or "text" in str(r).lower()
            ]

            if speech_responses:
                print(f"🎯 Speech Recognition Responses ({len(speech_responses)}):")
                for i, resp in enumerate(speech_responses[:3]):
                    print(f"  {i+1}. {json.dumps(resp, indent=4)}")
            else:
                print("🎯 No obvious speech recognition responses found")

            # Look for text/message responses
            text_responses = [
                r
                for r in responses
                if "text" in r.get("kind", "").lower()
                or "message" in r.get("kind", "").lower()
                or any(key in r for key in ["text", "message", "content"])
            ]

            if text_responses:
                print(f"💬 Text/Message Responses ({len(text_responses)}):")
                for i, resp in enumerate(text_responses[:3]):
                    print(f"  {i+1}. {json.dumps(resp, indent=4)}")
            else:
                print("💬 No obvious text/message responses found")

            # Look for audio responses
            audio_responses = [r for r in responses if r.get("kind") == "AudioData"]
            print(f"🎵 Audio Responses: {len(audio_responses)}")

            return responses, response_types


async def main():
    """Run the WebSocket response debugger."""
    debugger = WebSocketResponseDebugger()

    try:
        responses, response_types = await debugger.debug_single_turn()
        print(f"\n✅ Debug session completed successfully")
        print(
            f"📄 Use this information to update conversation_simulator.py response parsing"
        )

    except Exception as e:
        print(f"❌ Debug session failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
