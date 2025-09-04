/*
  Example usage of the managed-cert.bicep module
  
  This example shows how to deploy a domain and managed certificate
  for use with Azure Communication Services or other Azure services.
*/

// Import the managed certificate module
module managedCert './managed-cert.bicep' = {
  name: 'managed-cert-deployment'
  params: {
    // Required parameters
    domainName: 'mycompany.com'
    keyVaultId: '/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/my-rg/providers/Microsoft.KeyVault/vaults/my-keyvault'
    
    // Optional parameters
    location: 'eastus'
    skipDomainCreation: false // Set to true if domain already exists
    environment: 'prod'
    enableAutoRenewal: true
    validityInYears: 2
    
    // Contact information for domain registration
    domainContactInfo: {
      firstName: 'John'
      lastName: 'Doe'
      email: 'admin@mycompany.com'
      phone: '+1.5551234567'
      addressMailing: {
        address1: '123 Business Ave'
        city: 'Seattle'
        state: 'WA'
        country: 'US'
        postalCode: '98101'
      }
    }
    
    // Tags
    tags: {
      Environment: 'Production'
      Project: 'Communication-Services'
      Owner: 'Platform-Team'
      CostCenter: 'IT-Operations'
    }
  }
}

// Outputs from the certificate module
output certificateInfo object = {
  domainName: managedCert.outputs.domainName
  certificateOrderName: managedCert.outputs.certificateOrderName
  keyVaultSecretName: managedCert.outputs.keyVaultSecretName
  keyVaultSecretUri: managedCert.outputs.keyVaultSecretUri
  certificateStatus: managedCert.outputs.certificateStatus
  summary: managedCert.outputs.summary
}

// Example: Using the certificate with other Azure services
// module communicationService '../communication/acs.bicep' = {
//   name: 'acs-deployment'
//   params: {
//     name: 'my-acs-service'
//     customDomainName: managedCert.outputs.domainName
//     certificateSecretUri: managedCert.outputs.keyVaultSecretUri
//     // ... other ACS parameters
//   }
// }
