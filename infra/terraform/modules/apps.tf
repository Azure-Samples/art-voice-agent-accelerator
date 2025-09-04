# # ============================================================================
# # DATA SOURCES
# # ============================================================================

# # Get current Azure client configuration for tenant ID
# data "azurerm_client_config" "current" {}

# # ============================================================================
# # VARIABLES FOR EASYAUTH CONFIGURATION
# # - Docs:
# #   - Configure an app to trust a managed identity: https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-config-app-trust-managed-identity?tabs=microsoft-entra-admin-center%2Cdotnet#configure-a-federated-identity-credential-on-an-existing-application
# #   - Use Managed Identity of a Secret: https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad?tabs=workforce-configuration#use-a-managed-identity-instead-of-a-secret-preview
# # ============================================================================

# # Add new variables to variables.tf for EasyAuth configuration
# variable "frontend_app_registration_client_id" {
#   description = "Optional: Client ID of existing Azure AD app registration for frontend EasyAuth. If not provided, EasyAuth will be disabled."
#   type        = string
#   default     = null
#   sensitive   = true
# }

# variable "backend_app_registration_client_id" {
#   description = "Optional: Client ID of existing Azure AD app registration for backend EasyAuth. If not provided, EasyAuth will be disabled."
#   type        = string
#   default     = null
#   sensitive   = true
# }

# variable "tenant_id" {
#   description = "Azure AD tenant ID for EasyAuth configuration"
#   type        = string
#   default     = null
# }

# # ============================================================================
# # AZURE APP SERVICE PLANS (Separate for Frontend and Backend)
# # ============================================================================

# resource "azurerm_service_plan" "frontend" {
#   name                = "${local.resource_names.app_service_plan}-frontend"
#   resource_group_name = azurerm_resource_group.main.name
#   location            = azurerm_resource_group.main.location
#   os_type             = "Linux"
#   sku_name            = "B1" # Basic tier - adjust as needed

#   tags = local.tags
# }

# resource "azurerm_service_plan" "backend" {
#   name                = "${local.resource_names.app_service_plan}-backend"
#   resource_group_name = azurerm_resource_group.main.name
#   location            = azurerm_resource_group.main.location
#   os_type             = "Linux"
#   sku_name            = "B1" # Basic tier - adjust as needed

#   tags = local.tags
# }

# # ============================================================================
# # BACKEND LINUX APP SERVICE
# # ============================================================================

# resource "azurerm_linux_web_app" "backend" {
#   name                = "${var.name}-backend-app-${local.resource_token}"
#   resource_group_name = azurerm_resource_group.main.name
#   location            = azurerm_resource_group.main.location
#   service_plan_id     = azurerm_service_plan.backend.id

#   identity {
#     type         = "UserAssigned"
#     identity_ids = [azurerm_user_assigned_identity.backend.id]
#   }

#   logs {
#     application_logs {
#       file_system_level = "Information"
#     }
#     http_logs {
#       file_system {
#         retention_in_days = 7
#         retention_in_mb   = 35
#       }
#     }
#     detailed_error_messages = true
#     failed_request_tracing  = true
#   }

#   site_config {
#     application_stack {
#       python_version = "3.11"
#     }

#     always_on = true

#     # FastAPI startup command matching deployment script expectations
#     app_command_line = "python -m uvicorn apps.rtagent.backend.main:app --host 0.0.0.0 --port 8000"

#     # CORS configuration - will be updated after frontend is created
#     cors {
#       allowed_origins     = ["*"] # Temporary - will be updated via lifecycle
#       support_credentials = false # Must be false when allowed_origins includes "*"
#     }
#   }

