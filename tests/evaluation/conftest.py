"""
Pytest fixtures for evaluation tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

# CRITICAL: Set this BEFORE any other imports to prevent root conftest.py from mocking AOAI
os.environ["EVAL_USE_REAL_AOAI"] = "1"

import pytest

# Ensure the apps directory is in the Python path for imports
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Load .env.local first (before any other imports that might use env vars)
_env_local = _project_root / ".env.local"
if _env_local.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_local, override=False)

# Also try loading .env as fallback
_env_file = _project_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file, override=False)

# Bootstrap Azure App Configuration to load settings (AZURE_OPENAI_ENDPOINT, etc.)
_appconfig_loaded = False
try:
    from apps.artagent.backend.config.appconfig_provider import (
        bootstrap_appconfig,
        get_provider_status,
    )
    _appconfig_loaded = bootstrap_appconfig()
    if _appconfig_loaded:
        status = get_provider_status()
        print(f"✓ App Config loaded | endpoint={status.get('endpoint', '')[:40]}... label={status.get('label')}", file=sys.stderr)
    else:
        print("⚠ App Config not loaded (using env vars only)", file=sys.stderr)
except ImportError as e:
    print(f"⚠ App Config provider not available: {e}", file=sys.stderr)
except Exception as e:
    print(f"⚠ App Config bootstrap failed: {e}", file=sys.stderr)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add evaluation-specific CLI options."""
    parser.addoption(
        "--submit-to-foundry",
        action="store_true",
        default=False,
        help="Submit evaluation results to Azure AI Foundry after running",
    )
    parser.addoption(
        "--foundry-endpoint",
        type=str,
        default=None,
        help="Azure AI Foundry project endpoint (overrides env var)",
    )
    parser.addoption(
        "--eval-output-dir",
        type=str,
        default=None,
        help="Output directory for evaluation results (default: runs/)",
    )
    parser.addoption(
        "--eval-model",
        type=str,
        default=None,
        help="Model deployment for AI-based Foundry evaluators (default: gpt-4o)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers and check Azure OpenAI config."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (run with -m 'not slow' to skip)"
    )
    
    # Log Azure OpenAI configuration status for debugging
    # Note: At this point, App Config should already be loaded from module init
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    key_present = bool(os.environ.get("AZURE_OPENAI_KEY", ""))
    
    import logging
    logger = logging.getLogger("tests.evaluation.conftest")
    
    if endpoint:
        # Mask most of the endpoint for security
        masked = endpoint[:40] + "..." if len(endpoint) > 40 else endpoint
        logger.info(f"Azure OpenAI endpoint: {masked}")
    else:
        logger.error("AZURE_OPENAI_ENDPOINT not set! LLM calls will fail.")
        logger.error("Check .env.local has AZURE_APPCONFIG_ENDPOINT or set AZURE_OPENAI_ENDPOINT directly")
    
    if key_present:
        logger.info("Azure OpenAI: using API key auth")
    else:
        logger.info("Azure OpenAI: using Azure AD auth")


@pytest.fixture(scope="session")
def eval_output_dir(request: pytest.FixtureRequest) -> Path:
    """Get evaluation output directory."""
    custom_dir = request.config.getoption("--eval-output-dir")
    if custom_dir:
        path = Path(custom_dir)
    else:
        path = Path("runs")
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def submit_to_foundry_flag(request: pytest.FixtureRequest) -> bool:
    """Check if Foundry submission is enabled."""
    return request.config.getoption("--submit-to-foundry")


@pytest.fixture(scope="session")
def foundry_endpoint(request: pytest.FixtureRequest) -> str | None:
    """Get Foundry endpoint from CLI, environment, or app config.
    
    Resolution order:
    1. CLI option --foundry-endpoint
    2. Environment variable AZURE_AI_FOUNDRY_PROJECT_ENDPOINT (set by App Config bootstrap)
    3. Direct import from config module (fallback)
    """
    # 1. CLI option takes precedence
    cli_endpoint = request.config.getoption("--foundry-endpoint")
    if cli_endpoint:
        return cli_endpoint

    # 2. Environment variable (App Config bootstrap populates os.environ)
    # This is checked AFTER bootstrap_appconfig() runs at module init
    env_endpoint = os.environ.get("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
    if env_endpoint:
        return env_endpoint

    # 3. Try get_config_value for dynamic lookup from App Configuration
    try:
        from apps.artagent.backend.config import get_config_value
        config_endpoint = get_config_value(
            "azure/ai-foundry/project-endpoint", 
            "AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"
        )
        if config_endpoint:
            return config_endpoint
    except (ImportError, Exception):
        pass

    # 4. Final fallback: direct import (for when settings loaded from .env.local)
    try:
        from apps.artagent.backend.config import AZURE_AI_FOUNDRY_PROJECT_ENDPOINT
        if AZURE_AI_FOUNDRY_PROJECT_ENDPOINT:
            return AZURE_AI_FOUNDRY_PROJECT_ENDPOINT
    except ImportError:
        pass

    return None


@pytest.fixture(scope="session")
def foundry_model(request: pytest.FixtureRequest) -> str:
    """Get model deployment for Foundry evaluators."""
    return request.config.getoption("--eval-model") or "gpt-4o"


@pytest.fixture(scope="session")
def scenarios_dir() -> Path:
    """Get scenarios directory."""
    return Path(__file__).parent / "scenarios"


@pytest.fixture
def ab_test_scenarios(scenarios_dir: Path) -> Generator[Path, None, None]:
    """Yield paths to A/B test scenario files."""
    ab_dir = scenarios_dir / "ab_tests"
    if ab_dir.exists():
        for scenario_file in ab_dir.glob("*.yaml"):
            yield scenario_file
