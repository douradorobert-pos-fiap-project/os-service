from collections.abc import Callable
from typing import Any

from src.infrastructure.messaging.envelope import EventEnvelopeV1
from src.infrastructure.messaging.sqs_client import SQSClient


class SQSConsumer:
    def __init__(self, sqs: SQSClient, queue_url: str) -> None:
        self._sqs = sqs
        self._queue_url = queue_url

    def poll_once(self, handler: Callable[[dict[str, Any]], None]) -> str:
        messages = self._sqs.receive(self._queue_url)
        if not messages:
            return "empty"
        message = messages[0]
        try:
            if message.body is None:
                return "failed"
            envelope = EventEnvelopeV1.model_validate(message.body)
            handler(envelope.model_dump(mode="json"))
        except Exception:  # noqa: BLE001 - any handler failure must leave unacked
            return "failed"
        self._sqs.delete(self._queue_url, message.receipt_handle)
        return "processed"
