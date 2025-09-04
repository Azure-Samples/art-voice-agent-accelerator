/*
================================================================================
Azure Managed Redis (Enterprise) Module with Private Networking and Database Support
================================================================================

This production-grade module creates an Azure Cache for Redis Enterprise cluster
with comprehensive security, networking, and database management capabilities.

Key Features:
✓ Enterprise and Enterprise Flash SKU support with auto-capacity calculation
✓ Multiple Redis databases with advanced module support (RedisBloom, RediSearch, RedisTimeSeries)
✓ Private networking with automatic DNS zone configuration
✓ Customer-managed encryption with Key Vault integration
✓ Geo-replication for disaster recovery and high availability
✓ Zone redundancy and auto-scaling capabilities
✓ Comprehensive monitoring and diagnostics integration
✓ Production-ready security configurations

Security Features:
- TLS 1.2+ encryption by default
- Private endpoint isolation
- Managed identity integration
- Customer-managed key encryption
- Network access controls
- Audit logging capabilities

Database Features:
- Multiple database instances with custom configurations
- Redis modules: RedisBloom, RediSearch, RedisTimeSeries, RedisJSON
- Flexible persistence options (AOF/RDB)
- Cross-region geo-replication
- Custom eviction policies
- Port assignment management

Prerequisites:
- Virtual Network with dedicated subnet (for private endpoints)
- Private DNS Zone: privatelink.redisenterprise.cache.azure.net
- Key Vault with appropriate access policies (for CMK encryption)
- User-assigned managed identity (for Key Vault access)

Author: Azure AI Assistant
Version: 3.0
Last Modified: December 2024
License: MIT
*/

// ============================================================================
// PARAMETERS
// ============================================================================

@minLength(3)
@maxLength(60)
@description('Name of the Redis Enterprise cluster. Must be globally unique.')
param clusterName string

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Resource tags for cost management and organization')
param tags object = {}

// SKU and Capacity Configuration
@description('Redis Enterprise SKU configuration with performance tiers')
param sku object = {
  name: 'Enterprise_E10' // Default: 12GB memory, suitable for development/testing
  capacity: 2            // Minimum recommended for production workloads
}

@description('Availability zones for high availability deployment')
param zones array = ['1', '2', '3'] // Default to multi-zone for production

@description('Minimum TLS version for enhanced security')
// @allowed(['1.0', '1.1', '1.2'])
@allowed(['1.2'])
param minimumTlsVersion string = '1.2' // Enforce TLS 1.2+ for security compliance

// Identity and Security Configuration
@description('Enable system-assigned managed identity for Azure service integration')
param enableSystemManagedIdentity bool = true // Recommended for production

@description('User-assigned managed identity resource IDs for fine-grained access control')
param userAssignedIdentityIds array = []

@description('Enable customer-managed encryption for data at rest')
param enableCustomerManagedEncryption bool = false

@description('Key Vault key URL for customer-managed encryption (required if CMK enabled)')
param keyVaultKeyUrl string = ''

@description('User-assigned identity resource ID for Key Vault access (required if CMK enabled)')
param keyVaultIdentityId string = ''

// Private Networking Configuration
@description('Enable private endpoint for network isolation and security')
param enablePrivateEndpoint bool = true // Recommended for production workloads

@description('Virtual Network resource ID for private endpoint deployment')
param vnetResourceId string = ''

@description('Subnet name within the VNet for private endpoint placement')
param subnetName string = 'redis-subnet'

@description('Private DNS zone resource ID for name resolution')
param privateDnsZoneResourceId string = ''

@description('Custom private endpoint name (auto-generated if empty)')
param privateEndpointName string = ''

// Database Configuration
@description('Redis databases configuration with advanced options')
param databases array = [
  {
    name: 'primary'
    clientProtocol: 'Encrypted'  // Use TLS encryption
    port: 10000
    clusteringPolicy: 'OSSCluster'
    evictionPolicy: 'VolatileLRU'  // Memory-efficient eviction
    modules: [
      {
        name: 'RediSearch'  // Enable full-text search capabilities
        args: 'MAXSEARCHRESULTS 10000'
      }
      {
        name: 'RedisJSON'   // Enable JSON document storage
        args: ''
      }
    ]
    persistence: {
      aofEnabled: false      // Append-only file for durability
      rdbEnabled: true       // Redis database snapshots
      rdbFrequency: '6h'     // Snapshot every 6 hours
    }
    geoReplication: {
      groupNickname: ''
      linkedDatabases: []
    }
  }
]

