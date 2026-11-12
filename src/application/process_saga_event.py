from collections.abc import Callable
from uuid import NAMESPACE_URL, uuid5

from src.domain.saga import (
    InvalidSagaEvent,
    PendingCommand,
    SagaState,
    ServiceOrderSaga,
)
from src.domain.service_order import ServiceOrder
from src.infrastructure.messaging.envelope import EventEnvelopeV1
from src.infrastructure.observability.logging import bind_context, log_event
from src.infrastructure.observability.telemetry import record_event


class SagaProcessManager:
    """Coordinate the service-order Saga without owning participant rules."""

    def __init__(self, order: ServiceOrder) -> None:
        self.order = order
        self.saga = ServiceOrderSaga(id=order.saga_id, order_id=order.id)

    def handle_event(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        if event.event_id in self.saga.processed_event_ids:
            log_event(
                "saga.duplicate", event_id=event.event_id, event_type=event.event_type
            )
            return []
        self._validate_identity(event)

        handler = self._handlers().get((self.saga.state, event.event_type))
        if handler is None:
            raise InvalidSagaEvent(
                f"{self.saga.state} cannot handle {event.event_type}"
            )

        previous_state = self.saga.state
        with bind_context(
            correlation_id=event.correlation_id,
            saga_id=event.saga_id,
            order_id=event.order_id,
        ):
            commands = handler(event)
            attributes = {
                "event_type": event.event_type,
                "previous_state": previous_state.value,
                "current_state": self.saga.state.value,
                "event_id": str(event.event_id),
            }
            log_event("saga.transition", **attributes)
            record_event("SagaTransition", attributes)
        self.saga.processed_event_ids.add(event.event_id)
        return commands

    def _validate_identity(self, event: EventEnvelopeV1) -> None:
        if event.saga_id != self.saga.id or event.order_id != self.order.id:
            raise InvalidSagaEvent("event does not belong to this service-order Saga")

    def _handlers(
        self,
    ) -> dict[tuple[SagaState, str], Callable[[EventEnvelopeV1], list[PendingCommand]]]:
        return {
            (SagaState.STARTED, "ServiceOrderOpenedV1"): self._order_opened,
            (SagaState.WAITING_DIAGNOSIS, "DiagnosisCompletedV1"): (
                self._diagnosis_completed
            ),
            (SagaState.WAITING_QUOTE, "QuoteGeneratedV1"): self._quote_generated,
            (SagaState.WAITING_APPROVAL, "QuoteApprovedV1"): self._quote_approved,
            (SagaState.WAITING_APPROVAL, "QuoteRejectedV1"): self._quote_rejected,
            (SagaState.WAITING_EXECUTION, "ExecutionStartedV1"): (
                self._execution_started
            ),
            (SagaState.WAITING_EXECUTION, "ExecutionFailedV1"): (
                self._execution_failed_before_start
            ),
            (SagaState.WAITING_EXECUTION, "ExecutionCancelledV1"): (
                self._execution_failed_before_start
            ),
            (SagaState.IN_EXECUTION, "ExecutionCompletedV1"): (
                self._execution_completed
            ),
            (SagaState.IN_EXECUTION, "ExecutionFailedV1"): (
                self._execution_failed_after_start
            ),
            (SagaState.WAITING_PAYMENT, "PaymentPendingV1"): self._payment_pending,
            (SagaState.WAITING_PAYMENT, "PaymentConfirmedV1"): self._payment_confirmed,
        }

    def _command(self, event: EventEnvelopeV1, command_type: str) -> PendingCommand:
        command_id = uuid5(
            NAMESPACE_URL, f"{self.saga.id}:{event.event_id}:{command_type}"
        )
        return PendingCommand(
            command_id=command_id,
            command_type=command_type,
            saga_id=self.saga.id,
            order_id=self.order.id,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            occurred_at=event.occurred_at,
        )

    def _order_opened(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        self.order.request_diagnosis()
        self.saga.state = SagaState.WAITING_DIAGNOSIS
        return [self._command(event, "DiagnosisRequestedV1")]

    def _diagnosis_completed(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        self.order.complete_diagnosis()
        self.saga.state = SagaState.WAITING_QUOTE
        return [self._command(event, "QuoteGenerationRequestedV1")]

    def _quote_generated(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        self.order.receive_quote()
        self.saga.state = SagaState.WAITING_APPROVAL
        return []

    def _quote_approved(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        self.order.approve_quote()
        self.saga.state = SagaState.WAITING_EXECUTION
        return [self._command(event, "ExecutionRequestedV1")]

    def _quote_rejected(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        self.order.cancel()
        self.saga.state = SagaState.COMPENSATED
        return []

    def _execution_started(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        self.order.start_execution()
        self.saga.state = SagaState.IN_EXECUTION
        return []

    def _execution_failed_before_start(
        self, event: EventEnvelopeV1
    ) -> list[PendingCommand]:
        self.order.cancel()
        self.saga.state = SagaState.COMPENSATED
        return []

    def _execution_completed(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        self.order.complete_execution()
        self.order.request_payment()
        self.saga.state = SagaState.WAITING_PAYMENT
        return [self._command(event, "PaymentCreationRequestedV1")]

    def _execution_failed_after_start(
        self, event: EventEnvelopeV1
    ) -> list[PendingCommand]:
        self.order.require_manual_intervention()
        self.saga.state = SagaState.MANUAL_INTERVENTION
        return []

    def _payment_pending(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        return []

    def _payment_confirmed(self, event: EventEnvelopeV1) -> list[PendingCommand]:
        self.order.confirm_payment()
        self.order.deliver()
        self.saga.state = SagaState.COMPLETED
        return []
