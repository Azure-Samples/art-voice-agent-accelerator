# Azure App Configuration Migration Plan

## Phase 1: Terraform Module & Infrastructure (Backwards Compatible)

### 🎯 Objectives
1. Add Azure App Configuration resource to Terraform
2. Populate App Config with existing Terraform outputs
3. **Zero disruption** to existing Container Apps (they keep using env vars)
4. Enable gradual migration path for apps to switch to App Config

---

## 📋 Implementation Checklist

### Step 1: Create App Configuration Terraform Module ✅ COMPLETE
- [x] Create `infra/terraform/modules/appconfig/` module
- [x] Add `azurerm_app_configuration` resource
- [x] Configure managed identity access (backend UAI, frontend UAI)
- [x] Add Key Vault integration for secrets
- [x] Use environment labels (`dev`, `staging`, `prod`)

### Step 2: Populate Configuration Values ✅ COMPLETE
- [x] Create `azurerm_app_configuration_key` resources for all settings
- [x] Map existing Terraform outputs → App Config keys
- [x] Use Key Vault references for sensitive values (connection strings, keys)
- [x] Add feature flags section

### Step 3: Wire Module into Main Terraform ✅ COMPLETE
- [x] Add module call in `appconfig.tf`
- [x] Pass required variables (endpoints, identities, etc.)
- [x] Add outputs for App Config endpoint
- [x] **DO NOT** modify Container App env vars yet (backwards compat)

### Step 4: Update Container Apps (Optional - Phase 1.5)
- [ ] Add `AZURE_APPCONFIG_ENDPOINT` env var to containers
- [ ] Keep ALL existing env vars (dual-source period)
- [ ] Apps can migrate at their own pace

---

## 🏗️ Terraform Module Structure

```
infra/terraform/modules/appconfig/
├── main.tf           # App Configuration resource
├── keys.tf           # Configuration key/value pairs
├── secrets.tf        # Key Vault references
├── feature_flags.tf  # Feature flag definitions
├── access.tf         # RBAC for managed identities
├── variables.tf      # Module inputs
└── outputs.tf        # Module outputs
```

---

## 📝 Configuration Key Mapping

### Azure Services (Non-Sensitive)
| Terraform Output | App Config Key | Type |
|-----------------|----------------|------|
| `AZURE_OPENAI_ENDPOINT` | `azure/openai/endpoint` | value |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_ID` | `azure/openai/deployment` | value |
| `AZURE_OPENAI_API_VERSION` | `azure/openai/api-version` | value |
| `AZURE_SPEECH_ENDPOINT` | `azure/speech/endpoint` | value |
| `AZURE_SPEECH_REGION` | `azure/speech/region` | value |
| `AZURE_SPEECH_RESOURCE_ID` | `azure/speech/resource-id` | value |
| `ACS_ENDPOINT` | `azure/acs/endpoint` | value |
| `ACS_IMMUTABLE_ID` | `azure/acs/immutable-id` | value |
| `REDIS_HOSTNAME` | `azure/redis/hostname` | value |
| `REDIS_PORT` | `azure/redis/port` | value |

### Secrets (Key Vault References)
| Secret | App Config Key | Key Vault Secret |
|--------|----------------|------------------|
| App Insights Connection | `azure/appinsights/connection-string` | `appinsights-connection-string` |
| Cosmos Connection | `azure/cosmos/connection-string` | `cosmos-connection-string` |
| Redis Password | `azure/redis/password` | `redis-password` |

### Application Settings
| Setting | App Config Key | Default |
|---------|----------------|---------|
| Pool Size TTS | `app/pools/tts-size` | `50` |
| Pool Size STT | `app/pools/stt-size` | `50` |
| Session TTL | `app/session/ttl-seconds` | `1800` |
| Max Connections | `app/connections/max` | `200` |
| Environment | `app/environment` | `dev` |

### Feature Flags
| Flag | App Config Key | Default |
|------|----------------|---------|
| DTMF Validation | `.appconfig.featureflag/dtmf-validation` | `false` |
| Auth Validation | `.appconfig.featureflag/auth-validation` | `false` |
| Call Recording | `.appconfig.featureflag/call-recording` | `false` |
| Warm Pool | `.appconfig.featureflag/warm-pool` | `true` |

---

## ⚠️ Backwards Compatibility Strategy

### What We're NOT Changing (Phase 1)
1. ❌ Container App environment variables stay unchanged
2. ❌ `.env` file generation script stays (for local dev)
3. ❌ Python config module stays reading from `os.getenv()`
4. ❌ Postprovision scripts remain functional

### What We ARE Adding (Phase 1)
1. ✅ New App Configuration resource
2. ✅ All config values mirrored to App Config
3. ✅ RBAC for managed identities to read App Config
4. ✅ New output: `AZURE_APPCONFIG_ENDPOINT`

### Migration Safety
```hcl
# Container Apps will have BOTH sources available:
# 1. Direct env vars (existing - keeps working)
# 2. App Config endpoint (new - opt-in)

