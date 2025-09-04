// ============================================================================
// DEPLOYMENT METADATA & SCOPE
// ============================================================================

targetScope = 'subscription'

// ============================================================================
// CORE PARAMETERS
// ============================================================================

@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resource convention')
param environmentName string

@minLength(1)
@maxLength(20)
@description('Base name for the real-time audio agent application')
param name string = 'rtaudioagent'

@minLength(1)
@description('Primary location for all resources')
param location string

// ============================================================================
// TYPE IMPORTS
// ============================================================================

import { SubnetConfig, BackendConfigItem } from './modules/types.bicep'

// ============================================================================
// APPLICATION CONFIGURATION
// ============================================================================

// AZD Managed parameters for real-time audio application
@description('(AZD Managed) Flag indicating if the real-time audio client application exists and should be deployed')
param rtaudioClientExists bool

@description('(AZD Managed) Flag indicating if the real-time audio server application exists and should be deployed')
param rtaudioServerExists bool

@description('(AZD Managed) ACS phone number for real-time audio communication')
param acsSourcePhoneNumber string =''

// Managed with AZD (for non-Premium SKUs only):
// - To disable PublicNetworkAccess, APIM requires a private endpoint resource to be attached
// - This requires apim to be created first, then private endpoint, then disabling the network access
// - Manage this with AZD - post provision script:
//  - set the PublicNetworkAccess attribute to false
//  - disable the public network access via cli
@description('Enable public network access for API Management')
param apimPublicNetworkAccess bool = true
// ============================================================================
@description('Enable API Management for OpenAI load balancing and gateway functionality')
param enableAPIManagement bool = true

@description('Array of backend configurations for Azure OpenAI services when API Management is enabled')
param azureOpenAIBackendConfig BackendConfigItem[]

@description('SKU for Azure Managed Redis')
param redisSku string = 'MemoryOptimized_M10' 

@allowed(['United States', 'Europe', 'Asia Pacific', 'Australia', 'Brazil', 'Canada', 'France', 'Germany', 'India', 'Japan', 'Korea', 'Norway', 'Switzerland', 'UAE', 'UK'])
@description('Data location for Azure Communication Services')
param acsDataLocation string = 'United States'

// ============================================================================
// SECURITY & IDENTITY
// ============================================================================

@description('Principal ID of the user or service principal to assign application roles')
param principalId string

@allowed(['User', 'ServicePrincipal'])
@description('Type of principal (User or ServicePrincipal)')
param principalType string = 'User'

@description('Disable local authentication and use Azure AD/managed identity only')
param disableLocalAuth bool = true

@allowed(['standard', 'premium'])
@description('SKU for Azure Key Vault (standard or premium)')
param vaultSku string = 'standard'

// API Management authentication parameters
// These parameters configure APIM policies for JWT validation and authorization

// Currently commented out of the policy to simplify initial provisioning steps
// The expected audience claim value in JWT tokens for API access validation
// This should match the audience configured in your identity provider
// @description('The JWT audience claim value used for token validation in APIM policies')
// param jwtAudience string = ''

// The Azure Entra ID group object ID that grants access to the API
// Users must be members of this group to access protected endpoints
@description('Azure Entra ID group object ID for user authorization in APIM policies')
param entraGroupId string = ''

// ============================================================================
// NETWORK CONFIGURATION
// ============================================================================

@description('Name of the hub virtual network')
param hubVNetName string = 'vnet-hub-${name}-${environmentName}'

@description('Name of the spoke virtual network')
param spokeVNetName string = 'vnet-spoke-${name}-${environmentName}'

@description('Address prefix for the hub virtual network (CIDR notation)')
param hubVNetAddressPrefix string = '10.0.0.0/16'

@description('Address prefix for the spoke virtual network (CIDR notation)')
param spokeVNetAddressPrefix string = '10.1.0.0/16'

@description('Enable network isolation for all applicable Azure services')
param networkIsolation bool = true

param enableRedisHA bool = false
// Jumphost config
@secure()
param jumphostVmPassword string = ''
// ============================================================================
// CONSTANTS & COMPUTED VALUES
// ============================================================================

// Load Azure naming abbreviations for consistent resource naming
var abbrs = loadJsonContent('./abbreviations.json')

// Generate unique resource token based on subscription, environment, and location
var resourceToken = uniqueString(subscription().id, environmentName, location)


// APPLICATION GATEWAY CONFIGURATION PARAMETERS
@description('Enable Application Gateway deployment')
param enableApplicationGateway bool = true

@description('Application Gateway name (will be auto-generated if not provided)')
param applicationGatewayName string = ''

@description('Application Gateway FQDN for SSL certificate')
param domainFqdn string = ''

@description('Enable SSL certificate from Key Vault')
param enableSslCertificate bool = true

