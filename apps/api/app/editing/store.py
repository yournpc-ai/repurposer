"""Version store — the transactional half of the content write door (§2.2).

``apply_composition_edits`` is the ONLY way CompositionVersion rows are born
(LLM edits, deterministic gestures and future component commits all pass
through here). One transaction does: owner/permission check → base_ref check
→ pure op batch → whole-candidate validation → digest → version insert →
current-version CAS. The Composition row lock (SELECT … FOR UPDATE)
serializes concurrent editors across Chats; the base_ref check is the
optimistic contract on top.

Idempotency pair: ``request_id`` + ``request_digest``. A retry with the same
payload (owner, create/edit target/context, base reference and ops) returns
the originally committed version; the same key with a different payload
is rejected. ``request_id`` is globally unique when
present, so a create retry after a timeout can never double-birth a work.

Reads (``get_video_version`` / ``content_of``) live here too — the version
read face for the future Chat surface (§2.2: an explicit version read, never
"the chat's latest video").
"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.edits import BindSource, EditError, Op, apply_ops
from app.editing.schemas import CompositionContent
from app.editing.timing import DEFAULT_TIMEBASE
from app.editing.validators import (
    ContentValidationError,
    SnapshotFacts,
    validate_content,
)
from app.models.schemas import canonical_json_hash
from app.models.tables import Composition, CompositionVersion, Project, SourceSnapshot


class EditingError(ValueError):
    """Base for write-door rejections."""


class CompositionNotFound(EditingError):
    pass


class PermissionDenied(EditingError):
    """Cross-owner access — knowing a UUID never grants access (§9.1)."""


class StaleBase(EditingError):
    """base_ref does not name the Composition's current version."""


class RequestMismatch(EditingError):
    """Same request_id, different payload — never silently re-executed."""


class ContentDigestMismatch(EditingError):
    """The caller's expected content digest does not match the base version."""


class CandidateContentError(EditingError):
    """A direct final-content candidate failed before any version was saved."""

    def __init__(self, reason: str, *, content: dict[str, Any], errors: list[dict]):
        super().__init__(reason)
        self.content = deepcopy(content)
        self.errors = deepcopy(errors)
        self.issues = deepcopy(errors)


def _raw_clips(content: dict[str, Any]):
    timeline = content.get("timeline")
    if not isinstance(timeline, dict):
        return
    tracks = timeline.get("tracks")
    if not isinstance(tracks, list):
        return
    for track in tracks:
        if not isinstance(track, dict) or not isinstance(track.get("clips"), list):
            continue
        for clip in track["clips"]:
            if isinstance(clip, dict):
                yield clip