# Example: Container App keeps all existing env vars
env {
  name  = "AZURE_OPENAI_ENDPOINT"      # Existing - unchanged
  value = module.ai_foundry.openai_endpoint
}
env {
  name  = "AZURE_APPCONFIG_ENDPOINT"   # NEW - enables gradual migration
  value = azurerm_app_configuration.main.endpoint
}
```

---

## 🔐 Security Considerations

### Managed Identity Access
```hcl
# Backend UAI gets App Configuration Data Reader
resource "azurerm_role_assignment" "backend_appconfig" {
  scope                = azurerm_app_configuration.main.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}
```

### Key Vault Integration
- Secrets stored in Key Vault (existing)
- App Config holds **references** to Key Vault secrets
- Container Apps resolve secrets at runtime via managed identity

---

## 📊 Validation Checklist

### Pre-Deployment
- [ ] Run `terraform plan` - expect only **additions**, no changes/destroys
- [ ] Verify existing Container Apps are not modified
- [ ] Check that existing outputs remain unchanged

### Post-Deployment
- [ ] App Configuration resource created
- [ ] All configuration keys populated
- [ ] Feature flags visible in Azure Portal
- [ ] Managed identities can read App Config
- [ ] Existing Container Apps still function (env vars intact)
- [ ] Test `/api/v1/health/appconfig` endpoint returns status
- [ ] Verify readiness probe includes `app_configuration` check

### Rollback Plan
- Simply don't use App Config in apps
- All existing env vars remain functional
- App Config resource can be destroyed without impact

---

## 📅 Timeline

| Task | Effort | Dependencies |
|------|--------|--------------|
| Create Terraform module | 2-3 hours | None |
| Add to main.tf | 30 min | Module complete |
| Test with `terraform plan` | 30 min | Module integrated |
| Deploy to dev environment | 1 hour | Plan verified |
| Validate no regressions | 1 hour | Deployed |

---

## 🚀 Next Phases (Future)

### Phase 2: Python SDK Integration ✅ COMPLETE
- [x] Add `azure-appconfiguration>=1.7.0` to requirements
- [x] Create `AppConfigProvider` class with caching
- [x] Fallback chain: App Config → env vars → defaults
- [x] Add feature flag support
- [x] Create `/api/v1/health/appconfig` status endpoint
- [x] Add App Configuration to readiness probe

#### Files Created/Modified:
- `apps/artagent/backend/config/appconfig_provider.py` - Main provider (~350 lines)
- `apps/artagent/backend/config/__init__.py` - Updated exports
- `apps/artagent/backend/api/v1/endpoints/health.py` - Added status endpoints
- `pyproject.toml` - azure-appconfiguration in dependencies

#### Key Functions Available:
```python
from config import (
    get_config_value,      # Get config with fallback chain
    get_config_int,        # Get integer config
    get_config_float,      # Get float config  
    get_feature_flag,      # Get feature flag status
    get_provider_status,   # Get provider health info
    refresh_appconfig_cache,  # Force cache refresh
    initialize_appconfig,  # Initialize client (optional)
)
```

### Phase 3: Simplify Deployment Scripts ✅ COMPLETE
- [x] Create `local-dev-setup.sh` for minimal App Config-based local development
- [x] Create `postprovision-simplified.sh` (~150 lines vs ~400 lines original)
- [x] Keep `generate-env.sh` for legacy/fallback mode
- [x] URL patching remains (until App Config dynamic refresh in Phase 4)

#### Files Created:
- `devops/scripts/azd/helpers/local-dev-setup.sh` - Minimal local dev setup
- `devops/scripts/azd/postprovision-simplified.sh` - Streamlined post-provision

#### Script Size Comparison:
| Script | Original | Simplified | Reduction |
|--------|----------|------------|-----------|
| `postprovision.sh` | ~400 lines | ~200 lines | 50% |
| `generate-env.sh` | ~200 lines | Replaced by `local-dev-setup.sh` | N/A |
| **Local dev setup** | N/A | ~120 lines | New (minimal) |

#### Local Development Workflow (New):
```bash
# Option 1: App Config-based (recommended)
./devops/scripts/azd/helpers/local-dev-setup.sh --minimal
source .env.local
# App fetches config from Azure App Configuration at runtime

