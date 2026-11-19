"""Chat continuation for a staged, explicitly requested video preparation."""

import json
from dataclasses import replace
from uuid import UUID

from sqlalchemy import select

from app.agents.candidate_correction import RestoredCandidate
from app.agents.tool_loop import ToolObservation
from app.models.schemas import PresentPlanArgs, TaskItem
from app.models.tables import Message, WorkflowRun
from app.tools.video.visual_assets import current_scene_assets

IMAGE_TOOLS = {
    "ask_user", "answer", "read_conversation_context", "prepare_video_materials", "capture_web",
    "get_understanding", "get_web_page", "get_asset", "list_project_media",
    "list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview",
    "design_video", "prepare_visual_assets",
}
AUDIO_TOOLS = (IMAGE_TOOLS - {"prepare_visual_assets"}) | {
    "prepare_narration", "get_narration_alignment", "annotate_narration", "prepare_music",
}
PREPARATION_TOOLS = {"prepare_visual_assets", "prepare_narration", "prepare_music"}


class MediaDraftUnavailable(ValueError):
    """A settled preparation cannot continue against the authorized draft."""


def initial_media_journey(opening: Message | None) -> dict | None:
    from app.chat.readiness import infer_task_kind
    from app.chat.video_turn_seats import requested_video_production

    if opening is None or opening.role != "user":
        return None
    text = opening.content or ""
    if infer_task_kind(text) != "website_promo" or not requested_video_production(text):
        return None
    return {"opening_id": str(opening.id)}


async def visual_results(db, project_id: UUID, opening_id: str, draft_id: str | None = None) -> list[dict]:
    from app.models.schemas import WorkflowStatus

    statement = select(WorkflowRun.context).where(
        WorkflowRun.project_id == project_id,
        WorkflowRun.status == WorkflowStatus.COMPLETED,
        WorkflowRun.context["visual_asset_preparation"].is_not(None),
    )
    contexts = (await db.scalars(statement.order_by(WorkflowRun.created_at, WorkflowRun.id))).all()
    reusable, local = [], []
    for context in contexts:
        prep = context.get("visual_asset_preparation") or {}
        reference = (prep.get("request") or {}).get("draft_ref") or {}
        result = prep.get("result") or {}
        assets = result.get("assets") or []
        if (context.get("media_journey") or {}).get("opening_id") == opening_id and (
            draft_id is None or reference.get("draft_id") == draft_id
        ):
            local.extend(assets)
            local.extend(result.get("failures") or [])
        else:
            # A matching approved request can be reused across drafts. Its
            # attempts and failures do not spend this storyboard's retries.
            reusable.extend(
                {**asset, "cache_hit": True} for asset in assets
                if (asset.get("content_review") or {}).get("status") in {"pass", "advisory"}
            )
    return [*reusable, *local]


