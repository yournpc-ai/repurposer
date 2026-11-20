"""Execute media calls against the existing queue and return measured project media."""

import asyncio
import json
from uuid import UUID, uuid5

from sqlalchemy import func, select

from app.agents.tool_loop import ToolObservation
from app.agents.tool_progress import current_call_id, current_group_id
from app.chat.service import (
    _create_message, _lock_turn_for_transcript_write, latest_pending_question,
    resolve_confirmation_need, submit_confirmed_tasks,
)
from app.models.database import AsyncSessionLocal
from app.models.schemas import TaskItem, WorkflowStatus, canonical_json_hash
from app.models.tables import Composition, Conversation, Message, Output, Project, WorkflowRun, WorkflowStep
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


async def _record_export(db, project, receipt, run, *, recheck=False):
    from app.pipeline.run_review import output_is_delivered

    output = (await db.scalars(select(Output).join(WorkflowStep, Output.workflow_step_id == WorkflowStep.id)
        .where(WorkflowStep.run_id == run.id, WorkflowStep.kind == "produce_video",
               Output.project_id == project.id))).one_or_none()
    ref = run.context["version_ref"]
    if (output is None or not output_is_delivered(output)
            or output.type != "video" or not (output.files or {}).get("video")
            or str(output.composition_version_id) != receipt.intent["version_id"]
            or str(output.composition_id) != receipt.intent["composition_id"]
            or output.render_spec.get("provenance") != ref
            or (output.payload or {}).get("composition_digest") != ref["content_digest"]):
        raise ValueError("The renderer has no verified MP4 for the authorized version.")
    if recheck:
        from app.pipeline.rendering import _probe_artifacts

        violations, digest = await _probe_artifacts(output.render_spec, output.files["video"])
        if violations or (output.files.get("video_sha256") and digest != output.files["video_sha256"]):
            raise ValueError("The stored MP4 for this version is unavailable or failed media checks.")
    facts = {"role": "export", "status": "available", **ref, "output_id": str(output.id),
             "duration_seconds": output.payload["duration_seconds"], "review_pending": True}
    receipt.intent = {**receipt.intent, "media_result": facts}
    receipt.content = ("正式 MP4 已导出，待审片。" if (project.language or "").startswith("zh")
                       else "MP4 export complete. Output review is pending.")
    return receipt


async def deliver_video(db, turn, output_id, base):
    import hashlib
    from app.tools.video.review import read_output_video
    from app.pipeline.run_review import output_is_delivered

    group = current_group_id()
    if group and group == getattr(turn, "_video_review_group", None):
        raise ValueError("Read the Output review before deciding whether to deliver.")
    report = getattr(turn, "_video_review_report", None) or {}
    if (report.get("output_id") != str(output_id) or not report.get("frames")
            or any(report.get(k) != v for k, v in base.items())):
        raise ValueError("Delivery requires a review of this exact Output and selected version.")
    output = await db.scalar(select(Output).where(Output.id == output_id, Output.project_id == turn.project.id))
    if output is None or not output_is_delivered(output) or output.render_spec.get("provenance") != base:
        raise ValueError("The reviewed Output is unavailable.")
    data = await read_output_video(output.files["video"])
    if hashlib.sha256(data).hexdigest() != report["video_sha256"]:
        raise ValueError("The MP4 has changed since review. Review the actual file again.")
    opening = await _lock_turn_for_transcript_write(db, turn.turn_id, require_in_flight=True)
    if opening.conversation_id != turn.conversation_id:
        raise ValueError("The delivery does not belong to this Chat.")
    existing = await db.scalar(select(Message.id).where(
        Message.turn_id == opening.id, Message.intent["output_refs"].contains([str(output_id)]),
    ).limit(1))
    if existing is None:
        text = "正式成片已交付。" if (turn.project.language or "").startswith("zh") else "Your reviewed MP4 is ready."
        message = await _create_message(db, turn.conversation_id, "assistant", text, turn_id=opening.id,
            intent={"output_refs": [str(output_id)], "reviewed_version": base,
                    "reviewed_at": report["reviewed_at"], "video_sha256": report["video_sha256"]})
        await db.commit()
        if turn.on_row_append:
            await turn.on_row_append(message)
    return ToolObservation(json.dumps({"output_id": str(output_id), **base, "delivered_to_chat": True}))


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
    outcome_unknown = bool((run.context or {}).get("provider_outcome_unknown"))
    if run.status == WorkflowStatus.COMPLETED:
        try:
            if receipt.intent.get("tool") == "export_video":
                return await _record_export(db, project, receipt, run)
            if "visual_asset_preparation" in run.context:
                result = run.context["visual_asset_preparation"]["result"]
                if result["failures"]:
                    outcome_unknown = any(f.get("code") == "outcome_unknown" for f in result["failures"])
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
    facts = {"status": "provider_unknown" if outcome_unknown else "failed", "error": error}
    receipt.intent = {**receipt.intent, "media_result": facts}
    receipt.content = error
    return receipt


