/*
================================================================================
Example Usage: Azure Redis Cache Module
================================================================================

This file demonstrates various ways to deploy the Redis Cache module with
different configurations including basic deployment, private networking,
and premium features.
*/

// ============================================================================
// PARAMETERS
// ============================================================================

@description('Environment name (dev, staging, prod)')
param environmentName string = 'dev'

@description('Application name')
param applicationName string = 'rtmedagent'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Common tags for all resources')
param commonTags object = {
  Environment: environmentName
  Application: applicationName
  ManagedBy: 'Bicep'
}

// ============================================================================
// EXISTING RESOURCES (for private networking examples)
// ============================================================================

// Reference to existing virtual network (uncomment if using private networking)
// resource virtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
//   name: 'vnet-${applicationName}-${environmentName}'
// }

// Reference to existing private DNS zone (uncomment if using private networking)
// resource privateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' existing = {
//   name: 'privatelink.redis.cache.windows.net'
// }

// ============================================================================
// EXAMPLE 1: BASIC REDIS CACHE (Development)
// ============================================================================

module redisBasic '../redis.bicep' = {
  name: 'redis-basic-deployment'
  params: {
    redisCacheName: 'redis-${applicationName}-${environmentName}-basic'
    location: location
    tags: commonTags
    sku: {
      name: 'Basic'
      family: 'C'
      capacity: 0
    }
    redisVersion: 'latest'
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

// ============================================================================
// EXAMPLE 2: STANDARD REDIS CACHE (Staging)
// ============================================================================

module redisStandard '../redis.bicep' = {
  name: 'redis-standard-deployment'
  params: {
    redisCacheName: 'redis-${applicationName}-${environmentName}-standard'
    location: location
    tags: commonTags
    sku: {
      name: 'Standard'
      family: 'C'
      capacity: 1
    }
    redisVersion: '6.0'
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    
    // Custom Redis configuration
    redisConfiguration: {
      'notify-keyspace-events': 'KEA'
    }
    
    // Memory management
    memoryConfiguration: {
      maxmemoryPolicy: 'allkeys-lru'
    }
  }
}

// ============================================================================
// EXAMPLE 3: PREMIUM REDIS CACHE WITH PRIVATE NETWORKING (Production)
// ============================================================================

module redisPremiumPrivate '../redis.bicep' = {
  name: 'redis-premium-private-deployment'
  params: {
    redisCacheName: 'redis-${applicationName}-${environmentName}-premium'
    location: location
    tags: commonTags
    sku: {
      name: 'Premium'
      family: 'P'
      capacity: 1
    }
    redisVersion: 'latest'
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    
    // Zone redundancy for high availability
    enableZoneRedundancy: true
    zones: ['1', '2', '3']
    
    // Replication for read scaling
    replicasPerPrimary: 1
    
    // Private networking configuration
    privateNetworking: {
      enabled: true
      vnetResourceId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network/providers/Microsoft.Network/virtualNetworks/vnet-${applicationName}-${environmentName}'
      subnetName: 'redis-subnet'
      privateDnsZoneResourceId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.redis.cache.windows.net'
      privateEndpointName: 'pe-redis-${applicationName}-${environmentName}'
    }
    
    // Managed Identity
    identity: {
      type: 'SystemAssigned'
    }
    
    // Backup configuration
    backupConfiguration: {
      rdbBackupEnabled: true
      rdbBackupFrequency: 360
      rdbBackupMaxSnapshotCount: 3
      rdbStorageConnectionString: 'DefaultEndpointsProtocol=https;AccountName=storageaccount;AccountKey=key;EndpointSuffix=${environment().suffixes.storage}'
    }
    
    // Memory configuration
    memoryConfiguration: {
      maxmemoryPolicy: 'allkeys-lru'
      maxmemoryReserved: '125'
      maxmemoryDelta: '125'
      maxfragmentationmemoryReserved: '125'
    }
    
    // Custom Redis configuration
    redisConfiguration: {
      'notify-keyspace-events': 'KEA'
      maxclients: '1000'
    }
  }
}

// ============================================================================
// EXAMPLE 4: PREMIUM REDIS CACHE WITH CLUSTERING
// ============================================================================

module redisPremiumCluster '../redis.bicep' = {
  name: 'redis-premium-cluster-deployment'
  params: {
    redisCacheName: 'redis-${applicationName}-${environmentName}-cluster'
    location: location
    tags: commonTags
    sku: {
      name: 'Premium'
      family: 'P'
      capacity: 3
    }
    redisVersion: 'latest'
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    
    // Clustering configuration
    shardCount: 3
    
    // Zone redundancy
    enableZoneRedundancy: true
    
    // Memory configuration for cluster
    memoryConfiguration: {
      maxmemoryPolicy: 'allkeys-lru'
    }
  }
}

// ============================================================================
// EXAMPLE 5: REDIS CACHE WITH AAD AUTHENTICATION
// ============================================================================

module redisAAD '../redis.bicep' = {
  name: 'redis-aad-deployment'
  params: {
    redisCacheName: 'redis-${applicationName}-${environmentName}-aad'
    location: location
    tags: commonTags
    sku: {
      name: 'Standard'
      family: 'C'
      capacity: 2
    }
    redisVersion: 'latest'
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    disableAccessKeyAuthentication: true
    publicNetworkAccess: 'Enabled'
    
    // Managed Identity for AAD authentication
    identity: {
      type: 'SystemAssigned'
    }
  }
}

// ============================================================================
// OUTPUTS
// ============================================================================

// Basic Redis outputs
output redisBasicEndpoint string = redisBasic.outputs.hostName
// Note: Connection strings contain secrets and should be retrieved from Key Vault or module outputs directly

// Standard Redis outputs
output redisStandardEndpoint string = redisStandard.outputs.hostName
// Note: Connection strings contain secrets and should be retrieved from Key Vault or module outputs directly

// Premium Redis outputs
output redisPremiumEndpoint string = redisPremiumPrivate.outputs.hostName
output redisPremiumPrivateEndpointId string = redisPremiumPrivate.outputs.privateEndpointId

// Cluster Redis outputs
output redisClusterEndpoint string = redisPremiumCluster.outputs.hostName
output redisClusterConfig object = redisPremiumCluster.outputs.configurationSummary

// AAD Redis outputs
output redisAADEndpoint string = redisAAD.outputs.hostName
output redisAADConfig object = redisAAD.outputs.configurationSummary
