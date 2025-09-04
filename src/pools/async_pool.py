import asyncio
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, TypeVar

from utils.ml_logging import get_logger

logger = get_logger("async_pool")

T = TypeVar("T")


class AsyncPool:
    """
    Asynchronous resource pool for managing expensive-to-create client instances.

    This class provides a thread-safe pool of reusable resources backed by asyncio.Queue.
    It is designed for managing expensive-but-reusable clients such as STT/TTS services,
    database connections, or other resources that benefit from connection pooling.

    :param factory: Factory function that creates new instances of type T asynchronously.
    :param size: Maximum number of items to maintain in the pool.
    :return: An initialized AsyncPool instance ready for resource management.
    :raises TypeError: If factory is not a callable or size is not a positive integer.
    """

    def __init__(self, factory: Callable[[], Awaitable[T]], size: int):
        """
        Initialize the asynchronous resource pool with specified factory and size.

        This constructor sets up the internal queue and synchronization primitives
        required for managing the pool of resources. The pool starts empty and
        must be prepared before use.

        :param factory: Async factory function to create new resource instances.
        :param size: Maximum number of resources to maintain in the pool.
        :return: None.
        :raises ValueError: If size is less than or equal to zero.
        :raises TypeError: If factory is not callable.
        """
        if not callable(factory):
            logger.error("Factory must be a callable function")
            raise TypeError("Factory must be a callable function")

        if size <= 0:
            logger.error(f"Pool size must be positive, got: {size}")
            raise ValueError("Pool size must be positive")

        logger.info(f"Initializing AsyncPool with size: {size}")
        self._factory = factory
        self._size = size
        self._q: asyncio.Queue[T] = asyncio.Queue(maxsize=size)
        self._ready = asyncio.Event()

    async def prepare(self) -> None:
        """
        Pre-populate the pool with the specified number of resource instances.

        This method creates all pool resources upfront to avoid creation overhead
        during runtime. It should be called once during application startup.
        Subsequent calls to this method are safe and will be ignored.

        :param: None.
        :return: None.
        :raises Exception: If any resource creation fails during pool preparation.
        """
        if self._ready.is_set():
            logger.debug("Pool already prepared, skipping initialization")
            return

        try:
            logger.info(f"Preparing pool with {self._size} resources")
            for i in range(self._size):
                logger.debug(f"Creating resource {i+1}/{self._size}")
                item = await self._factory()
                await self._q.put(item)

            self._ready.set()
            logger.info("Pool preparation completed successfully")
        except Exception as e:
            logger.error(f"Failed to prepare pool: {e}")
            raise

    async def acquire(self, timeout: float | None = None) -> T:
        """
        Acquire a resource from the pool with optional timeout.

        This method retrieves an available resource from the pool. If no resources
        are immediately available, it will wait until one becomes available or
        the timeout expires.

        :param timeout: Maximum time to wait for a resource in seconds. None means wait indefinitely.
        :return: A resource instance of type T from the pool.
        :raises TimeoutError: If timeout expires before a resource becomes available.
        :raises RuntimeError: If the pool has not been prepared yet.
        """
        if not self._ready.is_set():
            logger.error("Attempted to acquire from unprepared pool")
            raise RuntimeError("Pool must be prepared before acquiring resources")

        try:
            if timeout is None:
                logger.debug("Acquiring resource from pool (no timeout)")
                return await self._q.get()
            else:
                logger.debug(f"Acquiring resource from pool (timeout: {timeout}s)")
                return await asyncio.wait_for(self._q.get(), timeout=timeout)
        except asyncio.TimeoutError as e:
            logger.warning(f"Resource acquisition timed out after {timeout}s")
            raise TimeoutError("Pool acquire timeout") from e

    async def release(self, item: T) -> None:
        """
        Return a resource to the pool for reuse by other consumers.

        This method puts a resource back into the pool, making it available
        for future acquisition. Resources should be returned in a clean,
        reusable state.

        :param item: The resource instance to return to the pool.
        :return: None.
        :raises ValueError: If item is None or invalid.
        """
        if item is None:
            logger.error("Cannot release None item to pool")
            raise ValueError("Cannot release None item to pool")

        try:
            logger.debug("Releasing resource back to pool")
            await self._q.put(item)
        except Exception as e:
            logger.error(f"Failed to release resource to pool: {e}")
            raise

    @asynccontextmanager
    async def lease(self, timeout: float | None = None):
        """
        Context manager for automatic resource acquisition and release.

        This method provides a convenient way to acquire a resource, use it
        within a context, and automatically return it to the pool when done.
        This ensures proper cleanup even if exceptions occur.

        :param timeout: Maximum time to wait for resource acquisition in seconds.
        :return: A context manager yielding a resource instance.
        :raises TimeoutError: If resource acquisition times out.
        :raises RuntimeError: If the pool has not been prepared yet.
        """
        logger.debug("Starting resource lease context")
        item = await self.acquire(timeout=timeout)
        try:
            logger.debug("Resource acquired, yielding to context")
            yield item
        finally:
            logger.debug("Resource lease context ending, releasing resource")
            await self.release(item)