#   app_settings = merge(
#     {
#       "BASE_URL" = var.backend_api_public_url != null ? var.backend_api_public_url : "https://<REPLACE_ME>"
#       # Azure Communication Services Configuration
#       "ACS_AUDIENCE"          = azapi_resource.acs.output.properties.immutableResourceId
#       "ACS_CONNECTION_STRING" = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=acs-connection-string)"
#       "ACS_ENDPOINT"          = "https://${azapi_resource.acs.output.properties.hostName}"
#       "ACS_STREAMING_MODE"    = "media"
#       "ACS_SOURCE_PHONE_NUMBER" = (
#         var.acs_source_phone_number != null && var.acs_source_phone_number != ""
#         ? var.acs_source_phone_number
#         : "TODO: Acquire an ACS phone number. See https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/telephony/get-phone-number?tabs=windows&pivots=platform-azp-new"
#       )
#       "PORT" = "8000"


#       # Regular environment variables
#       "AZURE_CLIENT_ID"                       = azurerm_user_assigned_identity.backend.client_id
#       "APPLICATIONINSIGHTS_CONNECTION_STRING" = azurerm_application_insights.main.connection_string

#       # Redis Configuration
#       "REDIS_HOST" = data.azapi_resource.redis_enterprise_fetched.output.properties.hostName
#       "REDIS_PORT" = tostring(var.redis_port)

#       # Azure Speech Services
#       "AZURE_SPEECH_ENDPOINT"        = "https://${azurerm_cognitive_account.speech.custom_subdomain_name}.cognitiveservices.azure.com/"
#       "AZURE_SPEECH_DOMAIN_ENDPOINT" = "https://${azurerm_cognitive_account.speech.custom_subdomain_name}.cognitiveservices.azure.com/"
#       "AZURE_SPEECH_RESOURCE_ID"     = azurerm_cognitive_account.speech.id
#       "AZURE_SPEECH_REGION"          = azurerm_cognitive_account.speech.location
#       "TTS_ENABLE_LOCAL_PLAYBACK"    = "false"

#       # Azure Cosmos DB
#       "AZURE_COSMOS_DATABASE_NAME"   = var.mongo_database_name
#       "AZURE_COSMOS_COLLECTION_NAME" = var.mongo_collection_name
#       "AZURE_COSMOS_CONNECTION_STRING" = replace(
#         data.azapi_resource.mongo_cluster_info.output.properties.connectionString,
#         "/mongodb\\+srv:\\/\\/[^@]+@([^?]+)\\?(.*)$/",
#         "mongodb+srv://$1?tls=true&authMechanism=MONGODB-OIDC&retrywrites=false&maxIdleTimeMS=120000"
#       )

#       # Azure OpenAI
#       "AZURE_OPENAI_ENDPOINT"                = azurerm_cognitive_account.openai.endpoint
#       "AZURE_OPENAI_CHAT_DEPLOYMENT_ID"      = "gpt-4o"
#       "AZURE_OPENAI_API_VERSION"             = "2025-01-01-preview"
#       "AZURE_OPENAI_CHAT_DEPLOYMENT_VERSION" = "2024-10-01-preview"

#       # Python-specific settings
#       "PYTHONPATH"                     = "/home/site/wwwroot"
#       "SCM_DO_BUILD_DURING_DEPLOYMENT" = "true"
#       "ENABLE_ORYX_BUILD"              = "true"
#       "ORYX_APP_TYPE"                  = "webapps"
#       "WEBSITES_PORT"                  = "8000"
#       }, var.backend_app_registration_client_id != null ? {
#       # Use EasyAuth with existing Azure AD app registration
#       "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID" = azurerm_user_assigned_identity.backend.client_id
#   } : {})

#   # Optional EasyAuth configuration for backend
#   dynamic "auth_settings_v2" {
#     for_each = var.backend_app_registration_client_id != null ? [1] : []

#     content {
#       auth_enabled           = true
#       require_authentication = false # Allow unauthenticated API calls for some endpoints
#       unauthenticated_action = "AllowAnonymous"
#       default_provider       = "azureactivedirectory"

#       # Excluded paths that don't require authentication
#       excluded_paths = [
#         "/health",
#         "/docs",
#         "/openapi.json",
#         "/favicon.ico",
#         "/.well-known/*"
#       ]

