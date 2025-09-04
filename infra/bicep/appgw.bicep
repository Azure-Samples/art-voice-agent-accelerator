// ============================================================================
// APPLICATION GATEWAY WITH AVM MODULE
// ============================================================================
// Structured and parameterized Application Gateway with SSL termination
// and Container App backend support

targetScope = 'resourceGroup'

// ============================================================================
// PARAMETERS
// ============================================================================

@description('Name of the Application Gateway')
param applicationGatewayName string

@description('Location for all resources')
param location string = resourceGroup().location

@description('Application Gateway SKU configuration')
@allowed(['Basic', 'Standard_v2', 'WAF_v2'])
param skuName string = 'WAF_v2'

@description('Application Gateway capacity (instance count)')
@minValue(1)
@maxValue(10)
param capacity int = 2

@description('Enable autoscaling')
param enableAutoscaling bool = true

@description('Minimum autoscale capacity')
@minValue(1)
@maxValue(32)
param autoscaleMinCapacity int = 2

@description('Maximum autoscale capacity')
@minValue(1)
@maxValue(32)
param autoscaleMaxCapacity int = 10

// ============================================================================
// NETWORKING PARAMETERS
// ============================================================================

@description('Resource ID of the subnet for Application Gateway')
param subnetResourceId string

@description('Resource ID of the public IP address (leave empty to create new)')
param publicIpResourceId string = ''

@description('Public IP address name (used when creating new public IP)')
param publicIpName string = '${applicationGatewayName}-pip'

@description('Public IP address SKU (used when creating new public IP)')
@allowed(['Basic', 'Standard'])
param publicIpSku string = 'Standard'

@description('Public IP address allocation method (used when creating new public IP)')
@allowed(['Dynamic', 'Static'])
param publicIpAllocationMethod string = 'Static'

@description('DNS domain name label for public IP (optional)')
param dnsNameLabel string = ''

@description('Private IP address for internal load balancing (optional)')
param privateIpAddress string = ''

@description('Enable HTTP/2 support')
param enableHttp2 bool = true

// ============================================================================
// SSL CERTIFICATE PARAMETERS
// ============================================================================
// @description('SSL certificate name')
// param sslCertificateName string = 'ssl-certificate'

var sslCertificateName = enableSslCertificate && length(sslCertificates) > 0 ? sslCertificates[0].?name : ''

@description('Resource ID of user-assigned managed identity with Key Vault access')
param managedIdentityResourceId string = ''

// ============================================================================
// BACKEND CONFIGURATION PARAMETERS
// ============================================================================

@description('Container App backend configuration')
param containerAppBackends array = [
  {
    name: 'container-app-backend'
    fqdn: 'myapp.azurecontainerapps.io'
    port: 80
    protocol: 'Http'
    healthProbePath: '/health'
    healthProbeProtocol: 'Http'
  }
]

@description('Additional backend pools (optional)')
param additionalBackends array = []

// ============================================================================
// ROUTING CONFIGURATION PARAMETERS
// ============================================================================

@description('HTTP frontend configurations (public configuration, not secrets)')
#disable-next-line secure-parameter-default
param httpFrontends array = [
  {
    name: 'http-listener'
    protocol: 'Http'
    frontendPort: 'port-80'
    hostName: ''
  }
]

@description('Enable HTTP to HTTPS redirect')
param enableHttpRedirect bool = true

@description('Request timeout in seconds')
@minValue(1)
@maxValue(86400)
param requestTimeout int = 30

// ============================================================================
// WAF CONFIGURATION PARAMETERS
// ============================================================================

@description('Enable Web Application Firewall')
param enableWaf bool = true

@description('WAF policy name (will be auto-generated if not provided)')
param wafPolicyName string = ''

@description('WAF mode')
@allowed(['Detection', 'Prevention'])
param wafMode string = 'Detection'

