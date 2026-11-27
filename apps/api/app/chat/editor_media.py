"""Execute media calls against the existing queue and return measured project media."""

import asyncio
import json
import re
from uuid import UUID, uuid5

from sqlalchemy import func, select

from app.agents.tool_loop import ToolObservation
from app.agents.tool_progress import current_call_id, current_group_id
from app.chat.service import (
    _create_message, _lock_turn_for_transcript_write, latest_pending_question,
    resolve_confirmation_need,
)
from app.models.database import AsyncSessionLocal
from app.models.schemas import canonical_json_hash
from app.models.tables import Composition, Conversation, ExportJob, Message, Output, Project
from app.pipeline.media_jobs import KINDS, enqueue_media, media_quote
from app.tools.video.audio_playback import playback_item


def _requests_paid_media(words, tool):
    """Recognize a direct request for this medium; ambiguous scope uses its quote."""
    medium_en, medium_zh = {
        "generate_voice": (r"voiceover|voice-over|narration|recording", r"旁白|配音|录音"),
        "generate_image": (r"image|picture|illustration", r"图片|图像|插图"),
        "generate_music": (r"music|score", r"音乐|配乐"),
    }[tool]
    # Conditional requests, existing material and quoted speech cannot grant
    # a new paid operation. The user can authorize the exact quote instead.
    if re.search(r"\b(?:if|unless|instead|existing|without|not|never|don't|avoid|whether)\b|[?？]|如果|除非|已经|不要|不用|不必|别", words, re.I):
        return False
    request = rf"^(?:please\s+)?(?:generate|create|record|make)\s+(?:(?:an?|the|short|new|english|chinese)\s+){{0,5}}(?:{medium_en})\b"
    chinese = rf"^(?:请|帮我|请帮我)?(?:生成|制作|录制|录|画)(?:一(?:段|张|句)|新的|简短的|中文|英文){{0,4}}(?:{medium_zh})"
    # Require an unambiguous end of the requested noun, e.g. “image of ...”.
    # “Generate an image prompt” and “录制旁白的教程” ask for different work.
    ending = r"(?:[.!。！]?\s*$|\s+(?:of|depicting|saying|reading)\s+)"
    zh_ending = r"(?:[。！!]?\s*$|[：:，,])"
    return bool(re.match(request + ending, words.strip(), re.I)
                or re.match(chinese + zh_ending, words.strip()))


async def _record_audio(db, project, receipt, result, request):
    music = "score_spec" in result or "music" in result
    effect = "sound_recipe" in result
    role = "music" if music else ("effect" if effect else "narration")
    item = await playback_item(db, project, role, result, request)
    facts = {
        "status": "available", "project_id": str(project.id), "role": role, "snapshot_id": item["snapshot_id"],
        "digest": item["digest"], "duration_seconds": item["duration_seconds"],
        "analysis_digest": item["analysis_digest"], "peak": max(item["peaks"]),
        "cache_hit": result["cache_hit"], "added_to_composition": False,
    }
    if music:
        music_info = result.get("music") or {}
        score_spec = result.get("score_spec")
        bpm = (
            score_spec["bpm"]
            if isinstance(score_spec, dict) and "bpm" in score_spec
            else ((result.get("beat_grid") or {}).get("bpm"))
        )
        facts.update(
            music_id=music_info["music_id"],
            score={"bpm": bpm, "style": request.get("style"), "lufs": music_info.get("lufs")},
        )
    elif effect:
        sr = result["sound_recipe"]
        facts.update(
            recipe_id=sr["recipe_id"],
            recipe_version=sr["recipe_version"],
            params=sr["params"],
            **({"tune": sr["tune"]} if "tune" in sr else {}),
            seed=sr["seed"],
            spec_sha256=sr["spec_sha256"],
            acoustics=result["acoustics"],
        )
    else:
        facts.update(alignment_id=result["alignment_id"], text=request["text"],
                     language=request["language"], voice_id=request["voice_id"])
    receipt.intent = {**receipt.intent, "media_result": facts}
    zh = (project.language or "").startswith("zh")
    if music:
        receipt.content = "配乐已生成，可以试听。" if zh else "The score is ready to play."
    elif effect:
        receipt.content = "音效已生成，可以试听。" if zh else "The sound effect is ready to play."
    else:
        receipt.content = "旁白已生成，可以试听。" if zh else "The voice recording is ready to play."
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
    facts = {"status": "available", "project_id": str(project.id), "role": "image", "snapshot_id": str(snapshot.id), "digest": snapshot.digest,
             "dimensions": asset["analysis"]["media_facts"]["dimensions"], "review": review["status"],
             "review_summary": review["summary"], "cache_hit": asset.get("cache_hit", False),
             "added_to_composition": False}
    receipt.intent = {**receipt.intent, "media_result": facts}
    receipt.blocks = [{"kind": "image_preview", "project_id": str(project.id), "snapshot_id": str(snapshot.id),
                       "digest": snapshot.digest, "description": review["summary"]}]
    receipt.content = "图片已生成，可查看审阅结果。" if (project.language or "").startswith("zh") else "The image is ready for review."
    return receipt


