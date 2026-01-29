# ============================================================================
# CARD API - MANAGED IDENTITIES
# ============================================================================

resource "azurerm_user_assigned_identity" "cardapi_backend" {
  name                = "${var.name}-cardapi-backend-${local.resource_token}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_user_assigned_identity" "cardapi_mcp" {
  name                = "${var.name}-cardapi-mcp-${local.resource_token}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

# ============================================================================
# CARD API - ACR PULL PERMISSIONS
# ============================================================================

resource "azurerm_role_assignment" "acr_cardapi_backend_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.cardapi_backend.principal_id
}

resource "azurerm_role_assignment" "acr_cardapi_mcp_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.cardapi_mcp.principal_id
}

# ============================================================================
# CARD API - APP CONFIGURATION ACCESS
# ============================================================================

resource "azurerm_role_assignment" "appconfig_cardapi_backend_reader" {
  scope                = module.appconfig.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = azurerm_user_assigned_identity.cardapi_backend.principal_id
}

resource "azurerm_role_assignment" "appconfig_cardapi_mcp_reader" {
  scope                = module.appconfig.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = azurerm_user_assigned_identity.cardapi_mcp.principal_id
}

# Key Vault access for cardapi_backend to read Cosmos connection string
resource "azurerm_role_assignment" "keyvault_cardapi_backend_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.cardapi_backend.principal_id
}

# ============================================================================
# CARD API - COSMOS DB MONGODB USER (READER ACCESS)
# ============================================================================

# Create a MongoDB user for cardapi_backend with reader access to the shared Cosmos DB
resource "azapi_resource" "cardapi_backend_db_user" {
  type      = "Microsoft.DocumentDB/mongoClusters/users@2025-04-01-preview"
  name      = azurerm_user_assigned_identity.cardapi_backend.principal_id
  parent_id = azapi_resource.mongoCluster.id
  body = {
    properties = {
      identityProvider = {
        properties = {
          principalType = "ServicePrincipal"
        }
        type = "MicrosoftEntraID"
      }
      roles = [
        {
          db   = "admin"
          role = "dbOwner"
        }
      ]
    }
  }
  lifecycle {
    ignore_changes = [
      body["properties"]["identityProvider"]["properties"]["principalType"],
      output["properties"]["provisioningState"],
      output["properties"]["roles"],
      output["id"],
      output["type"]
    ]
  }

  depends_on = [azapi_resource.mongoCluster]
}

# ============================================================================
# CARD API - COSMOS DB (DOCUMENT DATABASE)
# ============================================================================

# Note: For the cardapi, we're using the existing MongoDB cluster
# The decline codes are stored as JSON in the container itself for simplicity
# If you need a separate Cosmos DB instance, uncomment and configure below:

# resource "azapi_resource" "cardapi_mongoCluster" {
#   type                      = "Microsoft.DocumentDB/mongoClusters@2025-08-01-preview"
#   parent_id                 = azurerm_resource_group.main.id
#   schema_validation_enabled = false
#   name                      = "${local.resource_names.cosmos}-cardapi"
#   location                  = var.location
#   body = {
#     properties = {
#       administrator = {
#         userName = "cosmosadmin"
#         password = random_password.cosmos_cardapi_admin.result
#       }
#       authConfig = {
#         allowedModes = [
#           "MicrosoftEntraID",
#           "NativeAuth"
#         ]
#       }
#       compute = {
#         tier = "M25"
#       }
#       serverVersion = "8.0"
#       sharding = {
#         shardCount = 1
#       }
#       storage = {
#         sizeGb = 32
#       }
#     }
#   }
#   tags = local.tags
# }

# ============================================================================
# CARD API - BACKEND CONTAINER APP
# ============================================================================

resource "azurerm_container_app" "cardapi_backend" {
  name                         = "${var.name}-cardapi-be-${local.resource_token}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.cardapi_backend.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.cardapi_backend.id
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
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "main"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "AZURE_APPCONFIG_ENDPOINT"
        value = module.appconfig.endpoint
      }

      env {
        name  = "AZURE_APPCONFIG_LABEL"
        value = var.environment_name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.cardapi_backend.client_id
      }

      env {
        name  = "PORT"
        value = "8000"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }

      # Database and collection names (cardapi-specific)
      env {
        name  = "AZURE_COSMOS_DATABASE_NAME"
        value = "cardapi"
      }

      env {
        name  = "AZURE_COSMOS_COLLECTION_NAME"
        value = "declinecodes"
      }
    }
  }

  tags = merge(local.tags, {
    "azd-service-name" = "cardapi-be"
  })

  lifecycle {
    ignore_changes = [
      template[0].container[0].image
    ]
  }
}

# ============================================================================
# CARD API - MCP SERVER CONTAINER APP
# ============================================================================

resource "azurerm_container_app" "cardapi_mcp" {
  name                         = "${var.name}-cardapi-mcp-${local.resource_token}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.cardapi_mcp.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.cardapi_mcp.id
  }

  ingress {
    external_enabled = true  # MCP server exposed for external tool calls
    target_port      = 80
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "main"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = 0.25
      memory = "0.5Gi"

      # Health probes for the embedded HTTP server
      liveness_probe {
        transport = "HTTP"
        port      = 80
        path      = "/health"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 80
        path      = "/ready"
      }

      startup_probe {
        transport = "HTTP"
        port      = 80
        path      = "/health"
      }

      env {
        name  = "AZURE_APPCONFIG_ENDPOINT"
        value = module.appconfig.endpoint
      }

      env {
        name  = "AZURE_APPCONFIG_LABEL"
        value = var.environment_name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.cardapi_mcp.client_id
      }

      env {
        name  = "CARDAPI_BACKEND_URL"
        value = "https://${azurerm_container_app.cardapi_backend.ingress[0].fqdn}"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "PORT"
        value = "80"
      }

      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }
    }
  }

  tags = merge(local.tags, {
    "azd-service-name" = "cardapi-mcp"
  })

  lifecycle {
    ignore_changes = [
      template[0].container[0].image
    ]
  }
}

# ============================================================================
# CARD API - MONITORING PERMISSIONS
# ============================================================================

resource "azurerm_role_assignment" "cardapi_backend_metrics_publisher" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_container_app.cardapi_backend.identity[0].principal_id
}

resource "azurerm_role_assignment" "cardapi_mcp_metrics_publisher" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_container_app.cardapi_mcp.identity[0].principal_id
}

# ============================================================================
# CARD API - OUTPUTS
# ============================================================================

output "CARDAPI_BACKEND_CONTAINER_APP_NAME" {
  description = "Card API Backend Container App name"
  value       = azurerm_container_app.cardapi_backend.name
}

output "CARDAPI_MCP_CONTAINER_APP_NAME" {
  description = "Card API MCP Container App name"
  value       = azurerm_container_app.cardapi_mcp.name
}

output "CARDAPI_BACKEND_URL" {
  description = "Card API Backend URL"
  value       = "https://${azurerm_container_app.cardapi_backend.ingress[0].fqdn}"
}

output "CARDAPI_MCP_FQDN" {
  description = "Card API MCP internal FQDN"
  value       = azurerm_container_app.cardapi_mcp.ingress[0].fqdn
}

output "CARDAPI_CONTAINER_APP_URL" {
  description = "Card API MCP Container App public URL (for agent integration)"
  value       = "https://${azurerm_container_app.cardapi_mcp.ingress[0].fqdn}"
}
