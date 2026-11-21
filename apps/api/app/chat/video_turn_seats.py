"""Project video observations, scoped confirmations and reviewed delivery facts."""

import json
import re
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from botocore.exceptions import BotoCoreError, ClientError

from app.agents.tool_loop import TerminalRefusal, ToolObservation
from app.chat.activity_receipts import (
    SkillReadReceipt,
    music_search_receipt,
    music_selection_receipt,
    sfx_import_receipt,
    sfx_search_receipt,
)
from app.models.schemas import (
    AnnotateNarrationArgs,
    BuiltInSkillReference,
    ExternalSkillReference,
    GetNarrationAlignmentArgs,
    ImportSfxArgs,
    ProjectBrief,
    AlignRecordingArgs,
    ReviewVideoArgs,
    SearchSfxArgs,
    SelectMusicArgs,
    SelectVideoPresetArgs,
    ShowMusicCandidatesArgs,
    ShowVideoPresetsArgs,
    SkillReference,
    VideoPresetChoice,
)
from app.models.tables import Message, Project

if TYPE_CHECKING:
    pass


def _sfx_display_title(title: str) -> str:
    """Model-facing title; the raw provider title stays persisted for audit."""
    return re.sub(r"\.[A-Za-z][A-Za-z0-9]{0,15}$", "", title)


def audio_candidate_context_lines(candidate_logs: list[dict[str, Any]]) -> list[str]:
    """Project persisted SFX/Music sets and selections into model-facing facts.

    Candidate rows have empty prose by design, so the ordinary recent-message
    projection cannot carry their identities into the selection turn. This is
    a read-only projection of the same candidates_log archive used by selection;
    it never chooses a set on the user's behalf.
    """
    import json

    sets: dict[str, dict[str, Any]] = {}
    for log in candidate_logs:
        events = log.get("events") if isinstance(log, dict) else None
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            set_id = event.get("candidate_set_id")
            if not isinstance(set_id, str) or not set_id:
                continue
            kind = event.get("kind")
            if kind in {"sfx_set", "set", "music_set"}:
                members = event.get("members")
                expected_provider = "music_library" if kind == "music_set" else "freesound"
                if (
                    event.get("asset_id") is not None
                    or not isinstance(members, list)
                    or not members
                    or not all(
                        isinstance(member, dict)
                        and member.get("provider") == expected_provider
                        for member in members
                    )
                ):
                    continue
                sets[set_id] = {
                    "candidate_set_id": set_id,
                    "candidate_kind": "music" if kind == "music_set" else "sfx",
                    "topic": event.get("topic"),
                    "members": [
                        {
                            "member_index": index,
                            "ordinal": index + 1,
                            "title": (
                                _sfx_display_title(title)
                                if kind != "music_set" and isinstance((title := member.get("title")), str)
                                else member.get("title")
                            ),
                            "duration_seconds": member.get("duration_seconds"),
                        }
                        for index, member in enumerate(members)
                    ],
                    "selected": [],
                }
            elif kind == "selection" and set_id in sets:
                selected = event.get("selected")
                if isinstance(selected, list):
                    sets[set_id]["selected"] = [
                        index for index in selected
                        if isinstance(index, int) and not isinstance(index, bool)
                    ]
    if not sets:
        return []
    return [
        "已保存的音频候选集（供后续选择时引用）：",
        *(json.dumps(item, ensure_ascii=False) for item in sets.values()),
    ]


async def _owned_video_output(db, project, mention):
    from sqlalchemy import select

    from app.models.tables import Output

    try:
        output_id = UUID(str(mention.id))
    except ValueError:
        return None
    return await db.scalar(select(Output).join(Project, Output.project_id == Project.id).where(
        Output.id == output_id, Output.project_id == project.id, Project.user_id == project.user_id
    ))


async def video_target_hint(db, project, mentions=()):
    pins = [m for m in mentions or [] if m.type == "output"]
    if pins:
        row = await _owned_video_output(db, project, pins[0]) if len(pins) == 1 else None
        if row is None or not row.composition_id or not row.composition_version_id:
            return {"unavailable": True}
        return {"output_id": str(row.id), "output_version_id": str(row.composition_version_id), "composition_id": str(row.composition_id), "version_id": str(row.composition_version_id),
                **({"selected_region": pins[0].region.model_dump(mode="json")} if pins[0].region else {})}
    return None


