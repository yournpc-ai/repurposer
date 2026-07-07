"""Tests for the music library service, resolution, and clip-agent wiring.

Covers the pieces landed for the DB-backed AI-music library (see
docs/MUSIC_ARCHITECTURE.md): Music CRUD + in-use guard, brand/plan → ClipMusic
resolution, and the ClipMusic ``track_id`` → ``music_id`` alias round-trip.
Uses the in-memory SQLite ``db`` fixture; no MiniMax calls (audio bytes are
faked on disk via ``create_music_from_generation``).
"""

from uuid import uuid4

import pytest

from app.config import settings
from app.models.schemas import ClipMusic, ClipPlan
from app.models.tables import Clip, Project, User
from app.services.brand import (
    music_from_mood,
    music_from_plan,
    music_from_template,
    resolve_music_ref,
)
from app.services.music import (
    MusicInUseError,
    create_music_from_generation,
    delete_music,
    get_music_by_mood,
    is_music_in_use,
    list_music,
)
from app.services.music_generation import AUDIO_EXT, GeneratedMusic


@pytest.fixture(autouse=True)
def _tmp_asset_dir(tmp_path, monkeypatch):
    """Redirect music file writes to a tmp dir so tests don't pollute the repo."""
    monkeypatch.setattr(settings, "asset_dir", tmp_path)
    return tmp_path


def _fake_generated() -> GeneratedMusic:
    """A GeneratedMusic whose bytes are written to disk by the service."""
    audio = b"ID3fake-mp3-bytes"
    return GeneratedMusic(
        audio_bytes=audio,
        ext=AUDIO_EXT,
        duration_seconds=60,
        size_bytes=len(audio),
        model="test-model",
        generation_id="gen-123",
    )


async def _make_piece(db, *, mood: str, user_id=None, is_public: bool = True):
    return await create_music_from_generation(
        db,
        prompt=f"a {mood} track",
        generated=_fake_generated(),
        mood=mood,
        user_id=user_id,
        is_public=is_public,
    )


def test_clipmusic_track_id_alias_round_trips():
    """Legacy render_spec JSON with track_id still deserializes to music_id."""
    legacy = ClipMusic.model_validate(
        {"track_id": "abc-123", "enabled": True, "gain_db": -12}
    )
    assert legacy.music_id == "abc-123"
    assert legacy.enabled is True

    # Constructing by the new name and serializing yields music_id (not track_id).
    m = ClipMusic(music_id="xyz", enabled=True)
    dumped = m.model_dump(mode="json")
    assert dumped["music_id"] == "xyz"
    assert "track_id" not in dumped


def test_clipplan_music_defaults():
    """ClipPlan carries the new per-clip music fields with sane defaults."""
    plan = ClipPlan(id="c1", source_text="x", start_marker="a", end_marker="b")
    assert plan.music_id is None
    assert plan.music_enabled is True
    assert plan.music_gain_db == -18.0


@pytest.mark.asyncio
async def test_create_and_list_music(db):
    piece = await _make_piece(db, mood="calm")
    assert piece.mood == "calm"
    assert piece.file_path.endswith(f".{AUDIO_EXT}")

    pieces = await list_music(db)
    assert [p.mood for p in pieces] == ["calm"]


@pytest.mark.asyncio
async def test_list_music_public_plus_own(db):
    owner = uuid4()
    other = uuid4()
    await _make_piece(db, mood="calm")  # public, platform
    await _make_piece(db, mood="mine", user_id=owner, is_public=False)
    await _make_piece(db, mood="theirs", user_id=other, is_public=False)

    moods = {p.mood for p in await list_music(db, user_id=owner)}
    assert moods == {"calm", "mine"}  # own private + public; not others' private


@pytest.mark.asyncio
async def test_resolve_music_ref_by_uuid_and_mood(db):
    piece = await _make_piece(db, mood="corporate")

    by_uuid = await resolve_music_ref(db, str(piece.id))
    assert by_uuid is not None and by_uuid.id == piece.id

    by_mood = await resolve_music_ref(db, "corporate")
    assert by_mood is not None and by_mood.id == piece.id

    # Synonym normalizes to the library key.
    by_synonym = await resolve_music_ref(db, "business")
    assert by_synonym is not None and by_synonym.id == piece.id

    assert await resolve_music_ref(db, "none") is None
    assert await resolve_music_ref(db, "does-not-exist") is None
    assert await resolve_music_ref(db, None) is None


