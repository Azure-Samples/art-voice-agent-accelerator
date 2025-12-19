"""
VoiceLive Settings
==================

Configuration settings for Azure VoiceLive SDK integration.
Canonical location under apps/artagent/backend/voice/voicelive.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_ENV_FILE = _PROJECT_ROOT / ".env"
# Agents are now in apps/artagent/backend/registries/agentstore/
_AGENTSTORE_DIR = Path(__file__).resolve().parents[2] / "registries" / "agentstore"
_LEGACY_AGENT_ROOT = _PROJECT_ROOT / ".azure" / "_legacy" / "agents" / "vlagent"


class VoiceLiveSettings(BaseSettings):
    """Application settings with environment variable loading."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Azure VoiceLive Configuration
    azure_voicelive_endpoint: str = Field(..., description="Azure VoiceLive endpoint URL")
    azure_voicelive_model: str = Field(default="gpt-realtime", description="Model deployment name")
    azure_voicelive_api_key: str | None = Field(
        default=None, description="API key for authentication"
    )
    use_default_credential: bool = Field(
        default=False,
        description="If true, prefer DefaultAzureCredential over API key",
    )

    # Azure AD Authentication (alternative to API key)
    azure_client_id: str | None = Field(default=None, description="Azure AD client ID")
    azure_tenant_id: str | None = Field(default=None, description="Azure AD tenant ID")
    azure_client_secret: str | None = Field(default=None, description="Azure AD client secret")

    # Application Configuration
    start_agent: str = Field(default="Concierge", description="Initial agent to start with")
    agents_dir: str = Field(
        default=str(_AGENTSTORE_DIR),
        description="Directory containing agent YAML files (registries/agentstore)",
    )
    templates_dir: str = Field(
        default=str(_LEGACY_AGENT_ROOT / "templates"),
        description="Directory containing prompt templates",
    )

    # WebSocket Configuration
    ws_max_msg_size: int = Field(default=10 * 1024 * 1024, description="Max WebSocket message size")
    ws_heartbeat: int = Field(default=20, description="WebSocket heartbeat interval (seconds)")
    ws_timeout: int = Field(default=20, description="WebSocket timeout (seconds)")

    # Logging Configuration
    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    log_format: str = Field(
        default="%(asctime)s %(levelname)s %(name)s: %(message)s",
        description="Log message format",
    )

    # Audio Configuration
    enable_audio: bool = Field(default=True, description="Enable audio capture/playback")

    @property
    def agents_path(self) -> Path:
        """Get absolute path to agents directory (registries/agentstore)."""
        base = Path(self.agents_dir).expanduser()
        return base.resolve() if base.is_absolute() else (_AGENTSTORE_DIR / base).resolve()

    @property
    def templates_path(self) -> Path:
        """Get absolute path to templates directory."""
        base = Path(self.templates_dir).expanduser()
        return base.resolve() if base.is_absolute() else (_AGENTSTORE_DIR / base).resolve()

    @property
    def has_api_key_auth(self) -> bool:
        """Check if API key authentication is configured."""
        return bool(self.azure_voicelive_api_key)

    @property
    def has_azure_ad_auth(self) -> bool:
        """Check if Azure AD authentication is configured."""
        return bool(self.azure_client_id)

    def validate_auth(self) -> None:
        """Validate that at least one authentication method is configured."""
        if self.use_default_credential:
            return
        # We allow missing explicit credentials to support managed identity.


@lru_cache(maxsize=1)
def get_settings() -> VoiceLiveSettings:
    """Get or create settings instance (singleton pattern)."""
    settings = VoiceLiveSettings()
    settings.validate_auth()
    return settings


def reload_settings() -> VoiceLiveSettings:
    """Force reload of settings (useful for testing)."""
    get_settings.cache_clear()
    return get_settings()


__all__ = [
    "VoiceLiveSettings",
    "get_settings",
    "reload_settings",
]
