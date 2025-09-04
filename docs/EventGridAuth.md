
on the EasyAuth App Service Configs:

1. Navigate to the app service
2. Go to the app service's Authentication blade
3. On the added identity provider, select the "Edit" button
4. Within the "Edit Identity Provider" window, ensure the Client ID of the Event Grid service principal is in the Allowed Client Applications list.
5. Save the changes.
6. Navigate to the app registration on Entra ID side
7. Create an App Role - i.e "API Invoke" 
8. Ensure you are an Owner of this app registration, otherwise you will not be able to assign this role to the client application


Event Grid Client Application Config
1. Create app registration
2. Ensure you are an Owner over the App Registration
3. Navigate to the app registration's "API Permissions" blade
4. Add a permission for "Event Grid" and select the "user_impersonation"




(Configure the event subscription by using a Microsoft Entra application)[https://learn.microsoft.com/en-us/azure/event-grid/secure-webhook-delivery#configure-the-event-subscription-by-using-a-microsoft-entra-application]


(Script to Secure WebHook delivery with Microsoft Entra Application in Azure Event Grid)[https://learn.microsoft.com/en-us/azure/event-grid/scripts/powershell-webhook-secure-delivery-microsoft-entra-app]

> Event Grid Enterprise App Id: 4962773b-9cdb-44cf-a8bf-237846a00ab7

After script, login as the Event Grid Enterprise App Id in Azure CLI:
```bash
az login --service-principal -u [REPLACE_WITH_EVENT_GRID_SUBSCRIPTION_WRITER_APP_ID] -p [REPLACE_WITH_EVENT_GRID_SUBSCRIPTION_WRITER_APP_SECRET_VALUE] --tenant [REPLACE_WITH_TENANT_ID]

# Example (replace with your actual values):
# az login --service-principal -u <your-app-id> -p <your-app-secret> --tenant <your-tenant-id>
```
Cloud Events Schema = cloudeventschemav1_0


Create the Event Grid subscription:
```bash
az eventgrid system-topic event-subscription create --name [REPLACE_WITH_SUBSCRIPTION_NAME] -g [REPLACE_WITH_RESOURCE_GROUP] --system-topic-name [REPLACE_WITH_SYSTEM_TOPIC] --endpoint [REPLACE_WITH_WEBHOOK_ENDPOINT] --event-delivery-schema [REPLACE_WITH_WEBHOOK_EVENT_SCHEMA] --azure-active-directory-tenant-id [REPLACE_WITH_TENANT_ID] --azure-active-directory-application-id-or-uri [REPLACE_WITH_APPLICATION_ID_FROM_SCRIPT] --endpoint-type webhook


az eventgrid system-topic event-subscription create --name 'EG-Inbound-to-Orchestrator' -g rg-rtaudioagent-noazdtf --system-topic-name eg-topic-acs-gvkiflr9 --endpoint https://rtaudioagent-backend-app-gvkiflr9.azurewebsites.net/api/call/inbound --event-delivery-schema eventgridschema --azure-active-directory-tenant-id 9249ded8-dff5-4e90-9d80-3ae45c13ec3f --azure-active-directory-application-id-or-uri f0e2bf8c-8703-4658-b9b2-8bff99f1c9b6 --endpoint-type webhook
```

>You don't need to modify the value of $eventGridAppId. In this script, AzureEventGridSecureWebhookSubscriber as set for the $eventGridRoleName. Remember, you must be a member of the Microsoft Entra Application Administrator role or be an owner of the service principal of webhook app in Microsoft Entra ID to execute this script.
