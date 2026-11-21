"""Save an editable first version from ordered shots through the Composition store."""
from typing import Literal
from uuid import uuid5

from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import select

from app.agents.tool_progress import current_call_id
from app.editing.schemas import CompositionContent, Track, VersionSettings
from app.editing.store import RequestMismatch, apply_composition_edits, snapshot_facts
from app.models.schemas import canonical_json_hash
from app.models.tables import Composition, CompositionVersion, Message, Project, SourceSnapshot
from app.tools.video.design import (
    CompositionSceneAuthoring,
    CompositionScenePlan,
    _expand_scene_authoring,
    _place_skill_generator,
    _scene_plan_write,
)


def voice_generation_forbidden(text: str) -> bool:
    import re

    return bool(re.search(
        r"(?:不要|不用|不需要|禁止|不)(?:生成|合成|新增|创建|制作|使用|提供)?[^。！？；\n]{0,8}(?:配音|旁白|语音)"
        r"|(?:do not|don't|without|no)\s+(?:\w+\s+){0,4}(?:voice|narration|speech)",
        text or "", re.IGNORECASE,
    ))


class FirstShot(CompositionSceneAuthoring):
    scene_id: SkipJsonSchema[Literal[""]] = Field(default="", exclude=True)
    duration_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False,
                                           description="Exact duration of a still or title.")
    text_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    title_motion: Literal["static", "entrance"] = "static"
    source_motion: Literal["hold", "push"] = "hold"


class CreateVideoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    shots: list[FirstShot] = Field(min_length=1, max_length=64)
    aspect: Literal["16:9", "9:16", "1:1"] = "16:9"
    background: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    fps: int = Field(default=30, ge=1, le=120)
    pending_disposition: Literal["answer", "skip", "none"] = "none"


def _creation_context(db, turn):
    from app.chat.readiness import creative_state_for_pending
    from app.models.schemas import (
        BuiltInSkillReference,
        ExternalSkillReference,
        PendingPlan,
    )
    from app.skills.loading import load_skill_creative_context

    pending = turn.project.pending_brief
    creative_state = creative_state_for_pending(PendingPlan.model_validate(pending)) if pending else None
    reference = getattr(turn, "skill", None)
    provenance = {}
    skill = None
    if isinstance(reference, BuiltInSkillReference):
        provenance.update(skill_version=reference.version, skill_reference=reference.model_dump(mode="json"))
    elif isinstance(reference, ExternalSkillReference):
        async def load():
            return await load_skill_creative_context(
                db, owner_id=turn.project.user_id, skill_version_id=reference.skill_version_id,
            )

        skill = load
        provenance["skill_reference"] = reference.model_dump(mode="json")
    return creative_state, provenance, skill, None