async def deliver_video(db, turn, output_id, base):
    import hashlib
    from app.tools.video.review import read_output_video
    from app.pipeline.outputs import is_delivered_output

    group = current_group_id()
    if group and group == getattr(turn, "_video_review_group", None):
        raise ValueError("Read the Output review before deciding whether to deliver.")
    report = getattr(turn, "_video_review_report", None) or {}
    if (report.get("output_id") != str(output_id) or not report.get("frames")
            or any(report.get(k) != v for k, v in base.items())):
        raise ValueError("Delivery requires a review of this exact Output and selected version.")
    output = await db.scalar(select(Output).where(Output.id == output_id, Output.project_id == turn.project.id))
    if output is None or not is_delivered_output(output) or output.render_spec.get("provenance") != base:
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
        message = await _create_message(db, turn.conversation_id, "assistant", "", turn_id=opening.id,
            intent={"output_refs": [str(output_id)], "reviewed_version": base,
                    "reviewed_at": report["reviewed_at"], "video_sha256": report["video_sha256"]})
        await db.commit()
        if turn.on_row_append:
            await turn.on_row_append(message)
    charge = (await db.execute(
        select(Message.turn_id, Message.intent["media_result"]["charged_credits"].as_integer())
        .join(ExportJob, ExportJob.receipt_id == Message.id)
        .where(ExportJob.id == output.id, ExportJob.project_id == turn.project.id)
    )).one_or_none()
    turn._editor_delivery = {
        "output_id": str(output_id),
        "workbench_link": f"#workbench:output/{output_id}",
        **base,
        "delivered_to_chat": True,
    }
    if charge:
        turn._editor_delivery["export_charged_this_opening"] = charge[1] if charge[0] == turn.turn_id else 0
        turn._editor_delivery["original_export_charge"] = charge[1]
    return ToolObservation(json.dumps(turn._editor_delivery))


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
        if auth.get("recovery_quote"):
            return receipt
        return None
    if receipt.intent.get("composition_id"):
        head = await db.scalar(select(Composition.current_version_id).where(
            Composition.id == UUID(receipt.intent["composition_id"]), Composition.owner_id == project.user_id,
            Composition.origin_project_id == project.id,
        ))
        if str(head) != receipt.intent["version_id"]:
            raise ValueError("The work changed before authorization.")
    is_export = receipt.intent.get("tool") == "export_video"
    if is_export:
        from app.editing.store import get_video_version
        from app.tools.video.export import export_quote, fixed_export_spec

        comp, version = await get_video_version(db, owner_id=project.user_id, version_id=UUID(receipt.intent["version_id"]))
        spec, missing = await fixed_export_spec(db, project, comp, version)
        if missing:
            raise ValueError("The authorized version needs fixed media.")
        estimate = await export_quote(db, spec)
    else:
        params = auth.get("params")
        if params is None:
            raise ValueError("Request a fresh media quote for this saved authorization.")
        estimate = await media_quote(db, receipt.intent["tool"], params, project=project)
    if estimate is None or estimate.total[1] > auth["quote"]["total"][1]:
        raise ValueError("The media quote has changed.")
    execution = await _create_message(db, receipt.conversation_id, "assistant", "", turn_id=receipt.turn_id,
                                      intent={k: v for k, v in receipt.intent.items() if k != "media_permission"})
    if is_export:
        from app.pipeline.export_jobs import enqueue_export
        await enqueue_export(db, project, execution, spec, estimate.total[1])
    else:
        await enqueue_media(db, project, execution, params, estimate.total[1])
    execution.intent = {**execution.intent, "authorization_ref": str(receipt.id)}
    receipt.intent = {"media_permission": auth, "native_call_id": execution.intent["native_call_id"],
                      "fingerprint": execution.intent["fingerprint"], "media_receipt_id": str(execution.id)}
    return execution


