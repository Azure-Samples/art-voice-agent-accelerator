"""
Redis Key Manager for ARTAgent Voice AI Backend

Provides centralized, hierarchical key management with format:
{app_prefix}:{environment}:{data_type}:{identifier}:{component}

Examples:
- rtvoice:prod:call:call-connection-id-1234:session (ACS call using call_connection_id)
- rtvoice:prod:conversation:session-id-5678:context (conversation using session_id)
- rtvoice:dev:worker:worker-abc123:affinity (worker using worker_id)
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from utils.ml_logging import get_logger

logger = get_logger(__name__)


class DataType(str, Enum):
    """Data type categories for Redis key organization"""

    CALL = "call"
    CONVERSATION = "conversation"
    WORKER = "worker"
    SYSTEM = "system"
    CACHE = "cache"


class Component(str, Enum):
    """Component types within each data category"""

    # Call components
    SESSION = "session"
    RECORDING = "recording"
    PARTICIPANTS = "participants"
    MEDIA_STREAM = "media_stream"

    # Conversation components
    HISTORY = "history"
    CONTEXT = "context"
    TRANSCRIPT = "transcript"

    # Worker components
    AFFINITY = "affinity"
    HEARTBEAT = "heartbeat"

    # System components
    METRICS = "metrics"
    HEALTH = "health"


@dataclass
class TTLPolicy:
    """TTL policy with validation"""

    default: int
    max: int
    min: int = 60

    def validate(self, ttl: Optional[int] = None) -> int:
        """Return valid TTL within policy bounds"""
        if ttl is None:
            return self.default
        return max(self.min, min(ttl, self.max))


class RedisKeyManager:
    """Centralized Redis key management with hierarchical structure"""

    # TTL Policies (seconds) - simplified
    TTL_POLICIES = {
        DataType.CALL: TTLPolicy(3600, 7200),  # 1-2 hours
        DataType.CONVERSATION: TTLPolicy(1800, 3600),  # 30-60 mins
        DataType.WORKER: TTLPolicy(300, 600),  # 5-10 mins
        DataType.SYSTEM: TTLPolicy(3600, 86400),  # 1-24 hours
        DataType.CACHE: TTLPolicy(300, 1800),  # 5-30 mins
    }

    def __init__(self, environment: Optional[str] = None, app_prefix: str = "rtvoice"):
        self.environment = environment or os.getenv("ENVIRONMENT", "dev")
        self.app_prefix = app_prefix

        # Validate environment
        if self.environment not in ["dev", "test", "staging", "prod"]:
            logger.warning(f"Unknown environment '{self.environment}', using 'dev'")
            self.environment = "dev"

    def build_key(
        self,
        data_type: DataType,
        identifier: str,
        component: Optional[Component] = None,
    ) -> str:
        """Build hierarchical Redis key"""
        # Ensure identifier is always a string
        identifier_str = str(identifier)
        parts = [self.app_prefix, self.environment, data_type.value, identifier_str]
        if component:
            parts.append(component.value)
        return ":".join(parts)

    def get_ttl(self, data_type: DataType, ttl: Optional[int] = None) -> int:
        """Get validated TTL for data type"""
        policy = self.TTL_POLICIES.get(data_type, TTLPolicy(900, 3600))
        return policy.validate(ttl)

    # Simplified key builders
    def call_key(self, call_id: str, component: Component) -> str:
        """
        Build key for ACS call data

        Args:
            call_id: The ACS call connection ID (not a generated UUID)
            component: The specific component (session, recording, participants, etc.)

        Returns:
            Hierarchical key: rtvoice:{env}:call:{call_connection_id}:{component}
        """
        return self.build_key(DataType.CALL, call_id, component)

    def conversation_key(self, session_id: str, component: Component) -> str:
        return self.build_key(DataType.CONVERSATION, session_id, component)

    def worker_key(self, worker_id: str, component: Component) -> str:
        return self.build_key(DataType.WORKER, worker_id, component)

    def system_key(self, name: str, component: Component = Component.METRICS) -> str:
        return self.build_key(DataType.SYSTEM, name, component)

    # Pattern matching
    def get_pattern(self, data_type: DataType, identifier: str = "*") -> str:
        return self.build_key(data_type, identifier)

    # Migration helpers
    def migrate_legacy_key(self, legacy_key: str) -> Optional[str]:
        """Migrate legacy keys to new format"""
        try:
            if legacy_key.startswith("session:"):
                session_id = legacy_key.replace("session:", "")
                return self.conversation_key(session_id, Component.CONTEXT)

            if legacy_key.startswith("call:"):
                parts = legacy_key.split(":")
                if len(parts) >= 3:
                    call_id, component = parts[1], parts[2]
                    component_map = {
                        "recording": Component.RECORDING,
                        "participants": Component.PARTICIPANTS,
                        "media_streaming_status": Component.MEDIA_STREAM,
                        "session": Component.SESSION,
                    }
                    if component in component_map:
                        return self.call_key(call_id, component_map[component])

            if legacy_key.endswith(":hist"):
                conversation_id = legacy_key.replace(":hist", "")
                return self.conversation_key(conversation_id, Component.HISTORY)

        except Exception as e:
            logger.warning(f"Failed to migrate key '{legacy_key}': {e}")

        return None


# Global instance for easy access
_default_manager = None


def get_key_manager(environment: Optional[str] = None) -> RedisKeyManager:
    """Get Redis Key Manager instance (singleton for default environment)"""
    global _default_manager

    if environment is None:
        if _default_manager is None:
            _default_manager = RedisKeyManager()
        return _default_manager

    # Return new instance for different environments
    return RedisKeyManager(environment)
