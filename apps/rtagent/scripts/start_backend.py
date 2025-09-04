"""
start_backend.py
----------------
Script to launch the FastAPI backend (Websocket) for local development.

Features
========
- Ensures the correct conda environment is active.
- Sets PYTHONPATH so that `apps.rtagent.*` imports resolve.
- Starts the backend, or prints clear onboarding instructions if not
  in the right environment.

Usage
-----
    python start_backend.py [conda_env_name]

Default environment name: audioagent
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("start_backend")

DEFAULT_ENV_NAME = "audioagent"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def find_project_root() -> Path:
    """
    Walk upward from this file until ``environment.yaml`` is found.

    :return: Path pointing to the project root.
    :raises RuntimeError: if the file cannot be located.
    """
    here = Path(__file__).resolve()
    for candidate in [here] + list(here.parents):
        if (candidate / "environment.yaml").exists():
            return candidate
    raise RuntimeError("Could not find project root (environment.yaml not found)")


PROJECT_ROOT: Path = find_project_root()
ENV_FILE: Path = PROJECT_ROOT / "environment.yaml"
BACKEND_SCRIPT: Path = PROJECT_ROOT / "apps/rtagent/backend/main.py"


def conda_env_exists(env_name: str) -> bool:
    """Return ``True`` if *env_name* exists in the local conda installation."""
    try:
        result = subprocess.run(
            ["conda", "env", "list"],
            check=True,
            capture_output=True,
            text=True,
        )
        return env_name in result.stdout
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to list conda environments: %s", exc.stderr.strip())
        return False


def create_conda_env(env_yaml: Path) -> None:
    """Create a conda environment from *env_yaml*."""
    if not env_yaml.exists():
        raise FileNotFoundError(f"{env_yaml} does not exist")

    logger.info("Creating conda environment from %s", env_yaml)
    try:
        subprocess.run(["conda", "env", "create", "-f", str(env_yaml)], check=True)
        logger.info("Conda environment created successfully.")
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to create conda environment: %s", exc.stderr.strip())
        raise RuntimeError("Environment creation failed") from exc


def start_backend(env_name: str) -> None:
    """
    Launch the FastAPI backend using *env_name*.

    If the current interpreter is already inside that environment,
    execute the backend directly. Otherwise, print clear instructions.
    """
    if not BACKEND_SCRIPT.exists():
        raise FileNotFoundError(f"Backend script not found at {BACKEND_SCRIPT}")

    current_env = os.environ.get("CONDA_DEFAULT_ENV")
    if current_env == env_name:
        logger.info("Using conda env '%s' — starting backend…", env_name)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        try:
            subprocess.run(
                [sys.executable, str(BACKEND_SCRIPT)],
                env=env,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Backend exited with status %s", exc.returncode)
            sys.exit(exc.returncode)
        return
    # Not already inside the desired env
    if not conda_env_exists(env_name):
        logger.error("Conda env '%s' not found. Create it with:", env_name)
        logger.error("    conda env create -f %s", ENV_FILE)
        sys.exit(1)

    logger.info("")
    logger.info("To launch the backend, run:")
    logger.info("  conda activate %s", env_name)
    logger.info("  set PYTHONPATH=%s", PROJECT_ROOT)
    logger.info("  python %s", BACKEND_SCRIPT)
    logger.info("")
    logger.info("On Unix shells:")
    logger.info("  export PYTHONPATH=%s", PROJECT_ROOT)
    logger.info("  python %s", BACKEND_SCRIPT)
    logger.info("")
    logger.info(
        "(This script does not auto-activate conda envs. "
        "Run the above commands in your terminal.)"
    )
    sys.exit(0)


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    target_env = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ENV_NAME
    try:
        start_backend(target_env)
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ Backend launch failed: %s", exc)
        sys.exit(1)
