"""Classify permanent sound effects by production domain."""

from alembic import op
import sqlalchemy as sa

revision = "n1a01_sound_domains"
down_revision = "m8a01_universal_asset_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sound_effects", sa.Column("domain", sa.String(24), nullable=False, server_default="video"))
    op.execute("""UPDATE sound_effects SET domain = 'interface', category = 'toggle'
                  WHERE engine_kind = 'sample' AND scope = 'platform' AND slug = 'foley_switch'
                    AND source_provider = 'code4fukui' AND category = 'tactile_ui'""")
    op.execute("""UPDATE sound_effects SET category = 'impacts'
                  WHERE engine_kind = 'sample' AND scope = 'platform' AND slug IN ('foley_metal', 'foley_steel')
                    AND source_provider = 'code4fukui' AND category = 'foley_organic'""")
    op.create_check_constraint("ck_sfx_domain", "sound_effects", "domain IN ('interface', 'video')")
    op.create_index("ix_sfx_domain_cat", "sound_effects", ["domain", "category"])


def downgrade() -> None:
    op.execute("""UPDATE sound_effects SET category = 'tactile_ui'
                  WHERE engine_kind = 'sample' AND scope = 'platform' AND slug = 'foley_switch'
                    AND source_provider = 'code4fukui' AND category = 'toggle'""")
    op.execute("""UPDATE sound_effects SET category = 'foley_organic'
                  WHERE engine_kind = 'sample' AND scope = 'platform' AND slug IN ('foley_metal', 'foley_steel')
                    AND source_provider = 'code4fukui' AND category = 'impacts'""")
    op.drop_index("ix_sfx_domain_cat", table_name="sound_effects")
    op.drop_constraint("ck_sfx_domain", "sound_effects", type_="check")
    op.drop_column("sound_effects", "domain")
