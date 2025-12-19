# :material-rocket: Deployment Guide

!!! tip "First Time Deploying?"
    For your first deployment, use the [Quickstart Guide](../getting-started/quickstart.md) — it covers `azd up` in detail.
    
    This guide covers **advanced deployment scenarios** and **production considerations**.

---

## :material-format-list-checks: Deployment Options

| Scenario | Method | Guide |
|----------|--------|-------|
| **First deployment** | `azd up` | [Quickstart](../getting-started/quickstart.md) |
| **Production deployment** | azd + custom config | [Production Guide](production.md) |
| **CI/CD pipeline** | GitHub Actions | [CI/CD Guide](cicd.md) |
| **Direct Terraform** | `terraform apply` | [This page](#direct-terraform-deployment) |

---

## :material-cog: Infrastructure Overview

All deployments create these Azure resources:

=== "AI & Communication"
    - **Azure OpenAI** — GPT-4o for conversations
    - **Azure Speech Services** — STT/TTS with VoiceLive API
    - **Azure Communication Services** — Voice calls, telephony

=== "Data Layer"
    - **Cosmos DB** — MongoDB API for conversation history
    - **Redis Enterprise** — Session caching
    - **Blob Storage** — Audio files, media
    - **Key Vault** — Secrets management

=== "Compute & Config"
    - **Container Apps** — Frontend + backend hosting
    - **Container Registry** — Image storage
    - **App Configuration** — Centralized settings

=== "Monitoring"
    - **Application Insights** — Telemetry, traces
    - **Log Analytics** — Centralized logging

---

## :material-shield-check: Prerequisites

!!! warning "Permissions Required"
    | Permission | Purpose |
    |------------|---------|
    | **Contributor** | Create resources |
    | **User Access Administrator** | Assign managed identity roles |

See [Prerequisites](../getting-started/prerequisites.md) for tool installation.

---

## :material-terraform: Direct Terraform Deployment

For advanced users who prefer direct Terraform control:

### Step 1: Configure Backend

```bash
cd infra/terraform

# Set subscription
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
```

### Step 2: Configure Variables

Create `terraform.tfvars`:

```hcl
environment_name = "prod"
location         = "eastus"
principal_id     = "<your-principal-id>"

# Customize SKUs for production
redis_sku = "Enterprise_E10"
```

### Step 3: Deploy

```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

---

## :material-phone: Phone Number Setup

Phone numbers enable PSTN (telephone) calls. **Not required for browser-based voice.**

See [Phone Number Setup](phone-number-setup.md) for:

- Purchasing numbers via Portal or CLI
- Configuring Event Grid webhooks
- Testing inbound calls

---

## :material-cog-outline: Deployment Hooks & Configuration

The `azd up` command runs automated pre-provisioning and post-provisioning hooks that handle environment validation, setup, and configuration.

### Pre-Provisioning Hook

The pre-provisioning script (`devops/scripts/azd/preprovision.sh`) runs before Terraform and performs:

| Task | Description |
|------|-------------|
| **Tool Validation** | Checks az, azd, jq, docker are installed |
| **CLI Extensions** | Auto-installs quota, redisenterprise, cosmosdb-preview extensions |
| **Azure Auth** | Validates Azure CLI and azd authentication |
| **Subscription Config** | Sets ARM_SUBSCRIPTION_ID for Terraform |
| **Provider Registration** | Registers required Azure resource providers |
| **Regional Availability** | Checks if services are available in target region |
| **Quota Checks** | Validates OpenAI TPM quotas (opt-in for others) |
| **Remote State Setup** | Creates Azure Storage for Terraform state |

### Post-Provisioning Hook

The post-provisioning script (`devops/scripts/azd/postprovision.sh`) runs after Terraform and handles:

| Task | Description |
|------|-------------|
| **Cosmos DB Init** | Seeds database with initial data |
| **Phone Number Config** | Interactive prompt for ACS phone number |
| **URL Updates** | Configures backend/WebSocket URLs in App Configuration |
| **Settings Sync** | Syncs config/appconfig.json to Azure App Configuration |
| **Local Dev Setup** | Generates .env.local for local development |

### Environment Variables & Flags

Control deployment behavior with these environment variables:

#### Preflight Check Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `PREFLIGHT_DEEP_CHECKS` | `false` | Enable slow quota checks for Cosmos DB, Redis, Container Apps |
| `PREFLIGHT_LIVE_CHECKS` | `true` | Enable live Azure API checks (set `false` in CI for faster runs) |
| `CI` | - | Auto-detected; affects interactive prompts and default behaviors |

**Example: Enable deep quota checks**
```bash
PREFLIGHT_DEEP_CHECKS=true azd up
```

#### Terraform State Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_STATE` | `false` | Use local Terraform state instead of Azure Storage |
| `RS_STORAGE_ACCOUNT` | - | Existing storage account for remote state |
| `RS_RESOURCE_GROUP` | - | Resource group for remote state storage |
| `RS_CONTAINER_NAME` | - | Blob container for state files |
| `RS_STATE_KEY` | - | State file key (auto-set to `<env>.tfstate`) |
| `TF_INIT_SKIP_INTERACTIVE` | - | Skip interactive prompts during Terraform init |

**Example: Use local state for development**
```bash
azd env set LOCAL_STATE true
azd up
```

**Example: Use existing remote state**
```bash
azd env set RS_STORAGE_ACCOUNT "mystorageaccount"
azd env set RS_RESOURCE_GROUP "rg-tfstate"
azd env set RS_CONTAINER_NAME "tfstate"
azd env set RS_STATE_KEY "myenv.tfstate"
azd up
```

#### CI/CD Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `CI` | - | Set to `true` for CI/CD pipelines |
| `GITHUB_ACTIONS` | - | Auto-set in GitHub Actions |
| `AZD_SKIP_INTERACTIVE` | - | Skip all interactive prompts |
| `ACS_SOURCE_PHONE_NUMBER` | - | Pre-configure phone number (E.164 format) |

**Example: CI/CD deployment**
```bash
export CI=true
export TF_INIT_SKIP_INTERACTIVE=true
export ACS_SOURCE_PHONE_NUMBER="+18001234567"
azd up --no-prompt
```

---

## :material-arrow-right: Next Steps

| Topic | Guide |
|-------|-------|
| **Production hardening** | [Production Guide](production.md) |
| **CI/CD pipelines** | [CI/CD Guide](cicd.md) |
| **Phone configuration** | [Phone Number Setup](phone-number-setup.md) |
| **Monitoring setup** | [Monitoring Guide](../operations/monitoring.md) |
| **Security** | [Authentication](../security/authentication.md) |

---

## Advanced: Direct Terraform Deployment

For users who need more control over the deployment process, you can use Terraform directly instead of `azd`.

### Terraform Variables

Configure your `terraform.tfvars`:

```hcl
# Environment configuration
environment_name = "dev"
name            = "rtaudioagent"
location        = "eastus"

# Principal configuration (replace with your user ID)
principal_id   = "your-user-principal-id-here"
principal_type = "User"

# Azure Communication Services data location
acs_data_location = "United States"

# Authentication settings
disable_local_auth = true

# Redis Enterprise SKU (adjust based on your needs and regional availability)
redis_sku = "MemoryOptimized_M10"

# OpenAI model deployments with latest models
model_deployments = [
  {
    name     = "gpt-4-1-mini"
    version  = "2024-11-20"
    sku_name = "DataZoneStandard"
    capacity = 50
  },
  {
    name     = "o3-mini"
    version  = "2025-01-31"
    sku_name = "DataZoneStandard"
    capacity = 30
  }
]
```

### Deploy with Terraform

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

> **📖 For full Terraform details** including module structure, all variables, and outputs, see the [Infrastructure README](https://github.com/Azure-Samples/art-voice-agent-accelerator/tree/main/infra/README.md).

---

## Building Container Images

For custom image builds or manual deployments, build and push containers to Azure Container Registry:

```bash
# From repo root
ACR_NAME=$(terraform output -raw container_registry_name)   # or azd env get-value
ACR_LOGIN_SERVER="$ACR_NAME.azurecr.io"

az acr login --name $ACR_NAME

# Backend image
docker build \
  -f apps/artagent/backend/Dockerfile \
  -t $ACR_LOGIN_SERVER/voice-agent-backend:$(git rev-parse --short HEAD) \
  apps/artagent/backend
docker push $ACR_LOGIN_SERVER/voice-agent-backend:$(git rev-parse --short HEAD)

# Frontend image
docker build \
  -f apps/artagent/frontend/Dockerfile \
  -t $ACR_LOGIN_SERVER/voice-agent-frontend:$(git rev-parse --short HEAD) \
  apps/artagent/frontend
docker push $ACR_LOGIN_SERVER/voice-agent-frontend:$(git rev-parse --short HEAD)
```

Update your Terraform variables (`backend_image_tag`, `frontend_image_tag`) to match the tags you pushed.

---

## Connectivity Testing

Test your deployed application to ensure everything works correctly:

### Health Check

```bash
# Get backend URL
BACKEND_URL=$(azd env get-value BACKEND_CONTAINER_APP_URL)

# Test health endpoint
curl -I $BACKEND_URL/health
```

### WebSocket Testing

```bash
# Install wscat for WebSocket testing
npm install -g wscat

# Test WebSocket connection with the media endpoint
BACKEND_FQDN=$(azd env get-value BACKEND_CONTAINER_APP_FQDN)
wscat -c wss://$BACKEND_FQDN/api/v1/media/stream

# Test real-time communication endpoint
wscat -c wss://$BACKEND_FQDN/api/v1/stream
```

**Expected Behavior:**

- Health endpoint returns 200 OK with service status information
- WebSocket connection establishes successfully without errors
- Receives connection confirmation message with session details
- Use `Ctrl+C` to disconnect gracefully

> **Need help?** See our [Monitoring and Troubleshooting](#monitoring-and-troubleshooting) section below.

---

## Environment Management

### Switch Between Environments

```bash
# List all environments
azd env list

# Switch environment
azd env select <environment-name>

# View current variables
azd env get-values
```

### Update Configurations

```bash
# View all environment variables
azd env get-values

# Update location
azd env set AZURE_LOCATION <azure-region>

# Update phone number
azd env set ACS_SOURCE_PHONE_NUMBER <phone-number>

# Apply changes
azd deploy
```

### Environment Files for Local Development

Generate environment files from deployed infrastructure:

```bash
# Generate .env file from Terraform outputs
make generate_env_from_terraform

# Update with Key Vault secrets
make update_env_with_secrets

# View current environment file
make show_env_file
```

---

## Terraform State Configuration

### For Azure Developer CLI

Remote state is **automatically configured** by `azd` pre-provision hooks. No manual setup required.

### For Direct Terraform

See the [Infrastructure README](https://github.com/Azure-Samples/art-voice-agent-accelerator/tree/main/infra/README.md#terraform-backend-configuration) for detailed state configuration options:

- **BYOS**: Bring your own storage account via environment variables
- **Local State**: Set `LOCAL_STATE=true` for development/testing  
- **Manual backend.tf**: Configure your own backend settings

---

## Monitoring and Troubleshooting

### Deployment Monitoring

#### Azure Developer CLI
```bash
# Check deployment status
azd show

# View environment details
azd env get-values

# View deployment logs
azd deploy --debug
```

#### Direct Terraform
```bash
# Check Terraform state
terraform show

# View outputs
terraform output

# Monitor deployment
make monitor_backend_deployment
make monitor_frontend_deployment
```

### Container App Logs

```bash
# Real-time logs
az containerapp logs show \
    --name ca-voice-agent-backend \
    --resource-group $(azd env get-value AZURE_RESOURCE_GROUP) \
    --follow

# Recent logs (last 100 lines)
az containerapp logs show \
    --name ca-voice-agent-backend \
    --resource-group $(azd env get-value AZURE_RESOURCE_GROUP) \
    --tail 100
```

### Common Issues & Solutions

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **Terraform Init Fails** | Backend configuration errors, state lock issues | Check storage account permissions, verify backend.tf configuration, ensure unique state key |
| **Container Won't Start** | App unavailable, startup errors, health check failures | Check environment variables, verify managed identity permissions, review container logs |
| **Redis Connection Issues** | Cache connection timeouts, authentication failures | Verify Redis Enterprise configuration, check firewall rules, validate access policies |
| **Phone Number Issues** | ACS calling fails, webhook errors | Verify phone number is purchased and configured correctly, check webhook endpoints |
| **OpenAI Rate Limits** | API quota exceeded, throttling errors | Check deployment capacity, monitor usage in Azure Portal, consider scaling up |
| **WebSocket Connection Fails** | Connection refused, handshake errors, timeout issues | Check Container App ingress settings, test health endpoint, verify CORS configuration |
| **Live Voice API Issues** | Audio streaming problems, voice quality issues | Verify Azure Speech Live Voice API configuration, check network connectivity, review audio codecs |
| **Agent Routing Problems** | Incorrect model selection, tool call failures | Check agent configuration, verify model deployments, validate tool registry setup |

### Health Check Commands

```bash
# Basic health check with detailed output
BACKEND_URL=$(azd env get-value BACKEND_CONTAINER_APP_URL)
curl -v $BACKEND_URL/health

# Test specific agent endpoints
curl $BACKEND_URL/api/v1/agents/health
curl $BACKEND_URL/api/v1/media/health

# Test WebSocket connection with timeout
BACKEND_FQDN=$(azd env get-value BACKEND_CONTAINER_APP_FQDN)
timeout 10s wscat -c wss://$BACKEND_FQDN/api/v1/stream

# Check all service endpoints with status
echo "Backend: https://$BACKEND_FQDN"
echo "Frontend: https://$(azd env get-value FRONTEND_CONTAINER_APP_FQDN)"
echo "Health: $BACKEND_URL/health"
echo "API Docs: $BACKEND_URL/docs"
```

### Advanced Debugging

#### Enable Debug Logging
```bash
# Deploy with debug logging
azd deploy --debug

# Check container environment variables
az containerapp show \
    --name $(azd env get-value BACKEND_CONTAINER_APP_NAME) \
    --resource-group $(azd env get-value AZURE_RESOURCE_GROUP) \
    --query "properties.template.containers[0].env"
```

#### Verify RBAC Assignments
```bash
# Check managed identity assignments
az role assignment list \
    --assignee $(azd env get-value BACKEND_UAI_PRINCIPAL_ID) \
    --all \
    --output table

# Verify Key Vault access
az keyvault show \
    --name $(azd env get-value AZURE_KEY_VAULT_NAME) \
    --query "properties.accessPolicies"
```

> **Need more help?** For detailed troubleshooting steps, diagnostic commands, and solutions to common issues, see the comprehensive [Troubleshooting Guide](../operations/troubleshooting.md).

---

## Cleanup

Remove all deployed resources:

```bash
# Delete all resources (recommended)
azd down

# Delete specific environment
azd env delete <environment-name>

# Direct Terraform cleanup
cd infra/terraform
terraform destroy
```

---

## Advanced Configuration

### Container Apps Scaling Configuration

Update container app scaling in your `terraform.tfvars`:

```hcl
# Adjust based on expected load
container_apps_configuration = {
  backend = {
    min_replicas = 1
    max_replicas = 10
    cpu_limit    = "1.0"
    memory_limit = "2Gi"
  }
  frontend = {
    min_replicas = 1
    max_replicas = 5
    cpu_limit    = "0.5"
    memory_limit = "1Gi"
  }
}
```

### Model Configuration

Customize OpenAI model deployments for the latest supported models:

```hcl
model_deployments = [
  {
    name     = "gpt-4-1-mini"
    version  = "2024-11-20"
    sku_name = "DataZoneStandard"
    capacity = 100  # Increase for higher throughput
  },
  {
    name     = "o3-mini"
    version  = "2025-01-31"
    sku_name = "DataZoneStandard"
    capacity = 50   # Adjust based on reasoning workload
  }
]
```

### Security Hardening

For production deployments, consider:

```hcl
# Enhanced security settings
disable_local_auth = true
enable_redis_ha    = true
principal_type     = "ServicePrincipal"  # For CI/CD deployments

# Use higher Redis SKU for production
redis_sku = "Enterprise_E20"
```

### Multi-Region Deployment

Configure secondary regions for OpenAI and Cosmos DB:

```hcl
# Primary location
location = "eastus"

# Secondary locations for specific services
openai_location   = "westus2"
cosmosdb_location = "westus"
```

---

## Support & Next Steps

!!! tip "Additional Resources & Best Practices"
    Always test locally first to isolate issues before deploying to Azure. Use the comprehensive load testing framework in `tests/load/` to validate performance under realistic conditions.

    - **[Local Development Guide](../getting-started/local-development.md)** - Set up and test on your local machine
    - **[Troubleshooting Guide](../operations/troubleshooting.md)** - Comprehensive problem-solving guide
    - **[Repository Structure](../guides/repository-structure.md)** - Understand the codebase layout
    - **[Utilities & Services](../guides/utilities.md)** - Core infrastructure components
    - **[Terraform Infrastructure README](https://github.com/Azure-Samples/art-voice-agent-accelerator/tree/main/infra/terraform/README.md)** - Detailed infrastructure documentation
