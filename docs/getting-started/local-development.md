# :material-laptop: Local Development

!!! info "Prerequisite: Azure Resources"
    This guide assumes you've already deployed infrastructure via [Quickstart](quickstart.md).
    
    If you haven't deployed yet, run `azd up` first—it only takes 15 minutes.

---

## :material-target: What You'll Set Up

```mermaid
flowchart LR
    subgraph LOCAL["Your Machine"]
        BE[Backend<br/>FastAPI :8010]
        FE[Frontend<br/>Vite :5173]
    end
    
    subgraph AZURE["Azure (already deployed)"]
        AC[App Config]
        AI[OpenAI + Speech]
        ACS[Communication Services]
    end
    
    FE --> BE
    BE --> AC
    AC --> AI
    AC --> ACS
    
    style LOCAL fill:#e3f2fd
    style AZURE fill:#fff3e0
```

| Component | Port | Purpose |
|-----------|------|---------|
| **Backend** | `8010` | FastAPI + WebSocket voice pipeline |
| **Frontend** | `5173` | Vite + React demo UI |
| **Dev Tunnel** | External | ACS callbacks for phone calls |

---

## :material-numeric-1-circle: Python Environment

Choose **one** of these options:

=== ":material-star: uv (Recommended)"

    [uv](https://docs.astral.sh/uv/) is 10-100x faster than pip.
    
    ```bash
    # Install uv (if not installed)
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Sync dependencies (creates .venv automatically)
    uv sync
    ```

=== "venv + pip"

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Windows: .venv\Scripts\activate
    pip install -e .[dev]
    ```

=== "Conda"

    ```bash
    conda env create -f environment.yaml
    conda activate audioagent
    uv sync  # or: pip install -e .[dev]
    ```

!!! tip "Local Audio Capture (Optional)"
    If you need local microphone capture/playback features (e.g., for testing with `pyaudio`), install the `audio` extra:
    
    ```bash
    # First install the system portaudio library
    # macOS: brew install portaudio
    # Ubuntu/Debian: apt-get install portaudio19-dev
    
    # Then install with audio extras
    pip install -e ".[dev-all]"  # or: pip install -e ".[dev,audio]"
    ```
    
    This is **not required** for the main voice pipeline which uses Azure Communication Services.

---

## :material-numeric-2-circle: Environment Configuration

### Option A: Use App Configuration (Recommended)

After `azd up`, a `.env.local` file was auto-generated:

```bash
# Verify it exists
cat .env.local
```

**Expected contents:**
```bash
AZURE_APPCONFIG_ENDPOINT=https://<your-appconfig>.azconfig.io
AZURE_APPCONFIG_LABEL=dev
AZURE_TENANT_ID=<your-tenant-id>
```

!!! success "That's all you need!"
    The backend automatically fetches all settings (OpenAI, Speech, ACS, Redis, etc.) from Azure App Configuration at startup.

### Option B: Legacy — Full `.env` File (Manual Setup)

If you **don't have infrastructure** or need to work offline:

```bash
cp .env.sample .env
# Edit .env with your values
```

??? example "Full `.env.sample` Reference"
    The `.env.sample` file contains all available configuration options. Here are the **required** variables:
    
    ```bash
    # ============================================================================
    # REQUIRED: Azure Identity
    # ============================================================================
    AZURE_TENANT_ID=                                    # Azure AD tenant ID
    AZURE_SUBSCRIPTION_ID=                              # Azure subscription ID
    
    # ============================================================================
    # REQUIRED: Azure OpenAI
    # ============================================================================
    AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
    AZURE_OPENAI_KEY=                                   # API key (or use managed identity)
    AZURE_OPENAI_CHAT_DEPLOYMENT_ID=gpt-4o              # Your chat model deployment
    
    # ============================================================================
    # REQUIRED: Azure Speech Services
    # ============================================================================
    AZURE_SPEECH_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
    AZURE_SPEECH_KEY=                                   # Speech service API key
    AZURE_SPEECH_REGION=eastus                          # Region must match endpoint
    
    # ============================================================================
    # REQUIRED: Azure Communication Services (for telephony)
    # ============================================================================
    ACS_CONNECTION_STRING=endpoint=https://your-acs.communication.azure.com/;accesskey=...
    ACS_ENDPOINT=https://your-acs.communication.azure.com
    ACS_SOURCE_PHONE_NUMBER=+1234567890                 # E.164 format (skip if browser-only)
    
    # ============================================================================
    # REQUIRED: Redis (session management)
    # ============================================================================
    REDIS_HOST=your-redis.redis.azure.net
    REDIS_PORT=6380
    REDIS_PASSWORD=                                     # Or REDIS_ACCESS_KEY
    
    # ============================================================================
    # REQUIRED: Azure Storage (recordings, audio)
    # ============================================================================
    AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
    AZURE_BLOB_CONTAINER=acs
    
    # ============================================================================
    # REQUIRED: Cosmos DB (conversation history)
    # ============================================================================
    AZURE_COSMOS_CONNECTION_STRING=mongodb+srv://...
    AZURE_COSMOS_DATABASE_NAME=audioagentdb
    AZURE_COSMOS_COLLECTION_NAME=audioagentcollection
    
    # ============================================================================
    # REQUIRED: Application Insights (telemetry)
    # ============================================================================
    APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...
    
    # ============================================================================
    # REQUIRED (Local Dev): Base URL for webhooks
    # ============================================================================
    BASE_URL=https://your-tunnel.devtunnels.ms
    ```
    
    See the full [`.env.sample`](https://github.com/Azure-Samples/art-voice-agent-accelerator/blob/main/.env.sample) for optional settings like pool sizes, voice configuration, feature flags, and VoiceLive integration.

---

## :material-numeric-3-circle: Start Dev Tunnel

!!! info "When is this needed?"
    Dev Tunnels are required for **phone calls** (PSTN) because Azure Communication Services needs to reach your local machine for callbacks. Skip this section if you're only using browser-based voice.

### Install Dev Tunnels CLI

=== ":material-microsoft: Windows"

    ```powershell
    winget install Microsoft.devtunnel
    ```

=== ":material-apple: macOS"

    ```bash
    brew install --cask devtunnel
    ```

=== ":material-linux: Linux"

    ```bash
    curl -sL https://aka.ms/DevTunnelCliInstall | bash
    ```

### Create and Start Tunnel

```bash
# Login to Dev Tunnels (one-time)
devtunnel login

# Create a tunnel with anonymous access (required for ACS callbacks)
devtunnel create --allow-anonymous

# Add port 8010 to the tunnel
devtunnel port create -p 8010

# Start hosting the tunnel (keep this terminal open)
devtunnel host
```

!!! success "Copy the HTTPS URL"
    After running `devtunnel host`, you'll see output like:
    ```
    Connect via browser: https://abc123-8010.usw3.devtunnels.ms
    ```
    Copy this URL—you'll need it for `BASE_URL`.

### Configure BASE_URL

Set the tunnel URL in your environment:

```bash
# In .env or .env.local
BASE_URL=https://abc123-8010.usw3.devtunnels.ms
```

## :material-numeric-4-circle: Start Backend

```bash
uv run uvicorn apps.artagent.backend.main:app --host 0.0.0.0 --port 8010 --reload
```

??? tip "Using venv?"
    ```bash
    source .venv/bin/activate
    uvicorn apps.artagent.backend.main:app --host 0.0.0.0 --port 8010 --reload
    ```

---

## :material-numeric-5-circle: Start Frontend

Open a **new terminal**:

```bash
cd apps/artagent/frontend

# Create frontend .env
echo "VITE_BACKEND_BASE_URL=http://localhost:8010" > .env

npm install
npm run dev
```

**Open:** http://localhost:5173

---

## :material-check-circle: Verify It Works

1. Open http://localhost:5173
2. Allow microphone access
3. Start talking
4. You should see:
    - Transcripts appearing
    - AI responses
    - Audio playback

### API Documentation

The backend exposes interactive API documentation:

| URL | Format | Best For |
|-----|--------|----------|
| http://localhost:8010/redoc | ReDoc | Reading API reference |
| http://localhost:8010/docs | Swagger UI | Interactive testing |

!!! tip "Explore Available Endpoints"
    Visit `/redoc` to see all available API endpoints, request/response schemas, and WebSocket contracts for the voice pipeline.

---

## :material-tools: Development Alternatives

### VS Code Debugging

Built-in debug configurations in `.vscode/launch.json`:

| Configuration | What It Does |
|---------------|--------------|
| `[RT Agent] Python Debugger: FastAPI` | Debug backend with breakpoints |
| `[RT Agent] React App: Browser Debug` | Debug frontend in browser |

1. Set breakpoints in code
2. Press **F5**
3. Select configuration
4. Debug!

### Docker Compose

For containerized local development:

```bash
docker-compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:8080 |
| Backend | http://localhost:8010 |

1. Open http://localhost:5173
2. Allow microphone access
3. Start talking
4. You should see:
    - Transcripts appearing
    - AI responses
    - Audio playback

## :material-phone: Phone (PSTN) Setup

!!! note "Optional"
    Only needed if you want to make/receive actual phone calls.

1. **Purchase a phone number** via Azure Portal or:
   ```bash
   make purchase_acs_phone_number
   ```

2. **Configure Event Grid** subscription:
   - Event: `Microsoft.Communication.IncomingCall`
   - Endpoint: `https://<tunnel-url>/api/v1/calls/answer`

3. **Dial the number** and talk to your AI agent!

📚 **Full guide:** [Phone Number Setup](../deployment/phone-number-setup.md)

| Configuration | What It Does |
|---------------|--------------|
| `[RT Agent] Python Debugger: FastAPI` | Debug backend with breakpoints |
| `[RT Agent] React App: Browser Debug` | Debug frontend in browser |

## :material-bug: Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 404 on callbacks | Stale `BASE_URL` | Update `.env` with new tunnel URL |
| No audio | Invalid Speech key | Check Azure Speech resource |
| WebSocket closes | Wrong backend URL | Verify `VITE_BACKEND_BASE_URL` |
| Import errors | Missing deps | Re-run `uv sync` |
| Phone call no events | Event Grid not configured | Update subscription endpoint |

📚 **More help:** [Troubleshooting Guide](../operations/troubleshooting.md)

---

## :material-test-tube: Testing

```bash
# Quick unit tests
uv run pytest tests/test_acs_media_lifecycle.py -v

# All tests
uv run pytest tests/ -v
```

📚 **Full guide:** [Testing Guide](../operations/testing.md)

---

## :material-cog: Customizing Agents, Tools, and Scenarios

Now that you're running locally, you can modify agent behavior, add custom tools, and create new scenarios directly in code.

| What to Customize | Location | Guide |
|-------------------|----------|-------|
| Add a new tool | `apps/artagent/backend/registries/toolstore/` | [Tools Guide](../architecture/registries/tools.md) |
| Create/modify an agent | `apps/artagent/backend/registries/agentstore/` | [Agents Guide](../architecture/registries/agents.md) |
| Define a scenario | `apps/artagent/backend/registries/scenariostore/` | [Scenarios Guide](../architecture/registries/scenarios.md) |

📚 **Full guide:** [Registries Overview](../architecture/registries/index.md)
