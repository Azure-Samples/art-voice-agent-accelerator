"""
Voice Session Context
======================

Typed session context for voice handlers, replacing the ad-hoc websocket.state
attributes with explicit, typed fields that can be passed through the call stack.

This is Phase 1 of the Voice Handler Simplification - see:
docs/proposals/voice-handler-simplification.md

Why This Exists:
----------------
Previously, ~20+ attributes were set on websocket.state:
    ws.state.session_context = ...
    ws.state.tts_client = ...
    ws.state.stt_client = ...
    ws.state.lt = ...
    ws.state.cm = ...
    ws.state.is_synthesizing = ...
    # etc.

Problems with websocket.state:
- No type safety (any code can add any attribute)
- Implicit dependencies (hard to know what reads what)
- Hard to test (must mock websocket.state)
- Race conditions (concurrent access from multiple threads)

This context object provides:
- Explicit typed fields
- IDE autocompletion and type checking
- Can be passed through the call stack (no global state)
- Testable without mocking websocket

Usage:
------
    # In MediaHandler.create():
    context = VoiceSessionContext(
        session_id=session_id,
        transport="acs",
        tts_client=tts_client,
        stt_client=stt_client,
        ...
    )

    # Pass to SpeechCascadeHandler:
    handler = SpeechCascadeHandler(context=context, ...)

    # In orchestrator:
    async def process_turn(self, context: VoiceSessionContext):
        if context.tts_cancel_requested:
            return

Migration Notes:
----------------
During the transition, websocket.state attributes are maintained for
backward compatibility but will log deprecation warnings.

See Also:
---------
- SessionState: State snapshot from MemoManager (session_state.py)
- OrchestratorContext: Per-turn context for orchestrator (base.py)
"""

from __future__ import annotations

import asyncio
import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from fastapi import WebSocket

    from apps.artagent.backend.voice.speech_cascade.handler import SpeechCascadeHandler
    from apps.artagent.backend.voice.speech_cascade.orchestrator import (
        CascadeOrchestratorAdapter,
    )
    from apps.artagent.backend.voice.tts import TTSPlayback
    from src.enums.stream_modes import StreamMode
    from src.pools.session_manager import SessionContext
    from src.speech.speech_recognizer import StreamingSpeechRecognizerFromBytes
    from src.stateful.state_managment import MemoManager
    from src.tools.latency_tool import LatencyTool


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class TransportType(str, Enum):
    """Voice transport types."""

    BROWSER = "browser"
    ACS = "acs"
    VOICELIVE = "voicelive"


# ─────────────────────────────────────────────────────────────────────────────
# Protocols (for type hints without circular imports)
# ─────────────────────────────────────────────────────────────────────────────