# Option 2: Legacy full .env (fallback)
./devops/scripts/azd/helpers/local-dev-setup.sh --legacy
source .env.legacy
```

#### Migration Path:
1. **New deployments**: Use `postprovision-simplified.sh` 
2. **Existing deployments**: Keep using `postprovision.sh` (still works)
3. **Gradual transition**: Switch when ready, no breaking changes

### Phase 4: Dynamic Configuration ✅ COMPLETE
- [x] Add App Config Sentinel key for change detection
- [x] Implement `ConfigurationRefreshManager` for sentinel monitoring
- [x] Add `start_dynamic_refresh()` / `stop_dynamic_refresh()` functions
- [x] Add `on_config_refresh()` callback registration
- [x] Add Terraform sentinel key with `ignore_changes` lifecycle
- [ ] A/B testing with percentage-based rollouts (future enhancement)

#### Environment Variables for Dynamic Refresh:
| Variable | Default | Description |
|----------|---------|-------------|
| `APPCONFIG_ENABLE_DYNAMIC_REFRESH` | `false` | Enable/disable dynamic refresh |
| `APPCONFIG_REFRESH_INTERVAL_SECONDS` | `30` | How often to check sentinel |
| `APPCONFIG_SENTINEL_KEY` | `app/sentinel` | Key to monitor for changes |

#### Usage:
```python
from config import (
    start_dynamic_refresh,
    stop_dynamic_refresh,
    on_config_refresh,
)

# Register callback for config changes
def handle_config_change():
    print("Configuration changed!")
    # Reinitialize components that depend on config
    
on_config_refresh(handle_config_change)

# Start monitoring (requires APPCONFIG_ENABLE_DYNAMIC_REFRESH=true)
start_dynamic_refresh()

# In shutdown
stop_dynamic_refresh()
```

#### Trigger Config Refresh (CLI):
```bash
# Update sentinel to trigger refresh in all running apps
az appconfig kv set \
  --endpoint $AZURE_APPCONFIG_ENDPOINT \
  --key app/sentinel \
  --value "v$(date +%s)" \
  --label dev
