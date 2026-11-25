"""Evidence from the exported cut, its pinned sources, and the matching saved Skill."""

from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from sqlalchemy import select

API_ROOT = Path(__file__).resolve().parents[1]


def screenshots(directory: Path | None) -> list[Path]:
    if directory is None:
        # Bundled captures of the desktop product surfaces.
        bundled = API_ROOT.parents[1] / "docs/tasks/affectui-evidence/after"
        paths = [bundled / f"{surface}-1280-light.png" for surface in ("home", "projects")]
    else:
        paths = sorted(directory.iterdir()) if directory.is_dir() else []
    images = [p for p in paths if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    if not images:
        raise ValueError("No PNG/JPG product screenshots found. Supply --assets-dir <directory>.")
    for path in images:
        with Image.open(path) as img:
            if img.format not in {"PNG", "JPEG"}:
                raise ValueError(f"Expected a PNG/JPG screenshot: {path}")
            img.verify()
    return images


async def upload_screens(client, project_id, paths):
    attachments = []
    for path in paths:
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        with path.open("rb") as file:
            response = await client.post(
                f"/api/v1/projects/{project_id}/assets/upload",
                data={"type": "image"},
                files={"file": (path.name, file, mime)},
            )
        response.raise_for_status()
        attachments.append({"id": response.json()["id"], "name": path.name, "type": "image"})
    return attachments


def mid_act_seconds(scenes, timebase):
    ordered = sorted((s["range"] for s in scenes), key=lambda r: r["start"])
    if len(ordered) < 3:
        return ()
    return tuple(
        (r["start"] + r["end"]) / (2 * timebase)
        for r in (ordered[0], ordered[len(ordered) // 2], ordered[-1])
    )


def score_cut(version, snapshots, asset_ids):
    from app.editing.catalog import SOUND_ENGINE_NAME, SOUND_ENGINE_VERSION
    from app.editing.timing import SOURCE_TIMEBASE

    tracks = version.timeline["tracks"] if version else []
    scenes = version.scenes if version else []
    settings = version.settings if version else {}
    timebase = settings.get("timebase", SOURCE_TIMEBASE)
    fps = settings.get("fps", {"num": 30, "den": 1})
    frame = fps["den"] / fps["num"]
    anchors = [s["range"]["start"] / timebase for s in scenes]
    effect_peaks = []
    effects = []
    used_images = set()
    speech = any(s.get("speech_clip_ids") for s in scenes)
    for track in tracks:
        for clip in track["clips"]:
            obj = clip["object"]
            source = clip.get("source") or {}
            for ref in [source, *obj.get("resources", [])]:
                snap = snapshots.get(ref.get("snapshot_id"))
                if snap and snap.kind == "image":
                    used_images.add(str(snap.asset_id))
            speech |= obj["kind"] == "speech" or track["role"] == "dialogue"
            snap = snapshots.get(source.get("snapshot_id"))
            meta = (snap.meta or {}) if snap else {}
            origin = meta.get("origin") or {}
            window = source.get("source_range") or {}
            offset = window.get("start", 0) / SOURCE_TIMEBASE
            start = clip["range"]["start"] / timebase
            end = clip["range"]["end"] / timebase
            if track["role"] == "music":
                grid = meta.get("beat_grid") or {}
                rate = grid.get("source_timebase") or 1
                beats = (start + beat / rate - offset for beat in grid.get("beats", []))
                anchors.extend(b for b in beats if start <= b < end)
            if track["role"] == "effect" and obj["kind"] == "audio":
                effects.append(clip["clip_id"])
                if (
                    origin.get("kind") == "sound_recipe"
                    and origin.get("engine") == SOUND_ENGINE_NAME
                    and origin.get("engine_version") == SOUND_ENGINE_VERSION
                ):
                    peak_ms = (origin.get("acoustics") or {}).get("peak_offset_ms")
                    if peak_ms is not None:
                        peak = start + peak_ms / 1000 - offset
                        if start <= peak < end:
                            effect_peaks.append(peak)
    return {
        "uploaded_screenshot_in_cut": bool(used_images & asset_ids),
        "zero_narration": bool(tracks and scenes) and not speech,
        "effect_track_nonempty": bool(effects),
        "sound_engine_peak_on_beat_or_cut": any(
            abs(p - a) <= frame for p in effect_peaks for a in anchors
        ),
    }


def score_delivery(exchanges, preview_status, preview, media):
    opening = exchanges[0] if exchanges else []
    slots = preview.get("slots") or []
    numbered = [f"[{i:02d}]" for i in range(1, len(slots) + 1)]
    return {
        "autonomous_kinetic_launch": any(
            e["tool"] == "load_skill"
            and e["ok"]
            and e["arguments"].get("skill_id") == "kinetic-launch"
            for e in opening
        ),
        "saved_as_skill_in_followup": any(
            e["tool"] == "save_composition_as_skill" and e["ok"]
            for turn in exchanges[1:]
            for e in turn
        ),
        "slot_blueprint_v1_numbered_preview": (
            preview_status == 200
            and bool(slots)
            and [s["code"] for s in slots] == numbered
            and all(code in preview.get("copyable_checklist", "") for code in numbered)
        ),
        "export_media_probe": bool(media and media.passed),
        "launch_duration_25_to_30_seconds": bool(
            media and 25 <= (media.duration_seconds or 0) <= 30
        ),
        "cross_act_midpoint_pngs": bool(
            media and len(media.extracted_pngs) == 3 and media.non_black_frames == 3
        ),
    }


async def inspect_delivery(
    client, db, user_id, project_id, storage_dir, asset_ids, exchanges, out_dir, probe
):
    from app.models.tables import CompositionVersion, Output, SkillVersion, SourceSnapshot
    from app.providers.storage import matches_export_location

    output = await db.scalar(
        select(Output)
        .where(
            Output.project_id == project_id,
            Output.type == "video",
            Output.composition_version_id.is_not(None),
        )
        .order_by(Output.created_at.desc())
        .limit(1)
    )
    version = await db.get(CompositionVersion, output.composition_version_id) if output else None
    media = None
    preview_status = None
    preview = {}
    snapshots = {}
    if version:
        ids = [s["snapshot_id"] for s in version.sources]
        snapshots = {
            str(s.id): s
            for s in await db.scalars(select(SourceSnapshot).where(SourceSnapshot.id.in_(ids)))
        }
        key = (output.files or {}).get("video")
        if matches_export_location(key, user_id, project_id, output.id):
            path = storage_dir / urlsplit(key).path.lstrip("/")
            media = probe(
                path,
                frame_out_dir=out_dir / "frames",
                sample_seconds=mid_act_seconds(version.scenes, version.settings["timebase"]),
            )
        template = await db.scalar(
            select(SkillVersion)
            .where(
                SkillVersion.owner_id == user_id,
                SkillVersion.source_uri
                == f"composition://{version.composition_id}@v{version.version}",
                SkillVersion.capability_report["supported"].contains(["slot_blueprint_v1"]),
            )
            .order_by(SkillVersion.created_at.desc())
            .limit(1)
        )
        if template:
            resp = await client.get(f"/api/v1/skills/{template.id}/slot-preview")
            preview_status = resp.status_code
            if resp.is_success:
                preview = resp.json()
    checks = score_cut(version, snapshots, asset_ids)
    checks.update(score_delivery(exchanges, preview_status, preview, media))
    evidence = {
        "output_id": str(output.id) if output else None,
        "version_id": str(version.id) if version else None,
        "slot_preview_status": preview_status,
        "skill_version_id": preview.get("skill_version_id"),
        "slot_codes": [s["code"] for s in preview.get("slots", [])],
        "scene_midpoints_seconds": mid_act_seconds(version.scenes, version.settings["timebase"])
        if version
        else [],
    }
    return checks, evidence, media
