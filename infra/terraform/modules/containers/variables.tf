# ============================================================================
# SIMPLIFIED CONTAINER APPS MODULE VARIABLES
# ============================================================================

variable "name" {
  description = "The base name for resources"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region for resources"
  type        = string
}

variable "resource_token" {
  description = "Unique resource token for naming"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ============================================================================
# INFRASTRUCTURE DEPENDENCIES
# ============================================================================

variable "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID for container environment"
  type        = string
}

variable "container_registry_login_server" {
  description = "Container registry login server"
  type        = string
}

variable "frontend_identity_id" {
  description = "Frontend user-assigned managed identity ID"
  type        = string
}

variable "backend_identity_id" {
  description = "Backend user-assigned managed identity ID"
  type        = string
}

# ============================================================================
# FRONTEND CONFIGURATION
# ============================================================================

variable "frontend_config" {
  description = "Frontend container app configuration"
  type = object({
    target_port      = optional(number, 8080)
    min_replicas     = optional(number, 1)
    max_replicas     = optional(number, 10)
    cpu              = optional(number, 0.5)
    memory           = optional(string, "1.0Gi")
    default_image    = optional(string, "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest")
    azd_service_name = optional(string, "rtaudio-client-aca")
  })
  default = {}
}

variable "frontend_env_vars" {
  description = "Environment variables for frontend container"
  type = list(object({
    name        = string
    value       = optional(string)
    secret_name = optional(string)
  }))
  default = []
}

# ============================================================================
# BACKEND CONFIGURATION
# ============================================================================

variable "backend_config" {
  description = "Backend container app configuration"
  type = object({
    target_port      = optional(number, 8000)
    min_replicas     = optional(number, 1)
    max_replicas     = optional(number, 10)
    cpu              = optional(number, 1.0)
    memory           = optional(string, "2.0Gi")
    default_image    = optional(string, "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest")
    azd_service_name = optional(string, "rtaudio-server-aca")
  })
  default = {}
}

variable "backend_env_vars" {
  description = "Environment variables for backend container"
  type = list(object({
    name        = string
    value       = optional(string)
    secret_name = optional(string)
  }))
  default = []
}

# ============================================================================
# SECRETS CONFIGURATION
# ============================================================================

variable "secrets" {
  description = "Secrets for container apps"
  type = list(object({
    name                = string
    identity            = string
    key_vault_secret_id = string
  }))
  default = []
}