async def _submit(db, project, receipt, task, quote, via):
    export = receipt if task.tool == "produce_video" else None
    if export is not None:
        # Serialize even independent Chat openings before checking for a
        # completed export. In-flight production is fenced by create_run.
        await db.execute(select(Project.id).where(Project.id == project.id).with_for_update())
        existing = await db.scalar(select(WorkflowRun).where(
            WorkflowRun.project_id == project.id, WorkflowRun.status == WorkflowStatus.COMPLETED,
            WorkflowRun.context["editor_media"].as_string().is_not(None),
            WorkflowRun.context["version_ref"]["composition_version_id"].as_string() == receipt.intent["version_id"],
        ).order_by(WorkflowRun.created_at.desc()).limit(1))
        if existing is not None:
            await _record_export(db, project, receipt, existing, recheck=True)
            return existing.id
    run = await submit_confirmed_tasks(
        db, project, None, [task], name=task.params.get("name", task.tool), instruction=None,
        confirmation_id=receipt.intent["editor_media"], confirmed_via=via, quote=quote, export_receipt=export,
    )
    from app.models.tables import CreditTransaction

    hold = await db.scalar(select(CreditTransaction.amount).where(
        CreditTransaction.idempotency_key == f"run:{run.id}:hold"))
    if -(hold or 0) > quote["total"][1]:
        raise ValueError("The media price changed before submission.")
    run.context = {**run.context, "editor_media": receipt.intent["editor_media"]}
    receipt.workflow_run_id = run.id
    return run.id


