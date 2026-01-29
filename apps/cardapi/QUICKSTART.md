# Card Decline API - Quick Reference

## 🚀 Quick Start

### Local Development
```bash
cd apps/cardapi
./start.sh
./test_api.py    # Run tests
./stop.sh        # When done
```

### Docker
```bash
cd apps/cardapi

# Build and run backend
docker build -f Dockerfile.backend -t cardapi-backend .
docker run -p 8000:8000 cardapi-backend

# Build and run MCP
docker build -f Dockerfile.mcp -t cardapi-mcp .
docker run -e CARDAPI_BACKEND_URL=http://backend:8000 -p 80:80 cardapi-mcp
```

### Azure Deployment
```bash
# From project root
azd deploy cardapi-backend
azd deploy cardapi-mcp
```

## 📋 API Endpoints

| Endpoint | Method | Description | Example |
|----------|--------|-------------|---------|
| `/health` | GET | Health check | `curl localhost:8000/health` |
| `/api/v1/codes` | GET | Get all codes | `curl localhost:8000/api/v1/codes` |
| `/api/v1/codes/{code}` | GET | Get specific code | `curl localhost:8000/api/v1/codes/51` |
| `/api/v1/search` | GET | Search codes | `curl "localhost:8000/api/v1/search?q=PIN"` |
| `/api/v1/metadata` | GET | Get metadata | `curl localhost:8000/api/v1/metadata` |

## 🔍 Common Decline Codes

### Numeric (Base24)
- **51** - Insufficient funds
- **55** - Invalid PIN
- **61** - Daily limit reached
- **75** - Max invalid PIN tries
- **94** - Duplicate transaction

### Alphanumeric (FAST)
- **C1** - Card status closed
- **RT** - Fraud protection scoring
- **K1** - Client lock
- **CV** - CVV verification failed
- **S4** - Account status closed

## 🔧 Query Parameters

### Filter by Type
```bash
# Numeric codes only (Base24)
curl "localhost:8000/api/v1/codes?code_type=numeric"

# Alphanumeric codes only (FAST)
curl "localhost:8000/api/v1/codes?code_type=alphanumeric"
```

### Search Examples
```bash
# Search for insufficient funds
curl "localhost:8000/api/v1/search?q=insufficient"

# Search for PIN issues
curl "localhost:8000/api/v1/search?q=PIN"

# Search fraud-related
curl "localhost:8000/api/v1/search?q=fraud"

# Search with type filter
curl "localhost:8000/api/v1/search?q=expired&code_type=numeric"
```

## 📊 Response Format

### Individual Code
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

### Code List
```json
{
  "codes": [
    { "code": "51", ... },
    { "code": "55", ... }
  ],
  "total": 2
}
```

## 🤖 MCP Tools

When integrated with AI agents:

### 1. lookup_decline_code
```
Input: { "code": "51" }
Output: Full details for code 51
```

### 2. search_decline_codes
```
Input: { "query": "PIN", "code_type": "numeric" }
Output: All PIN-related numeric codes
```

### 3. get_all_decline_codes
```
Input: { "code_type": "alphanumeric" }
Output: All alphanumeric codes
```

### 4. get_decline_codes_metadata
```
Input: {}
Output: Database statistics and info
```

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Check logs
tail -f apps/cardapi/backend.log

# Verify database exists
ls -la apps/cardapi/database/decline_codes_policy_pack.json
```

### MCP connection issues
```bash
# Verify backend is running
curl http://localhost:8000/health

# Check MCP logs
tail -f apps/cardapi/mcp_app.log

# Verify environment variable
echo $CARDAPI_BACKEND_URL
```

### Docker build fails
```bash
# Ensure you're in the right directory
cd apps/cardapi

# Check Docker is running
docker ps

# Build with verbose output
docker build -f Dockerfile.backend --progress=plain -t cardapi-backend .
```

## 📁 Project Structure

```
apps/cardapi/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt     # Python dependencies
│   └── __init__.py
├── mcp_app/
│   ├── service.py          # MCP server
│   ├── requirements.txt    # Python dependencies
│   └── __init__.py
├── database/
│   └── decline_codes_policy_pack.json  # Decline codes policy pack database
├── Dockerfile.backend      # Backend container
├── Dockerfile.mcp          # MCP container
├── README.md               # Full documentation
├── QUICKSTART.md           # This file
├── start.sh                # Local dev startup
├── stop.sh                 # Local dev shutdown
└── test_api.py             # API test suite
```

## 🔗 Related Files

- [CARDAPI_USAGE_GUIDE.md](backend/CARDAPI_USAGE_GUIDE.md) - Detailed usage guide
- [CARDAPI_MCP_UPDATES.md](mcp_app/CARDAPI_MCP_UPDATES.md) - MCP server updates
- `infra/terraform/cardapi.tf` - Azure infrastructure
- `azure.yaml` - Deployment configuration

## 📚 Documentation

- Full API docs: http://localhost:8000/docs (when running locally)
- ReDoc: http://localhost:8000/redoc
- Detailed README: [README.md](README.md)

## 💡 Tips

1. **Use the OpenAPI docs**: Visit `/docs` for interactive API testing
2. **Filter your queries**: Use `code_type` parameter to reduce results
3. **Check metadata first**: Get counts and info before querying all codes
4. **Use search wisely**: Search is case-insensitive and searches all fields
5. **Monitor logs**: Check Application Insights in Azure for production issues

## 🆘 Support

- Check logs: `backend.log` and `mcp_app.log`
- Verify health: `curl localhost:8000/health`
- Run tests: `./test_api.py`
- Review errors in Application Insights (Azure deployment)
