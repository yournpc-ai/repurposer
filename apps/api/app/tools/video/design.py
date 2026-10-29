"""The design orchestration for the video content chain (B1/B2).

One entry — ``design_video`` — serves both chat paths. It owns the IO half
of design (capture reuse, snapshot freezing, the director call); content
law stays in app/editing (the write door is apply_composition_edits, always
through editing/service). The whole flow rides a DEDICATED session: the
write door commits, and a chat turn's long transaction never wraps it.

Two material paths:
- website promo: the project's captured WEB_PAGE assets → frozen snapshots
  → the launch-film template instantiated from the director's slots;
- motion graphics: the message's copy → the MG director → free scenes.

A redraft (``composition_id`` present) redesigns the SAME work's direction
into a child version; its material is the base version's own bound
snapshots — never a silent recapture.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import UUID

import structlog
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.director import (
    DirectionRejected,
    LaunchFilmDirection,
    MixedDirection,
    ProgramDirection,
    resolve_launch_direction,
    resolve_mixed_direction,
    validate_generated_image_direction,
    validate_mg_direction,
    validate_program_direction,
)
from app.editing.edits import AddClip, Op
from app.editing.schemas import SpeechObject
from app.editing.service import (
    compute_change_set,
    redraft_batch,
    version_read_dict,
)
from app.editing.store import (
    apply_composition_edits,
    content_of,
    get_video_version,
    snapshot_facts,
)
from app.editing.storyboard import storyboard_payload
from app.editing.templates import (
    DesignSlots,
    MusicBed,
    ViewFact,
    instantiate_generated_image,
    instantiate_mg,
    instantiate_mixed,
    instantiate_program,
    instantiate_template,
    load_template,
)
from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus, AssetType, DesignVideoArgs
from app.models.tables import Asset, Output, Project, SourceSnapshot
from app.tools.video.agents import (
    image_director,
    mg_director,
    mixed_director,
    program_director,
    video_director,
)
from app.tools.video.narration import narration_synth_config, resolve_video_voice
from app.tools.video.programs import ensure_generator_clip
from app.tools.video.preparation import (
    snapshot_music_track,
    snapshot_video_asset,
    snapshot_video_output,
    snapshot_web_asset,
)

logger = structlog.get_logger()

# The capture settle wait (the film chain's same law): the design drafts
# from the captured world, so a freshly-declared URL's capture completes
# inside the design beat — bounded, honestly refused past the ceiling.
_CAPTURE_SETTLE_WAIT_S = 1800.0
_CAPTURE_SETTLE_POLL_S = 2.0
# Director repair budget: one first answer + bounded grounding repairs.
_MAX_DIRECTION_ATTEMPTS = 3
_OPS = TypeAdapter(list[Op])


class DesignError(ValueError):
    """A design refusal whose text is model-facing (capture gap, grounding
    failure, write-door rejection)."""


class CaptureSettleTimeout(DesignError):
    """Pages still in flight past the ceiling — the draft refuses a
    half-captured world."""


async def _await_captures_settled(
    db: AsyncSession, project_id: UUID, *, urls: set[str] | None = None
) -> None:
    """Wait until the project's WEB_PAGE captures leave PENDING/PROCESSING
    (bounded). Reads re-fresh (populate_existing) so the worker's commits
    show through."""
    deadline = time.monotonic() + _CAPTURE_SETTLE_WAIT_S
    await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)
    while True:
        rows = list(
            (
                await db.execute(
                    select(Asset)
                    .where(
                        Asset.project_id == project_id,
                        Asset.type == AssetType.WEB_PAGE,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        in_flight = [
            a for a in rows
            if a.processing_status in (AssetStatus.PENDING, AssetStatus.PROCESSING)
            and (urls is None or (a.meta or {}).get("capture_url") in urls)
        ]
        if not in_flight:
            return
        if time.monotonic() >= deadline:
            raise CaptureSettleTimeout(
                f"the page capture is still running after "
                f"{_CAPTURE_SETTLE_WAIT_S:.0f}s — the design refused to "
                "draft from a half-captured world; try again in a moment"
            )
        await asyncio.sleep(_CAPTURE_SETTLE_POLL_S)


async def _project_web_assets(db: AsyncSession, project_id: UUID) -> list[Asset]:
    """The project's genuinely-captured pages, oldest first."""
    return list(
        (
            await db.execute(
                select(Asset)
                .where(
                    Asset.project_id == project_id,
                    Asset.type == AssetType.WEB_PAGE,
                    Asset.processing_status == AssetStatus.COMPLETED,
                )
                .order_by(Asset.created_at)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


def _view_facts(snapshots: list[SourceSnapshot]) -> list[ViewFact]:
    """Every captured view, in preference order (fold first per page, bind
    order across pages); a view with unreadable facts is skipped, never
    invented."""
    views: list[ViewFact] = []
    for page, snapshot in enumerate(snapshots):
        for view in (snapshot.meta or {}).get("views") or []:
            if not view.get("storage_key") or not view.get("width") or not view.get("height"):
                continue
            views.append(
                ViewFact(
                    snapshot_id=snapshot.id,
                    snapshot_digest=snapshot.digest,
                    view_id=str(view["view_id"]),
                    width=int(view["width"]),
                    height=int(view["height"]),
                    elements=list(view.get("elements") or []),
                    heading=str(view.get("heading") or ""),
                    page=page,
                )
            )
    return views


def _lines_text(snapshot_metas: list[dict[str, Any]]) -> str:
    from app.editing.grounding import manifest_lines

    lines = manifest_lines(snapshot_metas)
    if not lines:
        return "(the captured pages exposed no citable text)"
    return "\n".join(f"L{line.index} [{line.kind}] {line.text}" for line in lines)


def _capture_status_text(snapshot_metas: list[dict[str, Any]]) -> str:
    """Frozen capture completeness, kept outside the citable product copy."""
    rows: list[str] = []
    for page, meta in enumerate(snapshot_metas, start=1):
        truncated = meta.get("body_truncated")
        if truncated is True:
            state = "TRUNCATED — the rendered body is incomplete; do not claim full-page coverage"
        elif truncated is False:
            state = "not truncated by the bounded capture"
        else:
            state = "UNKNOWN — this older snapshot froze no body-truncation fact"
        rows.append(f"page {page}: rendered body {state}")
    return "\n".join(rows) or "no captured-page completeness facts"


def _views_text(views: list[ViewFact]) -> str:
    rows: list[str] = []
    for i, view in enumerate(views, start=1):
        elements = []
        for e in view.elements[:24]:
            flags = " covered" if e.get("covered") else ""
            if e.get("storage_key"):
                flags += " +element-image"
                css = e.get("css_box")
                if isinstance(css, dict):
                    flags += (
                        " CSS(" + ",".join(
                            f"{float(css.get(key) or 0):g}"
                            for key in ("x", "y", "width", "height")
                        ) + f")@{float(e.get('device_scale_factor') or 1):g}x"
                    )
            label = str(e.get("text") or "")[:60]
            elements.append(f"{e.get('id')}:{e.get('kind')}{flags} {label!r}")
        rows.append(
            f"V{i} (page {view.page}, view {view.view_id}, "
            f"{view.width}x{view.height}, heading {view.heading!r})\n  elements: "
            + ("; ".join(elements) if elements else "(no element inventory)")
        )
    return "\n".join(rows)


def _video_materials_text(snapshots: list[SourceSnapshot]) -> str:
    """Compact frozen media facts for source-window and caption decisions."""
    rows: list[str] = []
    for snapshot in snapshots:
        meta = snapshot.meta or {}
        media = meta.get("media") or {}
        rows.append(
            f"snapshot_id={snapshot.id} · title={str(meta.get('title') or '').strip()!r} · "
            f"duration={(snapshot.duration_ticks or 0) / 90000:.3f}s · "
            f"{media.get('width')}x{media.get('height')} · has_audio={bool(media.get('has_audio'))}"
        )
        transcript = str(meta.get("transcript") or "").strip()
        if transcript:
            rows.append("transcript: " + transcript[:12000])
        timed: list[str] = []
        for word in (meta.get("words") or [])[:600]:
            text = str(word.get("word") or word.get("text") or "").strip()
            if text:
                timed.append(f"{float(word.get('start') or 0):.2f}-{float(word.get('end') or 0):.2f}:{text}")
        if timed:
            rows.append("word timings (SOURCE seconds): " + " ".join(timed))
    return "\n".join(rows)


async def _directed_mixed(
    *,
    snapshots: list[SourceSnapshot],
    focus: str | None,
    instruction: str | None,
    language: str | None,
    current: str | None,
    target_seconds: float | None,
) -> MixedDirection:
    facts = {
        snapshot.id: {
            "kind": snapshot.kind,
            "digest": snapshot.digest,
            "duration_ticks": snapshot.duration_ticks,
            "storage_key": snapshot.storage_key,
            "meta": snapshot.meta or {},
        }
        for snapshot in snapshots
    }
    materials_text = _video_materials_text(snapshots)
    feedback: str | None = None
    last_violations: list[str] = []
    for _attempt in range(_MAX_DIRECTION_ATTEMPTS):
        direction = await mixed_director.call(
            materials_text=materials_text,
            focus=focus,
            instruction=instruction,
            language=language,
            current=current,
            target_seconds=target_seconds,
            repair_feedback=feedback,
        )
        try:
            return resolve_mixed_direction(
                direction, snapshot_facts=facts, target_seconds=target_seconds
            )
        except DirectionRejected as exc:
            last_violations = exc.violations
            feedback = "\n".join(f"- {item}" for item in exc.violations)
    raise DesignError(
        "the mixed-video director's answer stayed invalid after "
        f"{_MAX_DIRECTION_ATTEMPTS} attempts: " + "; ".join(last_violations)
    )


async def _view_media_inputs(snapshots: list[SourceSnapshot], views: list[ViewFact]) -> list[Any]:
    """The walk views' screenshots ground the director's camera choices
    (compressed thumbnails — a creative judgment needs legibility, not
    pixels). Bounded count; an unreadable image degrades to text inventory."""
    from app.pipeline.step_context import media_input_for_image  # deferred: execution layer

    items: list[Any] = []
    keys_by_view: dict[tuple[UUID, str], str] = {}
    for snapshot in snapshots:
        for view in (snapshot.meta or {}).get("views") or []:
            keys_by_view[(snapshot.id, str(view.get("view_id")))] = str(view.get("storage_key") or "")
    for i, view in enumerate(views[:8], start=1):
        key = keys_by_view.get((view.snapshot_id, view.view_id))
        if not key:
            continue
        item = await media_input_for_image(
            key,
            caption=f"V{i} — page {view.page}, view {view.view_id} ({view.heading or 'captured view'})",
            max_px=1280,
        )
        if item is not None:
            items.append(item)
        if i <= 4:
            element = next(
                (candidate for candidate in view.elements if candidate.get("storage_key")),
                None,
            )
            if element is not None:
                crop = await media_input_for_image(
                    str(element["storage_key"]),
                    caption=(
                        f"V{i} element {element.get('id')} — the captured target crop; "
                        "its CSS box and pixel mapping are listed in the view inventory"
                    ),
                    max_px=1280,
                )
                if crop is not None:
                    items.append(crop)
    return items


def _current_design_summary(content_scenes: list[dict[str, Any]]) -> str:
    """The redraft prompt's current-design echo: scene keys + intents +
    on-screen text — compact, factual."""
    rows: list[str] = []
    for scene in content_scenes:
        texts = []
        for clip in scene.get("clips", []):
            if clip.get("object_kind") == "text" and clip.get("text"):
                texts.append(str(clip["text"]).replace("\n", " / ")[:80])
        # Director answers use template scene keys, not the stored Scene ids.
        scene_key = str(scene["scene_id"])
        if scene_key.startswith("scn_"):
            scene_key = scene_key[4:]
        rows.append(
            f"- {scene_key}: {scene.get('intent') or ''}"
            + (" | " + "; ".join(texts) if texts else "")
            + (" | narration: " + str(scene["narration"]).replace("\n", " / ") if scene.get("narration") else "")
        )
    return "\n".join(rows)


async def _directed_launch_slots(
    *,
    template_min_views: int,
    snapshot_metas: list[dict[str, Any]],
    views: list[ViewFact],
    images: list[Any],
    focus: str | None,
    instruction: str | None,
    language: str | None,
    current: str | None,
) -> DesignSlots:
    """The bounded direction loop: answer → resolve/ground → repair with the
    violation echo. Past the budget the design refuses honestly."""
    lines_text = _lines_text(snapshot_metas)
    capture_status_text = _capture_status_text(snapshot_metas)
    views_text = _views_text(views)
    feedback: str | None = None
    last_violations: list[str] = []
    for _attempt in range(_MAX_DIRECTION_ATTEMPTS):
        direction: LaunchFilmDirection = await video_director.call(
            lines_text=lines_text,
            capture_status_text=capture_status_text,
            views_text=views_text,
            focus=focus,
            instruction=instruction,
            language=language,
            current=current,
            page_images=images,
            repair_feedback=feedback,
        )
        try:
            return resolve_launch_direction(
                direction,
                snapshot_metas=snapshot_metas,
                views=views,
                template_min_views=template_min_views,
            )
        except DirectionRejected as exc:
            last_violations = exc.violations
            feedback = "\n".join(f"- {v}" for v in exc.violations)
    raise DesignError(
        "the director's answer stayed ungrounded after "
        f"{_MAX_DIRECTION_ATTEMPTS} attempts: " + "; ".join(last_violations)
    )


async def _resolve_bed(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    requested: str | None,
    base_content: Any,
) -> MusicBed | None:
    """The bed's one resolution seat for the website-promo path (音频三态):
    an explicit ``off`` is terminal; a redraft re-pins the BASE version's
    own bed snapshot (a redesign never silently swaps the music); a fresh
    design resolves persona skin → calm default. ``None`` = silent film.
    """
    if requested == "off":
        return None
    if base_content is not None:
        for track in base_content.timeline.tracks:
            if track.role != "music":
                continue
            for clip in track.clips:
                if clip.source is not None:
                    facts = await snapshot_facts(db, {clip.source.snapshot_id})
                    fact = facts.get(clip.source.snapshot_id)
                    if fact is not None and fact.get("duration_ticks"):
                        return MusicBed(
                            snapshot_id=clip.source.snapshot_id,
                            snapshot_digest=fact["digest"],
                            duration_ticks=int(fact["duration_ticks"]),
                        )
        return None
    from app.pipeline.music import resolve_bed_track  # deferred: pipeline seam

    project = await db.get(Project, project_id)
    if project is None:
        return None
    track = await resolve_bed_track(db, project, requested)
    if track is None:
        return None
    snapshot = await snapshot_music_track(db, track, owner_id=owner_id)
    if not snapshot.duration_ticks:
        return None
    return MusicBed(
        snapshot_id=snapshot.id,
        snapshot_digest=snapshot.digest,
        duration_ticks=int(snapshot.duration_ticks),
    )


def _base_narration(content: Any) -> tuple[str | None, dict[str, Any] | None]:
    clips = sorted(
        (
            clip
            for track in content.timeline.tracks
            for clip in track.clips
            if isinstance(clip.object, SpeechObject)
        ),
        key=lambda clip: clip.range.start,
    )
    if not clips:
        return None, None
    voices = [
        {
            "provider": clip.object.provider,
            "model": clip.object.model,
            "voice_id": clip.object.voice_id,
            "language": clip.object.language,
        }
        for clip in clips
    ]
    if any(voice != voices[0] for voice in voices[1:]):
        raise DesignError("an open redraft of per-scene voice changes is ambiguous; use update_speech")
    return "\n".join(clip.object.text for clip in clips), voices[0]


async def _resolve_narration_voice(
    db: AsyncSession,
    *,
    project_id: UUID,
    base_content: Any,
) -> dict[str, Any] | None:
    if base_content is not None:
        return _base_narration(base_content)[1]
    from app.platform.project_context import resolve_persona

    project = await db.get(Project, project_id)
    persona = await resolve_persona(db, project) if project is not None else None
    config = narration_synth_config()
    return {
        "provider": config["provider"],
        "model": config["model"],
        "voice_id": resolve_video_voice((persona.voice or None) if persona is not None else None),
    }


async def _design_locked(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    args: DesignVideoArgs,
    request_id: str | None,
) -> dict[str, Any]:
    from app.pipeline.assets import (  # deferred: capture lifecycle owner
        create_web_page_assets_committed_from_urls,
    )

    base_content = None
    base_version = None
    composition = None
    if args.composition_id is not None:
        composition, base_version = await get_video_version(
            db, owner_id=owner_id, composition_id=args.composition_id
        )
        base_content = content_of(base_version)

    mixed_design = False
    if not args.text:
        mixed_design = bool(args.material_output_ids)
        if base_content is not None:
            mixed_design = any(
                clip.object.kind == "video"
                for track in base_content.timeline.tracks
                for clip in track.clips
            )
        if args.material_asset_ids:
            asset_types = list((await db.scalars(select(Asset.type).where(
                Asset.id.in_(args.material_asset_ids), Asset.user_id == owner_id
            ))).all())
            mixed_design = mixed_design or AssetType.VIDEO in asset_types

    if args.mode == "program":
        # ---- controlled visual program: Agent source → exact preview → version ----
        direction: ProgramDirection = await program_director.call(
            text=args.text or "",
            focus=args.focus,
            instruction=args.specific_instruction or "",
            language=args.language,
            target_seconds=args.target_seconds,
        )
        validate_program_direction(
            direction, source_text=args.text, target_seconds=args.target_seconds
        )
        raw_ops = instantiate_program(
            direction, aspect=args.aspect or "16:9", background=args.background
        )
        provenance = {"skill": None, "mode": "program"}
        name = (direction.name or "").strip()[:24] or ""
    elif args.mode == "image":
        # ---- model image: save the request now; authorized production generates later ----
        image_direction = await image_director.call(
            text=args.text or "",
            focus=args.focus,
            instruction=args.specific_instruction or "",
            language=args.language,
            target_seconds=args.target_seconds,
        )
        validate_generated_image_direction(
            image_direction, source_text=args.text, target_seconds=args.target_seconds
        )
        raw_ops = instantiate_generated_image(
            image_direction, aspect=args.aspect or "16:9", background=args.background
        )
        provenance = {"skill": None, "mode": "image"}
        name = (image_direction.name or "").strip()[:24] or ""
    elif args.text:
        # ---- the MG path: no capture, no snapshot — copy in, scenes out ----
        if args.composition_id is not None and args.material_urls:
            raise DesignError("a redraft keeps its material; new URLs start a new work")
        current = None
        if base_content is not None:
            current = _current_design_summary(
                storyboard_payload(
                    base_content,
                    composition_id=composition.id,
                    version_id=base_version.id,
                    version=base_version.version,
                    content_digest=base_version.content_digest,
                )["scenes"]
            )
        base_narration = _base_narration(base_content)[0] if base_content is not None else None
        narration_enabled = args.narration_enabled is not False and (
            args.narration is not None or args.narration_enabled is True or base_narration is not None
        )
        narration_text = (
            args.narration if args.narration is not None else base_narration
        ) if narration_enabled else None
        if narration_enabled and not narration_text:
            raise DesignError("a narrated redraft needs exact spoken copy or an existing SpeechObject")
        narration_voice = (
            await _resolve_narration_voice(db, project_id=project_id, base_content=base_content)
            if narration_enabled else None
        )
        direction = await mg_director.call(
            text=args.text,
            focus=args.focus,
            instruction=args.specific_instruction,
            language=args.language,
            current=current,
            scene_count=args.scene_count,
            target_seconds=args.target_seconds,
            narration=narration_text,
            background=args.background,
        )
        validate_mg_direction(
            direction,
            source_text=args.text,
            scene_count=args.scene_count,
            target_seconds=args.target_seconds,
            narration_text=narration_text,
        )
        if narration_voice is not None:
            narration_voice["language"] = (
                args.language or direction.language or narration_voice.get("language") or "en"
            ).split("-")[0].split("_")[0].lower()
        bed = await _resolve_bed(
            db,
            owner_id=owner_id,
            project_id=project_id,
            requested=args.music,
            base_content=base_content,
        )
        raw_ops = instantiate_mg(
            direction,
            aspect=args.aspect or "16:9",
            background=args.background,
            narration_voice=narration_voice,
            music_bed=bed,
        )
        provenance = {"skill": None, "mode": "mg", "language": args.language or direction.language}
        name = (direction.name or "").strip()[:24] or ""
    elif mixed_design:
        # ---- mixed media: frozen real video → native title/captions + sound ----
        if composition is not None and (args.material_urls or args.material_asset_ids or args.material_output_ids):
            raise DesignError("a redraft keeps its bound snapshots; new material starts a new work")
        if composition is not None:
            snapshot_ids = [b.snapshot_id for b in base_content.sources]  # type: ignore[union-attr]
            snapshots = [
                row
                for row in (await db.execute(select(SourceSnapshot).where(SourceSnapshot.id.in_(snapshot_ids)))).scalars().all()
                if row.kind == "video"
            ]
            snapshots.sort(key=lambda row: snapshot_ids.index(row.id))
        else:
            snapshots = []
            asset_ids = args.material_asset_ids or []
            if asset_ids:
                assets = list((await db.scalars(select(Asset).where(
                    Asset.id.in_(asset_ids),
                    Asset.user_id == owner_id,
                    Asset.type == AssetType.VIDEO,
                    Asset.processing_status == AssetStatus.COMPLETED,
                ))).all())
                if len(assets) != len(set(asset_ids)):
                    raise DesignError("every mixed-design asset must be an accessible, processed video")
                assets.sort(key=lambda item: asset_ids.index(item.id))
                snapshots.extend([await snapshot_video_asset(db, item, owner_id=owner_id) for item in assets])
            output_ids = args.material_output_ids or []
            if output_ids:
                outputs = list((await db.scalars(select(Output).join(Project, Output.project_id == Project.id).where(
                    Output.id.in_(output_ids), Project.user_id == owner_id
                ))).all())
                if len(outputs) != len(set(output_ids)):
                    raise DesignError("every mixed-design output must be accessible to this user")
                outputs.sort(key=lambda item: output_ids.index(item.id))
                snapshots.extend([await snapshot_video_output(db, item, owner_id=owner_id) for item in outputs])
        if not snapshots:
            raise DesignError("the base version binds no real video — choose a recording as material")
        await db.flush()
        current = None
        if base_content is not None:
            current = _current_design_summary(
                storyboard_payload(
                    base_content,
                    composition_id=composition.id,
                    version_id=base_version.id,
                    version=base_version.version,
                    content_digest=base_version.content_digest,
                )["scenes"]
            )
        direction = await _directed_mixed(
            snapshots=snapshots,
            focus=args.focus,
            instruction=args.specific_instruction,
            language=args.language,
            current=current,
            target_seconds=args.target_seconds,
        )
        selected = next(snapshot for snapshot in snapshots if snapshot.id == direction.source_snapshot_id)
        bed = await _resolve_bed(
            db,
            owner_id=owner_id,
            project_id=project_id,
            requested=args.music,
            base_content=base_content,
        )
        raw_ops = instantiate_mixed(
            direction,
            snapshot_digest=selected.digest,
            aspect=args.aspect or "16:9",
            background=args.background,
            music_bed=bed,
        )
        provenance = {"skill": None, "mode": "mixed"}
        name = (direction.name or "").strip()[:24] or str((selected.meta or {}).get("title") or "")[:24]
    else:
        # ---- the website-promo path: capture → snapshot → template --------
        if composition is not None and (args.material_urls or args.material_asset_ids):
            raise DesignError("a redraft keeps its bound snapshots; new material needs an explicit new design")
        if args.composition_id is None and args.material_urls:
            await create_web_page_assets_committed_from_urls(
                project_id, owner_id, args.material_urls
            )
            await _await_captures_settled(
                db, project_id, urls={url.strip() for url in args.material_urls}
            )
        template = load_template("launch-film")
        if composition is not None:
            # Redraft: the base version's OWN bound snapshots are the world.
            snapshot_ids = [b.snapshot_id for b in base_content.sources]  # type: ignore[union-attr]
            snapshots = [
                row
                for row in (await db.execute(select(SourceSnapshot).where(SourceSnapshot.id.in_(snapshot_ids)))).scalars().all()
                if row.kind == "web"
            ]
            snapshots.sort(key=lambda row: snapshot_ids.index(row.id))
            if not snapshots:
                raise DesignError("the base version binds no web snapshots — design a new work")
        else:
            if args.material_asset_ids:
                assets = list((await db.scalars(select(Asset).where(
                    Asset.id.in_(args.material_asset_ids), Asset.user_id == owner_id,
                    Asset.type == AssetType.WEB_PAGE, Asset.processing_status == AssetStatus.COMPLETED,
                ))).all())
                if len(assets) != len(set(args.material_asset_ids)) or any(not (a.meta or {}).get("shots") for a in assets):
                    raise DesignError("a referenced webpage is inaccessible or not fully captured")
                assets.sort(key=lambda a: args.material_asset_ids.index(a.id))
            else:
                assets = [a for a in await _project_web_assets(db, project_id) if (a.meta or {}).get("shots")]
            if args.material_urls:
                requested_urls = {url.strip() for url in args.material_urls}
                assets = [
                    a for a in assets
                    if (a.meta or {}).get("capture_url") in requested_urls
                ]
            if not assets:
                raise DesignError(
                    "the project has no captured web page yet — send the site's "
                    "URL so the system can capture it before designing"
                )
            snapshots = [await snapshot_web_asset(db, a, owner_id=owner_id) for a in assets]
            await db.flush()
        views = _view_facts(snapshots)
        if len(views) < template.min_views:
            raise DesignError(
                f"only {len(views)} usable page views are captured; this arc "
                f"needs at least {template.min_views} — capture more of the page first"
            )
        snapshot_metas = [s.meta or {} for s in snapshots]
        images = await _view_media_inputs(snapshots, views)
        current = None
        if base_content is not None:
            current = _current_design_summary(
                storyboard_payload(
                    base_content,
                    composition_id=composition.id,
                    version_id=base_version.id,
                    version=base_version.version,
                    content_digest=base_version.content_digest,
                )["scenes"]
            )
        slots = await _directed_launch_slots(
            template_min_views=template.min_views,
            snapshot_metas=snapshot_metas,
            views=views,
            images=images,
            focus=args.focus,
            instruction=args.specific_instruction,
            language=args.language,
            current=current,
        )
        bed = await _resolve_bed(
            db,
            owner_id=owner_id,
            project_id=project_id,
            requested=args.music,
            base_content=base_content,
        )
        raw_ops = instantiate_template(template, slots, views, music_bed=bed)
        provenance = {
            "skill": "launch-film",
            "template_id": template.template_id,
            "template_version": template.template_version,
        }
        name = slots.name or _fallback_name(snapshot_metas)

    provenance.setdefault("language", args.language or ((base_version.skill_provenance or {}).get("language") if base_version else None))
    ops = _OPS.validate_python(raw_ops)
    for op in ops:
        if (
            isinstance(op, AddClip)
            and op.clip.object.kind == "generator"
            and op.clip.object.runtime == "drawing-v1"
        ):
            # Preview is a bounded candidate preflight. Orphaned content-
            # addressed media from a later validation rejection is reusable;
            # it never becomes a SourceSnapshot or a delivered Output.
            await ensure_generator_clip(op.clip)
    if composition is None:
        composition, version, replayed = await apply_composition_edits(
            db,
            owner_id=owner_id,
            origin_project_id=project_id,
            ops=ops,
            request_id=request_id,
            name=name,
            skill_provenance=provenance,
        )
        base_content = None
    else:
        ops = redraft_batch(base_content, ops)  # type: ignore[arg-type]
        composition, version, replayed = await apply_composition_edits(
            db,
            owner_id=owner_id,
            composition_id=composition.id,
            base_version_id=base_version.id,  # type: ignore[union-attr]
            base_digest=base_version.content_digest,  # type: ignore[union-attr]
            ops=ops,
            request_id=request_id,
            skill_provenance=provenance,
        )

    new_content = content_of(version)
    facts = await snapshot_facts(db, {b.snapshot_id for b in new_content.sources})
    payload = storyboard_payload(
        new_content,
        composition_id=composition.id,
        version_id=version.id,
        version=version.version,
        content_digest=version.content_digest,
        source_facts=facts,
    )
    read = version_read_dict(composition, version, payload)
    if base_content is not None:
        read["change_set"] = compute_change_set(base_content, new_content)
    read["replayed"] = replayed
    return read


def _fallback_name(snapshot_metas: list[dict[str, Any]]) -> str:
    """The honest parametric label when the director named nothing: the
    page's own title line, else the host (never a hard-coded phrase)."""
    from urllib.parse import urlparse

    for meta in snapshot_metas:
        for line in meta.get("lines") or []:
            if line.get("kind") == "title" and str(line.get("text") or "").strip():
                return str(line["text"]).strip()[:24]
    for meta in snapshot_metas:
        url = meta.get("canonical_url")
        if isinstance(url, str) and url:
            return (urlparse(url).netloc or url)[:24]
    return ""


async def design_video(
    *,
    owner_id: UUID,
    project_id: UUID,
    args: DesignVideoArgs,
    request_id: str | None,
) -> dict[str, Any]:
    """The chat seats' one design entry — own session, own transaction."""
    async with AsyncSessionLocal() as db:
        return await _design_locked(
            db,
            owner_id=owner_id,
            project_id=project_id,
            args=args,
            request_id=request_id,
        )
