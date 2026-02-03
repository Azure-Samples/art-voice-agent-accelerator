# Card Decline API

A self-contained MCP (Model Context Protocol) server for querying debit card and ATM card decline reason codes.

## Overview

The Card Decline API provides:
- **MCP Server**: Self-contained Model Context Protocol interface for AI agents
- **Direct Data Access**: Loads data from local JSON (dev) or Azure Cosmos DB (prod)
- **Comprehensive Database**: JSON-based database containing decline code information

## Architecture

```
┌─────────────────┐
│   AI Agent      │
└────────┬────────┘
         │ MCP Protocol (stdio/HTTP)
         ↓
┌─────────────────────────────────────────┐
│           MCP Server (Self-contained)    │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │     Data Loading Layer           │   │
│  │                                  │   │
│  │  Local Dev:    Azure Prod:       │   │
│  │  JSON File  →  Cosmos DB (OIDC)  │   │
│  └──────────────────────────────────┘   │
└──────────────────────────────────────────┘
         │
         ↓
┌──────────────────────────────────────────┐
│  decline_codes_policy_pack.json (Local)  │
│          OR                               │
│  Azure Cosmos DB - cardapi database      │
└──────────────────────────────────────────┘
```

## Components

### MCP Server (`/mcp_app`)

Self-contained Model Context Protocol server for AI agent interaction.

**Tools Available:**
- `lookup_decline_code` - Look up specific code
- `search_decline_codes` - Search by description/keywords
- `get_all_decline_codes` - List all codes
- `get_decline_codes_metadata` - Get database info

### Database (`/database`)

JSON document database (`decline_codes_policy_pack.json`) containing:
- **Numeric codes** (Base24 system)
- **Alphanumeric codes** (FAST system)
- Descriptions, detailed information, and recommended actions
- Policy pack data: script references, orchestrator actions, contextual rules, and escalation configurations

## Local Development

### Prerequisites
- Python 3.11+
- pip

### Setup

1. **Install MCP dependencies:**
   ```bash
   cd apps/cardapi/mcp_app
   pip install -r requirements.txt
   ```

2. **Run the MCP server:**
   ```bash
   export PYTHONPATH="$(pwd)/../../../"
   python service.py
   ```
   The MCP server will be running and listening for connections.

   In local development, it loads from `database/decline_codes_policy_pack.json`.

### Quick Start Script

```bash
cd apps/cardapi
./start.sh
```

## Docker Deployment

### Build Image

```bash
cd apps/cardapi
docker build -f Dockerfile.mcp -t cardapi-mcp .
docker run -p 80:80 cardapi-mcp
```

For Azure Cosmos DB connection:
```bash
docker run \
  -e AZURE_COSMOS_DATABASE_NAME=cardapi \
  -e AZURE_COSMOS_COLLECTION_NAME=declinecodes \
  -p 80:80 cardapi-mcp
```

## Azure Deployment

The Card API is deployed as an Azure Container App with direct Cosmos DB access via managed identity.

### Deploy with Azure Developer CLI

```bash
# From project root
azd deploy cardapi-mcp
```

### Infrastructure

The Terraform configuration (`infra/terraform/cardapi.tf`) creates:
- Managed identity for the MCP service
- Container App in the shared environment
- Cosmos DB MongoDB user with read access
- Key Vault access for connection strings
- RBAC permissions for ACR, App Configuration, and Application Insights
- External ingress with optional EasyAuth

### Environment Variables

| Variable | Local Dev | Azure |
|----------|-----------|-------|
| `AZURE_COSMOS_DATABASE_NAME` | Optional | `cardapi` |
| `AZURE_COSMOS_COLLECTION_NAME` | Optional | `declinecodes` |
| `AZURE_CLIENT_ID` | Not set (uses az login) | UAI client ID |
| `PYTHONPATH` | Workspace root | `/app` |

### EasyAuth (Optional)

Enable Microsoft Entra ID authentication:
```bash
./devops/scripts/azd/helpers/enable-easyauth-cardapi-mcp.sh \
  -g "$AZURE_RESOURCE_GROUP" \
  -a "$CARDAPI_MCP_CONTAINER_APP_NAME" \
  -i "$CARDAPI_MCP_UAI_CLIENT_ID"
```

## Code Types Reference

### Numeric Codes (Base24)
- Two or three digit numbers (e.g., 02, 51, 700)
- Declines processed by Base24 system
- Examples: 51 (Insufficient funds), 55 (Invalid PIN)

### Alphanumeric Codes (FAST)
- Letters or letter-number combinations (e.g., C1, RT, QA-QZ)
- Declines processed by FAST system
- Examples: C1 (Card status closed), RT (Fraud protection scoring)

## Data Model

Each decline code contains:
```json
{
  "code": "51",
  "description": "Insufficient funds",
  "information": "Account does not have available funds.",
  "actions": [
    "Transfer funds if applicable",
    "Use another payment method"
  ],
  "code_type": "numeric"
}
```

## Integration with AI Agents

AI agents can use the MCP server to:
1. Look up specific decline codes when customers report errors
2. Search for codes based on symptom descriptions
3. Get recommended actions to resolve issues
4. Understand the difference between Base24 and FAST declines

Example AI agent interaction:
```
Agent: A customer received decline code 51. What should they do?
MCP: [lookup_decline_code code="51"]
Response: Code 51 indicates Insufficient funds. Actions: Transfer funds if applicable or use another payment method.
```

## Maintenance

### Updating Decline Codes

**Local Development:**
1. Edit `database/decline_codes_policy_pack.json`
2. Validate JSON structure
3. Restart MCP service

**Azure (Cosmos DB):**
1. Use the provisioning script: `python apps/cardapi/scripts/provision_data.py`
2. Or update directly via Azure Portal / MongoDB client

### Adding New Codes

Add to either `numeric_codes` or `alphanumeric_codes` array:
```json
{
  "code": "XX",
  "description": "Brief description",
  "information": "Detailed information about the decline",
  "actions": ["Action 1", "Action 2"]
}
```

## Security

- MCP server uses managed identity for Azure authentication (no secrets)
- Cosmos DB access via OIDC (Microsoft Entra ID)
- Optional EasyAuth for external access control
- Key Vault integration for connection strings

## Monitoring

The service publishes metrics to Application Insights:
- Request counts and durations
- Error rates
- Custom events for code lookups
- Dependency tracking

## References

- [QUICKSTART.md](./QUICKSTART.md) - Quick start guide
- [MCP Updates](./mcp_app/CARDAPI_MCP_UPDATES.md) - MCP server details
