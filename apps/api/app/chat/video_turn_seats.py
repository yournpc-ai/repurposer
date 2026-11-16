"""The video family's turn seats (ADR-145 phase B) — ONE implementation;
the plan path's and the chat path's runners both delegate here (the
codebase's two-path mirror stays thin instead of copying 100+ lines).

Layering: chat may import editing (the pure content services) and
tools/video (the LLM/capture orchestration). The write door commits on a
DEDICATED session — the turn's own long transaction never rides it; the
turn only carries the presentation receipt (pending_brief's
video_presentation slice) and the storyboard block on the presenting row.
"""

import json
import re
import time
import structlog
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID

from app.agents.tool_loop import TerminalRefusal, ToolObservation
from app.agents.working_drafts import (
    WorkingDraftRejected,
    WorkingDraftReviewed,
    WorkingDraftUpdated,
    exception_errors,
    record_working_draft_review,
    working_draft_arguments,
    working_draft_review_facts,
)
from app.editing.validators import ContentValidationError
from app.chat.activity_receipts import (
    component_receipt,
    VideoDraftReviewReceipt,
    music_search_receipt,
    music_selection_receipt,
    SkillReadReceipt,
    sfx_import_receipt,
    sfx_search_receipt,
    video_revision_receipt,
)
from app.models.schemas import (
    AnnotateNarrationArgs,
    BuiltInSkillReference,
    ExternalSkillReference,
    GetNarrationAlignmentArgs,
    ImportSfxArgs,
    PendingPlan,
    PrepareNarrationArgs,
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


class VideoTargetAmbiguityFeedback(str):
    def __new__(cls, message: str, *, candidates: list[dict[str, Any]], base_ref: dict[str, Any]):
        value = super().__new__(cls, message)
        value.candidates = candidates
        value.base_ref = base_ref
        return value


def bind_video_revision_base(params: Any, base_ref: dict[str, Any] | None) -> Any:
    if getattr(params, "base_ref", None) is not None or base_ref is None:
        return params
    from app.models.schemas import VideoVersionRef

    return params.model_copy(update={"base_ref": VideoVersionRef.model_validate(base_ref)})


def _sfx_display_title(title: str) -> str:
    """Model-facing title; the raw provider title stays persisted for audit."""
    return re.sub(r"\.[A-Za-z][A-Za-z0-9]{0,15}$", "", title)


_SFX_SOUND_EN = r"(?:sfx|sound(?:\s+effect)?s?|audio\s+cues?|click(?:\s+sound)?)"
_SFX_SOUND_ZH = r"(?:音效|声音|提示音|点击音)"
_SFX_STRONG_ACTION_EN = re.compile(
    rf"\b(?:search(?:\s+for)?|find|look\s+for|source|replace|swap|change)\b"
    rf"[^\n.!?]{{0,80}}\b{_SFX_SOUND_EN}\b",
    re.IGNORECASE,
)
_SFX_ADD_ACTION_EN = re.compile(
    rf"\badd\b[^\n.!?]{{0,80}}\b{_SFX_SOUND_EN}\b", re.IGNORECASE
)
_SFX_STRONG_ACTION_ZH = re.compile(
    rf"(?:搜索|搜寻|检索|查找|找|替换|更换|换掉|换成)"
    rf"[^。！？\n]{{0,32}}{_SFX_SOUND_ZH}"
    rf"|(?:把|将)[^。！？\n]{{0,32}}{_SFX_SOUND_ZH}[^。！？\n]{{0,16}}(?:替换|更换|换掉)"
)
_SFX_ADD_ACTION_ZH = re.compile(
    rf"(?:添加|新增|加入)[^。！？\n]{{0,32}}{_SFX_SOUND_ZH}"
)


def sfx_search_requested(user_text: str) -> bool:
    """Server-side admission for provider search, keyed to the current user words.

    Naming a template's already-fixed cue is not a request to search. Explicit
    search/replacement remains admissible; an add request is too unless the
    same message explicitly says the effect is fixed.
    """
    text = user_text.strip()
    if not text:
        return False
    if re.search(
        r"\b(?:do\s+not|don't|never|without)\s+(?:search|find|look\s+for|source)\b",
        text,
        re.IGNORECASE,
    ) or re.search(r"(?:不要|不用|禁止|无需|不需要|不)[^。！？\n]{0,12}(?:搜索|搜寻|检索|查找|找)", text):
        return False
    if _SFX_STRONG_ACTION_EN.search(text) or _SFX_STRONG_ACTION_ZH.search(text):
        return True
    has_fixed_declaration = bool(re.search(r"\bfixed\b|固定", text, re.IGNORECASE))
    return bool(
        (_SFX_ADD_ACTION_EN.search(text) or _SFX_ADD_ACTION_ZH.search(text))
        and not has_fixed_declaration
    )


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
        "Persisted audio candidate sets (internal references for a later selection turn):",
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
        Output.id == output_id, Project.user_id == project.user_id
    ))


