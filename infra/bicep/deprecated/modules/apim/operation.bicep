@description('The name of the existing API Management (APIM) service.')
param apimName string

@description('The name of the existing API.')
param apiName string

@description('The name for the new API operation. This is the resource name.')
param operationName string

@description('The display name for the API operation.')
param operationDisplayName string

@description('The description for the API operation.')
param operationDescription string

@description('The HTTP method for the API operation (e.g., GET, POST, PUT, DELETE).')
@allowed([
  'GET'
  'POST'
  'PUT'
  'DELETE'
  'PATCH'
  'HEAD'
  'OPTIONS'
  'TRACE'
])
param method string

@description('The URL template for the API operation. Example: /users/{userId}')
param urlTemplate string

@description('Optional. The content of the policy to apply to this operation. Defaults to an empty policy.')
param policyContent string = ''

resource apimService 'Microsoft.ApiManagement/service@2022-08-01' existing = {
  name: apimName
}

resource api 'Microsoft.ApiManagement/service/apis@2022-08-01' existing = {
  name: apiName
  parent: apimService
}

resource operation 'Microsoft.ApiManagement/service/apis/operations@2022-08-01' = {
  name: operationName
  parent: api
  properties: {
    displayName: operationDisplayName
    description: operationDescription
    method: method
    urlTemplate: urlTemplate
    templateParameters: [] // Add template parameters if needed, e.g., for path parameters like {userId}
    request: {} // Define request body schema if applicable
    responses: [] // Define expected responses
  }
}

resource operationPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-09-01-preview' = if (!empty(policyContent)) {
  name: 'policy'
  parent: operation
  properties: {
    format: 'rawxml'
    value: policyContent
  }
}



output operationId string = operation.id
output operationName string = operation.name
