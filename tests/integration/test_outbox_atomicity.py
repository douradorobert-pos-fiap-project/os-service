from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from src.application.open_service_order import open_order
from src.application.process_saga_event import SagaProcessManager
from src.infrastructure.database.inbox import claim_event
from src.infrastructure.database.models import OutboxMessageModel, ServiceOrderModel
from src.infrastructure.database.repositories import persist_order_aggregate
from src.infrastructure.messaging.envelope import EventEnvelopeV1


def opened_order_with_command():
    correlation_id = uuid4()
    order = open_order(uuid4(), uuid4(), correlation_id)
    process = SagaProcessManager(order)
    event_id = uuid4()
    commands = process.handle_event(
        EventEnvelopeV1(
            event_id=event_id,
            event_type="ServiceOrderOpenedV1",
            occurred_at=datetime(2026, 11, 8, 18, 0, tzinfo=UTC),
            correlation_id=correlation_id,
            causation_id=event_id,
            saga_id=order.saga_id,
            order_id=order.id,
            payload={},
        )
    )
    return order, process.saga, commands


def test_rollback_removes_both_order_and_outbox(
    session_factory: sessionmaker[Session],
) -> None:
    order, saga, commands = opened_order_with_command()

    with (
        pytest.raises(RuntimeError, match="simulated failure"),
        session_factory.begin() as session,
    ):
        persist_order_aggregate(session, order, saga, commands)
        raise RuntimeError("simulated failure")

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ServiceOrderModel)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxMessageModel)) == 0


def test_commit_persists_both_order_and_outbox(
    session_factory: sessionmaker[Session],
) -> None:
    order, saga, commands = opened_order_with_command()

    with session_factory.begin() as session:
        persist_order_aggregate(session, order, saga, commands)

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ServiceOrderModel)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxMessageModel)) == 1
        message = session.scalar(select(OutboxMessageModel))
        assert message is not None
        occurred_at = datetime.fromisoformat(message.payload["occurred_at"])
        assert occurred_at.tzinfo == UTC


def test_inbox_deduplicates_per_consumer(
    session_factory: sessionmaker[Session],
) -> None:
    event_id = uuid4()

    with session_factory.begin() as session:
        assert claim_event(session, event_id, "os-saga") is True
        assert claim_event(session, event_id, "os-saga") is False
        assert claim_event(session, event_id, "audit-projection") is True