@description('WAF policy state')
@allowed(['Enabled', 'Disabled'])
param wafPolicyState string = 'Enabled'

@description('Request body check setting')
param wafRequestBodyCheck bool = true

@description('Maximum request body size in KB')
@minValue(8)
@maxValue(128)
param wafMaxRequestBodySizeInKb int = 128

@description('File upload limit in MB')
@minValue(0)
@maxValue(750)
param wafFileUploadLimitInMb int = 100

@description('OWASP rule set version')
@allowed(['2.2.9', '3.0', '3.1', '3.2'])
param owaspRuleSetVersion string = '3.2'

// Note: Custom WAF rules and exclusions are not currently implemented
// These parameters can be added back when WAF customization is needed

// ============================================================================
// MONITORING PARAMETERS
// ============================================================================

@description('Enable telemetry collection')
param enableTelemetry bool = true

@description('Log Analytics workspace resource ID for diagnostics')
param logAnalyticsWorkspaceResourceId string = ''

// Note: Storage account for diagnostics is not currently implemented
// This parameter can be added back when storage diagnostics are needed

@description('Tags to apply to all resources')
param tags object = {}

// ============================================================================
// VARIABLES
// ============================================================================

var enableSslCertificate = length(sslCertificates) > 0

// WAF policy name generation
var generatedWafPolicyName = !empty(wafPolicyName) ? wafPolicyName : '${applicationGatewayName}-waf-policy'

// Build backend address pools
var backendPools = concat(
  map(containerAppBackends, backend => {
    name: backend.name
    properties: {
      backendAddresses: [
        {
          fqdn: backend.fqdn
        }
      ]
    }
  }),
  map(additionalBackends, backend => {
    name: backend.name
    properties: {
      backendAddresses: backend.addresses
    }
  })
)
// Build backend HTTP settings
var backendHttpSettings = map(containerAppBackends, backend => {
  name: '${backend.name}-http-settings'
  properties: {
    port: backend.protocol == 'Https' ? 443 : backend.port
    protocol: backend.protocol
    cookieBasedAffinity: 'Disabled'
    pickHostNameFromBackendAddress: true
    requestTimeout: requestTimeout
    trustedRootCertificates: backend.protocol == 'Https' ? [] : null
    probe: contains(backend, 'healthProbePath') ? {
      id: resourceId('Microsoft.Network/applicationGateways/probes', applicationGatewayName, '${backend.name}-health-probe')
    } : null
  }
})

// Build health probes
var healthProbes = map(filter(containerAppBackends, backend => contains(backend, 'healthProbePath')), backend => {
  name: '${backend.name}-health-probe'
  properties: {
    protocol: backend.?healthProbeProtocol ?? (backend.protocol == 'Https' ? 'Https' : 'Http')
    path: backend.healthProbePath
    interval: 30
    timeout: 30
    unhealthyThreshold: 3
    pickHostNameFromBackendHttpSettings: true
    minServers: 0
    match: {
      statusCodes: [
        '200-399'
      ]
    }
  }
})

// Build frontend IP configurations
var frontendIpConfigs = concat([
  {
    name: 'public-frontend-ip'
    properties: {
      privateIPAllocationMethod: 'Dynamic'
      publicIPAddress: {
        id: actualPublicIpResourceId
      }
    }
  }
], !empty(privateIpAddress) ? [
  {
    name: 'private-frontend-ip'
    properties: {
      privateIPAddress: privateIpAddress
      privateIPAllocationMethod: 'Static'
      subnet: {
        id: subnetResourceId
      }
    }
  }
] : [])

// Build HTTP listeners with SSL support - combine base listeners with conditional HTTPS
var allHttpFrontends = concat(httpFrontends, (enableSslCertificate) ? [{
  name: 'https-listener'
  protocol: 'Https'
  frontendPort: 'port-443'
  hostName: ''
  requireSni: false
  useSslCertificate: true
}] : [])

