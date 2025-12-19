/*
=============================================================================
AI GATEWAY MODULE
=============================================================================

This module deploys AI Gateway infrastructure for real-time voice applications:
- Azure OpenAI Services with multiple model deployments and load balancing
- API Management (APIM) for gateway functionality, authentication, and policies
- Backend pools for high availability and load distribution
- Private endpoints for secure connectivity
- Role assignments for managed identity access
=============================================================================
*/

// ============================================================================
// TYPE IMPORTS
// ============================================================================

import { BackendConfigItem } from './modules/types.bicep'
import { lockType } from 'br/public:avm/utl/types/avm-common-types:0.4.1'

// ============================================================================
// CORE PARAMETERS
// ============================================================================

@minLength(1)
@maxLength(64)
@description('Base name for the AI Gateway resources')
param name string

@description('Azure region for resource deployment')
param location string = resourceGroup().location

@description('Environment identifier (dev, test, prod)')
param env string?

@description('Resource ID of Key Vault for storing secrets')
param keyVaultResourceId string

@description('Common tags to apply to all resources')
param tags object = {}

// ============================================================================
// AZURE OPENAI CONFIGURATION
// ============================================================================

@description('Array of backend configurations for Azure OpenAI services')
param backendConfig BackendConfigItem[]

@allowed(['S0'])
@description('SKU for Azure OpenAI services')
param aiSvcSku string = 'S0'

@description('Disable local authentication and use managed identity only')
param disableLocalAuth bool = true

@description('Name of the backend pool for OpenAI load balancing')
param oaiBackendPoolName string = 'openai-backend-pool'

// ============================================================================
// API MANAGEMENT CONFIGURATION
// ============================================================================

@description('Enable API Management for AI Services gateway functionality')
param enableAPIManagement bool = false

param apimPublicNetworkAccess bool = true

@allowed(['BasicV2', 'StandardV2'])
@description('SKU for API Management service')
param apimSku string = 'StandardV2'

@description('Email address of the API Management publisher')
param apimPublisherEmail string = 'noreply@microsoft.com'

@description('Name of the API Management publisher')
param apimPublisherName string = 'Microsoft'

@description('Named values for API Management configuration')
param namedValues array = []

@description('Logger configurations for API Management')
param loggers array = []

// ============================================================================
// AUTHENTICATION & AUTHORIZATION
// ============================================================================

@description('JWT audience claim value for token validation in APIM policies')
param audience string = ''

@description('Azure Entra ID group object ID for user authorization')
param entraGroupId string = ''

// ============================================================================
// IDENTITY & SECURITY
// ============================================================================

@description('Enable system-assigned managed identity')
param enableSystemAssignedIdentity bool = true

@description('Array of user-assigned managed identity resource IDs')
param userAssignedResourceIds array?

@description('Resource lock configuration')
param lock lockType = {
  name: null
  kind: env == 'prod' ? 'CanNotDelete' : 'None'
}

// ============================================================================
// NETWORKING CONFIGURATION
// ============================================================================

@allowed(['None', 'External', 'Internal'])
@description('Virtual network integration type for API Management')
param virtualNetworkType string

@description('Subnet resource ID for API Management integration')
param apimSubnetResourceId string = ''

@description('Subnet resource ID for private endpoints')
param privateEndpointSubnetId string = ''

@description('Private DNS zone resource ID for Azure OpenAI')
param aoaiDnsZoneId string = ''

// ============================================================================
// MONITORING & DIAGNOSTICS
// ============================================================================

@description('Diagnostic settings configuration for monitoring')
param diagnosticSettings array = []

// ============================================================================
// VARIABLES
// ============================================================================

var resourceSuffix = uniqueString(subscription().id, resourceGroup().id)

var formattedApimName = length('apim-${name}-${resourceSuffix}') <= 50
  ? 'apim-${name}-${resourceSuffix}'
  : 'apim-${substring(name, 0, 50 - length('apim--${resourceSuffix}'))}-${resourceSuffix}'

var openAIAPISpec = loadTextContent('./modules/apim/specs/azure-openai-2024-10-21.yaml')

var aoaiInboundXml = replace(
  replace(
    replace(
      replace(
        loadTextContent('./modules/apim/policies/openAI/inbound.xml'), 
        '{tenant-id}', 
        tenant().tenantId
      ), 
      '{backend-id}', 
      oaiBackendPoolName
    ),
    '{audience}',
    audience
  ),
  '{entra-group-id}',
  entraGroupId
)

// ============================================================================
// AZURE OPENAI SERVICES
// ============================================================================

@description('Deploy Azure OpenAI services with model deployments')
@batchSize(1)
module aiSvc 'br/public:avm/res/cognitive-services/account:0.11.0' = [for (backend, i) in backendConfig: {
  name: 'aiServices-${i}-${resourceSuffix}-${backend.location}'
  params: {
    // Core configuration
    kind: 'OpenAI'
    sku: aiSvcSku
    name: 'aisvc-${i}-${resourceSuffix}-${backend.location}'
    location: location
    customSubDomainName: 'aisvc-${i}-${resourceSuffix}-${backend.location}'
    
    // Security configuration
    disableLocalAuth: disableLocalAuth
    publicNetworkAccess: apimPublicNetworkAccess == true ? 'Enabled' : 'Disabled'
    
    // Model deployments
    deployments: [for model in backend.models: {
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
    }]
    
    // Key Vault integration (only if local auth is enabled)
    secretsExportConfiguration: disableLocalAuth ? null : {
      accessKey1Name: 'aisvc-${i}-${resourceSuffix}-${backend.location}-accessKey1'
      keyVaultResourceId: keyVaultResourceId
    }
    
    // Private networking
    privateEndpoints: !empty(privateEndpointSubnetId) && !empty(aoaiDnsZoneId) ? [
      {
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            {
              privateDnsZoneResourceId: aoaiDnsZoneId
            }
          ]
        }
        subnetResourceId: privateEndpointSubnetId
      }
    ] : []
    
    // Monitoring
    diagnosticSettings: diagnosticSettings
    tags: tags
  }
}]