#       active_directory_v2 {
#         client_id                  = var.backend_app_registration_client_id
#         tenant_auth_endpoint       = "https://login.microsoftonline.com/${var.tenant_id != null ? var.tenant_id : data.azurerm_client_config.current.tenant_id}/v2.0"
#         client_secret_setting_name = "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"

#         allowed_audiences = [
#           var.backend_app_registration_client_id,
#           "api://${var.backend_app_registration_client_id}"
#         ]
#         # Allow frontend app registration and ACS managed identity to access backend
#         allowed_applications = concat(
#           var.frontend_app_registration_client_id != null ? [var.frontend_app_registration_client_id] : [],
#           try(azapi_resource.acs.output.identity.principalId, null) != null
#           ? [azapi_resource.acs.output.identity.clientId]
#           : []
#         )
#       }

#       login {
#         logout_endpoint                   = "/.auth/logout"
#         token_store_enabled               = true
#         preserve_url_fragments_for_logins = false
#       }
#     }
#   }

#   key_vault_reference_identity_id = azurerm_user_assigned_identity.backend.id

#   tags = merge(local.tags, {
#     "azd-service-name" = "rtaudio-server"
#   })

#   lifecycle {
#     ignore_changes = [
#       # app_settings,
#       site_config[0].app_command_line,
#       site_config[0].cors, # Ignore CORS changes to prevent cycles
#       tags
#     ]
#   }

#   depends_on = [
#     azurerm_key_vault_secret.acs_connection_string,
#     azurerm_role_assignment.keyvault_backend_secrets
#   ]
# }

# # ============================================================================
# # FRONTEND LINUX APP SERVICE
# # ============================================================================

# resource "azurerm_linux_web_app" "frontend" {
#   name                = "${var.name}-frontend-app-${local.resource_token}"
#   resource_group_name = azurerm_resource_group.main.name
#   location            = azurerm_resource_group.main.location
#   service_plan_id     = azurerm_service_plan.frontend.id

#   identity {
#     type         = "UserAssigned"
#     identity_ids = [azurerm_user_assigned_identity.frontend.id]
#   }

#   logs {
#     application_logs {
#       file_system_level = "Information"
#     }
#     http_logs {
#       file_system {
#         retention_in_days = 7
#         retention_in_mb   = 35
#       }
#     }
#     detailed_error_messages = true
#     failed_request_tracing  = true
#   }

#   site_config {
#     application_stack {
#       node_version = "22-lts" # Latest LTS Node.js for Vite
#     }

#     always_on = true

#     # Vite production build and serve command using the serve package
#     app_command_line = "npm run build && npm run start"

#     # CORS configuration - no circular dependency
#     cors {
#       allowed_origins     = ["*"] # Frontend doesn't need restricted CORS
#       support_credentials = false # Must be false when allowed_origins includes "*"
#     }

#     # Enable static file compression and proper MIME types
#     use_32_bit_worker = false
#     ftps_state        = "Disabled"
#     http2_enabled     = true
#   }

#   # Environment variables for Vite build and runtime
#   app_settings = merge({
#     # Build-time environment variables for Vite
#     "VITE_AZURE_REGION"     = azurerm_cognitive_account.speech.location
#     "VITE_BACKEND_BASE_URL" = var.backend_api_public_url != null ? var.backend_api_public_url : "https://${azurerm_linux_web_app.backend.default_hostname}"
#     "VITE_ALLOWED_HOSTS"    = "https://${azurerm_linux_web_app.backend.default_hostname}"

#     # Azure Client ID for managed identity authentication
#     "AZURE_CLIENT_ID" = azurerm_user_assigned_identity.frontend.client_id

#     # Application Insights for frontend monitoring
#     "APPLICATIONINSIGHTS_CONNECTION_STRING" = azurerm_application_insights.main.connection_string
#     "APPINSIGHTS_INSTRUMENTATIONKEY"        = azurerm_application_insights.main.instrumentation_key

