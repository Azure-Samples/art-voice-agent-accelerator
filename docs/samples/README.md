# Samples & Labs

Explore hands-on notebooks that demonstrate how to build and extend the Real-Time
Voice Agent. The repository groups content into quickstart “Hello World” tutorials
and deeper lab exercises.

## Hello World Series

Beginner-friendly notebooks under `samples/hello_world/` walk through the core
features step by step.

| Notebook | Summary |
| --- | --- |
| `01-create-your-first-rt-agent.ipynb` | Assemble a basic customer-support voice agent end to end. |
| `02-run-test-rt-agent.ipynb` | Execute call flows and validate the agent locally. |
| `03-create-your-first-foundry-agents.ipynb` | Provision Azure AI Foundry agents and wire them into the pipeline. |
| `04-exploring-live-api.ipynb` | Explore Azure Live Voice API capabilities. |
| `05-create-your-first-livevoice.ipynb` | Build out Live Voice scenarios using the accelerator scaffold. |

Tips:
- Run notebooks in sequence for a guided learning path.
- Launch Jupyter from the repo root so relative imports work (`jupyter lab`).
- Ensure `.env` contains valid Azure credentials before executing calls.

## Advanced Labs

Deep-dive content lives in `samples/labs/` and focuses on performance tuning,
state management, and experimentation.

| Notebook | Focus |
| --- | --- |
| `01-build-your-audio-agent.ipynb` | Full voice-to-voice pipeline with Azure AI components. |
| `02-how-to-use-aoai-for-realtime-transcriptions.ipynb` | Optimize Azure OpenAI for real-time STT. |
| `03-latency-arena.ipynb` | Measure and optimize end-to-end latency. |
| `04-memory-agents.ipynb` | Implement conversational memory and session persistence. |
| `05-speech-to-text-multilingual.ipynb` | Multi-language transcription workflows. |
| `06-text-to-speech.ipynb` | Tune neural voice synthesis and SSML. |
| `07-vad.ipynb` | Voice activity detection experiments. |
| `08-speech-to-text-diarization.ipynb` | Multi-speaker diarization strategies. |
| `voice-live.ipynb` | Real-time voice tests across environments. |

### Audio Experiment Bundles

- `labs/podcast_voice_tests/` – Compare TTS model outputs against ground-truth
  recordings to evaluate voice quality.
- `labs/recordings/` – Store captured audio samples for regression testing and
  debugging.

## Environment Checklist

1. Python 3.11+ with project dependencies installed (`uv sync` or `pip install -e .`).
2. Jupyter or VS Code notebooks. Activate the project virtual environment first.
3. Azure resources (Speech, OpenAI, ACS, Redis) provisioned and referenced in `.env`.

## Suggested Paths

- **New to the stack?** Start with the Hello World series (notebooks 01 → 05).
- **Voice quality & tuning:** Labs 06, 07, and the podcast voice tests.
- **Performance & reliability:** Labs 03 and `voice-live.ipynb` for latency and live
  validation.

For additional context, see `samples/README.md` in the repository root—this page is a
condensed version suitable for the documentation site.
