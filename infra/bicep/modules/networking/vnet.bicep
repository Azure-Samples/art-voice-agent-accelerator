@description('The location for all resources')
param location string = resourceGroup().location

@description('Name of the Virtual Network')
param vnetName string 

import { SubnetConfig } from '../types.bicep'

@description('Address space for the Virtual Network')
param vnetAddressPrefix string

@description('List of Subnet configurations')
param subnets SubnetConfig[]

@description('Tags to apply to all resources')
param tags object = {}

@description('Resource ID of the Log Analytics workspace for diagnostics')
param workspaceResourceId string


resource vnet 'Microsoft.Network/virtualNetworks@2024-07-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    // subnets: [for subnet in subnets: {
    //   name: subnet.name
    //   properties: {
    //     addressPrefix: subnet.addressPrefix
    //     // Fix the delegation syntax
    //     delegations: subnet.?delegations ?? []
    //     // Add service endpoints if they exist
    //     serviceEndpoints: subnet.?serviceEndpoints ?? []
    //     // // Ensure private endpoint policies are disabled for delegation compatibility
    //     // privateEndpointNetworkPolicies: 'Disabled'
    //     // privateLinkServiceNetworkPolicies: 'Disabled'  
    //   }
    // }]
  }
}
@batchSize(1)
// Network Security Groups for each subnet
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = [for subnet in subnets: {
  name: 'nsg-${subnet.name}'
  location: location
  tags: tags
  properties: {
    securityRules: subnet.?securityRules ?? []
  }
  dependsOn: [
    vnet
  ]
}]

@batchSize(1)
// Associate NSGs with subnets
resource subnetUpdate 'Microsoft.Network/virtualNetworks/subnets@2024-07-01' = [for (subnet, i) in subnets: {
  name: subnet.name
  parent: vnet
  properties: {
    addressPrefix: subnet.addressPrefix
    networkSecurityGroup: {
      id: nsg[i].id
    }
    delegations: subnet.?delegations ?? []
    serviceEndpoints: subnet.?serviceEndpoints ?? []
  }
  dependsOn: [
    nsg[i]
  ]
}]

@batchSize(1)
// Diagnostic settings for NSGs
resource nsgDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = [for (subnet, i) in subnets: {
  name: 'diag-${nsg[i].name}'
  scope: nsg[i]
  properties: {
    workspaceId: workspaceResourceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}]
// var subnetResourceIds = [for subnet in subnets: resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, subnet.name)]

// Diagnostic settings for VNet
resource vnetDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${vnet.name}'
  scope: vnet
  properties: {
    workspaceId: workspaceResourceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// Output VNet and subnet details for downstream modules
output vnetId string = vnet.id
output vnetName string = vnet.name
// output subnetResourceIds array = subnetResourceIds
output subnetNames array = [for subnet in subnets: subnet.name]
output subnets object = toObject(subnets, subnet => subnet.name, subnet => resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, subnet.name))

// output privateDnsZoneId string = enablePrivateDnsZone && role == 'hub' ? privateDnsZone.id : ''
// output privateDnsZoneName string = enablePrivateDnsZone && role == 'hub' ? privateDnsZone.name : ''
// output vnetLinksLink string = role == 'spoke' ? vnetLinks.id : ''
output resourceGroupName string = resourceGroup().name
