# 📧 Email Service Setup

After deploying infrastructure, configure Azure Communication Services (ACS) Email for agent tools that send emails (e.g., claim confirmations, notifications).

!!! note "Optional Service"
    Email is only required if your agents use email tools. Voice calls work without it.

---

## Quick Setup

!!! tip "Managed Identity (default in Azure)"
    When the backend runs in Azure (Container Apps / App Service) it authenticates
    to ACS — including the Email Communication Service — via the backend's
    user-assigned managed identity. The Terraform grants `Contributor` on the
    ACS resource, which covers Calling, Email, and SMS data planes. **No
    connection string is required in production**; just set `ACS_ENDPOINT` and
    `AZURE_EMAIL_SENDER_ADDRESS`. The connection-string path below is only
    needed for local development without `az login`.

### Step 1: Get Connection String

1. Go to [Azure Portal](https://portal.azure.com) → your **ACS resource**
2. Select **Settings** → **Keys** in the left navigation
3. Copy the **Connection string** (Primary or Secondary)

### Step 2: Get Sender Address

1. In your ACS resource, select **Email** → **Try Email**
2. Note the **Send email from** dropdown value (e.g., `05d1f9c1-c240-4502-a370-4b039d729fea.azurecomm.net`)
3. Your sender address is: `DoNotReply@<that-domain>`

### Step 3: Update Environment

Add to your `.env`:

```bash
# Production (managed identity — preferred):
ACS_ENDPOINT=https://<your-acs>.communication.azure.com/
AZURE_EMAIL_SENDER_ADDRESS=DoNotReply@<your-domain>.azurecomm.net

# Optional local-dev override (connection string):
AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING=endpoint=https://<your-acs>.communication.azure.com/;accesskey=<key>
# Force connection-string mode even in Azure if needed:
# ACS_USE_MANAGED_IDENTITY=false
```

### Step 4: Restart Backend

```bash
# Restart to pick up new env vars
make start_backend
```

---

## Verifying Configuration

### Test via Portal

1. Go to ACS resource → **Email** → **Try Email**
2. Enter a recipient email
3. Click **Send**
4. Check your inbox

### Test via API

```bash
curl -X POST "http://localhost:8010/api/v1/tools/test-email" \
  -H "Content-Type: application/json" \
  -d '{"to": "your-email@example.com", "subject": "Test", "body": "Hello from ACS!"}'
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ACS_ENDPOINT` | Yes (prod) | ACS resource endpoint, used with managed identity |
| `AZURE_EMAIL_SENDER_ADDRESS` | Yes | Sender email (e.g., `DoNotReply@xxx.azurecomm.net`) |
| `AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING` | Local dev | ACS connection string (used only if MI is unavailable) |
| `ACS_USE_MANAGED_IDENTITY` | No | `true`/`false` override. Default: auto-detect Azure-hosted environment |

---

## Custom Domains (Optional)

By default, emails come from `DoNotReply@xxx.azurecomm.net`. For a custom domain:

1. Go to ACS resource → **Email** → **Domains**
2. Click **Add domain**
3. Follow DNS verification steps
4. Update `AZURE_EMAIL_SENDER_ADDRESS` with your custom sender

📚 **Full guide:** [Azure Docs - Email Domains](https://learn.microsoft.com/azure/communication-services/quickstarts/email/add-custom-verified-domains)

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Email service not configured" | Missing env vars | Add `AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING` and `AZURE_EMAIL_SENDER_ADDRESS` |
| "Invalid sender address" | Wrong format | Use `DoNotReply@<domain>.azurecomm.net` format |
| Emails not received | Spam filter | Check spam folder; use custom domain for production |
| 401 Unauthorized | Invalid connection string | Regenerate keys in Azure Portal |

---

## Related

- [Phone Number Setup](phone-number-setup.md) - Configure PSTN calling
- [Local Development](../getting-started/local-development.md) - Full local setup guide
