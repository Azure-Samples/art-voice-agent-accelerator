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

### How Config Loading Works

```
┌─────────────────────────────────────────────────────────────┐
│  .env.local (bootstrap only)                                │
│  ├── AZURE_APPCONFIG_ENDPOINT  ───┐                        │
│  ├── AZURE_APPCONFIG_LABEL        │  ← Your environment    │
│  └── AZURE_TENANT_ID              ↓                        │
│                        ┌─────────────────────┐             │
│                        │  Azure App Config   │             │
│                        │  (28+ shared keys)  │             │
│                        └─────────────────────┘             │
│                                   ↓                        │
│  Pulls: phone number, OpenAI, Speech, Redis, etc.          │
│                                                             │
│  .env.local OVERRIDES (local-specific only)                │
│  └── BASE_URL (your tunnel URL)                            │
│  └── AZURE_EMAIL_* (optional)                              │
└─────────────────────────────────────────────────────────────┘
```

!!! info "What is `AZURE_APPCONFIG_LABEL`?"
    It's like a **namespace** in App Configuration. Same key can have different values per label:
    
    ```
    azure/acs/source-phone-number
    ├── label: "artagentv2"  → +18663687875  (your env)
    ├── label: "dev"         → +1555...      (dev team)
    └── label: "prod"        → +1800...      (production)
    ```
    
    Your app only loads keys matching its label. **The phone number is stored in App Config, not `.env.local`.**

!!! info "What goes where?"
    | Config | Location | Why |
    |--------|----------|-----|
    | Phone number, OpenAI, Speech, Redis | **App Configuration** | Shared across team/deployments |
    | Tunnel URL (`BASE_URL`) | **`.env.local`** | Different per developer machine |
    | Email credentials | **`.env.local`** | Optional, local override |

### Option A: Use App Configuration (Recommended)

After `azd up`, a `.env.local` file was auto-generated:

```bash
# Verify it exists
cat .env.local
```

**Expected contents:**
```bash
AZURE_APPCONFIG_ENDPOINT=https://<your-appconfig>.azconfig.io
AZURE_APPCONFIG_LABEL=<your-environment>   # e.g., artagentv2, dev, prod
AZURE_TENANT_ID=<your-tenant-id>
```

At startup, the backend:

1. Reads `.env.local` for App Config connection info
2. Connects to Azure App Configuration
3. Pulls all keys with matching label (e.g., `artagentv2`)
4. Merges with any local overrides in `.env.local`

!!! success "Shared config is automatic!"
    Phone number, OpenAI endpoints, Speech keys, Redis, etc. are all in App Config. You don't need to copy them locally.

### Local Overrides in `.env.local`

Add these to `.env.local` for local-specific values:

```bash
# Dev tunnel URL (REQUIRED for phone calls)
BASE_URL=https://your-tunnel-8010.devtunnels.ms

# Email service (OPTIONAL)
AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING=endpoint=https://...
AZURE_EMAIL_SENDER_ADDRESS=DoNotReply@xxx.azurecomm.net
```

!!! tip "You can override ANY App Config value"
    `.env.local` values take precedence over App Configuration. If you need a different phone number for local testing:
    
    ```bash
    # Override the phone number locally
    ACS_SOURCE_PHONE_NUMBER=+1234567890
    ```
    
    This is useful for:
    
    - Testing with a different phone number
    - Debugging with custom endpoints
    - Working offline without App Config access

!!! warning "Don't commit secrets to .env.local"
    `.env.local` is gitignored. Keep shared secrets in App Configuration so the team uses the same values.

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

### Step 1: Purchase a Phone Number

📚 **See:** [Phone Number Setup Guide](../deployment/phone-number-setup.md) for full instructions on:

- Purchasing via Azure Portal or CLI
- Configuring in App Configuration
- Troubleshooting

**Quick option:**
```bash
make purchase_acs_phone_number
```

### Step 2: Add Phone Number to `.env.local`

After purchasing, add the phone number to your `.env.local`:

```bash
# ACS Phone Number (E.164 format)
ACS_SOURCE_PHONE_NUMBER=+18663687875
```

!!! info "App Config vs .env.local"
    The phone number can be stored in either location:
    
    - **App Configuration** → Shared across team (recommended for deployed environments)
    - **`.env.local`** → Local override (useful for personal testing)
    
    If set in both, `.env.local` takes precedence.

### Step 3: Configure Event Grid Webhook

For **inbound calls** to reach your local machine, you must configure Event Grid.

📚 **See:** [Phone Number Setup - Event Grid](../deployment/phone-number-setup.md#configuring-event-grid-webhook) for full instructions.

**Quick steps:**

1. Go to [Azure Portal](https://portal.azure.com) → your **ACS resource**
2. Select **Events** → **+ Event Subscription**
3. Configure:
   - **Event Types**: `Incoming Call` only
   - **Endpoint Type**: Webhook
   - **Endpoint URL**: `https://<your-tunnel>/api/v1/calls/answer`
4. Click **Create**

!!! warning "Dev Tunnel URL Changes"
    Each time you create a new dev tunnel, you get a new URL. You must **update the Event Grid subscription endpoint** with the new URL, or incoming calls won't reach your local machine.

### Step 4: Test It

Dial your ACS phone number and talk to your AI agent!

---

## :material-email: Email Service Setup

!!! note "Optional"
    Only needed if your agents use email tools (claim confirmations, notifications).

1. Go to [Azure Portal](https://portal.azure.com) → your **ACS resource** → **Settings** → **Keys**
2. Copy the **Connection string**
3. Go to **Email** → **Try Email** to find your sender domain
4. Add to `.env.local`:
   ```bash
   AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING=endpoint=https://...
   AZURE_EMAIL_SENDER_ADDRESS=DoNotReply@<domain>.azurecomm.net
   ```
5. Restart backend

📚 **Full guide:** [Email Setup](../deployment/email-setup.md)

| Configuration | What It Does |
|---------------|--------------|
| `[RT Agent] Python Debugger: FastAPI` | Debug backend with breakpoints |
| `[RT Agent] React App: Browser Debug` | Debug frontend in browser |

## :material-console: Makefile Commands

| Command | Description |
|---------|-------------|
| `make start_backend` | Start FastAPI backend on port 8010 |
| `make start_frontend` | Start Vite frontend on port 5173 |
| `make start_tunnel` | Start dev tunnel for ACS callbacks |
| `make purchase_acs_phone_number` | Purchase toll-free number from ACS |

---

## :material-bug: Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 404 on callbacks | Stale `BASE_URL` | Update `.env` with new tunnel URL |
| No audio | Invalid Speech key | Check Azure Speech resource |
| WebSocket closes | Wrong backend URL | Verify `VITE_BACKEND_BASE_URL` |
| Import errors | Missing deps | Re-run `uv sync` |
| Phone call no events | Event Grid not configured | Update subscription endpoint |
| Phone call no events | Tunnel URL changed | Update Event Grid webhook URL |

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
