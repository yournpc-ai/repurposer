"""Chat continuation for a staged, explicitly requested video preparation."""

import json
from dataclasses import replace
from math import isfinite
from uuid import UUID

from sqlalchemy import select

from app.agents.candidate_correction import RestoredCandidate
from app.agents.tool_loop import ToolObservation
from app.chat.service import _scope_turn_row_lock_ownership
from app.models.schemas import PresentPlanArgs, TaskItem
from app.models.tables import Conversation, Message, Project, WorkflowRun
from app.tools.video.visual_assets import current_scene_assets

IMAGE_TOOLS = {
    "ask_user", "answer", "read_conversation_context", "prepare_video_materials", "capture_web",
    "get_understanding", "get_web_page", "get_asset", "list_project_media",
    "list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview",
    "design_video", "prepare_visual_assets",
}
AUDIO_TOOLS = (IMAGE_TOOLS - {"prepare_visual_assets"}) | {
    "prepare_narration", "get_narration_alignment", "annotate_narration",
}
PREPARATION_TOOLS = {"prepare_visual_assets", "prepare_narration"}


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
        elif review.get("reviewer_version") != spec.review_version():
            missing.append(spec.scene_id)
        elif review.get("status") == "unavailable" and not item.get("review_retry_of"):
            unavailable.append(spec.scene_id)
        elif review.get("status") == "fail":
            if attempt_count < 2:
                repair.append(spec.scene_id)
            else:
                blocked.append(spec.scene_id)
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


