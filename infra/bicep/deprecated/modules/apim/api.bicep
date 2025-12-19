@description('The name of the API to be appended in resource names.')
param name string

@description('The description for the API.')
param apiDescription string

@description('The display name for the API.')
param apiDisplayName string

@description('The path for the API.')
param apiPath string

@description('The name of the existing API Management (APIM) service.')
param apimName string

@description('The Text Content of the Policy.')
param policyContent string

@description('The URL for the API specification.')
param apiSpecURL string
@description('The name of the subscription for the API.')
param apiSubscriptionName string
@description('The description of the subscription for the API.')
param apiSubscriptionDescription string

resource _apim 'Microsoft.ApiManagement/service@2022-08-01' existing = {
  name: apimName
}

resource api 'Microsoft.ApiManagement/service/apis@2022-08-01' = {
  name: name
  parent: _apim
  properties: {
    apiType: 'http'
    description: apiDescription
    displayName: apiDisplayName
    format: 'openapi-link'
    path: apiPath
    protocols: [
      'https'
    ]
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'api-key'
      query: 'api-key'
    }
    type: 'http'
    value: apiSpecURL
  }
}

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-09-01-preview' = {
  name: 'policy'
  parent: api
  properties: {
    format: 'rawxml'
    value: policyContent
  }
}

resource apiSubscription 'Microsoft.ApiManagement/service/subscriptions@2023-09-01-preview' = {
  name: apiSubscriptionName
  parent: _apim
  properties: {
    allowTracing: true
    displayName: apiSubscriptionDescription
    scope: '/apis/${api.id}'
    state: 'active'
  }
}

@description('Optional. A list of operations to apply specific policies to. Each object should include operationName and operationPolicyContent.')
type OperationPolicy = {
  operationName: string
  operationPolicyContent: string
}

param operations OperationPolicy[] = []

resource existingOperations 'Microsoft.ApiManagement/service/apis/operations@2022-08-01' existing = [for operation in operations: if (!empty(operation.operationName)) {
  name: operation.operationName
  parent: api
}]

resource operationPolicies 'Microsoft.ApiManagement/service/apis/operations/policies@2023-09-01-preview' = [for (operation, iterationIndex) in operations: if (!empty(operation.operationName) && !empty(operation.operationPolicyContent)) {
  name: 'policy'
  parent: existingOperations[iterationIndex]
  properties: {
    format: 'rawxml'
    value: operation.operationPolicyContent
  }
}]

output apiName string = api.name
output apiPath string = api.properties.path
output apiId string = api.id
output apiScope string = '/apis/${api.id}'
output apiSubscriptionId string = apiSubscription.id
output apiSubscriptionName string = apiSubscription.name
// Output the subscription key for the API subscription
output apiSubscriptionKey string = apiSubscription.listSecrets().primaryKey
