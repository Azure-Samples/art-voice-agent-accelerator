# Configuration System

## Structure

Simplified configuration with 4 core files:

```
config/
├── __init__.py     # Main exports (use this for imports)
├── settings.py     # All environment-loaded settings (organized by domain)
├── constants.py    # Hard-coded values that never change
└── types.py        # Structured dataclass config objects
```

## Quick Start

```python
# Import specific settings
from config import POOL_SIZE_TTS, AZURE_OPENAI_ENDPOINT, AGENT_AUTH_CONFIG

# Import structured config object
from config import AppConfig
config = AppConfig()
print(config.speech_pools.tts_pool_size)

# Validate settings
from config import validate_settings
result = validate_settings()
```

## Settings Organization (settings.py)

All environment variables are organized by domain:

| Section | Examples |
|---------|----------|
| **Azure Identity** | `AZURE_TENANT_ID`, `BACKEND_AUTH_CLIENT_ID` |
| **Azure OpenAI** | `AZURE_OPENAI_ENDPOINT`, `DEFAULT_TEMPERATURE` |
| **Azure Speech** | `AZURE_SPEECH_REGION`, `AZURE_SPEECH_KEY` |
| **Azure ACS** | `ACS_ENDPOINT`, `ACS_SOURCE_PHONE_NUMBER` |
| **Azure Storage** | `AZURE_COSMOS_CONNECTION_STRING` |
| **Agent Configs** | `AGENT_AUTH_CONFIG`, `AGENT_FRAUD_CONFIG` |
| **Voice & TTS** | `GREETING_VOICE_TTS`, `TTS_SAMPLE_RATE_UI` |
| **Connections** | `MAX_WEBSOCKET_CONNECTIONS`, `POOL_SIZE_TTS` |
| **Feature Flags** | `ENABLE_AUTH_VALIDATION`, `DEBUG_MODE` |
| **Security** | `ALLOWED_ORIGINS`, `ENTRA_EXEMPT_PATHS` |

## Structured Config (types.py)

For type-safe access with validation:

```python
from config import AppConfig

config = AppConfig()

# Access nested config
config.speech_pools.tts_pool_size  # int
config.connections.max_connections  # int
config.voice.default_voice  # str

# Validate configuration
result = config.validate()
if not result["valid"]:
    print(result["issues"])

# Get capacity info
info = config.get_capacity_info()
print(f"Effective capacity: {info['effective_capacity']} sessions")
```

## Adding New Settings

1. Add to `settings.py` in the appropriate section
2. Export from `__init__.py` 
3. (Optional) Add to a dataclass in `types.py` for structured access

## Legacy Files (Deprecated)

The following files are deprecated and will be removed:
- `app_settings.py` - Use `settings.py` instead
- `infrastructure.py` - Merged into `settings.py`
- `voice_config.py` - Merged into `settings.py`
- `connection_config.py` - Merged into `settings.py`
- `feature_flags.py` - Merged into `settings.py`
- `security_config.py` - Merged into `settings.py`
- `ai_config.py` - Merged into `settings.py`
- `app_config.py` - Use `types.py` instead

## Validation

```bash
python -c "from config import validate_settings; print(validate_settings())"
```