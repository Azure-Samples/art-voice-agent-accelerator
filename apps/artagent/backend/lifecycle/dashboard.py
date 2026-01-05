"""
Startup Dashboard - Clean developer-friendly status display.

Provides a concise summary of application configuration and endpoints
without overwhelming junior developers with excessive detail.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def build_startup_dashboard(
    app: FastAPI,
    startup_results: list[tuple[str, float]],
) -> str:
    """
    Build a clean, developer-friendly startup summary.

    Focuses on actionable information:
    - Environment and configuration
    - Key endpoints for testing
    - Any warnings or issues
    """
    from apps.artagent.backend.config import (
        ACS_CONNECTION_STRING,
        ACS_ENDPOINT,
        ACS_SOURCE_PHONE_NUMBER,
        BASE_URL,
        DEBUG_MODE,
        DOCS_URL,
        ENABLE_AUTH_VALIDATION,
        ENABLE_DOCS,
        ENVIRONMENT,
        OPENAPI_URL,
        REDOC_URL,
    )

    base_url = BASE_URL or f"http://localhost:{os.getenv('PORT', '8080')}"
    total_time = sum(d for _, d in startup_results)

    # Build status indicators
    status_lines = []

    # ACS status
    acs_ready = all([ACS_ENDPOINT, ACS_CONNECTION_STRING, ACS_SOURCE_PHONE_NUMBER])
    acs_status = f"✓ Phone: {ACS_SOURCE_PHONE_NUMBER}" if acs_ready else "✗ Not configured"

    # Agent count
    agents = getattr(app.state, "unified_agents", {})
    agent_count = len(agents)

    # Speech pool status
    tts_pool = getattr(app.state, "tts_pool", None)
    stt_pool = getattr(app.state, "stt_pool", None)
    speech_status = "ready"
    if tts_pool and stt_pool:
        tts_warm = tts_pool.snapshot().get("warm_pool_size", 0)
        stt_warm = stt_pool.snapshot().get("warm_pool_size", 0)
        if tts_warm > 0 or stt_warm > 0:
            speech_status = f"warmed (TTS:{tts_warm}, STT:{stt_warm})"

    lines = [
        "",
        "╭" + "─" * 58 + "╮",
        "│  Azure Real-Time Voice Agent                             │",
        "╰" + "─" * 58 + "╯",
        "",
        f"  Environment: {ENVIRONMENT:<12}  Debug: {'ON' if DEBUG_MODE else 'OFF'}",
        f"  Auth:        {'ENABLED' if ENABLE_AUTH_VALIDATION else 'DISABLED':<12}  Agents: {agent_count}",
        f"  Speech:      {speech_status}",
        f"  ACS:         {acs_status}",
        "",
    ]

    # Show startup timing (collapsed)
    lines.append(f"  Startup: {total_time:.1f}s total")
    step_summary = ", ".join(f"{name}:{dur:.1f}s" for name, dur in startup_results)
    if len(step_summary) > 55:
        step_summary = step_summary[:52] + "..."
    lines.append(f"    ({step_summary})")
    lines.append("")

    # Key endpoints (most useful for developers)
    lines.append("  Quick Links:")
    lines.append(f"    Base URL:    {base_url}")
    if ENABLE_DOCS and DOCS_URL:
        lines.append(f"    Swagger UI:  {base_url}{DOCS_URL}")
    if ENABLE_DOCS and REDOC_URL:
        lines.append(f"    ReDoc:       {base_url}{REDOC_URL}")
    lines.append(f"    Health:      {base_url}/api/v1/health")
    lines.append("")

    # Show loaded agents
    if agents:
        lines.append("  Agents:")
        for name in sorted(agents.keys())[:5]:  # Show first 5
            lines.append(f"    • {name}")
        if len(agents) > 5:
            lines.append(f"    ... and {len(agents) - 5} more")
        lines.append("")

    # Scenario info
    scenario = getattr(app.state, "scenario", None)
    if scenario:
        start_agent = getattr(app.state, "start_agent", "Concierge")
        lines.append(f"  Scenario: {scenario.name} (start: {start_agent})")
        lines.append("")

    lines.append("─" * 60)

    return "\n".join(lines)


def build_minimal_banner(total_time: float) -> str:
    """Build a minimal one-line startup banner."""
    from apps.artagent.backend.config import BASE_URL, ENVIRONMENT

    base_url = BASE_URL or f"http://localhost:{os.getenv('PORT', '8080')}"
    return f"✓ Voice Agent ({ENVIRONMENT}) ready in {total_time:.1f}s → {base_url}"
