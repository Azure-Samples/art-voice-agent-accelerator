# ============================================================================
# CONTAINER APPS ENVIRONMENT OUTPUTS
# ============================================================================

output "container_environment_id" {
  description = "Container Apps Environment resource ID"
  value       = azurerm_container_app_environment.main.id
}

output "container_environment_name" {
  description = "Container Apps Environment name"
  value       = azurerm_container_app_environment.main.name
}

# ============================================================================
# FRONTEND CONTAINER APP OUTPUTS
# ============================================================================

output "frontend_container_app_name" {
  description = "Frontend Container App name"
  value       = azurerm_container_app.frontend.name
}

output "frontend_container_app_fqdn" {
  description = "Frontend Container App FQDN"
  value       = azurerm_container_app.frontend.ingress[0].fqdn
}

output "frontend_container_app_url" {
  description = "Frontend Container App URL"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

# ============================================================================
# BACKEND CONTAINER APP OUTPUTS
# ============================================================================

output "backend_container_app_name" {
  description = "Backend Container App name"
  value       = azurerm_container_app.backend.name
}

output "backend_container_app_fqdn" {
  description = "Backend Container App FQDN"
  value       = azurerm_container_app.backend.ingress[0].fqdn
}

output "backend_container_app_url" {
  description = "Backend Container App URL"
  value       = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}
