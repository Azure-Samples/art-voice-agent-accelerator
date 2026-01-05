#!/usr/bin/env python3
"""
Speech Cascade Orchestrator Test Script
========================================

Interactive testing tool for validating chat completions vs responses API.

Usage:
    python devops/scripts/misc/test_orchestrator.py
    python devops/scripts/misc/test_orchestrator.py --model gpt-5-mini --endpoint responses --verbosity 2
    python devops/scripts/misc/test_orchestrator.py --interactive
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Add backend directory to path for config imports
backend_dir = PROJECT_ROOT / "apps" / "artagent" / "backend"
sys.path.insert(0, str(backend_dir))

# ============================================================================
# BOOTSTRAP CONFIGURATION (MUST BE FIRST)
# ============================================================================
# Load .env/.env.local files first
from dotenv import load_dotenv

env_local_path = PROJECT_ROOT / ".env.local"
env_path = PROJECT_ROOT / ".env"

config_source = "system environment"
if env_local_path.exists():
    print(f"📄 Loading .env.local from: {env_local_path}")
    load_dotenv(env_local_path, override=True)
    config_source = ".env.local"
elif env_path.exists():
    print(f"📄 Loading .env from: {env_path}")
    load_dotenv(env_path, override=True)
    config_source = ".env"
else:
    print("⚠️  No .env or .env.local file found. Using system environment variables.")

# Bootstrap Azure App Configuration (if configured)
appconfig_loaded = False
try:
    from config.appconfig_provider import bootstrap_appconfig, get_provider_status

    appconfig_loaded = bootstrap_appconfig()
    if appconfig_loaded:
        status = get_provider_status()
        endpoint_name = status.get("endpoint", "").split("//")[-1].split(".")[0] if status.get("endpoint") else "unknown"
        print(f"✅ Loaded configuration from Azure App Config ({endpoint_name})")
        config_source = f"Azure App Config ({endpoint_name})"
except Exception as e:
    print(f"⚠️  App Configuration not available: {e}")
    print("   Using .env/environment variables only")

# Now safe to import modules that depend on environment variables
from apps.artagent.backend.registries.agentstore.base import ModelConfig
from apps.artagent.backend.voice.shared.base import OrchestratorContext
from apps.artagent.backend.voice.speech_cascade.orchestrator import CascadeOrchestratorAdapter
from utils.ml_logging import get_logger

logger = get_logger("orchestrator_test")


def display_config_info():
    """Display loaded configuration information."""
    print("\n" + "="*80)
    print("🔧 LOADED CONFIGURATION")
    print("="*80)

    # Show configuration source
    print(f"\n📍 Configuration Source: {config_source}")

    # Show App Config status if available
    if appconfig_loaded:
        try:
            from config.appconfig_provider import get_provider_status
            status = get_provider_status()
            print(f"   App Config Endpoint: {status.get('endpoint', 'N/A')}")
            print(f"   App Config Label: {status.get('label', 'N/A')}")
            print(f"   Keys Loaded: {status.get('key_count', 0)}")
        except Exception:
            pass

    # Show authentication method
    api_key = os.getenv("AZURE_OPENAI_KEY")
    client_id = os.getenv("AZURE_CLIENT_ID")

    print()
    if api_key:
        print("🔑 Authentication Method: API Key")
    elif client_id:
        print(f"🔐 Authentication Method: Managed Identity (Client ID: {client_id})")
    else:
        print("🔐 Authentication Method: Azure CLI / DefaultAzureCredential")

    print()

    config_vars = {
        "Azure OpenAI Endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", "❌ Not set"),
        "Azure OpenAI API Version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        "Default Deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
        "Speech Region": os.getenv("AZURE_SPEECH_REGION", "Not set"),
        "Speech Endpoint": os.getenv("AZURE_SPEECH_ENDPOINT", "Not set"),
        "TTS Voice": os.getenv("DEFAULT_TTS_VOICE", "en-US-AvaMultilingualNeural"),
        "Environment": os.getenv("ENVIRONMENT", "dev"),
    }

    for key, value in config_vars.items():
        print(f"  {key}: {value}")

    # Optionally show API key if set (masked)
    if api_key:
        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        print(f"  Azure OpenAI API Key: {masked_key}")

    print("\n" + "="*80 + "\n")


class OrchestratorTester:
    """Interactive tester for speech cascade orchestrator."""

    def __init__(self):
        """Initialize the tester."""
        self.adapter = None
        self.results = []

    async def initialize_orchestrator(
        self,
        model_config: ModelConfig,
        agent_name: str = "TestAgent",
    ) -> CascadeOrchestratorAdapter:
        """
        Initialize the orchestrator with a specific model configuration.

        Args:
            model_config: Model configuration to test
            agent_name: Name of the test agent

        Returns:
            Initialized orchestrator adapter
        """
        from apps.artagent.backend.registries.agentstore.base import UnifiedAgent
        from apps.artagent.backend.voice.speech_cascade.orchestrator import CascadeConfig

        # Create a simple test agent
        test_agent = UnifiedAgent(
            name=agent_name,
            description="Test agent for validating orchestrator functionality",
            greeting="Hello! I'm a test agent.",
            cascade_model=model_config,
            model=model_config,
            prompt_template="""You are a helpful AI assistant.

