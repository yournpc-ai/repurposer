"""Owner-scoped global media & asset library routes (/api/v1/assets).

Read-only index over the caller's persistent TOS-backed entities (VIDEO_PROJECT §9.1):
- User-uploaded project/persona assets (``Asset`` with stored ``file_url``)
- Delivered video exports (``Output`` passing ``is_delivered_output``)
- User-generated BGM tracks (``Music`` where ``generated_by_user_id == owner``)
- User-designed custom voices (``Voice`` where ``owner_id == owner`` and ``scope == "user"``)
- User-saved reusable skills (``UserSkill`` + latest ``SkillVersion``)

Never lists object-storage prefixes directly; every record comes from PostgreSQL
with strict owner-scoped authorization.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.dependencies import DBDep, get_current_user_required
from app.models.tables import (
    Asset,
    CompositionVersion,
    Music,
    Output,
    Project,
    SkillVersion,
    User,
    UserSkill,
    Voice,
)
from app.pipeline.outputs import is_delivered_output, visible_outputs_stmt
from app.providers.storage import (
    is_export_location,
    matches_export_location,
    presign_download,
    resolve_stored_url,
    stream_url,
)
from app.skills.resolution import _blueprint_summary_for_version

router = APIRouter()

_MAX_LIBRARY_ITEMS = 200


class LibraryProjectFolder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    upload_count: int
    export_count: int
    total_count: int
    latest_at: datetime | None = None


class LibraryUploadItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    type: str
    project_id: UUID | None = None
    project_title: str | None = None
    stream_url: str | None = None
    duration_seconds: int | None = None
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    processing_status: str
    created_at: datetime | None = None


class LibraryExportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    project_id: UUID
    project_title: str | None = None
    composition_id: UUID | None = None
    composition_version_id: UUID | None = None
    composition_version_number: int | None = None
    video_url: str | None = None
    poster_url: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    created_at: datetime | None = None


class LibraryAudioItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: Literal["music", "voice"]
    title: str
    subtitle: str | None = None
    stream_url: str | None = None
    duration_seconds: float | None = None
    size_bytes: int | None = None
    tags: list[str] = []
    use_count: int = 0
    created_at: datetime | None = None


class LibrarySkillItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: UUID
    skill_version_id: UUID
    name: str
    description: str
    version_number: int
    act_count: int | None = None
    slot_count: int | None = None
    duration_s: float | None = None
    style_preset: str | None = None
    created_at: datetime | None = None


class AssetLibraryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projects: list[LibraryProjectFolder]
    uploads: list[LibraryUploadItem]
    exports: list[LibraryExportItem]
    audio: list[LibraryAudioItem]
    skills: list[LibrarySkillItem]


class AssetDownloadUrlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    expires_in: int


def _safe_int(val: object) -> int | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    return None


def _safe_float(val: object) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _resolve_output_video_and_poster(
    output: Output, *, owner_id: UUID
) -> tuple[str | None, str | None]:
    files = output.files if isinstance(output.files, dict) else {}
    raw_video = None
    for key in ("video", "mp4", "stream", "url", "final"):
        candidate = files.get(key)
        if isinstance(candidate, str) and candidate.strip():
            raw_video = candidate
            break
    video_url: str | None = None
    if raw_video:
        if is_export_location(raw_video):
            video_url = (
                resolve_stored_url(raw_video)
                if matches_export_location(raw_video, owner_id, output.project_id, output.id)
                else None
            )
        else:
            video_url = resolve_stored_url(raw_video)

    raw_poster = None
    for key in ("poster", "thumbnail", "cover", "image"):
        candidate = files.get(key)
        if isinstance(candidate, str) and candidate.strip():
            raw_poster = candidate
            break
    poster_url = resolve_stored_url(raw_poster) if raw_poster else None
    return video_url, poster_url


def _output_title(output: Output, project_title: str | None, version_number: int | None) -> str:
    payload = output.payload if isinstance(output.payload, dict) else {}
    for key in ("name", "title", "hook"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()[:120]
    base = (project_title or "Video").strip()
    if version_number is not None:
        return f"{base} · v{version_number}"
    return base


def _output_duration_and_dims(output: Output) -> tuple[float | None, int | None, int | None]:
    payload = output.payload if isinstance(output.payload, dict) else {}
    spec = output.render_spec if isinstance(output.render_spec, dict) else {}
    duration = _safe_float(payload.get("duration_seconds")) or _safe_float(spec.get("duration_seconds"))
    if duration is None:
        canvas = spec.get("canvas") if isinstance(spec.get("canvas"), dict) else {}
        fps = _safe_float(canvas.get("fps")) or _safe_float(spec.get("fps"))
        frames = _safe_float(spec.get("durationInFrames")) or _safe_float(spec.get("duration_frames"))
        if fps and frames and fps > 0:
            duration = round(frames / fps, 2)
    canvas = spec.get("canvas") if isinstance(spec.get("canvas"), dict) else {}
    width = _safe_int(payload.get("width")) or _safe_int(canvas.get("width")) or _safe_int(spec.get("width"))
    height = _safe_int(payload.get("height")) or _safe_int(canvas.get("height")) or _safe_int(spec.get("height"))
    return duration, width, height


@router.get("/library", response_model=AssetLibraryResponse)
async def get_asset_library(
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> AssetLibraryResponse:
    """Return an owner-scoped index of the user's TOS-backed assets, exports, audio, and saved skills."""
    owner_id = UUID(str(current_user.id))

    # 1. User-uploaded assets that carry an actual stored object key
    asset_rows = list(
        await db.scalars(
            select(Asset)
            .where(Asset.user_id == owner_id, Asset.file_url.is_not(None))
            .order_by(Asset.created_at.desc())
            .limit(_MAX_LIBRARY_ITEMS)
        )
    )

    # 2. Delivered video outputs owned by this user
    output_rows = list(
        await db.scalars(
            visible_outputs_stmt()
            .join(Project, Output.project_id == Project.id)
            .where(Project.user_id == owner_id)
            .order_by(Output.created_at.desc())
            .limit(_MAX_LIBRARY_ITEMS)
        )
    )
    delivered_outputs = [out for out in output_rows if is_delivered_output(out)]

    # 3. Resolve project titles for referenced projects
    project_ids = {
        pid
        for pid in (
            *(a.project_id for a in asset_rows if a.project_id is not None),
            *(o.project_id for o in delivered_outputs if o.project_id is not None),
        )
    }
    project_titles: dict[UUID, str] = {}
    if project_ids:
        proj_rows = list(
            await db.scalars(
                select(Project).where(
                    Project.id.in_(project_ids),
                    Project.user_id == owner_id,
                )
            )
        )
        project_titles = {p.id: p.title for p in proj_rows}

    # 4. Resolve CompositionVersion numbers for delivered outputs
    version_ids = list(
        dict.fromkeys(
            out.composition_version_id
            for out in delivered_outputs
            if out.composition_version_id is not None
        )
    )
    version_numbers: dict[UUID, int] = {}
    if version_ids:
        ver_rows = list(
            await db.scalars(
                select(CompositionVersion).where(CompositionVersion.id.in_(version_ids))
            )
        )
        version_numbers = {v.id: v.version for v in ver_rows}

    uploads: list[LibraryUploadItem] = []
    folder_stats: dict[UUID, dict] = {}

    def _bump_folder(pid: UUID | None, field: Literal["upload_count", "export_count"], ts: datetime | None) -> None:
        if pid is None:
            return
        entry = folder_stats.get(pid)
        if entry is None:
            entry = {
                "id": pid,
                "title": project_titles.get(pid) or "Untitled",
                "upload_count": 0,
                "export_count": 0,
                "latest_at": ts,
            }
            folder_stats[pid] = entry
        entry[field] += 1
        if ts is not None and (entry["latest_at"] is None or ts > entry["latest_at"]):
            entry["latest_at"] = ts

    for asset in asset_rows:
        meta = asset.meta if isinstance(asset.meta, dict) else {}
        asset_type = asset.type.value if hasattr(asset.type, "value") else str(asset.type)
        proc_status = (
            asset.processing_status.value
            if hasattr(asset.processing_status, "value")
            else str(asset.processing_status)
        )
        uploads.append(
            LibraryUploadItem(
                id=asset.id,
                title=asset.display_name or str(asset.id),
                type=asset_type,
                project_id=asset.project_id,
                project_title=project_titles.get(asset.project_id) if asset.project_id else None,
                stream_url=stream_url(asset.file_url),
                duration_seconds=asset.duration_seconds,
                size_bytes=_safe_int(meta.get("size_bytes") or meta.get("file_size")),
                width=_safe_int(meta.get("width")),
                height=_safe_int(meta.get("height")),
                processing_status=proc_status,
                created_at=asset.created_at,
            )
        )
        _bump_folder(asset.project_id, "upload_count", asset.created_at)

    exports: list[LibraryExportItem] = []
    for out in delivered_outputs:
        video_url, poster_url = _resolve_output_video_and_poster(out, owner_id=owner_id)
        if not video_url:
            continue
        ver_num = (
            version_numbers.get(out.composition_version_id)
            if out.composition_version_id is not None
            else None
        )
        p_title = project_titles.get(out.project_id)
        duration_s, width, height = _output_duration_and_dims(out)
        exports.append(
            LibraryExportItem(
                id=out.id,
                title=_output_title(out, p_title, ver_num),
                project_id=out.project_id,
                project_title=p_title,
                composition_id=out.composition_id,
                composition_version_id=out.composition_version_id,
                composition_version_number=ver_num,
                video_url=video_url,
                poster_url=poster_url,
                duration_seconds=duration_s,
                width=width,
                height=height,
                created_at=out.created_at,
            )
        )
        _bump_folder(out.project_id, "export_count", out.created_at)

    # 5. User-owned generated music & designed voices
    music_rows = list(
        await db.scalars(
            select(Music)
            .where(Music.generated_by_user_id == owner_id)
            .order_by(Music.created_at.desc())
            .limit(_MAX_LIBRARY_ITEMS)
        )
    )
    voice_rows = list(
        await db.scalars(
            select(Voice)
            .where(Voice.owner_id == owner_id, Voice.scope == "user")
            .order_by(Voice.created_at.desc())
            .limit(_MAX_LIBRARY_ITEMS)
        )
    )
    audio: list[LibraryAudioItem] = []
    for track in music_rows:
        audio.append(
            LibraryAudioItem(
                id=track.id,
                kind="music",
                title=track.title or track.mood or "Generated track",
                subtitle=track.prompt or track.mood,
                stream_url=f"/api/v1/music/{track.id}/stream",
                duration_seconds=_safe_float(track.duration_seconds),
                size_bytes=_safe_int(track.size_bytes),
                tags=[str(tag) for tag in (track.tags or []) if tag],
                use_count=int(track.use_count or 0),
                created_at=track.created_at,
            )
        )
    for voice in voice_rows:
        has_preview = bool(voice.preview_audio_key or voice.reference_audio_key)
        audio.append(
            LibraryAudioItem(
                id=voice.id,
                kind="voice",
                title=voice.name,
                subtitle=voice.description or voice.design_prompt,
                stream_url=f"/api/v1/voices/{voice.id}/audio" if has_preview else None,
                duration_seconds=None,
                size_bytes=None,
                tags=[str(tag) for tag in (voice.tone_tags or []) if tag],
                use_count=int(voice.use_count or 0),
                created_at=voice.created_at,
            )
        )
    audio.sort(key=lambda item: item.created_at.timestamp() if item.created_at else 0.0, reverse=True)

    # 6. User-saved external skills (latest version per skill)
    skill_rows = list(
        await db.scalars(
            select(UserSkill)
            .where(UserSkill.owner_id == owner_id)
            .order_by(UserSkill.created_at.desc())
            .limit(_MAX_LIBRARY_ITEMS)
        )
    )
    skills: list[LibrarySkillItem] = []
    if skill_rows:
        skill_ids = [s.id for s in skill_rows]
        ver_rows_all = list(
            await db.scalars(
                select(SkillVersion)
                .where(
                    SkillVersion.owner_id == owner_id,
                    SkillVersion.skill_id.in_(skill_ids),
                )
                .order_by(SkillVersion.skill_id, SkillVersion.version.desc())
            )
        )
        latest_by_skill: dict[UUID, SkillVersion] = {}
        for sv in ver_rows_all:
            if sv.skill_id not in latest_by_skill:
                latest_by_skill[sv.skill_id] = sv
        for skill in skill_rows:
            ver = latest_by_skill.get(skill.id)
            if ver is None:
                continue
            caps = [
                str(item)
                for item in ((ver.capability_report or {}).get("supported") or [])
                if isinstance(item, str) and item
            ]
            bp_summary = _blueprint_summary_for_version(ver, caps)
            skills.append(
                LibrarySkillItem(
                    skill_id=skill.id,
                    skill_version_id=ver.id,
                    name=skill.name,
                    description=skill.description,
                    version_number=ver.version,
                    act_count=bp_summary.act_count if bp_summary else None,
                    slot_count=bp_summary.slot_count if bp_summary else None,
                    duration_s=bp_summary.duration_s if bp_summary else None,
                    style_preset=bp_summary.style_preset if bp_summary else None,
                    created_at=ver.created_at or skill.created_at,
                )
            )

    projects = [
        LibraryProjectFolder(
            id=entry["id"],
            title=entry["title"],
            upload_count=entry["upload_count"],
            export_count=entry["export_count"],
            total_count=entry["upload_count"] + entry["export_count"],
            latest_at=entry["latest_at"],
        )
        for entry in sorted(
            folder_stats.values(),
            key=lambda e: e["latest_at"].timestamp() if e["latest_at"] else 0.0,
            reverse=True,
        )
    ]

    return AssetLibraryResponse(
        projects=projects,
        uploads=uploads,
        exports=exports,
        audio=audio,
        skills=skills,
    )


@router.get("/{asset_id}/download", response_model=AssetDownloadUrlResponse)
async def download_asset(
    asset_id: UUID,
    db: DBDep,
    response: Response,
    current_user: User = Depends(get_current_user_required),
) -> AssetDownloadUrlResponse:
    """Issue a short-lived presigned attachment download URL for an owned Asset."""
    owner_id = UUID(str(current_user.id))
    asset = await db.scalar(
        select(Asset).where(Asset.id == asset_id, Asset.user_id == owner_id)
    )
    if asset is None or not asset.file_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    ttl = 300
    raw_name = (asset.display_name or Path(asset.file_url).name or f"{asset.id}").strip()
    # Ensure filename keeps its extension when user-facing title omitted it.
    ext = Path(asset.file_url).suffix
    if ext and not raw_name.lower().endswith(ext.lower()):
        raw_name = f"{raw_name}{ext}"
    url = await presign_download(asset.file_url, ttl=ttl, filename=raw_name)
    response.headers["Cache-Control"] = "private, no-store"
    return AssetDownloadUrlResponse(url=url, expires_in=ttl)
