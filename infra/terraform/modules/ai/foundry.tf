# Terraform module for provisioning Azure AI Foundry aligned with the ai-services deployment.

locals {
  account_name_raw          = lower(trimspace(var.foundry_account_name))
  custom_subdomain_name_raw = var.foundry_custom_subdomain_name != null && trimspace(var.foundry_custom_subdomain_name) != "" ? lower(trimspace(var.foundry_custom_subdomain_name)) : local.account_name_raw

  project_name_raw = var.project_name != null && trimspace(var.project_name) != "" ? lower(trimspace(var.project_name)) : "${local.account_name_raw}-project"

  project_display_name_raw = var.project_display_name != null && trimspace(var.project_display_name) != "" ? trimspace(var.project_display_name) : local.project_name_raw

  project_description_raw = var.project_description != null && trimspace(var.project_description) != "" ? trimspace(var.project_description) : "Azure AI Foundry project ${local.project_display_name_raw}"

  project_id_guid = "${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 0, 8)}-${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 8, 4)}-${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 12, 4)}-${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 16, 4)}-${substr(azapi_resource.ai_foundry_project.output.properties.internalId, 20, 12)}"
}

resource "azapi_resource" "ai_foundry_account" {
  type                      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                      = local.account_name_raw
  parent_id                 = var.resource_group_id
  location                  = var.location
  schema_validation_enabled = false
  tags                      = var.tags

  body = {
    kind = "AIServices"
    sku = {
      name = var.foundry_sku_name
    }
    identity = {
      type = "SystemAssigned"
    }
    properties = {
      allowProjectManagement        = true
      disableLocalAuth              = var.disable_local_auth
      customSubDomainName           = local.custom_subdomain_name_raw
      publicNetworkAccess           = var.public_network_access
      restrictOutboundNetworkAccess = false
    }
  }

  response_export_values = [
    "properties.endpoint",
    "properties.endpoints"
  ]
}


resource "azurerm_cognitive_deployment" "model" {
  for_each = { for deployment in var.model_deployments : deployment.name => deployment }

  name                 = each.value.name
  cognitive_account_id = azapi_resource.ai_foundry_account.id

  sku {
    name     = each.value.sku_name
    capacity = each.value.capacity
  }

  model {
    format  = "OpenAI"
    name    = each.value.name
    version = each.value.version
  }
}

resource "azapi_resource" "ai_foundry_project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = local.project_name_raw
  parent_id                 = azapi_resource.ai_foundry_account.id
  location                  = var.location
  schema_validation_enabled = false

  body = {

    identity = {
      type = "SystemAssigned"
    }
    sku = {
      name = var.project_sku_name
    }
    properties = {
      displayName = local.project_display_name_raw
      description = local.project_description_raw
    }
  }
  response_export_values = [
    "identity.principalId",
    "properties.internalId"
  ]
}
