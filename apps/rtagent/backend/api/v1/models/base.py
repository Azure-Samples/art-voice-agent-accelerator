"""
Base model classes for database entities.

Provides common functionality for all database models including:
- Unique ID generation
- Timestamp tracking
- Standard field definitions
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel as PydanticBaseModel, Field


class BaseModel(PydanticBaseModel):
    """
    Base model for all database entities.

    Provides:
    - Unique ID generation
    - Standard configuration
    """

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")

    class Config:
        """Pydantic configuration for database models."""

        # Enable ORM mode for SQLAlchemy integration
        from_attributes = True

        # Use enum values instead of names
        use_enum_values = True

        # Validate assignment
        validate_assignment = True

        # JSON encoders for special types
        json_encoders = {datetime: lambda v: v.isoformat(), UUID: lambda v: str(v)}


class TimestampedModel(BaseModel):
    """
    Base model with timestamp tracking.

    Extends BaseModel with:
    - Creation timestamp
    - Last update timestamp
    """

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the record was created",
    )

    updated_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the record was last updated"
    )

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to current time."""
        self.updated_at = datetime.utcnow()
