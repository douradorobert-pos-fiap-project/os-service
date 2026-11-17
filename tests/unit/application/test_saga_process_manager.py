from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.application.process_saga_event import SagaProcessManager
from src.domain.saga import InvalidSagaEvent, SagaState
from src.domain.service_order import ServiceOrder
from src.domain.service_order_status import ServiceOrderStatus
from src.infrastructure.messaging.envelope import EventEnvelopeV1


def envelope(
    event_type: str,
    *,
    saga_id: UUID,
    order_id: UUID,
    event_id: UUID | None = None,
    payload: dict | None = None,
) -> EventEnvelopeV1:
    identifier = event_id or uuid4()
    return EventEnvelopeV1(
        event_id=identifier,
        event_type=event_type,
        event_version=1,
        occurred_at=datetime(2026, 11, 8, 18, 0, tzinfo=UTC),
        correlation_id=uuid4(),
        causation_id=uuid4(),
        saga_id=saga_id,
        order_id=order_id,
        payload=payload or {},
    )


def manager() -> SagaProcessManager:
    saga_id = uuid4()
    order = ServiceOrder(
        id=uuid4(), customer_id=uuid4(), vehicle_id=uuid4(), saga_id=saga_id
    )
    return SagaProcessManager(order)


def test_saga_generates_the_happy_path_commands() -> None:
    process = manager()
    recommended_service_id = uuid4()
    sequence = [
        ("ServiceOrderOpenedV1", "DiagnosisRequestedV1"),
        ("DiagnosisCompletedV1", "QuoteGenerationRequestedV1"),
        ("QuoteGeneratedV1", None),
        ("QuoteApprovedV1", "ExecutionRequestedV1"),
        ("ExecutionStartedV1", None),
        ("ExecutionCompletedV1", "PaymentCreationRequestedV1"),
        ("PaymentPendingV1", None),
        ("PaymentConfirmedV1", None),
    ]

    for event_type, expected_command in sequence:
        commands = process.handle_event(
            envelope(
                event_type,
                saga_id=process.saga.id,
                order_id=process.order.id,
                payload=(
                    {"recommended_service_ids": [str(recommended_service_id)]}
                    if event_type == "DiagnosisCompletedV1"
                    else None
                ),
            )
        )
        assert [command.command_type for command in commands] == (
            [expected_command] if expected_command else []
        )
        if event_type == "DiagnosisCompletedV1":
            assert commands[0].payload == {
                "recommended_service_ids": [str(recommended_service_id)]
            }

    assert process.order.status is ServiceOrderStatus.DELIVERED
    assert process.saga.state is SagaState.COMPLETED


def test_duplicate_event_is_acknowledged_without_a_second_command() -> None:
    process = manager()
    event_id = uuid4()
    opened = envelope(
        "ServiceOrderOpenedV1",
        saga_id=process.saga.id,
        order_id=process.order.id,
        event_id=event_id,
    )

    first = process.handle_event(opened)
    duplicate = process.handle_event(opened)

    assert len(first) == 1
    assert duplicate == []


def test_same_event_always_produces_the_same_command_id() -> None:
    process_a = manager()
    process_b = SagaProcessManager(
        ServiceOrder(
            id=process_a.order.id,
            customer_id=process_a.order.customer_id,
            vehicle_id=process_a.order.vehicle_id,
            saga_id=process_a.saga.id,
        )
    )
    opened = envelope(
        "ServiceOrderOpenedV1",
        saga_id=process_a.saga.id,
        order_id=process_a.order.id,
    )

    command_a = process_a.handle_event(opened)[0]
    command_b = process_b.handle_event(opened)[0]

    assert command_a.command_id == command_b.command_id


def test_out_of_order_event_does_not_advance_or_deduplicate_the_saga() -> None:
    process = manager()
    approved = envelope(
        "QuoteApprovedV1",
        saga_id=process.saga.id,
        order_id=process.order.id,
    )

    with pytest.raises(InvalidSagaEvent):
        process.handle_event(approved)

    assert process.saga.state is SagaState.STARTED
    assert approved.event_id not in process.saga.processed_event_ids


