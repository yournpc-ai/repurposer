"""Chat continuation for a staged, explicitly requested video preparation."""

import json
from dataclasses import replace
from uuid import UUID

from sqlalchemy import select

from app.agents.tool_loop import ToolObservation
from app.models.schemas import PresentPlanArgs, TaskItem
from app.models.tables import Message, WorkflowRun
from app.tools.video.visual_assets import current_scene_assets

IMAGE_TOOLS = {
    "answer", "read_conversation_context", "prepare_video_materials", "capture_web",
    "get_understanding", "get_web_page", "get_asset", "list_project_media",
    "list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview",
    "design_video", "prepare_visual_assets",
}
AUDIO_TOOLS = IMAGE_TOOLS | {
    "prepare_narration", "get_narration_alignment", "annotate_narration", "prepare_music",
}
PREPARATION_TOOLS = {"prepare_visual_assets", "prepare_narration", "prepare_music"}


def initial_media_journey(opening: Message | None) -> dict | None:
    from app.chat.readiness import infer_task_kind
    from app.chat.video_turn_seats import requested_video_production

    if opening is None or opening.role != "user":
        return None
    text = opening.content or ""
    if infer_task_kind(text) != "website_promo" or not requested_video_production(text):
        return None
    return {"opening_id": str(opening.id)}


async def visual_results(db, project_id: UUID) -> list[dict]:
    from app.models.schemas import WorkflowStatus

    contexts = (await db.scalars(select(WorkflowRun.context).where(
        WorkflowRun.project_id == project_id,
        WorkflowRun.status == WorkflowStatus.COMPLETED,
        WorkflowRun.context["visual_asset_preparation"].is_not(None),
    ).order_by(WorkflowRun.created_at, WorkflowRun.id))).all()
    preparations = [context.get("visual_asset_preparation") or {} for context in contexts]
    return [
        item for preparation in preparations
        for key in ("assets", "failures")
        for item in (preparation.get("result") or {}).get(key, [])
    ]


def media_actions(draft: dict | None, results: list[dict]) -> dict:
    from app.tools.video.media_analysis import IMAGE_REVIEWER_VERSION
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
        elif review.get("reviewer_version") != IMAGE_REVIEWER_VERSION:
            missing.append(spec.scene_id)
        elif review.get("status") == "unavailable" and not item.get("review_retry_of"):
            unavailable.append(spec.scene_id)
        elif review.get("status") == "fail" and attempt_count < 2:
            repair.append(spec.scene_id)
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
        "blocked_scene_ids": blocked,
        "missing_scene_ids": missing,
        "review_retry_scene_ids": unavailable,
        "repair_scene_ids": repair,
        "scene_failures": failures,
    }


def audio_timing_ready(draft: dict) -> bool:
    from app.agents.working_drafts import working_draft_review_facts
    from app.tools.video.narration_draft import (
        assert_narration_ready_for_score,
        current_narration_facts,
    )

    scenes = working_draft_review_facts(draft)["scenes"]
    if not scenes or not all(scene["clip_ids"] for scene in scenes):
        return False
    try:
        assert_narration_ready_for_score(draft)
        return bool(current_narration_facts(draft))
    except ValueError:
        return False


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


async def dock_media_observation(turn, name: str, observation: ToolObservation) -> ToolObservation:
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
    if name == "prepare_music" and not turn.media_state.get("audio_timing_ready"):
        return replace(
            observation, ok=False,
            text="Finish the draft scenes and confirm READY narration timing before music.",
        )
    if name == "prepare_narration":
        scene_id = task.params.get("scene_id")
        previous = await turn.db.scalars(select(WorkflowRun.id).where(
            WorkflowRun.project_id == turn.project.id,
            WorkflowRun.context["media_journey"]["opening_id"].as_string()
            == turn.media_journey["opening_id"],
            WorkflowRun.context["narration_preparation"]["request"]["scene_id"].as_string()
            == scene_id,
        ).limit(2))
        if len(previous.all()) >= 2:
            return replace(
                observation, ok=False, text=f"Scene {scene_id} reached its narration retry limit."
            )
    zh = str(turn.project.language or "").startswith("zh")
    labels = {
        "prepare_visual_assets": ("分镜图片准备", "Scene image preparation"),
        "prepare_narration": ("分镜旁白准备", "Scene narration preparation"),
        "prepare_music": ("电子配乐准备", "Electronic music preparation"),
    }
    label = labels[name][0 if zh else 1]
    rejection = await turn._present_plan(
        PresentPlanArgs(tasks=[task], name=label, production_intent=True),
        f"接下来是{label}。我会沿用当前草稿与已确定的要求。"
        if zh else f"Next is {label.lower()}, using the current draft and agreed brief.",
    )
    if rejection:
        turn.media_start_rejections += 1
        turn.media_start_blocker = rejection
        return replace(
            observation, ok=False, text=f"Preparation could not start: {rejection}",
            stop_after_observation=turn.media_start_rejections >= 2,
        )
    if turn.outcome and turn.outcome[1] is not None:
        run = await turn.db.get(WorkflowRun, turn.outcome[1])
        run.context = {**run.context, "media_journey": turn.media_journey}
    return replace(observation, stop_after_observation=True)


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
    if context.get("music_preparation"):
        # The normal delivery has persisted its audio playback blocks.
        run.context = {**context, "media_continuation_finished": True}
        await db.commit()
        return
    opening = await db.get(Message, UUID(journey["opening_id"]), populate_existing=True)
    if (
        opening is None or opening.conversation_id != conversation.id
        or opening.turn_state != "settled" or (opening.intent or {}).get("stop_requested_at")
        or await latest_pending_question(db, conversation.id) is not None
    ):
        return
    newer_input = await db.scalar(select(Message.id).where(
        Message.conversation_id == conversation.id, Message.role == "user",
        Message.seq > opening.seq,
    ).limit(1))
    if newer_input is not None:
        return

    await db.refresh(conversation, ["context"])
    preparation = (
        context.get("visual_asset_preparation") or context.get("narration_preparation") or {}
    )
    draft_id = ((preparation.get("request") or {}).get("draft_ref") or {}).get("draft_id")
    current = next((
        item for item in reversed(context_items(conversation.context))
        if (item.get("candidate") or {}).get("target_tool") == "design_video"
        and (item.get("candidate") or {}).get("candidate_id") == draft_id
    ), None)
    draft = (
        current.get("executed_arguments")
        if current and (current.get("candidate") or {}).get("active") is True else None
    )
    if not isinstance(draft, dict):
        return
    images = await visual_results(db, project.id)
    phase = media_actions(draft, images)["phase"]
    if phase == "images_blocked":
        run.context = {**context, "media_continuation_finished": True}
        await db.commit()
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
        )
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
