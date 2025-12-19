@export()
@description('Model deployment configuration')
type ModelDeployment = {
  @description('SKU name for the model')
  sku: ('Standard' | 'GlobalStandard' | 'ProvisionedThroughput')
  
  @description('Capacity for the model deployment')
  @minValue(1)
  @maxValue(1000)
  capacity: int
  
  @description('Model deployment name')
  name: string
  
  @description('Model version')
  version: string
}

@export()
@description('Container app KV Secret reference configuration')
type ContainerAppKvSecret = {
  @description('Key Vault secret name')
  name: string

  @description('Key Vault resource Url')
  keyVaultUrl: string

  @description('Identity to retrieve the secret')
  identity: string
}

@export()
@description('APIM configuration settings')
type ApimConfig = {
  @description('APIM SKU')
  sku: ('BasicV2' | 'StandardV2' | 'PremiumV2')

  @description('Publisher email address')
  publisherEmail: string

  @description('Publisher name')
  publisherName: string

  @description('Enable virtual network integration')
  enableVnetIntegration: bool?

  @description('Subnet resource ID for APIM (required if enableVnetIntegration is true)')
  subnetResourceId: string?

  @description('Custom domain configurations')
  customDomains: array?

  @description('Enable developer portal')
  enableDeveloperPortal: bool?

  @description('API versioning configuration')
  apiVersioning: {
    enabled: bool
    defaultVersion: string?
    versioningScheme: ('Segment' | 'Query' | 'Header')?
  }?
}

@export()
@description('Load balancing configuration')
type LoadBalancingConfig = {
  @description('Load balancing algorithm')
  algorithm: ('RoundRobin' | 'LeastConnections' | 'Priority' | 'Weighted')

  @description('Health check configuration')
  healthCheck: {
    enabled: bool
    path: string?
    intervalSeconds: int?
    timeoutSeconds: int?
    healthyThreshold: int?
    unhealthyThreshold: int?
  }?

  @description('Circuit breaker configuration')
  circuitBreaker: {
    enabled: bool
    failureThreshold: int?
    recoveryTimeSeconds: int?
    monitoringWindowSeconds: int?
  }?

  @description('Retry policy configuration')
  retryPolicy: {
    maxRetries: int
    backoffStrategy: ('Fixed' | 'Exponential' | 'Linear')?
    baseDelaySeconds: int?
    maxDelaySeconds: int?
  }?
}


@export()
@description('Role assignment configuration for managed identities')
type RoleAssignmentConfig = {
  @description('The role definition ID or name')
  roleDefinitionIdOrName: string

  @description('Description of why this role is needed')
  description: string?

  @description('The scope at which to assign the role (defaults to resource group)')
  scope: ('resourceGroup' | 'subscription' | 'resource')?

  @description('Resource ID when scope is "resource"')
  resourceId: string?

  @description('Principal type for the assignment')
  principalType: ('ServicePrincipal' | 'User' | 'Group')?

  @description('Condition for the role assignment (Azure ABAC)')
  condition: string?

  @description('Version of the condition syntax')
  conditionVersion: ('2.0')?
}

@export()
@description('Managed identity configuration')
type ManagedIdentityConfig = {
  @description('Enable system-assigned managed identity')
  systemAssigned: bool

  @description('User-assigned managed identity resource IDs')
  userAssignedResourceIds: string[]?

  @description('Role assignments for the managed identity')
  roleAssignments: RoleAssignmentConfig[]?
}

@export()
@description('Common Azure built-in role names')
type AzureBuiltInRole = {
  // AI Services roles
  CognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  CognitiveServicesOpenAIContributor: 'a001fd3d-188f-4b5d-821b-7da978bf7442'
  CognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  
  // Key Vault roles
  KeyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  KeyVaultCryptoUser: '12338af0-0e69-4776-bea7-57ae8d297424'
  
  // Storage roles
  StorageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  StorageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  
  // Monitoring roles
  MonitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
  LogAnalyticsContributor: '92aaf0da-9dab-42b6-94a3-d43ce8d16293'
  
  // General roles
  Reader: 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
  Contributor: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
}


@export()
@description('Configuration for an AI backend deployment - Updated structure')
type BackendConfigItem = {
  @description('Unique name identifier for the backend configuration')
  @minLength(3)
  @maxLength(50)
  name: string

  @description('Azure region where the backend will be deployed')
  location: string

  @description('Priority of the backend (1 = highest priority)')
  @minValue(1)
  @maxValue(100)
  priority: int

  @description('Array of models to deploy in this backend')
  @minLength(1)
  models: ModelDeployment[]

  @description('Weight of the backend for load balancing (optional)')
  @minValue(1)
  @maxValue(1000)
  weight: int?

  @description('SKU for the AI Services resource (optional)')
  sku: ('S0' | 'S1')?

  @description('Enable private endpoint for this backend (optional)')
  enablePrivateEndpoint: bool?

  @description('Custom domain configuration (optional)')
  customDomain: string?

  @description('Network ACLs configuration (optional)')
  networkAcls: {
    defaultAction: ('Allow' | 'Deny')
    ipRules: array?
    virtualNetworkRules: array?
  }?
}



@export()
@description('Configuration for a subnet in a virtual network')
type SubnetConfig = {
  name: string
  addressPrefix: string
  serviceEndpoints: []? // Optional service endpoints for the subnet
  delegations: SubnetDelegation[]?
  securityRules: SecurityRule[]?
}

@export()
@description('Network security rule configuration')
type SecurityRule = {
  @description('Security rule name')
  name: string
  
  @description('Security rule properties')
  properties: {
    @description('Rule priority')
    priority: int
    
    @description('Protocol')
    protocol: ('Tcp' | 'Udp' | 'Icmp' | '*')
    
    @description('Access type')
    access: ('Allow' | 'Deny')
    
    @description('Direction')
    direction: ('Inbound' | 'Outbound')
    
    @description('Source address prefix')
    sourceAddressPrefix: string
    
    @description('Source port range')
    sourcePortRange: string
    
    @description('Destination address prefix')
    destinationAddressPrefix: string
    
    @description('Destination port range')
    destinationPortRange: string
  }
}

@export()
@description('Configuration for subnet delegation')
type SubnetDelegation = {
  @description('Delegation ID')
  id: string?
  
  @description('Delegation name')
  name: string
  @description('Delegation properties')
  properties: {
    @description('Service name for the delegation (e.g., Microsoft.Web/serverFarms)')
    serviceName: string
  }
  
  @description('Delegation type')
  type: string?
}

@export()
@description('Configuration for a user-assigned managed identity')
type UserAssignedIdentityConfig = {
  @description('Resource ID of the user-assigned managed identity')
  resourceId: string

  clientId: string

  principalId: string

  roleAssignments: RoleAssignmentConfig[]?
}
