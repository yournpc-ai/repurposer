"""Two concurrent downloads of the same verified SFX candidate."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.editing.sources import register_snapshot
from app.editing.timing import SOURCE_TIMEBASE
from app.models.schemas import ImportSfxArgs
from app.models.tables import (
    Asset,
    Conversation,
    Message,
    MessageSeqCounter,
    Project,
    SourceSnapshot,
    User,
)
from app.providers.freesound import FreesoundSound
from app.tools.video import preparation, sfx

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


@pytest.fixture
async def sfx_import_race(database, monkeypatch):
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

    async with database() as db:
        chats = [Conversation(user_id=user_id, project_id=project_id) for _ in range(2)]
        db.add_all(chats)
        await db.flush()
        db.add(Message(conversation_id=chats[0].id, role="assistant", content="", seq=1,
                       intent={"type": "candidates_log", "ref": "found", "events": [envelope]}))
        db.add(MessageSeqCounter(conversation_id=chats[0].id, last_seq=1))
        await db.commit()

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

    monkeypatch.setattr(sfx, "get_cc0_mp3", current_sound)
    monkeypatch.setattr(sfx, "download_mp3_preview", download)
    monkeypatch.setattr(sfx, "_validate_mp3_bytes", lambda data: None)
    monkeypatch.setattr(sfx.storage, "save", save)
    monkeypatch.setattr(sfx.storage, "read", read)
    monkeypatch.setattr(preparation, "snapshot_audio_asset", fake_snapshot)

    return SimpleNamespace(user=user, project=project, chats=chats, arguments=args,
                           downloads=lambda: download_count, digest=DIGEST)


async def assert_one_import(database, race, first, second):
    assert race.downloads() == 2
    assert first == second
    assert first["snapshot_digest"] == DIGEST

    async with database() as db:
        assert await db.scalar(select(func.count()).select_from(Asset)) == 1
        assert await db.scalar(select(func.count()).select_from(SourceSnapshot)) == 1
        asset = await db.get(Asset, UUID(first["asset_id"]))
        snapshot = await db.get(SourceSnapshot, UUID(first["snapshot_id"]))
        assert asset.user_id == race.user.id and asset.project_id == race.project.id
        assert asset.meta["content_sha256"] == DIGEST
        assert snapshot.asset_id == asset.id and snapshot.digest == DIGEST
        assert snapshot.meta["origin"]["candidate_set_id"] == str(CANDIDATE_SET_ID)
