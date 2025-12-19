# ============================================================================
# APP CONFIGURATION MODULE - OUTPUTS
# ============================================================================

output "id" {
  description = "Resource ID of the App Configuration"
  value       = azurerm_app_configuration.main.id
}

output "name" {
  description = "Name of the App Configuration"
  value       = azurerm_app_configuration.main.name
}

output "endpoint" {
  description = "Endpoint URL of the App Configuration"
  value       = azurerm_app_configuration.main.endpoint
}

output "primary_read_key" {
  description = "Primary read-only access key (if local auth enabled)"
  value       = azurerm_app_configuration.main.primary_read_key
  sensitive   = true
}

output "identity_principal_id" {
  description = "Principal ID of the App Configuration's system-assigned managed identity"
  value       = azurerm_app_configuration.main.identity[0].principal_id
}

output "identity_tenant_id" {
  description = "Tenant ID of the App Configuration's system-assigned managed identity"
  value       = azurerm_app_configuration.main.identity[0].tenant_id
}

output "label" {
  description = "Environment label used for all configuration keys"
  value       = local.label
}