@description('Key Vault secret ID for SSL certificate')
@secure()
param sslCertificateKeyVaultSecretId string = ''

@description('User identity resource ID for Key Vault secret access to be assigned to the AppGW')
@secure()
param keyVaultSecretUserIdentity string = ''


@description('Enable Web Application Firewall')
param enableWaf bool = true

@description('WAF mode (Detection or Prevention)')
@allowed(['Detection', 'Prevention'])
param wafMode string = 'Detection'

@description('Application Gateway minimum capacity')
@minValue(1)
@maxValue(32)
param applicationGatewayMinCapacity int = 2

@description('Application Gateway maximum capacity')
@minValue(1)
@maxValue(32)
param applicationGatewayMaxCapacity int = 10



// ============================================================================
// VARIABLES (add after existing variables section)
// ============================================================================
var tags = {
  'azd-env-name': environmentName
  'hidden-title': 'Real Time Audio ${environmentName}'
}

// ============================================================================
// RESOURCE GROUPS
// ============================================================================
resource hubRg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-hub-${substring(name, 0, min(length(name), 20))}-${substring(environmentName, 0, min(length(environmentName), 10))}'
  location: location
  tags: tags
}

resource spokeRg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-spoke-${substring(name, 0, min(length(name), 20))}-${substring(environmentName, 0, min(length(environmentName), 10))}'
  location: location
  tags: tags
}


