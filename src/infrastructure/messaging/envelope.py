"""Versioned envelope shared by asynchronous integration messages."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class EventEnvelopeV1(BaseModel):
    """Metadata required to trace and safely process a version-one message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    event_type: str = Field(min_length=1)
    event_version: Literal[1] = 1
    occurred_at: AwareDatetime
    correlation_id: UUID
    causation_id: UUID
    saga_id: UUID
    order_id: UUID
    payload: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def normalize_timestamp_to_utc(cls, value: datetime) -> datetime:
        """Serialize every accepted aware timestamp in UTC."""
        return value.astimezone(UTC)

