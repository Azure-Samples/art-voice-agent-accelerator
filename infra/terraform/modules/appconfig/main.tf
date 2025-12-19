# ============================================================================
# APP CONFIGURATION MODULE - MAIN RESOURCE
# ============================================================================
# This module creates an Azure App Configuration resource and populates it
# with application settings, service endpoints, and feature flags.
#
# Key design decisions:
# - Uses environment labels (dev, staging, prod) for multi-env support
# - Secrets are stored as Key Vault references (not raw values)
# - Feature flags use the standard .appconfig.featureflag/ prefix
# - RBAC-based access (no access keys)
# ============================================================================

resource "azurerm_app_configuration" "main" {
  name                       = var.name
  resource_group_name        = var.resource_group_name
  location                   = var.location
  sku                        = var.sku
  local_auth_enabled         = false # Enforce managed identity only
  public_network_access      = "Enabled"
  purge_protection_enabled   = false # Allow deletion in non-prod
  soft_delete_retention_days = 1     # Minimal retention for dev

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# ============================================================================
# RBAC ASSIGNMENTS
# ============================================================================

# App Configuration Data Reader for backend managed identity
resource "azurerm_role_assignment" "backend_reader" {
  scope                = azurerm_app_configuration.main.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = var.backend_identity_principal_id
}

# App Configuration Data Reader for frontend managed identity
resource "azurerm_role_assignment" "frontend_reader" {
  scope                = azurerm_app_configuration.main.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = var.frontend_identity_principal_id
}

# App Configuration Data Owner for deployer (admin access)
resource "azurerm_role_assignment" "deployer_owner" {
  scope                = azurerm_app_configuration.main.id
  role_definition_name = "App Configuration Data Owner"
  principal_id         = var.deployer_principal_id
  principal_type       = var.deployer_principal_type
}

# Key Vault Secrets User for App Configuration's system identity
# Required to resolve Key Vault references
resource "azurerm_role_assignment" "appconfig_keyvault" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_app_configuration.main.identity[0].principal_id
}

# ============================================================================
# LOCAL VARIABLES
# ============================================================================

locals {
  # Environment label for all keys
  label = var.environment_name

  # Content type constants
  content_type_text    = "text/plain"
  content_type_json    = "application/json"
  content_type_kv_ref  = "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8"
  content_type_feature = "application/vnd.microsoft.appconfig.ff+json;charset=utf-8"
}
