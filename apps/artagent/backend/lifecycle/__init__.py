"""
Lifecycle Management for Voice Agent Application.

This package provides a clean, modular approach to application startup and shutdown.

Usage:
    from lifecycle import LifecycleManager, LifecycleStep

    manager = LifecycleManager()
    manager.add_step("redis", start_redis, stop_redis)
    manager.add_step("speech", start_speech)

    await manager.run_startup()
    # ... app runs ...
    await manager.run_shutdown()
"""

from .manager import LifecycleManager, LifecycleStep
from .steps import (
    register_agents_step,
    register_aoai_step,
    register_core_state_step,
    register_event_handlers_step,
    register_external_services_step,
    register_speech_pools_step,
    register_warmup_step,
)

__all__ = [
    "LifecycleManager",
    "LifecycleStep",
    "register_core_state_step",
    "register_speech_pools_step",
    "register_aoai_step",
    "register_warmup_step",
    "register_external_services_step",
    "register_agents_step",
    "register_event_handlers_step",
]
