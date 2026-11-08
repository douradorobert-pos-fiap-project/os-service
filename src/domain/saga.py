from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class SagaState(StrEnum):
    STARTED = "STARTED"
    WAITING_DIAGNOSIS = "WAITING_DIAGNOSIS"
    WAITING_QUOTE = "WAITING_QUOTE"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_EXECUTION = "WAITING_EXECUTION"
    IN_EXECUTION = "IN_EXECUTION"
    WAITING_PAYMENT = "WAITING_PAYMENT"
    COMPLETED = "COMPLETED"
    COMPENSATED = "COMPENSATED"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class InvalidSagaEvent(ValueError):
    """Raised when an event cannot be applied in the current Saga state."""


@dataclass(frozen=True)
class PendingCommand:
    command_id: UUID
    command_type: str
    saga_id: UUID
    order_id: UUID
    correlation_id: UUID
    causation_id: UUID
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceOrderSaga:
    id: UUID
    order_id: UUID
    state: SagaState = SagaState.STARTED
    processed_event_ids: set[UUID] = field(default_factory=set)
