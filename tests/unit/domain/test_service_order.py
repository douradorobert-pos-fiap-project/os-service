from uuid import uuid4

import pytest

from src.application.open_service_order import open_order
from src.domain.service_order import InvalidServiceOrderTransition, ServiceOrder
from src.domain.service_order_status import ServiceOrderStatus


def new_order() -> ServiceOrder:
    return ServiceOrder(
        id=uuid4(),
        customer_id=uuid4(),
        vehicle_id=uuid4(),
        saga_id=uuid4(),
    )


def test_open_order_starts_received_with_stable_business_ids() -> None:
    customer_id = uuid4()
    vehicle_id = uuid4()
    correlation_id = uuid4()

    order = open_order(customer_id, vehicle_id, correlation_id)

    assert order.customer_id == customer_id
    assert order.vehicle_id == vehicle_id
    assert order.correlation_id == correlation_id
    assert order.status is ServiceOrderStatus.RECEIVED


def test_order_follows_the_approved_distributed_happy_path() -> None:
    order = new_order()

    order.request_diagnosis()
    order.complete_diagnosis()
    order.receive_quote()
    order.approve_quote()
    order.start_execution()
    order.complete_execution()
    order.request_payment()
    order.confirm_payment()
    order.deliver()

    assert order.status is ServiceOrderStatus.DELIVERED


def test_order_cannot_be_delivered_before_payment_confirmation() -> None:
    order = new_order()

    with pytest.raises(InvalidServiceOrderTransition):
        order.deliver()

    assert order.status is ServiceOrderStatus.RECEIVED


def test_order_cannot_request_payment_before_execution_completion() -> None:
    order = new_order()
    order.request_diagnosis()
    order.complete_diagnosis()
    order.receive_quote()
    order.approve_quote()

    with pytest.raises(InvalidServiceOrderTransition):
        order.request_payment()

    assert order.status is ServiceOrderStatus.EXECUTION_PENDING


@pytest.mark.parametrize(
    "advance",
    [
        lambda order: order.request_diagnosis(),
        lambda order: (order.request_diagnosis(), order.complete_diagnosis()),
        lambda order: (
            order.request_diagnosis(),
            order.complete_diagnosis(),
            order.receive_quote(),
        ),
        lambda order: (
            order.request_diagnosis(),
            order.complete_diagnosis(),
            order.receive_quote(),
            order.approve_quote(),
        ),
    ],
)
def test_order_can_be_cancelled_before_repair_starts(advance) -> None:
    order = new_order()
    advance(order)

    order.cancel()

    assert order.status is ServiceOrderStatus.CANCELLED


def test_started_repair_requires_manual_intervention_instead_of_cancellation() -> None:
    order = new_order()
    order.request_diagnosis()
    order.complete_diagnosis()
    order.receive_quote()
    order.approve_quote()
    order.start_execution()

    with pytest.raises(InvalidServiceOrderTransition):
        order.cancel()

    order.require_manual_intervention()
    assert order.status is ServiceOrderStatus.MANUAL_INTERVENTION
