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

## 🏗️ What Gets Created

```
┌─────────────────────────────────────────────────────────────────┐
│                   AZURE RESOURCES                                │
├──────────────────────┬──────────────────────────────────────────┤
│   AI & Voice         │   Azure OpenAI (GPT-4o)                  │
│                      │   Azure AI Speech (STT/TTS)              │
│                      │   Azure VoiceLive (real-time)            │
│                      │   Azure Communication Services           │
├──────────────────────┼──────────────────────────────────────────┤
│   Data & Storage     │   Cosmos DB (MongoDB API)                │
│                      │   Redis Enterprise (caching)             │
│                      │   Blob Storage (audio/media)             │
│                      │   Key Vault (secrets)                    │
├──────────────────────┼──────────────────────────────────────────┤
│   Compute            │   Container Apps (frontend + backend)    │
│                      │   Container Registry                     │
├──────────────────────┼──────────────────────────────────────────┤
│   Configuration      │   App Configuration (central config)     │
├──────────────────────┼──────────────────────────────────────────┤
│   Monitoring         │   Application Insights                   │
│                      │   Log Analytics Workspace                │
└──────────────────────┴──────────────────────────────────────────┘
```

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
