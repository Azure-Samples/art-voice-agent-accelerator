# **ARTVoice Frontend**

**React voice interface** with WebSocket real-time communication for Azure Communication Services.

## **Quick Start**

```bash
npm install
npm run dev  # http://localhost:5173
```

## **Architecture**

```
frontend/
├── src/
│   ├── main.jsx              # React entry point
│   └── components/
│       └── App.jsx           # Complete voice app, including outbound phone calls
├── package.json
├── entrypoint.sh             # Container startup (App Config integration)
└── .env                      # Local development configuration
```

## **Features**

- **Real-time Voice Processing** - WebAudio API integration
- **WebSocket Communication** - Live backend connectivity  
- **Azure Communication Services** - Phone call integration
- **Health Monitoring** - Backend status indicators

## **Configuration**

### Local Development

```bash
# .env
VITE_BACKEND_BASE_URL=http://localhost:8010
```

### Azure Deployment (App Configuration)

When deployed to Azure Container Apps, the frontend reads configuration from **Azure App Configuration** at container startup:

| App Config Key | Description |
|----------------|-------------|
| `app/frontend/backend-url` | Backend API URL (e.g., `https://backend.azurecontainerapps.io`) |
| `app/frontend/ws-url` | WebSocket URL (e.g., `wss://backend.azurecontainerapps.io`) |

The container uses managed identity to authenticate with App Configuration. Environment variables set in Container Apps:

```
AZURE_APPCONFIG_ENDPOINT=https://appconfig-xxx.azconfig.io
AZURE_APPCONFIG_LABEL=<environment>
AZURE_CLIENT_ID=<managed-identity-client-id>
```

The `entrypoint.sh` script:
1. Acquires an access token via managed identity (IMDS)
2. Fetches `backend-url` and `ws-url` from App Configuration
3. Replaces `__BACKEND_URL__` and `__WS_URL__` placeholders in built JS files
4. Starts the web server

## **Key Dependencies**

- **React 19** - Core framework
- **Vite** - Build tool and dev server
- **Azure Communication Services** - Voice calling SDK
- **Microsoft Cognitive Services** - Speech SDK

## UI Components

**Main Interface**:
- 768px fixed width
- Voice controls (start/stop, phone)
- Real-time waveform animation
- Message bubbles with timestamps
- Backend health status
- Help system modal

## Phone, email, and SMS providers

Open **Place call** to inspect three independent communication services:

- **Telephony provider** starts on **ACS (standalone)** for every page load.
  **Teams Phone (via ACS/TPE)** is an explicit opt-in for the next outbound call,
  enabled only when the backend reports its configuration available. Both use
  the existing ACS transport, dashboard relay, status, and termination paths.
- **Email provider** remains **ACS Email** and **SMS provider** remains **ACS SMS**.
  Their status is server-configured; the selectors do not update server settings.
  External email/SMS alternatives are visible but disabled, not implemented, and
  not wired. Teams Phone is **not** an email or SMS service.
- **Voice engine** (Custom Speech/Cascade or VoiceLive) is independent of the
  telephony choice.

The UI reads `GET /api/v1/calls/providers` using the same configured backend URL
as the rest of the application. These statuses describe configuration only, not
live connectivity, licensing, permissions, or successful provisioning. A missing
or invalid catalog, discovery failure, or unavailable selected provider blocks
outbound calls and exposes **Retry providers** / **Refresh providers**.
Unavailable alternatives also show their reason and unmet requirements while
ACS is selected. For example, an enabled Teams configuration is still unavailable
when the installed Call Automation SDK lacks explicit `teams_app_source` support;
the UI never infers availability from the enabled flag or resource account.
Teams requires Call Automation SDK 1.5.0+ with that capability in the running
backend interpreter; a newer lockfile alone does not upgrade an older runtime.
Email/SMS server detail messages remain visible: configuration does not validate
delivery or turn demo-only tools into live integrations.
Older backends without discovery must be updated; the UI deliberately does not
assume ACS is configured or silently fall back from Teams to ACS.

The actual `POST /api/v1/calls/initiate` includes
`telephony_provider: "acs" | "teams"` alongside the existing target, engine, and
browser-session context. Provider selection is component-local, survives status
refreshes and calls, and is never saved to local storage. It is locked while a
request is in flight, while the phone is ringing, and during a connected call.
Repeated clicks cannot start a second call. **Initiating**, **waiting for
connection**, and **Connected** are distinct states; a successful POST alone
does not mean connected. Hangup uses the shared termination API.

