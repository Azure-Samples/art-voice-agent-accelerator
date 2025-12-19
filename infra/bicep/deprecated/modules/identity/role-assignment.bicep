/*
  Role Assignment Module
  
  This module handles role assignments for managed identities with:
  - Support for built-in and custom roles
  - Multiple scopes (resource group, subscription, resource)
  - Condition-based access (ABAC)
  - Bulk assignments
*/

import { RoleAssignmentConfig, AzureBuiltInRole } from '../types.bicep'

@description('The principal ID to assign roles to')
param principalId string

@description('The principal type')
@allowed(['ServicePrincipal', 'User', 'Group'])
param principalType string = 'ServicePrincipal'

@description('Array of role assignments to create')
param roleAssignments RoleAssignmentConfig[]

@description('Resource group name for resource-scoped assignments')
param targetResourceGroupName string = resourceGroup().name

@description('Subscription ID for subscription-scoped assignments')
param targetSubscriptionId string = subscription().subscriptionId

// Built-in role definitions
var builtInRoles = loadJsonContent('../data/built-in-roles.json')

// Process each role assignment
resource roleAssignmentsResourceGroup 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (assignment, i) in roleAssignments: if (assignment.?scope == null || assignment.scope == 'resourceGroup') {
  name: guid(resourceGroup().id, principalId, assignment.roleDefinitionIdOrName, 'rg', string(i))
  scope: resourceGroup()
  properties: {
    principalId: principalId
    principalType: assignment.?principalType ?? principalType
    roleDefinitionId: contains(builtInRoles, assignment.roleDefinitionIdOrName) 
      ? subscriptionResourceId('Microsoft.Authorization/roleDefinitions', builtInRoles[assignment.roleDefinitionIdOrName])
      : contains(assignment.roleDefinitionIdOrName, '/') 
        ? assignment.roleDefinitionIdOrName
        : subscriptionResourceId('Microsoft.Authorization/roleDefinitions', assignment.roleDefinitionIdOrName)
    description: assignment.?description
    condition: assignment.?condition
    conditionVersion: assignment.?conditionVersion
  }
}]

resource roleAssignmentsResource 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (assignment, i) in roleAssignments: if (assignment.?scope == 'resource' && assignment.?resourceId != null) {
  name: guid(assignment.resourceId!, principalId, assignment.roleDefinitionIdOrName, 'res', string(i))
  scope: az.resourceId(split(assignment.resourceId!, '/')[2], split(assignment.resourceId!, '/')[4], split(assignment.resourceId!, '/')[6], split(assignment.resourceId!, '/')[7], split(assignment.resourceId!, '/')[8])
  properties: {
    principalId: principalId
    principalType: assignment.?principalType ?? principalType
    roleDefinitionId: contains(builtInRoles, assignment.roleDefinitionIdOrName) 
      ? subscriptionResourceId('Microsoft.Authorization/roleDefinitions', builtInRoles[assignment.roleDefinitionIdOrName])
      : contains(assignment.roleDefinitionIdOrName, '/') 
        ? assignment.roleDefinitionIdOrName
        : subscriptionResourceId('Microsoft.Authorization/roleDefinitions', assignment.roleDefinitionIdOrName)
    description: assignment.?description
    condition: assignment.?condition
    conditionVersion: assignment.?conditionVersion
  }
}]

// Outputs
output assignedRoles array = [for (assignment, i) in roleAssignments: {
  role: assignment.roleDefinitionIdOrName
  scope: assignment.?scope ?? 'resourceGroup'
  resourceId: assignment.?resourceId
  principalId: principalId
}]

output roleAssignmentIds array = concat(
  [for (assignment, i) in roleAssignments: if (assignment.?scope == null || assignment.scope == 'resourceGroup') roleAssignmentsResourceGroup[i].id],
  [for (assignment, i) in roleAssignments: if (assignment.?scope == 'resource') roleAssignmentsResource[i].id]
)
