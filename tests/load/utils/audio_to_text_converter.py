#!/usr/bin/env python3
"""
Audio to Text Converter for Load Test Analysis

Converts recorded PCM audio chunks to text using Azure Speech Services
to understand what the agent actually said during conversations.
"""

import json
import wave
import tempfile
from pathlib import Path
from typing import List, Dict, Any
import azure.cognitiveservices.speech as speechsdk
import os
from dataclasses import dataclass


@dataclass
class AudioTranscription:
    """Results from audio-to-text conversion."""

    audio_file: str
    transcribed_text: str
    confidence: float
    duration_s: float
    success: bool
    error_message: str = ""


class AudioToTextConverter:
    """Converts recorded PCM audio files to text using Azure Speech Services."""

    def __init__(self, speech_key: str = None, speech_region: str = None):
        """Initialize with Azure Speech Service credentials."""
        # Try to get credentials from environment
        self.speech_key = speech_key or os.getenv("AZURE_SPEECH_KEY")
        self.speech_region = speech_region or os.getenv("AZURE_SPEECH_REGION")

        if not self.speech_key or not self.speech_region:
            raise ValueError(
                "Azure Speech Service credentials required. Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION environment variables."
            )

        # Configure speech recognizer
        speech_config = speechsdk.SpeechConfig(
            subscription=self.speech_key, region=self.speech_region
        )
        speech_config.speech_recognition_language = "en-US"

        self.speech_config = speech_config

    def pcm_to_wav(self, pcm_file_path: str, wav_file_path: str) -> bool:
        """Convert PCM file to WAV format for speech recognition."""
        try:
            # Read PCM data
            with open(pcm_file_path, "rb") as pcm_file:
                pcm_data = pcm_file.read()

            # Create WAV file
            with wave.open(wav_file_path, "wb") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(16000)  # 16kHz
                wav_file.writeframes(pcm_data)

            return True

        except Exception as e:
            print(f"Error converting PCM to WAV: {e}")
            return False

    def transcribe_audio_file(self, audio_file_path: str) -> AudioTranscription:
        """Transcribe a single audio file to text."""

        audio_file_path = Path(audio_file_path)

        # Check if file exists
        if not audio_file_path.exists():
            return AudioTranscription(
                audio_file=str(audio_file_path),
                transcribed_text="",
                confidence=0.0,
                duration_s=0.0,
                success=False,
                error_message="Audio file not found",
            )

        try:
            # Convert PCM to WAV if needed
            if audio_file_path.suffix.lower() == ".pcm":
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as temp_wav:
                    wav_file_path = temp_wav.name

                if not self.pcm_to_wav(str(audio_file_path), wav_file_path):
                    return AudioTranscription(
                        audio_file=str(audio_file_path),
                        transcribed_text="",
                        confidence=0.0,
                        duration_s=0.0,
                        success=False,
                        error_message="Failed to convert PCM to WAV",
                    )
            else:
                wav_file_path = str(audio_file_path)

            # Calculate duration
            duration_s = audio_file_path.stat().st_size / (16000 * 2)  # 16kHz, 16-bit

            # Create audio input
            audio_input = speechsdk.AudioConfig(filename=wav_file_path)
            speech_recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config, audio_config=audio_input
            )

            # Perform recognition
            result = speech_recognizer.recognize_once()

            # Clean up temp file if created
            if audio_file_path.suffix.lower() == ".pcm":
                try:
                    os.unlink(wav_file_path)
                except:
                    pass

            # Process result
            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                return AudioTranscription(
                    audio_file=str(audio_file_path),
                    transcribed_text=result.text,
                    confidence=1.0,  # Azure doesn't provide confidence in recognize_once
                    duration_s=duration_s,
                    success=True,
                )
            elif result.reason == speechsdk.ResultReason.NoMatch:
                return AudioTranscription(
                    audio_file=str(audio_file_path),
                    transcribed_text="",
                    confidence=0.0,
                    duration_s=duration_s,
                    success=True,
                    error_message="No speech detected",
                )
            else:
                return AudioTranscription(
                    audio_file=str(audio_file_path),
                    transcribed_text="",
                    confidence=0.0,
                    duration_s=duration_s,
                    success=False,
                    error_message=f"Recognition failed: {result.reason}",
                )

        except Exception as e:
            return AudioTranscription(
                audio_file=str(audio_file_path),
                transcribed_text="",
                confidence=0.0,
                duration_s=0.0,
                success=False,
                error_message=str(e),
            )

    def process_conversation_recordings(self, conversation_file: str) -> Dict[str, Any]:
        """Process all audio files in a conversation recording and add transcriptions."""

        with open(conversation_file, "r") as f:
            conversations = json.load(f)

        results = {
            "transcription_summary": {
                "total_audio_files": 0,
                "successfully_transcribed": 0,
                "failed_transcriptions": 0,
                "empty_audio": 0,
            },
            "conversations": [],
        }

        print(f"🎤 Processing audio transcriptions from: {conversation_file}")

        for conv_idx, conversation in enumerate(conversations):
            print(
                f"\n📞 Conversation {conv_idx + 1}: {conversation['session_id'][:8]}..."
            )

            conv_result = {
                "session_id": conversation["session_id"],
                "template_name": conversation["template_name"],
                "duration_s": conversation["duration_s"],
                "turns": [],
            }

            for turn in conversation["turns"]:
                turn_result = {
                    "turn_number": turn["turn_number"],
                    "user_input_text": turn["user_input_text"],
                    "user_speech_recognized": turn["user_speech_recognized"],
                    "agent_text_responses": turn["agent_text_responses"],
                    "audio_chunks_received": turn["audio_chunks_received"],
                    "transcribed_agent_responses": [],
                }

                # Transcribe audio files for this turn
                if "audio_files" in turn and turn["audio_files"]:
                    print(
                        f"  🔄 Turn {turn['turn_number']}: Transcribing {len(turn['audio_files'])} audio files..."
                    )

                    for audio_file_info in turn["audio_files"]:
                        if "path" in audio_file_info:
                            audio_path = audio_file_info["path"]

                            # Transcribe the audio
                            transcription = self.transcribe_audio_file(audio_path)

                            if transcription.success:
                                if transcription.transcribed_text.strip():
                                    print(
                                        f"    ✅ {audio_file_info.get('filename', 'audio')}: '{transcription.transcribed_text}'"
                                    )
                                    results["transcription_summary"][
                                        "successfully_transcribed"
                                    ] += 1
                                else:
                                    print(
                                        f"    📭 {audio_file_info.get('filename', 'audio')}: No speech detected"
                                    )
                                    results["transcription_summary"]["empty_audio"] += 1
                            else:
                                print(
                                    f"    ❌ {audio_file_info.get('filename', 'audio')}: {transcription.error_message}"
                                )
                                results["transcription_summary"][
                                    "failed_transcriptions"
                                ] += 1

                            # Add transcription to results
                            turn_result["transcribed_agent_responses"].append(
                                {
                                    "audio_file": audio_file_info.get(
                                        "filename", "unknown"
                                    ),
                                    "transcribed_text": transcription.transcribed_text,
                                    "confidence": transcription.confidence,
                                    "duration_s": transcription.duration_s,
                                    "success": transcription.success,
                                    "error_message": transcription.error_message,
                                }
                            )

                            results["transcription_summary"]["total_audio_files"] += 1
                else:
                    print(
                        f"  📭 Turn {turn['turn_number']}: No audio files to transcribe"
                    )

                conv_result["turns"].append(turn_result)

            results["conversations"].append(conv_result)

        return results

    def save_transcription_results(
        self, results: Dict[str, Any], output_file: str = None
    ):
        """Save transcription results to JSON file."""

        if output_file is None:
            timestamp = Path(output_file).stem if output_file else "transcriptions"
            output_file = f"tests/load/results/audio_transcriptions_{timestamp}.json"

        # Create output directory
        output_dir = Path(output_file).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n💾 Transcription results saved to: {output_file}")

        # Print summary
        summary = results["transcription_summary"]
        print(f"\n📊 TRANSCRIPTION SUMMARY:")
        print(f"   Total audio files: {summary['total_audio_files']}")
        print(f"   Successfully transcribed: {summary['successfully_transcribed']}")
        print(f"   Empty/no speech: {summary['empty_audio']}")
        print(f"   Failed transcriptions: {summary['failed_transcriptions']}")

        if summary["total_audio_files"] > 0:
            success_rate = (
                (summary["successfully_transcribed"] + summary["empty_audio"])
                / summary["total_audio_files"]
                * 100
            )
            print(f"   Success rate: {success_rate:.1f}%")


def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert recorded conversation audio to text"
    )
    parser.add_argument(
        "--conversation-file",
        "-f",
        required=True,
        help="Path to recorded conversation JSON file",
    )
    parser.add_argument("--output", "-o", help="Output file for transcription results")
    parser.add_argument(
        "--speech-key",
        help="Azure Speech Service key (or set AZURE_SPEECH_KEY env var)",
    )
    parser.add_argument(
        "--speech-region",
        help="Azure Speech Service region (or set AZURE_SPEECH_REGION env var)",
    )

    args = parser.parse_args()

    try:
        # Initialize converter
        converter = AudioToTextConverter(
            speech_key=args.speech_key, speech_region=args.speech_region
        )

        # Process conversations
        results = converter.process_conversation_recordings(args.conversation_file)

        # Save results
        converter.save_transcription_results(results, args.output)

        print(f"\n✅ Audio transcription complete!")

    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
