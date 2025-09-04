"""
services/redis_services.py
--------------------------
Re-export thin wrappers around Azure Redis that your code already
implements in `src.redis.*`. Keeping them here isolates the rest of
the app from the direct SDK dependency.
"""

from src.redis.manager import AzureRedisManager

__all__ = [
    "AzureRedisManager",
]
