# ============================================================================
# OUTPUTS FOR AZD INTEGRATION AND APPLICATION CONFIGURATION
# ============================================================================
output "ENVIRONMENT_NAME" {
  description = "Deployment environment name (e.g., dev, staging, prod)"
  value       = var.environment_name
}

output "AZURE_RESOURCE_GROUP" {
  description = "Azure Resource Group name"
  value       = azurerm_resource_group.main.name
}

output "AZURE_LOCATION" {
  description = "Azure region location"
  value       = azurerm_resource_group.main.location
}

# AI Services
output "AZURE_OPENAI_ENDPOINT" {
  description = "Azure OpenAI endpoint"
  value       = module.ai_foundry.openai_endpoint
}

output "AZURE_OPENAI_CHAT_DEPLOYMENT_ID" {
  description = "Azure OpenAI Chat Deployment ID. Default chat model to use if not specified by the agent config."
  value       = "gpt-4o"
}

output "AZURE_OPENAI_API_VERSION" {
  description = "Azure OpenAI API version"
  value       = "2025-01-01-preview"
}

output "AZURE_SPEECH_ENDPOINT" {
  description = "Azure Speech Services endpoint"
  value       = module.ai_foundry.endpoint
}

output "AZURE_SPEECH_RESOURCE_ID" {
  description = "Azure Speech Services resource ID"
  value       = module.ai_foundry.account_id
}

output "AZURE_SPEECH_REGION" {
  description = "Azure Speech Services location"
  value       = module.ai_foundry.location
}

# Communication Services
output "ACS_ENDPOINT" {
  description = "Azure Communication Services endpoint"
  value       = "https://${azapi_resource.acs.output.properties.hostName}"
}

output "ACS_IMMUTABLE_ID" {
  description = "Azure Communication Services immutable ID"
  value       = azapi_resource.acs.output.properties.immutableResourceId
}

output "ACS_RESOURCE_ID" {
  description = "Azure Communication Services resource ID"
  value       = azapi_resource.acs.id
}


# output "ACS_MANAGED_IDENTITY_PRINCIPAL_ID" {
#   description = "Azure Communication Services system-assigned managed identity principal ID"
#   value = data.azapi_resource.acs_identity_details.identity.principalId
# }

# Data Services
output "AZURE_STORAGE_ACCOUNT_NAME" {
  description = "Azure Storage Account name"
  value       = azurerm_storage_account.main.name
}

output "AZURE_STORAGE_BLOB_ENDPOINT" {
  description = "Azure Storage Blob endpoint"
  value       = azurerm_storage_account.main.primary_blob_endpoint
}

output "AZURE_STORAGE_CONTAINER_URL" {
  description = "Azure Storage Container URL"
  value       = "${azurerm_storage_account.main.primary_blob_endpoint}${azurerm_storage_container.audioagent.name}"
}

output "AZURE_COSMOS_DATABASE_NAME" {
  description = "Azure Cosmos DB database name"
  value       = var.mongo_database_name
}

output "AZURE_COSMOS_COLLECTION_NAME" {
  description = "Azure Cosmos DB collection name"
  value       = var.mongo_collection_name
}

output "AZURE_COSMOS_CONNECTION_STRING" {
  description = "Azure Cosmos DB connection string"
  value = replace(
    data.azapi_resource.mongo_cluster_info.output.properties.connectionString,
    "/mongodb\\+srv:\\/\\/[^@]+@([^?]+)\\?(.*)$/",
    "mongodb+srv://$1?tls=true&authMechanism=MONGODB-OIDC&retrywrites=false&maxIdleTimeMS=120000"
  )
}

# Redis
output "REDIS_HOSTNAME" {
  description = "Redis Enterprise hostname"
  value       = data.azapi_resource.redis_enterprise_fetched.output.properties.hostName
}

output "REDIS_PORT" {
  description = "Redis Enterprise port"
  value       = var.redis_port
}

# Key Vault
output "AZURE_KEY_VAULT_NAME" {
  description = "Azure Key Vault name"
  value       = azurerm_key_vault.main.name
}

output "AZURE_KEY_VAULT_ENDPOINT" {
  description = "Azure Key Vault endpoint"
  value       = azurerm_key_vault.main.vault_uri
}

# Managed Identities
output "BACKEND_UAI_CLIENT_ID" {
  description = "Backend User Assigned Identity Client ID"
  value       = azurerm_user_assigned_identity.backend.client_id
}

output "BACKEND_UAI_PRINCIPAL_ID" {
  description = "Backend User Assigned Identity Principal ID"
  value       = azurerm_user_assigned_identity.backend.principal_id
}

output "FRONTEND_UAI_CLIENT_ID" {
  description = "Frontend User Assigned Identity Client ID"
  value       = azurerm_user_assigned_identity.frontend.client_id
}

output "FRONTEND_UAI_PRINCIPAL_ID" {
  description = "Frontend User Assigned Identity Principal ID"
  value       = azurerm_user_assigned_identity.frontend.principal_id
}

# Container Registry
output "AZURE_CONTAINER_REGISTRY_ENDPOINT" {
  description = "Azure Container Registry endpoint"
  value       = azurerm_container_registry.main.login_server
}

# Monitoring
output "APPLICATIONINSIGHTS_CONNECTION_STRING" {
  description = "Application Insights connection string"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "LOG_ANALYTICS_WORKSPACE_ID" {
  description = "Log Analytics workspace ID"
  value       = azurerm_log_analytics_workspace.main.id
}

# Performance Configuration Outputs
output "AOAI_POOL_SIZE" {
  description = "Azure OpenAI pool size for performance optimization"
  value       = var.aoai_pool_size
}

output "TTS_POOL_SIZE" {
  description = "TTS pool size for concurrent session handling"
  value       = var.tts_pool_size
}

output "STT_POOL_SIZE" {
  description = "STT pool size for concurrent session handling"
  value       = var.stt_pool_size
}

output "CONTAINER_CPU_CORES" {
  description = "CPU cores allocated per container instance"
  value       = var.container_cpu_cores
}

output "CONTAINER_MEMORY_GB" {
  description = "Memory allocated per container instance"
  value       = var.container_memory_gb
}

output "CONTAINER_MIN_REPLICAS" {
  description = "Minimum container replicas for high availability"
  value       = var.container_app_min_replicas
}

output "CONTAINER_MAX_REPLICAS" {
  description = "Maximum container replicas for auto-scaling"
  value       = var.container_app_max_replicas
}

output "REDIS_SKU_OPTIMIZED" {
  description = "Redis Enterprise SKU for optimal performance"
  value       = var.redis_sku
}


output "ai_foundry_account_id" {
  description = "Resource ID of the AI Foundry account"
  value       = module.ai_foundry.account_id
}

output "ai_foundry_account_endpoint" {
  description = "Endpoint URI for the AI Foundry account"
  value       = module.ai_foundry.endpoint
}

output "ai_foundry_project_id" {
  description = "Resource ID of the AI Foundry project"
  value       = module.ai_foundry.project_id
}

output "ai_foundry_project_identity_principal_id" {
  description = "Managed identity principal ID assigned to the AI Foundry project"
  value       = module.ai_foundry.project_identity_principal_id
}
