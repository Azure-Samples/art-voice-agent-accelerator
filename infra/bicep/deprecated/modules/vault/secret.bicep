@description('The name of the Key Vault')
param keyVaultName string

@description('The name of the secret')
param secretName string

@description('The value of the secret')
@secure()
param secretValue string

@description('Tags to apply to the secret')
param tags object = {}

@description('Content type of the secret')
param contentType string = ''

@description('Expiration date of the secret in ISO 8601 format')
param expiresOn string = ''

@description('Not before date of the secret in ISO 8601 format')
param notBefore string = ''

@description('Whether the secret is enabled')
param enabled bool = true

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource secret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: secretName
  tags: tags
  properties: {
    value: secretValue
    contentType: contentType
    attributes: {
      enabled: enabled
      exp: !empty(expiresOn) ? dateTimeToEpoch(expiresOn) : null
      nbf: !empty(notBefore) ? dateTimeToEpoch(notBefore) : null
    }
  }
}

@description('The resource ID of the created secret')
output resourceId string = secret.id

@description('The name of the created secret')
output name string = secret.name

@description('The URI of the created secret')
output secretUri string = secret.properties.secretUri

@description('The URI of the created secret without version')
output secretUriWithoutVersion string = secret.properties.secretUriWithVersion
