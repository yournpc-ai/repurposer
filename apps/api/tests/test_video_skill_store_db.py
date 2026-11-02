"""External Skill persistence against disposable Postgres; no paid IO."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.database import Base
from app.models.schemas import ExternalSkillReference
from app.models.tables import SkillVersion, User
from app.skills.resolution import list_available_skills, resolve_chat_skill
from app.skills.external import SkillPolicy, build_skill_draft
from app.skills.store import SkillNotFoundError, get_skill_version, import_external_skill

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def database():
    name = f"rep_skill_test_{uuid4().hex[:12]}"
    server = settings.database_url.rsplit("/", 1)[0]
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(f"{server}/{name}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


async def _user(factory) -> UUID:
    async with factory() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.commit()
        return user.id


def _draft(
    extra: bytes = b"", *, policy: SkillPolicy | None = None,
    capabilities=(),
):
    return build_skill_draft(
        {
            "SKILL.md": (
                b"---\nname: external-method\ndescription: A reusable method.\n"
                b"---\nUse the method.\n"
            ),
            "references/method.md": b"Keep the declared structure." + extra,
        },
        declared_capabilities=capabilities,
        source_uri="https://example.invalid/skill",
        source_revision="rev-1",
        policy=policy or SkillPolicy(mode="strict", scene_count=1),
    )


async def test_skill_versions_round_trip_append_and_enforce_owner(database):
    owner_id = await _user(database)
    other_id = await _user(database)
    async with database() as db:
        first, replayed = await import_external_skill(db, owner_id=owner_id, draft=_draft())
        assert first.version == 1 and not replayed
        same, replayed = await import_external_skill(db, owner_id=owner_id, draft=_draft())
        assert same.id == first.id and replayed
        second, replayed = await import_external_skill(
            db, owner_id=owner_id, draft=_draft(b"\nAdaptive detail.")
        )
        assert second.version == 2 and not replayed
        third, replayed = await import_external_skill(
            db,
            owner_id=owner_id,
            draft=_draft(
                b"\nAdaptive detail.",
                policy=SkillPolicy(mode="adaptive", adaptation_bounds=["Keep one scene."]),
            ),
        )
        assert third.version == 3 and not replayed
        assert third.source_hash == second.source_hash
        assert third.version_digest != second.version_digest
        await db.commit()

    async with database() as db:
        loaded = await get_skill_version(db, owner_id=owner_id, skill_version_id=first.id)
        assert loaded.instructions == "Use the method."
        assert loaded.references[0]["text"] == "Keep the declared structure."
        assert loaded.policy["mode"] == "strict"
        assert loaded.policy["scene_count"] == 1
        unchanged = await get_skill_version(db, owner_id=owner_id, skill_version_id=second.id)
        assert unchanged.id != first.id
        with pytest.raises(SkillNotFoundError):
            await get_skill_version(db, owner_id=other_id, skill_version_id=first.id)

    async with database() as db:
        # Pre-digest rows replay by their complete persisted draft, without a
        # backfill that would violate the production immutability trigger.
        legacy = await db.get(SkillVersion, second.id)
        legacy.version_digest = None
        await db.commit()
        replay, replayed = await import_external_skill(
            db, owner_id=owner_id, draft=_draft(b"\nAdaptive detail.")
        )
        assert replay.id == second.id and replayed


async def test_skill_resolver_is_owner_scoped_and_version_exact(database):
    owner_id = await _user(database)
    other_id = await _user(database)
    async with database() as db:
        first, _ = await import_external_skill(
            db,
            owner_id=owner_id,
            draft=_draft(b"\nUse opacity.", capabilities={"animation:opacity"}),
        )
        second, _ = await import_external_skill(
            db,
            owner_id=owner_id,
            draft=_draft(b"\nVersion two. Use opacity.", capabilities={"animation:opacity"}),
        )
        undeclared, _ = await import_external_skill(db, owner_id=owner_id, draft=_draft())
        await db.commit()

    async with database() as db:
        reference = ExternalSkillReference(kind="external", skill_version_id=first.id)
        resolved = await resolve_chat_skill(
            db, owner_id=owner_id, reference=reference, message="use external-method"
        )
        assert resolved.reference == reference
        options = await list_available_skills(db, owner_id=owner_id)
        external_ids = {
            option.reference.skill_version_id
            for option in options
            if isinstance(option.reference, ExternalSkillReference)
        }
        assert external_ids == {first.id, second.id}
        assert undeclared.id not in external_ids
        ambiguous = await resolve_chat_skill(
            db, owner_id=owner_id, reference=None, message="use external-method"
        )
        assert ambiguous.reference is None
        assert len(ambiguous.ambiguous) == 2
        follow_up = await resolve_chat_skill(
            db,
            owner_id=owner_id,
            reference=None,
            message="v2",
            prior_references=[
                ExternalSkillReference(kind="external", skill_version_id=first.id),
                ExternalSkillReference(kind="external", skill_version_id=second.id),
            ],
        )
        assert follow_up.reference == ExternalSkillReference(
            kind="external", skill_version_id=second.id
        )
        with pytest.raises(SkillNotFoundError):
            await resolve_chat_skill(
                db, owner_id=other_id, reference=reference, message="use external-method"
            )
