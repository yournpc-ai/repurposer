"""Pure tests for the perception family (app/chat/perception/) — the chat
loop's read tools (ADR-077 判词②, T2b).

No DB, no LLM, no HTTP (suite discipline): the executes themselves need a
session and stay e2e-covered (scripts/chat_scenarios.py). What's gated HERE
is the registry's shape and its contracts with the loop and the prompts:

- every entry carries the registry discipline (name + params + execute +
  碎碎念 copy key) and the naming law (get_*/list_*/search_* — the prompts
  teach the family by its prefix);
- the loop projection is non-terminal and wire-shaped;
- the caption-style behavior notes never drift from the clip-spec Literal
  (the catalog → Literal → notes chain's Python-side gate);
- every perception-family name MENTIONED in the chat prompt templates is
  registered (门禁枚举 — the prompt-side drift alarm).
"""

import re
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from uuid import uuid4

import pytest

from app.agents.tool_loop import ToolObservation, tool_spec
from app.chat.perception import (
    PERCEPTION_TOOLS,
    perception_chat_tools,
    run_perception_tool,
)
from app.chat.perception.executes import _CAPTION_STYLE_LINES, _resolve_asset_target
from app.models.schemas import AssetType, ClipSpec

_PROMPTS = Path(__file__).resolve().parents[1] / "app" / "prompts" / "chat"


def test_registry_shape_and_naming_law() -> None:
    assert set(PERCEPTION_TOOLS) == {
        "get_output_spec",
        "get_understanding",
        "list_caption_styles",
        "search_music",
        "get_run_status",
        "get_asset",
        "get_craft_skeleton",
    }
    for name, entry in PERCEPTION_TOOLS.items():
        assert re.fullmatch(r"(get|list|search)_[a-z_]+", name), name
        assert entry.name == name
        assert entry.description.strip()
        assert callable(entry.execute)
        # The 碎碎念 copy key — the tool NAME never reaches the user face
        # (简报 §3 禁令); the key is what the SSE inspecting frame carries.
        assert entry.activity_key.startswith("chat.inspecting.")


def test_projection_is_non_terminal_and_wire_shaped() -> None:
    tools = perception_chat_tools("search_music", "get_run_status")
    assert [t.name for t in tools] == ["search_music", "get_run_status"]
    assert all(not t.terminal for t in tools)
    spec = tool_spec(tools[0])
    assert spec["function"]["name"] == "search_music"
    assert "query" in spec["function"]["parameters"]["properties"]
    # A zero-arg read compiles the empty object schema.
    assert tool_spec(tools[1])["function"]["parameters"] == {
        "type": "object",
        "properties": {},
    }
    # Unknown names raise at declaration time, never mid-turn.
    with pytest.raises(KeyError):
        perception_chat_tools("get_nothing")


def test_caption_style_notes_mirror_the_spec_literal() -> None:
    ids = set(get_args(ClipSpec.model_fields["caption_style_preset"].annotation))
    assert set(_CAPTION_STYLE_LINES) == ids


def test_prompt_mentions_are_registered() -> None:
    """Every get_*/list_*/search_* token anywhere in the chat templates —
    prose or {# provenance #} comments — is a registered read tool."""
    mentioned: set[str] = set()
    for path in _PROMPTS.glob("*.j2"):
        mentioned.update(
            re.findall(r"\b(?:get|list|search)_[a-z_]+\b", path.read_text())
        )
    unknown = mentioned - set(PERCEPTION_TOOLS)
    assert not unknown, f"templates mention unregistered read tools: {unknown}"


@pytest.mark.asyncio
async def test_project_less_turn_reads_as_an_honest_empty_observation() -> None:
    """The defensive shape (a project-less chat turn): an honest empty
    observation, never a crash, never a fabricated read."""
    observation = await run_perception_tool(None, None, "get_run_status", None)
    assert isinstance(observation, ToolObservation)
    assert "nothing to read" in observation.text


# ---- get_asset 工具自证 provenance (2026-09-17 交互完整性批 ①) --------------
#
# The prompt surface never lists asset ids, so a required asset_id forced the
# model to invent one (the 2026-09-16 incident). The idless call resolves
# deterministically: 0 → honest empty, 1 → the read, N → the roster (the
# re-call's legitimate id source); an explicit id resolves by membership.


def _asset(**over) -> SimpleNamespace:
    base = dict(
        id=uuid4(),
        project_id=uuid4(),
        type=AssetType.VIDEO,
        file_url="bucket/uploads/talk.mp4",
        title="talk.mp4",
        duration_seconds=15,
        meta={"language": "en"},
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_idless_read_with_no_file_assets_is_an_honest_empty() -> None:
    resolved = _resolve_asset_target([], None)
    assert isinstance(resolved, str) and "No file assets" in resolved
    # Text-only projects (no file_url) read the same honest empty.
    text_asset = _asset(type=AssetType.TRANSCRIPT, file_url=None)
    resolved = _resolve_asset_target([text_asset], None)
    assert isinstance(resolved, str) and "No file assets" in resolved


def test_idless_read_with_exactly_one_file_asset_reads_it() -> None:
    only = _asset()
    # A text asset alongside does not break the uniqueness — the FILE asset
    # is the only read target of its kind.
    text_asset = _asset(type=AssetType.TRANSCRIPT, file_url=None)
    assert _resolve_asset_target([only], None) is only
    assert _resolve_asset_target([text_asset, only], None) is only


def test_idless_read_with_several_file_assets_returns_the_roster() -> None:
    a, b = _asset(title="a.mp4"), _asset(title="b.mp4", meta={})
    resolved = _resolve_asset_target([a, b], None)
    assert isinstance(resolved, str)
    # The roster carries the real ids — the re-call's provenance — and the
    # tool never guesses a target itself.
    assert str(a.id) in resolved and str(b.id) in resolved
    assert "a.mp4" in resolved and "b.mp4" in resolved


def test_explicit_id_resolves_by_membership() -> None:
    a, b = _asset(), _asset()
    assert _resolve_asset_target([a, b], a.id) is a
    # An @-mention's reach: a TEXT asset (no file_url) stays readable by id.
    text_asset = _asset(type=AssetType.TRANSCRIPT, file_url=None)
    assert _resolve_asset_target([a, text_asset], text_asset.id) is text_asset


def test_explicit_unknown_id_is_an_honest_miss_naming_the_roster_door() -> None:
    a = _asset()
    resolved = _resolve_asset_target([a], uuid4())
    assert isinstance(resolved, str) and "No asset with id" in resolved
    assert "roster" in resolved
