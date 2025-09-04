// Azure Redis Enterprise - Example Usage Scenarios
// This file demonstrates various ways to use the am-redis.bicep module

targetScope = 'resourceGroup'

// ============================================================================
// PARAMETERS
// ============================================================================

@description('Environment name (dev, test, prod)')
param environment string = 'dev'

@description('Application name prefix')
param appName string = 'myapp'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Resource tags')
param tags object = {
  environment: environment
  project: appName
  deployedBy: 'bicep'
  solution: 'redis-enterprise'
}

// ============================================================================
// VARIABLES
// ============================================================================

var vnetName = '${appName}-vnet-${environment}'
var redisSubnetName = 'redis-enterprise-subnet'
var privateDnsZoneName = 'privatelink.redisenterprise.cache.azure.net'

// ============================================================================
// EXAMPLE 1: Basic Redis Enterprise Cluster (Development)
// ============================================================================

module redisEnterpriseBasic '../modules/app/am-redis.bicep' = if (environment == 'dev') {
  name: 'redis-enterprise-basic-${environment}'
  params: {
    clusterName: '${appName}-redis-ent-${environment}'
    location: location
    tags: tags
    sku: {
      name: 'Enterprise_E10'
      capacity: 2
    }
    minimumTlsVersion: '1.2'
    enableSystemManagedIdentity: true
    databases: [
      {
        name: 'default'
        clientProtocol: 'Encrypted'
        port: 10000
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'AllKeysLRU'
        modules: []
        persistence: {
          aofEnabled: false
          rdbEnabled: true
          rdbFrequency: '12h'
        }
      }
    ]
  }
}

// ============================================================================
// EXAMPLE 2: Virtual Network for Private Redis Enterprise
// ============================================================================

