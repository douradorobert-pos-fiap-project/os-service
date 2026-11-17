from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.application.open_service_order import open_order
from src.application.process_saga_event import SagaProcessManager
from src.infrastructure.database.inbox import claim_event
from src.infrastructure.database.models import (
    Base,
    CustomerModel,
    OutboxMessageModel,
    ServiceOrderModel,
    VehicleModel,
)
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


def test_order_aggregate_flushes_parent_before_saga_foreign_key():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    order, saga, commands = opened_order_with_command()
    with factory.begin() as session:
        session.add(
            CustomerModel(
                id=str(order.customer_id), name="Smoke test", document="90000000001"
            )
        )
        session.add(
            VehicleModel(
                id=str(order.vehicle_id),
                customer_id=str(order.customer_id),
                license_plate="SMK0001",
                make="SMOKE",
                model="Synthetic",
                year=2026,
            )
        )

    with factory.begin() as session:
        persist_order_aggregate(session, order, saga, commands)

    with factory() as session:
        assert session.get(ServiceOrderModel, str(order.id)) is not None

    engine.dispose()
