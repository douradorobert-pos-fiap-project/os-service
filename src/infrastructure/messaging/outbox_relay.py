from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from src.infrastructure.database.models import OutboxMessageModel


@dataclass(frozen=True)
class OutboxRecord:
    id: str
    payload: dict[str, Any]
    attempts: int


class SQLAlchemyOutboxStore:
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def claim_batch(self, limit: int, lease_seconds: int) -> list[OutboxRecord]:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            messages = session.scalars(
                select(OutboxMessageModel)
                .where(
                    OutboxMessageModel.published_at.is_(None),
                    or_(
                        OutboxMessageModel.lease_until.is_(None),
                        OutboxMessageModel.lease_until < now,
                    ),
                    or_(
                        OutboxMessageModel.next_attempt_at.is_(None),
                        OutboxMessageModel.next_attempt_at <= now,
                    ),
                )
                .order_by(OutboxMessageModel.occurred_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            lease_until = now + timedelta(seconds=lease_seconds)
            for message in messages:
                message.lease_until = lease_until
            return [
                OutboxRecord(
                    id=message.id,
                    payload=message.payload,
                    attempts=message.attempts,
                )
                for message in messages
            ]

    def mark_published(self, message_id: str) -> None:
        with self._session_factory.begin() as session:
            message = session.get(OutboxMessageModel, message_id)
            message.published_at = datetime.now(UTC)
            message.lease_until = None

    def mark_failed(self, message_id: str, delay_seconds: int) -> None:
        with self._session_factory.begin() as session:
            message = session.get(OutboxMessageModel, message_id)
            message.attempts += 1
            message.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=delay_seconds
            )
            message.lease_until = None


class OutboxRelay:
    def __init__(
        self,
        store: SQLAlchemyOutboxStore,
        sqs: Any,
        queue_url: str,
        *,
        base_retry_seconds: int = 1,
    ) -> None:
        self._store = store
        self._sqs = sqs
        self._queue_url = queue_url
        self._base_retry_seconds = base_retry_seconds

    def run_once(self) -> int:
        published = 0
        for message in self._store.claim_batch(limit=10, lease_seconds=30):
            try:
                self._sqs.send(self._queue_url, message.payload)
            except Exception:  # noqa: BLE001 - every publisher failure is retryable
                delay = min(self._base_retry_seconds * (2**message.attempts), 300)
                self._store.mark_failed(message.id, delay)
                continue
            self._store.mark_published(message.id)
            published += 1
        return published
