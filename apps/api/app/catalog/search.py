"""Visibility, ranking and bounded projections shared by the gallery and editor."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, or_, select

from app.models.tables import SoundEffect, VisualPreset

Energy = Literal["subtle", "medium", "high", "explosive"]


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str | None = Field(default=None, max_length=160)
    category: str | None = Field(default=None, max_length=48)
    mood: str | None = Field(default=None, max_length=64)
    energy: Energy | None = None
    limit: int = Field(default=10, ge=1, le=20)


class BlockArgs(SearchArgs):
    style_preset: str | None = Field(default=None, max_length=64)
    needs_media: Literal["any", "none", "image_or_video"] = "any"


class SoundArgs(SearchArgs):
    sync_cue: Literal["onset", "energy_peak", "end_peak"] | None = None
    max_duration_ms: int | None = Field(default=None, gt=0)


class DetailArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=1, max_length=8)


TOOLS = {
    "get_music": ("music", DetailArgs),
    "get_voices": ("voice", DetailArgs),
    "search_blocks": ("block", BlockArgs),
    "get_blocks": ("block", DetailArgs),
    "search_text_presets": ("text_preset", SearchArgs),
    "get_text_presets": ("text_preset", DetailArgs),
    "search_sfx_library": ("sfx", SoundArgs),
    "get_sfx": ("sfx", DetailArgs),
}


def visible(model, owner_id: UUID):
    return model.status.in_(("curated", "ready")) & (
        (model.scope == "platform") | (model.owner_id == owner_id)
    )


def _projection(kind, owner_id):
    sound = kind == "sfx"
    model = SoundEffect if sound else VisualPreset
    key = model.slug if sound else model.preset_id
    cols = [
        key.label("id"),
        model.category,
        model.name,
        model.moods,
        model.energy,
        model.summary,
        model.use_for,
        model.avoid,
    ]
    cols += [model.duration_ms, model.sync_cue] if sound else [model.slot_summary]
    stmt = select(*cols).where(visible(model, owner_id))
    if not sound:
        stmt = stmt.where(model.asset_kind == kind)
    return model, key, stmt


async def search_catalog(db, owner_id, kind, args, *, offset=0):
    model, key, stmt = _projection(kind, owner_id)
    for field in ("category", "energy", "sync_cue"):
        if value := getattr(args, field, None):
            stmt = stmt.where(getattr(model, field) == value)
    if isinstance(args, BlockArgs) and args.needs_media != "any":
        stmt = stmt.where(model.slot_summary["needs_media"].astext == args.needs_media)
    if isinstance(args, SoundArgs) and args.max_duration_ms:
        stmt = stmt.where(model.duration_ms <= args.max_duration_ms)
    score = 0.3 * func.ln(1 + model.use_count)
    if args.mood:
        match = or_(model.moods.contains([args.mood]), model.tags.contains([args.mood]))
        stmt = stmt.where(match)
        score += case((match, 4.0), else_=0.0)
    if style := getattr(args, "style_preset", None):
        score += case((model.compatible_styles.contains([style]), 3.0), else_=0.0)
    if q := args.query:
        text = model.search_text
        literal = text.icontains(q, autoescape=True)
        exact = or_(model.tags.contains([q]), model.moods.contains([q]))
        stmt = stmt.where(or_(literal, text.op("%")(q), text.op("%>")(q), exact))
        score += (
            2.5 * func.similarity(text, q)
            + case((literal, 2.0), else_=0.0)
            + case((exact, 4.0), else_=0.0)
        )
    rows = await db.execute(
        stmt.order_by(score.desc(), model.id.asc()).offset(offset).limit(args.limit)
    )
    return {"items": [dict(row) for row in rows.mappings()]}


async def catalog_details(db, owner_id, kind, ids):
    if kind in {"music", "voice"}:
        return await audio_details(db, owner_id, kind, ids)
    model, key, stmt = _projection(kind, owner_id)
    if kind == "sfx":
        stmt = stmt.add_columns(
            model.engine_kind,
            model.peak_offset_ms,
            model.mix_hint,
            model.lufs,
            model.recipe_id,
            model.recipe_version,
            model.params_schema,
            model.storage_key,
        )
    else:
        stmt = stmt.add_columns(
            model.props_schema, model.example_props, model.director_notes, model.recommended_sfx
        )
    result = await db.execute(stmt.where(key.in_(ids)))
    by_id = {}
    for row in result.mappings():
        item = dict(row)
        if kind == "sfx":
            storage_key = item.pop("storage_key")
            if item["engine_kind"] == "sample":
                from app.providers import storage

                item["storage_ready"] = bool(storage_key and await storage.exists(storage_key))
                for field in ("recipe_id", "recipe_version", "params_schema"):
                    item.pop(field)
        by_id[item["id"]] = item
    return {"items": [by_id[k] for k in dict.fromkeys(ids) if k in by_id]}


async def audio_details(db, owner_id, kind, ids):
    from app.models.tables import Music, Voice

    parsed = []
    for key in ids:
        try:
            parsed.append(UUID(key))
        except ValueError:
            continue
    if kind == "music":
        stmt = select(
            Music.id,
            Music.title.label("name"),
            Music.genre,
            Music.bpm,
            Music.energy,
            Music.summary,
            Music.mood,
            Music.use_for,
            Music.avoid,
            Music.lufs,
            Music.duration_seconds,
            Music.compatible_styles,
        ).where(
            Music.status.in_(("ready", "curated")),
            Music.id.in_(parsed),
            or_(
                Music.scope == "platform",
                Music.is_public.is_(True),
                Music.generated_by_user_id == owner_id,
            ),
        )
    else:
        stmt = select(
            Voice.id,
            Voice.name,
            Voice.description,
            Voice.pacing,
            Voice.languages,
            Voice.tone_tags,
            Voice.use_for,
            Voice.avoid,
            Voice.compatible_styles,
            Voice.provider_voice_id,
        ).where(visible(Voice, owner_id), Voice.id.in_(parsed))
    rows = {row["id"]: {**row, "id": str(row["id"])} for row in (await db.execute(stmt)).mappings()}
    return {"items": [rows[key] for key in dict.fromkeys(parsed) if key in rows]}