def scene_asset_changes(previous: dict, current: dict, results: list[dict]) -> dict:
    prior = {spec.scene_id: spec.request_digest() for spec in current_scene_assets(previous)}
    specs = current_scene_assets(current)
    state = media_actions(current, results)
    pending = set(state["missing_scene_ids"] + state["review_retry_scene_ids"]
                  + state["repair_scene_ids"] + state["blocked_scene_ids"])
    return {
        "changed_scene_ids": [s.scene_id for s in specs if prior.get(s.scene_id) != s.request_digest()],
        "reusable_scene_ids": [s.scene_id for s in specs if s.scene_id not in pending],
        "prepare_scene_ids": state["missing_scene_ids"],
        "review_existing_scene_ids": state["review_retry_scene_ids"],
        "repair_scene_ids": state["repair_scene_ids"],
        "blocked_scene_ids": state["blocked_scene_ids"],
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


async def settled_recordings(db, project_id: UUID, opening_id: str, draft_id: str) -> list[dict]:
    from app.models.schemas import WorkflowStatus

    prep = WorkflowRun.context["narration_preparation"]
    rows = await db.scalars(select(prep).where(
        WorkflowRun.project_id == project_id,
        WorkflowRun.status == WorkflowStatus.COMPLETED,
        WorkflowRun.context["media_journey"]["opening_id"].as_string() == opening_id,
        prep.as_string().is_not(None),
    ).order_by(WorkflowRun.created_at, WorkflowRun.id))
    return [
        part for preparation in rows.all() for part in preparation.get("scenes") or [preparation]
        if ((part.get("request") or {}).get("draft_ref") or {}).get("draft_id") == draft_id
        and part.get("result")
    ]


def cached_recording(draft: dict, result: dict) -> dict | None:
    from app.tools.video.narration_draft import scene_narration_request

    scene_id = result.get("scene_id")
    try:
        speech = scene_narration_request(draft, scene_id)
    except ValueError:
        return None
    if result.get("text") != speech["text"]:
        return None
    decode = ((result.get("analysis") or {}).get("media_facts") or {}).get("decode") or {}
    return {
        "request": {"scene_id": scene_id, **speech},
        "result": {
            "scene_id": scene_id,
            "alignment_id": result.get("alignment_id"),
            "audio_snapshot_id": result.get("audio_snapshot_id"),
            "duration_seconds": result.get("actual_duration_seconds") or decode.get("duration_seconds"),
        },
    }


def cached_recordings_for_draft(items: list[dict], opening_id: str, draft_id: str) -> list[dict]:
    """Cache hits have a successful tool receipt instead of a WorkflowRun."""
    drafts = {}
    recordings = []
    for item in items:
        if item.get("turn_id") != opening_id or not item.get("ok"):
            continue
        candidate = item.get("candidate") or {}
        if item.get("tool") == "design_video" and candidate.get("candidate_id") == draft_id:
            drafts[candidate["candidate_digest"]] = item.get("executed_arguments")
        if item.get("tool") != "prepare_narration":
            continue
        reference = (item.get("arguments") or {}).get("draft_ref") or {}
        draft = drafts.get(reference.get("draft_digest"))
        if reference.get("draft_id") != draft_id or not draft:
            continue
        try:
            result = json.loads(item["text"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not isinstance(result, dict) or result.get("cache") != "hit"
            or result.get("draft_ref") != reference
            or result.get("scene_id") != item["arguments"].get("scene_id")
        ):
            continue
        part = cached_recording(draft, result)
        if part:
            recordings.append(part)
    return recordings


def narration_resume_state(draft: dict, recordings: list[dict]) -> dict:
    """Project measured originals onto the speech in this exact working revision."""
    from app.editing.timing import DEFAULT_TIMEBASE

    confirmed = {
        f["scene_id"]: (f.get("alignment") or {}).get("alignment_id")
        for f in draft["design"].get("narrations") or []
        if (f.get("alignment") or {}).get("status") == "READY"
    }
    by_script = {}
    for part in recordings:
        request, result = part["request"], part["result"]
        duration = result.get("duration_seconds")
        key = tuple(request.get(k) for k in ("scene_id", "text", "voice_id", "language"))
        if (all(key) and request["scene_id"] == result.get("scene_id")
                and result.get("alignment_id") and result.get("audio_snapshot_id")
                and isinstance(duration, (float, int)) and isfinite(duration) and duration > 0):
            previous = by_script.get(key)
            if previous is None or previous["alignment_id"] != confirmed.get(request["scene_id"]):
                by_script[key] = result

    content = draft["content"]
    timebase = (content.get("settings") or {}).get("timebase", DEFAULT_TIMEBASE)
    speech = {
        clip["scene_id"]: clip["object"]
        for track in content["timeline"]["tracks"] for clip in track["clips"]
        if (clip.get("object") or {}).get("kind") == "speech" and not clip["object"].get("alignment")
    }
    scenes, pending = [], []
    measured = 0.0
    for scene in content["scenes"]:
        scene_id = scene["scene_id"]
        if scene_id not in speech:
            continue
        obj = speech[scene_id]
        window = scene["range"]
        row = {
            "scene_id": scene_id, "text": obj["text"],
            "window_seconds": (window["end"] - window["start"]) / timebase,
        }
        result = by_script.get((scene_id, obj["text"], obj.get("voice_id"), obj.get("language")))
        if result:
            row.update({k: result[k] for k in ("alignment_id", "audio_snapshot_id", "duration_seconds")})
            row["timing_confirmed"] = confirmed.get(scene_id) == result["alignment_id"]
            measured += result["duration_seconds"]
        else:
            pending.append(scene_id)
        scenes.append(row)
    target = (draft["design"].get("user_constraints") or {}).get("target_seconds")
    return {
        "scenes": scenes, "pending_scene_ids": pending,
        "draft_seconds": max((s["range"]["end"] for s in content["scenes"]), default=0) / timebase,
        "target_seconds": target, "matched_audio_seconds": round(measured, 3),
        "remaining_seconds": round(target - measured, 3) if target is not None else None,
    }


def media_write_rejection(phase: str, name: str, params, narration_resume=None) -> str | None:
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
    if narration_resume is not None:
        if name == "prepare_narration" and params.scene_id not in narration_resume["pending_scene_ids"]:
            return "This scene is not pending. Use the matching recording in narration_resume.scenes."
        if name in {"get_narration_alignment", "annotate_narration"} and not any(
            row.get("alignment_id") == str(params.alignment_id) for row in narration_resume["scenes"]
        ):
            return "Use an alignment from the current narration_resume.scenes."
        update = getattr(params, "narration_update", None)
        if update and all(
            getattr(update, field, None) is None for field in ("text", "voice_id", "language")
        ):
            scene = next((s for s in narration_resume["scenes"] if s["scene_id"] == update.scene_id), {})
            if update.alignment_id:
                if scene.get("alignment_id") != str(update.alignment_id):
                    return "This alignment does not match the scene's current text, voice and language. Check narration_resume."
            elif not scene.get("timing_confirmed"):
                return "Read the current scene's recording and supply its READY alignment_id before retiming."
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
    if name == "prepare_narration" and observation.ok:
        cached = json.loads(observation.text)
        if cached.get("cache") == "hit":
            from app.tools.video.audio_playback import record_prepared_audio

            role = "narration"
            message = await record_prepared_audio(
                turn.db, turn.project, turn.conversation_id, turn.media_journey, role,
                cached.get("result") or cached, cached, working_draft=working_draft,
            )
            state = message.intent["media_journey"]["state"]
            if state == "active" and turn.media_state.get("narration_resume") is not None:
                part = cached_recording(working_draft, cached)
                if part:
                    turn.media_resume_narration.append(part)
            if state in {"complete", "blocked"}:
                turn.outcome = (message, None, turn.settled_pending, [])
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
    resume = turn.media_state.get("narration_resume")
    if resume is None:
        ready = {fact["scene_id"] for fact in current_narration_facts(draft)}
        required = {
            clip["scene_id"] for track in draft["content"]["timeline"]["tracks"] for clip in track["clips"]
            if (clip.get("object") or {}).get("kind") == "speech" and not clip["object"].get("alignment")
        }
        missing = required.difference(scene_ids, ready)
    else:
        missing = set(resume["pending_scene_ids"]).difference(scene_ids)
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
    started = bool(turn.outcome and turn.outcome[1])
    result = json.loads(observation.text)
    result.update({
        "ok": started, "execution": "run_created" if started else "run_not_created",
        "run_id": str(turn.outcome[1]) if started else None,
    })
    result.pop("next", None)
    return replace(observation, ok=started, text=json.dumps(result, ensure_ascii=False),
                   stop_after_observation=True)


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


@_scope_turn_row_lock_ownership
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
        blocked = set(state["blocked_scene_ids"])
        scenes = ", ".join(str(index) for index, scene in enumerate(draft["content"]["scenes"], 1)
                           if scene["scene_id"] in blocked)
        reasons = " ".join(failure["detail"] for failure in state["scene_failures"]
                           if failure["scene_id"] in blocked and failure["code"] == "content_review_failed")
        await stop_continuation(
            f"Image preparation stopped at scene {scenes}. " + (reasons or "A usable image or review is still missing after recovery."),
            f"分镜 {scenes} 的图片准备已停止。" + (reasons or "重试后仍缺少符合要求的图片或审阅结果。"),
        )
        return
    creative = CreativeState.model_validate(context.get("creative_state"))
    pending = PendingPlan(
        prompt=opening.content, brief=creative.brief, creative_state=creative,
    )
    recent = await list_conversation_messages(db, conversation.id)
    recordings = None
    if context.get("narration_preparation"):
        recordings = await settled_recordings(db, project.id, journey["opening_id"], draft_id)
        recordings.extend(cached_recordings_for_draft(
            context_items(conversation.context), journey["opening_id"], draft_id,
        ))
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
                media_resume_narration=recordings,
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
