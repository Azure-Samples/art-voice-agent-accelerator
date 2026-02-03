# ============================================================================
# CARD API - MANAGED IDENTITY
# ============================================================================
#
# The CardAPI MCP server is self-contained and connects directly to Cosmos DB.
# No separate backend container is needed.
# ============================================================================

resource "azurerm_user_assigned_identity" "cardapi_mcp" {
  name                = "${var.name}-cardapi-mcp-${local.resource_token}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

# ============================================================================
# CARD API - ACR PULL PERMISSIONS
# ============================================================================

resource "azurerm_role_assignment" "acr_cardapi_mcp_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.cardapi_mcp.principal_id
}

# ============================================================================
# CARD API - APP CONFIGURATION ACCESS
# ============================================================================

resource "azurerm_role_assignment" "appconfig_cardapi_mcp_reader" {
  scope                = module.appconfig.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = azurerm_user_assigned_identity.cardapi_mcp.principal_id
}

# ============================================================================
# CARD API - KEY VAULT ACCESS (for Cosmos connection string)
# ============================================================================

resource "azurerm_role_assignment" "keyvault_cardapi_mcp_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.cardapi_mcp.principal_id
}

# ============================================================================
# CARD API - COSMOS DB MONGODB USER (READ ACCESS)
# ============================================================================

# Create a MongoDB user for cardapi_mcp with access to the shared Cosmos DB.
# NOTE: Cosmos DB MongoDB vCore currently only supports assigning the 'dbOwner'
# role on the 'admin' database for Microsoft Entra ID principals. This grants
# broader privileges than required for the CardAPI MCP server, which is intended
# to perform read-only operations only.
#
# SECURITY IMPLICATIONS:
# - The managed identity technically has permissions to perform write operations.
# - Application code MUST treat this connection as read-only and MUST NOT issue
#   any write/DDL operations.
# - Platform/operations teams MUST configure monitoring/alerting on Cosmos DB
#   (e.g., diagnostic logs or activity logs) to detect and investigate any write
#   operations performed by this identity.
# - Where Cosmos DB introduces more granular roles or read-only connection
#   mechanisms, this configuration SHOULD be updated to remove the 'dbOwner'
#   assignment or switch to a read-only connection string.
resource "azapi_resource" "cardapi_mcp_db_user" {
  type      = "Microsoft.DocumentDB/mongoClusters/users@2025-04-01-preview"
  name      = azurerm_user_assigned_identity.cardapi_mcp.principal_id
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
# CARD API - MCP SERVER CONTAINER APP
# ============================================================================
#
# Self-contained MCP server that connects directly to Cosmos DB for decline codes.
# Uses managed identity for authentication (no secrets stored).
# ============================================================================

resource "azurerm_container_app" "cardapi_mcp" {
  name                         = "cardapi-mcp-${local.resource_token}"
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
    target_port      = 8080
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
        port      = 8080
        path      = "/health"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8080
        path      = "/ready"
      }

      startup_probe {
        transport = "HTTP"
        port      = 8080
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

      # Cosmos DB connection (via OIDC - uses AZURE_CLIENT_ID for managed identity)
      env {
        name  = "AZURE_COSMOS_DATABASE_NAME"
        value = "cardapi"
      }

      env {
        name  = "AZURE_COSMOS_COLLECTION_NAME"
        value = "declinecodes"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "PORT"
        value = "8080"
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

resource "azurerm_role_assignment" "cardapi_mcp_metrics_publisher" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_container_app.cardapi_mcp.identity[0].principal_id
}

# ============================================================================
# CARD API - OUTPUTS
# ============================================================================

output "CARDAPI_MCP_CONTAINER_APP_NAME" {
  description = "Card API MCP Container App name"
  value       = azurerm_container_app.cardapi_mcp.name
}

output "CARDAPI_MCP_FQDN" {
  description = "Card API MCP FQDN"
  value       = azurerm_container_app.cardapi_mcp.ingress[0].fqdn
}

output "CARDAPI_CONTAINER_APP_URL" {
  description = "Card API MCP Container App public URL (for agent integration)"
  value       = "https://${azurerm_container_app.cardapi_mcp.ingress[0].fqdn}"
}

output "CARDAPI_MCP_UAI_CLIENT_ID" {
  description = "Card API MCP User-Assigned Identity Client ID (for EasyAuth)"
  value       = azurerm_user_assigned_identity.cardapi_mcp.client_id
}
