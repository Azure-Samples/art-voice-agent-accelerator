#!/usr/bin/env python3
"""
Benchmark SpeechCascade TTS: blocking vs streaming synthesis.

Measures **time-to-first-audio (TTFA)** and total synthesis time for the two
synthesis paths on ``src.speech.text_to_speech.SpeechSynthesizer``:

  * ``synthesize_to_pcm``         — blocking; returns only after the whole
                                    utterance is rendered (current hot path).
  * ``synthesize_to_pcm_stream``  — streaming; yields PCM as Azure renders it.

TTFA is the dominant perceived-latency metric for real-time voice: how long the
caller waits in silence before hearing the first audio byte.

Usage:
    # Requires live Azure Speech credentials in the environment:
    #   AZURE_SPEECH_REGION (+ AZURE_SPEECH_KEY, or managed identity / az login)
    python tools/benchmark_tts_streaming.py
    python tools/benchmark_tts_streaming.py --voice en-US-AvaMultilingualNeural \
        --sample-rate 16000 --runs 3

Run this BEFORE and AFTER enabling streaming to capture a direct comparison.
The streaming column is the new behavior; the blocking column is the baseline.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
import wave
from pathlib import Path

# Make the repo importable when run directly.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_env() -> None:
    """Load the same config the app uses so this tool picks up Azure Speech
    credentials (AZURE_SPEECH_REGION/KEY) without a manual ``export``.

    Two layers, mirroring the backend:
      1. ``.env`` / ``.env.local`` (provides AZURE_APPCONFIG_ENDPOINT, etc.)
      2. Azure App Configuration (the real source of Speech region/key), synced
         into ``os.environ`` via ``bootstrap_appconfig`` when configured.

    Existing environment variables win for the dotenv layer (override=False).
    Failures are non-fatal — the caller still validates AZURE_SPEECH_REGION.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]

    if load_dotenv is not None:
        backend_dir = _REPO_ROOT / "apps" / "artagent" / "backend"
        for env_file in (
            backend_dir / ".env.local",
            _REPO_ROOT / ".env.local",
            _REPO_ROOT / ".env",
        ):
            if env_file.exists():
                load_dotenv(env_file, override=False)
                break

    # Layer 2: Azure App Configuration (where Speech region/key actually live).
    try:
        from apps.artagent.backend.config.appconfig_provider import bootstrap_appconfig

        bootstrap_appconfig()
    except Exception as exc:  # non-fatal; region check below reports the gap
        print(f"(App Configuration bootstrap skipped: {exc})", file=sys.stderr)


_load_env()

from src.speech.text_to_speech import SpeechSynthesizer  # noqa: E402

# Representative utterances across short/medium/long lengths.
SAMPLE_TEXTS = {
    "short": "Sure, one moment.",
    "medium": "Thanks for calling. I can help you check your account balance and recent transactions.",
    "long": (
        "I understand your concern, and I want to make sure we resolve this for you today. "
        "Let me pull up your account details, review the last few transactions, and then walk "
        "you through the options available so you can decide what works best for your situation."
    ),
}


def _fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:8.1f} ms"


def bench_blocking(synth: SpeechSynthesizer, text: str, voice: str, sample_rate: int) -> dict:
    """Measure blocking synthesis: first audio == total (no incremental output)."""
    start = time.perf_counter()
    pcm = synth.synthesize_to_pcm(
        text=text, voice=voice, sample_rate=sample_rate, style="chat", rate="+3%"
    )
    total = time.perf_counter() - start
    return {
        "ttfa": total,  # blocking: nothing is available until everything is
        "total": total,
        "bytes": len(pcm) if pcm else 0,
    }


def bench_streaming(synth: SpeechSynthesizer, text: str, voice: str, sample_rate: int) -> dict:
    """Measure streaming synthesis: TTFA == time until first yielded chunk."""
    start = time.perf_counter()
    ttfa: float | None = None
    total_bytes = 0
    for chunk in synth.synthesize_to_pcm_stream(
        text=text, voice=voice, sample_rate=sample_rate, style="chat", rate="+3%"
    ):
        if ttfa is None:
            ttfa = time.perf_counter() - start
        total_bytes += len(chunk)
    total = time.perf_counter() - start
    return {
        "ttfa": ttfa if ttfa is not None else total,
        "total": total,
        "bytes": total_bytes,
    }


def _summarize(runs: list[dict], key: str) -> tuple[float, float]:
    values = [r[key] for r in runs]
    return statistics.mean(values), (statistics.pstdev(values) if len(values) > 1 else 0.0)