// ============================================================================
// API MANAGEMENT SERVICE
// ============================================================================

@description('Deploy API Management service for AI Gateway functionality')
module apim 'br/public:avm/res/api-management/service:0.9.1' = if (enableAPIManagement) {
  name: formattedApimName
  params: {
    // Core configuration
    name: formattedApimName
    location: location
    sku: apimSku
    publisherEmail: apimPublisherEmail
    publisherName: apimPublisherName
    
    // Identity configuration
    managedIdentities: {
      systemAssigned: enableSystemAssignedIdentity
      userAssignedResourceIds: userAssignedResourceIds
    }
    
    // Networking
    virtualNetworkType: virtualNetworkType
    subnetResourceId: !empty(apimSubnetResourceId) ? apimSubnetResourceId : null
    

    // Configuration
    namedValues: namedValues
    loggers: loggers
    lock: lock
    
    // Backend services
    backends: [for (backend, i) in backendConfig: {
      name: backend.name
      tls: {
        validateCertificateChain: true
        validateCertificateName: false
      }
      url: '${aiSvc[i].outputs.endpoint}openai'
    }]
    
    // Initialize with empty APIs (configured separately)
    apis: []
    policies: []
    
    // Monitoring
    diagnosticSettings: diagnosticSettings
    tags: tags
  }
}

// ============================================================================
// API MANAGEMENT RESOURCES
// ============================================================================

// Get reference to deployed APIM service
resource apimService 'Microsoft.ApiManagement/service@2024-05-01' existing = if (enableAPIManagement) {
  name: formattedApimName
  dependsOn: [apim]
}

// Create backend pool for load balancing across OpenAI services
resource backendPool 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = if (enableAPIManagement) {
  name: oaiBackendPoolName
  parent: apimService
  properties: {
    description: 'Backend pool for Azure OpenAI load balancing'
    type: 'Pool'
    pool: {
      services: [for (backend, i) in backendConfig: {
        id: '/backends/${backend.name}'
        priority: backend.priority
        weight: min(backend.?weight ?? 10, 100)
      }]
    }
  }
}

// Create OpenAI API definition
resource openAiApi 'Microsoft.ApiManagement/service/apis@2022-08-01' = if (enableAPIManagement) {
  name: 'openai'
  parent: apimService
  properties: {
    displayName: 'OpenAI API'
    description: 'Azure OpenAI API for real-time voice applications'
    path: 'openai'
    protocols: ['https']
    subscriptionRequired: false // Use JWT instead
    subscriptionKeyParameterNames: {
      header: 'api-key'
      query: 'api-key'
    }
    format: 'openapi+json'
    value: openAIAPISpec
  }
}

// Create API subscription
resource aoaiSubscription 'Microsoft.ApiManagement/service/subscriptions@2024-06-01-preview' = if (enableAPIManagement) {
  name: 'openai-apim-subscription'
  parent: apimService
  properties: {
    allowTracing: true
    displayName: 'OpenAI API Subscription'
    scope: '/apis/${openAiApi.id}'
    state: 'active'
  }
}

// Apply inbound policy for authentication and load balancing
resource aoaiInboundPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-09-01-preview' = if (enableAPIManagement) {
  name: 'policy'
  parent: openAiApi
  properties: {
    format: 'rawxml'
    value: aoaiInboundXml
  }
}

// ============================================================================
// ROLE ASSIGNMENTS
// ============================================================================

// Grant APIM system identity access to AI services
resource apimAiDeveloperRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (enableAPIManagement && enableSystemAssignedIdentity) {
  name: guid(resourceGroup().id, apimService.id, 'Azure-AI-Developer')
  scope: resourceGroup()
  properties: {
    principalId: apimService.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '64702f94-c441-49e6-a78b-ef80e0188fee')
    principalType: 'ServicePrincipal'
  }
  dependsOn: [aiSvc, apim]
}

// ============================================================================
// OUTPUTS
// ============================================================================

@description('API Management service information')
output apim object = enableAPIManagement ? {
  name: apimService.name
  resourceId: apimService.id
  location: apimService.location
  sku: apimService.sku.name
  gatewayUrl: apimService.properties.gatewayUrl
  identity: apimService.identity
} : {}

@description('AI Gateway endpoints for application consumption')
output endpoints object = {
  openAI: enableAPIManagement 
    ? '${apimService.properties.gatewayUrl}/openai'
    : length(backendConfig) > 0 ? aiSvc[0].outputs.endpoints['OpenAI Language Model Instance API'] : ''
}

@description('Azure OpenAI service endpoints (direct access)')
output aiGatewayEndpoints array = [for (item, i) in backendConfig: aiSvc[i].outputs.endpoint]

@description('Azure OpenAI service resource IDs')
output aiGatewayServiceIds array = [for (item, i) in backendConfig: aiSvc[i].outputs.resourceId]

@description('Complete AI Services outputs for advanced integration scenarios')
output aiSvcOutputs array = [for (item, i) in backendConfig: aiSvc[i].outputs]

@description('API Management subscription key for OpenAI API access')
#disable-next-line outputs-should-not-contain-secrets
output openAiSubscriptionKey string = enableAPIManagement ? aoaiSubscription.listSecrets().primaryKey : ''
