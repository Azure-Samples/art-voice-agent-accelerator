"""
V1 Event Processor Demo
======================

Demonstrates how to use the new V1 Event Processor inspired by Azure's Event Processor pattern.
This shows integration with legacy handlers and simplified event processing.
"""

import asyncio
import json
from azure.core.messaging import CloudEvent
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Import the V1 event system
from apps.rtagent.backend.api.v1.events import (
    get_call_event_processor,
    register_default_handlers,
    get_processor_stats,
    get_active_calls,
    ACSEventTypes,
)


async def demo_v1_event_processing():
    """
    Demo showing how to use the V1 Event Processor.
    """
    print("🚀 V1 Event Processor Demo")
    print("=" * 50)

    # 1. Register default handlers (adapted from legacy)
    print("📋 Registering default handlers...")
    register_default_handlers()

    # 2. Get processor instance
    processor = get_call_event_processor()

    # 3. Show initial stats
    print("📊 Initial processor stats:")
    stats = get_processor_stats()
    print(json.dumps(stats, indent=2))

    # 4. Create sample CloudEvents (like from ACS webhook)
    sample_events = [
        CloudEvent(
            source="azure.communication.callautomation",
            type=ACSEventTypes.CALL_CONNECTED,
            data={
                "callConnectionId": "demo-call-123",
                "callConnectionProperties": {"connectedTime": "2025-08-11T10:30:00Z"},
            },
        ),
        CloudEvent(
            source="azure.communication.callautomation",
            type=ACSEventTypes.PARTICIPANTS_UPDATED,
            data={
                "callConnectionId": "demo-call-123",
                "participants": [
                    {
                        "identifier": {
                            "phoneNumber": {"value": "+1234567890"},
                            "rawId": "4:+1234567890",
                        }
                    }
                ],
            },
        ),
        CloudEvent(
            source="azure.communication.callautomation",
            type=ACSEventTypes.DTMF_TONE_RECEIVED,
            data={"callConnectionId": "demo-call-123", "tone": "1", "sequenceId": 1},
        ),
    ]

    # 5. Process events through V1 processor
    print("🔄 Processing sample events...")

    # Mock request state (normally from FastAPI request.app.state)
    class MockRequestState:
        def __init__(self):
            self.redis = None
            self.acs_caller = None
            self.clients = []

    mock_state = MockRequestState()

    # Process the events
    result = await processor.process_events(sample_events, mock_state)

    print("✅ Processing result:")
    print(json.dumps(result, indent=2))

    # 6. Show updated stats
    print("📊 Updated processor stats:")
    final_stats = get_processor_stats()
    print(json.dumps(final_stats, indent=2))

    # 7. Show active calls
    print("📞 Active calls:")
    active_calls = get_active_calls()
    print(list(active_calls))

    print("✅ Demo completed!")


def create_webhook_handler_example():
    """
    Example of how to integrate V1 Event Processor with FastAPI webhook endpoint.
    """
    app = FastAPI()

    @app.post("/webhook/acs-events")
    async def handle_acs_webhook(request: Request):
        """
        Example webhook handler using V1 Event Processor.

        This replaces the complex event registry with simple, direct processing.
        """
        try:
            # Parse CloudEvents from webhook
            events_data = await request.json()

            # Convert to CloudEvent objects
            cloud_events = []
            for event_data in events_data:
                cloud_event = CloudEvent(
                    source="azure.communication.callautomation",
                    type=event_data.get("eventType", "Unknown"),
                    data=event_data.get("data", event_data),
                )
                cloud_events.append(cloud_event)

            # Ensure handlers are registered
            register_default_handlers()

            # Process through V1 Event Processor
            processor = get_call_event_processor()
            result = await processor.process_events(cloud_events, request.app.state)

            return JSONResponse(
                {
                    "status": "success",
                    "processed": result.get("processed", 0),
                    "api_version": "v1",
                    "processor_type": "v1_event_processor",
                }
            )

        except Exception as e:
            return JSONResponse({"error": str(e), "api_version": "v1"}, status_code=500)

    return app


if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo_v1_event_processing())

    print("\n" + "=" * 50)
    print("📖 Integration Example:")
    print("See create_webhook_handler_example() for FastAPI integration")
    print("Key benefits of V1 Event Processor:")
    print("- ✅ Simple handler registration")
    print("- ✅ Call correlation by callConnectionId")
    print("- ✅ Direct integration with legacy handlers")
    print("- ✅ No complex middleware or retry logic")
    print("- ✅ Inspired by Azure's Event Processor pattern")
