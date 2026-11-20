"""Read project evidence from canonical tables for every model continuation.

No parallel memory store: an observation becomes project evidence only when
its own business write is readable here. Authorization and immutable version
identities are enforced before rendering. Imported content is data, never law.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from collections import Counter

import structlog
from uuid import UUID

from sqlalchemy import or_, select

from app.agents.tool_loop import ContextSnapshot
from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetStatus
from app.models.tables import Asset, Composition, CompositionVersion, Conversation, PageReading, Project, SourceSnapshot
from app.tools.world import normalize_page_url

logger = structlog.get_logger()

MAX_CONTEXT_CHARS = 192_000
MAX_RESOURCE_CHARS = 176_000


def page_context_key(project_id: UUID, url: str, text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return f"page:{project_id}:{normalize_page_url(url)}:{digest}"


def source_context(snapshot: Any) -> dict[str, Any]:
    """Default model projection; complete geometry remains in SourceSnapshot.meta."""
    meta = snapshot.meta or {}
    resource = {
        "snapshot_id": str(snapshot.id),
        "kind": snapshot.kind,
        "digest": snapshot.digest,
        "duration_ticks": snapshot.duration_ticks,
        "origin_project_id": str(snapshot.origin_project_id) if snapshot.origin_project_id else None,
    }
    if snapshot.kind == "web":
        from app.editing.director import recapturable_web_elements
        from app.tools.video.preparation import frozen_source_lines

        resource.update({
            "citable_lines": [
                {key: line.get(key) for key in ("line_id", "kind", "text") if line.get(key) is not None}
                for line in frozen_source_lines(snapshot)
            ],
            "views": [
                {
                    "view_id": view.get("view_id"),
                    "heading": view.get("heading"),
                    "width": view.get("width"),
                    "height": view.get("height"),
                    "digest": view.get("digest"),
                    "storage_key": view.get("storage_key"),
                    "targets": [
                        {
                            key: element.get(key)
                            for key in ("id", "kind", "text", "label")
                            if element.get(key) is not None
                        }
                        for element in view.get("elements") or []
                    ],
                }
                for view in meta.get("views") or []
            ],
            "capabilities": {
                "reuse_frozen_views": True,
                "dom_recapture_element_ids": sorted(recapturable_web_elements(meta)),
            },
            "projection": "此处仅列简要信息；用 prepare_video_materials 选取 snapshot/view/element 可读取目标的确切事实",
        })
    else:
        media = meta.get("media") or meta
        resource.update({
            "title": (meta.get("music") or {}).get("title"),
            "width": media.get("width"),
            "height": media.get("height"),
            "origin": meta.get("origin"),
            "view_id": meta.get("view_id"),
            "web_snapshot_id": meta.get("web_snapshot_id"),
        })
    return resource


def render_resources(resources: list[tuple[str, dict[str, Any]]]) -> ContextSnapshot:
    """Compact, deduplicated projections; an omitted/truncated item has no full key."""
    sections = [
        "CURRENT PROJECT EVIDENCE（服务端读取的事实）。直接使用已有内容，只读取缺失细节或用户明确要求刷新的资源。以已保存的作品为准，失败的候选不属于已保存版本。"
    ]
    keys: set[str] = set()
    used = len(sections[0])
    seen: set[str] = set()
    omitted: list[dict[str, str]] = []
    for key, resource in resources:
        if key in seen:
            continue
        seen.add(key)
        text = json.dumps({"resource_key": key, **resource}, ensure_ascii=False, default=str)
        if len(text) > MAX_RESOURCE_CHARS or used + len(text) + 2 > MAX_CONTEXT_CHARS - 8_000:
            omitted.append({"resource_key": key, "kind": str(resource.get("kind", "")),
                            "reason": "达到上下文大小上限，请显式读取资源以获取完整内容"})
            continue
        sections.append(text)
        used += len(text) + 2
        keys.add(key)
    if omitted:
        # Bound even an exceptionally large project's omitted-resource catalog.
        catalog = json.dumps({"omitted_resource_count": len(omitted), "omitted": omitted[:8]}, ensure_ascii=False)
        sections.append(catalog)
    return ContextSnapshot(
        "\n\n".join(sections),
        frozenset(keys),
        resources=tuple((key, resource) for key, resource in resources if key in keys),
    )


def merge_skill_read_receipts(receipts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Merge newest-first settled receipts by immutable package and resource.

    A turn-scoped PackageSession reports only its own reads. Across turns, a
    path+digest is one successful read, a shot keeps its latest preview check,
    and media_files counts unique preview resources rather than repeated reads.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        identity = str(receipt.get("package_identity") or "")
        if identity:
            grouped.setdefault(identity, []).append(receipt)

    merged: dict[str, dict[str, Any]] = {}
    for identity, versions in grouped.items():
        reads: dict[tuple[str, str, str], dict[str, Any]] = {}
        previews: dict[str, dict[str, Any]] = {}
        for receipt in reversed(versions):
            for read in receipt.get("reads") or []:
                if not isinstance(read, dict):
                    continue
                path, digest = read.get("path"), read.get("digest")
                if isinstance(path, str) and isinstance(digest, str):
                    key = (path, digest, str(read.get("kind") or ""))
                    reads[key] = read
            for check in receipt.get("preview_checks") or []:
                if not isinstance(check, dict):
                    continue
                shot_id = check.get("shot_id")
                if isinstance(shot_id, str) and shot_id:
                    previews[shot_id] = check
        media_keys = {
            (path, digest)
            for (path, digest, kind) in reads
            if kind == "preview"
        }
        merged[identity] = {
            **versions[0],
            "reads": list(reads.values()),
            "preview_checks": list(previews.values()),
            "media_files": len(media_keys),
        }
    return merged


async def settled_skill_read_receipts(
    db, *, project_id: UUID, owner_id: UUID
) -> dict[str, dict[str, Any]]:
    from app.chat.conversation_context import context_items

    conversations = (await db.scalars(select(Conversation).where(
        Conversation.project_id == project_id, Conversation.user_id == owner_id
    ))).all()
    items = [
        item
        for conversation in conversations
        for item in context_items(conversation.context)
        if item.get("ok") and (item.get("receipt") or {}).get("kind") == "skill_read"
    ]
    items.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
    return merge_skill_read_receipts([item["receipt"] for item in items])


async def load_project_context(db, *, project_id: UUID, owner_id: UUID) -> ContextSnapshot:
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.user_id == owner_id))
    if project is None:
        raise PermissionError("project context is not accessible")
    resources: list[tuple[str, dict[str, Any]]] = []
    # Current works carry revision targets and current values, not a second
    # full Composition document. Exact reads remain available through the
    # canonical version tool when a wider scope is genuinely needed.
    versions = (await db.execute(
        select(Composition, CompositionVersion)
        .join(CompositionVersion, (Composition.current_version_id == CompositionVersion.id)
              & (CompositionVersion.composition_id == Composition.id))
        .where(Composition.origin_project_id == project_id, Composition.owner_id == owner_id)
        .order_by(Composition.created_at.desc())
    )).all()
    compact_saved_work = bool(versions)
    bound_snapshot_ids: set[UUID] = set()
    for composition, version in versions:
        for source in version.sources or []:
            if source.get("snapshot_id"):
                bound_snapshot_ids.add(UUID(str(source["snapshot_id"])))
        scenes = version.scenes or []
        tracks = (version.timeline or {}).get("tracks") or []
        resources.append((f"composition:{version.id}:{version.content_digest}", {
            "kind": "composition", "composition_id": str(composition.id), "name": composition.name,
            "version_id": str(version.id), "version": version.version, "content_digest": version.content_digest,
            "base_ref": {"composition_id": str(composition.id), "composition_version_id": str(version.id), "content_digest": version.content_digest},
            "timebase": version.settings.get("timebase", 90000),
            "clip_count": sum(len(track.get("clips") or []) for track in tracks),
            "scene_count": len(scenes),
            "duration_ticks": max((c["range"]["end"] for t in tracks for c in t.get("clips", [])), default=0),
        }))
    pages = (await db.scalars(select(PageReading).where(PageReading.project_id == project_id)
                              .order_by(PageReading.url))).all()
    if not compact_saved_work:
        for page in pages:
            resources.append((page_context_key(project_id, page.url, page.text), {
                "kind": "web_page", "url": page.url, "captured_at": page.fetched_at, "text": page.text,
            }))
    # Receipts are turn-scoped at birth. Merge all settled turns by immutable
    # package/resource identity so a later SKILL.md read cannot erase an earlier
    # successful preview. History never claims to carry current visual evidence.
    skill_receipts = await settled_skill_read_receipts(
        db, project_id=project_id, owner_id=owner_id
    )
    for identity, receipt in list(skill_receipts.items())[:4]:
        resources.append((f"skill-read:{identity}", {
            "kind": "skill_read_receipt",
            "package_identity": identity,
            "skill_reference": receipt.get("skill_reference"),
            "reads": receipt.get("reads") or [],
            "preview_checks": receipt.get("preview_checks") or [],
            "media_files_actually_read": receipt.get("media_files", 0),
            "receipt_contains_media": False,
            "note": "此回执证明此前读取过资源，但本身不含媒体。使用本次请求其他位置附上的实际媒体，只有证据缺失或不足时才读取预览。",
        }))
    assets = (await db.scalars(select(Asset).where(Asset.project_id == project_id, Asset.user_id == owner_id)
                               .order_by(Asset.created_at))).all()
    from app.pipeline.assets import asset_text_content
    for asset in assets:
        # Material content is available without manufacturing a new reading.
        text = asset_text_content(asset)
        resources.append((f"asset:{asset.id}", {
            "kind": "asset", "asset_id": str(asset.id), "type": getattr(asset.type, "value", asset.type),
            "name": asset.title, "status": getattr(asset.processing_status, "value", asset.processing_status),
            "text": text if asset.processing_status == AssetStatus.COMPLETED else "",
            "edited_text": asset.edited_transcript,
            "url": (asset.meta or {}).get("capture_url"),
            "captured_view_count": len((asset.meta or {}).get("shots") or []),
            "language": (asset.meta or {}).get("language"),
        }))
    from app.chat.conversation_context import context_items

    draft_snapshot_ids: set[UUID] = set()
    conversations = (await db.scalars(select(Conversation).where(
        Conversation.project_id == project_id, Conversation.user_id == owner_id
    ))).all()
    for conversation in conversations:
        for item in context_items(conversation.context):
            candidate = item.get("candidate") or {}
            if not candidate.get("active", True) or candidate.get("target_tool") != "design_video":
                continue
            arguments = item.get("executed_arguments") or {}
            for source in (arguments.get("content") or {}).get("sources") or []:
                if source.get("snapshot_id"):
                    draft_snapshot_ids.add(UUID(str(source["snapshot_id"])))
    snapshots = (await db.scalars(
        select(SourceSnapshot).outerjoin(Asset, SourceSnapshot.asset_id == Asset.id)
        .where(SourceSnapshot.owner_id == owner_id, or_(
            (Asset.project_id == project_id) & (Asset.user_id == owner_id),
            SourceSnapshot.origin_project_id == project_id,
            SourceSnapshot.id.in_(bound_snapshot_ids | draft_snapshot_ids),
        ))
        .order_by(SourceSnapshot.captured_at)
    )).all()
    text_seats: dict[str, UUID] = {}
    snapshot_by_asset: dict[UUID, UUID] = {}
    snapshot_by_url: dict[str, UUID] = {}
    from app.tools.video.preparation import frozen_source_lines
    for snapshot in snapshots:
        resource = source_context(snapshot)
        resources.append((f"snapshot:{snapshot.id}:{snapshot.digest}", resource))
        if snapshot.kind == "web":
            lines = frozen_source_lines(snapshot)
            if not lines:
                continue
            if snapshot.asset_id is not None:
                snapshot_by_asset[snapshot.asset_id] = snapshot.id
            canonical_url = (snapshot.meta or {}).get("canonical_url")
            if canonical_url:
                snapshot_by_url[normalize_page_url(canonical_url)] = snapshot.id
            text = "".join("\n".join(line["text"] for line in lines).split())
            if text:
                text_seats.setdefault(text, snapshot.id)
    for _, resource in resources:
        if resource.get("kind") not in {"web_page", "asset"}:
            continue
        snapshot_id = None
        if resource.get("kind") == "asset" and resource.get("asset_id"):
            snapshot_id = snapshot_by_asset.get(UUID(str(resource["asset_id"])))
        url = resource.get("url")
        if snapshot_id is None and url:
            snapshot_id = snapshot_by_url.get(normalize_page_url(str(url)))
        if snapshot_id is None and resource.get("text"):
            normalized = "".join(str(resource["text"]).split())
            snapshot_id = text_seats.get(normalized)
        if snapshot_id is not None:
            resource["text"] = ""
            resource["edited_text"] = None
            resource["text_snapshot_id"] = str(snapshot_id)
            resource["text_projection"] = "deduplicated; snapshot citable_lines are the semantic text seat"
    counts = dict(Counter(resource["kind"] for _, resource in resources))
    from app.models.schemas import Brief, BriefSlotSource

    pending = project.pending_brief if isinstance(project.pending_brief, dict) else {}
    brief = Brief.model_validate(pending.get("brief") or {})
    resources.insert(0, (f"project:{project_id}", {
        "kind": "project", "project_id": str(project_id), "title": project.title,
        "status": getattr(project.status, "value", project.status), "resource_counts": counts,
        "user_stated_constraints": [
            item.value for item in brief.constraints
            if item.value and item.source == BriefSlotSource.USER_STATED
        ],
    }))
    snapshot = render_resources(resources)
    logger.info("project_context_loaded", project_id=str(project_id),
                resources=dict(Counter(resource["kind"] for _, resource in resources)),
                included_resources=len(snapshot.keys), total_resources=len(resources), chars=len(snapshot.text))
    return snapshot


def project_context_reader(project_id: UUID, owner_id: UUID):
    """A fresh session sees tool writes committed outside the Chat transaction."""
    async def read() -> ContextSnapshot:
        async with AsyncSessionLocal() as db:
            return await load_project_context(db, project_id=project_id, owner_id=owner_id)
    return read
