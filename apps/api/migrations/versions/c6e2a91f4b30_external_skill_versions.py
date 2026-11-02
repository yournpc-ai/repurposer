"""Owner-scoped external Skills and immutable SkillVersions.

Revision ID: c6e2a91f4b30
Revises: b8d5e3f1a720
Create Date: 2026-11-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c6e2a91f4b30"
down_revision: str | Sequence[str] | None = "b8d5e3f1a720"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_user_skills_owner_name"),
    )
    op.create_index("ix_user_skills_owner_id", "user_skills", ["owner_id"])
    op.create_table(
        "skill_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("declared_inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capability_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("source_revision", sa.String(length=128), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["user_skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "source_hash", name="uq_skill_versions_source_hash"),
        sa.UniqueConstraint("skill_id", "version", name="uq_skill_versions_version"),
    )
    op.create_index("ix_skill_versions_owner_id", "skill_versions", ["owner_id"])
    op.create_index("ix_skill_versions_skill_id", "skill_versions", ["skill_id"])
    op.execute(
        """
        CREATE FUNCTION reject_skill_version_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'SkillVersion rows are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER skill_versions_immutable
        BEFORE UPDATE OR DELETE ON skill_versions
        FOR EACH ROW EXECUTE FUNCTION reject_skill_version_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER skill_versions_immutable ON skill_versions")
    op.execute("DROP FUNCTION reject_skill_version_mutation()")
    op.drop_index("ix_skill_versions_skill_id", table_name="skill_versions")
    op.drop_index("ix_skill_versions_owner_id", table_name="skill_versions")
    op.drop_table("skill_versions")
    op.drop_index("ix_user_skills_owner_id", table_name="user_skills")
    op.drop_table("user_skills")
