"""SFX deterministic import race against disposable Postgres; no paid/media IO."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.editing.sources import register_snapshot
from app.editing.timing import SOURCE_TIMEBASE
from app.models.database import Base
from app.models.schemas import ImportSfxArgs
from app.models.tables import Asset, Conversation, Message, Project, SourceSnapshot, User
from app.providers.freesound import FreesoundSound
from app.tools.video import preparation, sfx

pytestmark = pytest.mark.asyncio

CANDIDATE_SET_ID = UUID("11111111-1111-1111-1111-111111111111")
MP3 = b"deterministic-test-mp3-bytes"
DIGEST = hashlib.sha256(MP3).hexdigest()
SOUND = FreesoundSound(
    provider_id="12345",
    title="Door click",
    author="field-recordist",
    duration_seconds=3.2,
    source_url="https://freesound.org/people/field-recordist/sounds/12345/",
    preview_url="https://cdn.freesound.org/previews/123/12345-hq.mp3",
    license="CC0",
    attribution='"Door click" by field-recordist on Freesound (CC0 1.0)',
)


@pytest_asyncio.fixture
async def database():
    name = f"rep_sfx_test_{uuid4().hex[:12]}"
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


async def test_concurrent_import_returns_one_verified_asset_and_snapshot(database, monkeypatch):
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="SFX race")
        db.add(project)
        await db.commit()
        user_id, project_id = user.id, project.id

    args = ImportSfxArgs(candidate_set_id=CANDIDATE_SET_ID, member_index=0)
    envelope = {
        "kind": "set",
        "candidate_set_id": str(CANDIDATE_SET_ID),
        "topic": "door click",
        "asset_id": None,
        "members": [{
            "start": 0,
            "end": SOUND.duration_seconds,
            "excerpt": SOUND.title,
            "speaker": None,
            "provider": "freesound",
            "provider_id": SOUND.provider_id,
            "title": SOUND.title,
            "author": SOUND.author,
            "duration_seconds": SOUND.duration_seconds,
            "source_url": SOUND.source_url,
            "preview_url": SOUND.preview_url,
            "license": SOUND.license,
            "attribution": SOUND.attribution,
            "query": "door click",
        }],
    }

    async def persisted_events(*args, **kwargs):
        return [envelope]

    async def current_sound(provider_id):
        assert provider_id == SOUND.provider_id
        return SOUND

    both_downloading = asyncio.Event()
    download_count = 0
    download_lock = asyncio.Lock()

    async def download(sound):
        nonlocal download_count
        async with download_lock:
            download_count += 1
            if download_count == 2:
                both_downloading.set()
        await both_downloading.wait()
        return MP3

    objects: dict[str, bytes] = {}

    async def save(key, data, content_type=None):
        objects[key] = data

    async def read(key):
        return objects[key]

    async def fake_snapshot(db, asset, *, owner_id):
        return await register_snapshot(
            db,
            owner_id=owner_id,
            asset=asset,
            kind="audio",
            storage_key=f"source-snapshots/{DIGEST}.mp3",
            digest=DIGEST,
            duration_ticks=round(SOUND.duration_seconds * SOURCE_TIMEBASE),
            meta={"media": {"sample_rate": 48000, "channels": 2}, "origin": asset.meta["origin"]},
            captured_at=datetime.now(UTC),
        )

    monkeypatch.setattr(sfx, "_persisted_candidate_events", persisted_events)
    monkeypatch.setattr(sfx, "get_cc0_mp3", current_sound)
    monkeypatch.setattr(sfx, "download_mp3_preview", download)
    monkeypatch.setattr(sfx, "_validate_mp3_bytes", lambda data: None)
    monkeypatch.setattr(sfx.storage, "save", save)
    monkeypatch.setattr(sfx.storage, "read", read)
    monkeypatch.setattr(preparation, "snapshot_audio_asset", fake_snapshot)

    async def import_in_own_transaction():
        async with database() as db:
            project = await db.get(Project, project_id)
            return await sfx.import_sfx_candidate(db, project=project, args=args)

    first, second = await asyncio.gather(
        import_in_own_transaction(), import_in_own_transaction()
    )
    assert download_count == 2
    assert first == second
    assert first["snapshot_digest"] == DIGEST

    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Asset)) == 1
        assert await db.scalar(select(func.count()).select_from(SourceSnapshot)) == 1
        asset = await db.get(Asset, UUID(first["asset_id"]))
        snapshot = await db.get(SourceSnapshot, UUID(first["snapshot_id"]))
        assert asset.user_id == user_id and asset.project_id == project_id
        assert asset.meta["content_sha256"] == DIGEST
        assert snapshot.asset_id == asset.id and snapshot.digest == DIGEST
        assert snapshot.meta["origin"]["candidate_set_id"] == str(CANDIDATE_SET_ID)


async def test_settled_candidate_log_feeds_next_turn_context_but_not_same_turn_import(
    database, monkeypatch,
):
    from app.chat.video_turn_seats import video_context_lines

    monkeypatch.setattr(settings, "video_project_enabled", True)
    async with database() as db:
        user = User(email=f"{uuid4()}@example.test", name="test")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="SFX context")
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.commit()
        user_id, project_id, conversation_id = user.id, project.id, conversation.id

    args = ImportSfxArgs(candidate_set_id=CANDIDATE_SET_ID, member_index=0)
    async with database() as db:
        project = await db.get(Project, project_id)
        with pytest.raises(sfx.SfxError, match="no persisted SFX candidate set"):
            await sfx.import_sfx_candidate(db, project=project, args=args)

    envelope = {
        "kind": "set",
        "candidate_set_id": str(CANDIDATE_SET_ID),
        "topic": "door click",
        "asset_id": None,
        "members": [{
            "provider": "freesound",
            "title": "Door click",
            "duration_seconds": 3.2,
        }],
    }
    async with database() as db:
        db.add(Message(
            conversation_id=conversation_id,
            role="assistant",
            content="",
            attachments=[],
            mentions=[],
            intent={"type": "candidates_log", "ref": "settled-search", "events": [envelope]},
            seq=1,
        ))
        await db.commit()

    async with database() as db:
        project = await db.get(Project, project_id)
        lines = await video_context_lines(db, project)
    assert lines[0].startswith("Persisted SFX candidate sets")
    projected = json.loads(lines[1])
    assert projected["candidate_set_id"] == str(CANDIDATE_SET_ID)
    assert projected["members"] == [{
        "member_index": 0, "ordinal": 1,
        "title": "Door click", "duration_seconds": 3.2,
    }]