#     # Node.js and Vite build configuration
#     "PORT"                           = "8080"
#     "NODE_ENV"                       = "production"
#     "NPM_CONFIG_PRODUCTION"          = "false" # Allow dev dependencies for build
#     "SCM_DO_BUILD_DURING_DEPLOYMENT" = "true"
#     "ENABLE_ORYX_BUILD"              = "true"
#     "ORYX_PLATFORM_NAME"             = "nodejs"

#     # Vite-specific optimizations
#     "VITE_NODE_ENV" = "production"
#     "BUILD_FLAGS"   = "--mode production"

#     # Website configuration for Vite SPA
#     "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
#     "WEBSITES_PORT"                       = "8080"
#     "WEBSITE_NODE_DEFAULT_VERSION"        = "22-lts"
#     "SCM_COMMAND_IDLE_TIMEOUT"            = "1800" # 30 minutes for build timeout

#     # Static file serving optimizations
#     "WEBSITE_STATIC_COMPRESSION"      = "1"
#     "WEBSITE_DYNAMIC_CACHE"           = "1"
#     "WEBSITE_ENABLE_SYNC_UPDATE_SITE" = "true"

#     # Always include Speech key for frontend when local auth is enabled
#     "VITE_AZURE_SPEECH_KEY" = var.disable_local_auth ? "" : "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=speech-key)"
#     }, var.disable_local_auth ? {
#     # Use managed identity for authentication
#     "VITE_USE_MANAGED_IDENTITY" = "true"
#     } : {
#     # Additional settings when local auth is enabled (keys are used)
#     }, var.frontend_app_registration_client_id != null ? {
#     # Use EasyAuth with existing Azure AD app registration
#     "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID" = azurerm_user_assigned_identity.frontend.client_id
#   } : {})

#   # Optional EasyAuth configuration for frontend
#   dynamic "auth_settings_v2" {
#     for_each = var.frontend_app_registration_client_id != null ? [1] : []

#     content {
#       auth_enabled           = true
#       require_authentication = true
#       unauthenticated_action = "RedirectToLoginPage"
#       default_provider       = "azureactivedirectory"

#       excluded_paths = [
#         "/health",
#         "/favicon.ico",
#         "/.well-known/*",
#         "/static/*"
#       ]

#       microsoft_v2 {
#         client_id                  = var.frontend_app_registration_client_id
#         client_secret_setting_name = "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"
#         allowed_audiences = [
#           var.frontend_app_registration_client_id,
#           "api://${var.frontend_app_registration_client_id}"
#         ]
#         login_scopes = [
#           "openid",
#           "profile",
#           "email"
#         ]
#       }

#       login {
#         logout_endpoint                   = "/.auth/logout"
#         token_store_enabled               = false # Better for SPAs
#         preserve_url_fragments_for_logins = true
#       }
#     }
#   }

#   # Key Vault references require the app service to have access
#   key_vault_reference_identity_id = azurerm_user_assigned_identity.frontend.id

#   tags = merge(local.tags, {
#     "azd-service-name" = "rtaudio-client"
#   })

#   lifecycle {
#     ignore_changes = [
#       app_settings,
#       site_config[0].app_command_line,
#       tags
#     ]
#   }

#   depends_on = [
#     azurerm_role_assignment.keyvault_frontend_secrets,
#     azurerm_linux_web_app.backend # Explicit dependency to ensure backend is created first
#   ]
# }

# # ============================================================================
# # UPDATE BACKEND CORS AFTER FRONTEND IS CREATED (Optional)
# # ============================================================================

# # This resource updates the backend CORS settings after frontend is created
# # to avoid circular dependency while still having proper CORS configuration
# resource "null_resource" "update_backend_cors" {
#   count = 1 # Only run if you want to update CORS after both services exist

#   provisioner "local-exec" {
#     command = <<-EOT
#       az webapp cors add --resource-group ${azurerm_resource_group.main.name} --name ${azurerm_linux_web_app.backend.name} --allowed-origins https://${azurerm_linux_web_app.frontend.default_hostname} https://${azapi_resource.acs.output.properties.hostName}
#     EOT
#   }

