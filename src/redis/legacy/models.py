# Note: This is not implemented, WIP to be used in the future.
"""
This module defines Pydantic models for managing and validating data structures
used in Redis interactions within the application. These models are designed to
ensure data consistency and provide type safety when working with Redis.

Classes:
    TurnHistoryItem:
        Represents a single turn in a conversation history, including the role
        ('user' or 'agent'), the text of the message, and a timestamp.

    SessionState:
        Represents the state of a user session, including session ID, user ID,
        activity status, turn number, last input, mute status, and language preference.

    CallAutomationEvent:
        Represents events related to call automation, including session ID, event type,
        timestamp, and optional metadata.

Notes:
    Benefits of using models for Redis:
    - Ensures data validation and type safety, reducing runtime errors.
    - Provides a clear schema for data stored in Redis, improving maintainability.
    - Facilitates serialization and deserialization of data for Redis operations.
    - Enhances readability and documentation of the codebase.
"""


from typing import List, Literal, Optional

from pydantic import BaseModel


class TurnHistoryItem(BaseModel):
    role: str  # 'user' or 'agent'
    text: str
    timestamp: str


class SessionState(BaseModel):
    session_id: str
    user_id: Optional[str]
    active: bool = True
    turn_number: int = 0
    last_input: Optional[str] = None
    is_muted: bool = False
    language: Optional[str] = "en-US"


class CallAutomationEvent(BaseModel):
    session_id: str
    event_type: Literal[
        "participants_updated",
        "call_connected",
        "recording_started",
        "recording_stopped",
        "call_disconnected",
    ]
    timestamp: str
    metadata: Optional[dict]
