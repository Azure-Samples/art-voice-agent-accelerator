@description('The name of the Communication Service resource')
param communicationServiceName string

@description('The data location for the Communication Service')
@allowed([
  'Africa'
  'Asia Pacific'
  'Australia'
  'Brazil'
  'Canada'
  'Europe'
  'France'
  'Germany'
  'India'
  'Japan'
  'Korea'
  'Norway'
  'Switzerland'
  'UAE'
  'UK'
  'United States'
])
param dataLocation string = 'United States'

@description('Diagnostic settings configuration for the Communication Service')
param diagnosticSettings object = {}

@description('Tags to apply to the Communication Service resource')
param tags object = {}

// ============================================================================
// COMMUNICATION SERVICE
// ============================================================================

@description('Azure Communication Services resource')
resource communicationService 'Microsoft.Communication/CommunicationServices@2023-04-01-preview' = {
  name: communicationServiceName
  location: 'global' // Communication Services is always deployed globally
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dataLocation: dataLocation
  }
}

// ============================================================================
// DIAGNOSTIC SETTINGS
// ============================================================================

@description('Diagnostic settings for the Communication Service')
resource communicationServiceDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(diagnosticSettings)) {
  name: '${communicationService.name}-diagnostic-settings'
  scope: communicationService
  properties: {
    workspaceId: diagnosticSettings.?workspaceResourceId
    storageAccountId: diagnosticSettings.?storageAccountResourceId
    eventHubAuthorizationRuleId: diagnosticSettings.?eventHubAuthorizationRuleResourceId
    eventHubName: diagnosticSettings.?eventHubName
    logs: diagnosticSettings.?logs ?? [
      {
      categoryGroup: 'allLogs'
      enabled: true
      retentionPolicy: {
        enabled: false
        days: 0
      }
      }
    ]
    metrics: diagnosticSettings.?metrics ?? [
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

// ============================================================================
// OUTPUTS
// ============================================================================

@description('The endpoint URL of the Communication Service')
output endpoint string = 'https://${communicationService.properties.hostName}'

@description('The name of the Communication Service resource')
output communicationServiceName string = communicationService.name

@description('The location where the Communication Service is deployed')
output location string = communicationService.location

@description('The primary key for the Communication Service')
#disable-next-line outputs-should-not-contain-secrets
output primaryKey string = communicationService.listKeys().primaryKey

@description('The primary connection string for the Communication Service')
#disable-next-line outputs-should-not-contain-secrets
output connectionString string = communicationService.listKeys().primaryConnectionString

@description('The principal ID of the system-assigned managed identity')
output managedIdentityPrincipalId string = communicationService.identity.principalId

@description('The client ID of the system-assigned managed identity')
output managedIdentityClientId string = communicationService.identity.tenantId
