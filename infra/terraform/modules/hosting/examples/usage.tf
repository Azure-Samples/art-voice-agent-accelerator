# ============================================================================
# SAMPLE USAGE OF THE HOSTING MODULE
# This file demonstrates how to use the flexible hosting module that can
# deploy to either Container Apps or App Service based on the hosting_platform variable
# ============================================================================

# Example: Using the hosting module with containers (default)
module "hosting_containers" {
  source = "./modules/hosting"

  # Platform selection - defaults to "containers"
  hosting_platform = "containers" # or "webapps"

  # Basic configuration
  name                = "myapp"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  resource_token      = "abc123"
  tags = {
    Environment = "dev"
    Project     = "rtaudio"
  }

  # Infrastructure dependencies
  log_analytics_workspace_id      = azurerm_log_analytics_workspace.main.id
  container_registry_login_server = azurerm_container_registry.main.login_server # Required for containers
  frontend_identity_id            = azurerm_user_assigned_identity.frontend.id
  backend_identity_id             = azurerm_user_assigned_identity.backend.id

  # Application configuration
  frontend_config = {
    port             = 8080
    azd_service_name = "frontend-app"
    # Container-specific settings
    min_replicas = 1
    max_replicas = 5
    cpu          = 0.5
    memory       = "1.0Gi"
    # WebApp-specific settings (ignored when using containers)
    sku_name     = "B1"
    node_version = "22-lts"
  }

  backend_config = {
    port             = 8000
    azd_service_name = "backend-api"
    # Container-specific settings
    min_replicas = 1
    max_replicas = 10
    cpu          = 1.0
    memory       = "2.0Gi"
    # WebApp-specific settings (ignored when using containers)
    sku_name       = "B2"
    python_version = "3.11"
  }

  # Frontend environment variables
  frontend_env_vars = [
    {
      name  = "VITE_BACKEND_BASE_URL"
      value = "https://myapp-backend-abc123.azurecontainerapps.io"
    },
    {
      name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
      value = azurerm_application_insights.main.connection_string
    },
    {
      name  = "PORT"
      value = "8080"
    }
  ]

  # Backend environment variables
  backend_env_vars = [
    {
      name  = "AZURE_CLIENT_ID"
      value = azurerm_user_assigned_identity.backend.client_id
    },
    {
      name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
      value = azurerm_application_insights.main.connection_string
    },
    {
      name  = "REDIS_HOST"
      value = azurerm_redis_cache.main.hostname
    },
    {
      name  = "REDIS_PORT"
      value = "6380"
    },
    {
      name        = "ACS_CONNECTION_STRING"
      secret_name = "acs-connection-string" # Reference to container secret
    },
    {
      name        = "AZURE_SPEECH_KEY"
      secret_name = "speech-key"
    }
  ]

  # Secrets (only used with containers)
  secrets = [
    {
      name                = "acs-connection-string"
      identity            = azurerm_user_assigned_identity.backend.id
      key_vault_secret_id = azurerm_key_vault_secret.acs_connection_string.versionless_id
    },
    {
      name                = "speech-key"
      identity            = azurerm_user_assigned_identity.backend.id
      key_vault_secret_id = azurerm_key_vault_secret.speech_key.versionless_id
    }
  ]

  # CORS settings
  frontend_cors_origins    = ["*"]
  backend_cors_origins     = ["*"]
  cors_support_credentials = false

  # Logging settings
  enable_diagnostics = true
  log_retention_days = 7
  log_retention_mb   = 35
}

# Example: Using the same module with webapps
module "hosting_webapps" {
  source = "./modules/hosting"

  # Platform selection - switch to webapps
  hosting_platform = "webapps"

  # Same basic configuration
  name                = "myapp"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  resource_token      = "abc123"
  tags = {
    Environment = "prod"
    Project     = "rtaudio"
  }

  # Infrastructure dependencies (container_registry_login_server not needed for webapps)
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  frontend_identity_id       = azurerm_user_assigned_identity.frontend.id
  backend_identity_id        = azurerm_user_assigned_identity.backend.id

  # Application configuration
  frontend_config = {
    port             = 8080
    azd_service_name = "frontend-webapp"
    # WebApp-specific settings are now used
    sku_name         = "S1" # Standard tier for production
    node_version     = "22-lts"
    app_command_line = "npm run build && npm run start"
    always_on        = true
  }

  backend_config = {
    port             = 8000
    azd_service_name = "backend-webapp"
    # WebApp-specific settings are now used
    sku_name         = "S2" # Standard tier for production
    python_version   = "3.11"
    app_command_line = "python -m uvicorn apps.rtagent.backend.main:app --host 0.0.0.0 --port 8000"
    always_on        = true
  }

  # Environment variables (converted to app settings for webapps)
  # Note: secret_name is ignored for webapps, use Key Vault references instead
  frontend_env_vars = [
    {
      name  = "VITE_BACKEND_BASE_URL"
      value = "https://myapp-backend-app-abc123.azurewebsites.net"
    },
    {
      name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
      value = azurerm_application_insights.main.connection_string
    },
    {
      name  = "VITE_AZURE_SPEECH_KEY"
      value = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=speech-key)"
    }
  ]

  backend_env_vars = [
    {
      name  = "AZURE_CLIENT_ID"
      value = azurerm_user_assigned_identity.backend.client_id
    },
    {
      name  = "ACS_CONNECTION_STRING"
      value = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=AcsConnectionString)"
    },
    {
      name  = "AZURE_SPEECH_KEY"
      value = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=speech-key)"
    }
  ]

  # Secrets not used with webapps (use Key Vault references instead)
  secrets = []
}

# ============================================================================
# OUTPUTS EXAMPLES
# ============================================================================

# Common outputs work for both platforms
output "frontend_url" {
  description = "Frontend application URL"
  value       = module.hosting_containers.frontend_url
}

output "backend_url" {
  description = "Backend API URL"
  value       = module.hosting_containers.backend_url
}

output "hosting_platform_used" {
  description = "The hosting platform that was used"
  value       = module.hosting_containers.hosting_platform
}

# Platform-specific outputs
output "container_environment_id" {
  description = "Container Apps Environment ID (only available when using containers)"
  value       = module.hosting_containers.container_environment_id
}

output "frontend_service_plan_id" {
  description = "Frontend Service Plan ID (only available when using webapps)"
  value       = module.hosting_webapps.frontend_service_plan_id
}
