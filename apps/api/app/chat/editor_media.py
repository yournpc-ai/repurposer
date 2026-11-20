"""Execute media calls against the existing queue and return measured project media."""

import asyncio
import json
from uuid import UUID, uuid5

from sqlalchemy import func, select

from app.agents.tool_loop import ToolObservation
from app.agents.tool_progress import current_call_id
from app.chat.service import (
    _create_message, _lock_turn_for_transcript_write, latest_pending_question,
    resolve_confirmation_need, submit_confirmed_tasks,
)
from app.models.database import AsyncSessionLocal
from app.models.schemas import TaskItem, WorkflowStatus, canonical_json_hash
from app.models.tables import Composition, Conversation, Message, Project, WorkflowRun, WorkflowStep
from app.pipeline.orchestrator import derive_task_estimates
from app.tools.music.score import instrumental_score
from app.tools.video.audio_playback import playback_item
from app.tools.video.music_preparation import cached_music_preparation


async def _record_audio(db, project, receipt, result, request):
    music = "score_spec" in result
    role = "music" if music else "narration"
    item = await playback_item(db, project, role, result, request)
    facts = {
        "status": "available", "role": role, "snapshot_id": item["snapshot_id"],
        "digest": item["digest"], "duration_seconds": item["duration_seconds"],
        "analysis_digest": item["analysis_digest"], "peak": max(item["peaks"]),
        "cache_hit": result["cache_hit"], "added_to_composition": False,
    }
    if music:
        facts.update(music_id=result["music"]["music_id"],
                     score={"bpm": result["score_spec"]["bpm"], "style": request.get("style")})
    else:
        facts.update(alignment_id=result["alignment_id"], text=request["text"],
                     language=request["language"], voice_id=request["voice_id"])
    receipt.intent = {**receipt.intent, "media_result": facts}
    zh = (project.language or "").startswith("zh")
    receipt.content = (("配乐已生成，可以试听。" if music else "旁白已生成，可以试听。") if zh else
                       ("The score is ready to play." if music else "The voice recording is ready to play."))
    receipt.blocks = [{"kind": "audio_playback", "project_id": str(project.id), "items": [item]}]
    return receipt


async def _record_image(db, project, receipt, asset):
    from app.models.tables import SourceSnapshot
    from app.tools.video.visual_assets import visual_asset_result_images

    snapshot = await db.get(SourceSnapshot, UUID(asset["snapshot"]["snapshot_id"]))
    if (snapshot is None or snapshot.kind != "image" or snapshot.owner_id != project.user_id
            or snapshot.origin_project_id != project.id or snapshot.digest != asset["media"]["digest"]
            or snapshot.storage_key != asset["media"]["storage_key"]):
        raise ValueError("The image snapshot does not match its fixed source.")
    await visual_asset_result_images([asset])
    review = asset["content_review"]
    facts = {"status": "available", "role": "image", "snapshot_id": str(snapshot.id), "digest": snapshot.digest,
             "dimensions": asset["analysis"]["media_facts"]["dimensions"], "review": review["status"],
             "review_summary": review["summary"], "cache_hit": asset.get("cache_hit", False),
             "added_to_composition": False}
    receipt.intent = {**receipt.intent, "media_result": facts}
    receipt.blocks = [{"kind": "image_preview", "project_id": str(project.id), "snapshot_id": str(snapshot.id),
                       "digest": snapshot.digest, "description": review["summary"]}]
    receipt.content = "图片已生成，可查看审阅结果。" if (project.language or "").startswith("zh") else "The image is ready for review."
    return receipt


async def settle_media_receipt(db, project, run):
    """Worker delivery, live tool return and history recovery share one locked receipt."""
    receipt = await db.scalar(select(Message).where(
        Message.workflow_run_id == run.id, Message.intent.has_key("editor_media"),
    ).with_for_update().execution_options(populate_existing=True))
    if receipt is None:
        raise ValueError("The media request receipt is unavailable.")
    facts = receipt.intent.get("media_result")
    if facts:
        return receipt
    if run.status == WorkflowStatus.COMPLETED:
        try:
            if "visual_asset_preparation" in run.context:
                result = run.context["visual_asset_preparation"]["result"]
                if result["failures"]:
                    raise ValueError(result["failures"][0]["detail"])
                return await _record_image(db, project, receipt, result["assets"][0])
            prep = run.context.get("music_preparation") or run.context["narration_preparation"]
            return await _record_audio(db, project, receipt, prep["result"], prep["request"])
        except ValueError as exc:
            error = str(exc)
    elif run.status in (WorkflowStatus.FAILED, WorkflowStatus.CANCELLED):
        error = await db.scalar(select(WorkflowStep.error).where(
            WorkflowStep.run_id == run.id, WorkflowStep.error.is_not(None)).limit(1))
        error = str(error or run.status.value)
    else:
        return None
    facts = {"status": "failed", "error": error}
    receipt.intent = {**receipt.intent, "media_result": facts}
    receipt.content = error
    return receipt


