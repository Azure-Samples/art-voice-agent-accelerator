#!/usr/bin/env python3
"""
Evaluation Streaming Viewer
===========================

Runs evaluations while streaming structured per-turn output in real-time.
Suppresses all noise and shows only the essential turn-by-turn information.

Usage:
    python tests/evaluation/run-eval-stream.py run --input <scenario.yaml>
    
    # Or via shell wrapper:
    ./tests/evaluation/run-eval-stream.sh run --input <scenario.yaml>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Colors for terminal output
# ═══════════════════════════════════════════════════════════════════════════════

class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Foreground
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"
    
    @classmethod
    def disable(cls):
        """Disable colors for non-TTY output."""
        for attr in dir(cls):
            if not attr.startswith('_') and isinstance(getattr(cls, attr), str):
                setattr(cls, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# ═══════════════════════════════════════════════════════════════════════════════
# Turn Event Pretty Printer
# ═══════════════════════════════════════════════════════════════════════════════

def truncate(text: str, max_len: int = 200) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def format_duration(ms: float) -> str:
    """Format duration in human readable format."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}m"


def print_turn_event(event: dict[str, Any], turn_number: int) -> None:
    """Pretty-print a single turn event."""
    C = Colors
    
    turn_id = event.get("turn_id", "unknown")
    agent = event.get("agent_name", "unknown")
    user_text = event.get("user_text", "")
    response_text = event.get("response_text", "")
    tool_calls = event.get("tool_calls", [])
    handoff = event.get("handoff")
    e2e_ms = event.get("e2e_ms", 0)
    ttft_ms = event.get("ttft_ms")
    response_tokens = event.get("response_tokens")
    error = event.get("error")
    
    # Header
    print()
    print(f"{C.BOLD}{C.CYAN}{'═' * 70}{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}Turn {turn_number}: {turn_id}{C.RESET}  {C.DIM}│{C.RESET}  "
          f"{C.BLUE}Agent: {agent}{C.RESET}  {C.DIM}│{C.RESET}  "
          f"{C.GRAY}{format_duration(e2e_ms)}{C.RESET}")
    print(f"{C.CYAN}{'─' * 70}{C.RESET}")
    
    # User input
    print(f"{C.YELLOW}👤 User:{C.RESET}")
    print(f"   {user_text}")
    
    # Tool calls (if any)
    if tool_calls:
        print()
        print(f"{C.MAGENTA}🔧 Tools ({len(tool_calls)}):{C.RESET}")
        for tc in tool_calls:
            tool_name = tc.get("name", "unknown")
            duration = tc.get("duration_ms", 0)
            status = tc.get("status", "unknown")
            args = tc.get("arguments", {})
            result_summary = tc.get("result_summary", "")
            
            # Status indicator
            if status == "success":
                status_icon = f"{C.GREEN}✓{C.RESET}"
            elif status == "error":
                status_icon = f"{C.RED}✗{C.RESET}"
            else:
                status_icon = f"{C.YELLOW}?{C.RESET}"
            
            print(f"   {status_icon} {C.BOLD}{tool_name}{C.RESET} "
                  f"{C.DIM}({format_duration(duration)}){C.RESET}")
            
            # Show key arguments (abbreviated)
            if args:
                arg_strs = []
                for k, v in list(args.items())[:3]:
                    v_str = str(v)[:30]
                    arg_strs.append(f"{k}={v_str}")
                if arg_strs:
                    print(f"      {C.DIM}args: {', '.join(arg_strs)}{C.RESET}")
            
            # Show result summary (abbreviated)
            if result_summary and result_summary != "<tool callback not received>":
                result_preview = truncate(result_summary.replace('\n', ' '), 80)
                print(f"      {C.DIM}→ {result_preview}{C.RESET}")
    
    # Handoff (if occurred)
    if handoff:
        source = handoff.get("source_agent", "?")
        target = handoff.get("target_agent", "?")
        tool_name = handoff.get("tool_name", "")
        print()
        print(f"{C.YELLOW}🔀 Handoff:{C.RESET} {source} → {C.BOLD}{target}{C.RESET}")
        if tool_name:
            print(f"      {C.DIM}via {tool_name}{C.RESET}")
    
    # Response
    print()
    print(f"{C.GREEN}🤖 Response:{C.RESET}")
    
    # Wrap response text nicely
    response_lines = response_text.split('\n')
    for line in response_lines[:10]:  # Limit to 10 lines
        wrapped = truncate(line, 100)
        print(f"   {wrapped}")
    if len(response_lines) > 10:
        print(f"   {C.DIM}... ({len(response_lines) - 10} more lines){C.RESET}")
    
    # Metrics footer - important for verbosity assessment
    metrics = []
    total_tokens = event.get("total_tokens") or event.get("prompt_tokens", 0) + (response_tokens or 0)
    if total_tokens:
        metrics.append(f"total: {total_tokens} tokens")
    if response_tokens:
        # Highlight high token counts (verbosity indicator)
        if response_tokens > 150:
            metrics.append(f"{C.YELLOW}response: {response_tokens} tokens{C.RESET}")
        elif response_tokens > 100:
            metrics.append(f"response: {response_tokens} tokens")
        else:
            metrics.append(f"{C.GREEN}response: {response_tokens} tokens{C.RESET}")
    if ttft_ms:
        metrics.append(f"TTFT: {format_duration(ttft_ms)}")
    
    if metrics:
        print()
        print(f"   {C.DIM}{' │ '.join(metrics)}{C.RESET}")
    
    # Error (if any)
    if error:
        print()
        print(f"   {C.RED}⚠ Error: {error}{C.RESET}")


