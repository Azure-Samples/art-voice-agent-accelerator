# ============================================================================
# AZURE STORAGE ACCOUNT
# ============================================================================

resource "azurerm_storage_account" "main" {
  name                = local.resource_names.storage
  resource_group_name = azurerm_resource_group.main.name
  location            = var.cosmosdb_location != null ? var.cosmosdb_location : var.location
  account_tier        = "Standard"
  # Snyk ignore: poc, geo-replication not required
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  min_tls_version                 = "TLS1_2"
  public_network_access_enabled   = true
  allow_nested_items_to_be_public = false

  # Enable blob properties
  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  tags = local.tags
}

# Storage containers
resource "azurerm_storage_container" "audioagent" {
  name                  = "audioagent"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "prompt" {
  name                  = "prompt"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

# RBAC assignments for Storage
resource "azurerm_role_assignment" "storage_backend_contributor" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}

resource "azurerm_role_assignment" "storage_principal_reader" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = local.principal_id
  principal_type       = local.principal_type
}

resource "azurerm_role_assignment" "storage_principal_contributor" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = local.principal_id
  principal_type       = local.principal_type
}

# ============================================================================
# COSMOS DB (MONGODB API)
# ============================================================================
resource "azapi_resource" "mongoCluster" {
  type      = "Microsoft.DocumentDB/mongoClusters@2025-04-01-preview"
  parent_id = azurerm_resource_group.main.id
  name      = local.resource_names.cosmos
  location  = var.location
  body = {
    properties = {
      administrator = {
        userName = "adminuser"
        password = random_password.cosmos_admin.result
      }
      authConfig = {
        # Ensure the order is always the same and matches the API's default
        allowedModes = [
          "MicrosoftEntraID",
          "NativeAuth"
        ]
      }
      backup = {}
      compute = {
        tier = var.cosmosdb_sku
      }
      createMode = "Default"
      dataApi = {
        mode = "Disabled"
      }
      highAvailability = {
        targetMode = "Disabled"
      }
      publicNetworkAccess = var.cosmosdb_public_network_access_enabled ? "Enabled" : "Disabled"
      serverVersion       = "5.0"
      sharding = {
        shardCount = 1
      }
      storage = {
        sizeGb = 128
        type   = "PremiumSSD"
      }
    }
  }
  tags = local.tags

  # Suppress diffs for allowedModes array ordering
  lifecycle {
    ignore_changes = [
      body["properties"]["authConfig"]["allowedModes"],
      output["properties"]["authConfig"]["allowedModes"],
      output["properties"]["backup"]["earliestRestoreTime"],
      output["properties"]["clusterStatus"],
      output["properties"]["connectionString"],
      output["properties"]["infrastructureVersion"],
      output["properties"]["provisioningState"],
      output["properties"]["replica"]["replicationState"],
      output["properties"]["replica"]["role"],
      output["tags"]
    ]
  }
}

# MongoDB firewall rule to allow all IP addresses
resource "azapi_resource" "mongo_firewall_all" {
  count = var.cosmosdb_public_network_access_enabled ? 1 : 0
  type      = "Microsoft.DocumentDB/mongoClusters/firewallRules@2025-04-01-preview"
  parent_id = azapi_resource.mongoCluster.id
  name      = "allowAll"
  body = {
    properties = {
      startIpAddress = "0.0.0.0"
      endIpAddress   = "255.255.255.255"
    }
  }

  depends_on = [azapi_resource.mongoCluster]
}


# Store Entra ID connection string in Key Vault
resource "azurerm_key_vault_secret" "cosmos_entra_connection_string" {
  name         = "cosmos-entra-connection-string"
  value        = "${data.azapi_resource.mongo_cluster_info.output.properties.connectionString}?authSource=%24external&authMechanism=MONGODB-OIDC"
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.keyvault_admin, data.azapi_resource.mongo_cluster_info]
}

# Generate random password for Cosmos DB admin
resource "random_password" "cosmos_admin" {
  length  = 16
  special = true
}

# Store Cosmos DB admin password in Key Vault
resource "azurerm_key_vault_secret" "cosmos_admin_password" {
  name         = "cosmos-admin-password"
  value        = random_password.cosmos_admin.result
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.keyvault_admin]
}
# RBAC assignments for Cosmos DB vCore cluster
resource "azapi_resource" "cosmos_backend_db_user" {
  type      = "Microsoft.DocumentDB/mongoClusters/users@2025-04-01-preview"
  name      = azurerm_user_assigned_identity.backend.principal_id
  parent_id = azapi_resource.mongoCluster.id
  body = {
    properties = {
      identityProvider = {
        properties = {
          principalType = "ServicePrincipal"
        }
        type = "MicrosoftEntraID"
        // For remaining properties, see IdentityProvider objects
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
}

# RBAC assignments for Cosmos DB vCore cluster
resource "azapi_resource" "cosmos_principal_user" {
  type      = "Microsoft.DocumentDB/mongoClusters/users@2025-04-01-preview"
  name      = data.azuread_client_config.current.object_id
  parent_id = azapi_resource.mongoCluster.id
  body = {
    properties = {
      identityProvider = {
        properties = {
          principalType = var.principal_type
        }
        type = "MicrosoftEntraID"
        // For remaining properties, see IdentityProvider objects
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
    prevent_destroy = false
  }
}

# Data sources to retrieve MongoDB cluster information
data "azapi_resource" "mongo_cluster_info" {
  type      = "Microsoft.DocumentDB/mongoClusters@2025-04-01-preview"
  parent_id = azurerm_resource_group.main.id
  name      = azapi_resource.mongoCluster.name

  depends_on = [azapi_resource.mongoCluster]
}


# Store MongoDB connection details in Key Vault
resource "azurerm_key_vault_secret" "cosmos_connection_string" {
  name         = "cosmos-connection-string"
  value        = data.azapi_resource.mongo_cluster_info.output.properties.connectionString
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.keyvault_admin, data.azapi_resource.mongo_cluster_info]
}