async def submit_editor_media(turn, name, args, composition, version, call_id):
    if name == "generate_voice":
        from app.chat.editor_create import voice_generation_forbidden

        if voice_generation_forbidden(getattr(turn, "text", "")):
            raise ValueError("The user explicitly disallowed narration generation.")
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
        replay_ids = (opening.intent or {}).get("media_replay_ids", {})
        original = replay_ids.get(identity, identity)
        receipt = await db.scalar(select(Message).where(
            Message.turn_id == opening.id, Message.intent["editor_media"].as_string() == original,
        ))
        if receipt and name == "export_video" and receipt.intent.get("composition_id") == composition_id:
            # The native call keeps its original export pin when a retry sees a newer head.
            fingerprint = canonical_json_hash({"tool": name, "version": receipt.intent["version_id"], "params": params})
        if not receipt and name == "export_video":
            receipt = await db.scalar(select(Message).where(
                Message.turn_id == opening.id, Message.intent["fingerprint"].astext == fingerprint,
                (Message.intent.has_key("export_job") | Message.intent.has_key("media_permission")),
            ).order_by(Message.seq.desc()).limit(1))
        if not receipt and (opening.intent or {}).get("resumed_media"):
            # A resumed model can repeat the exact request with a fresh native
            # id. Return the existing receipt without acquiring another hold.
            receipt = await db.scalar(select(Message).where(
                Message.turn_id == opening.id, Message.intent["fingerprint"].astext == fingerprint,
                Message.intent["media_result"]["status"].astext.in_(("available", "declined", "provider_unknown")),
            ).order_by(Message.seq).limit(1))
        if receipt:
            if receipt.intent["fingerprint"] != fingerprint:
                raise ValueError("This call already belongs to different parameters.")
            if receipt.intent.get("media_result") or receipt.question or receipt.intent.get("export_job") or receipt.intent.get("media_job"):
                existing = receipt.intent.get("editor_media")
                if existing and original != existing:
                    opening.intent = {**(opening.intent or {}), "media_replay_ids": {**replay_ids, identity: existing}}
                    await db.commit()
                return receipt
        else:
            from app.chat.editor_create import media_generation_forbidden

            if name in KINDS and media_generation_forbidden(opening.content or ""):
                raise ValueError("Use the existing project sources. The user excluded new media.")
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
            if pending and (pending.intent or {}).get("media_permission"):
                raise ValueError("Resolve the outstanding authorization before generating more media.")
            from app.chat.video_turn_seats import asks_for_export, draft_only_request

            preview = None
            if name == "export_video":
                if draft_only_request(opening.content or ""):
                    raise ValueError("The current request is limited to the editable work and its preview.")
                preview = getattr(turn, "_editor_last_preview", None) or {}
                from app.tools.video.export import export_quote, fixed_export_spec

                spec, missing = await fixed_export_spec(db, project, composition, version)
                if not missing and (preview.get("composition_version_id") != version_id
                        or preview.get("content_digest") != version.content_digest
                        or not preview.get("mp4_sha256")
                        or current_group_id() and preview.get("decision") == current_group_id()):
                    raise ValueError("Inspect actual preview evidence for this version before deciding to export it.")
            elif name == "generate_image":
                from app.tools.video.visual_assets import SceneAssetSpec, preflight_scene_svgs

                source = ({"kind": "controlled_svg", "program": args.svg} if args.svg else
                          {"kind": "minimax_image", "prompt": args.prompt})
                spec = SceneAssetSpec(scene_id="editor_image", intent=args.prompt, source=source)
                basis = {"user_words": [opening.content], "scene_roles": {spec.scene_id: opening.content}}
                if args.evidence_snapshot_id:
                    from app.models.tables import SourceSnapshot
                    from app.tools.video.preparation import frozen_source_lines

                    source = await db.get(SourceSnapshot, args.evidence_snapshot_id)
                    if (source is None or source.kind != "web" or source.owner_id != turn.user_id
                            or source.origin_project_id != project.id):
                        raise ValueError("Select a verified webpage from this project.")
                    lines = frozen_source_lines(source)
                    if not lines:
                        raise ValueError("The selected webpage has no verifiable text.")
                    basis["source_evidence"] = "\n".join(line["text"] for line in lines)[:4000]
                preflight_scene_svgs([spec])
                params = {"scene": spec.model_dump(mode="json"), "review_basis": basis}
            activity_id = await db.scalar(select(Message.id).where(
                Message.turn_id == opening.id, Message.intent["frame"]["status"].astext == "active",
                Message.intent["frame"]["call_id"].astext == call_id,
            ).order_by(Message.seq.desc()).limit(1))
            receipt = await _create_message(
                db, turn.conversation_id, "assistant", "", turn_id=opening.id,
                intent={"editor_media": identity, "native_call_id": call_id, "fingerprint": fingerprint,
                        "composition_id": composition_id, "version_id": version_id, "tool": name,
                        **({"export_preview": preview} if preview else {}),
                        "activity_id": str(activity_id) if activity_id else None},
            )
            if name == "export_video":
                if missing:
                    receipt.intent = {**receipt.intent, "media_result": {
                        "status": "dependencies_not_ready", "role": "export", "dependencies": missing,
                        "error": "Resolve the missing sources, verify their timeline bindings, then preview the saved version.",
                    }}
                    await db.commit()
                    return receipt
                estimate = await export_quote(db, spec)
            else:
                estimate = await media_quote(db, name, params, project=project)
            need = await resolve_confirmation_need(db, turn.user_id, estimate)
            quote = estimate.model_dump(mode="json") if estimate else None
            if not quote:
                raise ValueError("A bounded media quote is unavailable.")
            # Account auto-approval covers requested video/promo production
            # (voiceover, music, visuals, and export). Non-production edits or
            # questions still require explicit consent before spending credits.
            recovering = bool((opening.intent or {}).get("resumed_media"))
            auto_production = asks_for_export(opening.content or "") and not recovering
            export_needs_consent = False
            if name == "export_video" and not auto_production:
                confirmed = (opening.intent or {}).get("video_confirmation") or {}
                export_needs_consent = not (
                    confirmed.get("action") == "produce" and confirmed.get("base_ref") == turn._video_base_ref
                )
            paid = estimate.total[1] > 0
            another_paid_call = False
            if paid and not auto_production:
                another_paid_call = await db.scalar(select(Message.id).where(
                    Message.turn_id == opening.id, Message.id != receipt.id,
                    Message.intent["tool"].astext == name,
                    (Message.intent.has_key("export_job") | Message.intent.has_key("media_job")
                     | Message.intent.has_key("media_permission")),
                ).limit(1)) is not None
            needs_media_consent = paid and name in KINDS and not auto_production and (
                recovering or not _requests_paid_media(opening.content or "", name)
            )
            fixed_reuse = recovering and not paid and name in {"generate_voice", "generate_image"}
            if another_paid_call or (recovering and paid) or needs_media_consent or export_needs_consent or (need.requires_confirmation and not fixed_reuse):
                zh = (project.language or "").startswith("zh")
                text = (f"允许这次素材生成吗？最多使用 {need.quote_high} 积分。" if zh else
                        f"Authorize this media generation for up to {need.quote_high} credits?")
                if name == "export_video":
                    text = (f"允许导出这个版本的 MP4 吗？最多使用 {need.quote_high} 积分。" if zh else
                            f"Authorize MP4 export of this version for up to {need.quote_high} credits?")
                if name in KINDS:
                    zh_name, en_name = {"generate_voice": ("旁白", "narration"), "generate_music": ("音乐", "music"),
                                        "generate_image": ("图片", "image")}[name]
                    detail = args.model_dump(mode="json", exclude_none=True)
                    label = detail.get("prompt") or detail.get("text") or detail.get("style") or ""
                    text = (f"允许为「{label}」生成{zh_name}吗？最多使用 {estimate.total[1]} 积分。" if zh else
                            f"Generate {en_name} for “{label}” for up to {estimate.total[1]} credits?")
                receipt.content = text
                receipt.question = {"kind": "question", "question": text,
                                    "options": [{"id": "approve", "label": "允许" if zh else "Allow"},
                                                {"id": "decline", "label": "取消" if zh else "Decline"}]}
                receipt.intent = {**receipt.intent, "media_permission": {"quote": quote, "recovery_quote": recovering, **({"params": params} if name in KINDS else {})}}
                await db.commit()
                return receipt
            if name == "export_video":
                from app.pipeline.export_jobs import enqueue_export
                await enqueue_export(db, project, receipt, spec, estimate.total[1])
            else:
                await enqueue_media(db, project, receipt, params, estimate.total[1])
            await db.commit()
        return receipt


