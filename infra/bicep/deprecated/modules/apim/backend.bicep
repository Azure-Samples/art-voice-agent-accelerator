/**
 * Backend Module
 * This module creates API Management backends and, if multiple backends are provided, a backend pool.
 *
 * Parameters:
 * - backendInstances: Array of backend definitions.
 *   Each object can include:
 *     - name: unique backend name.
 *     - url: service endpoint.
 *     - description (optional): description for the backend.
 *     - weight (optional): backend weight for the pool (default 10).
 *     - priority (optional): backend priority for the pool (default 1).
 *     - failureCount (optional): number of failures to trigger the circuit breaker (default 1).
 *     - errorReasons (optional): list of error reasons (default: ['Server errors']).
 *     - failureInterval (optional): time interval to evaluate failures (default 'PT5M').
 *     - statusCodeRanges (optional): list of status code ranges (default: [{ min:429, max:429 }]).
 *     - breakerRuleName (optional): circuit breaker rule name (default 'defaultBreakerRule').
 *     - tripDuration (optional): duration the breaker remains open (default 'PT1M').
 *     - acceptRetryAfter (optional): whether Retry-After header is supported (default false).
 *
 * - backendPoolName: The name of the backend pool to be created (if more than one backend is provided).
 * - apimResource: The APIM resource object (from your main deployment) to which the backends belong.
 */

 @description('Array of backend instance definitions.')
type statusCodeRangeType = {
  @description('Minimum status code in the range')
  min: int

  @description('Maximum status code in the range')
  max: int
}

type backendInstanceType = {
  @description('Unique backend name')
  name: string

  @description('Service endpoint URL')
  url: string

  @description('Optional description for the backend')
  description: string?

  @description('Backend weight for the pool. Default is 10.')
  weight: int?

  @description('Backend priority for the pool. Default is 1.')
  priority: int?

  @description('Number of failures to trigger the circuit breaker. Default is 1.')
  failureCount: int?

  @description('List of error reasons. Default is ["Server errors"].')
  errorReasons: string[]?

  @description('Time interval to evaluate failures. Default is "PT5M".')
  failureInterval: string?

  @description('List of status code ranges. Default is [{min:429, max:429}].')
  statusCodeRanges: statusCodeRangeType[]?

  @description('Circuit breaker rule name. Default is "defaultBreakerRule".')
  breakerRuleName: string?

  @description('Duration the breaker remains open. Default is "PT1M".')
  tripDuration: string?

  @description('Whether Retry-After header is supported. Default is false.')
  acceptRetryAfter: bool?
}

param backendInstances backendInstanceType[]

 @description('Name for the backend pool; used if more than one backend instance is provided.')
 param backendPoolName string = 'backend-pool'

 @description('The parent API Management resource name.')
 param apimName string

 resource apimResource 'Microsoft.ApiManagement/service@2023-09-01-preview' existing = {
   name: apimName
 }

 // Create individual backend resources for each provided instance
 @batchSize(1)
 resource backends 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = [for instance in backendInstances: {
   name: instance.name
   parent: apimResource
   properties: {
    description: 'Backend for ${instance.name}. Part of pool ${backendPoolName}.'
     url: instance.url
     protocol: 'http'
     tls: {
       validateCertificateChain: true
       validateCertificateName: true
     }
     circuitBreaker: {
       rules: [
         {
           failureCondition: {
             count: 1
             errorReasons: instance.?errorReasons ?? [
               'Server errors'
             ]
             interval: instance.?failureInterval ?? 'PT5M'
             statusCodeRanges: instance.?statusCodeRanges ?? [
               {
                 min: 429
                 max: 429
               }
             ]
           }
           name: instance.?breakerRuleName ?? 'defaultBreakerRule'
           tripDuration: instance.?tripDuration ?? 'PT1M'
           acceptRetryAfter: instance.?acceptRetryAfter ?? true
         }
       ]
     }
   }
 }]

 // If more than one backend instance is provided, create a backend pool resource.
 resource backendPool 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = {
   name: backendPoolName
   parent: apimResource
   properties: {
     description: 'Generic Backend Pool'
     type: 'Pool'
     pool: {
       services: [for instance in backendInstances: {
           id: '/backends/${instance.name}'
           priority: instance.?priority ?? 1
           weight: instance.?weight ?? 10
       }]
     }
   }
   dependsOn: [
     backends
   ]
 }


//  @description('Outputs the created backend pool resource. If only one backend is used, this will be null.')
//  output backendPoolOutput object = length(backendInstances) > 1 ? backendPool : null
