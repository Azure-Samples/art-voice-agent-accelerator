# 🗣️ Real-Time Audio Agent - Terraform Infrastructure

> **Currently only supports Public configuration for PoC purposes.**

## 📋 Table of Contents
- [🏗️ Architecture Overview](#️-architecture-overview)
- [🚀 Quick Start](#-quick-start)
- [🔧 Infrastructure Components](#-infrastructure-components)
- [🔐 Security & RBAC](#-security--rbac)
- [⚙️ Configuration](#️-configuration)
- [📚 Reference](#-reference)

## 🏗️ Architecture Overview

![Infrastructure Architecture](../docs/assets/MVPDeploy_infratf.png)

This Terraform configuration deploys a **production-ready** Real-Time Audio Agent infrastructure on Azure, featuring:

- 🤖 **AI Services**: Azure OpenAI (GPT-4o) + Speech Services for intelligent conversations
- 📞 **Communication**: Azure Communication Services for real-time voice/messaging
- 🗄️ **Data Layer**: Cosmos DB (MongoDB API) + Redis Enterprise + Blob Storage
- 🔐 **Security**: Managed Identity authentication with RBAC everywhere
- 📦 **Hosting**: Azure Container Apps with auto-scaling and monitoring


## 🚀 Quick Start

### Prerequisites
- **Azure CLI**: >=2.50.0 + authenticated
- **Terraform**: >=1.0 installed
- **Azure Permissions**: Contributor role on target subscription

### 🎯 One-Command Deployment

**Using Azure Developer CLI (Recommended)**
```bash
azd provision
```

**Using Terraform CLI**
```bash
cd infra-tf
terraform init && terraform apply
```

## 🔧 Infrastructure Components

### 🤖 AI & Communication Layer
| Service | Purpose | Configuration |
|---------|---------|---------------|
| **Azure OpenAI** | GPT-4o model for conversations | S0 tier, managed identity auth |
| **Speech Services** | Real-time STT/TTS processing | S0 tier, integrated with ACS |
| **Communication Services** | Voice calls, messaging, WebRTC | US data location, phone number ready, cognitive services linked |

### 🗄️ Data & Storage Layer
| Service | Purpose | Configuration |
|---------|---------|---------------|
| **Cosmos DB** | Session/conversation data | MongoDB API, autoscale (1000 RU/s) |
| **Redis Enterprise** | High-performance caching | E10 SKU, RBAC auth, clustering |
| **Storage Account** | Audio files & prompts | StorageV2, LRS, private containers |

### 🔐 Security & Identity Layer
| Service | Purpose | Configuration |
|---------|---------|---------------|
| **Managed Identities** | Service authentication | Backend + Frontend UAI |
| **Key Vault** | Secrets management | RBAC-enabled, automatic provisioning |
| **RBAC Assignments** | Least-privilege access | 8 service-specific roles |

### 📦 Container & Monitoring Layer
| Service | Purpose | Configuration |
|---------|---------|---------------|
| **Container Apps** | Serverless app hosting | Auto-scaling, Log Analytics integration |
| **Container Registry** | Image storage | Basic tier, managed identity access |
| **Application Insights** | Performance monitoring | Centralized telemetry |
| **Diagnostic Settings** | Comprehensive logging | All ACS log categories enabled |

### 📊 Monitoring & Diagnostics

This infrastructure includes **comprehensive diagnostic settings** for Azure Communication Services, enabling:

#### 📞 Call Automation & Voice Monitoring
- **Real-time call operations**: API calls, media operations, streaming usage
- **Call quality metrics**: Media statistics, client operations, service outcomes
- **Call session data**: Summary logs with participant details and duration
- **Cognitive services integration**: Managed identity-based Speech Services linkage

#### 🎤 Recording & Compliance
- **Call recording operations**: Start, stop, pause, resume recording events
- **Recording metadata**: Duration, content type, format, end reasons
- **Closed captions**: Accessibility and transcription logging

#### 📈 Performance & Quality Assurance
- **Quality metrics**: Aggregated calling metrics in daily bins
- **Customer feedback**: Call survey data for experience insights
- **Media diagnostics**: Stream-level diagnostics for troubleshooting

#### 🔄 Omnichannel Communication
- **SMS operations**: Message send, receive, delivery status
- **Chat services**: Text-based customer interactions
- **Email services**: Send operations, delivery status, user engagement

#### 🔐 Security & Infrastructure
- **Authentication events**: Security and access monitoring
- **Usage analytics**: Billing and capacity planning data
- **Routing intelligence**: Job router operations for smart call distribution

All logs are centralized in **Log Analytics** for:
- Real-time monitoring and alerting
- Historical analysis and reporting  
- Integration with Azure Monitor dashboards
- Custom query capabilities for business insights

### 🔗 Cognitive Services Integration

This infrastructure implements **seamless integration** between Azure Communication Services and Speech Services for real-time transcription:

#### 🔐 Managed Identity Authentication
- **System-assigned managed identity** enabled on Communication Services
- **Automatic credential management** - no API keys required
- **Role-based access control** with "Cognitive Services User" role
- **Production-ready security** following Azure best practices

#### 🌐 Domain-Based Endpoints
- **Custom domain endpoint** for Speech Services integration
- **Consistent performance** across Azure regions
- **Automatic failover support** for high availability
- **Optimized routing** for real-time audio workloads

#### 🎤 Real-Time Transcription Features
- **Live speech-to-text** during active calls
- **Multi-language support** for global call centers
- **Low-latency processing** for responsive interactions
- **Seamless integration** with Call Automation APIs

#### 📋 Configuration Details
```bash
# Speech Service Domain Endpoint (used by ACS)
AZURE_SPEECH_DOMAIN_ENDPOINT="https://{custom-subdomain}.cognitiveservices.azure.com/"

# Traditional Regional Endpoint (for direct SDK calls)
AZURE_SPEECH_ENDPOINT="https://{region}.api.cognitive.microsoft.com/"
```

The **domain endpoint** is specifically used for ACS integration, while the **regional endpoint** is available for direct Speech SDK operations.

## 🔐 Security & RBAC

### 🛡️ Security Features
- ✅ **Managed Identity First**: Zero stored credentials
- ✅ **RBAC Everywhere**: Least-privilege access control  
- ✅ **TLS Encryption**: All communication encrypted
- ✅ **Key Vault Integration**: Secure secret management

### 🔑 Service-Specific RBAC Matrix

| Service | Role | Identity | Access Level |
|---------|------|----------|-------------|
| Azure OpenAI | `Cognitive Services OpenAI User` | Backend + Frontend UAI | Model access |
| Speech Services | `Cognitive Services User` | Backend + Frontend UAI | STT/TTS |
| Storage Account | `Storage Blob Data Contributor` | Backend UAI | Read/write files |
| Key Vault | `Key Vault Secrets User` | Backend UAI | Runtime secrets |
| Container Registry | `AcrPull` | Backend + Frontend UAI | Image access |
| Redis Enterprise | `Custom Access Policy` | Backend UAI | Cache operations |

## ⚙️ Configuration

### 🔧 Terraform Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|:--------:|
| `environment_name` | Environment identifier | - | ✅ |
| `location` | Azure region | - | ✅ |
| `name` | Application base name | `rtaudioagent` | |
| `disable_local_auth` | Use managed identity only | `true` | |
| `openai_models` | Model deployments | `[gpt-4o]` | |
| `redis_sku` | Redis Enterprise SKU | `MemoryOptimized_M10` | |

### 🚀 Container Apps Deployment

**Using azd (Automatic)**
```bash
azd deploy
```

**Using Terraform outputs**
```bash
# Export key variables
export AZURE_OPENAI_ENDPOINT=$(terraform output -raw AZURE_OPENAI_ENDPOINT)
export AZURE_CLIENT_ID=$(terraform output -raw BACKEND_UAI_CLIENT_ID)
export ACS_ENDPOINT=$(terraform output -raw ACS_ENDPOINT)

# Deploy with managed identity
az containerapp create \
    --name backend-app \
    --resource-group $(terraform output -raw AZURE_RESOURCE_GROUP) \
    --environment $(terraform output -raw CONTAINER_APPS_ENVIRONMENT_NAME) \
    --user-assigned $(terraform output -raw BACKEND_UAI_CLIENT_ID)
```

## 📚 Reference

### 📋 Complete Resource List

<details>
<summary>🗂️ <strong>Terraform Documentation (Click to expand)</strong></summary>

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.0 |
| <a name="requirement_azuread"></a> [azuread](#requirement\_azuread) | ~> 3.0 |
| <a name="requirement_azurerm"></a> [azurerm](#requirement\_azurerm) | ~> 4.0 |
| <a name="requirement_random"></a> [random](#requirement\_random) | ~> 3.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_azapi"></a> [azapi](#provider\_azapi) | 2.5.0 |
| <a name="provider_azuread"></a> [azuread](#provider\_azuread) | 3.4.0 |
| <a name="provider_azurerm"></a> [azurerm](#provider\_azurerm) | 4.35.0 |
| <a name="provider_random"></a> [random](#provider\_random) | 3.7.2 |

## Resources
| Name | Type |
|------|------|
| [azapi_resource.backendRedisUser](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource) | resource |
| [azapi_resource.cosmos_backend_db_user](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource) | resource |
| [azapi_resource.cosmos_principal_user](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource) | resource |
| [azapi_resource.mongoCluster](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource) | resource |
| [azapi_resource.principalRedisUser](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource) | resource |
| [azapi_resource.redisDatabase](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource) | resource |
| [azapi_resource.redisEnterprise](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource) | resource |
| [azurerm_application_insights.main](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/application_insights) | resource |
| [azurerm_cognitive_account.openai](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/cognitive_account) | resource |
| [azurerm_cognitive_account.speech](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/cognitive_account) | resource |
| [azurerm_cognitive_deployment.openai_models](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/cognitive_deployment) | resource |
| [azurerm_communication_service.main](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/communication_service) | resource |
| [azurerm_container_app.backend](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/container_app) | resource |
| [azurerm_container_app.frontend](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/container_app) | resource |
| [azurerm_container_app_environment.main](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/container_app_environment) | resource |
| [azurerm_container_registry.main](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/container_registry) | resource |
| [azurerm_eventgrid_system_topic.acs](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/eventgrid_system_topic) | resource |
| [azurerm_key_vault.main](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault) | resource |
| [azurerm_key_vault_secret.acs_connection_string](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_key_vault_secret.acs_primary_key](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_key_vault_secret.cosmos_admin_password](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_key_vault_secret.cosmos_connection_string](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_key_vault_secret.cosmos_entra_connection_string](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_key_vault_secret.openai_key](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_key_vault_secret.speech_key](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_log_analytics_workspace.main](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace) | resource |
| [azurerm_resource_group.main](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group) | resource |
| [azurerm_role_assignment.acr_backend_pull](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.acr_frontend_pull](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.acr_principal_pull](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.acr_principal_push](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.keyvault_admin](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.keyvault_backend_secrets](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.openai_backend_user](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.openai_frontend_user](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.speech_backend_user](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.speech_frontend_user](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.storage_backend_contributor](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.storage_principal_contributor](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_role_assignment.storage_principal_reader](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment) | resource |
| [azurerm_storage_account.main](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_account) | resource |
| [azurerm_storage_container.audioagent](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_container) | resource |
| [azurerm_storage_container.prompt](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/storage_container) | resource |
| [azurerm_user_assigned_identity.backend](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/user_assigned_identity) | resource |
| [azurerm_user_assigned_identity.frontend](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/user_assigned_identity) | resource |
| [random_password.cosmos_admin](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/password) | resource |
| [random_string.resource_token](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string) | resource |
| [azapi_resource.mongo_cluster_info](https://registry.terraform.io/providers/Azure/azapi/latest/docs/data-sources/resource) | data source |
| [azapi_resource.redis_enterprise_fetched](https://registry.terraform.io/providers/Azure/azapi/latest/docs/data-sources/resource) | data source |
| [azuread_client_config.current](https://registry.terraform.io/providers/hashicorp/azuread/latest/docs/data-sources/client_config) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_environment_name"></a> [environment\_name](#input\_environment\_name) | Name of the environment that can be used as part of naming resource convention | `string` | n/a | yes |
| <a name="input_location"></a> [location](#input\_location) | Primary location for all resources | `string` | n/a | yes |
| <a name="input_acs_data_location"></a> [acs\_data\_location](#input\_acs\_data\_location) | Data location for Azure Communication Services | `string` | `"United States"` | no |
| <a name="input_disable_local_auth"></a> [disable\_local\_auth](#input\_disable\_local\_auth) | Disable local authentication and use Azure AD/managed identity only | `bool` | `true` | no |
| <a name="input_enable_redis_ha"></a> [enable\_redis\_ha](#input\_enable\_redis\_ha) | Enable Redis Enterprise High Availability | `bool` | `false` | no |
| <a name="input_mongo_collection_name"></a> [mongo\_collection\_name](#input\_mongo\_collection\_name) | Name of the MongoDB collection | `string` | `"audioagentcollection"` | no |
| <a name="input_mongo_database_name"></a> [mongo\_database\_name](#input\_mongo\_database\_name) | Name of the MongoDB database | `string` | `"audioagentdb"` | no |
| <a name="input_name"></a> [name](#input\_name) | Base name for the real-time audio agent application | `string` | `"rtaudioagent"` | no |
| <a name="input_openai_models"></a> [openai\_models](#input\_openai\_models) | Azure OpenAI model deployments | ```list(object({ name = string version = string sku_name = string capacity = number }))``` | ```[ { "capacity": 50, "name": "gpt-4o", "sku_name": "Standard", "version": "2024-11-20" } ]``` | no |
| <a name="input_principal_id"></a> [principal\_id](#input\_principal\_id) | Principal ID of the user or service principal to assign application roles | `string` | `null` | no |
| <a name="input_principal_type"></a> [principal\_type](#input\_principal\_type) | Type of principal (User or ServicePrincipal) | `string` | `"User"` | no |
| <a name="input_redis_port"></a> [redis\_port](#input\_redis\_port) | Port for Azure Managed Redis | `number` | `10000` | no |
| <a name="input_redis_sku"></a> [redis\_sku](#input\_redis\_sku) | SKU for Azure Managed Redis (Enterprise) | `string` | `"MemoryOptimized_M10"` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_ACS_ENDPOINT"></a> [ACS\_ENDPOINT](#output\_ACS\_ENDPOINT) | Azure Communication Services endpoint |
| <a name="output_ACS_RESOURCE_ID"></a> [ACS\_RESOURCE\_ID](#output\_ACS\_RESOURCE\_ID) | Azure Communication Services resource ID |
| <a name="output_ACS_DIAGNOSTICS_SETTING_ID"></a> [ACS\_DIAGNOSTICS\_SETTING\_ID](#output\_ACS\_DIAGNOSTICS\_SETTING\_ID) | Azure Communication Services diagnostic setting ID |
| <a name="output_ACS_MANAGED_IDENTITY_PRINCIPAL_ID"></a> [ACS\_MANAGED\_IDENTITY\_PRINCIPAL\_ID](#output\_ACS\_MANAGED\_IDENTITY\_PRINCIPAL\_ID) | Azure Communication Services system-assigned managed identity principal ID |
| <a name="output_ACS_COGNITIVE_SERVICES_CONNECTION_ID"></a> [ACS\_COGNITIVE\_SERVICES\_CONNECTION\_ID](#output\_ACS\_COGNITIVE\_SERVICES\_CONNECTION\_ID) | Azure Communication Services cognitive services connection ID |
| <a name="output_APPLICATIONINSIGHTS_CONNECTION_STRING"></a> [APPLICATIONINSIGHTS\_CONNECTION\_STRING](#output\_APPLICATIONINSIGHTS\_CONNECTION\_STRING) | Application Insights connection string |
| <a name="output_AZURE_CONTAINER_REGISTRY_ENDPOINT"></a> [AZURE\_CONTAINER\_REGISTRY\_ENDPOINT](#output\_AZURE\_CONTAINER\_REGISTRY\_ENDPOINT) | Azure Container Registry endpoint |
| <a name="output_AZURE_KEY_VAULT_ENDPOINT"></a> [AZURE\_KEY\_VAULT\_ENDPOINT](#output\_AZURE\_KEY\_VAULT\_ENDPOINT) | Azure Key Vault endpoint |
| <a name="output_AZURE_KEY_VAULT_NAME"></a> [AZURE\_KEY\_VAULT\_NAME](#output\_AZURE\_KEY\_VAULT\_NAME) | Azure Key Vault name |
| <a name="output_AZURE_LOCATION"></a> [AZURE\_LOCATION](#output\_AZURE\_LOCATION) | Azure region location |
| <a name="output_AZURE_OPENAI_API_VERSION"></a> [AZURE\_OPENAI\_API\_VERSION](#output\_AZURE\_OPENAI\_API\_VERSION) | Azure OpenAI API version |
| <a name="output_AZURE_OPENAI_CHAT_DEPLOYMENT_ID"></a> [AZURE\_OPENAI\_CHAT\_DEPLOYMENT\_ID](#output\_AZURE\_OPENAI\_CHAT\_DEPLOYMENT\_ID) | Azure OpenAI Chat Deployment ID |
| <a name="output_AZURE_OPENAI_ENDPOINT"></a> [AZURE\_OPENAI\_ENDPOINT](#output\_AZURE\_OPENAI\_ENDPOINT) | Azure OpenAI endpoint |
| <a name="output_AZURE_OPENAI_RESOURCE_ID"></a> [AZURE\_OPENAI\_RESOURCE\_ID](#output\_AZURE\_OPENAI\_RESOURCE\_ID) | Azure OpenAI resource ID |
| <a name="output_AZURE_RESOURCE_GROUP"></a> [AZURE\_RESOURCE\_GROUP](#output\_AZURE\_RESOURCE\_GROUP) | Azure Resource Group name |
| <a name="output_AZURE_SPEECH_ENDPOINT"></a> [AZURE\_SPEECH\_ENDPOINT](#output\_AZURE\_SPEECH\_ENDPOINT) | Azure Speech Services endpoint |
| <a name="output_AZURE_SPEECH_REGION"></a> [AZURE\_SPEECH\_REGION](#output\_AZURE\_SPEECH\_REGION) | Azure Speech Services region |
| <a name="output_AZURE_SPEECH_DOMAIN_ENDPOINT"></a> [AZURE\_SPEECH\_DOMAIN\_ENDPOINT](#output\_AZURE\_SPEECH\_DOMAIN\_ENDPOINT) | Azure Speech Services domain endpoint for ACS integration |
| <a name="output_AZURE_SPEECH_RESOURCE_ID"></a> [AZURE\_SPEECH\_RESOURCE\_ID](#output\_AZURE\_SPEECH\_RESOURCE\_ID) | Azure Speech Services resource ID |
| <a name="output_AZURE_STORAGE_ACCOUNT_NAME"></a> [AZURE\_STORAGE\_ACCOUNT\_NAME](#output\_AZURE\_STORAGE\_ACCOUNT\_NAME) | Azure Storage Account name |
| <a name="output_AZURE_STORAGE_BLOB_ENDPOINT"></a> [AZURE\_STORAGE\_BLOB\_ENDPOINT](#output\_AZURE\_STORAGE\_BLOB\_ENDPOINT) | Azure Storage Blob endpoint |
| <a name="output_AZURE_STORAGE_CONTAINER_URL"></a> [AZURE\_STORAGE\_CONTAINER\_URL](#output\_AZURE\_STORAGE\_CONTAINER\_URL) | Azure Storage Container URL |
| <a name="output_BACKEND_CONTAINER_APP_FQDN"></a> [BACKEND\_CONTAINER\_APP\_FQDN](#output\_BACKEND\_CONTAINER\_APP\_FQDN) | Backend Container App FQDN |
| <a name="output_BACKEND_CONTAINER_APP_NAME"></a> [BACKEND\_CONTAINER\_APP\_NAME](#output\_BACKEND\_CONTAINER\_APP\_NAME) | Backend Container App name |
| <a name="output_BACKEND_CONTAINER_APP_URL"></a> [BACKEND\_CONTAINER\_APP\_URL](#output\_BACKEND\_CONTAINER\_APP\_URL) | Backend Container App URL |
| <a name="output_BACKEND_UAI_CLIENT_ID"></a> [BACKEND\_UAI\_CLIENT\_ID](#output\_BACKEND\_UAI\_CLIENT\_ID) | Backend User Assigned Identity Client ID |
| <a name="output_BACKEND_UAI_PRINCIPAL_ID"></a> [BACKEND\_UAI\_PRINCIPAL\_ID](#output\_BACKEND\_UAI\_PRINCIPAL\_ID) | Backend User Assigned Identity Principal ID |
| <a name="output_BASE_URL"></a> [BASE\_URL](#output\_BASE\_URL) | Base URL for the application |
| <a name="output_CONTAINER_APPS_ENVIRONMENT_ID"></a> [CONTAINER\_APPS\_ENVIRONMENT\_ID](#output\_CONTAINER\_APPS\_ENVIRONMENT\_ID) | Container Apps Environment resource ID |
| <a name="output_CONTAINER_APPS_ENVIRONMENT_NAME"></a> [CONTAINER\_APPS\_ENVIRONMENT\_NAME](#output\_CONTAINER\_APPS\_ENVIRONMENT\_NAME) | Container Apps Environment name |
| <a name="output_FRONTEND_CONTAINER_APP_FQDN"></a> [FRONTEND\_CONTAINER\_APP\_FQDN](#output\_FRONTEND\_CONTAINER\_APP\_FQDN) | Frontend Container App FQDN |
| <a name="output_FRONTEND_CONTAINER_APP_NAME"></a> [FRONTEND\_CONTAINER\_APP\_NAME](#output\_FRONTEND\_CONTAINER\_APP\_NAME) | Frontend Container App name |
| <a name="output_FRONTEND_CONTAINER_APP_URL"></a> [FRONTEND\_CONTAINER\_APP\_URL](#output\_FRONTEND\_CONTAINER\_APP\_URL) | Frontend Container App URL |
| <a name="output_FRONTEND_UAI_CLIENT_ID"></a> [FRONTEND\_UAI\_CLIENT\_ID](#output\_FRONTEND\_UAI\_CLIENT\_ID) | Frontend User Assigned Identity Client ID |
| <a name="output_FRONTEND_UAI_PRINCIPAL_ID"></a> [FRONTEND\_UAI\_PRINCIPAL\_ID](#output\_FRONTEND\_UAI\_PRINCIPAL\_ID) | Frontend User Assigned Identity Principal ID |
| <a name="output_LOG_ANALYTICS_WORKSPACE_ID"></a> [LOG\_ANALYTICS\_WORKSPACE\_ID](#output\_LOG\_ANALYTICS\_WORKSPACE\_ID) | Log Analytics workspace ID |
| <a name="output_REDIS_HOSTNAME"></a> [REDIS\_HOSTNAME](#output\_REDIS\_HOSTNAME) | Redis Enterprise hostname |
| <a name="output_REDIS_PORT"></a> [REDIS\_PORT](#output\_REDIS\_PORT) | Redis Enterprise port |
<!-- END_TF_DOCS -->

</details>

---

### 🎯 Key Differences from Bicep
- **Simplified Networking**: Public endpoints for development (vs. private endpoints in Bicep)
- **RBAC Focus**: Enhanced managed identity assignments
- **Consolidated Resources**: Streamlined component organization
- **Developer Experience**: Optimized for quick iteration and testing

### 📞 Post-Deployment Steps
1. **📱 Phone Number**: Provision ACS phone number via Azure Portal
2. **🔧 App Configuration**: Deploy container apps with environment variables
3. **📊 Monitoring**: Configure Application Insights dashboards
4. **🧪 Testing**: Run health checks and load testing

### 🚨 Production Considerations
- **🔒 Private Endpoints**: Enable for production workloads
- **📈 Scaling**: Review SKUs for expected load
- **💰 Cost Optimization**: Monitor usage and adjust tiers
- **🛡️ Security**: Review RBAC assignments and network policies