param hubSubnets SubnetConfig[] = [
  {
    name: 'loadBalancer'          // App Gateway subnet
    addressPrefix: '10.0.0.0/27'
    securityRules: [
      // Required inbound rules for Application Gateway v2
      {
        name: 'AllowHTTPSInbound'
        properties: {
          priority: 1000
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowHTTPInbound'
        properties: {
          priority: 1010
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'
        }
      }
      {
        name: 'AllowGatewayManagerInbound'
        properties: {
          priority: 1020
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'GatewayManager'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '65200-65535'
        }
      }
      {
        name: 'AllowAzureLoadBalancerInbound'
        properties: {
          priority: 1030
          protocol: '*'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'AzureLoadBalancer'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
      {
        name: 'AllowAzureInfrastructureInbound'
        properties: {
          priority: 1040
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '65503-65534'
        }
      }
      // Required outbound rules for Application Gateway v2
      {
        name: 'AllowInternetOutbound'
        properties: {
          priority: 1000
          protocol: '*'
          access: 'Allow'
          direction: 'Outbound'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '*'
        }
      }
    ]
  }
  {
    name: 'services'              // Shared services like monitor, orchestrators
    addressPrefix: '10.0.0.64/26'
  }
  {
    name: 'jumpbox'               // Optional, minimal size
    addressPrefix: '10.0.10.0/27'
  }
  {
    name: 'apim'
    addressPrefix: '10.0.1.0/27'
    delegations: [
      {
        name: 'Microsoft.Web/serverFarms'
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
    securityRules: [
      {
        name: 'AllowHTTPS'
        properties: {
          priority: 1000
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowHTTP'
        properties: {
          priority: 1010
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'
        }
      }
      {
        name: 'AllowAPIMManagement'
        properties: {
          priority: 1020
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'ApiManagement'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '3443'
        }
      }
      {
        name: 'AllowLoadBalancer'
        properties: {
          priority: 1030
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'AzureLoadBalancer'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '6390'
        }
      }
      {
        name: 'AllowOutboundHTTPS'
        properties: {
          priority: 1000
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Outbound'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowOutboundHTTP'
        properties: {
          priority: 1010
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Outbound'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '80'
        }
      }
    ]
  }
]

param spokeSubnets SubnetConfig[] = [
  {
    name: 'privateEndpoint'       // PE for Redis, Cosmos, Speech, Blob
    addressPrefix: '10.1.0.0/26'
  }
  {
    name: 'app'        // Real-time agents, FastAPI, containers
    addressPrefix: '10.1.10.0/23'
    delegations: [
      {
        name: 'Microsoft.App/environments'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
  {
    name: 'cache'                 // Redis workers (can be merged into `app` if simple)
    addressPrefix: '10.1.2.0/26'
  }
]

// ============================================================================
// APPLICATION GATEWAY
// ============================================================================
// Application Gateway name generation
var generatedApplicationGatewayName = !empty(applicationGatewayName) ? applicationGatewayName : '${abbrs.networkApplicationGateways}${name}-${environmentName}'

// PUBLIC IP FOR APPLICATION GATEWAY
module applicationGatewayPublicIp 'br/public:avm/res/network/public-ip-address:0.6.0' = if (enableApplicationGateway) {
  scope: hubRg
  name: 'appgw-public-ip'
  params: {
    name: '${abbrs.networkPublicIPAddresses}${generatedApplicationGatewayName}'
    location: location
    tags: tags
    skuName: 'Standard'
    publicIPAllocationMethod: 'Static'
    // Only set dnsSettings if we have a valid FQDN
    dnsSettings: !empty(domainFqdn) ? {
      domainNameLabel: split(domainFqdn, '.')[0]
      domainNameLabelScope: 'TenantReuse'
    } : {
      domainNameLabel: '${generatedApplicationGatewayName}-${resourceToken}'
      domainNameLabelScope: 'TenantReuse'
    }
  }
}

// MANAGED IDENTITY FOR APPLICATION GATEWAY
module applicationGatewayIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.0' = if (enableApplicationGateway && enableSslCertificate) {
  scope: hubRg
  name: 'appgw-identity'
  params: {
    name: '${abbrs.managedIdentityUserAssignedIdentities}${generatedApplicationGatewayName}'
    location: location
    tags: tags
  }
}

module applicationGateway 'appgw.bicep' = if (enableApplicationGateway) {
  scope: hubRg
  name: 'application-gateway'
  params: {
    // Basic configuration
    applicationGatewayName: generatedApplicationGatewayName
    location: location
    tags: tags
    
    // Network configuration
    subnetResourceId: hubNetwork.outputs.subnets.loadBalancer
    publicIpResourceId: applicationGatewayPublicIp.outputs.resourceId
    
    // SKU and scaling configuration
    skuName: 'WAF_v2'
    enableAutoscaling: true
    autoscaleMinCapacity: applicationGatewayMinCapacity
    autoscaleMaxCapacity: applicationGatewayMaxCapacity
    
    // SSL configuration
    sslCertificates: [
      {
        name: '${generatedApplicationGatewayName}-ssl-cert'
        properties: {
          keyVaultSecretId: sslCertificateKeyVaultSecretId
          
          // -- Can only enable either keyvaultSecretId or both data + password. --
          // data: sslCertificateData
          // password: sslCertificatePassword
        } 
      }
    ]
    managedIdentityResourceId: keyVaultSecretUserIdentity != '' ? keyVaultSecretUserIdentity : ''
    
    // Container App backends - use simpler FQDN construction
    containerAppBackends: [
      {
        name: 'rtaudioagent-backend'
        fqdn: app.outputs.backendContainerAppFqdn
        port: 443
        protocol: 'Https'
        healthProbePath: '/health'
        healthProbeProtocol: 'Https'
      }
      {
        name: 'rtaudioagent-frontend'
        fqdn: app.outputs.frontendContainerAppFqdn
        port: 80
        protocol: 'Http'
        healthProbePath: '/'
        healthProbeProtocol: 'Http'
      }
    ]
    
    // Use default frontend ports (80, 443) and listeners
    // Remove custom frontendPorts and httpListeners - let the module use defaults
    
    // Security configuration
    enableHttpRedirect: true
    enableHttp2: true
    enableWaf: enableWaf
    wafMode: wafMode
    
    // Monitoring configuration
    enableTelemetry: true
    logAnalyticsWorkspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
  }
  dependsOn: enableSslCertificate ? [
    app // Ensure container apps are deployed first
    keyVault // Ensure Key Vault and role assignments are ready when SSL is enabled
  ] : [
    app // Ensure container apps are deployed first
  ]
}


// ============================================================================
// MONITORING & OBSERVABILITY
// ============================================================================

module monitoring 'br/public:avm/ptn/azd/monitoring:0.1.0' = {
  name: 'monitoring'
  scope: hubRg
  params: {
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
    applicationInsightsDashboardName: '${abbrs.portalDashboards}${resourceToken}'
    location: location
    tags: tags
  }
}

// ============================================================================
// VIRTUAL NETWORKS (HUB & SPOKE TOPOLOGY)
// ============================================================================

// Hub VNet - Contains shared services, monitoring, and network appliances
module hubNetwork 'network.bicep' = {
  scope: hubRg
  name: hubVNetName
  params: {
    vnetName: hubVNetName
    location: location
    vnetAddressPrefix: hubVNetAddressPrefix
    subnets: hubSubnets
    workspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
    tags: tags
  }
}

// Spoke VNet - Contains application workloads and private endpoints
module spokeNetwork 'network.bicep' = {
  scope: spokeRg
  name: spokeVNetName
  params: {
    vnetName: spokeVNetName
    location: location
    vnetAddressPrefix: spokeVNetAddressPrefix
    subnets: spokeSubnets
    workspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
    tags: tags
  }
}

// ============================================================================
// PRIVATE DNS ZONES FOR AZURE SERVICES
// ============================================================================

// Storage Account (Blob) private DNS zone
module blobDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'blob-dns-zone'
  scope: hubRg
  params: {
    #disable-next-line no-hardcoded-env-urls
    dnsZoneName: 'privatelink.blob.core.windows.net'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// API Management private DNS zone
module apimDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'apim-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.azure-api.net'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Cosmos DB (MongoDB API) private DNS zone
module cosmosMongoDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'cosmos-mongo-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.mongo.cosmos.azure.com'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Cosmos DB (Core/SQL API) private DNS zone
module documentsDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'cosmos-documents-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.documents.azure.com'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Key Vault private DNS zone
module vaultDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'keyvault-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.vaultcore.azure.net'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Container Apps private DNS zone
module containerAppsDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'container-apps-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.${location}.azurecontainerapps.io'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Azure Container Registry private DNS zone
module acrDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'acr-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.${location}.azurecr.io'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Cognitive Services (OpenAI) private DNS zone
module aiservicesDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'cognitive-services-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.cognitiveservices.azure.com'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Azure OpenAI private DNS zone
module openaiDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'openai-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.openai.azure.com'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Azure Cognitive Search private DNS zone
module searchDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'search-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.search.windows.net'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// Azure Cache for Redis Enterprise private DNS zone
module redisDnsZone './modules/networking/private-dns-zone.bicep' = if (networkIsolation) {
  name: 'redis-enterprise-dns-zone'
  scope: hubRg
  params: {
    dnsZoneName: 'privatelink.redis.azure.net'
    tags: tags
    virtualNetworkName: hubNetwork.outputs.vnetName
  }
}

// ============================================================================
// VNET PEERING (HUB-SPOKE CONNECTIVITY)
// ============================================================================

// Hub to Spoke peering
module peerHubToSpoke './modules/networking/peer-virtual-networks.bicep' = {
  scope: hubRg
  name: 'peer-hub-to-spoke'
  params: {
    localVnetName: hubNetwork.outputs.vnetName
    remoteVnetId: spokeNetwork.outputs.vnetId
    remoteVnetName: spokeNetwork.outputs.vnetName
  }
}

// Spoke to Hub peering
module peerSpokeToHub './modules/networking/peer-virtual-networks.bicep' = {
  scope: spokeRg
  name: 'peer-spoke-to-hub'
  params: {
    localVnetName: spokeNetwork.outputs.vnetName
    remoteVnetId: hubNetwork.outputs.vnetId
    remoteVnetName: hubNetwork.outputs.vnetName
  }
  dependsOn: [
    peerHubToSpoke
  ]
}

// ============================================================================
// APPLICATION MANAGED IDENTITIES
// ============================================================================

// User-assigned managed identity for backend services
module uaiAudioAgentBackendIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.2.1' = {
  name: 'backend-managed-identity'
  scope: spokeRg
  params: {
    name: '${name}${abbrs.managedIdentityUserAssignedIdentities}backend-${resourceToken}'
    location: location
    tags: tags
  }
}

// User-assigned managed identity for frontend services
module uaiAudioAgentFrontendIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.2.1' = {
  name: 'frontend-managed-identity'
  scope: spokeRg
  params: {
    name: '${name}${abbrs.managedIdentityUserAssignedIdentities}frontend-${resourceToken}'
    location: location
    tags: tags
  }
}

// ============================================================================
// KEY VAULT FOR SECRETS MANAGEMENT
// ============================================================================

module keyVault 'br/public:avm/res/key-vault/vault:0.12.1' = {
  name: 'key-vault'
  scope: spokeRg
  params: {
    name: '${abbrs.keyVaultVaults}${resourceToken}'
    location: location
    sku: vaultSku
    tags: tags
    enableRbacAuthorization: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow' // TODO: Change to 'Deny' for production with proper firewall rules
      bypass: 'AzureServices'
    }
    roleAssignments: concat([
      {
        principalId: principalId
        principalType: principalType
        roleDefinitionIdOrName: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '00482a5a-887f-4fb3-b363-3b7fe8e74483') // Key Vault Administrator
      }
      {
        principalId: uaiAudioAgentBackendIdentity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'Key Vault Secrets User'
      }
    ], (enableApplicationGateway && enableSslCertificate) ? [
      {
        principalId: applicationGatewayIdentity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'Key Vault Secrets User'
      }
    ] : [])
    privateEndpoints: [
      {
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            {
              privateDnsZoneResourceId: vaultDnsZone.outputs.id
            }
          ]
        }
        subnetResourceId: spokeNetwork.outputs.subnets.privateEndpoint
      }
    ]
    diagnosticSettings: [
      {
        name: 'default'
        workspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
        logCategoriesAndGroups: [
          {
            categoryGroup: 'allLogs'
            enabled: true
          }
        ]
        metricCategories: [
          {
            category: 'AllMetrics'
            enabled: true
          }
        ]
      }
    ]
  }
}

// ============================================================================
// AZURE SPEECH SERVICES
// ============================================================================

module speechService 'br/public:avm/res/cognitive-services/account:0.11.0' = {
  name: 'speech-service'
  scope: hubRg
  params: {
    kind: 'SpeechServices'
    sku: 'S0'
    name: 'speech-${environmentName}-${resourceToken}'
    customSubDomainName: 'speech-${environmentName}-${resourceToken}'
    location: location
    tags: tags
    disableLocalAuth: disableLocalAuth
    
    // Store access keys in Key Vault if local auth is enabled
    secretsExportConfiguration: disableLocalAuth ? null : {
      accessKey1Name: 'speech-key'
      keyVaultResourceId: keyVault.outputs.resourceId
    }

    // Grant access to ACS and Frontend identity
    roleAssignments: [
      {
        principalId: acs.outputs.managedIdentityPrincipalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'Cognitive Services User'
      }
      {
        principalId: uaiAudioAgentFrontendIdentity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'Cognitive Services User'
      }
    ]
    
    publicNetworkAccess: 'Enabled' // Required for ACS integration
    
    diagnosticSettings: [
      {
        name: 'default'
        workspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
        logCategoriesAndGroups: [
          {
            categoryGroup: 'allLogs'
            enabled: true
          }
        ]
        metricCategories: [
          {
            category: 'AllMetrics'
            enabled: true
          }
        ]
      }
    ]
  }
}

// ============================================================================
// AZURE COMMUNICATION SERVICES
// ============================================================================

// Communication Service for real-time voice and messaging
// NOTE: Phone number provisioning must be done manually after deployment
module acs 'modules/communication/communication-services.bicep' = {
  name: 'communication-services'
  scope: hubRg
  params: {
    communicationServiceName: 'acs-${name}-${environmentName}-${resourceToken}'
    dataLocation: acsDataLocation
    diagnosticSettings: {
      workspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
    }
    tags: tags
  }
}

// Store ACS connection string in Key Vault
module acsConnectionStringSecret 'modules/vault/secret.bicep' = {
  name: 'acs-connection-string-secret'
  scope: spokeRg
  params: {
    keyVaultName: keyVault.outputs.name
    secretName: '${acs.outputs.communicationServiceName}-connection-string'
    secretValue: acs.outputs.connectionString
    tags: tags
  }
}
// Store ACS primary key in Key Vault
module acsPrimaryKeySecret 'modules/vault/secret.bicep' = {
  name: 'acs-primary-key-secret'
  scope: spokeRg
  params: {
    keyVaultName: keyVault.outputs.name
    secretName: 'acs-primary-key'
    secretValue: acs.outputs.primaryKey
    tags: tags
  }
}

// ============================================================================
// AI GATEWAY (API MANAGEMENT + AZURE OPENAI)
// ============================================================================
module aiGateway 'ai-gateway.bicep' = {
  scope: hubRg
  name: 'ai-gateway'
  params: {
    name: name
    location: location
    tags: tags
    
    // JWT and security configuration
    // audience: jwtAudience
    entraGroupId: entraGroupId
    
    // APIM configuration
    enableAPIManagement: enableAPIManagement
    apimPublicNetworkAccess: apimPublicNetworkAccess
    apimSku: 'StandardV2'
    virtualNetworkType: 'External'
    backendConfig: azureOpenAIBackendConfig
    apimSubnetResourceId: hubNetwork.outputs.subnets.apim
    
    // Private DNS and networking
    aoaiDnsZoneId: networkIsolation ? openaiDnsZone.outputs.id : ''
    privateEndpointSubnetId: spokeNetwork.outputs.subnets.privateEndpoint
    keyVaultResourceId: keyVault.outputs.resourceId
    
    // Application Insights logging
    loggers: [
      {
        credentials: {
          instrumentationKey: monitoring.outputs.applicationInsightsInstrumentationKey
        }
        description: 'Logger to Azure Application Insights'
        isBuffered: false
        loggerType: 'applicationInsights'
        name: 'logger'
        resourceId: monitoring.outputs.applicationInsightsResourceId
      }
    ]
    
    // Diagnostic settings
    diagnosticSettings: [
      {
        name: 'default'
        workspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
        logCategoriesAndGroups: [
          {
            categoryGroup: 'allLogs'
            enabled: true
          }
        ]
        metricCategories: [
          {
            category: 'AllMetrics'
            enabled: true
          }
        ]
      }
    ]
  }
}

// ============================================================================
// API MANAGEMENT PRIVATE ENDPOINT
// ============================================================================

// Private endpoint for API Management in spoke VNet
module apimPrivateEndpoint 'br/public:avm/res/network/private-endpoint:0.8.1' = if (enableAPIManagement && networkIsolation) {
  name: 'apim-private-endpoint'
  scope: spokeRg
  params: {
    name: 'pe-apim-${name}-${environmentName}'
    location: location
    tags: tags
    
    // Network configuration
    subnetResourceId: spokeNetwork.outputs.subnets.privateEndpoint
    
    // APIM service configuration
    privateLinkServiceConnections: [
      {
        name: 'apim-connection'
        properties: {
          privateLinkServiceId: aiGateway.outputs.apim.resourceId
          groupIds: ['Gateway']
        }
      }
    ]
    
    // DNS configuration
    privateDnsZoneGroup: {
      name: 'apim-dns-zone-group'
      privateDnsZoneGroupConfigs: [
        {
          name: 'apim-dns-config'
          privateDnsZoneResourceId: apimDnsZone.outputs.id
        }
      ]
    }
  }
  dependsOn: [
  ]
}

// Store APIM subscription key in Key Vault
module apimSubscriptionKeySecret 'modules/vault/secret.bicep' = if (enableAPIManagement) {
  name: 'apim-subscription-key-secret'
  scope: spokeRg
  params: {
    keyVaultName: keyVault.outputs.name
    secretName: 'openai-apim-subscription-key'
    secretValue: aiGateway.outputs.openAiSubscriptionKey
    tags: tags
  }
}


// ============================================================================
// JUMPHOST (OPTIONAL - ONLY WHEN NETWORK ISOLATION ENABLED)
// ============================================================================
module vmPasswordSecret 'modules/vault/secret.bicep' = if (networkIsolation) {
  name: 'jumphost-admin-password'
  scope: spokeRg
  params: {
    keyVaultName: keyVault.outputs.name
    secretName: 'jumphost-admin-password'
    secretValue: jumphostVmPassword
    tags: tags
  }
}

module winJumphost 'modules/jumphost/windows-vm.bicep' = if (networkIsolation) {
  name: 'win-jumphost'
  scope: hubRg
  params: {
    vmName: 'jumphost-${name}-${environmentName}'
    location: location
    adminUsername: 'azureuser'
    adminPassword: jumphostVmPassword
    vmSize: 'Standard_B2s'
    subnetId: hubNetwork.outputs.subnets.jumpbox
    tags: tags
  }
}

// ============================================================================
// REDIS ENTERPRISE CACHE
// ============================================================================

module redisEnterprise 'br/public:avm/res/cache/redis-enterprise:0.1.1' = {
  name: 'redis-enterprise'
  scope: spokeRg
  params: {
    name: 'redis-${name}-${resourceToken}'
    location: location
    tags: tags
    skuName: redisSku
    highAvailability: enableRedisHA == true ? 'Enabled' : 'Disabled'
    
    // Database configuration with RBAC authentication
    database: {
      accessKeysAuthentication: 'Disabled' // Use RBAC instead of access keys
      accessPolicyAssignments: [
        {
          name: 'backend-access'
          userObjectId: uaiAudioAgentBackendIdentity.outputs.clientId
        }
      ]
      diagnosticSettings: [
        {
          logCategoriesAndGroups: [
            {
              categoryGroup: 'allLogs'
              enabled: true
            }
          ]
          name: 'redis-database-logs'
          workspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
        }
      ]
    }
    
    // Cluster-level diagnostics
    diagnosticSettings: [
      {
        metricCategories: [
          {
            category: 'AllMetrics'
          }
        ]
        name: 'redis-cluster-metrics'
        workspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
      }
    ]
    
    // Private endpoint configuration
    privateEndpoints: [
      {
        privateDnsZoneGroup: {
          privateDnsZoneGroupConfigs: [
            {
              privateDnsZoneResourceId: redisDnsZone.outputs.id
            }
          ]
        }
        subnetResourceId: spokeNetwork.outputs.subnets.privateEndpoint
      }
    ]
  }
}

// Cosmos + Storage Account
module data 'data.bicep' = {
  scope: spokeRg
  name: 'data-layer'
  params: {
    // Required parameters from data.bicep
    resourceToken: resourceToken
    location: location
    tags: tags
    name: name
    
    // Storage configuration
    storageSkuName: 'Standard_LRS'
    storageContainerName: 'recordings'
    
    // Key Vault for secrets
    keyVaultResourceId: keyVault.outputs.resourceId
    
    // Network configuration
    privateEndpointSubnetId: spokeNetwork.outputs.subnets.privateEndpoint
    cosmosDnsZoneId: cosmosMongoDnsZone.outputs.id
    
    userAssignedIdentity: {
      resourceId: uaiAudioAgentBackendIdentity.outputs.resourceId
      clientId: uaiAudioAgentBackendIdentity.outputs.clientId
      principalId: uaiAudioAgentBackendIdentity.outputs.principalId
    }
    principalId: principalId
    principalType: principalType
  }
}

module storage 'br/public:avm/res/storage/storage-account:0.9.1' = {
  scope: spokeRg
  name: 'storage'
  params: {
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
    kind: 'StorageV2'
    skuName: 'Standard_LRS'
    publicNetworkAccess: 'Enabled' // Necessary for uploading documents to storage container
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    blobServices: {
      deleteRetentionPolicyDays: 2
      deleteRetentionPolicyEnabled: true
      containers: [
        {
          name: 'audioagent'
          publicAccess: 'None'
        }
        {
          name: 'prompt'
          publicAccess: 'None'
        }
      ]
    }
    roleAssignments: [
      {
        roleDefinitionIdOrName: 'Storage Blob Data Contributor'
        principalId: uaiAudioAgentBackendIdentity.outputs.principalId
        principalType: 'ServicePrincipal'
      }
      {
        roleDefinitionIdOrName: 'Storage Blob Data Reader'
        principalId: principalId
        // principalType: 'User'  
        principalType: principalType
      } 
      {
        roleDefinitionIdOrName: 'Storage Blob Data Contributor'
        principalId: principalId
        // principalType: 'User'
        principalType: principalType
      }      
    ]
  }
}

// ============================================================================
// APPLICATION SERVICES (CONTAINER APPS)
// ============================================================================

module app 'app.bicep' = {
  scope: spokeRg
  name: 'application-services'
  params: {
    name: name
    location: location
    tags: tags
    
    // UAIs for backend and frontend container apps
    backendUserAssignedIdentity: {
      resourceId: uaiAudioAgentBackendIdentity.outputs.resourceId
      principalId: uaiAudioAgentBackendIdentity.outputs.principalId
      clientId: uaiAudioAgentBackendIdentity.outputs.clientId
    }
    frontendUserAssignedIdentity: {
      resourceId: uaiAudioAgentFrontendIdentity.outputs.resourceId
      principalId: uaiAudioAgentFrontendIdentity.outputs.principalId
      clientId: uaiAudioAgentFrontendIdentity.outputs.clientId
    }

    // backendCertificate: {
    //   certificateKeyVaultProperties: {
    //     identityResourceId: keyVaultSecretUserIdentity
    //     keyVaultUrl: sslCertificateKeyVaultSecretId
    //   }
    //   certificateType: 'ServerSSLCertificate' // Optional, ServerSSLCertificate or ImagePullTrustedCA
    //   domainName: domainFqdn
    // }

    frontendEnvVars: frontendEnvVars
    backendEnvVars: backendEnvVars
    backendSecrets: backendSecrets

    // Monitoring configuration
    logAnalyticsWorkspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
    
    // RBAC configuration
    principalId: principalId
    principalType: principalType
    
    // Network configuration
    appSubnetResourceId: spokeNetwork.outputs.subnets.app
    privateDnsZoneResourceId: containerAppsDnsZone.outputs.id
    privateEndpointSubnetResourceId: spokeNetwork.outputs.subnets.privateEndpoint

    backendCors: {
      allowedOrigins: [
          acs.outputs.endpoint
          'https://${domainFqdn}'
          'http://localhost:5173'
        ]
        allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
        allowedHeaders: ['*']
        allowCredentials: true
    }

    // AZD Managed Variables
    rtaudioClientExists: rtaudioClientExists
    rtaudioServerExists: rtaudioServerExists
  }
}

// Redis configuration variables
var redisEndpointParts = split(redisEnterprise.outputs.endpoint, ':')
var redis_host = redisEndpointParts[0]
var redis_port = length(redisEndpointParts) > 1 ? redisEndpointParts[1] : '10000'

var backendSecrets = [
  {
    name: 'acs-connection-string'
    keyVaultUrl: acsConnectionStringSecret.outputs.secretUri
    identity: uaiAudioAgentBackendIdentity.outputs.resourceId
  }
  {
    name: 'cosmos-connection-string'
    keyVaultUrl: data.outputs.mongoConnectionStringSecretUri
    identity: uaiAudioAgentBackendIdentity.outputs.resourceId
  }
  {
    name: 'openai-apim-subscription-key'
    keyVaultUrl: enableAPIManagement ? apimSubscriptionKeySecret.outputs.secretUri : ''
    identity: uaiAudioAgentBackendIdentity.outputs.resourceId
  }
  {
    name: 'speech-key'
    keyVaultUrl: speechService.outputs.exportedSecrets['speech-key'].secretUri
    identity: uaiAudioAgentBackendIdentity.outputs.resourceId
  }
]
var frontendEnvVars = [
    {
      name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
      value: monitoring.outputs.applicationInsightsConnectionString
    }
    {
      name: 'AZURE_CLIENT_ID'
      value: uaiAudioAgentFrontendIdentity.outputs.clientId 
    }
    {
      name: 'PORT'
      value: '5173'
    }
    {
      name: 'VITE_BACKEND_BASE_URL'
      value: enableApplicationGateway ? 'https://${domainFqdn}' : ''
    }
]
var backendEnvVars = [
  {
    name: 'AZURE_COSMOS_CONNECTION_STRING'
    secretRef: 'cosmos-connection-string'
  }
  {
    name: 'AZURE_SPEECH_KEY'
    secretRef: 'speech-key'
  }
  {
    name: 'ACS_CONNECTION_STRING'
    secretRef: 'acs-connection-string'
  }

  {
    name: 'AZURE_CLIENT_ID'
    value: uaiAudioAgentBackendIdentity.outputs.clientId
  }

  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: monitoring.outputs.applicationInsightsConnectionString
  }

  {
    name: 'ACS_SOURCE_PHONE_NUMBER'
    value: acsSourcePhoneNumber
  }
  
  // Base URL for webhooks (typically set by deployment environment)
  {
    name: 'BASE_URL'
    value: enableApplicationGateway ? 'https://${domainFqdn}' : ''
  }
  
  // Redis Configuration
  {
    name: 'REDIS_HOST'
    value: redis_host
  }
  {
    name: 'REDIS_PORT'
    value: redis_port
  }
  
  // Azure Speech Services
  {
    name: 'AZURE_SPEECH_ENDPOINT'
    value: speechService.outputs.endpoint
  }

  {
    name: 'AZURE_SPEECH_RESOURCE_ID'
    value: speechService.outputs.resourceId
  }
  {
    name: 'AZURE_SPEECH_REGION'
    value: location
  }
  
  // Azure Storage (from app module outputs)
  // {
  //   name: 'AZURE_STORAGE_CONTAINER_URL'
  //   value: '${app.outputs.storageAccountBlobEndpoint}recordings'
  // }
  // {
  //   name: 'AZURE_STORAGE_CONNECTION_STRING'
  //   secretRef: 'storage-connection-string'
  // }
  
  // Azure Cosmos DB
  {
    name: 'AZURE_COSMOS_DB_DATABASE_NAME'
    value: data.outputs.mongoDatabaseName
  }
  {
    name: 'AZURE_COSMOS_DB_COLLECTION_NAME'
    value: data.outputs.mongoCollectionName
  }

  
  // Azure OpenAI
  {
    name: 'AZURE_OPENAI_ENDPOINT'
    value: aiGateway.outputs.endpoints.openAI
  }
  // Disabled to use Entra JWT tokens to auth vs APIM policy (based on group membership)
  // {
  //   name: 'AZURE_OPENAI_KEY'
  //   secretRef: enableAPIManagement ? 'openai-apim-subscription-key' : 'openai-primary-key'
  // }
  {
    name: 'AZURE_OPENAI_CHAT_DEPLOYMENT_ID'
    value: 'gpt-4o'
  }
  {
    name: 'AZURE_OPENAI_API_VERSION'
    value: '2025-01-01-preview'
  }
]

// ============================================================================
// OUTPUTS FOR AZD INTEGRATION
// ============================================================================

@description('Azure Resource Group name')
output AZURE_RESOURCE_GROUP string = spokeRg.name

@description('Azure Container Registry endpoint')
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = app.outputs.containerRegistryEndpoint

@description('Azure Communication Services endpoint')
output ACS_ENDPOINT string = acs.outputs.endpoint

@description('Application Gateway resource ID')
output APPLICATION_GATEWAY_RESOURCE_ID string = enableApplicationGateway ? applicationGateway.outputs.applicationGatewayResourceId : ''

@description('Application Gateway public IP address')
output APPLICATION_GATEWAY_PUBLIC_IP string = enableApplicationGateway ? applicationGateway.outputs.publicIpAddress : ''

@description('Application Gateway FQDN')
output APPLICATION_GATEWAY_FQDN string = enableApplicationGateway ? applicationGateway.outputs.fqdn : ''

@description('Application Gateway name')
output APPLICATION_GATEWAY_NAME string = enableApplicationGateway ? applicationGateway.outputs.applicationGatewayName : ''

@description('WAF policy resource ID')
output WAF_POLICY_RESOURCE_ID string = enableApplicationGateway && enableWaf ? applicationGateway.outputs.wafPolicyResourceId : ''

@description('Backend User Assigned Identity Principal ID, to be added to the entra group postprovision')
output BACKEND_UAI_PRINCIPAL_ID string = uaiAudioAgentBackendIdentity.outputs.principalId

@description('Backend Container App name')
output BACKEND_CONTAINER_APP_NAME string = app.outputs.backendContainerAppName

@description('Backend Resource Group name')
output BACKEND_RESOURCE_GROUP_NAME string = spokeRg.name
