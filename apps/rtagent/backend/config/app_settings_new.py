"""
Application Settings
===================

Main configuration module that consolidates all settings from specialized
configuration modules for easy access throughout the application.
"""

# Import all settings from specialized modules
from .voice_config import *
from .connection_config import *
from .feature_flags import *
from .ai_config import *
from .security_config import *

# ==============================================================================
# VALIDATION FUNCTIONS
# ==============================================================================


def validate_app_settings():
    """
    Validate current application settings and return validation results.

    Returns:
        Dict containing validation status, issues, warnings, and settings count
    """
    issues = []
    warnings = []

    # Check critical pool settings
    if POOL_SIZE_TTS < 1:
        issues.append("POOL_SIZE_TTS must be at least 1")
    elif POOL_SIZE_TTS < 10:
        warnings.append(f"POOL_SIZE_TTS ({POOL_SIZE_TTS}) is quite low for production")

    if POOL_SIZE_STT < 1:
        issues.append("POOL_SIZE_STT must be at least 1")
    elif POOL_SIZE_STT < 10:
        warnings.append(f"POOL_SIZE_STT ({POOL_SIZE_STT}) is quite low for production")

    # Check connection settings
    if MAX_WEBSOCKET_CONNECTIONS < 1:
        issues.append("MAX_WEBSOCKET_CONNECTIONS must be at least 1")
    elif MAX_WEBSOCKET_CONNECTIONS > 1000:
        warnings.append(
            f"MAX_WEBSOCKET_CONNECTIONS ({MAX_WEBSOCKET_CONNECTIONS}) is very high"
        )

    # Check timeout settings
    if CONNECTION_TIMEOUT_SECONDS < 60:
        warnings.append(
            f"CONNECTION_TIMEOUT_SECONDS ({CONNECTION_TIMEOUT_SECONDS}) is quite short"
        )

    # Check voice settings
    if not GREETING_VOICE_TTS:
        issues.append("GREETING_VOICE_TTS is empty")

    # Count all settings from current module
    import sys

    current_module = sys.modules[__name__]
    settings_count = len(
        [
            name
            for name in dir(current_module)
            if name.isupper() and not name.startswith("_")
        ]
    )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "settings_count": settings_count,
    }


if __name__ == "__main__":
    # Quick validation check
    result = validate_app_settings()
    print(f"App Settings Validation: {'✅ VALID' if result['valid'] else '❌ INVALID'}")

    if result["issues"]:
        print("Issues:")
        for issue in result["issues"]:
            print(f"  ❌ {issue}")

    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  ⚠️  {warning}")

    print(f"Total settings: {result['settings_count']}")
