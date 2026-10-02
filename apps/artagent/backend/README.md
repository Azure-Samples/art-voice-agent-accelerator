# ARTVoice Backend

FastAPI backend for real-time voice AI via Azure Communication Services.

## Architecture

```
Phone → ACS → WebSocket → STT → Multi-Agent AI → TTS → Audio
```

## Structure

```
backend/
├── main.py              # FastAPI app + startup
├── api/v1/              # REST + WebSocket endpoints
├── voice/               # Voice orchestration (SpeechCascade, VoiceLive)
├── registries/          # Agent, tool, scenario registration
└── config/              # Settings and feature flags
```

## Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/api/v1/media/stream` | ACS media streaming WebSocket |
| `/api/v1/realtime/conversation` | Real-time voice WebSocket |
| `/api/v1/calls/*` | Call management |
| `/health` | Health check |

## Communication providers: ACS and Teams Phone

ACS remains the default for existing deployments. The phone UI can select
**ACS (standalone)** or **Teams Phone (via ACS/TPE)** for the next outbound call.
This is independent of the Cascade/VoiceLive engine selection. It does not
change inbound routing, switch an active call, or provision Teams resources.
Email and SMS remain server-configured ACS services; external-provider choices
are visibly unavailable, not simulated implementations. Teams Phone is not an
email or programmable SMS delivery provider.

`GET /api/v1/calls/providers` reports non-secret configuration status. A
`configured` option means local prerequisites are present, not that tenant
permissions, licensing, carrier routing, delivery or connectivity have been
confirmed. Unavailable selections are rejected by the backend before creating a
call. Teams failure never falls back to ACS automatically.

### Optional Teams Phone setup

An administrator must first provision Teams Phone extensibility: associate the
Teams resource account with **the same ACS resource used by this backend**,
assign its Resource Account license and service number, configure PSTN
connectivity (for example Teams Direct Routing with a certified SBC), and grant
server-side calling access. This is Teams Direct Routing, not ACS Direct Routing.
See Microsoft's [TPE overview](https://learn.microsoft.com/en-us/azure/communication-services/concepts/interop/tpe/teams-phone-extensibility-overview)
and [server-initiated calling prerequisites](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/tpe/teams-phone-extensibility-server-outbound-call).

Then configure the backend and restart it:

```dotenv
TEAMS_PHONE_ENABLED=true
TEAMS_PHONE_RESOURCE_ACCOUNT_ID=<Teams-resource-account-Entra-object-ID>
```

The corresponding App Configuration keys are `azure/teams-phone/enabled` and
`azure/teams-phone/resource-account-id`. The flag defaults to false. These values
stay on the server; the browser cannot supply an arbitrary resource account.
Dependencies require Call Automation Python SDK 1.5.0 or later, exposing
`create_call(..., teams_app_source=...)` (the lockfile includes 1.5.0). Older
already-installed SDKs disable Teams explicitly
without disabling an otherwise configured standalone ACS path.

Keep the existing ACS authentication, public `BASE_URL`, incoming Event Grid
subscription, callback authentication, and media WebSocket configuration.
TPE uses those same Call Automation callbacks and media protocol, so both voice
engines and call termination continue through the existing ACS transport.
No second ACS client, transport masquerading as Teams, or number purchase is
needed for Teams-only operation. `ACS_SOURCE_PHONE_NUMBER` remains required for
standalone ACS outbound calls but is optional when Teams is configured.

```json
{
  "target_number": "+15551234567",
  "telephony_provider": "teams",
  "streaming_mode": "media"
}
```

Send this to `POST /api/v1/calls/initiate`. Omitted `telephony_provider` preserves
ACS behavior. The response, outbound call context and lifecycle event include the
selected provider. The SDK uses `MicrosoftTeamsAppIdentifier` for Teams calls,
never the standalone ACS caller ID. Incoming calls are routed by the tenant and
the called number, not by a browser's selection; both use `/api/v1/calls/answer`.
Only one Teams resource account per backend deployment is supported by this
configuration.

This addition does not implement new SIP destinations, repair demo transfer/MFA
tools, or claim certification. Production Teams voice-agent support and the
selected SDK/media combination must be confirmed for the deployment. Disabling
the Teams flag and restarting removes it from selectable providers without
removing ACS configuration or migrating resources.

## Core Folders

### `registries/` - Agent, Tool, Scenario System
```
registries/
├── agentstore/          # Agent definitions (YAML-based)
├── toolstore/           # Tool registry (@register_tool)
└── scenariostore/       # Industry scenarios (banking, etc.)
```

