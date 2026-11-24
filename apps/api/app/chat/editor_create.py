"""Save an editable first version from ordered shots or motion blocks through the Composition store."""
import re
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import select

from app.agents.tool_progress import current_call_id
from app.editing.catalog import MotionBlockId
from app.editing.edits import AddScene, SetTransition, apply_ops
from app.editing.revisions import motion_block_ops
from app.editing.schemas import (
    CompositionContent,
    ProductShowcaseProps,
    Scene,
    TimeRange,
    Track,
    Transition,
    TransitionKind,
    VersionSettings,
)
from app.editing.store import RequestMismatch, apply_composition_edits, snapshot_facts
from app.editing.styles import CompositionStyle, StylePresetId, resolve_style_tokens
from app.editing.timing import seconds_to_ticks
from app.models.schemas import canonical_json_hash
from app.models.tables import Asset, Composition, CompositionVersion, Message, Project, SourceSnapshot
from app.tools.video.design import (
    CompositionSceneAuthoring,
    CompositionScenePlan,
    _expand_scene_authoring,
    _place_skill_generator,
    _scene_plan_write,
)


async def resolve_motion_block_resources(
    db,
    *,
    owner_id: UUID,
    project_id: UUID,
    block_id: str,
    props: dict[str, Any],
    resources: list[UUID] | None,
    view_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve owner-scoped image or captured-webpage snapshots for a MotionBlockObject."""
    from app.editing.sources import register_web_view_snapshot

    legacy_asset = select(Asset.id).where(Asset.user_id == owner_id, Asset.project_id == project_id)
    resolved_props = props
    resolved_resources: list[dict[str, Any]] = []
    ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
    for idx, res_id in enumerate(resources or []):
        snap = await db.scalar(select(SourceSnapshot).where(
            SourceSnapshot.id == res_id,
            SourceSnapshot.owner_id == owner_id,
            (SourceSnapshot.origin_project_id == project_id)
            | (SourceSnapshot.origin_project_id.is_(None) & SourceSnapshot.asset_id.in_(legacy_asset)),
        ))
        if snap is None:
            raise ValueError(f"Resource snapshot {res_id} is unavailable in this project.")
        if snap.kind == "web":
            views = (snap.meta or {}).get("views") or []
            chosen_view = view_id or (views[0].get("view_id") if views else None)
            if not chosen_view:
                raise ValueError("The captured webpage has no rendered views.")
            if idx == 0 and block_id == "product_showcase":
                resolved_props = ProductShowcaseProps.resolve_props(resolved_props, views, chosen_view)
            snap = await register_web_view_snapshot(
                db, owner_id=owner_id, web_snapshot=snap, view_id=chosen_view,
            )
            await db.flush()
        if snap.kind != "image" or not snap.storage_key:
            raise ValueError("Motion block resources must be fixed images or captured webpage views.")
        ctype = (snap.meta or {}).get("content_type") or (
            "image/jpeg" if snap.storage_key.lower().endswith((".jpg", ".jpeg"))
            else "image/webp" if snap.storage_key.lower().endswith(".webp")
            else "image/png"
        )
        if ctype not in ext_map:
            ctype = "image/png"
        resolved_resources.append({
            "path": f"media/img_{idx}{ext_map[ctype]}",
            "snapshot_id": str(snap.id),
            "snapshot_digest": snap.digest,
            "content_type": ctype,
        })
    return resolved_props, resolved_resources


def media_generation_forbidden(text: str) -> bool:
    """An explicit instruction to work exclusively with existing material."""
    return bool(re.search(
        r"(?:^|[.!?。！？;；\n])\s*(?:no new media(?: or export)?|"
        r"(?:do not|don't) generate (?:any )?new media|"
        r"(?:不要|不用|禁止)(?:生成|新增)(?:任何)?(?:新)?素材)(?=\s*(?:$|[.!?。！？;；，,\n]))",
        text or "", re.IGNORECASE,
    ))


def voice_generation_forbidden(text: str) -> bool:
    return media_generation_forbidden(text) or bool(re.search(
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
    source_motion: Literal["hold", "push"] = Field(
        default="hold",
        description="Hold preserves the source framing, including motion already recorded in footage. "
                    "Push adds animated camera movement. Choose it only for an intended extra camera push.",
    )


class FirstMotionBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: MotionBlockId = Field(
        description="Native motion block ID from creative_catalog.motion_blocks (13 blocks).",
    )
    duration_seconds: float = Field(
        gt=0,
        le=60,
        allow_inf_nan=False,
        description="Duration in seconds for this motion block act.",
    )
    props: dict[str, Any] = Field(
        description=(
            "Declarative props for the chosen motion block. For metric_grid, items[].value must "
            "include its unit/symbol (e.g. '3s', '85%', '4.2×', '$1.8M'), keeping label strictly as the metric name."
        ),
    )
    resources: list[UUID] | None = Field(
        default=None,
        max_length=16,
        description="Pinned image or captured webpage snapshot IDs for this block.",
    )
    view_id: str | None = Field(
        default=None,
        max_length=120,
        description="Optional view_id when passing a webpage snapshot in resources.",
    )
    transition_after: TransitionKind | None = Field(
        default=None,
        description="Optional centered transition into the next adjacent motion block ('crossfade', 'whip_pan', 'wipe_reveal', 'zoom_through', 'iris_focus').",
    )
    transition_duration_seconds: float = Field(
        default=0.5,
        gt=0,
        le=2.0,
        allow_inf_nan=False,
        description="Centered transition duration in seconds when transition_after is set.",
    )


class CreateVideoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    shots: list[FirstShot] = Field(
        default_factory=list,
        max_length=64,
        description="Ordered media/title shots. Optional when declaring native motion_blocks directly.",
    )
    motion_blocks: list[FirstMotionBlock] = Field(
        default_factory=list,
        max_length=24,
        description=(
            "Ordered native declarative motion-graphics acts (statement_hook, product_showcase, "
            "device_mockup, chat_demo, flow_diagram, step_timeline, split_compare, bento_features, "
            "metric_grid, data_chart, quote_proof, kinetic_title, closing_cta) built sequentially "
            "with optional act transitions."
        ),
    )
    aspect: Literal["16:9", "9:16", "1:1"] = "16:9"
    background: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    fps: int = Field(default=30, ge=1, le=120)
    style_preset: StylePresetId | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Optional orthogonal CompositionStyle preset (institutional_dark, swiss_paper, vox_editorial, kinetic_anime).",
    )
    accent_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        exclude_if=lambda v: v is None,
        description="Optional hex accent override paired with style_preset.",
    )
    pending_disposition: Literal["answer", "skip", "none"] = Field(
        default="none",
        description=(
            "When a pending_question exists in context: use 'skip' if the user explicitly "
            "pivoted away from or cancelled it, 'answer' if the user answered it, or 'none' otherwise."
        ),
    )

    @model_validator(mode="after")
    def _require_shots_or_motion_blocks(self):
        if not self.shots and not self.motion_blocks:
            raise ValueError("Provide at least one entry in shots or motion_blocks.")
        return self


def _creation_context(db, turn):
    from app.chat.readiness import creative_state_for_pending
    from app.models.schemas import (
        BuiltInSkillReference,
        ExternalSkillReference,
        ProjectBrief,
    )
    from app.skills.loading import load_skill_creative_context

    pending = turn.project.pending_brief
    creative_state = creative_state_for_pending(ProjectBrief.model_validate(pending)) if pending else None
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
        if identity in (opening.intent or {}).get("media_replay_ids", {}) or await db.scalar(
            select(Message.id).where(Message.turn_id == opening.id, Message.intent["editor_media"].astext == identity)
        ):
            raise RequestMismatch("This call already belongs to a media request.")

        ids = {sid for shot in args.shots for sid in (shot.snapshot_id, shot.narration_snapshot_id) if sid}
        facts: dict[UUID, dict[str, Any]] = {}
        if ids:
            accessible = set(await db.scalars(select(SourceSnapshot.id).where(SourceSnapshot.id.in_(ids),
                                  SourceSnapshot.owner_id == owner, SourceSnapshot.origin_project_id == project)))
            if accessible != ids:
                raise ValueError("Choose fixed sources available in this project.")
            facts = await snapshot_facts(db, ids)
            # A prepared web-view image is an alias for one view of its immutable parent.
            parents = {UUID(fact["meta"]["web_snapshot_id"]) for fact in facts.values()
                       if fact["meta"].get("origin") == "web_view" and fact["meta"].get("web_snapshot_id")}
            if parents - ids:
                owned = set(await db.scalars(select(SourceSnapshot.id).where(
                    SourceSnapshot.id.in_(parents - ids), SourceSnapshot.owner_id == owner,
                    SourceSnapshot.origin_project_id == project)))
                if owned != parents - ids:
                    raise ValueError("The webpage behind this view is unavailable in this project.")
                facts.update(await snapshot_facts(db, owned))
        from app.tools.video.design import explicit_design_constraints

        required = explicit_design_constraints(
            getattr(turn, "text", ""), brief=turn.project.pending_brief,
        )
        total_acts = len(args.shots) + len(args.motion_blocks)
        if required.get("scene_count") is not None and total_acts != required["scene_count"]:
            raise ValueError(f"The user fixed {required['scene_count']} shots; received {total_acts}.")
        if any(shot.narration is not None for shot in args.shots) and voice_generation_forbidden(getattr(turn, "text", "")):
            raise ValueError("The user explicitly disallowed narration generation. Use existing sources or native text instead.")
        if required.get("target_seconds") is not None:
            ticks = seconds_to_ticks(required["target_seconds"])
            planned_seconds = (
                sum(shot.duration_seconds or 0 for shot in args.shots)
                + sum(mb.duration_seconds for mb in args.motion_blocks)
            )
            if planned_seconds > 0:
                actual_ticks = (
                    sum(seconds_to_ticks(shot.duration_seconds or 0) for shot in args.shots)
                    + sum(seconds_to_ticks(mb.duration_seconds) for mb in args.motion_blocks)
                )
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
        comp_style = (
            CompositionStyle(preset_id=args.style_preset, accent_color=args.accent_color)
            if args.style_preset is not None
            else None
        )
        effective_bg = args.background
        if comp_style is not None and "background" not in args.model_fields_set and required.get("background") is None:
            effective_bg = resolve_style_tokens(comp_style)["canvas_bg"]
        version_settings = VersionSettings(
            width=width, height=height, fps={"num": args.fps}, background=effective_bg, style=comp_style
        )
        content = CompositionContent(settings=version_settings, creative_state=creative_state).model_dump(mode="json")
        shots = [shot.model_copy(update={"scene_id": f"scene_{i + 1}"}) for i, shot in enumerate(args.shots)]
        if shots:
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
        if args.motion_blocks:
            comp_content = CompositionContent.model_validate(content)
            rate = comp_content.settings.timebase
            cursor_ticks = max(
                [clip.range.end for track in comp_content.timeline.tracks for clip in track.clips]
                + [scene.range.end for scene in comp_content.scenes]
                + [0]
            )
            scene_index = len(comp_content.scenes)
            placed_blocks: list[tuple[str, str, int, int, FirstMotionBlock]] = []
            bound_digests: dict[UUID, str] = {
                b.snapshot_id: b.snapshot_digest
                for b in comp_content.sources
                if b.snapshot_digest
            }
            for idx, mb in enumerate(args.motion_blocks):
                resolved_props, resolved_resources = await resolve_motion_block_resources(
                    db,
                    owner_id=owner,
                    project_id=project,
                    block_id=mb.block_id,
                    props=mb.props,
                    resources=mb.resources,
                    view_id=mb.view_id,
                )
                for res in resolved_resources:
                    bound_digests[UUID(res["snapshot_id"])] = res["snapshot_digest"]
                dur_ticks = seconds_to_ticks(mb.duration_seconds, rate)
                if dur_ticks <= 0:
                    raise ValueError("Motion block duration must be at least one composition tick.")
                start = cursor_ticks
                end = start + dur_ticks
                cursor_ticks = end
                scene_index += 1
                scene_id = f"scene_{scene_index}"
                intent_label = str(
                    resolved_props.get("headline")
                    or resolved_props.get("title")
                    or resolved_props.get("brand_name")
                    or resolved_props.get("quote")
                    or args.name
                )[:120]
                clip_id = f"clp_mg_{idx + 1}"
                object_id = f"obj_mg_{idx + 1}"
                block_ops = motion_block_ops(
                    comp_content,
                    block_id=mb.block_id,
                    props=resolved_props,
                    resources=resolved_resources,
                    clip_id=clip_id,
                    object_id=object_id,
                    scene_id=scene_id,
                    start=start,
                    end=end,
                )
                comp_content = apply_ops(
                    comp_content,
                    [
                        AddScene(
                            op="add_scene",
                            scene=Scene(
                                scene_id=scene_id,
                                range=TimeRange(start=start, end=end),
                                intent=intent_label,
                            ),
                        ),
                        *block_ops,
                    ],
                    bound_digests,
                )
                landed_track_id = next(
                    (
                        t.track_id
                        for t in comp_content.timeline.tracks
                        if any(c.clip_id == clip_id for c in t.clips)
                    ),
                    "",
                )
                placed_blocks.append((clip_id, landed_track_id, start, end, mb))

            transition_ops = []
            for idx in range(len(placed_blocks) - 1):
                from_id, from_track, from_start, from_end, mb = placed_blocks[idx]
                to_id, to_track, to_start, to_end, _ = placed_blocks[idx + 1]
                if mb.transition_after is None:
                    continue
                if from_track != to_track or from_end != to_start:
                    continue
                max_dur = min(from_end - from_start, to_end - to_start) // 2
                trn_ticks = min(seconds_to_ticks(mb.transition_duration_seconds, rate), max_dur)
                if trn_ticks > 0:
                    transition_ops.append(
                        SetTransition(
                            op="set_transition",
                            transition=Transition(
                                transition_id=f"trn_mg_{idx + 1}",
                                from_clip_id=from_id,
                                to_clip_id=to_id,
                                kind=mb.transition_after,
                                duration=trn_ticks,
                                alignment="center",
                            ),
                        )
                    )
            if transition_ops:
                comp_content = apply_ops(comp_content, transition_ops, bound_digests)
            content = comp_content.model_dump(mode="json")
        if generator_resources:
            provenance["skill_generator_resources"] = generator_resources
        if required.get("target_seconds") is not None:
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

    rate_saved = saved.settings["timebase"]
    created_clip_facts = [
        {
            "clip_id": clip["clip_id"],
            "object_id": clip["object"]["object_id"],
            "start_seconds": clip["range"]["start"] / rate_saved,
            "end_seconds": clip["range"]["end"] / rate_saved,
        }
        for track in saved.timeline["tracks"]
        for clip in track["clips"]
    ]
    _remember_labels(
        turn,
        created_clip_facts,
        saved.id,
        saved.content_digest,
        saved.version,
        composition_id=saved.composition_id,
    )
    total_duration_seconds = max(
        (clip["range"]["end"] / rate_saved for track in saved.timeline["tracks"] for clip in track["clips"]),
        default=0.0,
    )
    return {
        "composition_id": str(saved.composition_id),
        "version_id": str(saved.id),
        "version": saved.version,
        "content_digest": saved.content_digest,
        "duration_seconds": total_duration_seconds,
        "saved": True,
        "shots": [
            {
                "seconds": (clip["range"]["end"] - clip["range"]["start"]) / rate_saved,
                "text": clip["object"]["text"],
                "color": clip["object"]["style"]["color"],
                "animated": bool(clip["animations"]),
            }
            for track in saved.timeline["tracks"]
            for clip in track["clips"]
            if clip["object"]["kind"] == "text"
        ],
        "motion_blocks": [
            {
                "clip_id": clip["clip_id"],
                "block_id": clip["object"]["block_id"],
                "start_seconds": clip["range"]["start"] / rate_saved,
                "end_seconds": clip["range"]["end"] / rate_saved,
            }
            for track in saved.timeline["tracks"]
            for clip in track["clips"]
            if clip["object"]["kind"] == "motion_block"
        ],
    }
