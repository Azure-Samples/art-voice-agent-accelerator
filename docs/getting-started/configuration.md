# :material-cog: Configuration Guide

!!! info "Fine-Tune Your Voice Agent"
    Comprehensive configuration options for environment variables, authentication, and optional features.

## :material-file-settings: Environment Setup

### Step 1: Environment File Creation

!!! tip "Quick Setup"
    Start with the provided template for all required variables.

```bash title="Copy and configure environment template"
# Copy the environment template
cp .env.example .env

# Edit with your preferred editor
code .env  # VS Code
# or nano .env, vim .env, etc.
```

### Step 2: Required Configuration

=== "Azure Speech Services"
    | Variable | Required | Description | Example |
    |----------|----------|-------------|---------|
    | `AZURE_SPEECH_KEY` | ✅ (unless using managed identity) | Speech resource key | `1a2b3c4d5e6f...` |
    | `AZURE_SPEECH_REGION` | ✅ | Azure region identifier | `eastus`, `westeurope` |
    | `AZURE_SPEECH_ENDPOINT` | Optional | Custom endpoint URL | `https://custom.cognitiveservices.azure.com` |
    | `AZURE_SPEECH_RESOURCE_ID` | Optional | Full resource ID for managed identity | `/subscriptions/.../accounts/speech-svc` |

=== "Azure Communication Services"
    | Variable | Required | Description | Example |
    |----------|----------|-------------|---------|
    | `AZURE_COMMUNICATION_CONNECTION_STRING` | ✅ for call automation | ACS connection string | `endpoint=https://...;accesskey=...` |
    | `ACS_RESOURCE_CONNECTION_STRING` | Alternative | Legacy naming convention | Same format as above |

=== "Optional Services"
    | Variable | Required | Description | Example |
    |----------|----------|-------------|---------|
    | `AZURE_OPENAI_ENDPOINT` | Optional | Azure OpenAI service endpoint | `https://my-openai.openai.azure.com` |
    | `AZURE_OPENAI_KEY` | Optional | Azure OpenAI API key | `sk-...` |
    | `REDIS_CONNECTION_STRING` | For session state | Redis cache connection | `redis://localhost:6379` |

