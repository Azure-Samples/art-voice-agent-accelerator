"""
Enums package for the voice agent system.

This package contains various enumerations used throughout the application
for consistent type safety and value validation.
"""

from .monitoring import SpanAttr
from .stream_modes import StreamMode

__all__ = [
    "SpanAttr",
    "StreamMode",
]
