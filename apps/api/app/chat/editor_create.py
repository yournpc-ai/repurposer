"""Save an editable first version from ordered shots or motion blocks through the Composition store."""
import re
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import select

from app.agents.tool_progress import current_call_id
from app.editing.catalog import MotionBlockId
from app.editing.edits import AddClip, AddScene, AddTrack, BindSource, SetTransition, apply_ops
from app.editing.revisions import motion_block_ops, text_safe_layout
from app.editing.schemas import (
    AudioObject,
    CaptionDerivation,
    Clip,
    ClipSource,
    CompositionContent,
    ProductShowcaseProps,
    Scene,
    SpeechObject,
    TextObject,
    TimeRange,
    Track,
    Transition,
    TransitionKind,
    VersionSettings,
    speech_text_digest,
)
from app.editing.store import RequestMismatch, apply_composition_edits, snapshot_facts
from app.editing.styles import CompositionStyle, StylePresetId, resolve_style_tokens
from app.editing.text_presets import (
    TextStylePresetId,
    default_caption_text_style,
    resolve_text_preset_token,
    text_style_from_token,
)
from app.editing.timing import (
    output_ticks_to_source_ticks,
    seconds_to_ticks,
    source_ticks_to_output_ticks,
)
from app.models.schemas import canonical_json_hash
from app.models.tables import Asset, Composition, CompositionVersion, Message, Music, Project, SourceSnapshot
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
    narration: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="Optional spoken voiceover script for this motion block act (concise 12-22 EN words or 22-38 ZH chars per act).",
    )
    caption_translations: list[str] | None = Field(
        default=None,
        max_length=16,
        description=(
            "Optional ordered list of concise second-language translation lines matching each spoken phrase/clause "
            "in narration for bilingual subtitles. Line 1 is always derived verbatim from the spoken TTS cues; "
            "each entry aligns onto Line 2 in lockstep."
        ),
    )
    caption_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=600,
        description=(
            "Optional bilingual translation override (prefer caption_translations). For single-language acts, omit "
            "caption_text — captions are derived verbatim and millisecond-synced from narration automatically."
        ),
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
            "with optional narration, caption_translations, resources, and act transitions."
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
    voice_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        exclude_if=lambda v: v is None,
        description="Optional voice reference (permanent voices.id UUID from search_voices/design_voice, provider_voice_id, or stock voice ID). Defaults to persona/house voice.",
    )
    narration_language: str | None = Field(
        default=None,
        min_length=2,
        max_length=16,
        exclude_if=lambda v: v is None,
        description="Optional narration ISO language code (e.g. 'en', 'zh'). Auto-detected when omitted.",
    )
    music_id: UUID | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Optional permanent music library ID (from search_music/generate_music) attached as full-length BGM with smooth fades and voiceover ducking.",
    )
    bgm_gain_db: float = Field(
        default=-21.0,
        ge=-40.0,
        le=0.0,
        allow_inf_nan=False,
        description="Optional BGM gain in dB when music_id is provided (defaults to -22 dB under narration, -14 dB without narration).",
    )
    caption_preset: TextStylePresetId | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
        description="Optional caption text style preset override (e.g. 'bilingual_cinema', 'cinema_glass', 'vox_label').",
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