var listeners = map(allHttpFrontends, listener => {
  name: listener.name
  properties: union({
    frontendIPConfiguration: {
      id: resourceId('Microsoft.Network/applicationGateways/frontendIPConfigurations', applicationGatewayName, 'public-frontend-ip')
    }
    frontendPort: {
      id: resourceId('Microsoft.Network/applicationGateways/frontendPorts', applicationGatewayName, listener.frontendPort)
    }
    protocol: listener.protocol
    hostNames: !empty(listener.hostName) ? [listener.hostName] : []
    requireServerNameIndication: listener.?requireSni ?? false
  }, (listener.protocol == 'Https' && contains(listener, 'useSslCertificate') && listener.useSslCertificate && enableSslCertificate) ? {
    sslCertificate: {
      id: resourceId('Microsoft.Network/applicationGateways/sslCertificates', applicationGatewayName, sslCertificateName)
    }
  } : {})
})

// Build request routing rules
var routingRules = concat(
  // Single main routing rule for the primary backend (first container app)
  length(containerAppBackends) > 0 ? [{
    name: (enableSslCertificate) ? 'https-main-rule' : 'http-main-rule'
    properties: {
      ruleType: 'Basic'
      priority: 100
      httpListener: {
        id: resourceId('Microsoft.Network/applicationGateways/httpListeners', applicationGatewayName, (enableSslCertificate) ? 'https-listener' : 'http-listener')
      }
      backendAddressPool: {
        id: resourceId('Microsoft.Network/applicationGateways/backendAddressPools', applicationGatewayName, containerAppBackends[0].name)
      }
      backendHttpSettings: {
        id: resourceId('Microsoft.Network/applicationGateways/backendHttpSettingsCollection', applicationGatewayName, '${containerAppBackends[0].name}-http-settings')
      }
      rewriteRuleSet: {
        id: resourceId('Microsoft.Network/applicationGateways/rewriteRuleSets', applicationGatewayName, 'websocket-rewrite-rules')
      }
    }
  }] : [],
  // HTTP redirect rule (only if SSL is enabled and redirect is enabled)
  (enableHttpRedirect && enableSslCertificate) ? [{
    name: 'http-redirect-rule'
    properties: {
      ruleType: 'Basic'
      priority: 300
      httpListener: {
        id: resourceId('Microsoft.Network/applicationGateways/httpListeners', applicationGatewayName, 'http-listener')
      }
      redirectConfiguration: {
        id: resourceId('Microsoft.Network/applicationGateways/redirectConfigurations', applicationGatewayName, 'http-to-https-redirect')
      }
    }
  }] : []
)

param sslCertificates array = []

// Rewrite rule sets for WebSocket path handling
var rewriteRuleSets = [
  {
    name: 'websocket-rewrite-rules'
    properties: {
      rewriteRules: [
        {
          name: 'websocket-user-agent-rewrite'
          ruleSequence: 100
          conditions: [
            {
              variable: 'var_uri_path'
              pattern: '^/(realtime|relay|call/stream)$'
              ignoreCase: false
              negate: false
            }
          ]
          actionSet: {
            requestHeaderConfigurations: [
              {
                headerName: 'User-Agent'
                headerValue: 'RTAudioAgent/1.0 (WebSocketClient; RealTime)'
              }
            ]
          }
        }
      ]
    }
  }
]

// Redirect configurations (only when SSL is enabled and redirect is enabled)
var redirectConfigurations = (enableHttpRedirect && enableSslCertificate) ? [
  {
    name: 'http-to-https-redirect'
    properties: {
      redirectType: 'Permanent'
      targetListener: {
        id: resourceId('Microsoft.Network/applicationGateways/httpListeners', applicationGatewayName, 'https-listener')
      }
      includePath: true
      includeQueryString: true
    }
  }
] : []