This UI does not create Teams admin resources, change inbound routing or
deployment-wide defaults, or request/display credentials or resource-account
identifiers. Configure those prerequisites on the server.

Targeted tests (mocked APIs; no live telephony or backend required):

```bash
node --test src/utils/communicationProviders.test.js
npm run test:e2e -- e2e/communication-providers.spec.js
```

## Quick Tune: agents and scenarios

**Quick Tune** is the single authoring entry point on the main page. Open its
sidebar control to edit agents and scenarios. To start from a prompt, choose
**Create scenario** inside the same workspace; there is no separate create button.
The panel overlays the conversation as a floating, fixed-position drawer on
desktop and becomes a modal panel on smaller screens - opening or expanding it
never resizes or shifts the conversation window. **Advanced Builder** retains
the full agent and graph editors, connection setup, and less-common
configuration options.

| View | What to edit |
|------|--------------|
| **Tune agent** | Select an agent, then open **Behavior**, **Tools**, or **Voice & model**. **Open prompt editor** provides a larger Markdown/Jinja workspace. Technical audio settings are under **Fine controls**. |
| **Edit scenario** | Choose any existing template or session scenario, including single-agent scenarios. Update its purpose, icon, context, defaults, agents, and handoffs, or open the graphical editor. |
| **Create scenario** | Describe an outcome, optionally restrict the tool catalog, and generate an editable draft. |

**Tune agent** and **Edit scenario** include a clickable graph preview of the
scenario selected for editing (initially the active scenario). It shows up to
three real agents, their configured tool counts when available, and actual
handoffs; larger scenarios show how many agents are included in the excerpt.
**Open graphical editor** opens that same scenario draft to drag nodes, connect
agents, and edit handoff conditions. Previewing or opening the graph does not
save, activate, or change the running conversation. Unsaved scenario edits are
reflected in the preview and labeled **Draft**. The full canvas keeps the user's
node positions; the compact preview uses its own readable, automatic layout.
If the complete scenario cannot load, **Retry preview** reloads it without
blocking agent tuning or replacing a session override with an unrelated template.

Tuning targets the named agent, not the last-created session agent. Unedited
prompts, tool assignments, model options, and context are retained when saving.
Use **Duplicate agent** to create an independent copy; existing names cannot be
overwritten through that action.
Copies keep the complete shipped prompt, including its existing Jinja logic, and
allow prose edits without truncation. Legacy handoff tools are not copied into the
new agent; the scenario supplies its routing.

The model list is scoped to the service that will use it: Custom Speech lists
deployments on the primary Foundry resource; VoiceLive BYOM lists deployments on
the VoiceLive resource. Resource/region attribution and cross-region advisories
remain visible in Quick Tune. Non-managed VoiceLive models require an explicit
BYOM profile, and known realtime/text profile mismatches cannot be applied.

### Choose a regional Speech voice

**Voice & model**, the Agent Builder, and the Scenario Builder agent editor share
one voice picker that works from the full catalog returned by the connected Speech
resource:

1. **Voice language** — pick a locale such as *English (United States)*. Two
   entries are pinned at the top: **Multilingual** (MAI, Dragon HD Omni, and
   `*Multilingual*` voices) and **All languages**. Each entry shows its voice count.
   The picker starts on the current voice's locale.
2. **Family** — **All**, **MAI**, **HD**, or **Standard**, with counts for the
   chosen language.
3. **Voice** — the filtered list. Typing searches every language by display name,
   service identifier, locale, gender, or style, so you can jump to a voice without
   changing the language first.

**Refresh regional voice catalog** requests fresh discovery instead of using the
ten-minute cache. Discovery does not block the rest of the agent editor. The
current voice and other settings are preserved if refresh fails or the voice is
not returned by the resource.

Catalog provenance matters: a registration-only backend may return just voices
referenced by repository agents. An unavailable Speech resource uses explicitly
labelled, limited starter presets; a stale regional cache is also labelled. Use a
Speech-connected backend for the full regional list. Regional Speech availability
does not by itself validate every VoiceLive model/voice combination; custom,
personal, and native-model voices can require separate configuration.

### MAI voice and transcription options

MAI voices appear first, newest model first with Flash ahead of the full model:
**MAI-Voice-2.1-Flash**, **MAI-Voice-2.1**, then legacy **MAI-Voice-2-Flash** and
**MAI-Voice-2** names if the resource still returns them. Select the **MAI** family
to see them all. Documented MAI voices are listed even when the resource's catalog
omits them, and are labelled as such.

