# Orchestrator Test Script

Interactive testing tool for validating the Speech Cascade orchestrator with both Chat Completions and Responses API endpoints.

## Features

- ✅ Test both `/chat/completions` and `/responses` endpoints
- ✅ Validate parameter differences (verbosity, min_p, typical_p, etc.)
- ✅ Compare responses across endpoints and verbosity levels
- ✅ Interactive mode for live testing
- ✅ Detailed parameter and response logging
- ✅ Automatic .env/.env.local file loading
- ✅ **Azure App Configuration integration** - Seamless config loading from App Config
- ✅ **Entra RBAC authentication by default** - Same auth strategy as the backend

## Quick Start

### Prerequisites

**🔐 Authentication: Entra RBAC (Recommended)**

The script uses **Azure Entra ID (Azure AD) authentication by default**, matching the backend's authentication strategy. No API key required!

**Option 1: Local Development with Entra RBAC (Recommended)**

1. Login to Azure CLI:
```bash
az login
```

2. Create `.env.local` in the project root:
```bash
# .env.local
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
```

That's it! The script will automatically use your Azure CLI credentials.

**Option 2: Local Development with API Key (Fallback)**

If you prefer API key authentication:

```bash
# .env.local
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-api-key-here  # Optional - only if not using Entra
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
```

**Option 3: Azure App Configuration (Production/Team)**

The script automatically loads configuration from Azure App Configuration:

```bash
# .env.local (minimal - just App Config connection)
AZURE_APPCONFIG_ENDPOINT=https://your-appconfig.azconfig.io
AZURE_APPCONFIG_LABEL=dev  # or prod, staging, etc.
AZURE_CLIENT_ID=your-managed-identity-client-id  # For production/managed identity
```

When using App Config, all Azure OpenAI settings are automatically loaded from centralized configuration.

**Authentication Hierarchy:**
1. **API Key** (if `AZURE_OPENAI_KEY` is explicitly set)
2. **Managed Identity** (if `AZURE_CLIENT_ID` is set - production)
3. **Azure CLI Credentials** (from `az login` - local development)
4. **DefaultAzureCredential** (fallback)

**Configuration Hierarchy:**
1. Azure App Configuration (if `AZURE_APPCONFIG_ENDPOINT` is set)
2. .env.local file overrides
3. .env file fallback
4. System environment variables

### Interactive Mode (Recommended)

```bash
cd /path/to/art-voice-agent-accelerator
python devops/scripts/misc/test_orchestrator.py --interactive
```

Or use the quick test script:

```bash
./devops/scripts/misc/quick_test.sh
```

**Interactive Commands:**

```
> test What is the capital of France?
> config verbosity 2
> config endpoint_preference responses
> test Explain quantum computing
> compare What are the benefits of AI?
> show
> help
> quit
```

## Usage Examples

### 1. Single Query Test

Test with default settings (auto endpoint detection):

```bash
python devops/scripts/misc/test_orchestrator.py --query "What is machine learning?"
```

### 2. Test with Responses API

Explicitly use responses endpoint with high verbosity:

```bash
python devops/scripts/misc/test_orchestrator.py \
  --model gpt-5-mini \
  --endpoint responses \
  --verbosity 2 \
  --min-p 0.1 \
  --query "Explain the theory of relativity"
```

### 3. Test with Chat Completions

Use chat completions endpoint:

```bash
python devops/scripts/misc/test_orchestrator.py \
  --model gpt-4o \
  --endpoint chat \
  --verbosity 0 \
  --query "What is Python?"
```

### 4. Compare Endpoints

Compare the same query across both endpoints and all verbosity levels:

```bash
python devops/scripts/misc/test_orchestrator.py \
  --model gpt-4o \
  --compare \
  --query "What is artificial intelligence?"
```

This will test:
- Chat Completions: verbosity 0, 1, 2
- Responses API: verbosity 0, 1, 2

And show a comparison summary.

## Interactive Mode Commands

### `test <query>`

Test a query with current configuration:

```
> test What is the meaning of life?
```

### `config <param> <value>`

Update configuration parameters:

```
> config endpoint_preference responses
> config verbosity 2
> config temperature 0.9
> config min_p 0.1
> config deployment_id gpt-5-mini
```