async def video_target_hint(db, project, mentions=()):
    for mention in mentions or []:
        if mention.type != "output":
            continue
        row = await _owned_video_output(db, project, mention)
        if row is not None and row.composition_id is not None:
            return {"composition_id": str(row.composition_id)}
    return None


async def video_context_lines(
    db, project, mentions=(), *, skill: SkillReference | None = None,
    skill_ambiguity: list[str] | None = None,
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
            "Server-pinned Skill for this turn's FIRST design only: "
            + json.dumps(skill.model_dump(mode="json"), ensure_ascii=False)
        )
    if skill_ambiguity:
        lines.append(
            "The user's Skill name is ambiguous between "
            + ", ".join(skill_ambiguity)
            + "; ask which exact Skill/version they mean before designing."
        )
    # Assets, page bodies, frozen sources and complete compositions ride the
    # fresh shared project context, never a second stale identity-only list.
    receipt = (project.pending_brief or {}).get("video_presentation")
    if receipt:
        lines.append("Video currently under review: " + json.dumps(receipt, ensure_ascii=False))
    for mention in mentions or []:
        if mention.type == "asset":
            try:
                asset_id = UUID(str(mention.id))
            except ValueError:
                continue  # A staged local file has no server asset id yet.
            asset = await db.scalar(select(Asset).where(Asset.id == asset_id, Asset.user_id == project.user_id))
            if asset is not None:
                lines.append("Mentioned source material: " + json.dumps({"asset_id": str(asset.id),
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
            lines.append("Mentioned video output: " + json.dumps(payload, ensure_ascii=False))
    return lines


def _version_context_keys(read: dict) -> tuple[str, ...]:
    version_id, digest = read.get("composition_version_id"), read.get("content_digest")
    return (f"composition:{version_id}:{digest}",) if version_id and digest else ()


async def read_video_for_presentation(db, project, params):
    """Read the saved version and prepare an explicitly requested local Scrub."""
    from app.editing.service import video_version_read, format_storyboard_text
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
    project: Project,
    args: ReviewVideoArgs,
    on_report: Callable[[dict[str, Any]], None] | None = None,
) -> str | ToolObservation | TerminalRefusal:
    """Decode and review the exact Output; persist its advisory report."""

    import json
    from app.models.database import AsyncSessionLocal
    from app.tools.video.review import ReviewAttemptFailed, ReviewError, review_video

    try:
        async with AsyncSessionLocal() as video_db:
            report = await review_video(video_db, owner_id=project.user_id, args=args)
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
        return f"review_video rejected: {exc}"
    if on_report is not None:
        on_report(report)
    from app.chat.activity_receipts import video_review_receipt

    return ToolObservation(
        "Content review saved on the exact reviewed Output. These are the persisted report facts "
        "(advisory still-frame findings, not a delivery gate):\n"
        + json.dumps(report, ensure_ascii=False),
        receipt=video_review_receipt(report),
    )


async def video_proposal_guard(db, project, tasks, *, pending_read=None, production_intent=None, mentions=()):
    if not any(t.tool == "produce_video" for t in tasks):
        return None
    # Native tool loops occasionally serialize a nested object as JSON text.
    # Normalize that one bounded shape BEFORE any guard reads it; malformed
    # values become repair feedback, never a 500 or an implicit redesign.
    import json
    for task in tasks:
        if task.tool != "produce_video":
            continue
        params = dict(task.params or {})
        ref = params.get("version_ref")
        if isinstance(ref, str):
            try:
                ref = json.loads(ref)
            except (TypeError, ValueError):
                return "Video production held: version_ref must be the saved base_ref object, not opaque text. Re-read the version and relay its base_ref."
            if not isinstance(ref, dict):
                return "Video production held: version_ref must be the saved base_ref object. Re-read the version and relay its base_ref."
            task.params = {**params, "version_ref": ref}
    from app.tools.video.production import pin_video_production, latest_video_approval
    from app.editing.store import CompositionNotFound, PermissionDenied
    # A later revision may carry this turn's explicit "change and make".
    # It still waits for the creative overview to finish before auto Start.
    prior = (project.pending_brief or {}).get("video_presentation") or {}
    if len(tasks) == 1:
        # A new revision is not presented yet. Recover the presentation of
        # its actual base work, rather than the other work last shown in Chat.
        ref = ((pending_read or {}).get("previous_version_ref")
               or (tasks[0].params or {}).get("version_ref") or {})
        if prior.get("composition_version_id") != ref.get("composition_version_id"):
            from sqlalchemy import select
            from app.models.tables import Conversation
            shown = await db.scalar(select(Message).join(Conversation, Message.conversation_id == Conversation.id)
                .where(Conversation.project_id == project.id, Message.blocks.contains([
                    {"kind": "video_storyboard", "composition_version_id": ref.get("composition_version_id"), "presentation_complete": True}
                ])).order_by(Message.seq.desc()).limit(1))
            if shown is not None:
                block = next(b for b in shown.blocks if b.get("composition_version_id") == ref.get("composition_version_id"))
                prior = {**block, "presented_message_id": str(shown.id)}
                stored = PendingPlan.model_validate(project.pending_brief or {})
                project.pending_brief = stored.model_copy(update={"video_presentation": prior}).model_dump(mode="json")
            else:
                from app.models.tables import WorkflowRun
                previous = await db.scalar(select(WorkflowRun).where(
                    WorkflowRun.project_id == project.id,
                    WorkflowRun.context["version_ref"]["composition_version_id"].as_string() == ref.get("composition_version_id"),
                ).order_by(WorkflowRun.created_at.desc()).limit(1))
                proven = (previous.context or {}).get("video_presentation") if previous else None
                if proven and proven.get("presentation_complete"):
                    prior = proven
                    stored = PendingPlan.model_validate(project.pending_brief or {})
                    project.pending_brief = stored.model_copy(update={"video_presentation": prior}).model_dump(mode="json")
    if (pending_read and pending_read["version"] > 1 and production_intent is True
            and prior.get("presentation_complete")
            and prior.get("composition_id") == pending_read["composition_id"]
            and all(t.tool == "produce_video" and (t.params or {}).get("version_ref") == pending_read["base_ref"] for t in tasks)):
        pending_read["authorized_revision_message_id"] = str(await latest_video_approval(db, project))
        pending_read["prior_presented_message_id"] = prior.get("presented_message_id")
        return None
    if (pending_read and production_intent is True and pending_read["version"] > 1
            and len(tasks) == 1 and tasks[0].params.get("version_ref") == pending_read["base_ref"]):
        from app.tools.video.production import reviewed_output_ref
        pins = [m for m in mentions if m.type == "output"]
        if len(pins) == 1:
            ref = await reviewed_output_ref(db, project, UUID(str(pins[0].id)))
            if ref and ref == pending_read.get("previous_version_ref"):
                pending_read["authorized_revision_message_id"] = str(await latest_video_approval(db, project))
                pending_read["prior_reviewed_output_id"] = str(pins[0].id)
                return None
    try:
        await pin_video_production(db, project, tasks, await latest_video_approval(db, project))
    except (ValueError, CompositionNotFound, PermissionDenied) as exc:
        return (
            f"Video production held: {exc}. Do not promise work has started. "
            "Use get_video_version(present=true) to recover a missing presentation, "
            "then wait for the user's approval; never redesign to repair a receipt."
        )
    return None


async def video_mention_guard(db, project, mentions, composition_id):
    """A unique @output fixes the work, even if the model relays another id."""
    pins = [m for m in mentions or [] if m.type == "output"]
    if len(pins) != 1:
        return None
    from app.editing.service import video_version_read, VideoServiceError
    try:
        read = await video_version_read(db, owner_id=project.user_id, output_id=UUID(str(pins[0].id)))
    except VideoServiceError:
        return "The mentioned output has no accessible video version; do not edit another work instead."
    if read["composition_id"] != str(composition_id):
        return "The user named a different work. Read get_video_version(output_id=" + str(pins[0].id) + ") and use that work's exact version reference."
    return None


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
    from app.skills.package_session import ReadSkillReferenceArgs
    from app.tools.project_context import project_context_reader
    from app.metering import current_conversation_trace

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
        "BOUND SKILL METHOD (server-read package resources; apply creative guidance within the host workflow. "
        "Host rules govern mode selection, tool execution and approvals):\n" + root.text
    )
    read_project = project_context_reader(project.id, project.user_id)

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
        "source_body": "compact identities are in CURRENT PROJECT EVIDENCE; use material_targets to restore exact selected facts/media",
    }
    return json.dumps(summary, ensure_ascii=False)