async def _submit(db, project, receipt, task, quote, via):
    run = await submit_confirmed_tasks(
        db, project, None, [task], name=task.params.get("name", task.tool), instruction=None,
        confirmation_id=receipt.intent["editor_media"], confirmed_via=via, quote=quote,
    )
    run.context = {**run.context, "editor_media": receipt.intent["editor_media"]}
    receipt.workflow_run_id = run.id
    return run.id


async def answer_media_permission(db, project, receipt, approved):
    """The answer row lock makes the exact quote and its answer single-use."""
    auth = receipt.intent["media_permission"]
    if not approved:
        receipt.intent = {**receipt.intent, "media_result": {"status": "declined"}}
        return
    head = await db.scalar(select(Composition.current_version_id).where(
        Composition.id == UUID(receipt.intent["composition_id"]), Composition.owner_id == project.user_id,
        Composition.origin_project_id == project.id,
    ))
    if str(head) != receipt.intent["version_id"]:
        raise ValueError("The work changed before authorization.")
    task = TaskItem.model_validate(auth["task"])
    estimate = await derive_task_estimates(db, project, [task])
    if estimate is None or estimate.total[1] > auth["quote"]["total"][1]:
        raise ValueError("The media quote has changed.")
    await _submit(db, project, receipt, task, estimate.model_dump(mode="json"), "user_option")


async def _cached_voice(project, args):
    from app.editing.schemas import SpeechObject
    from app.tools.video.alignment_store import request_alignment
    from app.tools.video.narration_store import peek_original
    from app.tools.video.preparation import snapshot_narration_original

    speech = SpeechObject(kind="speech", object_id="obj_prepare_narration", **args.model_dump())
    original = await peek_original(project.user_id, speech)
    if original is None:
        return None
    async with AsyncSessionLocal() as db:
        _, snapshot = await snapshot_narration_original(db, project, text=args.text, original=original)
        await db.commit()
    aligned = await request_alignment(owner_id=project.user_id, audio_snapshot_id=snapshot.id, text=args.text)
    return {"audio_snapshot_id": str(snapshot.id), "audio_digest": snapshot.digest,
            "alignment_id": aligned["alignment_id"], "cache_hit": True}


async def submit_editor_media(turn, name, args, composition, version, call_id):
    identity = str(uuid5(turn.turn_id, call_id))
    params = args.model_dump(mode="json")
    fingerprint = canonical_json_hash({"tool": name, "composition": str(composition.id), "params": params})
    async with AsyncSessionLocal() as db:
        opening = await _lock_turn_for_transcript_write(db, turn.turn_id)
        project = await db.scalar(select(Project).join(Conversation, Conversation.project_id == Project.id).where(
            Conversation.id == opening.conversation_id, Conversation.id == turn.conversation_id,
            Conversation.user_id == turn.user_id, Project.id == turn.project.id, Project.user_id == turn.user_id,
        ))
        if project is None or opening.role != "user":
            raise ValueError("Media request is outside the current project.")
        receipt = await db.scalar(select(Message).where(
            Message.turn_id == opening.id, Message.intent["editor_media"].as_string() == identity,
        ))
        if receipt:
            if receipt.intent["fingerprint"] != fingerprint:
                raise ValueError("This call already belongs to different parameters.")
            if receipt.intent.get("media_result") or receipt.question:
                return receipt
        else:
            if opening.turn_state != "in_flight":
                raise ValueError("This media request has ended.")
            head = await db.scalar(select(Composition.current_version_id).where(Composition.id == composition.id))
            if head != version.id or turn._video_base_ref["content_digest"] != version.content_digest:
                raise ValueError("The work has changed. Inspect its current version.")
            pending = await latest_pending_question(db, turn.conversation_id)
            if pending and ((pending.question or {}).get("kind") == "task_book" or
                            (pending.intent or {}).get("media_permission")):
                raise ValueError("Resolve the outstanding authorization before generating more media.")
            if name == "generate_image":
                from app.tools.video.params import PrepareVisualAssetsParams
                from app.tools.video.production import resolve_visual_asset_selection
                from app.tools.video.visual_assets import SceneAssetSpec, cached_visual_asset, preflight_scene_svgs

                source = ({"kind": "controlled_svg", "program": args.svg} if args.svg else
                          {"kind": "minimax_image", "prompt": args.prompt})
                spec = SceneAssetSpec(scene_id="editor_image", intent=args.prompt, source=source)
                request = PrepareVisualAssetsParams(
                    scene_assets=[spec], version_ref=turn._video_base_ref, opening_id=opening.id,
                    evidence_snapshot_id=args.evidence_snapshot_id,
                )
                specs = await resolve_visual_asset_selection(db, project, request)
                preflight_scene_svgs(specs)
                cached = await cached_visual_asset(owner_id=turn.user_id, project_id=project.id, spec=specs[0])
                task = TaskItem(tool="prepare_visual_assets", params=request.model_dump(mode="json", exclude_none=True))
            elif name == "generate_music":
                task = TaskItem(tool="prepare_music", params=params)
                cached = await cached_music_preparation(owner_id=turn.user_id, project_id=project.id,
                                                        score=instrumental_score(args))
            else:
                task = TaskItem(tool="prepare_narration", params=params)
                cached = await _cached_voice(project, args)
            receipt = await _create_message(
                db, turn.conversation_id, "assistant", "", turn_id=opening.id,
                intent={"editor_media": identity, "fingerprint": fingerprint,
                        "composition_id": str(composition.id), "version_id": str(version.id)},
            )
            if cached is not None:
                if name == "generate_image":
                    await _record_image(db, project, receipt, cached)
                else:
                    await _record_audio(db, project, receipt, cached, params)
                await db.commit()
                return receipt
            estimate = await derive_task_estimates(db, project, [task])
            need = await resolve_confirmation_need(db, turn.user_id, estimate, require_quote=True)
            quote = estimate.model_dump(mode="json") if estimate else None
            if not quote:
                raise ValueError("A bounded media quote is unavailable.")
            if need.requires_confirmation:
                zh = (project.language or "").startswith("zh")
                text = (f"允许这次素材生成吗？最多使用 {need.quote_high} 积分。" if zh else
                        f"Authorize this media generation for up to {need.quote_high} credits?")
                receipt.content = text
                receipt.question = {"kind": "question", "question": text,
                                    "options": [{"id": "approve", "label": "允许" if zh else "Allow"},
                                                {"id": "decline", "label": "取消" if zh else "Decline"}]}
                receipt.intent = {**receipt.intent, "media_permission": {"task": task.model_dump(), "quote": quote}}
                await db.commit()
                return receipt
            await _submit(db, project, receipt, task, quote, "editor_tool")
            await db.commit()
        return receipt