// Virtual Network for private Redis Enterprise scenarios
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = if (environment != 'dev') {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
    subnets: [
      {
        name: redisSubnetName
        properties: {
          addressPrefix: '10.0.1.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'app-subnet'
        properties: {
          addressPrefix: '10.0.2.0/24'
        }
      }
      {
        name: 'key-vault-subnet'
        properties: {
          addressPrefix: '10.0.3.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// Private DNS Zone for Redis Enterprise
resource privateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = if (environment != 'dev') {
  name: privateDnsZoneName
  location: 'global'
  tags: tags
}

// Link Private DNS Zone to VNet
resource privateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (environment != 'dev') {
  parent: privateDnsZone
  name: '${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

// ============================================================================
// EXAMPLE 3: User-Assigned Managed Identity and Key Vault (Production)
// ============================================================================

// User-assigned managed identity for Key Vault access
resource userAssignedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = if (environment == 'prod') {
  name: '${appName}-redis-identity-${environment}'
  location: location
  tags: tags
}

// Key Vault for customer-managed encryption
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = if (environment == 'prod') {
  name: '${appName}-kv-${environment}-${uniqueString(resourceGroup().id)}'
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enabledForDiskEncryption: true
    enabledForTemplateDeployment: true
    enablePurgeProtection: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    }
  }
}

// Key for Redis Enterprise encryption
resource redisEncryptionKey 'Microsoft.KeyVault/vaults/keys@2023-07-01' = if (environment == 'prod') {
  parent: keyVault
  name: 'redis-enterprise-encryption-key'
  tags: tags
  properties: {
    kty: 'RSA'
    keySize: 2048
    keyOps: ['encrypt', 'decrypt', 'sign', 'verify', 'wrapKey', 'unwrapKey']
  }
}

// Role assignment for managed identity to access Key Vault
resource keyVaultCryptoOfficerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (environment == 'prod') {
  name: guid(keyVault.id, userAssignedIdentity.id, 'Key Vault Crypto Officer')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '14b46e9e-c2b7-41b4-b07b-48a6ebf60603') // Key Vault Crypto Officer
    principalId: userAssignedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// EXAMPLE 4: Redis Enterprise with Multiple Databases and Modules (Test)
// ============================================================================

module redisEnterpriseMultiDB '../modules/app/am-redis.bicep' = if (environment == 'test') {
  name: 'redis-enterprise-multi-db-${environment}'
  params: {
    clusterName: '${appName}-redis-ent-${environment}'
    location: location
    tags: union(tags, { databases: 'multiple', modules: 'enabled' })
    sku: {
      name: 'Enterprise_E20'
      capacity: 4
    }
    zones: ['1', '2', '3']
    minimumTlsVersion: '1.2'
    enableSystemManagedIdentity: true
    databases: [
      {
        name: 'cache-db'
        port: 10000
        clientProtocol: 'Encrypted'
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'AllKeysLRU'
        modules: []
        persistence: {
          rdbEnabled: true
          rdbFrequency: '6h'
          aofEnabled: false
        }
      }
      {
        name: 'search-db'
        port: 10001
        clientProtocol: 'Encrypted'
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'NoEviction'
        modules: [
          {
            name: 'RediSearch'
            args: ''
          }
        ]
        persistence: {
          rdbEnabled: true
          rdbFrequency: '12h'
          aofEnabled: true
          aofFrequency: '1s'
        }
      }
      {
        name: 'timeseries-db'
        port: 10002
        clientProtocol: 'Encrypted'
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'NoEviction'
        modules: [
          {
            name: 'RedisTimeSeries'
            args: 'RETENTION_POLICY 86400'
          }
        ]
        persistence: {
          rdbEnabled: true
          rdbFrequency: '6h'
          aofEnabled: false
        }
      }
      {
        name: 'bloom-db'
        port: 10003
        clientProtocol: 'Encrypted'
        evictionPolicy: 'NoEviction'
        modules: [
          {
            name: 'RedisBloom'
            args: 'ERROR_RATE 0.001 INITIAL_SIZE 1000'
          }
        ]
        persistence: {
          rdbEnabled: true
          rdbFrequency: '12h'
          aofEnabled: false
        }
      }
    ]
  }
}

// ============================================================================
// EXAMPLE 5: Redis Enterprise with Private Networking (Production)
// ============================================================================

module redisEnterprisePrivate '../modules/app/am-redis.bicep' = if (environment == 'prod') {
  name: 'redis-enterprise-private-${environment}'
  params: {
    clusterName: '${appName}-redis-ent-${environment}'
    location: location
    tags: union(tags, { networking: 'private', tier: 'enterprise' })
    sku: {
      name: 'Enterprise_E50'
      capacity: 6
    }
    zones: ['1', '2', '3']
    minimumTlsVersion: '1.2'
    enableSystemManagedIdentity: true
    userAssignedIdentityIds: [userAssignedIdentity.id]
    enableCustomerManagedEncryption: true
    keyVaultKeyUrl: redisEncryptionKey.properties.keyUriWithVersion
    keyVaultIdentityId: userAssignedIdentity.id
    enablePrivateEndpoint: true
    vnetResourceId: vnet.id
    subnetName: redisSubnetName
    privateDnsZoneResourceId: privateDnsZone.id
    privateEndpointName: '${appName}-redis-ent-pe-${environment}'
    databases: [
      {
        name: 'production-cache'
        port: 10000
        clientProtocol: 'Encrypted'
        clusteringPolicy: 'EnterpriseCluster'
        evictionPolicy: 'AllKeysLRU'
        persistence: {
          rdbEnabled: true
          rdbFrequency: '6h'
          aofEnabled: true
          aofFrequency: '1s'
        }
      }
      {
        name: 'production-search'
        port: 10001
        clientProtocol: 'Encrypted'
        clusteringPolicy: 'EnterpriseCluster'
        evictionPolicy: 'NoEviction'
        modules: [
          {
            name: 'RediSearch'
            args: ''
          }
          {
            name: 'RedisJSON'
            args: ''
          }
        ]
        persistence: {
          rdbEnabled: true
          rdbFrequency: '12h'
          aofEnabled: true
          aofFrequency: '1s'
        }
      }
    ]
  }
  dependsOn: [
    privateDnsZoneLink
    keyVaultCryptoOfficerAssignment
  ]
}

// ============================================================================
// EXAMPLE 6: Redis Enterprise Flash SKU (High Performance)
// ============================================================================

module redisEnterpriseFlash '../modules/app/am-redis.bicep' = if (environment == 'prod') {
  name: 'redis-enterprise-flash-${environment}'
  params: {
    clusterName: '${appName}-redis-flash-${environment}'
    location: location
    tags: union(tags, { sku: 'flash', performance: 'high' })
    sku: {
      name: 'EnterpriseFlash_F700'
      capacity: 9
    }
    zones: ['1', '2', '3']
    minimumTlsVersion: '1.2'
    enableSystemManagedIdentity: true
    databases: [
      {
        name: 'high-perf-cache'
        port: 10000
        clientProtocol: 'Encrypted'
        clusteringPolicy: 'EnterpriseCluster'
        evictionPolicy: 'AllKeysLFU'
        persistence: {
          rdbEnabled: true
          rdbFrequency: '1h'
          aofEnabled: false
        }
      }
      {
        name: 'analytics-db'
        port: 10001
        clientProtocol: 'Encrypted'
        clusteringPolicy: 'EnterpriseCluster'
        evictionPolicy: 'NoEviction'
        modules: [
          {
            name: 'RedisTimeSeries'
            args: 'RETENTION_POLICY 604800'
          }
          {
            name: 'RedisBloom'
            args: 'ERROR_RATE 0.0001 INITIAL_SIZE 10000'
          }
        ]
        persistence: {
          rdbEnabled: true
          rdbFrequency: '6h'
          aofEnabled: false
        }
      }
    ]
  }
}

// ============================================================================
// EXAMPLE 7: Redis Enterprise with Geo-Replication Setup
// ============================================================================

// Secondary region setup (example for geo-replication)
module redisEnterpriseSecondary '../modules/app/am-redis.bicep' = if (environment == 'prod') {
  name: 'redis-enterprise-secondary-${environment}'
  params: {
    clusterName: '${appName}-redis-ent-sec-${environment}'
    location: 'West US 2' // Different region for geo-replication
    tags: union(tags, { role: 'secondary', replication: 'enabled' })
    sku: {
      name: 'Enterprise_E20'
      capacity: 4
    }
    zones: ['1', '2', '3']
    minimumTlsVersion: '1.2'
    enableSystemManagedIdentity: true
    databases: [
      {
        name: 'replica-db'
        port: 10000
        clientProtocol: 'Encrypted'
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'NoEviction'
        persistence: {
          rdbEnabled: true
          rdbFrequency: '6h'
          aofEnabled: false
        }
      }
    ]
  }
}

// ============================================================================
// OUTPUTS
// ============================================================================

// Basic Redis Enterprise outputs (dev environment)
output basicRedisEnterpriseHostName string = environment == 'dev' ? redisEnterpriseBasic.outputs.hostName : ''
output basicRedisEnterpriseDatabases array = environment == 'dev' ? redisEnterpriseBasic.outputs.databaseConnections : []

// Multi-database Redis Enterprise outputs (test environment)
output multiDBRedisEnterpriseHostName string = environment == 'test' ? redisEnterpriseMultiDB.outputs.hostName : ''
output multiDBRedisEnterpriseDatabases array = environment == 'test' ? redisEnterpriseMultiDB.outputs.databaseConnections : []
output multiDBConfigSummary object = environment == 'test' ? redisEnterpriseMultiDB.outputs.configurationSummary : {}

// Private Redis Enterprise outputs (prod environment)
output privateRedisEnterpriseHostName string = environment == 'prod' ? redisEnterprisePrivate.outputs.hostName : ''
output privateRedisEnterpriseDatabases array = environment == 'prod' ? redisEnterprisePrivate.outputs.databaseConnections : []
output privateRedisEnterprisePrivateEndpointIP array = environment == 'prod' ? redisEnterprisePrivate.outputs.privateEndpointIPs : []

// Flash Redis Enterprise outputs (prod environment)
output flashRedisEnterpriseHostName string = environment == 'prod' ? redisEnterpriseFlash.outputs.hostName : ''
output flashRedisEnterpriseDatabases array = environment == 'prod' ? redisEnterpriseFlash.outputs.databaseConnections : []

// Secondary Redis Enterprise outputs (prod environment)
output secondaryRedisEnterpriseHostName string = environment == 'prod' ? redisEnterpriseSecondary.outputs.hostName : ''
output secondaryRedisEnterpriseDatabases array = environment == 'prod' ? redisEnterpriseSecondary.outputs.databaseConnections : []

// Network outputs
output vnetId string = environment != 'dev' ? vnet.id : ''
output privateDnsZoneId string = environment != 'dev' ? privateDnsZone.id : ''
output keyVaultId string = environment == 'prod' ? keyVault.id : ''
output userAssignedIdentityId string = environment == 'prod' ? userAssignedIdentity.id : ''

// Application configuration for environment
output applicationConfiguration object = environment == 'dev' ? redisEnterpriseBasic.outputs.applicationConfig : (
  environment == 'test' ? multiDBRedisEnterpriseMultiDB.outputs.applicationConfig : redisEnterprisePrivate.outputs.applicationConfig
)

// Connection strings for primary databases (sensitive)
output primaryDatabaseConnections array = environment == 'dev' ? [
  {
    environment: 'dev'
    database: redisEnterpriseBasic.outputs.databaseConnections[0].name
    connectionString: redisEnterpriseBasic.outputs.databaseConnections[0].connectionString
    protocol: redisEnterpriseBasic.outputs.databaseConnections[0].clientProtocol
  }
] : environment == 'test' ? [for db in redisEnterpriseMultiDB.outputs.databaseConnections: {
  environment: 'test'
  database: db.name
  connectionString: db.connectionString
  protocol: db.clientProtocol
}] : [for db in redisEnterprisePrivate.outputs.databaseConnections: {
  environment: 'prod'
  database: db.name
  connectionString: db.connectionString
  protocol: db.clientProtocol
}]