// Diagnostic settings
var diagnosticSettings = !empty(logAnalyticsWorkspaceResourceId) ? [
  {
    name: 'applicationGatewayDiagnostics'
    workspaceResourceId: logAnalyticsWorkspaceResourceId
    logCategoriesAndGroups: [
      {
        categoryGroup: 'allLogs'
      }
    ]
    metricCategories: [
      {
        category: 'AllMetrics'
      }
    ]
  }
] : []

// Managed identities configuration
var managedIdentities = !empty(managedIdentityResourceId) ? {
  userAssignedResourceIds: [
    managedIdentityResourceId
  ]
} : {}

// Note: Autoscale configuration is defined in the resource directly
// This variable is not needed since autoscaling is handled inline

// ============================================================================
// COMPUTED VARIABLES
// ============================================================================

// Determine the public IP resource ID to use
var actualPublicIpResourceId = !empty(publicIpResourceId) ? publicIpResourceId : publicIpAddress.outputs.resourceId

// Build frontend ports conditionally based on SSL configuration
var actualFrontendPorts = concat([
  {
    name: 'port-80'
    port: 80
  }
], (enableSslCertificate) ? [
  {
    name: 'port-443'
    port: 443
  }
] : [])

// ============================================================================
// RESOURCES
// ============================================================================

// Create public IP address if not provided
module publicIpAddress 'br/public:avm/res/network/public-ip-address:0.6.0' = if (empty(publicIpResourceId)) {
  name: 'public-ip-deployment'
  params: {
    name: publicIpName
    location: location
    skuName: publicIpSku
    publicIPAllocationMethod: publicIpAllocationMethod
    dnsSettings: !empty(dnsNameLabel) ? {
      domainNameLabel: dnsNameLabel
      domainNameLabelScope: 'TenantReuse'
      fqdn: null
      reverseFqdn: null
    } : null
    tags: tags
  }
}

// ============================================================================
// WAF POLICY DEPLOYMENT (CONDITIONAL)
// ============================================================================

module applicationGatewayWebApplicationFirewallPolicy 'br/public:avm/res/network/application-gateway-web-application-firewall-policy:0.2.0' = if (enableWaf) {
  name: 'waf-policy-deployment'
  params: {
    // Required parameters
    name: generatedWafPolicyName
    location: location
    
    // Managed rules configuration
    managedRules: {
      managedRuleSets: [
        {
          ruleSetType: 'OWASP'
          ruleSetVersion: owaspRuleSetVersion
          ruleGroupOverrides: []
        }
      ]
    }
    
    // Policy settings
    policySettings: {
      state: wafPolicyState
      mode: wafMode
      requestBodyCheck: wafRequestBodyCheck
      maxRequestBodySizeInKb: wafMaxRequestBodySizeInKb
      fileUploadLimitInMb: wafFileUploadLimitInMb
      requestBodyInspectLimitInKB: wafMaxRequestBodySizeInKb
      requestBodyEnforcement: true
    }
    
    // Tags
    tags: tags
  }
}
// ============================================================================
// APPLICATION GATEWAY DEPLOYMENT
// ============================================================================

