from opentelemetry import trace
from opentelemetry.trace import SpanKind
import asyncio
import os
import threading
import time
from typing import Any, Dict, List, Optional

from utils.azure_auth import get_credential

import redis
from redis.exceptions import AuthenticationError
from utils.ml_logging import get_logger


class AzureRedisManager:
    """
    AzureRedisManager provides a simplified interface to connect, store,
    retrieve, and manage session data using Azure Cache for Redis.
    """

    @property
    def is_connected(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            return self.ping()
        except Exception as e:
            self.logger.error("Redis connection check failed: %s", e)
            return False

    def __init__(
        self,
        host: Optional[str] = None,
        access_key: Optional[str] = None,
        port: Optional[int] = None,
        db: int = 0,
        ssl: bool = True,
        credential: Optional[object] = None,  # For DefaultAzureCredential
        user_name: Optional[str] = None,
        scope: Optional[str] = None,
    ):
        """
        Initialize the Redis connection.
        """
        self.logger = get_logger(__name__)
        self.host = host or os.getenv("REDIS_HOST")
        self.access_key = access_key or os.getenv("REDIS_ACCESS_KEY")
        self.port = (
            port if isinstance(port, int) else int(os.getenv("REDIS_PORT", port))
        )
        self.db = db
        self.ssl = ssl
        self.tracer = trace.get_tracer(__name__)
        if not self.host:
            raise ValueError(
                "Redis host must be provided either as argument or environment variable."
            )
        if ":" in self.host:
            host_parts = self.host.rsplit(":", 1)
            if host_parts[1].isdigit():
                self.host = host_parts[0]
                self.port = int(host_parts[1])

        # AAD credential details
        self.credential = credential or get_credential()
        self.scope = (
            scope or os.getenv("REDIS_SCOPE") or "https://redis.azure.com/.default"
        )
        self.user_name = user_name or os.getenv("REDIS_USER_NAME") or "user"
        self._auth_expires_at = 0  # For AAD token refresh tracking

        # Build initial client and, if using AAD, start a refresh thread
        self._create_client()
        if not self.access_key:
            t = threading.Thread(target=self._refresh_loop, daemon=True)
            t.start()

    async def initialize(self) -> None:
        """
        Async initialization method for FastAPI lifespan compatibility.

        Validates Redis connectivity and ensures proper initialization.
        This method is idempotent and can be called multiple times safely.
        """
        try:
            self.logger.info(f"Validating Redis connection to {self.host}:{self.port}")

            # Validate connection with health check
            loop = asyncio.get_event_loop()
            ping_result = await loop.run_in_executor(None, self._health_check)

            if ping_result:
                self.logger.info("✅ Redis connection validated successfully")
            else:
                raise ConnectionError("Redis health check failed")

        except Exception as e:
            self.logger.error(f"Redis initialization failed: {e}")
            raise ConnectionError(f"Failed to initialize Redis: {e}")

    def _health_check(self) -> bool:
        """
        Perform comprehensive health check on Redis connection.
        """
        try:
            # Basic connectivity test
            if not self.redis_client.ping():
                return False

            # Test basic operations
            test_key = "health_check_test"
            self.redis_client.set(test_key, "test_value", ex=5)
            result = self.redis_client.get(test_key)
            self.redis_client.delete(test_key)

            return result == "test_value"

        except Exception as e:
            self.logger.error(f"Redis health check failed: {e}")
            return False

    def _redis_span(self, name: str, op: str | None = None):
        host = (self.host or "").split(":")[0]
        return self.tracer.start_as_current_span(
            name,
            kind=SpanKind.CLIENT,
            attributes={
                "peer.service": "azure-managed-redis",
                "server.address": host,
                "server.port": self.port or 6380,
                "db.system": "redis",
                **({"db.operation": op} if op else {}),
            },
        )

    def _create_client(self):
        """(Re)create self.redis_client and record expiry for AAD."""
        if self.access_key:
            # static key-based auth
            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.access_key,
                ssl=self.ssl,
                decode_responses=True,
                socket_keepalive=True,
                health_check_interval=30,
                socket_connect_timeout=0.2,
                socket_timeout=1.0,
                max_connections=200,
                client_name="rtagent-api",
            )
            self.logger.info("Azure Redis connection initialized with access key.")
        else:
            # get fresh AAD token
            token = self.credential.get_token(self.scope)
            self.token_expiry = token.expires_on
            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                username=self.user_name,
                password=token.token,
                ssl=self.ssl,
                decode_responses=True,
            )
            self.logger.info(
                "Azure Redis connection initialized with AAD token (expires at %s).",
                self.token_expiry,
            )

    def _refresh_loop(self):
        """Background thread: sleep until just before expiry, then refresh token."""
        while True:
            now = int(time.time())
            # sleep until 60s before expiry
            wait = max(self.token_expiry - now - 60, 1)
            time.sleep(wait)
            try:
                self.logger.debug("Refreshing Azure Redis AAD token in background...")
                self._create_client()
            except Exception as e:
                self.logger.error("Failed to refresh Redis token: %s", e)
                # retry sooner if something goes wrong
                time.sleep(5)

    def publish_event(self, stream_key: str, event_data: Dict[str, Any]) -> str:
        """Append an event to a Redis stream."""
        with self._redis_span("Redis.XADD"):
            return self.redis_client.xadd(stream_key, event_data)

    def read_events_blocking(
        self,
        stream_key: str,
        last_id: str = "$",
        block_ms: int = 30000,
        count: int = 1,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Block and read new events from a Redis stream starting after `last_id`.
        Returns list of new events (or None on timeout).
        """
        with self._redis_span("Redis.XREAD"):
            streams = self.redis_client.xread(
                {stream_key: last_id}, block=block_ms, count=count
            )
            return streams if streams else None

    async def publish_event_async(
        self, stream_key: str, event_data: Dict[str, Any]
    ) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.publish_event, stream_key, event_data
        )

    async def read_events_blocking_async(
        self,
        stream_key: str,
        last_id: str = "$",
        block_ms: int = 30000,
        count: int = 1,
    ) -> Optional[List[Dict[str, Any]]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.read_events_blocking, stream_key, last_id, block_ms, count
        )

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            with self._redis_span("Redis.PING"):
                return self.redis_client.ping()
        except AuthenticationError:
            # token might have expired early: rebuild & retry once
            self.logger.info("Redis auth error on ping, refreshing token")
            self._create_client()
            with self._redis_span("Redis.PING"):
                return self.redis_client.ping()

    def set_value(
        self, key: str, value: str, ttl_seconds: Optional[int] = None
    ) -> bool:
        """Set a string value in Redis (optionally with TTL)."""
        with self._redis_span("Redis.SET"):
            if ttl_seconds is not None:
                return self.redis_client.setex(key, ttl_seconds, str(value))
            return self.redis_client.set(key, str(value))

    def get_value(self, key: str) -> Optional[str]:
        """Get a string value from Redis."""
        with self._redis_span("Redis.GET"):
            value = self.redis_client.get(key)
            return value.decode() if isinstance(value, bytes) else value

    def store_session_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Store session data using a Redis hash."""
        with self._redis_span("Redis.HSET"):
            return bool(self.redis_client.hset(session_id, mapping=data))

    def get_session_data(self, session_id: str) -> Dict[str, str]:
        """Retrieve all session data for a given session ID."""
        with self._redis_span("Redis.HGETALL"):
            raw = self.redis_client.hgetall(session_id)
            return dict(raw)

    def update_session_field(self, session_id: str, field: str, value: str) -> bool:
        """Update a single field in the session hash."""
        with self._redis_span("Redis.HSET"):
            return bool(self.redis_client.hset(session_id, field, value))

    def delete_session(self, session_id: str) -> int:
        """Delete a session from Redis."""
        with self._redis_span("Redis.DEL"):
            return self.redis_client.delete(session_id)

    def list_connected_clients(self) -> List[Dict[str, str]]:
        """List currently connected clients."""
        with self._redis_span("Redis.CLIENTLIST"):
            return self.redis_client.client_list()

    async def store_session_data_async(
        self, session_id: str, data: Dict[str, Any]
    ) -> bool:
        """Async version using thread pool executor."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.store_session_data, session_id, data
            )
        except asyncio.CancelledError:
            self.logger.debug(
                f"store_session_data_async cancelled for session {session_id}"
            )
            # Don't log as warning - cancellation is normal during shutdown
            raise
        except Exception as e:
            self.logger.error(
                f"Error in store_session_data_async for session {session_id}: {e}"
            )
            return False

    async def get_session_data_async(self, session_id: str) -> Dict[str, str]:
        """Async version of get_session_data using thread pool executor."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.get_session_data, session_id)
        except asyncio.CancelledError:
            self.logger.debug(
                f"get_session_data_async cancelled for session {session_id}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"Error in get_session_data_async for session {session_id}: {e}"
            )
            return {}

    async def update_session_field_async(
        self, session_id: str, field: str, value: str
    ) -> bool:
        """Async version of update_session_field using thread pool executor."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.update_session_field, session_id, field, value
            )
        except asyncio.CancelledError:
            self.logger.debug(
                f"update_session_field_async cancelled for session {session_id}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"Error in update_session_field_async for session {session_id}: {e}"
            )
            return False

    async def delete_session_async(self, session_id: str) -> int:
        """Async version of delete_session using thread pool executor."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.delete_session, session_id)
        except asyncio.CancelledError:
            self.logger.debug(
                f"delete_session_async cancelled for session {session_id}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"Error in delete_session_async for session {session_id}: {e}"
            )
            return 0

    async def get_value_async(self, key: str) -> Optional[str]:
        """Async version of get_value using thread pool executor."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.get_value, key)
        except asyncio.CancelledError:
            self.logger.debug(f"get_value_async cancelled for key {key}")
            raise
        except Exception as e:
            self.logger.error(f"Error in get_value_async for key {key}: {e}")
            return None

    async def set_value_async(
        self, key: str, value: str, ttl_seconds: Optional[int] = None
    ) -> bool:
        """Async version of set_value using thread pool executor."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.set_value, key, value, ttl_seconds
            )
        except asyncio.CancelledError:
            self.logger.debug(f"set_value_async cancelled for key {key}")
            raise
        except Exception as e:
            self.logger.error(f"Error in set_value_async for key {key}: {e}")
            return False