async def video_context_lines(
    db, project, mentions=(), *, skill: SkillReference | None = None,
):
    """Skill, candidate and presentation facts; resources have one fresh assembler."""
    import json

    from sqlalchemy import select

    from app.models.tables import Asset, Conversation
    candidate_logs = list((await db.execute(
        select(Message.intent)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.project_id == project.id,
            Conversation.user_id == project.user_id,
            Message.intent["type"].astext == "candidates_log",
        )
        .order_by(Message.seq)
    )).scalars())
    from app.tools.video.presets import video_preset_candidate_context_lines
    lines = [
        *audio_candidate_context_lines(candidate_logs),
        *video_preset_candidate_context_lines(candidate_logs),
    ]
    if skill is not None:
        lines.append(
            "服务端仅为本轮首稿绑定的 Skill："
            + json.dumps(skill.model_dump(mode="json"), ensure_ascii=False)
        )
    # Assets, page bodies, frozen sources and complete compositions ride the
    # fresh shared project context, never a second stale identity-only list.
    receipt = (project.pending_brief or {}).get("video_presentation")
    if receipt:
        lines.append("正在审阅的视频：" + json.dumps(receipt, ensure_ascii=False))
    for mention in mentions or []:
        if mention.type == "asset":
            try:
                asset_id = UUID(str(mention.id))
            except ValueError:
                continue  # A staged local file has no server asset id yet.
            asset = await db.scalar(select(Asset).where(Asset.id == asset_id, Asset.user_id == project.user_id))
            if asset is not None:
                lines.append("用户提到的源素材：" + json.dumps({"asset_id": str(asset.id),
                    "type": asset.type.value, "name": asset.title,
                    "processing_status": asset.processing_status.value}, ensure_ascii=False))
            continue
        if mention.type != "output":
            continue
        row = await _owned_video_output(db, project, mention)
        if row is not None and row.composition_version_id:
            payload: dict[str, object] = {"output_id": str(row.id),
                "composition_id": str(row.composition_id),
                "composition_version_id": str(row.composition_version_id),
                "content_digest": (row.payload or {}).get("composition_digest")}
            if mention.region:
                payload["selected_region"] = mention.region.model_dump(mode="json")
            lines.append("用户提到的视频输出：" + json.dumps(payload, ensure_ascii=False))
    return lines


def _version_context_keys(read: dict) -> tuple[str, ...]:
    version_id, digest = read.get("composition_version_id"), read.get("content_digest")
    return (f"composition:{version_id}:{digest}",) if version_id and digest else ()


async def read_video_for_presentation(db, project, params):
    """Read the saved version and prepare an explicitly requested local Scrub."""
    from app.editing.service import format_storyboard_text, video_version_read
    from app.editing.store import CompositionNotFound, PermissionDenied
    try:
        read = await video_version_read(db, owner_id=project.user_id,
            version_id=params.version_id, composition_id=params.composition_id,
            output_id=params.output_id)
        if params.scrub is not None:
            from app.tools.video.preview import prepare_saved_video_scrub
            read = await prepare_saved_video_scrub(
                db, read, owner_id=project.user_id, target=params.scrub
            )
    except (CompositionNotFound, PermissionDenied, ValueError):
        return None, "No accessible video version at this reference."
    observation = format_storyboard_text(read)
    if read.get("video_preview"):
        import json
        preview = read["video_preview"]
        observation += "\nLOCAL SCRUB (not an Output or complete-video preview): " + json.dumps({
            "status": preview.get("status"),
            "reason": preview.get("reason"),
            "scope": preview.get("scope"),
        }, ensure_ascii=False)
    return read, ToolObservation(
        observation, context_keys=_version_context_keys(read)
    )


async def review_video_seat(
    *,
    turn, args: ReviewVideoArgs,
) -> str | ToolObservation | TerminalRefusal:
    """Decode and review the exact Output; persist its advisory report."""

    import json

    from app.models.database import AsyncSessionLocal
    from app.tools.video.review import ReviewAttemptFailed, ReviewError, review_video

    turn._video_review_report = None
    selected = (getattr(turn, "_editor_export", None) or getattr(turn, "_editor_output_pin", None) or {})
    if selected.get("output_id") and str(args.output_id) != selected["output_id"]:
        return ToolObservation("Review the exact selected Output.", ok=False)
    try:
        async with AsyncSessionLocal() as video_db:
            report = await review_video(video_db, owner_id=turn.project.user_id, project_id=turn.project.id,
                                        opening_id=turn.turn_id, args=args)
    except ReviewAttemptFailed as exc:
        return TerminalRefusal(
            str(exc),
            facts={
                "kind": "video_review_failure",
                "output_id": str(args.output_id),
                "at_seconds": args.at_seconds,
                "previous_report": exc.previous_report,
            },
        )
    except (ReviewError, ValueError) as exc:
        return ToolObservation(str(exc), ok=False, user_error=str(exc))
    from app.agents.tool_progress import current_group_id

    turn._video_review_report = report
    turn._video_review_group = current_group_id()
    from app.chat.activity_receipts import video_review_receipt

    return ToolObservation(
        "内容审阅结果已保存在本次审阅的确切 Output 上。以下为已保存的报告事实，仅基于静帧给出建议，不决定能否交付：\n"
        + json.dumps(report, ensure_ascii=False),
        receipt=video_review_receipt(report),
    )


async def video_request_id(db, conversation_id: UUID, counter: int) -> str:
    """Key a call by its persisted user turn, never the whole conversation.

    Re-entering the same turn/call keeps its key; subsequent user messages
    in the same Chat get a different namespace. The existing Chat execution
    mutex serializes turns in one conversation.
    """
    from sqlalchemy import select

    message_id = await db.scalar(
        select(Message.id)
        .where(Message.conversation_id == conversation_id, Message.role == "user")
        .order_by(Message.seq.desc())
        .limit(1)
    )
    if message_id is None:
        raise ValueError("video edits require a persisted user message")
    return f"video:{message_id}:{counter}"


