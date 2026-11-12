from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from src.api.dependencies import SessionDep
from src.application.open_service_order import open_order
from src.application.process_saga_event import SagaProcessManager
from src.infrastructure.database.repositories import (
    get_customer,
    get_history,
    get_order,
    get_vehicle,
    persist_order_aggregate,
)
from src.infrastructure.messaging.envelope import EventEnvelopeV1

router = APIRouter(prefix="/api/v1/service-orders", tags=["service-orders"])


class ServiceOrderCreate(BaseModel):
    customer_id: UUID
    vehicle_id: UUID


class ServiceOrderResponse(BaseModel):
    id: UUID
    customer_id: UUID
    vehicle_id: UUID
    saga_id: UUID
    status: str


class HistoryResponse(BaseModel):
    status: str
    occurred_at: datetime


def to_response(order) -> ServiceOrderResponse:
    return ServiceOrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        vehicle_id=order.vehicle_id,
        saga_id=order.saga_id,
        status=order.status.value,
    )


@router.post("", response_model=ServiceOrderResponse, status_code=status.HTTP_201_CREATED)
def create_service_order(
    data: ServiceOrderCreate,
    request: Request,
    session: SessionDep,
) -> ServiceOrderResponse:
    correlation_id: UUID = request.state.correlation_id
    with session.begin():
        if get_customer(session, data.customer_id) is None:
            raise HTTPException(status_code=404, detail="customer not found")
        vehicle = get_vehicle(session, data.vehicle_id)
        if vehicle is None:
            raise HTTPException(status_code=404, detail="vehicle not found")
        if vehicle.customer_id != str(data.customer_id):
            raise HTTPException(
                status_code=409, detail="vehicle does not belong to customer"
            )

        order = open_order(data.customer_id, data.vehicle_id, correlation_id)
        process = SagaProcessManager(order)
        opened_id = uuid4()
        commands = process.handle_event(
            EventEnvelopeV1(
                event_id=opened_id,
                event_type="ServiceOrderOpenedV1",
                occurred_at=datetime.now(UTC),
                correlation_id=correlation_id,
                causation_id=opened_id,
                saga_id=order.saga_id,
                order_id=order.id,
                payload={},
            )
        )
        persist_order_aggregate(session, order, process.saga, commands)
    return to_response(order)


@router.get("/{order_id}", response_model=ServiceOrderResponse)
def detail_service_order(
    order_id: UUID, session: SessionDep
) -> ServiceOrderResponse:
    order = get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="service order not found")
    return to_response(order)


@router.get("/{order_id}/history", response_model=list[HistoryResponse])
def service_order_history(
    order_id: UUID, session: SessionDep
) -> list[HistoryResponse]:
    if get_order(session, order_id) is None:
        raise HTTPException(status_code=404, detail="service order not found")
    return [
        HistoryResponse(status=entry.status, occurred_at=entry.occurred_at)
        for entry in get_history(session, order_id)
    ]
