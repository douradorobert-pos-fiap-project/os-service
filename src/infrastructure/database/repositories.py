from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.saga import PendingCommand, ServiceOrderSaga
from src.domain.service_order import ServiceOrder
from src.domain.service_order_status import ServiceOrderStatus
from src.infrastructure.database.models import (
    CustomerModel,
    SagaModel,
    ServiceOrderHistoryModel,
    ServiceOrderModel,
    VehicleModel,
)
from src.infrastructure.database.outbox import command_to_outbox


def persist_order_aggregate(
    session: Session,
    order: ServiceOrder,
    saga: ServiceOrderSaga,
    commands: list[PendingCommand],
) -> None:
    session.add(
        ServiceOrderModel(
            id=str(order.id),
            customer_id=str(order.customer_id),
            vehicle_id=str(order.vehicle_id),
            saga_id=str(order.saga_id),
            correlation_id=str(order.correlation_id),
            status=order.status.value,
        )
    )
    session.add(
        SagaModel(
            id=str(saga.id),
            order_id=str(order.id),
            state=saga.state.value,
            processed_event_ids=sorted(
                str(value) for value in saga.processed_event_ids
            ),
        )
    )
    session.add(
        ServiceOrderHistoryModel(order_id=str(order.id), status=order.status.value)
    )
    session.add_all(command_to_outbox(command) for command in commands)


def get_order(session: Session, order_id: UUID) -> ServiceOrder | None:
    model = session.get(ServiceOrderModel, str(order_id))
    if model is None:
        return None
    return ServiceOrder(
        id=UUID(model.id),
        customer_id=UUID(model.customer_id),
        vehicle_id=UUID(model.vehicle_id),
        saga_id=UUID(model.saga_id),
        correlation_id=UUID(model.correlation_id),
        status=ServiceOrderStatus(model.status),
    )


def get_history(session: Session, order_id: UUID) -> list[ServiceOrderHistoryModel]:
    return list(
        session.scalars(
            select(ServiceOrderHistoryModel)
            .where(ServiceOrderHistoryModel.order_id == str(order_id))
            .order_by(ServiceOrderHistoryModel.occurred_at)
        )
    )


def get_customer(session: Session, customer_id: UUID) -> CustomerModel | None:
    return session.get(CustomerModel, str(customer_id))


def get_vehicle(session: Session, vehicle_id: UUID) -> VehicleModel | None:
    return session.get(VehicleModel, str(vehicle_id))
