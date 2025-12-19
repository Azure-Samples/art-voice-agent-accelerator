#!/usr/bin/env python3
"""
Audio Generation Helper for Load Testing
========================================

Uses the production text-to-speech module to generate proper audio files
for conversational flows that will be recognized by the orchestrator.

This version writes human-readable filenames (phrase/label + short hash)
and a JSON sidecar per file with the original text and metadata. It also
appends a line to `manifest.jsonl` in the cache directory for quick lookup.
"""

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the src directory to Python path to import text_to_speech
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ["DISABLE_CLOUD_TELEMETRY"] = "true"

from src.speech.text_to_speech import SpeechSynthesizer


class LoadTestAudioGenerator:
    """Generates and caches audio files for load testing using production TTS."""

    def __init__(self, cache_dir: str = "tests/load/audio_cache"):
        """Initialize the audio generator with caching directory."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize the speech synthesizer with environment credentials
        self.synthesizer = SpeechSynthesizer(
            region=os.getenv("AZURE_SPEECH_REGION"),
            key=os.getenv("AZURE_SPEECH_KEY"),
            language="en-US",
            voice="en-US-JennyMultilingualNeural",  # Use a clear conversational voice
            playback="never",  # Disable local playback for load testing
            enable_tracing=False,  # Disable tracing for performance
        )

        print("🎤 Audio generator initialized")
        print(f"📂 Cache directory: {self.cache_dir}")
        print(f"🌍 Region: {os.getenv('AZURE_SPEECH_REGION')}")
        print(
            f"🔑 Using API Key: {'Yes' if os.getenv('AZURE_SPEECH_KEY') else 'No (DefaultAzureCredential)'}"
        )

    def _slugify(self, value: str, max_len: int = 60) -> str:
        """Create a filesystem-friendly slug from arbitrary text."""
        value = (value or "").strip().lower()
        # Keep alnum and replace spaces/invalids with '-'
        cleaned = []
        prev_dash = False
        for ch in value:
            if ch.isalnum():
                cleaned.append(ch)
                prev_dash = False
            elif ch in {" ", "-", "_"}:
                if not prev_dash:
                    cleaned.append("-")
                    prev_dash = True
            else:
                if not prev_dash:
                    cleaned.append("-")
                    prev_dash = True
        slug = "".join(cleaned).strip("-")
        if len(slug) > max_len:
            slug = slug[:max_len].rstrip("-")
        return slug or "audio"

    def _short_hash(self, text: str, voice: str) -> str:
        """Deterministic short hash for content identity."""
        return hashlib.md5(f"{text}|{voice}".encode()).hexdigest()[:10]

    def _full_hash(self, text: str, voice: str) -> str:
        """Full MD5 hash retained for legacy cache compatibility."""
        return hashlib.md5(f"{text}|{voice}".encode()).hexdigest()

    def _find_cached_by_hash(self, short_hash: str, full_hash: str | None = None) -> Path | None:
        """Find an existing cached file that matches the hash regardless of prefix.

        Also checks for legacy filenames of the form `audio_<fullhash>.pcm`.
        """
        # New-style readable filenames with suffix _<short_hash>.pcm
        for p in self.cache_dir.glob(f"*_{short_hash}.pcm"):
            if p.is_file():
                return p
        # Legacy naming: audio_<fullhash>.pcm
        if full_hash:
            legacy = self.cache_dir / f"audio_{full_hash}.pcm"
            if legacy.exists() and legacy.is_file():
                return legacy
        return None

    def _resolve_cache_path(self, text: str, voice: str, label: str | None) -> Path:
        """Resolve a readable, deterministic cache path based on text/voice and optional label.

        If a file already exists for the same text+voice (matched by short hash), reuse it.
        Otherwise, generate a slug-based filename that includes the label and a short hash.
        """
        shash = self._short_hash(text, voice)
        fhash = self._full_hash(text, voice)
        # Reuse any existing file for this hash
        existing = self._find_cached_by_hash(shash, fhash)
        if existing:
            return existing
        # Build a readable prefix from label or text snippet
        prefix_source = label or text[:80]
        # Prefer a short phrase-based slug to aid identification
        prefix = self._slugify(prefix_source)
        return self.cache_dir / f"{prefix}_{shash}.pcm"

    def generate_audio(
        self,
        text: str,
        voice: str = None,
        force_regenerate: bool = False,
        label: str | None = None,
        scenario: str | None = None,
        turn_index: int | None = None,
        turn_count: int | None = None,
    ) -> bytes:
        """
        Generate audio for the given text using Azure TTS.

        Args:
            text: Text to synthesize
            voice: Optional voice name (defaults to configured voice)
            force_regenerate: If True, regenerate even if cached

        Returns:
            PCM audio data bytes suitable for streaming
        """
        voice = voice or self.synthesizer.voice
        cache_file = self._resolve_cache_path(text, voice, label)

        # Return cached audio if available and not forcing regeneration
        if cache_file.exists() and not force_regenerate:
            print(f"📄 Using cached audio: {cache_file.name}")
            return cache_file.read_bytes()

        print(f"🎵 Generating audio for: '{text[:50]}...'")

        try:
            # Generate audio using production TTS with optimized settings for speech recognition
            audio_bytes = self.synthesizer.synthesize_to_pcm(
                text=text,
                voice=voice,
                sample_rate=16000,  # Standard rate for speech recognition
                style="chat",  # Conversational style
                rate="+0%",  # Natural rate
            )

            if not audio_bytes:
                raise ValueError("No audio data generated")

            # Cache the generated audio
            cache_file.write_bytes(audio_bytes)
            duration_sec = len(audio_bytes) / (16000 * 2)
            print(f"✅ Cached {len(audio_bytes)} bytes → {cache_file.name} ({duration_sec:.2f}s)")

            # Write sidecar metadata for human readability
            meta = {
                "filename": cache_file.name,
                "path": str(cache_file),
                "text": text,
                "voice": voice,
                "sample_rate": 16000,
                "style": "chat",
                "rate": "+0%",
                "duration_seconds": duration_sec,
                "label": label,
                "scenario": scenario,
                "turn_index": turn_index,
                "turn_count": turn_count,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "hash": self._short_hash(text, voice),
            }
            try:
                sidecar = cache_file.with_suffix(".json")
                sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
                # Append to global manifest.jsonl for quick lookup
                with (self.cache_dir / "manifest.jsonl").open("a", encoding="utf-8") as mf:
                    mf.write(json.dumps(meta, ensure_ascii=False) + "\n")
            except Exception as me:
                print(f"⚠️  Failed to write metadata for {cache_file.name}: {me}")

            return audio_bytes

        except Exception as e:
            print(f"❌ Failed to generate audio: {e}")
            # Return empty bytes to avoid breaking the simulation
            return b""

    def pregenerate_conversation_audio(
        self, conversation_texts: list, voice: str = None
    ) -> dict[str, bytes]:
        """
        Pre-generate audio for all texts in a conversation.

        Args:
            conversation_texts: List of text strings to generate audio for
            voice: Optional voice name

        Returns:
            Dictionary mapping text to audio bytes
        """
        print(f"🔄 Pre-generating audio for {len(conversation_texts)} utterances...")

        audio_cache = {}
        for i, text in enumerate(conversation_texts):
            print(f"📝 [{i+1}/{len(conversation_texts)}] Processing: '{text[:50]}...'")
            label = f"utterance-{i+1}"
            audio_bytes = self.generate_audio(text, voice, label=label)
            audio_cache[text] = audio_bytes

        print(f"✅ Pre-generation complete: {len(audio_cache)} audio files ready")
        return audio_cache

    def clear_cache(self):
        """Clear all cached audio files."""
        cache_files = list(self.cache_dir.glob("*.pcm"))
        for cache_file in cache_files:
            cache_file.unlink()
        print(f"🗑️ Cleared {len(cache_files)} cached audio files")

    def get_cache_info(self) -> dict[str, any]:
        """Get information about the audio cache."""
        cache_files = list(self.cache_dir.glob("*.pcm"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "cache_directory": str(self.cache_dir),
            "file_count": len(cache_files),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
        }

    def validate_configuration(self) -> bool:
        """Validate that the TTS configuration is working."""
        try:
            print("🔍 Validating Azure TTS configuration...")
            return self.synthesizer.validate_configuration()
        except Exception as e:
            print(f"❌ Configuration validation failed: {e}")
            return False

    def generate_conversation_sets(
        self, max_turns: int = 10, scenarios: list = None
    ) -> dict[str, dict[str, bytes]]:
        """
        Generate multiple conversation sets with configurable turn counts.

        Args:
            max_turns: Maximum number of turns to generate per conversation
            scenarios: List of conversation scenarios to generate

        Returns:
            Dictionary mapping scenario names to audio cache dictionaries
        """
        if scenarios is None:
            scenarios = [
                "insurance_inquiry",
                "quick_question",
                "confused_customer",
                "claim_filing",
                "policy_update",
                "billing_inquiry",
            ]

        conversation_templates = self._get_conversation_templates()
        all_conversation_sets = {}

        print(
            f"🎭 Generating conversation sets for {len(scenarios)} scenarios, up to {max_turns} turns each"
        )

        for scenario in scenarios:
            if scenario not in conversation_templates:
                print(f"⚠️  Skipping unknown scenario: {scenario}")
                continue

            scenario_audio_cache = {}
            base_texts = conversation_templates[scenario]

            print(f"\n📋 Processing scenario: {scenario}")

            # Generate audio for each turn count (1 to max_turns)
            for turn_count in range(1, min(max_turns + 1, len(base_texts) + 1)):
                conversation_texts = base_texts[:turn_count]

                print(f"  🔄 Generating {turn_count}-turn conversation...")

                for i, text in enumerate(conversation_texts):
                    turn_key = f"{scenario}_turn_{i+1}_of_{turn_count}"
                    label = f"{scenario}-turn-{i+1}-of-{turn_count}"
                    audio_bytes = self.generate_audio(
                        text,
                        label=label,
                        scenario=scenario,
                        turn_index=i + 1,
                        turn_count=turn_count,
                    )
                    scenario_audio_cache[turn_key] = audio_bytes

                    duration = len(audio_bytes) / (16000 * 2) if audio_bytes else 0
                    print(f"    📝 Turn {i+1}: '{text[:40]}...' ({duration:.2f}s)")

            all_conversation_sets[scenario] = scenario_audio_cache
            print(f"  ✅ {scenario}: {len(scenario_audio_cache)} audio files generated")

        return all_conversation_sets

    def _get_conversation_templates(self) -> dict[str, list]:
        """Define conversation templates for 2 simplified scenarios."""
        return {
            "insurance_inquiry": [
                "Hello, my name is Alice Brown, my social is 1234, and my zip code is 60601",
                "I'm calling about my auto insurance policy",
                "I need to understand what's covered under my current plan",
                "What happens if I get into an accident?",
                "Thank you for all the information, that's very helpful",
            ],
            "quick_question": [
                "Hi there, I have a quick question",
                "Can you help me check my account balance?",
                "Thanks, that's all I needed to know",
            ],
        }


def main():
    """Enhanced audio generator with multiple conversation scenarios."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate PCM audio files for load testing")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=5,
        help="Maximum number of turns per conversation (default: 5)",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=["insurance_inquiry", "quick_question"],
        default=["insurance_inquiry", "quick_question"],
        help="Conversation scenarios to generate (simplified to 2 scenarios)",
    )
    parser.add_argument(
        "--voices",
        nargs="+",
        default=["en-US-JennyMultilingualNeural"],
        help="Voice names to use for generation",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear existing cache before generating",
    )

    args = parser.parse_args()

    generator = LoadTestAudioGenerator()

    # Clear cache if requested
    if args.clear_cache:
        generator.clear_cache()

    # Validate configuration
    if not generator.validate_configuration():
        print("❌ Configuration validation failed. Please check your Azure Speech credentials.")
        return

    # Generate conversation sets for multiple voices
    all_generated = {}

    for voice in args.voices:
        print(f"\n🎤 Generating audio with voice: {voice}")
        generator.synthesizer.voice = voice

        conversation_sets = generator.generate_conversation_sets(
            max_turns=args.max_turns, scenarios=args.scenarios
        )

        all_generated[voice] = conversation_sets

    # Summary report
    print("\n📊 GENERATION SUMMARY")
    print("=" * 60)

    total_files = 0
    for voice, scenarios in all_generated.items():
        voice_files = sum(len(audio_cache) for audio_cache in scenarios.values())
        total_files += voice_files
        print(f"🎤 {voice}: {voice_files} files across {len(scenarios)} scenarios")

        for scenario, audio_cache in scenarios.items():
            total_duration = sum(
                len(audio_bytes) / (16000 * 2)
                for audio_bytes in audio_cache.values()
                if audio_bytes
            )
            print(f"   📋 {scenario}: {len(audio_cache)} files, {total_duration:.1f}s total")

    # Show cache info
    cache_info = generator.get_cache_info()
    print("\n📂 Cache Info:")
    print(f"  Files: {cache_info['file_count']}")
    print(f"  Size: {cache_info['total_size_mb']:.2f} MB")
    print(f"  Directory: {cache_info['cache_directory']}")

    print(f"\n✅ Generated {total_files} total audio files")
    print(f"🚀 Ready for load testing with up to {args.max_turns} conversation turns!")


if __name__ == "__main__":
    main()
