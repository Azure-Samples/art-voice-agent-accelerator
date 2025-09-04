@description('Azure region for all resources.')
param location string

@description('Tags to apply to all resources.')
param tags object = {}

@description('A unique string used to generate resource names. Defaults to a unique string based on resource group ID for uniqueness.')
param resourceToken string = uniqueString(resourceGroup().id)

@description('Name of the existing Key Vault where secrets will be stored.')
param keyVaultName string

@description('Specifies whether public network access is enabled for Speech Service. Set to "Disabled" to rely on private networking (Private Endpoints need to be configured separately).')
@allowed([
  'Enabled'
  'Disabled'
])
param speechPublicNetworkAccess string = 'Enabled'

@description('Data location for Azure Communication Services (e.g., "UnitedStates", "Europe", "AsiaPacific"). This cannot be changed after the resource is created.')
param acsDataLocation string = 'UnitedStates'

@description('Specifies whether public network access is enabled for Communication Services. Set to "Disabled" to rely on private networking (Private Endpoints need to be configured separately).')
@allowed([
  'Enabled'
  'Disabled'
])
param acsPublicNetworkAccess string = 'Enabled'

@description('Specifies whether public network access is enabled for AI Services. Set to "Disabled" to rely on private networking (Private Endpoints need to be configured separately).')
@allowed([
  'Enabled'
  'Disabled'
])
param aiServicesPublicNetworkAccess string = 'Enabled'

@description('SKU name for Speech Service. Default is S0.')
param speechSkuName string = 'S0'

@description('SKU name for AI Services. Default is S0.')
param aiServicesSkuName string = 'S0'

// --- Existing Resources ---
@description('Reference to the existing Key Vault. The deploying principal needs "Key Vault Secrets Officer" or equivalent permissions to write secrets.')
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// --- Azure Speech Service ---
@description('Deploys Azure Speech Service.')
module speechService 'br/public:avm/res/cognitive-services/account:0.4.0' = {
  name: 'deploy-speech-${toLower(resourceToken)}' // Module instance name
  params: {
    name: 'speech-${toLower(resourceToken)}' // Azure resource name
    location: location
    tags: tags
    kind: 'SpeechServices'
    sku: speechSkuName
    publicNetworkAccess: speechPublicNetworkAccess
    // Note: If publicNetworkAccess is 'Disabled', Private Endpoints must be configured separately for connectivity.
    managedIdentities: {
      systemAssigned: true
    }
  }
}

@description('Stores Speech Service key in Key Vault.')
resource speechServiceKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'speechServiceKey-${toLower(resourceToken)}'
  properties: {
    value: speechService // Primary key
    attributes: {
      enabled: true
    }
    contentType: 'text/plain'
  }
}

// --- Azure Communication Services ---
@description('Deploys Azure Communication Services.')
module acs 'br/public:avm/res/communication/communication-service:0.3.0' = {
  name: 'deploy-acs-${toLower(resourceToken)}'
  params: {
    name: 'acs-${toLower(resourceToken)}'
    location: location
    tags: tags
    dataLocation: acsDataLocation

  }
}

@description('Creates a source phone number for ACS (purchased number).')
resource acsPhoneNumber 'Microsoft.Communication/communicationServices/phonenumbers@2023-04-01-preview' = {
  name: '${acs.name}/sourcephonenumber'
  location: location
  properties: {
    phoneNumberType: 'TollFree' // or 'Geographic', adjust as needed
    assignmentType: 'Application'
    capabilities: {
      calling: 'InboundOutbound'
      sms: 'InboundOutbound'
    }
    // You may need to specify region, areaCode, and other regulatory properties depending on your scenario.
  }
}

// --- Azure AI Services (Cognitive Services Account - Multi-service) ---
@description('Deploys Azure AI Services (multi-service account).')
module aiServices 'br/public:avm/res/cognitive-services/account:0.4.0' = {
  name: 'deploy-aiservices-${toLower(resourceToken)}' // Module instance name
  params: {
    name: 'aisvc-${toLower(resourceToken)}' // Azure resource name
    location: location
    tags: tags
    kind: 'AIServices' // Use 'CognitiveServices' for traditional multi-service account if 'AIServices' is not desired.
    sku: {
      name: aiServicesSkuName
    }
    publicNetworkAccess: aiServicesPublicNetworkAccess
    // Note: If publicNetworkAccess is 'Disabled', Private Endpoints must be configured separately for connectivity.
  }
}

@description('Stores AI Services key in Key Vault.')
resource aiServicesKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'aiServicesKey-${toLower(resourceToken)}'
  properties: {
    value: aiServices.outputs.keys[0].value // Primary key
    attributes: {
      enabled: true
    }
    contentType: 'text/plain'
  }
}

// --- Outputs ---
@description('Name of the deployed Speech Service.')
output speechServiceName string = speechService.outputs.name

@description('Endpoint of the deployed Speech Service.')
output speechServiceEndpoint string = speechService.outputs.endpoint

@description('URI of the Speech Service key stored in Key Vault.')
output speechServiceKeySecretUri string = speechServiceKeySecret.properties.secretUriWithVersion

@description('Resource ID of the deployed Speech Service.')
output speechServiceResourceId string = speechService.outputs.resourceId

@description('Name of the deployed Azure Communication Services.')
output acsName string = acs.outputs.name

@description('Endpoint of the deployed Azure Communication Services.')
output acsEndpoint string = acs.outputs.endpoint

@description('URI of the ACS primary key stored in Key Vault.')
output acsPrimaryKeySecretUri string = acsPrimaryKeySecret.properties.secretUriWithVersion

@description('Resource ID of the deployed Azure Communication Services.')
output acsResourceId string = acs.outputs.resourceId

@description('Name of the deployed Azure AI Services account.')
output aiServicesName string = aiServices.outputs.name

@description('Endpoint of the deployed Azure AI Services account.')
output aiServicesEndpoint string = aiServices.outputs.endpoint

@description('URI of the AI Services key stored in Key Vault.')
output aiServicesKeySecretUri string = aiServicesKeySecret.properties.secretUriWithVersion

@description('Resource ID of the deployed Azure AI Services account.')
output aiServicesResourceId string = aiServices.outputs.resourceId

