# :material-monitor-dashboard: Monitoring & Observability Guide

!!! abstract "Application Insights Integration"
    This guide explains how to configure, use, and troubleshoot Azure Application Insights for comprehensive telemetry in the real-time audio agent application.

The application uses the **Azure Monitor OpenTelemetry Distro** to automatically collect and send telemetry data to Application Insights, including:
- Structured logging
- Distributed request tracing
- Performance metrics
- Live Metrics

---

## :material-cogs: Configuration & Authentication

### Environment Variables

| Variable                                | Description                                      | Default   | Required |
| --------------------------------------- | ------------------------------------------------ | --------- | -------- |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | The connection string for your App Insights resource. | None      | **Yes**  |
| `AZURE_MONITOR_DISABLE_LIVE_METRICS`    | Disables Live Metrics to reduce permissions.     | `false`   | No       |
| `ENVIRONMENT`                           | Sets the environment (`dev`, `prod`).            | `dev`     | No       |

### Authentication

The telemetry configuration uses the `DefaultAzureCredential` chain, which automatically handles authentication in both local and deployed environments:
1.  **Managed Identity (in Azure):** Automatically uses the system-assigned or user-assigned managed identity of the hosting service (e.g., Container Apps).
2.  **Local Development:** Falls back to credentials from Azure CLI, Visual Studio Code, or environment variables.

---

## :material-lock-check: Permissions & Troubleshooting

!!! question "Problem: 'Forbidden' errors or 'The Agent/SDK does not have permissions to send telemetry'"
    **Symptoms:**
    ```
    azure.core.exceptions.HttpResponseError: Operation returned an invalid status 'Forbidden'
    Content: {"Code":"InvalidOperation","Message":"The Agent/SDK does not have permissions to send telemetry..."}
    ```
    This error typically occurs because the identity running the application (your user account locally, or a managed identity in Azure) lacks the necessary permissions to write telemetry, especially for the **Live Metrics** feature.

    **Solutions:**
    1.  **Immediate Fix (Disable Live Metrics):** The simplest solution is to disable the Live Metrics feature, which requires elevated permissions.
        ```bash
        # Add this to your .env file or export it
        AZURE_MONITOR_DISABLE_LIVE_METRICS=true
        ```
    2.  **Grant Permissions (Local Development):** Grant your user account the `Application Insights Component Contributor` role on the App Insights resource.
        ```bash
        # Grant permissions to your Azure CLI user
        az role assignment create \
          --assignee $(az account show --query user.name -o tsv) \
          --role "Application Insights Component Contributor" \
          --scope <your-app-insights-resource-id>
        ```
    3.  **Configure Managed Identity (Production):** In Azure, ensure the managed identity of your Container App has the `Application Insights Component Contributor` role. This is handled automatically by the provided Bicep and Terraform templates.

---

## :material-magnify: Viewing Telemetry & Logs

Once configured, you can explore your application's telemetry in the Azure portal.

### Log Analytics Queries
Navigate to your Application Insights resource, select **Logs**, and run Kusto (KQL) queries.

!!! example "Kusto Query Examples"
    === "View Recent Errors"
        ```kusto
        traces
        | where timestamp > ago(1h)
        | where severityLevel >= 3 // 3 for Error, 4 for Critical
        | order by timestamp desc
        ```
    === "Trace a Specific Call"
        ```kusto
        requests
        | where url contains "start_call"
        | project timestamp, url, resultCode, duration, operation_Id
        | join kind=inner (
            traces | extend operation_Id = tostring(customDimensions.operation_Id)
        ) on operation_Id
        ```
    === "Custom Metrics"
        ```kusto
        customMetrics
        | where name == "custom_requests_total"
        | extend endpoint = tostring(customDimensions.endpoint)
        | summarize sum(value) by endpoint
        ```

### Key Monitoring Features
- **Application Map:** Visualizes the dependencies and communication between your services.
- **Live Metrics:** Real-time performance data (if permissions are granted).
- **Performance:** Analyze request latency, dependency calls, and identify bottlenecks.
- **Failures:** Investigate exceptions and failed requests with detailed stack traces.

---

## :material-hammer-wrench: Production Best Practices

- **Use Managed Identity:** Always prefer managed identities for authentication in Azure.
- **Use Key Vault:** Store the Application Insights connection string in Azure Key Vault and reference it in your application configuration.
- **Grant Minimal Permissions:** Assign the most restrictive role necessary. If you don't need Live Metrics, the `Monitoring Metrics Publisher` role may be sufficient.
- **Enable Alerts:** Configure alert rules in Azure Monitor to be notified of high error rates, performance degradation, or other critical events.
- **Sample Telemetry:** For high-traffic applications, configure sampling to reduce costs while still collecting representative data.

!!! info "Additional Resources"
    - **[Azure Monitor OpenTelemetry Documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-overview)**
    - **[Application Insights Troubleshooting](https://learn.microsoft.com/en-us/azure/azure-monitor/app/troubleshoot)**
    - **[Azure RBAC Documentation](https://learn.microsoft.com/en-us/azure/role-based-access-control/)**