async def prepare_bound_skill_context(*, project, skill, message, package_sessions):
    """Read static Skill instructions before the model; long IO stays in tools.

    The returned reader refreshes committed project facts every continuation.
    Skill/package budgets, permissions and existing read receipts are reused.
    """
    from dataclasses import replace

    from app.metering import current_conversation_trace
    from app.skills.package_session import ReadSkillReferenceArgs
    from app.tools.project_context import project_context_reader

    if project is None or skill is None:
        return project_context_reader(project.id, project.user_id) if project is not None else None

    async def observed(name, params, operation):
        logger = structlog.get_logger()
        identity = {**(current_conversation_trace() or {}), "project_id": str(project.id),
                    "scope": "prompt_assembly", "path": getattr(params, "path", None)}
        started = time.monotonic()
        logger.info("initial_chat_dependency_started", tool_name=name, **identity)
        try:
            result = await operation()
        except BaseException as exc:
            logger.info("initial_chat_dependency_interrupted", tool_name=name,
                        error_type=type(exc).__name__, **identity)
            raise
        logger.info("initial_chat_dependency_completed", tool_name=name, ok=result.ok,
                    duration_ms=int((time.monotonic() - started) * 1000), **identity)
        return result

    if not package_sessions:
        from app.models.database import AsyncSessionLocal
        from app.tools.project_context import settled_skill_read_receipts

        async with AsyncSessionLocal() as db:
            receipts = await settled_skill_read_receipts(
                db, project_id=project.id, owner_id=project.user_id
            )
        # Restore text only after the real package exists and its immutable
        # identity, owner and per-resource digests have been checked.
        probe = await skill_read_seat(
            project=project, skill=skill, package_sessions=package_sessions,
            name="read_skill_reference", args=ReadSkillReferenceArgs(path="SKILL.md"),
        )
        package = package_sessions.get(skill.model_dump_json())
        receipt = receipts.get(package.receipt_identity(skill)) if package is not None else None
        if package is not None and receipt is not None:
            await package.restore_text_reads(receipt, skill=skill, owner_id=project.user_id)
        root = probe
    else:
        root_args = ReadSkillReferenceArgs(path="SKILL.md")
        root = await observed("read_skill_reference", root_args, lambda: skill_read_seat(
            project=project, skill=skill, package_sessions=package_sessions,
            name="read_skill_reference", args=root_args))
    method = (
        "BOUND SKILL METHOD（服务端读取的包内资源）。按用户选择采用创作方法。示例仅作参考。工具访问与费用授权由宿主核验。\n" + root.text
    )
    read_project = project_context_reader(project.id, project.user_id, skill.model_dump(mode="json"))

    async def read():
        current = await read_project()
        return replace(current, skill_method=method)
    return read


async def skill_read_seat(
    *,
    project: Project,
    skill: SkillReference | None,
    package_sessions: dict[str, Any],
    name: str,
    args: Any,
) -> ToolObservation:
    """Read the currently bound immutable Skill inside the ordinary Chat loop."""
    from app.skills.package_reader import open_builtin_skill_package
    from app.skills.package_session import SkillPackageBudgetError, SkillPackageSession

    if skill is None:
        return ToolObservation("No Skill is bound to this message; package reads are unavailable.", ok=False)
    key = skill.model_dump_json()
    package = package_sessions.get(key)
    if package is None:
        if isinstance(skill, BuiltInSkillReference):
            package = SkillPackageSession(open_builtin_skill_package(skill.skill_id, skill.version))
        elif isinstance(skill, ExternalSkillReference):
            from app.models.database import AsyncSessionLocal
            from app.skills.loading import load_skill_creative_context

            async with AsyncSessionLocal() as db:
                context = await load_skill_creative_context(
                    db,
                    owner_id=project.user_id,
                    skill_version_id=skill.skill_version_id,
                )
            package = context.package
        else:
            return ToolObservation("The bound Skill reference is unavailable.", ok=False)
        package_sessions[key] = package
    try:
        observed = await package.observe(name, args)
    except SkillPackageBudgetError as exc:
        return ToolObservation(f"Skill read stopped: {exc}", ok=False)
    receipt = SkillReadReceipt(
        package_identity=package.receipt_identity(skill),
        skill_reference=skill.model_dump(mode="json"),
        owner_id=str(project.user_id),
        reads=package.provenance["reads"],
        preview_checks=package.provenance["preview_checks"],
        media_files=package.media_files,
    )
    return ToolObservation(
        observed.text,
        ok=observed.ok,
        images=observed.images,
        receipt=receipt if observed.ok else None,
        # Actual image evidence remains attached for the whole current loop;
        # a textual manifest never substitutes for it.
        context_lifetime="turn" if observed.images else "project",
        context_keys=(),
    )


def _shared_material_summary(facts: dict) -> str:
    summary = {
        **facts,
        "resources": [
            {
                key: value
                for key, value in resource.items()
                if key not in {"lines", "citable_lines", "views", "selected_target"}
            }
            for resource in facts.get("resources", [])
        ],
        "selected_targets": [
            {
                "snapshot_id": resource.get("snapshot_id"),
                "view_id": (resource.get("selected_target") or {}).get("view_id"),
                "element_id": (resource.get("selected_target") or {}).get("element_id"),
            }
            for resource in facts.get("resources", [])
            if resource.get("selected_target")
        ],
        "source_body": "简要标识见 CURRENT PROJECT EVIDENCE；用 material_targets 取回所选目标的确切事实或媒体",
    }
    return json.dumps(summary, ensure_ascii=False)


