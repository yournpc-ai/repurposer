"""Index permanent sound effects and visual presets for director discovery."""

from alembic import op
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "m8a01_universal_asset_catalog"
down_revision = "k7f01_permanent_audio_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column("voices", Column("pacing", String(24)))
    op.add_column("voices", Column("use_for", JSONB, nullable=False, server_default="[]"))
    op.add_column("voices", Column("avoid", JSONB, nullable=False, server_default="[]"))
    op.add_column("voices", Column("search_text", Text, nullable=False, server_default=""))
    op.create_index(
        "ix_voices_search_trgm",
        "voices",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.add_column("music", Column("genre", String(48)))
    op.add_column("music", Column("energy", String(16), nullable=False, server_default="medium"))
    op.add_column("music", Column("bpm", Integer))
    op.add_column("music", Column("summary", String(280)))
    op.add_column("music", Column("use_for", JSONB, nullable=False, server_default="[]"))
    op.add_column("music", Column("avoid", JSONB, nullable=False, server_default="[]"))
    op.add_column("music", Column("search_text", Text, nullable=False, server_default=""))
    op.create_index(
        "ix_music_search_trgm",
        "music",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.execute("""UPDATE music SET bpm = COALESCE(meta->>'bpm', meta->>'reference_bpm')::int
                  WHERE COALESCE(meta->>'bpm', meta->>'reference_bpm') ~ '^[1-9][0-9]{0,2}$'""")
    op.execute("""UPDATE music SET search_text = concat_ws(' ', title,mood,prompt,tags,compatible_styles,
                  genre,energy,summary,use_for,avoid,meta->>'style',bpm)""")
    op.execute("""UPDATE voices SET search_text = concat_ws(' ', name,description,design_prompt,gender,
                  age_band,provider_voice_id,languages,tone_tags,compatible_styles,pacing,use_for,avoid)""")
    op.create_index("ix_music_bpm", "music", ["bpm"])
    op.create_table(
        "sound_effects",
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("slug", String(120), nullable=False, unique=True, index=True),
        Column("engine_kind", String(24), nullable=False),
        Column("category", String(48), nullable=False, index=True),
        Column("subcategory", String(64), nullable=True),
        Column("name", String(160), nullable=False),
        Column("name_zh", String(160), nullable=True),
        Column("summary", String(280), nullable=False),
        Column("moods", JSONB, nullable=False, server_default="[]"),
        Column("energy", String(16), nullable=False, server_default="medium"),
        Column("use_for", JSONB, nullable=False, server_default="[]"),
        Column("avoid", JSONB, nullable=False, server_default="[]"),
        Column("tags", JSONB, nullable=False, server_default="[]"),
        Column("compatible_styles", JSONB, nullable=False, server_default="[]"),
        Column("duration_ms", Integer, nullable=False),
        Column("peak_offset_ms", Integer, nullable=False, server_default="0"),
        Column("sync_cue", String(24), nullable=False, server_default="onset"),
        Column("lufs", Float, nullable=True),
        Column("mix_hint", String(280), nullable=True),
        Column("storage_key", String(512), nullable=True),
        Column("ext", String(12), nullable=True),
        Column("size_bytes", BigInteger, nullable=True),
        Column("content_sha256", String(64), nullable=True),
        Column("recipe_id", String(80), nullable=True),
        Column("recipe_version", Integer, nullable=True),
        Column("params_schema", JSONB, nullable=True),
        Column("source_provider", String(32), nullable=False, server_default="curated"),
        Column("source_url", String(512), nullable=True),
        Column("license", String(100), nullable=True),
        Column("attribution", Text, nullable=True),
        Column(
            "owner_id",
            UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        Column("scope", String(24), nullable=False, server_default="platform"),
        Column("status", String(24), nullable=False, server_default="curated"),
        Column("use_count", Integer, nullable=False, server_default="0"),
        Column("search_text", Text, nullable=False, server_default=""),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        CheckConstraint("scope IN ('platform', 'user')", name="ck_sound_effects_scope"),
        CheckConstraint(
            "status IN ('curated', 'ready', 'archived')", name="ck_sound_effects_status"
        ),
        CheckConstraint(
            "energy IN ('subtle', 'medium', 'high', 'explosive')", name="ck_sound_effects_energy"
        ),
        CheckConstraint(
            "engine_kind IN ('sample', 'dsp_recipe')", name="ck_sound_effects_engine_kind"
        ),
        CheckConstraint(
            "sync_cue IN ('onset', 'energy_peak', 'end_peak')", name="ck_sound_effects_sync_cue"
        ),
    )
    op.create_index("ix_sfx_scope_status_cat", "sound_effects", ["scope", "status", "category"])
    op.create_index("ix_sfx_energy_sync", "sound_effects", ["energy", "sync_cue"])
    op.create_index("ix_sfx_moods_gin", "sound_effects", ["moods"], postgresql_using="gin")
    op.create_index("ix_sfx_tags_gin", "sound_effects", ["tags"], postgresql_using="gin")
    op.create_index(
        "ix_sfx_search_trgm",
        "sound_effects",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_table(
        "visual_presets",
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("asset_kind", String(24), nullable=False, index=True),
        Column("preset_id", String(120), nullable=False),
        Column("render_version", Integer, nullable=False, server_default="1"),
        Column("domain", String(32), nullable=False),
        Column("category", String(48), nullable=False, index=True),
        Column("subcategory", String(64), nullable=True),
        Column("name", String(160), nullable=False),
        Column("name_zh", String(160), nullable=True),
        Column("summary", String(280), nullable=False),
        Column("moods", JSONB, nullable=False, server_default="[]"),
        Column("energy", String(16), nullable=False, server_default="medium"),
        Column("use_for", JSONB, nullable=False, server_default="[]"),
        Column("avoid", JSONB, nullable=False, server_default="[]"),
        Column("tags", JSONB, nullable=False, server_default="[]"),
        Column("compatible_styles", JSONB, nullable=False, server_default="[]"),
        Column("slot_summary", JSONB, nullable=False, server_default="{}"),
        Column("recommended_sfx", JSONB, nullable=False, server_default="[]"),
        Column("props_schema", JSONB, nullable=False, server_default="{}"),
        Column("example_props", JSONB, nullable=False, server_default="{}"),
        Column("director_notes", Text, nullable=True),
        Column("preview_spec", JSONB, nullable=False, server_default="{}"),
        Column("preview_duration_s", Float, nullable=False, server_default="3.0"),
        Column("is_builtin", Boolean, nullable=False, server_default="true"),
        Column(
            "owner_id",
            UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        Column("scope", String(24), nullable=False, server_default="platform"),
        Column("status", String(24), nullable=False, server_default="curated"),
        Column("use_count", Integer, nullable=False, server_default="0"),
        Column("search_text", Text, nullable=False, server_default=""),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        CheckConstraint("scope IN ('platform', 'user')", name="ck_visual_presets_scope"),
        CheckConstraint(
            "status IN ('curated', 'ready', 'archived')", name="ck_visual_presets_status"
        ),
        CheckConstraint(
            "energy IN ('subtle', 'medium', 'high', 'explosive')", name="ck_visual_presets_energy"
        ),
        CheckConstraint(
            "asset_kind IN ('block', 'text_preset', 'transition')",
            name="ck_visual_presets_asset_kind",
        ),
        UniqueConstraint("asset_kind", "preset_id", name="uq_visual_presets_kind_id"),
    )
    op.create_index(
        "ix_vp_kind_scope_status_cat",
        "visual_presets",
        ["asset_kind", "scope", "status", "category"],
    )
    op.create_index("ix_vp_moods_gin", "visual_presets", ["moods"], postgresql_using="gin")
    op.create_index("ix_vp_tags_gin", "visual_presets", ["tags"], postgresql_using="gin")
    op.create_index(
        "ix_vp_search_trgm",
        "visual_presets",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_table("visual_presets")
    op.drop_table("sound_effects")
    op.drop_column("voices", "search_text")
    op.drop_column("voices", "avoid")
    op.drop_column("voices", "use_for")
    op.drop_column("voices", "pacing")
    op.drop_column("music", "search_text")
    op.drop_column("music", "avoid")
    op.drop_column("music", "use_for")
    op.drop_column("music", "summary")
    op.drop_column("music", "bpm")
    op.drop_column("music", "energy")
    op.drop_column("music", "genre")