**Usage:**
```python
from apps.artagent.backend.registries.agentstore import discover_agents
from apps.artagent.backend.registries.toolstore import register_tool
from apps.artagent.backend.registries.scenariostore import load_scenario
```

See [`registries/README.md`](./registries/README.md) for details.

### `voice/` - Voice Orchestration
```
voice/
├── speech_cascade/      # Custom STT/TTS pipeline orchestrator
├── voicelive/           # Azure OpenAI Realtime API orchestrator
└── handoffs/            # Agent handoff logic
```

Two orchestration paths:
- **SpeechCascade**: Custom pipeline (MAI Transcribe 2.0 → AOAI → Azure Speech TTS)
- **VoiceLive**: Managed API (Azure OpenAI Realtime with built-in voice)

### `api/v1/` - HTTP + WebSocket APIs
```
api/v1/
├── endpoints/
│   ├── calls.py         # ACS call management
│   ├── media.py         # Media streaming handler
│   ├── realtime.py      # Real-time voice handler
│   └── health.py        # Health checks
└── schemas/             # Pydantic request/response models
```

### `config/` - Configuration
```
config/
├── app_config.py        # Main app settings
├── app_settings.py      # Agent/orchestrator settings
└── feature_flags.py     # Feature toggles
```

## Quick Start

### Run Backend
```bash
make start_backend
```

### Add New Agent
1. Create YAML in `registries/agentstore/`
2. Define prompts, tools, handoffs
3. Restart or call `/api/v1/agents/refresh`

### Add New Tool
```python
# In registries/toolstore/your_tool.py
from apps.artagent.backend.registries.toolstore.registry import register_tool

@register_tool(name="your_tool", description="...")
async def your_tool(param: str) -> dict:
    return {"result": "..."}
```

### Load Scenario
```python
from apps.artagent.backend.registries.scenariostore import load_scenario

scenario = load_scenario("banking_customer_service")
agents = get_scenario_agents("banking_customer_service")
```

## WebSocket Flow

```
1. Client connects → /api/v1/media/stream or /api/v1/realtime/conversation
2. Audio chunks → STT (Azure Speech or Realtime API)
3. Text → Multi-agent orchestrator
4. Response → TTS (Azure Speech or Realtime API)
5. Audio → Stream back to client
```

## Troubleshooting

### Import Errors
Use new paths:
```python
# ✅ Correct
from apps.artagent.backend.registries.agentstore import discover_agents

# ❌ Old (deprecated)
from apps.artagent.backend.agents_store import discover_agents
```

### Agent Not Found
```python
agents = discover_agents()
print([a.name for a in agents])  # List all discovered agents
```

### Tool Not Registered
```python
from apps.artagent.backend.registries.toolstore.registry import list_tools
print(list_tools())  # List all registered tools
```

### Health Check Failed
```bash
curl http://localhost:8000/health
```

Check logs for Azure service connectivity issues (Speech, OpenAI, Redis, CosmosDB).

## Scenario authoring and local authentication

Scenario generation reads its chat deployment from the runtime configuration
provider, after App Configuration has loaded. It must not use an import-time
deployment value: importing the configuration package during bootstrap can happen
before the cloud settings have been synchronized.

If generation fails locally, distinguish these cases:

- **App Configuration returns 401/403:** sign in to the tenant configured by
  `AZURE_TENANT_ID` and confirm that identity can read the configured App
  Configuration store. A successful generic `/health` response does not prove
  model inference access.
- **No chat deployment configured:** check the runtime
  `azure/openai/deployment-id` / `AZURE_OPENAI_CHAT_DEPLOYMENT_ID` setting.
- **Invalid generated draft:** the authoring endpoint gives the model one bounded
  opportunity to repair the validation errors. It never applies an invalid draft
  or silently removes unknown tools or protected context fields.

Generate and review are read-only. Agent/scenario persistence and activation occur
only through the explicit Apply endpoint.

When multiple Azure accounts are used on the same workstation, set
`AZURE_AUTH_SUBSCRIPTION` to the subscription ID (or unique name) associated with
the authorized login. Local App Configuration, OpenAI/Speech/Redis credentials,
and VoiceLive then use that account explicitly, including token refresh, instead
of following later `az account set` changes from another project. This does not
change the CLI's global default or grant access. Hosted managed identity remains
unchanged. Use the project environment (`uv sync`), not an older global Python
environment: subscription-pinned `AzureCliCredential` requires Azure Identity
1.20 or newer.
Resource tenant challenges are checked against `AZURE_TENANT_ID`; a different
tenant is rejected. For a matching challenge, the redundant tenant selector is
omitted because Azure CLI rejects combining `--tenant` and `--subscription`.

