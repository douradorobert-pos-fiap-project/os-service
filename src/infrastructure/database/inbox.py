"""Idempotent consumer receipt registration."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import InboxMessageModel


def claim_event(session: Session, event_id: UUID, consumer: str) -> bool:
    existing = session.scalar(
        select(InboxMessageModel).where(
            InboxMessageModel.event_id == str(event_id),
            InboxMessageModel.consumer == consumer,
        )
    )
    if existing is not None:
        return False
    session.add(InboxMessageModel(event_id=str(event_id), consumer=consumer))
    return True