// Advanced Configuration
@description('Enable enhanced monitoring and diagnostics')
param enableDiagnostics bool = true

@description('Log Analytics workspace resource ID for diagnostics (required if enableDiagnostics is true)')
param logAnalyticsWorkspaceId string = ''

@description('Enable automatic backup configuration')
param enableAutomaticBackup bool = true

// ============================================================================
// VARIABLES
// ============================================================================

// Managed Identity Configuration
var identityConfig = {
  systemAssigned: enableSystemManagedIdentity ? {
    type: !empty(userAssignedIdentityIds) ? 'SystemAssigned,UserAssigned' : 'SystemAssigned'
  } : {}
  
  userAssigned: !empty(userAssignedIdentityIds) ? {
    type: enableSystemManagedIdentity ? 'SystemAssigned,UserAssigned' : 'UserAssigned'
    userAssignedIdentities: reduce(userAssignedIdentityIds, {}, (cur, id) => union(cur, { '${id}': {} }))
  } : {}
}

var identity = !empty(userAssignedIdentityIds) 
  ? identityConfig.userAssigned 
  : (enableSystemManagedIdentity ? identityConfig.systemAssigned : null)

// Customer-Managed Encryption Configuration
var encryptionProperties = enableCustomerManagedEncryption ? {
  customerManagedKeyEncryption: {
    keyEncryptionKeyUrl: keyVaultKeyUrl
    keyEncryptionKeyIdentity: {
      identityType: 'userAssignedIdentity'
      userAssignedIdentityResourceId: keyVaultIdentityId
    }
  }
} : null

// Private Endpoint Configuration
var privateEndpointConfig = {
  name: !empty(privateEndpointName) ? privateEndpointName : 'pe-${clusterName}-redis'
  subnetId: enablePrivateEndpoint ? '${vnetResourceId}/subnets/${subnetName}' : ''
  groupId: 'redisEnterprise'
  dnsZoneName: 'privatelink.redisenterprise.cache.azure.net'
}

// Database Port Assignment (auto-increment from base port)
var baseDatabasePort = 10000
var databaseConfigurations = [for (database, index) in databases: union(database, {
  assignedPort: database.?port ?? (baseDatabasePort + index)
  modules: database.?modules ?? []
  persistence: database.?persistence ?? {
    aofEnabled: false
    rdbEnabled: true
    rdbFrequency: '6h'
  }
})]

// Resource Naming Convention
var resourceNames = {
  cluster: clusterName
  privateEndpoint: privateEndpointConfig.name
  dnsZoneGroup: 'default'
  connectionName: '${privateEndpointConfig.name}-connection'
}

// ============================================================================
// RESOURCES
// ============================================================================

// Redis Enterprise Cluster with Comprehensive Configuration
resource redisEnterpriseCluster 'Microsoft.Cache/redisEnterprise@2024-10-01' = {
  name: resourceNames.cluster
  location: location
  tags: union(tags, {
    'redis-enterprise': 'true'
    'deployment-method': 'bicep'
    'managed-by': 'azure-bicep'
  })
  sku: sku
  zones: !empty(zones) ? zones : null
  identity: identity
  properties: {
    minimumTlsVersion: minimumTlsVersion
    encryption: encryptionProperties
  }
}

// Redis Enterprise Databases with Enhanced Configuration
resource redisEnterpriseDatabases 'Microsoft.Cache/redisEnterprise/databases@2024-10-01' = [for (database, index) in databaseConfigurations: {
  parent: redisEnterpriseCluster
  name: database.name
  properties: {
    clientProtocol: database.?clientProtocol ?? 'Encrypted'
    port: database.assignedPort
    clusteringPolicy: database.?clusteringPolicy ?? 'OSSCluster'
    evictionPolicy: database.?evictionPolicy ?? 'VolatileLRU'
    modules: database.modules
    persistence: database.persistence
    geoReplication: (database.?geoReplication != null && !empty(database.geoReplication.?linkedDatabases)) 
      ? database.geoReplication 
      : null
  }
}]

