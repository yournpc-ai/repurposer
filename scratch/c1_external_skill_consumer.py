"""Real C1/C3 consumer: original package → saved version → Agent → revision → Output."""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import av
from sqlalchemy import select, text

ROOT = Path("/Users/sylas/repurposer")
sys.path.insert(0, str(ROOT / "apps/api"))

from app.editing.schemas import CompositionContent, GeneratorObject  # noqa: E402
from app.editing.director import DirectionRejected  # noqa: E402
from app.editing.service import revise_video  # noqa: E402
from app.editing.store import content_of  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import DesignVideoArgs, RenderStatus, ReviseVideoArgs  # noqa: E402
from app.models.tables import Composition, CompositionVersion, Output, Project  # noqa: E402
from app.providers import storage  # noqa: E402
from app.providers.llm import minimax as minimax_module  # noqa: E402
from app.providers.llm.base import LLMSchemaError  # noqa: E402
from app.skills.external import (  # noqa: E402
    SkillInputDeclaration,
    SkillPolicy,
    build_skill_draft,
)
from app.skills.store import SkillNotFoundError, get_skill_version, import_external_skill  # noqa: E402
from app.tools.video.agents import program_director  # noqa: E402
from app.tools.video.design import DesignError, design_video  # noqa: E402
from app.tools.video.produce import queue_composition_render  # noqa: E402
from app.tools.video.programs import (  # noqa: E402
    ProgramError,
    enrich_generator_previews,
    generator_preview_images,
    prepare_generator_media,
)

SOURCE = ROOT / "scratch/video-shotcraft-1266a3ec"
OUT = ROOT / "scratch/c1-external-skill"
STATE_PATH = OUT / "evidence.json"
SOURCE_URI = "https://github.com/Vincentwei1021/video-shotcraft"
SOURCE_REVISION = "1266a3ec4831289c4d893d42dd5102723658039a"
REFERENCES = [
    "references/shots/typography/marker-underline-title.md",
    "demos/typography/marker-underline-title/MarkerUnderlineTitle.tsx",
]
CAPABILITIES = {
    "animation:opacity",
    "animation:transform.position",
    "animation:transform.scale",
    "animation:transform.rotation",
    "animation:blur",
    "animation:letter-spacing",
    "text:word-parts",
    "capture:web",
}


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


def version_summary(read: dict[str, Any]) -> dict[str, Any]:
    storyboard = read["storyboard"]
    clips = [clip for scene in storyboard["scenes"] for clip in scene["clips"]] + storyboard[
        "unassigned_clips"
    ]
    return {
        "composition_id": read["composition_id"],
        "composition_version_id": read["composition_version_id"],
        "content_digest": read["content_digest"],
        "version": read["version"],
        "skill_adaptation": read.get("skill_adaptation"),
        "clips": [
            {
                key: clip.get(key)
                for key in (
                    "clip_id", "object_id", "object_kind", "runtime", "program_digest",
                    "parameters", "output", "code", "text", "layout",
                )
                if clip.get(key) is not None
            }
            for clip in clips
        ],
        "generator_previews": read["generator_previews"],
    }


