/*
  Enhanced AI Services Module
  
  This module deploys Azure AI Services (OpenAI) with:
  - Multiple model deployments from models array
  - Private endpoint support
  - Managed identity configuration
  - Network security controls
  - Comprehensive monitoring and diagnostics
*/

import { ModelDeployment } from '../types.bicep'

// Core Parameters
@description('The name of the AI Services resource')
@minLength(3)
@maxLength(64)
param name string

@description('The location where the AI Services will be deployed')
param location string

@description('The SKU for the AI Services resource')
@allowed(['S0', 'S1'])
param sku string = 'S0'

@description('Tags to apply to all resources')
param tags object = {}

// Model Configuration - Updated to accept array directly
@description('Array of models to deploy')
param models ModelDeployment[]

// Security Configuration
@description('Enable private endpoint for the AI Services')
param enablePrivateEndpoint bool = false

@description('Subnet resource ID for private endpoint')
param servicesSubnetResourceId string = ''

@description('Custom subdomain name for the AI Services endpoint')
param customSubdomainName string = ''

@description('Network ACLs configuration')
param networkAcls object = {
  defaultAction: 'Allow'
  ipRules: []
  virtualNetworkRules: []
}

// Monitoring Configuration
@description('Diagnostic settings configuration')
param diagnosticSettings array = []

// Key Vault Configuration
@description('Key Vault resource ID for storing API keys')
param keyVaultResourceId string = ''
param kind string = 'OpenAI'

param privateDNSZoneResourceId string = ''

// Variables
var uniqueSuffix = uniqueString(subscription().id, resourceGroup().id, name)
var _aiSvcName = length(name) > 50 ? '${substring(name, 0, 50)}-${uniqueSuffix}' : name
var defaultSubdomainName = 'oai-${uniqueSuffix}'

param disableLocalAuth bool = true // Keep enabled for now, can be disabled in prod

// AI Services Resource
// resource _aiSvc 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
//   name: _aiSvcName
//   location: location
//   tags: tags
//   kind: 'OpenAI'
//   sku: {
//     name: sku
//   }
//   identity: {
//     type: 'SystemAssigned'
//   }
//   properties: {
//     customSubDomainName: !empty(customSubdomainName) ? customSubdomainName : defaultSubdomainName
//     publicNetworkAccess: enablePrivateEndpoint ? 'Disabled' : 'Enabled'
//     networkAcls: networkAcls
//     disableLocalAuth: false // Keep enabled for now, can be disabled in prod
//     restrictOutboundNetworkAccess: false
//     apiProperties: {
//       statisticsEnabled: false
//     }
//   }
// }
module aiSvc 'br/public:avm/res/cognitive-services/account:0.11.0' = {
  name: 'accountDeployment'
  params: {
    // Required parameters
    kind: kind
    name: _aiSvcName
    // Non-required parameters
    disableLocalAuth: disableLocalAuth
    location: location
    secretsExportConfiguration: {
      accessKey1Name: 'aisvc-${_aiSvcName}-accessKey1'
      keyVaultResourceId: keyVaultResourceId
    }
    deployments: [ for model in models: {
        model: {
          format: 'OpenAI'
          name: model.name
          version: model.version
        }
        name: model.name
        sku: {
          name: model.sku
          capacity: model.capacity
        }
      }
    ]
    privateEndpoints:[
      {
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            {
              privateDnsZoneResourceId: privateDNSZoneResourceId
            }
            {
              privateDnsZoneResourceId: '<privateDnsZoneResourceId>'
            }
          ]
        }
        subnetResourceId: '<subnetResourceId>'
      }
    ]
    publicNetworkAccess: 'Disabled'
  }
}

resource _aiSvc 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' existing = {
  name: _aiSvcName
}

// Model Deployments - Deploy each model from the models array
@batchSize(1)
resource deployments 'Microsoft.CognitiveServices/accounts/deployments@2023-10-01-preview' = [for (model, i) in models: {
  parent: _aiSvc
  name: model.name
  sku: {
    name: model.sku
    capacity: model.capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: contains(model.name, 'gpt-4o') ? 'gpt-4o' : contains(model.name, 'gpt-4') ? 'gpt-4' : contains(model.name, 'gpt-35') ? 'gpt-35-turbo' : model.name
      version: model.version
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
    raiPolicyName: 'Microsoft.Default'
  }
}]

// Private Endpoint (if enabled)
module privateEndpoint '../networking/private-endpoint.bicep' = if (enablePrivateEndpoint && !empty(servicesSubnetResourceId)) {
  name: '${name}-private-endpoint'
  params: {
    name: 'pe-${_aiSvcName}'
    location: location
    tags: tags
    privateLinkServiceId: _aiSvc.id
    groupIds: ['account']
    subnetResourceId: servicesSubnetResourceId
    privateDnsZoneName: 'privatelink.openai.azure.com'
  }
}

// Diagnostic Settings
resource diagnosticSetting 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = [for (setting, i) in diagnosticSettings: {
  scope: _aiSvc
  name: '${setting.?name ?? 'diag'}-${_aiSvcName}'
  properties: {
    workspaceId: setting.?workspaceResourceId
    logs: setting.?logs ?? [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: setting.?metrics ?? [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}]


// Outputs
@description('The name of the AI Services resource')
output name string = _aiSvc.name

@description('The resource ID of the AI Services')
output id string = _aiSvc.id

@description('The location of the AI Services')
output location string = _aiSvc.location

@description('The principal ID of the system-assigned managed identity')
output principalId string = _aiSvc.identity.principalId

@description('AI Services endpoints')
output endpoints object = {
  'OpenAI Language Model Instance API': 'https://${_aiSvc.properties.endpoint}'
  custom: 'https://${_aiSvc.properties.customSubDomainName}.openai.azure.com'
}

@description('Model deployment information')
output modelDeployments array = [for (model, i) in models: {
  name: deployments[i].name
  model: model.name
  version: model.version
  capacity: model.capacity
  sku: model.sku
  endpoint: 'https://${_aiSvc.properties.endpoint}/openai/deployments/${deployments[i].name}'
}]

@description('Private endpoint information')
output privateEndpoint object = enablePrivateEndpoint && !empty(servicesSubnetResourceId) ? {
  id: privateEndpoint.outputs.privateEndpointId
  name: privateEndpoint.outputs.privateEndpointName
  ipAddress: privateEndpoint.outputs.privateIpAddress
} : {}


output keyVaultSecretReferences object = aiSvc.outputs.exportedSecrets
