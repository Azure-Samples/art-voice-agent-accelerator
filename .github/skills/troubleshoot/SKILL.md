---
name: troubleshoot
description: Agent-first, read-only diagnosis of the voice pipeline (deploy, telephony, STT, LLM, TTS, state) — gather evidence via Azure MCP / azd artifacts / CLI, probe the user for missing details, and recommend fixes without changing anything
---

# Troubleshoot Skill

Use this skill to **diagnose** problems in the Real-Time Voice Agent pipeline. This is a
read-only investigative workflow: gather evidence, reason about it, ask the user for the
details you don't have, then hand back a clear findings + recommended-fix report.

> **🧭 Golden rule:** Diagnose, don't change. You find and explain the problem. The **user**
> decides whether and how to apply the fix.

---

## 🚧 Guardrails (read this first)

**You MUST NOT** (without explicit, per-action user approval):

- ❌ Edit code, YAML, `.env*`, Terraform, Bicep, or any config file
- ❌ Run state-changing Azure/infra commands: `azd up`, `azd provision`, `azd deploy`,
  `azd down`, `azd env set`, `terraform apply/destroy`, `az ... create/update/delete`,
  `az containerapp update`, scaling, restarts, key rotation
- ❌ Run `git commit`, `git push`, `git reset`, branch deletes, or `bd` writes
- ❌ Restart, redeploy, purge, or "nuke and redeploy" anything as a shortcut
- ❌ Invoke any **MCP tool with a write side-effect** (e.g. anything that creates GitHub issues,
  updates resources, or scales/restarts) — including a "scan" tool whose options default to writing
- ❌ Print secrets/connection strings/keys in full — mask them (`endpoint=...;accesskey=***`)

**You MUST**:

- ✅ Prefer **read-only** commands (`show`, `list`, `get`, `logs`, `query`, `curl`, `ping`)
- ✅ **Ask before assuming** — see Step 0. Probe for the missing detail instead of guessing
- ✅ Present a **fix as a recommendation** the user applies, or ask for approval before running it
- ✅ State your confidence and what evidence is still missing

If a fix genuinely requires a write action, **stop and propose it** — show the exact command,
explain the blast radius, and let the user run it or approve it.

---

## Step 0 — Ask before you assume

Never start guessing. First pin down the situation with a few targeted questions. Ask only
what you can't already infer from the repo or the user's message:

1. **Where is it failing?** Local dev (`make start_backend`) or deployed (Container Apps via `azd`)?
2. **Which environment?** (`azd env list` shows them — confirm which one.)
3. **What's the symptom, concretely?** Error text, no audio, dropped call, high latency,
   wrong agent, silence, garbled speech, 4xx/5xx, timeout?
4. **What changed recently?** New deploy, config edit, region, model, phone number, dependency bump?
5. **Reproducibility?** Every call or intermittent? A specific agent/scenario/number?
6. **What do you already have?** Logs, a `call_id`/correlation id, screenshots, the azd env values?

> If the user gives a vague report ("calls don't work"), ask for one concrete failing example
> (a `call_id`, a timestamp, the exact error) before diving in. One good example beats ten guesses.

---

## Triage map — symptom → likely layer

| Symptom | Start at | Key signals |
| --- | --- | --- |
| `azd up`/provision fails | Deploy & infra | preflight, providers, quota, TF state lock |
| Call never connects / webhook silent | Telephony (ACS) | webhook reachable, ACS conn string, devtunnel |
| Call connects, no/garbled transcript | STT | Speech key/region, streaming mode, audio format |
| Long pauses before agent replies | LLM | AOAI deployment, quota/429, token limits, streaming |
| No audio back / robotic / cut off | TTS | voice name, TTS pool, barge-in/VAD |
| Wrong agent or no handoff | Orchestration | scenario YAML, agent registry, handoff service |
| State lost / session resets | Redis/state | Redis reachability, MemoManager, worker affinity |
| Container unhealthy / restart loop | Runtime | readiness checks, env propagation, startup logs |

---

## Read-only diagnostic playbook

### Azure MCP (preferred fast path for deployed envs)

