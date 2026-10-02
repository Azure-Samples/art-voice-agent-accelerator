terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.81, < 5.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.10"
    }
  }
}

variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "resource_group_id" {
  type = string
}

variable "environment_id" {
  type = string
}

variable "private_link_location" {
  description = "AFD Private Link region, preferably the Container Apps region."
  type        = string
}

variable "private_link_request_message" {
  description = "Unpredictable per-deployment approval marker, never a publicly guessable profile name."
  type        = string
  sensitive   = true
}

variable "allowed_service_tags" {
  description = "Service tags permitted to access user-facing routes."
  type        = list(string)
  sensitive   = true
  validation {
    condition = (
      length(var.allowed_service_tags) > 0 &&
      length(var.allowed_service_tags) <= 10 &&
      alltrue([for tag in var.allowed_service_tags : can(regex("^[A-Za-z][A-Za-z0-9.]+$", tag))])
    )
    error_message = "Supply 1-10 nonempty service tag names, not CIDRs or wildcards."
  }
}

variable "origins" {
  type = map(object({
    hostname          = string
    health_probe_path = string
    allow_acs         = bool
  }))
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "log_analytics_workspace_id" {
  type = string
}