async def execute_generate_sfx(turn, args, composition, version):
    """Local zero-credit deterministic SFX synthesis fast path.

    Skips paid confirmation dialog while preserving opening lock, Stop check,
    native-call idempotency, single-flight dedupe, and durable Chat playback receipt.
    """
    from app.chat.editor_recovery import editor_lock_key
    from app.chat.service import TurnStopped
    from app.editing.catalog import SOUND_RECIPE_CATALOG, build_sound_spec, sound_spec_digest
    from app.editing.store import content_of
    from app.models.tables import SourceSnapshot
    from app.tools.video.sfx_synthesis import SfxSynthesisError, synthesize_project_sfx

    call_id = current_call_id()
    if not turn.turn_id or not call_id or turn.project is None:
        raise ValueError("A durable message, project, and native call identity are required.")

    recipe_id = args.recipe_id
    explicit_tune = args.tune.model_dump(exclude_none=True) if args.tune else {}
    tune = explicit_tune.copy()
    merged_params = dict(args.params or {})
    seed = args.seed
    if args.base_clip_id:
        if version is None:
            raise ValueError("Select a saved composition before revising an existing SFX clip.")
        content = content_of(version)
        target_clip = next(
            (c for t in content.timeline.tracks for c in t.clips if c.clip_id == args.base_clip_id),
            None,
        )
        if target_clip is None or target_clip.source is None or target_clip.object.kind != "audio":
            raise ValueError("Select an existing sound-effect audio clip to revise.")
        async with AsyncSessionLocal() as db:
            base_snap = await db.get(SourceSnapshot, target_clip.source.snapshot_id)
        origin = ((base_snap.meta or {}).get("origin") or {}) if base_snap else {}
        if origin.get("kind") != "sound_recipe":
            raise ValueError("The selected clip was not synthesized from a sound recipe.")
        if recipe_id is None:
            recipe_id = origin["recipe_id"]
        if recipe_id == origin.get("recipe_id"):
            tune = {**(origin.get("tune") or {}), **tune}
            base_params = dict(origin.get("params") or {})
            base_params.update(merged_params)
            merged_params = base_params
            if seed is None:
                seed = origin.get("seed")
    if not recipe_id:
        raise ValueError("Specify a sound recipe_id or a base_clip_id to revise.")

    if recipe_id not in SOUND_RECIPE_CATALOG:
        raise ValueError(f"Unknown sound recipe: {recipe_id}")
    if args.target_duration_ms is not None and "length_scale" not in explicit_tune:
        from app.editing.catalog import SOUND_ACOUSTICS, normalize_sound_params

        base_ms = normalize_sound_params(recipe_id, merged_params).get("length", SOUND_ACOUSTICS[recipe_id]["duration_ms"])
        tune["length_scale"] = args.target_duration_ms / base_ms
    spec = build_sound_spec(recipe_id, params=merged_params, seed=seed, tune=tune)
    spec_sha256 = sound_spec_digest(spec)
    identity = str(uuid5(turn.turn_id, call_id))
    composition_id = str(composition.id) if composition else None
    version_id = str(version.id) if version else None
    fingerprint = canonical_json_hash({
        "tool": "generate_sfx",
        "spec_sha256": spec_sha256,
        "place_at_seconds": args.place_at_seconds,
        "align_peak_at_seconds": args.align_peak_at_seconds,
        "gain_db": args.gain_db,
    })

    def _sfx_observation(payload: dict) -> ToolObservation:
        if payload.get("placed") and payload.get("version_id") and payload.get("content_digest"):
            return ToolObservation(
                json.dumps(payload),
                ok=payload.get("status") == "available",
                version_saved=True,
            )
        return ToolObservation(json.dumps(payload), ok=payload.get("status") == "available")

    admission = turn.__dict__.setdefault("_media_admission", asyncio.Lock())
    async with admission:
        await turn.db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id))))
        async with AsyncSessionLocal() as db:
            opening = await _lock_turn_for_transcript_write(db, turn.turn_id)
            project = await db.scalar(select(Project).join(Conversation, Conversation.project_id == Project.id).where(
                Conversation.id == opening.conversation_id, Conversation.id == turn.conversation_id,
                Conversation.user_id == turn.user_id, Project.id == turn.project.id, Project.user_id == turn.user_id,
            ))
            if project is None or opening.role != "user":
                raise ValueError("SFX request is outside the current project.")
            if any(edit["request"] == identity for edit in (opening.intent or {}).get("editor_commits", [])):
                raise ValueError("This call already belongs to a different operation.")
            receipt = await db.scalar(select(Message).where(
                Message.turn_id == opening.id, Message.intent["editor_media"].as_string() == identity,
            ))
            if receipt is not None:
                if receipt.intent.get("fingerprint") != fingerprint:
                    raise ValueError("This call already belongs to different SFX parameters.")
                if receipt.intent.get("media_result"):
                    facts = dict(receipt.intent["media_result"])
                    facts["delivered_to_chat"] = facts.get("status") == "available"
                    return _sfx_observation(facts)
            if opening.turn_state != "in_flight":
                raise TurnStopped(str(turn.turn_id))

            activity_id = await db.scalar(select(Message.id).where(
                Message.turn_id == opening.id, Message.intent["frame"]["status"].astext == "active",
                Message.intent["frame"]["call_id"].astext == call_id,
            ).order_by(Message.seq.desc()).limit(1))

    synth_error: SfxSynthesisError | None = None
    result = None
    try:
        result = await synthesize_project_sfx(
            owner_id=turn.user_id,
            project_id=turn.project.id,
            recipe_id=spec["recipe_id"],
            params=spec["params"],
            **({"tune": spec["tune"]} if tune else {}),
            seed=spec["seed"],
        )
    except SfxSynthesisError as exc:
        synth_error = exc

    recipe_meta = SOUND_RECIPE_CATALOG[spec["recipe_id"]]
    placed_version_info: dict | None = None
    # Secondary Stop fence under opening lock before writing Message or emitting SSE.
    async with admission:
        await turn.db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id))))
        async with AsyncSessionLocal() as db:
            opening = await _lock_turn_for_transcript_write(db, turn.turn_id)
            if opening.turn_state != "in_flight":
                raise TurnStopped(str(turn.turn_id))
            existing = await db.scalar(select(Message).where(
                Message.turn_id == opening.id, Message.intent["editor_media"].as_string() == identity,
            ))
            if existing is not None and existing.intent.get("media_result"):
                facts = dict(existing.intent["media_result"])
                facts["delivered_to_chat"] = facts.get("status") == "available"
                return _sfx_observation(facts)
            if existing is None:
                existing = await _create_message(
                    db, turn.conversation_id, "assistant", "", turn_id=opening.id,
                    intent={
                        "editor_media": identity,
                        "native_call_id": call_id,
                        "fingerprint": fingerprint,
                        "composition_id": composition_id,
                        "version_id": version_id,
                        "tool": "generate_sfx",
                        "operation": "generate_sfx",
                        "activity_id": str(activity_id) if activity_id else None,
                    },
                )
            if synth_error is not None:
                existing.intent = {
                    **existing.intent,
                    "media_result": {"status": "failed", "role": "effect", "error": str(synth_error)},
                }
                await db.commit()
                return ToolObservation(str(synth_error), ok=False, user_error=str(synth_error))
            project = await db.get(Project, turn.project.id)
            row = await _record_audio(
                db, project, existing, result,
                {"recipe_id": spec["recipe_id"], "title": f"{recipe_meta['name']} ({spec['recipe_id']})"},
            )
            media_facts = dict(row.intent["media_result"])
            place_at = args.place_at_seconds
            if args.align_peak_at_seconds is not None:
                place_at = max(0, args.align_peak_at_seconds - result["acoustics"]["peak_offset_ms"] / 1000)
            if place_at is not None and composition is not None:
                from app.editing.revisions import fixed_audio_ops
                from app.editing.store import apply_composition_edits
                from app.editing.timing import (
                    output_ticks_to_source_ticks,
                    seconds_to_ticks,
                    source_ticks_to_output_ticks,
                )
                from app.models.tables import CompositionVersion

                comp = await db.scalar(select(Composition).where(
                    Composition.id == composition.id,
                    Composition.owner_id == turn.user_id,
                    Composition.origin_project_id == turn.project.id,
                ))
                cur_version = (
                    await db.get(CompositionVersion, comp.current_version_id)
                    if comp is not None and comp.current_version_id is not None
                    else None
                )
                snap = await db.get(SourceSnapshot, UUID(media_facts["snapshot_id"]))
                if comp is not None and cur_version is not None and snap is not None and snap.duration_ticks:
                    comp_content = content_of(cur_version)
                    rate = comp_content.settings.timebase
                    limit = max(
                        [c.range.end for t in comp_content.timeline.tracks for c in t.clips]
                        + [s.range.end for s in comp_content.scenes]
                        + [0]
                    )
                    start = seconds_to_ticks(place_at, rate)
                    if limit <= 0 or start >= limit:
                        raise ValueError(
                            f"place_at_seconds ({place_at:g}s) must fall strictly before the "
                            f"composition end ({limit / rate:g}s)."
                        )
                    raw_end = start + source_ticks_to_output_ticks(snap.duration_ticks, rate)
                    if raw_end > limit:
                        end = limit
                        source_end = max(1, output_ticks_to_source_ticks(end - start, rate))
                    else:
                        end = raw_end
                        source_end = snap.duration_ticks

                    def _overlaps(t):
                        return any(c.range.start < end and start < c.range.end for c in t.clips)

                    existing_effects = sorted(
                        (t for t in comp_content.timeline.tracks if t.kind == "audio" and t.role == "effect"),
                        key=lambda t: t.order,
                    )
                    free_track = next((t for t in existing_effects if not _overlaps(t)), None)
                    if free_track is not None:
                        track_id = free_track.track_id
                    else:
                        used_ids = {t.track_id for t in comp_content.timeline.tracks}
                        track_id = "trk_editor_effect"
                        idx = 2
                        while track_id in used_ids:
                            track_id = f"trk_editor_effect_{idx}"
                            idx += 1

                    gain_db = args.gain_db if args.gain_db is not None else -14.5
                    clip_id = f"clp_sfx_{identity.replace('-', '')[:16]}"
                    object_id = f"obj_sfx_{identity.replace('-', '')[:16]}"
                    ops = fixed_audio_ops(
                        comp_content,
                        source_id=snap.id,
                        source_digest=snap.digest,
                        track_id=track_id,
                        role="effect",
                        clip_id=clip_id,
                        object_id=object_id,
                        scene_id=None,
                        start=start,
                        end=end,
                        source_start=0,
                        source_end=source_end,
                        gain_db=gain_db,
                    )
                    _, saved, _ = await apply_composition_edits(
                        db,
                        owner_id=turn.user_id,
                        composition_id=comp.id,
                        base_version_id=cur_version.id,
                        base_digest=cur_version.content_digest,
                        request_id=f"sfx_place:{identity}",
                        skill_provenance=cur_version.skill_provenance,
                        ops=ops,
                    )
                    media_facts.update(
                        added_to_composition=True,
                        placed=True,
                        clip_id=clip_id,
                        track_id=track_id,
                        start_seconds=start / rate,
                        end_seconds=end / rate,
                        gain_db=gain_db,
                        composition_id=str(comp.id),
                        version_id=str(saved.id),
                        version=saved.version,
                        content_digest=saved.content_digest,
                    )
                    row.intent = {
                        **row.intent,
                        "media_result": media_facts,
                        "silent_chat_receipt": True,
                    }
                    placed_version_info = {
                        "composition_id": str(comp.id),
                        "version_id": str(saved.id),
                        "version": saved.version,
                        "content_digest": saved.content_digest,
                        "clip_id": clip_id,
                        "object_id": object_id,
                        "start_seconds": start / rate,
                        "end_seconds": end / rate,
                    }
                else:
                    media_facts["placed"] = False
                    media_facts["next_step"] = "Call insert_audio with this snapshot_id to place the SFX onto the timeline."
                    row.intent = {**row.intent, "media_result": media_facts}
            else:
                media_facts["placed"] = False
                media_facts["next_step"] = "Call insert_audio with this snapshot_id to place the SFX onto the timeline."
                row.intent = {**row.intent, "media_result": media_facts}
            await db.commit()
            receipt = row

    if turn.on_row_append and placed_version_info is None:
        await turn.on_row_append(receipt)
    facts = dict(receipt.intent["media_result"])
    facts["sync_cue"] = recipe_meta["sync_cue"]
    facts["mix_hint"] = recipe_meta["mix_hint"]
    facts["delivered_to_chat"] = placed_version_info is None
    labels = turn.__dict__.setdefault("_editor_labels", {})
    for key in ("snapshot_id", "digest", "analysis_digest", "spec_sha256"):
        if facts.get(key):
            for token in (facts[key], facts[key][:8], facts[key][:12]):
                labels[token] = ("这份音效", "this sound effect")
    if placed_version_info is not None:
        from app.chat.editor import _remember_labels

        new_base_ref = {
            "composition_id": placed_version_info["composition_id"],
            "composition_version_id": placed_version_info["version_id"],
            "content_digest": placed_version_info["content_digest"],
        }
        turn._video_base_ref = new_base_ref
        turn._inspected_version = placed_version_info["version_id"]
        group = current_group_id()
        if group:
            previous_write = getattr(turn, "_batch_commit", None)
            new_ids = {placed_version_info["clip_id"], placed_version_info["object_id"]}
            if previous_write and previous_write[0] == group:
                new_ids.update(previous_write[2])
            turn._batch_commit = (group, new_base_ref, new_ids)
        _remember_labels(
            turn,
            [
                {
                    "clip_id": placed_version_info["clip_id"],
                    "object_id": placed_version_info["object_id"],
                    "start_seconds": placed_version_info["start_seconds"],
                    "end_seconds": placed_version_info["end_seconds"],
                }
            ],
            placed_version_info["version_id"],
            placed_version_info["content_digest"],
            placed_version_info["version"],
            composition_id=placed_version_info["composition_id"],
        )
    return _sfx_observation(facts)


