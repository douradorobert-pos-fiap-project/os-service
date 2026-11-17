from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from src.infrastructure.database.models import (
    InboxMessageModel,
    OutboxMessageModel,
    SagaModel,
    ServiceOrderHistoryModel,
    ServiceOrderModel,
)
from src.infrastructure.messaging.envelope import EventEnvelopeV1
from src.infrastructure.messaging.handler import process_event


def test_diagnosis_event_advances_saga_and_is_idempotent(client, session_factory):
    customer = client.post(
        "/api/v1/customers", json={"name": "Test customer", "document": "12345678901"}
    ).json()
    vehicle = client.post(
        "/api/v1/vehicles",
        json={
            "customer_id": customer["id"],
            "license_plate": "ABC1234",
            "make": "Test",
            "model": "Car",
            "year": 2020,
        },
    ).json()
    order = client.post(
        "/api/v1/service-orders",
        json={"customer_id": customer["id"], "vehicle_id": vehicle["id"]},
    ).json()
    event = EventEnvelopeV1(
        event_id=uuid4(),
        event_type="DiagnosisCompletedV1",
        occurred_at=datetime.now(UTC),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        saga_id=order["saga_id"],
        order_id=order["id"],
        payload={"recommended_service_ids": [str(uuid4())]},
    )

    assert process_event(session_factory, event.model_dump(mode="json")) is True
    assert process_event(session_factory, event.model_dump(mode="json")) is False

    with session_factory() as session:
        saved_order = session.get(ServiceOrderModel, order["id"])
        saved_saga = session.get(SagaModel, order["saga_id"])
        messages = session.scalars(select(OutboxMessageModel)).all()
        receipts = session.scalars(select(InboxMessageModel)).all()
        history = session.scalars(select(ServiceOrderHistoryModel)).all()

    assert saved_order.status == "DIAGNOSIS_COMPLETED"
    assert saved_saga.state == "WAITING_QUOTE"
    assert [message.message_type for message in messages] == [
        "DiagnosisRequestedV1",
        "QuoteGenerationRequestedV1",
    ]
    assert messages[-1].payload["payload"]["recommended_service_ids"]
    assert len(receipts) == 1
    assert [entry.status for entry in history] == [
        "DIAGNOSIS_PENDING",
        "DIAGNOSIS_COMPLETED",
    ]
