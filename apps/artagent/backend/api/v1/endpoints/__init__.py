"""
API Endpoints Package
====================

WebSocket and REST endpoints for voice conversations.

Endpoint Overview:
------------------
health.py       - Health checks, readiness probes (GET /api/v1/health/*)
calls.py        - ACS call lifecycle webhooks (POST /api/v1/calls/*)
media.py        - ACS media streaming WebSocket (WS /api/v1/media/*)
browser.py      - Browser WebSocket endpoints (WS /api/v1/browser/*)
agent_builder.py - Dynamic agent configuration (POST /api/v1/agent-builder/*)

WebSocket Flow:
---------------
Phone calls (ACS):
    1. ACS sends webhook to /calls/incomingCall
    2. We answer, ACS connects to /media/ws
    3. MediaHandler(transport=ACS) processes audio

Browser calls:
    1. Frontend connects to /browser/conversation
    2. MediaHandler(transport=BROWSER) processes audio
    3. Dashboard connects to /browser/dashboard/relay for updates

Key Files:
----------
- media.py: ACS telephony - receives JSON-wrapped audio from phone
- browser.py: Web browser - receives raw PCM audio from mic
- Both use the same MediaHandler with different transport modes
- agent_builder.py: REST API for creating dynamic agents at runtime
- scenario_builder.py: REST API for creating dynamic scenarios at runtime
"""

from . import agent_builder, browser, calls, health, media, scenario_builder

__all__ = ["health", "calls", "media", "browser", "agent_builder", "scenario_builder"]
