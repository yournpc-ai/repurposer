"""Synchronize code-owned discovery fields while preserving usage and lifecycle state."""

from functools import lru_cache
from uuid import NAMESPACE_URL, uuid5

from pydantic import TypeAdapter
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.catalog.builtin import BLOCK_SUMMARIES, BLOCKS, TRANSITIONS
from app.catalog.preview import preview_spec
from app.editing.catalog import MOTION_BLOCK_CATALOG, SOUND_ACOUSTICS, SOUND_RECIPE_CATALOG
from app.editing.schemas import MOTION_BLOCK_PROP_MODELS, Transition
from app.editing.text_presets import (
    TEXT_STYLE_PRESET_CATALOG,
    TEXT_STYLE_PRESETS,
    TextStylePresetToken,
)
from app.models.tables import SoundEffect, VisualPreset


def search_document(row):
    fields = (
        "slug",
        "preset_id",
        "name",
        "name_zh",
        "category",
        "subcategory",
        "summary",
        "tags",
        "moods",
        "use_for",
        "avoid",
        "compatible_styles",
    )
    return " ".join(
        " ".join(value) if isinstance(value, list) else str(value)
        for field in fields
        if (value := row.get(field))
    )


def _styles(energy):
    if energy in ("high", "explosive"):
        return ["kinetic_anime", "vox_editorial"]
    return ["institutional_dark", "swiss_paper"]


@lru_cache(maxsize=1)
def builtin_rows():
    visuals, sounds = [], []
    for key, meta in MOTION_BLOCK_CATALOG.items():
        zh, category, mood, energy, recipes, props = BLOCKS[key]
        model = MOTION_BLOCK_PROP_MODELS[key]
        model.model_validate(props)
        required = "image_resource" in meta["required_slots"]
        visuals.append(
            dict(
                asset_kind="block",
                preset_id=key,
                render_version=meta["version"],
                domain=meta["domain"],
                category=category,
                subcategory=meta["category"],
                name=meta["name"],
                name_zh=zh,
                summary=BLOCK_SUMMARIES[key],
                moods=[mood],
                energy=energy,
                use_for=meta["use_for"],
                avoid=meta["avoid"],
                tags=[category, mood],
                compatible_styles=_styles(energy),
                recommended_sfx=["dsp_" + recipe for recipe in recipes],
                slot_summary={
                    "needs_media": "image_or_video" if required else "none",
                    "required": meta["required_slots"],
                    "ideal_dur_s": meta["suggested_duration_s"],
                },
                props_schema=model.model_json_schema(),
                example_props=props,
                director_notes=" ".join([meta["desc"], *meta["use_for"], *meta["avoid"]]),
                preview_spec=preview_spec("block", key, props, required),
            )
        )
    for key, meta in TEXT_STYLE_PRESET_CATALOG.items():
        visuals.append(
            dict(
                asset_kind="text_preset",
                preset_id=key,
                render_version=1,
                domain="typography",
                category=meta["category"],
                subcategory=key,
                name=meta["name"],
                name_zh=meta["name_zh"],
                summary=meta["visual_signature"],
                moods=meta["moods"],
                energy=meta["energy"],
                use_for=meta["use_for"],
                avoid=meta["avoid"],
                tags=[meta["category"], key],
                compatible_styles=_styles(meta["energy"]),
                recommended_sfx=["dsp_title_bloom"],
                slot_summary={"needs_media": "none", "required": ["text"]},
                props_schema=TypeAdapter(TextStylePresetToken).json_schema(),
                example_props=TEXT_STYLE_PRESETS[key],
                director_notes=meta["visual_signature"],
                preview_spec=preview_spec("text_preset", key, {}),
            )
        )
    for key, (zh, mood, energy, summary, use, avoid) in TRANSITIONS.items():
        visuals.append(
            dict(
                asset_kind="transition",
                preset_id=key,
                render_version=1,
                domain="transition",
                category="transition",
                subcategory=key,
                name=key.replace("_", " ").title(),
                name_zh=zh,
                summary=summary,
                moods=[mood],
                energy=energy,
                use_for=[use],
                avoid=[avoid],
                tags=[key],
                compatible_styles=_styles(energy),
                recommended_sfx=["dsp_velvet_pass"],
                slot_summary={"required": ["from_clip_id", "to_clip_id"]},
                props_schema=Transition.model_json_schema(),
                example_props={
                    "transition_id": "cut",
                    "from_clip_id": "clip0",
                    "to_clip_id": "clip1",
                    "kind": key,
                    "duration": 30000,
                },
                director_notes=use,
                preview_spec=preview_spec("transition", key, {}),
            )
        )
    for key, meta in SOUND_RECIPE_CATALOG.items():
        measured = SOUND_ACOUSTICS[key]
        sounds.append(
            dict(
                slug="dsp_" + key,
                engine_kind="dsp_recipe",
                recipe_id=key,
                recipe_version=meta["version"],
                domain=meta["domain"],
                category=meta["category"],
                subcategory=meta["category"],
                name=meta["name"],
                name_zh=meta["name_zh"],
                summary=meta["desc"],
                moods=meta["moods"],
                energy=meta["energy"],
                use_for=meta["use_for"],
                avoid=meta["avoid"],
                tags=[key, meta["category"]],
                compatible_styles=_styles(meta["energy"]),
                sync_cue=meta["sync_cue"],
                mix_hint=meta["mix_hint"],
                params_schema=meta["params"],
                source_provider="sound_engine",
                duration_ms=measured["duration_ms"],
                peak_offset_ms=measured["peak_offset_ms"],
                lufs=measured["lufs"],
            )
        )
    for row in visuals + sounds:
        row["search_text"] = search_document(row)
    return visuals, sounds


async def sync_builtin_catalog(db):
    visuals, sounds = builtin_rows()
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended("repurposer/builtin_catalog", 0)))
    )
    for model, rows, keys in [
        (VisualPreset, visuals, ["asset_kind", "preset_id"]),
        (SoundEffect, sounds, ["slug"]),
    ]:
        values = [
            {
                **row,
                "id": uuid5(NAMESPACE_URL, "repurposer/catalog/" + "/".join(row[k] for k in keys)),
            }
            for row in rows
        ]
        stmt = insert(model).values(values)
        updates = {k: stmt.excluded[k] for k in rows[0] if k not in keys}
        owned = model.is_builtin if model is VisualPreset else model.engine_kind == "dsp_recipe"
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=keys,
                set_={**updates, "updated_at": func.now()},
                where=(model.scope == "platform")
                & owned
                & or_(*(model.__table__.c[k].is_distinct_from(v) for k, v in updates.items())),
            )
        )


async def ensure_builtin_catalog(db):
    """Refresh missing built-ins on first read when startup hooks are bypassed."""
    sentinels = ("code_terminal", "browser_url_load")
    visual_count = select(func.count()).select_from(VisualPreset).where(
        VisualPreset.asset_kind == "block",
        VisualPreset.preset_id.in_(sentinels),
        VisualPreset.scope == "platform",
        VisualPreset.is_builtin,
    ).scalar_subquery()
    sound = select(SoundEffect.id).where(
        SoundEffect.slug == "dsp_tension_radar",
        SoundEffect.domain == "video",
        SoundEffect.engine_kind == "dsp_recipe",
        SoundEffect.scope == "platform",
    ).exists()
    if not await db.scalar(select((visual_count == len(sentinels)) & sound)):
        await sync_builtin_catalog(db)
        await db.commit()