### Existing scenario edits and prompt previews

`GET /api/v1/scenario-builder/session/{session_id}?scenario_name=...` reads a
named scenario without activating it. Omitting the name retains the active-scenario
behavior. Scenario updates return the complete editable configuration, including
tools and agent defaults. The session catalog uses saved overrides of built-in
scenarios rather than reverting their displayed settings to the YAML template.

The prompt editor uses a read-only endpoint:

```http
POST /api/v1/agent-builder/prompt-preview?session_id=...
Content-Type: application/json

{
  "agent_name": "BankingConcierge",
  "prompt": "You are {{ agent_name }}. {% if caller_name is defined %}Welcome {{ caller_name }}.{% endif %}",
  "template_vars": {},
  "tools": [],
  "scenario": null,
  "mode": "voicelive"
}
```

Explicit `template_vars`, `tools`, and `scenario` values describe an unsaved draft
for preview only. A null scenario resolves the session's active scenario. Context
precedence matches runtime: base defaults, agent template variables, scenario
globals, scenario agent-default variables, then available runtime values. Cascade
and VoiceLive use shared binding helpers; connection-only VoiceLive values are
marked unavailable when there is no live connection. Tool selections are not
implicitly a Jinja `tools` variable.

Responses include insertable variable paths and expressions, source/type metadata,
safe snapshot values, rendered text, missing-variable paths, warnings, and
diagnostics with line numbers. Ordinary syntax, undefined-value, unsupported
operation, and rendering-limit errors return diagnostics rather than pretending
the original template rendered successfully. Invalid requests and unavailable
context return sanitized HTTP errors without echoing submitted or stored values.

Preview runs against sanitized JSON in a separately bounded Jinja sandbox. It
supports normal conditions, bounded loops, JSON dictionary access, and common
filters, while rejecting imports, private attribute access, arbitrary calls,
recursive macros, and unbounded work. Limits include a 192 KB request, 64 KB UTF-8
prompt, 128 KB context/output, 1,000 loop iterations, and 512 displayed variable
paths. Credentials, verification codes, internal runtime objects, and
credential-like text are omitted or redacted. The endpoint does not persist,
register, activate, invoke a model, or execute tools. Handoff instructions and
conversation recap text appended by runtime are outside this template preview.

### Regional voice discovery

`GET /api/v1/agent-builder/voices` enumerates the configured Speech resource with
the Speech SDK's `get_voices_async()` and returns every discovered voice, including
non-English voices absent from the starter presets. The response includes locale,
gender, voice family, styles, status, resource/region provenance, discovery time,
and completeness/cache flags. It is a catalog query, not a synthesis or VoiceLive
compatibility test.

Discovery runs outside the request event loop and is coalesced per resource.
Successful catalogs are cached for ten minutes, keyed by region, endpoint,
resource ID, and credential fingerprint. `use_cache=false` forces a refresh.
Caller waits are bounded; a timed-out SDK request is shared rather than starting
additional requests. Temporary failures are throttled. A same-resource snapshot
up to one hour old can be returned with a stale warning; otherwise the response
explicitly marks the limited preset fallback as unverified/incomplete.

Optional `category` and `language` filters apply to the discovered catalog, not a
curated allowlist. `total_available` retains the unfiltered count.
`include_unverified=true` supplements discovery with explicitly unverified
presets; `presets_only=true` requests an offline preset catalog without contacting
Azure. When regional discovery omits HD voices, documented HD entries are
retained with per-voice verification flags and an explicit catalog warning.
Custom/personal voices and native VoiceLive model voices can
require separate configuration beyond the regional prebuilt Speech catalog.

