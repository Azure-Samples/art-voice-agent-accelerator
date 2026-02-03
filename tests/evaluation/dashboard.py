#!/usr/bin/env python3
"""
Evaluation Dashboard
====================

Rich terminal-based data visualizations for evaluation runs.

Provides:
- Aggregate statistics across all runs
- Latency distribution charts (ASCII histograms)
- Cost analysis overview
- Tool usage statistics
- Historical trend visualization
- Scenario comparison tables

No external dependencies - uses Unicode box-drawing for charts.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal Colors (copied from eval_cli to keep module standalone)
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
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_RED = "\033[41m"
    BG_BLUE = "\033[44m"


def clear_screen():
    """Clear terminal screen."""
    os.system('clear' if os.name != 'nt' else 'cls')


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RunSummary:
    """Summary data from a single evaluation run."""
    run_id: str
    scenario_name: str
    timestamp: datetime
    total_turns: int
    model_name: str
    
    # Latency
    e2e_mean_ms: float
    e2e_p50_ms: float
    e2e_p95_ms: float
    
    # Tools
    tool_calls: int
    tool_precision: float
    tool_recall: float
    
    # Cost
    input_tokens: int
    output_tokens: int
    cost_usd: float
    
    # Handoffs
    handoff_count: int
    
    # Groundedness
    grounded_ratio: float
    
    # Pass/Fail
    passed: bool | None = None
    
    @classmethod
    def from_json(cls, data: dict[str, Any], run_id: str) -> "RunSummary":
        """Load from summary.json data."""
        latency = data.get("latency_metrics", {})
        tool = data.get("tool_metrics", {})
        cost = data.get("cost_analysis", {})
        ground = data.get("groundedness_metrics", {})
        handoff = data.get("handoff_metrics", {})
        model = data.get("eval_model_config", {})
        
        # Parse timestamp
        ts_str = data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            timestamp = datetime.now()
        
        return cls(
            run_id=run_id,
            scenario_name=data.get("scenario_name", "unknown"),
            timestamp=timestamp,
            total_turns=data.get("total_turns", 0),
            model_name=model.get("model_name", "unknown"),
            e2e_mean_ms=latency.get("e2e_mean_ms", 0),
            e2e_p50_ms=latency.get("e2e_p50_ms", 0),
            e2e_p95_ms=latency.get("e2e_p95_ms", 0),
            tool_calls=tool.get("total_calls", 0),
            tool_precision=tool.get("precision", 0),
            tool_recall=tool.get("recall", 0),
            input_tokens=cost.get("total_input_tokens", 0),
            output_tokens=cost.get("total_output_tokens", 0),
            cost_usd=cost.get("estimated_cost_usd", 0),
            handoff_count=handoff.get("total_handoffs", 0),
            grounded_ratio=ground.get("avg_grounded_span_ratio", 0),
            passed=data.get("pass_fail"),
        )


@dataclass
class DashboardData:
    """Aggregate data for dashboard visualization."""
    runs: list[RunSummary] = field(default_factory=list)
    
    @property
    def total_runs(self) -> int:
        return len(self.runs)
    
    @property
    def scenarios(self) -> set[str]:
        return {r.scenario_name for r in self.runs}
    
    @property 
    def models(self) -> set[str]:
        return {r.model_name for r in self.runs}
    
    def runs_by_scenario(self) -> dict[str, list[RunSummary]]:
        result: dict[str, list[RunSummary]] = {}
        for r in self.runs:
            result.setdefault(r.scenario_name, []).append(r)
        return result
    
    def runs_by_model(self) -> dict[str, list[RunSummary]]:
        result: dict[str, list[RunSummary]] = {}
        for r in self.runs:
            result.setdefault(r.model_name, []).append(r)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════════════════════

def load_all_runs(runs_dir: Path) -> DashboardData:
    """Load all evaluation runs from the runs/ directory."""
    data = DashboardData()
    
    if not runs_dir.exists():
        return data
    
    # Look for summary.json in run directories
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        
        summary_file = run_dir / "summary.json"
        if not summary_file.exists():
            continue
        
        try:
            with open(summary_file, encoding="utf-8") as f:
                summary_data = json.load(f)
            run = RunSummary.from_json(summary_data, run_dir.name)
            data.runs.append(run)
        except Exception:
            continue  # Skip invalid files
    
    # Sort by timestamp (newest first)
    data.runs.sort(key=lambda r: r.timestamp, reverse=True)
    
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# ASCII Charts
# ═══════════════════════════════════════════════════════════════════════════════

def horizontal_bar(value: float, max_value: float, width: int = 30, color: str = C.CYAN) -> str:
    """Create a horizontal bar chart segment."""
    if max_value <= 0:
        return ""
    
    filled = int((value / max_value) * width)
    filled = min(filled, width)
    
    bar = "█" * filled + "░" * (width - filled)
    return f"{color}{bar}{C.RESET}"


def sparkline(values: list[float], width: int = 20) -> str:
    """Create a sparkline from a list of values."""
    if not values:
        return ""
    
    # Sparkline characters (8 levels)
    chars = " ▁▂▃▄▅▆▇█"
    
    min_v = min(values)
    max_v = max(values)
    range_v = max_v - min_v if max_v != min_v else 1
    
    # Sample values to fit width
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = values
    
    result = ""
    for v in sampled:
        idx = int(((v - min_v) / range_v) * 7)
        idx = max(0, min(7, idx))
        result += chars[idx + 1]
    
    return result


def histogram_ascii(values: list[float], bins: int = 10, width: int = 40, 
                    title: str = "", unit: str = "") -> list[str]:
    """Create an ASCII histogram."""
    if not values:
        return [f"{C.DIM}No data{C.RESET}"]
    
    lines = []
    
    # Calculate bins
    min_v = min(values)
    max_v = max(values)
    range_v = max_v - min_v if max_v != min_v else 1
    bin_width = range_v / bins
    
    # Count values in each bin
    counts = [0] * bins
    for v in values:
        idx = min(int((v - min_v) / bin_width), bins - 1)
        counts[idx] += 1
    
    max_count = max(counts) if counts else 1
    
    if title:
        lines.append(f"{C.BOLD}{title}{C.RESET}")
        lines.append("")
    
    # Draw histogram
    for i, count in enumerate(counts):
        bin_start = min_v + i * bin_width
        bin_end = min_v + (i + 1) * bin_width
        
        bar_width = int((count / max_count) * width) if max_count > 0 else 0
        bar = "█" * bar_width
        
        # Color based on position (green=fast, yellow=medium, red=slow for latency)
        if i < bins // 3:
            color = C.GREEN
        elif i < 2 * bins // 3:
            color = C.YELLOW
        else:
            color = C.RED
        
        label = f"{bin_start:>7.0f}-{bin_end:<7.0f}{unit}"
        lines.append(f"  {label} │{color}{bar}{C.RESET} {count}")
    
    return lines


def latency_timeline(runs: list[Any], max_items: int = 10) -> list[str]:
    """Create a compact latency timeline showing recent runs with visual comparison."""
    if not runs:
        return [f"{C.DIM}No data{C.RESET}"]
    
    lines = []
    lines.append(f"{C.BOLD}Recent Runs (newest first):{C.RESET}")
    lines.append("")
    
    # Get recent runs sorted by time
    recent = sorted(runs, key=lambda r: r.timestamp, reverse=True)[:max_items]
    
    if not recent:
        return lines + [f"{C.DIM}No runs{C.RESET}"]
    
    # Find max latency for scaling bars
    max_lat = max(r.e2e_mean_ms for r in recent)
    
    # Show sparkline of all runs first (oldest to newest for natural reading)
    all_sorted = sorted(runs, key=lambda r: r.timestamp)
    all_latencies = [r.e2e_mean_ms / 1000 for r in all_sorted]
    spark = sparkline(all_latencies, width=min(len(all_latencies), 30))
    
    min_lat = min(all_latencies)
    max_lat_s = max(all_latencies)
    lines.append(f"  All runs: {C.DIM}{min_lat:.1f}s{C.RESET} {C.CYAN}{spark}{C.RESET} {C.DIM}{max_lat_s:.1f}s{C.RESET}")
    lines.append("")
    
    for run in recent:
        date = run.timestamp.strftime("%m/%d %H:%M")
        latency_s = run.e2e_mean_ms / 1000
        
        # Color based on latency (green < 3s, yellow 3-8s, red > 8s)
        if latency_s < 3:
            color = C.GREEN
            indicator = "●"
        elif latency_s < 8:
            color = C.YELLOW
            indicator = "●"
        else:
            color = C.RED
            indicator = "●"
        
        # Mini bar (max 12 chars)
        bar_width = int((run.e2e_mean_ms / max_lat) * 12) if max_lat > 0 else 0
        bar = "▓" * bar_width + "░" * (12 - bar_width)
        
        # Scenario name (truncated)
        scenario = run.scenario_name[:28] + ".." if len(run.scenario_name) > 30 else run.scenario_name
        
        # Build info badges
        badges = []
        
        # Turns badge
        badges.append(f"{C.CYAN}{run.total_turns}t{C.RESET}")
        
        # Tools badge  
        if run.tool_calls > 0:
            tool_color = C.GREEN if run.tool_precision > 0.7 else (C.YELLOW if run.tool_precision > 0.4 else C.DIM)
            badges.append(f"{tool_color}🔧{run.tool_calls}{C.RESET}")
        
        # Handoff badge
        if run.handoff_count > 0:
            badges.append(f"{C.MAGENTA}↔{run.handoff_count}{C.RESET}")
        
        # Cost badge
        if run.cost_usd > 0:
            badges.append(f"{C.DIM}${run.cost_usd:.2f}{C.RESET}")
        
        badges_str = " ".join(badges)
        
        # First line: date, latency indicator, latency value, bar
        lines.append(f"  {C.DIM}{date}{C.RESET}  {color}{indicator}{C.RESET} {latency_s:>5.1f}s {C.DIM}{bar}{C.RESET}")
        
        # Second line: scenario name and badges
        lines.append(f"           {scenario}")
        lines.append(f"           {badges_str}")
        lines.append("")
    
    # Legend
    lines.append(f"  {C.DIM}Legend: Nt=turns  🔧N=tools  ↔N=handoffs  $N.NN=cost{C.RESET}")
    
    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard Views
# ═══════════════════════════════════════════════════════════════════════════════

def show_overview(data: DashboardData) -> list[str]:
    """Generate overview statistics."""
    lines = []
    
    if not data.runs:
        return [f"{C.DIM}No evaluation runs found. Run some scenarios first!{C.RESET}"]
    
    # Summary stats
    total_cost = sum(r.cost_usd for r in data.runs)
    total_turns = sum(r.total_turns for r in data.runs)
    total_tools = sum(r.tool_calls for r in data.runs)
    avg_latency = sum(r.e2e_mean_ms for r in data.runs) / len(data.runs)
    
    lines.append(f"  {C.BOLD}Total Runs:{C.RESET}         {data.total_runs}")
    lines.append(f"  {C.BOLD}Unique Scenarios:{C.RESET}   {len(data.scenarios)}")
    lines.append(f"  {C.BOLD}Models Used:{C.RESET}        {', '.join(data.models)}")
    lines.append(f"  {C.BOLD}Total Turns:{C.RESET}        {total_turns}")
    lines.append(f"  {C.BOLD}Total Tool Calls:{C.RESET}   {total_tools}")
    lines.append(f"  {C.BOLD}Total Cost:{C.RESET}         ${total_cost:.4f}")
    lines.append(f"  {C.BOLD}Avg Latency:{C.RESET}        {avg_latency/1000:.2f}s")
    lines.append("")
    
    # Recent runs mini-table
    lines.append(f"  {C.CYAN}Recent Runs:{C.RESET}")
    lines.append(f"  {'─' * 70}")
    lines.append(f"  {C.DIM}{'Scenario':<35} {'Model':<12} {'Turns':<6} {'Latency':<10} {'Cost':<8}{C.RESET}")
    lines.append(f"  {'─' * 70}")
    
    for run in data.runs[:5]:
        scenario = run.scenario_name[:33] + ".." if len(run.scenario_name) > 35 else run.scenario_name
        model = run.model_name[:10] + ".." if len(run.model_name) > 12 else run.model_name
        latency = f"{run.e2e_mean_ms/1000:.2f}s"
        cost = f"${run.cost_usd:.4f}"
        lines.append(f"  {scenario:<35} {model:<12} {run.total_turns:<6} {latency:<10} {cost:<8}")
    
    return lines


def show_latency_analysis(data: DashboardData) -> list[str]:
    """Generate latency analysis view."""
    lines = []
    
    if not data.runs:
        return [f"{C.DIM}No data{C.RESET}"]
    
    # Collect all latencies
    latencies = [r.e2e_mean_ms for r in data.runs]
    
    # Stats
    avg = sum(latencies) / len(latencies)
    sorted_lat = sorted(latencies)
    p50 = sorted_lat[len(sorted_lat) // 2]
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if len(sorted_lat) >= 20 else sorted_lat[-1]
    
    lines.append(f"  {C.CYAN}Latency Statistics (across all runs):{C.RESET}")
    lines.append("")
    lines.append(f"    Mean:  {avg/1000:>8.2f}s")
    lines.append(f"    P50:   {p50/1000:>8.2f}s")
    lines.append(f"    P95:   {p95/1000:>8.2f}s")
    lines.append(f"    Min:   {min(latencies)/1000:>8.2f}s")
    lines.append(f"    Max:   {max(latencies)/1000:>8.2f}s")
    lines.append("")
    
    # Histogram
    hist_lines = histogram_ascii(
        latencies, 
        bins=8, 
        width=35, 
        title="Distribution (ms)",
        unit="ms"
    )
    lines.extend(["  " + line for line in hist_lines])
    lines.append("")
    
    # Timeline of recent runs (replaces hard-to-read trend chart)
    if len(data.runs) >= 2:
        timeline_lines = latency_timeline(data.runs, max_items=8)
        lines.extend(["  " + line for line in timeline_lines])
    
    return lines


def show_cost_analysis(data: DashboardData) -> list[str]:
    """Generate cost analysis view."""
    lines = []
    
    if not data.runs:
        return [f"{C.DIM}No data{C.RESET}"]
    
    # Aggregate by model
    by_model = data.runs_by_model()
    
    lines.append(f"  {C.CYAN}Cost by Model:{C.RESET}")
    lines.append("")
    
    total_cost = sum(r.cost_usd for r in data.runs)
    max_cost = max(sum(r.cost_usd for r in runs) for runs in by_model.values())
    
    for model, runs in sorted(by_model.items(), key=lambda x: -sum(r.cost_usd for r in x[1])):
        model_cost = sum(r.cost_usd for r in runs)
        input_tok = sum(r.input_tokens for r in runs)
        output_tok = sum(r.output_tokens for r in runs)
        pct = (model_cost / total_cost * 100) if total_cost > 0 else 0
        
        bar = horizontal_bar(model_cost, max_cost, width=25)
        lines.append(f"    {model:<15} {bar} ${model_cost:.4f} ({pct:.0f}%)")
        lines.append(f"    {' '*15} {C.DIM}↳ {input_tok:,} in / {output_tok:,} out tokens{C.RESET}")
    
    lines.append("")
    lines.append(f"  {C.BOLD}Total Cost:{C.RESET} ${total_cost:.4f}")
    lines.append(f"  {C.BOLD}Avg per Run:{C.RESET} ${total_cost/len(data.runs):.4f}")
    
    # Cost trend
    if len(data.runs) >= 3:
        lines.append("")
        time_sorted = sorted(data.runs, key=lambda r: r.timestamp)
        
        # Cumulative cost
        cumulative = []
        running = 0.0
        for r in time_sorted:
            running += r.cost_usd
            cumulative.append((r.timestamp.isoformat()[:10], running))
        
        lines.append(f"  {C.CYAN}Cumulative Cost Over Time:{C.RESET}")
        lines.append("")
        spark = sparkline([c[1] for c in cumulative], width=40)
        lines.append(f"    $0 {C.GREEN}{spark}{C.RESET} ${running:.2f}")
    
    return lines


def show_tool_analysis(data: DashboardData) -> list[str]:
    """Generate tool usage analysis view."""
    lines = []
    
    if not data.runs:
        return [f"{C.DIM}No data{C.RESET}"]
    
    # Aggregate tool metrics
    total_calls = sum(r.tool_calls for r in data.runs)
    avg_precision = sum(r.tool_precision for r in data.runs) / len(data.runs)
    avg_recall = sum(r.tool_recall for r in data.runs) / len(data.runs)
    
    lines.append(f"  {C.CYAN}Tool Usage Summary:{C.RESET}")
    lines.append("")
    lines.append(f"    Total Tool Calls:    {total_calls}")
    lines.append(f"    Avg per Run:         {total_calls / len(data.runs):.1f}")
    lines.append("")
    
    # Precision/Recall gauges
    lines.append(f"  {C.CYAN}Tool Accuracy:{C.RESET}")
    lines.append("")
    
    prec_bar = horizontal_bar(avg_precision, 1.0, width=30, color=C.GREEN if avg_precision > 0.7 else C.YELLOW)
    recall_bar = horizontal_bar(avg_recall, 1.0, width=30, color=C.GREEN if avg_recall > 0.7 else C.YELLOW)
    
    lines.append(f"    Precision:  {prec_bar} {avg_precision*100:.0f}%")
    lines.append(f"    Recall:     {recall_bar} {avg_recall*100:.0f}%")
    lines.append("")
    
    # F1 Score
    if avg_precision + avg_recall > 0:
        f1 = 2 * (avg_precision * avg_recall) / (avg_precision + avg_recall)
        f1_bar = horizontal_bar(f1, 1.0, width=30, color=C.GREEN if f1 > 0.7 else C.YELLOW)
        lines.append(f"    F1 Score:   {f1_bar} {f1*100:.0f}%")
    
    lines.append("")
    
    # Groundedness
    avg_ground = sum(r.grounded_ratio for r in data.runs) / len(data.runs)
    ground_bar = horizontal_bar(avg_ground, 1.0, width=30, color=C.GREEN if avg_ground > 0.5 else C.RED)
    lines.append(f"  {C.CYAN}Response Quality:{C.RESET}")
    lines.append("")
    lines.append(f"    Grounded Ratio: {ground_bar} {avg_ground*100:.0f}%")
    
    return lines


def show_scenario_comparison(data: DashboardData) -> list[str]:
    """Generate scenario comparison table."""
    lines = []
    
    if not data.runs:
        return [f"{C.DIM}No data{C.RESET}"]
    
    by_scenario = data.runs_by_scenario()
    
    lines.append(f"  {C.CYAN}Scenario Comparison:{C.RESET}")
    lines.append("")
    lines.append(f"  {'─' * 80}")
    lines.append(f"  {C.DIM}{'Scenario':<30} {'Runs':<6} {'Avg Latency':<12} {'Avg Cost':<10} {'Precision':<10}{C.RESET}")
    lines.append(f"  {'─' * 80}")
    
    for scenario, runs in sorted(by_scenario.items(), key=lambda x: -len(x[1])):
        name = scenario[:28] + ".." if len(scenario) > 30 else scenario
        count = len(runs)
        avg_lat = sum(r.e2e_mean_ms for r in runs) / count / 1000
        avg_cost = sum(r.cost_usd for r in runs) / count
        avg_prec = sum(r.tool_precision for r in runs) / count
        
        # Color code metrics
        lat_color = C.GREEN if avg_lat < 5 else (C.YELLOW if avg_lat < 10 else C.RED)
        prec_color = C.GREEN if avg_prec > 0.7 else (C.YELLOW if avg_prec > 0.4 else C.RED)
        
        lines.append(
            f"  {name:<30} {count:<6} "
            f"{lat_color}{avg_lat:<12.2f}s{C.RESET} "
            f"${avg_cost:<9.4f} "
            f"{prec_color}{avg_prec*100:<9.0f}%{C.RESET}"
        )
    
    lines.append(f"  {'─' * 80}")
    
    return lines


def show_handoff_analysis(data: DashboardData) -> list[str]:
    """Generate handoff analysis view."""
    lines = []
    
    if not data.runs:
        return [f"{C.DIM}No data{C.RESET}"]
    
    total_handoffs = sum(r.handoff_count for r in data.runs)
    runs_with_handoffs = sum(1 for r in data.runs if r.handoff_count > 0)
    
    lines.append(f"  {C.CYAN}Handoff Statistics:{C.RESET}")
    lines.append("")
    lines.append(f"    Total Handoffs:        {total_handoffs}")
    lines.append(f"    Runs with Handoffs:    {runs_with_handoffs} / {len(data.runs)}")
    
    if runs_with_handoffs > 0:
        avg_handoffs = total_handoffs / runs_with_handoffs
        lines.append(f"    Avg per Run (w/ HO):   {avg_handoffs:.1f}")
    
    lines.append("")
    
    # Handoff distribution
    handoff_counts = [r.handoff_count for r in data.runs]
    max_ho = max(handoff_counts) if handoff_counts else 0
    
    if max_ho > 0:
        lines.append(f"  {C.CYAN}Handoffs per Run Distribution:{C.RESET}")
        lines.append("")
        
        # Count how many runs have each number of handoffs
        for i in range(max_ho + 1):
            count = sum(1 for h in handoff_counts if h == i)
            bar = horizontal_bar(count, len(data.runs), width=25)
            lines.append(f"    {i} handoff(s): {bar} {count}")
    
    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive Dashboard Menu
# ═══════════════════════════════════════════════════════════════════════════════

def get_input(prompt: str, valid_options: list[str] | None = None) -> str:
    """Get user input with optional validation."""
    import sys
    while True:
        try:
            response = input(f"\n{C.YELLOW}>{C.RESET} {prompt}: ").strip()
            if valid_options is None or len(valid_options) == 0 or response.lower() in [v.lower() for v in valid_options]:
                return response
            print(f"{C.RED}Invalid option. Choose from: {', '.join(valid_options)}{C.RESET}")
        except (KeyboardInterrupt, EOFError):
            return "0"


def print_header(title: str):
    """Print a styled header."""
    width = 70
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


def show_dashboard_menu(runs_dir: Path) -> str:
    """Show the dashboard main menu."""
    clear_screen()
    print_header("📊 Evaluation Dashboard")
    
    # Load data for stats
    data = load_all_runs(runs_dir)
    
    if data.runs:
        print(f"  {C.DIM}Loaded {len(data.runs)} runs from {len(data.scenarios)} scenarios{C.RESET}")
    else:
        print(f"  {C.DIM}No evaluation runs found. Run some scenarios first!{C.RESET}")
    print()
    
    print_menu_item(1, "Overview", "Summary statistics and recent runs")
    print_menu_item(2, "Latency Analysis", "Response time distribution and trends")
    print_menu_item(3, "Cost Analysis", "Token usage and cost breakdown by model")
    print_menu_item(4, "Tool Analysis", "Precision, recall, and groundedness")
    print_menu_item(5, "Scenario Comparison", "Compare metrics across scenarios")
    print_menu_item(6, "Handoff Analysis", "Agent handoff statistics")
    print()
    print_menu_item(0, "Back to Main Menu", highlight=True)
    
    return get_input("Select view", ["0", "1", "2", "3", "4", "5", "6"])


def show_dashboard_view(view_name: str, runs_dir: Path):
    """Display a specific dashboard view."""
    clear_screen()
    
    data = load_all_runs(runs_dir)
    
    view_map = {
        "1": ("📈 Overview", show_overview),
        "2": ("⏱️  Latency Analysis", show_latency_analysis),
        "3": ("💰 Cost Analysis", show_cost_analysis),
        "4": ("🔧 Tool Analysis", show_tool_analysis),
        "5": ("📋 Scenario Comparison", show_scenario_comparison),
        "6": ("🔀 Handoff Analysis", show_handoff_analysis),
    }
    
    if view_name not in view_map:
        return
    
    title, view_func = view_map[view_name]
    print_header(title)
    
    lines = view_func(data)
    for line in lines:
        print(line)
    
    print()
    get_input("Press Enter to continue", [])


def run_dashboard(runs_dir: Path):
    """Main dashboard loop."""
    while True:
        choice = show_dashboard_menu(runs_dir)
        
        if choice == "0":
            break
        elif choice in ["1", "2", "3", "4", "5", "6"]:
            show_dashboard_view(choice, runs_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    # Find runs directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    runs_dir = project_root / "runs"
    
    if not runs_dir.exists():
        print(f"{C.RED}No runs/ directory found. Run some evaluations first!{C.RESET}")
        sys.exit(1)
    
    run_dashboard(runs_dir)
