# App Configuration Module

Centralized configuration management for the Real-Time Voice Agent.

## Features

- All service endpoints and settings in one place
- Environment labels (dev, staging, prod)
- Feature flags with Azure-native format
- Key Vault references for secrets
- RBAC-only access (no access keys)
- Dynamic refresh via sentinel key

## Usage

```hcl
module "appconfig" {
  source = "./modules/appconfig"
  name   = "appconfig-${var.environment_name}"
  # ...
}
```

## Configuration Keys

### Azure Services
| Key | Description |
|-----|-------------|
| `azure/openai/endpoint` | Azure OpenAI endpoint |
| `azure/openai/deployment-id` | Chat deployment ID |
| `azure/openai/api-version` | API version |
| `azure/openai/default-temperature` | Default LLM temperature |
| `azure/openai/default-max-tokens` | Default max tokens |
| `azure/openai/request-timeout` | Request timeout (seconds) |
| `azure/speech/endpoint` | Azure Speech endpoint |
| `azure/speech/region` | Azure Speech region |
| `azure/speech/resource-id` | Speech resource ID |
| `azure/acs/endpoint` | ACS endpoint |
| `azure/acs/immutable-id` | ACS immutable resource ID |
| `azure/acs/source-phone-number` | Source phone number |
| `azure/acs/connection-string` | ACS connection string (Key Vault ref) |
| `azure/redis/hostname` | Redis hostname |
| `azure/redis/port` | Redis port |
| `azure/cosmos/database-name` | Cosmos DB database |
| `azure/cosmos/collection-name` | Cosmos DB collection |
| `azure/cosmos/connection-string` | Cosmos connection string |
| `azure/storage/account-name` | Storage account name |
| `azure/storage/container-url` | Blob container URL |
| `azure/voicelive/endpoint` | Voice Live endpoint (optional) |
| `azure/voicelive/model` | Voice Live model (optional) |
| `azure/appinsights/connection-string` | App Insights connection |

### Pool Settings
| Key | Description | Default |
|-----|-------------|---------|
| `app/pools/tts-size` | TTS pool size | 50 |
| `app/pools/stt-size` | STT pool size | 50 |
| `app/pools/aoai-size` | AOAI pool size | 50 |
| `app/pools/low-water-mark` | Pool low water mark | 10 |
| `app/pools/high-water-mark` | Pool high water mark | 45 |
| `app/pools/acquire-timeout` | Pool acquire timeout | 5 |
| `app/pools/warm-tts-size` | Warm TTS pool size | 3 |
| `app/pools/warm-stt-size` | Warm STT pool size | 2 |
| `app/pools/warm-refresh-interval` | Warm pool refresh interval | 30 |
| `app/pools/warm-session-max-age` | Warm session max age | 1800 |

### Connection Settings
| Key | Description | Default |
|-----|-------------|---------|
| `app/connections/max-websocket` | Max WebSocket connections | 200 |
| `app/connections/queue-size` | Connection queue size | 50 |
| `app/connections/warning-threshold` | Warning threshold | 150 |
| `app/connections/critical-threshold` | Critical threshold | 180 |
| `app/connections/timeout-seconds` | Connection timeout | 300 |
| `app/connections/heartbeat-interval` | Heartbeat interval | 30 |

### Session Settings
| Key | Description | Default |
|-----|-------------|---------|
| `app/session/ttl-seconds` | Session TTL | 1800 |
| `app/session/cleanup-interval` | Cleanup interval | 300 |
| `app/session/state-ttl` | State TTL | 86400 |
| `app/session/max-concurrent` | Max concurrent sessions | 1000 |

### Voice & TTS Settings
| Key | Description | Default |
|-----|-------------|---------|
| `app/voice/tts-sample-rate-ui` | TTS sample rate (UI) | 48000 |
| `app/voice/tts-sample-rate-acs` | TTS sample rate (ACS) | 16000 |
| `app/voice/tts-chunk-size` | TTS chunk size | 1024 |
| `app/voice/tts-processing-timeout` | TTS timeout | 8 |
| `app/voice/stt-processing-timeout` | STT timeout | 10 |
| `app/voice/silence-duration-ms` | VAD silence duration | 1300 |
| `app/voice/recognized-languages` | Supported languages | en-US,es-ES,... |
| `app/voice/default-tts-voice` | Default TTS voice | en-US-EmmaMultilingualNeural |

### Monitoring Settings
| Key | Description | Default |
|-----|-------------|---------|
| `app/monitoring/metrics-interval` | Metrics collection interval | 60 |
| `app/monitoring/pool-metrics-interval` | Pool metrics interval | 30 |

### Application URLs
| Key | Description |
|-----|-------------|
| `app/backend/base-url` | Backend public URL (set by postprovision) |
| `app/frontend/backend-url` | Frontend's backend URL |
| `app/frontend/ws-url` | Frontend's WebSocket URL |

### Special Keys
| Key | Description |
|-----|-------------|
| `app/sentinel` | Sentinel key for dynamic refresh |
| `app/environment` | Environment name |

## Feature Flags

| Flag | Description | Default |
|------|-------------|---------|
| `dtmf-validation` | DTMF tone validation | false |
| `auth-validation` | Entra ID auth validation | false |
| `call-recording` | ACS call recording | false |
| `warm-pool` | Pre-warmed connection pool | true |
| `session-persistence` | Redis session persistence | true |
| `performance-logging` | Performance logging | true |
| `tracing` | Distributed tracing | true |
| `connection-limits` | Connection limiting | true |

## Dynamic Refresh

To trigger a config refresh in running applications:

```bash
az appconfig kv set --endpoint <endpoint> --key app/sentinel --value "v$(date +%s)"
```

## Backwards Compatibility

Container Apps use minimal bootstrap env vars:
- `AZURE_APPCONFIG_ENDPOINT` - App Config endpoint
- `AZURE_APPCONFIG_LABEL` - Environment label
- `AZURE_CLIENT_ID` - Managed identity client ID

All other configuration is loaded from App Configuration at runtime.