References: [Speech voice discovery](https://learn.microsoft.com/azure/ai-services/speech-service/rest-text-to-speech#get-a-list-of-voices)
and [Voice Live voice/model support](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live).

### MAI transcription and voice configuration

Cascade and text-based VoiceLive BYOM now request MAI Transcribe 2.0 by default
using the literal identifier `mai-transcribe-2`. It is preserved through
authoring, persistence, and SDK requests; it is **not** rewritten to the generic
`mai-transcribe` alias. Explicit Azure Speech and other provider choices remain
unchanged. The generic MAI alias is still selectable, and legacy
`mai-transcribe-1.5` settings retain their previous normalization to that alias.

**Availability:** `mai-transcribe-2` is an explicitly requested, undocumented
VoiceLive model identifier. The public
[VoiceLive reference](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-how-to#mai-transcribe-preview)
documents only `mai-transcribe`; the versioned
[MAI-Transcribe-2 documentation](https://learn.microsoft.com/azure/ai-services/speech-service/mai-transcribe)
describes Fast Transcription, not this live API. The runtime does not substitute
the alias or Azure Speech if the requested model is unavailable. Confirm support
on your VoiceLive endpoint before deployment; this default requires access to
that model.

In VoiceLive, use `session.input_audio_transcription_settings.model` with a managed
text model or an explicit `byom-azure-openai-chat-completion` /
`byom-foundry-anthropic-messages` profile. An omitted provider in either text BYOM
profile selects `mai-transcribe-2`. The shared YAML and editor default, `model:
auto`, selects MAI 2.0 for those profiles and retains Azure Speech otherwise.
Setting `model: azure-speech` explicitly opts out; an explicit provider always
wins over the default. Native realtime models and
`byom-azure-openai-realtime` are rejected for MAI input. Validation also runs during
handoffs against the actual connection model/profile. MAI connections use API
`2026-04-10`; ordinary existing connections retain their version behavior.
Custom speech maps and phrase lists must be removed explicitly rather than being
silently dropped. There is no undocumented `custom-cascade` profile sent on the
wire; a managed text model already creates a speech/chat/speech pipeline.

In the application's Custom Speech/Cascade mode,
`speech.transcription_model` defaults to `mai-transcribe-2`; set it to
`azure-speech` to opt back into the pooled Speech SDK recognizer. Definitions
saved without this field also pick up the new default. The async input provider creates a
session-owned VoiceLive connection using the managed `gpt-4.1` text host and
`create_response: false`. It does not request model responses or synthesize audio:
the normal Cascade LLM and pooled Speech TTS remain in charge. It waits for a
matching `session.updated` acknowledgement (including the exact model identifier)
before accepting PCM, applies bounded
audio backpressure, preserves final-transcript ordering, and closes on provider
failure instead of substituting another recognizer. This connection never enters
or releases the Speech SDK pool.

Browser PCM defaults to 24 kHz and ACS to 16 kHz, mono PCM16. MAI input rejects
diarization and global Speech phrase biases. Semantic segmentation selects
semantic VAD; a single candidate language becomes a hint and multiple candidates
use explicitly reported automatic detection. Provider changes require reconnecting.

`runtime_transcription_models` on the voice catalog advertises implemented backend
routing, not regional model availability. MAI voice IDs use `voice.type:
azure-standard` and remain intact through VoiceLive requests and Cascade SSML.
The configured Speech resource must separately support the chosen MAI voice.

### Foundry prompt-agent direction

A versioned Foundry **prompt agent**, rather than a hosted voice agent, is a good
fit for making the authoring instructions, model and tool definitions visible.
The current generator remains the direct-model path; no Foundry authoring agent
is provisioned automatically.

The recommended authoring tools are read-only and bound to the calling session
on the server, with no model-supplied session identifier:

| Tool | Purpose |
|------|---------|
| `find_session_agents` | Search the effective registry, including current session overrides. |
| `get_agent_configuration` | Read a selected agent's current configuration, with private values protected. |
| `list_available_tools` | Inspect registered capabilities and current MCP availability. |
| `get_current_scenario` | Read the active scenario and current review draft. |
| `validate_scenario_draft` | Return schema, routing and capability errors without writing state. |

The app must execute these lookups against the latest session cache, return the
tool results to the Foundry agent, and revalidate the final result before review.
Keep Apply and all business-tool execution outside the authoring agent.

Current versioned prompt-agent guidance:
[Create a prompt agent](https://learn.microsoft.com/azure/foundry/agents/quickstarts/prompt-agent)
and [function calling](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/function-calling).
Azure AI Projects 1.x is not the versioned prompt-agent SDK; use the documented
2.x SDK or REST contract when implementing this provider.

### Front Door telephony authentication (opt-in)

`ENABLE_FRONT_DOOR=false` is the default and preserves existing ingress behavior.
Set it to `true` **together with** the private-origin Front Door Premium/WAF
deployment; this backend flag does not create a firewall or restrict ordinary
user routes to a VPN. Those restrictions and origin lockdown remain infrastructure
requirements.

The backend fails during application setup if any required setting is absent or
invalid:

| Environment variable | Required value when enabled |
|---|---|
| `ENABLE_FRONT_DOOR` | `true` to require the telephony authentication gate. |
| `ACS_AUDIENCE` | The ACS **immutable resource UUID** (not the ARM ID, endpoint, tenant ID, or application client ID). |
| `ACS_ARM_RESOURCE_ID` | Full ARM resource ID of that same ACS resource, `/subscriptions/.../resourceGroups/.../providers/Microsoft.Communication/communicationServices/...`. |
| `EVENT_GRID_WEBHOOK_SECRET` | Random high-entropy shared secret, 32–4096 printable non-space ASCII characters. Generate at least 32 random bytes, encode for use in a header, store in Key Vault, and supply through an ACA secret reference. |

These deployment security values are environment settings, not App Configuration
feature flags. Changing them requires a new backend revision/restart. Do not
commit or log the webhook secret.

Only these exact telephony routes are public exceptions to VPN user access:

| Route | Authentication before handler execution |
|---|---|
| `POST /api/v1/calls/callbacks` | ACS bearer JWT in `Authorization`. |
| `WebSocket /api/v1/media/stream` | ACS bearer JWT in the upgrade's `Authorization` header, checked **before accepting** or creating a voice session. |
| `POST /api/v1/calls/answer` | `X-EventGrid-Webhook-Secret` header, constant-time comparison, then Event Grid event/topic validation. |

The ACS verifier pins `RS256`, the issuer
`https://acscallautomation.communication.azure.com`, and the JWKS endpoint
`https://acscallautomation.communication.azure.com/calling/keys`. It requires
`exp`, `iss`, and `aud`, verifies the signature, expiry and configured audience,
and ignores token-supplied key URLs. Keys are retrieved asynchronously with a
five-second total deadline and bounded response size, cached for one hour, and
refreshed on an unknown key ID. Unknown-key refreshes and failed downloads are
throttled for 30 seconds. Expired cached keys are not used on refresh failure.
Missing/invalid credentials or unavailable signing keys fail closed (HTTP 401;
WebSocket close before acceptance produces HTTP 403 in Uvicorn). The documented
five-minute callback JWT and **24-hour media JWT** are both supported: the
verifier checks `exp`, not a hard-coded five-minute token lifetime.

Configure the incoming-call Event Grid subscription with `EventGridSchema`,
event type `Microsoft.Communication.IncomingCall`, and a **static, secret**
delivery attribute named `X-EventGrid-Webhook-Secret`, from subscription creation
onward. The same header is required for subscription validation. No query-string
secret or anonymous validation fallback is supported. The authenticated payload
must be a non-empty event array whose every `topic` matches `ACS_ARM_RESOURCE_ID`
(case-insensitive ARM comparison); other event types, conflicting CloudEvents
`source`/`type` fields, malformed incoming contexts, and mixed validation batches
are rejected before the handler runs. A single authenticated
`Microsoft.EventGrid.SubscriptionValidationEvent` with a non-empty
`data.validationCode` returns `{"validationResponse": "..."}` directly from the
gate, **without requiring ACS startup or a call session**. Body reads are limited
to 1 MiB and five seconds. This change is shared by Cascade and VoiceLive; it
does not change either orchestrator or outbound ACS authentication.

With `ENABLE_AUTH_VALIDATION=true`, the telephony ASGI gate runs **outside**
the existing Entra HTTP middleware. Only an internal marker on a successfully
authenticated **exact** telephony route bypasses Entra; headers/query parameters
cannot set that marker. Legacy callback/media prefix exemptions are removed in
this mode, so suffix routes and ordinary HTTP APIs still require Entra.
Existing health exemptions remain unchanged. When Front Door is disabled,
legacy Entra behavior remains unchanged. If ACA EasyAuth is also configured,
its external policy must permit these exact machine-authenticated routes to
reach this gate; do not broadly exclude `/api/v1/calls/*`. Front Door must
forward the authorization and secret headers, and its anonymous health probe
must target the existing health endpoint, not these telephony routes.

References:
[ACS webhook and media JWT validation](https://learn.microsoft.com/azure/communication-services/how-tos/call-automation/secure-webhook-endpoint),
[Event Grid static delivery headers](https://learn.microsoft.com/azure/event-grid/delivery-properties)
(including webhook validation),
and [Event Grid subscription validation](https://learn.microsoft.com/azure/event-grid/end-point-validation-event-grid-events-schema).