async def prepare_video_materials_seat(
    *, project: Project, args: Any, turn_id: UUID | None = None,
) -> ToolObservation:
    from app.agents.errors import AgentStopError
    from app.tools.research.capture import CaptureError
    from app.tools.video.design import DesignError, prepare_video_materials

    try:
        facts, images = await prepare_video_materials(
            owner_id=project.user_id, project_id=project.id, args=args, turn_id=turn_id,
        )
    except (DesignError, ValueError, AgentStopError, CaptureError, OSError) as exc:
        return ToolObservation(f"Material preparation rejected: {exc}", ok=False)
    keys = tuple(facts.pop("context_keys"))
    return ToolObservation(
        json.dumps(facts, ensure_ascii=False),
        images=tuple(images),
        context_lifetime="project",
        context_keys=keys,
        project_text=_shared_material_summary(facts) if images else None,
    )


async def analyze_brand_seat(*, project: Project, args: Any, user_text: str) -> ToolObservation:
    """Extract with real PNG evidence, then save through one independent short transaction."""
    from app.chat.readiness import (
        brief_with_user_constraints,
        creative_state_for_pending,
        urls_from_text,
    )
    from app.chat.service import merge_brief
    from app.models.database import AsyncSessionLocal
    from app.models.schemas import CreativeState, ProjectBrief, seal_creative_state
    from app.providers.llm.base import LLMError
    from app.tools.video.brand import BrandEvidenceError, analyze_brand

    stored = ProjectBrief.model_validate(project.pending_brief or {})
    current = creative_state_for_pending(stored) or CreativeState()
    source_text = user_text if urls_from_text(user_text) else stored.prompt or user_text
    brief = merge_brief(
        args.brief,
        brief_with_user_constraints(
            user_text, brief_with_user_constraints(source_text, current.brief)
        ),
    )
    try:
        profile, facts = await analyze_brand(
            owner_id=project.user_id,
            project_id=project.id,
            user_text=source_text,
            brief=brief,
        )
    except (BrandEvidenceError, LLMError, ValueError, OSError) as exc:
        return ToolObservation(
            f"Brand analysis failed without saving a BrandProfile: {exc}", ok=False
        )

    async with AsyncSessionLocal() as db:
        current_project = await db.get(Project, project.id, with_for_update=True)
        if current_project is None or current_project.user_id != project.user_id:
            return ToolObservation("Brand analysis could not save: project unavailable", ok=False)
        latest = ProjectBrief.model_validate(current_project.pending_brief or {})
        latest_state = creative_state_for_pending(latest) or CreativeState()
        latest_source_text = (
            user_text if urls_from_text(user_text) else latest.prompt or source_text
        )
        latest_brief = merge_brief(
            args.brief,
            brief_with_user_constraints(
                user_text, brief_with_user_constraints(latest_source_text, latest_state.brief)
            ),
        )
        if not latest.prompt:
            latest.prompt = source_text
        latest.brief = latest_brief
        latest.creative_state = seal_creative_state(CreativeState(
            brief=latest_brief,
            brand_profile=profile,
            source_refs=profile.source_refs,
        ))
        current_project.pending_brief = latest.model_dump(mode="json")
        await db.commit()
        project.pending_brief = current_project.pending_brief
    return ToolObservation(json.dumps(facts, ensure_ascii=False))


async def capture_web_seat(*, project: Project, args: Any) -> ToolObservation:
    from app.tools.video.design import DesignError, capture_video_web

    try:
        facts, images = await capture_video_web(
            owner_id=project.user_id, project_id=project.id, request=args,
        )
    except (DesignError, ValueError) as exc:
        return ToolObservation(f"Web capture rejected or failed: {exc}", ok=False)
    keys = tuple(facts.pop("context_keys"))
    return ToolObservation(
        json.dumps(facts, ensure_ascii=False),
        images=tuple(images),
        context_lifetime="project",
        context_keys=keys,
        project_text=_shared_material_summary(facts) if images else None,
    )








async def show_video_presets_seat(
    *,
    project: Project,
    args: ShowVideoPresetsArgs,
    on_candidates,
) -> ToolObservation:
    """Present real dynamic native Presets through the existing candidate channel."""

    from app.tools.video.presets import VideoPresetError, show_video_preset_candidates

    try:
        payload = show_video_preset_candidates(args.preset_ids)
    except VideoPresetError as exc:
        return ToolObservation(f"show_video_presets rejected: {exc}", ok=False)
    await on_candidates(payload)
    facts = {
        "candidate_set_id": payload["candidate_set_id"],
        "members": [
            {
                "member_index": index,
                "ordinal": index + 1,
                "preset_id": member["preset_id"],
                "duration_seconds": member["duration_seconds"],
            }
            for index, member in enumerate(payload["members"])
        ],
    }
    return ToolObservation(
        "事实：已展示 2–4 个真实的原生 Preset 预览。未创建 CompositionVersion 或 Run，用户尚未选择或表示制作意图。可在卡片播放。简要比较并请用户按序号选择，然后结束本轮。\n"
        + json.dumps(facts, ensure_ascii=False)
    )


