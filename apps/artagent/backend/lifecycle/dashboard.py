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
    deferred_steps: list[str] | None = None,
) -> str:
    """
    Build a clean, developer-friendly startup summary.

    Focuses on actionable information:
    - Environment and configuration
    - Key endpoints for testing
    - Any warnings or issues
    - Deferred tasks running in background
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

    # ACS status
    acs_ready = all([ACS_ENDPOINT, ACS_CONNECTION_STRING, ACS_SOURCE_PHONE_NUMBER])
    acs_status = ACS_SOURCE_PHONE_NUMBER if acs_ready else "not configured"

    # ACS telephony endpoints (only present when the caller was initialized)
    acs_caller = getattr(app.state, "acs_caller", None)
    acs_callback_url = getattr(acs_caller, "callback_url", None)
    acs_websocket_url = getattr(acs_caller, "websocket_url", None)
    acs_recording_url = getattr(acs_caller, "recording_callback_url", None)
    acs_auth_mode = getattr(acs_caller, "effective_auth_mode", None)
    # Make the auth mechanism unambiguous: Entra = managed identity / RBAC,
    # connection_string = shared access key.
    _acs_auth_labels = {
        "entra": "Entra ID (managed identity · RBAC)",
        "connection_string": "connection string (access key)",
    }
    if acs_auth_mode:
        acs_status = f"{acs_status} · auth {_acs_auth_labels.get(acs_auth_mode, acs_auth_mode)}"

    # Agent count
    agents = getattr(app.state, "unified_agents", {})
    agent_count = len(agents)

    # Registered tool count (surfaced here since the registry log is debug-level)
    try:
        from apps.artagent.backend.registries.toolstore.registry import list_tools

        tool_count = len(list_tools())
    except Exception:
        tool_count = 0

    # Speech pool status
    tts_pool = getattr(app.state, "tts_pool", None)
    stt_pool = getattr(app.state, "stt_pool", None)
    speech_status = "ready"
    if tts_pool and stt_pool:
        tts_warm = tts_pool.snapshot().get("warm_pool_size", 0)
        stt_warm = stt_pool.snapshot().get("warm_pool_size", 0)
        if tts_warm > 0 or stt_warm > 0:
            speech_status = f"warmed · TTS {tts_warm}, STT {stt_warm}"

    # ---- Header banner (fixed 60-char width) ----
    inner = 58
    title = f"  Azure Real-Time Voice Agent · {ENVIRONMENT}"
    lines = [
        "",
        "╭" + "─" * inner + "╮",
        "│" + title[:inner].ljust(inner) + "│",
        "╰" + "─" * inner + "╯",
        "",
    ]

    # ---- Runtime facts (two columns) ----
    lines.append("  Runtime")
    lines.append(
        f"    Environment  {ENVIRONMENT:<14} Auth    {'ENABLED' if ENABLE_AUTH_VALIDATION else 'DISABLED'}"
    )
    lines.append(
        f"    Debug        {'ON' if DEBUG_MODE else 'OFF':<14} Agents  {agent_count}"
    )
    lines.append(f"    Speech       {speech_status}")
    lines.append(f"    ACS          {acs_status}")
    if acs_callback_url:
        lines.append(f"                 callback   {acs_callback_url}")
    if acs_websocket_url:
        lines.append(f"                 websocket  {acs_websocket_url}")
    # Only show recording when it differs from the callback URL (avoid duplication)
    if acs_recording_url and acs_recording_url != acs_callback_url:
        lines.append(f"                 recording  {acs_recording_url}")
    lines.append("")

    # ---- Startup story (total + slowest step, no truncation) ----
    lines.append(f"  Startup      core ready in {total_time:.1f}s across {len(startup_results)} step(s)")
    if startup_results:
        slowest_name, slowest_dur = max(startup_results, key=lambda x: x[1])
        lines.append(f"               slowest: {slowest_name} {slowest_dur:.1f}s")
    if deferred_steps:
        lines.append(f"  Deferred     {', '.join(deferred_steps)} — warming in background")
    lines.append("")

    # Key endpoints (most useful for developers)
    lines.append("  Endpoints")
    lines.append(f"    Base         {base_url}")
    if ENABLE_DOCS and DOCS_URL:
        lines.append(f"    Swagger      {base_url}{DOCS_URL}")
    if ENABLE_DOCS and REDOC_URL:
        lines.append(f"    ReDoc        {base_url}{REDOC_URL}")
    lines.append(f"    Health       {base_url}/api/v1/health")
    lines.append(f"    Ready        {base_url}/api/v1/ready")
    lines.append("")

    # Show loaded agents (compact, comma-separated)
    if agents:
        names = sorted(agents.keys())
        shown = ", ".join(names[:6])
        suffix = f" … +{len(names) - 6} more" if len(names) > 6 else ""
        header = f"  Agents ({agent_count})"
        if tool_count:
            header += f" · {tool_count} tools"
        lines.append(header)
        lines.append(f"    {shown}{suffix}")
        lines.append("")

    # Scenario info
    scenario = getattr(app.state, "scenario", None)
    if scenario:
        start_agent = getattr(app.state, "start_agent", "Concierge")
        lines.append(f"  Scenario     {scenario.name} (start: {start_agent})")
        lines.append("")

    lines.append("─" * 60)

    return "\n".join(lines)


def build_minimal_banner(total_time: float) -> str:
    """Build a minimal one-line startup banner."""
    from apps.artagent.backend.config import BASE_URL, ENVIRONMENT

    base_url = BASE_URL or f"http://localhost:{os.getenv('PORT', '8080')}"
    return f"✓ Voice Agent ({ENVIRONMENT}) ready in {total_time:.1f}s → {base_url}"
