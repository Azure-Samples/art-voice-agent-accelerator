# 🚀 GitHub Actions Deployment Automation

This directory contains GitHub Actions workflows for automated deployment of your Real-Time Audio Agent application to Azure using Azure Developer CLI (AZD).

## 🎯 Workflows

| Workflow | File | Description |
|----------|------|-------------|
| **Deploy to Azure** | [`deploy-azd-complete.yml`](./deploy-azd-complete.yml) | Main deployment workflow - use this one |
| **Deploy Documentation** | [`docs.yml`](./docs.yml) | Deploys static HTML docs to GitHub Pages |
| **Test AZD Hooks** | [`test-azd-hooks.yml`](./test-azd-hooks.yml) | Tests preprovision/postprovision hooks across platforms |
| **Live Evals (Staging)** | [`live-evals-staging.yml`](./live-evals-staging.yml) | Strict scenario and voice E2E gates after staging application deployment |
| **Weekly Voice Live roadmap** | [`voicelive-roadmap.md`](./voicelive-roadmap.md) | Monday documentation/code review; new integration proposals or timestamped updates to similar issues |
| **_template-deploy-azd** | [`_template-deploy-azd.yml`](./_template-deploy-azd.yml) | ⚠️ Internal template - do not run directly |

## Validate deployment-state access before deploying

The manual **Deploy to Azure** workflow supports `action=validate-state`,
including the `mosdev` environment. This mode opens only the runner's temporary
state-access rule, checks the existing state blob with Entra authentication,
initializes azd's Terraform cache, and runs `azd env refresh`. It does not run
Terraform plan/apply, build or deploy images, change application networking, or
update GitHub environment variables. The owned rule is cleaned up with
`always()`, including when validation fails.

Before enabling this path in GitHub:

1. Publish only reviewed changes on a separate branch. Do not push unfinished
   work to `staging` or `main`, which have deployment triggers. Keep internal
   network guides, IPAM exports, local `.azure` files, state, plans, and
   credentials out of the public repository.
2. Create the target GitHub environment with deployment-branch restrictions
   and the required approval policy. Configure an OIDC identity whose trust
   matches that repository/environment; prefer no client secret.
3. Configure its Azure authentication secrets and `RS_RESOURCE_GROUP`,
   `RS_STORAGE_ACCOUNT`, and `RS_CONTAINER_NAME` variables.
4. Set `TF_STATE_MANAGE_RUNNER_IP=true` and the existing
   `TF_STATE_NSP_PROFILE_ID`. Give the identity state-blob permissions,
   account metadata read access, and narrowly scoped NSP rule-management and
   association-read permissions as described below.
5. Select the reviewed branch, target environment, and `validate-state` action.
   Review its result before selecting a deployment action.

Raw Terraform/azd output is not printed or uploaded by the validation step.
Terraform's GitHub wrapper is disabled so child `terraform output` calls do
not publish sensitive state outputs as step outputs.

The legacy **Make Resources Public** step is disabled unless
`ALLOW_LEGACY_PUBLIC_NETWORKING=true` is explicitly configured. Even then it
refuses to run with NSP or Front Door. Deployment access must not reopen private
origins or bypass the state perimeter. Post-deployment CORS uses the Front Door
frontend hostname when enabled.

For `mosdev`, the checked-in parameters preserve `westus2`, workload profiles,
and the opted-in Front Door configuration. Review a full Terraform plan before
an apply, particularly when changing from a human deployer to a CI identity.
Environments enabling Front Door must also configure the environment secret
`FRONT_DOOR_ALLOWED_SERVICE_TAGS` with an approved JSON array of egress service
tags. Preview and execution pass it as `TF_VAR_front_door_allowed_service_tags`;
the default is empty and enabled deployments reject it. Keep organization-specific
allowlists out of checked-in parameter files.

Triggering this workflow from a VPN-connected laptop is supported without
direct laptop access to state. Running `azd` **on the laptop itself** is
different: its Storage-facing egress must match an approved NSP rule (or use a
private route). VPN membership alone does not grant that access.

