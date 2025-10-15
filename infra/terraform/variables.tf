# ============================================================================
# VARIABLES
# ============================================================================
variable "backend_api_public_url" {
  description = "Fully qualified URL to map to the backend API, requirement to allow ACS to validate and deliver webhook and WebSocket events (e.g., https://<app-name>.azurewebsites.net)."
  default     = null

  validation {
    condition     = var.backend_api_public_url == null || var.backend_api_public_url == "" || can(regex("^https://[^/]+$", var.backend_api_public_url))
    error_message = "Backend API public URL must start with 'https://' and must not have a trailing slash."
  }
}

variable "environment_name" {
  description = "Name of the environment that can be used as part of naming resource convention"
  type        = string
  validation {
    condition     = length(var.environment_name) >= 1 && length(var.environment_name) <= 64
    error_message = "Environment name must be between 1 and 64 characters."
  }
}
variable "acs_source_phone_number" {
  description = "Azure Communication Services phone number for outbound calls (E.164 format)"
  type        = string
  default     = null
  validation {
    condition     = var.acs_source_phone_number == null || can(regex("^\\+[1-9]\\d{1,14}$", var.acs_source_phone_number))
    error_message = "ACS source phone number must be in E.164 format (e.g., +1234567890) or null."
  }
}
variable "name" {
  description = "Base name for the real-time audio agent application"
  type        = string
  default     = "rtaudioagent"
  validation {
    condition     = length(var.name) >= 1 && length(var.name) <= 20
    error_message = "Name must be between 1 and 20 characters."
  }
}

variable "location" {
  description = "Primary location for all resources"
  type        = string
}

variable "openai_location" {
  description = "Optional secondary Azure OpenAI location to use if defined; will be prioritized over var.location for OpenAI resources."
  type        = string
  default     = null
}

variable "cosmosdb_location" {
  description = "Optional secondary Azure Cosmos DB location to use if defined; will be prioritized over var.location for Cosmos DB resources."
  type        = string
  default     = null
}

variable "cosmosdb_sku" {
  description = "SKU for Azure Cosmos DB (MongoDB Cluster)"
  type        = string
  default     = "M10"
}

variable "cosmosdb_public_network_access_enabled" {
  description = "Enable public network access for Cosmos DB (required for non-VNet deployments)"
  type        = bool
  default     = true
}

variable "principal_id" {
  description = "Principal ID of the user or service principal to assign application roles"
  type        = string
  default     = null
  sensitive   = true
}

variable "principal_type" {
  description = "Type of principal (User or ServicePrincipal)"
  type        = string
  default     = "User"
  validation {
    condition     = contains(["User", "ServicePrincipal"], var.principal_type)
    error_message = "Principal type must be either 'User' or 'ServicePrincipal'."
  }
}

variable "deployed_by" {
  description = "Identifier of the deployer (e.g., 'Full Name <email@domain>' or UPN). Used to tag resources for traceability."
  type        = string
  default     = null
}

variable "acs_data_location" {
  description = "Data location for Azure Communication Services"
  type        = string
  default     = "United States"
  validation {
    condition = contains([
      "United States", "Europe", "Asia Pacific", "Australia", "Brazil", "Canada",
      "France", "Germany", "India", "Japan", "Korea", "Norway", "Switzerland", "UAE", "UK"
    ], var.acs_data_location)
    error_message = "ACS data location must be a valid Azure Communication Services data location."
  }
}

variable "disable_local_auth" {
  description = "Disable local authentication and use Azure AD/managed identity only"
  type        = bool
  default     = true
}

variable "enable_redis_ha" {
  description = "Enable Redis Enterprise High Availability for production workloads"
  type        = bool
  default     = true
}

variable "redis_sku" {
  description = "SKU for Azure Managed Redis (Enterprise) optimized for performance"
  type        = string
  default     = "MemoryOptimized_M10"
  validation {
    condition = contains([
      "MemoryOptimized_M10", "MemoryOptimized_M20", "MemoryOptimized_M50",
      "MemoryOptimized_M100", "ComputeOptimized_X5", "ComputeOptimized_X10"
    ], var.redis_sku)
    error_message = "Redis SKU must be a valid Enterprise tier SKU."
  }
}