module applicationGateway 'br/public:avm/res/network/application-gateway:0.6.0' = {
  name: '${applicationGatewayName}-deployment'
  params: {
    // Required parameters
    name: applicationGatewayName
    location: location
    
    // SKU configuration
    sku: skuName
    capacity: enableAutoscaling ? null : capacity
    
    // Autoscaling configuration
    autoscaleMinCapacity: enableAutoscaling ? autoscaleMinCapacity : null
    autoscaleMaxCapacity: enableAutoscaling ? autoscaleMaxCapacity : null
    
    // Network configuration
    gatewayIPConfigurations: [
      {
        name: 'gateway-ip-config'
        properties: {
          subnet: {
            id: subnetResourceId
          }
        }
      }
    ]
    
    frontendIPConfigurations: frontendIpConfigs
    
    // Fix frontend ports - ensure proper structure for AVM module
    frontendPorts: map(actualFrontendPorts, port => {
      name: port.name
      properties: {
        port: port.port
      }
    })
    
    // Backend configuration
    backendAddressPools: backendPools
    backendHttpSettingsCollection: backendHttpSettings
    probes: healthProbes
    
    // Listener and routing configuration
    httpListeners: listeners
    requestRoutingRules: routingRules
    
    // Rewrite rule sets
    rewriteRuleSets: rewriteRuleSets
    
    // SSL configuration
    sslCertificates: sslCertificates
    
    // Redirect configuration
    redirectConfigurations: redirectConfigurations
    
    // WAF policy configuration (conditional)
    firewallPolicyResourceId: enableWaf ? applicationGatewayWebApplicationFirewallPolicy.outputs.resourceId : null
    
    // Advanced configuration
    enableHttp2: enableHttp2
    
    // Identity configuration
    managedIdentities: managedIdentities
    
    // Monitoring configuration
    enableTelemetry: enableTelemetry
    diagnosticSettings: diagnosticSettings
    
    // Tags
    tags: tags
  }
  dependsOn: enableWaf ? [applicationGatewayWebApplicationFirewallPolicy] : []
}

// ============================================================================
// OUTPUTS
// ============================================================================

@description('Resource ID of the Application Gateway')
output applicationGatewayResourceId string = applicationGateway.outputs.resourceId

@description('Name of the Application Gateway')
output applicationGatewayName string = applicationGateway.outputs.name

@description('Resource ID of the WAF policy (if enabled)')
output wafPolicyResourceId string = enableWaf ? applicationGatewayWebApplicationFirewallPolicy.outputs.resourceId : ''

@description('Name of the WAF policy (if enabled)')
output wafPolicyName string = enableWaf ? applicationGatewayWebApplicationFirewallPolicy.outputs.name : ''

@description('Resource ID of the public IP address used by the Application Gateway')
output publicIpResourceId string = actualPublicIpResourceId

@description('Public IP address of the Application Gateway')
output publicIpAddress string = !empty(publicIpResourceId) 
  ? reference(publicIpResourceId, '2023-09-01').ipAddress 
  : publicIpAddress.outputs.ipAddress

@description('FQDN of the Application Gateway public IP')
output fqdn string = !empty(publicIpResourceId) 
  ? reference(publicIpResourceId, '2023-09-01').dnsSettings.fqdn 
  : (!empty(dnsNameLabel) ? '${dnsNameLabel}.${location}.cloudapp.azure.com' : '')

@description('Backend pool names')
output backendPoolNames array = map(backendPools, pool => pool.name)

@description('HTTP listener names')
output httpListenerNames array = map(listeners, listener => listener.name)

@description('Application Gateway configuration summary')
output summary object = {
  name: applicationGateway.outputs.name
  resourceId: applicationGateway.outputs.resourceId
  wafEnabled: enableWaf
  wafPolicyName: enableWaf ? applicationGatewayWebApplicationFirewallPolicy.outputs.name : ''
  wafPolicyResourceId: enableWaf ? applicationGatewayWebApplicationFirewallPolicy.outputs.resourceId : ''
  location: location
  sku: skuName
  sslEnabled: enableSslCertificate
  httpRedirectEnabled: enableHttpRedirect
  http2Enabled: enableHttp2
  autoscalingEnabled: enableAutoscaling
  backendCount: length(backendPools)
  listenerCount: length(listeners)
}

// ============================================================================
// ROUTING RULES CONFIGURATION
// ============================================================================
// NOTE: Each HTTP listener can only be used by ONE routing rule.
// If you need multiple backends, consider using:
// 1. Path-based routing with URL path maps
// 2. Host-based routing with multiple listeners
// 3. Separate Application Gateways
// 
// Current implementation uses the first backend as the default route.
// Additional backends are created but require manual path-based configuration.