def media_actions(draft: dict | None, results: list[dict]) -> dict:
    from app.tools.video.media_analysis import image_reviewer_version
    from app.tools.video.visual_assets import VISUAL_ASSET_RUNNER_VERSION, ControlledSVGSource

    draft = draft or {}
    specs = current_scene_assets(draft)
    planned = {scene["scene_id"] for scene in (draft.get("content") or {}).get("scenes") or []}
    latest = {item["request_digest"]: item for item in results}
    missing, unavailable, repair, blocked = [], [], [], []
    failures, unknown = [], []
    attempts: dict[str, set[tuple[str, str | None]]] = {}
    for item in results:
        if not item.get("cache_hit"):
            execution = item.get("execution") or {}
            attempts.setdefault(item["scene_id"], set()).add((
                item["request_digest"], execution.get("run_id") or item.get("execution_id"),
            ))
        if item.get("code") == "outcome_unknown":
            unknown.append(item["scene_id"])
    for spec in specs:
        item = latest.get(spec.request_digest(), {})
        provenance = item.get("provenance") or {}
        review = item.get("content_review") or {}
        attempt_count = len(attempts.get(spec.scene_id, set()))
        if (
            spec.scene_id in unknown and spec.source.kind == "minimax_image"
            and (not item or item.get("code"))
        ):
            if attempt_count >= 2:
                blocked.append(spec.scene_id)
            else:
                repair.append(spec.scene_id)
            failures.append({
                "scene_id": spec.scene_id, "code": "outcome_unknown",
                "detail": "Reuse an available fixed result or switch this scene to a local source.",
            })
        elif item.get("code"):
            failures.append({
                "scene_id": spec.scene_id, "code": item["code"], "detail": item["detail"],
            })
            if attempt_count >= 2:
                blocked.append(spec.scene_id)
            elif item["code"] == "invalid_svg":
                repair.append(spec.scene_id)
            else:
                missing.append(spec.scene_id)
        elif not item and attempt_count >= 2:
            blocked.append(spec.scene_id)
        elif not item or (
            isinstance(spec.source, ControlledSVGSource)
            and provenance.get("runner_version") != VISUAL_ASSET_RUNNER_VERSION
        ):
            missing.append(spec.scene_id)
        elif review.get("reviewer_version") != image_reviewer_version(spec.source.kind):
            missing.append(spec.scene_id)
        elif review.get("status") == "unavailable" and not item.get("review_retry_of"):
            unavailable.append(spec.scene_id)
        elif review.get("status") == "fail" and attempt_count < 2:
            repair.append(spec.scene_id)
            failures.append({
                "scene_id": spec.scene_id, "code": "content_review_failed",
                "detail": review.get("summary") or "The fixed image failed content review.",
            })
        elif review.get("status") not in {"pass", "advisory"}:
            blocked.append(spec.scene_id)
    ready = bool(planned) and planned == {spec.scene_id for spec in specs} and not (
        missing or unavailable or repair or blocked
    )
    phase = "images"
    if blocked:
        phase = "images_blocked"
    elif ready:
        phase = "audio"
    return {
        "phase": phase,
        "approved_images": [
            {
                "scene_id": spec.scene_id,
                "snapshot": latest[spec.request_digest()].get("snapshot"),
                "review_status": latest[spec.request_digest()]["content_review"]["status"],
            }
            for spec in specs if ready
        ],
        "blocked_scene_ids": blocked,
        "missing_scene_ids": missing,
        "review_retry_scene_ids": unavailable,
        "repair_scene_ids": repair,
        "scene_failures": failures,
    }


def audio_timing_issue(draft: dict) -> str | None:
    from app.agents.working_drafts import working_draft_review_facts
    from app.tools.video.narration_draft import (
        assert_narration_ready_for_score,
        current_narration_facts,
    )

    scenes = working_draft_review_facts(draft)["scenes"]
    unfilled = [scene["scene_id"] for scene in scenes if not scene["clip_ids"]]
    if unfilled:
        return "Author the planned scenes with their narration: " + ", ".join(unfilled)
    try:
        assert_narration_ready_for_score(draft)
        if not current_narration_facts(draft):
            return "Author and prepare the requested narration on the existing Scenes"
    except ValueError as exc:
        return str(exc)
    return None


def allowed_media_tools(phase: str) -> set[str]:
    if phase == "images_blocked":
        return {"answer"}
    return AUDIO_TOOLS if phase == "audio" else IMAGE_TOOLS


def media_write_rejection(phase: str, name: str, params) -> str | None:
    if name not in allowed_media_tools(phase):
        return f"This preparation is at {phase}. Use only the available actions for that phase."
    if name == "prepare_narration" and (
        getattr(params, "draft_ref", None) is None or not getattr(params, "scene_id", None)
    ):
        return "Prepare narration for an exact current draft_ref and scene_id."
    if name == "design_video" and phase == "audio" and any(
        getattr(params, field, None) for field in ("scene_plan", "scene_assets")
    ):
        return "Continue the existing storyboard from its draft_ref and approved pictures."
    if name == "design_video" and (
        getattr(params, "save", False)
        or (phase == "images" and any(
            getattr(params, field, None) for field in
            ("scene", "scene_id", "tracks", "objects", "clips",
             "narration_update", "music_snapshot_id")
        ))
    ):
        return (
            "The current preparation does not save a Composition. During images, "
            "write scene_plan and scene_assets only, then prepare and review the images."
        )
    return None


