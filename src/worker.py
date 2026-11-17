import os
import time

from src.infrastructure.database.session import SessionFactory
from src.infrastructure.messaging.consumer import SQSConsumer
from src.infrastructure.messaging.handler import process_event
from src.infrastructure.messaging.outbox_relay import (
    OutboxRelay,
    SQLAlchemyOutboxStore,
)
from src.infrastructure.messaging.sqs_client import (
    SQS_LONG_POLL_WAIT_SECONDS,
    SQSClient,
)
from src.infrastructure.observability.logging import log_event


def main() -> None:
    environment = os.getenv("APP_ENV", "local")
    sqs = SQSClient.from_env()
    queue_urls = {
        service: sqs.queue_url(f"{environment}-{service}-events")
        for service in ("os-service", "billing-service", "execution-service")
    }
    inbox_url = queue_urls["os-service"]
    routes = {
        "DiagnosisRequestedV1": queue_urls["execution-service"],
        "QuoteGenerationRequestedV1": queue_urls["billing-service"],
        "ExecutionRequestedV1": queue_urls["execution-service"],
        "PaymentCreationRequestedV1": queue_urls["billing-service"],
    }
    relay = OutboxRelay(SQLAlchemyOutboxStore(SessionFactory), sqs, routes)
    consumer = SQSConsumer(sqs, inbox_url, wait_time_seconds=SQS_LONG_POLL_WAIT_SECONDS)
    log_event("worker.started", service="os-service")

    while True:
        relay.run_once()
        result = consumer.poll_once(
            lambda message: process_event(SessionFactory, message)
        )
        if result == "empty":
            time.sleep(0.5)


if __name__ == "__main__":
    main()
