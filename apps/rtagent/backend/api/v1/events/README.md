# V1 Event Processor Integration Guide

## Overview

The V1 Event Processor is a simplified event processing system inspired by Azure's CallAutomationEventProcessor pattern. It replaces the complex event registry with a clean, direct approach focused on real-time call processing.

## Key Features

- **Call Correlation**: Automatically correlates events by `callConnectionId`
- **Simple Registration**: Easy handler registration without complex middleware
- **Legacy Integration**: Adapts existing handlers from `acs_event_handlers.py`
- **Azure Pattern**: Follows Azure's Event Processor documentation patterns
- **Performance Focused**: No unnecessary overhead for real-time operations

## Quick Start

### 1. Basic Usage

```python
from apps.rtagent.backend.api.v1.events import (
    get_call_event_processor,
    register_default_handlers,
    ACSEventTypes
)

# Register default handlers (from legacy implementation)
register_default_handlers()

# Get processor instance
processor = get_call_event_processor()

# Process CloudEvents from ACS webhook
result = await processor.process_events(cloud_events, request.app.state)
```

### 2. Custom Handler Registration

```python
from apps.rtagent.backend.api.v1.events import CallEventContext

async def my_custom_handler(context: CallEventContext) -> None:
    """Custom handler for call events."""
    print(f"Handling {context.event_type} for call {context.call_connection_id}")
    
    # Access event data
    event_data = context.get_event_data()
    tone = context.get_event_field("tone")
    
    # Access dependencies
    if context.memo_manager:
        context.memo_manager.update_context("custom_field", "value")

# Register the handler
processor = get_call_event_processor()
processor.register_handler(ACSEventTypes.DTMF_TONE_RECEIVED, my_custom_handler)
```

### 3. FastAPI Integration

```python
from fastapi import FastAPI, Request
from azure.core.messaging import CloudEvent

app = FastAPI()

@app.post("/webhook/acs-events")
async def handle_acs_webhook(request: Request):
    """ACS webhook handler using V1 Event Processor."""
    events_data = await request.json()
    
    # Convert to CloudEvent objects
    cloud_events = [
        CloudEvent(
            source="azure.communication.callautomation",
            type=event.get("eventType"),
            data=event.get("data", event)
        )
        for event in events_data
    ]
    
    # Ensure handlers are registered
    register_default_handlers()
    
    # Process events
    processor = get_call_event_processor()
    result = await processor.process_events(cloud_events, request.app.state)
    
    return {"status": "success", **result}
```

## Architecture Benefits

### Compared to Complex Event Registry

| Feature | V1 Event Processor | Old Event Registry |
|---------|-------------------|-------------------|
| **Complexity** | Simple, direct | Complex middleware |
| **Performance** | Optimized for real-time | Event dispatching overhead |
| **Handler Registration** | Direct function registration | Complex context hierarchies |
| **Call Correlation** | Built-in by callConnectionId | Manual correlation needed |
| **Azure Alignment** | Follows Azure patterns | Custom architecture |

### Event Flow

```
ACS Webhook → CloudEvent → V1 Processor → Handler Functions
     ↓              ↓            ↓              ↓
Raw JSON → Structured → Call Correlation → Business Logic
```

## Migration from Legacy

### Before (Legacy Event Handlers)
```python
# Complex registration in separate file
from apps.rtagent.backend.src.handlers.acs_event_handlers import process_call_events

result = await process_call_events(events, request)
```

### After (V1 Event Processor)
```python
# Simple, direct processing
from apps.rtagent.backend.api.v1.events import get_call_event_processor, register_default_handlers

register_default_handlers()
processor = get_call_event_processor()
result = await processor.process_events(cloud_events, request.app.state)
```

## Available Handlers

The V1 Event Processor includes these handlers adapted from legacy:

- **Call Lifecycle**: `handle_call_connected`, `handle_call_disconnected`
- **Participants**: `handle_participants_updated`
- **DTMF**: `handle_dtmf_tone_received`
- **Media**: `handle_play_completed`, `handle_play_failed`
- **Recognition**: `handle_recognize_completed`, `handle_recognize_failed`

## Monitoring

```python
# Get processor statistics
stats = get_processor_stats()
# Returns: events_processed, events_failed, active_calls, etc.

# Get active calls
active_calls = get_active_calls()
# Returns: Set of call connection IDs
```

## Best Practices

1. **Register Once**: Call `register_default_handlers()` at application startup
2. **Error Handling**: Handlers use error isolation - one failure won't stop others
3. **Context Access**: Use `CallEventContext` to access event data and dependencies
4. **Async Handlers**: All handlers should be async functions
5. **Correlation**: Events are automatically correlated by `callConnectionId`

## Integration with Existing Code

The V1 Event Processor is designed to be a drop-in replacement for the legacy event processing while maintaining compatibility with existing handler logic.

```python
# Update ACSLifecycleHandler.process_call_events method
async def process_call_events(self, events, request):
    # Old way
    # from apps.rtagent.backend.src.handlers.acs_event_handlers import process_call_events
    # result = await process_call_events(events, request)
    
    # New way - V1 Event Processor
    from ..events import get_call_event_processor, register_default_handlers
    register_default_handlers()
    processor = get_call_event_processor()
    result = await processor.process_events(cloud_events, request.app.state)
    
    return result
```

This provides a clean, performant, and maintainable approach to ACS event processing that aligns with Azure's recommended patterns while keeping the simplicity needed for real-time voice applications.
