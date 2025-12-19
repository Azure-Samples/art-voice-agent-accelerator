#!/usr/bin/env python3
"""
Conversation Playback Utility

Plays back recorded conversations from load testing, allowing you to:
1. Listen to agent audio responses
2. See the conversation text flow
3. Analyze conversation patterns

Usage:
    python conversation_playback.py --conversation-file recorded_conversations_TIMESTAMP.json
    python conversation_playback.py --session-id load-test-abc123
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class ConversationPlayer:
    """Play back recorded conversations with audio and text analysis."""

    def __init__(self):
        self.results_dir = Path("tests/load/results")
        self.audio_dir = self.results_dir / "conversation_audio"

    def list_available_conversations(self):
        """List all available recorded conversations."""
        conversation_files = list(self.results_dir.glob("recorded_conversations_*.json"))

        if not conversation_files:
            print("No recorded conversations found in tests/load/results/")
            return

        print("Available recorded conversations:")
        for i, file in enumerate(conversation_files, 1):
            try:
                with open(file) as f:
                    data = json.load(f)
                print(f"{i}. {file.name}")
                print(f"   Conversations: {len(data)}")
                if data:
                    templates = set(conv.get("template_name", "unknown") for conv in data)
                    print(f"   Templates: {', '.join(templates)}")
                print()
            except Exception as e:
                print(f"{i}. {file.name} (error reading: {e})")

    def load_conversation_file(self, file_path: str) -> list[dict[str, Any]]:
        """Load conversations from JSON file."""
        file_path = Path(file_path)

        if not file_path.exists():
            # Try relative to results directory
            file_path = self.results_dir / file_path.name

        if not file_path.exists():
            raise FileNotFoundError(f"Conversation file not found: {file_path}")

        with open(file_path) as f:
            return json.load(f)

    def display_conversation_flow(self, conversation: dict[str, Any]):
        """Display the text flow of a conversation."""
        print(f"\n{'='*80}")
        print("CONVERSATION FLOW ANALYSIS")
        print(f"{'='*80}")
        print(f"Session ID: {conversation['session_id']}")
        print(f"Template: {conversation['template_name']}")
        print(f"Duration: {conversation['duration_s']:.1f}s")
        print(f"Total Turns: {conversation['total_turns']}")
        print(f"Successful Turns: {conversation['successful_turns']}")
        print(f"Audio Files: {len(conversation.get('audio_files', []))}")
        print()

        for turn in conversation["turns"]:
            print(
                f"TURN {turn['turn_number']} ({'✅ Success' if turn['turn_successful'] else '❌ Failed'})"
            )
            print(f"{'='*60}")

            flow = turn.get("conversation_flow", {})

            # User input
            print("👤 USER SAID:")
            print(f"   \"{flow.get('user_said', turn.get('user_input_text', 'N/A'))}\"")
            print()

            # Speech recognition result
            if flow.get("system_heard") or turn.get("user_speech_recognized"):
                print("🎯 SYSTEM HEARD:")
                heard_text = flow.get("system_heard") or turn.get("user_speech_recognized")
                print(f'   "{heard_text}"')

                # Check if recognition was accurate
                user_said = flow.get("user_said", turn.get("user_input_text", ""))
                if heard_text.lower().strip() != user_said.lower().strip():
                    print("   ⚠️  Recognition differs from input")
                print()

            # Agent text responses
            agent_responses = flow.get("agent_responded") or turn.get("agent_text_responses", [])
            if agent_responses:
                print("🤖 AGENT RESPONDED:")
                for i, response in enumerate(agent_responses, 1):
                    print(f'   {i}. "{response}"')
            else:
                print("🤖 AGENT RESPONDED: (Text not captured)")
            print()

            # Audio info
            audio_available = flow.get("audio_response_available", False)
            audio_files = [
                af for af in turn.get("audio_files", []) if af.get("type") == "combined_response"
            ]
            audio_chunks_received = turn.get("audio_chunks_received", 0)

            print("🎵 AUDIO RESPONSE:")
            if audio_available and audio_files:
                for audio_file in audio_files:
                    duration = audio_file.get("duration_s", 0)
                    size_kb = audio_file.get("size_bytes", 0) / 1024
                    print(f"   File: {audio_file['filename']}")
                    print(f"   Duration: {duration:.1f}s, Size: {size_kb:.1f}KB")
                    print(f"   Path: {audio_file['path']}")
            elif audio_available and audio_chunks_received > 0:
                print(f"   Audio response received: {audio_chunks_received} chunks")
                print(
                    "   (Audio file not saved - this was a non-recorded conversation or file save failed)"
                )
            else:
                print("   No audio response recorded")
            print()

            # Performance metrics
            print("⏱️  PERFORMANCE:")
            print(f"   Speech Recognition: {turn['speech_recognition_latency_ms']:.1f}ms")
            print(f"   Agent Processing: {turn['agent_processing_latency_ms']:.1f}ms")
            print(f"   End-to-End: {turn['end_to_end_latency_ms']:.1f}ms")
            print()

            if turn.get("error_message"):
                print(f"❌ ERROR: {turn['error_message']}")
                print()

            print("-" * 80)
            print()

    def play_audio_file(self, audio_path: str):
        """Play an audio file using system audio player."""
        audio_path = Path(audio_path)

        if not audio_path.exists():
            print(f"Audio file not found: {audio_path}")
            return False

        print(f"Playing audio: {audio_path.name}")

        # Try different audio players based on platform
        try:
            if sys.platform == "win32":
                # Windows - try Windows Media Player or built-in player
                subprocess.run(["start", str(audio_path)], shell=True, check=True)
            elif sys.platform == "darwin":
                # macOS - use afplay
                subprocess.run(["afplay", str(audio_path)], check=True)
            else:
                # Linux - try aplay for PCM files
                subprocess.run(
                    ["aplay", "-f", "S16_LE", "-r", "16000", str(audio_path)],
                    check=True,
                )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to play audio: {e}")
            return False
        except FileNotFoundError:
            print("No suitable audio player found on system")
            print(f"You can manually play the PCM file: {audio_path}")
            print("Format: 16-bit PCM, 16kHz sample rate")
            return False

    def interactive_playback(self, conversations: list[dict[str, Any]]):
        """Interactive conversation playback."""
        if not conversations:
            print("No conversations to play back")
            return

        print(f"Loaded {len(conversations)} conversations")
        print()

        while True:
            print("Select a conversation to analyze:")
            for i, conv in enumerate(conversations, 1):
                print(
                    f"{i}. {conv['template_name']} ({conv['session_id'][:8]}...) - {conv['total_turns']} turns"
                )

            print("0. Exit")

            try:
                choice = input("\nEnter your choice: ").strip()

                if choice == "0" or choice.lower() in ["exit", "quit"]:
                    break

                conv_idx = int(choice) - 1
                if 0 <= conv_idx < len(conversations):
                    conversation = conversations[conv_idx]
                    self.display_conversation_flow(conversation)

                    # Ask if user wants to play audio
                    audio_files = [
                        af
                        for af in conversation.get("audio_files", [])
                        if af.get("type") == "combined_response"
                    ]

                    if audio_files:
                        play_audio = input("\nPlay audio responses? (y/n): ").strip().lower()
                        if play_audio in ["y", "yes"]:
                            for audio_file in audio_files:
                                print(
                                    f"\nPlaying Turn {audio_file['filename'].split('_turn_')[1].split('_')[0]} audio..."
                                )
                                self.play_audio_file(audio_file["path"])
                                input("Press Enter to continue...")

                    input("\nPress Enter to return to conversation list...")
                else:
                    print("Invalid choice")

            except (ValueError, KeyboardInterrupt):
                print("\nExiting...")
                break


def main():
    parser = argparse.ArgumentParser(
        description="Play back recorded conversations from load testing"
    )
    parser.add_argument("--conversation-file", help="JSON file containing recorded conversations")
    parser.add_argument("--session-id", help="Specific session ID to analyze")
    parser.add_argument("--list", action="store_true", help="List available conversation files")

    args = parser.parse_args()

    player = ConversationPlayer()

    if args.list:
        player.list_available_conversations()
        return

    if args.conversation_file:
        try:
            conversations = player.load_conversation_file(args.conversation_file)

            if args.session_id:
                # Filter to specific session
                conversations = [c for c in conversations if c["session_id"] == args.session_id]
                if not conversations:
                    print(f"Session ID {args.session_id} not found")
                    return

            player.interactive_playback(conversations)

        except Exception as e:
            print(f"Error loading conversation file: {e}")
    else:
        # Show available files and let user choose
        player.list_available_conversations()
        print("\nUse --conversation-file <filename> to analyze specific conversations")


if __name__ == "__main__":
    main()
