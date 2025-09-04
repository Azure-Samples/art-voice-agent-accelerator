@description('Name of the container app')
param name string

@description('Ingress target port for the container app')
param ingressTargetPort int

@description('Minimum number of replicas')
param scaleMinReplicas int = 1

@description('Maximum number of replicas')
param scaleMaxReplicas int = 10

@description('Sticky session affinity (optional)')
param stickySessionsAffinity string = 'none'

@description('Container definitions for the app')
param containers array

@description('User-assigned managed identity resource ID')
param userAssignedResourceId string = ''

@description('Container registry definitions')
param registries array = []

param customDomains array = []

@description('Resource ID of the container apps environment')
param environmentResourceId string

@description('Location for the container app')
param location string

@description('Tags for the container app')
param tags object = {}

@description('Array of secrets at the container app control plane level. Each item is an object: { name: <secret name>, value: <secret value> }')
param secrets secretType[] = []

@description('Array of secret references for environment variables. Each item is an object: { name: <env var>, secretRef: <secret name> }')
param secretEnvRefs SecretEnvVarType[] = []

@description('Ingress settings for the container app')
param ingressExternal bool = false

@description('Enable EasyAuth integration')
param enableEasyAuth bool = false

@description('Issuer URL for EasyAuth')
param issuer string = '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'

var _secrets = enableEasyAuth
  ? union([
      {
        name: 'override-use-mi-fic-assertion-client-id'
        value: userAssignedIdentity.properties.clientId
      }
    ], secrets)
  : secrets

@export()
@description('The type for a secret.')
type secretType = {
  @description('Optional. Resource ID of a managed identity to authenticate with Azure Key Vault, or System to use a system-assigned identity.')
  identity: string?

  @description('Conditional. The URL of the Azure Key Vault secret referenced by the Container App. Required if `value` is null.')
  keyVaultUrl: string?

  @description('Optional. The name of the container app secret.')
  name: string?

  @description('Conditional. The container app secret value, if not fetched from the Key Vault. Required if `keyVaultUrl` is not null.')
  @secure()
  value: string?
}

type SecretEnvVarType = {
  name: string
  secretRef: string
}
param corsPolicy object = {}

resource userAssignedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2018-11-30' existing = if (!empty(userAssignedResourceId)) {
  scope: resourceGroup()
  name: last(split(userAssignedResourceId, '/'))
}

module containerApp 'br/public:avm/res/app/container-app:0.16.0' = {
  name: name
  params: {
    name: name
    location: location
    tags: tags
    environmentResourceId: environmentResourceId
    secrets: _secrets
    managedIdentities: {
      userAssignedResourceIds: [
        userAssignedResourceId
      ]
    }
    customDomains: customDomains
    registries: registries
    containers: [for c in containers: {
      name: c.name
      image: c.image
      resources: c.resources
      env: union(
        c.env,
        secretEnvRefs
      )
    }]
    scaleSettings: {
      minReplicas: scaleMinReplicas
      maxReplicas: scaleMaxReplicas
    }
    corsPolicy: corsPolicy
    ingressExternal: ingressExternal
    ingressTargetPort: ingressTargetPort
    stickySessionsAffinity: stickySessionsAffinity
    trafficLatestRevision: true
    trafficWeight: 100
  }
}

// ----------------------------------------------------------------------------------------
// Enabling EasyAuth for the ContainerApp (if enabled via param)
// ----------------------------------------------------------------------------------------
module easyAuthAppReg '../identity/appregistration.bicep' = if (enableEasyAuth) {
  name: 'easyauth-reg'
  params: {
    clientAppName: '${name}-easyauth-client-app'
    clientAppDisplayName: '${name}-EasyAuth-app'
    webAppEndpoint: 'https://${containerApp.outputs.fqdn}'
    webAppIdentityId: empty(userAssignedResourceId) 
      ? (containerApp.outputs.?systemAssignedMIPrincipalId ?? '') 
      : userAssignedIdentity.properties.clientId
    issuer: issuer
  }
}

module containerAppUpdate '../identity/appupdate.bicep' = if (enableEasyAuth) {
  name: 'easyauth-${name}-appupdate'
  params: {
    containerAppName: containerApp.outputs.name
    clientId: easyAuthAppReg.outputs.clientAppId
    openIdIssuer: issuer
  }
}

// ----------------------------------------------------------------------------------------
// Outputs
// ----------------------------------------------------------------------------------------

@description('The name of the container app.')
output containerAppName string = containerApp.outputs.name

@description('The fully qualified domain name (FQDN) of the container app.')
output containerAppFqdn string = containerApp.outputs.fqdn

@description('The resource ID of the container app.')
output containerAppResourceId string = containerApp.outputs.resourceId

@description('The principal ID of the system-assigned managed identity, if enabled.')
output systemAssignedMIPrincipalId string = empty(userAssignedResourceId) ? (containerApp.outputs.?systemAssignedMIPrincipalId ?? '') : ''

@description('The principal ID of the user-assigned managed identity, if configured.')
output userAssignedMIPrincipalId string = !empty(userAssignedResourceId) ? userAssignedIdentity.properties.principalId : ''

@description('The client ID of the EasyAuth application registration, if EasyAuth is enabled.')
output easyAuthClientAppId string = enableEasyAuth ? easyAuthAppReg.outputs.clientAppId : ''
