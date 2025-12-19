"""
Resource pool implementations for managing Azure service connections.

Exports:
- WarmableResourcePool: Primary pool with optional pre-warming and session awareness
- AllocationTier: Enum indicating resource allocation tier (DEDICATED/WARM/COLD)
- OnDemandResourcePool: Legacy alias for WarmableResourcePool (for backward compatibility)
"""

from src.pools.on_demand_pool import AllocationTier, OnDemandResourcePool
from src.pools.warmable_pool import WarmableResourcePool

__all__ = [
    "AllocationTier",
    "OnDemandResourcePool",
    "WarmableResourcePool",
]
