# ⚡ Local Development

Run the ARTVoice Accelerator locally with raw commands. No Makefile usage. Keep secrets out of git and rotate any previously exposed keys.

---

## 1. Scope

What this covers:
- Local backend (FastAPI + Uvicorn) and frontend (Vite/React)
- Dev tunnel for inbound [Azure Communication Services](https://learn.microsoft.com/en-us/azure/communication-services/) callbacks
- Environment setup via venv OR Conda
- Minimal `.env` files (root + frontend)

What this does NOT cover:
- Full infra provisioning
- CI/CD
- Persistence hardening

---

## 2. Prerequisites

| Tool | Notes |
|------|-------|
| Python 3.11 | Required runtime |
| Node.js ≥ 22 | Frontend |
| Azure CLI | `az login` first |
| Dev Tunnels | `az extension add --name dev-tunnel` |
| (Optional) Conda | If using `environment.yaml` |
| Provisioned Azure resources | For real STT/TTS/LLM/ACS |

If you only want a browser demo (no phone), ACS variables are optional.

---

## 3. Clone Repository

```bash
git clone https://github.com/pablosalvador10/gbb-ai-audio-agent.git
cd gbb-ai-audio-agent
```

---

## 4. Python Environment (Choose One)

### Option A: venv
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Option B: Conda
```bash
conda env create -f environment.yaml
conda activate audioagent
pip install -r requirements.txt   # sync with lock
```

---

## 5. Root `.env` (Create in repo root)

Minimal template (edit placeholders; DO NOT commit real values):

```
# ===== Azure OpenAI =====
AZURE_OPENAI_ENDPOINT=https://<your-aoai>.openai.azure.com
AZURE_OPENAI_KEY=<aoai-key>
AZURE_OPENAI_DEPLOYMENT=gpt-4-1-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT_ID=gpt-4-1-mini
AZURE_OPENAI_CHAT_DEPLOYMENT_VERSION=2024-11-20

# ===== Speech =====
AZURE_SPEECH_REGION=<speech-region>
AZURE_SPEECH_KEY=<speech-key>

# ===== ACS (optional unless using phone/PSTN) =====
ACS_CONNECTION_STRING=endpoint=https://<your-acs>.communication.azure.com/;accesskey=<acs-key>
ACS_SOURCE_PHONE_NUMBER=+1XXXXXXXXXX
ACS_ENDPOINT=https://<your-acs>.communication.azure.com

# ===== Optional Data Stores =====
REDIS_HOST=<redis-host>
REDIS_PORT=6380
REDIS_PASSWORD=<redis-password>
AZURE_COSMOS_CONNECTION_STRING=<cosmos-conn-string>
AZURE_COSMOS_DATABASE_NAME=audioagentdb
AZURE_COSMOS_COLLECTION_NAME=audioagentcollection

# ===== Runtime =====
ENVIRONMENT=dev
ACS_STREAMING_MODE=media

# ===== Filled after dev tunnel starts =====
BASE_URL=https://<tunnel-url>
```

Ensure `.env` is in `.gitignore`.

---

## 6. Start Dev Tunnel

Required if you want ACS callbacks (phone flow) or remote test:

```bash
devtunnel host -p 8010 --allow-anonymous
```

Copy the printed HTTPS URL and set `BASE_URL` in root `.env`. Update it again if the tunnel restarts (URL changes).

The Dev Tunnel URL will look similar to:
```bash
https://abc123xy-8010.usw3.devtunnels.ms
```

---

## 7. Run Backend

```bash
cd apps/rtagent/backend
uvicorn apps.rtagent.backend.main:app --host 0.0.0.0 --port 8010 --reload
```

---

## 8. Frontend Environment

Create or edit `apps/rtagent/frontend/.env`:

Use the dev tunnel URL by default so the frontend (and any external device or ACS-related flows) reaches your backend consistently—even if you open the UI on another machine or need secure HTTPS.

```
# Recommended (works across devices / matches ACS callbacks)
VITE_BACKEND_BASE_URL=https://<tunnel-url>
```

If the tunnel restarts (URL changes), update both `BASE_URL` in the root `.env` and this value.

---

## 9. Run Frontend

```bash
cd apps/rtagent/frontend
npm install
npm run dev
```

Open: http://localhost:5173

WebSocket URL is auto-derived by replacing `http/https` with `ws/wss`.

---

## 10. Optional: Phone (PSTN) Flow

1. Purchase ACS phone number (Portal or CLI).

2. Ensure these vars are set in your root `.env` (with real values):

   ```
   ACS_CONNECTION_STRING=endpoint=...
   ACS_SOURCE_PHONE_NUMBER=+1XXXXXXXXXX
   ACS_ENDPOINT=https://<your-acs>.communication.azure.com
   BASE_URL=https://<tunnel-hash>-8010.usw3.devtunnels.ms
   ```

3. Create a single Event Grid subscription for the Incoming Call event pointing to your answer handler:
   - Inbound endpoint:  
     `https://<tunnel-hash>-8010.usw3.devtunnels.ms/api/v1/calls/answer`
   - Event type: `Microsoft.Communication.IncomingCall`
   - (Callbacks endpoint `/api/v1/calls/callbacks` is optional unless you need detailed lifecycle events.)

   If tunnel URL changes, update the subscription (delete & recreate or update endpoint).

   Reference: [Subscribing to events](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/events/subscribe-to-event)

4. Dial the number; observe:
   - Call connection established
   - Media session events
   - STT transcripts
   - TTS audio frames

---

## 11. Quick Browser Test

1. Backend + frontend running.
2. Open app, allow microphone.
3. Speak → expect:
   - Interim/final transcripts
   - Model response
   - Audio playback

---

## 12. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| 404 on callbacks | Stale `BASE_URL` | Restart tunnel, update `.env` |
| No audio | Speech key/region invalid | Verify Azure Speech resource |
| WS closes fast | Wrong `VITE_BACKEND_BASE_URL` | Use exact backend/tunnel URL |
| Slow first reply | Cold pool warm-up | Keep process running |
| Phone call no events | ACS callback not updated to tunnel | Reconfigure Event Grid subscription |
| Import errors | Missing dependencies | Re-run `pip install -r requirements.txt` |

---

Keep secrets out of commits. Rotate anything that has leaked.