def media_task_from_observation(name: str, observation: ToolObservation) -> TaskItem | None:
    if name not in PREPARATION_TOOLS or not observation.ok:
        return None
    result = json.loads(observation.text)
    if result.get("cache") != "miss":
        return None
    task = TaskItem.model_validate(result["plan_task"])
    if task.tool != name:
        raise ValueError("Media preparation returned a different task")
    return task


async def dock_media_observation(
    turn, name: str, observation: ToolObservation, *, working_draft=None
) -> ToolObservation:
    if name in {"prepare_narration", "prepare_music"} and observation.ok:
        cached = json.loads(observation.text)
        if name == "prepare_music":
            if not turn.media_state.get("audio_timing_ready"):
                return replace(
                    observation, ok=False,
                    text="Finish the draft scenes and confirm READY narration timing before music.",
                )
        if cached.get("cache") == "hit":
            from app.tools.video.audio_playback import record_prepared_audio

            role = "music" if name == "prepare_music" else "narration"
            message = await record_prepared_audio(
                turn.db, turn.project, turn.conversation_id, turn.media_journey, role,
                cached.get("result") or cached, cached, working_draft=working_draft,
            )
            state = message.intent["media_journey"]["state"]
            if state in {"complete", "blocked"}:
                turn.outcome = (message, None, turn.settled_pending, [])
                # The score's full measured result reaches the next model call
                # before folding. Only its closing answer is allowed after this.
                if state == "complete":
                    turn.media_score_delivered = True
                    return observation
                return replace(observation, ok=False, text=message.content, stop_after_observation=True)
    if name == "prepare_visual_assets" and observation.ok:
        result = json.loads(observation.text)
        if result.get("cache") == "hit":
            turn.media_visual_results.extend(result.get("assets", []))
    task = media_task_from_observation(name, observation)
    if task is None:
        return observation
    if name == "prepare_visual_assets":
        unknown = {
            item["scene_id"] for item in turn.media_state.get("scene_failures", [])
            if item["code"] == "outcome_unknown"
        }
        if unknown.intersection(task.params["scene_ids"]):
            from app.tools.video.params import PrepareVisualAssetsParams
            from app.tools.video.production import resolve_visual_asset_selection
            from app.tools.video.visual_assets import has_fixed_visual_source

            try:
                selected = await resolve_visual_asset_selection(
                    turn.db, turn.project, PrepareVisualAssetsParams.model_validate(task.params),
                )
                for spec in selected:
                    if spec.scene_id in unknown and not await has_fixed_visual_source(
                        owner_id=turn.project.user_id, project_id=turn.project.id, spec=spec,
                    ):
                        raise ValueError("No fixed result for the unresolved provider request")
            except ValueError:
                return replace(
                    observation, ok=False,
                    text="A prior image request is unresolved. Use a local source for that scene.",
                )
    if name == "prepare_narration":
        # The loop validates every call in this provider response before starting any recording.
        return observation
    return await _dock_tasks(turn, [task], observation, working_draft)


async def finish_narration_batch(turn, observations):
    from app.agents.working_drafts import working_draft_review_facts
    from app.tools.video.narration_draft import current_narration_facts

    reference = observations[0][0].draft_ref
    if any(params.draft_ref != reference for params, _ in observations):
        return ToolObservation("Use one current draft_ref for the entire recording batch.", ok=False)
    scene_ids = [params.scene_id for params, _ in observations]
    if len(set(scene_ids)) != len(scene_ids):
        return ToolObservation("A recording batch must name each scene once.", ok=False)
    tasks = [task for _, observation in observations
             if (task := media_task_from_observation("prepare_narration", observation)) is not None]
    draft = observations[0][0]._working_draft
    scenes = working_draft_review_facts(draft)["scenes"]
    unfilled = [s["scene_id"] for s in scenes if not s["clip_ids"]]
    if unfilled:
        return ToolObservation(f"Finish authoring the planned scenes before recording: {', '.join(unfilled)}.", ok=False)
    ready = {fact["scene_id"] for fact in current_narration_facts(draft)}
    required = {
        clip["scene_id"] for track in draft["content"]["timeline"]["tracks"] for clip in track["clips"]
        if (clip.get("object") or {}).get("kind") == "speech" and not clip["object"].get("alignment")
    }
    missing = required.difference(scene_ids, ready)
    if missing:
        return ToolObservation(
            f"Include all pending narrations in one tool_calls array. Missing: {', '.join(sorted(missing))}.",
            ok=False,
        )
    if not tasks:
        return None
    previous = await turn.db.scalars(select(WorkflowRun.context).where(
        WorkflowRun.project_id == turn.project.id,
        WorkflowRun.context["media_journey"]["opening_id"].as_string() == turn.media_journey["opening_id"],
    ))
    attempts = {}
    for context in previous.all():
        preparation = (context or {}).get("narration_preparation") or {}
        for part in preparation.get("scenes") or [preparation]:
            scene = (part.get("request") or {}).get("scene_id")
            attempts[scene] = attempts.get(scene, 0) + 1
    limited = [task.params["scene_id"] for task in tasks if attempts.get(task.params["scene_id"], 0) >= 2]
    if limited:
        return ToolObservation(f"Narration retry limit reached for {', '.join(limited)}.", ok=False)
    order = [s["scene_id"] for s in draft["content"]["scenes"]]
    tasks.sort(key=lambda task: order.index(task.params["scene_id"]))
    return await _dock_tasks(turn, tasks, observations[0][1], draft)