def _write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    """Wrap raw little-endian 16-bit mono PCM in a WAV container for playback."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def dump_wav(synth: SpeechSynthesizer, text: str, voice: str, sample_rate: int, out_dir: Path) -> int:
    """
    Synthesize ``text`` via BOTH paths, save each as a WAV, and byte-compare.

    This isolates *content* from *delivery*: play the two WAVs directly. If
    ``streaming.wav`` sounds robotic/choppy on its own, the defect is in
    ``synthesize_to_pcm_stream`` (content). If both sound clean but the live
    call is robotic, the defect is in the WebSocket/AudioWorklet delivery path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    blocking_pcm = synth.synthesize_to_pcm(
        text=text, voice=voice, sample_rate=sample_rate, style="chat", rate="+3%"
    )
    stream_chunks = list(
        synth.synthesize_to_pcm_stream(
            text=text, voice=voice, sample_rate=sample_rate, style="chat", rate="+3%"
        )
    )
    streaming_pcm = b"".join(stream_chunks)

    blocking_path = out_dir / "blocking.wav"
    streaming_path = out_dir / "streaming.wav"
    _write_wav(blocking_path, blocking_pcm, sample_rate)
    _write_wav(streaming_path, streaming_pcm, sample_rate)

    print(f"Text: {text!r}")
    print(f"  sample_rate     : {sample_rate} Hz")
    print(f"  stream chunks   : {len(stream_chunks)} "
          f"(sizes: min={min((len(c) for c in stream_chunks), default=0)}, "
          f"max={max((len(c) for c in stream_chunks), default=0)})")
    print(f"  blocking  bytes : {len(blocking_pcm)}")
    print(f"  streaming bytes : {len(streaming_pcm)}")

    odd = [i for i, c in enumerate(stream_chunks) if len(c) % 2 != 0]
    if odd:
        print(f"  ⚠️  {len(odd)} stream chunk(s) have ODD byte length "
              f"(indices {odd[:10]}{'...' if len(odd) > 10 else ''}) — "
              f"a misaligned 16-bit sample boundary WILL cause robotic audio.")
    else:
        print("  ✓ all stream chunks are 16-bit aligned (even byte lengths)")

    if len(blocking_pcm) == len(streaming_pcm):
        if blocking_pcm == streaming_pcm:
            print("  ✓ blocking and streaming PCM are BYTE-IDENTICAL "
                  "→ content is fine; robotic audio is a DELIVERY/playback issue.")
        else:
            first_diff = next(
                (i for i in range(len(blocking_pcm)) if blocking_pcm[i] != streaming_pcm[i]),
                -1,
            )
            print(f"  ⚠️  same length but bytes DIFFER (first diff at offset {first_diff}) "
                  f"→ streaming content is corrupted.")
    else:
        print(f"  ⚠️  length mismatch (Δ={len(streaming_pcm) - len(blocking_pcm)} bytes) "
              f"→ streaming is dropping/duplicating audio.")

    print(f"\nWrote:\n  {blocking_path}\n  {streaming_path}")
    print("\n👉 Play BOTH files. If streaming.wav sounds robotic on its own, the bug is in")
    print("   synthesize_to_pcm_stream. If it sounds clean, the bug is in the live delivery path.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--voice",
        default="en-US-AvaMultilingualNeural",
        help="Neural voice name (default: en-US-AvaMultilingualNeural)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        choices=[16000, 24000, 48000],
        help="Output PCM sample rate (16000=ACS, 48000=browser)",
    )
    parser.add_argument(
        "--runs", type=int, default=3, help="Iterations per text/path (default: 3)"
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        default=True,
        help="Issue one warm-up synthesis before timing (default: on)",
    )
    parser.add_argument(
        "--dump-wav",
        metavar="DIR",
        default=None,
        help="Diagnostic mode: synthesize one utterance via both paths, save "
        "blocking.wav + streaming.wav to DIR, and byte-compare (skips timing).",
    )
    args = parser.parse_args()

    region = os.getenv("AZURE_SPEECH_REGION")
    if not region:
        print(
            "ERROR: AZURE_SPEECH_REGION is not set. Set Azure Speech credentials "
            "(AZURE_SPEECH_REGION + AZURE_SPEECH_KEY, or use managed identity / az login).",
            file=sys.stderr,
        )
        return 2

    print(f"Voice={args.voice}  sample_rate={args.sample_rate}Hz  runs={args.runs}  region={region}")
    print("=" * 78)

    synth = SpeechSynthesizer(voice=args.voice, playback="never")

    if not getattr(synth, "is_ready", False):
        print("ERROR: SpeechSynthesizer is not ready (check credentials).", file=sys.stderr)
        return 2

    if args.warmup:
        try:
            synth.warm_connection()
        except Exception as exc:  # non-fatal
            print(f"(warm-up skipped: {exc})")

    if args.dump_wav:
        return dump_wav(
            synth, SAMPLE_TEXTS["medium"], args.voice, args.sample_rate, Path(args.dump_wav)
        )

    header = (
        f"{'text':7} | {'path':9} | {'TTFA (mean±sd)':>22} | "
        f"{'total (mean±sd)':>22} | {'bytes':>8}"
    )
    print(header)
    print("-" * len(header))

    for label, text in SAMPLE_TEXTS.items():
        results: dict[str, list[dict]] = {"blocking": [], "streaming": []}
        for _ in range(args.runs):
            results["blocking"].append(bench_blocking(synth, text, args.voice, args.sample_rate))
            results["streaming"].append(bench_streaming(synth, text, args.voice, args.sample_rate))

        for path in ("blocking", "streaming"):
            ttfa_mean, ttfa_sd = _summarize(results[path], "ttfa")
            total_mean, total_sd = _summarize(results[path], "total")
            avg_bytes = int(statistics.mean(r["bytes"] for r in results[path]))
            print(
                f"{label:7} | {path:9} | "
                f"{_fmt_ms(ttfa_mean)} ±{_fmt_ms(ttfa_sd).strip():>9} | "
                f"{_fmt_ms(total_mean)} ±{_fmt_ms(total_sd).strip():>9} | "
                f"{avg_bytes:8d}"
            )

        # TTFA improvement for this text.
        b_ttfa, _ = _summarize(results["blocking"], "ttfa")
        s_ttfa, _ = _summarize(results["streaming"], "ttfa")
        if s_ttfa > 0:
            speedup = b_ttfa / s_ttfa
            saved_ms = (b_ttfa - s_ttfa) * 1000
            print(f"{'':7} | {'Δ TTFA':9} | streaming is {speedup:5.1f}x faster ({saved_ms:7.0f} ms sooner)")
        print("-" * len(header))

    print("\nNote: blocking TTFA == total (no audio until the full utterance renders).")
    print("Streaming TTFA is the time until the FIRST PCM chunk is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
