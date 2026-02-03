#!/usr/bin/env python3
"""
Interactive Evaluation CLI
==========================

A simple menu-driven CLI for running evaluation scenarios.

Usage:
    python tests/evaluation/eval_cli.py
    
    # Or make it executable:
    chmod +x tests/evaluation/eval_cli.py
    ./tests/evaluation/eval_cli.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ═══════════════════════════════════════════════════════════════════════════════
# Backend Target Configuration
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BackendTarget:
    """Represents a backend target for evaluations."""
    name: str
    url: str
    source: str  # 'local', 'azd', 'custom'
    
    def display(self) -> str:
        """Return display string for the target."""
        if self.source == 'local':
            return f"{self.name} ({self.url})"
        elif self.source == 'azd':
            # Truncate long Azure URLs
            short_url = self.url[:50] + "..." if len(self.url) > 50 else self.url
            return f"{self.name} ({short_url})"
        else:
            return f"{self.name}: {self.url}"


def get_azd_backend_url() -> str | None:
    """Get backend URL from azd environment."""
    try:
        result = subprocess.run(
            ["azd", "env", "get-value", "BACKEND_CONTAINER_APP_URL"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip()
            if url.startswith("https://"):
                return url
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_azd_env_name() -> str | None:
    """Get current azd environment name."""
    try:
        result = subprocess.run(
            ["azd", "env", "get-value", "AZURE_ENV_NAME"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal Colors & Helpers
# ═══════════════════════════════════════════════════════════════════════════════

class C:
    """Terminal colors."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"


def clear_screen():
    """Clear terminal screen."""
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header(title: str):
    """Print a styled header."""
    width = 60
    print()
    print(f"{C.CYAN}{'═' * width}{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}  {title}{C.RESET}")
    print(f"{C.CYAN}{'═' * width}{C.RESET}")
    print()


def print_menu_item(num: int, label: str, description: str = "", highlight: bool = False):
    """Print a menu item."""
    color = C.CYAN if highlight else C.WHITE
    print(f"  {C.BOLD}{color}[{num}]{C.RESET} {label}")
    if description:
        print(f"      {C.DIM}{description}{C.RESET}")


def get_input(prompt: str, valid_options: list[str] | None = None) -> str:
    """Get user input with optional validation."""
    while True:
        try:
            response = input(f"\n{C.YELLOW}>{C.RESET} {prompt}: ").strip()
            # Empty valid_options means accept any input (including empty)
            if valid_options is None or len(valid_options) == 0 or response.lower() in [v.lower() for v in valid_options]:
                return response
            print(f"{C.RED}Invalid option. Choose from: {', '.join(valid_options)}{C.RESET}")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.YELLOW}Goodbye!{C.RESET}")
            sys.exit(0)


