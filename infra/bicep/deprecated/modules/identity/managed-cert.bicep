/*
  Managed Certificate Module
  
  This module creates an App Service Domain and Managed Certificate for secure HTTPS communication.
  The certificate is publicly trusted and suitable for Azure Communication Services integration.
  
  Features:
  - App Service Domain registration with public DNS resolution
  - Managed SSL certificate generation and lifecycle management
  - Key Vault integration for secure certificate storage
  - Configurable domain creation (skip if domain already exists)
  - Azure naming conventions and best practices
*/

metadata name = 'App Service Domain and Managed Certificate'
metadata description = 'Creates a publicly resolvable domain and managed SSL certificate with Key Vault integration'
metadata owner = 'Platform Team'

// Core Parameters
@description('The domain name to register (e.g., myexampledomain.com)')
@minLength(4)
@maxLength(253)
param domainName string

@description('The full resource ID of the Key Vault for certificate storage')
param keyVaultId string

@description('Azure region for resource deployment')
param location string = resourceGroup().location

// Configuration Parameters
@description('Skip domain creation if the domain already exists')
param skipDomainCreation bool = false

@description('Environment designation (dev, test, staging, prod)')
@allowed(['dev', 'test', 'staging', 'prod'])
param environment string = 'dev'

@description('Tags to apply to all resources')
param tags object = {}

@description('Enable auto-renewal for the certificate')
param enableAutoRenewal bool = false

@description('Certificate validity period in years')
@allowed([1, 2, 3])
param validityInYears int = 1

@description('Contact information for domain registration')
param domainContactInfo object = {
  firstName: 'Admin'
  lastName: 'User'
  email: 'admin@${domainName}'
  phone: '+1.1234567890'
  addressMailing: {
    address1: '123 Main St'
    city: 'Seattle'
    state: 'WA'
    country: 'US'
    postalCode: '98101'
  }
}

@description('Agreement timestamp for domain registration')
param agreementTimestamp string = utcNow()

// Variables
var resourceSuffix = uniqueString(subscription().id, resourceGroup().id)
var certificateOrderName = 'cert-${replace(domainName, '.', '-')}-${resourceSuffix}'
var keyVaultName = last(split(keyVaultId, '/'))
var keyVaultSubscriptionId = split(keyVaultId, '/')[2]
var keyVaultResourceGroupName = split(keyVaultId, '/')[4]
var secretName = 'cert-${replace(domainName, '.', '-')}'

var commonTags = union(tags, {
  Environment: environment
  DomainName: domainName
  ManagedBy: 'Bicep'
  Purpose: 'SSL-Certificate'
})

// DNS Zone for the domain (created first to get the ID)
resource dnsZone 'Microsoft.Network/dnsZones@2018-05-01' = if (!skipDomainCreation) {
  name: domainName
  location: 'global'
  tags: commonTags
  properties: {}
}

// App Service Domain (conditionally created)
resource appServiceDomain 'Microsoft.DomainRegistration/domains@2023-01-01' = if (!skipDomainCreation) {
  name: domainName
  location: 'global' // Domains are global resources
  tags: commonTags
  properties: {
    // Contact information for domain registration
    contactAdmin: domainContactInfo
    contactBilling: domainContactInfo
    contactRegistrant: domainContactInfo
    contactTech: domainContactInfo
    
    // Privacy and auto-renewal settings
    privacy: true
    autoRenew: enableAutoRenewal
    consent: {
      agreementKeys: []
      agreedAt: agreementTimestamp
      agreedBy: 'admin@${domainName}'
    }
    
    // DNS configuration
    dnsType: 'AzureDns'
    dnsZoneId: dnsZone.id
  }
}

// Reference existing domain if skipDomainCreation is true
resource existingDomain 'Microsoft.DomainRegistration/domains@2023-01-01' existing = if (skipDomainCreation) {
  name: domainName
}

// App Service Managed Certificate Order (simplified)
resource certificateOrder 'Microsoft.CertificateRegistration/certificateOrders@2023-01-01' = {
  name: certificateOrderName
  location: 'global' // Certificate orders are global resources
  tags: commonTags
  properties: {
    // Domain validation
    distinguishedName: 'CN=${domainName}'
    validityInYears: validityInYears
    keySize: 2048
    productType: 'StandardDomainValidatedSsl'
    autoRenew: enableAutoRenewal
  }
}

// Certificate binding to the certificate order
resource certificate 'Microsoft.CertificateRegistration/certificateOrders/certificates@2023-01-01' = {
  parent: certificateOrder
  name: secretName
  location: location
  tags: commonTags
  properties: {
    keyVaultId: keyVaultId
    keyVaultSecretName: secretName
  }
}

// Key Vault reference for secret storage
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
  scope: resourceGroup(keyVaultSubscriptionId, keyVaultResourceGroupName)
}

// Module for Key Vault access policy (to handle cross-scope deployment)
module keyVaultAccessPolicyModule 'key-vault-access-policy.bicep' = {
  name: 'kv-access-policy-${resourceSuffix}'
  scope: resourceGroup(keyVaultSubscriptionId, keyVaultResourceGroupName)
  params: {
    keyVaultName: keyVaultName
    certificateOrderPrincipalId: '00000000-0000-0000-0000-000000000000' // Placeholder - replace with actual service principal
    tenantId: subscription().tenantId
  }
}

// DNS TXT record for domain verification (if domain was created)
resource verificationRecord 'Microsoft.Network/dnsZones/TXT@2018-05-01' = if (!skipDomainCreation) {
  parent: dnsZone
  name: 'asuid'
  properties: {
    TTL: 3600
    TXTRecords: [
      {
        value: ['placeholder-verification-token']
      }
    ]
  }
}

// Outputs
@description('The registered domain name')
output domainName string = domainName

@description('The domain resource ID')
output domainResourceId string = skipDomainCreation ? existingDomain.id : appServiceDomain.id

@description('The DNS zone resource ID (if created)')
output dnsZoneResourceId string = skipDomainCreation ? '' : dnsZone.id

@description('The certificate order name')
output certificateOrderName string = certificateOrder.name

@description('The certificate order resource ID')
output certificateOrderResourceId string = certificateOrder.id

@description('The certificate resource ID')
output certificateResourceId string = certificate.id

@description('The Key Vault secret name containing the certificate')
output keyVaultSecretName string = secretName

@description('The Key Vault URI for the certificate secret')
output keyVaultSecretUri string = '${keyVault.properties.vaultUri}secrets/${secretName}'

@description('Certificate status')
output certificateStatus string = certificateOrder.properties.status

@description('Summary of created resources')
output summary object = {
  domainName: domainName
  domainCreated: !skipDomainCreation
  certificateOrderName: certificateOrder.name
  keyVaultSecretName: secretName
  autoRenewal: enableAutoRenewal
  environment: environment
  status: certificateOrder.properties.status
}
