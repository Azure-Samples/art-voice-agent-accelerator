# Adding a New Agent

This guide shows how to add a brand-new specialist agent (e.g., Billing) to the modular orchestrator without changing any existing behavior. You’ll:

- create a YAML config
- instantiate the agent at startup
- write a tiny handler
- register the handler
- (optional) list it in the default specialists
- route into it from tools/LLM

Routing, greetings, voice sync, and session-safe broadcasting are handled by the orchestrator.

## Where things live

- Orchestrator package: apps/rtagent/backend/src/orchestration/
- public entry point (called per turn): route_turn(cm, transcript, ws, is_acs=...)
- register API: register_specialist(name, handler)
- config API: configure_entry_and_specialists(entry_agent='AutoAuth', specialists=[...])
- agent resolution (recommended): ws.app.state.agent_instances[name]
- agent resolution (also supported): ws.app.state.<attr> via a binding map

## 1) Create your agent YAML

Create a config file consumed by ARTAgent, e.g. configs/agents/billing.yaml.

```yaml
# configs/agents/billing.yaml
agent:
  name: Billing
  creator: Voice Agent Team
  organization: XYMZ Insurance
  description: Handles billing questions, payments, and invoices.

model:
  deployment_id: gpt-4o-mini
  temperature: 0.4
  top_p: 0.95
  max_tokens: 2048

voice:
  name: en-US-JennyNeural
  style: chat
  rate: "+3%"

prompts:
  # Put this template in your templates directory
  path: voice_agent_billing.jinja

tools:
  # Tools must exist in the tool registry (string) or be inline tool specs (dict).
  - verify_policy
  - lookup_invoice
```

## 2) Instantiate the agent at startup

Create the instance during app startup so the orchestrator can find it.

### Option A (recommended, no code changes elsewhere): store in a dict keyed by the exact agent name.

```python
# main.py (inside lifespan startup AFTER other agents are created)
from apps.rtagent.backend.src.agents.artagent.base import ARTAgent

# ensure the dict exists
app.state.agent_instances = getattr(app.state, "agent_instances", {})

# create and store your agent
app.state.agent_instances["Billing"] = ARTAgent(
    config_path="configs/agents/billing.yaml"
)
```

### Option B (explicit binding): add a dedicated attribute and a binding entry (only if you prefer a named attribute).

```python
# main.py (startup)
app.state.billing_agent = ARTAgent(config_path="configs/agents/billing.yaml")

# If you maintain a binding table, add:
# from apps.rtagent.backend.src.orchestration.artagent.bindings import AGENT_BINDINGS, AgentBinding
# AGENT_BINDINGS["Billing"] = AgentBinding(name="Billing", ws_attr="billing_agent")
```

Either approach works. Option A requires no binding updates.

## 3) Write a tiny handler

Create apps/rtagent/backend/src/agents/billing_handler.py. The easiest path is to reuse the shared specialist runner so you inherit latency tracking, history injection, and tool post-processing.

```python
# apps/rtagent/backend/src/agents/billing_handler.py
from __future__ import annotations
from fastapi import WebSocket

# Helper to read from core memory safely
from apps.rtagent.backend.src.orchestration.artagent.cm_utils import cm_get

# ✅ If you split helpers into modules (recommended):
from apps.rtagent.backend.src.orchestration.artagent.specialists import _run_specialist_base  # adjust import if needed

# 🔁 If you're still on a single orchestrator module containing the helper:
# from apps.rtagent.backend.src.orchestration import _run_specialist_base

async def run_billing_agent(cm, utterance: str, ws: WebSocket, *, is_acs: bool) -> None:
    caller_name = cm_get(cm, "caller_name")
    policy_id = cm_get(cm, "policy_id")

    context_msg = (
        f"Authenticated caller: {caller_name} (Policy: {policy_id}) | Topic: billing"
    )
    await _run_specialist_base(
        agent_key="Billing",
        cm=cm,
        utterance=utterance,
        ws=ws,
        is_acs=is_acs,
        context_message=context_msg,
        respond_kwargs={
            "caller_name": caller_name,
            "policy_id": policy_id,
            "topic": "billing",
        },
        latency_label="billing_agent",
    )
```

### Alternative (fully explicit handler)

If you prefer not to import the shared runner, mirror the explicit pattern:

```python
from __future__ import annotations
from typing import Any, Dict
from fastapi import WebSocket

from apps.rtagent.backend.src.orchestration.artagent.cm_utils import cm_get
from apps.rtagent.backend.src.orchestration.artagent.voice_sync import sync_voice_from_agent
from apps.rtagent.backend.src.orchestration.artagent.tools_post import process_tool_response
from apps.rtagent.backend.src.orchestration.artagent.metrics import track_latency

async def run_billing_agent(cm, utterance: str, ws: WebSocket, *, is_acs: bool) -> None:
    agent = ws.app.state.agent_instances.get("Billing")
    caller_name = cm_get(cm, "caller_name")
    policy_id = cm_get(cm, "policy_id")

    # Optional: context line into the transcript for grounding
    cm.append_to_history(
        getattr(agent, "name", "Billing"),
        "assistant",
        f"Authenticated caller: {caller_name} (Policy: {policy_id}) | Topic: billing",
    )

    async with track_latency(ws.state.lt, "billing_agent", ws.app.state.redis, meta={"agent": "Billing"}):
        resp: Dict[str, Any] = await agent.respond(
            cm,
            utterance,
            ws,
            is_acs=is_acs,
            caller_name=caller_name,
            policy_id=policy_id,
            topic="billing",
        )

    await process_tool_response(cm, resp, ws, is_acs)
```

