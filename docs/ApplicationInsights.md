# Application Insights Integration Guide

This guide explains how to configure and troubleshoot Azure Application Insights telemetry for the real-time audio agent application.

## Overview

The application uses Azure Monitor OpenTelemetry to send telemetry data to Application Insights, including:
- Structured logging
- Request tracing
- Performance metrics
- Live metrics (when permissions allow)

## Quick Fix for Permission Errors

If you're seeing "Forbidden" errors related to Application Insights telemetry, apply this immediate fix:

```bash
# Set environment variable to disable live metrics
export AZURE_MONITOR_DISABLE_LIVE_METRICS=true

# Set development environment
export ENVIRONMENT=dev
```

Or add to your `.env` file:
```bash
AZURE_MONITOR_DISABLE_LIVE_METRICS=true
ENVIRONMENT=dev
```

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Application Insights connection string | None | Yes |
| `AZURE_MONITOR_DISABLE_LIVE_METRICS` | Disable live metrics to reduce permission requirements | `false` | No |
| `ENVIRONMENT` | Environment type (dev/staging/prod) | None | No |
| `AZURE_MONITOR_LOGGER_NAME` | Custom logger name | `default` | No |

### Connection String Format

```
InstrumentationKey=your-instrumentation-key;IngestionEndpoint=https://your-region.in.applicationinsights.azure.com/;LiveEndpoint=https://your-region.livediagnostics.monitor.azure.com/
```

## Authentication

The telemetry configuration uses Azure credential chain in this order:

1. **Managed Identity** (for Azure-hosted applications)
   - App Service: System-assigned or user-assigned managed identity
   - Container Apps: System-assigned or user-assigned managed identity

2. **DefaultAzureCredential** (for local development)
   - Azure CLI credentials
   - Visual Studio Code credentials
   - Environment variables (if configured)

## Permissions Required

### Basic Telemetry (Logs, Traces, Metrics)
- `Microsoft.Insights/components/read`
- `Microsoft.Insights/telemetry/write`

### Live Metrics (Real-time monitoring)
- `Microsoft.Insights/components/write`
- Additional live metrics API permissions

### Recommended Roles

1. **Application Insights Component Contributor**
   ```bash
   az role assignment create \
     --assignee <user-or-managed-identity> \
     --role "Application Insights Component Contributor" \
     --scope "/subscriptions/{subscription}/resourceGroups/{rg}/providers/Microsoft.Insights/components/{name}"
   ```

2. **Monitoring Contributor** (broader access)
   ```bash
   az role assignment create \
     --assignee <user-or-managed-identity> \
     --role "Monitoring Contributor" \
     --scope "/subscriptions/{subscription}/resourceGroups/{rg}"
   ```

## Troubleshooting

### Common Error: "The Agent/SDK does not have permissions to send telemetry"

**Symptoms:**
```
azure.core.exceptions.HttpResponseError: Operation returned an invalid status 'Forbidden'
Content: {"Code":"InvalidOperation","Message":"The Agent/SDK does not have permissions to send telemetry to this resource."}
```

**Solutions:**

1. **Immediate Fix (Disable Live Metrics):**
   ```bash
   export AZURE_MONITOR_DISABLE_LIVE_METRICS=true
   ```

2. **Grant Permissions for Local Development:**
   ```bash
   # Get your user principal name
   az account show --query user.name -o tsv
   
   # Grant Application Insights permissions
   az role assignment create \
     --assignee $(az account show --query user.name -o tsv) \
     --role "Application Insights Component Contributor" \
     --scope <your-app-insights-resource-id>
   ```

3. **Configure Managed Identity for Production:**
   ```bash
   # Enable system-assigned managed identity (App Service example)
   az webapp identity assign --resource-group <rg> --name <app-name>
   
   # Grant permissions to the managed identity
   az role assignment create \
     --assignee <managed-identity-principal-id> \
     --assignee-principal-type ServicePrincipal \
     --role "Application Insights Component Contributor" \
     --scope <your-app-insights-resource-id>
   ```

### Environment-Specific Behavior

The telemetry configuration automatically adjusts based on environment:

- **Development (`dev`, `development`, `local`)**: Live metrics disabled by default
- **Production (`prod`, `production`)**: Live metrics enabled if permissions allow
- **Azure-hosted**: Attempts to use managed identity credentials

## Testing

### Test Basic Telemetry
```python
import logging
from utils.telemetry_config import setup_azure_monitor

# Configure telemetry
setup_azure_monitor("test-logger")

# Test logging
logger = logging.getLogger("test-logger")
logger.info("Test message", extra={"custom_property": "test_value"})
```

### Run Diagnostics
```bash
python utils/fix_appinsights.py
```

## Integration with FastAPI

The telemetry is automatically configured when the application starts:

```python
from utils.telemetry_config import setup_azure_monitor

# In your main.py or startup code
setup_azure_monitor("audioagent")
```

OpenTelemetry will automatically instrument:
- FastAPI requests and responses
- Azure SDK calls
- HTTP client requests (aiohttp, requests)
- Custom logging

## Production Deployment

For production deployment with Azure Container Apps or App Service:

1. **Enable Managed Identity:**
   ```bicep
   identity: {
     type: 'SystemAssigned'
   }
   ```

2. **Grant Permissions in Bicep:**
   ```bicep
   resource appInsightsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
     name: guid(appInsights.id, containerApp.id, 'ae349356-3a1b-4a5e-921d-050484c6347e')
     scope: appInsights
     properties: {
       roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ae349356-3a1b-4a5e-921d-050484c6347e') // Application Insights Component Contributor
       principalId: containerApp.identity.principalId
       principalType: 'ServicePrincipal'
     }
   }
   ```

3. **Configure Environment Variables:**
   ```bicep
   environmentVariables: [
     {
       name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
       value: appInsights.properties.ConnectionString
     }
     {
       name: 'ENVIRONMENT'
       value: 'production'
     }
   ]
   ```

## Monitoring and Alerting

Once properly configured, you can monitor your application through:

1. **Application Insights Portal**
   - Live metrics (if enabled)
   - Application map
   - Performance counters
   - Custom telemetry

2. **Log Analytics Queries**
   ```kusto
   traces
   | where timestamp > ago(1h)
   | where severityLevel >= 2
   | order by timestamp desc
   ```

3. **Custom Metrics**
   ```python
   from azure.monitor.opentelemetry import configure_azure_monitor
   from opentelemetry import metrics
   
   # Get meter
   meter = metrics.get_meter(__name__)
   
   # Create custom counter
   request_counter = meter.create_counter("custom_requests_total")
   request_counter.add(1, {"endpoint": "/api/health"})
   ```

## Security Considerations

- Never hardcode connection strings in source code
- Use Key Vault to store connection strings in production
- Grant minimal required permissions
- Regularly audit role assignments
- Enable diagnostic settings for audit logging

## Support and Resources

- [Azure Monitor OpenTelemetry Documentation](https://docs.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-overview)
- [Application Insights Troubleshooting](https://docs.microsoft.com/en-us/azure/azure-monitor/app/troubleshoot)
- [Azure RBAC Documentation](https://docs.microsoft.com/en-us/azure/role-based-access-control/)
