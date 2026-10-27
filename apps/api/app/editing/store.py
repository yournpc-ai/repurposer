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

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.editing.edits import BindSource, EditError, Op, apply_ops
from app.editing.schemas import CompositionContent
from app.editing.timing import DEFAULT_TIMEBASE
from app.editing.validators import (
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


def content_of(version: CompositionVersion) -> CompositionContent:
    """Reassemble the typed content from a version row's four columns."""
    return CompositionContent(
        schema_version=version.schema_version,
        settings=version.settings,
        sources=version.sources,
        scenes=version.scenes,
        timeline=version.timeline,
    )


def content_digest_of(content: CompositionContent) -> str:
    """The version's content identity (§2.4): settings + sources + scenes +
    timeline, canonical-JSON hashed. Presentation receipts and other
    out-of-content state never feed it."""
    return canonical_json_hash(
        {
            "schema_version": content.schema_version,
            "settings": content.settings.model_dump(mode="json"),
            "sources": [b.model_dump(mode="json") for b in content.sources],
            "scenes": [s.model_dump(mode="json") for s in content.scenes],
            "timeline": content.timeline.model_dump(mode="json"),
        }
    )


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
    ops: list[Op],
    request_id: str | None = None,
    composition_id: UUID | None = None,
    base_version_id: UUID | None = None,
    base_digest: str | None = None,
    origin_project_id: UUID | None = None,
    name: str = "",
) -> tuple[Composition, CompositionVersion, bool]:
    """The single content write door. Returns (composition, version, replayed)
    — ``replayed=True`` means the request_id matched a committed version and
    NOTHING new was written (the retry's honest answer).

    Create path: ``composition_id=None`` births a Composition whose version 1
    is built from EMPTY content + the op batch (the batch must add settings,
    tracks and clips — the whole-candidate validation decides sufficiency).
    Edit path: the batch rides on the base version's content.
    """
    request_digest = (
        canonical_json_hash({
            "owner_id": owner_id,
            "mode": "create" if composition_id is None else "edit",
            "composition_id": composition_id,
            "base_version_id": base_version_id,
            "base_digest": base_digest,
            "origin_project_id": origin_project_id,
            "name": name,
            "ops": [op.model_dump(mode="json") for op in ops],
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

        # --- resolve bound snapshots (the digest source of truth) -----------
        bind_ids = {op.snapshot_id for op in ops if isinstance(op, BindSource)}
        referenced_ids = {
            b.snapshot_id for b in base_content.sources
        }
        facts = await snapshot_facts(db, bind_ids | referenced_ids)
        for sid in bind_ids:
            if sid not in facts:
                raise EditError(f"snapshot {sid} does not exist")
            if facts[sid]["owner_id"] != owner_id:
                raise PermissionDenied(f"snapshot {sid} belongs to another user")
        bound_digests = {sid: f["digest"] for sid, f in facts.items()}

        # --- pure batch apply + whole-candidate validation -------------------
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
            skill_provenance=None,
            content_digest=content_digest_of(candidate),
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
    except Exception:
        # No half-versions: any failure rolls the whole transaction back —
        # the composition row (create path), the version row and the head
        # pointer land together or not at all. Attributes are never read
        # after the rollback (expired ORM state is a MissingGreenlet trap).
        await db.rollback()
        raise


def default_timebase() -> int:
    """The content timebase new versions default to (display seam for callers
    that need the constant without importing schemas)."""
    return DEFAULT_TIMEBASE
