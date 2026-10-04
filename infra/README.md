# 🚀 Infrastructure Guide

> **For deployment instructions, see the [Quickstart Guide](../docs/getting-started/quickstart.md).**

This document covers Terraform infrastructure details for advanced users who need to customize or understand the underlying resources.

---

## 📋 Quick Commands

| Action | Command |
|--------|---------|
| Deploy everything | `azd up` |
| Infrastructure only | `azd provision` |
| Apps only | `azd deploy` |
| Tear down | `azd down --force --purge` |
| Switch environments | `azd env select <name>` |

---

## 🏗️ Infrastructure Resources

The following Azure resources are automatically deployed when you run `azd up`:

### AI & Voice Services

| Resource | Purpose | Private Networking Documentation |
|----------|---------|----------------------------------|
| **Azure OpenAI (AI Foundry)** | GPT-4o model deployments for conversational AI | [Configure Private Endpoints](https://learn.microsoft.com/en-us/azure/ai-services/cognitive-services-virtual-networks) |
| **Azure AI Speech Services** | Speech-to-Text (STT) and Text-to-Speech (TTS) | [Configure Private Endpoints](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-private-link) |
| **Azure VoiceLive (AI Foundry)** | Real-time voice-to-voice with gpt-4o-realtime (optional, based on region availability) | [Configure Private Endpoints](https://learn.microsoft.com/en-us/azure/ai-services/cognitive-services-virtual-networks) |
| **Azure Communication Services** | Call Automation and Media Streaming for telephony | [Configure Private Link](https://learn.microsoft.com/en-us/azure/communication-services/concepts/networking/private-link) |
| **Azure Email Communication Service** | Email domain management (managed domain) | Part of ACS private networking |

### Data & Storage Services

| Resource | Purpose | Private Networking Documentation |
|----------|---------|----------------------------------|
| **Cosmos DB (MongoDB API)** | Persistent storage for conversation history and agent state | [Configure Private Endpoints](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-configure-private-endpoints) |
| **Azure Cache for Redis (Enterprise)** | In-memory caching for session state and low-latency data access | [Configure Private Link](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-private-link) |
| **Azure Storage Account** | Blob storage for audio recordings, prompts, and media files | [Configure Private Endpoints](https://learn.microsoft.com/en-us/azure/storage/common/storage-private-endpoints) |
| **Azure Key Vault** | Secure storage for secrets, connection strings, and API keys | [Configure Private Link](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-service) |
| **Azure App Configuration** | Centralized configuration management for all application settings | [Configure Private Endpoints](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-private-endpoint) |

### Compute & Hosting Services

| Resource | Purpose | Private Networking Documentation |
|----------|---------|----------------------------------|
| **Azure Container Apps** | Hosts the FastAPI backend and React frontend applications | [VNet Integration](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom) |
| **Container Apps Environment** | Shared environment for container apps with logging integration | [Workload Profiles in VNets](https://learn.microsoft.com/en-us/azure/container-apps/workload-profiles-overview) |
| **Azure Container Registry** | Private Docker image repository for application containers | [Configure Private Link](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-link) |

### Monitoring & Configuration Services

| Resource | Purpose | Private Networking Documentation |
|----------|---------|----------------------------------|
| **Application Insights** | Distributed tracing, telemetry, and performance monitoring | [Private Link Scope](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/private-link-security) |
| **Log Analytics Workspace** | Centralized log aggregation and query engine | [Private Link Scope](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/private-link-security) |
| **Event Grid System Topic** | Event subscription for ACS incoming call notifications | [Configure Private Endpoints](https://learn.microsoft.com/en-us/azure/event-grid/configure-private-endpoints) |

### Identity & Access Management

| Resource | Purpose | Private Networking Documentation |
|----------|---------|----------------------------------|
| **User-Assigned Managed Identity (Backend)** | Identity for backend container app to access Azure resources | N/A - Uses Microsoft Entra ID endpoints |
| **User-Assigned Managed Identity (Frontend)** | Identity for frontend container app to access Azure resources | N/A - Uses Microsoft Entra ID endpoints |

### 🔐 Production Private Networking

The active `azure.yaml` deploys Terraform Container Apps. It does **not** deploy
Application Gateway. The gateway templates in `infra/bicep/deprecated/` are
legacy examples, not an additional hop in the Terraform deployment.

```
Corporate/VPN clients -> Front Door Premium + WAF -> Private Link -> Container Apps
ACS / Event Grid      -> exact authenticated routes --^
```

The optional configuration below closes public access to the **Container Apps
environment**. It does not make the separate AI, database, storage, Key Vault,
or App Configuration endpoints private. Those require separate network design.

**Implementation Guide:**
- [Production Deployment Guide](../docs/deployment/production.md#network-perimeter)
- [Azure Well-Architected Framework - Networking](https://learn.microsoft.com/en-us/azure/well-architected/networking/)
- [Hub-and-Spoke Network Topology](https://learn.microsoft.com/en-us/azure/architecture/networking/architecture/hub-spoke)

### Opt-in corporate/VPN access with Front Door Premium

`enable_front_door` defaults to `false`; existing deployments do not acquire a
Front Door profile or change their public URLs until explicitly enabled.
Premium Front Door, WAF, Private Link, and their traffic/logging incur additional
charges. No Application Gateway, customer VNet, NSG, or static VPN CIDR list is
needed for this direct Private Link integration.

For a **new** deployment:

```bash
# Replace this placeholder with service tags approved for your environment.
# Keep the actual allowlist in private deployment configuration.
export TF_VAR_front_door_allowed_service_tags='["<approved-service-tag>"]'
azd env set ENABLE_FRONT_DOOR true
azd env set CONTAINER_APP_WORKLOAD_PROFILES_ENABLED true
azd up
```

Alternatively, set `enable_front_door` and
`container_app_workload_profiles_enabled` to `true` in
`infra/terraform/params/main.tfvars.<environment>.json`. The preprovision hook
merges that file; explicit azd flag values override it. Do not edit generated
`main.tfvars.json`. Advanced parameters in the same params file:

```json
{
  "enable_front_door": true,
  "container_app_workload_profiles_enabled": true,
  "front_door_private_link_location": "eastus2"
}
```

The egress allowlist has no default. Set `TF_VAR_front_door_allowed_service_tags`
privately for local deployment, or configure the GitHub environment secret
`FRONT_DOOR_ALLOWED_SERVICE_TAGS` as a JSON array for CI. The workflow passes it
to Terraform without logging it. Terraform treats this input as sensitive.
An enabled Front Door module rejects an empty allowlist; omission never means
allowing public traffic. Do not commit organization-specific network identifiers
to parameter files. The placeholders above must be replaced, not deployed as-is.

Omit `front_door_private_link_location` to use the application's region. Verify
that it is an [AFD Private Link supported region](https://learn.microsoft.com/azure/frontdoor/private-link#region-availability).
A different region adds inter-region routing and can increase voice latency.

**Migration warning:** a legacy consumption-only Container Apps environment
cannot gain workload profiles in place. Terraform replaces the environment and
its apps when that setting changes. Use a new azd environment and planned
cutover, or review the replacement plan and accept downtime before provisioning.
Workload profiles still support Consumption billing; dedicated compute is not
required. Keep `CONTAINER_APP_WORKLOAD_PROFILES_ENABLED=true` if you later disable
Front Door, to avoid another environment replacement. Disabling Front Door
restores public origin access and is not a security-preserving rollback.
If a legacy Application Gateway exists outside this Terraform stack, migrate
its DNS/callback consumers explicitly before retiring it; these hooks do not
delete independently managed gateways.

For an upfront workload-profile migration before activating Front Door, leave
`enable_front_door=false` and set only the workload-profile flag. Supply
`container_images` (keys `frontend`, `backend`, `cardapi`) with the currently
deployed image references during the replacement. `ignore_changes` protects
image updates on existing apps, **not newly created replacement apps**; without
these overrides, Terraform uses its provisioning placeholder images. This also
avoids unintentionally deploying unrelated uncommitted application changes.
Update callback URLs and restore EasyAuth after the app FQDNs change, then
activate Front Door only with the authenticated-ingress backend image deployed.

**Enforcement and traffic paths:**

- Separate frontend, backend, and CardAPI endpoints share one Premium profile.
  Every endpoint has a Prevention-mode WAF policy covering `/*`. A negated
  `SocketAddr` / `ServiceTagMatch` custom Block rule admits the configured
  approved egress tags. The operator is defined by the public
  [Front Door WAF ARM schema](https://learn.microsoft.com/azure/templates/microsoft.network/2025-10-01/frontdoorwebapplicationfirewallpolicies).
  Confirm that the supplied service tags are supported for your environment;
  this accelerator does not supply organization-specific tags or infer approval.
- Origins use TLS with hostname validation and Private Link to the managed
  environment. Environment `public_network_access = Disabled` blocks direct
  `*.azurecontainerapps.io` bypasses. The postprovision hook approves only
  private endpoint requests matching this deployment's unpredictable marker
  and fails rather than opening a public fallback. Initial Front Door origin
  provisioning can take more than ten minutes before the approval step.
- Only backend `POST /api/v1/calls/answer`,
  `POST /api/v1/calls/callbacks`, and `GET /api/v1/media/stream` are exempt from
  the corporate network gate. They are **not** WAF Allow rules: managed
  inspection still applies. Browser voice, administrative APIs, and all other
  paths remain corporate-only.
- The backend requires signed ACS JWTs on callbacks and media establishment.
  Incoming-call Event Grid delivery uses a generated Key Vault-backed secret
  header and validates the event's ACS resource topic. Missing or invalid
  credentials fail closed, including WebSockets before acceptance. The
  postdeploy hook creates the IncomingCall subscription only after the actual
  app can authenticate and answer subscription validation, not against the
  provisioning placeholder image. Existing competing subscriptions must be
  reconciled before cutover to avoid double-answering calls.
- Terraform owns backend bootstrap/security environment variables, including
  `ENABLE_FRONT_DOOR`, `ACS_AUDIENCE`, `ACS_ARM_RESOURCE_ID`, and the
  `EVENT_GRID_WEBHOOK_SECRET` secret reference. Put other runtime customization
  in App Configuration rather than out-of-band edits to container env vars.
- Public URL outputs, frontend runtime configuration, backend CORS, and
  frontend EasyAuth redirects use Front Door. The `*_CONTAINER_APP_FQDN`
  outputs still identify the private origins. CardAPI's internal URL remains
  suitable for same-environment backend tool calls; `CARDAPI_PUBLIC_URL` is
  corporate-only. External noncorporate tool callers, Genesys, and other
  providers are not implicitly exempted by the ACS policy.

**Managed-rule exclusions:** the `Microsoft_DefaultRuleSet` 2.1 managed rules
stay in Prevention mode with two narrow exclusions for fields that legitimately
contain text the rules score as attacks:

- The `session_id` query argument is excluded from session-fixation rules
  943110 and 943120 only. The SPA and API sit on different Front Door hosts and
  the agent catalog and Quick Tune APIs pass the app's own session ID.
- The JSON body fields `prompt`, `greeting`, `return_greeting`, and
  `description` are excluded from the whole rule set. They carry Jinja prompt
  templates and natural-language greetings saved by Quick Tune and the Agent
  Builder; `{{ }}` / `{% %}` syntax and even plain greetings trip the
  SQLi/XSS/RCE signatures (for example 942200).

The backend renders those templates with Jinja's `ImmutableSandboxedEnvironment`,
so excluding them from WAF inspection does not open a template-injection path.
Everything else in those requests is still inspected. A WAF block returns 403
without CORS headers, so browsers report only `Failed to fetch`; if a save
fails that way, query `AzureDiagnostics` for
`Category == "FrontDoorWebApplicationFirewallLog"` and `action_s == "Block"`
to find the matched rule and field. Policy changes take about ten minutes to
propagate through Front Door.

**Latency and long calls:** do not stack Application Gateway behind Front Door.
Front Door is still an extra network hop; no fixed latency improvement or
penalty is promised. WAF examines the WebSocket handshake, not each audio frame.
All routes have caching disabled so Upgrade headers reach the origins.
Front Door documents a five-minute WebSocket idle timeout, a maximum
two-hour connection lifetime, and 3,000 concurrent WebSockets per profile
(contact Azure support for higher limits). Calls near two hours require a
separate reconnect/resume design; this option does not add seamless ACS
reconnection. HTTP origin response timeout is distinct from WebSocket lifetime.

Front Door access, health-probe, and WAF logs go to the existing Log Analytics
workspace. Before production cutover, compare WSS establishment time,
conversational p50/p95 latency, jitter, and disconnects with the direct baseline.
Also confirm corporate access succeeds, noncorporate browser/API traffic fails,
direct origin access fails, legitimate phone calls work, and forged callbacks
and media handshakes fail. Provisioning alone cannot establish these results.

References: [ACA Private Link integration](https://learn.microsoft.com/azure/container-apps/how-to-integrate-with-azure-front-door),
[Front Door WebSockets](https://learn.microsoft.com/azure/frontdoor/standard-premium/websocket),
[WAF ARM match conditions](https://learn.microsoft.com/azure/templates/microsoft.network/2025-10-01/frontdoorwebapplicationfirewallpolicies#matchcondition),
[ACS webhook/WebSocket authentication](https://learn.microsoft.com/azure/communication-services/how-tos/call-automation/secure-webhook-endpoint).

### State account policy exclusion and network repair

**Preferred for policy-managed environments: enforced NSP.** If governance
automation removes temporary exemption tags, use the policy-supported
`SecuredByPerimeter` mode rather than repeatedly reopening the public endpoint.
The bootstrap template is independent of Terraform's own backend, so it can
secure an existing state account without first accessing its state:

```bash
python3 devops/scripts/azd/helpers/configure-state-nsp.py \
  --subscription "<subscription-id>" \
  --resource-group "<state-resource-group>" \
  --account "<state-account>" \
  --vpn-cidr "<approved-public-vpn-cidr>"

azd env set TF_STATE_NSP_PROFILE_ID "<profileId returned by bootstrap>"
azd env set TF_STATE_ALLOW_PUBLIC_ACCESS false
```

Repeat `--vpn-cidr` for each approved IPAM public prefix. Do not substitute
private `10.x` addresses or infer an entire subnet from one observed address.
The template creates an inbound VPN rule and an **Enforced** association before
the helper switches the account to `SecuredByPerimeter`. It does not create or
move Terraform state, enable anonymous blob access, or use transition mode.

With `TF_STATE_NSP_PROFILE_ID` set, preprovision validates the association and
performs an Entra-authenticated state-blob check; it never applies the legacy
exemption or downgrades the perimeter. Run the same check independently:

```bash
python3 devops/scripts/azd/helpers/terraform-state-access.py validate \
  --subscription "<subscription-id>" --resource-group "<state-resource-group>" \
  --account "<state-account>" --container tfstate --blob "<environment>.tfstate" \
  --nsp-profile-id "<profileId>"
azd provision --preview
```

For GitHub-hosted runners, configure the GitHub environment variables
`TF_STATE_MANAGE_RUNNER_IP=true` and `TF_STATE_NSP_PROFILE_ID`. The deployment
workflow opens a uniquely named, single-IP NSP rule before state access and
removes only its owned rule in an `always()` cleanup step. Permanent VPN rules
are not removed. See the [workflow guide](../.github/workflows/README.md) for
permissions, existing-state prerequisites, and recovery after abrupt runner
loss. A bootstrap success proves the configured posture, **not** connectivity:
the blob check and the actual `azd`/pipeline operation must also succeed.

NSP access logs require a destination in the same perimeter. Do not associate
an existing application-wide Log Analytics workspace merely to diagnose state
access: doing so can affect unrelated telemetry. Corporate VPN and GitHub runner
traffic can have different egress addresses; validate the Storage-facing route
rather than assuming an Internet IP-discovery service reports that address.

**Legacy, explicitly approved public-firewall environments:** the following
tag-based repair remains opt-in. It is not used in NSP mode.

An existing remote-state configuration is not evidence that its storage account
is still reachable. `preprovision.sh` calls `helpers/initialize-terraform.sh`,
which can repair policy/network drift even when all `RS_*` settings already
exist. This repair is **opt-in** and affects only the selected state account:

```bash
azd env set TF_STATE_ALLOW_PUBLIC_ACCESS true
# Optional but recommended with split-tunnel VPNs: use the Azure-facing egress IP.
azd env set TF_STATE_ALLOWED_IP "<deployer-public-ipv4>"
azd hooks run preprovision
```

The helper merges `SecurityControl=Ignore` into the account's existing tags,
sets the firewall default to `Deny`, adds the single deployment IP, then sets
`publicNetworkAccess=Enabled`. Anonymous blob access remains disabled and the
Terraform backend continues to use Entra authentication. Existing IP rules,
private endpoints, and unrelated tags are preserved. Without an explicit IP,
the helper uses its public-IP discovery routine; a split-tunnel VPN may require
an explicit Azure-facing address instead.

The inspected `StorageAccount_PublicNetwork_Modify` definition provides
**`SecurityControl` (singular)** and **`Ignore`** as its exclusion defaults.
This is an account-scoped policy-supported exclusion, not a change to the policy
assignment. Use it only where your governance process permits that exclusion.
For a different approved policy configuration, set
`TF_STATE_EXCLUSION_TAG_NAME` / `TF_STATE_EXCLUSION_TAG_VALUE`; do not guess a
plural tag or change governance policy to make the script pass.

The tag and restricted public endpoint remain configured for subsequent
deployments. Setting `TF_STATE_ALLOW_PUBLIC_ACCESS=false` stops future repairs;
it does not remove the tag or close an already enabled endpoint. If the
policy still forces public access off, the hook fails explicitly without
falling back to an allow-all firewall. Use approved private connectivity in
that case.

Preflight and state repair also refuse to run against an Azure CLI subscription
that differs from the selected azd environment. They do not silently retarget
the environment when another terminal changes the shared CLI default. Use the
intended subscription/tenant in a separate CLI context for concurrent deployments.

### 📊 Resource Naming Conventions

All resources are deployed into a single resource group with consistent naming:

```
Resource Group: rg-{environment_name}-{resource_token}
Example: rg-dev-abc123xyz
```

Individual resources follow this pattern:
```
{service-prefix}-{name}-{resource_token}
```

### 🔍 Finding Your Resources

After deployment, you can find all resources in the Azure Portal:

1. Navigate to the resource group shown in `azd env get-values | grep AZURE_RESOURCE_GROUP`
2. Or use Azure CLI:
   ```bash
   az resource list --resource-group <your-resource-group> --output table
   ```

### 💡 Cost Considerations

The deployed infrastructure uses consumption-based and low-tier SKUs by default to minimize costs during development. For production workloads, consider:

- Upgrading to higher SKUs for better performance and SLA
- Enabling reserved capacity for predictable workloads
- Implementing auto-scaling policies
- See [Cost Optimization](../docs/deployment/production.md#cost-optimization) for detailed strategies

---

## ⚙️ Terraform Configuration

### Directory Structure

```
infra/terraform/
├── main.tf              # Main infrastructure, providers
├── backend.tf           # State backend (auto-generated)
├── variables.tf         # Variable definitions
├── outputs.tf           # Output values for azd
├── provider.conf.json   # Backend config (auto-generated)
├── params/              # Per-environment tfvars
│   └── main.tfvars.json
└── modules/             # Reusable modules
```

### Variable Sources

| Source | Purpose | Example |
|--------|---------|---------|
| `azd env set TF_VAR_*` | Dynamic values | `TF_VAR_location`, `TF_VAR_environment_name` |
| `params/main.tfvars.json` | Static per-env config | SKUs, feature flags |
| `variables.tf` defaults | Fallback values | Default regions |

### Terraform State

State is stored in Azure Storage (remote) by default. During `azd provision`, you'll be prompted:

- **(Y)es** — Auto-create storage account for remote state ✅ Recommended
- **(N)o** — Use local state (development only)
- **(C)ustom** — Bring your own storage account

To use local state:
```bash
azd env set LOCAL_STATE "true"
azd provision
```

### azd Lifecycle Hooks

| Script | When | What It Does |
|--------|------|--------------|
| `preprovision.sh` | Before Terraform | Sets up state storage, TF_VAR_* |
| `postprovision.sh` | After Terraform | Generates `.env.local` |
| `postdown.sh` | After `azd down` | Optional cleanup of remote state storage; reminds about `azd down --purge` |

---

## 🔧 Customization

### Change Resource SKUs

Edit `infra/terraform/params/main.tfvars.json`:

```json
{
  "redis_sku": "Enterprise_E10",
  "cosmosdb_throughput": 1000
}
```

### Add New Resources

1. Add Terraform code in `infra/terraform/`
2. Add outputs to `outputs.tf`
3. Reference outputs in `azure.yaml` if needed

### Multi-Environment

```bash
# Create production environment
azd env new prod
azd env set AZURE_LOCATION "westus2"
azd provision

# Switch between environments
azd env select dev
```

---

## 🔍 Debugging

```bash
# View azd environment
azd env get-values

# View Terraform state
cd infra/terraform && terraform show

# Check App Configuration
az appconfig kv list --endpoint $AZURE_APPCONFIG_ENDPOINT --auth-mode login
```

---

## 📚 Related Docs

| Topic | Link |
|-------|------|
| **Getting Started** | [Quickstart](../docs/getting-started/quickstart.md) |
| **Local Development** | [Local Dev Guide](../docs/getting-started/local-development.md) |
| **Production Deployment** | [Production Guide](../docs/deployment/production.md) |
| **Troubleshooting** | [Troubleshooting](../docs/operations/troubleshooting.md) |
