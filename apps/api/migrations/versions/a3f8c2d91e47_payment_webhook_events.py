"""Add durable payment webhook receipts and alert outbox.

Revision ID: a3f8c2d91e47
Revises: f2a7c4e9b613
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3f8c2d91e47"
down_revision: str | Sequence[str] | None = "f2a7c4e9b613"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("livemode", sa.Boolean(), nullable=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("first_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_status", sa.String(length=20), nullable=True),
        sa.Column("alert_attempt_count", sa.Integer(), nullable=False),
        sa.Column("alert_next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_last_error", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "attempt_count >= 1", name="ck_payment_webhook_attempts_positive"
        ),
        sa.CheckConstraint(
            "alert_attempt_count >= 0", name="ck_payment_webhook_alert_attempts"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_payment_webhook_events_dedupe_key"),
        sa.UniqueConstraint("event_id", name="uq_payment_webhook_events_event_id"),
    )
    op.create_index(
        "ix_payment_webhook_events_order_id",
        "payment_webhook_events",
        ["order_id"],
    )
    op.create_index(
        "ix_payment_webhook_events_checkout_session_id",
        "payment_webhook_events",
        ["checkout_session_id"],
    )
    op.create_index(
        "ix_payment_webhook_events_alert_due",
        "payment_webhook_events",
        ["alert_status", "alert_next_attempt_at"],
    )
    op.create_index(
        "ix_payment_webhook_events_first_received_at",
        "payment_webhook_events",
        ["first_received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_webhook_events_first_received_at",
        table_name="payment_webhook_events",
    )
    op.drop_index(
        "ix_payment_webhook_events_alert_due",
        table_name="payment_webhook_events",
    )
    op.drop_index(
        "ix_payment_webhook_events_checkout_session_id",
        table_name="payment_webhook_events",
    )
    op.drop_index(
        "ix_payment_webhook_events_order_id",
        table_name="payment_webhook_events",
    )
    op.drop_table("payment_webhook_events")