async def select_video_preset_seat(
    *,
    project: Project,
    args: SelectVideoPresetArgs,
    on_candidates,
) -> ToolObservation:
    """Validate and repaint one original candidate; this is never an edit or Run."""

    from app.models.database import AsyncSessionLocal
    from app.tools.video.presets import (
        VideoPresetError,
        resolve_video_preset_choice,
    )

    try:
        async with AsyncSessionLocal() as candidate_db:
            preset_id = await resolve_video_preset_choice(
                candidate_db,
                project=project,
                choice=VideoPresetChoice(
                    candidate_set_id=args.candidate_set_id,
                    member_index=args.member_index,
                ),
            )
    except (VideoPresetError, ValueError) as exc:
        return ToolObservation(
            f"select_video_preset rejected: {exc}; no selection or version was written",
            ok=False,
        )
    await on_candidates({
        "kind": "selection",
        "candidate_set_id": str(args.candidate_set_id),
        "selected": [args.member_index],
    })
    return ToolObservation(json.dumps({
        "candidate_set_id": str(args.candidate_set_id),
        "member_index": args.member_index,
        "ordinal": args.member_index + 1,
        "preset_id": preset_id,
        "selection_only": True,
        "version_written": False,
        "run_created": False,
    }, ensure_ascii=False))


async def search_sfx_seat(
    *,
    project: Project,
    args: SearchSfxArgs,
    user_text: str,
    on_candidates,
) -> ToolObservation:
    """Emit real CC0 candidates; only the settled turn makes them importable."""

    from app.chat.sfx_intent import allows_provider_search, sfx_intent_agent
    from app.providers.llm.base import LLMError

    try:
        decision = await sfx_intent_agent.call(user_text=user_text)
    except LLMError as exc:
        return ToolObservation(
            f"search_sfx admission unavailable ({type(exc).__name__}); no provider search ran",
            ok=False,
        )
    admission = decision.model_dump(mode="json")
    if not allows_provider_search(decision):
        return ToolObservation(
            "search_sfx admission rejected by the classified user intent; no provider "
            "search ran and no candidates were emitted.\n"
            + json.dumps({"admission": admission}, ensure_ascii=False),
            ok=False,
        )
    from app.providers.freesound import FreesoundError
    from app.tools.video.sfx import SfxError, search_sfx_candidates

    try:
        payload = await search_sfx_candidates(args.query)
    except (SfxError, FreesoundError) as exc:
        return ToolObservation(f"search_sfx failed honestly: {exc}", ok=False)
    await on_candidates(payload)
    selection_facts = {
        "candidate_set_id": payload["candidate_set_id"],
        "topic": payload["topic"],
        "members": [
            {
                "member_index": index,
                "ordinal": index + 1,
                "title": _sfx_display_title(member["title"]),
                "duration_seconds": member["duration_seconds"],
            }
            for index, member in enumerate(payload["members"])
        ],
    }
    return ToolObservation(
        "事实：已展示候选，未写入素材或视频版本。可报告候选数量、显示名称和时长。用户可在卡片实际试听并按序号选择；本次搜索没有试听结果。\n"
        + json.dumps({"admission": admission, **selection_facts}, ensure_ascii=False),
        receipt=sfx_search_receipt(selection_facts),
    )


async def import_sfx_seat(
    *,
    project: Project,
    args: ImportSfxArgs,
    on_candidates,
) -> ToolObservation | TerminalRefusal:
    """Resolve a settled candidate, freeze its MP3 and repaint its selection."""

    import json

    from app.models.database import AsyncSessionLocal
    from app.providers.freesound import FreesoundError
    from app.tools.video.sfx import SfxError, import_sfx_candidate

    try:
        async with AsyncSessionLocal() as video_db:
            facts = await import_sfx_candidate(video_db, project=project, args=args)
    except (SfxError, FreesoundError, ValueError, PermissionError) as exc:
        return TerminalRefusal(
            f"the selected SFX import failed deterministically: {exc}; no revision was made",
            facts={"kind": "sfx_import_failure"},
        )
    await on_candidates({
        "kind": "selection",
        "candidate_set_id": str(args.candidate_set_id),
        "selected": [args.member_index],
    })
    selection_facts = {
        key: facts[key]
        for key in (
            "asset_id",
            "snapshot_id",
            "snapshot_digest",
            "duration_seconds",
            "title",
        )
    }
    selection_facts["title"] = _sfx_display_title(facts["title"])
    return ToolObservation(
        "事实：选中的 MP3 已作为音频素材导入，并有下列不可变 SourceSnapshot。未修改 CompositionVersion。\n"
        + json.dumps(selection_facts, ensure_ascii=False),
        receipt=sfx_import_receipt(
            selection_facts,
            candidate_set_id=args.candidate_set_id,
            member_index=args.member_index,
        ),
    )