def _infer_narration_language(text: str, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip().lower()
    if any(0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF for ch in text):
        return "zh"
    return "en"


def _resolve_create_caption_style(
    settings_obj: VersionSettings,
    *,
    caption_preset: TextStylePresetId | None,
    is_bilingual: bool,
):
    font_size = max(28, round(settings_obj.width * 38 / 1920))
    style_tokens = (
        resolve_style_tokens(settings_obj.style)
        if settings_obj.style is not None
        else None
    )
    if caption_preset is not None:
        token = resolve_text_preset_token(caption_preset, style_tokens)
        style = text_style_from_token(token, font_size=font_size, align="center", line_height=1.3)
    elif is_bilingual:
        token = resolve_text_preset_token("bilingual_cinema", style_tokens)
        style = text_style_from_token(token, font_size=font_size, align="center", line_height=1.3)
    else:
        style = default_caption_text_style(
            settings_obj, font_size=font_size, align="center", line_height=1.3
        )
    if style.background is not None and style.background_mode == "box":
        style = style.model_copy(
            update={
                "background_mode": "pill",
                "background_padding": style.background_padding if style.background_padding != (0.0, 0.0) else (20.0, 10.0),
                "background_radius": style.background_radius or 10.0,
                "background_opacity": 0.78 if style.background_opacity == 1.0 else style.background_opacity,
            }
        )
    return style


async def _prepare_motion_block_narration(
    db,
    *,
    project: Project,
    text: str,
    provider_voice_id: str,
    language: str,
    execution_id: str,
    scene_id: str,
) -> dict[str, Any]:
    """Synthesize or reuse a speed-1.0 narration original for a motion block act.

    Uses cached ``video_narrations`` originals first; synthesizes via MiniMax when
    configured; otherwise degrades cleanly to a pending ``SpeechObject`` plan so
    offline/deterministic runs work without live API calls.
    """
    from app.config import settings
    from app.tools.video.narration import (
        narration_billable_upper_bound,
        prepare_original_narration,
    )
    from app.tools.video.narration_store import peek_original
    from app.tools.video.params import narration_original_policy
    from app.tools.video.preparation import snapshot_narration_original

    speech = SpeechObject(
        kind="speech",
        object_id=f"obj_mb_speech_{scene_id}",
        text=text,
        voice_id=provider_voice_id,
        language=language,
    )
    original = await peek_original(project.user_id, speech)
    if original is None and settings.minimax_api_key:
        budget = narration_billable_upper_bound(" ".join(text.split())) * 2
        original, _ = await prepare_original_narration(
            speech,
            user_id=project.user_id,
            execution_id=execution_id,
            policy=narration_original_policy(budget),
        )
    if original is not None:
        _, snap = await snapshot_narration_original(
            db, project, text=text, original=original, scene_id=scene_id
        )
        await db.flush()
        return {
            "mode": "prepared",
            "snapshot": snap,
            "duration_s": float(original["duration_s"]),
            "cues": list(original.get("cues") or []),
        }
    return {"mode": "pending"}


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
        has_any_narration = any(shot.narration is not None for shot in args.shots) or any(
            mb.narration is not None for mb in args.motion_blocks
        )
        if has_any_narration and voice_generation_forbidden(getattr(turn, "text", "")):
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

            has_mb_narration = any(mb.narration is not None for mb in args.motion_blocks)
            resolved_provider_voice_id: str | None = None
            if has_mb_narration:
                from app.pipeline.voices import resolve_voice_id
                from app.platform.project_context import resolve_persona
                from app.tools.video.narration import DEFAULT_VIDEO_VOICE_ID, resolve_video_voice

                raw_voice_ref = args.voice_id
                if not raw_voice_ref:
                    persona = await resolve_persona(db, turn.project)
                    raw_voice_ref = resolve_video_voice(persona.voice if persona else None) or DEFAULT_VIDEO_VOICE_ID
                resolved_provider_voice_id, _ = await resolve_voice_id(
                    db, voice_ref=raw_voice_ref, owner_id=owner, increment_use=True
                )

            deferred_captions: list[tuple[str, int, int, str, Any, Any]] = []
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

                scene_index += 1
                scene_id = f"scene_{scene_index}"
                eff_duration_s = mb.duration_seconds
                narr_prep: dict[str, Any] | None = None
                eff_lang = (
                    _infer_narration_language(mb.narration, args.narration_language)
                    if mb.narration is not None
                    else None
                )
                if mb.narration is not None:
                    assert resolved_provider_voice_id is not None and eff_lang is not None
                    narr_prep = await _prepare_motion_block_narration(
                        db,
                        project=turn.project,
                        text=mb.narration,
                        provider_voice_id=resolved_provider_voice_id,
                        language=eff_lang,
                        execution_id=identity,
                        scene_id=scene_id,
                    )
                    if narr_prep["mode"] == "prepared" and required.get("target_seconds") is None:
                        measured_s = float(narr_prep["duration_s"])
                        has_visual_callout = bool(resolved_props.get("callout_steps"))
                        if has_visual_callout:
                            eff_duration_s = max(mb.duration_seconds, measured_s + 0.45)
                        else:
                            eff_duration_s = max(
                                measured_s + 0.45,
                                min(mb.duration_seconds, measured_s + 1.5),
                            )

                dur_ticks = seconds_to_ticks(eff_duration_s, rate)
                if dur_ticks <= 0:
                    raise ValueError("Motion block duration must be at least one composition tick.")
                start = cursor_ticks
                end = start + dur_ticks
                cursor_ticks = end
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

                scene_speech_ids: list[str] = []
                extra_audio_ops: list[Any] = []
                if mb.narration is not None and narr_prep is not None:
                    dialogue_track = next(
                        (t for t in comp_content.timeline.tracks if t.kind == "audio" and t.role == "dialogue"),
                        None,
                    )
                    if dialogue_track is None:
                        dialogue_track = Track(
                            track_id="trk_dialogue",
                            kind="audio",
                            role="dialogue",
                            order=max((t.order for t in comp_content.timeline.tracks if t.kind == "audio"), default=-1) + 1,
                            clips=[],
                        )
                        extra_audio_ops.append(AddTrack(op="add_track", track=dialogue_track))

                    from app.editing.caption_timing import (
                        build_motion_block_caption_phrases,
                        detect_text_language,
                    )

                    if narr_prep["mode"] == "prepared":
                        snap: SourceSnapshot = narr_prep["snapshot"]
                        bound_digests[snap.id] = snap.digest
                        if snap.id not in {b.snapshot_id for b in comp_content.sources}:
                            extra_audio_ops.append(BindSource(op="bind_source", snapshot_id=snap.id))
                        lead = seconds_to_ticks(0.15, rate)
                        audio_out_ticks = source_ticks_to_output_ticks(snap.duration_ticks, rate)
                        if start + lead + audio_out_ticks <= end:
                            speech_start = start + lead
                        else:
                            speech_start = start
                        avail_out = max(1, end - speech_start)
                        used_src_ticks = min(
                            snap.duration_ticks,
                            output_ticks_to_source_ticks(min(audio_out_ticks, avail_out), rate),
                        )
                        speech_end = speech_start + source_ticks_to_output_ticks(used_src_ticks, rate)
                        if speech_end > end:
                            used_src_ticks = max(1, used_src_ticks - 1)
                            speech_end = speech_start + source_ticks_to_output_ticks(used_src_ticks, rate)
                        extra_audio_ops.append(
                            AddClip(
                                op="add_clip",
                                track_id=dialogue_track.track_id,
                                clip=Clip(
                                    clip_id=f"clp_vo_{scene_id}",
                                    range=TimeRange(start=speech_start, end=speech_end),
                                    scene_id=scene_id,
                                    source=ClipSource(
                                        snapshot_id=snap.id,
                                        snapshot_digest=snap.digest,
                                        source_range=TimeRange(start=0, end=used_src_ticks),
                                    ),
                                    object=AudioObject(
                                        kind="audio",
                                        object_id=f"obj_vo_{scene_id}",
                                        gain_db=0.0,
                                    ),
                                    animations=[],
                                ),
                            )
                        )
                        cues = narr_prep.get("cues") or []
                        timed_phrases, is_bilingual = build_motion_block_caption_phrases(
                            mb.narration,
                            cues=cues,
                            duration_ms=float(narr_prep["duration_s"]) * 1000.0,
                            language=eff_lang or "en",
                            caption_translations=mb.caption_translations,
                            caption_text=mb.caption_text,
                        )
                        caption_style = _resolve_create_caption_style(
                            comp_content.settings,
                            caption_preset=args.caption_preset,
                            is_bilingual=is_bilingual,
                        )
                        prev_end = speech_start
                        for phrase in timed_phrases:
                            cs = max(
                                prev_end,
                                speech_start + seconds_to_ticks(phrase.time_begin_ms / 1000.0, rate),
                            )
                            ce = min(
                                speech_end,
                                speech_start + seconds_to_ticks(phrase.time_end_ms / 1000.0, rate),
                            )
                            if ce <= cs:
                                continue
                            deferred_captions.append(
                                (scene_id, cs, ce, phrase.text, caption_style, None)
                            )
                            prev_end = ce
                    else:
                        assert resolved_provider_voice_id is not None and eff_lang is not None
                        speech_clip_id = f"clp_speech_{scene_id}"
                        speech_obj_id = f"obj_speech_{scene_id}"
                        scene_speech_ids.append(speech_clip_id)
                        extra_audio_ops.append(
                            AddClip(
                                op="add_clip",
                                track_id=dialogue_track.track_id,
                                clip=Clip(
                                    clip_id=speech_clip_id,
                                    range=TimeRange(start=start, end=end),
                                    scene_id=scene_id,
                                    source=None,
                                    object=SpeechObject(
                                        kind="speech",
                                        object_id=speech_obj_id,
                                        text=mb.narration,
                                        voice_id=resolved_provider_voice_id,
                                        language=eff_lang,
                                        gain_db=0.0,
                                    ),
                                    animations=[],
                                ),
                            )
                        )
                        pending_line2: str | None = None
                        if mb.caption_translations:
                            cleaned_trans = [t.strip() for t in mb.caption_translations if t and t.strip()]
                            if cleaned_trans:
                                pending_line2 = " ".join(cleaned_trans)
                        elif mb.caption_text and mb.caption_text.strip():
                            lines = [ln.strip() for ln in mb.caption_text.splitlines() if ln.strip()]
                            if len(lines) >= 2:
                                pending_line2 = " ".join(lines[1:])
                            elif len(lines) == 1 and detect_text_language(lines[0]) != detect_text_language(mb.narration, hint=eff_lang):
                                pending_line2 = lines[0]
                        caption_display = f"{mb.narration}\n{pending_line2}" if pending_line2 else mb.narration
                        caption_style = _resolve_create_caption_style(
                            comp_content.settings,
                            caption_preset=args.caption_preset,
                            is_bilingual=pending_line2 is not None,
                        )
                        derivation = CaptionDerivation(
                            speech_object_id=speech_obj_id,
                            state="derived",
                            source_text_digest=speech_text_digest(mb.narration),
                            alignment="minimax-t2a-v2-sentence-v1",
                        )
                        deferred_captions.append(
                            (scene_id, start, end, caption_display, caption_style, derivation)
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
                                speech_clip_ids=scene_speech_ids,
                            ),
                        ),
                        *block_ops,
                        *extra_audio_ops,
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

            if deferred_captions:
                caption_ops: list[Any] = []
                cap_track = next(
                    (t for t in comp_content.timeline.tracks if t.kind == "visual" and t.role == "caption"),
                    None,
                )
                if cap_track is None:
                    cap_track = Track(
                        track_id="trk_caption",
                        kind="visual",
                        role="caption",
                        order=max((t.order for t in comp_content.timeline.tracks if t.kind == "visual"), default=-1) + 1,
                        clips=[],
                    )
                    caption_ops.append(AddTrack(op="add_track", track=cap_track))
                cap_layout = text_safe_layout(
                    comp_content.settings.width, comp_content.settings.height, "bottom", role="caption"
                )
                for cap_idx, (c_scene_id, c_start, c_end, c_text, c_style, c_deriv) in enumerate(deferred_captions, start=1):
                    caption_ops.append(
                        AddClip(
                            op="add_clip",
                            track_id=cap_track.track_id,
                            clip=Clip(
                                clip_id=f"clp_cap_{cap_idx}",
                                range=TimeRange(start=c_start, end=c_end),
                                scene_id=c_scene_id,
                                source=None,
                                object=TextObject(
                                    kind="text",
                                    object_id=f"obj_cap_{cap_idx}",
                                    text=c_text,
                                    layout=cap_layout,
                                    style=c_style,
                                    caption=c_deriv,
                                ),
                                animations=[],
                            ),
                        )
                    )
                comp_content = apply_ops(comp_content, caption_ops, bound_digests)

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

        if args.music_id is not None:
            from app.skills.blueprint import music_clips_for_window
            from app.tools.video.preparation import snapshot_music_track

            comp_content = CompositionContent.model_validate(content)
            track_row = await db.get(Music, args.music_id)
            if track_row is None or track_row.status == "archived" or not (
                track_row.is_public or track_row.scope == "platform" or track_row.generated_by_user_id == owner
            ):
                raise ValueError(f"Music {args.music_id} is unavailable.")
            bgm_snap = await snapshot_music_track(db, track_row, owner_id=owner)
            if bgm_snap.origin_project_id is None:
                bgm_snap.origin_project_id = project
            track_row.use_count = int(track_row.use_count or 0) + 1
            await db.flush()

            total_ticks = max(
                (clip.range.end for trk in comp_content.timeline.tracks for clip in trk.clips),
                default=0,
            )
            if total_ticks > 0:
                has_dialogue = any(
                    trk.kind == "audio" and trk.role == "dialogue" and trk.clips
                    for trk in comp_content.timeline.tracks
                )
                eff_bgm_gain = (
                    args.bgm_gain_db
                    if "bgm_gain_db" in args.model_fields_set
                    else (-22.0 if has_dialogue else -14.0)
                )
                bgm_clips = music_clips_for_window(
                    settings=comp_content.settings,
                    start=0,
                    end=total_ticks,
                    source_id=bgm_snap.id,
                    digest=bgm_snap.digest,
                    source_ticks=bgm_snap.duration_ticks,
                    id_stem="create_bgm",
                    gain_db=eff_bgm_gain,
                    fade_in_seconds=0.8,
                    fade_out_seconds=1.5,
                )
                bgm_ops: list[Any] = []
                bound_digests_bgm = {
                    b.snapshot_id: b.snapshot_digest
                    for b in comp_content.sources
                    if b.snapshot_digest
                }
                bound_digests_bgm[bgm_snap.id] = bgm_snap.digest
                if bgm_snap.id not in {b.snapshot_id for b in comp_content.sources}:
                    bgm_ops.append(BindSource(op="bind_source", snapshot_id=bgm_snap.id))
                music_track = next(
                    (t for t in comp_content.timeline.tracks if t.kind == "audio" and t.role == "music"),
                    None,
                )
                if music_track is None:
                    music_track = Track(
                        track_id="trk_music",
                        kind="audio",
                        role="music",
                        order=max((t.order for t in comp_content.timeline.tracks if t.kind == "audio"), default=-1) + 1,
                        clips=[],
                    )
                    bgm_ops.append(AddTrack(op="add_track", track=music_track))
                for bc in bgm_clips:
                    bgm_ops.append(AddClip(op="add_clip", track_id=music_track.track_id, clip=bc))
                comp_content = apply_ops(comp_content, bgm_ops, bound_digests_bgm)
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
        "narration_clips": [
            {
                "clip_id": clip["clip_id"],
                "kind": clip["object"]["kind"],
                "start_seconds": clip["range"]["start"] / rate_saved,
                "end_seconds": clip["range"]["end"] / rate_saved,
            }
            for track in saved.timeline["tracks"]
            if track["kind"] == "audio" and track["role"] == "dialogue"
            for clip in track["clips"]
        ],
        "bgm_clips": [
            {
                "clip_id": clip["clip_id"],
                "gain_db": clip["object"].get("gain_db"),
                "start_seconds": clip["range"]["start"] / rate_saved,
                "end_seconds": clip["range"]["end"] / rate_saved,
            }
            for track in saved.timeline["tracks"]
            if track["kind"] == "audio" and track["role"] == "music"
            for clip in track["clips"]
        ],
    }
