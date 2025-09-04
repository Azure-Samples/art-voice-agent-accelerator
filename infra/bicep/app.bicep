@description('The location used for all deployed resources')
param location string = resourceGroup().location

@description('Tags that will be applied to all resources')
param tags object = {}

@description('Name of the environment that can be used as part of naming resource convention')
param name string

import { ContainerAppKvSecret } from './modules/types.bicep'

// AZD managed variables
param rtaudioClientExists bool
param rtaudioServerExists bool

// Required parameters for the app environment (app config values, secrets, etc.)
@description('Enable EasyAuth for the frontend internet facing container app')
param enableEasyAuth bool = true

param logAnalyticsWorkspaceResourceId string = '00000000-0000-0000-0000-000000000000'

// Network parameters for reference
// param vnetName string
// param appgwSubnetResourceId string
param appSubnetResourceId string

@description('Id of the user or app to assign application roles')
param principalId string
param principalType string

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = uniqueString(subscription().id, resourceGroup().id, location)

param frontendEnvVars array = []

param backendUserAssignedIdentity object = {}
param frontendUserAssignedIdentity object = {}
param frontendExternalAccessEnabled bool = true

param backendCors object = {}
param backendSecrets ContainerAppKvSecret[] 
param backendEnvVars array = []

param backendCertificate object = {}
param backendCustomDomains array = []

var beContainerName =  toLower(substring('rtagent-server-${resourceToken}', 0, 22))
var feContainerName =  toLower(substring('rtagent-client-${resourceToken}', 0, 22))

// Container registry
module containerRegistry 'br/public:avm/res/container-registry/registry:0.1.1' = {
  name: 'registry'
  params: {
    name: '${name}${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
    publicNetworkAccess: 'Enabled'
    roleAssignments: [
      {
        principalId: principalId
        principalType: principalType
        roleDefinitionIdOrName: 'AcrPull'
      }
      {
        principalId: principalId
        principalType: principalType
        roleDefinitionIdOrName: 'AcrPush'
      }
      // Temporarily disabled - managed identity deployment timing issue
      {
        principalId: frontendUserAssignedIdentity.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'AcrPull'
      }
      {
        principalId: backendUserAssignedIdentity.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'AcrPull'
      }
    ]
  }
}

// Container apps environment (deployed into appSubnet)
module externalContainerAppsEnvironment 'br/public:avm/res/app/managed-environment:0.11.2' = if (frontendExternalAccessEnabled){
  name: 'external-container-apps-environment'
  params: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsWorkspaceResourceId, '2022-10-01').customerId
        sharedKey: listKeys(logAnalyticsWorkspaceResourceId, '2022-10-01').primarySharedKey
      }
    }
    publicNetworkAccess: frontendExternalAccessEnabled == true ? 'Enabled' : 'Disabled' // Enables public access to the Container Apps Environment
    name: 'ext-${name}${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    zoneRedundant: false
    infrastructureSubnetResourceId: frontendExternalAccessEnabled == true ? null : appSubnetResourceId // Enables private networking in the specified subnet
    internal: frontendExternalAccessEnabled == false
    tags: tags
  }
}

param privateDnsZoneResourceId string = ''
param privateEndpointSubnetResourceId string = ''

// Container apps environment (deployed into appSubnet)
module containerAppsEnvironment 'br/public:avm/res/app/managed-environment:0.11.2' = {
  name: 'container-apps-environment'
  params: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsWorkspaceResourceId, '2022-10-01').customerId
        sharedKey: listKeys(logAnalyticsWorkspaceResourceId, '2022-10-01').primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'D4'
        workloadProfileType: 'D4'
        maximumCount: 10
        minimumCount: 1
      }
    ]
    managedIdentities: {
      systemAssigned: false
      userAssignedResourceIds: !empty(backendCertificate) ? [backendCertificate.?certificateKeyVaultProperties.?identityResourceId] : []
    }
    certificate: backendCertificate // Optional SSL certificate for the backend container app

    publicNetworkAccess: 'Disabled' // Disables public access to the Container Apps Environment
    name: '${name}${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    zoneRedundant: false
    infrastructureSubnetResourceId: appSubnetResourceId // Enables private networking in the specified subnet
    internal: appSubnetResourceId != '' ? true : false
    tags: tags
  }
}

// Private endpoint for Container Apps Environment
module containerAppsPrivateEndpoint './modules/networking/private-endpoint.bicep' = if (privateDnsZoneResourceId != '' && privateEndpointSubnetResourceId != '') {
    name: 'backend-container-apps-private-endpoint'
    params: {
      name: 'pe-${name}${resourceToken}'
      location: location
      tags: tags
      subnetId: privateEndpointSubnetResourceId
      serviceId: containerAppsEnvironment.outputs.resourceId
      groupIds: ['managedEnvironments']
      dnsZoneId: privateDnsZoneResourceId
    }
}


