"""Create the OS Service-owned schema.

Revision ID: 001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("document", sa.String(14), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "vehicles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("license_plate", sa.String(10), nullable=False, unique=True),
        sa.Column("make", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vehicles_customer_id", "vehicles", ["customer_id"])
    op.create_table(
        "service_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_id", sa.String(36), nullable=False),
        sa.Column("vehicle_id", sa.String(36), nullable=False),
        sa.Column("saga_id", sa.String(36), nullable=False, unique=True),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_service_orders_customer_id", "service_orders", ["customer_id"])
    op.create_index("ix_service_orders_vehicle_id", "service_orders", ["vehicle_id"])
    op.create_index("ix_service_orders_correlation_id", "service_orders", ["correlation_id"])
    op.create_table(
        "service_order_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("service_orders.id"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_service_order_history_order_id", "service_order_history", ["order_id"])
    op.create_table(
        "sagas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("service_orders.id"), nullable=False, unique=True),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("processed_event_ids", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_outbox_messages_message_type", "outbox_messages", ["message_type"])
    op.create_index("ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"])
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("consumer", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "consumer", name="uq_inbox"),
    )


def downgrade() -> None:
    op.drop_table("inbox_messages")
    op.drop_index("ix_outbox_messages_aggregate_id", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_message_type", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_table("sagas")
    op.drop_index("ix_service_order_history_order_id", table_name="service_order_history")
    op.drop_table("service_order_history")
    op.drop_index("ix_service_orders_correlation_id", table_name="service_orders")
    op.drop_index("ix_service_orders_vehicle_id", table_name="service_orders")
    op.drop_index("ix_service_orders_customer_id", table_name="service_orders")
    op.drop_table("service_orders")
    op.drop_index("ix_vehicles_customer_id", table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_table("customers")
