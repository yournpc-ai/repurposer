"""add payment_orders for Stripe credit-package purchases

Revision ID: f7a2c4d9e1b6
Revises: a6e9c2d4f801
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f7a2c4d9e1b6"
down_revision: Union[str, Sequence[str], None] = "a6e9c2d4f801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_key", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("credits", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("provider_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("credit_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_minor >= 0", name="ck_payment_orders_amount_nonnegative"),
        sa.CheckConstraint("credits > 0", name="ck_payment_orders_credits_positive"),
        sa.ForeignKeyConstraint(["credit_transaction_id"], ["credit_transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_checkout_session_id", name="uq_payment_orders_checkout_session"
        ),
        sa.UniqueConstraint(
            "credit_transaction_id", name="uq_payment_orders_credit_transaction"
        ),
    )
    op.create_index(
        "ix_payment_orders_user_created_at",
        "payment_orders",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_orders_user_created_at", table_name="payment_orders")
    op.drop_table("payment_orders")