## Weekly Voice Live roadmap

This [GitHub Agentic Workflow](https://github.github.com/gh-aw/) runs every Monday
at **09:17 UTC** (`17 9 * * 1`) and supports manual dispatch. It uses the native
repository agent
[`voicelive-roadmap`](../agents/voicelive-roadmap.agent.md), also selectable in
Copilot for interactive research. The agent is imported into the workflow prompt
and selected through `engine.agent`; its code-context map is versioned alongside
the application. Interactive invocations without safe-output tools produce
drafts only.

The starting source is the
[public Python Voice Live integration guide](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-voice-agent-integration?pivots=programming-language-python).
The agent follows relevant official overview, release, API and SDK links, then
traces candidate features through the **checked-out code and tests**, including
native Voice Live, SpeechCascade compatibility, agent YAML, Quick Tune, SDK pins,
and deployment prerequisites. Scheduled runs inspect the default branch, not
unmerged local work. Manual runs inspect the selected ref and cite its commit.

Each proposal includes evidence/source URLs, preview/GA status, SDK/API and
region/model/auth requirements, concrete code gaps, P0-P3 priority, S/M/L/XL
complexity, rough effort/confidence, implementation outline and acceptance criteria.
The first scan establishes baseline gaps; it does not label every feature new.

### Duplicate handling and publication boundaries

The agent searches open **and closed** issues, bodies and comments, feature
synonyms, and related PRs, including human-authored issues without automation
labels. It matches intended outcomes and runtime contracts, not only titles.
Visible `Feature ID: voicelive:<capability>` lines preserve capability identity
across renames and preview-to-GA transitions. HTML comment markers are not used
for this identity because safe-output sanitization removes agent-authored HTML.

A similar issue receives one **timestamped delta comment** only when material
evidence changes; the original description and maintainer decisions are preserved.
Unchanged scans do not post heartbeat comments. Closed/completed, rejected,
ambiguous, already implemented, and in-flight PR cases have explicit handling in
the agent profile; nothing is automatically reopened or assigned.

The research job has read-only GitHub permissions. Separate safe-output jobs can
create at most **five issues** and **ten comments** per run in this repository,
with title deduplication as an additional backstop. There are no code/PR, issue
state, label-editing or assignment outputs. Safe outputs sanitize content and
retain the framework's threat detection. The workflow serializes runs across
refs so a manual run cannot race the weekly scan.

`min-integrity: none` deliberately lets deduplication see outsider and bot issues
that the public-repository default would filter. All retrieved content is
untrusted; it cannot authorize commands or override instructions. This broadens
read visibility, not write permissions. Semantic similarity and material-change
assessment are model judgments, not a deterministic guarantee; review proposals.
The built-in `add-comment` handler can technically address PRs, but the agent is
explicitly limited to issue comments. There are no cross-repository write targets.

Existing issue/comment history is the durable baseline; there is no expiring
cache to cause repeat proposals. Missing source/search evidence is reported as
incomplete rather than "no changes"; affected writes are withheld. No weekly
summary or automatic failure issues are created. Review Actions logs, summaries,
safe-output previews and artifacts for outcomes, deferred items, and errors.

### Activation

1. Enable GitHub Issues and Actions in **AIappsGBBFactory/art-voice-agent-accelerator**.
2. Configure the repository Actions secret **`COPILOT_GITHUB_TOKEN`** with a
   fine-grained PAT belonging to a Copilot-enabled account and the account
   permission **Copilot Requests: Read**. Enter it through GitHub Settings or
   `gh secret set COPILOT_GITHUB_TOKEN --repo AIappsGBBFactory/art-voice-agent-accelerator`.
   Never put the value in a file, prompt, issue, or commit. The ordinary
   `GITHUB_TOKEN` supplies scoped repository reads and issue publication, not
   Copilot inference; the existing deployment `GH_PAT` is not reused.
3. Merge the agent, Markdown workflow and generated `voicelive-roadmap.lock.yml`
   onto the default branch. A local file or agent profile alone does **not**
   activate a schedule. GitHub Actions executes the generated lock file.
4. Run **Weekly Voice Live roadmap** from Actions with `dry_run` checked (the
   manual default). Review the issue/comment previews before a publishing run.
   Uncheck `dry_run` to publish manually; scheduled runs publish automatically.

```bash
gh workflow run voicelive-roadmap.lock.yml \
  --repo AIappsGBBFactory/art-voice-agent-accelerator --ref main -f dry_run=true
```

An organization with supported Copilot centralized billing can instead configure
`permissions.copilot-requests: write` and recompile, following the
[official authentication guide](https://github.github.com/gh-aw/reference/auth/).
This alternative is not enabled here: an existing Copilot subscription alone does
not prove organization inference billing is configured. No Azure credentials or
application dependencies are needed by the researcher.

GitHub may delay scheduled runs and disables schedules in inactive public
repositories after 60 days. Enable workflow failure notifications and inspect the
Actions history; absence of an issue does not prove that a scan completed.
Actions and Copilot usage/billing apply. Disable this workflow in Actions to pause.

### Maintaining the workflow

The checked-in lock file is generated with **gh-aw v0.88.7**. Do not edit it by
hand. Recompile after modifying the Markdown workflow or imported agent:

```bash
gh extension install github/gh-aw --pin v0.88.7  # if not already installed
gh aw compile voicelive-roadmap --validate --no-check-update
pytest tests/test_voicelive_roadmap_workflow.py -q
```

Commit the source, agent, generated lock, and `.github/aw/actions-lock.json`
together. Deliberately review compiler upgrades and generated action/container
pins. The offline regressions check the
schedule, staged default, read/write separation, output limits, agent binding,
and source/lock parity; they do not claim to prove model-level semantic matching.

## Staging live evaluations

After a successful staging `up` or `deploy`, the finalizer dispatches live
evaluations with `--ref staging`. Dispatch uses the job's `GITHUB_TOKEN` with
`actions: write`, not `GH_PAT`, and an API rejection fails the dispatch step.
Provision-only runs, teardown and PR previews do not dispatch evaluations.

The deployed backend URL, Container App name and resource group are passed as
workflow inputs. They take precedence over saved environment variables, so an
expired variable-persistence PAT cannot leave the readiness gate or WebSocket
driver targeting stale backend coordinates. Readiness polls the mounted
`/api/v1/health` endpoint. A manual staging dispatch can supply the same inputs
or use the saved environment variables.

`GH_PAT` is still used separately to persist environment variables. A `401 Bad
credentials` error there requires an operator to replace that secret; the job
token does not acquire environment-variable administration permissions. Other
Azure endpoint/authentication variables must remain configured correctly.

If a failed live-eval run says `Branch "main" is not allowed to deploy to staging`
and has no executed steps, inspect the workflow on the **default branch**.
GitHub reads `workflow_run` triggers from that branch, not the triggering staging
commit. An older default-branch copy must also have its obsolete `workflow_run`
trigger removed; updating staging alone does not retire it. Do not loosen the
staging environment protection or rerun the rejected main-branch job. Use a
staging `workflow_dispatch` run instead.

Live evaluations access Azure services and the decline scenario can send email.
The offline workflow regressions run their actual shell steps with stubbed
`gh`, `az` and `curl` commands:

```bash
AZURE_APPCONFIG_ENDPOINT='' pytest tests/test_live_eval_workflow.py
```

Headless scenarios run the streaming Cascade path with the production
`MemoManager` in explicit local-only mode. The retired evaluation
`MockMemoManager`/history/core-memory copies are not an alternate state contract.
Inline scenario definitions use `ScenarioConfig.from_dict`, including handoff
conditions, generic identity requirements and agent defaults. The recorder
forwards TTS callback metadata unchanged; its first-chunk timing measures
text-to-TTS dispatch, not synthesized audio arriving at a client. The separate
WebSocket jobs measure actual audio arrival. Recorded pipeline errors fail
functional validation even if a scenario has no other content assertions.
Native token counters are cumulative for an agent session. The recorder uses
per-turn deltas and captures source usage before a handoff resets the counters,
so later replies do not inherit earlier token charges or false verbosity
failures. Native counters and returned results are unchanged. Cost estimates
still use the final agent's model configuration for each turn; they are not a
per-model billing ledger for mixed-model handoffs. The email scenario explicitly
asks for the exact destination address while retaining its recipient assertions.
The banking test fixture explicitly applies its request-only conditions to both
declared routing forms and asks for the recalled decline code without supplying
the answer. This clarifies that fixture's policy; it does not change production
generic-routing permissions or remove the no-handoff/context assertions.
Headless sessions now warm and reuse their actual async OpenAI client, rather
than warming an unrelated synchronous client and opening a new transport each
turn. Owned clients and session overrides are cleaned up on completion or
cancellation; caller-provided clients remain borrowed. History is read for the
current agent after a handoff, not permanently for the session's starting agent.

The WebSocket driver waits for the native browser readiness event and greeting
quiescence, then observes replies concurrently with paced input. Its EOS anchor
is the end of user PCM, before endpointing silence. `turn_wall_ms` ends at the
last response frame, excluding the observer's quiet wait; it still includes
audio delivery and is not the headless model-processing metric. Typed transcript
snapshots replace prior content, deltas append, and final-turn envelopes close
their stream. Control/user messages cannot complete an unanswered turn. Missing
responses, timeouts and mid-turn closes stop the scenario instead of sending a
new utterance over unresolved output. No latency budgets are increased.
The wire driver selects the deployed industry scenario; it does not install
inline `session_config` or model overrides. Those functional/configuration
expectations are exercised by the headless suite. Voice jobs are audio and
latency smoke tests of the deployed configuration, not proof of inline routing.
Completion still uses a bounded quiet-window heuristic: audio frames have no
response identity, and an unusually delayed greeting or silent gap between
responses can limit attribution. Inspect server traces for ambiguous runs.

The blocking unit gate also covers async OpenAI invocation, Azure-host identity
detection, and deferred VoiceLive memory sync. Four legacy ACS authentication
expectations remain in `.github/quarantined-tests.txt`: implementing a different
credential priority or SMS managed identity needs an explicit behavior decision,
not a test-only assertion change.

The frontend gate also runs the Quick Tune Playwright suite with Firefox after
the unit tests and production build. These tests cover draft/Apply boundaries,
prompt context insertion, tool and voice catalogs, per-mode Foundry resources,
scenario graph editing, and responsive layouts against mocked APIs. Failure
screenshots are uploaded as `authoring-browser-results`. Real HTTP/Redis
registration tests are opt-in and are not enabled in this browser CI job.

## 🚀 Quick Start

### Deploy Everything
1. Go to **Actions** → **Deploy to Azure**
2. Click **Run workflow**
3. Select environment (`dev`/`staging`/`prod`) and action (`up`)

### Available Actions
| Action | Description |
|--------|-------------|
| `up` | Provision infrastructure + deploy application (default) |
| `provision` | Infrastructure only (Terraform) |
| `deploy` | Application only (requires existing infrastructure) |
| `down` | Destroy all resources |

## 🏗️ Workflow Architecture

The template workflow is organized into clean, separate jobs:

```
┌──────────────────────────────────────────────────────────────┐
│                    Deploy to Azure                           │
│                 (deploy-azd-complete.yml)                    │
└──────────────────────┬───────────────────────────────────────┘
                       │ calls
                       ▼
┌──────────────────────────────────────────────────────────────┐
│              _template-deploy-azd.yml                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────┐    ┌─────────────┐    ┌──────────┐             │
│  │  Setup  │───▶│   Execute   │───▶│ Finalize │             │
│  │   🔐    │    │ 🏗️📦🚀💥   │    │    📋    │             │
│  └─────────┘    └─────────────┘    └──────────┘             │
│       │                                                      │
│       │ (PRs only)                                          │
│       ▼                                                      │
│  ┌─────────┐                                                │
│  │ Preview │                                                │
│  │   📋    │                                                │
│  └─────────┘                                                │
└──────────────────────────────────────────────────────────────┘
```

### Jobs

| Job | Description |
|-----|-------------|
| **Setup** | Azure authentication (OIDC or Service Principal) |
| **Preview** | Runs `azd provision --preview` for PRs |
| **Execute** | Runs the selected azd command (`provision`/`deploy`/`up`/`down`) |
| **Finalize** | Updates GitHub environment variables, generates summary |

## 🔐 Authentication

### OIDC (Recommended)
Configure federated credentials in Azure AD:
```
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
```

### Service Principal (Fallback)
```
AZURE_CLIENT_ID
AZURE_CLIENT_SECRET
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
```

### Terraform state behind an enforced network security perimeter

GitHub-hosted runners can use a temporary, uniquely named inbound access rule on
an enforced Azure Network Security Perimeter (NSP) profile. Configure these
GitHub environment variables:

```text
TF_STATE_MANAGE_RUNNER_IP=true
TF_STATE_NSP_PROFILE_ID=/subscriptions/.../providers/Microsoft.Network/networkSecurityPerimeters/.../profiles/...
```

IP management defaults to `false`, which performs no network writes. An
optional `TF_STATE_RUNNER_IP` environment variable may supply one pre-approved
IPv4 address; CIDRs, IPv6 addresses, wildcards, and all-network ranges are
rejected. Without the override, the helper discovers the runner's public IPv4
over bounded HTTPS.

Before any preview, provision, deploy, up, or down operation that can initialize
Terraform, the reusable workflow:

1. Uses the explicit `AZURE_SUBSCRIPTION_ID`, `RS_RESOURCE_GROUP`,
   `RS_STORAGE_ACCOUNT`, `RS_CONTAINER_NAME`, and environment state key.
2. Validates that the profile is a full ARM ID in the same subscription, the
   state account has `publicNetworkAccess=SecuredByPerimeter`, and exactly one
   matching resource association is `Enforced`. It never changes the account
   posture, association mode, tags, firewall defaults, or other rules.
3. Reads existing inbound profile rules first. If an approved CIDR already
   covers the runner, it is reused and never removed. Otherwise, the helper
   creates one per-job rule containing only `<runner-ip>/32`, using the stable
   `Microsoft.Network/networkSecurityPerimeters/profiles/accessRules@2024-07-01`
   REST schema.
4. Writes a mode-`0600` lease under `RUNNER_TEMP` before mutation, adds only the
   exact created rule ID and ownership to it, and polls
   `az storage blob exists --auth-mode login`. An `exists:false` result fails
   rather than creating alternate or empty state.
5. Runs an `always()` cleanup step that deletes only the exact NSP rule ID owned
   by the lease. Cleanup is idempotent when open was skipped or no rule was
   added.

If `TF_STATE_NSP_PROFILE_ID` is unset, the helper retains compatibility with the
classic storage firewall and requires `publicNetworkAccess=Enabled` plus
`defaultAction=Deny`; it adds/removes a bare IPv4 rule because Storage rejects
literal `/31` and `/32` rules. A `SecuredByPerimeter` account is rejected unless
an explicit profile is configured.

The workflow identity needs **Storage Blob Data Contributor** on the state
container/account. NSP mode also needs narrowly scoped read access to the
configured profile and resource associations, plus access-rule read/write/delete
on that profile. Classic mode instead needs
`Microsoft.Storage/storageAccounts/read` and
`Microsoft.Storage/storageAccounts/write` on the state account. Neither mode
uses account keys or Shared Key authorization. See the official
[NSP CLI quickstart](https://learn.microsoft.com/azure/private-link/create-network-security-perimeter-cli)
and [2024-07-01 access-rule schema](https://learn.microsoft.com/azure/templates/microsoft.network/2024-07-01/networksecurityperimeters/profiles/accessrules).

The helper can also be exercised directly after Azure CLI login:

```bash
export TF_STATE_MANAGE_RUNNER_IP=true
export AZURE_SUBSCRIPTION_ID=...
export RS_RESOURCE_GROUP=...
export RS_STORAGE_ACCOUNT=...
export RS_CONTAINER_NAME=...
export RS_STATE_KEY=dev.tfstate
export TF_STATE_NSP_PROFILE_ID=/subscriptions/.../profiles/...

python devops/scripts/azd/helpers/terraform-state-access.py open \
  --lease-file .terraform-state-access-lease.json
# Run the state operation.
python devops/scripts/azd/helpers/terraform-state-access.py close \
  --lease-file .terraform-state-access-lease.json
```

GitHub's `always()` cleanup covers ordinary success, failure, and cancellation,
but no workflow can guarantee cleanup after abrupt runner loss. If that occurs,
use the failed run's lease/logged run identifier and runner IP to verify the
exact rule, then delete only the recorded NSP access-rule ID (or exact classic
IP rule). Never replace this with Learning mode, a broad GitHub/Azure address
range, or an all-networks fallback.

## ⚙️ Environment Variables

After deployment, these variables are automatically set on the GitHub environment:

| Variable | Description |
|----------|-------------|
| `AZURE_APPCONFIG_ENDPOINT` | Azure App Configuration endpoint |
| `AZURE_APPCONFIG_LABEL` | Configuration label for the environment |

These are used on subsequent deployments to maintain consistency.

## 🌍 Environments

| Environment | Trigger | Purpose |
|-------------|---------|---------|
| `dev` | Push to `main` | Development and testing |
| `staging` | Manual | Pre-production validation |
| `prod` | Manual | Production |

## 📋 Triggers

- **Push to `main`**: Auto-deploys to `dev`
- **Pull Request**: Preview infrastructure changes
- **Manual**: Run any action on any environment

## 🧪 Test AZD Hooks Workflow

The `test-azd-hooks.yml` workflow validates the AZD preprovision and postprovision hooks across multiple platforms.

### What It Tests

| Test | Description |
|------|-------------|
| **Lint** | ShellCheck analysis of all shell scripts |
| **Syntax Validation** | Bash syntax checking (`bash -n`) |
| **Logging Functions** | Verifies unified logging utilities work |
| **Location Resolution** | Tests tfvars-based location resolution |
| **Backend Configuration** | Tests Terraform backend.tf generation |
| **Regional Availability** | Validates Azure service availability checks |

### Platforms Tested

| Platform | Runner | Shell |
|----------|--------|-------|
| 🐧 Linux | `ubuntu-latest` | Bash |
| 🍎 macOS | `macos-latest` | Bash |
| 🪟 Windows | `windows-latest` | Git Bash |

### Triggers

- Push to `main` or `staging` (when hook scripts change)
- Pull requests (when hook scripts change)
- Manual dispatch with optional debug mode

### Running Locally

```bash
# Validate script syntax
bash -n devops/scripts/azd/preprovision.sh
bash -n devops/scripts/azd/postprovision.sh

# Run preflight checks
cd devops/scripts/azd/helpers
source preflight-checks.sh
run_preflight_checks

# Test with local state (no Azure required)
export LOCAL_STATE=true
export AZURE_ENV_NAME=local-test
export AZURE_LOCATION=eastus2
bash devops/scripts/azd/preprovision.sh terraform
```

## 🔗 Related Documentation

- [Azure Developer CLI Guide](../../docs/deployment/azd-guide.md)
- [Infrastructure Overview](../../docs/architecture/)
- [Troubleshooting](../../docs/operations/)

## 🛠️ Local Development

```bash
# Deploy everything
azd up --environment dev

# Infrastructure only
azd provision --environment dev

# Application only
azd deploy --environment dev

# Destroy resources
azd down --environment dev
```

### Prerequisites
- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Terraform](https://terraform.io/downloads)
- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)
- Docker for container builds
