# ============================================================================
# APP CONFIGURATION
# ============================================================================
# Centralized configuration store for all application settings.
# 
# Terraform creates:
# - App Configuration resource
# - RBAC assignments for managed identities
# - Key Vault access for the App Config system identity
#
# ALL configuration keys (infrastructure endpoints + app settings) are 
# synced by postprovision.sh using azd env values and /config/appconfig.json
# ============================================================================

module "appconfig" {
  source = "./modules/appconfig"

  name                = "appconfig-${var.environment_name}-${local.resource_token}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  environment_name    = var.environment_name
  sku                 = "standard"
  tags                = local.tags

  # Identity access
  backend_identity_principal_id  = azurerm_user_assigned_identity.backend.principal_id
  frontend_identity_principal_id = azurerm_user_assigned_identity.frontend.principal_id
  deployer_principal_id          = local.principal_id
  deployer_principal_type        = local.principal_type

  # Key Vault integration (for App Config to resolve KV references)
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [
    azurerm_key_vault.main,
    azurerm_role_assignment.keyvault_admin,
  ]
}