variable "redis_port" {
  description = "Port for Azure Managed Redis"
  type        = number
  default     = 10000
}

variable "model_deployments" {
  description = "Azure OpenAI model deployments optimized for high performance"
  type = list(object({
    name     = string
    version  = string
    sku_name = string
    capacity = number
  }))
  default = [
    {
      name     = "gpt-4o"
      version  = "2024-11-20"
      sku_name = "DataZoneStandard"
      capacity = 150
    },
    {
      name     = "gpt-4o-mini"
      version  = "2024-07-18"
      sku_name = "DataZoneStandard"
      capacity = 150
    },
    {
      name     = "gpt-4.1-mini"
      version  = "2025-04-14"
      sku_name = "DataZoneStandard"
      capacity = 150
    },
    {
      name     = "gpt-4.1"
      version  = "2025-04-14"
      sku_name = "DataZoneStandard"
      capacity = 150
    }
  ]
}

variable "mongo_database_name" {
  description = "Name of the MongoDB database"
  type        = string
  default     = "audioagentdb"
  validation {
    condition     = length(var.mongo_database_name) >= 1 && length(var.mongo_database_name) <= 64
    error_message = "MongoDB database name must be between 1 and 64 characters."
  }
}

variable "mongo_collection_name" {
  description = "Name of the MongoDB collection"
  type        = string
  default     = "audioagentcollection"
  validation {
    condition     = length(var.mongo_collection_name) >= 1 && length(var.mongo_collection_name) <= 64
    error_message = "MongoDB collection name must be between 1 and 64 characters."
  }
}

variable "container_app_min_replicas" {
  description = "Minimum number of container app replicas for high availability"
  type        = number
  default     = 5
  validation {
    condition     = var.container_app_min_replicas >= 1 && var.container_app_min_replicas <= 25
    error_message = "Container app min replicas must be between 1 and 25."
  }
}

variable "container_app_max_replicas" {
  description = "Maximum number of container app replicas for auto-scaling"
  type        = number
  default     = 50
  validation {
    condition     = var.container_app_max_replicas >= 1 && var.container_app_max_replicas <= 300
    error_message = "Container app max replicas must be between 1 and 300."
  }
}

variable "container_cpu_cores" {
  description = "CPU cores allocated to each container instance"
  type        = number
  default     = 2
  validation {
    condition     = contains([0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2], var.container_cpu_cores)
    error_message = "Container CPU cores must be one of: 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2"
  }
}

variable "container_memory_gb" {
  description = "Memory in GB allocated to each container instance"
  type        = string
  default     = "4.0Gi"
  validation {
    condition     = contains(["0.5Gi", "1.0Gi", "1.5Gi", "2.0Gi", "2.5Gi", "3.0Gi", "3.5Gi", "4.0Gi"], var.container_memory_gb)
    error_message = "Container memory must be between 0.5Gi and 4.0Gi in 0.5Gi increments."
  }
}

variable "aoai_pool_size" {
  description = "Size of the Azure OpenAI client pool for optimal performance"
  type        = number
  default     = 50
  validation {
    condition     = var.aoai_pool_size >= 5 && var.aoai_pool_size <= 200
    error_message = "AOAI pool size must be between 5 and 200."
  }
}

variable "tts_pool_size" {
  description = "Size of the TTS client pool for optimal performance"
  type        = number
  default     = 100
  validation {
    condition     = var.tts_pool_size >= 10 && var.tts_pool_size <= 500
    error_message = "TTS pool size must be between 10 and 500."
  }
}

variable "stt_pool_size" {
  description = "Size of the STT client pool for optimal performance"
  type        = number
  default     = 100
  validation {
    condition     = var.stt_pool_size >= 10 && var.stt_pool_size <= 500
    error_message = "STT pool size must be between 10 and 500."
  }

}
