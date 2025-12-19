# ============================================================================
# APP CONFIGURATION MODULE - VARIABLES (INFRASTRUCTURE ONLY)
# ============================================================================
# Application-tier settings (pools, connections, voice, monitoring, features)
# are now managed via /config/appconfig.json and synced by postprovision.sh
# ============================================================================

variable "name" {
  description = "Name for the App Configuration resource"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region for the App Configuration"
  type        = string
}

variable "environment_name" {
  description = "Environment name (dev, staging, prod) - used as label"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "sku" {
  description = "SKU for App Configuration (free or standard)"
  type        = string
  default     = "standard"
  validation {
    condition     = contains(["free", "standard"], var.sku)
    error_message = "SKU must be 'free' or 'standard'."
  }
}

# ============================================================================
# IDENTITY VARIABLES
# ============================================================================

variable "backend_identity_principal_id" {
  description = "Principal ID of the backend managed identity"
  type        = string
}

variable "frontend_identity_principal_id" {
  description = "Principal ID of the frontend managed identity"
  type        = string
}

variable "deployer_principal_id" {
  description = "Principal ID of the deployer (for admin access)"
  type        = string
}

variable "deployer_principal_type" {
  description = "Type of deployer principal (User or ServicePrincipal)"
  type        = string
  default     = "User"
}

# ============================================================================
# KEY VAULT INTEGRATION
# ============================================================================

variable "key_vault_id" {
  description = "Resource ID of the Key Vault for RBAC assignment"
  type        = string
}
