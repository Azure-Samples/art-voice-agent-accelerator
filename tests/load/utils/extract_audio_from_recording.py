#!/usr/bin/env python3
"""
Audio Extractor from Conversation Recordings

Extracts audio chunks from recorded conversation data and converts them to text
using Azure Speech Services. This works with the existing conversation recording
format without needing to save files to disk first.
"""

import base64
import json
import os
import tempfile
import wave
from pathlib import Path
from typing import Any

import azure.cognitiveservices.speech as speechsdk


class AudioExtractorFromRecording:
    """Extracts and transcribes audio directly from conversation recording data."""

    def __init__(self, speech_key: str = None, speech_region: str = None):
        """Initialize with Azure Speech Service credentials."""
        self.speech_key = speech_key or os.getenv("AZURE_SPEECH_KEY")
        self.speech_region = speech_region or os.getenv("AZURE_SPEECH_REGION")

        if not self.speech_key or not self.speech_region:
            print("⚠️  Azure Speech Service credentials not found.")
            print("   Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION environment variables")
            print("   or the tool will skip transcription and only extract audio.")
            self.speech_enabled = False
        else:
            self.speech_enabled = True
            # Configure speech recognizer
            speech_config = speechsdk.SpeechConfig(
                subscription=self.speech_key, region=self.speech_region
            )
            speech_config.speech_recognition_language = "en-US"
            self.speech_config = speech_config

    def pcm_to_wav_bytes(self, pcm_data: bytes) -> bytes:
        """Convert PCM bytes to WAV format bytes."""
        with tempfile.NamedTemporaryFile() as temp_wav:
            with wave.open(temp_wav.name, "wb") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(16000)  # 16kHz
                wav_file.writeframes(pcm_data)

            temp_wav.seek(0)
            return temp_wav.read()

    def transcribe_audio_bytes(self, audio_bytes: bytes) -> dict[str, Any]:
        """Transcribe audio bytes to text."""

        if not self.speech_enabled:
            return {
                "text": "",
                "success": False,
                "error": "Speech recognition not configured",
            }

        try:
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                wav_path = temp_wav.name

                # Write PCM data as WAV
                with wave.open(wav_path, "wb") as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(16000)  # 16kHz
                    wav_file.writeframes(audio_bytes)

            # Create audio input and recognizer
            audio_input = speechsdk.AudioConfig(filename=wav_path)
            speech_recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config, audio_config=audio_input
            )

            # Perform recognition
            result = speech_recognizer.recognize_once()

            # Clean up temp file
            try:
                os.unlink(wav_path)
            except:
                pass

            # Process result
            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                return {
                    "text": result.text,
                    "success": True,
                    "confidence": 1.0,
                    "duration_s": len(audio_bytes) / (16000 * 2),
                }
            elif result.reason == speechsdk.ResultReason.NoMatch:
                return {
                    "text": "",
                    "success": True,
                    "error": "No speech detected",
                    "duration_s": len(audio_bytes) / (16000 * 2),
                }
            else:
                return {
                    "text": "",
                    "success": False,
                    "error": f"Recognition failed: {result.reason}",
                    "duration_s": len(audio_bytes) / (16000 * 2),
                }

        except Exception as e:
            return {"text": "", "success": False, "error": str(e), "duration_s": 0}

    def extract_audio_from_responses(self, responses: list[dict[str, Any]]) -> list[bytes]:
        """Extract audio data from WebSocket response objects."""

        audio_chunks = []

        for response in responses:
            if response.get("kind") == "AudioData":
                audio_payload = response.get("audioData", {})
                if "data" in audio_payload:
                    try:
                        audio_bytes = base64.b64decode(audio_payload["data"])
                        audio_chunks.append(audio_bytes)
                    except Exception as e:
                        print(f"      ⚠️  Failed to decode audio data: {e}")

        return audio_chunks

    def process_conversation_file(self, conversation_file: str) -> dict[str, Any]:
        """Process a conversation recording file and extract/transcribe audio."""

        print(f"🎤 Processing conversation file: {conversation_file}")

        try:
            with open(conversation_file) as f:
                conversations = json.load(f)
        except Exception as e:
            return {"error": f"Failed to load conversation file: {e}"}

        results = {
            "file": conversation_file,
            "conversations_processed": 0,
            "turns_processed": 0,
            "audio_chunks_found": 0,
            "audio_transcribed": 0,
            "conversations": [],
        }

        for conv_idx, conversation in enumerate(conversations):
            print(f"\n📞 Conversation {conv_idx + 1}: {conversation['session_id'][:8]}...")

            conv_result = {
                "session_id": conversation["session_id"],
                "template_name": conversation.get("template_name", "unknown"),
                "turns": [],
            }

            for turn in conversation.get("turns", []):
                turn_number = turn.get("turn_number", 0)
                print(f"  🔄 Turn {turn_number}: Processing responses...")

                turn_result = {
                    "turn_number": turn_number,
                    "user_input": turn.get("user_input_text", ""),
                    "audio_chunks_found": 0,
                    "audio_transcriptions": [],
                    "combined_audio_text": "",
                }

                # Extract audio from full_responses_received if available
                if "full_responses_received" in turn and turn["full_responses_received"]:
                    print(f"    📋 Found {len(turn['full_responses_received'])} raw responses")

                    audio_chunks = self.extract_audio_from_responses(
                        turn["full_responses_received"]
                    )
                    turn_result["audio_chunks_found"] = len(audio_chunks)
                    results["audio_chunks_found"] += len(audio_chunks)

                    if audio_chunks:
                        print(f"    🎵 Extracted {len(audio_chunks)} audio chunks")

                        # Combine all audio chunks for this turn
                        combined_audio = b"".join(audio_chunks)

                        if combined_audio and self.speech_enabled:
                            print(
                                f"    🔄 Transcribing combined audio ({len(combined_audio)} bytes)..."
                            )

                            transcription = self.transcribe_audio_bytes(combined_audio)

                            if transcription["success"] and transcription["text"]:
                                turn_result["combined_audio_text"] = transcription["text"]
                                results["audio_transcribed"] += 1
                                print(f"    ✅ Agent said: '{transcription['text']}'")
                            else:
                                error_msg = transcription.get("error", "No speech detected")
                                print(f"    📭 No speech transcribed: {error_msg}")

                        elif combined_audio:
                            print("    📄 Audio extracted but speech recognition not available")
                            turn_result["combined_audio_text"] = (
                                "[Audio available - speech recognition disabled]"
                            )

                    else:
                        print("    📭 No audio chunks found in responses")
                else:
                    print("    📭 No full_responses_received data available")

                conv_result["turns"].append(turn_result)
                results["turns_processed"] += 1

            results["conversations"].append(conv_result)
            results["conversations_processed"] += 1

        return results

    def print_results(self, results: dict[str, Any]):
        """Print processing results in a readable format."""

        print("\n" + "=" * 60)
        print("AUDIO EXTRACTION AND TRANSCRIPTION RESULTS")
        print("=" * 60)

        print(f"File: {results['file']}")
        print(f"Conversations processed: {results['conversations_processed']}")
        print(f"Turns processed: {results['turns_processed']}")
        print(f"Audio chunks found: {results['audio_chunks_found']}")
        print(f"Audio successfully transcribed: {results['audio_transcribed']}")

        for conv in results.get("conversations", []):
            print(f"\n📞 Conversation: {conv['session_id'][:8]}... ({conv['template_name']})")

            for turn in conv["turns"]:
                print(f"  Turn {turn['turn_number']}:")
                print(f"    User: {turn['user_input']}")

                if turn["combined_audio_text"]:
                    print(f"    Agent: {turn['combined_audio_text']}")
                elif turn["audio_chunks_found"] > 0:
                    print(
                        f"    Agent: [Found {turn['audio_chunks_found']} audio chunks but no text transcribed]"
                    )
                else:
                    print("    Agent: [No audio found]")

        # Save results
        output_file = f"tests/load/results/audio_extraction_{int(results.get('timestamp', 0))}.json"
        results["timestamp"] = int(__import__("time").time())

        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n💾 Results saved to: {output_file}")


def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract and transcribe audio from conversation recordings"
    )
    parser.add_argument(
        "--file", "-f", required=True, help="Path to conversation recording JSON file"
    )
    parser.add_argument(
        "--speech-key",
        help="Azure Speech Service key (or set AZURE_SPEECH_KEY env var)",
    )
    parser.add_argument(
        "--speech-region",
        help="Azure Speech Service region (or set AZURE_SPEECH_REGION env var)",
    )

    args = parser.parse_args()

    # Check if file exists
    if not Path(args.file).exists():
        print(f"❌ File not found: {args.file}")
        exit(1)

    try:
        extractor = AudioExtractorFromRecording(
            speech_key=args.speech_key, speech_region=args.speech_region
        )

        results = extractor.process_conversation_file(args.file)

        if "error" in results:
            print(f"❌ Error: {results['error']}")
            exit(1)

        extractor.print_results(results)

        print("\n✅ Audio extraction and transcription complete!")

    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
