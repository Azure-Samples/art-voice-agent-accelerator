"""
Genesys AudioConnector Integration
====================================

Bridges Genesys Cloud AudioConnector (AudioHook v2 protocol) to Azure VoiceLive API,
enabling real-time voice AI agents to work with Genesys Cloud contact center.

Architecture:
    Genesys Cloud / Simulator
        ↕ WebSocket (µ-law 8kHz + AudioHook v2 JSON)
    GenesysVoiceLiveHandler
        ↕ Audio conversion (µ-law 8kHz ↔ PCM16 24kHz)
    Azure VoiceLive API (via azure.ai.voicelive SDK)
        ↕ Multi-agent orchestration
    LiveOrchestrator (agents, tools, handoffs)
"""

from .handler import GenesysVoiceLiveHandler

__all__ = ["GenesysVoiceLiveHandler"]
