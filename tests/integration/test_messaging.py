from datetime import UTC, datetime
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from moto import mock_aws
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.database.inbox import claim_event
from src.infrastructure.database.models import Base, OutboxMessageModel
from src.infrastructure.messaging.consumer import SQSConsumer
from src.infrastructure.messaging.outbox_relay import (
    OutboxRelay,
    SQLAlchemyOutboxStore,
)
from src.infrastructure.messaging.sqs_client import SQSClient


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def queues():
    with mock_aws(config={"core": {"service_whitelist": ["sqs"]}}):
        client = boto3.client(
            "sqs",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
        dlq_url = client.create_queue(QueueName="orders-dlq")["QueueUrl"]
        dlq_arn = client.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        queue_url = client.create_queue(
            QueueName="orders",
            Attributes={
                "VisibilityTimeout": "0",
                "RedrivePolicy": (
                    '{"deadLetterTargetArn":"' + dlq_arn + '","maxReceiveCount":"3"}'
                ),
            },
        )["QueueUrl"]
        yield client, queue_url, dlq_url


def envelope(event_id=None, event_type="ServiceOrderCreatedV1") -> dict:
    identifier = event_id or uuid4()
    return {
        "event_id": str(identifier),
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": "2026-11-11T12:00:00+00:00",
        "correlation_id": str(uuid4()),
        "causation_id": str(uuid4()),
        "saga_id": str(uuid4()),
        "order_id": str(uuid4()),
        "payload": {"status": "RECEIVED"},
    }


def test_sqs_client_reads_elasticmq_endpoint_from_environment(monkeypatch):
    monkeypatch.setenv("SQS_ENDPOINT_URL", "http://elasticmq:9324")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")

    client = SQSClient.from_env()

    assert client.endpoint_url == "http://elasticmq:9324"


def test_consumer_acknowledges_only_after_committed_idempotent_handler(
    queues, session_factory
):
    raw_client, queue_url, _ = queues
    sqs = SQSClient(raw_client)
    event_id = uuid4()
    sqs.send(queue_url, envelope(event_id))
    sqs.send(queue_url, envelope(event_id))
    side_effects: list[str] = []

    def handler(message: dict) -> None:
        with session_factory.begin() as session:
            if claim_event(session, event_id, "orders-test"):
                side_effects.append(message["event_type"])

    consumer = SQSConsumer(sqs, queue_url)
    assert consumer.poll_once(handler) == "processed"
    assert consumer.poll_once(handler) == "processed"
    assert consumer.poll_once(handler) == "empty"
    assert side_effects == ["ServiceOrderCreatedV1"]


def test_poison_message_is_not_acknowledged_and_reaches_dlq(queues):
    raw_client, queue_url, dlq_url = queues
    sqs = SQSClient(raw_client)
    raw_client.send_message(QueueUrl=queue_url, MessageBody="not-json")
    consumer = SQSConsumer(sqs, queue_url)

    assert [consumer.poll_once(lambda message: None) for _ in range(3)] == [
        "failed",
        "failed",
        "failed",
    ]

    assert consumer.poll_once(lambda message: None) == "empty"
    assert len(sqs.receive(dlq_url)) == 1


def test_out_of_order_event_remains_available_for_retry(queues):
    _, queue_url, _ = queues
    sqs = SQSClient(queues[0])
    sqs.send(queue_url, envelope(event_type="PaymentConfirmedV1"))

    def reject(message: dict) -> None:
        raise RuntimeError("execution must complete first")

    consumer = SQSConsumer(sqs, queue_url)
    assert consumer.poll_once(reject) == "failed"
    assert consumer.poll_once(lambda message: None) == "processed"


def test_relay_leases_and_publishes_outbox(queues, session_factory):
    _, queue_url, _ = queues
    message = OutboxMessageModel(
        id=str(uuid4()),
        message_type="ServiceOrderCreatedV1",
        aggregate_id=str(uuid4()),
        payload=envelope(),
    )
    with session_factory.begin() as session:
        session.add(message)
    store = SQLAlchemyOutboxStore(session_factory)
    relay = OutboxRelay(store, SQSClient(queues[0]), queue_url)

    assert relay.run_once() == 1

    with session_factory() as session:
        saved = session.get(OutboxMessageModel, message.id)
        assert saved.published_at is not None
        assert saved.lease_until is None
    assert (
        SQSClient(queues[0]).receive(queue_url)[0].body["event_id"]
        == message.payload["event_id"]
    )


def test_relay_failure_schedules_exponential_retry(session_factory):
    message = OutboxMessageModel(
        id=str(uuid4()),
        message_type="ServiceOrderCreatedV1",
        aggregate_id=str(uuid4()),
        payload=envelope(),
    )
    with session_factory.begin() as session:
        session.add(message)

    class UnavailableSQS:
        def send(self, queue_url, payload):
            raise EndpointConnectionError(endpoint_url="http://unavailable")

    relay = OutboxRelay(
        SQLAlchemyOutboxStore(session_factory),
        UnavailableSQS(),
        "http://queue",
        base_retry_seconds=2,
    )
    before = datetime.now(UTC)

    assert relay.run_once() == 0

    with session_factory() as session:
        saved = session.scalar(
            select(OutboxMessageModel).where(OutboxMessageModel.id == message.id)
        )
        assert saved.attempts == 1
        assert saved.next_attempt_at.replace(tzinfo=UTC) >= before
        assert saved.lease_until is None
