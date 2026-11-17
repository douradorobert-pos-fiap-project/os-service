from collections.abc import Callable
from typing import Any

from src.infrastructure.messaging.envelope import EventEnvelopeV1
from src.infrastructure.messaging.sqs_client import SQSClient
from src.infrastructure.observability.logging import bind_context, log_event
from src.infrastructure.observability.telemetry import record_event


class SQSConsumer:
    def __init__(
        self, sqs: SQSClient, queue_url: str, wait_time_seconds: int = 0
    ) -> None:
        self._sqs = sqs
        self._queue_url = queue_url
        self._wait_time_seconds = wait_time_seconds

    def poll_once(self, handler: Callable[[dict[str, Any]], Any]) -> str:
        messages = self._sqs.receive(self._queue_url, self._wait_time_seconds)
        if not messages:
            return "empty"
        message = messages[0]
        try:
            if message.body is None:
                log_event("message.invalid", receive_count=message.receive_count)
                return "failed"
            envelope = EventEnvelopeV1.model_validate(message.body)
            with bind_context(
                correlation_id=envelope.correlation_id,
                saga_id=envelope.saga_id,
                order_id=envelope.order_id,
            ):
                handler(envelope.model_dump(mode="json"))
                attributes = {
                    "event_id": str(envelope.event_id),
                    "event_type": envelope.event_type,
                    "receive_count": message.receive_count,
                }
                log_event("message.consumed", **attributes)
                record_event("MessageConsumed", attributes)
        except Exception as exc:  # noqa: BLE001 - handler failure stays unacked
            log_event(
                "message.failed",
                error_type=type(exc).__name__,
                receive_count=message.receive_count,
            )
            return "failed"
        self._sqs.delete(self._queue_url, message.receipt_handle)
        return "processed"
