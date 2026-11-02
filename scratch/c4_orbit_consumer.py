"""Exercise the C4 orbit consumer through existing Agent/edit/render seams."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import av
from PIL import Image
from pydantic import TypeAdapter
from sqlalchemy import select

from app.editing.edits import Op
from app.editing.schemas import CompositionContent, GeneratorObject
from app.editing.service import revise_video
from app.editing.sources import register_snapshot
from app.editing.store import apply_composition_edits, content_of
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AssetStatus,
    AssetType,
    DesignVideoArgs,
    RenderStatus,
    ReviseVideoArgs,
)
from app.models.tables import Asset, Composition, CompositionVersion, Output, Project
from app.providers import storage
from app.tools.video.agents import program_director
from app.tools.video.design import design_video
from app.tools.video.preparation import store_source_bytes
from app.tools.video.produce import queue_composition_render
from app.tools.video.programs import (
    ProgramError,
    enrich_generator_previews,
    generator_preview_images,
    prepare_generator_media,
)

ROOT = Path("/Users/sylas/repurposer")
OUT = ROOT / "scratch/c4-orbit"
STATE_PATH = OUT / "evidence.json"
CREATE_REQUEST = "c4-orbit-agent-v1"
IMAGE_REQUEST = "c4-orbit-native-image-v2"
REVISE_REQUEST = "c4-orbit-speed-v3"
TITLE = "Ideas in motion"
INSTRUCTION = """Create a refined decorative background with at least three concentric
circular orbit tracks around an open central area. Each orbit must have a clearly
different radius and angular speed, and at least one orbit must rotate in the
opposite direction. Put small geometric satellites and symbols (circles, diamonds,
plus signs or star-like polygons) on every orbit, with fine rings and a few subtle
radial markers. Keep the lower central area visually calm for a separate native
title. Use a dark navy field with cyan, violet and warm coral accents. Expose
meaningful scalar parameters including exactly speed_multiplier, orbit_scale and
accent_color, and make the program actually read them. The motion must be
continuous and deterministic."""
OPS = TypeAdapter(list[Op])


def save_state(state: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def generator_of(content: CompositionContent):
    return next(
        clip
        for track in content.timeline.tracks
        for clip in track.clips
        if isinstance(clip.object, GeneratorObject)
    )


def version_summary(read: dict[str, Any], previews: list[dict[str, Any]]) -> dict[str, Any]:
    storyboard = read["storyboard"]
    clips = [clip for scene in storyboard["scenes"] for clip in scene["clips"]] + storyboard[
        "unassigned_clips"
    ]
    return {
        "composition_id": read["composition_id"],
        "composition_version_id": read["composition_version_id"],
        "content_digest": read["content_digest"],
        "version": read["version"],
        "clips": [
            {
                key: clip.get(key)
                for key in (
                    "clip_id",
                    "object_id",
                    "object_kind",
                    "runtime",
                    "program_digest",
                    "parameters",
                    "output",
                    "code",
                    "text",
                    "layout",
                    "fit",
                    "snapshot_id",
                )
                if clip.get(key) is not None
            }
            for clip in clips
        ],
        "generator_previews": previews,
    }


async def preview_observations(read: dict[str, Any]) -> list[dict[str, Any]]:
    observations = []
    for image in await generator_preview_images(read):
        encoded = image.data_url.split(",", 1)[1]
        payload = base64.b64decode(encoded)
        observations.append(
            {
                "caption": image.caption,
                "mime": image.mime,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    return observations


async def project_and_image(state: dict[str, Any]) -> tuple[UUID, UUID]:
    if state.get("project_id") and state.get("owner_id"):
        return UUID(state["project_id"]), UUID(state["owner_id"])
    async with AsyncSessionLocal() as db:
        owner_id = (
            await db.scalars(select(Project.user_id).order_by(Project.created_at.desc()).limit(1))
        ).one()
        project = Project(user_id=owner_id, title="C4 Orbit Generator Consumer", language="en")
        db.add(project)
        await db.flush()
        source = (ROOT / "apps/web/public/icon-512.png").read_bytes()
        with Image.open(io.BytesIO(source)) as image:
            width, height = image.size
        upload_key = await storage.get_upload_path(project.id, owner_id, "c4-orbit-brand-icon.png")
        await storage.save(upload_key, source, content_type="image/png")
        asset = Asset(
            user_id=owner_id,
            project_id=project.id,
            type=AssetType.IMAGE,
            file_url=upload_key,
            title="Repurposer brand icon (project-owned)",
            processing_status=AssetStatus.COMPLETED,
            meta={
                "content_sha256": hashlib.sha256(source).hexdigest(),
                "authorized_source": "apps/web/public/icon-512.png",
            },
        )
        db.add(asset)
        await db.flush()
        await db.commit()
        state.update(
            {
                "project_id": str(project.id),
                "owner_id": str(owner_id),
                "image_asset": {
                    "asset_id": str(asset.id),
                    "title": asset.title,
                    "authorized_source": asset.meta["authorized_source"],
                    "sha256": asset.meta["content_sha256"],
                    "width": width,
                    "height": height,
                },
                "scope": (
                    "Direct domain-tool consumer; no Chat presentation, Run, "
                    "production authorization or credits are fabricated."
                ),
            }
        )
        save_state(state)
        return project.id, owner_id


async def create_agent_version(state: dict[str, Any], project_id: UUID, owner_id: UUID) -> None:
    if state.get("v1"):
        return
    failures = state.setdefault("agent_preflight_failures", [])
    if not failures:
        # The first invocation before this resumable evidence writer reached the
        # bounded runtime and was rejected before any CompositionVersion write.
        failures.append(
            {
                "diagnostic": (
                    "Initial Agent candidate: schema repair corrected overlong prose; "
                    "bounded preview then rejected six line commands with 145 points "
                    "(cap 128)."
                ),
                "version_saved": False,
            }
        )
        save_state(state)
    instruction = INSTRUCTION
    for _ in range(2):
        observations = []
        original_call = program_director.call

        async def capture_call(**ctx):
            direction = await original_call(**ctx)
            observations.append(
                {
                    "request": ctx,
                    "returned_direction": direction.model_dump(mode="json"),
                }
            )
            return direction

        program_director.call = capture_call
        try:
            read = await design_video(
                owner_id=owner_id,
                project_id=project_id,
                request_id=CREATE_REQUEST,
                args=DesignVideoArgs(
                    mode="program",
                    text=TITLE,
                    language="en",
                    target_seconds=6,
                    aspect="16:9",
                    background="#0B1020",
                    specific_instruction=instruction,
                ),
            )
        except ProgramError as exc:
            failures.append(
                {
                    "diagnostic": str(exc),
                    "agent_observations": observations,
                    "version_saved": False,
                }
            )
            save_state(state)
            instruction = (
                f"{INSTRUCTION}\nPrevious candidate failed the bounded preview: {exc}. "
                "Correct that concrete violation. Use ellipse commands for full rings or "
                "keep every line/polygon point list at 96 points or fewer. Keep intent "
                "within 120 characters and visual_description within 240 characters."
            )
            continue
        finally:
            program_director.call = original_call
        assert len(observations) == 1, "candidate was not authored by the real Agent"
        enriched = await enrich_generator_previews(read)
        previews = enriched["generator_previews"]
        assert len(previews) == 1
        state.setdefault("agent_observations", []).extend(observations)
        state["v1"] = version_summary(read, previews)
        state["v1"]["preview_model_inputs"] = await preview_observations(read)
        save_state(state)
        return
    raise RuntimeError("bounded Agent/preview correction did not produce a valid candidate")


async def add_native_image(state: dict[str, Any], owner_id: UUID) -> None:
    if state.get("v2"):
        return
    async with AsyncSessionLocal() as db:
        composition = await db.get(Composition, UUID(state["v1"]["composition_id"]))
        base = await db.get(CompositionVersion, UUID(state["v1"]["composition_version_id"]))
        asset = await db.get(Asset, UUID(state["image_asset"]["asset_id"]))
        data = await storage.read(asset.file_url)
        storage_key, digest = await store_source_bytes(data, ".png", "image/png")
        snapshot = await register_snapshot(
            db,
            owner_id=owner_id,
            asset=asset,
            kind="image",
            storage_key=storage_key,
            digest=digest,
            duration_ticks=None,
            meta={
                "width": state["image_asset"]["width"],
                "height": state["image_asset"]["height"],
                "authorized_source": state["image_asset"]["authorized_source"],
            },
            captured_at=datetime.now(UTC),
        )
        content = content_of(base)
        end = max(scene.range.end for scene in content.scenes)
        ops = OPS.validate_python(
            [
                {"op": "bind_source", "snapshot_id": str(snapshot.id)},
                {
                    "op": "add_track",
                    "track": {
                        "track_id": "trk_authorized_image",
                        "kind": "visual",
                        "role": "main",
                        "order": 2,
                        "clips": [],
                    },
                },
                {
                    "op": "add_clip",
                    "track_id": "trk_authorized_image",
                    "clip": {
                        "clip_id": "clp_authorized_image",
                        "range": {"start": 0, "end": end},
                        "scene_id": "scn_program",
                        "source": {
                            "snapshot_id": str(snapshot.id),
                            "snapshot_digest": digest,
                            "source_range": None,
                        },
                        "object": {
                            "kind": "image",
                            "object_id": "obj_authorized_image",
                            "layout": {"x": 1560.0, "y": 90.0, "width": 220.0, "height": 220.0},
                            "fit": "contain",
                            "transform": {
                                "x": 0.0,
                                "y": 0.0,
                                "scale": 1.0,
                                "rotation": 0.0,
                                "origin": "center",
                            },
                            "opacity": 1.0,
                        },
                        "animations": [],
                    },
                },
            ]
        )
        _, version, _ = await apply_composition_edits(
            db,
            owner_id=owner_id,
            composition_id=composition.id,
            base_version_id=base.id,
            base_digest=base.content_digest,
            ops=ops,
            request_id=IMAGE_REQUEST,
            skill_provenance=base.skill_provenance,
        )
        state["image_asset"]["snapshot_id"] = str(snapshot.id)
        state["image_asset"]["snapshot_digest"] = digest
        state["v2"] = {
            "composition_version_id": str(version.id),
            "content_digest": version.content_digest,
            "version": version.version,
        }
        save_state(state)


async def revise_speed(state: dict[str, Any], owner_id: UUID) -> None:
    if state.get("v3"):
        return
    async with AsyncSessionLocal() as db:
        base = await db.get(CompositionVersion, UUID(state["v2"]["composition_version_id"]))
        before = generator_of(content_of(base))
        parameters = dict(before.object.parameters)
        old_speed = parameters.get("speed_multiplier")
        assert (
            isinstance(old_speed, (int, float))
            and not isinstance(old_speed, bool)
            and old_speed > 0
        )
        parameters["speed_multiplier"] = old_speed * 1.6
        args = ReviseVideoArgs.model_validate(
            {
                "base_ref": {
                    "composition_id": state["v1"]["composition_id"],
                    "composition_version_id": str(base.id),
                    "content_digest": base.content_digest,
                },
                "edits": [
                    {
                        "op": "update_generator",
                        "clip_id": before.clip_id,
                        "parameters": parameters,
                    }
                ],
            }
        )

        async def preflight(candidate: CompositionContent) -> None:
            await prepare_generator_media(candidate)

        read = await revise_video(
            db,
            owner_id=owner_id,
            args=args,
            request_id=REVISE_REQUEST,
            prepare_candidate=preflight,
        )
        after = generator_of(
            content_of(await db.get(CompositionVersion, UUID(read["composition_version_id"])))
        )
        assert after.object.code == before.object.code
        assert after.object.program_digest() != before.object.program_digest()
        assert after.object.parameters["speed_multiplier"] == parameters["speed_multiplier"]
        assert read["storyboard"]["scenes"][0]["clips"]
        enriched = await enrich_generator_previews(read)
        previews = enriched["generator_previews"]
        assert len(previews) == 1
        assert previews[0]["program_digest"] == after.object.program_digest()
        assert (
            previews[0]["program_digest"] != state["v1"]["generator_previews"][0]["program_digest"]
        )
        assert previews[0]["media_digest"] != state["v1"]["generator_previews"][0]["media_digest"]
        state["speed_revision"] = {
            "parameter": "speed_multiplier",
            "before": old_speed,
            "after": parameters["speed_multiplier"],
            "code_unchanged": True,
            "old_program_digest": before.object.program_digest(),
            "new_program_digest": after.object.program_digest(),
            "change_set": read["change_set"],
        }
        state["v3"] = version_summary(read, previews)
        state["v3"]["preview_model_inputs"] = await preview_observations(read)
        save_state(state)


async def fixed_production(state: dict[str, Any], project_id: UUID) -> None:
    if not state.get("output_id"):
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, project_id)
            composition = await db.get(Composition, UUID(state["v1"]["composition_id"]))
            version = await db.get(CompositionVersion, UUID(state["v3"]["composition_version_id"]))
            output = await queue_composition_render(
                db,
                project=project,
                composition=composition,
                version=version,
                execution_id=f"c4-orbit-runless-{version.id}",
            )
            await db.commit()
            state["output_id"] = str(output.id)
            state["production"] = {
                "run_less": True,
                "workflow_step_id": output.workflow_step_id,
                "composition_digest": output.payload["composition_digest"],
                "generator_media": output.payload["generator_media"],
                "execution_digest": output.payload.get("execution_digest"),
                "render_spec_provenance": output.render_spec.get("provenance"),
            }
            save_state(state)

    output_id = UUID(state["output_id"])
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 600
    while True:
        async with AsyncSessionLocal() as db:
            output = await db.get(Output, output_id)
            status = output.render_status.value
            if status in {RenderStatus.COMPLETED, RenderStatus.FAILED, RenderStatus.CANCELLED}:
                assert status == RenderStatus.COMPLETED, output.render_error
                assert output.workflow_step_id is None
                assert output.payload["composition_digest"] == state["v3"]["content_digest"]
                media = output.payload["generator_media"]["obj_generator"]
                assert media["program_digest"] == state["speed_revision"]["new_program_digest"]
                assert output.render_spec["provenance"] == {
                    "composition_id": state["v1"]["composition_id"],
                    "composition_version_id": state["v3"]["composition_version_id"],
                    "content_digest": state["v3"]["content_digest"],
                }
                version = await db.get(CompositionVersion, output.composition_version_id)
                reuse = []
                retry_media = await prepare_generator_media(
                    content_of(version), on_reuse=reuse.append
                )
                assert reuse == [True]
                assert retry_media["obj_generator"]["media"] == media["media"]
                state["production"].update(
                    {
                        "render_status": status,
                        "files": output.files,
                        "duration_seconds": output.payload.get("duration_seconds"),
                        "execution_digest": output.payload.get("execution_digest"),
                        "retry_preparation_reused_exact_media": True,
                        "retry_program_digest": retry_media["obj_generator"]["program_digest"],
                        "agent_authoring_calls_total": (
                        len(state["agent_preflight_failures"])
                        + len(state["agent_observations"])
                    ),
                    }
                )
                video = await storage.read(output.files["video"])
                (OUT / "final.mp4").write_bytes(video)
                state["production"]["video_sha256"] = hashlib.sha256(video).hexdigest()
                state["frames"] = extract_frames(video)
                save_state(state)
                return
        if loop.time() >= deadline:
            raise TimeoutError(f"Output {output_id} did not finish")
        await asyncio.sleep(2)


def extract_frames(video: bytes) -> list[dict[str, Any]]:
    rows = []
    with av.open(io.BytesIO(video), mode="r") as container:
        stream = next(s for s in container.streams if s.type == "video")
        fps = float(stream.average_rate)
        for seconds in (0.5, 3.0, 5.5):
            target = int(seconds / stream.time_base)
            container.seek(target, stream=stream, backward=True, any_frame=False)
            decoded = None
            for frame in container.decode(stream):
                if frame.time is not None and frame.time >= seconds - (0.5 / fps):
                    decoded = frame
                    break
            assert decoded is not None
            image = decoded.to_image().convert("RGB")
            path = OUT / f"final-{seconds:.1f}s.png"
            image.save(path)
            payload = path.read_bytes()
            rows.append(
                {
                    "requested_seconds": seconds,
                    "actual_seconds": decoded.time,
                    "frame": round(decoded.time * fps),
                    "path": str(path),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    assert len({row["sha256"] for row in rows}) == len(rows)
    return rows


async def main() -> None:
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    project_id, owner_id = await project_and_image(state)
    await create_agent_version(state, project_id, owner_id)
    await add_native_image(state, owner_id)
    await revise_speed(state, owner_id)
    await fixed_production(state, project_id)
    print(
        json.dumps(
            {
                "composition_id": state["v1"]["composition_id"],
                "v1": {
                    key: state["v1"][key] for key in ("composition_version_id", "content_digest")
                },
                "v3": {
                    key: state["v3"][key] for key in ("composition_version_id", "content_digest")
                },
                "speed_revision": state["speed_revision"],
                "output_id": state["output_id"],
                "production": state["production"],
                "frames": state["frames"],
                "evidence": str(STATE_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