## Guidelines
- Provide clear, concise responses
- Be direct and informative
- Respond naturally

Current test: Validating {{endpoint_type}} endpoint with verbosity={{verbosity}}""",
            tool_names=[],
            template_vars={
                "endpoint_type": model_config.endpoint_preference or "auto",
                "verbosity": model_config.verbosity,
            },
        )

        # Create cascade configuration
        cascade_config = CascadeConfig(
            start_agent=agent_name,
            model_name=model_config.deployment_id,
            call_connection_id="test-call-123",
            session_id="test-session-456",
            enable_rag=False,  # Disable RAG for testing
            streaming=False,  # Use non-streaming for testing
        )

        # Create orchestrator adapter with correct parameters
        adapter = CascadeOrchestratorAdapter(
            config=cascade_config,
            agents={agent_name: test_agent},
            handoff_map={},  # No handoffs for single-agent testing
        )

        return adapter

    async def test_query(
        self,
        query: str,
        model_config: ModelConfig,
        show_params: bool = True,
    ) -> dict[str, any]:
        """
        Test a single query with the orchestrator.

        Args:
            query: User query to test
            model_config: Model configuration
            show_params: Whether to show detailed parameters

        Returns:
            Result dictionary with response and metadata
        """
        print(f"\n{'='*80}")
        print(f"🧪 Testing Query: {query}")
        print(f"{'='*80}")

        # Initialize orchestrator
        adapter = await self.initialize_orchestrator(model_config)

        # Show configuration
        if show_params:
            print(f"\n📋 Model Configuration:")
            print(f"  Deployment ID: {model_config.deployment_id}")
            print(f"  Endpoint Preference: {model_config.endpoint_preference}")
            print(f"  Model Family: {model_config.model_family or 'auto-detected'}")
            print(f"  Temperature: {model_config.temperature}")
            print(f"  Verbosity: {model_config.verbosity}")
            if model_config.min_p is not None:
                print(f"  Min P: {model_config.min_p}")
            if model_config.typical_p is not None:
                print(f"  Typical P: {model_config.typical_p}")
            if model_config.reasoning_effort:
                print(f"  Reasoning Effort: {model_config.reasoning_effort}")
            if model_config.include_reasoning:
                print(f"  Include Reasoning: {model_config.include_reasoning}")

        # Create context
        context = OrchestratorContext(
            session_id="test-session-456",
            call_connection_id="test-call-123",
            user_text=query,
            conversation_history=[],
            metadata={
                "run_id": "test-run-123",
            },
        )

        # Process turn
        print(f"\n⏳ Processing with orchestrator...")
        try:
            result = await adapter.process_turn(context)

            # Display results
            print(f"\n✅ Response Received:")
            print(f"{'─'*80}")
            print(result.response_text)
            print(f"{'─'*80}")

            # Show metadata
            print(f"\n📊 Response Metadata:")
            print(f"  Agent: {result.agent_name}")
            if result.input_tokens:
                print(f"  Input Tokens: {result.input_tokens}")
            if result.output_tokens:
                print(f"  Output Tokens: {result.output_tokens}")
            if result.latency_ms:
                print(f"  Latency: {result.latency_ms:.2f}ms")
            if result.error:
                print(f"  ❌ Error: {result.error}")

            return {
                "query": query,
                "response": result.response_text,
                "model": model_config.deployment_id,
                "endpoint": model_config.endpoint_preference,
                "verbosity": model_config.verbosity,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": result.latency_ms,
                "error": result.error,
            }

        except Exception as e:
            print(f"\n❌ Error during processing:")
            print(f"  {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

            return {
                "query": query,
                "response": None,
                "model": model_config.deployment_id,
                "endpoint": model_config.endpoint_preference,
                "error": str(e),
            }

    async def compare_endpoints(
        self,
        query: str,
        deployment_id: str = "gpt-4o",
        verbosity_levels: list[int] = [0, 1, 2],
    ) -> None:
        """
        Compare the same query across different endpoint and verbosity settings.

        Args:
            query: Query to test
            deployment_id: Model deployment to use
            verbosity_levels: List of verbosity levels to test
        """
        print(f"\n{'='*80}")
        print(f"🔬 ENDPOINT COMPARISON TEST")
        print(f"{'='*80}")
        print(f"Query: {query}")
        print(f"Model: {deployment_id}")

        results = []

        # Test chat completions endpoint
        for verbosity in verbosity_levels:
            print(f"\n\n{'─'*80}")
            print(f"Testing: Chat Completions (Verbosity={verbosity})")
            print(f"{'─'*80}")

            config = ModelConfig(
                deployment_id=deployment_id,
                endpoint_preference="chat",
                verbosity=verbosity,
                temperature=0.7,
                top_p=0.9,
                max_tokens=4096,
            )

            result = await self.test_query(query, config, show_params=True)
            results.append(result)

        # Test responses API endpoint
        for verbosity in verbosity_levels:
            print(f"\n\n{'─'*80}")
            print(f"Testing: Responses API (Verbosity={verbosity})")
            print(f"{'─'*80}")

            config = ModelConfig(
                deployment_id=deployment_id,
                endpoint_preference="responses",
                verbosity=verbosity,
                temperature=0.7,
                min_p=0.1,
                typical_p=0.9,
                max_completion_tokens=4096,
            )

            result = await self.test_query(query, config, show_params=True)
            results.append(result)

        # Summary
        print(f"\n\n{'='*80}")
        print(f"📈 COMPARISON SUMMARY")
        print(f"{'='*80}")

        for i, result in enumerate(results, 1):
            endpoint = result.get("endpoint", "unknown")
            verbosity = result.get("verbosity", 0)
            response_len = len(result.get("response", "")) if result.get("response") else 0
            tokens = result.get("output_tokens", "N/A")
            latency = result.get("latency_ms", "N/A")

            print(f"\n{i}. {endpoint.upper()} | Verbosity={verbosity}")
            print(f"   Response Length: {response_len} chars")
            print(f"   Output Tokens: {tokens}")
            print(f"   Latency: {latency}")
            if result.get("error"):
                print(f"   ❌ Error: {result['error']}")

        self.results = results

    async def interactive_mode(self):
        """Run interactive testing mode."""
        print(f"\n{'='*80}")
        print(f"🎮 INTERACTIVE ORCHESTRATOR TESTER")
        print(f"{'='*80}")
        print("\nCommands:")
        print("  test <query>          - Test a query with current config")
        print("  config <param> <val>  - Update configuration")
        print("  show                  - Show current configuration")
        print("  env                   - Show loaded environment")
        print("  compare <query>       - Compare endpoints for a query")
        print("  help                  - Show this help")
        print("  quit                  - Exit")

        # Default configuration from environment
        config = ModelConfig(
            deployment_id=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
            endpoint_preference="auto",
            verbosity=0,
            temperature=0.7,
            top_p=0.9,
            max_tokens=4096,
        )

        def show_config():
            """Display current configuration."""
            print(f"\n📋 Current Configuration:")
            print(f"  deployment_id: {config.deployment_id}")
            print(f"  endpoint_preference: {config.endpoint_preference}")
            print(f"  verbosity: {config.verbosity}")
            print(f"  temperature: {config.temperature}")
            print(f"  top_p: {config.top_p}")
            print(f"  max_tokens: {config.max_tokens}")
            if config.min_p is not None:
                print(f"  min_p: {config.min_p}")
            if config.typical_p is not None:
                print(f"  typical_p: {config.typical_p}")

        while True:
            try:
                user_input = input("\n> ").strip()
                if not user_input:
                    continue

                parts = user_input.split(maxsplit=2)
                command = parts[0].lower()

                if command == "quit" or command == "exit":
                    print("👋 Goodbye!")
                    break

                elif command == "help":
                    print("\nAvailable commands:")
                    print("  test <query>          - Test a query")
                    print("  config <param> <val>  - Update config (e.g., config verbosity 2)")
                    print("  show                  - Show current config")
                    print("  env                   - Show loaded environment")
                    print("  compare <query>       - Compare endpoints")
                    print("  quit                  - Exit")

                elif command == "show":
                    show_config()

                elif command == "env":
                    display_config_info()

                elif command == "test":
                    if len(parts) < 2:
                        print("❌ Usage: test <query>")
                        continue
                    query = " ".join(parts[1:])
                    await self.test_query(query, config)

                elif command == "compare":
                    if len(parts) < 2:
                        print("❌ Usage: compare <query>")
                        continue
                    query = " ".join(parts[1:])
                    await self.compare_endpoints(query, config.deployment_id)

                elif command == "config":
                    if len(parts) < 3:
                        print("❌ Usage: config <param> <value>")
                        print("   Examples: config verbosity 2")
                        print("             config endpoint_preference responses")
                        continue

                    param = parts[1]
                    value = parts[2]

                    # Update configuration
                    if param == "deployment_id":
                        config.deployment_id = value
                    elif param == "endpoint_preference":
                        if value not in ["auto", "chat", "responses"]:
                            print("❌ endpoint_preference must be: auto, chat, or responses")
                            continue
                        config.endpoint_preference = value
                    elif param == "verbosity":
                        config.verbosity = int(value)
                    elif param == "temperature":
                        config.temperature = float(value)
                    elif param == "top_p":
                        config.top_p = float(value)
                    elif param == "max_tokens":
                        config.max_tokens = int(value)
                    elif param == "min_p":
                        config.min_p = float(value) if value.lower() != "none" else None
                    elif param == "typical_p":
                        config.typical_p = float(value) if value.lower() != "none" else None
                    elif param == "reasoning_effort":
                        config.reasoning_effort = value if value.lower() != "none" else None
                    else:
                        print(f"❌ Unknown parameter: {param}")
                        continue

                    print(f"✅ Updated {param} = {value}")
                    show_config()

                else:
                    print(f"❌ Unknown command: {command}")
                    print("   Type 'help' for available commands")

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test speech cascade orchestrator with chat/responses API"
    )
    parser.add_argument(
        "--model",
        default=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
        help="Model deployment ID (default: from .env or gpt-4o)",
    )
    parser.add_argument(
        "--endpoint",
        choices=["auto", "chat", "responses"],
        default="auto",
        help="Endpoint preference (default: auto)",
    )
    parser.add_argument(
        "--verbosity",
        type=int,
        choices=[0, 1, 2],
        default=0,
        help="Verbosity level: 0=minimal, 1=standard, 2=detailed (default: 0)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Temperature (default: 0.7)",
    )
    parser.add_argument(
        "--min-p",
        type=float,
        default=None,
        help="Minimum probability (responses API only)",
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Query to test (if not provided, runs interactive mode)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare endpoints for the query",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode",
    )
    parser.add_argument(
        "--show-env",
        action="store_true",
        help="Show loaded environment configuration",
    )

    args = parser.parse_args()

    # Show environment info if requested
    if args.show_env:
        display_config_info()

    tester = OrchestratorTester()

    # Interactive mode
    if args.interactive or not args.query:
        display_config_info()
        await tester.interactive_mode()
        return

    # Single query test
    config = ModelConfig(
        deployment_id=args.model,
        endpoint_preference=args.endpoint,
        verbosity=args.verbosity,
        temperature=args.temperature,
        min_p=args.min_p,
        max_tokens=4096,
    )

    if args.compare:
        await tester.compare_endpoints(args.query, args.model)
    else:
        await tester.test_query(args.query, config)


if __name__ == "__main__":
    # Ensure we have Azure OpenAI endpoint
    required_env_vars = ["AZURE_OPENAI_ENDPOINT"]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print("\n" + "="*80)
        print("❌ Missing required environment variable: AZURE_OPENAI_ENDPOINT")
        print("\n📝 Configuration Options:")
        print("\n1. Local Development with Entra RBAC (recommended):")
        print(f"   {PROJECT_ROOT}/.env.local")
        print("\n   Example content:")
        print("   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/")
        print("   AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o")
        print("\n   Authentication: Uses Azure CLI credentials (run 'az login')")
        print("   The script will automatically use your Azure identity for authentication.")
        print("\n2. Local Development with API Key (fallback):")
        print("   Add to .env.local if you prefer API key authentication:")
        print("   AZURE_OPENAI_KEY=your-api-key-here")
        print("\n3. Azure App Configuration (recommended for production/team):")
        print("   Set AZURE_APPCONFIG_ENDPOINT in .env.local:")
        print("   AZURE_APPCONFIG_ENDPOINT=https://your-appconfig.azconfig.io")
        print("   AZURE_APPCONFIG_LABEL=dev  # or prod, staging, etc.")
        print("\n   The script will automatically load all configuration from App Config.")
        print("   Production: Uses Managed Identity authentication (AZURE_CLIENT_ID)")
        print("\n" + "="*80)
        print("\n💡 Tips:")
        print("   - Entra RBAC (Azure AD) is the default authentication method")
        print("   - For local development, ensure you're logged in: az login")
        print("   - API key is only used if AZURE_OPENAI_KEY is explicitly set")
        print("   - The backend uses the same authentication strategy")
        print("\n" + "="*80)
        sys.exit(1)

    # Validate authentication setup
    api_key = os.getenv("AZURE_OPENAI_KEY")
    client_id = os.getenv("AZURE_CLIENT_ID")

    if api_key:
        print("🔑 Authentication: Using API Key")
    elif client_id:
        print(f"🔐 Authentication: Using Managed Identity (Client ID: {client_id})")
    else:
        print("🔐 Authentication: Using Azure CLI credentials (DefaultAzureCredential)")
        print("   Ensure you're logged in with: az login")

    asyncio.run(main())