def confirm(prompt: str, default: bool = True) -> bool:
    """Get yes/no confirmation."""
    suffix = "[Y/n]" if default else "[y/N]"
    response = get_input(f"{prompt} {suffix}").lower()
    if not response:
        return default
    return response in ('y', 'yes')


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario Discovery
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Scenario:
    """Represents an evaluation scenario."""
    name: str
    path: Path
    description: str
    category: str
    demo_user: dict[str, Any] | None
    turns: int
    agents: list[str]
    
    @classmethod
    def from_yaml(cls, path: Path) -> "Scenario":
        """Load scenario from YAML file."""
        with open(path, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # Extract info
        name = data.get("scenario_name", data.get("name", path.stem))
        description = data.get("description", "No description")
        if isinstance(description, str):
            description = description.strip().split('\n')[0][:80]  # First line, truncated
        
        demo_user = data.get("demo_user")
        turns = len(data.get("turns", []))
        
        # Get agents from session_config or scenario config
        session_config = data.get("session_config", {})
        agents = session_config.get("agents", [])
        if not agents:
            agents = [session_config.get("start_agent", "Unknown")]
        
        # Determine category from path
        category = path.parent.name
        if category == "scenarios":
            category = "general"
        
        return cls(
            name=name,
            path=path,
            description=description,
            category=category,
            demo_user=demo_user,
            turns=turns,
            agents=agents,
        )


def discover_scenarios(base_dir: Path) -> dict[str, list[Scenario]]:
    """Discover all scenarios organized by category."""
    scenarios_dir = base_dir / "scenarios"
    if not scenarios_dir.exists():
        return {}
    
    by_category: dict[str, list[Scenario]] = {}
    
    for yaml_file in scenarios_dir.rglob("*.yaml"):
        # Skip schema files
        if "schema" in yaml_file.name:
            continue
        
        try:
            scenario = Scenario.from_yaml(yaml_file)
            if scenario.category not in by_category:
                by_category[scenario.category] = []
            by_category[scenario.category].append(scenario)
        except Exception as e:
            print(f"{C.DIM}Warning: Could not load {yaml_file}: {e}{C.RESET}")
    
    # Sort scenarios within each category
    for cat in by_category:
        by_category[cat].sort(key=lambda s: s.name)
    
    return by_category


# ═══════════════════════════════════════════════════════════════════════════════
# Menu Screens
# ═══════════════════════════════════════════════════════════════════════════════

def show_main_menu(backend_target: BackendTarget | None = None) -> str:
    """Show main menu and return action."""
    clear_screen()
    print_header("🎯 Evaluation CLI")
    
    print(f"  {C.DIM}Run agent evaluations with structured streaming output{C.RESET}")
    
    # Show current backend target (for info - evals run in-process currently)
    if backend_target:
        if backend_target.source == 'local':
            color = C.GREEN
        elif backend_target.source == 'azd':
            color = C.CYAN
        else:
            color = C.YELLOW
        print(f"  {C.DIM}Backend:{C.RESET} {color}{backend_target.name}{C.RESET} {C.DIM}(exported as EVAL_BACKEND_URL){C.RESET}")
    print()
    
    print_menu_item(1, "Run Scenario", "Select and run an evaluation scenario")
    print_menu_item(2, "Quick Run", "Run the most recent scenario again")
    print_menu_item(3, "List Scenarios", "Browse all available scenarios")
    print_menu_item(4, "View Results", "Browse recent evaluation results")
    print_menu_item(5, "Dashboard", "Visualize metrics across all runs")
    print_menu_item(6, "Settings", "Configure backend target")
    print()
    print_menu_item(0, "Exit", highlight=True)
    
    return get_input("Select option", ["0", "1", "2", "3", "4", "5", "6"])


def show_category_menu(scenarios_by_category: dict[str, list[Scenario]]) -> str | None:
    """Show category selection menu."""
    clear_screen()
    print_header("📁 Select Category")
    
    categories = list(scenarios_by_category.keys())
    
    for i, cat in enumerate(categories, 1):
        count = len(scenarios_by_category[cat])
        print_menu_item(i, cat.replace("_", " ").title(), f"{count} scenario(s)")
    
    print()
    print_menu_item(0, "Back", highlight=True)
    
    valid = ["0"] + [str(i) for i in range(1, len(categories) + 1)]
    choice = get_input("Select category", valid)
    
    if choice == "0":
        return None
    return categories[int(choice) - 1]


def show_scenario_menu(scenarios: list[Scenario], category: str) -> Scenario | None:
    """Show scenario selection menu."""
    clear_screen()
    print_header(f"📋 {category.replace('_', ' ').title()} Scenarios")
    
    for i, scenario in enumerate(scenarios, 1):
        agents_str = ", ".join(scenario.agents[:2])
        if len(scenario.agents) > 2:
            agents_str += f" +{len(scenario.agents) - 2}"
        
        suffix = ""
        if scenario.demo_user:
            suffix = f" {C.GREEN}[demo user]{C.RESET}"
        
        print_menu_item(i, scenario.name, f"{scenario.turns} turns • {agents_str}{suffix}")
        # Show description if available
        if scenario.description and scenario.description != "No description":
            desc = scenario.description[:70] + "..." if len(scenario.description) > 70 else scenario.description
            print(f"      {C.DIM}{desc}{C.RESET}")
    
    print()
    print_menu_item(0, "Back", highlight=True)
    
    valid = ["0"] + [str(i) for i in range(1, len(scenarios) + 1)]
    choice = get_input("Select scenario", valid)
    
    if choice == "0":
        return None
    return scenarios[int(choice) - 1]


def show_scenario_details(scenario: Scenario) -> tuple[bool, str | None]:
    """Show scenario details and confirm run. Returns (should_run, email_override)."""
    clear_screen()
    print_header(f"🔍 {scenario.name}")
    
    print(f"  {C.CYAN}Description:{C.RESET}")
    print(f"    {scenario.description}")
    print()
    
    print(f"  {C.CYAN}Configuration:{C.RESET}")
    print(f"    Path:    {C.DIM}{scenario.path}{C.RESET}")
    print(f"    Turns:   {scenario.turns}")
    print(f"    Agents:  {', '.join(scenario.agents)}")
    print()
    
    email_override = None
    if scenario.demo_user:
        print(f"  {C.GREEN}Demo User:{C.RESET}")
        print(f"    Name:    {scenario.demo_user.get('full_name', 'N/A')}")
        print(f"    Email:   {scenario.demo_user.get('email', 'N/A')}")
        print(f"    Seed:    {scenario.demo_user.get('seed', 'random')}")
        print()
        
        # Ask about email override for testing email tools
        print(f"  {C.YELLOW}📧 Email Override:{C.RESET}")
        print(f"    {C.DIM}To test email-sending tools (e.g. send_decline_summary_email),{C.RESET}")
        print(f"    {C.DIM}you can provide your own email address to receive the emails.{C.RESET}")
        print()
        
        override_input = input(f"  {C.YELLOW}>{C.RESET} Your email (or Enter to use default): ").strip()
        if override_input and "@" in override_input:
            email_override = override_input
            print(f"    {C.GREEN}✓ Will send emails to: {email_override}{C.RESET}")
        print()
    
    should_run = confirm("Run this scenario?")
    return should_run, email_override


def show_results_menu(runs_dir: Path) -> Path | None:
    """Show recent results and allow selection."""
    clear_screen()
    print_header("📊 Recent Results")
    
    if not runs_dir.exists():
        print(f"  {C.DIM}No results found. Run some evaluations first!{C.RESET}")
        get_input("Press Enter to continue", [])
        return None
    
    # Find recent event files
    event_files = sorted(
        runs_dir.glob("*_events.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )[:10]
    
    if not event_files:
        print(f"  {C.DIM}No results found. Run some evaluations first!{C.RESET}")
        get_input("Press Enter to continue", [])
        return None
    
    for i, f in enumerate(event_files, 1):
        import time
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
        name = f.stem.replace("_events", "")
        print_menu_item(i, name, mtime)
    
    print()
    print_menu_item(0, "Back", highlight=True)
    
    valid = ["0"] + [str(i) for i in range(1, len(event_files) + 1)]
    choice = get_input("Select result to view", valid)
    
    if choice == "0":
        return None
    return event_files[int(choice) - 1]


def view_result(event_file: Path):
    """View a result file with summary."""
    import json
    
    clear_screen()
    print_header(f"📊 {event_file.stem.replace('_events', '')}")
    
    events = []
    with open(event_file, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    
    if not events:
        print(f"  {C.DIM}No events recorded{C.RESET}")
    else:
        total_turns = len(events)
        total_tools = sum(len(e.get("tool_calls", [])) for e in events)
        handoffs = sum(1 for e in events if e.get("handoff"))
        avg_e2e = sum(e.get("e2e_ms", 0) for e in events) / max(total_turns, 1)
        
        print(f"  {C.CYAN}Summary:{C.RESET}")
        print(f"    Turns:     {total_turns}")
        print(f"    Tools:     {total_tools}")
        print(f"    Handoffs:  {handoffs}")
        print(f"    Avg E2E:   {avg_e2e/1000:.1f}s")
        print()
        
        print(f"  {C.CYAN}Turns:{C.RESET}")
        for i, e in enumerate(events, 1):
            agent = e.get("agent_name", "?")
            user = e.get("user_text", "")[:50]
            response = e.get("response_text", "")[:50]
            print(f"    {C.BOLD}{i}.{C.RESET} [{agent}]")
            print(f"       {C.DIM}User: {user}...{C.RESET}")
            print(f"       {C.DIM}Response: {response}...{C.RESET}")
    
    print()
    get_input("Press Enter to continue", [])


# ═══════════════════════════════════════════════════════════════════════════════
# Run Evaluation
# ═══════════════════════════════════════════════════════════════════════════════

def run_scenario(scenario: Scenario, project_root: Path, email_override: str | None = None, backend_target: BackendTarget | None = None):
    """Run a scenario with streaming output."""
    clear_screen()
    print_header(f"▶️  Running: {scenario.name}")
    
    if backend_target:
        if backend_target.source == 'local':
            color = C.GREEN
        elif backend_target.source == 'azd':
            color = C.CYAN
        else:
            color = C.YELLOW
        print(f"  {C.DIM}Target:{C.RESET} {color}{backend_target.display()}{C.RESET}")
    
    if email_override:
        print(f"  {C.GREEN}📧 Email override: {email_override}{C.RESET}")
    
    if backend_target or email_override:
        print()
    
    # Use the streaming runner
    cmd = [
        sys.executable,
        "tests/evaluation/run-eval-stream.py",
        "run",
        "--input", str(scenario.path),
    ]
    
    # Set up environment with overrides
    env = os.environ.copy()
    if email_override:
        env["EVAL_EMAIL_OVERRIDE"] = email_override
    if backend_target:
        env["EVAL_BACKEND_URL"] = backend_target.url
    
    try:
        subprocess.run(cmd, cwd=project_root, env=env)
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Interrupted!{C.RESET}")
    
    print()
    get_input("Press Enter to continue", [])


# ═══════════════════════════════════════════════════════════════════════════════
# Settings Menu
# ═══════════════════════════════════════════════════════════════════════════════

def show_settings_menu(current_target: BackendTarget | None) -> BackendTarget | None:
    """Show settings menu for backend target selection.
    
    Note: Backend selection affects EVAL_BACKEND_URL environment variable passed
    to evaluation runs. The current evaluation runner uses in-process orchestration,
    so this is primarily for documentation and future HTTP-mode support.
    """
    clear_screen()
    print_header("⚙️  Settings")
    
    # Show current target
    print(f"  {C.CYAN}Backend Target (for HTTP mode):{C.RESET}")
    if current_target:
        if current_target.source == 'local':
            color = C.GREEN
        elif current_target.source == 'azd':
            color = C.CYAN
        else:
            color = C.YELLOW
        print(f"    {color}{current_target.display()}{C.RESET}")
    else:
        print(f"    {C.DIM}In-process (default){C.RESET}")
    print()
    
    # Note about current mode
    print(f"  {C.DIM}Note: Evaluations currently run in-process for fastest execution.{C.RESET}")
    print(f"  {C.DIM}Backend URL is exported as EVAL_BACKEND_URL for future HTTP mode.{C.RESET}")
    print()
    
    # Build available targets
    targets: list[BackendTarget] = [
        BackendTarget("Local Dev (port 8000)", "http://localhost:8000", "local"),
        BackendTarget("Local Dev (port 8010)", "http://localhost:8010", "local"),
    ]
    
    # Try to get azd backend URL
    azd_url = get_azd_backend_url()
    azd_env = get_azd_env_name()
    if azd_url:
        env_label = f" ({azd_env})" if azd_env else ""
        targets.append(BackendTarget(f"Azure Deployed{env_label}", azd_url, "azd"))
    
    print(f"  {C.CYAN}Select Backend Target:{C.RESET}")
    print()
    
    print_menu_item(1, "In-process", "Run orchestrator directly (default, fastest)")
    
    for i, target in enumerate(targets, 2):
        if target.source == 'local':
            print_menu_item(i, target.name, target.url)
        elif target.source == 'azd':
            # Truncate long Azure URLs for display
            short_url = target.url[:55] + "..." if len(target.url) > 55 else target.url
            print_menu_item(i, target.name, short_url)
    
    # Custom URL option
    custom_idx = len(targets) + 2
    print_menu_item(custom_idx, "Custom URL", "Enter a custom backend URL")
    
    print()
    print_menu_item(0, "Back", highlight=True)
    
    # Status info
    if not azd_url:
        print()
        print(f"  {C.DIM}💡 Azure URL not available. Run 'azd env get-values' to check deployment.{C.RESET}")
    
    valid = ["0", "1"] + [str(i) for i in range(2, custom_idx + 1)]
    choice = get_input("Select target", valid)
    
    if choice == "0":
        return current_target  # No change
    elif choice == "1":
        return None  # In-process mode
    elif choice == str(custom_idx):
        # Custom URL
        print()
        custom_url = input(f"  {C.YELLOW}>{C.RESET} Enter backend URL: ").strip()
        if custom_url:
            if not custom_url.startswith(("http://", "https://")):
                custom_url = "http://" + custom_url
            return BackendTarget("Custom", custom_url, "custom")
        return current_target
    else:
        # Selected a predefined target
        idx = int(choice) - 2
        if 0 <= idx < len(targets):
            return targets[idx]
    
    return current_target


# ═══════════════════════════════════════════════════════════════════════════════
# Main Loop
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point."""
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    runs_dir = project_root / "runs"
    
    # State
    last_scenario: Scenario | None = None
    last_email_override: str | None = None
    backend_target: BackendTarget | None = None  # None = in-process mode
    
    # Discover scenarios
    scenarios_by_category = discover_scenarios(script_dir)
    
    if not scenarios_by_category:
        print(f"{C.RED}No scenarios found in {script_dir / 'scenarios'}{C.RESET}")
        return 1
    
    while True:
        action = show_main_menu(backend_target)
        
        if action == "0":
            print(f"\n{C.CYAN}Goodbye!{C.RESET}\n")
            break
        
        elif action == "1":  # Run Scenario
            category = show_category_menu(scenarios_by_category)
            if category:
                scenario = show_scenario_menu(scenarios_by_category[category], category)
                if scenario:
                    should_run, email_override = show_scenario_details(scenario)
                    if should_run:
                        last_scenario = scenario
                        last_email_override = email_override
                        run_scenario(scenario, project_root, email_override, backend_target)
        
        elif action == "2":  # Quick Run
            if last_scenario:
                email_note = f" (email: {last_email_override})" if last_email_override else ""
                if confirm(f"Run '{last_scenario.name}' again{email_note}?"):
                    run_scenario(last_scenario, project_root, last_email_override, backend_target)
            else:
                clear_screen()
                print_header("⚡ Quick Run")
                print(f"  {C.DIM}No previous scenario. Run a scenario first!{C.RESET}")
                get_input("Press Enter to continue", [])
        
        elif action == "3":  # List Scenarios
            clear_screen()
            print_header("📋 All Scenarios")
            
            all_scenarios: list[Scenario] = []
            for category, scenarios in sorted(scenarios_by_category.items()):
                print(f"\n{C.BOLD}{C.CYAN}{category.replace('_', ' ').title()}{C.RESET}")
                for s in scenarios:
                    all_scenarios.append(s)
                    num = len(all_scenarios)
                    demo = f" {C.GREEN}[demo]{C.RESET}" if s.demo_user else ""
                    print(f"  {C.DIM}[{num}]{C.RESET} {s.name} ({s.turns} turns){demo}")
                    # Show description if available and not default
                    if s.description and s.description != "No description":
                        # Truncate long descriptions
                        desc = s.description[:70] + "..." if len(s.description) > 70 else s.description
                        print(f"      {C.DIM}{desc}{C.RESET}")
            
            print(f"\n{C.DIM}Enter a number to run, or press Enter to go back{C.RESET}")
            choice = input(f"\n{C.YELLOW}>{C.RESET} Select scenario (or Enter to go back): ").strip()
            
            if choice and choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(all_scenarios):
                    scenario = all_scenarios[idx]
                    should_run, email_override = show_scenario_details(scenario)
                    if should_run:
                        last_scenario = scenario
                        last_email_override = email_override
                        run_scenario(scenario, project_root, email_override, backend_target)
        
        elif action == "4":  # View Results
            result = show_results_menu(runs_dir)
            if result:
                view_result(result)
        
        elif action == "5":  # Dashboard
            try:
                from tests.evaluation.dashboard import run_dashboard
                run_dashboard(runs_dir)
            except ImportError as e:
                clear_screen()
                print_header("📊 Dashboard")
                print(f"  {C.RED}Dashboard unavailable: {e}{C.RESET}")
                get_input("Press Enter to continue", [])
        
        elif action == "6":  # Settings
            backend_target = show_settings_menu(backend_target)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