def _snapshot_id(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _raw_snapshot_ids(content: dict[str, Any]) -> set[UUID]:
    ids: set[UUID] = set()
    sources = content.get("sources")
    if isinstance(sources, list):
        for binding in sources:
            if isinstance(binding, dict) and (sid := _snapshot_id(binding.get("snapshot_id"))) is not None:
                ids.add(sid)
    for clip in _raw_clips(content):
        source = clip.get("source")
        if isinstance(source, dict) and (sid := _snapshot_id(source.get("snapshot_id"))) is not None:
            ids.add(sid)
        obj = clip.get("object")
        project = obj.get("project") if isinstance(obj, dict) else None
        resources = project.get("resources") if isinstance(project, dict) else None
        if isinstance(resources, list):
            for resource in resources:
                if isinstance(resource, dict) and (sid := _snapshot_id(resource.get("snapshot_id"))) is not None:
                    ids.add(sid)
    return ids


def _resolve_raw_snapshot_references(
    content: dict[str, Any], facts: SnapshotFacts, *, owner_id: UUID
) -> dict[str, Any]:
    """Pin immutable snapshot digests from server facts, never model prose."""
    resolved = deepcopy(content)
    ids = _raw_snapshot_ids(resolved)
    for snapshot_id in ids:
        fact = facts.get(snapshot_id)
        if fact is None or fact.get("owner_id") != owner_id:
            raise EditError(f"snapshot {snapshot_id} is not accessible to this user")
    sources = resolved.get("sources")
    if sources is None:
        sources = []
        resolved["sources"] = sources
    if not isinstance(sources, list):
        return resolved
    bound: set[UUID] = set()
    for binding in sources:
        if not isinstance(binding, dict):
            continue
        snapshot_id = _snapshot_id(binding.get("snapshot_id"))
        if snapshot_id is not None and snapshot_id in facts:
            binding["snapshot_digest"] = facts[snapshot_id]["digest"]
            bound.add(snapshot_id)
    for clip in _raw_clips(resolved):
        source = clip.get("source")
        if isinstance(source, dict):
            snapshot_id = _snapshot_id(source.get("snapshot_id"))
            if snapshot_id is not None and snapshot_id in facts:
                source["snapshot_digest"] = facts[snapshot_id]["digest"]
        obj = clip.get("object")
        project = obj.get("project") if isinstance(obj, dict) else None
        resources = project.get("resources") if isinstance(project, dict) else None
        if isinstance(resources, list):
            for resource in resources:
                if not isinstance(resource, dict):
                    continue
                snapshot_id = _snapshot_id(resource.get("snapshot_id"))
                if snapshot_id is not None and snapshot_id in facts:
                    resource["snapshot_digest"] = facts[snapshot_id]["digest"]
    for snapshot_id in sorted(_raw_snapshot_ids(resolved) - bound, key=str):
        sources.append({
            "snapshot_id": str(snapshot_id),
            "snapshot_digest": facts[snapshot_id]["digest"],
        })
    return resolved


def _candidate_errors(exc: Exception) -> list[dict]:
    if isinstance(exc, ValidationError):
        return json.loads(exc.json(include_input=False, include_url=False))
    issues = getattr(exc, "issues", None)
    if issues:
        return deepcopy(issues)
    return [{"loc": [], "type": "content_validation", "msg": str(exc)}]


def content_of(version: CompositionVersion) -> CompositionContent:
    """Reassemble typed content, mapping only legacy persisted Generator names.

    The compatibility copy never writes the version row or recomputes its stored
    content_digest; every newly saved version serializes ``producer`` only.
    """
    timeline = deepcopy(version.timeline)
    if isinstance(timeline, dict):
        for track in timeline.get("tracks") or []:
            if not isinstance(track, dict):
                continue
            for clip in track.get("clips") or []:
                if not isinstance(clip, dict):
                    continue
                obj = clip.get("object")
                if not isinstance(obj, dict) or obj.get("kind") != "generator":
                    continue
                legacy_runtime = obj.get("runtime")
                if not isinstance(legacy_runtime, str):
                    continue
                producer = {
                    "drawing-v1": "draw-2d",
                    "component-v1": "remotion-project",
                    "image-v1": "image-generation",
                }.get(legacy_runtime)
                if producer is not None and "producer" not in obj:
                    obj.pop("runtime")
                    obj["producer"] = producer
    return CompositionContent(
        schema_version=version.schema_version,
        settings=version.settings,
        sources=version.sources,
        scenes=version.scenes,
        timeline=timeline,
    )


def content_digest_of(
    content: CompositionContent, *, skill_provenance: dict | None = None
) -> str:
    """The version's content identity (§2.4): settings + sources + scenes +
    timeline, canonical-JSON hashed — plus the creation provenance when one
    was pinned (§2.1: the digest covers 创作 provenance). Presentation
    receipts and other out-of-content state never feed it. Versions written
    before provenance existed keep their digest shape (the key joins only
    when present)."""
    parts: dict = {
        "schema_version": content.schema_version,
        "settings": content.settings.model_dump(mode="json"),
        "sources": [b.model_dump(mode="json") for b in content.sources],
        "scenes": [s.model_dump(mode="json") for s in content.scenes],
        "timeline": content.timeline.model_dump(mode="json"),
    }
    if skill_provenance is not None:
        parts["skill_provenance"] = skill_provenance
    return canonical_json_hash(parts)


async def snapshot_facts(
    db: AsyncSession, snapshot_ids: set[UUID]
) -> SnapshotFacts:
    """Resolve snapshot rows to plain facts (digest/kind/duration/owner/
    storage_key/manifest). Shared read seat for the write door AND the produce
    path — never a write."""
    if not snapshot_ids:
        return {}
    rows = (
        (await db.execute(select(SourceSnapshot).where(SourceSnapshot.id.in_(snapshot_ids))))
        .scalars()
        .all()
    )
    return {
        row.id: {
            "digest": row.digest,
            "kind": row.kind,
            "duration_ticks": row.duration_ticks,
            "owner_id": row.owner_id,
            "storage_key": row.storage_key,
            "meta": row.meta or {},
        }
        for row in rows
    }


async def get_video_version(
    db: AsyncSession,
    *,
    owner_id: UUID,
    version_id: UUID | None = None,
    composition_id: UUID | None = None,
) -> tuple[Composition, CompositionVersion]:
    """The explicit version read face (§2.2): by version id, or a
    Composition's current version. Owner-checked — a foreign id is
    indistinguishable from a missing one."""
    if version_id is not None:
        version = await db.get(CompositionVersion, version_id)
        if version is None:
            raise CompositionNotFound(f"version {version_id} does not exist")
        composition = await db.get(Composition, version.composition_id)
    elif composition_id is not None:
        composition = await db.get(Composition, composition_id)
        if composition is None:
            raise CompositionNotFound(f"composition {composition_id} does not exist")
        if composition.current_version_id is None:
            raise CompositionNotFound(f"composition {composition_id} has no version")
        version = await db.get(CompositionVersion, composition.current_version_id)
    else:
        raise EditingError("get_video_version needs version_id or composition_id")
    if composition is None or version is None:
        raise CompositionNotFound("composition/version row missing")
    if composition.owner_id != owner_id:
        raise PermissionDenied("that composition belongs to another user")
    return composition, version


async def _replay_request(
    db: AsyncSession,
    *,
    owner_id: UUID,
    request_id: str | None,
    request_digest: str | None,
) -> tuple[Composition, CompositionVersion, bool] | None:
    """One replay law for initial lookup, lock wait and unique-index race.

    Keys are globally unique, but knowing a key never grants access to its
    owner or reveals whether another owner's payload matches.
    """
    if request_id is None:
        return None
    existing = (
        await db.execute(
            select(CompositionVersion).where(CompositionVersion.request_id == request_id)
        )
    ).scalar_one_or_none()
    if existing is None:
        return None
    composition = await db.get(Composition, existing.composition_id)
    if composition is None or composition.owner_id != owner_id:
        raise PermissionDenied("that request belongs to another user")
    if existing.request_digest != request_digest:
        raise RequestMismatch("request_id was already committed with a different payload")
    return composition, existing, True


async def apply_composition_edits(
    db: AsyncSession,
    *,
    owner_id: UUID,
    ops: list[Op] | None = None,
    content: dict[str, Any] | CompositionContent | None = None,
    request_id: str | None = None,
    composition_id: UUID | None = None,
    base_version_id: UUID | None = None,
    base_digest: str | None = None,
    origin_project_id: UUID | None = None,
    name: str = "",
    skill_provenance: dict | None = None,
) -> tuple[Composition, CompositionVersion, bool]:
    """The single content write door. Returns (composition, version, replayed).

    Internal deterministic callers may still supply ``ops``. Chat authoring
    supplies the complete final ``content`` instead; both paths share the same
    owner/base checks, immutable snapshot resolution, whole-candidate
    validation, idempotency and immutable-version commit.
    """
    if (ops is None) == (content is None):
        raise EditingError("supply exactly one of ops or complete content")
    direct_content = (
        content.model_dump(mode="json") if isinstance(content, CompositionContent)
        else deepcopy(content) if content is not None
        else None
    )
    request_digest = (
        canonical_json_hash({
            "owner_id": owner_id,
            "mode": "create" if composition_id is None else "edit",
            "composition_id": composition_id,
            "base_version_id": base_version_id,
            "base_digest": base_digest,
            "origin_project_id": origin_project_id,
            "name": name,
            "skill_provenance": skill_provenance,
            "content": direct_content,
            "ops": [op.model_dump(mode="json") for op in ops] if ops is not None else None,
        })
        if request_id is not None
        else None
    )

    # --- idempotency: the request may already have landed -------------------
    replay = await _replay_request(
        db, owner_id=owner_id, request_id=request_id, request_digest=request_digest,
    )
    if replay is not None:
        return replay

    try:
        # --- load + authorize -----------------------------------------------
        if composition_id is None:
            if origin_project_id is None:
                raise EditingError("creating a composition requires origin_project_id")
            project = await db.get(Project, origin_project_id)
            if project is None or project.user_id != owner_id:
                raise PermissionDenied("origin chat is unavailable to this user")
            composition = Composition(
                id=uuid4(),
                owner_id=owner_id,
                origin_project_id=origin_project_id,
                name=name,
            )
            db.add(composition)
            base_version: CompositionVersion | None = None
            base_content = CompositionContent(
                settings={"width": 1920, "height": 1080},
            )
        else:
            composition = (
                await db.execute(
                    select(Composition)
                    .where(Composition.id == composition_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if composition is None:
                raise CompositionNotFound(f"composition {composition_id} does not exist")
            if composition.owner_id != owner_id:
                raise PermissionDenied("that composition belongs to another user")
            # Post-lock recheck: a concurrent twin of THIS request may have
            # committed while we waited on the row lock — answer the retry,
            # never double-land it.
            replay = await _replay_request(
                db, owner_id=owner_id, request_id=request_id, request_digest=request_digest,
            )
            if replay is not None:
                return replay
            if base_version_id is None or composition.current_version_id != base_version_id:
                raise StaleBase(
                    "base_version_id is not the composition's current version — "
                    "re-read the head and rebase"
                )
            base_version = await db.get(CompositionVersion, base_version_id)
            if base_version is None:
                raise CompositionNotFound(f"base version {base_version_id} does not exist")
            if base_digest is not None and base_version.content_digest != base_digest:
                raise ContentDigestMismatch(
                    "the base version's content digest does not match the reference"
                )
            base_content = content_of(base_version)

        if direct_content is not None:
            # Direct authoring is already the complete final work. Resolve all
            # immutable media identities before strict schema + semantic checks.
            direct_facts = await snapshot_facts(db, _raw_snapshot_ids(direct_content))
            direct_content = _resolve_raw_snapshot_references(
                direct_content, direct_facts, owner_id=owner_id
            )
            candidate = CompositionContent.model_validate(direct_content)
            candidate_ids = {b.snapshot_id for b in candidate.sources}
            candidate_facts = await snapshot_facts(db, candidate_ids)
            validate_content(candidate, candidate_facts)
        else:
            assert ops is not None
            # --- internal deterministic op batch -----------------------------
            bind_ids = {op.snapshot_id for op in ops if isinstance(op, BindSource)}
            referenced_ids = {b.snapshot_id for b in base_content.sources}
            facts = await snapshot_facts(db, bind_ids | referenced_ids)
            for sid in bind_ids:
                if sid not in facts:
                    raise EditError(f"snapshot {sid} does not exist")
                if facts[sid]["owner_id"] != owner_id:
                    raise PermissionDenied(f"snapshot {sid} belongs to another user")
            bound_digests = {sid: f["digest"] for sid, f in facts.items()}
            candidate = apply_ops(base_content, ops, bound_digests)
            candidate_ids = {b.snapshot_id for b in candidate.sources}
            candidate_facts = await snapshot_facts(db, candidate_ids)
            validate_content(candidate, candidate_facts)

        # --- land the version + move the head (same transaction) -------------
        version = CompositionVersion(
            id=uuid4(),
            composition_id=composition.id,
            version=(base_version.version + 1) if base_version else 1,
            base_version_id=base_version.id if base_version else None,
            schema_version=candidate.schema_version,
            settings=candidate.settings.model_dump(mode="json"),
            sources=[b.model_dump(mode="json") for b in candidate.sources],
            scenes=[s.model_dump(mode="json") for s in candidate.scenes],
            timeline=candidate.timeline.model_dump(mode="json"),
            skill_provenance=skill_provenance,
            content_digest=content_digest_of(candidate, skill_provenance=skill_provenance),
            request_id=request_id,
            request_digest=request_digest,
        )
        db.add(version)
        try:
            await db.flush()
        except IntegrityError:
            # Create-race twin: the same request_id committed on another
            # transaction between our pre-check and this flush.
            await db.rollback()
            replay = await _replay_request(
                db, owner_id=owner_id, request_id=request_id, request_digest=request_digest,
            )
            if replay is not None:
                return replay
            # An unrelated integrity failure must retain its original cause.
            raise
        composition.current_version_id = version.id
        await db.commit()
        return composition, version, False
    except Exception as exc:
        # No half-versions: any failure rolls the whole transaction back. Keep
        # the direct candidate in local raw JSON before rollback so Chat can
        # retain it as an uncommitted working draft without a DB side write.
        raw_candidate = deepcopy(direct_content) if direct_content is not None else None
        errors = _candidate_errors(exc) if raw_candidate is not None else []
        await db.rollback()
        if raw_candidate is not None and isinstance(
            exc, (ValidationError, ContentValidationError, EditError)
        ):
            raise CandidateContentError(
                str(exc), content=raw_candidate, errors=errors
            ) from exc
        raise


def default_timebase() -> int:
    """The content timebase new versions default to (display seam for callers
    that need the constant without importing schemas)."""
    return DEFAULT_TIMEBASE