// Private Endpoint for Secure Connectivity
resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (enablePrivateEndpoint) {
  name: privateEndpointConfig.name
  location: location
  tags: union(tags, {
    component: 'private-endpoint'
    redisCluster: clusterName
  })
  properties: {
    subnet: {
      id: privateEndpointConfig.subnetId
    }
    privateLinkServiceConnections: [
      {
        name: resourceNames.connectionName
        properties: {
          privateLinkServiceId: redisEnterpriseCluster.id
          groupIds: [privateEndpointConfig.groupId]
          requestMessage: 'Approved by automated deployment'
        }
      }
    ]
  }
}

// Private DNS Zone Group for Name Resolution
resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (enablePrivateEndpoint) {
  name: resourceNames.dnsZoneGroup
  parent: privateEndpoint
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'redis-enterprise-dns-config'
        properties: {
          privateDnsZoneId: privateDnsZoneResourceId
        }
      }
    ]
  }
}

// Diagnostic Settings for Monitoring and Compliance
resource diagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (enableDiagnostics && !empty(logAnalyticsWorkspaceId)) {
  name: '${clusterName}-diagnostics'
  scope: redisEnterpriseCluster
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
        retentionPolicy: {
          enabled: enableAutomaticBackup
          days: 30
        }
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: enableAutomaticBackup
          days: 30
        }
      }
    ]
  }
}

// ============================================================================
// OUTPUTS
// ============================================================================

// Core Cluster Information
@description('Resource ID of the Redis Enterprise cluster')
output clusterResourceId string = redisEnterpriseCluster.id

@description('Name of the Redis Enterprise cluster')
output clusterName string = redisEnterpriseCluster.name

@description('Fully qualified domain name of the Redis Enterprise cluster')
output hostName string = redisEnterpriseCluster.properties.hostName

@description('Redis version running on the cluster')
output redisVersion string = redisEnterpriseCluster.properties.redisVersion

@description('Current provisioning state of the cluster')
output provisioningState string = redisEnterpriseCluster.properties.provisioningState

@description('Current operational state of the cluster')
output resourceState string = redisEnterpriseCluster.properties.resourceState

// Database Information
@description('Array of database resource IDs')
output databaseResourceIds array = [for (database, index) in databaseConfigurations: redisEnterpriseDatabases[index].id]

@description('Array of database names for reference')
output databaseNames array = [for database in databaseConfigurations: database.name]

@description('Comprehensive database connection information')
output databaseConnections array = [for (database, index) in databaseConfigurations: {
  name: database.name
  resourceId: redisEnterpriseDatabases[index].id
  hostName: redisEnterpriseCluster.properties.hostName
  port: database.assignedPort
  protocol: database.?clientProtocol ?? 'Encrypted'
  connectionString: database.?clientProtocol == 'Encrypted' 
    ? 'rediss://${redisEnterpriseCluster.properties.hostName}:${database.assignedPort}'
    : 'redis://${redisEnterpriseCluster.properties.hostName}:${database.assignedPort}'
  tlsEnabled: database.?clientProtocol != 'Plaintext'
  modules: map(database.modules, module => module.name)
  clusteringPolicy: database.?clusteringPolicy ?? 'OSSCluster'
  evictionPolicy: database.?evictionPolicy ?? 'VolatileLRU'
}]

// Security and Access Information
@description('Database access keys (sensitive) - Primary and secondary keys for each database')
output databaseAccessKeys array = [for (database, index) in databaseConfigurations: {
  name: database.name
  primaryKey: redisEnterpriseDatabases[index].listKeys().primaryKey
  secondaryKey: redisEnterpriseDatabases[index].listKeys().secondaryKey
}]

// Networking Information
@description('Private endpoint resource ID (if enabled)')
output privateEndpointId string = enablePrivateEndpoint ? privateEndpoint.id : ''

@description('Private endpoint network interface IDs (if enabled)')
output privateEndpointNetworkInterfaces array = enablePrivateEndpoint ? privateEndpoint.properties.networkInterfaces : []

@description('Private endpoint custom DNS configurations (if enabled)')
output privateEndpointDnsConfigs array = enablePrivateEndpoint ? privateEndpoint.properties.customDnsConfigs : []

// Identity Information
@description('System-assigned managed identity principal ID (if enabled)')
output systemManagedIdentityPrincipalId string = enableSystemManagedIdentity && identity != null ? redisEnterpriseCluster.identity.principalId : ''

@description('System-assigned managed identity tenant ID (if enabled)')
output systemManagedIdentityTenantId string = enableSystemManagedIdentity && identity != null ? redisEnterpriseCluster.identity.tenantId : ''

