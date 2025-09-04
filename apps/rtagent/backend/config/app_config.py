"""
Application Configuration Objects
=================================

Structured configuration objects using dataclasses for the real-time voice agent.
Provides type-safe access to configuration with validation and easy serialization.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from .connection_config import (
    POOL_SIZE_TTS,
    POOL_SIZE_STT,
    POOL_LOW_WATER_MARK,
    POOL_HIGH_WATER_MARK,
    POOL_ACQUIRE_TIMEOUT,
    MAX_WEBSOCKET_CONNECTIONS,
    CONNECTION_QUEUE_SIZE,
    ENABLE_CONNECTION_LIMITS,
    CONNECTION_WARNING_THRESHOLD,
    CONNECTION_CRITICAL_THRESHOLD,
    CONNECTION_TIMEOUT_SECONDS,
    SESSION_TTL_SECONDS,
    SESSION_CLEANUP_INTERVAL,
    MAX_CONCURRENT_SESSIONS,
    ENABLE_SESSION_PERSISTENCE,
    SESSION_STATE_TTL,
)
from .voice_config import (
    GREETING_VOICE_TTS,
    DEFAULT_VOICE_STYLE,
    DEFAULT_VOICE_RATE,
    TTS_SAMPLE_RATE_UI,
    TTS_SAMPLE_RATE_ACS,
    TTS_CHUNK_SIZE,
    TTS_PROCESSING_TIMEOUT,
    STT_PROCESSING_TIMEOUT,
)
from .feature_flags import (
    ENABLE_PERFORMANCE_LOGGING,
    ENABLE_TRACING,
    METRICS_COLLECTION_INTERVAL,
    POOL_METRICS_INTERVAL,
    DTMF_VALIDATION_ENABLED,
    ENABLE_AUTH_VALIDATION,
)
from .security_config import (
    ALLOWED_ORIGINS,
    ENTRA_EXEMPT_PATHS,
)
from .ai_config import (
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    AOAI_REQUEST_TIMEOUT,
)


@dataclass
class SpeechPoolConfig:
    """Configuration for speech service pools."""

    tts_pool_size: int = POOL_SIZE_TTS
    stt_pool_size: int = POOL_SIZE_STT
    low_water_mark: int = POOL_LOW_WATER_MARK
    high_water_mark: int = POOL_HIGH_WATER_MARK
    acquire_timeout: float = POOL_ACQUIRE_TIMEOUT
    stt_timeout: float = STT_PROCESSING_TIMEOUT
    tts_timeout: float = TTS_PROCESSING_TIMEOUT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tts_pool_size": self.tts_pool_size,
            "stt_pool_size": self.stt_pool_size,
            "low_water_mark": self.low_water_mark,
            "high_water_mark": self.high_water_mark,
            "acquire_timeout": self.acquire_timeout,
            "stt_timeout": self.stt_timeout,
            "tts_timeout": self.tts_timeout,
        }


@dataclass
class ConnectionConfig:
    """Configuration for WebSocket connection management."""

    max_connections: int = MAX_WEBSOCKET_CONNECTIONS
    queue_size: int = CONNECTION_QUEUE_SIZE
    enable_limits: bool = ENABLE_CONNECTION_LIMITS
    warning_threshold: int = CONNECTION_WARNING_THRESHOLD
    critical_threshold: int = CONNECTION_CRITICAL_THRESHOLD
    timeout_seconds: float = CONNECTION_TIMEOUT_SECONDS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_connections": self.max_connections,
            "queue_size": self.queue_size,
            "enable_limits": self.enable_limits,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class SessionConfig:
    """Configuration for session management."""

    ttl_seconds: int = SESSION_TTL_SECONDS
    cleanup_interval: int = SESSION_CLEANUP_INTERVAL
    max_concurrent_sessions: int = MAX_CONCURRENT_SESSIONS
    enable_persistence: bool = ENABLE_SESSION_PERSISTENCE
    state_ttl: int = SESSION_STATE_TTL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ttl_seconds": self.ttl_seconds,
            "cleanup_interval": self.cleanup_interval,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "enable_persistence": self.enable_persistence,
            "state_ttl": self.state_ttl,
        }


@dataclass
class VoiceConfig:
    """Configuration for voice and TTS settings."""

    default_voice: str = GREETING_VOICE_TTS
    default_style: str = DEFAULT_VOICE_STYLE
    default_rate: str = DEFAULT_VOICE_RATE
    sample_rate_ui: int = TTS_SAMPLE_RATE_UI
    sample_rate_acs: int = TTS_SAMPLE_RATE_ACS
    chunk_size: int = TTS_CHUNK_SIZE
    processing_timeout: float = TTS_PROCESSING_TIMEOUT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_voice": self.default_voice,
            "default_style": self.default_style,
            "default_rate": self.default_rate,
            "sample_rate_ui": self.sample_rate_ui,
            "sample_rate_acs": self.sample_rate_acs,
            "chunk_size": self.chunk_size,
            "processing_timeout": self.processing_timeout,
        }


@dataclass
class AIConfig:
    """Configuration for AI processing."""

    request_timeout: float = AOAI_REQUEST_TIMEOUT
    default_temperature: float = DEFAULT_TEMPERATURE
    default_max_tokens: int = DEFAULT_MAX_TOKENS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_timeout": self.request_timeout,
            "default_temperature": self.default_temperature,
            "default_max_tokens": self.default_max_tokens,
        }


@dataclass
class MonitoringConfig:
    """Configuration for monitoring and observability."""

    metrics_interval: int = METRICS_COLLECTION_INTERVAL
    pool_metrics_interval: int = POOL_METRICS_INTERVAL
    enable_performance_logging: bool = ENABLE_PERFORMANCE_LOGGING
    enable_tracing: bool = ENABLE_TRACING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics_interval": self.metrics_interval,
            "pool_metrics_interval": self.pool_metrics_interval,
            "enable_performance_logging": self.enable_performance_logging,
            "enable_tracing": self.enable_tracing,
        }


@dataclass
class SecurityConfig:
    """Configuration for security and authentication."""

    enable_auth_validation: bool = ENABLE_AUTH_VALIDATION
    allowed_origins: List[str] = field(default_factory=lambda: ALLOWED_ORIGINS.copy())
    exempt_paths: List[str] = field(default_factory=lambda: ENTRA_EXEMPT_PATHS.copy())
    enable_dtmf_validation: bool = DTMF_VALIDATION_ENABLED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enable_auth_validation": self.enable_auth_validation,
            "allowed_origins": self.allowed_origins,
            "exempt_paths": self.exempt_paths,
            "enable_dtmf_validation": self.enable_dtmf_validation,
        }


@dataclass
class AppConfig:
    """Complete application configuration."""

    speech_pools: SpeechPoolConfig = field(default_factory=SpeechPoolConfig)
    connections: ConnectionConfig = field(default_factory=ConnectionConfig)
    sessions: SessionConfig = field(default_factory=SessionConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization."""
        return {
            "speech_pools": self.speech_pools.to_dict(),
            "connections": self.connections.to_dict(),
            "sessions": self.sessions.to_dict(),
            "voice": self.voice.to_dict(),
            "ai": self.ai.to_dict(),
            "monitoring": self.monitoring.to_dict(),
            "security": self.security.to_dict(),
        }

    def validate(self) -> Dict[str, Any]:
        """Validate configuration and return validation results."""
        issues = []
        warnings = []

        # Validate speech pools
        if self.speech_pools.tts_pool_size < 1:
            issues.append("TTS pool size must be at least 1")
        elif self.speech_pools.tts_pool_size < 10:
            warnings.append(
                f"TTS pool size ({self.speech_pools.tts_pool_size}) is quite low"
            )

        if self.speech_pools.stt_pool_size < 1:
            issues.append("STT pool size must be at least 1")
        elif self.speech_pools.stt_pool_size < 10:
            warnings.append(
                f"STT pool size ({self.speech_pools.stt_pool_size}) is quite low"
            )

        # Validate connections
        if self.connections.max_connections < 1:
            issues.append("Max connections must be at least 1")
        elif self.connections.max_connections > 1000:
            warnings.append(
                f"Max connections ({self.connections.max_connections}) is very high"
            )

        # Validate pool capacity vs connections
        total_pool_capacity = (
            self.speech_pools.tts_pool_size + self.speech_pools.stt_pool_size
        )
        if self.connections.max_connections > total_pool_capacity:
            warnings.append(
                f"Connection limit ({self.connections.max_connections}) exceeds total pool capacity ({total_pool_capacity})"
            )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "config_summary": {
                "phase": "Phase 1"
                if self.connections.max_connections <= 200
                else "Phase 2+",
                "tts_pool": self.speech_pools.tts_pool_size,
                "stt_pool": self.speech_pools.stt_pool_size,
                "max_connections": self.connections.max_connections,
                "estimated_capacity": f"{min(self.speech_pools.tts_pool_size, self.speech_pools.stt_pool_size)} concurrent sessions",
            },
        }

    def get_capacity_info(self) -> Dict[str, Any]:
        """Get capacity planning information."""
        return {
            "speech_pools": {
                "tts_capacity": self.speech_pools.tts_pool_size,
                "stt_capacity": self.speech_pools.stt_pool_size,
                "bottleneck": "TTS"
                if self.speech_pools.tts_pool_size < self.speech_pools.stt_pool_size
                else "STT",
                "effective_capacity": min(
                    self.speech_pools.tts_pool_size, self.speech_pools.stt_pool_size
                ),
            },
            "connections": {
                "max_websocket_connections": self.connections.max_connections,
                "queue_size": self.connections.queue_size,
                "limits_enabled": self.connections.enable_limits,
            },
            "phase_assessment": {
                "current_phase": "Phase 1"
                if self.connections.max_connections <= 200
                else "Phase 2+",
                "ready_for_scale": self.connections.max_connections >= 100
                and self.speech_pools.tts_pool_size >= 50,
                "recommendations": self._get_recommendations(),
            },
        }

    def _get_recommendations(self) -> List[str]:
        """Get configuration recommendations."""
        recommendations = []

        if self.speech_pools.tts_pool_size < 50:
            recommendations.append(
                f"Consider increasing TTS pool to 50+ (currently {self.speech_pools.tts_pool_size})"
            )

        if self.speech_pools.stt_pool_size < 50:
            recommendations.append(
                f"Consider increasing STT pool to 50+ (currently {self.speech_pools.stt_pool_size})"
            )

        if self.connections.max_connections < 200:
            recommendations.append(
                f"For Phase 1, consider max connections of 200 (currently {self.connections.max_connections})"
            )

        if not self.connections.enable_limits:
            recommendations.append("Enable connection limits for production deployment")

        if not self.monitoring.enable_tracing:
            recommendations.append("Enable tracing for better observability")

        return recommendations
