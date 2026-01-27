# 📧 Email Service Setup

After deploying infrastructure, configure Azure Communication Services (ACS) Email for agent tools that send emails (e.g., claim confirmations, notifications).

!!! note "Optional Service"
    Email is only required if your agents use email tools. Voice calls work without it.

---

## Quick Setup

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
# ACS Email Configuration
AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING=endpoint=https://<your-acs>.communication.azure.com/;accesskey=<key>
AZURE_EMAIL_SENDER_ADDRESS=DoNotReply@<your-domain>.azurecomm.net
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
| `AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING` | Yes | ACS connection string with email permissions |
| `AZURE_EMAIL_SENDER_ADDRESS` | Yes | Sender email (e.g., `DoNotReply@xxx.azurecomm.net`) |

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
