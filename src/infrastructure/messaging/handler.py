from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.application.process_saga_event import SagaProcessManager
from src.domain.saga import SagaState, ServiceOrderSaga
from src.domain.service_order import ServiceOrder
from src.domain.service_order_status import ServiceOrderStatus
from src.infrastructure.database.inbox import claim_event
from src.infrastructure.database.models import (
    SagaModel,
    ServiceOrderHistoryModel,
    ServiceOrderModel,
)
from src.infrastructure.database.outbox import command_to_outbox
from src.infrastructure.messaging.envelope import EventEnvelopeV1

CONSUMER_NAME = "os-saga"


def process_event(
    session_factory: sessionmaker[Session], message: dict[str, Any]
) -> bool:
    event = EventEnvelopeV1.model_validate(message)
    with session_factory.begin() as session:
        if not claim_event(session, event.event_id, CONSUMER_NAME):
            return False

        order_model = session.scalar(
            select(ServiceOrderModel)
            .where(ServiceOrderModel.id == str(event.order_id))
            .with_for_update()
        )
        saga_model = session.scalar(
            select(SagaModel)
            .where(SagaModel.id == str(event.saga_id))
            .with_for_update()
        )
        if order_model is None or saga_model is None:
            raise LookupError("service-order saga aggregate not found")

        order = ServiceOrder(
            id=UUID(order_model.id),
            customer_id=UUID(order_model.customer_id),
            vehicle_id=UUID(order_model.vehicle_id),
            saga_id=UUID(order_model.saga_id),
            correlation_id=UUID(order_model.correlation_id),
            status=ServiceOrderStatus(order_model.status),
        )
        saga = ServiceOrderSaga(
            id=UUID(saga_model.id),
            order_id=UUID(saga_model.order_id),
            state=SagaState(saga_model.state),
            processed_event_ids={
                UUID(value) for value in saga_model.processed_event_ids
            },
        )
        manager = SagaProcessManager(order, saga)
        previous_status = order.status
        commands = manager.handle_event(event)

        order_model.status = order.status.value
        saga_model.state = manager.saga.state.value
        saga_model.processed_event_ids = sorted(
            str(value) for value in manager.saga.processed_event_ids
        )
        if order.status is not previous_status:
            session.add(
                ServiceOrderHistoryModel(
                    order_id=str(order.id), status=order.status.value
                )
            )
        session.add_all(command_to_outbox(command) for command in commands)
        session.flush()
    return True
