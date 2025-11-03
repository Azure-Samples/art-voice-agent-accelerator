# :material-rocket: Deployment Guide

!!! success "Production-Ready Deployment"
    Comprehensive guide to deploy your Real-Time Voice Agent using Terraform infrastructure and Azure Container Apps.

## :material-cloud: Infrastructure Overview

This deployment uses **Terraform** as Infrastructure as Code with **Azure Container Apps** for hosting, providing:

=== "Core Services"
    - **:material-brain: AI Services**: Azure OpenAI (GPT-4 models) + Speech Services with Live Voice API
    - **:material-phone: Communication**: Azure Communication Services for real-time voice and telephony
    - **:material-database: Data Layer**: Cosmos DB (MongoDB API) + Redis Enterprise + Blob Storage
    - **:material-security: Security**: Managed Identity with role-based access control (RBAC)

=== "Platform & Monitoring"
    - **:material-docker: Hosting**: Azure Container Apps with auto-scaling and built-in TLS
    - **:material-chart-line: Monitoring**: Application Insights + Log Analytics with OpenTelemetry tracing
    - **:material-network: Networking**: Private endpoints and VNet integration for enhanced security

!!! info "Infrastructure Details"
    See the complete **[Terraform Infrastructure README](https://github.com/Azure-Samples/art-voice-agent-accelerator/tree/main/infra/terraform/README.md)** for resource specifications and configuration options.

## :material-format-list-checks: Prerequisites

!!! warning "Before You Begin"
    Ensure you have the following tools and permissions configured.

| Tool                                                                                             | Version          | Purpose                                |
| ------------------------------------------------------------------------------------------------ | ---------------- | -------------------------------------- |
| [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)                              | >=2.50.0         | Azure resource management              |
| [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | Latest           | Simplified deployment                  |
| [Terraform](https://developer.hashicorp.com/terraform/downloads)                                 | >=1.1.7, <2.0.0   | Infrastructure as Code                 |
| [Docker](https://docs.docker.com/get-docker/)                                                    | 20.10+           | Containerization and local testing     |
| Node.js                                                                                          | 18+              | Frontend development                   |
| Python                                                                                           | 3.11+            | Backend development                    |

### Azure Permissions

!!! danger "Required Permissions"
    Your Azure account needs these permissions in the target subscription:
    
    - **Owner** or **Contributor** + **User Access Administrator**
    - Permission to create managed identities and assign their roles
    - Permission to create service principals (only needed when enabling EasyAuth)
    - Permission to assign roles to resources

```bash title="Verify Azure permissions"
# Login to Azure
az login

# Check current subscription and permissions
az account show
az role assignment list --assignee $(az account show --query user.name -o tsv) --include-inherited
```

---

## :material-rocket: Quick Start with Azure Developer CLI

The easiest and **recommended** way to deploy this application is using the Azure Developer CLI with its Terraform backend.

### Step 1: Clone and Initialize
```bash
git clone https://github.com/Azure-Samples/art-voice-agent-accelerator.git
cd art-voice-agent-accelerator
azd auth login
azd init
```

### Step 2: Set Environment Variables
```bash
azd env new <environment-name>
azd env set AZURE_LOCATION "eastus"
azd env set AZURE_ENV_NAME "<environment-name>"
```

### Step 3: Deploy Infrastructure and Applications
```bash
azd up
```

**Total deployment time**: ~15 minutes for complete infrastructure and application deployment.

!!! info "Additional Resources"
    For more comprehensive guidance on development and operations:
    
    - **[Repository Structure](../guides/repository-structure.md)** - Understand the codebase layout
    - **[Utilities & Services](../guides/utilities.md)** - Core infrastructure components
    - **[Local Development Guide](../getting-started/local-development.md)** - Set up and test on your local machine

---

## Alternative: Direct Terraform Deployment

For users who prefer direct Terraform control or in environments where `azd` is not available:

### Step 1: Initialize Terraform Backend
```bash
# Set your Azure subscription
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
export AZURE_ENV_NAME="dev"  # or your preferred environment name

# Configure backend storage (see Backend Storage Configuration below)
cd infra/terraform
cp backend.tf.example backend.tf
# Edit backend.tf with your storage account details
```

### Step 2: Configure Variables
```bash
# Copy and customize terraform variables
cp terraform.tfvars.example terraform.tfvars

# Get your principal ID for RBAC assignments
PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)
echo "principal_id = \"$PRINCIPAL_ID\"" >> terraform.tfvars
```

### Step 3: Deploy Infrastructure
```bash
terraform init
terraform plan
terraform apply
```

### Step 4: Deploy your application

Review the deployment steps to deploy a container application after infrastructure is provisioned.

[Quickstart: Deploy your first container app with containerapp up](https://learn.microsoft.com/en-us/azure/container-apps/get-started?tabs=bash)

---

## Detailed Deployment Steps

### 1. Environment Configuration

#### Azure Developer CLI Setup
Configure your deployment environment with the required parameters:

```bash
# Create production environment
azd env new production

# Set core parameters
azd env set AZURE_LOCATION "eastus"
azd env set AZURE_ENV_NAME "production"

# Optional: Configure specific settings
azd env set AZURE_PRINCIPAL_ID $(az ad signed-in-user show --query id -o tsv)
```

#### Direct Terraform Setup
For direct Terraform deployments, configure your `terraform.tfvars`:

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

### 2. Terraform Infrastructure Provisioning

Deploy Azure resources using Terraform:
#### With Azure Developer CLI (Recommended)
```bash
# Full deployment (provisions infrastructure and deploys applications)
azd up

# Infrastructure only
azd provision
```
**What happens during `azd up`:**

1. **Pre-provision hooks** (configured in [`azure.yaml`](https://github.com/Azure-Samples/art-voice-agent-accelerator/blob/main/azure.yaml)) automatically set up Terraform backend storage
2. **Infrastructure provisioning** uses Terraform modules in [`infra/terraform/`](https://github.com/Azure-Samples/art-voice-agent-accelerator/blob/main/infra/terraform/)
3. **Post-provision hooks** configure phone numbers and generate environment files
4. **Application deployment** builds and deploys containers to Azure Container Apps

**Automation scripts** (located in [`devops/scripts/azd/`](https://github.com/Azure-Samples/art-voice-agent-accelerator/tree/main/devops/scripts/azd/)):

- [`preprovision.sh`](https://github.com/Azure-Samples/art-voice-agent-accelerator/blob/main/devops/scripts/azd/preprovision.sh) - Sets up Terraform backend storage and validates prerequisites
- [`postprovision.sh`](https://github.com/Azure-Samples/art-voice-agent-accelerator/blob/main/devops/scripts/azd/postprovision.sh) - Configures ACS phone numbers and generates environment files

See [`azure.yaml`](https://github.com/Azure-Samples/art-voice-agent-accelerator/blob/main/azure.yaml) for the complete hook configuration and script orchestration.

#### With Direct Terraform
```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

**Resources Created:**

- Azure Container Apps Environment with auto-scaling and ingress management
- Azure OpenAI Service (GPT-4.1-mini, O3-mini models) with intelligent model routing
- Azure Communication Services with Live Voice API integration
- Redis Enterprise Cache for session management and real-time data
- Key Vault with managed identity authentication and secure secret rotation
- Azure Container Registry for application image management
- Storage Account with blob containers for audio and conversation data
- Cosmos DB (MongoDB API) for persistent conversation history and agent memory
- Application Insights & Log Analytics with OpenTelemetry distributed tracing
- User-assigned managed identities with comprehensive RBAC permissions

> For detailed infrastructure information, see the [Terraform Infrastructure README](https://github.com/Azure-Samples/art-voice-agent-accelerator/tree/main/infra/terraform/README.md).

### 3. Application Deployment

Deploy your application code to the provisioned infrastructure:

#### With Azure Developer CLI
```bash
# Deploy applications to existing infrastructure
azd deploy
```

#### With Direct Terraform + Make
```bash
# Deploy both backend and frontend
make deploy_backend
make deploy_frontend

# Monitor deployment progress
make monitor_backend_deployment
make monitor_frontend_deployment
```

#### Build and Publish Container Images
Before running `make deploy_*` or Terraform application modules, build and push your containers to the Azure Container Registry created earlier.

```bash
# From repo root
ACR_NAME=$(terraform output -raw container_registry_name)   # or azd env get-value
ACR_LOGIN_SERVER="$ACR_NAME.azurecr.io"

az acr login --name $ACR_NAME

# Backend image (Dockerfile: apps/rtagent/backend/Dockerfile)
docker build \
  -f apps/rtagent/backend/Dockerfile \
  -t $ACR_LOGIN_SERVER/voice-agent-backend:$(git rev-parse --short HEAD) \
  apps/rtagent/backend
docker push $ACR_LOGIN_SERVER/voice-agent-backend:$(git rev-parse --short HEAD)

# Frontend image (Dockerfile: apps/rtagent/frontend/Dockerfile)
docker build \
  -f apps/rtagent/frontend/Dockerfile \
  -t $ACR_LOGIN_SERVER/voice-agent-frontend:$(git rev-parse --short HEAD) \
  apps/rtagent/frontend
docker push $ACR_LOGIN_SERVER/voice-agent-frontend:$(git rev-parse --short HEAD)
```

Update your Terraform variables (for example, `backend_image_tag` and `frontend_image_tag`) to match the tags you pushed so the Container Apps pick up the correct images.

Need a local integration pass before pushing? Use the root [`docker-compose.yml`](../../docker-compose.yml) to build and validate the services together:

```bash
docker compose build
docker compose up
```

Stop the compose stack when finished, publish fresh images, then re-run your Terraform or Make-based deployment.

### 4. Phone Number Configuration

Configure an Azure Communication Services phone number for voice calls:

#### Automatic via azd (Recommended)
The `azd up` command automatically handles phone number provisioning through post-provision hooks.

#### Manual Configuration
```bash
# Purchase a phone number using the helper script
make purchase_acs_phone_number

# Or set an existing number
azd env set ACS_SOURCE_PHONE_NUMBER "+1234567890"
```

#### Via Azure Portal
1. Navigate to your Azure Communication Services resource in the Azure Portal
2. Go to **Phone numbers** → **Get** in the left navigation menu
3. Select your country/region, number type (Geographic or Toll-free), and required features
4. Complete the purchase process and wait for number provisioning
5. Update your environment configuration with the purchased number
6. Configure webhook endpoints for incoming call handling

> **Detailed Guide**: [Get a phone number for Azure Communication Services](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/telephony/get-phone-number)


#### Configure Inbound Call Webhook
1. Open your Azure Communication Services resource in the Azure Portal.
2. Select **Events** → **+ Event Subscription**.
3. Choose **Inbound Call** as the event type.
4. Set the endpoint type to **Web Hook** and provide the callback URL:
   - Local development: `https://<your-devtunnel-host>/api/v1/calls/answer`
   - Deployed backend: `https://<backend-container-app-endpoint>/api/v1/calls/answer`
5. Complete the subscription wizard to enable webhook delivery for inbound calls.

> ***Optional: Secure Event Grid Delivery with Microsoft Entra ID***
>
>    If you need authenticated delivery, configure the Event Grid subscription to use Microsoft Entra ID for webhook validation. Follow the [Entra ID authentication guidance](https://learn.microsoft.com/azure/event-grid/authenticate-with-microsoft-entra-id) and grant your event handler the required app registration and role assignments before enabling the subscription.

### 5. Connectivity Testing

Test your deployed application to ensure everything works correctly:

#### Health Check
```bash
# Get backend URL
BACKEND_URL=$(azd env get-value BACKEND_CONTAINER_APP_URL)

# Test health endpoint
curl -I $BACKEND_URL/health
```

#### WebSocket Testing
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
- Real-time audio streaming capabilities are functional
- Use `Ctrl+C` to disconnect gracefully

> **Need help?** See our [troubleshooting section](#monitoring-and-troubleshooting) below.

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

## Backend Storage Configuration

### Terraform Remote State

#### For Azure Developer CLI Deployments
Remote state is automatically configured by the `azd` pre-provision hooks. No manual setup required.

#### For Direct Terraform Deployments

You have two options for managing Terraform state:

**Option 1: Bring Your Own Storage (BYOS)**
Set environment variables for your existing storage account:

```bash
export RS_STORAGE_ACCOUNT="yourstorageaccount"
export RS_CONTAINER_NAME="tfstate"
export RS_RESOURCE_GROUP="your-rg"
export RS_STATE_KEY="rtaudioagent.tfstate"
```

**Option 2: Configure backend.tf manually**
```bash
# Copy the example and configure
cp infra/terraform/backend.tf.example infra/terraform/backend.tf

# Edit backend.tf with your storage account details
terraform {
  backend "azurerm" {
    resource_group_name  = "your-terraform-state-rg"
    storage_account_name = "yourtfstateaccount"
    container_name       = "tfstate"
    key                  = "rtaudioagent.tfstate"
    use_azuread_auth     = true
    subscription_id      = "your-subscription-id"
  }
}
```

#### Create Storage Account for Terraform State

If you don't have a storage account for Terraform state:

```bash
# Set variables
RG_NAME="rg-terraform-state"
STORAGE_NAME="tfstate$(openssl rand -hex 4)"
LOCATION="eastus"

# Create resource group and storage account
az group create --name $RG_NAME --location $LOCATION
az storage account create \
  --name $STORAGE_NAME \
  --resource-group $RG_NAME \
  --location $LOCATION \
  --sku Standard_LRS \
  --encryption-services blob

# Create container
az storage container create \
  --name tfstate \
  --account-name $STORAGE_NAME \
  --auth-mode login

echo "Configure your backend.tf with:"
echo "  storage_account_name = \"$STORAGE_NAME\""
echo "  resource_group_name  = \"$RG_NAME\""
```

### Required Terraform Versions

```hcl
terraform {
  required_version = ">= 1.1.7, < 2.0.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    azapi = {
      source = "Azure/azapi"
    }
  }
}
```

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
