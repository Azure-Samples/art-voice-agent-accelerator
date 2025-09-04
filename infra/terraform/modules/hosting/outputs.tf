# ============================================================================
# COMMON OUTPUTS
# ============================================================================

output "hosting_platform" {
  description = "The hosting platform being used"
  value       = var.hosting_platform
}

# ============================================================================
# FRONTEND OUTPUTS
# ============================================================================

output "frontend_name" {
  description = "Frontend service name"
  value = var.hosting_platform == "containers" ? (
    length(module.containers) > 0 ? module.containers[0].frontend_container_app_name : null
    ) : (
    length(module.webapps) > 0 ? module.webapps[0].frontend_app_service_name : null
  )
}

output "frontend_url" {
  description = "Frontend service URL"
  value = var.hosting_platform == "containers" ? (
    length(module.containers) > 0 ? module.containers[0].frontend_container_app_url : null
    ) : (
    length(module.webapps) > 0 ? module.webapps[0].frontend_app_service_url : null
  )
}

output "frontend_hostname" {
  description = "Frontend service hostname"
  value = var.hosting_platform == "containers" ? (
    length(module.containers) > 0 ? module.containers[0].frontend_container_app_fqdn : null
    ) : (
    length(module.webapps) > 0 ? module.webapps[0].frontend_app_service_hostname : null
  )
}

# ============================================================================
# BACKEND OUTPUTS
# ============================================================================

output "backend_name" {
  description = "Backend service name"
  value = var.hosting_platform == "containers" ? (
    length(module.containers) > 0 ? module.containers[0].backend_container_app_name : null
    ) : (
    length(module.webapps) > 0 ? module.webapps[0].backend_app_service_name : null
  )
}

output "backend_url" {
  description = "Backend service URL"
  value = var.hosting_platform == "containers" ? (
    length(module.containers) > 0 ? module.containers[0].backend_container_app_url : null
    ) : (
    length(module.webapps) > 0 ? module.webapps[0].backend_app_service_url : null
  )
}

output "backend_hostname" {
  description = "Backend service hostname"
  value = var.hosting_platform == "containers" ? (
    length(module.containers) > 0 ? module.containers[0].backend_container_app_fqdn : null
    ) : (
    length(module.webapps) > 0 ? module.webapps[0].backend_app_service_hostname : null
  )
}

# ============================================================================
# PLATFORM-SPECIFIC OUTPUTS
# ============================================================================

# Container Apps specific outputs
output "container_environment_id" {
  description = "Container Apps Environment ID (only when using containers)"
  value = var.hosting_platform == "containers" ? (
    length(module.containers) > 0 ? module.containers[0].container_environment_id : null
  ) : null
}

output "container_environment_name" {
  description = "Container Apps Environment name (only when using containers)"
  value = var.hosting_platform == "containers" ? (
    length(module.containers) > 0 ? module.containers[0].container_environment_name : null
  ) : null
}

# App Service specific outputs
output "frontend_service_plan_id" {
  description = "Frontend Service Plan ID (only when using webapps)"
  value = var.hosting_platform == "webapps" ? (
    length(module.webapps) > 0 ? module.webapps[0].frontend_service_plan_id : null
  ) : null
}

output "backend_service_plan_id" {
  description = "Backend Service Plan ID (only when using webapps)"
  value = var.hosting_platform == "webapps" ? (
    length(module.webapps) > 0 ? module.webapps[0].backend_service_plan_id : null
  ) : null
}
