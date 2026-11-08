from src.domain.saga import PendingCommand
from src.infrastructure.database.models import OutboxMessageModel


def command_to_outbox(command: PendingCommand) -> OutboxMessageModel:
    return OutboxMessageModel(
        id=str(command.command_id),
        message_type=command.command_type,
        aggregate_id=str(command.order_id),
        occurred_at=command.occurred_at,
        payload={
            "event_id": str(command.command_id),
            "event_type": command.command_type,
            "event_version": 1,
            "occurred_at": command.occurred_at.isoformat(),
            "correlation_id": str(command.correlation_id),
            "causation_id": str(command.causation_id),
            "saga_id": str(command.saga_id),
            "order_id": str(command.order_id),
            "payload": command.payload,
        },
    )
