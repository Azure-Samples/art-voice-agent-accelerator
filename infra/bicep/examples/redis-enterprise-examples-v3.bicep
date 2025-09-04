/*
================================================================================
Azure Redis Enterprise Bicep Module - Comprehensive Usage Examples
================================================================================

This file demonstrates various deployment scenarios for the Azure Redis Enterprise
module, from basic setups to complex production configurations.

Examples included:
1. Basic Development Environment
2. Production Environment with Private Networking
3. Multi-Database Configuration with Redis Modules
4. Customer-Managed Encryption Setup
5. Geo-Replication Configuration
6. Comprehensive Monitoring and Diagnostics
7. High-Availability Multi-Zone Setup
8. Enterprise Flash for Ultra-Low Latency

Prerequisites for all examples:
- Resource Group
- Virtual Network with dedicated subnet (for private endpoints)
- Private DNS Zone: privatelink.redisenterprise.cache.azure.net
- Key Vault (for CMK examples)
- User-assigned Managed Identity (for CMK examples)
- Log Analytics Workspace (for monitoring examples)

Author: Azure AI Assistant
Version: 3.0
Last Modified: December 2024
*/

// ============================================================================
// SHARED PARAMETERS
// ============================================================================

@description('Resource name prefix for all resources')
param resourcePrefix string = 'contoso'

@description('Environment suffix (dev, test, prod)')
param environment string = 'dev'

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Common tags for all resources')
param commonTags object = {
  Environment: environment
  Project: 'Redis-Enterprise-Demo'
  CostCenter: 'IT-Infrastructure'
  Owner: 'Platform-Team'
}

// ============================================================================
// PREREQUISITE RESOURCES (SHARED)
// ============================================================================

// Virtual Network for Private Endpoints
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${resourcePrefix}-vnet-${environment}'
  location: location
  tags: commonTags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
    subnets: [
      {
        name: 'redis-subnet'
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
    ]
  }
}

// Private DNS Zone for Redis Enterprise
resource privateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.redisenterprise.cache.azure.net'
  location: 'global'
  tags: commonTags
}

// Link DNS Zone to VNet
resource dnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateDnsZone
  name: '${vnet.name}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

// Log Analytics Workspace for Monitoring
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${resourcePrefix}-logs-${environment}'
  location: location
  tags: commonTags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

// User-Assigned Managed Identity for Key Vault Access
resource userManagedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${resourcePrefix}-identity-${environment}'
  location: location
  tags: commonTags
}

// Key Vault for Customer-Managed Encryption
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${resourcePrefix}-kv-${environment}'
  location: location
  tags: commonTags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenant().tenantId
    enabledForDiskEncryption: true
    enabledForTemplateDeployment: true
    enabledForDeployment: true
    enableRbacAuthorization: true
    accessPolicies: []
  }
}

// Key for Customer-Managed Encryption
resource encryptionKey 'Microsoft.KeyVault/vaults/keys@2023-07-01' = {
  parent: keyVault
  name: 'redis-encryption-key'
  properties: {
    kty: 'RSA'
    keySize: 2048
    keyOps: [
      'encrypt'
      'decrypt'
      'sign'
      'verify'
      'wrapKey'
      'unwrapKey'
    ]
  }
}

// ============================================================================
// EXAMPLE 1: BASIC DEVELOPMENT ENVIRONMENT
// ============================================================================

