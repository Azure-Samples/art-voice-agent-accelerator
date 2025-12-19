module "ai_foundry_voice_live" {
  count  = local.should_create_voice_live_account ? 1 : 0
  source = "./modules/ai"

  resource_group_id = azurerm_resource_group.main.id
  location          = local.voice_live_primary_region
  tags              = local.tags

  disable_local_auth            = var.disable_local_auth
  foundry_account_name          = local.resource_names.voice_live_foundry_account
  foundry_custom_subdomain_name = local.resource_names.voice_live_foundry_account

  project_name         = local.resource_names.voice_live_foundry_project
  project_display_name = local.voice_live_project_display
  project_description  = local.voice_live_project_desc

  model_deployments = local.voice_live_model_deployments

  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

resource "azurerm_role_assignment" "ai_foundry_voice_live_account_role_for_backend_container" {
  count = local.should_create_voice_live_account ? 1 : 0

  scope                = module.ai_foundry_voice_live[count.index].account_id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}

resource "azurerm_role_assignment" "ai_foundry_voice_live_account_role_for_deployment_principal" {
  count = local.should_create_voice_live_account ? 1 : 0

  scope                = module.ai_foundry_voice_live[count.index].account_id
  role_definition_name = "Cognitive Services User"
  principal_id         = local.principal_id
}

resource "azurerm_monitor_diagnostic_setting" "ai_foundry_voice_live_account" {
  count = local.should_create_voice_live_account ? 1 : 0

  name                       = module.ai_foundry_voice_live[count.index].account_name
  target_resource_id         = module.ai_foundry_voice_live[count.index].account_id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "Audit"
  }

  enabled_log {
    category = "RequestResponse"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
