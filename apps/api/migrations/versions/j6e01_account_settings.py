"""Track signed-in devices and delivery of opted-in publication alerts."""

from alembic import op
import sqlalchemy as sa

revision = "j6e01_account_settings"
down_revision = "j6d05_project_brief"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_agent", sa.String(512), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    op.create_index("ix_login_sessions_expires_at", "login_sessions", ["expires_at"])
    op.add_column("notifications", sa.Column("email_due_at", sa.DateTime(timezone=True)))
    op.add_column(
        "notifications",
        sa.Column("email_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_notifications_email_due",
        "notifications",
        ["email_due_at"],
        postgresql_where=sa.text("email_due_at IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_notifications_email_due", table_name="notifications")
    op.drop_column("notifications", "email_attempts")
    op.drop_column("notifications", "email_due_at")
    op.drop_table("login_sessions")
