from dataclasses import dataclass, field
from uuid import UUID, uuid4

from src.domain.service_order_status import ServiceOrderStatus


class InvalidServiceOrderTransition(ValueError):
    """Raised when a requested status change violates the business lifecycle."""


_TRANSITIONS: dict[ServiceOrderStatus, set[ServiceOrderStatus]] = {
    ServiceOrderStatus.RECEIVED: {
        ServiceOrderStatus.DIAGNOSIS_PENDING,
        ServiceOrderStatus.CANCELLED,
    },
    ServiceOrderStatus.DIAGNOSIS_PENDING: {
        ServiceOrderStatus.DIAGNOSIS_COMPLETED,
        ServiceOrderStatus.CANCELLED,
    },
    ServiceOrderStatus.DIAGNOSIS_COMPLETED: {
        ServiceOrderStatus.AWAITING_APPROVAL,
        ServiceOrderStatus.CANCELLED,
    },
    ServiceOrderStatus.AWAITING_APPROVAL: {
        ServiceOrderStatus.EXECUTION_PENDING,
        ServiceOrderStatus.CANCELLED,
    },
    ServiceOrderStatus.EXECUTION_PENDING: {
        ServiceOrderStatus.IN_EXECUTION,
        ServiceOrderStatus.CANCELLED,
    },
    ServiceOrderStatus.IN_EXECUTION: {
        ServiceOrderStatus.COMPLETED,
        ServiceOrderStatus.MANUAL_INTERVENTION,
    },
    ServiceOrderStatus.COMPLETED: {
        ServiceOrderStatus.PAYMENT_PENDING,
        ServiceOrderStatus.MANUAL_INTERVENTION,
    },
    ServiceOrderStatus.PAYMENT_PENDING: {
        ServiceOrderStatus.PAID,
        ServiceOrderStatus.MANUAL_INTERVENTION,
    },
    ServiceOrderStatus.PAID: {
        ServiceOrderStatus.DELIVERED,
        ServiceOrderStatus.MANUAL_INTERVENTION,
    },
    ServiceOrderStatus.DELIVERED: {ServiceOrderStatus.MANUAL_INTERVENTION},
    ServiceOrderStatus.CANCELLED: set(),
    ServiceOrderStatus.MANUAL_INTERVENTION: set(),
}


@dataclass
class ServiceOrder:
    id: UUID
    customer_id: UUID
    vehicle_id: UUID
    saga_id: UUID
    correlation_id: UUID = field(default_factory=uuid4)
    status: ServiceOrderStatus = ServiceOrderStatus.RECEIVED

    def _transition_to(self, target: ServiceOrderStatus) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidServiceOrderTransition(f"{self.status} -> {target}")
        self.status = target

    def request_diagnosis(self) -> None:
        self._transition_to(ServiceOrderStatus.DIAGNOSIS_PENDING)

    def complete_diagnosis(self) -> None:
        self._transition_to(ServiceOrderStatus.DIAGNOSIS_COMPLETED)

    def receive_quote(self) -> None:
        self._transition_to(ServiceOrderStatus.AWAITING_APPROVAL)

    def approve_quote(self) -> None:
        self._transition_to(ServiceOrderStatus.EXECUTION_PENDING)

    def start_execution(self) -> None:
        self._transition_to(ServiceOrderStatus.IN_EXECUTION)

    def complete_execution(self) -> None:
        self._transition_to(ServiceOrderStatus.COMPLETED)

    def request_payment(self) -> None:
        self._transition_to(ServiceOrderStatus.PAYMENT_PENDING)

    def confirm_payment(self) -> None:
        self._transition_to(ServiceOrderStatus.PAID)

    def deliver(self) -> None:
        self._transition_to(ServiceOrderStatus.DELIVERED)

    def cancel(self) -> None:
        self._transition_to(ServiceOrderStatus.CANCELLED)

    def require_manual_intervention(self) -> None:
        self._transition_to(ServiceOrderStatus.MANUAL_INTERVENTION)