If an **Azure SRE-agent MCP server** is wired into this workspace, prefer its purpose-built
tools over hand-rolled CLI — they already know the ARTagent topology. Confirm they're available
first (don't assume; if no Azure MCP is connected, fall back to the `az`/`curl` commands below):

| Tool | Use it for | Read-only? |
| --- | --- | --- |
| `check_deployment_health` | One-shot health of all services + deps for `dev`/`staging`/`prod` | ✅ yes |
| `analyze_deployment_logs` | App Insights logs by `service` (`rtaudio-server`/`rtaudio-client`/`all`), `severity`, `time_range` | ✅ yes |
| `analyze_pool_metrics` | STT/TTS warm-pool utilization & exhaustion risk (`time_range`, `alert_threshold`) | ✅ yes |
| `analyze_voice_channel_security` | WebSocket auth / rate-limit / pool security scan | ⚠️ **see warning** |

> **⚠️ `analyze_voice_channel_security` defaults `auto_create_issues: true`** — that **creates
> GitHub issues** (a write action). Under these guardrails you must call it with
> `auto_create_issues: false`, or get explicit user approval before letting it file issues.

Generic Azure MCP servers (resource lookup, `az`-equivalent, App Insights KQL) are fine too —
use only their **read** operations (`get`/`list`/`show`/`query`). Never invoke create/update/delete
MCP operations as part of diagnosis. If you need historical KQL/latency analysis, hand off to the
`observability-insights` skill.

### A. Local dev

```bash
# Is the backend up and what does it think is healthy?
curl -s http://localhost:8010/api/v1/health        | jq .
curl -s http://localhost:8010/api/v1/readiness     | jq '{status, checks}'
curl -s http://localhost:8010/api/v1/pools         | jq .
curl -s http://localhost:8010/api/v1/metrics/summary | jq .

# Port already taken? (inspect only — do NOT kill without asking)
lsof -iTCP:8010 -sTCP:LISTEN -n -P

# What config does the app actually see? (mask before sharing)
azd env get-values 2>/dev/null | sed -E 's/(accesskey|key|password|secret)=[^;]*/\1=***/gi'
```

### B. Deployed (Container Apps)

```bash
# Resolve the deployed backend from azd artifacts
azd env select <env>
BACKEND="https://$(azd env get-value BACKEND_CONTAINER_APP_FQDN)"

# Health across all dependencies (read-only)
curl -s --max-time 10 "$BACKEND/api/v1/readiness" | jq '{status, checks}'

# Or run the bundled script
./devops/scripts/quick_health_check.sh <env>

# Live + recent logs (read-only)
az containerapp logs show --name <app> --resource-group <rg> --follow      # tail
az containerapp logs show --name <app> --resource-group <rg> --tail 200    # snapshot
az containerapp revision list --name <app> --resource-group <rg> -o table  # which revision is live
```

### C. Per-layer probes

```bash
# Redis / state
make test_redis_connection          # connectivity only
make connect_redis                  # interactive inspect (read keys; don't FLUSH)

# App Config (what runtime values resolve to)
make show_appconfig
make show_appconfig_acs

# Azure OpenAI quota / 429 cause (read-only)
az cognitiveservices account deployment list -g <rg> -n <openai-account> -o table
az cognitiveservices usage list -l <region> -o json \
  | jq -r '.[] | select(.name.value | startswith("OpenAI.")) | "\(.name.value)\t\(.currentValue)/\(.limit)"'
```

When the problem needs **historical traces, latency percentiles, or a call timeline** across
the deployed stack, switch to the **`observability-insights`** skill — it builds the wider
picture from Azure Monitor / Log Analytics and renders it as KQL + diagrams.

---

## How to reason

1. **Confirm the layer** using the triage map and the health/readiness output (don't assume).
2. **Pull evidence** with read-only commands for that layer only — avoid shotgun-running everything.
3. **Correlate** by `call.connection.id` (ACS), `session.id` (browser), or `operation_Id` across logs, traces, and the user's report — App Insights has no `call_id` field.
4. **Form one hypothesis at a time**, name the evidence for and against it, and the gap.
5. If evidence is missing, **ask the user** for the specific artifact rather than assuming.

---

## Output format

End every investigation with this structure:

```markdown
### Diagnosis
- **Symptom:** <what the user observed>
- **Most likely cause:** <layer + root cause> (confidence: high/medium/low)
- **Evidence:** <commands run + key lines, secrets masked>
- **Still unknown:** <what you'd need to confirm>

### Recommended fix (you apply this)
1. <exact command or file edit, shown — not executed without approval>
2. <verification step to confirm it worked>

### If that doesn't resolve it
- <next hypothesis to test>
```

---

## Reference

- Quick fixes by error: [`TROUBLESHOOTING.md`](../../../TROUBLESHOOTING.md)
- Deploy flow & hooks: `deployment-guide` skill
- Wider context + visuals: `observability-insights` skill
- Azure MCP fast path (when connected): SRE-agent `check_deployment_health`, `analyze_deployment_logs`, `analyze_pool_metrics`, `analyze_voice_channel_security` (set `auto_create_issues: false`)
- Health endpoints: `apps/artagent/backend/api/v1/endpoints/health.py`
- Health script: `devops/scripts/quick_health_check.sh`
