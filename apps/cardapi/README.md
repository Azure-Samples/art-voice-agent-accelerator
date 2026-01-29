# Card Decline API

A microservices architecture for querying and managing debit card and ATM card decline reason codes.

## Overview

The Card Decline API provides:
- **REST API Backend**: FastAPI-based service for querying decline codes
- **MCP Server**: Model Context Protocol interface for AI agents to interact with the API
- **Document Database**: JSON-based database containing comprehensive decline code information

## Architecture

```
┌─────────────────┐
│   AI Agent      │
└────────┬────────┘
         │ MCP Protocol (stdio)
         ↓
┌─────────────────┐
│   MCP Server    │
│  (Port 80 HTTP) │
└────────┬────────┘
         │ HTTP
         ↓
┌─────────────────┐      ┌──────────────────┐
│ FastAPI Backend │ ───→ │ decline_codes    │
│  (Port 8000)    │      │   .json          │
└─────────────────┘      └──────────────────┘
```

## Components

### 1. Backend API (`/backend`)

FastAPI REST service providing endpoints for decline code lookups.

**Endpoints:**
- `GET /` - Root/health check
- `GET /health` - Health check
- `GET /api/v1/codes` - Get all decline codes (filter by type)
- `GET /api/v1/codes/{code}` - Get specific decline code
- `GET /api/v1/search?q={query}` - Search decline codes
- `GET /api/v1/metadata` - Get database metadata

**Example Requests:**
```bash
# Get specific code
curl http://localhost:8000/api/v1/codes/51

# Search for codes
curl http://localhost:8000/api/v1/search?q=insufficient

# Get all numeric codes
curl http://localhost:8000/api/v1/codes?code_type=numeric
```

### 2. MCP Server (`/mcp_app`)

Model Context Protocol server that wraps the backend API for AI agent interaction.

**Tools Available:**
- `lookup_decline_code` - Look up specific code
- `search_decline_codes` - Search by description/keywords
- `get_all_decline_codes` - List all codes
- `get_decline_codes_metadata` - Get database info

### 3. Database (`/database`)

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

1. **Install backend dependencies:**
   ```bash
   cd apps/cardapi/backend
   pip install -r requirements.txt
   ```

2. **Run the backend:**
   ```bash
   python main.py
   ```
   The API will be available at http://localhost:8000

3. **Install MCP dependencies:**
   ```bash
   cd ../mcp_app
   pip install -r requirements.txt
   ```

4. **Run the MCP server:**
   ```bash
   export CARDAPI_BACKEND_URL=http://localhost:8000
   python service.py
   ```
   The MCP server will be running and listening for connections

### Testing the API

```bash
# Test health endpoint
curl http://localhost:8000/health

# Look up code 51 (Insufficient funds)
curl http://localhost:8000/api/v1/codes/51

# Search for PIN-related codes
curl http://localhost:8000/api/v1/search?q=PIN

# Get all alphanumeric codes
curl http://localhost:8000/api/v1/codes?code_type=alphanumeric
```

## Docker Deployment

### Build Images

**Backend:**
```bash
cd apps/cardapi
docker build -f Dockerfile.backend -t cardapi-backend .
docker run -p 8000:8000 cardapi-backend
```

**MCP Server:**
```bash
docker build -f Dockerfile.mcp -t cardapi-mcp .
docker run -e CARDAPI_BACKEND_URL=http://backend:8000 -p 80:80 cardapi-mcp
```

## Azure Deployment

The Card API is deployed as two Azure Container Apps within the existing infrastructure:

1. **cardapi-backend** - External-facing REST API
2. **cardapi-mcp** - Internal MCP server

### Deploy with Azure Developer CLI

```bash
# From project root
azd deploy cardapi-backend
azd deploy cardapi-mcp
```

### Infrastructure

The Terraform configuration (`infra/terraform/cardapi.tf`) creates:
- Managed identities for both services
- Container Apps in the shared environment
- RBAC permissions for ACR, App Configuration, and Application Insights
- Ingress configurations (external for backend, internal for MCP)

### Environment Variables

Both services are configured with:
- `AZURE_APPCONFIG_ENDPOINT` - App Configuration endpoint
- `AZURE_APPCONFIG_LABEL` - Environment label
- `AZURE_CLIENT_ID` - Managed identity client ID
- `APPLICATIONINSIGHTS_CONNECTION_STRING` - Telemetry connection string

MCP server additionally has:
- `CARDAPI_BACKEND_URL` - URL to the backend API

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

1. Edit `database/decline_codes_policy_pack.json`
2. Validate JSON structure
3. Restart backend service (auto-reloads on startup)

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

## Monitoring

Both services publish metrics to Application Insights:
- Request counts and durations
- Error rates
- Custom events for code lookups
- Dependency tracking

## Security

- Backend uses external ingress with HTTPS
- MCP server uses internal ingress (not exposed to internet)
- Both services authenticate to Azure services using managed identities
- No secrets stored in code or environment variables

## Contributing

When adding new features:
1. Follow the Copilot instructions in `.github/copilot-instructions.md`
2. Use existing patterns from `src/` modules
3. Maintain async/await patterns
4. Add appropriate logging with `get_logger(__name__)`

## References

- [QUICKSTART.md](./QUICKSTART.md) - Quick start guide for the Card Decline API
- [CARDAPI_USAGE_GUIDE.md](./backend/CARDAPI_USAGE_GUIDE.md) - Detailed usage guide
- [CARDAPI_MCP_UPDATES.md](./mcp_app/CARDAPI_MCP_UPDATES.md) - MCP server updates and details
