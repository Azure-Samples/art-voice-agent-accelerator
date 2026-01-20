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

For production deployments, all services should be placed behind private endpoints within a Virtual Network (VNet). The recommended architecture includes:

```
Internet → Application Gateway (WAF) → Container Apps (VNet integrated)
                                        ↓
                          Private Endpoints (all Azure services)
```

**Key Benefits:**
- **Security**: No public internet exposure for data and AI services
- **Compliance**: Meet regulatory requirements for data isolation
- **Performance**: Lower latency through Azure backbone network
- **Cost**: Reduced data egress charges

**Implementation Guide:**
- [Production Deployment Guide](../docs/deployment/production.md#network-perimeter)
- [Azure Well-Architected Framework - Networking](https://learn.microsoft.com/en-us/azure/well-architected/networking/)
- [Hub-and-Spoke Network Topology](https://learn.microsoft.com/en-us/azure/architecture/networking/architecture/hub-spoke)

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