def test_quote_rejection_compensates_before_execution() -> None:
    process = manager()
    for event_type in (
        "ServiceOrderOpenedV1",
        "DiagnosisCompletedV1",
        "QuoteGeneratedV1",
    ):
        process.handle_event(
            envelope(
                event_type,
                saga_id=process.saga.id,
                order_id=process.order.id,
            )
        )

    commands = process.handle_event(
        envelope(
            "QuoteRejectedV1",
            saga_id=process.saga.id,
            order_id=process.order.id,
        )
    )

    assert commands == []
    assert process.order.status is ServiceOrderStatus.CANCELLED
    assert process.saga.state is SagaState.COMPENSATED


def test_execution_failure_after_start_requires_manual_intervention() -> None:
    process = manager()
    for event_type in (
        "ServiceOrderOpenedV1",
        "DiagnosisCompletedV1",
        "QuoteGeneratedV1",
        "QuoteApprovedV1",
        "ExecutionStartedV1",
    ):
        process.handle_event(
            envelope(
                event_type,
                saga_id=process.saga.id,
                order_id=process.order.id,
            )
        )

    commands = process.handle_event(
        envelope(
            "ExecutionFailedV1",
            saga_id=process.saga.id,
            order_id=process.order.id,
        )
    )

    assert commands == []
    assert process.order.status is ServiceOrderStatus.MANUAL_INTERVENTION
    assert process.saga.state is SagaState.MANUAL_INTERVENTION


def test_execution_cancellation_before_start_compensates_saga() -> None:
    process = manager()
    for event_type in (
        "ServiceOrderOpenedV1",
        "DiagnosisCompletedV1",
        "QuoteGeneratedV1",
        "QuoteApprovedV1",
    ):
        process.handle_event(
            envelope(
                event_type,
                saga_id=process.saga.id,
                order_id=process.order.id,
            )
        )

    commands = process.handle_event(
        envelope(
            "ExecutionCancelledV1",
            saga_id=process.saga.id,
            order_id=process.order.id,
        )
    )

    assert commands == []
    assert process.order.status is ServiceOrderStatus.CANCELLED
    assert process.saga.state is SagaState.COMPENSATED


def test_payment_rejection_requires_manual_intervention() -> None:
    process = manager()
    for event_type in (
        "ServiceOrderOpenedV1",
        "DiagnosisCompletedV1",
        "QuoteGeneratedV1",
        "QuoteApprovedV1",
        "ExecutionStartedV1",
        "ExecutionCompletedV1",
    ):
        process.handle_event(
            envelope(
                event_type,
                saga_id=process.saga.id,
                order_id=process.order.id,
            )
        )

    process.handle_event(
        envelope(
            "PaymentRejectedV1",
            saga_id=process.saga.id,
            order_id=process.order.id,
        )
    )

    assert process.order.status is ServiceOrderStatus.MANUAL_INTERVENTION
    assert process.saga.state is SagaState.MANUAL_INTERVENTION


def test_payment_refund_moves_delivered_order_to_manual_intervention() -> None:
    process = manager()
    for event_type in (
        "ServiceOrderOpenedV1",
        "DiagnosisCompletedV1",
        "QuoteGeneratedV1",
        "QuoteApprovedV1",
        "ExecutionStartedV1",
        "ExecutionCompletedV1",
        "PaymentPendingV1",
        "PaymentConfirmedV1",
    ):
        process.handle_event(
            envelope(
                event_type,
                saga_id=process.saga.id,
                order_id=process.order.id,
            )
        )

    process.handle_event(
        envelope(
            "PaymentRefundedV1",
            saga_id=process.saga.id,
            order_id=process.order.id,
        )
    )

    assert process.order.status is ServiceOrderStatus.MANUAL_INTERVENTION
    assert process.saga.state is SagaState.MANUAL_INTERVENTION
