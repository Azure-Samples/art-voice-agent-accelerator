---
name: service-catalog
description: 'Service catalog and guided onboarding for the azd deployment. USE WHEN the user wants to discover, install, set up, or be walked through the deployable components (Azure OpenAI/AI Foundry, Speech, ACS/telephony, Cosmos DB, Redis, Container Apps, Key Vault, App Config, CardAPI MCP), asks "what gets deployed", "what services does this use", "help me onboard", "set up the deployment", "guide me through azd up", "which components do I need", or wants to enable optional pieces (phone number, EasyAuth, data seeding). Acts as the entry point an agent hooks into to assess current state, present the catalog, and onboard each component. DO NOT USE FOR: deep azd hook/flow internals or model-availability checks (use deployment-guide); runtime failure diagnosis (use troubleshoot); telemetry/log analysis (use observability-insights).'
---

# Service Catalog & Guided Onboarding

This skill is the **entry point an agent hooks into** to help a user discover and stand up the
components of the azd deployment. Treat the catalog below as a menu: assess what already exists,
present the relevant items, and onboard each one with concrete commands and a verification step.

> Pair with `deployment-guide` for hook/flow internals and model availability, `troubleshoot` for
> failure diagnosis, and `observability-insights` for telemetry. This skill is about **discovery and
> onboarding**, not debugging.

## Agent Playbook

Follow this loop. Do not dump the whole catalog unprompted — scope to the user's goal first.

1. **Assess state.** Run the discovery commands below to learn what is already provisioned
   (`azd env get-values`, resource group contents). Never assume a clean slate.
2. **Clarify intent.** Ask: *full deployment* (everything via `azd up`) vs *single component*
   (e.g. just enable a phone number, just seed CardAPI data, just turn on EasyAuth)?
3. **Present the relevant catalog rows** — purpose, dependencies, and what the user must decide
   (region, model, SKU, optional features).
4. **Onboard each item** using its row: run/show the command, then run its verification.
5. **Confirm + hand off.** Summarize what now exists and the logical next step (deploy, place a
   test call, open the frontend).

### Decision: full deploy vs targeted onboard

| User intent | Route |
|-------------|-------|
| "Deploy everything / get started" | Core path: `azd auth login` → `azd up` → run post-provision onboarding |
| "Add/change one thing" | Jump to that catalog row; skip provisioning that already succeeded |
| "What does this even use?" | Present the Infrastructure Catalog, then ask what to set up |

## Core Path (`azd up`)

```bash
azd auth login          # 1. Authenticate
azd env new <name>      # 2. (first time) create an environment
azd up                  # 3. preprovision → terraform apply → postprovision → deploy
```

- **preprovision** (`devops/scripts/azd/preprovision.sh`): preflight checks (tools/auth/providers/
  region/quota), Terraform backend, generates `main.tfvars.json` + provider config.
- **terraform apply**: creates the infrastructure rows below (`infra/terraform/*.tf`).
- **postprovision** (`devops/scripts/azd/postprovision.sh`): the onboarding catalog (data seed, phone,
  App Config, `.env.local`, EasyAuth).
- **deploy**: builds/pushes the three `services` from `azure.yaml`.

## Service Catalog (deployed apps)

Defined in `azure.yaml` under `services:`. Each is a Container App.

| Service | What it is | Source | Onboard / verify |
|---------|-----------|--------|------------------|
| `rtaudio-server` | FastAPI voice backend (orchestrators, agents, WS) | `apps/artagent/backend/Dockerfile` | `azd deploy rtaudio-server` → hit `/health` on the app URL |
| `rtaudio-client` | React frontend UI | `apps/artagent/frontend/Dockerfile` | `azd deploy rtaudio-client` → open the app URL in a browser |
| `cardapi-mcp` | CardAPI MCP tool server (sample backing tools) | `apps/cardapi/Dockerfile.mcp` | `azd deploy cardapi-mcp` → check MCP endpoint responds |

## Infrastructure Catalog (provisioned by Terraform)

Each row maps to a `infra/terraform/*.tf` file. Tunable inputs live in
`infra/terraform/params/main.tfvars.<env>.json` and `terraform.tfvars.example`.

