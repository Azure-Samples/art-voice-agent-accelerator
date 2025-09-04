# ============================================================================
# HOSTING PLATFORM SELECTOR MODULE VARIABLES
# ============================================================================

variable "hosting_platform" {
  description = "The hosting platform to use: 'containers' or 'webapps'"
  type        = string
  default     = "containers"

  validation {
    condition     = contains(["containers", "webapps"], var.hosting_platform)
    error_message = "The hosting_platform value must be either 'containers' or 'webapps'."
  }
}

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
  description = "Log Analytics workspace ID"
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

# Container-specific variables
variable "container_registry_login_server" {
  description = "Container registry login server (required for containers)"
  type        = string
  default     = null
}

# ============================================================================
# ENVIRONMENT VARIABLES CONFIGURATION
# ============================================================================

variable "frontend_env_vars" {
  description = "Environment variables for frontend"
  type = list(object({
    name        = string
    value       = optional(string)
    secret_name = optional(string)
  }))
  default = []
}

variable "backend_env_vars" {
  description = "Environment variables for backend"
  type = list(object({
    name        = string
    value       = optional(string)
    secret_name = optional(string)
  }))
  default = []
}

# Secrets for containers
variable "secrets" {
  description = "Secrets for container apps (only used with containers platform)"
  type = list(object({
    name                = string
    identity            = string
    key_vault_secret_id = string
  }))
  default = []
}

# ============================================================================
# PLATFORM-SPECIFIC CONFIGURATION
# ============================================================================

variable "frontend_config" {
  description = "Frontend application configuration"
  type = object({
    # Common settings
    port             = optional(number, 8080)
    azd_service_name = optional(string, "rtaudio-client")

    # Container-specific
    min_replicas  = optional(number, 1)
    max_replicas  = optional(number, 10)
    cpu           = optional(number, 0.5)
    memory        = optional(string, "1.0Gi")
    default_image = optional(string, "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest")

    # WebApp-specific
    sku_name          = optional(string, "B1")
    node_version      = optional(string, "22-lts")
    app_command_line  = optional(string, "npm run build && npm run start")
    always_on         = optional(bool, true)
    use_32_bit_worker = optional(bool, false)
    ftps_state        = optional(string, "Disabled")
    http2_enabled     = optional(bool, true)
  })
  default = {}
}

variable "backend_config" {
  description = "Backend application configuration"
  type = object({
    # Common settings
    port             = optional(number, 8000)
    azd_service_name = optional(string, "rtaudio-server")

    # Container-specific
    min_replicas  = optional(number, 1)
    max_replicas  = optional(number, 10)
    cpu           = optional(number, 1.0)
    memory        = optional(string, "2.0Gi")
    default_image = optional(string, "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest")

    # WebApp-specific
    sku_name         = optional(string, "B1")
    python_version   = optional(string, "3.11")
    app_command_line = optional(string, "python -m uvicorn apps.rtagent.backend.main:app --host 0.0.0.0 --port 8000")
    always_on        = optional(bool, true)
  })
  default = {}
}

# ============================================================================
# CORS AND LOGGING CONFIGURATION
# ============================================================================

variable "frontend_cors_origins" {
  description = "CORS allowed origins for frontend"
  type        = list(string)
  default     = ["*"]
}

variable "backend_cors_origins" {
  description = "CORS allowed origins for backend"
  type        = list(string)
  default     = ["*"]
}

variable "cors_support_credentials" {
  description = "Whether CORS should support credentials"
  type        = bool
  default     = false
}

variable "enable_diagnostics" {
  description = "Whether to enable diagnostic settings"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Log retention in days"
  type        = number
  default     = 7
}

variable "log_retention_mb" {
  description = "Log retention in MB"
  type        = number
  default     = 35
}