Available parameters:
- `deployment_id` - Model deployment name
- `endpoint_preference` - `auto`, `chat`, or `responses`
- `verbosity` - 0 (minimal), 1 (standard), 2 (detailed)
- `temperature` - 0.0 to 2.0
- `top_p` - 0.0 to 1.0
- `max_tokens` - Integer
- `min_p` - Float (responses API only)
- `typical_p` - Float (responses API only)
- `reasoning_effort` - `low`, `medium`, `high` (o1/o3 models)

### `show`

Display current model configuration:

```
> show
📋 Current Configuration:
  deployment_id: gpt-5-mini
  endpoint_preference: responses
  verbosity: 2
  temperature: 0.7
  ...
```

### `env`

Display loaded environment configuration (including App Config and authentication status):

```
> env
🔧 LOADED CONFIGURATION
================================================================================

📍 Configuration Source: Azure App Config (your-appconfig)
   App Config Endpoint: https://your-appconfig.azconfig.io
   App Config Label: dev
   Keys Loaded: 45

🔐 Authentication Method: Azure CLI / DefaultAzureCredential

  Azure OpenAI Endpoint: https://your-resource.openai.azure.com/
  Azure OpenAI API Version: 2024-10-21
  Default Deployment: gpt-4o
  Speech Region: eastus
  Environment: dev
  ...
```

Authentication methods shown:
- `🔑 API Key` - Using AZURE_OPENAI_KEY (explicit)
- `🔐 Managed Identity` - Using AZURE_CLIENT_ID (production)
- `🔐 Azure CLI / DefaultAzureCredential` - Using az login (local dev)

### `compare <query>`

Compare endpoints for a query:

```
> compare What is the best programming language?
```

### `help`

Show available commands.

### `quit` / `exit`

Exit the tester.

## Output Explanation

### Test Output

```
================================================================================
🧪 Testing Query: What is machine learning?
================================================================================

📋 Model Configuration:
  Deployment ID: gpt-4o
  Endpoint Preference: responses
  Model Family: gpt-4
  Temperature: 0.7
  Verbosity: 2
  Min P: 0.1

⏳ Processing with orchestrator...

✅ Response Received:
────────────────────────────────────────────────────────────────────────────────
Machine learning is a subset of artificial intelligence (AI) that focuses on...
────────────────────────────────────────────────────────────────────────────────

📊 Response Metadata:
  Agent: TestAgent
  Input Tokens: 45
  Output Tokens: 120
  Latency: 1234.56ms
```

### Comparison Output

```
================================================================================
📈 COMPARISON SUMMARY
================================================================================

1. CHAT | Verbosity=0
   Response Length: 250 chars
   Output Tokens: 60
   Latency: 890.12

2. CHAT | Verbosity=1
   Response Length: 450 chars
   Output Tokens: 110
   Latency: 1234.56

3. RESPONSES | Verbosity=2
   Response Length: 800 chars
   Output Tokens: 200
   Latency: 2100.34
```

## Troubleshooting

### Missing AZURE_OPENAI_ENDPOINT

```
❌ Missing required environment variable: AZURE_OPENAI_ENDPOINT
```

**Fix Option 1 - Entra RBAC (recommended):**

1. Login to Azure:
```bash
az login
```

2. Create `.env.local` in the project root:
```bash
# .env.local
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
```

**Note:** No API key needed! The script uses your Azure identity.

**Fix Option 2 - API Key (fallback):**

```bash
# .env.local
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
```

**Fix Option 3 - Azure App Configuration:**

Set up App Config connection in `.env.local`:

```bash
# .env.local
AZURE_APPCONFIG_ENDPOINT=https://your-appconfig.azconfig.io
AZURE_APPCONFIG_LABEL=dev
```

All Azure OpenAI settings will be automatically loaded from App Config.

### Authentication Errors

**Error: "DefaultAzureCredential failed to retrieve a token"**

**Common Causes:**
1. **Not logged in to Azure CLI**
   ```bash
   az login
   ```

2. **Insufficient permissions on Azure OpenAI resource**
   - Verify you have "Cognitive Services OpenAI User" role
   - Check with: `az role assignment list --assignee your-email@domain.com`

