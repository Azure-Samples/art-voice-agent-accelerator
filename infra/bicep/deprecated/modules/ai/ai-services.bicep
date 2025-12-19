//////////////////////////////////////////////
// AI Services Module
//
// This module creates an AI service resource using the CognitiveServices API,
// assigns a managed identity, and grants the OpenAI User role to specified clients.
//
// Supported AI Services:
//   • Azure Cognitive Services for OpenAI
//   • Azure Cognitive Services for Document Intelligence
//
// Parameters:
//   • location: The Azure region where the resource will be deployed.
//   • tags: An object representing the tags to apply to all resources.
//   • oaiModels: An array of OpenAI models to be deployed to the AI service.
//
// Outputs:
//   • aiServicesId: The resource ID of the created AI service.
//   • aiServicesName: The name of the AI service.
//   • aiServicesPrincipalId: The managed identity principal ID for the AI service.
//   • endpoints: An object with various endpoints for accessing the created service.
//////////////////////////////////////////////
import { ModelConfig, BackendConfigItem } from '../types.bicep'

@description('Azure region of the deployment.')
param location string

@description('Tags to add to the resources.')
param tags object


@description('Name of the AI service. Note: Only alphanumeric characters and no dashes used to ensure DNS compatibility.')
param name string

@description('If provided, the resource ID of the subnet to deploy the AI service with private endpoint.')
param servicesSubnetResourceId string = ''

@description('Resource ID of the Log Analytics workspace for diagnostics.')
param logAnalyticsWorkspaceResourceId string = ''

@allowed([
  'S0'
])
@description('AI service SKU. Only S0 is currently allowed.')
param sku string = 'S0'

param models ModelConfig[] = []

// Ensure hostname meets custom subdomain requirements: alphanumeric and hyphens only, 2-64 chars, no trailing hyphen
// Ensure name is not longer than 36 characters and has no trailing hyphens
var nameTrimmed = length(name) > 64 ? substring(name, 0, 64) : name
var aiServicesHostname =  replace(nameTrimmed, '-', '')
// Define the AI service resource with managed identity

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: aiServicesHostname
  location: location
  sku: {
    name: sku
  }
  kind: 'AIServices'
  properties: {
    publicNetworkAccess: empty(servicesSubnetResourceId) ? 'Enabled' : 'Disabled'
    disableLocalAuth: false
    customSubDomainName: aiServicesHostname
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
}

resource aiServicesDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceResourceId)) {
  name: '${aiServicesHostname}-diagnostics'
  scope: aiServices
  properties: {
    workspaceId: logAnalyticsWorkspaceResourceId
    logs: [
      {
        category: 'Audit'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
      {
        category: 'RequestResponse'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

// If a subnet is provided, create a private endpoint for the AI service
resource aiServicesPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-05-01' = if (!empty(servicesSubnetResourceId)) {
  name: '${aiServicesHostname}-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: servicesSubnetResourceId
    }
    privateLinkServiceConnections: [
      {
        name: '${aiServicesHostname}-plsc'
        properties: {
          privateLinkServiceId: aiServices.id
          groupIds: [ 'account' ]
        }
      }
    ]
  }
}

@batchSize(1)
resource modelDeployments 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = [ for m in models: {
  parent: aiServices
  name: m.name
  sku: {
    name: m.sku
    capacity: m.capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: m.name
      version: m.version
    }
    currentCapacity: m.capacity
  }
}]

// Outputs for integration and further automation
output id string = aiServices.id
output name string = aiServices.name
output principalId string = aiServices.identity.principalId
output key string = aiServices.listKeys().key1
output location string = aiServices.location
output endpoints object = aiServices.properties.endpoints
output modelDeployments array = [for (m, i) in models: {
  name: modelDeployments[i].name
  id: modelDeployments[i].id
  model: {
    name: m.name
    version: m.version
  }
  capacity: m.capacity
  sku: m.sku
  endpoint: '${aiServices.properties.endpoints['OpenAI Language Model Instance API']}/deployments/${modelDeployments[i].name}'
}]
