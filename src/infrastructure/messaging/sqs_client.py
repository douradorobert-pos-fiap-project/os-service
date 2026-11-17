import json
import os
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config

from src.infrastructure.observability.logging import bind_context, log_event
from src.infrastructure.observability.telemetry import record_event


@dataclass(frozen=True)
class ReceivedMessage:
    body: dict[str, Any] | None
    receipt_handle: str
    receive_count: int


class SQSClient:
    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> "SQSClient":
        endpoint_url = os.getenv("SQS_ENDPOINT_URL") or None
        options: dict[str, Any] = {
            "service_name": "sqs",
            "region_name": os.getenv("AWS_REGION", "us-east-1"),
            "endpoint_url": endpoint_url,
            "config": Config(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=2,
                read_timeout=2,
            ),
        }
        if endpoint_url:
            options["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "local")
            options["aws_secret_access_key"] = os.getenv(
                "AWS_SECRET_ACCESS_KEY", "local"
            )
        return cls(boto3.client(**options))

    @property
    def endpoint_url(self) -> str:
        return self._client.meta.endpoint_url

    def send(self, queue_url: str, envelope: dict[str, Any]) -> str:
        with bind_context(
            correlation_id=envelope.get("correlation_id"),
            saga_id=envelope.get("saga_id"),
            order_id=envelope.get("order_id"),
        ):
            response = self._client.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(envelope, separators=(",", ":")),
            )
            attributes = {
                "event_id": envelope.get("event_id"),
                "event_type": envelope.get("event_type"),
                "message_id": response["MessageId"],
            }
            log_event("message.published", **attributes)
            record_event("MessagePublished", attributes)
        return response["MessageId"]

    def queue_url(self, queue_name: str) -> str:
        return self._client.get_queue_url(QueueName=queue_name)["QueueUrl"]

    def receive(
        self, queue_url: str, wait_time_seconds: int = 0
    ) -> list[ReceivedMessage]:
        response = self._client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_time_seconds,
            AttributeNames=["ApproximateReceiveCount"],
        )
        received = []
        for message in response.get("Messages", []):
            try:
                body = json.loads(message["Body"])
            except (json.JSONDecodeError, TypeError):
                body = None
            received.append(
                ReceivedMessage(
                    body=body if isinstance(body, dict) else None,
                    receipt_handle=message["ReceiptHandle"],
                    receive_count=int(
                        message.get("Attributes", {}).get(
                            "ApproximateReceiveCount", "1"
                        )
                    ),
                )
            )
        return received

    def delete(self, queue_url: str, receipt_handle: str) -> None:
        self._client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
