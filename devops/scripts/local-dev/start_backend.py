"""
start_backend.py
----------------
Script to launch the FastAPI backend (WebSocket) for local development.

Features
========
- Uses uv for package management (replaces conda).
- Sets PYTHONPATH so that `apps.artagent.*` imports resolve.
- Starts the backend with uvicorn.

Usage
-----
    python start_backend.py
    # or
    uv run python start_backend.py
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("start_backend")


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def find_project_root() -> Path:
    """
    Walk upward from this file until ``pyproject.toml`` is found.

    :return: Path pointing to the project root.
    :raises RuntimeError: if the file cannot be located.
    """
    here = Path(__file__).resolve()
    for candidate in [here] + list(here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("Could not find project root (pyproject.toml not found)")


PROJECT_ROOT: Path = find_project_root()
BACKEND_MODULE = "apps.artagent.backend.main:app"


def check_uv_installed() -> bool:
    """Check if uv is installed and available."""
    return shutil.which("uv") is not None


def check_venv_exists() -> bool:
    """Check if .venv exists in project root."""
    return (PROJECT_ROOT / ".venv").exists()


def create_venv() -> None:
    """Create virtual environment and install dependencies using uv."""
    logger.info("Creating virtual environment with uv...")
    try:
        subprocess.run(
            ["uv", "sync"],
            cwd=PROJECT_ROOT,
            check=True,
        )
        logger.info("Virtual environment created and dependencies installed.")
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to create virtual environment: %s", exc)
        raise RuntimeError("Environment creation failed") from exc


def start_backend() -> None:
    """
    Launch the FastAPI backend using uvicorn.
    
    Uses uv run to ensure the correct virtual environment is used.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    
    # Check if we're already in a virtual environment
    in_venv = sys.prefix != sys.base_prefix
    
    if in_venv:
        # Already in venv, run directly
        logger.info("Starting backend with uvicorn...")
        try:
            subprocess.run(
                [
                    sys.executable, "-m", "uvicorn",
                    BACKEND_MODULE,
                    "--host", "0.0.0.0",
                    "--port", "8000",
                    "--reload",
                ],
                env=env,
                cwd=PROJECT_ROOT,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Backend exited with status %s", exc.returncode)
            sys.exit(exc.returncode)
    else:
        # Use uv run to execute in the project's virtual environment
        if not check_uv_installed():
            logger.error("uv is not installed. Install it with:")
            logger.error("    curl -LsSf https://astral.sh/uv/install.sh | sh")
            logger.error("  or")
            logger.error("    pip install uv")
            sys.exit(1)
        
        if not check_venv_exists():
            logger.info("Virtual environment not found. Creating with uv sync...")
            create_venv()
        
        logger.info("Starting backend with uv run...")
        try:
            subprocess.run(
                [
                    "uv", "run",
                    "uvicorn", BACKEND_MODULE,
                    "--host", "0.0.0.0",
                    "--port", "8000",
                    "--reload",
                ],
                env=env,
                cwd=PROJECT_ROOT,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Backend exited with status %s", exc.returncode)
            sys.exit(exc.returncode)


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    try:
        start_backend()
    except KeyboardInterrupt:
        logger.info("Backend stopped by user.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ Backend launch failed: %s", exc)
        sys.exit(1)
