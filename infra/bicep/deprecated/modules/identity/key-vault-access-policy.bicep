/*
  Key Vault Access Policy Module
  
  This module manages access policies for Key Vault to handle cross-scope deployments
*/

@description('Key Vault name')
param keyVaultName string

@description('Principal ID to grant access to')
param certificateOrderPrincipalId string

@description('Tenant ID')
param tenantId string

// Key Vault resource
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// Access policy for certificate management
resource accessPolicy 'Microsoft.KeyVault/vaults/accessPolicies@2023-07-01' = {
  parent: keyVault
  name: 'add'
  properties: {
    accessPolicies: [
      {
        tenantId: tenantId
        objectId: certificateOrderPrincipalId
        permissions: {
          secrets: [
            'get'
            'set'
            'delete'
          ]
          certificates: [
            'get'
            'create'
            'import'
            'update'
            'delete'
            'list'
          ]
        }
      }
    ]
  }
}

// Outputs
output keyVaultId string = keyVault.id
output accessPolicyId string = accessPolicy.id
