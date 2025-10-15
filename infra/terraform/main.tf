# ============================================================================
# TERRAFORM CONFIGURATION
# ============================================================================

terraform {
  required_version = ">= 1.1.7, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    azapi = {
      source = "Azure/azapi"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
  storage_use_azuread = true
}

provider "azuread" {}

provider "azapi" {
  skip_provider_registration = false
}

# ============================================================================
# DATA SOURCES
# ============================================================================

data "azuread_client_config" "current" {}

# ============================================================================
# RANDOM RESOURCES
# ============================================================================

resource "random_string" "resource_token" {
  length  = 8
  upper   = false
  special = false
}

# ============================================================================
# LOCALS & VARIABLES
# ============================================================================

locals {
  principal_id   = var.principal_id != null ? var.principal_id : data.azuread_client_config.current.object_id
  principal_type = var.principal_type
  # Generate a unique resource token
  resource_token = random_string.resource_token.result

  # Common tags
  tags = {
    "azd-env-name"    = var.environment_name
    "hidden-title"    = "Real Time Audio ${var.environment_name}"
    "project"         = "gbb-ai-audio-agent"
    "environment"     = var.environment_name
    "deployment"      = "terraform"
    "deployed_by"     = coalesce(var.deployed_by, local.principal_id)
    # To bypass Azure policy which enforces private networking configuration for nonprod environments
    "SecurityControl" = var.environment_name != "prod" ? "Ignore" : null
  }

  # Resource naming with Azure standard abbreviations
  # Following Azure Cloud Adoption Framework: https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations
  resource_names = {
    resource_group     = "rg-${var.name}-${var.environment_name}"
    app_service_plan   = "asp-${var.name}-${var.environment_name}-${local.resource_token}"
    key_vault          = "kv-${local.resource_token}"
    speech             = "spch-${var.environment_name}-${local.resource_token}"
    openai             = "oai-${local.resource_token}"
    cosmos             = "cosmos-${local.resource_token}"
    storage            = "st${local.resource_token}"
    redis              = "redis${local.resource_token}"
    acs                = "acs-${var.name}-${var.environment_name}-${local.resource_token}"
    container_registry = "cr${var.name}${local.resource_token}"
    log_analytics      = "log-${local.resource_token}"
    app_insights       = "ai-${local.resource_token}"
    container_env      = "cae-${var.name}-${var.environment_name}-${local.resource_token}"
    foundry_account    = "aif${var.name}${var.environment_name}"
    foundry_project    = "aif${var.name}${var.environment_name}proj"
  }

  foundry_project_display = "AI Foundry ${var.environment_name}"
  foundry_project_desc    = "AI Foundry project for ${var.environment_name} environment"
}
