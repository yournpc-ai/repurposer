"""Add permanent voices library table and upgrade music table for compounding reuse."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "k7f01_permanent_audio_library"
down_revision = "j6e02_message_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(24), nullable=False, server_default=sa.text("'user'")),
        sa.Column("status", sa.String(24), nullable=False, server_default=sa.text("'ready'")),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("design_prompt", sa.Text(), nullable=True),
        sa.Column(
            "languages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("gender", sa.String(24), nullable=True),
        sa.Column("age_band", sa.String(32), nullable=True),
        sa.Column(
            "tone_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "compatible_styles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("provider", sa.String(32), nullable=False, server_default=sa.text("'minimax'")),
        sa.Column("provider_voice_id", sa.String(255), nullable=False),
        sa.Column("reference_audio_key", sa.String(512), nullable=True),
        sa.Column("preview_audio_key", sa.String(512), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_voices_scope_status", "voices", ["scope", "status"])
    op.create_index("ix_voices_owner_status", "voices", ["owner_id", "status"])

    # Drop UNIQUE constraint on music.mood safely (inspect actual constraint name)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for uc in inspector.get_unique_constraints("music"):
        if uc.get("column_names") == ["mood"] and uc.get("name"):
            op.drop_constraint(uc["name"], "music", type_="unique")
    op.create_index("ix_music_mood", "music", ["mood"])

    op.add_column(
        "music",
        sa.Column("scope", sa.String(24), nullable=False, server_default=sa.text("'platform'")),
    )
    op.add_column(
        "music",
        sa.Column("status", sa.String(24), nullable=False, server_default=sa.text("'curated'")),
    )
    op.add_column(
        "music",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "music",
        sa.Column(
            "compatible_styles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "music",
        sa.Column("instrumental", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("music", sa.Column("lufs", sa.Float(), nullable=True))
    op.add_column(
        "music",
        sa.Column("use_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "music",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("music", "is_favorite")
    op.drop_column("music", "use_count")
    op.drop_column("music", "lufs")
    op.drop_column("music", "instrumental")
    op.drop_column("music", "compatible_styles")
    op.drop_column("music", "tags")
    op.drop_column("music", "status")
    op.drop_column("music", "scope")
    op.drop_index("ix_music_mood", table_name="music")
    op.create_unique_constraint("music_mood_key", "music", ["mood"])

    op.drop_index("ix_voices_owner_status", table_name="voices")
    op.drop_index("ix_voices_scope_status", table_name="voices")
    op.drop_table("voices")