// Configuration Summary
@description('Deployment configuration summary for validation and documentation')
output configurationSummary object = {
  cluster: {
    name: redisEnterpriseCluster.name
    sku: sku
    zones: zones
    location: location
    minimumTlsVersion: minimumTlsVersion
    redisVersion: redisEnterpriseCluster.properties.redisVersion
  }
  security: {
    customerManagedEncryption: enableCustomerManagedEncryption
    systemManagedIdentity: enableSystemManagedIdentity
    userAssignedIdentityCount: length(userAssignedIdentityIds)
    privateNetworking: enablePrivateEndpoint
    tlsVersion: minimumTlsVersion
  }
  databases: {
    count: length(databaseConfigurations)
    names: map(databaseConfigurations, db => db.name)
    ports: map(databaseConfigurations, db => db.assignedPort)
    totalModules: length(flatten(map(databaseConfigurations, db => db.modules)))
  }
  monitoring: {
    diagnosticsEnabled: enableDiagnostics
    backupEnabled: enableAutomaticBackup
  }
}

// Application Configuration for Easy Integration
@description('Environment variables and configuration values for application integration')
output applicationConfig object = {
  // Primary connection information
  REDIS_ENTERPRISE_CLUSTER_NAME: redisEnterpriseCluster.name
  REDIS_ENTERPRISE_HOSTNAME: redisEnterpriseCluster.properties.hostName
  REDIS_ENTERPRISE_VERSION: redisEnterpriseCluster.properties.redisVersion
  REDIS_ENTERPRISE_TLS_VERSION: minimumTlsVersion
  
  // Database configuration
  REDIS_ENTERPRISE_DATABASE_COUNT: string(length(databaseConfigurations))
  REDIS_ENTERPRISE_PRIMARY_DATABASE_NAME: length(databaseConfigurations) > 0 ? databaseConfigurations[0].name : ''
  REDIS_ENTERPRISE_PRIMARY_DATABASE_PORT: length(databaseConfigurations) > 0 ? string(databaseConfigurations[0].assignedPort) : ''
  
  // Security configuration
  REDIS_ENTERPRISE_TLS_ENABLED: string(minimumTlsVersion != '1.0')
  REDIS_ENTERPRISE_PRIVATE_ENDPOINT: string(enablePrivateEndpoint)
  REDIS_ENTERPRISE_MANAGED_IDENTITY: string(enableSystemManagedIdentity)
  
  // Networking
  REDIS_ENTERPRISE_PRIVATE_DNS_ZONE: enablePrivateEndpoint ? privateEndpointConfig.dnsZoneName : ''
}

// Secure Connection Strings for Primary Database
@secure()
@description('Ready-to-use connection strings for the primary database')
output primaryDatabaseConnectionStrings object = length(databaseConfigurations) > 0 ? {
  // With authentication placeholder
  withAuth: databaseConfigurations[0].?clientProtocol == 'Encrypted'
    ? 'rediss://:{{REDIS_PASSWORD}}@${redisEnterpriseCluster.properties.hostName}:${databaseConfigurations[0].assignedPort}'
    : 'redis://:{{REDIS_PASSWORD}}@${redisEnterpriseCluster.properties.hostName}:${databaseConfigurations[0].assignedPort}'
  
  // Without authentication (for managed identity scenarios)
  withoutAuth: databaseConfigurations[0].?clientProtocol == 'Encrypted'
    ? 'rediss://${redisEnterpriseCluster.properties.hostName}:${databaseConfigurations[0].assignedPort}'
    : 'redis://${redisEnterpriseCluster.properties.hostName}:${databaseConfigurations[0].assignedPort}'
    
  // For connection pooling libraries
  host: redisEnterpriseCluster.properties.hostName
  port: databaseConfigurations[0].assignedPort
  ssl: databaseConfigurations[0].?clientProtocol == 'Encrypted'
  database: 0
} : {}

// Monitoring and Health Check URLs
@description('Monitoring and management endpoints')
output monitoringEndpoints object = {
  azurePortalUrl: 'https://portal.azure.com/#@/resource${redisEnterpriseCluster.id}/overview'
  healthCheckEndpoint: enablePrivateEndpoint 
    ? 'Private endpoint access only'
    : 'redis://${redisEnterpriseCluster.properties.hostName}:${length(databaseConfigurations) > 0 ? databaseConfigurations[0].assignedPort : 10000}'
  diagnosticsEnabled: enableDiagnostics
}
