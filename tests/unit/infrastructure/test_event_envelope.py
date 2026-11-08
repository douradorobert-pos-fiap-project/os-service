from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.infrastructure.messaging.envelope import EventEnvelopeV1


def valid_event_data() -> dict[str, object]:
    return {
        "event_id": uuid4(),
        "event_type": "ServiceOrderOpened",
        "event_version": 1,
        "occurred_at": datetime(2026, 11, 8, 15, 30, tzinfo=UTC),
        "correlation_id": uuid4(),
        "causation_id": uuid4(),
        "saga_id": uuid4(),
        "order_id": uuid4(),
        "payload": {"customer_id": "customer-123"},
    }


def test_valid_envelope_round_trips_as_json() -> None:
    envelope = EventEnvelopeV1.model_validate(valid_event_data())

    restored = EventEnvelopeV1.model_validate_json(envelope.model_dump_json())

    assert restored == envelope
    assert isinstance(restored.event_id, UUID)
    assert restored.occurred_at.utcoffset() == UTC.utcoffset(restored.occurred_at)


@pytest.mark.parametrize(
    "required_field",
    [
        "event_id",
        "event_type",
        "occurred_at",
        "correlation_id",
        "causation_id",
        "saga_id",
        "order_id",
        "payload",
    ],
)
def test_envelope_rejects_a_missing_required_field(required_field: str) -> None:
    data = valid_event_data()
    del data[required_field]

    with pytest.raises(ValidationError):
        EventEnvelopeV1.model_validate(data)


def test_envelope_rejects_an_unsupported_version() -> None:
    data = valid_event_data()
    data["event_version"] = 2

    with pytest.raises(ValidationError):
        EventEnvelopeV1.model_validate(data)


def test_envelope_rejects_a_naive_timestamp() -> None:
    data = valid_event_data()
    data["occurred_at"] = datetime(2026, 11, 8, 15, 30)

    with pytest.raises(ValidationError):
        EventEnvelopeV1.model_validate(data)


def test_envelope_rejects_an_invalid_uuid() -> None:
    data = valid_event_data()
    data["event_id"] = "not-a-uuid"

    with pytest.raises(ValidationError):
        EventEnvelopeV1.model_validate(data)

