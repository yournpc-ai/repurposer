"""Pure SFX provider/candidate journey boundaries; no network, DB or decoder."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agents.tool_loop import ChatTool, ToolLoopAgent, ToolObservation
from app.chat.video_turn_seats import (
    import_sfx_seat,
    search_sfx_seat,
    sfx_candidate_context_lines,
)

from app.config import settings
from app.models.schemas import ImportSfxArgs, SearchSfxArgs
from app.providers.llm.base import ProviderCapabilities, ToolCall, ToolGeneration
from app.providers.freesound import (
    FreesoundError,
    FreesoundSound,
    _sound_from_payload,
    search_cc0_mp3,
)
import app.tools.video.sfx as sfx


def _payload(**overrides):
    payload = {
        "id": 12345,
        "name": "Door click",
        "username": "field-recordist",
        "duration": 3.2,
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "url": "https://freesound.org/people/field-recordist/sounds/12345/",
        "previews": {
            "preview-hq-mp3": "https://cdn.freesound.org/previews/123/12345-hq.mp3",
        },
    }
    return payload | overrides


def _sound() -> FreesoundSound:
    return _sound_from_payload(_payload())


def test_cc0_mapping_and_license_or_preview_change_fail_closed():
    sound = _sound()
    assert sound.provider_id == "12345"
    assert sound.license == "CC0"
    assert sound.attribution == '"Door click" by field-recordist on Freesound (CC0 1.0)'
    with pytest.raises(FreesoundError, match="no longer CC0"):
        _sound_from_payload(_payload(license="https://creativecommons.org/licenses/by/4.0/"))
    with pytest.raises(FreesoundError, match="no MP3 preview"):
        _sound_from_payload(_payload(previews={"preview-hq-ogg": "https://cdn.freesound.org/previews/123/12345.ogg"}))


def test_missing_provider_configuration_is_honest(monkeypatch):
    monkeypatch.setattr(settings, "freesound_api_key", "")
    with pytest.raises(FreesoundError, match="FREESOUND_API_KEY"):
        asyncio.run(search_cc0_mp3("door click"))


def test_set_envelope_resolves_only_persisted_member_identity(monkeypatch):
    async def fake_search(query: str, *, limit: int = 3):
        assert query == "door click" and limit == 3
        return [_sound()]

    monkeypatch.setattr(sfx, "search_cc0_mp3", fake_search)
    envelope = asyncio.run(sfx.search_sfx_candidates("door click"))
    assert envelope["kind"] == "set"
    assert envelope["asset_id"] is None
    assert envelope["members"][0]["preview_url"].endswith(".mp3")
    set_id = UUID(envelope["candidate_set_id"])
    member = sfx.resolve_candidate_member(
        [envelope], candidate_set_id=set_id, member_index=0
    )
    assert member["provider_id"] == "12345"
    with pytest.raises(sfx.SfxError, match="member does not exist"):
        sfx.resolve_candidate_member(
            [envelope], candidate_set_id=set_id, member_index=1
        )
    with pytest.raises(sfx.SfxError, match="no persisted SFX candidate set"):
        sfx.resolve_candidate_member([], candidate_set_id=set_id, member_index=0)


def test_next_turn_context_keeps_exact_set_member_identities_without_guessing():
    first = {
        "kind": "set",
        "candidate_set_id": "11111111-1111-1111-1111-111111111111",
        "topic": "door click",
        "asset_id": None,
        "members": [{
            "provider": "freesound", "title": "Door click", "duration_seconds": 3.2,
        }],
    }
    second = {
        "kind": "set",
        "candidate_set_id": "22222222-2222-2222-2222-222222222222",
        "topic": "door close",
        "asset_id": None,
        "members": [
            {"provider": "freesound", "title": "Wooden door", "duration_seconds": 1.4},
            {"provider": "freesound", "title": "Metal door", "duration_seconds": 2.1},
        ],
    }
    lines = sfx_candidate_context_lines([
        {"type": "candidates_log", "events": [first]},
        {"type": "candidates_log", "events": [second]},
        {"type": "candidates_log", "events": [{
            "kind": "selection",
            "candidate_set_id": second["candidate_set_id"],
            "selected": [1],
        }]},
    ])
    assert lines[0].startswith("Persisted SFX candidate sets")
    projected = [json.loads(line) for line in lines[1:]]
    assert [item["candidate_set_id"] for item in projected] == [
        first["candidate_set_id"], second["candidate_set_id"],
    ]
    assert projected[1]["members"] == [
        {"member_index": 0, "ordinal": 1, "title": "Wooden door", "duration_seconds": 1.4},
        {"member_index": 1, "ordinal": 2, "title": "Metal door", "duration_seconds": 2.1},
    ]
    assert projected[1]["selected"] == [1]


def test_same_turn_emitted_set_is_not_a_persisted_import_source():
    envelope = {
        "kind": "set",
        "candidate_set_id": "11111111-1111-1111-1111-111111111111",
        "members": [],
    }
    # Emission settles into candidates_log only after the turn. The import
    # resolver sees the settled archive, never the in-turn emission buffer.
    assert envelope["kind"] == "set"
    with pytest.raises(sfx.SfxError, match="no persisted SFX candidate set"):
        sfx.resolve_candidate_member(
            [], candidate_set_id=UUID(envelope["candidate_set_id"]), member_index=0,
        )


def test_import_args_reject_urls_and_other_provider_supplied_facts():
    with pytest.raises(ValidationError):
        ImportSfxArgs.model_validate({
            "candidate_set_id": "11111111-1111-1111-1111-111111111111",
            "member_index": 0,
            "preview_url": "https://cdn.freesound.org/previews/fake.mp3",
        })


class _FakeAudioContainer:
    def __init__(self, codec="mp3", *, audio=True, frames=(object(),)):
        self.streams = SimpleNamespace(audio=[SimpleNamespace(
            codec_context=SimpleNamespace(name=codec),
        )] if audio else [])
        self.frames = frames
        self.closed = False

    def decode(self, _stream):
        return iter(self.frames)

    def close(self):
        self.closed = True


@pytest.mark.parametrize("codec", ["mp3", "mp3float"])
def test_real_mp3_decoder_names_pass_with_decodable_frames(monkeypatch, codec):
    container = _FakeAudioContainer(codec)
    monkeypatch.setattr(sfx.av, "open", lambda *args, **kwargs: container)
    sfx._validate_mp3_bytes(b"fake-but-decoder-driven-mp3")
    assert container.closed is True


def test_non_mp3_empty_missing_audio_and_undecodable_bytes_fail_honestly(monkeypatch):
    with pytest.raises(sfx.SfxError, match="empty"):
        sfx._validate_mp3_bytes(b"")

    non_mp3 = _FakeAudioContainer("aac")
    monkeypatch.setattr(sfx.av, "open", lambda *args, **kwargs: non_mp3)
    with pytest.raises(sfx.SfxError, match="expected an MP3 audio stream"):
        sfx._validate_mp3_bytes(b"aac")
    assert non_mp3.closed is True

    no_audio = _FakeAudioContainer(audio=False)
    monkeypatch.setattr(sfx.av, "open", lambda *args, **kwargs: no_audio)
    with pytest.raises(sfx.SfxError, match="no audio stream"):
        sfx._validate_mp3_bytes(b"container")

    no_frames = _FakeAudioContainer(frames=())
    monkeypatch.setattr(sfx.av, "open", lambda *args, **kwargs: no_frames)
    with pytest.raises(sfx.SfxError, match="no decodable audio frames"):
        sfx._validate_mp3_bytes(b"mp3")


def test_search_observation_has_selection_facts_not_provider_provenance(monkeypatch):
    async def fake_search(query):
        return {
            "kind": "set",
            "candidate_set_id": "11111111-1111-1111-1111-111111111111",
            "topic": query,
            "asset_id": None,
            "members": [{
                "title": "Door click.mp3",
                "duration_seconds": 3.2,
                "author": "field-recordist",
                "source_url": "https://freesound.org/people/field-recordist/sounds/12345/",
                "license": "CC0",
            }],
        }

    monkeypatch.setattr(settings, "video_project_enabled", True)
    monkeypatch.setattr(sfx, "search_sfx_candidates", fake_search)
    emitted = []

    async def on_candidates(payload):
        emitted.append(payload)

    observation = asyncio.run(search_sfx_seat(
        project=SimpleNamespace(),
        args=SearchSfxArgs(query="door click"),
        on_candidates=on_candidates,
    ))
    assert len(emitted) == 1
    assert emitted[0]["members"][0]["source_url"].startswith("https://")
    content = observation.text
    assert "Door click" in content and "3.2" in content
    assert "Door click.mp3" not in content
    assert "candidate count, display titles and durations" in content
    assert "candidate cards provide actual playback" in content
    assert "no listening result" in content
    for unwanted in ("Freesound", "field-recordist", "CC0", "source_url"):
        assert unwanted not in content


def test_failed_selection_import_ends_loop_without_repeat_or_new_search(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def fail_import(*args, **kwargs):
        raise sfx.SfxError("the preview cannot be decoded")

    monkeypatch.setattr(settings, "video_project_enabled", True)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(sfx, "import_sfx_candidate", fail_import)

    class Client:
        capabilities = ProviderCapabilities(supports_native_tools=True)

        def __init__(self):
            self.entries = 0

        async def generate_with_tools(self, **kwargs):
            self.entries += 1
            if self.entries == 1:
                return ToolGeneration(content="Importing", tool_calls=[ToolCall(
                    id="import-1",
                    name="import_sfx",
                    arguments={
                        "candidate_set_id": "11111111-1111-1111-1111-111111111111",
                        "member_index": 0,
                    },
                )])
            return ToolGeneration(content="Searching again", tool_calls=[ToolCall(
                id="search-2",
                name="search_sfx",
                arguments={"query": "another batch"},
            )])

    client = Client()
    tools = [
        ChatTool("import_sfx", "Import the selected sound.", ImportSfxArgs, terminal=False),
        ChatTool("search_sfx", "Search sounds.", SearchSfxArgs, terminal=False),
    ]
    agent = ToolLoopAgent(
        name="sfx_selection_terminal_test",
        prompt="intent_router.j2",
        system="test system",
        assemble=lambda **ctx: ({"recent": []}, []),
        tools=tools,
        client=client,
    )
    calls = []
    emitted = []

    async def on_candidates(payload):
        emitted.append(payload)

    async def execute(name, params, prose):
        calls.append(name)
        if name == "import_sfx":
            return await import_sfx_seat(
                project=SimpleNamespace(), args=params, on_candidates=on_candidates,
            )
        return ToolObservation("an automatic replacement search ran")

    result = asyncio.run(agent.call_loop(execute))
    assert result.ended_by == "import_sfx"
    assert result.refusal_facts == {"kind": "sfx_import_failure"}
    assert calls == ["import_sfx"]
    assert client.entries == 1
    assert emitted == []