MAI voices synthesize only in
[supported regions](https://learn.microsoft.com/azure/ai-services/speech-service/mai-voices#availability-and-regions).
When MAI is selected, the picker states whether the relevant resource supports it:
the Speech resource for **Custom Speech**, the VoiceLive resource for **VoiceLive**,
and either resource in the builders (agent definitions serve both modes). If the
region is unsupported, the picker names it, explains the fix, links the region list,
and disables MAI options until you turn on **Select MAI voices anyway**. Choosing an
MAI voice uses the `azure-standard` voice type.

**Input transcription** is a primary control in both **Custom Speech** and
**VoiceLive**, with **MAI Transcribe 2.0** listed first. This choice preserves the
explicit wire identifier `mai-transcribe-2`; it is never rewritten to
`mai-transcribe`. The separate **MAI Transcribe (generic alias)** option uses
`mai-transcribe` and does **not** pin version 2.0. Legacy `mai-transcribe-1.5`
selections display as the generic alias for compatibility.

An omitted Custom Speech `speech.transcription_model` now defaults to
`mai-transcribe-2`. Advanced Builder exposes the same provider selector, including
an explicit **Azure Speech** override. Existing explicit providers are retained.

For VoiceLive, **Auto (follow profile)** resolves to `mai-transcribe-2` for
`byom-azure-openai-chat-completion` and `byom-foundry-anthropic-messages`, and to
`azure-speech` for other profiles. New/reset Advanced Builder sessions use
`model: auto` so a later BYOM profile change is not pinned to an implicit Azure
setting. Missing, null, or empty model settings also default to explicit 2.0 for
those two BYOM profiles; other profiles retain their existing service default.
Native realtime and BYOM realtime audio pipelines are unchanged. Explicit Azure,
generic MAI, and other model choices do not follow profile changes. The helper
text shows the effective input, and clearing a selection retains language,
custom speech, and phrase-list settings rather than silently resetting them.

**Availability remains unconfirmed:** the connected backend's
`runtime_transcription_models` advertises implementation support, not a successful
service probe, entitlement, or regional availability. The explicit 2.0 identifier
is not confirmed by the linked public VoiceLive documentation. Confirm support
on your configured endpoint before deployment; the generic alias is not evidence
that version 2.0 is available.

For **VoiceLive**, **Model source** makes the pipeline explicit. MAI input requires
a managed text model or a BYOM chat/Messages profile; native realtime audio and
BYOM realtime profiles are not interchangeable with that pipeline. The
**Use managed gpt-4.1** action is explicit: it changes the VoiceLive model and
clears BYOM only when selected. A BYOM deployment remains the user's choice.
There is no invented `custom-cascade` query profile: managed text models already
use a speech/chat/speech pipeline.

Azure-only phrase lists and custom speech models are not silently discarded when
selecting MAI. Incompatible configuration blocks the affected mode's Save/Apply
until the user removes those options or chooses Azure Speech. New MAI input
selection is disabled on older backends that do not advertise the required
runtime support for that exact identifier. Validation also checks inferred
defaults: an omitted Cascade provider cannot bypass the diarization guard.

For **Custom Speech**, MAI input uses a separate speech-only VoiceLive connection
with automatic model responses disabled. The selected Cascade LLM and pooled
Speech TTS are unchanged. **Semantic turn detection** controls the MAI connection's
VAD; Azure SDK diarization is not supported. A single candidate language is a hint;
multiple candidate languages use automatic detection rather than an enforced
allowlist. Configured global Azure Speech phrase biases must be removed before
starting MAI input. Provider/region/auth failures are reported instead of silently
switching back to Azure Speech. Input-provider changes require a new connection.

References: [MAI voices](https://learn.microsoft.com/azure/ai-services/speech-service/mai-voices),
[VoiceLive MAI transcription](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-how-to#mai-transcribe-preview),
and [BYOM profiles](https://learn.microsoft.com/azure/ai-services/speech-service/how-to-bring-your-own-model).

Targeted provider/default tests:

```bash
node --test src/utils/maiSpeech.test.js
npm run test:e2e -- e2e/mai-speech.spec.js
```

### Edit an existing scenario

Choose **Edit scenario**, then select **Scenario to edit**. Each scenario retains
its own unsaved configuration and node layout as you switch between scenarios or
close Quick Tune. The scenario name is its stable identity; editing a built-in
scenario creates or updates a session override rather than rewriting its YAML
template.

**Scenario context** and **Agent defaults** accept typed JSON objects, preserving
nested data, booleans, and numbers. Invalid JSON and unsupported default keys
block saving; they are not silently discarded. Unedited tools and defaults remain
part of the configuration. Legacy scenarios that allow all registered agents keep
that behavior until you explicitly restrict their membership.

Use **Save scenario** for the current scenario. When editing a different scenario,
**Save & activate** explicitly selects it for the next conversation. Merely
choosing or editing it does not change the running scenario. End an active
conversation before saving scenario changes.

### Edit prompts with session context

Under **Behavior**, choose **Open prompt editor**. The pop-out has a full-height
Markdown/Jinja source area, formatting controls, undo/redo, and a searchable
context browser. On smaller screens, **Source**, **Context**, and **Preview** tabs
keep each view usable without shrinking the conversation window.

Context entries show their path, source, type, and a safe snapshot value. Inserting
an entry replaces the current text selection with its Jinja expression, not the
literal session value. Unavailable values use an explicit `default("")` expression;
sensitive entries cannot be inserted through the browser.

**Preview prompt** renders a read-only snapshot without calling models, executing
tools, or registering configurations. **Rendered text** displays the literal
prompt text, not executable HTML. Syntax errors include line numbers, and an old
preview is marked stale when the source or authoring context changes. Refresh to
render the latest draft. Previewing unsaved scenario context is explicitly labeled:
save that scenario separately before relying on those values at runtime.

If context loading reports that the preview endpoint is unavailable, the connected
backend is older than the editor. Start or restart the updated API, then use
**Retry** or **Refresh session context** in the existing editor. A browser reload
is not required and would discard unsaved workspace drafts.

Closing the editor keeps prompt changes in the Quick Tune draft. Existing agents
can use the same **Save changes** / **Apply & reconnect** action inside the pop-out.
For a newly generated scenario agent, **Done editing** returns to graph review;
only **Apply scenario** registers it. Keyboard shortcuts include Ctrl/Cmd+B,
Ctrl/Cmd+I, Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, and Ctrl/Cmd+Enter for preview. Tab retains
normal keyboard navigation.

### Choose tools

**Tools** opens a catalog rather than a multi-select dropdown and brings its list
into view. Search by purpose, tool name, or an agent's name; open **Filters** to
narrow the list by **Category** or **Assigned to**.
The **Selected** view reviews only the current selection. Filters and pagination
never remove selections that are out of view.

Each entry shows its description, identifier, category, built-in or MCP source,
and agent assignments. **View tool details** expands the complete description,
required and optional inputs, schema, and the full agent list. Assignment labels
distinguish templates, saved session configurations, and unsaved workspace drafts.
These are configuration references, not evidence that an agent executed a tool.
MCP registration does not imply a working connection.

Selections stay in the agent draft until **Save changes** or the applicable Apply
action. **Clear selection** only clears editable capabilities; scenario-managed
handoff tools are preserved. Missing registered tools remain visible in the
selection and are never silently removed. The same catalog is available in a
generated agent's graph inspector and under **Tool scope** when creating a scenario.
Changing generation scope does not assign tools to the currently running agent;
**Use all registered tools** restores unrestricted catalog scope.

### Generate a scenario

1. Describe what the conversation should accomplish and select **Generate draft**.
2. The result automatically opens in the **graphical scenario editor** for
   review: drag agent nodes (including new, not-yet-connected specialists),
   inspect or edit an agent, edit a handoff's routing condition, and add or
   remove routes. Nothing is saved, registered, or activated by generating,
   dragging, or editing here - only **Apply scenario** persists anything.
   Existing agents are reused unchanged; new specialists are drafted only when
   needed. Choose **Customize a copy** to change a reused agent without
   overwriting it. A simple list-based review remains available in the same
   workspace for the same draft.
3. Edit the draft directly or provide a refinement and select **Refine draft**.
   Resolve missing capabilities and fill in required scenario context. Closing
   the graphical editor keeps the draft and any node positions - reopen it with
   **Graphical editor** to continue exactly where you left off.
4. Select **Apply scenario**, then start a conversation to try it.

The graph keeps its canvas usable in narrower windows: **Agents** and **Routes**
open dismissible panels instead of squeezing the canvas between fixed sidebars.
On smaller screens, inspecting an agent uses the full editor area; **Close
inspector** returns to the graph without losing edits or node positions. The
dialog's close and Apply actions remain outside the scrolling editor. Long names
and descriptions wrap in panels and menus; compact node summaries offer the full
name on hover and the full configuration through **View agent details**.

Generation uses the backend's configured Azure OpenAI integration and registered
tool catalog. A configured chat-model deployment is required for generation;
applying generated scenarios and saving new copies require Redis so the complete
configuration can be persisted atomically. It does not execute tools or change
the active scenario during generation. The backend
checks references and current tool availability again on Apply, and reports
generation or persistence failures in the workspace rather than silently
substituting a sample scenario. MCP tools still require working connections;
registration alone does not guarantee availability.

Drafts remain in the workspace when closing it, switching views, or selecting
another agent. They are **not saved** until Apply/Save and do not survive a page
reload or switching sessions. Applied configurations are session-scoped; editing
does not rewrite the repository's YAML templates.

### Applying changes during a conversation

- **Apply live** is available for supported VoiceLive voice-name, speaking-rate,
  and turn-detection changes to the running agent.
- **Apply & reconnect** saves structural changes and reconnects an active browser
  conversation. Instructions, tools, models, transcription, voice style, and pitch
  are not silently dropped from the live-update payload.
- Phone calls are not automatically hung up. Changes requiring a new connection
  are saved for the next call.
- End an active conversation before applying a different scenario or changing
  handoffs. Drafting and reviewing remain available during the call.

The mode selector edits settings for **Custom Speech** or **VoiceLive**; it does
not switch a running conversation's orchestration mode.

### Frontend development checks

```bash
npm run test:unit
npm run build
npm run test:e2e -- quick-tune.spec.js existing-scenarios.spec.js prompt-editor.spec.js scenario-graph-review.spec.js authoring-layout.spec.js tool-catalog.spec.js regional-voices.spec.js mai-speech.spec.js scenario-switching.spec.js
```

Browser tests mock the backend APIs. When another worktree is using the default
development port, set `PLAYWRIGHT_PORT=5183` (or another free port). On a fresh
Playwright installation, run `npx playwright install chromium` before browser
tests. The authoring layout suite covers desktop, tablet, and phone-sized windows
with long agent names, model IDs, and tool names, including dropdowns, handoff
editing, and the graph inspector.

The blocking unit-test workflow runs the frontend unit suite, production build,
and mocked Firefox authoring suite. Live HTTP/Redis registration checks remain
explicit opt-in; browser tests never synthesize speech or execute business tools.

For registration checks against a running local backend (real HTTP and Redis,
without route mocks), use a dedicated local instance:

```bash
LOCAL_CONFIG_API=http://127.0.0.1:8011/api/v1 PLAYWRIGHT_PORT=5183 \
  npm run test:e2e -- quick-tune-live-registration.spec.js
```

These checks create uniquely named test sessions and remove them afterward.
They verify configuration registration and browser-to-API updates, not acceptance
by Azure Speech or VoiceLive. Live Azure checks require access to the configured
tenant and resources. If Chromium cannot launch on the host, set
`PLAYWRIGHT_BROWSER=firefox` after installing the existing runner's Firefox browser
with `npx playwright install firefox`.

### Configuration-to-service bindings

| Configuration | Runtime binding |
|---------------|-----------------|
| Voice name, rate, style, pitch | Cascade SSML and VoiceLive voice objects; pitch is request-local, not shared between pooled clients. |
| VoiceLive temperature / output limit | `RequestSession.temperature` (0–1) and `max_response_output_tokens`. |
| VoiceLive transcription | Model, language, custom Speech options, and phrase hints are preserved in `AudioInputTranscriptionOptions`. |
| Cascade model options | Chat Completions by default, or explicit Responses streaming; supported options, structured tool history, and usage events use the selected API's shape. |
| Scenario routes | Named and generic handoff tools resolve the session scenario's target, announced/discrete behavior, and context-sharing settings. |

VoiceLive does not use the Cascade endpoint selector, Top P, verbosity, or
reasoning controls. Its supported generation controls are shown separately.
Min P and Typical P are unsupported by the OpenAI endpoints and are disabled;
previously stored values can be cleared in Advanced Builder. An available
reasoning summary can be requested through the Responses endpoint.

Registration/serialization tests are distinct from live service acceptance.
Model-specific capability, regional availability, credentials, and successful
Speech/VoiceLive calls still require an authorized Azure environment.
