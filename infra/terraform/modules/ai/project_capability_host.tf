locals {
  create_ai_foundry_capability_host = (
    var.ai_search_id != null &&
    var.storage_account_id != null &&
    var.cosmosdb_account_id != null
  )

  resource_group_name = split("/", var.resource_group_id)[4]
}

## Create the AI Foundry project capability host (only when required IDs provided)
##
resource "azapi_resource" "ai_foundry_project_capability_host" {
  count = local.create_ai_foundry_capability_host ? 1 : 0

  depends_on = [
    azapi_resource.conn_aisearch,
    azapi_resource.conn_cosmosdb,
    azapi_resource.conn_storage,
    time_sleep.wait_rbac
  ]
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview"
  name                      = "caphostproj"
  parent_id                 = azapi_resource.ai_foundry_project.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind = "Agents"
      vectorStoreConnections = [
        local.aisearch_name_from_id
      ]
      storageConnections = [
        local.storage_name_from_id
      ]
      threadStorageConnections = [
        local.cosmos_name_from_id
      ]
    }
  }
}


## Create the necessary data plane role assignments to the CosmosDb databases created by the AI Foundry Project
##
resource "azurerm_cosmosdb_sql_role_assignment" "cosmosdb_db_sql_role_aifp_user_thread_message_store" {
  count = local.create_ai_foundry_capability_host ? 1 : 0

  depends_on = [
    azapi_resource.ai_foundry_project_capability_host
  ]
  name                = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}userthreadmessage_dbsqlrole")
  resource_group_name = local.resource_group_name
  account_name        = local.cosmos_name_from_id
  scope               = "${local.cosmos_name_from_id}/dbs/enterprise_memory/colls/${local.project_id_guid}-thread-message-store"
  role_definition_id  = "${local.cosmos_name_from_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.ai_foundry_project.output.identity.principalId
}

resource "azurerm_cosmosdb_sql_role_assignment" "cosmosdb_db_sql_role_aifp_system_thread_name" {
  count = local.create_ai_foundry_capability_host ? 1 : 0

  depends_on = [
    azurerm_cosmosdb_sql_role_assignment.cosmosdb_db_sql_role_aifp_user_thread_message_store
  ]
  name                = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}systemthread_dbsqlrole")
  resource_group_name = local.resource_group_name
  account_name        = local.cosmos_name_from_id
  scope               = "${var.cosmosdb_account_id}/dbs/enterprise_memory/colls/${local.project_id_guid}-system-thread-message-store"
  role_definition_id  = "${var.cosmosdb_account_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.ai_foundry_project.output.identity.principalId
}

resource "azurerm_cosmosdb_sql_role_assignment" "cosmosdb_db_sql_role_aifp_entity_store_name" {
  count = local.create_ai_foundry_capability_host ? 1 : 0

  depends_on = [
    azurerm_cosmosdb_sql_role_assignment.cosmosdb_db_sql_role_aifp_system_thread_name
  ]
  name                = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}entitystore_dbsqlrole")
  resource_group_name = local.resource_group_name
  account_name        = local.cosmos_name_from_id
  scope               = "${var.cosmosdb_account_id}/dbs/enterprise_memory/colls/${local.project_id_guid}-agent-entity-store"
  role_definition_id  = "${var.cosmosdb_account_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azapi_resource.ai_foundry_project.output.identity.principalId
}

## Create the necessary data plane role assignments to the Azure Storage Account containers created by the AI Foundry Project
##
resource "azurerm_role_assignment" "storage_blob_data_owner_ai_foundry_project" {
  count = local.create_ai_foundry_capability_host ? 1 : 0

  depends_on = [
    azapi_resource.ai_foundry_project_capability_host
  ]
  name                 = uuidv5("dns", "${azapi_resource.ai_foundry_project.name}${azapi_resource.ai_foundry_project.output.identity.principalId}${local.storage_name_from_id}storageblobdataowner")
  scope                = local.storage_name_from_id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azapi_resource.ai_foundry_project.output.identity.principalId
  condition_version    = "2.0"
  condition            = <<-EOT
    (
        (
            !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/read'})
            AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/filter/action'})
            AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/write'})
        )
        OR
        (@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringStartsWithIgnoreCase '${local.project_id_guid}'
        AND @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringLikeIgnoreCase '*-azureml-agent')
    )
    EOT
}

# ## Added AI Foundry account purger to avoid running into InUseSubnetCannotBeDeleted-lock caused by the agent subnet delegation.
# ## The azapi_resource_action.purge_ai_foundry (only gets executed during destroy) purges the AI foundry account removing /subnets/snet-agent/serviceAssociationLinks/legionservicelink so the agent subnet can get properly removed.

# resource "azapi_resource_action" "purge_ai_foundry" {
#   method      = "DELETE"
#   resource_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.CognitiveServices/locations/${azurerm_resource_group.rg.location}/resourceGroups/${local.resource_group_name}/deletedAccounts/aifoundry${random_string.unique.result}"
#   type        = "Microsoft.Resources/resourceGroups/deletedAccounts@2021-04-30"
#   when        = "destroy"

#   depends_on = [time_sleep.purge_ai_foundry_cooldown]
# }

# resource "time_sleep" "purge_ai_foundry_cooldown" {
#   destroy_duration = "900s" # 10-15m is enough time to let the backend remove the /subnets/snet-agent/serviceAssociationLinks/legionservicelink

#   depends_on = [azurerm_subnet.subnet_agent]
# }