async def create_video(db, turn, args: CreateVideoArgs):
    from app.chat.service import _lock_turn_for_transcript_write
    from app.editing.service import video_version_read

    opening = await _lock_turn_for_transcript_write(db, turn.turn_id)
    if opening.role != "user" or opening.conversation_id != turn.conversation_id:
        raise ValueError("The opening message is unavailable.")
    owner, project = turn.project.user_id, turn.project.id
    identity = str(uuid5(turn.turn_id, current_call_id()))
    fingerprint = canonical_json_hash({"tool": "create_video", "args": args.model_dump(mode="json")})
    markers = (opening.intent or {}).get("editor_commits", [])
    marker = next((item for item in markers if item["request"] == identity), None)
    if marker:
        if marker["fingerprint"] != fingerprint:
            raise RequestMismatch("This call already saved different content.")
        saved = await db.scalar(select(CompositionVersion).join(Composition, Composition.id == CompositionVersion.composition_id)
                                .where(CompositionVersion.request_id == identity, Composition.owner_id == owner,
                                       Composition.origin_project_id == project))
        if saved is None:
            raise ValueError("The saved version is unavailable.")
    else:
        if opening.turn_state != "in_flight":
            raise ValueError("This turn has ended.")
        await db.execute(select(Project.id).where(Project.id == project, Project.user_id == owner)
                         .with_for_update(key_share=True))
        if await db.scalar(select(Composition.id).where(Composition.origin_project_id == project).limit(1)):
            raise ValueError("This project already has a saved work. Inspect it before editing.")
        if await db.scalar(select(Message.id).where(Message.turn_id == opening.id,
                                                    Message.intent["editor_media"].astext == identity)):
            raise RequestMismatch("This call already belongs to a media request.")

        ids = {sid for shot in args.shots for sid in (shot.snapshot_id, shot.narration_snapshot_id) if sid}
        accessible = set(await db.scalars(select(SourceSnapshot.id).where(SourceSnapshot.id.in_(ids),
                              SourceSnapshot.owner_id == owner, SourceSnapshot.origin_project_id == project)))
        if accessible != ids:
            raise ValueError("Choose fixed sources available in this project.")
        facts = await snapshot_facts(db, ids)
        from app.tools.video.design import explicit_design_constraints

        required = explicit_design_constraints(
            getattr(turn, "text", ""), brief=turn.project.pending_brief,
        )
        if required.get("scene_count") is not None and len(args.shots) != required["scene_count"]:
            raise ValueError(f"The user fixed {required['scene_count']} shots; received {len(args.shots)}.")
        if any(shot.narration is not None for shot in args.shots) and voice_generation_forbidden(getattr(turn, "text", "")):
            raise ValueError("The user explicitly disallowed narration generation. Use existing sources or native text instead.")
        if required.get("target_seconds") is not None:
            from app.editing.timing import seconds_to_ticks

            ticks = seconds_to_ticks(required["target_seconds"])
            if sum(shot.duration_seconds or 0 for shot in args.shots) > 0:
                actual_ticks = sum(seconds_to_ticks(shot.duration_seconds or 0) for shot in args.shots)
                if abs(actual_ticks - ticks) > 3000:
                    raise ValueError("The ordered shots do not match the user's fixed total duration.")
        for field in ("aspect", "background", "fps"):
            if required.get(field) is not None and getattr(args, field) != required[field]:
                raise ValueError(f"The requested {field} does not match the user's fixed value.")
        if any(shot.skill_resource is not None for shot in args.shots):
            from app.config import settings
            from app.models.schemas import ExternalSkillReference

            if not settings.component_bake_enabled:
                raise ValueError("Controlled Skill Generators are unavailable in this deployment. Use fixed media or native text.")
            if not isinstance(getattr(turn, "skill", None), ExternalSkillReference):
                raise ValueError("A controlled Generator requires the current bound external Skill.")
        creative_state, provenance, skill_loader, _ = _creation_context(db, turn)
        skill = await skill_loader() if skill_loader is not None else None
        package = skill.package if skill is not None else None
        if skill is not None:
            provenance["external_skill"] = skill.provenance
        width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[args.aspect]
        settings = VersionSettings(width=width, height=height, fps={"num": args.fps}, background=args.background)
        content = CompositionContent(settings=settings, creative_state=creative_state).model_dump(mode="json")
        shots = [shot.model_copy(update={"scene_id": f"scene_{i + 1}"}) for i, shot in enumerate(args.shots)]
        content = _scene_plan_write(content, [CompositionScenePlan(scene_id=shot.scene_id,
                                    intent=shot.headline or args.name) for shot in shots])
        generator_resources = {}
        for shot in shots:
            content = await _expand_scene_authoring(content, shot, facts, owner)
            placement = shot.skill_resource
            if placement is None:
                continue
            placement = placement.model_copy(update={
                "scene_id": shot.scene_id,
                "track_id": placement.track_id or "trk_main",
                "clip_id": placement.clip_id or f"clp_{shot.scene_id}_skill",
            })
            tracks = content["timeline"]["tracks"]
            if not any(track["track_id"] == placement.track_id for track in tracks):
                tracks.append(Track(
                    track_id=placement.track_id, kind="visual", role="main",
                    order=max((track["order"] for track in tracks), default=-1) + 1,
                ).model_dump(mode="json"))
            content, declaration_digest = await _place_skill_generator(
                db, owner_id=owner, project_id=project, content=content,
                placement=placement, skill=skill, package=package,
            )
            generator_resources[placement.clip_id] = {
                "resource_id": placement.resource_id,
                "declaration_digest": declaration_digest,
                "skill_version_id": str(skill.version.id),
            }
        if generator_resources:
            provenance["skill_generator_resources"] = generator_resources
        if required.get("target_seconds") is not None:
            from app.editing.timing import seconds_to_ticks

            total_ticks = max(
                (clip["range"]["end"] for track in content["timeline"]["tracks"] for clip in track["clips"]),
                default=0,
            )
            if abs(total_ticks - seconds_to_ticks(required["target_seconds"])) > 3000:
                raise ValueError("The assembled work does not match the user's fixed total duration.")
        activity = await db.scalar(select(Message.id).where(Message.turn_id == opening.id,
                                   Message.intent["frame"]["call_id"].astext == current_call_id(),
                                   Message.intent["frame"]["status"].astext == "active").limit(1))
        opening.intent = {**(opening.intent or {}), "editor_commits": [*markers, {
            "request": identity, "tool": "create_video", "fingerprint": fingerprint,
            "activity_row": str(activity) if activity else None,
        }]}
        _, saved, _ = await apply_composition_edits(db, owner_id=owner, origin_project_id=project,
                                                    name=args.name, content=content, request_id=identity,
                                                    skill_provenance=provenance or None)
    settle = getattr(turn, "_settle_pending_by_disposition", None) or getattr(turn, "_settle_by_disposition", None)
    if settle is not None:
        await settle(args.pending_disposition)
    read = await video_version_read(db, owner_id=owner, version_id=saved.id)
    turn._video_presentation_pending = read
    from app.chat.editor import _remember_labels

    _remember_labels(turn, [], saved.id, saved.content_digest, saved.version)
    return {"composition_id": str(saved.composition_id), "version_id": str(saved.id), "version": saved.version,
            "content_digest": saved.content_digest, "saved": True, "shots": [
                {"seconds": (clip["range"]["end"] - clip["range"]["start"]) / saved.settings["timebase"],
                 "text": clip["object"]["text"], "color": clip["object"]["style"]["color"],
                 "animated": bool(clip["animations"])} for track in saved.timeline["tracks"] for clip in track["clips"]
                if clip["object"]["kind"] == "text"
            ]}