3. **Wrong Azure subscription**
   ```bash
   az account list
   az account set --subscription <subscription-id>
   ```

4. **Managed Identity not configured (production)**
   - Ensure `AZURE_CLIENT_ID` is set correctly
   - Verify managed identity has permissions on Azure OpenAI

**Verification:**
```bash
> env
# Check "Authentication Method" line
# Should show: Azure CLI / DefaultAzureCredential
```

### Azure App Configuration Not Loading

```
⚠️  App Configuration not available: <error>
   Using .env/environment variables only
```

**Common Causes:**
1. **Endpoint not accessible** - Check network/firewall settings
2. **Authentication failed** - Ensure Azure credentials are configured:
   - Local: `az login` or set `AZURE_CLIENT_ID`
   - Production: Managed Identity configured
3. **Invalid endpoint format** - Must end with `.azconfig.io`
4. **Missing label** - Check `AZURE_APPCONFIG_LABEL` matches your App Config

**Verify with:**
```bash
> env
# Shows configuration source and App Config status
```

### Deployment Not Found

```
❌ Error: DeploymentNotFound
```

**Fix:** Use a valid deployment name from your Azure OpenAI resource:

```bash
> config deployment_id your-actual-deployment-name
```

### Unsupported Parameter

```
❌ Error: Unsupported parameter: 'max_tokens' is not supported with this model
```

**Fix:** The model requires responses API. Set endpoint preference:

```bash
> config endpoint_preference responses
```

Or use the `--endpoint responses` flag.

## Validation Checklist

Use this script to validate:

- ✅ Endpoint routing (auto, chat, responses)
- ✅ Parameter separation (max_tokens vs max_completion_tokens)
- ✅ Verbosity levels (0=minimal, 1=standard, 2=detailed)
- ✅ GPT-5 model compatibility
- ✅ Reasoning model support (o1, o3, o4)
- ✅ Advanced sampling (min_p, typical_p)
- ✅ Error handling and user-friendly messages

## Example Testing Flow

```bash
# Start interactive mode
python devops/scripts/misc/test_orchestrator.py --interactive

# Or use the quick start script
./devops/scripts/misc/quick_test.sh

# Test auto detection
> test Hello!
> show

# Check environment configuration
> env

# Test responses API with GPT-5
> config deployment_id gpt-5-mini
> config endpoint_preference responses
> config verbosity 2
> test Explain quantum mechanics
> show

# Compare endpoints
> config deployment_id gpt-4o
> compare What is the best way to learn programming?

# Test with minimal verbosity
> config verbosity 0
> config endpoint_preference chat
> test Quick answer: what is 2+2?

# Exit
> quit
```

## Notes

### Verbosity Levels
- **Verbosity 0 (Minimal):** Optimized for real-time voice (lowest latency, shortest responses)
- **Verbosity 1 (Standard):** Balanced detail level
- **Verbosity 2 (Detailed):** Maximum detail with reasoning (if supported)

### Endpoint Selection
- **Auto Endpoint:** Automatically selects based on model family and parameters
- **Chat Endpoint:** Forces `/chat/completions` (for gpt-4, gpt-4o)
- **Responses Endpoint:** Forces `/responses` (for gpt-5, o1, o3, o4)

### Authentication Strategy (Matches Backend)
The test script uses the **same authentication strategy as the backend**:

1. **Entra RBAC (Azure AD) by default** - No API key required
   - Local dev: Uses Azure CLI credentials (`az login`)
   - Production: Uses Managed Identity (`AZURE_CLIENT_ID`)

2. **API Key fallback** - Only if `AZURE_OPENAI_KEY` is explicitly set

This ensures the test script authenticates exactly like the production application, making tests more reliable and reducing configuration overhead.

## Integration with Testing

This script can be used alongside:
- Manual testing via voice interface
- Automated test suites
- Parameter tuning experiments
- Model comparison studies

For automated testing, pipe queries from a file:

```bash
while IFS= read -r query; do
    python devops/scripts/misc/test_orchestrator.py --query "$query" --endpoint responses
done < devops/scripts/misc/test_queries.txt
```
