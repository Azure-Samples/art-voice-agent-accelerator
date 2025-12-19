# 📞 Phone Number Setup Guide

After deploying the infrastructure, you need to configure an Azure Communication Services (ACS) phone number for inbound and outbound voice calls.

## Quick Overview

| Method | Best For | Time |
|--------|----------|------|
| [Azure Portal](#option-1-azure-portal-recommended) | First-time setup | ~5 min |
| [Azure CLI](#option-2-azure-cli) | Automation/scripting | ~2 min |
| [Post-provision Script](#option-3-post-provision-script) | During deployment | Automatic |

---

## Option 1: Azure Portal (Recommended)

### Step 1: Navigate to Phone Numbers

1. Go to the [Azure Portal](https://portal.azure.com)
2. Find your **Azure Communication Services** resource (named `acs-<environment>-<token>`)
3. In the left navigation, select **Telephony and SMS** → **Phone numbers**

![ACS Phone Numbers](https://learn.microsoft.com/azure/communication-services/media/telephony/telephony-overview.png)

### Step 2: Get a Phone Number

1. Click **+ Get** in the top toolbar
2. Select your country/region (e.g., **United States**)
3. Choose number type:
   - **Toll-free** (recommended for demos) - No geographic restrictions
   - **Local/Geographic** - Tied to a specific area code
4. Select features:
   - ✅ **Make calls** - Required for outbound
   - ✅ **Receive calls** - Required for inbound
   - ✅ **Send SMS** (optional)
5. Click **Search** to find available numbers
6. Select a number and click **Purchase**

!!! note "Processing Time"
    Phone number provisioning typically takes 1-2 minutes.

### Step 3: Update App Configuration

Once you have your phone number (e.g., `+18001234567`), update it in Azure App Configuration:

1. Go to your **App Configuration** resource (named `appconfig-<environment>-<token>`)
2. Select **Configuration explorer** in the left navigation
3. Click **+ Create** → **Key-value**
4. Enter:
   - **Key**: `azure/acs/source-phone-number`
   - **Label**: Your environment name (e.g., `contoso`)
   - **Value**: Your phone number in E.164 format (e.g., `+18001234567`)
5. Click **Apply**

### Step 4: Trigger Configuration Refresh

To have running applications pick up the new phone number without restart:

```bash
# Update the sentinel key to trigger refresh
az appconfig kv set \
  --endpoint "https://appconfig-<env>-<token>.azconfig.io" \
  --key "app/sentinel" \
  --value "v$(date +%s)" \
  --label "<environment>" \
  --yes
```

Or in the Azure Portal:

1. Find the key `app/sentinel` in Configuration explorer
2. Edit its value to any new value (e.g., `v2`)
3. Click **Apply**

---

## Option 2: Azure CLI

### Purchase and Configure in One Command

```bash
# Set your variables
ACS_NAME="acs-<environment>-<token>"
RESOURCE_GROUP="rg-<environment>-<token>"
APPCONFIG_ENDPOINT="https://appconfig-<environment>-<token>.azconfig.io"
LABEL="<environment>"

# Purchase a toll-free number
PHONE_NUMBER=$(az communication phonenumber purchase \
  --name $ACS_NAME \
  --resource-group $RESOURCE_GROUP \
  --phone-number-type tollFree \
  --country-code US \
  --capabilities calling \
  --query phoneNumber -o tsv)

echo "Purchased: $PHONE_NUMBER"

# Update App Configuration
az appconfig kv set \
  --endpoint $APPCONFIG_ENDPOINT \
  --key "azure/acs/source-phone-number" \
  --value "$PHONE_NUMBER" \
  --label $LABEL \
  --yes

# Trigger refresh
az appconfig kv set \
  --endpoint $APPCONFIG_ENDPOINT \
  --key "app/sentinel" \
  --value "v$(date +%s)" \
  --label $LABEL \
  --yes

echo "✅ Phone number configured in App Config"
```

---

## Option 3: Post-provision Script

During `azd up` deployment, the post-provision script offers interactive phone number configuration:

```text
Phone number options:
  1) Enter existing phone number
  2) Provision new from Azure
  3) Skip

Choice (1-3): 
```

If you select option 1, enter your phone number in E.164 format (`+1234567890`).

---

## Verifying the Configuration

### Check App Configuration

```bash
# List all ACS-related keys
az appconfig kv list \
  --endpoint $APPCONFIG_ENDPOINT \
  --label $LABEL \
  --key "azure/acs/*" \
  --output table
```

Expected output:

```text
Key                              Value
-------------------------------  ----------------
azure/acs/endpoint              https://acs-xxx.communication.azure.com
azure/acs/immutable-id          xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
azure/acs/source-phone-number   +18001234567
```

### Test Outbound Call

```bash
BACKEND_URL=$(azd env get-value BACKEND_CONTAINER_APP_URL)

curl -X POST "$BACKEND_URL/api/v1/calls/outbound" \
  -H "Content-Type: application/json" \
  -d '{"target_phone_number": "+1YOUR_PHONE"}'
```

---

## Troubleshooting

### "Phone number not configured" Error

The application reads the phone number from App Configuration at startup. If you see this error:

1. Verify the key exists: `azure/acs/source-phone-number`
2. Verify the label matches your environment
3. Trigger a config refresh (update `app/sentinel`)
4. Restart the backend container if dynamic refresh is disabled

### "Phone number not verified" Error

ACS requires phone numbers to be verified for certain countries. Go to **Phone numbers** in your ACS resource and check the verification status.

### Number Format Issues

Always use E.164 format:

- ✅ Correct: `+18001234567`
- ❌ Wrong: `800-123-4567`, `1-800-123-4567`, `(800) 123-4567`

---

## Next Steps

After configuring your phone number:

1. **Configure inbound webhook** - See [Deployment Guide](README.md#configure-inbound-call-webhook)
2. **Test voice calls** - Use the frontend UI or API
3. **Monitor call logs** - Check Application Insights

!!! tip "Local Development"
    For local development with dev tunnels, ensure your webhook URL is updated in the ACS Event Grid subscription.
