@description('The name of the local Virtual Network')
param localVnetName string

@description('The name of the remote Virtual Network')
param remoteVnetName string

@description('The ID of the remote virtual network')
param remoteVnetId string

resource vnetPeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2021-08-01' = {
  name: '${localVnetName}/peerTo-${remoteVnetName}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: remoteVnetId
    }
  }
}
