# ============================================================================
# CONTAINER REGISTRY
# ============================================================================

resource "azurerm_container_registry" "main" {
  name                = local.resource_names.container_registry
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false

  public_network_access_enabled = true

  tags = local.tags
}

# RBAC assignments for Container Registry
resource "azurerm_role_assignment" "acr_principal_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = local.principal_id
  principal_type       = local.principal_type
}

resource "azurerm_role_assignment" "acr_principal_push" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPush"
  principal_id         = local.principal_id
  principal_type       = local.principal_type
}

resource "azurerm_role_assignment" "acr_frontend_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.frontend.principal_id
}

resource "azurerm_role_assignment" "acr_backend_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}


# ============================================================================
# CONTAINER APPS ENVIRONMENT
# ============================================================================

resource "azurerm_container_app_environment" "main" {
  name                = local.resource_names.container_env
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  tags = local.tags
}

# ============================================================================
# CONTAINER APPS
# ============================================================================

# Normalize memory format to match Azure API response (e.g., "4Gi" -> "4.0Gi")
# This prevents frivolous Terraform updates due to format differences
locals {
  # Ensure memory format includes decimal (Azure returns "4.0Gi", not "4Gi")
  normalized_backend_memory = replace(
    var.container_memory_gb,
    "/^([0-9]+)(Gi)$/",
    "$1.0$2"
  )
  # Frontend uses fixed 1Gi
  normalized_frontend_memory = "1.0Gi"
}

# Frontend Container App
resource "azurerm_container_app" "frontend" {
  name                         = "${var.name}-frontend-${local.resource_token}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  // Image is managed outside of terraform (i.e azd deploy)
  // EasyAuth configs are managed outside of terraform
  // Note: env vars are now managed via Azure App Configuration (apps read at runtime)
  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
      ingress[0].cors,
      ingress[0].client_certificate_mode,
      ingress[0].ip_security_restriction
    ]
  }

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.frontend.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.frontend.id
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 10

    container {
      name   = "main"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = 0.5
      memory = local.normalized_frontend_memory

      # Azure App Configuration (PRIMARY CONFIG SOURCE)
      env {
        name  = "AZURE_APPCONFIG_ENDPOINT"
        value = module.appconfig.endpoint
      }

      env {
        name  = "AZURE_APPCONFIG_LABEL"
        value = var.environment_name
      }

      # Managed Identity for authentication
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.frontend.client_id
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "PORT"
        value = "8080"
      }
    }
  }

  tags = merge(local.tags, {
    "azd-service-name" = "rtaudio-client"
  })
}

# Backend Container App
resource "azurerm_container_app" "backend" {
  name                         = "${var.name}-backend-${local.resource_token}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.backend.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.backend.id
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.container_app_min_replicas
    max_replicas = var.container_app_max_replicas

    container {
      name   = "main"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = var.container_cpu_cores
      memory = local.normalized_backend_memory

      # ======================================================================
      # BOOTSTRAP ENVIRONMENT VARIABLES
      # ======================================================================
      # Only essential vars for app startup. All other configuration
      # (including secrets via Key Vault references) is fetched from
      # Azure App Configuration at runtime.
      # ======================================================================

      # Azure App Configuration (PRIMARY CONFIG SOURCE)
      env {
        name  = "AZURE_APPCONFIG_ENDPOINT"
        value = module.appconfig.endpoint
      }

      env {
        name  = "AZURE_APPCONFIG_LABEL"
        value = var.environment_name
      }

      # Managed Identity for authentication to Azure services
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.backend.client_id
      }

      # Application port
      env {
        name  = "PORT"
        value = "8000"
      }

      # Application Insights (needed early for telemetry)
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      # Python runtime
      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }
    }
  }

  tags = merge(local.tags, {
    "azd-service-name" = "rtaudio-server"
  })

  // Image is managed outside of terraform (i.e azd deploy)
  // Note: env vars are now managed via Azure App Configuration (apps read at runtime)
  lifecycle {
    ignore_changes = [
      template[0].container[0].image
    ]
  }
  depends_on = [
    azurerm_key_vault_secret.acs_connection_string,
    azurerm_role_assignment.keyvault_backend_secrets
  ]
}

# ============================================================================
# ROLE ASSIGNMENTS: Monitoring Metrics Publisher for system-assigned identities
# ============================================================================

# Grant the frontend Container App's system-assigned identity permission to publish metrics
resource "azurerm_role_assignment" "frontend_metrics_publisher_system" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_container_app.frontend.identity[0].principal_id
}

# Grant the backend Container App's system-assigned identity permission to publish metrics
resource "azurerm_role_assignment" "backend_metrics_publisher_system" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_container_app.backend.identity[0].principal_id
}

# Container Apps Environment
output "CONTAINER_APPS_ENVIRONMENT_ID" {
  description = "Container Apps Environment resource ID"
  value       = azurerm_container_app_environment.main.id
}

output "CONTAINER_APPS_ENVIRONMENT_NAME" {
  description = "Container Apps Environment name"
  value       = azurerm_container_app_environment.main.name
}

# Container Apps
output "FRONTEND_CONTAINER_APP_NAME" {
  description = "Frontend Container App name"
  value       = azurerm_container_app.frontend.name
}

output "BACKEND_CONTAINER_APP_NAME" {
  description = "Backend Container App name"
  value       = azurerm_container_app.backend.name
}

output "FRONTEND_CONTAINER_APP_FQDN" {
  description = "Frontend Container App FQDN"
  value       = azurerm_container_app.frontend.ingress[0].fqdn
}

output "BACKEND_CONTAINER_APP_FQDN" {
  description = "Backend Container App FQDN"
  value       = azurerm_container_app.backend.ingress[0].fqdn
}

output "FRONTEND_CONTAINER_APP_URL" {
  description = "Frontend Container App URL"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "BACKEND_CONTAINER_APP_URL" {
  description = "Backend Container App URL"
  value       = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}


output "BACKEND_API_URL" {
  description = "Backend API URL"
  value       = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}
