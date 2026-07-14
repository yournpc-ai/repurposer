"""clip publishing suite and rename outputs

Revision ID: 1569e085b02b
Revises: eb812df93567
Create Date: 2026-07-15 01:52:47.953082

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1569e085b02b'
down_revision: str | Sequence[str] | None = 'eb812df93567'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize_derivative_type(value: str) -> str:
    """Map legacy derivative type names to the new output naming."""
    return {
        "linkedin_post": "post",
        "summary": "post",
        "quote_card": "quotes",
        "blog": "article",
    }.get(value, value)


def _normalize_content_plan(obj: object) -> object:
    """Recursively rewrite legacy derivative_type values inside a content_plan dict."""
    if isinstance(obj, dict):
        return {
            k: _normalize_derivative_type(v) if k == "derivative_type" and isinstance(v, str) else _normalize_content_plan(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_normalize_content_plan(item) for item in obj]
    return obj


def upgrade() -> None:
    """Upgrade schema."""
    # Add publishing-suite columns to clips.
    op.add_column('clips', sa.Column('title', sa.String(length=255), nullable=True))
    op.add_column('clips', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('clips', sa.Column('hashtags', sa.JSON(), nullable=True))
    op.add_column('clips', sa.Column('cover_image_url', sa.String(length=512), nullable=True))
    op.add_column('clips', sa.Column('topic', sa.String(length=255), nullable=True))
    op.add_column('clips', sa.Column('start_time', sa.Float(), nullable=True))
    op.add_column('clips', sa.Column('end_time', sa.Float(), nullable=True))

    # Rename DerivativeType enum values to the new output naming.
    # Two legacy values (linkedin_post, summary) collapse into 'post', so we
    # add the new values first, migrate rows, then rebuild the enum type to
    # remove the legacy values (PostgreSQL does not support DROP VALUE).
    op.execute("ALTER TYPE derivativetype ADD VALUE IF NOT EXISTS 'post'")
    op.execute("ALTER TYPE derivativetype ADD VALUE IF NOT EXISTS 'quotes'")
    op.execute("ALTER TYPE derivativetype ADD VALUE IF NOT EXISTS 'article'")

    op.execute("UPDATE derivatives SET type = 'post' WHERE type = 'summary'")
    op.execute("UPDATE derivatives SET type = 'post' WHERE type = 'linkedin_post'")
    op.execute("UPDATE derivatives SET type = 'quotes' WHERE type = 'quote_card'")
    op.execute("UPDATE derivatives SET type = 'article' WHERE type = 'blog'")

    # Reshape legacy summary content to match the new Post schema.
    # Summary stored {tldr, key_points, full}; Post requires {content, hashtags}.
    op.execute(
        """
        UPDATE derivatives
        SET content = jsonb_build_object(
            'content', COALESCE(content->>'full', content->>'tldr', ''),
            'hashtags', '[]'::jsonb
        )::json
        WHERE type = 'post'
          AND (
              content::jsonb ? 'tldr'
              OR content::jsonb ? 'key_points'
              OR content::jsonb ? 'full'
          )
        """
    )

    # Rewrite legacy derivative_type values inside persisted content_plan JSON.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, content_plan FROM projects WHERE content_plan IS NOT NULL")
    ).fetchall()
    for project_id, content_plan in rows:
        normalized = _normalize_content_plan(content_plan)
        if normalized != content_plan:
            connection.execute(
                sa.text("UPDATE projects SET content_plan = :content_plan WHERE id = :id"),
                {"content_plan": normalized, "id": project_id},
            )

    # Rebuild the enum type to drop legacy values.
    # PostgreSQL does not support ALTER TYPE ... DROP VALUE, so we create a new
    # type, move the column to it, drop the old type, and rename the new one.
    op.execute("CREATE TYPE derivativetype_new AS ENUM ('post', 'quotes', 'carousel', 'article')")
    op.execute(
        "ALTER TABLE derivatives ALTER COLUMN type TYPE derivativetype_new "
        "USING type::text::derivativetype_new"
    )
    op.execute("DROP TYPE derivativetype")
    op.execute("ALTER TYPE derivativetype_new RENAME TO derivativetype")

    # Downgrade hint: legacy summary rows are collapsed into post and cannot be
    # disambiguated on rollback. This is accepted per the migration design.


def downgrade() -> None:
    """Downgrade schema."""
    # Rebuild the enum type to restore legacy values.
    op.execute(
        "CREATE TYPE derivativetype_new AS ENUM ("
        "'linkedin_post', 'quote_card', 'carousel', 'summary', 'blog'"
        ")"
    )
    op.execute(
        "ALTER TABLE derivatives ALTER COLUMN type TYPE derivativetype_new "
        "USING type::text::derivativetype_new"
    )
    op.execute("DROP TYPE derivativetype")
    op.execute("ALTER TYPE derivativetype_new RENAME TO derivativetype")

    # Migrate rows back to legacy values (lossy: post rows become linkedin_post,
    # original summary rows are indistinguishable).
    op.execute("UPDATE derivatives SET type = 'linkedin_post' WHERE type = 'post'")
    op.execute("UPDATE derivatives SET type = 'quote_card' WHERE type = 'quotes'")
    op.execute("UPDATE derivatives SET type = 'blog' WHERE type = 'article'")

    # Drop publishing-suite columns.
    op.drop_column('clips', 'end_time')
    op.drop_column('clips', 'start_time')
    op.drop_column('clips', 'topic')
    op.drop_column('clips', 'cover_image_url')
    op.drop_column('clips', 'hashtags')
    op.drop_column('clips', 'description')
    op.drop_column('clips', 'title')