async def save_preview_inputs(read: dict[str, Any], label: str) -> list[dict[str, Any]]:
    rows = []
    for index, image in enumerate(await generator_preview_images(read)):
        payload = base64.b64decode(image.data_url.split(",", 1)[1])
        path = OUT / f"{label}-representative-{index}.png"
        path.write_bytes(payload)
        rows.append({
            "caption": image.caption,
            "path": str(path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        })
    return rows


async def import_original_package(state: dict[str, Any]) -> None:
    if state.get("skill_version_id"):
        return
    files = {
        str(path.relative_to(SOURCE)): path.read_bytes()
        for path in sorted(SOURCE.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(SOURCE).parts
    }
    policy = SkillPolicy(
        mode="adaptive",
        adaptation_bounds=[
            "Replace all demo product copy and brand furniture with the actual product copy.",
            "Keep one emphasized keyword and one variable-width, lightly rough marker stroke.",
            "Start the stroke 4–8 frames after the title settles and draw left-to-right in 8–12 frames.",
            "Palette and title layout may follow the product; extend only the final hold for readability.",
        ],
    )
    draft = build_skill_draft(
        files,
        declared_capabilities=CAPABILITIES,
        source_uri=SOURCE_URI,
        source_revision=SOURCE_REVISION,
        declared_inputs=[
            SkillInputDeclaration(
                name="product_title",
                binding="text",
                description="Actual product title containing the keyword to emphasize.",
            )
        ],
        policy=policy,
    )
    async with AsyncSessionLocal() as db:
        owner_id = (
            await db.scalars(select(Project.user_id).order_by(Project.created_at.desc()).limit(1))
        ).one()
        project = Project(
            user_id=owner_id,
            title="C1 External Skill Held-out Consumer",
            language="en",
        )
        db.add(project)
        await db.flush()
        version, replayed = await import_external_skill(db, owner_id=owner_id, draft=draft)
        replay, _ = await import_external_skill(db, owner_id=owner_id, draft=draft)
        await db.commit()
        assert replay.id == version.id and replayed is False
        try:
            await get_skill_version(db, owner_id=uuid4(), skill_version_id=version.id)
        except SkillNotFoundError:
            foreign_read_rejected = True
        else:
            foreign_read_rejected = False
        assert foreign_read_rejected

    async with AsyncSessionLocal() as db:
        try:
            await db.execute(
                text("UPDATE skill_versions SET instructions = 'mutated' WHERE id = :id"),
                {"id": str(version.id)},
            )
        except Exception as exc:  # database trigger must reject the write
            immutable_error = str(exc)
            await db.rollback()
        else:
            raise AssertionError("SkillVersion UPDATE unexpectedly succeeded")

    state.update({
        "project_id": str(project.id),
        "owner_id": str(owner_id),
        "skill_id": str(version.skill_id),
        "skill_version_id": str(version.id),
        "import": {
            "raw_package_files": len(files),
            "raw_package_bytes": sum(map(len, files.values())),
            "accepted_references": len(draft.references),
            "accepted_source_hash": draft.source_hash,
            "source_uri": draft.source_uri,
            "source_revision": draft.source_revision,
            "name_unchanged": draft.name,
            "policy": draft.policy.model_dump(mode="json"),
            "declared_inputs": [item.model_dump(mode="json") for item in draft.declared_inputs],
            "capability_report": draft.capability_report.model_dump(mode="json"),
            "same_source_reimport_replayed": True,
            "foreign_owner_read_rejected": foreign_read_rejected,
            "database_immutability_rejected_update": immutable_error,
        },
        "selected_reference_paths": REFERENCES,
        "scope": "Direct domain-tool consumer; no Chat/Run authorization or credits are fabricated.",
    })
    save_state(state)


async def create_held_out_version(state: dict[str, Any]) -> None:
    if state.get("v1"):
        return
    state["preflight_quote"] = {
        "provider": "minimax",
        "model": minimax_module.settings.minimax_model,
        "token_rates_per_million_usd": minimax_module.PRICING[minimax_module.settings.minimax_model],
        "agent_attempt_budget": 5,
        "revision_agent_calls": 0,
        "run_less_render_vendor_price": 0,
    }
    save_state(state)
    base_instruction = (
        "Create one restrained editorial title shot for Repurposer using the selected "
        "external method. The exact on-screen copy is 'Turn dense research into a clear "
        "weekly briefing'. Emphasize only the word 'clear'. Use a warm off-white paper "
        "field, dark readable type, and one warm amber marker. Do not copy the reference "
        "product's name, logo or demo sentences. The title must settle before the marker "
        "draws. Expose numeric marker_draw_frames and CSS-color marker_color parameters "
        "and actually read them, so the saved method can be revised without rewriting code."
    )
    failures = state.setdefault("agent_preflight_failures", [])
    observations = state.setdefault("agent_observations", [])
    usages = state.setdefault("model_usage", [])
    if not failures and not observations and not usages:
        # Provider-log facts from the first resumed process: two real calls,
        # rejected by ProgramDirection prose bounds before any version write.
        usages.extend([
            {"prompt_tokens": 9072, "completion_tokens": 22394, "total_tokens": 31466},
            {"prompt_tokens": 9268, "completion_tokens": 17413, "total_tokens": 26681},
        ])
        failures.append({
            "diagnostic": (
                "The first design attempt and its schema repair exceeded prose bounds: "
                "visual_description must be at most 240 characters and intent at most 120. "
                "Return concise fields within those existing schema limits."
            ),
            "version_saved": False,
        })
        save_state(state)
    original_call = program_director.call
    original_log = minimax_module._log_usage

    def capture_usage(usage):
        if usage:
            usages.append(copy.deepcopy(usage))
        original_log(usage)

    for _ in range(max(0, 5 - len(failures))):
        instruction = base_instruction
        if failures:
            instruction += (
                "\nThe previous candidate failed validation or controlled preview: "
                + failures[-1]["diagnostic"]
                + "\nCorrect that concrete violation while preserving the requested method."
            )

        async def capture_call(**ctx):
            direction = await original_call(**ctx)
            observations.append({
                "request": ctx,
                "returned_direction": direction.model_dump(mode="json"),
            })
            return direction

        program_director.call = capture_call
        minimax_module._log_usage = capture_usage
        try:
            read = await design_video(
                owner_id=UUID(state["owner_id"]),
                project_id=UUID(state["project_id"]),
                request_id="c1-held-out-agent-v1",
                args=DesignVideoArgs(
                    mode="program",
                    text="Turn dense research into a clear weekly briefing",
                    language="en",
                    target_seconds=3,
                    aspect="16:9",
                    background="#F5F1E8",
                    specific_instruction=instruction,
                ),
                skill_version_id=UUID(state["skill_version_id"]),
                skill_reference_paths=REFERENCES,
            )
        except (ProgramError, LLMSchemaError, DesignError, DirectionRejected) as exc:
            failures.append({"diagnostic": str(exc), "version_saved": False})
            save_state(state)
            continue
        finally:
            program_director.call = original_call
            minimax_module._log_usage = original_log
        enriched = await enrich_generator_previews(read)
        state["v1"] = version_summary(enriched)
        state["v1"]["preview_model_inputs"] = await save_preview_inputs(enriched, "v1")
        save_state(state)
        return
    raise RuntimeError("bounded Agent/preview correction did not produce a valid held-out shot")


async def revise_with_saved_method(state: dict[str, Any]) -> None:
    if state.get("v2"):
        return
    async with AsyncSessionLocal() as db:
        base = await db.get(CompositionVersion, UUID(state["v1"]["composition_version_id"]))
        before = generator_of(content_of(base))
        parameters = dict(before.object.parameters)
        old_frames = parameters.get("marker_draw_frames")
        assert isinstance(old_frames, (int, float)) and not isinstance(old_frames, bool)
        new_frames = 12 if old_frames != 12 else 11
        assert 8 <= new_frames <= 12
        old_color = parameters.get("marker_color")
        assert isinstance(old_color, str)
        parameters["marker_draw_frames"] = new_frames
        parameters["marker_color"] = "#A94E20"
        args = ReviseVideoArgs.model_validate({
            "base_ref": {
                "composition_id": state["v1"]["composition_id"],
                "composition_version_id": str(base.id),
                "content_digest": base.content_digest,
            },
            "edits": [{
                "op": "update_generator",
                "clip_id": before.clip_id,
                "parameters": parameters,
            }],
        })

        async def preflight(candidate: CompositionContent) -> None:
            await prepare_generator_media(candidate)

        read = await revise_video(
            db,
            owner_id=UUID(state["owner_id"]),
            args=args,
            request_id="c1-held-out-method-revision-v2",
            prepare_candidate=preflight,
        )
        after = generator_of(
            content_of(await db.get(CompositionVersion, UUID(read["composition_version_id"])))
        )
        assert after.object.code == before.object.code
        assert after.object.program_digest() != before.object.program_digest()
        assert (base.skill_provenance or {})["external_skill"]["skill_version_id"] == state[
            "skill_version_id"
        ]
        enriched = await enrich_generator_previews(read)
        state["revision"] = {
            "marker_draw_frames": {"before": old_frames, "after": new_frames},
            "marker_color": {"before": old_color, "after": "#A94E20"},
            "code_unchanged": True,
            "skill_version_inherited": True,
            "old_program_digest": before.object.program_digest(),
            "new_program_digest": after.object.program_digest(),
            "change_set": read["change_set"],
        }
        state["v2"] = version_summary(enriched)
        state["v2"]["preview_model_inputs"] = await save_preview_inputs(enriched, "v2")
        save_state(state)


async def revise_native_title_from_frames(state: dict[str, Any]) -> None:
    """Apply the frame-evidenced native edit without rewriting Agent media."""
    if state.get("v3"):
        return
    async with AsyncSessionLocal() as db:
        base = await db.get(CompositionVersion, UUID(state["v2"]["composition_version_id"]))
        before = generator_of(content_of(base))
        args = ReviseVideoArgs.model_validate({
            "base_ref": {
                "composition_id": state["v1"]["composition_id"],
                "composition_version_id": str(base.id),
                "content_digest": base.content_digest,
            },
            "edits": [{
                "op": "update_text",
                "clip_id": "clp_program_title",
                "color": "#17202A",
                "background": None,
                "x": 153.6,
                "y": 453.6,
                "width": 1612.8,
                "height": 172.8,
            }],
        })
        reuse = []

        async def preflight(candidate: CompositionContent) -> None:
            await prepare_generator_media(candidate, on_reuse=reuse.append)

        read = await revise_video(
            db,
            owner_id=UUID(state["owner_id"]),
            args=args,
            request_id="c1-held-out-native-title-v3",
            prepare_candidate=preflight,
        )
        after = generator_of(
            content_of(await db.get(CompositionVersion, UUID(read["composition_version_id"])))
        )
        assert after.object.code == before.object.code
        assert after.object.program_digest() == before.object.program_digest()
        assert reuse == [True]
        enriched = await enrich_generator_previews(read)
        state["native_frame_revision"] = {
            "observed_problem": (
                "Actual Output placed the native title in a bottom dark chip while "
                "the Agent-authored marker was centered, away from the keyword."
            ),
            "edit": "Center the native title, use dark text and clear its chip background.",
            "generator_code_unchanged": True,
            "generator_program_digest_unchanged": after.object.program_digest(),
            "generator_media_reused": True,
            "change_set": read["change_set"],
        }
        state["v3"] = version_summary(enriched)
        state["v3"]["preview_model_inputs"] = await save_preview_inputs(enriched, "v3")
        save_state(state)


def extract_frames(video: bytes, *, prefix: str = "final") -> list[dict[str, Any]]:
    rows = []
    with av.open(io.BytesIO(video), mode="r") as container:
        stream = next(s for s in container.streams if s.type == "video")
        fps = float(stream.average_rate)
        for seconds in (0.5, 1.5, 2.7):
            container.seek(int(seconds / stream.time_base), stream=stream, backward=True)
            decoded = None
            for frame in container.decode(stream):
                if frame.time is not None and frame.time >= seconds - (0.5 / fps):
                    decoded = frame
                    break
            assert decoded is not None
            path = OUT / f"{prefix}-{seconds:.1f}s.png"
            decoded.to_image().convert("RGB").save(path)
            payload = path.read_bytes()
            rows.append({
                "requested_seconds": seconds,
                "actual_seconds": decoded.time,
                "frame": round(decoded.time * fps),
                "path": str(path),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
    return rows


async def produce_exact_output(state: dict[str, Any]) -> None:
    if not state.get("final_output_id"):
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, UUID(state["project_id"]))
            composition = await db.get(Composition, UUID(state["v1"]["composition_id"]))
            version = await db.get(CompositionVersion, UUID(state["v3"]["composition_version_id"]))
            output = await queue_composition_render(
                db,
                project=project,
                composition=composition,
                version=version,
                execution_id=f"c1-external-skill-approved-{version.id}",
            )
            await db.commit()
            state["final_output_id"] = str(output.id)
            save_state(state)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 600
    while True:
        async with AsyncSessionLocal() as db:
            output = await db.get(Output, UUID(state["final_output_id"]))
            status = output.render_status.value
            if status in {RenderStatus.COMPLETED, RenderStatus.FAILED, RenderStatus.CANCELLED}:
                assert status == RenderStatus.COMPLETED, output.render_error
                assert str(output.composition_version_id) == state["v3"]["composition_version_id"]
                assert output.payload["composition_digest"] == state["v3"]["content_digest"]
                video = await storage.read(output.files["video"])
                (OUT / "approved.mp4").write_bytes(video)
                state["final_production"] = {
                    "run_less": True,
                    "workflow_step_id": output.workflow_step_id,
                    "render_status": status,
                    "files": output.files,
                    "duration_seconds": output.payload.get("duration_seconds"),
                    "execution_digest": output.payload.get("execution_digest"),
                    "render_spec_provenance": output.render_spec.get("provenance"),
                    "video_sha256": hashlib.sha256(video).hexdigest(),
                    "charged_credits": 0,
                }
                state["final_frames"] = extract_frames(video, prefix="approved")
                save_state(state)
                return
        if loop.time() >= deadline:
            raise TimeoutError(f"Output {state['final_output_id']} did not finish")
        await asyncio.sleep(2)


async def main() -> None:
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    await import_original_package(state)
    await create_held_out_version(state)
    await revise_with_saved_method(state)
    await revise_native_title_from_frames(state)
    await produce_exact_output(state)
    usages = state.get("model_usage", [])
    state["model_usage_summary"] = {
        "calls": len(usages),
        "prompt_tokens": sum(int(item.get("prompt_tokens") or 0) for item in usages),
        "completion_tokens": sum(int(item.get("completion_tokens") or 0) for item in usages),
        "estimated_usd": minimax_module.price_tokens(
            sum(int(item.get("prompt_tokens") or 0) for item in usages),
            sum(int(item.get("completion_tokens") or 0) for item in usages),
        ),
    }
    save_state(state)
    print(json.dumps({
        "skill_version_id": state["skill_version_id"],
        "composition_id": state["v1"]["composition_id"],
        "v1": state["v1"]["composition_version_id"],
        "v2": state["v2"]["composition_version_id"],
        "v3": state["v3"]["composition_version_id"],
        "revision": state["revision"],
        "native_frame_revision": state["native_frame_revision"],
        "rejected_output_id": state["output_id"],
        "output_id": state["final_output_id"],
        "production": state["final_production"],
        "model_usage_summary": state["model_usage_summary"],
        "frames": state["final_frames"],
        "evidence": str(STATE_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
