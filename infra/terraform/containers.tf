variable "container_images" {
  description = "Optional initial images for frontend, backend, and cardapi when creating/replacing apps. Subsequent image deployments remain managed by azd."
  type        = map(string)
  default     = {}
  validation {
    condition = alltrue([
      for name, image in var.container_images :
      contains(["frontend", "backend", "cardapi"], name) && length(trimspace(image)) > 0
    ])
    error_message = "container_images supports only frontend, backend, and cardapi with nonempty image references."
  }
}

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

  public_network_access = var.enable_front_door ? "Disabled" : "Enabled"

  dynamic "workload_profile" {
    for_each = var.container_app_workload_profiles_enabled ? [1] : []
    content {
      name                  = "Consumption"
      workload_profile_type = "Consumption"
    }
  }

  lifecycle {
    precondition {
      condition     = !var.enable_front_door || var.container_app_workload_profiles_enabled
      error_message = "Front Door requires container_app_workload_profiles_enabled=true. Review the environment replacement plan before migrating a legacy deployment."
    }
  }

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
  workload_profile_name        = var.container_app_workload_profiles_enabled ? "Consumption" : null

  // Image is managed outside of terraform (i.e azd deploy)
  // EasyAuth configs are managed outside of terraform
  // Note: env vars are now managed via Azure App Configuration (apps read at runtime)
  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
      ingress[0].cors,
      ingress[0].client_certificate_mode,
      ingress[0].ip_security_restriction,
      # EasyAuth's FIC magic secret ("override-use-mi-fic-assertion-client-id")
      # is added out-of-band by devops/scripts/azd/helpers/enable-easyauth.sh.
      # Without ignoring it, every `azd provision` (terraform apply) treats it
      # as drift and deletes it, leaving the authConfig pointing at a missing
      # secret and breaking the login redirect.
      secret
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
      image  = lookup(var.container_images, "frontend", "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest")
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
  workload_profile_name        = var.container_app_workload_profiles_enabled ? "Consumption" : null

  dynamic "secret" {
    for_each = var.enable_front_door ? [1] : []
    content {
      name                = "event-grid-webhook-secret"
      identity            = azurerm_user_assigned_identity.backend.id
      key_vault_secret_id = azurerm_key_vault_secret.event_grid_webhook[0].versionless_id
    }
  }

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
      image  = lookup(var.container_images, "backend", "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest")
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

      env {
        name  = "ENABLE_FRONT_DOOR"
        value = tostring(var.enable_front_door)
      }

      dynamic "env" {
        for_each = var.enable_front_door ? {
          ACS_AUDIENCE        = azapi_resource.acs.output.properties.immutableResourceId
          ACS_ARM_RESOURCE_ID = azapi_resource.acs.id
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.enable_front_door ? [1] : []
        content {
          name        = "EVENT_GRID_WEBHOOK_SECRET"
          secret_name = "event-grid-webhook-secret"
        }
      }
    }
  }

  tags = merge(local.tags, {
    "azd-service-name" = "rtaudio-server"
  })

  // Image is managed outside of terraform (i.e azd deploy)
  // Terraform owns bootstrap/security env vars; runtime settings come from App Configuration.
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
# STICKY SESSIONS
# ============================================================================
# The azurerm provider does not support sticky sessions natively.
# Use azapi_update_resource to enable session affinity so that requests
# from the same client are routed to the same replica.

resource "azapi_update_resource" "frontend_sticky_sessions" {
  type        = "Microsoft.App/containerApps@2024-03-01"
  resource_id = azurerm_container_app.frontend.id

  body = {
    properties = {
      configuration = {
        ingress = {
          stickySessions = {
            affinity = "sticky"
          }
        }
      }
    }
  }
}

resource "azapi_update_resource" "backend_sticky_sessions" {
  type        = "Microsoft.App/containerApps@2024-03-01"
  resource_id = azurerm_container_app.backend.id

  body = {
    properties = {
      configuration = {
        ingress = {
          stickySessions = {
            affinity = "sticky"
          }
          # azurerm_container_app has no cors_policy argument, so the ingress
          # CORS policy is set via the Container Apps REST API. Container Apps
          # ingress (Envoy) answers the CORS preflight (OPTIONS) at the edge
          # using these values; without it, browser cross-origin calls from the
          # frontend Container App fail their preflight with "No
          # 'Access-Control-Allow-Origin' header is present".
          corsPolicy = {
            allowedOrigins = ["https://${local.frontend_public_hostname}"]
            allowedMethods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
            # Includes the Application Insights JS SDK correlation headers
            # (Request-Id, Request-Context, traceparent, tracestate) so browser
            # distributed-tracing calls are not rejected at the ingress preflight.
            allowedHeaders   = ["Content-Type", "Authorization", "X-Requested-With", "Accept", "Cache-Control", "Request-Id", "Request-Context", "traceparent", "tracestate"]
            exposeHeaders    = ["Content-Length", "Content-Range", "Request-Context"]
            allowCredentials = true
            maxAge           = 86400
          }
        }
      }
    }
  }
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
  description = "Frontend public URL (Front Door when enabled)"
  value       = "https://${local.frontend_public_hostname}"
}

output "BACKEND_CONTAINER_APP_URL" {
  description = "Backend public URL (Front Door when enabled)"
  value       = "https://${local.backend_public_hostname}"
}


output "BACKEND_API_URL" {
  description = "Backend API URL"
  value       = "https://${local.backend_public_hostname}"
}