async def show_music_candidates_seat(
    *,
    project: Project,
    args: ShowMusicCandidatesArgs,
    on_candidates,
) -> ToolObservation:
    """Emit playable local-library Music candidates; only a settled turn is selectable."""

    from app.models.database import AsyncSessionLocal
    from app.tools.video.music_candidates import MusicCandidateError, show_music_candidate_set

    try:
        async with AsyncSessionLocal() as db:
            payload = await show_music_candidate_set(
                db,
                owner_id=project.user_id,
                query=args.query,
            )
    except (MusicCandidateError, ValueError) as exc:
        return ToolObservation(f"show_music_candidates failed honestly: {exc}", ok=False)
    await on_candidates(payload)
    selection_facts = {
        "candidate_set_id": payload["candidate_set_id"],
        "topic": payload["topic"],
        "members": [
            {
                "member_index": index,
                "ordinal": index + 1,
                "title": member["title"],
                "duration_seconds": member["duration_seconds"],
            }
            for index, member in enumerate(payload["members"])
        ],
    }
    return ToolObservation(
        "事实：已展示本地 Music 候选，未写入素材、CompositionVersion 或 Run。用户可在卡片实际播放，再按序号选择。本次观察没有试听结果。\n"
        + json.dumps(selection_facts, ensure_ascii=False),
        receipt=music_search_receipt(selection_facts),
    )


async def select_music_seat(
    *,
    project: Project,
    args: SelectMusicArgs,
    on_candidates,
) -> ToolObservation | TerminalRefusal:
    """Resolve a settled Music candidate without downloading or writing a version."""

    from app.models.database import AsyncSessionLocal
    from app.tools.video.music_candidates import MusicCandidateError, select_music_candidate

    try:
        async with AsyncSessionLocal() as db:
            facts = await select_music_candidate(
                db,
                project=project,
                candidate_set_id=args.candidate_set_id,
                member_index=args.member_index,
            )
    except (MusicCandidateError, ValueError, PermissionError) as exc:
        return TerminalRefusal(
            f"the selected Music choice failed deterministically: {exc}; no revision was made",
            facts={"kind": "music_selection_failure"},
        )
    await on_candidates({
        "kind": "selection",
        "candidate_set_id": str(args.candidate_set_id),
        "selected": [args.member_index],
    })
    selection_facts = {
        key: facts[key]
        for key in ("music_id", "title", "duration_seconds")
    }
    return ToolObservation(
        "事实：已解析保存的本地 Music 选择，未导入素材、修改 CompositionVersion 或启动 Run。可用 prepare_video_materials 固定该 music_id。\n"
        + json.dumps(selection_facts, ensure_ascii=False),
        receipt=music_selection_receipt(
            selection_facts,
            candidate_set_id=args.candidate_set_id,
            member_index=args.member_index,
        ),
    )


async def align_recording_seat(
    *, project: Project | None, args: AlignRecordingArgs, mentions=()
) -> str | ToolObservation:
    if project is None:
        return "narration preparation needs a project context"
    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.database import AsyncSessionLocal
    from app.tools.video.alignment_store import request_alignment, wait_for_alignment
    request_text = args.text
    try:
        async with AsyncSessionLocal() as db:
            from app.models.tables import Asset
            from app.tools.video.preparation import snapshot_audio_asset

            asset = await db.get(Asset, args.audio_asset_id)
            if asset is None or asset.user_id != project.user_id:
                return "the referenced AUDIO asset is not accessible"
            generated = isinstance((asset.meta or {}).get("origin"), dict) and bool(
                asset.meta["origin"].get("video_narration_hash")
            )
            mentioned = {
                str(getattr(mention, "id", ""))
                for mention in mentions
                if getattr(mention, "type", None) == "asset"
            }
            if not generated and str(args.audio_asset_id) not in mentioned:
                return (
                    "align_recording requires the user's explicit @asset reference for "
                    "this AUDIO recording; no alignment was requested"
                )
            snapshot = await snapshot_audio_asset(db, asset, owner_id=project.user_id)
            await db.commit()
            snapshot_id = snapshot.id
        requested = await request_alignment(
            owner_id=project.user_id, audio_snapshot_id=snapshot_id, text=request_text
        )
        read = await wait_for_alignment(
            owner_id=project.user_id, alignment_id=UUID(requested["alignment_id"])
        )
        analysis = None
        async with AsyncSessionLocal() as db:
            from app.models.tables import SourceSnapshot

            fixed = await db.get(SourceSnapshot, snapshot_id)
            analysis_ref = (fixed.meta or {}).get("analysis_ref") if fixed is not None else None
        if analysis_ref:
            from app.tools.video.media_analysis import read_report

            analysis = await read_report(analysis_ref)
    except (ValueError, PermissionError) as exc:
        return ToolObservation(f"align_recording rejected: {exc}", ok=False)
    except (BotoCoreError, ClientError, OSError):
        return ToolObservation("Narration audio or its measured analysis is unavailable.", ok=False)
    payload = (read.get("payload") or {})
    duration_ticks = payload.get("duration_ticks")
    read.update({
        "actual_duration_seconds": (
            duration_ticks / (payload.get("source_timebase") or SOURCE_TIMEBASE)
            if duration_ticks is not None else None
        ),
        "cues": [
            {
                "sentence_id": sentence.get("sentence_id"),
                "text": sentence.get("text"),
                "start_tick": sentence.get("start_tick"),
                "end_tick": sentence.get("end_tick"),
            }
            for sentence in payload.get("sentences") or []
        ],
        "analysis": analysis,
        "scope": "结果仅含原速音频及其实际对齐，未创建 CompositionVersion 或视频 Output。",
    })
    return ToolObservation(json.dumps(read, ensure_ascii=False), fold_after_delivery=True)


