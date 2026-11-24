"""Owner-scoped Skill slot-preview & pinned static font routes (/api/v1/skills)."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.dependencies import DBDep, get_current_user_required
from app.editing.catalog import build_sound_spec, sound_spec_digest
from app.editing.styles import StylePresetId
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks
from app.models.tables import User, UserSkill
from app.skills.blueprint import (
    BLUEPRINT_CAPABILITY,
    SkillBlueprintV1,
    load_blueprint_from_skill_version,
)
from app.skills.slot_preview import (
    ALLOWED_FONT_FILENAMES,
    FONTS_DIR,
    SlotManifestItem,
    build_slot_preview_video_spec,
    format_slot_checklist,
)
from app.skills.store import SkillNotFoundError, get_skill_version

skills_router = APIRouter()

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class SlotPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_version_id: UUID
    name: str
    duration_s: float
    style_preset: StylePresetId
    locale: Literal["zh", "en"]
    video_spec: dict[str, Any]
    slots: list[SlotManifestItem]
    copyable_checklist: str


class SlotPreviewExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style_preset: StylePresetId | None = None
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    locale: Literal["zh", "en"] = "zh"
    include_sfx: bool = True


def _font_media_type(filename: str) -> str:
    return "font/ttf" if filename.lower().endswith(".ttf") else "font/otf"


@skills_router.get("/fonts/{filename}")
async def get_pinned_font(filename: str) -> FileResponse:
    """Serve strictly allowlisted pinned font files for browser Remotion Player."""
    if filename not in ALLOWED_FONT_FILENAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Font not found")
    path = (FONTS_DIR / filename).resolve()
    if path.parent != FONTS_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Font not found")
    return FileResponse(
        path=path,
        media_type=_font_media_type(filename),
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def _load_owner_blueprint(
    db: DBDep, *, owner_id: UUID, skill_version_id: UUID
) -> tuple[str, SkillBlueprintV1]:
    try:
        version = await get_skill_version(
            db, owner_id=owner_id, skill_version_id=skill_version_id
        )
    except SkillNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill version not found.",
        ) from exc

    supported = (version.capability_report or {}).get("supported") or []
    if BLUEPRINT_CAPABILITY not in supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This Skill version is not a slot_blueprint_v1 template and cannot generate a slot preview.",
        )
    try:
        bp = load_blueprint_from_skill_version(version)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    skill = await db.get(UserSkill, version.skill_id)
    name = skill.name if skill is not None else "template"
    return name, bp


def _effective_preset_id(
    bp: SkillBlueprintV1, style_preset: StylePresetId | None
) -> StylePresetId:
    if style_preset is not None:
        return style_preset
    if bp.style is not None:
        return bp.style.preset_id
    return "institutional_dark"


@skills_router.get(
    "/{skill_version_id}/slot-preview",
    response_model=SlotPreviewResponse,
)
async def get_slot_preview(
    skill_version_id: UUID,
    style_preset: StylePresetId | None = Query(default=None),
    accent_color: str | None = Query(default=None),
    locale: Literal["zh", "en"] = Query(default="zh"),
    db: DBDep = None,
    current_user: User = Depends(get_current_user_required),
) -> SlotPreviewResponse:
    """Deterministically compile a numbered [01]..[N] slot preview VideoSpec."""
    clean_accent: str | None = None
    if accent_color is not None and accent_color.strip():
        clean_accent = accent_color.strip()
        if not _HEX_COLOR_RE.fullmatch(clean_accent):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="accent_color must be a 6-digit hex color like #14B8A6.",
            )

    name, bp = await _load_owner_blueprint(
        db, owner_id=current_user.id, skill_version_id=skill_version_id
    )
    spec, slots, _, duration_s = build_slot_preview_video_spec(
        bp,
        skill_version_id=skill_version_id,
        style_preset=style_preset,
        accent_color=clean_accent,
        locale=locale,
        font_url_prefix="/api/v1/skills/fonts",
        inline_placeholders=True,
    )
    checklist = format_slot_checklist(slots, locale=locale, template_name=name)
    return SlotPreviewResponse(
        skill_version_id=skill_version_id,
        name=name,
        duration_s=duration_s,
        style_preset=_effective_preset_id(bp, style_preset),
        locale=locale,
        video_spec=spec,
        slots=slots,
        copyable_checklist=checklist,
    )


async def _synthesize_blueprint_sfx_inline(
    bp: SkillBlueprintV1,
    *,
    render_root: str,
) -> dict[str, tuple[UUID, str, int, str]]:
    """Synthesize unique blueprint SFX cues via apps/render into data:audio/wav URLs."""
    if not bp.sfx_cues:
        return {}
    endpoint = f"{render_root}/synthesize-sfx"
    cache: dict[str, tuple[UUID, str, int, str]] = {}
    out: dict[str, tuple[UUID, str, int, str]] = {}
    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            for cue in bp.sfx_cues:
                sound_spec = build_sound_spec(
                    cue.recipe_id, params=cue.params, seed=cue.seed
                )
                spec_hash = sound_spec_digest(sound_spec)
                if spec_hash not in cache:
                    resp = await client.post(
                        endpoint,
                        json={
                            "recipe_id": sound_spec["recipe_id"],
                            "params": sound_spec["params"],
                            "seed": sound_spec["seed"],
                        },
                    )
                    if resp.status_code != 200:
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Render SFX synthesis unavailable (status {resp.status_code}).",
                        )
                    payload = resp.json()
                    wav_b64 = payload["wav_base64"]
                    wav_bytes = base64.b64decode(wav_b64)
                    wav_digest = hashlib.sha256(wav_bytes).hexdigest()
                    dur_ms = float((payload.get("acoustics") or {}).get("duration_ms") or 350.0)
                    dur_ticks = max(1, seconds_to_ticks(dur_ms / 1000.0, SOURCE_TIMEBASE))
                    snap_id = uuid5(NAMESPACE_URL, f"slot-sfx-v2:{spec_hash}:{wav_digest}")
                    data_url = f"data:audio/wav;base64,{wav_b64}"
                    cache[spec_hash] = (snap_id, wav_digest, dur_ticks, data_url)
                out[cue.cue_id] = cache[spec_hash]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Render service is unavailable for SFX synthesis: {type(exc).__name__}",
        ) from exc
    return out


@skills_router.post("/{skill_version_id}/slot-preview/export")
async def export_slot_preview_mp4(
    skill_version_id: UUID,
    body: SlotPreviewExportRequest,
    request: Request,
    db: DBDep = None,
    current_user: User = Depends(get_current_user_required),
) -> Response:
    """Render and return a 1080p MP4 numbered slot promo via the render service."""
    name, bp = await _load_owner_blueprint(
        db, owner_id=current_user.id, skill_version_id=skill_version_id
    )
    render_root = settings.render_url.removesuffix("/render").rstrip("/")

    sfx_snapshots: dict[str, tuple[UUID, str, int, str]] | None = None
    if body.include_sfx and bp.sfx_cues:
        sfx_snapshots = await _synthesize_blueprint_sfx_inline(
            bp, render_root=render_root
        )

    api_base = str(request.base_url).rstrip("/")
    spec, _, _, _ = build_slot_preview_video_spec(
        bp,
        skill_version_id=skill_version_id,
        style_preset=body.style_preset,
        accent_color=body.accent_color,
        locale=body.locale,
        font_url_prefix=f"{api_base}/api/v1/skills/fonts",
        inline_placeholders=True,
        sfx_snapshots=sfx_snapshots,
    )

    endpoint = f"{render_root}/render-mp4"
    try:
        async with httpx.AsyncClient(
            timeout=max(120.0, float(settings.render_timeout_seconds)),
            trust_env=False,
        ) as client:
            resp = await client.post(endpoint, json={"spec": spec})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Video render service is currently unavailable: {type(exc).__name__}",
        ) from exc

    if resp.status_code != 200:
        detail = "Video render service failed to export slot preview."
        try:
            err_body = resp.json()
            if isinstance(err_body, dict) and err_body.get("error"):
                detail = str(err_body["error"])
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )

    safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-") or "template"
    preset_id = _effective_preset_id(bp, body.style_preset)
    filename = f"{safe_slug}-{preset_id}-{body.locale}-slot-promo.mp4"
    return Response(
        content=resp.content,
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