## 4) Register the handler

Tell the orchestrator which coroutine to call when active_agent == "Billing". Do this once at startup (after the app initializes).

```python
# main.py (after app = initialize_app()) or at the end of lifespan startup
from apps.rtagent.backend.src.orchestration import register_specialist
from apps.rtagent.backend.src.agents.artagent.billing_handler import run_billing_agent

register_specialist("Billing", run_billing_agent)
```

The registry key must exactly match the agent name you used in agent_instances["Billing"] (or the binding name).

## 5) (Optional) Add to the default specialists list

Not required, but you can include Billing in the ordered specialists list:

```python
from apps.rtagent.backend.src.orchestration import configure_entry_and_specialists

configure_entry_and_specialists(
    entry_agent="AutoAuth",
    specialists=["General", "Claims", "Billing"]
)
```

The entry agent is always coerced to AutoAuth (auth first, then route).

## 6) Route into your agent (no orchestrator edits)

There are three ways the orchestrator switches agents:

### 6.1 Explicit hand-off (recommended for new agents)

Return this from any tool/LLM output:

```json
{
  "success": true,
  "handoff": "ai_agent",
  "target_agent": "Billing",
  "topic": "payment_arrangements"
}
```

The orchestrator sets active_agent="Billing", syncs voice, sends a greeting, and continues.

### 6.2 Intent-based routing (built-in)

Only for "claims" and "general". For Billing and other new agents, use explicit hand-off.

### 6.3 Human escalation

Triggers session termination automatically (no extra code):

```json
{
  "success": true,
  "handoff": "human_agent",
  "reason": "backend_error"
}
```

## 7) Voice + greeting behavior (automatic)

When the orchestrator switches to your agent it automatically:

- copies voice_name, voice_style, voice_rate from your ARTAgent into CoreMemory,
- emits a first-time greeting (or a “welcome back” greeting thereafter),
- speaks via TTS (ACS or WebSocket) using your agent’s voice.

No extra work needed.

## 8) Quick test checklist

- Start the backend; ensure there are no import errors.
- Confirm your instance exists after startup:
  - app.state.agent_instances["Billing"] (Option A), or
  - app.state.billing_agent (Option B).
- Trigger a hand-off by returning:
  - {"success": true, "handoff": "ai_agent", "target_agent": "Billing"}
- Watch logs for:
  - Hand-off → Billing
  - greeting + TTS
  - correct voice in use
- Verify the frontend shows “Billing specialist” greeting and subsequent replies.
- Run a short conversation; ensure state persists and no exceptions occur.

## 9) Common pitfalls

- Name mismatch: "Billing" must match:
  - the registry key in register_specialist("Billing", ...),
  - the instance key agent_instances["Billing"] (or the binding name),
  - the target_agent string returned by tools/LLM.
- No instance: You registered the handler but never created an ARTAgent in startup.
- Forgot to import registration: If you register from a module that never imports at startup, the handler won’t be in the registry. Register from a guaranteed path (main.py or inside the lifespan block).
- Wrong helper import path: If you haven’t split helpers into modules yet, import _run_specialist_base directly from the orchestrator module instead of orchestration.specialists.

## 10) Minimal end-to-end diff (copy/paste)

**A) YAML — configs/agents/billing.yaml (from Step 1)**

**B) Startup instance — main.py (inside lifespan)**

```python
app.state.agent_instances = getattr(app.state, "agent_instances", {})
app.state.agent_instances["Billing"] = ARTAgent(
    config_path="configs/agents/billing.yaml"
)
```

**C) Handler — apps/rtagent/backend/src/agents/billing_handler.py (from Step 3)**

**D) Registration — main.py (after app init) or inside lifespan**

```python
from apps.rtagent.backend.src.orchestration import register_specialist
from apps.rtagent.backend.src.agents.artagent.billing_handler import run_billing_agent

register_specialist("Billing", run_billing_agent)
```

File tree snippet (for orientation)

```text
apps/
  rtagent/
    backend/
      src/
        agents/
          billing_handler.py
          base.py                     # ARTAgent class
        orchestration/
          __init__.py                 # exposes register_specialist, configure_entry_and_specialists, route_turn
          # specialists.py            # (optional if you split helpers)
          # cm_utils.py, metrics.py   # (optional if you split helpers)
configs/
  agents/
    billing.yaml
```