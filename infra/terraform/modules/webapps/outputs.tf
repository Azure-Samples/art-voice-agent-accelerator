# ============================================================================
# FRONTEND WEB APP OUTPUTS
# ============================================================================

output "frontend_app_service_name" {
  description = "Frontend App Service name"
  value       = azurerm_linux_web_app.frontend.name
}

output "frontend_app_service_url" {
  description = "Frontend App Service URL"
  value       = "https://${azurerm_linux_web_app.frontend.default_hostname}"
}

output "frontend_app_service_hostname" {
  description = "Frontend App Service hostname"
  value       = azurerm_linux_web_app.frontend.default_hostname
}

# ============================================================================
# BACKEND WEB APP OUTPUTS
# ============================================================================

output "backend_app_service_name" {
  description = "Backend App Service name"
  value       = azurerm_linux_web_app.backend.name
}

output "backend_app_service_url" {
  description = "Backend App Service URL"
  value       = "https://${azurerm_linux_web_app.backend.default_hostname}"
}

output "backend_app_service_hostname" {
  description = "Backend App Service hostname"
  value       = azurerm_linux_web_app.backend.default_hostname
}

# ============================================================================
# SERVICE PLAN OUTPUTS
# ============================================================================

output "frontend_service_plan_id" {
  description = "Frontend Service Plan ID"
  value       = azurerm_service_plan.frontend.id
}

output "backend_service_plan_id" {
  description = "Backend Service Plan ID"
  value       = azurerm_service_plan.backend.id
}