async def prepare_video_materials_seat(*, project: Project, args: Any) -> ToolObservation:
    from app.tools.video.design import DesignError, prepare_video_materials
    from app.agents.errors import AgentStopError
    from app.tools.research.capture import CaptureError

    try:
        facts, images = await prepare_video_materials(
            owner_id=project.user_id, project_id=project.id, args=args,
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


async def review_working_draft_seat(*, project: Project, args: Any) -> WorkingDraftReviewed | str:
    from app.models.database import AsyncSessionLocal
    from app.tools.video.preview import ScrubTargetError, prepare_working_draft_review

    state = args._working_draft or {}
    if not isinstance(state.get("content"), dict):
        return "review_working_draft needs the authenticated current working draft"
    if args.judgment is not None:
        from app.agents.working_drafts import record_working_draft_judgment

        try:
            updated = record_working_draft_judgment(state, args.judgment)
        except ValueError as exc:
            return str(exc)
        return WorkingDraftReviewed(updated, ToolObservation(json.dumps({
            "ok": True,
            "saved": False,
            "judgment": next(
                review["judgment"] for review in updated["review"]["reviews"]
                if review["evidence_id"] == args.judgment.evidence_id
            ),
            "review": working_draft_review_facts(updated),
        }, ensure_ascii=False), context_lifetime="call",
            accepted_interim_prose=(
                args.judgment.summary if args.judgment.verdict == "issue" else None
            ),
        ))
    started = {
        "content": state["content"],
        "design": state.get("design") or {},
        "review": {
            **(state.get("review") or {}),
            "schema_version": 1,
            "started": True,
            "reviews": list((state.get("review") or {}).get("reviews") or []),
            "invalidated": list((state.get("review") or {}).get("invalidated") or []),
        },
    }
    try:
        async with AsyncSessionLocal() as db:
            evidence, media = await prepare_working_draft_review(
                db, owner_id=project.user_id, args=args,
            )
    except (ScrubTargetError, ValueError) as exc:
        return WorkingDraftReviewed(started, ToolObservation(json.dumps({
            "ok": False,
            "saved": False,
            "error": str(exc),
            "review": working_draft_review_facts(started),
        }, ensure_ascii=False), ok=False))
    updated = record_working_draft_review(state, evidence)
    evidence["evidence_id"] = updated["review"]["reviews"][-1]["evidence_id"]
    observation = evidence["observation"]
    receipt = VideoDraftReviewReceipt(
        evidence_id=evidence["evidence_id"],
        draft_digest=evidence["draft_ref"]["draft_digest"],
        content_digest=evidence["content_digest"],
        media_digest=observation["media_digest"],
        source_range_seconds=evidence["scope"]["source_range_seconds"],
        scene_ids=evidence["scope"]["scene_ids"],
        continuous=True,
    )
    return WorkingDraftReviewed(updated, ToolObservation(json.dumps({
        "ok": True,
        "saved": False,
        "evidence": evidence,
        "review": working_draft_review_facts(updated),
    }, ensure_ascii=False), images=media, receipt=receipt, context_lifetime="call"))


async def design_video_seat(
    *,
    project: Project,
    args: Any,
    request_id: str,
    skill: SkillReference | None = None,
    skill_ambiguity: list[str] | None = None,
    package_sessions: dict[str, Any] | None = None,
    user_text: str = "",
) -> tuple[dict[str, Any] | None, Any]:
    """Merge one draft write or save the assembled version through the write door."""

    from app.editing.edits import EditError  # deferred: write door
    from app.editing.service import format_storyboard_text  # deferred: editing seam
    from app.editing.store import (  # deferred: write door
        CandidateContentError,
        CompositionNotFound,
        PermissionDenied,
    )
    from app.tools.video.design import CandidateDesignError, DesignError, design_video  # deferred: tool seam
    from app.agents.errors import AgentStopError
    from app.providers.llm.base import LLMError

    if skill_ambiguity:
        return None, (
            "design_video held: the named Skill is ambiguous between "
            + ", ".join(skill_ambiguity)
            + ". Ask which exact Skill/version the user means; no version was designed."
        )
    if skill is not None and args.composition_id is not None:
        return None, (
            "design_video rejected: an explicit Skill binds only a new first version. "
            "Use revise_video with the existing version's base_ref; do not reload the Skill."
        )
    try:
        read = await design_video(
            owner_id=project.user_id,
            project_id=project.id,
            args=args,
            request_id=request_id,
            skill_reference=skill,
            skill_package=(
                package_sessions.get(skill.model_dump_json())
                if package_sessions is not None and skill is not None else None
            ),
            request_context={
                "user_text": user_text,
                "brief": getattr(project, "pending_brief", None),
            },
        )
        if isinstance(read, WorkingDraftUpdated):
            return None, read
    except (AgentStopError, LLMError) as exc:
        facts = getattr(exc, "facts", {"stage": "design", "version_saved": False, "run_started": False})
        return None, ToolObservation(
            "DESIGN STOPPED: " + str(exc) + "\n" + json.dumps(facts, ensure_ascii=False)
            + "\nExplain this failure and the completed stages honestly. No new version was saved and no production started. "
            "Do not retry design_video or start production in this turn. "
            "No production does NOT mean zero usage or zero cost: model calls have already occurred. "
            "Report only the known stage facts; do not claim all materials passed or invent a billing amount. "
            "A source/view binding mismatch is an assembly error, not evidence that a captured element is missing. "
            "Preserve preview_checks/media_files facts: a Skill shot preview is separate from native presets; "
            "do not claim a successfully read Skill preview is absent merely because no native preset matches. "
            "Use plain user-facing language about completed work, the obstacle and saved/production status. "
            "Do not dump schema fields, internal IDs, counters or stack traces. Do not tell the user that "
            "repeating the same request will repair this failure; do not ask them to resend the production request, and do not invent new preference questions.",
            ok=False,
        )
    except (CompositionNotFound, PermissionDenied):
        return None, (
            "that video work does not exist in this project — never "
            "retry with the same reference; if the user named an older "
            "work, say honestly it is gone"
        )
    except CandidateContentError as exc:
        return None, WorkingDraftRejected(
            str(exc), exception_errors(exc), working_draft_arguments(args, exc.content)
        )
    except CandidateDesignError as exc:
        content = exc.working_content or (getattr(args, "_working_draft", None) or {}).get("content")
        if not isinstance(content, dict):
            return None, f"design_video rejected: {exc}"
        return None, WorkingDraftRejected(
            str(exc), exception_errors(exc), working_draft_arguments(args, content)
        )
    except (ContentValidationError, EditError) as exc:
        content = (getattr(args, "_working_draft", None) or {}).get("content")
        if isinstance(content, dict):
            return None, WorkingDraftRejected(
                str(exc), exception_errors(exc), working_draft_arguments(args, content)
            )
        return None, f"design_video rejected: {exc}"
    except (DesignError, ValueError) as exc:
        return None, f"design_video rejected: {exc}"
    from app.models.database import AsyncSessionLocal
    from app.tools.video.programs import generator_preview_images

    if args.scrub is not None:
        from app.tools.video.preview import ScrubTargetError, prepare_saved_video_scrub
        try:
            async with AsyncSessionLocal() as preview_db:
                read = await prepare_saved_video_scrub(
                    preview_db, read, owner_id=project.user_id, target=args.scrub
                )
        except ScrubTargetError as exc:
            read["scrub_rejected"] = str(exc)
    redraft = read.get("change_set") is not None
    preview = read.get("video_preview") or {}
    scope = preview.get("scope") or {}
    scrub_facts = ""
    if read.get("scrub_rejected"):
        scrub_facts = "\nLOCAL SCRUB NOT PROVIDED: " + read["scrub_rejected"]
    if preview:
        scrub_facts = (
            "\nLOCAL SCRUB (not an Output or a complete-video preview; "
            "an isolated Object does not prove scene layout, occlusion or joins):\n"
            + json.dumps({
                "status": preview.get("status"),
                "reason": preview.get("reason"),
                "scope": scope,
                "generator_previews": read.get("generator_previews") or [],
            }, ensure_ascii=False)
        )
    return read, ToolObservation(
        f"Video version {read['version']} saved "
        f"(composition {read['composition_id']}; "
        f"{'the earlier versions stay in history' if redraft else 'first version'}; "
        "no plan docked, no run started, nothing has been produced)."
        + scrub_facts
        + "\nSAVED VERSION (execution truth):\n"
        + format_storyboard_text(read),
        images=tuple(await generator_preview_images(
            read, clip_ids=set(scope.get("clip_ids") or [])
        )) if scope else (),
        receipt=component_receipt(read),
        context_keys=_version_context_keys(read),
    )


async def revise_video_seat(
    *,
    project: Project,
    args: Any,
    request_id: str,
    conversation_id: UUID | None = None,
    user_text: str = "",
    pending_question: Any = None,
) -> tuple[dict[str, Any] | None, Any]:
    """Revise an exact saved version through complete entities or one bounded action."""

    from app.agents.candidate_correction import CandidateRejected
    from app.editing.edits import EditError
    from app.editing.revisions import RevisionInputError, RevisionTargetAmbiguityError
    from app.editing.validators import ContentValidationError
    from app.editing.presets import PresetError
    from app.editing.service import (  # deferred: editing seam
        VideoServiceError,
        format_revision_text,
        revise_video,
    )
    from app.editing.store import (  # deferred: write door
        CandidateContentError,
        CompositionNotFound,
        ContentDigestMismatch,
        PermissionDenied,
        StaleBase,
    )
    from app.models.database import AsyncSessionLocal  # deferred: db seam
    from app.tools.video.programs import generator_preview_images

    from app.models.schemas import ReviseVideoActionArgs

    if isinstance(args, ReviseVideoActionArgs):
        args.bind_request_context(user_text=user_text, pending_question=pending_question)

    try:
        async with AsyncSessionLocal() as video_db:
            read = await revise_video(
                video_db,
                owner_id=project.user_id,
                args=args,
                request_id=request_id,
            )
            if getattr(args, "scrub", None) is not None:
                from app.tools.video.preview import (
                    ScrubTargetError,
                    prepare_saved_video_scrub,
                    revision_scrub_affected,
                )
                if not revision_scrub_affected(read, args.scrub):
                    read["scrub_rejected"] = "the Scrub target is outside this revision's affected scope"
                else:
                    try:
                        read = await prepare_saved_video_scrub(
                            video_db, read, owner_id=project.user_id, target=args.scrub
                        )
                    except ScrubTargetError as exc:
                        read["scrub_rejected"] = str(exc)
    except RevisionTargetAmbiguityError as exc:
        return None, VideoTargetAmbiguityFeedback(
            "revise_video needs clarification before any write: "
            + str(exc)
            + ". Candidate facts from the current base version: "
            + json.dumps(exc.candidates, ensure_ascii=False)
            + ". Current base_ref: "
            + json.dumps(args.base_ref.model_dump(mode="json"), ensure_ascii=False)
            + ". Call ask_user with one question and options grounded in these candidates; "
            "do not answer in prose, guess a target, or retry a write before the user answers.",
            candidates=exc.candidates,
            base_ref=args.base_ref.model_dump(mode="json"),
        )
    except RevisionInputError as exc:
        return None, CandidateRejected(str(exc), exception_errors(exc))
    except (StaleBase, ContentDigestMismatch, CompositionNotFound, PermissionDenied) as exc:
        return None, (
            "revise_video did not write: "
            + str(exc)
            + ". Re-read the current version with get_video_version and create a new candidate from its base_ref."
        )
    except (CandidateContentError, ContentValidationError, EditError) as exc:
        return None, f"revise_video rejected: {exc}"
    except (PresetError, VideoServiceError) as exc:
        return None, f"revise_video rejected: {exc}"
    except ValueError as exc:
        return None, f"revise_video rejected: {exc}"
    read["previous_version_ref"] = args.base_ref.model_dump(mode="json")
    changed_clip_ids = {
        str(item.get("clip_id"))
        for group in ("added", "updated")
        for item in (read.get("change_set") or {}).get("clips", {}).get(group, [])
    }
    generator_clip_ids = {
        str(clip.get("clip_id"))
        for scene in read.get("storyboard", {}).get("scenes", [])
        for clip in scene.get("clips", [])
        if clip.get("clip_id") in changed_clip_ids and clip.get("object_kind") == "generator"
    }
    preview = read.get("video_preview") or {}
    scope = preview.get("scope") or {}
    scrub_facts = ""
    if read.get("scrub_rejected"):
        scrub_facts = "\nLOCAL SCRUB NOT PROVIDED: " + read["scrub_rejected"]
    if preview:
        scrub_facts = (
            "\nLOCAL SCRUB (not an Output or a complete-video preview; "
            "an isolated Object does not prove scene layout, occlusion or joins):\n"
            + json.dumps({
                "status": preview.get("status"),
                "reason": preview.get("reason"),
                "scope": scope,
                "generator_previews": read.get("generator_previews") or [],
            }, ensure_ascii=False)
        )
    return read, ToolObservation(
        f"World facts: video version {read['version']} is saved as a revision; "
        "no run started and nothing has been produced. The saved version "
        "reference rides the presenting reply. Follow the Video works law "
        "for the user-facing natural-language handoff. These saved facts contain the system-computed "
        "field-level delta and the reference needed by the next tool:\n"
        + format_revision_text(read)
        + scrub_facts,
        images=tuple(await generator_preview_images(
            read, clip_ids=set(scope.get("clip_ids") or [])
        )) if scope else (),
        context_keys=_version_context_keys(read),
        receipt=video_revision_receipt(
            read,
            component_clip_ids=generator_clip_ids,
        ),
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
        "World facts: 2–4 real native Preset previews were emitted; no CompositionVersion, "
        "Run, production intent or selection was created. The cards own playback. Close "
        "with a concise comparison and invite an ordinary ordinal choice.\n"
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

    if not sfx_search_requested(user_text):
        return ToolObservation(
            "search_sfx admission rejected: the current user message does not "
            "explicitly ask to find, add or replace a sound effect; no provider "
            "search ran and no candidates were emitted.",
            ok=False,
        )
    import json
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
        "World facts: the candidates were emitted; no asset or video version was written. "
        "The response facts are the candidate count, display titles and durations. "
        "The candidate cards provide actual playback for the user to audition and choose "
        "by ordinal; this search observation contains no listening result.\n"
        + json.dumps(selection_facts, ensure_ascii=False),
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
        "World facts: the selected MP3 is a completed audio asset with this immutable "
        "SourceSnapshot; no CompositionVersion changed. Use revise_video with a complete audio Clip (and its Track when adding a new Track).\n"
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
        "World facts: local Music candidates were emitted; no asset, CompositionVersion "
        "or Run was written. The cards provide actual playback for a later ordinal choice. "
        "This observation contains no listening result.\n"
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
        "World facts: the persisted local Music choice is resolved; no asset was imported, "
        "no CompositionVersion changed and no Run started. prepare_video_materials freezes "
        "this music_id; revise_video owns its music-track placement.\n"
        + json.dumps(selection_facts, ensure_ascii=False),
        receipt=music_selection_receipt(
            selection_facts,
            candidate_set_id=args.candidate_set_id,
            member_index=args.member_index,
        ),
    )


async def prepare_narration_seat(
    *, project: Project | None, args: PrepareNarrationArgs, mentions=()
) -> str | ToolObservation:
    if project is None:
        return "narration preparation needs a project context"
    from app.models.database import AsyncSessionLocal
    from app.tools.video.alignment_store import request_alignment, wait_for_alignment

    try:
        mentions = mentions or ()
        if args.audio_asset_id is not None:
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
                        "prepare_narration requires the user's explicit @asset reference for "
                        "this AUDIO recording; no alignment was requested"
                    )
                snapshot = await snapshot_audio_asset(db, asset, owner_id=project.user_id)
                await db.commit()
                snapshot_id = snapshot.id
        else:
            # A cache probe stays read-only. Missing audio is prepared only by
            # the ordinary presented/authorized narration-only Run scope.
            from app.editing.schemas import SpeechObject
            from app.tools.video.narration_store import peek_original
            from app.tools.video.preparation import snapshot_narration_original

            speech = SpeechObject(
                kind="speech",
                object_id="obj_prepare_narration",
                text=args.text,
                voice_id=args.voice_id,
                language=args.language,
            )
            original = await peek_original(project.user_id, speech)
            if original is None:
                return (
                    "No fixed VideoNarration original exists for this exact script, voice "
                    "and language, so no alignment was requested. For fresh synthesis, "
                    "present exactly one prepare_narration task with the same text, voice_id "
                    "and language through the current turn's ordinary plan tool "
                    "(present_plan or propose_tasks), carrying the user's actual "
                    "production_intent. The plan/Start machinery owns quote and spending "
                    "authorization; produce_video is not a substitute. After the plan is "
                    "presented or its Run starts, close this turn and do not poll synthesis"
                )
            async with AsyncSessionLocal() as db:
                _, snapshot = await snapshot_narration_original(
                    db, project, text=args.text, original=original
                )
                await db.commit()
                snapshot_id = snapshot.id
        requested = await request_alignment(
            owner_id=project.user_id, audio_snapshot_id=snapshot_id, text=args.text
        )
        read = await wait_for_alignment(
            owner_id=project.user_id, alignment_id=UUID(requested["alignment_id"])
        )
    except (ValueError, PermissionError) as exc:
        return f"prepare_narration rejected: {exc}"
    return ToolObservation(json.dumps(read, ensure_ascii=False))


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
    *, production_requested: bool = False,
) -> PendingPlan | None:
    """The presentation association (ADR-145 phase B; the film stamp's
    sibling): fires from a runner's finish when a video design/revision
    beat this turn is owed its presentation and a TERMINAL speech row
    actually persisted. Two writes ride the turn's one transaction: the
    receipt on ``pending_brief.video_presentation`` (with the presenting
    row's id filled in) and the storyboard block on that row. Returns the
    updated PendingPlan, or None when nothing was owed / no row persisted.
    A rejection stop that presents the saved version's complete facts is a
    presentation row too; a degrade without that presentation never stamps.

    The first design records whether the user requested production.
    """
    if read is None or message is None:
        return None
    from app.editing.service import (  # deferred: editing seam
        storyboard_block,
        video_presentation_receipt,
    )

    receipt = video_presentation_receipt(read, review_hold=True)
    if production_requested and read["version"] == 1:
        receipt["production_invited"] = True
    for key in ("authorized_revision_message_id", "prior_presented_message_id", "prior_reviewed_output_id"):
        if read.get(key):
            receipt[key] = read[key]
    receipt["presented_message_id"] = str(message.id)
    stored = PendingPlan.model_validate(project.pending_brief or {})
    updated = stored.model_copy(update={"video_presentation": receipt})
    project.pending_brief = updated.model_dump(mode="json")
    message.blocks = [{**storyboard_block(read), "presented_message_id": str(message.id)}]
    return updated


