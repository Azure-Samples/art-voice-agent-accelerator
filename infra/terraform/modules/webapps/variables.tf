# ============================================================================
# SIMPLIFIED WEB APPS MODULE VARIABLES
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
  description = "Log Analytics workspace ID for diagnostics"
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
  description = "Frontend web app configuration"
  type = object({
    sku_name          = optional(string, "B1")
    node_version      = optional(string, "22-lts")
    port              = optional(number, 8080)
    app_command_line  = optional(string, "npm run build && npm run start")
    azd_service_name  = optional(string, "rtaudio-client")
    always_on         = optional(bool, true)
    use_32_bit_worker = optional(bool, false)
    ftps_state        = optional(string, "Disabled")
    http2_enabled     = optional(bool, true)
  })
  default = {}
}

variable "frontend_app_settings" {
  description = "App settings for frontend web app"
  type        = map(string)
  default     = {}
}

# ============================================================================
# BACKEND CONFIGURATION
# ============================================================================

variable "backend_config" {
  description = "Backend web app configuration"
  type = object({
    sku_name         = optional(string, "B1")
    python_version   = optional(string, "3.11")
    port             = optional(number, 8000)
    app_command_line = optional(string, "python -m uvicorn apps.rtagent.backend.main:app --host 0.0.0.0 --port 8000")
    azd_service_name = optional(string, "rtaudio-server")
    always_on        = optional(bool, true)
  })
  default = {}
}

variable "backend_app_settings" {
  description = "App settings for backend web app"
  type        = map(string)
  default     = {}
}

# ============================================================================
# CORS CONFIGURATION
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

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

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