!!! info "Microsoft Learn Resources"
    - **[Speech Services Keys](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/overview#create-a-speech-resource-in-the-azure-portal)** - Get your Speech Services credentials
    - **[Communication Services Setup](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/create-communication-resource)** - Create ACS resources
    - **[Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource)** - Set up OpenAI integration

## :material-security: Managed Identity (Recommended for Production)

!!! success "Enhanced Security"
    Use managed identity to eliminate API keys in production environments.

### Configuration for Managed Identity

```bash title="Managed identity environment variables"
# Disable API key authentication
AZURE_SPEECH_KEY=""

# Required: Region and Resource ID
AZURE_SPEECH_REGION=eastus
AZURE_SPEECH_RESOURCE_ID=/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<speech-service-name>

# Enable managed identity
USE_MANAGED_IDENTITY=true
```

### Azure Role Assignments

=== "Required Roles"
    **For Speech Services**:
    ```bash title="Assign Speech Services role"
    # Get your managed identity principal ID
    IDENTITY_PRINCIPAL_ID=$(az identity show \
        --name your-managed-identity \
        --resource-group your-resource-group \
        --query principalId -o tsv)
    
    # Assign Cognitive Services User role
    az role assignment create \
        --assignee $IDENTITY_PRINCIPAL_ID \
        --role "Cognitive Services User" \
        --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<speech-name>"
    ```

=== "Optional Roles"
    **For Azure OpenAI**:
    ```bash title="Assign OpenAI role"
    az role assignment create \
        --assignee $IDENTITY_PRINCIPAL_ID \
        --role "Cognitive Services OpenAI User" \
        --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<openai-name>"
    ```

!!! info "Microsoft Learn Resources"
    - **[Managed Identity Overview](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview)** - Understanding managed identities
    - **[Role-Based Access Control](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)** - Azure RBAC fundamentals

## :material-microphone: Voice Configuration

!!! tip "Customization Options"
    Tailor voice characteristics for your specific use case and audience.

### Default Voice Settings

Customize default voices via `apps/rtagent/backend/config/voice_config.py`. You can override values with environment variables:

=== "Voice Selection"
    ```bash title="Voice configuration options"
    # Primary voice selection
    DEFAULT_VOICE_ALIAS=support_contact_center
    DEFAULT_VOICE_NAME=en-US-JennyMultilingualNeural
    
    # Voice characteristics  
    DEFAULT_VOICE_STYLE=customer-service
    DEFAULT_VOICE_RATE=+10%
    DEFAULT_VOICE_PITCH=medium
    ```

=== "Advanced Settings"
    ```bash title="Advanced voice options"
    # Audio quality settings
    AUDIO_OUTPUT_FORMAT=audio-24khz-48kbitrate-mono-mp3
    SAMPLE_RATE=24000
    
    # Streaming configuration
    ENABLE_STREAMING=true
    STREAM_CHUNK_SIZE=1024
    
    # Pronunciation and SSML
    ENABLE_SSML_PROCESSING=true
    PRONUNCIATION_LEXICON_URI=https://example.com/lexicon.xml
    ```

### Voice Aliases

Configure voice aliases for different scenarios:

| Alias | Voice | Style | Use Case |
|-------|-------|-------|----------|
| `support_contact_center` | `en-US-JennyMultilingualNeural` | `customer-service` | Customer support calls |
| `sales_assistant` | `en-US-AriaNeural` | `friendly` | Sales and marketing |
| `technical_narrator` | `en-US-BrianNeural` | `newscast` | Technical documentation |
| `casual_chat` | `en-US-SaraNeural` | `chat` | Informal conversations |

!!! info "Microsoft Learn Resources"
    - **[Voice Gallery](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts)** - Browse all available voices
    - **[SSML Reference](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup)** - Speech Synthesis Markup Language
    - **[Voice Tuning](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis-viseme)** - Advanced voice customization

## :material-chart-line: Telemetry & Observability

!!! success "Production Monitoring"
    Enable comprehensive monitoring and tracing for production deployments.

### OpenTelemetry Configuration

```bash title="OpenTelemetry environment variables"
# Azure Monitor integration
OTEL_EXPORTER_OTLP_ENDPOINT=https://<workspace-id>.monitor.azure.com/v1/traces
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <instrumentation-key>"
OTEL_SERVICE_NAME=rt-voice-agent
OTEL_SERVICE_VERSION=1.0.0

# Service identification
OTEL_RESOURCE_ATTRIBUTES=service.name=rt-voice-agent,service.version=1.0.0,deployment.environment=production

# Tracing configuration
OTEL_TRACES_EXPORTER=otlp
OTEL_METRICS_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
```

### Logging Configuration

=== "Development"
    ```bash title="Development logging"
    LOG_LEVEL=DEBUG
    LOG_FORMAT=human-readable
    ENABLE_CORRELATION_ID=true
    LOG_TO_FILE=false
    ```

=== "Production"
    ```bash title="Production logging"
    LOG_LEVEL=INFO
    LOG_FORMAT=json
    ENABLE_CORRELATION_ID=true
    LOG_TO_FILE=true
    LOG_FILE_PATH=/var/log/voice-agent/app.log
    LOG_ROTATION_SIZE=10MB
    LOG_RETENTION_DAYS=30
    ```

### Application Insights Setup

!!! tip "Quick Setup"
    Use the Makefile command to bootstrap Application Insights automatically.

```bash title="Bootstrap Application Insights"
# Configure Azure Monitor and Application Insights
make configure_observability

# This will:
# 1. Create Application Insights workspace
# 2. Configure connection strings
# 3. Set up log analytics workspace
# 4. Update .env with correct values
```

!!! info "Microsoft Learn Resources"
    - **[Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)** - Application performance monitoring
    - **[OpenTelemetry with Azure](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable)** - OpenTelemetry integration guide
    - **[Log Analytics](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-analytics-overview)** - Centralized logging solution

## :material-folder: Storage and File Management

### Local Storage Configuration

```bash title="Storage environment variables"
# Audio output configuration
AUDIO_OUTPUT_DIR=./output/audio
ENABLE_AUDIO_CACHE=true
AUDIO_CACHE_TTL=3600  # 1 hour in seconds

# Application cache
VOICE_AGENT_CACHE_DIR=./cache
CACHE_MAX_SIZE=1GB

# Temporary files
TEMP_FILE_DIR=./tmp
TEMP_FILE_CLEANUP_INTERVAL=300  # 5 minutes
```

### Headless Environment Settings

!!! warning "CI/CD and Headless Deployments"
    Disable audio playback for automated environments and server deployments.

```bash title="Headless configuration"
# Disable local audio playback
TTS_ENABLE_LOCAL_PLAYBACK=false

# Headless environment detection
FORCE_HEADLESS_MODE=true

# Alternative audio output
AUDIO_OUTPUT_FORMAT=file  # Options: file, stream, buffer
SAVE_AUDIO_FILES=true     # Save to disk for debugging
```## :material-key: Secrets Management

!!! danger "Security Best Practices"
    Never commit secrets to version control. Use secure secret management for all environments.

### Local Development

=== "Using direnv"
    ```bash title="Setup direnv for automatic environment loading"
    # Install direnv (macOS)
    brew install direnv
    
    # Add to shell configuration
    echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc
    source ~/.zshrc
    
    # Create .envrc file
    echo "dotenv .env" > .envrc
    direnv allow .
    ```

=== "Using python-dotenv"
    ```python title="Load environment variables in Python"
    from dotenv import load_dotenv
    import os
    
    # Load .env file
    load_dotenv()
    
    # Access variables
    speech_key = os.getenv('AZURE_SPEECH_KEY')
    speech_region = os.getenv('AZURE_SPEECH_REGION')
    ```

### GitHub Actions

```yaml title="GitHub Actions secrets configuration"
# .github/workflows/deploy.yml
env:
  AZURE_SPEECH_KEY: ${{ secrets.AZURE_SPEECH_KEY }}
  AZURE_SPEECH_REGION: ${{ secrets.AZURE_SPEECH_REGION }}
  AZURE_COMMUNICATION_CONNECTION_STRING: ${{ secrets.ACS_CONNECTION_STRING }}
```

**Setup Steps**:
1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Add each required secret from your `.env` file

### Azure Key Vault Integration

=== "Terraform/AZD Deployment"
    ```bash title="Sync Key Vault secrets to local environment"
    # After infrastructure deployment
    make update_env_with_secrets
    
    # This will:
    # 1. Read secrets from Azure Key Vault
    # 2. Update your local .env file
    # 3. Validate all required variables are set
    ```

=== "Manual Key Vault Setup"
    ```bash title="Azure Key Vault commands"
    # Store secrets in Key Vault
    az keyvault secret set \
        --vault-name your-key-vault \
        --name "azure-speech-key" \
        --value "your-speech-key-here"
    
    # Retrieve secrets
    az keyvault secret show \
        --vault-name your-key-vault \
        --name "azure-speech-key" \
        --query "value" -o tsv
    ```

### Environment Validation

```bash title="Validate environment configuration"
# Check required variables are set
python -c "
import os
required_vars = [
    'AZURE_SPEECH_REGION',
    'AZURE_COMMUNICATION_CONNECTION_STRING'
]

missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    print(f'❌ Missing required variables: {missing}')
    exit(1)
else:
    print('✅ All required environment variables are set')
"
```

!!! info "Microsoft Learn Resources"
    - **[Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/overview)** - Secure secret management
    - **[Key Vault Integration](https://learn.microsoft.com/en-us/azure/key-vault/general/tutorial-net-create-vault-azure-web-app)** - Application integration patterns
    - **[GitHub Actions with Azure](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure)** - Secure GitHub workflows

## :material-check-circle: Configuration Validation

### Environment Health Check

```python title="Comprehensive configuration validation"
#!/usr/bin/env python3
"""Configuration validation script"""

import os
from typing import Dict, List, Tuple

def validate_config() -> Tuple[bool, List[str]]:
    """Validate all configuration settings."""
    issues = []
    
    # Required variables
    required = {
        'AZURE_SPEECH_REGION': 'Azure Speech Services region',
        'AZURE_COMMUNICATION_CONNECTION_STRING': 'Azure Communication Services connection',
    }
    
    # Check managed identity vs API key
    use_managed_identity = os.getenv('USE_MANAGED_IDENTITY', '').lower() == 'true'
    
    if use_managed_identity:
        if not os.getenv('AZURE_SPEECH_RESOURCE_ID'):
            issues.append('AZURE_SPEECH_RESOURCE_ID required for managed identity')
    else:
        if not os.getenv('AZURE_SPEECH_KEY'):
            issues.append('AZURE_SPEECH_KEY required (or enable managed identity)')
    
    # Check required variables
    for var, description in required.items():
        if not os.getenv(var):
            issues.append(f'Missing {var} ({description})')
    
    # Validate region format
    region = os.getenv('AZURE_SPEECH_REGION', '')
    if region and ' ' in region:
        issues.append(f'Invalid region format: "{region}". Use format like "eastus", not "East US"')
    
    return len(issues) == 0, issues

if __name__ == '__main__':
    valid, issues = validate_config()
    if valid:
        print('✅ Configuration validation passed')
    else:
        print('❌ Configuration validation failed:')
        for issue in issues:
            print(f'  - {issue}')
```

### Quick Configuration Test

```bash title="Quick configuration test"
# Run configuration validation
python scripts/validate_config.py

# Test Speech Services connection
python -c "
from src.speech.text_to_speech import SpeechSynthesizer
import os

try:
    synthesizer = SpeechSynthesizer(
        key=os.getenv('AZURE_SPEECH_KEY'),
        region=os.getenv('AZURE_SPEECH_REGION')
    )
    if synthesizer.validate_configuration():
        print('✅ Speech Services configuration valid')
    else:
        print('❌ Speech Services configuration invalid')
except Exception as e:
    print(f'❌ Error: {e}')
"
```

---

!!! success "Configuration Complete"
    Your Real-Time Voice Agent is now configured and ready for deployment. Next, explore the [API Reference](../api/README.md) to start building your voice application.