async def get_narration_alignment_seat(
    *, project: Project | None, args: GetNarrationAlignmentArgs
) -> str | ToolObservation:
    if project is None:
        return "narration alignment reads need a project context"
    from app.models.database import AsyncSessionLocal
    from app.tools.video.alignment_store import alignment_read, get_alignment

    try:
        async with AsyncSessionLocal() as db:
            row = await get_alignment(db, owner_id=project.user_id, alignment_id=args.alignment_id)
            read = alignment_read(row)
    except ValueError as exc:
        return f"get_narration_alignment rejected: {exc}"
    return ToolObservation(json.dumps(read, ensure_ascii=False))


async def annotate_narration_seat(
    *, project: Project | None, args: AnnotateNarrationArgs
) -> str | ToolObservation:
    if project is None:
        return "narration annotation needs a project context"
    from app.editing.alignment import NarrationPayload, NarrationSemantics
    from app.models.database import AsyncSessionLocal
    from app.tools.video.alignment_store import annotate_alignment, get_alignment

    try:
        async with AsyncSessionLocal() as db:
            row = await get_alignment(db, owner_id=project.user_id, alignment_id=args.alignment_id)
            if row.status != "ALIGNED":
                return "annotate_narration accepts only an ALIGNED row; READY is immutable"
            payload = NarrationPayload.model_validate(row.payload)
        expected_ids = [sentence.sentence_id for sentence in payload.sentences]
        supplied_ids = [sentence.sentence_id for sentence in args.sentences]
        if supplied_ids != expected_ids:
            return (
                "annotate_narration needs every current sentence exactly once and in order: "
                + ", ".join(expected_ids)
            )
        semantics_by_id = {
            item.sentence_id: NarrationSemantics(
                role=item.role,
                weight=item.weight,
                entities=item.entities,
                needs=item.needs,
                emphasis_word_ids=item.emphasis_word_ids,
            )
            for item in args.sentences
        }
        for sentence in payload.sentences:
            sentence.semantics = semantics_by_id[sentence.sentence_id]
        payload = NarrationPayload.model_validate(payload.model_dump(mode="json"))
        read = await annotate_alignment(
            owner_id=project.user_id,
            alignment_id=args.alignment_id,
            payload=payload,
            expected_timing_digest=args.expected_timing_digest,
        )
    except ValueError as exc:
        return f"annotate_narration rejected: {exc}"
    return ToolObservation(json.dumps(read, ensure_ascii=False))


def stamp_video_presentation(
    project: Project, message: Message | None, read: dict[str, Any] | None,
    *, production_requested: bool = False, observed_ranges: list[dict] | None = None,
) -> ProjectBrief | None:
    """The presentation association (ADR-145 phase B; the film stamp's
    sibling): fires from a runner's finish when a video design/revision
    beat this turn is owed its presentation and a TERMINAL speech row
    actually persisted. Two writes ride the turn's one transaction: the
    receipt on ``pending_brief.video_presentation`` (with the presenting
    row's id filled in) and the storyboard block on that row. Returns the
    updated ProjectBrief, or None when nothing was owed / no row persisted.
    A rejection stop that presents the saved version's complete facts is a
    presentation row too; a degrade without that presentation never stamps.

    The first design records whether the user requested production.
    """
    if message is None or (read is None and not observed_ranges):
        return None
    from app.editing.service import (  # deferred: editing seam
        storyboard_block,
        video_presentation_receipt,
    )

    blocks = list(observed_ranges or [])
    if read is not None:
        final_block = storyboard_block(read)
        if final_block not in blocks:
            blocks.append(final_block)
    message.blocks = [
        *(block for block in message.blocks or [] if block.get("kind") != "video_storyboard"),
        *({**block, "presented_message_id": str(message.id)} for block in blocks),
    ]
    if read is None or (read.get("scrub") or {}).get("kind") == "range":
        return None

    receipt = video_presentation_receipt(read, review_hold=True)
    if production_requested and read["version"] == 1:
        receipt["production_invited"] = True
    for key in ("authorized_revision_message_id", "prior_presented_message_id", "prior_reviewed_output_id"):
        if read.get(key):
            receipt[key] = read[key]
    receipt["presented_message_id"] = str(message.id)
    stored = ProjectBrief.model_validate(project.pending_brief or {})
    updated = stored.model_copy(update={"video_presentation": receipt})
    project.pending_brief = updated.model_dump(mode="json")
    return updated


def asks_for_export(text: str) -> bool:
    if draft_only_request(text) or re.search(
        r"多少|多久|多长|如何|怎样|怎么|\b(?:how (?:much|long|do)|what|which|why|when)\b", text, re.I
    ):
        return False
    return bool(re.search(
        r"导出|交付|(?:成片|mp4).{0,8}(?:发给|发我)|(?:发给我|给我发).{0,8}(?:成片|mp4)|"
        r"\b(?:export|deliver|send.{0,30}mp4)\b", text, re.I
    ))