async def _dock_tasks(turn, tasks, observation, draft):
    name = tasks[0].tool
    zh = str(turn.project.language or "").startswith("zh")
    labels = {
        "prepare_visual_assets": ("分镜图片准备", "Scene image preparation"),
        "prepare_narration": ("分镜旁白准备", "Scene narration preparation"),
        "prepare_music": ("电子配乐准备", "Electronic music preparation"),
    }
    label = labels[name][0 if zh else 1]
    rejection = await turn._present_plan(
        PresentPlanArgs(tasks=tasks, name=label, production_intent=True),
        label,
    )
    if rejection:
        turn.media_start_rejections += 1
        turn.media_start_blocker = rejection
        return replace(
            observation, ok=False, text=f"Preparation could not start: {rejection}",
            stop_after_observation=turn.media_start_rejections >= 2,
        )
    if turn.outcome:
        plan_message, run_id = turn.outcome[:2]
        scenes = [scene["scene_id"] for scene in ((draft or {}).get("content") or {}).get("scenes") or []]
        if run_id is not None:
            run = await turn.db.get(WorkflowRun, run_id)
            run.context = {**run.context, "media_journey": turn.media_journey}
        if plan_message is not None:
            plan_message.intent = {
                **(plan_message.intent or {}),
                "media_journey": {**turn.media_journey, "state": "active" if run_id else "blocked",
                                  "scene_order": scenes},
            }
    return replace(observation, stop_after_observation=True)


async def stop_media_journey(db, opening, conversation) -> dict | None:
    """Fence the next automatic Start even when its preceding Run is already complete."""
    from datetime import UTC, datetime

    from app.models.schemas import WorkflowStatus
    from app.models.tables import Project
    from app.pipeline.orchestrator import cancel_run

    opening_id = opening.id
    project_id = conversation.project_id
    await db.refresh(opening, with_for_update={"key_share": True})
    marker = await db.scalar(select(Message).where(
        Message.conversation_id == conversation.id,
        Message.intent["media_journey"]["opening_id"].as_string() == str(opening_id),
    ).order_by(Message.seq.desc().nulls_last()).limit(1).execution_options(populate_existing=True))
    if marker is None or opening.turn_state != "settled":
        return None
    journey = marker.intent["media_journey"]
    if journey["state"] not in {"active", "stopped"}:
        return {"seq": marker.seq, "intent": {"media_journey": journey}}
    stopped = {**journey, "state": "stopped"}
    receipt = {"seq": marker.seq, "intent": {"media_journey": stopped}}
    if not (opening.intent or {}).get("stop_requested_at"):
        opening.intent = {**(opening.intent or {}), "stop_requested_at": datetime.now(UTC).isoformat()}
    marker.intent = {**marker.intent, "media_journey": stopped}
    # Once the opening is fenced no further Start can commit. In the handoff
    # gap there is no Run to lock. If Start won, cancel in project → Run order.
    active_id = await db.scalar(select(WorkflowRun.id).where(
        WorkflowRun.project_id == project_id,
        WorkflowRun.context["media_journey"]["opening_id"].as_string() == str(opening_id),
        WorkflowRun.status.in_([WorkflowStatus.PENDING, WorkflowStatus.RUNNING, WorkflowStatus.WAITING_HUMAN]),
    ).limit(1))
    await db.commit()
    if active_id is not None:
        project = await db.get(Project, project_id, with_for_update=True, populate_existing=True)
        active = await db.get(WorkflowRun, active_id, with_for_update=True, populate_existing=True)
        if active is not None:
            await cancel_run(db, active, project)
    return receipt