module redisBasic '../modules/app/am-redis.bicep' = {
  name: 'redis-basic-${environment}'
  params: {
    clusterName: '${resourcePrefix}-redis-basic-${environment}'
    location: location
    tags: union(commonTags, {
      Purpose: 'Development'
      Example: 'Basic-Setup'
    })
    sku: {
      name: 'Enterprise_E10'
      capacity: 2
    }
    zones: [] // Single zone for cost optimization in dev
    enableSystemManagedIdentity: true
    enablePrivateEndpoint: false // Public endpoint for dev simplicity
    databases: [
      {
        name: 'cache'
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
// EXAMPLE 2: PRODUCTION ENVIRONMENT WITH PRIVATE NETWORKING
// ============================================================================

module redisProduction '../modules/app/am-redis.bicep' = {
  name: 'redis-production-${environment}'
  params: {
    clusterName: '${resourcePrefix}-redis-prod-${environment}'
    location: location
    tags: union(commonTags, {
      Purpose: 'Production'
      Example: 'Private-Networking'
      Tier: 'Critical'
    })
    sku: {
      name: 'Enterprise_E50'
      capacity: 4
    }
    zones: ['1', '2', '3'] // Multi-zone for high availability
    minimumTlsVersion: '1.2'
    enableSystemManagedIdentity: true
    
    // Private networking configuration
    enablePrivateEndpoint: true
    vnetResourceId: vnet.id
    subnetName: 'redis-subnet'
    privateDnsZoneResourceId: privateDnsZone.id
    privateEndpointName: '${resourcePrefix}-redis-pe-${environment}'
    
    // Database configuration
    databases: [
      {
        name: 'primary'
        clientProtocol: 'Encrypted'
        port: 10000
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'VolatileLRU'
        modules: [
          {
            name: 'RediSearch'
            args: 'MAXSEARCHRESULTS 10000 TIMEOUT 5000'
          }
        ]
        persistence: {
          aofEnabled: true
          aofFrequency: '1s'
          rdbEnabled: true
          rdbFrequency: '6h'
        }
      }
    ]
    
    // Monitoring configuration
    enableDiagnostics: true
    logAnalyticsWorkspaceId: logAnalytics.id
    enableAutomaticBackup: true
  }
}

// ============================================================================
// EXAMPLE 3: MULTI-DATABASE CONFIGURATION WITH REDIS MODULES
// ============================================================================

module redisMultiDatabase '../modules/app/am-redis.bicep' = {
  name: 'redis-multi-db-${environment}'
  params: {
    clusterName: '${resourcePrefix}-redis-multi-${environment}'
    location: location
    tags: union(commonTags, {
      Purpose: 'Multi-Database'
      Example: 'Redis-Modules'
    })
    sku: {
      name: 'Enterprise_E100'
      capacity: 6
    }
    zones: ['1', '2', '3']
    enableSystemManagedIdentity: true
    enablePrivateEndpoint: true
    vnetResourceId: vnet.id
    subnetName: 'redis-subnet'
    privateDnsZoneResourceId: privateDnsZone.id
    
    databases: [
      {
        name: 'search-database'
        clientProtocol: 'Encrypted'
        port: 10000
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'NoEviction'
        modules: [
          {
            name: 'RediSearch'
            args: 'MAXSEARCHRESULTS 100000 MAXAGGREGATERESULTS 10000'
          }
          {
            name: 'RedisJSON'
            args: ''
          }
        ]
        persistence: {
          aofEnabled: true
          aofFrequency: '1s'
          rdbEnabled: true
          rdbFrequency: '6h'
        }
      }
      {
        name: 'timeseries-database'
        clientProtocol: 'Encrypted'
        port: 10001
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'VolatileTTL'
        modules: [
          {
            name: 'RedisTimeSeries'
            args: 'RETENTION_POLICY 86400'
          }
        ]
        persistence: {
          aofEnabled: false
          rdbEnabled: true
          rdbFrequency: '12h'
        }
      }
      {
        name: 'bloom-database'
        clientProtocol: 'Encrypted'
        port: 10002
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'AllKeysLRU'
        modules: [
          {
            name: 'RedisBloom'
            args: 'ERROR_RATE 0.001 INITIAL_SIZE 10000'
          }
        ]
        persistence: {
          aofEnabled: false
          rdbEnabled: true
          rdbFrequency: '6h'
        }
      }
      {
        name: 'cache-database'
        clientProtocol: 'Encrypted'
        port: 10003
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'AllKeysLRU'
        modules: []
        persistence: {
          aofEnabled: false
          rdbEnabled: false
        }
      }
    ]
    
    enableDiagnostics: true
    logAnalyticsWorkspaceId: logAnalytics.id
    enableAutomaticBackup: true
  }
}

// ============================================================================
// EXAMPLE 4: CUSTOMER-MANAGED ENCRYPTION SETUP
// ============================================================================

// Key Vault access policy for the managed identity
resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, userManagedIdentity.id, 'Key Vault Crypto Officer')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '14b46e9e-c2b7-41b4-b07b-48a6ebf60603') // Key Vault Crypto Officer
    principalId: userManagedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

module redisEncryption '../modules/app/am-redis.bicep' = {
  name: 'redis-encryption-${environment}'
  params: {
    clusterName: '${resourcePrefix}-redis-cmk-${environment}'
    location: location
    tags: union(commonTags, {
      Purpose: 'Encryption'
      Example: 'Customer-Managed-Keys'
      Security: 'High'
    })
    sku: {
      name: 'Enterprise_E20'
      capacity: 2
    }
    zones: ['1', '2']
    
    // Identity configuration for encryption
    enableSystemManagedIdentity: true
    userAssignedIdentityIds: [userManagedIdentity.id]
    
    // Customer-managed encryption
    enableCustomerManagedEncryption: true
    keyVaultKeyUrl: encryptionKey.properties.keyUriWithVersion
    keyVaultIdentityId: userManagedIdentity.id
    
    // Private networking
    enablePrivateEndpoint: true
    vnetResourceId: vnet.id
    subnetName: 'redis-subnet'
    privateDnsZoneResourceId: privateDnsZone.id
    
    databases: [
      {
        name: 'encrypted-data'
        clientProtocol: 'Encrypted'
        port: 10000
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'NoEviction'
        modules: [
          {
            name: 'RedisJSON'
            args: ''
          }
        ]
        persistence: {
          aofEnabled: true
          aofFrequency: '1s'
          rdbEnabled: true
          rdbFrequency: '6h'
        }
      }
    ]
    
    enableDiagnostics: true
    logAnalyticsWorkspaceId: logAnalytics.id
    enableAutomaticBackup: true
  }
  dependsOn: [
    keyVaultRoleAssignment
  ]
}

// ============================================================================
// EXAMPLE 5: GEO-REPLICATION CONFIGURATION (PRIMARY REGION)
// ============================================================================

module redisGeoReplicationPrimary '../modules/app/am-redis.bicep' = {
  name: 'redis-geo-primary-${environment}'
  params: {
    clusterName: '${resourcePrefix}-redis-geo-primary-${environment}'
    location: location
    tags: union(commonTags, {
      Purpose: 'Geo-Replication'
      Example: 'Primary-Region'
      ReplicationRole: 'Primary'
    })
    sku: {
      name: 'Enterprise_E50'
      capacity: 4
    }
    zones: ['1', '2', '3']
    enableSystemManagedIdentity: true
    enablePrivateEndpoint: true
    vnetResourceId: vnet.id
    subnetName: 'redis-subnet'
    privateDnsZoneResourceId: privateDnsZone.id
    
    databases: [
      {
        name: 'replicated-data'
        clientProtocol: 'Encrypted'
        port: 10000
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'NoEviction'
        modules: []
        persistence: {
          aofEnabled: true
          aofFrequency: '1s'
          rdbEnabled: true
          rdbFrequency: '6h'
        }
        geoReplication: {
          groupNickname: 'global-redis-group'
          linkedDatabases: [] // Will be populated after secondary deployment
        }
      }
    ]
    
    enableDiagnostics: true
    logAnalyticsWorkspaceId: logAnalytics.id
    enableAutomaticBackup: true
  }
}

// ============================================================================
// EXAMPLE 6: ENTERPRISE FLASH FOR ULTRA-LOW LATENCY
// ============================================================================

module redisFlash '../modules/app/am-redis.bicep' = {
  name: 'redis-flash-${environment}'
  params: {
    clusterName: '${resourcePrefix}-redis-flash-${environment}'
    location: location
    tags: union(commonTags, {
      Purpose: 'Ultra-Low-Latency'
      Example: 'Enterprise-Flash'
      Performance: 'Maximum'
    })
    sku: {
      name: 'EnterpriseFlash_F300'
      capacity: 3
    }
    zones: ['1', '2', '3']
    minimumTlsVersion: '1.2'
    enableSystemManagedIdentity: true
    
    enablePrivateEndpoint: true
    vnetResourceId: vnet.id
    subnetName: 'redis-subnet'
    privateDnsZoneResourceId: privateDnsZone.id
    
    databases: [
      {
        name: 'high-performance-cache'
        clientProtocol: 'Encrypted'
        port: 10000
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'AllKeysLRU'
        modules: []
        persistence: {
          aofEnabled: false // Disabled for maximum performance
          rdbEnabled: true
          rdbFrequency: '12h'
        }
      }
      {
        name: 'real-time-analytics'
        clientProtocol: 'Encrypted'
        port: 10001
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'VolatileLRU'
        modules: [
          {
            name: 'RedisTimeSeries'
            args: 'RETENTION_POLICY 3600'
          }
        ]
        persistence: {
          aofEnabled: false
          rdbEnabled: false // No persistence for real-time data
        }
      }
    ]
    
    enableDiagnostics: true
    logAnalyticsWorkspaceId: logAnalytics.id
    enableAutomaticBackup: false // Not needed for cache-only workloads
  }
}

// ============================================================================
// EXAMPLE 7: COMPREHENSIVE MONITORING AND DIAGNOSTICS
// ============================================================================

module redisMonitoring '../modules/app/am-redis.bicep' = {
  name: 'redis-monitoring-${environment}'
  params: {
    clusterName: '${resourcePrefix}-redis-monitor-${environment}'
    location: location
    tags: union(commonTags, {
      Purpose: 'Monitoring-Demo'
      Example: 'Full-Observability'
    })
    sku: {
      name: 'Enterprise_E20'
      capacity: 2
    }
    zones: ['1', '2']
    enableSystemManagedIdentity: true
    
    enablePrivateEndpoint: true
    vnetResourceId: vnet.id
    subnetName: 'redis-subnet'
    privateDnsZoneResourceId: privateDnsZone.id
    
    databases: [
      {
        name: 'monitored-cache'
        clientProtocol: 'Encrypted'
        port: 10000
        clusteringPolicy: 'OSSCluster'
        evictionPolicy: 'AllKeysLRU'
        modules: [
          {
            name: 'RediSearch'
            args: 'MAXSEARCHRESULTS 1000'
          }
        ]
        persistence: {
          aofEnabled: true
          aofFrequency: '1s'
          rdbEnabled: true
          rdbFrequency: '6h'
        }
      }
    ]
    
    // Full monitoring configuration
    enableDiagnostics: true
    logAnalyticsWorkspaceId: logAnalytics.id
    enableAutomaticBackup: true
  }
}

// ============================================================================
// OUTPUTS FOR REFERENCE
// ============================================================================

// Basic deployment outputs
output basicRedisHostname string = redisBasic.outputs.hostName
output basicRedisConfig object = redisBasic.outputs.configurationSummary

// Production deployment outputs
output productionRedisConfig object = redisProduction.outputs.configurationSummary
output productionDatabaseConnections array = redisProduction.outputs.databaseConnections

// Multi-database outputs
output multiDatabaseConfig object = redisMultiDatabase.outputs.configurationSummary
output multiDatabaseNames array = redisMultiDatabase.outputs.databaseNames

// Encryption deployment outputs
output encryptionRedisConfig object = redisEncryption.outputs.configurationSummary

// Flash deployment outputs
output flashRedisPerformanceConfig object = redisFlash.outputs.configurationSummary

// Monitoring deployment outputs
output monitoringConfig object = redisMonitoring.outputs.configurationSummary
output monitoringEndpoints object = redisMonitoring.outputs.monitoringEndpoints

// Shared infrastructure outputs
output vnetId string = vnet.id
output privateDnsZoneId string = privateDnsZone.id
output logAnalyticsWorkspaceId string = logAnalytics.id
output userManagedIdentityId string = userManagedIdentity.id
output keyVaultId string = keyVault.id
