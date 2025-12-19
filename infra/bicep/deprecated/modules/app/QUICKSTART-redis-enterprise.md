# Azure Redis Enterprise Module - Quick Start Guide

This guide helps you get started with the Azure Redis Enterprise Bicep module quickly and securely.

## Quick Start Options

### Option 1: Basic Development Setup (Fastest)
```bash
# Deploy basic Redis Enterprise for development
az deployment group create \
  --resource-group myResourceGroup \
  --template-file examples/redis-enterprise-examples-v3.bicep \
  --parameters resourcePrefix=myapp environment=dev
```

### Option 2: Production Setup with Private Networking
```bash
# Deploy production-ready Redis Enterprise with private endpoints
az deployment group create \
  --resource-group myResourceGroup \
  --template-file examples/redis-enterprise-examples-v3.bicep \
  --parameters resourcePrefix=mycompany environment=prod
```

### Option 3: Custom Single Module Deployment
```bash
# Deploy just the Redis Enterprise module with custom settings
az deployment group create \
  --resource-group myResourceGroup \
  --template-file modules/app/am-redis.bicep \
  --parameters @my-redis-params.json
```

## Parameter File Examples

### Basic Parameters (my-redis-params.json)
```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "clusterName": {
      "value": "my-redis-cluster"
    },
    "location": {
      "value": "East US 2"
    },
    "sku": {
      "value": {
        "name": "Enterprise_E10",
        "capacity": 2
      }
    },
    "enableSystemManagedIdentity": {
      "value": true
    },
    "databases": {
      "value": [
        {
          "name": "cache",
          "clientProtocol": "Encrypted",
          "port": 10000,
          "modules": [
            {
              "name": "RediSearch",
              "args": "MAXSEARCHRESULTS 10000"
            }
          ]
        }
      ]
    }
  }
}
```

### Production Parameters with Private Networking
```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "clusterName": {
      "value": "prod-redis-cluster"
    },
    "location": {
      "value": "East US 2"
    },
    "sku": {
      "value": {
        "name": "Enterprise_E50",
        "capacity": 4
      }
    },
    "zones": {
      "value": ["1", "2", "3"]
    },
    "enableSystemManagedIdentity": {
      "value": true
    },
    "enablePrivateEndpoint": {
      "value": true
    },
    "vnetResourceId": {
      "value": "/subscriptions/{subscription-id}/resourceGroups/{rg-name}/providers/Microsoft.Network/virtualNetworks/{vnet-name}"
    },
    "subnetName": {
      "value": "redis-subnet"
    },
    "privateDnsZoneResourceId": {
      "value": "/subscriptions/{subscription-id}/resourceGroups/{rg-name}/providers/Microsoft.Network/privateDnsZones/privatelink.redisenterprise.cache.azure.net"
    },
    "databases": {
      "value": [
        {
          "name": "primary",
          "clientProtocol": "Encrypted",
          "port": 10000,
          "modules": [
            {
              "name": "RediSearch",
              "args": "MAXSEARCHRESULTS 50000"
            },
            {
              "name": "RedisJSON",
              "args": ""
            }
          ],
          "persistence": {
            "aofEnabled": true,
            "aofFrequency": "1s",
            "rdbEnabled": true,
            "rdbFrequency": "6h"
          }
        }
      ]
    },
    "enableDiagnostics": {
      "value": true
    },
    "logAnalyticsWorkspaceId": {
      "value": "/subscriptions/{subscription-id}/resourceGroups/{rg-name}/providers/Microsoft.OperationalInsights/workspaces/{workspace-name}"
    }
  }
}
```

## Prerequisites Checklist

Before deploying, ensure you have:

- [ ] Azure CLI installed and logged in
- [ ] Target resource group created
- [ ] Appropriate Azure permissions (Contributor or Owner on the resource group)
- [ ] For private endpoints: Virtual Network with dedicated subnet
- [ ] For private endpoints: Private DNS zone `privatelink.redisenterprise.cache.azure.net`
- [ ] For customer-managed encryption: Key Vault with encryption key
- [ ] For diagnostics: Log Analytics workspace

## Post-Deployment Steps

### 1. Verify Deployment
```bash
# Check cluster status
az redis-enterprise show \
  --cluster-name <cluster-name> \
  --resource-group <resource-group>

# List databases
az redis-enterprise database list \
  --cluster-name <cluster-name> \
  --resource-group <resource-group>
```

### 2. Test Connectivity
```bash
# For public endpoints (development)
redis-cli -h <hostname> -p <port> --tls ping

# For private endpoints (from within VNet)
redis-cli -h <hostname> -p <port> --tls ping
```

### 3. Retrieve Connection Information
```bash
# Get access keys
az redis-enterprise database list-keys \
  --cluster-name <cluster-name> \
  --database-name <database-name> \
  --resource-group <resource-group>

# Get connection string
echo "rediss://:<access-key>@<hostname>:<port>"
```

## Common Configurations

### High-Performance Caching
- SKU: `Enterprise_E50` or higher
- Zones: `["1", "2", "3"]`
- Eviction Policy: `AllKeysLRU`
- Persistence: Disabled for maximum performance

### Search and Analytics
- SKU: `Enterprise_E100` or higher
- Modules: `RediSearch`, `RedisJSON`
- Eviction Policy: `NoEviction`
- Persistence: Enabled with AOF

### Time Series Data
- SKU: `Enterprise_E20` or higher
- Modules: `RedisTimeSeries`
- Eviction Policy: `VolatileTTL`
- Persistence: RDB only

### Ultra-Low Latency
- SKU: `EnterpriseFlash_F300` or higher
- Flash-based storage for sub-millisecond latency
- Minimal persistence for maximum speed

## Troubleshooting

### Common Issues

1. **Deployment Timeout**
   - Increase deployment timeout
   - Check quota limits in the region

2. **Private Endpoint Connection Issues**
   - Verify VNet and subnet configuration
   - Check DNS zone configuration and linking

3. **Access Key Issues**
   - Ensure proper RBAC permissions
   - Check managed identity configuration

4. **Module Loading Failures**
   - Verify module compatibility with SKU
   - Check module argument syntax

### Diagnostic Commands

```bash
# Check deployment status
az deployment group show \
  --name <deployment-name> \
  --resource-group <resource-group>

# View deployment logs
az monitor activity-log list \
  --resource-group <resource-group> \
  --max-events 50

# Test DNS resolution (for private endpoints)
nslookup <hostname>
```

## Support and Resources

- [Azure Redis Enterprise Documentation](https://docs.microsoft.com/azure/azure-cache-for-redis/cache-redis-enterprise)
- [Redis Modules Documentation](https://redis.io/modules)
- [Bicep Language Reference](https://docs.microsoft.com/azure/azure-resource-manager/bicep)
- [Azure Private Link Documentation](https://docs.microsoft.com/azure/private-link)

## Next Steps

1. Review the comprehensive examples in `redis-enterprise-examples-v3.bicep`
2. Customize parameters for your specific requirements
3. Set up monitoring and alerting
4. Implement backup and disaster recovery strategies
5. Configure application connection pools for optimal performance