class BargeInController(Protocol):
    """Protocol for barge-in controllers."""

    async def request(self) -> None:
        """Request barge-in (interrupt current TTS)."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Main Context Class
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class VoiceSessionContext:
    """
    Typed session context for voice handlers.

    Replaces the 20+ attributes on websocket.state with explicit,
    typed fields that can be passed through the call stack.

    Attributes:
        session_id: Unique session identifier
        call_connection_id: ACS call connection ID (or same as session_id)
        transport: Transport type (browser/acs/voicelive)

        tts_client: TTS synthesizer from pool (Azure Speech SDK)
        stt_client: STT recognizer from pool (Azure Speech SDK)

        memo_manager: Session memory manager (MemoManager)
        latency_tool: Latency tracking tool (LatencyTool)

        cancel_event: Async event for TTS cancellation
        is_synthesizing: Whether TTS synthesis is in progress
        audio_playing: Whether audio is being played to user
        tts_cancel_requested: Flag indicating TTS should stop

        orchestrator: The orchestrator adapter for this session
        tts_playback: TTSPlayback instance for voice synthesis
        speech_cascade: SpeechCascadeHandler for speech processing

        barge_in_controller: Controller for barge-in detection
        orchestration_tasks: Set of active orchestration tasks

        event_loop: Cached event loop for thread-safe scheduling

    Thread Safety:
        The cancel_event and boolean flags are safe to access from
        multiple threads. Other attributes should only be accessed
        from the main event loop.
    """

    # ─── Identity ───
    session_id: str
    call_connection_id: str | None = None
    transport: TransportType = TransportType.ACS
    conn_id: str | None = None  # Browser connection ID

    # ─── Pool Resources (acquired from pools) ───
    tts_client: Any = None  # SpeechSynthesizer
    stt_client: Any = None  # StreamingSpeechRecognizerFromBytes
    tts_tier: Any = None  # Pool tier info
    stt_tier: Any = None  # Pool tier info

    # ─── State Management ───
    memo_manager: MemoManager | None = None
    latency_tool: LatencyTool | None = None
    session_context: SessionContext | None = None  # Legacy wrapper
    stream_mode: StreamMode | None = None

    # ─── Cancellation State ───
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    is_synthesizing: bool = False
    audio_playing: bool = False
    tts_cancel_requested: bool = False

    # ─── Orchestration Components ───
    orchestrator: CascadeOrchestratorAdapter | None = None
    tts_playback: TTSPlayback | None = None
    speech_cascade: SpeechCascadeHandler | None = None

    # ─── Agent State ───
    # Cached current agent object (set by MediaHandler or orchestrator)
    _current_agent: Any = field(default=None, repr=False)

    # ─── Barge-In ───
    barge_in_controller: BargeInController | None = None

    # ─── Task Management ───
    orchestration_tasks: set = field(default_factory=set)
    current_tts_task: asyncio.Task | None = None

    # ─── Event Loop (for thread-safe scheduling) ───
    event_loop: asyncio.AbstractEventLoop | None = None

    # ─── WebSocket Reference (for backward compatibility) ───
    _websocket: WebSocket | None = field(default=None, repr=False)

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def websocket(self) -> WebSocket | None:
        """Get the WebSocket connection (set via populate_websocket_state)."""
        return self._websocket

    @property
    def session_short(self) -> str:
        """Short session ID for logging (last 8 chars)."""
        return self.session_id[-8:] if self.session_id else "unknown"

    @property
    def is_acs(self) -> bool:
        """Check if using ACS transport."""
        return self.transport == TransportType.ACS

    @property
    def is_browser(self) -> bool:
        """Check if using browser transport."""
        return self.transport == TransportType.BROWSER

    @property
    def is_voicelive(self) -> bool:
        """Check if using VoiceLive transport."""
        return self.transport == TransportType.VOICELIVE

    @property
    def current_agent(self) -> Any:
        """
        Get the current agent object for voice/TTS configuration.

        Returns the cached agent object. This is set by MediaHandler
        when initializing the session, and can be updated during agent
        handoffs.

        Returns:
            The current agent object (UnifiedAgent or similar) or None.
        """
        return self._current_agent

    @current_agent.setter
    def current_agent(self, agent: Any) -> None:
        """Set the current agent object."""
        self._current_agent = agent

    # ─────────────────────────────────────────────────────────────────────────
    # Cancellation Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def request_cancel(self) -> None:
        """
        Signal cancellation of current TTS/response.

        Thread-safe - can be called from any thread.
        """
        self.cancel_event.set()
        self.tts_cancel_requested = True

    def clear_cancel(self) -> None:
        """
        Reset cancellation state after handling.

        Thread-safe - can be called from any thread.
        """
        self.cancel_event.clear()
        self.tts_cancel_requested = False

    async def wait_for_cancel(self, timeout: float | None = None) -> bool:
        """
        Wait for cancellation signal.

        Args:
            timeout: Maximum time to wait (None = forever)

        Returns:
            True if cancelled, False if timeout
        """
        try:
            await asyncio.wait_for(self.cancel_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Thread-Safe Event Loop Access
    # ─────────────────────────────────────────────────────────────────────────

    def run_coroutine_threadsafe(
        self,
        coro: Any,
    ) -> asyncio.futures.Future | None:
        """
        Schedule a coroutine from a non-async thread.

        Args:
            coro: Coroutine to schedule

        Returns:
            Future that can be used to get the result, or None if no loop
        """
        if self.event_loop is None:
            return None
        return asyncio.run_coroutine_threadsafe(coro, self.event_loop)

    # ─────────────────────────────────────────────────────────────────────────
    # Backward Compatibility: Populate websocket.state
    # ─────────────────────────────────────────────────────────────────────────

    def populate_websocket_state(self, websocket: WebSocket) -> None:
        """
        Populate websocket.state with context values for backward compatibility.

        This method is temporary - use direct context access in new code.

        Args:
            websocket: The WebSocket to populate state on

        Deprecated:
            Access context directly instead of websocket.state
        """
        ws = websocket
        self._websocket = ws

        # Core resources
        ws.state.session_context = self.session_context
        ws.state.tts_client = self.tts_client
        ws.state.stt_client = self.stt_client
        ws.state.lt = self.latency_tool
        ws.state.cm = self.memo_manager
        ws.state.session_id = self.session_id
        ws.state.stream_mode = self.stream_mode

        # TTS state
        ws.state.is_synthesizing = self.is_synthesizing
        ws.state.audio_playing = self.audio_playing
        ws.state.tts_cancel_requested = self.tts_cancel_requested
        ws.state.tts_cancel_event = self.cancel_event
        ws.state.orchestration_tasks = self.orchestration_tasks

        # Event loop
        ws.state._loop = self.event_loop

        # Call connection ID (for ACS)
        if self.call_connection_id:
            ws.state.call_connection_id = self.call_connection_id

        # Speech cascade (set later)
        if self.speech_cascade:
            ws.state.speech_cascade = self.speech_cascade

        # Barge-in controller (set later)
        if self.barge_in_controller:
            ws.state.barge_in_controller = self.barge_in_controller
            ws.state.request_barge_in = self.barge_in_controller.request

    def sync_from_websocket_state(self, websocket: WebSocket) -> None:
        """
        Sync mutable state back from websocket.state.

        For backward compatibility during migration - reads boolean
        flags that may have been modified via websocket.state.

        Args:
            websocket: The WebSocket to read state from
        """
        ws = websocket
        self.is_synthesizing = getattr(ws.state, "is_synthesizing", False)
        self.audio_playing = getattr(ws.state, "audio_playing", False)
        self.tts_cancel_requested = getattr(ws.state, "tts_cancel_requested", False)


# ─────────────────────────────────────────────────────────────────────────────
# Deprecation Helpers
# ─────────────────────────────────────────────────────────────────────────────


class _DeprecatedWebSocketStateWrapper:
    """
    Wrapper that logs deprecation warnings when websocket.state is accessed.

    Usage (in future phase):
        ws.state = _DeprecatedWebSocketStateWrapper(context, original_state)
    """

    def __init__(self, context: VoiceSessionContext, original_state: Any):
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_original_state", original_state)
        object.__setattr__(self, "_warned_attrs", set())

    def __getattr__(self, name: str) -> Any:
        ctx = object.__getattribute__(self, "_context")
        warned = object.__getattribute__(self, "_warned_attrs")
        original = object.__getattribute__(self, "_original_state")

        # Map old names to context attributes
        mapping = {
            "session_id": "session_id",
            "cm": "memo_manager",
            "lt": "latency_tool",
            "tts_client": "tts_client",
            "stt_client": "stt_client",
            "is_synthesizing": "is_synthesizing",
            "audio_playing": "audio_playing",
            "tts_cancel_requested": "tts_cancel_requested",
            "tts_cancel_event": "cancel_event",
            "speech_cascade": "speech_cascade",
            "barge_in_controller": "barge_in_controller",
        }

        if name in mapping:
            if name not in warned:
                warned.add(name)
                warnings.warn(
                    f"websocket.state.{name} is deprecated. "
                    f"Use VoiceSessionContext.{mapping[name]} instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            return getattr(ctx, mapping[name])

        # Fall back to original state for unmapped attributes
        return getattr(original, name)

    def __setattr__(self, name: str, value: Any) -> None:
        ctx = object.__getattribute__(self, "_context")
        warned = object.__getattribute__(self, "_warned_attrs")
        original = object.__getattribute__(self, "_original_state")

        # Map old names to context attributes
        mapping = {
            "is_synthesizing": "is_synthesizing",
            "audio_playing": "audio_playing",
            "tts_cancel_requested": "tts_cancel_requested",
        }

        if name in mapping:
            if name not in warned:
                warned.add(name)
                warnings.warn(
                    f"websocket.state.{name} is deprecated. "
                    f"Use VoiceSessionContext.{mapping[name]} instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            setattr(ctx, mapping[name], value)
        else:
            setattr(original, name, value)


__all__ = [
    "VoiceSessionContext",
    "TransportType",
    "BargeInController",
]
