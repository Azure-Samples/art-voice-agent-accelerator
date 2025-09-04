# Configuration System

## Structure

Production-ready configuration separated by functionality for easy maintenance and clear ownership.

```
config/
├── constants.py        # Hard-coded constants and defaults
├── infrastructure.py   # Azure services, secrets, endpoints
├── app_settings.py     # Main settings aggregator
├── voice_config.py     # Voice, TTS, and speech settings
├── connection_config.py # WebSocket and session management
├── feature_flags.py    # Feature toggles and behaviors
├── ai_config.py        # AI model and agent settings
├── security_config.py  # CORS and authentication paths
└── app_config.py       # Structured dataclass objects
```

## Configuration Types

### **Infrastructure** (`infrastructure.py`)
Azure service connections, secrets, resource IDs
```python
AZURE_OPENAI_ENDPOINT
ACS_CONNECTION_STRING
AZURE_SPEECH_KEY
```

### **Voice & Speech** (`voice_config.py`)
TTS voices, speech recognition, audio settings
```python
GREETING_VOICE_TTS
TTS_SAMPLE_RATE_ACS
VAD_SEMANTIC_SEGMENTATION
```

### **Connections** (`connection_config.py`)
WebSocket limits, session management, connection pools
```python
MAX_WEBSOCKET_CONNECTIONS
SESSION_TTL_SECONDS
POOL_SIZE_TTS
```

### **Feature Flags** (`feature_flags.py`)
Feature toggles, environment settings, monitoring
```python
DTMF_VALIDATION_ENABLED
ENABLE_DOCS
ENABLE_TRACING
```

### **AI Models** (`ai_config.py`)
Agent configs, model parameters
```python
AGENT_AUTH_CONFIG
DEFAULT_TEMPERATURE
AOAI_REQUEST_TIMEOUT
```

### **Security** (`security_config.py`)
CORS settings, exempt authentication paths
```python
ALLOWED_ORIGINS
ENTRA_EXEMPT_PATHS
```

## Usage

```python
from config.app_settings import *  # All settings
from config.voice_config import GREETING_VOICE_TTS  # Specific
```

## Validation

```bash
python -m config.app_settings  # Validate all settings
```