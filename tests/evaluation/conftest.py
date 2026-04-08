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


def _load_azd_env_file() -> dict[str, str]:
    """Load the azd environment file (.azure/<env>/.env) if it exists.
    
    Also constructs ai_foundry_project_endpoint from account_endpoint + project_id
    if not directly available.
    """
    env_name = os.environ.get("AZURE_ENV_NAME", "")
    if not env_name:
        return {}
    
    azd_env_path = _project_root / ".azure" / env_name / ".env"
    if not azd_env_path.exists():
        return {}
    
    values = {}
    with open(azd_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                # Remove quotes if present
                value = value.strip().strip('"').strip("'")
                values[key] = value
    
    # If ai_foundry_project_endpoint not present, construct from available values
    # This is a fallback until Terraform is re-provisioned
    if "ai_foundry_project_endpoint" not in values:
        account_endpoint = values.get("ai_foundry_account_endpoint", "")
        project_id = values.get("ai_foundry_project_id", "")
        
        if account_endpoint and project_id:
            # Extract project name from resource ID
            # Format: /subscriptions/.../projects/<project-name>
            if "/projects/" in project_id:
                project_name = project_id.split("/projects/")[-1]
                
                # Extract resource name from account endpoint
                # Input: https://artagentz8kttnsmaif.cognitiveservices.azure.com/
                # Output resource name: artagentz8kttnsmaif
                import re
                match = re.match(r"https://([^.]+)\.", account_endpoint)
                if match:
                    resource_name = match.group(1)
                    # Construct the project endpoint in the format expected by Azure AI Evaluations SDK
                    # Format: https://{resource_name}.services.ai.azure.com/api/projects/{project_name}
                    constructed_endpoint = f"https://{resource_name}.services.ai.azure.com/api/projects/{project_name}"
                    values["ai_foundry_project_endpoint"] = constructed_endpoint
                    print(f"ℹ Constructed Foundry endpoint: {constructed_endpoint}", file=sys.stderr)
    
    return values


@pytest.fixture(scope="session")
def foundry_endpoint(request: pytest.FixtureRequest) -> str | None:
    """Get Foundry endpoint from CLI, environment, azd env, or app config.
    
    Resolution order:
    1. CLI option --foundry-endpoint
    2. Environment variable AZURE_AI_FOUNDRY_PROJECT_ENDPOINT
    3. azd env file (.azure/<env>/.env) - ai_foundry_project_endpoint
    4. App Config lookup
    5. Direct import from config module
    """
    # 1. CLI option takes precedence
    cli_endpoint = request.config.getoption("--foundry-endpoint")
    if cli_endpoint:
        return cli_endpoint

    # 2. Environment variable (App Config bootstrap populates os.environ)
    env_endpoint = os.environ.get("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT", "")
    if env_endpoint and env_endpoint.startswith("https://"):
        return env_endpoint

    # 3. Load from azd env file directly (.azure/<env>/.env)
    # This is the most reliable source after Terraform provisioning
    azd_values = _load_azd_env_file()
    azd_endpoint = azd_values.get("ai_foundry_project_endpoint", "")
    if azd_endpoint and azd_endpoint.startswith("https://"):
        return azd_endpoint

    # 4. Try get_config_value for dynamic lookup from App Configuration
    try:
        from apps.artagent.backend.config import get_config_value
        config_endpoint = get_config_value(
            "azure/ai-foundry/project-endpoint", 
            "AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"
        )
        # Only accept valid HTTPS URLs (ignore error messages and empty strings)
        if config_endpoint and config_endpoint.startswith("https://"):
            return config_endpoint
    except (ImportError, Exception):
        pass

    # 5. Final fallback: direct import (for when settings loaded from .env.local)
    try:
        from apps.artagent.backend.config import AZURE_AI_FOUNDRY_PROJECT_ENDPOINT
        if AZURE_AI_FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_FOUNDRY_PROJECT_ENDPOINT.startswith("https://"):
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