def requested_video_production(text: str) -> bool:
    """Recognize an explicit initial make request on a saved design turn."""
    if re.search(
        r"不(?:要|用)?(?:制作|渲染)|只(?:看|出|要|做)分镜|"
        r"\b(?:do not|don't|no)\s+(?:produce|production|render)|"
        r"\bstoryboard only\b|\b(?:make|create|produce)\s+(?:an?\s+)?(?:editable\s+)?storyboard\b",
        text, re.I,
    ):
        return False
    return bool(re.search(r"制作|做(?:一[个部条支]|成片)|\b(?:make|produce|create)\b", text, re.I))


def confirmed_video_task(confirmation: dict):
    from app.models.schemas import TaskItem

    return TaskItem(tool="produce_video", params={"version_ref": confirmation["base_ref"]})


async def short_video_confirmation(db, project, conversation_id, text, pending):
    """Resolve a brief affirmation against the last visible confirmation."""
    from sqlalchemy import select
    from app.models.tables import Composition, WorkflowRun
    from app.tools.video.production import is_short_video_affirmation

    if project is None or not is_short_video_affirmation(text):
        return None

    async def already_started(run, target):
        delivery = await db.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.intent["trigger"].astext == "run_completed",
                Message.intent["ref"].astext == str(run.id),
            ).order_by(Message.seq.desc()).limit(1)
        )
        delivery_intent = (delivery.intent or {}) if delivery is not None else {}
        if delivery is None and run.status.value == "completed":
            from app.pipeline.trigger_events import fire_trigger

            fire_trigger(project.id, "run_completed", str(run.id))
        return {
            "action": "already_started",
            **target,
            "run_id": str(run.id),
            "run_status": run.status.value,
            "output_refs": delivery_intent.get("output_refs") or [],
            "delivery_message_id": str(delivery.id) if delivery is not None else None,
        }

    receipt = (project.pending_brief or {}).get("video_presentation") or {}
    ref = {key: receipt.get(key) for key in ("composition_id", "composition_version_id", "content_digest")}
    if all(ref.values()):
        run = await db.scalar(
            select(WorkflowRun).where(
                WorkflowRun.project_id == project.id,
                WorkflowRun.context["version_ref"]["composition_version_id"].as_string()
                == ref["composition_version_id"],
            ).order_by(WorkflowRun.created_at.desc()).limit(1)
        )
        if run is not None and (run.context or {}).get("version_ref") == ref:
            return await already_started(run, {
                "base_ref": ref,
                "presented_message_id": receipt.get("presented_message_id"),
            })
    if not receipt.get("production_invited"):
        if pending is not None:
            return None
        last_run = await db.scalar(
            select(WorkflowRun).where(
                WorkflowRun.project_id == project.id,
                WorkflowRun.context["version_ref"]["composition_version_id"].as_string().is_not(None),
            ).order_by(WorkflowRun.created_at.desc()).limit(1)
        )
        if last_run is not None:
            return await already_started(last_run, {"base_ref": last_run.context["version_ref"]})
        return None
    presented = await db.get(Message, UUID(receipt["presented_message_id"]))
    if presented is None or presented.conversation_id != conversation_id:
        return None
    base_ref = {key: receipt[key] for key in ("composition_id", "composition_version_id", "content_digest")}
    target = {"base_ref": base_ref, "presented_message_id": str(presented.id)}
    work = await db.get(Composition, UUID(base_ref["composition_id"]))
    current = work is not None and str(work.current_version_id) == base_ref["composition_version_id"]
    if pending is not None:
        tasks = (pending.intent or {}).get("tasks") or []
        if ((pending.question or {}).get("kind") == "task_book"
                and receipt.get("presentation_complete")
                and len(tasks) == 1 and tasks[0].get("tool") == "produce_video"
                and (tasks[0].get("params") or {}).get("version_ref") == base_ref):
            return {"action": "start" if current else "stale", "quote_message_id": str(pending.id), **target}
        return None
    run = await db.scalar(
        select(WorkflowRun).where(
            WorkflowRun.project_id == project.id,
            WorkflowRun.context["video_presentation"]["presented_message_id"].as_string() == str(presented.id),
        ).limit(1)
    )
    if run is not None:
        return await already_started(run, target)
    last = await db.scalar(
        select(Message).where(
            Message.conversation_id == conversation_id, Message.role == "assistant",
            Message.seq >= presented.seq, Message.intent["type"].as_string().is_distinct_from("interim_prose"),
        ).order_by(Message.seq.desc()).limit(1)
    )
    if last is None or last.id != presented.id:
        opening = await db.get(Message, last.turn_id) if last is not None and last.turn_id else None
        prior = ((opening.intent or {}).get("video_confirmation") or {}) if opening is not None else {}
        if prior.get("action") != "wait" or prior.get("presented_message_id") != str(presented.id):
            return None
    if not current:
        return {"action": "stale", **target}
    return {"action": "produce" if receipt.get("presentation_complete") else "wait", **target}
