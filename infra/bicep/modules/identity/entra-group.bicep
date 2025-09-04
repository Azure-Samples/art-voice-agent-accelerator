extension microsoftGraphV1

@description('The name of the Entra ID group')
param groupName string

@description('The display name of the Entra ID group')
param groupDisplayName string = groupName

@description('The description of the Entra ID group')
param groupDescription string = ''

@description('The type of the group (Unified for Microsoft 365 groups, Security for security groups)')
@allowed(['Unified', 'Security'])
param groupType string = 'Security'

@description('Whether the group is mail-enabled')
param mailEnabled bool = false

@description('Whether the group is security-enabled')
param securityEnabled bool = true

@description('The visibility of the group (Public, Private, HiddenMembership)')
@allowed(['Public', 'Private', 'HiddenMembership'])
param visibility string = 'Private'

@description('Initial members to add to the group (object IDs)')
param initialMembers array = []

@description('Initial owners to add to the group (object IDs)')
param initialOwners array = []

resource entraGroup 'Microsoft.Graph/groups@v1.0' = {
  displayName: groupDisplayName
  uniqueName: groupName
  description: groupDescription
  groupTypes: groupType == 'Unified' ? ['Unified'] : []
  mailEnabled: mailEnabled
  securityEnabled: securityEnabled
  visibility: visibility
  members: initialMembers
  owners: initialOwners
}

@description('The object ID of the created group')
output groupId string = entraGroup.id

@description('The display name of the created group')
output groupDisplayName string = entraGroup.displayName

@description('The unique name of the created group')
output groupName string = entraGroup.uniqueName