#   depends_on = [
#     azurerm_linux_web_app.frontend,
#     azurerm_linux_web_app.backend,
#     azapi_resource.acs
#   ]

#   triggers = {
#     frontend_hostname = azurerm_linux_web_app.frontend.default_hostname
#     backend_name      = azurerm_linux_web_app.backend.name
#   }
# }

# # ============================================================================
# # DIAGNOSTIC SETTINGS FOR APP SERVICES
# # ============================================================================

# # Diagnostic settings for frontend App Service
# resource "azurerm_monitor_diagnostic_setting" "frontend_app_service" {
#   name                       = "${azurerm_linux_web_app.frontend.name}-diagnostics"
#   target_resource_id         = azurerm_linux_web_app.frontend.id
#   log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

#   # App Service log categories for frontend monitoring
#   enabled_log {
#     category = "AppServiceConsoleLogs"
#   }

#   enabled_log {
#     category = "AppServiceHTTPLogs"
#   }

#   enabled_log {
#     category = "AppServicePlatformLogs"
#   }

#   enabled_log {
#     category = "AppServiceAppLogs"
#   }

#   # Enable authentication logs if EasyAuth is configured
#   dynamic "enabled_log" {
#     for_each = var.frontend_app_registration_client_id != null ? [1] : []
#     content {
#       category = "AppServiceAuthenticationLogs"
#     }
#   }
# }

# # Diagnostic settings for backend App Service
# resource "azurerm_monitor_diagnostic_setting" "backend_app_service" {
#   name                       = "${azurerm_linux_web_app.backend.name}-diagnostics"
#   target_resource_id         = azurerm_linux_web_app.backend.id
#   log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

#   # App Service log categories for backend monitoring
#   enabled_log {
#     category = "AppServiceConsoleLogs"
#   }

#   enabled_log {
#     category = "AppServiceHTTPLogs"
#   }

#   enabled_log {
#     category = "AppServicePlatformLogs"
#   }

#   enabled_log {
#     category = "AppServiceAppLogs"
#   }

#   # Enable authentication logs if EasyAuth is configured
#   dynamic "enabled_log" {
#     for_each = var.backend_app_registration_client_id != null ? [1] : []
#     content {
#       category = "AppServiceAuthenticationLogs"
#     }
#   }

#   # Metrics for performance monitoring
#   # metric {
#   #   category = "AllMetrics"
#   # }
# }

# # ============================================================================
# # RBAC ASSIGNMENTS FOR APP SERVICES
# # ============================================================================

# # Key Vault access for frontend app service
# resource "azurerm_role_assignment" "keyvault_frontend_secrets" {
#   scope                = azurerm_key_vault.main.id
#   role_definition_name = "Key Vault Secrets User"
#   principal_id         = azurerm_user_assigned_identity.frontend.principal_id
# }

# # ============================================================================
# # OUTPUTS FOR APP SERVICES
# # ============================================================================

# output "FRONTEND_APP_SERVICE_NAME" {
#   description = "Frontend App Service name"
#   value       = azurerm_linux_web_app.frontend.name
# }

# output "BACKEND_APP_SERVICE_NAME" {
#   description = "Backend App Service name"
#   value       = azurerm_linux_web_app.backend.name
# }

# output "FRONTEND_APP_SERVICE_URL" {
#   description = "Frontend App Service URL"
#   value       = "https://${azurerm_linux_web_app.frontend.default_hostname}"
# }

# output "BACKEND_APP_SERVICE_URL" {
#   description = "Backend App Service URL"
#   value       = "https://${azurerm_linux_web_app.backend.default_hostname}"
# }

# output "BACKEND_API_URL" {
#   description = "Backend API URL"
#   value       = var.backend_api_public_url != null ? var.backend_api_public_url : "https://${azurerm_linux_web_app.backend.default_hostname}"
# }