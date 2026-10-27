"""Write-door and Output-lineage tests against disposable Postgres (ADR-145).

Covers the batch-1 mechanics that need a real transaction: same-chat
independence of two Compositions, cross-Chat concurrent edits (row lock +
base_ref CAS — never an overwrite), request_id idempotency (retry replays,
same key + different payload is refused), owner/permission law, version
monotonicity + atomicity, and the produce seam's Output lineage pins.

No paid IO: snapshots are local rows; nothing here renders.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import TypeAdapter
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.editing.edits import EditError, Op
from app.editing.store import (
    PermissionDenied,
    RequestMismatch,
    StaleBase,
    apply_composition_edits,
    get_video_version,
)
from app.editing.validators import ContentValidationError
from app.models.database import Base
from app.models.tables import (
    Composition,
    CompositionVersion,
    Output,
    Project,
    SourceSnapshot,
    User,
)
from app.tools.video.produce import queue_composition_render
from test_editing_edits_pure import (
    AUDIO_SNAPSHOT,
    AUDIO_DIGEST,
    IMG_SNAPSHOT,
    IMG_DIGEST,
    FOUR_S_TICKS,
    creation_ops,
)

pytestmark = pytest.mark.asyncio

OP = TypeAdapter(Op)


def set_intent(intent: str) -> Op:
    return OP.validate_python(
        {"op": "update_scene", "scene_id": "scn_open", "intent": intent}
    )


@pytest_asyncio.fixture
async def database():
    name = f"rep_editing_test_{uuid4().hex[:12]}"
    server = settings.database_url.rsplit("/", 1)[0]
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(f"{server}/{name}")
    try:
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.connect() as c:
            await c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


async def _user(factory, **kwargs):
    async with factory() as db:
        user = User(email=f"{uuid4()}@example.test", name="test", **kwargs)
        db.add(user)
        await db.commit()
        return user.id


async def _project(factory, user_id, title="chat"):
    async with factory() as db:
        project = Project(user_id=user_id, title=title)
        db.add(project)
        await db.commit()
        return project.id


async def _snapshots(factory, owner_id):
    async with factory() as db:
        db.add_all(
            [
                SourceSnapshot(
                    id=IMG_SNAPSHOT,
                    owner_id=owner_id,
                    kind="image",
                    storage_key="snapshots/img.png",
                    digest=IMG_DIGEST,
                    duration_ticks=None,
                ),
                SourceSnapshot(
                    id=AUDIO_SNAPSHOT,
                    owner_id=owner_id,
                    kind="audio",
                    storage_key="snapshots/bed.wav",
                    digest=AUDIO_DIGEST,
                    duration_ticks=FOUR_S_TICKS,
                ),
            ]
        )
        await db.commit()


async def _create(factory, owner_id, project_id, request_id=None, name="sample"):
    async with factory() as db:
        return await apply_composition_edits(
            db,
            owner_id=owner_id,
            origin_project_id=project_id,
            ops=creation_ops(),
            request_id=request_id,
            name=name,
        )


async def test_two_compositions_in_one_chat_are_independent(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp_a, ver_a1, _ = await _create(database, uid, pid, name="film A")
    comp_b, ver_b1, _ = await _create(database, uid, pid, name="film B")
    assert comp_a.id != comp_b.id and ver_a1.id != ver_b1.id

    # Edit A; B's head and content must not move.
    async with database() as db:
        _, ver_a2, _ = await apply_composition_edits(
            db,
            owner_id=uid,
            composition_id=comp_a.id,
            base_version_id=ver_a1.id,
            ops=[set_intent("new hook")],
        )
    async with database() as db:
        a = await db.get(Composition, comp_a.id)
        b = await db.get(Composition, comp_b.id)
        assert a.current_version_id == ver_a2.id
        assert b.current_version_id == ver_b1.id
        b_head = await db.get(CompositionVersion, b.current_version_id)
        assert b_head.scenes[0]["intent"] == "opening"


async def test_cross_chat_concurrent_edit_never_overwrites(database):
    uid = await _user(database)
    pid_a = await _project(database, uid, title="chat A")
    pid_b = await _project(database, uid, title="chat B")
    await _snapshots(database, uid)
    comp, ver1, _ = await _create(database, uid, pid_a)

    async def edit(intent: str):
        async with database() as db:
            return await apply_composition_edits(
                db,
                owner_id=uid,
                composition_id=comp.id,
                base_version_id=ver1.id,
                ops=[set_intent(intent)],
            )

    # Two Chats edit the same Composition off the same base — one lands,
    # the other MUST lose with StaleBase, never overwrite.
    results = await asyncio.gather(edit("from chat A"), edit("from chat B"), return_exceptions=True)
    wins = [r for r in results if not isinstance(r, Exception)]
    losses = [r for r in results if isinstance(r, StaleBase)]
    assert len(wins) == 1 and len(losses) == 1, results

    async with database() as db:
        head = await db.get(Composition, comp.id)
        assert head.current_version_id == wins[0][1].id
        n = await db.scalar(
            select(func.count()).select_from(CompositionVersion).where(
                CompositionVersion.composition_id == comp.id
            )
        )
        assert n == 2  # v1 + the one winner — the loser left no row


async def test_request_retry_replays_and_key_reuse_is_refused(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    request_id = uuid4().hex
    comp, ver, replayed = await _create(database, uid, pid, request_id=request_id)
    assert not replayed and ver.version == 1

    # Timeout retry: same key, same payload → the committed version, no write.
    comp2, ver2, replayed2 = await _create(database, uid, pid, request_id=request_id)
    assert replayed2 and ver2.id == ver.id and comp2.id == comp.id

    async with database() as db:
        n = await db.scalar(select(func.count()).select_from(CompositionVersion))
        assert n == 1

    # Same key, different payload → refused, never silently re-executed.
    async with database() as db:
        with pytest.raises(RequestMismatch):
            await apply_composition_edits(
                db,
                owner_id=uid,
                composition_id=comp.id,
                base_version_id=ver.id,
                request_id=request_id,
                ops=[set_intent("mutated")],
            )


@pytest.mark.parametrize("changed_field", ["composition_id", "base_version_id", "base_digest"])
async def test_request_identity_covers_edit_target_and_base(database, changed_field):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, base, _ = await _create(database, uid, pid)
    other, other_base, _ = await _create(database, uid, pid)
    request_id = uuid4().hex
    request = dict(
        owner_id=uid, composition_id=comp.id, base_version_id=base.id,
        base_digest=base.content_digest, request_id=request_id,
        ops=[set_intent("revised hook")],
    )
    async with database() as db:
        _, result, _ = await apply_composition_edits(db, **request)
    changed = dict(request)
    if changed_field == "composition_id":
        changed.update(composition_id=other.id, base_version_id=other_base.id)
    elif changed_field == "base_version_id":
        changed[changed_field] = result.id
    else:
        changed[changed_field] = "f" * 64
    async with database() as db:
        with pytest.raises(RequestMismatch):
            await apply_composition_edits(db, **changed)
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 3


@pytest.mark.parametrize("changed_field", ["origin_project_id", "name"])
async def test_create_request_identity_covers_context(database, changed_field):
    uid = await _user(database)
    pid = await _project(database, uid)
    other_pid = await _project(database, uid)
    await _snapshots(database, uid)
    request = dict(
        owner_id=uid, origin_project_id=pid, name="original",
        request_id=uuid4().hex, ops=creation_ops(),
    )
    async with database() as db:
        await apply_composition_edits(db, **request)
    changed = dict(request)
    changed[changed_field] = other_pid if changed_field == "origin_project_id" else "different"
    async with database() as db:
        with pytest.raises(RequestMismatch):
            await apply_composition_edits(db, **changed)
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Composition)) == 1


@pytest.mark.parametrize("mode", ["create", "edit"])
async def test_concurrent_identical_request_replays(database, monkeypatch, mode):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    request = dict(owner_id=uid, request_id=uuid4().hex)
    if mode == "edit":
        comp, base, _ = await _create(database, uid, pid)
        request.update(
            composition_id=comp.id, base_version_id=base.id,
            base_digest=base.content_digest, ops=[set_intent("one edit")],
        )
    else:
        request.update(origin_project_id=pid, ops=creation_ops())

    # Both transactions must observe the initial idempotency miss BEFORE
    # either proceeds. This forces the lock/unique-index recovery path,
    # rather than allowing a sequential retry to pass by scheduler luck.
    barrier = asyncio.Barrier(2)

    async def submit():
        async with database() as db:
            execute = db.execute
            first = True

            async def synchronized_execute(statement, *args, **kwargs):
                nonlocal first
                result = await execute(statement, *args, **kwargs)
                if first:
                    first = False
                    await barrier.wait()
                return result

            monkeypatch.setattr(db, "execute", synchronized_execute)
            return await apply_composition_edits(db, **request)

    results = await asyncio.wait_for(asyncio.gather(submit(), submit()), timeout=10)
    assert results[0][0].id == results[1][0].id
    assert results[0][1].id == results[1][1].id
    assert sorted(result[2] for result in results) == [False, True]
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Composition)) == 1
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == (
            2 if mode == "edit" else 1
        )


@pytest.mark.parametrize("origin", ["foreign", "missing"])
async def test_create_requires_owned_origin_chat(database, origin):
    uid = await _user(database)
    await _snapshots(database, uid)
    pid = await _project(database, await _user(database)) if origin == "foreign" else uuid4()
    async with database() as db:
        with pytest.raises(PermissionDenied):
            await apply_composition_edits(
                db, owner_id=uid, origin_project_id=pid, ops=creation_ops(),
            )
    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Composition)) == 0
        assert await db.scalar(select(func.count()).select_from(CompositionVersion)) == 0


async def test_permission_law(database):
    owner = await _user(database)
    stranger = await _user(database)
    pid = await _project(database, owner)
    await _snapshots(database, owner)
    comp, ver, _ = await _create(database, owner, pid)

    async with database() as db:
        # A stranger cannot edit, read, or reference the owner's snapshots.
        with pytest.raises(PermissionDenied):
            await apply_composition_edits(
                db,
                owner_id=stranger,
                composition_id=comp.id,
                base_version_id=ver.id,
                ops=[set_intent("hijack")],
            )
        with pytest.raises(PermissionDenied):
            await get_video_version(db, owner_id=stranger, composition_id=comp.id)

    # A stranger's own create binding the OWNER's snapshots is refused.
    stranger_pid = await _project(database, stranger, title="stranger chat")
    async with database() as db:
        with pytest.raises(PermissionDenied):
            await apply_composition_edits(
                db,
                owner_id=stranger,
                origin_project_id=stranger_pid,
                ops=creation_ops(),  # binds the OWNER's snapshots
            )


async def test_failed_batch_lands_no_version(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, ver1, _ = await _create(database, uid, pid)

    async with database() as db:
        with pytest.raises(ContentValidationError):
            await apply_composition_edits(
                db,
                owner_id=uid,
                composition_id=comp.id,
                base_version_id=ver1.id,
                ops=[
                    # valid op …
                    set_intent("fine"),
                    # … followed by a batch-poisoning op: unbound source digest.
                    OP.validate_python(
                        {
                            "op": "add_clip",
                            "track_id": "trk_main",
                            "clip": {
                                "clip_id": "clp_rogue",
                                "range": {"start": 0, "end": 90000},
                                "source": {
                                    "snapshot_id": str(IMG_SNAPSHOT),
                                    "snapshot_digest": "f" * 64,
                                },
                                "object": {
                                    "kind": "image",
                                    "object_id": "obj_rogue",
                                    "layout": {"x": 0, "y": 0, "width": 100, "height": 100},
                                },
                            },
                        }
                    ),
                ],
            )
    async with database() as db:
        head = await db.get(Composition, comp.id)
        assert head.current_version_id == ver1.id  # the head never moved
        n = await db.scalar(
            select(func.count()).select_from(CompositionVersion).where(
                CompositionVersion.composition_id == comp.id
            )
        )
        assert n == 1


async def test_queue_render_pins_output_lineage(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    comp, ver, _ = await _create(database, uid, pid)

    async with database() as db:
        project = await db.get(Project, pid)
        composition = await db.get(Composition, comp.id)
        version = await db.get(CompositionVersion, ver.id)
        output = await queue_composition_render(
            db, project=project, composition=composition, version=version
        )
        await db.commit()
        output_id = output.id

    async with database() as db:
        row = await db.get(Output, output_id)
        # §2.2 three-fact pin + the work anchor law (work_id = Composition.id).
        assert row.composition_id == comp.id
        assert row.composition_version_id == ver.id
        assert row.payload["composition_digest"] == ver.content_digest
        assert row.work_id == comp.id
        assert row.type == "video"
        assert row.render_status is not None and row.render_status.value == "pending"
        spec = row.render_spec
        assert spec["family"] == "video"
        assert spec["provenance"] == {
            "composition_id": str(comp.id),
            "composition_version_id": str(ver.id),
            "content_digest": ver.content_digest,
        }
        # 4s @ 30fps — the spec's quantized facts.
        assert spec["duration_frames"] == 120
        assert spec["fps"] == {"num": 30, "den": 1}

        # The Output DTO (§10.3 read face) carries the lineage and the
        # video spec survives serialization as its own envelope.
        from app.models.schemas import OutputResponse

        dto = OutputResponse.model_validate(row)
        assert dto.composition_id == comp.id
        assert dto.composition_version_id == ver.id
        assert dto.render_spec is not None and dto.render_spec.family == "video"
        assert dto.payload["composition_digest"] == ver.content_digest

        # Cross-owner produce is refused (below, with a foreign project).
    # A project owned by a different user must not produce the composition.
    stranger = await _user(database)
    async with database() as db:
        foreign_project = Project(user_id=stranger, title="foreign")
        db.add(foreign_project)
        await db.flush()
        composition = await db.get(Composition, comp.id)
        version = await db.get(CompositionVersion, ver.id)
        with pytest.raises(PermissionDenied):
            await queue_composition_render(
                db, project=foreign_project, composition=composition, version=version
            )


async def test_nonexistent_snapshot_bind_rejected(database):
    uid = await _user(database)
    pid = await _project(database, uid)
    await _snapshots(database, uid)
    ghost = uuid4()
    async with database() as db:
        ops = creation_ops()
        bind = OP.validate_python({"op": "bind_source", "snapshot_id": str(ghost)})
        with pytest.raises(EditError, match="does not exist"):
            await apply_composition_edits(
                db,
                owner_id=uid,
                origin_project_id=pid,
                ops=[*ops, bind],
            )