async def answer_media_permission(db, project, receipt, approved):
    """The answer row lock makes the exact quote and its answer single-use."""
    auth = receipt.intent["media_permission"]
    row_id = receipt.intent.get("activity_id")
    row = await db.get(Message, UUID(row_id), with_for_update=True) if row_id else None
    frame = (row.intent or {}).get("frame", {}) if row else {}
    if frame.get("call_state") == "awaiting_authorization":
        state = "running" if approved else "cancelled"
        row.intent = {**row.intent, "frame": {**frame, "status": "active" if approved else "cancelled",
                                              "call_state": state}}
    if not approved:
        receipt.intent = {**receipt.intent, "media_result": {"status": "declined"}}
        return
    if receipt.intent.get("composition_id"):
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
    execution = await _create_message(db, receipt.conversation_id, "assistant", "", turn_id=receipt.turn_id,
                                      intent={k: v for k, v in receipt.intent.items() if k != "media_permission"})
    await _submit(db, project, execution, task, estimate.model_dump(mode="json"), "user_option")
    receipt.intent = {"media_permission": {"quote": auth["quote"]}, "media_receipt_id": str(execution.id)}
    return execution


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
    from app.chat.service import _TURN_ROW_LOCKS_HELD

    if turn.turn_id in _TURN_ROW_LOCKS_HELD.get():
        raise ValueError("This request is already settling another authorization.")
    identity = str(uuid5(turn.turn_id, call_id))
    params = args.model_dump(mode="json")
    composition_id = str(composition.id) if composition else None
    version_id = str(version.id) if version else None
    fingerprint = canonical_json_hash({"tool": name, "composition": composition_id, "params": params})
    if name == "export_video":
        fingerprint = canonical_json_hash({"tool": name, "version": version_id, "params": params})
    async with AsyncSessionLocal() as db:
        opening = await _lock_turn_for_transcript_write(db, turn.turn_id)
        project = await db.scalar(select(Project).join(Conversation, Conversation.project_id == Project.id).where(
            Conversation.id == opening.conversation_id, Conversation.id == turn.conversation_id,
            Conversation.user_id == turn.user_id, Project.id == turn.project.id, Project.user_id == turn.user_id,
        ))
        if project is None or opening.role != "user":
            raise ValueError("Media request is outside the current project.")
        if any(edit["request"] == identity for edit in (opening.intent or {}).get("editor_commits", [])):
            raise ValueError("This call already belongs to a different operation.")
        receipt = await db.scalar(select(Message).where(
            Message.turn_id == opening.id, Message.intent["editor_media"].as_string() == identity,
        ))
        if receipt and name == "export_video" and receipt.intent.get("composition_id") == composition_id:
            # The native call keeps its original export pin when a retry sees a newer head.
            fingerprint = canonical_json_hash({"tool": name, "version": receipt.intent["version_id"], "params": params})
        if not receipt and (opening.intent or {}).get("resumed_media"):
            # A resumed model can repeat the exact request with a fresh native
            # id. Return the existing receipt without acquiring another hold.
            receipt = await db.scalar(select(Message).where(
                Message.turn_id == opening.id, Message.intent["fingerprint"].astext == fingerprint,
                Message.intent["media_result"]["status"].astext == "available",
            ).order_by(Message.seq).limit(1))
        if receipt:
            if receipt.intent["fingerprint"] != fingerprint:
                raise ValueError("This call already belongs to different parameters.")
            if receipt.intent.get("media_result") or receipt.question:
                return receipt
        else:
            if opening.turn_state != "in_flight":
                raise ValueError("This media request has ended.")
            if composition:
                head = await db.scalar(select(Composition.current_version_id).where(
                    Composition.id == composition.id, Composition.origin_project_id == project.id,
                    Composition.owner_id == turn.user_id,
                ))
                if head != version.id or turn._video_base_ref["content_digest"] != version.content_digest:
                    raise ValueError("The work has changed. Inspect its current version.")
            pending = await latest_pending_question(db, turn.conversation_id)
            if pending and ((pending.question or {}).get("kind") == "task_book" or
                            (pending.intent or {}).get("media_permission")):
                raise ValueError("Resolve the outstanding authorization before generating more media.")
            preview = None
            if name == "export_video":
                from app.chat.video_turn_seats import draft_only_request

                if draft_only_request(opening.content or ""):
                    raise ValueError("The current request is limited to an editable draft.")
                preview = getattr(turn, "_editor_last_preview", None) or {}
                if (preview.get("composition_version_id") != version_id
                        or preview.get("content_digest") != version.content_digest
                        or not preview.get("mp4_sha256")
                        or current_group_id() and preview.get("decision") == current_group_id()):
                    raise ValueError("Inspect actual preview evidence for this version before deciding to export it.")
                task = TaskItem(tool="produce_video", params={"version_ref": turn._video_base_ref})
                cached = None
            elif name == "generate_image":
                from app.tools.video.params import PrepareVisualAssetsParams
                from app.tools.video.production import resolve_visual_asset_selection
                from app.tools.video.visual_assets import SceneAssetSpec, cached_visual_asset, preflight_scene_svgs

                source = ({"kind": "controlled_svg", "program": args.svg} if args.svg else
                          {"kind": "minimax_image", "prompt": args.prompt})
                spec = SceneAssetSpec(scene_id="editor_image", intent=args.prompt, source=source)
                request = PrepareVisualAssetsParams(
                    scene_assets=[spec], version_ref=getattr(turn, "_video_base_ref", None), opening_id=opening.id,
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
            activity_id = await db.scalar(select(Message.id).where(
                Message.turn_id == opening.id, Message.intent["frame"]["status"].astext == "active",
                Message.intent["frame"]["call_id"].astext == call_id,
            ).order_by(Message.seq.desc()).limit(1))
            receipt = await _create_message(
                db, turn.conversation_id, "assistant", "", turn_id=opening.id,
                intent={"editor_media": identity, "fingerprint": fingerprint,
                        "composition_id": composition_id, "version_id": version_id, "tool": name,
                        **({"export_preview": preview} if preview else {}),
                        "activity_id": str(activity_id) if activity_id else None},
            )
            if cached is not None:
                if name == "generate_image":
                    await _record_image(db, project, receipt, {**cached, "cache_hit": True})
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
                if name == "export_video":
                    text = (f"允许导出这个版本的 MP4 吗？最多使用 {need.quote_high} 积分。" if zh else
                            f"Authorize MP4 export of this version for up to {need.quote_high} credits?")
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
        return ToolObservation("Awaiting authorization.", stop_after_observation=True, awaiting_authorization=True)
    if turn.on_row_append and receipt.workflow_run_id and not receipt.intent.get("media_result"):
        await turn.on_row_append(receipt)
    receipt = await wait_for_media_result(turn.project, receipt)
    if turn.on_row_append:
        await turn.on_row_append(receipt)
    if version is not None:
        turn._inspected_version = str(version.id)
    facts = dict(receipt.intent["media_result"])
    if facts.get("role") == "export":
        turn._editor_export = facts
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
    if current_group_id() and facts.get("snapshot_id") and not facts.get("cache_hit"):
        turn.__dict__.setdefault("_generated_in_response", {})[facts["snapshot_id"]] = current_group_id()
    facts["delivered_to_chat"] = facts.get("status") == "available" and facts.get("role") != "export"
    labels = turn.__dict__.setdefault("_editor_labels", {})
    for key in ("snapshot_id", "alignment_id", "digest", "music_id", "analysis_digest", "output_id"):
        if facts.get(key):
            for token in (facts[key], facts[key][:8], facts[key][:12]):
                labels[token] = ("这份素材", "this media")
    return ToolObservation(json.dumps(facts), images=images, ok=facts["status"] == "available",
                           user_error=facts.get("error"), provider_outcome_unknown=facts["status"] == "provider_unknown")


async def wait_for_media_result(project, receipt):
    run_id = receipt.workflow_run_id
    # No open submission transaction while a worker owns the operation.
    while not receipt.intent.get("media_result"):
        await asyncio.sleep(0.5)
        async with AsyncSessionLocal() as db:
            run = await db.get(WorkflowRun, run_id)
            if run is None:
                raise ValueError("The submitted media request is unavailable.")
            if run.status not in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
                settled = await settle_media_receipt(db, project, run)
                if settled is not None:
                    receipt = settled
                await db.commit()
    return receipt


async def continue_media_turn(db, project, receipt, **hooks):
    """Continue the original user request after an answered quote or a lost API process."""
    from app.chat.editor_recovery import editor_lock_key, report_committed_edits, settle_interrupted_members, settle_media_activity
    from app.chat.service import _plan_turn, _prefers_zh, list_conversation_messages
    from app.metering import bind_conversation_turn, fold_conversation_usage
    from app.models.schemas import ChatRequest

    turn_id = receipt.turn_id
    if not await db.scalar(select(func.pg_try_advisory_xact_lock(editor_lock_key(turn_id)))):
        return None
    async with AsyncSessionLocal() as state:
        opening = await state.get(Message, turn_id, with_for_update=True, populate_existing=True)
        if not opening or opening.turn_state != "in_flight":
            return None
        newest = await state.scalar(select(Message.id).where(
            Message.turn_id == turn_id, Message.intent.has_key("editor_media"),
        ).order_by(Message.seq.desc()).limit(1))
        if newest != receipt.id:
            return None
        await settle_media_activity(state, receipt)
        await settle_interrupted_members(state, turn_id)
        identity = receipt.intent["editor_media"]
        latest = await state.scalar(select(Message.id).where(
            Message.conversation_id == opening.conversation_id, Message.role == "user",
        ).order_by(Message.seq.desc()).limit(1))
        comp_id = receipt.intent.get("composition_id")
        head = await state.scalar(select(Composition.current_version_id).where(
            Composition.id == UUID(comp_id), Composition.owner_id == project.user_id,
            Composition.origin_project_id == project.id,
        )) if comp_id else None
        intent = opening.intent or {}
        # Once a continuation has begun, its own version receipts are authoritative.
        # An interrupted edit with committed writes is reported, never applied a second time.
        exported = receipt.intent["media_result"].get("role") == "export"
        if (not comp_id or str(head) != receipt.intent["version_id"] or latest != turn_id or
                (intent.get("editor_commits") and not exported) or intent.get("resumed_media") == identity or
                receipt.intent["media_result"]["status"] != "available"):
            await report_committed_edits(state, opening)
            available = receipt.intent["media_result"]["status"] == "available"
            if comp_id and str(head) != receipt.intent["version_id"] and available and not intent.get("editor_commits"):
                notice = ("素材已保存。生成期间影片已有新版本，请在当前版本选择插入位置。"
                          if _prefers_zh(opening.content) else
                          "The media is saved. The film changed during generation. Select a position in the current version.")
                if exported:
                    notice = ("原版本已导出，待检查正式成片。" if _prefers_zh(opening.content)
                              else "The previous version was exported and awaits Output review.")
                await _create_message(state, opening.conversation_id, "assistant", notice, turn_id=turn_id)
            opening.turn_state = "settled" if available and not comp_id else "failed"
            await state.commit()
            return None
        opening.intent = {**intent, "resumed_media": identity}
        await state.commit()
    conversation = await db.get(Conversation, opening.conversation_id)
    if hooks.get("on_loop_event") is None:
        from app.chat.routes import persistent_activity_hooks

        durable, _ = persistent_activity_hooks(db, conversation.id, turn_id)
        hooks.update(durable)
    with bind_conversation_turn(conversation_id=conversation.id, turn_id=turn_id, project_id=project.id) as usage:
        follow_up, _, _, _ = await _plan_turn(
            db, project.user_id, conversation, project,
            ChatRequest(project_id=project.id, message=opening.content, mentions=opening.mentions or []),
            recent=await list_conversation_messages(db, conversation.id), turn_id=turn_id,
            authorized_media=receipt, **hooks,
        )
    await fold_conversation_usage(db, user_id=project.user_id, project_id=project.id, accrued=usage.accrued)
    finished = await _lock_turn_for_transcript_write(db, turn_id, require_in_flight=True)
    finished.turn_state = "settled"
    await db.commit()
    return follow_up