module fetchFrontendLatestImage './modules/app/fetch-container-image.bicep' = {
  name: 'gbbAiAudioAgent-fetch-image'
  params: {
    exists: rtaudioClientExists
    name: feContainerName
  }
}
module fetchBackendLatestImage './modules/app/fetch-container-image.bicep' = {
  name: 'gbbAiAudioAgentBackend-fetch-image'
  params: {
    exists: rtaudioServerExists
    name: beContainerName
  }
}

module frontendAudioAgent 'modules/app/container-app.bicep' = {
  name: 'frontend-audio-agent'
  params: {
    name: feContainerName
    enableEasyAuth: enableEasyAuth
    corsPolicy: {
      allowedOrigins: [
        'http://localhost:5173'
        'http://localhost:3000'
      ]
      allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
      allowedHeaders: ['*']
      allowCredentials: false
    }
    
    ingressExternal: true

    ingressTargetPort: 5173
    scaleMinReplicas: 1
    scaleMaxReplicas: 10
    stickySessionsAffinity: 'sticky'
    containers: [
      {
        image: fetchFrontendLatestImage.outputs.?containers[?0].?image ?? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        name: 'main'
        resources: {
          cpu: json('0.5')
          memory: '1.0Gi'
        }
        env: frontendEnvVars
      }
    ]
    userAssignedResourceId: frontendUserAssignedIdentity.resourceId

    registries: [
      {
        server: containerRegistry.outputs.loginServer
        identity: frontendUserAssignedIdentity.resourceId
      }
    ]
    
    environmentResourceId: frontendExternalAccessEnabled ? externalContainerAppsEnvironment.outputs.resourceId : containerAppsEnvironment.outputs.resourceId
    // environmentResourceId: containerAppsEnvironment.outputs.resourceId
    location: location
    tags: union(tags, { 'azd-service-name': 'rtaudio-client' })
  }
  dependsOn: [
  ]
}

// Update backend CORS to include frontend container app origin
var updatedBackendCors = union(backendCors, {
  allowedOrigins: union(
    backendCors.?allowedOrigins ?? [],
    [
      'https://${frontendAudioAgent.outputs.containerAppFqdn}'
      'http://${frontendAudioAgent.outputs.containerAppFqdn}'
    ]
  )
})

module backendAudioAgent './modules/app/container-app.bicep' = {
  name: 'backend-audio-agent'
  params: {
    name: beContainerName
    ingressTargetPort: 8010
    scaleMinReplicas: 1
    scaleMaxReplicas: 10
    secrets: backendSecrets
    corsPolicy: updatedBackendCors

    ingressExternal: true // Limit to VNet, setting to false will limit network to Container App Environment
    customDomains: [
      // {
      //   name: backendCertificate.?domainName
      //   // /subscriptions/63862159-43c8-47f7-9f6f-6c63d56b0e17/resourceGroups/rg-spoke-rtaudioagent-localdev/providers/Microsoft.App/managedEnvironments/rtaudioagentcae-7ggx3vub2aaci/certificates/rtaudio-fullchain-fixed
      //   certificateId: '${containerAppsEnvironment.outputs.resourceId}/certificates/${backendCertificate.?name}'
      //   bindingType: 'Auto'
      // }
    ]
    containers: [
      {
        image: fetchBackendLatestImage.outputs.?containers[?0].?image ?? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        name: 'main'
        resources: {
          cpu: json('1.0')
          memory: '2.0Gi'
        }
        
        env: backendEnvVars
      }
    ]
    userAssignedResourceId: backendUserAssignedIdentity.?resourceId ?? ''
    registries: [
      {
        server: containerRegistry.outputs.loginServer
        identity: backendUserAssignedIdentity.?resourceId ?? ''
      }
    ]
    environmentResourceId: containerAppsEnvironment.outputs.resourceId
    location: location
    tags: union(tags, { 'azd-service-name': 'rtaudio-server' })
  }
}


// Outputs for downstream consumption and integration

// Container Registry
@description('The login server URL for the container registry')
output containerRegistryEndpoint string = containerRegistry.outputs.loginServer

@description('The resource ID of the container registry')
output containerRegistryResourceId string = containerRegistry.outputs.resourceId

@description('The resource ID of the container apps environment')
output containerAppsEnvironmentId string = containerAppsEnvironment.outputs.resourceId

@description('The resource ID of the backend container app')
output backendContainerAppResourceId string = backendAudioAgent.outputs.containerAppResourceId

@description('The name of the frontend container app')
output frontendAppName string = feContainerName

@description('The name of the backend container app')
output backendAppName string = beContainerName

@description('The container app name of the frontend application')
output frontendContainerAppName string = frontendAudioAgent.outputs.containerAppName

@description('The container app name of the backend application')
output backendContainerAppName string = backendAudioAgent.outputs.containerAppName

@description('The fully qualified domain name of the frontend container app')
output frontendContainerAppFqdn string = frontendAudioAgent.outputs.containerAppFqdn

@description('The fully qualified domain name of the backend container app')
output backendContainerAppFqdn string = backendAudioAgent.outputs.containerAppFqdn

// NOTE: These parameters are currently not used directly in this file, but are available for future use and for passing to modules that support subnet assignment.
