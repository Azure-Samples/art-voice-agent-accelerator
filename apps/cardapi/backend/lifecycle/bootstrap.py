"""
Bootstrap - Environment and configuration loading.

Handles the early-stage initialization that must happen before
any other modules are imported:
1. Load .env.local for local development
2. Bootstrap Azure App Configuration
3. Initialize telemetry

This module is designed to be imported first in main.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ============================================================================
# CRITICAL: Set OIDC allowed hosts BEFORE any other code
# ============================================================================
# PyMongo reads this at import time, so set it immediately (force override)
# Include both patterns to handle DNS SRV resolution:
# - *.mongocluster.cosmos.azure.com: connection string hostname
# - *.global.mongocluster.cosmos.azure.com: resolved SRV hostname
os.environ["MONGODB_OIDC_ALLOWED_HOSTS"] = "*.mongocluster.cosmos.azure.com,*.global.mongocluster.cosmos.azure.com"

# ============================================================================
# SETUP PATHS IMMEDIATELY AT IMPORT TIME
# ============================================================================
# This must happen at module import time, not in a function, so that
# subsequent imports in main.py can find the config module
_backend_dir = Path(__file__).parent.parent
_cardapi_root = _backend_dir.parent
_project_root = _cardapi_root.parent.parent

sys.path.insert(0, str(_cardapi_root))  # So 'config' module can be imported
sys.path.insert(0, str(_project_root))  # For workspace-level imports
sys.path.insert(0, str(_backend_dir))   # For backend-level imports


def _stderr(msg: str) -> None:
    """Write to stderr for early startup diagnostics."""
    print(msg, file=sys.stderr, flush=True)


def load_environment() -> Path | None:
    """
    Load environment variables from .env files.

    Search order:
    1. backend/.env.local
    2. backend/.env
    3. project_root/.env.local
    4. project_root/.env

    Returns:
        Path to the loaded env file, or None if none found.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    backend_dir = Path(__file__).parent.parent
    project_root = backend_dir.parent.parent.parent

    candidates = [
        backend_dir / ".env.local",
        backend_dir / ".env",
        project_root / ".env.local",
        project_root / ".env",
    ]

    for env_file in candidates:
        if env_file.exists():
            load_dotenv(env_file, override=False)
            return env_file

    return None


def bootstrap_appconfig() -> bool:
    """
    Load Azure App Configuration if configured.

    Returns:
        True if loaded successfully, False otherwise.
    """
    try:
        from config.appconfig_provider import bootstrap_appconfig as _bootstrap

        _bootstrap()
        return True
    except Exception:
        return False


def setup_telemetry() -> None:
    """Initialize telemetry and logging."""
    from utils.telemetry_config import setup_azure_monitor

    setup_azure_monitor(logger_name="")


def init_aoai_client() -> None:
    """Initialize the OpenAI client singleton."""
    from src.aoai.client import _init_client

    _init_client()


def bootstrap_all() -> dict:
    """
    Run all bootstrap steps.

    Returns:
        Dict with bootstrap status for each component.
    """
    # Force unbuffered output
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    status = {}

    # 1. Load environment
    env_file = load_environment()
    status["env_file"] = str(env_file.name) if env_file else None

    # 2. Paths already set up at module import time (see top of this file)

    # 3. Bootstrap App Configuration
    status["appconfig"] = bootstrap_appconfig()

    # 4. Setup telemetry
    setup_telemetry()
    status["telemetry"] = True

    # 5. Initialize OpenAI client
    try:
        init_aoai_client()
        status["aoai_client"] = True
    except Exception:
        status["aoai_client"] = False

    return status
