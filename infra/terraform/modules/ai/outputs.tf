output "account_name" {
  description = "Name of the AI Foundry Account"
  value       = azapi_resource.ai_foundry_account.name
}

output "account_id" {
  description = "Resource ID of the AI Foundry account."
  value       = azapi_resource.ai_foundry_account.id
}

output "endpoint" {
  description = "Endpoint for the AI Foundry account. Use this endpoint for Speech services, Voice Live, Doc Intel, etc."
  value       = try(azapi_resource.ai_foundry_account.output.properties.endpoint, null)
}

output "project_endpoint" {
  description = "Endpoint for the AI Foundry project."
  value       = try(azapi_resource.ai_foundry_project.output.properties.endpoint, null)
}

output "openai_endpoint" {
  description = "Endpoint for the AI Foundry account. Use this endpoint for OpenAI services."
  value       = try(azapi_resource.ai_foundry_account.output.properties.endpoints["OpenAI Language Model Instance API"], null)
}

output "project_id" {
  description = "Resource ID of the AI Foundry project."
  value       = azapi_resource.ai_foundry_project.id
}

output "project_name" {
  description = "Name of the AI Foundry project."
  value       = azapi_resource.ai_foundry_project.name
}

output "project_identity_principal_id" {
  description = "Principal ID of the AI Foundry project managed identity."
  value       = try(azapi_resource.ai_foundry_project.output.identity.principalId, null)
}

output "location" {
  description = "Azure region of the AI Foundry account."
  value       = var.location
}