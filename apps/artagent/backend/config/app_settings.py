"""
Application Settings (DEPRECATED)
=================================

This file is deprecated. Import from config or config.settings instead.

Migration:
    # Old
    from config.app_settings import POOL_SIZE_TTS

    # New
    from config import POOL_SIZE_TTS
"""

# Re-export everything from settings for backward compatibility
from .settings import *