```

---

## ✅ Implementation Status

| Phase | Status | Effort | Notes |
|-------|--------|--------|-------|
| Phase 1: Terraform Module | ✅ Complete | 3 hours | 6 files, validated |
| Phase 2: Python SDK | ✅ Complete | 2 hours | Provider + health endpoints |
| Phase 3: Script Simplification | ✅ Complete | 1 hour | 50% reduction |
| Phase 4: Dynamic Config | ✅ Complete | 1 hour | Sentinel-based refresh |
| Phase 5: Eliminate azd env vars | ✅ Complete | 1 hour | App Config as primary source |

**Total Effort: ~8 hours**

---

## 🔄 Phase 5: Postprovision Refactoring (App Config as Primary Source)

### Goals
- Eliminate redundant azd env var lookups for values already in App Config
- Remove Container App environment variable patching (apps read from App Config)
- Update URLs in App Config instead of patching containers
- Deprecate `generate-env.sh` in favor of `local-dev-setup.sh`

### Changes Made

#### New Terraform Keys
Added to `infra/terraform/modules/appconfig/keys.tf`:
- `app/backend/base-url` - Backend's public URL
- `app/frontend/backend-url` - Frontend's reference to backend
- `app/frontend/ws-url` - WebSocket URL for frontend

All use `lifecycle { ignore_changes = [value] }` since they're updated by postprovision.

#### New `postprovision-v2.sh`
Ultra-simplified script (~200 lines vs ~400 lines original):

**What it does:**
1. **Cosmos DB init** - One-time data seeding (unchanged)
2. **Phone number config** - Interactive/CI provisioning (unchanged)
3. **App Config URL updates** - Sets URL keys + triggers sentinel refresh

**What it removes:**
- ❌ Container App env var patching (`az containerapp update --set-env-vars`)
- ❌ Environment file generation (`generate-env.sh`)
- ❌ Multiple `get_azd_env_value` calls for config values

#### URL Update Flow (New)
```
Before: postprovision → az containerapp update → restart containers
After:  postprovision → az appconfig kv set → sentinel update → apps refresh
```

No container restart required! Apps pick up new URLs via dynamic refresh.

### File Summary

| File | Action | Purpose |
|------|--------|---------|
| `postprovision-v2.sh` | Created | New simplified script |
| `postprovision.sh` | Unchanged | Legacy, backwards compatible |
| `postprovision-simplified.sh` | Unchanged | Phase 3 version |
| `keys.tf` | Updated | Added URL keys |
| `variables.tf` | Updated | Added `backend_base_url` variable |

### Migration Path

**For new deployments:**
```bash
# Rename or symlink to use v2
mv devops/scripts/azd/postprovision.sh devops/scripts/azd/postprovision-legacy.sh
ln -s postprovision-v2.sh devops/scripts/azd/postprovision.sh
```

**For existing deployments:**
- Keep using `postprovision.sh` (still works)
- Test `postprovision-v2.sh` in dev first
- Switch when comfortable

### Comparison: Script Complexity

| Metric | Original | v2 | Reduction |
|--------|----------|----|-----------| 
| Lines of code | ~400 | ~200 | 50% |
| `get_azd_env_value` calls | ~25 | ~8 | 68% |
| `az containerapp update` calls | 3 | 0 | 100% |
| Container restarts | 2 | 0 | 100% |

---

## 🚀 Deployment Instructions

### First-Time Deployment
```bash
# 1. Deploy infrastructure (creates App Config)
azd provision

# 2. Post-provisioning runs automatically
#    - Cosmos DB init
#    - Phone number config (optional)
#    - URL patching

# 3. Verify App Config
az appconfig kv list --endpoint $(azd env get-value AZURE_APPCONFIG_ENDPOINT)
```

### Local Development
```bash
# Setup local environment (minimal - recommended)
./devops/scripts/azd/helpers/local-dev-setup.sh --minimal
source .env.local

# App connects to App Config via DefaultAzureCredential
python -m uvicorn apps.artagent.backend.main:app --reload
```

### Verify Integration
```bash
# Check App Config status
curl http://localhost:8080/api/v1/health/appconfig

# Force cache refresh
curl -X POST http://localhost:8080/api/v1/health/appconfig/refresh
```