| Component | Purpose | Terraform | Depends on | Key knobs |
|-----------|---------|-----------|-----------|-----------|
| Azure OpenAI / AI Foundry | GPT-4o for SpeechCascade LLM | `ai-foundry.tf` | region + model quota | `model_deployments`, region |
| AI Foundry (VoiceLive) | OpenAI Realtime for VoiceLive mode | `ai-foundry-vl.tf` | region availability | VoiceLive region/model |
| Speech Services | STT/TTS for cascade mode | `ai-services.tf*` | region | SKU (S0) |
| Communication Services | Telephony, WebSocket, WebRTC | `communication.tf` | Speech (cognitive link) | data location, phone number |
| Cosmos DB | Session/conversation persistence | `data.tf` | — | API (Mongo), autoscale RU/s |
| Storage Account | Audio files & prompts | `data.tf` | — | redundancy (LRS) |
| Redis Enterprise | Session cache / worker affinity | `redis.tf` | quota | SKU (E10) |
| Container Apps + Registry | Hosting for the 3 services | `containers.tf` | Log Analytics, identities | scaling, ACR tier |
| Key Vault | Secrets | `keyvault.tf` | — | RBAC mode |
| App Configuration | Dynamic runtime config | `appconfig.tf` | — | keys/labels |
| Core (LA, App Insights, UAI, RBAC) | Observability + identity + roles | `core.tf` | — | — |
| CardAPI resources | Backing infra for `cardapi-mcp` | `cardapi.tf` | Cosmos | — |

## Onboarding Catalog (post-provision tasks)

These run automatically in `postprovision.sh` but each is independently runnable / re-runnable.
Order matches `main()` in that script.

| # | Task | What it does | Re-run / enable | Optional? |
|---|------|--------------|-----------------|-----------|
| 1 | CardAPI data provisioning | Seeds Cosmos via `apps/cardapi/scripts/provision_data.py` | re-run postprovision | no (non-critical) |
| 2 | Phone number config | Provisions/links an ACS phone number (interactive) | `devops/scripts/azd/helpers/acs_phone_number_manager.py` | yes |
| 3 | App Config URL updates | Writes deployed service URLs into App Config | re-run postprovision | no |
| 4 | Sync App Config | `devops/scripts/azd/helpers/sync-appconfig.sh` | re-run helper | no |
| 5 | Generate `.env.local` | Local dev env from azd outputs | `devops/scripts/azd/helpers/local-dev-setup.sh` | no |
| 6 | EasyAuth (backend) | Entra auth on `rtaudio-server` (interactive) | `devops/scripts/azd/helpers/enable-easyauth.sh` | yes |
| 7 | EasyAuth (CardAPI MCP) | Entra auth on `cardapi-mcp` (interactive) | `devops/scripts/azd/helpers/enable-easyauth-cardapi-mcp.sh` | yes |

## Discovery Commands (assess current state)

Run these before onboarding so you build on what exists rather than re-provisioning.

```bash
# What azd already knows (env, endpoints, resource group, location)
azd env get-values

# Which services are deployed
azd show

# Resources actually present in the group
az resource list -g <resource-group> -o table

# Is a phone number already configured?
azd env get-value ACS_PHONE_NUMBER

# Is EasyAuth on?
azd env get-value EASYAUTH_ENABLED
```

## Prerequisites (gate before `azd up`)

Confirm before provisioning (enforced by `devops/scripts/azd/helpers/preflight-checks.sh`):

- Azure CLI `>=2.50.0`, authenticated (`az account show`)
- `azd` and Terraform `>=1.0` installed
- Contributor on the target subscription; required resource providers registered
- Sufficient Azure OpenAI + Speech quota in the chosen region (see `deployment-guide` for region/model checks)

## References

- `azure.yaml` — services + hooks
- `infra/terraform/README.md` — full component descriptions + RBAC
- `devops/scripts/azd/postprovision.sh` — onboarding task source of truth
- `docs/getting-started/quickstart.md` — first-time `azd up`
- Related skills: `deployment-guide`, `troubleshoot`, `observability-insights`
