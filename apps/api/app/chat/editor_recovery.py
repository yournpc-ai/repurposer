"""Reconcile interrupted Chat replies from editor writes in the immutable store."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select

from app.models.tables import Composition, CompositionVersion, Conversation, Message, Output, Project


def editor_lock_key(turn_id):
    # Stable signed bigint in PostgreSQL's advisory-lock key space.
    return int.from_bytes(turn_id.bytes[:8], "big", signed=True)


EDIT_LABELS = {
    "create_video": ("创建初稿", "create draft"),
    "instantiate_skill_blueprint": ("展开 Skill 蓝图", "instantiate Skill blueprint"),
    "insert_motion_block": ("加入动效组件", "insert motion block"),
    "update_motion_block": ("调整动效组件", "update motion block"),
    "set_composition_style": ("切换整片视觉风格", "apply visual style"),
    "apply_text_style": ("调整文字与字幕样式", "style text and captions"),
    "edit_audio_clip": ("调整音频片段", "edit audio clip"),
    "set_transition": ("设置转场", "set transition"),
    "insert_visual": ("插入图片", "insert image"),
    "insert_audio": ("插入音频", "insert audio"),
    "bind_clip_source": ("绑定固定素材", "bind fixed source"),
    "split_clip": ("分割", "split"),
    "remove_clip": ("移除片段", "remove clip"),
    "trim_clip": ("裁剪", "trim"),
    "extend_still": ("延长片段", "extend clip"),
    "move_clip": ("移动片段", "move"),
    "translate": ("平移画面", "translation"),
    "set_keyframe": ("调整关键帧", "adjust keyframe"),
    "scale": ("缩放", "scale"),
}


async def _committed_edits(db, opening):
    markers = (opening.intent or {}).get("editor_commits") or []
    if not markers:
        return []
    conversation = await db.get(Conversation, opening.conversation_id)
    rows = await db.scalars(
        select(CompositionVersion)
        .join(Composition, Composition.id == CompositionVersion.composition_id)
        .where(
            CompositionVersion.request_id.in_([m["request"] for m in markers]),
            Composition.owner_id == conversation.user_id,
            Composition.origin_project_id == conversation.project_id,
        )
    )
    versions = {v.request_id: v for v in rows}
    return [(m, versions[m["request"]]) for m in markers if m["request"] in versions]


def _saved_action(tool, before, saved, zh):
    label = EDIT_LABELS.get(tool, ("编辑作品", "edit work"))[0 if zh else 1]
    if tool != "extend_still" or before is None:
        return label
    from app.editing.store import content_of

    old = content_of(before)
    current = content_of(saved)
    # extend_still changes the end of one existing clip in the work's own timebase.
    ends = {clip.clip_id: clip.range.end for track in old.timeline.tracks for clip in track.clips}
    main_ends = [clip.range.end for track in current.timeline.tracks
                 if track.kind == "visual" and track.role == "main" for clip in track.clips]
    names = {"text": ("文字", "text"), "image": ("图片", "image"), "shape": ("图形", "shape")}
    for track in current.timeline.tracks:
        for clip in track.clips:
            previous_end = ends.get(clip.clip_id)
            if previous_end is None or clip.range.end <= previous_end:
                continue
            seconds = (clip.range.end - previous_end) / current.settings.timebase
            target = ("字幕", "caption") if track.role == "caption" else names.get(clip.object.kind, ("片段", "clip"))
            action = (f"{target[0]}延长了 {seconds:g} 秒" if zh
                      else f"extended the {target[1]} by {seconds:g} seconds")
            if main_ends and max(main_ends) < clip.range.end:
                action += "，这次修改没有延长主画面" if zh else ", without extending the main picture"
            return action
    return label


async def partial_edit_text(db, opening, reason, *, edits=None):
    """Read immutable commits and Chat receipts. The normal terminal writer owns the message."""
    from app.chat.service import _prefers_zh
    from app.pipeline.outputs import is_delivered_output

    if edits is None:
        edits = await _committed_edits(db, opening)
    if not edits:
        return None
    zh = _prefers_zh(reason)
    lines = [reason]
    works = {}
    for marker, version in edits:
        before = None
        if marker["tool"] == "extend_still" and version.base_version_id:
            before = await db.get(CompositionVersion, version.base_version_id)
        action = _saved_action(marker["tool"], before, version, zh)
        lines.append(f"已保存：{action}（第 {version.version} 版）。" if zh else f"Saved: {action} (version {version.version}).")
        works[version.composition_id] = version
    heads = dict((await db.execute(select(Composition.id, Composition.current_version_id)
                                   .where(Composition.id.in_(works)))).all())
    if any(heads[work] != version.id for work, version in works.items()):
        lines.append("此后作品还有其他已保存的修改。" if zh else "The draft has also changed since these edits.")

    # A historical card is usable only for its actual, still-visible Output.
    deliveries = await db.execute(
        select(Output, Message.turn_id)
        .join(Message, Message.intent["output_refs"].has_key(cast(Output.id, String)))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.conversation_id == opening.conversation_id,
            Message.role == "assistant",
            Message.intent["reviewed_version"] == Output.render_spec["provenance"],
            Output.project_id == Conversation.project_id,
            Output.composition_id.in_(works),
            Output.archived_at.is_(None),
            or_(Message.seq < opening.seq, Message.turn_id == opening.id),
        )
        .order_by(Message.seq.desc())
    )
    delivered, delivery_turn = next(
        ((output, turn_id) for output, turn_id in deliveries if is_delivered_output(output)), (None, None)
    )
    if delivered is not None:
        if delivery_turn == opening.id:
            lines.append("本轮已交付的成片可从交付消息打开。" if zh else "The file delivered this turn is available in its delivery message.")
        else:
            lines.append("之前交付的成片仍可从原消息打开。" if zh else "The previously delivered film is still available in its original message.")

    receipts = await db.scalars(select(Message).where(
        Message.turn_id == opening.id, Message.conversation_id == opening.conversation_id,
        or_(Message.intent.has_key("media_permission"), Message.intent.has_key("media_job"),
            Message.intent.has_key("export_job")),
    ).order_by(Message.seq))
    for receipt in receipts:
        intent = receipt.intent
        if intent.get("media_permission") and receipt.question and not receipt.answer:
            lines.append("还有一项费用等待确认。" if zh else "A charge still awaits your approval.")
        elif delivered is not None and (intent.get("media_result") or {}).get("output_id") == str(delivered.id):
            continue  # The delivery supersedes the worker's earlier “review pending” text.
        elif (intent.get("export_job") or intent.get("media_job")) and receipt.content:
            # This receipt is the worker's durable status, including errors/unknowns.
            lines.append(receipt.content)
    lines.append("可以从当前稿继续修改。" if zh else "You can continue editing the current draft.")
    return "\n".join(lines)


async def report_committed_edits(db, opening, *, failure_detail=None):
    from app.chat.editor import EDITOR_TOOLS
    from app.chat.service import _create_message, _prefers_zh

    edits = await _committed_edits(db, opening)
    if not edits:
        return
    done = {}
    for marker, _ in edits:
        if marker.get("activity_row"):
            done[UUID(marker["activity_row"])] = next(
                t.presentation.done_key for t in EDITOR_TOOLS if t.name == marker["tool"]
            )
    activities = await db.scalars(
        select(Message).where(
            Message.turn_id == opening.id,
            Message.intent["type"].astext == "activity",
            Message.intent["frame"]["status"].astext.in_(["active", "cancelled"]),
        )
    )
    for row in activities:
        frame = dict(row.intent["frame"])
        if row.id in done:
            frame.update(status="completed", key=done[row.id])
        elif frame["status"] == "active":
            frame["status"] = "cancelled"
        if frame.get("group_id"):
            frame["call_state"] = "not_executed" if frame.get("call_state") == "queued" else frame["status"]
        frame["settled_at"] = datetime.now(UTC).isoformat()
        row.intent = {**row.intent, "frame": frame}
    reason = failure_detail or ("本轮已中断。" if _prefers_zh(opening.content) else "This turn was interrupted.")
    text = await partial_edit_text(db, opening, reason, edits=edits)
    return await _create_message(
        db,
        opening.conversation_id,
        "assistant",
        text,
        turn_id=opening.id,
        intent={"type": "editor_recovery" if failure_detail is None else "turn_failed"},
    )


async def settle_interrupted_members(db, turn_id):
    active = await db.scalars(select(Message).where(
        Message.turn_id == turn_id, Message.intent["frame"].has_key("group_id"),
        Message.intent["frame"]["status"].astext == "active"))
    for member in active:
        frame = dict(member.intent["frame"])
        frame.update(status="cancelled", settled_at=datetime.now(UTC).isoformat(),
                     call_state="not_executed" if frame["call_state"] == "queued" else "cancelled")
        member.intent = {**member.intent, "frame": frame}


async def recover_interrupted_edits(db, conversation_id):
    """Called on history load and next submission. A live writer owns the
    advisory lock until its outer Chat transaction commits or rolls back."""
    recovered = False
    media_turns = select(Message.turn_id).where(
        Message.conversation_id == conversation_id, Message.intent.has_key("editor_media"))
    batch_turns = select(Message.turn_id).where(
        Message.conversation_id == conversation_id, Message.intent["frame"].has_key("group_id"))
    ids = list(
        await db.scalars(
            select(Message.id).where(
                Message.conversation_id == conversation_id,
                Message.turn_state == "in_flight",
                or_(Message.intent.has_key("editor_commits"), Message.id.in_(media_turns), Message.id.in_(batch_turns)),
            )
        )
    )
    for turn_id in ids:
        if not await db.scalar(select(func.pg_try_advisory_xact_lock(editor_lock_key(turn_id)))):
            continue
        row = await db.get(Message, turn_id, with_for_update=True, populate_existing=True)
        if row is not None and row.turn_state == "in_flight":
            media = list(await db.scalars(select(Message).where(
                Message.turn_id == row.id, Message.intent.has_key("editor_media"),
            ).order_by(Message.seq)))
            if any(m.intent.get("media_permission") and not m.answer for m in media):
                continue
            if any((m.intent.get("export_job") or m.intent.get("media_job")) and m.intent.get("media_result") and
                   not (row.intent or {}).get("resumed_media") for m in media):
                # The worker polls durable results and competes for the existing opening lock.
                continue
            pending = any((m.intent.get("export_job") or m.intent.get("media_job")) and not m.intent.get("media_result") for m in media)
            if pending:
                continue
            for receipt in media:
                await settle_media_activity(db, receipt)
            await report_committed_edits(db, row)
            await settle_interrupted_members(db, turn_id)
            row.turn_state = "failed"
            await db.flush()
            recovered = True
    return recovered


async def settle_media_activity(db, receipt):
    from app.chat.editor import EDITOR_TOOLS

    name = receipt.intent.get("tool")
    tool = next((t for t in EDITOR_TOOLS if t.name == name), None)
    if tool is None:
        return
    activity_id = receipt.intent.get("activity_id")
    query = select(Message).where(Message.turn_id == receipt.turn_id,
        Message.intent["frame"]["key"].astext == tool.presentation.active_key,
        Message.intent["frame"]["status"].astext == "active")
    if activity_id:
        query = query.where(Message.id == UUID(activity_id))
    activity = await db.scalar(query.order_by(Message.seq.desc()).limit(1))
    if activity:
        success = (receipt.intent.get("media_result") or {}).get("status") == "available"
        frame = {**activity.intent["frame"], "status": "completed" if success else "failed",
                 "settled_at": datetime.now(UTC).isoformat()}
        if frame.get("group_id"):
            result_status = (receipt.intent.get("media_result") or {}).get("status")
            frame["call_state"] = "provider_unknown" if result_status == "provider_unknown" else frame["status"]
        if success:
            frame["key"] = tool.presentation.done_key
        activity.intent = {**activity.intent, "frame": frame}


async def resume_job_receipts():
    """One bounded scan; the live API and every worker share the opening lock."""
    from sqlalchemy.orm import aliased
    from app.models.database import AsyncSessionLocal
    from app.chat.editor_media import continue_media_turn

    opening = aliased(Message)
    later = aliased(Message)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Conversation.project_id, Message.id)
            .select_from(Message).join(Conversation, Conversation.id == Message.conversation_id)
            .join(opening, opening.id == Message.turn_id)
            .where(opening.turn_state == "in_flight", Message.intent.has_key("media_result"),
                   or_(Message.intent.has_key("media_job"), Message.intent.has_key("export_job"),
                       Message.intent["media_permission"]["recovery_quote"].as_boolean().is_(True)))
            .where(~select(later.id).where(later.turn_id == opening.id, later.seq > Message.seq,
                                         later.intent.has_key("editor_media")).exists())
            .order_by(Message.created_at).limit(32))).all()
    for project_id, receipt_id in rows:
        async with AsyncSessionLocal() as db:
            await continue_media_turn(db, await db.get(Project, project_id), await db.get(Message, receipt_id))