async def generate_media(turn, name, args, composition, version):
    call_id = current_call_id()
    if not turn.turn_id or not call_id:
        raise ValueError("A durable message and native call identity are required.")
    from app.chat.editor_recovery import editor_lock_key

    await turn.db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id))))
    receipt = await submit_editor_media(turn, name, args, composition, version, call_id)
    if receipt.question and not receipt.answer:
        if hasattr(turn, "settled_pending"):
            turn.outcome = (receipt, None, turn.settled_pending, [])
        else:
            turn.outcome = (receipt, None, [], turn.settled_question)
        return ToolObservation("Awaiting authorization.", stop_after_observation=True)
    run_id = receipt.workflow_run_id
    # No open submission transaction while a worker owns the operation.
    while not receipt.intent.get("media_result"):
        await asyncio.sleep(0.5)
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, run_id)
            if run is None:
                raise ValueError("The submitted audio request is unavailable.")
            if run.status not in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
                settled = await settle_media_receipt(db, turn.project, run)
                if settled is not None:
                    receipt = settled
                await db.commit()
    if turn.on_row_append:
        await turn.on_row_append(receipt)
    turn._inspected_version = str(version.id)
    facts = dict(receipt.intent["media_result"])
    if facts.get("alignment_id"):
        from app.tools.video.alignment_store import wait_for_alignment

        aligned = await wait_for_alignment(owner_id=turn.user_id, alignment_id=UUID(facts["alignment_id"]),
                                           budget_seconds=45)
        payload = aligned.get("payload") or {}
        facts.update(alignment_status=aligned["status"], source_timebase=aligned["source_timebase"],
                     cues=[{k: sentence.get(k) for k in ("text", "start_tick", "end_tick", "status")}
                           for sentence in payload.get("sentences", [])], alignment_error=aligned.get("error"))
    images = []
    if facts.get("role") == "image":
        from app.models.tables import SourceSnapshot
        from app.tools.video.visual_assets import visual_asset_result_images

        async with AsyncSessionLocal() as db:
            snapshot = await db.get(SourceSnapshot, UUID(facts["snapshot_id"]))
            images = await visual_asset_result_images([{
                "media": {"storage_key": snapshot.storage_key, "digest": facts["digest"]},
                "scene_id": "editor_image", "snapshot": {"snapshot_id": str(snapshot.id)},
            }])
    facts["delivered_to_chat"] = True
    labels = turn.__dict__.setdefault("_editor_labels", {})
    for key in ("snapshot_id", "alignment_id", "digest", "music_id", "analysis_digest"):
        if facts.get(key):
            labels[facts[key]] = ("这份素材", "this media")
    return ToolObservation(json.dumps(facts), images=images, ok=facts["status"] == "available")
