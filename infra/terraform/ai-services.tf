# ============================================================================
# AZURE OPENAI
# ============================================================================

resource "azurerm_cognitive_account" "openai" {
  name                = local.resource_names.openai
  location            = var.openai_location != null ? var.openai_location : var.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "OpenAI"
  sku_name            = "S0"

  custom_subdomain_name         = local.resource_names.openai
  public_network_access_enabled = true

  # Use managed identity for authentication
  local_auth_enabled = !var.disable_local_auth

  tags = local.tags
}

# Diagnostic settings for Azure OpenAI
resource "azurerm_monitor_diagnostic_setting" "openai_diagnostics" {
  name                       = "${azurerm_cognitive_account.openai.name}-diagnostics"
  target_resource_id         = azurerm_cognitive_account.openai.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  # Common Cognitive Services categories
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

# OpenAI model deployments
resource "azurerm_cognitive_deployment" "openai_models" {
  for_each = { for idx, model in var.openai_models : model.name => model }

  name                 = each.value.name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = each.value.name
    version = each.value.version
  }

  sku {
    name     = each.value.sku_name
    capacity = each.value.capacity
  }
}

# RBAC assignments for OpenAI
resource "azurerm_role_assignment" "openai_backend_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}

resource "azurerm_role_assignment" "openai_frontend_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.frontend.principal_id
}

# Store OpenAI key in Key Vault (if local auth is enabled)
resource "azurerm_key_vault_secret" "openai_key" {
  count        = var.disable_local_auth ? 0 : 1
  name         = "openai-key"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.keyvault_admin]
}

# ============================================================================
# AZURE SPEECH SERVICES
# ============================================================================

resource "azurerm_cognitive_account" "speech" {
  name                = local.resource_names.speech
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "SpeechServices"
  sku_name            = "S0"

  custom_subdomain_name         = local.resource_names.speech
  public_network_access_enabled = true

  # Use managed identity for authentication
  #local_auth_enabled = !var.disable_local_auth

  tags = local.tags
}

# Diagnostic settings for Speech Services
resource "azurerm_monitor_diagnostic_setting" "speech_diagnostics" {
  name                       = "${azurerm_cognitive_account.speech.name}-diagnostics"
  target_resource_id         = azurerm_cognitive_account.speech.id
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

# RBAC assignments for Speech Services
resource "azurerm_role_assignment" "speech_backend_user" {
  scope                = azurerm_cognitive_account.speech.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}

resource "azurerm_role_assignment" "speech_frontend_user" {
  scope                = azurerm_cognitive_account.speech.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_user_assigned_identity.frontend.principal_id
}

# Store Speech key in Key Vault (if local auth is enabled)
resource "azurerm_key_vault_secret" "speech_key" {
  count        = var.disable_local_auth ? 0 : 1
  name         = "speech-key"
  value        = azurerm_cognitive_account.speech.primary_access_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.keyvault_admin]
}
