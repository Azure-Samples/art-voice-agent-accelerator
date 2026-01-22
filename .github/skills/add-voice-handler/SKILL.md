---
name: add-voice-handler
description: Add a new voice handler or feature to the voice module
---

# Add Voice Handler Skill

Add new voice features to `apps/artagent/backend/voice/`.

## Handler Template

```python
"""
Voice Feature Module
====================

Brief description of the voice feature.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.artagent.backend.voice.shared.context import VoiceSessionContext, TransportType
from apps.artagent.backend.voice.shared.handoff_service import HandoffService
from apps.artagent.backend.voice.shared.metrics_factory import LazyMeter, build_session_attributes
from utils.ml_logging import get_logger

if TYPE_CHECKING:
    from azure.cognitiveservices.speech import SpeechConfig

logger = get_logger(__name__)

# Lazy metrics
_meter = LazyMeter("voice.my_feature", version="1.0.0")
_latency = _meter.histogram(
    name="voice.my_feature.latency",
    description="Feature latency",
    unit="ms",
)


async def handle_my_feature(
    context: VoiceSessionContext,
    data: bytes,
) -> None:
    """
    Handle voice feature.

    Args:
        context: Voice session context (use instead of websocket.state)
        data: Input data to process
    """
    # Transport-aware processing
    if context.transport_type == TransportType.BROWSER:
        sample_rate = 48000
    elif context.transport_type == TransportType.ACS:
        sample_rate = 16000
    else:
        sample_rate = 24000  # VoiceLive

    # Process and record metrics
    attrs = build_session_attributes(context.session_id)
    _latency.record(latency_ms, attributes=attrs)
```

## Steps

1. Create file in `voice/` or appropriate subdirectory
2. Use `VoiceSessionContext` instead of `websocket.state`
3. Add lazy metrics with `voice.` prefix
4. Guard transport-specific behavior
5. Use async handlers (never block event loop)

## Required Patterns

### Session Context (Always Use)
```python
from apps.artagent.backend.voice.shared.context import VoiceSessionContext

context = VoiceSessionContext.from_websocket(websocket)
session_id = context.session_id
transport = context.transport_type
```

### TTS Playback (Transport-Agnostic)
```python
from apps.artagent.backend.voice.tts import TTSPlayback

tts = TTSPlayback(context)
await tts.speak(text)  # Auto-routes to browser/ACS/VoiceLive
```

### Handoff Resolution
```python
from apps.artagent.backend.voice.shared.handoff_service import HandoffService

handoff_service = HandoffService(
    scenario_name=scenario_name,
    handoff_map=handoff_map,
    agents=agents,
    memo_manager=memo_manager,
)
resolution = handoff_service.resolve_handoff(from_agent, to_agent)
```

### Lazy Speech SDK Import
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure.cognitiveservices.speech import SpeechConfig

def create_speech_config() -> "SpeechConfig":
    from azure.cognitiveservices.speech import SpeechConfig
    return SpeechConfig(...)
```

## Validation Checklist

- [ ] Uses `VoiceSessionContext` instead of `websocket.state`
- [ ] Uses `TTSPlayback` for audio output
- [ ] Uses `LazyMeter` pattern for metrics
- [ ] Async handlers don't block
- [ ] Speech SDK imports are lazy
- [ ] Metric names use `voice.` prefix
- [ ] Works for all transports (or properly guarded)

## Reference

See [voice-module.instructions.md](../../instructions/voice-module.instructions.md) for full patterns and contracts.
