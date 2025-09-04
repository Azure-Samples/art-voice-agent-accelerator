import json
import os
from typing import Any, Dict, List, Optional, Union

import redis.asyncio as redis
from utils.ml_logging import get_logger

from .key_manager import Component, DataType, RedisKeyManager


class AsyncAzureRedisManager:
    """
    Enhanced Azure Redis Manager with hierarchical key management and TTL optimization.

    Integrates with RedisKeyManager for consistent key structure across multi-worker
    Voice AI environments. Provides automatic TTL management, worker affinity tracking,
    and efficient bulk operations following Azure Well-Architected Framework principles.

    Key Features:
    - Hierarchical key structure with environment isolation
    - Automatic TTL management per data type
    - Worker affinity tracking for WebSocket sessions
    - Bulk operations for cleanup and monitoring
    - Legacy key migration support
    """

    def __init__(
        self,
        host: Optional[str] = None,
        access_key: Optional[str] = None,
        port: int = None,
        ssl: bool = True,
        credential: Optional[object] = None,  # For DefaultAzureCredential
        user_name: Optional[str] = None,
        scope: Optional[str] = None,
        default_ttl: int = 900,  # Default TTL: 15 minutes (900 seconds)
        environment: Optional[str] = None,  # Environment for key manager
    ):
        self.logger = get_logger(__name__)
        self.default_ttl = default_ttl  # Store default TTL
        self.key_manager = RedisKeyManager(environment)  # Initialize key manager
        self.host = host or os.getenv("REDIS_HOST")
        self.access_key = access_key or os.getenv("REDIS_ACCESS_KEY")
        self.port = port or os.getenv("REDIS_PORT")
        self.ssl = ssl
        if not self.host:
            raise ValueError(
                "Redis host must be provided either as argument or environment variable."
            )

        if ":" in self.host:
            self.host, port = self.host.rsplit(":", 1)
            if port.isdigit():
                self.port = int(port)

        if self.access_key:
            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.access_key,
                ssl=self.ssl,
                decode_responses=True,
            )
            self.logger.info(
                "Azure Redis async connection initialized with access key."
            )
        else:
            from utils.azure_auth import get_credential

            cred = credential or get_credential()
            scope = scope or os.getenv(
                "REDIS_SCOPE", "https://redis.azure.com/.default"
            )
            user_name = user_name or os.getenv("REDIS_USER_NAME", "user")
            token = cred.get_token(scope)

            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                ssl=self.ssl,
                username=user_name,
                password=token.token,
                decode_responses=True,
            )
            self.logger.info(
                "Azure Redis async connection initialized with DefaultAzureCredential."
            )

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        return await self.redis_client.ping()

    async def set_value(
        self, key: str, value: str, ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Set a string value in Redis with optional TTL.
        Uses default_ttl if ttl_seconds not specified and default_ttl > 0.
        Maintains backwards compatibility - if no TTL specified and default_ttl is 0, no TTL is set.
        """
        if ttl_seconds is None and self.default_ttl > 0:
            return await self.redis_client.setex(key, self.default_ttl, value)
        elif ttl_seconds is not None:
            return await self.redis_client.setex(key, ttl_seconds, value)
        else:
            return await self.redis_client.set(key, value)

    async def get_value(self, key: str) -> Optional[str]:
        """Get a string value from Redis."""
        value = await self.redis_client.get(key)
        return value if value else None

    async def store_session_data(
        self, session_id: str, data: Dict[str, Any], ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Store session data using a Redis hash.
        Uses default_ttl if ttl_seconds not specified and default_ttl > 0.
        Maintains backwards compatibility - if no TTL specified and default_ttl is 0, no TTL is set.
        """
        result = await self.redis_client.hset(session_id, mapping=data)

        # Apply TTL logic: use provided ttl_seconds, fallback to default_ttl, or no TTL
        if ttl_seconds is not None:
            await self.redis_client.expire(session_id, ttl_seconds)
        elif self.default_ttl > 0:
            await self.redis_client.expire(session_id, self.default_ttl)

        return result

    async def get_session_data(self, session_id: str) -> Dict[str, str]:
        """Retrieve all session data for a given session ID."""
        data = await self.redis_client.hgetall(session_id)
        return {k: v for k, v in data.items()}

    async def update_session_field(
        self, session_id: str, field: str, value: str, extend_ttl: bool = True
    ) -> bool:
        """
        Update a single field in the session hash.

        Args:
            session_id: The session ID
            field: The field name to update
            value: The new value
            extend_ttl: If True, resets TTL to default_ttl (keeps session alive)

        Returns:
            bool: True if successful
        """
        result = await self.redis_client.hset(session_id, field, value)

        # Optionally extend TTL on updates to keep session alive
        if extend_ttl and self.default_ttl > 0:
            await self.redis_client.expire(session_id, self.default_ttl)

        return result

    async def delete_session(self, session_id: str) -> int:
        """Delete a session from Redis."""
        return await self.redis_client.delete(session_id)

    async def list_connected_clients(self) -> List[Dict[str, str]]:
        """List currently connected clients."""
        return await self.redis_client.client_list()

    async def get_ttl(self, key: str) -> int:
        """
        Get the TTL (time to live) of a key in seconds.

        Returns:
            int: TTL in seconds, -1 if key has no TTL, -2 if key doesn't exist
        """
        return await self.redis_client.ttl(key)

    async def set_ttl(self, key: str, ttl_seconds: Optional[int] = None) -> bool:
        """
        Set TTL for an existing key.

        Args:
            key: The key to set TTL for
            ttl_seconds: TTL in seconds, uses default_ttl if None

        Returns:
            bool: True if TTL was set, False if key doesn't exist
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        return await self.redis_client.expire(key, ttl)

    async def refresh_session_ttl(self, session_id: str) -> bool:
        """
        Refresh the TTL of a session to keep it alive.
        Uses the default_ttl value.

        Returns:
            bool: True if TTL was refreshed, False if session doesn't exist
        """
        if self.default_ttl > 0:
            return await self.redis_client.expire(session_id, self.default_ttl)
        return False
