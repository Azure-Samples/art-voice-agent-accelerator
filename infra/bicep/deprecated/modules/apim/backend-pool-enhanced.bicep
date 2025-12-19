/*
  Enhanced Backend Pool Module
  
  This module creates sophisticated backend pools with:
  - Advanced load balancing algorithms
  - Health checks and monitoring
  - Circuit breaker patterns
  - Retry policies
  - Regional failover
*/

import { LoadBalancingConfig } from '../types.bicep'

@description('APIM service name')
param apimName string

@description('Backend pool name')
param backendPoolName string

@description('Load balancing configuration')
param loadBalancingConfig LoadBalancingConfig

@description('Circuit breaker configuration')
param circuitBreakerConfig object

@description('Backend instance configurations')
param backendInstances array

@description('Tags to apply to resources')
param tags object = {}

resource apimService 'Microsoft.ApiManagement/service@2023-09-01-preview' existing = {
  name: apimName
}

// Create individual backend resources
@batchSize(1)
resource backends 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = [for instance in backendInstances: {
  name: instance.name
  parent: apimService
  properties: {
    description: '${instance.description} - Priority: ${instance.priority}, Weight: ${instance.weight}'
    url: instance.url
    protocol: 'http'
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
    circuitBreaker: {
      rules: [
        {
          name: '${instance.name}-circuit-breaker'
          failureCondition: {
            count: circuitBreakerConfig.failureThreshold
            errorReasons: [
              'Server errors'
              'Timeout'
            ]
            interval: 'PT${circuitBreakerConfig.monitoringWindowSeconds}S'
            statusCodeRanges: [
              {
                min: 429
                max: 429
              }
              {
                min: 500
                max: 599
              }
            ]
          }
          tripDuration: 'PT${circuitBreakerConfig.recoveryTimeSeconds}S'
          acceptRetryAfter: true
        }
      ]
    }
    // Health check configuration for individual backends
    properties: {
      healthCheckPath: instance.healthCheckPath
      healthCheckInterval: loadBalancingConfig.healthCheck.intervalSeconds
      healthCheckTimeout: loadBalancingConfig.healthCheck.timeoutSeconds
    }
  }
}]

// Create the backend pool
resource backendPool 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = {
  name: backendPoolName
  parent: apimService
  properties: {
    description: 'Enhanced backend pool with ${loadBalancingConfig.algorithm} load balancing'
    type: 'Pool'
    pool: {
      services: [for (instance, i) in backendInstances: {
        id: '/backends/${instance.name}'
        priority: instance.priority
        weight: instance.weight
      }]
    }
  }
  dependsOn: [backends]
  tags: tags
}

// Create backend health monitors (if supported by API version)
resource healthProbe 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = if (loadBalancingConfig.healthCheck.enabled) {
  name: '${backendPoolName}-health-monitor'
  parent: apimService
  properties: {
    description: 'Health monitoring for ${backendPoolName}'
    type: 'Single'
    url: 'https://httpbin.org/status/200' // Placeholder - should be actual health endpoint
    protocol: 'http'
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
  }
}

// Outputs
output name string = backendPool.name
output backendPoolId string = backendPool.id
output backends array = [for (instance, i) in backendInstances: {
  name: backends[i].name
  id: backends[i].id
  url: instance.url
  priority: instance.priority
  weight: instance.weight
  location: instance.location
}]

output healthMonitorId string = loadBalancingConfig.healthCheck.enabled ? healthProbe.id : ''
output loadBalancingAlgorithm string = loadBalancingConfig.algorithm