def print_scenario_header(scenario_name: str, input_path: str, demo_user: dict | None = None) -> None:
    """Print scenario header."""
    C = Colors
    print()
    print(f"{C.BOLD}{C.WHITE}{'═' * 70}{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}  EVALUATION: {scenario_name}{C.RESET}")
    print(f"{C.DIM}  {input_path}{C.RESET}")
    
    if demo_user:
        print(f"{C.WHITE}{'─' * 70}{C.RESET}")
        print(f"  {C.CYAN}Demo User:{C.RESET} {demo_user.get('full_name', 'unknown')}")
        print(f"  {C.DIM}Email: {demo_user.get('email', 'N/A')}{C.RESET}")
        print(f"  {C.DIM}Scenario: {demo_user.get('scenario', 'banking')}{C.RESET}")
        if demo_user.get('seed'):
            print(f"  {C.DIM}Seed: {demo_user.get('seed')} (reproducible){C.RESET}")
    
    print(f"{C.BOLD}{C.WHITE}{'═' * 70}{C.RESET}")


def print_scenario_summary(events: list[dict], elapsed_s: float, runs_dir: Path | None = None) -> None:
    """Print summary after all turns complete."""
    C = Colors
    
    total_turns = len(events)
    total_tools = sum(len(e.get("tool_calls", [])) for e in events)
    handoffs = sum(1 for e in events if e.get("handoff"))
    errors = sum(1 for e in events if e.get("error"))
    avg_e2e = sum(e.get("e2e_ms", 0) for e in events) / max(total_turns, 1)
    
    # Token metrics for verbosity assessment
    total_response_tokens = sum(e.get("response_tokens", 0) or 0 for e in events)
    total_all_tokens = sum(
        e.get("total_tokens") or (e.get("prompt_tokens", 0) + (e.get("response_tokens", 0) or 0))
        for e in events
    )
    avg_response_tokens = total_response_tokens / max(total_turns, 1)
    
    print()
    print(f"{C.BOLD}{C.WHITE}{'═' * 70}{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}  SUMMARY{C.RESET}")
    print(f"{C.WHITE}{'─' * 70}{C.RESET}")
    print(f"  Turns:     {total_turns}")
    print(f"  Tools:     {total_tools}")
    print(f"  Handoffs:  {handoffs}")
    if errors:
        print(f"  {C.RED}Errors:    {errors}{C.RESET}")
    print(f"  Avg E2E:   {format_duration(avg_e2e)}")
    print(f"  Elapsed:   {elapsed_s:.1f}s")
    
    # Token summary (key for verbosity)
    print(f"{C.WHITE}{'─' * 70}{C.RESET}")
    print(f"  {C.CYAN}Tokens:{C.RESET}")
    print(f"    Total:    {total_all_tokens:,}")
    print(f"    Response: {total_response_tokens:,}")
    # Flag verbose responses
    if avg_response_tokens > 150:
        print(f"    {C.YELLOW}Avg/turn: {avg_response_tokens:.0f} tokens (VERBOSE){C.RESET}")
    elif avg_response_tokens > 100:
        print(f"    Avg/turn: {avg_response_tokens:.0f} tokens")
    else:
        print(f"    {C.GREEN}Avg/turn: {avg_response_tokens:.0f} tokens (concise){C.RESET}")
    
    # Show output files
    if runs_dir:
        recent_files = sorted(
            runs_dir.glob("*"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True
        )[:5]
        
        output_files = [f for f in recent_files if f.suffix in ('.jsonl', '.json') or f.is_dir()]
        if output_files:
            print(f"{C.WHITE}{'─' * 70}{C.RESET}")
            print(f"  {C.DIM}Output:{C.RESET}")
            for f in output_files[:3]:
                print(f"    {C.DIM}{f}{C.RESET}")
    
    print(f"{C.BOLD}{C.WHITE}{'═' * 70}{C.RESET}")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# File Watcher - Tails JSONL events file
# ═══════════════════════════════════════════════════════════════════════════════

class EventsFileTailer:
    """Tails an events JSONL file and yields new events as they arrive."""
    
    def __init__(self, runs_dir: Path, poll_interval: float = 0.1):
        self.runs_dir = runs_dir
        self.poll_interval = poll_interval
        self._stop = False
        self._start_time = time.time()
    
    def stop(self):
        self._stop = True
    
    def find_latest_events_file(self) -> Path | None:
        """Find the most recently created *_events.jsonl file after start_time."""
        events_files = list(self.runs_dir.glob("*_events.jsonl"))
        if not events_files:
            return None
        
        # Filter to files created after we started
        recent_files = [
            f for f in events_files 
            if f.stat().st_mtime >= self._start_time - 1  # 1 second buffer
        ]
        
        if not recent_files:
            return None
        
        return max(recent_files, key=lambda p: p.stat().st_mtime)
    
    def tail_events(self) -> list[dict]:
        """
        Tail the events file and yield new events as they're written.
        Returns list of all events when done.
        """
        events = []
        events_file = None
        file_position = 0
        turn_number = 0
        
        # Wait for events file to appear
        print(f"{Colors.DIM}Waiting for evaluation to start...{Colors.RESET}", end="", flush=True)
        
        while not self._stop:
            # Look for events file if we don't have one yet
            if events_file is None:
                events_file = self.find_latest_events_file()
                if events_file:
                    print(f"\r{Colors.DIM}Found: {events_file.name}{' ' * 30}{Colors.RESET}")
                    file_position = 0
            
            if events_file and events_file.exists():
                try:
                    with open(events_file, 'r', encoding='utf-8') as f:
                        f.seek(file_position)
                        new_lines = f.readlines()
                        file_position = f.tell()
                    
                    for line in new_lines:
                        line = line.strip()
                        if line:
                            try:
                                event = json.loads(line)
                                turn_number += 1
                                print_turn_event(event, turn_number)
                                events.append(event)
                            except json.JSONDecodeError:
                                pass  # Partial write, will get it next time
                                
                except (FileNotFoundError, IOError):
                    events_file = None  # File was moved/deleted
            
            time.sleep(self.poll_interval)
        
        return events


# ═══════════════════════════════════════════════════════════════════════════════
# Main Evaluation Runner
# ═══════════════════════════════════════════════════════════════════════════════

def run_evaluation_with_streaming(input_path: Path, output_dir: Path | None = None) -> int:
    """
    Run evaluation while streaming turn events to console.
    
    Returns:
        Exit code (0 = success)
    """
    import yaml
    
    # Load scenario to get name
    with open(input_path, encoding='utf-8') as f:
        scenario = yaml.safe_load(f)
    scenario_name = scenario.get("scenario_name", scenario.get("name", input_path.stem))
    demo_user = scenario.get("demo_user")
    
    print_scenario_header(scenario_name, str(input_path), demo_user)
    
    # Determine runs directory
    runs_dir = output_dir or Path("runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    
    # Start file tailer
    tailer = EventsFileTailer(runs_dir)
    
    project_root = Path(__file__).parent.parent.parent
    
    # Build command string - use shell redirection for reliable output suppression
    # Python subprocess's stdout/stderr=DEVNULL doesn't always work with Python logging
    input_abs = input_path.absolute()
    cmd_parts = [
        sys.executable, "-m", "tests.evaluation.cli",
        "run", "--input", str(input_abs)
    ]
    if output_dir:
        cmd_parts.extend(["--output", str(output_dir.absolute())])
    
    # Environment with aggressive log suppression
    env = os.environ.copy()
    env.update({
        "EVAL_LOG_LEVEL": "CRITICAL",  # Suppress everything
        "LOG_LEVEL": "CRITICAL",
        "DISABLE_CLOUD_TELEMETRY": "true",
        "AZURE_LOG_LEVEL": "error",
        "AZURE_SDK_LOG_LEVEL": "error",
        "OPENAI_LOG": "error",
        "PYTHONWARNINGS": "ignore",
        "GRPC_VERBOSITY": "NONE",
        # Force all Python logging to CRITICAL
        "LOGLEVEL": "CRITICAL",
    })
    
    # Build shell command with full redirection (more reliable than Python subprocess)
    shell_cmd = " ".join(cmd_parts) + " > /dev/null 2>&1"
    
    # Run evaluation in subprocess
    start_time = time.time()
    
    def run_subprocess():
        try:
            subprocess.run(
                shell_cmd,
                shell=True,
                cwd=project_root,
                env=env,
                stdin=subprocess.DEVNULL,
            )
        finally:
            tailer.stop()
    
    # Start subprocess in thread
    proc_thread = Thread(target=run_subprocess, daemon=True)
    proc_thread.start()
    
    # Tail events file
    try:
        events = tailer.tail_events()
    except KeyboardInterrupt:
        tailer.stop()
        print(f"\n{Colors.YELLOW}Interrupted!{Colors.RESET}")
        return 130
    
    # Wait for subprocess to finish
    proc_thread.join(timeout=5)
    
    elapsed = time.time() - start_time
    print_scenario_summary(events, elapsed, runs_dir)
    
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run evaluations with streaming per-turn output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # run subcommand
    run_parser = subparsers.add_parser("run", help="Run evaluation scenario")
    run_parser.add_argument(
        "--input", "-i",
        required=True,
        type=Path,
        help="Path to scenario YAML file",
    )
    run_parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output directory (default: runs/)",
    )
    run_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    
    args = parser.parse_args()
    
    if args.no_color:
        Colors.disable()
    
    if args.command == "run":
        if not args.input.exists():
            print(f"{Colors.RED}Error: Input file not found: {args.input}{Colors.RESET}")
            return 1
        return run_evaluation_with_streaming(args.input, args.output)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