async def generate_media(turn, name, args, composition, version):
    call_id = current_call_id()
    if not turn.turn_id or not call_id:
        raise ValueError("A durable message and native call identity are required.")
    from app.chat.editor_recovery import editor_lock_key

    # SQLAlchemy sessions are single-task. Serialize admission and the question row
    # on this opening, then wait for independent results outside the lock.
    admission = turn.__dict__.setdefault("_media_admission", asyncio.Lock())
    async with admission:
        await turn.db.execute(select(func.pg_advisory_xact_lock(editor_lock_key(turn.turn_id))))
        receipt = await submit_editor_media(turn, name, args, composition, version, call_id)
        if receipt.question and not receipt.answer:
            # The committed question belongs to a separate submission session.
            receipt = await turn.db.get(Message, receipt.id, populate_existing=True)
            turn.outcome = (receipt, turn.settled_pending)
            return ToolObservation("Awaiting authorization.", stop_after_observation=True, awaiting_authorization=True)
    if turn.on_row_append and (receipt.intent.get("export_job") or receipt.intent.get("media_job")) and not receipt.intent.get("media_result"):
        await turn.on_row_append(receipt)
    receipt = await wait_for_media_result(receipt, on_progress=turn.on_row_append)
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


async def wait_for_media_result(receipt, *, on_progress=None):
    # No open submission transaction while a worker owns the operation.
    while not receipt.intent.get("media_result"):
        await asyncio.sleep(0.5)
        async with AsyncSessionLocal() as db:
            prior_content = receipt.content
            receipt = await db.get(Message, receipt.id)
            if receipt is None:
                raise ValueError("Media receipt unavailable.")
            if on_progress and not receipt.intent.get("media_result") and receipt.content != prior_content:
                await on_progress(receipt)
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
        pending = await state.scalar(select(Message.id).where(
            Message.turn_id == turn_id, (Message.intent.has_key("media_job") | Message.intent.has_key("export_job")),
            ~Message.intent.has_key("media_result"),
        ).limit(1))
        if pending:
            return None
        newest = await state.scalar(select(Message.id).where(
            Message.turn_id == turn_id, Message.intent.has_key("editor_media"),
        ).order_by(Message.seq.desc()).limit(1))
        if newest != receipt.id:
            return None
        siblings = list(await state.scalars(select(Message).where(
            Message.turn_id == turn_id, (Message.intent.has_key("media_job") | Message.intent.has_key("export_job")),
            Message.intent.has_key("media_result"),
        ).order_by(Message.seq)))
        for member in siblings:
            await settle_media_activity(state, member)
        if not any(member.id == receipt.id for member in siblings):
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
        if exported and intent.get("resumed_media") == identity:
            delivered = await state.scalar(select(Message.id).where(
                Message.turn_id == turn_id,
                Message.intent["output_refs"].contains([receipt.intent["media_result"].get("output_id")]),
            ).limit(1))
            if delivered:
                opening.turn_state = "settled"
                await state.commit()
                return None
        review_pinned_export = exported and receipt.intent["media_result"]["status"] == "available" and latest != turn_id
        if ((comp_id and not exported and str(head) != receipt.intent["version_id"])
                or (latest != turn_id and not review_pinned_export) or
                (receipt.intent["media_result"]["status"] != "available" and
                 not any(member.intent["media_result"]["status"] == "available" for member in siblings))):
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
        attempts_key = "export_resume_attempts" if exported else "media_resume_attempts"
        attempts = int(intent.get(attempts_key, 0)) if intent.get("resumed_media") == identity else 0
        if attempts >= 3:
            opening.turn_state = "failed"
            await _create_message(state, opening.conversation_id, "assistant",
                "已保存的结果仍可查看，续行已中断。" if _prefers_zh(opening.content)
                else "The saved result is available. Continuation was interrupted.", turn_id=turn_id)
            await state.commit()
            return None
        intent = {**intent, attempts_key: attempts + 1}
        opening.intent = {**intent, "resumed_media": identity}
        await state.commit()
    conversation = await db.get(Conversation, opening.conversation_id)
    if hooks.get("on_loop_event") is None:
        from app.chat.routes import persistent_activity_hooks

        durable, _ = persistent_activity_hooks(db, conversation.id, turn_id)
        hooks.update(durable)
    with bind_conversation_turn(conversation_id=conversation.id, turn_id=turn_id, project_id=project.id) as usage:
        follow_up, _ = await _plan_turn(
            db, project.user_id, conversation, project,
            ChatRequest(project_id=project.id, message=opening.content, mentions=opening.mentions or []),
            recent=await list_conversation_messages(db, conversation.id), turn_id=turn_id,
            authorized_media=receipt, review_pinned_export=review_pinned_export, **hooks,
        )
    await fold_conversation_usage(db, user_id=project.user_id, project_id=project.id, accrued=usage.accrued)
    finished = await _lock_turn_for_transcript_write(db, turn_id, require_in_flight=True)
    pending = await latest_pending_question(db, opening.conversation_id)
    awaiting_quote = pending and pending.turn_id == turn_id and (pending.intent or {}).get("media_permission")
    finished.turn_state = "in_flight" if awaiting_quote else "settled"
    await db.commit()
    return follow_up