async def preceding_delivery(db, conversation_id, opening):
    """Read the reviewed delivery on the immediately preceding user turn."""
    from sqlalchemy import select

    if opening is None:
        return None
    prior = select(Message.id).where(
        Message.conversation_id == conversation_id, Message.role == "user",
        Message.seq < opening.seq,
    ).order_by(Message.seq.desc()).limit(1).scalar_subquery()
    receipt = await db.scalar(select(Message.intent).where(
        Message.conversation_id == conversation_id, Message.turn_id == prior,
        Message.intent.has_key("reviewed_version"), Message.intent.has_key("output_refs"),
    ).order_by(Message.seq.desc()).limit(1))
    if receipt and receipt["output_refs"]:
        return {**receipt["reviewed_version"], "output_id": receipt["output_refs"][0]}
    return None


def draft_only_request(text: str) -> bool:
    return bool(re.search(
        r"(?:只(?:要|需|看|出|做)|仅(?:需|要)?)(?:可编辑的?)?(?:初稿|草稿|分镜|预览)|"
        r"(?:不要|不用|无需|不需要|暂不|先不|别|不)(?:正式)?(?:导出|交付)|"
        r"\b(?:preview only|draft only|only (?:a |the )?(?:draft|preview)|no new media or export|(?:do not|don't|no) (?:formal )?(?:export|render|deliver))\b",
        text, re.I,
    ))


def requested_video_production(text: str) -> bool:
    """Recognize an explicit initial make request on a saved design turn."""
    if draft_only_request(text) or re.search(
        r"不(?:要|用)?(?:制作|渲染)|只(?:看|出|要|做)分镜|"
        r"\b(?:do not|don't|no)\s+(?:produce|production|render)|"
        r"\bstoryboard only\b|\b(?:make|create|produce)\s+(?:an?\s+)?(?:editable\s+)?storyboard\b",
        text, re.I,
    ):
        return False
    return bool(re.search(r"制作|做(?:一[个部条支只]|成片)|\b(?:make|produce|create)\b", text, re.I))


async def short_video_confirmation(db, project, conversation_id, text, pending):
    """Resolve a brief affirmation against the last visible confirmation."""
    from sqlalchemy import select

    from app.models.tables import Composition, ExportJob, Output

    if project is None or pending is not None or not re.fullmatch(
        r"(?:ok(?:ay)?|yes)[.!。！]?", text.strip(), re.I
    ):
        return None
    receipt = (project.pending_brief or {}).get("video_presentation") or {}
    if not receipt.get("production_invited"):
        return None
    presented = await db.get(Message, UUID(receipt["presented_message_id"]))
    if presented is None or presented.conversation_id != conversation_id:
        return None
    base_ref = {key: receipt[key] for key in ("composition_id", "composition_version_id", "content_digest")}
    target = {"base_ref": base_ref, "presented_message_id": str(presented.id)}
    work = await db.get(Composition, UUID(base_ref["composition_id"]))
    if work is None or work.origin_project_id != project.id:
        return None
    current = str(work.current_version_id) == base_ref["composition_version_id"]
    last = await db.scalar(
        select(Message).where(
            Message.conversation_id == conversation_id, Message.role == "assistant",
            Message.seq >= presented.seq, Message.intent["type"].as_string().is_distinct_from("interim_prose"),
        ).order_by(Message.seq.desc()).limit(1)
    )
    # An acknowledgement after export refers to the visible turn. An export
    # of the same version in another turn cannot answer a new question.
    if last is not None and last.turn_id:
        row = (await db.execute(
            select(ExportJob, Message).join(Message, Message.id == ExportJob.receipt_id).where(
                ExportJob.project_id == project.id,
                ExportJob.version_id == UUID(base_ref["composition_version_id"]),
                Message.conversation_id == conversation_id, Message.turn_id == last.turn_id,
            ).order_by(Message.seq.desc()).limit(1)
        )).first()
        if row is not None:
            job, tool = row
            delivery = None
            if job.status == "succeeded" and await db.get(Output, job.id) is not None:
                delivery = await db.scalar(select(Message).where(
                    Message.conversation_id == conversation_id, Message.turn_id == tool.turn_id,
                    Message.intent["reviewed_version"].contains(base_ref),
                    Message.intent["output_refs"].contains([str(job.id)]),
                ).order_by(Message.seq.desc()).limit(1))
            return {
                **target, "action": "existing_export", "export_job_id": str(job.id),
                "status": job.status, "media_result": (tool.intent or {}).get("media_result"),
                "output_refs": [str(job.id)] if delivery else [],
                "delivery_message_id": str(delivery.id) if delivery else None,
            }
    if last is None or last.id != presented.id:
        opening = await db.get(Message, last.turn_id) if last is not None and last.turn_id else None
        prior = ((opening.intent or {}).get("video_confirmation") or {}) if opening is not None else {}
        if prior.get("action") != "wait" or prior.get("presented_message_id") != str(presented.id):
            return None
    if not current:
        return {"action": "stale", **target}
    return {"action": "produce" if receipt.get("presentation_complete") else "wait", **target}
