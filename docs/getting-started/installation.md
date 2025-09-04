# Installation Guide

Complete installation instructions for the Real-Time Voice Agent.

## System Requirements

- **Python**: 3.11 or higher
- **Operating System**: Windows 10+, macOS 10.15+, or Linux
- **Memory**: Minimum 4GB RAM (8GB recommended)
- **Network**: Internet connectivity for Azure services

## Azure Prerequisites

### 1. Azure Subscription
You'll need an active Azure subscription. [Create one for free](https://azure.microsoft.com/free/) if you don't have one.

### 2. Azure Speech Services Resource
Create a Speech Services resource in the Azure portal:

1. Go to [Azure Portal](https://portal.azure.com)
2. Click "Create a resource"
3. Search for "Speech Services"
4. Select your subscription and resource group
5. Choose a region (e.g., East US, West Europe)
6. Select pricing tier (F0 for free tier, S0 for standard)

### 3. Get Your Credentials
After creating the resource:
- Copy the **Key** from the "Keys and Endpoint" section
- Note the **Region** where you created the resource
- Optionally copy the **Resource ID** for managed identity authentication

## Local Development Setup

### 1. Clone Repository
```bash
git clone https://github.com/pablosalvador10/gbb-ai-audio-agent.git
cd gbb-ai-audio-agent
```

### 2. Python Environment
We recommend using a virtual environment:

```bash
# Using venv
python -m venv audioagent
source audioagent/bin/activate  # Linux/macOS
# audioagent\Scripts\activate  # Windows

# Using conda
conda create -n audioagent python=3.11
conda activate audioagent
```

### 3. Install Dependencies
```bash
# Core dependencies
pip install -r requirements.txt

# Development dependencies (optional)
pip install -r requirements-dev.txt
```

### 4. Environment Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your credentials
nano .env  # or use your preferred editor
```

Required environment variables:
```bash
# Azure Speech Services
AZURE_SPEECH_KEY=your-speech-key-here
AZURE_SPEECH_REGION=eastus

# Optional: Custom endpoint
AZURE_SPEECH_ENDPOINT=https://your-custom-endpoint.cognitiveservices.azure.com

# Optional: For managed identity (production)
AZURE_SPEECH_RESOURCE_ID=/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.CognitiveServices/accounts/xxx

# Optional: Audio playback control
TTS_ENABLE_LOCAL_PLAYBACK=true
```

## Production Deployment

### Docker Container
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY utils/ ./utils/

# Set environment variables
ENV AZURE_SPEECH_REGION=eastus
ENV TTS_ENABLE_LOCAL_PLAYBACK=false

EXPOSE 8000
CMD ["python", "-m", "src.main"]
```

### Azure Container Instances
```bash
# Build and push to Azure Container Registry
az acr build --registry myregistry --image voice-agent:latest .

# Deploy to Container Instances with managed identity
az container create \
  --resource-group myResourceGroup \
  --name voice-agent \
  --image myregistry.azurecr.io/voice-agent:latest \
  --assign-identity \
  --environment-variables AZURE_SPEECH_REGION=eastus
```

### Azure App Service
```bash
# Deploy to App Service with system-assigned managed identity
az webapp create \
  --resource-group myResourceGroup \
  --plan myServicePlan \
  --name my-voice-agent \
  --runtime "PYTHON|3.11"

# Enable managed identity
az webapp identity assign \
  --resource-group myResourceGroup \
  --name my-voice-agent
```

## Verify Installation

### 1. Test Import
```python
python -c "
from src.speech.text_to_speech import SpeechSynthesizer
print('✅ Successfully imported SpeechSynthesizer')
"
```

### 2. Test Configuration
```python
from src.speech.text_to_speech import SpeechSynthesizer
import os

synthesizer = SpeechSynthesizer(
    key=os.getenv('AZURE_SPEECH_KEY'),
    region=os.getenv('AZURE_SPEECH_REGION')
)

if synthesizer.validate_configuration():
    print('✅ Configuration is valid')
else:
    print('❌ Configuration validation failed')
```

### 3. Test Basic Synthesis
```python
# Quick synthesis test
audio_data = synthesizer.synthesize_speech("Hello, world!")
print(f'✅ Generated {len(audio_data)} bytes of audio')
```

## Troubleshooting

### Common Installation Issues

**Import Error: No module named 'azure'**
```bash
pip install azure-cognitiveservices-speech
```

**Authentication Failed**
- Verify your `AZURE_SPEECH_KEY` is correct
- Check that your `AZURE_SPEECH_REGION` matches your resource
- Ensure your Azure subscription is active

**Audio Hardware Issues**
- Set `TTS_ENABLE_LOCAL_PLAYBACK=false` for headless environments
- Use `playback="never"` mode in production containers

**Network Connectivity**
- Ensure outbound HTTPS (port 443) access to Azure endpoints
- Check firewall rules for `*.cognitiveservices.azure.com`

### Getting Help

- **Documentation**: [API Reference](../api/overview.md)
- **Examples**: [Usage Examples](../examples/basic-usage.md)
- **Issues**: [GitHub Issues](https://github.com/pablosalvador10/gbb-ai-audio-agent/issues)

## Next Steps

- **[Quick Start Guide](quickstart.md)** - Get started with basic usage
- **[Configuration](configuration.md)** - Advanced configuration options
- **[API Reference](../api/overview.md)** - Complete API documentation
