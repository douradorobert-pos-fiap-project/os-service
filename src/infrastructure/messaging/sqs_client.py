import json
import os
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config


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
        response = self._client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(envelope, separators=(",", ":")),
        )
        return response["MessageId"]

    def receive(self, queue_url: str) -> list[ReceivedMessage]:
        response = self._client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=0,
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
        self._client.delete_message(
            QueueUrl=queue_url, ReceiptHandle=receipt_handle
        )
