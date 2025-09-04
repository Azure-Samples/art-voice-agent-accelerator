#!/usr/bin/env python3
"""
Standalone Audio File Generator for Load Testing

This script generates realistic customer audio files using Azure Speech Services
for testing the various agent flows (Auth, FNOL, General Info).

Usage:
    python generate_test_audio.py
    python generate_test_audio.py --output-dir ./test_audio --count 10
    python generate_test_audio.py --agent-type auth --voice "en-US-AriaNeural"
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
import logging

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load environment variables
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Import Azure Speech SDK and identity libraries
try:
    import azure.cognitiveservices.speech as speechsdk
    from azure.identity import DefaultAzureCredential
except ImportError:
    logging.error("Required Azure libraries not installed. Please install:")
    logging.error("pip install azure-cognitiveservices-speech azure-identity")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Customer conversation samples organized by agent type
CUSTOMER_CONVERSATIONS = {
    "auth": [
        "Hi, my name is Alice Brown, my zip code is 60610, and my last four digits of social security are 1234",
        "Hello, this is John Smith. My ZIP is 90210 and the last four of my SSN are 5678",
        "This is Maria Garcia, ZIP code 33101, last four social security digits 9876",
        "My name is David Wilson, I live in ZIP 10001, last four of my social are 4321",
        "Hi there, I'm Sarah Johnson. My ZIP code is 78701 and my last four SSN digits are 8765",
    ],
    "fnol_new_claim": [
        "I need to file a claim. I was rear-ended on Highway 95 about an hour ago",
        "I was in a car accident this morning. A truck hit my passenger side door",
        "My car was damaged in a parking lot. Someone hit it and left a note with their information",
        "I need to report a claim. My windshield was cracked by flying debris on the freeway",
        "I was backing out of my driveway and hit my neighbor's fence. I need to file a claim",
        "A tree fell on my car during the storm last night. I need to start a claim",
        "Someone broke into my car and stole my laptop. I want to file a theft claim",
    ],
    "fnol_existing_claim": [
        "I'm calling about my claim. The adjuster hasn't called me back yet",
        "I filed a claim last week and need an update on the status",
        "My claim number is 12345 and I wanted to check if you received the photos I sent",
        "I submitted my claim documents three days ago but haven't heard anything back",
        "The repair shop is asking for authorization. When will my claim be approved?",
        "I got an estimate but it's higher than what the adjuster quoted. What do I do?",
    ],
    "general_info": [
        "What does my comprehensive coverage include exactly?",
        "I want to know what my deductible is for collision coverage",
        "Can you explain what roadside assistance covers under my policy?",
        "I'm moving to a new state. Do I need to update my policy?",
        "How much does it cost to add a teenage driver to my policy?",
        "What's the difference between liability and full coverage?",
        "I want to increase my coverage limits. How much would that cost?",
        "Can you help me understand what uninsured motorist coverage does?",
    ],
    "emergency": [
        "I've been in an accident and my passenger is bleeding. We need help immediately",
        "There's smoke coming from my engine and I smell gas. What should I do?",
        "My car went off the road and we're trapped inside. Please send help",
        "I hit a pedestrian. They're not moving. I need emergency services now",
        "My car is on fire after the accident. I got out but I need the fire department",
    ],
    "escalation": [
        "I've been trying to reach someone about my claim for three weeks. This is ridiculous",
        "Your adjuster denied my claim but I think it should be covered. I want to speak to a supervisor",
        "I'm not satisfied with the settlement offer. I want to escalate this to management",
        "This is the fourth time I've called about the same issue. I need to speak to someone in charge",
        "I'm considering hiring a lawyer if this isn't resolved today",
    ],
}

# Voice options for different conversation types
VOICE_OPTIONS = {
    "default": "en-US-JennyMultilingualNeural",
    "male": "en-US-BrianMultilingualNeural",
    "female": "en-US-EmmaMultilingualNeural",
    "calm": "en-US-AriaNeural",
    "urgent": "en-US-DavisNeural",
    "frustrated": "en-US-GuyNeural",
}


class TestAudioGenerator:
    """Generate audio files for load testing customer conversations."""

    def __init__(self, output_dir: str = "./test_audio"):
        """Initialize the audio generator.

        Args:
            output_dir: Directory to save generated audio files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Azure Speech configuration with DefaultAzureCredential
        speech_region = os.getenv("AZURE_SPEECH_REGION", "centralus")
        speech_endpoint = os.getenv("AZURE_SPEECH_ENDPOINT")

        logger.info("Authenticating with DefaultAzureCredential...")

        try:
            # Get access token using DefaultAzureCredential
            credential = DefaultAzureCredential()
            token = credential.get_token("https://cognitiveservices.azure.com/.default")

            # Create speech config with endpoint if available, otherwise use region
            if speech_endpoint:
                logger.info(f"Using Azure Speech endpoint: {speech_endpoint}")
                self.speech_config = speechsdk.SpeechConfig(endpoint=speech_endpoint)
                self.speech_config.authorization_token = token.token
            else:
                logger.info(f"Using Azure Speech region: {speech_region}")
                self.speech_config = speechsdk.SpeechConfig(region=speech_region)
                self.speech_config.authorization_token = token.token

            # Store credential for token refresh if needed
            self._credential = credential

            logger.info("Successfully authenticated with DefaultAzureCredential")

        except Exception as e:
            logger.error(f"Failed to authenticate with DefaultAzureCredential: {e}")
            logger.error(
                "Please ensure you are logged in with 'az login' or have appropriate credentials configured"
            )
            raise

        # Set default voice
        self.speech_config.speech_synthesis_voice_name = VOICE_OPTIONS["default"]

        logger.info(
            f"Initialized audio generator with output directory: {self.output_dir}"
        )
        logger.info(f"Using Azure Speech region: {speech_region}")

    def generate_audio_file(
        self,
        text: str,
        filename: str,
        voice: str = None,
        style: str = "chat",
        rate: str = "+5%",
    ) -> Optional[str]:
        """Generate a single audio file from text.

        Args:
            text: Text to synthesize
            filename: Output filename (without extension)
            voice: Voice to use (defaults to current voice)
            style: Speech style
            rate: Speech rate

        Returns:
            Path to generated file or None if failed
        """
        try:
            # Use the existing authenticated speech config
            config = self.speech_config

            # Set voice for this synthesis
            current_voice = voice or config.speech_synthesis_voice_name
            config.speech_synthesis_voice_name = current_voice

            # Set output file
            file_path = self.output_dir / f"{filename}.wav"
            audio_config = speechsdk.audio.AudioOutputConfig(filename=str(file_path))

            # Create synthesizer and synthesize
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=config, audio_config=audio_config
            )

            # Use simple text synthesis first to test
            result = synthesizer.speak_text_async(text).get()

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info(f"Generated audio file: {file_path}")
                return str(file_path)
            else:
                logger.error(f"Speech synthesis failed with reason: {result.reason}")
                # Try to get error details safely
                try:
                    if hasattr(result, "error_details") and result.error_details:
                        logger.error(f"Error details: {result.error_details}")
                except:
                    logger.error("Could not retrieve error details")
                return None

        except Exception as e:
            logger.error(f"Error generating audio for '{filename}': {e}")
            return None

    def generate_agent_conversations(
        self, agent_type: str, count: int = None, voice: str = None
    ) -> List[str]:
        """Generate audio files for a specific agent type.

        Args:
            agent_type: Type of agent conversation (auth, fnol_new_claim, etc.)
            count: Number of files to generate (None = all available)
            voice: Voice to use for generation

        Returns:
            List of generated file paths
        """
        if agent_type not in CUSTOMER_CONVERSATIONS:
            logger.error(f"Unknown agent type: {agent_type}")
            return []

        conversations = CUSTOMER_CONVERSATIONS[agent_type]
        if count:
            conversations = conversations[:count]

        generated_files = []

        # Select appropriate voice based on agent type
        if not voice:
            if agent_type == "emergency":
                voice = VOICE_OPTIONS["urgent"]
            elif agent_type == "escalation":
                voice = VOICE_OPTIONS["frustrated"]
            else:
                voice = VOICE_OPTIONS["default"]

        for i, text in enumerate(conversations, 1):
            filename = f"{agent_type}_{i:02d}"
            file_path = self.generate_audio_file(text, filename, voice=voice)
            if file_path:
                generated_files.append(file_path)

        logger.info(f"Generated {len(generated_files)} files for {agent_type}")
        return generated_files

    def generate_all_conversations(
        self, count_per_type: int = None
    ) -> Dict[str, List[str]]:
        """Generate audio files for all agent types.

        Args:
            count_per_type: Max number of files per agent type

        Returns:
            Dictionary mapping agent types to generated file paths
        """
        all_generated = {}

        for agent_type in CUSTOMER_CONVERSATIONS.keys():
            generated_files = self.generate_agent_conversations(
                agent_type, count_per_type
            )
            all_generated[agent_type] = generated_files

        return all_generated

    def create_manifest(self, generated_files: Dict[str, List[str]]) -> str:
        """Create a JSON manifest of generated audio files.

        Args:
            generated_files: Dictionary of agent types to file paths

        Returns:
            Path to manifest file
        """
        manifest = {
            "generated_at": "",
            "total_files": sum(len(files) for files in generated_files.values()),
            "agent_types": {},
        }

        import datetime

        manifest["generated_at"] = datetime.datetime.now().isoformat()

        for agent_type, file_paths in generated_files.items():
            manifest["agent_types"][agent_type] = {
                "count": len(file_paths),
                "files": [
                    {
                        "filename": Path(fp).name,
                        "path": fp,
                        "text": self._get_text_for_file(agent_type, Path(fp).name),
                    }
                    for fp in file_paths
                ],
            }

        manifest_path = self.output_dir / "audio_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Created manifest: {manifest_path}")
        return str(manifest_path)

    def _get_text_for_file(self, agent_type: str, filename: str) -> str:
        """Get the original text for a generated file."""
        try:
            # Extract index from filename (e.g., "auth_01.wav" -> 0)
            index = int(filename.split("_")[1].split(".")[0]) - 1
            return CUSTOMER_CONVERSATIONS[agent_type][index]
        except (IndexError, ValueError):
            return "Unknown text"