async def continue_media_journey(db, project, conversation, run) -> None:
    """Resume one settled preparation from its original user turn, without a new user row."""
    from app.chat.conversation_context import context_items
    from app.chat.plan_turn import run_plan_turn
    from app.chat.service import (
        finalize_bailed_runs,
        fold_conversation_usage,
        latest_pending_question,
        list_conversation_messages,
    )
    from app.metering import bind_conversation_turn
    from app.models.schemas import ChatRequest, CreativeState, PendingPlan, WorkflowStatus

    if not (run.context or {}).get("media_journey"):
        return
    run = await db.get(WorkflowRun, run.id, with_for_update=True, populate_existing=True)
    if run is None:
        return
    context = run.context or {}
    journey = context.get("media_journey")
    if not journey or context.get("media_continuation_finished"):
        return
    if run.status != WorkflowStatus.COMPLETED:
        return
    if context.get("music_preparation") or context.get("narration_preparation"):
        # Only advance from a durable transcript receipt. A stopped delivery
        # remains an explicit, user-visible terminal outcome across restarts.
        receipt = await db.scalar(select(Message).where(
            Message.conversation_id == conversation.id, Message.workflow_run_id == run.id,
            Message.intent["trigger"].as_string() == "run_completed",
        ).order_by(Message.seq.desc()).limit(1))
        if receipt is None:
            return
        if not (receipt.intent or {}).get("media_journey"):
            from app.tools.video.audio_playback import audio_preparation, record_run_audio

            role, preparation = audio_preparation(run)
            await record_run_audio(
                db, project, conversation.id, journey, role, preparation,
                trigger_intent=receipt.intent,
                run_id=run.id, existing_message=receipt,
            )
        delivery_state = receipt.intent["media_journey"]["state"]
        if delivery_state in {"complete", "blocked", "stopped"}:
            run.context = {**context, "media_continuation_finished": True}
            await db.commit()
            return
    opening = await db.get(Message, UUID(journey["opening_id"]), populate_existing=True)
    valid_opening = opening is not None and opening.conversation_id == conversation.id
    language = getattr(conversation, "ui_language", None) or getattr(project, "language", None) or ""
    zh = language.startswith("zh") or (not language and valid_opening and "宣传片" in opening.content)

    async def stop_continuation(english: str, chinese: str, *, state: str = "blocked"):
        from app.chat.service import _create_message

        await _create_message(
            db, conversation.id, "assistant", chinese if zh else english,
            workflow_run_id=run.id, turn_id=opening.id if valid_opening else None,
            intent={"media_journey": {**journey, "state": state}},
        )
        run.context = {**context, "media_continuation_finished": True}
        await db.commit()

    if not valid_opening or opening.turn_state == "failed":
        await stop_continuation(
            "The original request is unavailable. Media preparation stopped.",
            "无法恢复最初的制作请求，素材准备已停止。",
        )
        return
    if (opening.intent or {}).get("stop_requested_at") or opening.turn_state == "cancelled":
        await stop_continuation("Media preparation stopped.", "素材准备已停止。", state="stopped")
        return
    if opening.turn_state != "settled":
        await stop_continuation(
            "The original request has not settled. Media preparation stopped.",
            "最初的请求尚未结算，后续素材准备已停止。",
        )
        return
    newer_input = await db.scalar(select(Message.id).where(
        Message.conversation_id == conversation.id, Message.role == "user",
        Message.seq > opening.seq,
    ).limit(1))
    if newer_input is not None:
        await stop_continuation(
            "The newer request superseded this media preparation.",
            "已收到后续请求，本次素材准备已停止。", state="stopped",
        )
        return
    if await latest_pending_question(db, conversation.id) is not None:
        await stop_continuation(
            "Media preparation paused at the outstanding Chat question.",
            "对话中有待处理的问题，本次素材准备已暂停。",
        )
        return

    await db.refresh(conversation, ["context"])
    preparation = (
        context.get("visual_asset_preparation") or context.get("narration_preparation") or {}
    )
    parts = preparation.get("scenes") or [preparation]
    reference = (parts[0].get("request") or {}).get("draft_ref") or {}
    draft_id = reference.get("draft_id")
    current = next((
        item for item in reversed(context_items(conversation.context))
        if (item.get("candidate") or {}).get("target_tool") == "design_video"
        and (item.get("candidate") or {}).get("candidate_id") == draft_id
    ), None)
    candidate = (current or {}).get("candidate") or {}
    draft = (current or {}).get("executed_arguments")
    if (
        not draft_id or not reference.get("draft_digest") or not isinstance(draft, dict)
        or not candidate.get("active") or candidate.get("candidate_digest") != reference["draft_digest"]
    ):
        await stop_continuation(
            "The working storyboard for this preparation has changed or is unavailable. Media preparation stopped.",
            "这次素材准备所用的分镜草稿已变更或无法读取，后续素材准备已停止。",
        )
        return
    images = await visual_results(db, project.id, journey["opening_id"], draft_id)
    state = media_actions(draft, images)
    if state["phase"] == "images_blocked":
        scenes = ", ".join(state["blocked_scene_ids"])
        await stop_continuation(
            f"Image preparation stopped for these scenes: {scenes}. The required image or review is still unavailable after recovery.",
            f"分镜 {scenes} 的图片准备已停止。恢复后仍缺少符合要求的图片或审阅结果。",
        )
        return
    creative = CreativeState.model_validate(context.get("creative_state"))
    pending = PendingPlan(
        prompt=opening.content, brief=creative.brief, creative_state=creative,
    )
    recent = await list_conversation_messages(db, conversation.id)
    user_id = UUID(str(project.user_id))
    with bind_conversation_turn(
        conversation_id=conversation.id, turn_id=str(run.id), project_id=project.id
    ) as usage:
        try:
            _, _, _, bailed = await run_plan_turn(
                db, user_id, conversation, project,
                ChatRequest(
                    project_id=project.id,
                    message="Continue the authorized media preparation from the settled Run.",
                ),
                recent=recent,
                turn_id=opening.id,
                media_journey=journey,
                media_resume_pending=pending,
                media_resume_narration=[p["result"] for p in parts if p.get("result")] if context.get("narration_preparation") else None,
                media_resume_draft=RestoredCandidate(
                    candidate_id=draft_id, candidate_digest=reference["draft_digest"],
                    tool_name="design_video", arguments=draft, errors=[],
                    base_keys=frozenset(candidate.get("base_keys") or []),
                    call_id=str(current.get("call_id") or run.id),
                ),
            )
        except MediaDraftUnavailable:
            await stop_continuation(
                "The current storyboard could not be verified against its sources. Media preparation stopped.",
                "无法核实当前分镜与素材来源的一致性，后续素材准备已停止。",
            )
            return
    await fold_conversation_usage(db, user_id=user_id, project_id=project.id, accrued=usage.accrued)
    run.context = {**context, "media_continuation_finished": True}
    await db.commit()
    if bailed:
        await finalize_bailed_runs(bailed)


async def recover_settled_media_journeys() -> None:
    """Replay unfinished media continuation events after a Worker restart."""
    from app.chat.trigger_turn import fire_trigger
    from app.models.database import AsyncSessionLocal
    from app.models.schemas import WorkflowStatus
    from app.pipeline.trigger_events import TRIGGER_RUN_COMPLETED, run_trigger_ref

    async with AsyncSessionLocal() as db:
        runs = (await db.scalars(select(WorkflowRun).where(
            WorkflowRun.status == WorkflowStatus.COMPLETED,
            WorkflowRun.context["media_journey"].as_string().is_not(None),
            WorkflowRun.context["media_continuation_finished"].as_string().is_(None),
        ))).all()
    for run in runs:
        fire_trigger(
            run.project_id, TRIGGER_RUN_COMPLETED,
            run_trigger_ref(run.id, TRIGGER_RUN_COMPLETED, run.context),
        )