@pytest.mark.asyncio
async def test_music_from_template_resolves_by_id(db):
    piece = await _make_piece(db, mood="uplifting")
    music = await music_from_template(
        db,
        {"musicEnabled": True, "musicId": str(piece.id), "musicGainDb": -14.0},
    )
    assert music.music_id == str(piece.id)
    assert music.url == f"/api/v1/music/{piece.id}/stream"
    assert music.enabled is True
    assert music.gain_db == -14.0


@pytest.mark.asyncio
async def test_music_from_template_legacy_mood_fallback(db):
    piece = await _make_piece(db, mood="calm")
    # Template saved before the rename: only musicMood is set.
    music = await music_from_template(db, {"musicEnabled": True, "musicMood": "calm"})
    assert music.music_id == str(piece.id)
    assert music.enabled is True


@pytest.mark.asyncio
async def test_music_from_template_disabled_when_off(db):
    await _make_piece(db, mood="calm")
    music = await music_from_template(db, {"musicEnabled": False, "musicMood": "calm"})
    # Piece resolves but playback stays off, honoring the brand toggle.
    assert music.enabled is False


@pytest.mark.asyncio
async def test_music_from_plan_prefers_plan_over_brand(db):
    brand_piece = await _make_piece(db, mood="calm")
    clip_piece = await _make_piece(db, mood="uplifting")

    plan = ClipPlan(
        id="c1",
        source_text="x",
        start_marker="a",
        end_marker="b",
        music_id=str(clip_piece.id),
        music_enabled=True,
        music_gain_db=-16.0,
    )
    brand_config = {"musicEnabled": True, "musicId": str(brand_piece.id)}
    music = await music_from_plan(db, plan, brand_config)
    assert music.music_id == str(clip_piece.id)  # the agent's per-clip pick wins
    assert music.gain_db == -16.0


@pytest.mark.asyncio
async def test_music_from_plan_falls_back_to_brand(db):
    brand_piece = await _make_piece(db, mood="calm")
    plan = ClipPlan(id="c1", source_text="x", start_marker="a", end_marker="b")
    brand_config = {"musicEnabled": True, "musicId": str(brand_piece.id)}
    music = await music_from_plan(db, plan, brand_config)
    assert music.music_id == str(brand_piece.id)


@pytest.mark.asyncio
async def test_music_from_mood(db):
    piece = await _make_piece(db, mood="corporate")
    music = await music_from_mood(db, "professional")  # synonym -> corporate
    assert music.music_id == str(piece.id)
    assert music.enabled is True

    absent = await music_from_mood(db, "unknown-mood")
    assert absent.music_id is None
    assert absent.enabled is False


@pytest.mark.asyncio
async def test_delete_music_refuses_when_in_use(db):
    user = User(id=uuid4(), email="u@example.com", name="U")
    db.add(user)
    await db.commit()
    project = Project(id=uuid4(), user_id=user.id, title="P", language="en")
    db.add(project)
    await db.commit()

    piece = await _make_piece(db, mood="calm")
    clip = Clip(
        project_id=project.id,
        hook="h",
        title_options=[],
        music_mood="calm",
        duration=30,
        language="en",
        render_spec={"music": {"music_id": str(piece.id), "enabled": True}},
    )
    db.add(clip)
    await db.commit()

    assert await is_music_in_use(db, piece.id) == 1
    with pytest.raises(MusicInUseError):
        await delete_music(db, piece.id)
    # Still present after the refused delete.
    assert await get_music_by_mood(db, "calm") is not None


@pytest.mark.asyncio
async def test_in_use_guard_catches_legacy_track_id(db):
    piece = await _make_piece(db, mood="calm")
    user = User(id=uuid4(), email="u2@example.com", name="U2")
    db.add(user)
    await db.commit()
    project = Project(id=uuid4(), user_id=user.id, title="P2", language="en")
    db.add(project)
    await db.commit()
    clip = Clip(
        project_id=project.id,
        hook="h",
        title_options=[],
        music_mood="calm",
        duration=30,
        language="en",
        render_spec={"music": {"track_id": str(piece.id), "enabled": True}},
    )
    db.add(clip)
    await db.commit()
    # The guard checks both the new music_id and the legacy track_id key.
    assert await is_music_in_use(db, piece.id) == 1
