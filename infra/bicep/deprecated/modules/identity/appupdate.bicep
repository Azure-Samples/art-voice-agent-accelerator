metadata description = 'Creates an Azure Container Apps Auth Config using Microsoft Entra as Identity Provider.'

@description('The name of the container apps resource within the current resource group scope')
param containerAppName string

@description('The client ID of the Microsoft Entra application.')
param clientId string

param openIdIssuer string

@description('Enable token store for the Container App.')
param includeTokenStore bool = false

@description('The URI of the Azure Blob Storage container to be used for token storage.')
param blobContainerUri string = ''
@description('The resource ID of the managed identity to be used for accessing the Azure Blob Storage.')
param appIdentityResourceId string = ''

resource app 'Microsoft.App/containerApps@2023-05-01' existing = {
  name: containerAppName
}

resource auth 'Microsoft.App/containerApps/authConfigs@2024-10-02-preview' = {
  parent: app
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      redirectToProvider: 'azureactivedirectory'
      unauthenticatedClientAction: 'RedirectToLoginPage'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: clientId
          clientSecretSettingName: 'override-use-mi-fic-assertion-client-id'
          openIdIssuer: openIdIssuer
        }
        validation: {
          defaultAuthorizationPolicy: {
            allowedApplications: [
            ]
          }
        }
      }
    }
    login: {
      // https://learn.microsoft.com/azure/container-apps/token-store
      tokenStore: {
        enabled: includeTokenStore
        azureBlobStorage: includeTokenStore ? {
          blobContainerUri: blobContainerUri
          managedIdentityResourceId: appIdentityResourceId
        } : {}
      }
    }
  }
}