def main():
    """Main function with command-line interface."""
    parser = argparse.ArgumentParser(
        description="Generate customer audio files for load testing"
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        default="./test_audio",
        help="Output directory for audio files (default: ./test_audio)",
    )

    parser.add_argument(
        "--agent-type",
        "-a",
        choices=list(CUSTOMER_CONVERSATIONS.keys()) + ["all"],
        default="all",
        help="Type of agent conversation to generate (default: all)",
    )

    parser.add_argument(
        "--count",
        "-c",
        type=int,
        help="Number of files to generate per agent type (default: all available)",
    )

    parser.add_argument(
        "--voice",
        "-v",
        choices=list(VOICE_OPTIONS.values()),
        help="Voice to use for synthesis",
    )

    parser.add_argument(
        "--list-voices", action="store_true", help="List available voice options"
    )

    args = parser.parse_args()

    if args.list_voices:
        print("Available voice options:")
        for name, voice in VOICE_OPTIONS.items():
            print(f"  {name}: {voice}")
        return

    # Check for required environment variables for DefaultAzureCredential
    speech_region = os.getenv("AZURE_SPEECH_REGION", "centralus")

    logger.info(f"Using Azure Speech Services in region: {speech_region}")
    logger.info("Authenticating with DefaultAzureCredential (no API key required)")
    logger.info(
        "Make sure you're logged in with 'az login' or have appropriate Azure credentials configured"
    )

    # Initialize generator
    generator = TestAudioGenerator(args.output_dir)

    try:
        if args.agent_type == "all":
            logger.info("Generating audio files for all agent types...")
            generated_files = generator.generate_all_conversations(args.count)
        else:
            logger.info(f"Generating audio files for {args.agent_type} agent...")
            files = generator.generate_agent_conversations(
                args.agent_type, args.count, args.voice
            )
            generated_files = {args.agent_type: files}

        # Create manifest
        manifest_path = generator.create_manifest(generated_files)

        # Summary
        total_files = sum(len(files) for files in generated_files.values())
        logger.info(f"\n=== Generation Complete ===")
        logger.info(f"Total files generated: {total_files}")
        logger.info(f"Output directory: {generator.output_dir}")
        logger.info(f"Manifest file: {manifest_path}")

        for agent_type, files in generated_files.items():
            logger.info(f"  {agent_type}: {len(files)} files")

    except KeyboardInterrupt:
        logger.info("Generation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during generation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
