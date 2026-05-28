# Genesys AudioConnector Simulator

Emulates a Genesys Cloud AudioConnector client for testing the ART Voice Agent Accelerator's Genesys integration without real Genesys infrastructure.

## Quick Start

**Prerequisites:** The ART backend must be running before starting the simulator. If it's not already running:

```bash
# From the repo root directory
python -m uvicorn apps.artagent.backend.main:app --host 0.0.0.0 --port 8081                                                
```

Then start the simulator:

```bash
cd tools/genesys_simulator
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.sample .env   # Edit .env with your server URL
python genesys_client_simulator.py
```

Speak into your microphone and hear the AI agent respond. Press `Ctrl+C` to stop.

### Connecting to a Server

```bash
# Local ART backend
python genesys_client_simulator.py ws://localhost:8081/api/v1/genesys/stream

# ART deployed on Azure Container Apps
python genesys_client_simulator.py wss://<your-app>.azurecontainerapps.io/api/v1/genesys/stream
```

The URL can also be set via `SIMULATOR_SERVER_URL` in your `.env` file.

## Connection Probe (diagnostic)

`probe_connection.py` is a headless, no-microphone diagnostic that reproduces the
**exact handshake Genesys Cloud performs when you activate an Audio Connector
integration** (or toggle it Inactive → Active). Use it to verify any ART
deployment's `/api/v1/genesys/stream` endpoint without a Genesys account or audio
hardware — handy in CI or when triaging an activation failure.

```bash
# Local backend
python probe_connection.py ws://localhost:8081/api/v1/genesys/stream

# Deployed backend
python probe_connection.py wss://<your-app>.azurecontainerapps.io/api/v1/genesys/stream
```

The probe sends an AudioHook `open` whose `conversationId`/`participant.id` are the
null UUID (`00000000-0000-0000-0000-000000000000`) — the marker Genesys uses for
its activation probe — then closes. It checks and prints PASS/FAIL for:

| Check | What it verifies |
|-------|------------------|
| Subprotocol negotiation | The server does **not** select a `Sec-WebSocket-Protocol` the client never offered. Genesys offers none; selecting one (e.g. `audiohook-v2`) makes a strict client abort the handshake — surfacing as a generic "problem communicating with the AudioConnector Bot" error with empty server logs. |
| `opened` within 5s | The server answers `open` with `opened` inside the Genesys activation window. |
| No audio during probe | The activation probe is not a real call, so the server should stream no audio. |
| Clean close | The server returns `closed`/`disconnect` after the client's `close`. |

Exit code is `0` when all checks pass, `1` otherwise. By default the probe offers
no subprotocol (mirroring Genesys exactly); pass `--offer-subprotocol audiohook`
only to exercise negotiation behavior.

> Note: "AudioHook v2" refers to the `version` field inside the JSON `open`
> message — it is **not** a WebSocket subprotocol. Genesys negotiates no
> subprotocol on the wire.

## Configuration

All settings are optional and configured via `.env` (see `.env.sample`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMULATOR_SERVER_URL` | `ws://localhost:8081/api/v1/genesys/stream` | ART backend Genesys endpoint |
| `PROMPT_NAME` | `Banking` | Scenario/prompt name sent to the server |
| `SIMULATOR_ORG_ID` | Auto-generated UUID | Genesys organization ID |
| `SIMULATOR_CONV_ID` | Auto-generated UUID | Genesys conversation ID |

## Parameters Sent to Server

The simulator sends these `inputVariables` in the AudioHook `open` message:

| Variable | Value | Description |
|----------|-------|-------------|
| `phoneNumber` | `+34666123456` | Caller phone number |
| `emailAddress` | `test@example.com` | Caller email address |
| `storedCardPresent` | `false` | Whether a stored card is present |
| `CURRENT_DATE` | Current date | Date for prompt context |
| `promptName` | From `PROMPT_NAME` env var | Scenario name |

These variables are available to the AI agent as caller context.

## AudioHook v2 Protocol

The simulator implements the [Genesys AudioHook v2](https://developer.genesys.cloud/devapps/audiohook/) WebSocket protocol.

### Audio Format

| Parameter | Value |
|-----------|-------|
| Format | PCMU (µ-law, ITU-T G.711) |
| Sample Rate | 8000 Hz |
| Channels | Mono (`external` channel) |
| Transport | WebSocket binary frames |

### Message Types

**Client → Server:**

| Message | Description |
|---------|-------------|
| `open` | Establish session with audio params and input variables |
| `ping` | Keep-alive (every 15s) |
| `close` | Terminate session |
| Binary frames | µ-law audio from microphone |

**Server → Client:**

| Message | Description |
|---------|-------------|
| `opened` | Session confirmation |
| `pong` | Keep-alive response |
| `event` | Transcripts, barge-in signals, playback lifecycle |
| `disconnect` | Server-initiated close |
| Binary frames | µ-law audio (agent response) |

### Event Types (Server → Client)

| Event | Description |
|-------|-------------|
| `transcript` | Speech-to-text result (channel: `external` for user, `internal` for agent) |
| `barge_in` | User interrupted — simulator stops current playback |
| `playback_started` | Agent audio playback began |
| `playback_completed` | Agent audio playback finished |

## Communication Flow

```
┌──────────────┐                    ┌──────────────────┐                    ┌─────────────────┐
│  Simulator   │                    │   ART Backend    │                    │  Azure Voice    │
│  (this tool) │                    │  (Genesys WS)    │                    │   Live API      │
└──────┬───────┘                    └────────┬─────────┘                    └────────┬────────┘
       │                                     │                                       │
       │──── WebSocket Connect ─────────────▶│                                       │
       │──── open (AudioHook v2) ───────────▶│                                       │
       │◀─── opened ─────────────────────────│                                       │
       │                                     │──── Connect to VoiceLive ────────────▶│
       │                                     │◀─── session.created ──────────────────│
       │                                     │                                       │
       │════ µ-law 8kHz audio ══════════════▶│════ PCM16 24kHz (upsampled 3x) ═════▶│
       │                                     │                                       │
       │                                     │◀═══ response.audio.delta ═════════════│
       │◀═══ µ-law 8kHz audio (paced) ══════│     (downsampled + µ-law encoded)     │
       │                                     │                                       │
       │◀─── event: transcript ──────────────│                                       │
       │◀─── event: barge_in ────────────────│                                       │
       │                                     │                                       │
       │──── ping ──────────────────────────▶│                                       │
       │◀─── pong ──────────────────────────│                                       │
       │                                     │                                       │
       │──── close ─────────────────────────▶│                                       │
       │◀─── disconnect ────────────────────│                                       │
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection refused | Verify the ART backend is running and the URL/port is correct |
| No audio output | Check ART backend logs for VoiceLive or Azure Speech errors |
| sounddevice error | `pip install --force-reinstall sounddevice`, check mic permissions |
| Crackly/noisy audio | Likely an audio codec issue in the backend — check ART logs for conversion errors |
| Session closes immediately | Check ART logs for Redis auth or agent loading failures |

## References

- [Genesys AudioHook v2 Protocol](https://developer.genesys.cloud/devapps/audiohook/)
- [AudioConnector Blueprint](https://github.com/GenesysCloudBlueprints/audioconnector-server-reference-implementation)
- [ITU-T G.711 (µ-law)](https://www.itu.int/rec/T-REC-G.711) — Audio encoding standard
