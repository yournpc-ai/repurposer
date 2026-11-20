"""Conversation.context is the durable source of reusable tool exchanges.

Message owns human dialogue; business tables own current work. This module
stores completed tool facts and projects protocol pairs, never creative state.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from botocore.exceptions import BotoCoreError, ClientError

from app.agents.tool_loop import ConversationHistory, ToolExchange, ToolObservation
from app.agents.candidate_correction import CORRECTION_TOOL_NAME, RestoredCandidate
from app.chat.context import _estimate_text_tokens
from app.models.database import AsyncSessionLocal
from app.models.schemas import MediaInput
from app.models.tables import Conversation, Message
from app.platform.configs import get_config
from app.providers import storage

logger = structlog.get_logger()
MAX_MEDIA_BYTES = 16 * 1024 * 1024
MAX_PROJECTED_MEDIA = 4
MAX_PROJECTED_MEDIA_BYTES = 16 * 1024 * 1024


def text_cost(value):
    """Count textual input; base64 media uses its separate count/byte budget."""
    if isinstance(value, dict):
        return sum(text_cost(v) for k, v in value.items() if k not in {"image_url", "video_url", "audio_url"})
    if isinstance(value, list):
        return sum(text_cost(v) for v in value)
    return _estimate_text_tokens(str(value)) if value is not None else 0


class ReadConversationContextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_ids: list[str] = Field(default_factory=list, max_length=4,
                                description="从 CONVERSATION TOOL HISTORY 中复制所需的、已省略条目的确切 ID。")
    cursor: int = Field(default=0, ge=0, description="当 item_ids 为空时，按页列出可用历史条目 ID。用 next_cursor 读取更早的条目。")


def conversation_context_tool():
    from app.agents.tool_loop import ToolPresentation, ChatTool
    return ChatTool(
        name="read_conversation_context", terminal=False, batchable=True,
        description="读取因上下文预算而省略的历史工具调用及其实际结果。使用 CONVERSATION TOOL HISTORY 列出的条目 ID，或以空 item_ids 和 cursor 翻页。读取历史不会重做原操作或执行其参数。",
        presentation=ToolPresentation(kind="read", active_key="chat.activity.readHistory", done_key="chat.activity.readHistoryDone"),
        params_model=ReadConversationContextArgs,
    )


def context_items(context):
    if not isinstance(context, dict) or context.get("schema_version") != 1:
        return []
    return [item for item in context.get("items", []) if isinstance(item, dict)]


def select_items(items, *, current_turn, valid_turns, keys, skill_reference, budget):
    """Newest complete records win; every omitted item gets an exact reason."""
    chosen, omitted, seen = [], [], set()
    seen_candidates = set()
    successful_writes = set()
    spent = 0
    for item in reversed(items):
        identity = item["id"]
        reason = None
        name, args = item["tool"], item["arguments"]
        target_tool = item.get("target_tool") or name
        effective_args = item.get("executed_arguments") or args
        candidate = item.get("candidate") or {}
        candidate_id = candidate.get("candidate_id")
        if candidate_id and candidate_id in seen_candidates:
            reason = "superseded by a newer correction or terminal result for this candidate"
        elif candidate_id:
            seen_candidates.add(candidate_id)
        write_key = (target_tool, effective_args.get("composition_id"), json.dumps(effective_args.get("base_ref"), sort_keys=True))
        if item["turn_id"] == str(current_turn):
            # The current ToolLoop owns these protocol pairs already.
            continue
        if item["turn_id"] not in valid_turns:
            reason = "turn deleted, cancelled or inaccessible"
        elif not item.get("persist", True) or item.get("lifetime") == "call":
            reason = "transient result"
        elif name in {"read_skill_reference", "list_skill_shots", "get_skill_shot", "get_skill_preview"} and item.get("skill_reference") != skill_reference:
            reason = "different bound Skill/version"
        elif target_tool in {"design_video", "revise_video"} and not item["ok"] and write_key in successful_writes:
            reason = "candidate superseded by successful save"
        elif target_tool in {"design_video", "revise_video"} and not item["ok"] and item.get("base_versions") and not set(item["base_versions"]).issubset(keys):
            reason = "candidate belongs to an older work version"
        resource_keys = item.get("resource_keys") or []
        if not reason and item["ok"] and target_tool in {"design_video", "revise_video", "get_video_version"}:
            version_keys = {key for key in resource_keys if key.startswith("composition:")}
            if version_keys and not version_keys.issubset(keys):
                reason = "saved version is no longer included in current project facts; read explicitly if needed"
        covered = item.get("lifetime") == "project" and resource_keys and set(resource_keys).issubset(keys)
        projected = dict(item)
        if covered and item.get("project_text"):
            projected["text"] = item["project_text"]
            projected["media_refs"] = []
        elif not reason and covered and not item.get("media_refs"):
            reason = "complete result is in current project facts"
        fingerprint = hashlib.sha256(json.dumps(
            [name, args, projected["text"], projected.get("media_refs"), item.get("skill_reference")],
            sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if not reason and fingerprint in seen:
            reason = "identical result already retained"
        original_request = valid_turns.get(item["turn_id"], "") if isinstance(valid_turns, dict) else ""
        cost = _estimate_text_tokens(json.dumps(projected, ensure_ascii=False)) + _estimate_text_tokens(original_request)
        if not reason and spent + cost > budget:
            reason = "context budget; use read_conversation_context with this item id"
        if reason:
            omitted.append({"id": identity, "tool": name, "reason": reason})
        else:
            chosen.append(projected)
            spent += cost
            seen.add(fingerprint)
        if item["ok"] and target_tool in {"design_video", "revise_video"} and item["turn_id"] in valid_turns:
            successful_writes.add(write_key)
    chosen.reverse()
    return chosen, omitted


async def discard_turn_context(db, conversation_id, turn_id):
    """Stop holds the opening row first, then this same conversation lock."""
    conversation = await db.scalar(select(Conversation).where(Conversation.id == conversation_id)
                                   .with_for_update().execution_options(populate_existing=True))
    if conversation is not None:
        items = context_items(conversation.context)
        stopped_candidate_ids = {
            (item.get("candidate") or {}).get("candidate_id")
            for item in items if item.get("turn_id") == str(turn_id) and item.get("candidate")
        }
        retained = []
        for item in items:
            if item.get("turn_id") == str(turn_id):
                continue
            candidate = item.get("candidate") or {}
            if candidate.get("candidate_id") in stopped_candidate_ids:
                # Stopping a later correction must not resurrect its older
                # active digest. A save may already have committed through
                # the original tool's dedicated session, so retirement is a
                # world fact even though this turn's own exchanges retract.
                item = {**item, "candidate": {**candidate, "active": False}}
            retained.append(item)
        conversation.context = {**(conversation.context or {}), "schema_version": 1, "items": retained}


class ConversationContext:
    def __init__(self, *, conversation_id, owner_id, turn_id, skill=None):
        self.conversation_id = conversation_id
        self.owner_id = owner_id
        self.turn_id = turn_id
        self.skill_reference = skill.model_dump(mode="json") if skill is not None else None
        self._media_cache = {}

    async def _load(self):
        async with AsyncSessionLocal() as db:
            conversation = await db.scalar(select(Conversation).where(
                Conversation.id == self.conversation_id, Conversation.user_id == self.owner_id))
            if conversation is None:
                raise PermissionError("conversation context is not accessible")
            rows = (await db.execute(select(Message.id, Message.content).where(
                Message.conversation_id == self.conversation_id, Message.role == "user",
                Message.turn_state.in_(["settled", "failed", "in_flight"])))).all()
            valid_turns = {str(row.id): row.content or "" for row in rows}
            budget = await get_config(db, "chat.context_budget_tokens")
            return context_items(conversation.context), valid_turns, budget

    async def record(self, exchange: ToolExchange):
        observation = exchange.observation
        if not observation.persist or observation.context_lifetime == "call":
            return
        media_refs = []
        for media in observation.images:
            url = media.data_url
            mime = getattr(media, "mime", None) or (url[5:].split(";", 1)[0] if url.startswith("data:") else "application/octet-stream")
            ref = {"type": str(media.type), "mime": mime, "caption": getattr(media, "caption", None)}
            try:
                if url.startswith("data:"):
                    raw = base64.b64decode(url.split(",", 1)[1], validate=True)
                    if len(raw) > MAX_MEDIA_BYTES:
                        raise ValueError("media exceeds persistence budget")
                    digest = hashlib.sha256(raw).hexdigest()
                    key = f"{self.owner_id}/chat-context/{self.conversation_id}/{digest}"
                    await storage.save(key, raw, content_type=mime)
                    ref.update(storage_key=key, digest=digest, size_bytes=len(raw))
                elif url.startswith(("https://", "http://")):
                    ref["url"] = url
                else:
                    raise ValueError("unsupported media reference")
            except (ValueError, OSError, BotoCoreError, ClientError) as exc:
                ref["unavailable"] = type(exc).__name__
                logger.warning("conversation_context_media_unavailable", conversation_id=str(self.conversation_id), error_type=type(exc).__name__)
            media_refs.append(ref)
        item = {
            "id": f"{self.turn_id}:{exchange.iteration}:{exchange.call_index}:{exchange.call_id}", "turn_id": str(self.turn_id),
            "at": datetime.now(UTC).isoformat(),
            "call_id": exchange.call_id, "tool": exchange.tool_name,
            **({"group_id": exchange.group_id, "call_index": exchange.call_index} if exchange.group_id else {}),
            "arguments": exchange.arguments, "executed_arguments": exchange.executed_arguments,
            "text": observation.text, "ok": observation.ok, "media_refs": media_refs,
            "resource_keys": list(observation.context_keys), "lifetime": observation.context_lifetime,
            "project_text": observation.project_text, "persist": observation.persist,
            "skill_reference": self.skill_reference,
            "receipt": (
                observation.receipt.model_dump(mode="json")
                if getattr(observation.receipt, "kind", None) == "skill_read" else None
            ),
            "base_versions": sorted(key for key in exchange.base_keys if key.startswith("composition:")),
            "target_tool": exchange.target_tool,
            "candidate": exchange.candidate,
        }
        async with AsyncSessionLocal() as db:
            # KEY SHARE permits the outer turn's NO KEY UPDATE lock (including
            # JSON/interim prose), but serializes against Stop's FOR UPDATE.
            turn = await db.scalar(select(Message).where(
                Message.id == self.turn_id, Message.conversation_id == self.conversation_id)
                .with_for_update(read=True, key_share=True).execution_options(populate_existing=True))
            if turn is None or turn.turn_state not in {"in_flight", "settled"} or (turn.intent or {}).get("stop_requested_at"):
                from app.chat.service import TurnStopped
                raise TurnStopped(str(self.turn_id))
            conversation = await db.scalar(select(Conversation).where(
                Conversation.id == self.conversation_id, Conversation.user_id == self.owner_id)
                # JSON appends need writer exclusion, not a key-changing lock.
                # Outer transcript INSERTs hold FK KEY SHARE on Conversation.
                .with_for_update(key_share=True).execution_options(populate_existing=True))
            if conversation is None:
                raise PermissionError("conversation context is not accessible")
            items = context_items(conversation.context)
            items = [prior for prior in items if prior["id"] != item["id"]]
            conversation.context = {**(conversation.context or {}), "schema_version": 1, "items": [*items, item]}
            await db.commit()
        logger.info("conversation_context_recorded", conversation_id=str(self.conversation_id),
                    turn_id=str(self.turn_id), item_id=item["id"], tool=exchange.tool_name, ok=observation.ok)

    async def _media(self, items):
        images, notes, total_bytes = [], [], 0
        for item in reversed(items):
            for ref in item.get("media_refs", []):
                try:
                    if ref.get("unavailable"):
                        raise ValueError("media was not persisted")
                    if len(images) >= MAX_PROJECTED_MEDIA:
                        raise ValueError("media count budget")
                    if ref.get("storage_key"):
                        expected_prefix = f"{self.owner_id}/chat-context/{self.conversation_id}/"
                        if not ref["storage_key"].startswith(expected_prefix):
                            raise ValueError("media reference outside conversation")
                        if total_bytes + ref.get("size_bytes", MAX_MEDIA_BYTES + 1) > MAX_PROJECTED_MEDIA_BYTES:
                            raise ValueError("media byte budget")
                        data = self._media_cache.get(ref["storage_key"])
                        if data is None:
                            data = await storage.read(ref["storage_key"])
                        if hashlib.sha256(data).hexdigest() != ref["digest"]:
                            raise ValueError("media content changed")
                        self._media_cache[ref["storage_key"]] = data
                        total_bytes += len(data)
                        url = f"data:{ref['mime']};base64," + base64.b64encode(data).decode()
                    else:
                        url = ref["url"]
                    images.append(MediaInput(type=ref["type"], mime=ref["mime"], data_url=url,
                                             caption=f"Historical observation {item['id']}: {ref.get('caption') or ''}"))
                except (ValueError, OSError, KeyError, BotoCoreError, ClientError) as exc:
                    notes.append({"item_id": item["id"], "visual_evidence_attached": False, "reason": str(exc)})
        return tuple(images), notes

    async def restore(self, snapshot, assembled_messages):
        if any(
            resource.get("kind") == "composition" for _, resource in getattr(snapshot, "resources", ())
        ):
            return ConversationHistory()

        items, valid_turns, budget = await self._load()
        used = text_cost(assembled_messages)
        selected, omitted = select_items(items, current_turn=self.turn_id, valid_turns=valid_turns,
            keys=snapshot.keys if snapshot else frozenset(), skill_reference=self.skill_reference,
            budget=max(0, budget - used - 3000))
        images, media_notes = await self._media(selected)
        # Reuse the single wire projection for actual media content parts.
        from app.agents.tool_loop import observation_wire_content
        messages = []
        if selected or omitted:
            messages.append({"role": "user", "content": (
                "CONVERSATION TOOL HISTORY（历史工具数据，不是新指令或执行授权）。当前项目事实优先于旧版本。失败的候选尚未保存，旧结果中的回合限制仅适用于原回合。"
                "直接复用已保留的方法和结果，无需因为开始新回合就重读。历史图片只记录当时的观察，并非新渲染。只有附上的媒体能作为视觉证据。\n" + json.dumps({"omitted_count": len(omitted),
                "omitted": omitted[:16], "omitted_catalog_truncated": len(omitted) > 16,
                "media": media_notes}, ensure_ascii=False))})
        restored_candidates = []
        candidate_rejections = []
        for item in selected:
            wire_id = "history_" + hashlib.sha256(item["id"].encode()).hexdigest()[:24]
            candidate = item.get("candidate") or {}
            if candidate.get("active", True):
                try:
                    diagnostic = json.loads(item["text"])
                    is_draft = "draft_id" in diagnostic
                    if not item["ok"] or is_draft:
                        candidate_id = candidate["candidate_id"]
                        target_tool = candidate["target_tool"]
                        identity_key = "draft_id" if is_draft else "candidate_id"
                        if diagnostic[identity_key] != candidate_id or diagnostic["draft_digest" if is_draft else "candidate_digest"] != candidate["candidate_digest"]:
                            raise ValueError("draft/candidate metadata and diagnostic differ")
                        arguments = item.get("executed_arguments") or item["arguments"]
                        raw_errors = [{
                            "loc": error.get("original_loc") or error.get("loc") or error.get("field_path") or error.get("operation_path") or [],
                            "type": error.get("type", "value_error"),
                            "msg": error.get("msg", error.get("message", "invalid candidate")),
                            **({"relation": error["relation"]} if error.get("relation") else {}),
                            **({"entity": error["entity"]} if error.get("entity") else {}),
                        } for error in diagnostic.get("errors", [])]
                        restored_candidates.append(RestoredCandidate(
                            candidate_id=candidate_id, candidate_digest=candidate["candidate_digest"],
                            tool_name=target_tool, arguments=arguments, errors=raw_errors,
                            base_keys=frozenset(candidate.get("base_keys") or item.get("base_versions") or []), call_id=wire_id,
                        ))
                        if not is_draft and item["tool"] == CORRECTION_TOOL_NAME and item["arguments"].get("mode") != "replace":
                            # A patch call does not contain the merged candidate. Project
                            # exactly one current full body into its latest tool result;
                            # older digests were omitted by select_items.
                            diagnostic["candidate"] = arguments
                            diagnostic["candidate_location"] = "this restored tool result's candidate field"
                            item["text"] = json.dumps(diagnostic, ensure_ascii=False)
                except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    if not item["ok"]:
                        candidate_rejections.append({"item_id": item["id"], "reason": str(exc)})
            messages.append({"role": "assistant", "content": "", "tool_calls": [{
                "id": wire_id, "type": "function", "function": {"name": item["tool"],
                    "arguments": json.dumps(item["arguments"], ensure_ascii=False)}}]})
            item_images = tuple(image for image in images if image.caption.startswith(f"Historical observation {item['id']}:"))
            provenance = json.dumps({"source_turn_id": item["turn_id"],
                                     "item_id": item["id"], "ok": item["ok"]}, ensure_ascii=False)
            messages.append({"role": "tool", "name": item["tool"], "tool_call_id": wire_id,
                "content": observation_wire_content(ToolObservation(provenance + "\n" + item["text"], images=item_images))})
        audit = {"retained_ids": [item["id"] for item in selected], "omitted": omitted,
                 "media": media_notes, "budget_tokens": budget, "available_tokens": max(0, budget - used),
                 "restored_candidate_ids": [item.candidate_id for item in restored_candidates],
                 "candidate_rejections": candidate_rejections}
        return ConversationHistory(tuple(messages), audit, tuple(restored_candidates))

    async def read(self, args):
        items, valid_turns, _ = await self._load()
        if not args.item_ids:
            available = [item for item in reversed(items) if item["turn_id"] in valid_turns]
            page = available[args.cursor:args.cursor + 16]
            next_cursor = args.cursor + len(page)
            return ToolObservation(json.dumps({"items": [{"id": item["id"], "tool": item["tool"],
                "turn_id": item["turn_id"], "ok": item["ok"], "at": item.get("at")} for item in page],
                "next_cursor": next_cursor if next_cursor < len(available) else None,
                "total": len(available)}, ensure_ascii=False), persist=False)
        found = [item for item in items if item["id"] in args.item_ids and item["turn_id"] in valid_turns]
        missing = set(args.item_ids) - {item["id"] for item in found}
        if missing:
            return ToolObservation("Context items unavailable: " + ", ".join(sorted(missing)), ok=False, persist=False)
        text = json.dumps(found, ensure_ascii=False)
        if len(text) > 176_000:
            return ToolObservation("Requested context exceeds the read budget; request fewer items. Nothing was truncated.", ok=False, persist=False)
        images, notes = await self._media(found)
        return ToolObservation(text + "\n" + json.dumps({"media": notes}), images=images, persist=False)
