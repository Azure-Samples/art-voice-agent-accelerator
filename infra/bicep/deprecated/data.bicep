targetScope = 'resourceGroup'

// Required parameters
@description('The abbreviations object for resource naming')
var abbrs = loadJsonContent('./abbreviations.json')

@description('Unique token for resource naming')
param resourceToken string

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Resource tags')
param tags object = {}

@description('The name prefix for resources')
param name string

@description('Storage SKU name')
param storageSkuName string = 'Standard_LRS'

@description('Storage container name for audio files')
param storageContainerName string = 'audioagent'

@description('Key Vault resource ID for storing secrets')
param keyVaultResourceId string

@description('Private endpoint subnet resource ID')
param privateEndpointSubnetId string

@description('Cosmos DB DNS zone resource ID for private endpoint')
param cosmosDnsZoneId string

// Database parameters
param databaseName string = 'audioagentdb'
@description('Maximum autoscale throughput for the database shared with up to 25 collections')
@minValue(1000)
@maxValue(1000000)
param sharedAutoscaleMaxThroughput int = 1000

param collectionName string = 'audioagentcollection'
// App code needs to support the RBAC first. Currently, it uses local auth.
// @description('Disable local authentication for Cosmos DB')
// param disableLocalAuth bool = false
var disableLocalAuth = false

@description('Backend user assigned identity for RBAC')
param userAssignedIdentity object = {}

@description('Principal ID for RBAC assignments')
param principalId string = ''

@description('Principal type for RBAC assignments')
param principalType string = 'User'

// Storage Account
module storage 'br/public:avm/res/storage/storage-account:0.9.1' = {
  name: 'storage'
  params: {
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
    kind: 'StorageV2'
    skuName: storageSkuName
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
          name: storageContainerName
          publicAccess: 'None'
        }
        {
          name: 'prompt'
          publicAccess: 'None'
        }
      ]
    }
    roleAssignments: !empty(userAssignedIdentity) ? [
      {
        roleDefinitionIdOrName: 'Storage Blob Data Contributor'
        principalId: userAssignedIdentity.principalId
        principalType: 'ServicePrincipal'
      }
    ] : []
  }
}

// Cosmos DB MongoDB Cluster
resource mongoCluster 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: 'mongodb${resourceToken}'
  location: location
  tags: tags
  kind: 'MongoDB'
  properties: {
    disableLocalAuth: disableLocalAuth
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    apiProperties: {
      serverVersion: '7.0'
    }
    capabilities: [
      {
        name: 'EnableMongo'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    publicNetworkAccess: 'Enabled'
  }
}
resource database 'Microsoft.DocumentDB/databaseAccounts/mongodbDatabases@2022-05-15' = {
  parent: mongoCluster
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
    options: {
      autoscaleSettings: {
        maxThroughput: sharedAutoscaleMaxThroughput
      }
    }
  }
}

resource collection 'Microsoft.DocumentDb/databaseAccounts/mongodbDatabases/collections@2022-05-15' = {
  parent: database
  name: collectionName
  properties: {
    resource: {
      id: collectionName
      indexes: [
        {
          key: {
            keys: [
              '_id'
            ]
          }
        }
        {
          key: {
            keys: [
              '$**'
            ]
          }
        }
      ]
    }
  }
}

// MongoDB Private Endpoint
module mongoPrivateEndpoint 'br/public:avm/res/network/private-endpoint:0.7.1' = if (!empty(privateEndpointSubnetId) && !empty(cosmosDnsZoneId)) {
  name: 'mongo-pe-${name}-${resourceToken}'
  params: {
    name: 'mongo-pe-${name}-${resourceToken}'
    location: location
    subnetResourceId: privateEndpointSubnetId
    privateLinkServiceConnections: [
      {
        name: 'mongo-pls-${name}-${resourceToken}'
        properties: {
          privateLinkServiceId: mongoCluster.id
          groupIds: [
            'MongoDB'
          ]
        }
      }
    ]
    privateDnsZoneGroup: {
      privateDnsZoneGroupConfigs: [
        {
          name: 'default'
          privateDnsZoneResourceId: cosmosDnsZoneId
        }
      ]
    }
    // roleAssignments: !empty(userAssignedIdentity) ? [
    //   {
    //     roleDefinitionIdOrName: 'Cosmos DB Account User'
    //     principalId: userAssignedIdentity.principalId
    //     principalType: 'ServicePrincipal'
    //   }
    // ] : []
  }
}

// Store MongoDB connection string in Key Vault if local auth is enabled
resource mongoConnectionString 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!disableLocalAuth) {
  name: '${last(split(keyVaultResourceId, '/'))}/mongo-connection-string'
  properties: {
    value: mongoCluster.listConnectionStrings().connectionStrings[0].connectionString
  }
}

// Outputs
@description('Storage account resource ID')
output storageAccountResourceId string = storage.outputs.resourceId

@description('Storage account name')
output storageAccountName string = storage.outputs.name

@description('Storage account blob endpoint')
output storageAccountBlobEndpoint string = storage.outputs.primaryBlobEndpoint

@description('MongoDB cluster resource ID')
output mongoClusterResourceId string = mongoCluster.id

@description('MongoDB cluster name')
output mongoClusterName string = mongoCluster.name

@description('MongoDB connection string (only if local auth enabled)')
output mongoConnectionStringSecretName string = !disableLocalAuth ? 'mongo-connection-string' : ''
output mongoConnectionStringSecretUri string = !disableLocalAuth ? mongoConnectionString.properties.secretUri : ''

@description('MongoDB database resource ID')
output mongoDatabaseResourceId string = database.id

@description('MongoDB database name')
output mongoDatabaseName string = database.name

@description('MongoDB collection resource ID')
output mongoCollectionResourceId string = collection.id

@description('MongoDB collection name')
output mongoCollectionName string = collection.name
