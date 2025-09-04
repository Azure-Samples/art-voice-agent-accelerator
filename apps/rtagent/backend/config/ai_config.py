"""
AI and Model Configuration
===========================

Azure OpenAI, model parameters, and AI-related settings
for the real-time voice agent.
"""

import os

# ==============================================================================
# AGENT CONFIGURATIONS
# ==============================================================================

# Agent configuration file paths
AGENT_AUTH_CONFIG = os.getenv(
    "AGENT_AUTH_CONFIG", "apps/rtagent/backend/src/agents/artagent/agent_store/auth_agent.yaml"
)

AGENT_CLAIM_INTAKE_CONFIG = os.getenv(
    "AGENT_CLAIM_INTAKE_CONFIG",
    "apps/rtagent/backend/src/agents/artagent/agent_store/claim_intake_agent.yaml",
)

AGENT_GENERAL_INFO_CONFIG = os.getenv(
    "AGENT_GENERAL_INFO_CONFIG",
    "apps/rtagent/backend/src/agents/artagent/agent_store/general_info_agent.yaml",
)

# ==============================================================================
# AZURE OPENAI SETTINGS
# ==============================================================================

# Model behavior configuration
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "500"))

# Request timeout settings
AOAI_REQUEST_TIMEOUT = float(os.getenv("AOAI_REQUEST_TIMEOUT", "30.0"))
