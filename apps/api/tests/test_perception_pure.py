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
from datetime import UTC, datetime
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
        "get_node",
        "get_understanding",
        "list_caption_styles",
        "search_music",
        "get_run_status",
        "list_runs",
        "get_pending_plan",
        "get_asset",
        "get_craft_skeleton",
        "search_transcript",
        "get_segment",
        "get_artifact",
    }
    for name, entry in PERCEPTION_TOOLS.items():
        assert re.fullmatch(r"(get|list|search)_[a-z_]+", name), name
        assert entry.name == name
        assert entry.description.strip()
        assert callable(entry.execute)
        # The 碎碎念 copy key — the tool NAME never reaches the user face
        # (简报 §3 禁令); the key is what the SSE inspecting frame carries.
        # Two legal families (iter-2 ⑥, N-57): the generic inspecting
        # vocabulary, and the work-session family (search_transcript's
        # 改籍 seat — the discovery read rides chat.explore.searching).
        assert entry.activity_key.startswith(("chat.inspecting.", "chat.explore."))
        if entry.name == "search_transcript":
            assert entry.activity_key == "chat.explore.searching"


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


# ---- A-1 程序盲改修复 (2026-09-22): get_node's full-program renderer -----------
#
# The context's Graph section truncates programs at 140 chars, but the
# edit_graph rule requires composing the NEW program from the CURRENT one —
# get_node is the read-before-write seat. Gated here: the program rides
# VERBATIM under the budget cap (never silently truncated — a silent cut
# would re-open the blind-revision hole), and the detail lines carry
# state / products / downstream honestly.


def _node(**over) -> SimpleNamespace:
    base = dict(
        id=uuid4(),
        project_id=uuid4(),
        type="text",
        state="done",
        spec={
            "summary": "English post",
            "prompt": "Write a LinkedIn post about the talk.",
            "output_ids": [str(uuid4()), str(uuid4())],
        },
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestNodeDetailLines:
    def test_full_program_rides_verbatim_under_the_cap(self) -> None:
        from app.chat.perception.executes import (
            _NODE_PROGRAM_LIMIT,
            _node_detail_lines,
        )

        program = "p" * 500  # past the context's 140, far under the cap
        lines = _node_detail_lines(_node(spec={"prompt": program}), [])
        program_line = next(l for l in lines if l.startswith("- Program"))
        assert program_line == f"- Program (full): {program}"
        assert len(program) < _NODE_PROGRAM_LIMIT

    def test_over_cap_program_says_so_honestly(self) -> None:
        from app.chat.perception.executes import (
            _NODE_PROGRAM_LIMIT,
            _node_detail_lines,
        )

        program = "p" * (_NODE_PROGRAM_LIMIT + 100)
        lines = _node_detail_lines(_node(spec={"prompt": program}), [])
        program_line = next(l for l in lines if l.startswith("- Program"))
        assert f"truncated at {_NODE_PROGRAM_LIMIT}" in program_line
        assert program_line.startswith(f"- Program (full): {'p' * 100}")

    def test_state_products_and_downstream_render(self) -> None:
        from app.chat.perception.executes import _node_detail_lines

        node = _node()
        child_a, child_b = str(uuid4()), str(uuid4())
        lines = _node_detail_lines(node, [child_a, child_b])
        assert lines[0] == f"Node {node.id} — type=text, state=done"
        assert next(l for l in lines if l.startswith("- Label")) == (
            "- Label: English post"
        )
        products = next(l for l in lines if l.startswith("- Products"))
        assert products.startswith("- Products: 2 (ids: ")
        downstream = next(l for l in lines if l.startswith("- Downstream"))
        assert child_a in downstream and child_b in downstream

    def test_empty_spec_reads_honestly(self) -> None:
        from app.chat.perception.executes import _node_detail_lines

        lines = _node_detail_lines(_node(spec={}), [])
        assert "- Program: (none — this node's spec has no prompt)" in lines
        assert "- Products: none" in lines
        assert "- Downstream: none" in lines


# ---- 同族 read 洞 (审计 §7 d/e, 2026-09-22): run history + docked plan ------


class TestRunHistoryLines:
    def test_roster_newest_first_with_receipt_name(self) -> None:
        from app.chat.perception.executes import _run_history_lines

        run = SimpleNamespace(
            id=uuid4(),
            status="COMPLETED",
            created_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
            context={"name": "German post"},
        )
        lines = _run_history_lines([run])
        assert len(lines) == 1
        assert str(run.id) in lines[0]
        assert "COMPLETED" in lines[0] and "German post" in lines[0]
        assert "2026-09-22" in lines[0]

    def test_missing_context_and_name_read_cleanly(self) -> None:
        from app.chat.perception.executes import _run_history_lines

        run = SimpleNamespace(
            id=uuid4(), status="RUNNING", created_at=None, context=None
        )
        (line,) = _run_history_lines([run])
        assert "RUNNING" in line
        assert "started ?" in line  # the stamp helper's honest unknown
        assert line.count(" — ") == 1  # no empty name tail


class TestPendingPlanLines:
    def _plan(self, **intent_over):
        from app.models.schemas import InferredIntent, PendingPlan

        intent = InferredIntent(
            action="draft",
            tasks=[
                {"tool": "select_clips", "params": {"count": 3}},
                {"tool": "write_post", "params": {"language": "de"}},
            ],
            specific_instruction="focus on the Q&A section",
            caption_mode="bilingual",
            name=intent_over.pop("name", "German clips + post"),
            **intent_over,
        )
        return PendingPlan(prompt="剪三条德语短片加一篇帖子", intent=intent)

    def test_chain_instruction_and_mode_render(self) -> None:
        from app.chat.perception.executes import _pending_plan_lines

        lines = _pending_plan_lines(self._plan())
        joined = "\n".join(lines)
        assert "- Original request: 剪三条德语短片加一篇帖子" in joined
        assert "- Name: German clips + post" in joined
        assert "  - select_clips" in joined and '"count": 3' in joined
        assert "  - write_post" in joined and '"language": "de"' in joined
        assert "- Extra instruction: focus on the Q&A section" in joined
        assert "- Caption mode: bilingual" in joined

    def test_sparse_plan_renders_chain_only(self) -> None:
        from app.chat.perception.executes import _pending_plan_lines
        from app.models.schemas import InferredIntent, PendingPlan

        plan = PendingPlan(
            prompt="",
            intent=InferredIntent(
                action="draft", tasks=[{"tool": "write_post", "params": {}}]
            ),
        )
        lines = _pending_plan_lines(plan)
        assert lines == ["- Tasks:", "  - write_post"]


# ---- 信任锚注入 (ADR-083, 2026-09-17): the understanding digest formatter ----
#
# understanding_digest_lines is the ONE formatting law with two consumers
# (the get_understanding read + the plan turn's assemble injection). Gated
# here: the caps keep the digest prompt-sized, and the empty-stub shape
# reads as "nothing to say" ([]) so the caller's block simply stays absent.


class TestUnderstandingDigestLines:
    def test_full_row_renders_all_sections_capped(self) -> None:
        from app.chat.perception.executes import understanding_digest_lines
        from app.models.schemas import MaterialUnderstanding

        u = MaterialUnderstanding(
            overall_summary="x" * 400,
            core_thesis="y" * 300,
            themes=[f"t{i}" for i in range(12)],
            target_audience="z" * 200,
        )
        lines = understanding_digest_lines(u)
        assert lines[0] == f"- Summary: {'x' * 300}"
        assert lines[1] == f"- Core thesis: {'y' * 200}"
        assert lines[2] == "- Themes: " + ", ".join(f"t{i}" for i in range(8))
        assert lines[3] == f"- Audience: {'z' * 120}"

    def test_empty_stub_reads_as_nothing_to_say(self) -> None:
        from app.chat.perception.executes import understanding_digest_lines
        from app.models.schemas import MaterialUnderstanding

        assert understanding_digest_lines(
            MaterialUnderstanding(core_thesis="")
        ) == []

    def test_quotables_and_beats_render_counts_and_examples(self) -> None:
        from app.chat.perception.executes import understanding_digest_lines
        from app.models.schemas import MaterialUnderstanding, QuotableLine

        u = MaterialUnderstanding(
            core_thesis="thesis",
            quotable_lines=[
                QuotableLine.model_validate({"text": f"line {i}", "start": i, "end": i + 1})
                for i in range(5)
            ],
        )
        lines = understanding_digest_lines(u)
        quoted = next(l for l in lines if l.startswith("- Quotable lines:"))
        assert "5" in quoted and "line 0" in quoted and "line 3" not in quoted


# ---- 证据 reads (ADR-088 §2 拍 2, 2026-09-22 迭代一): search + segment -------


class TestCueMatchLines:
    def test_anchor_and_speaker_render(self) -> None:
        from app.chat.perception.executes import _cue_match_lines

        matches = [
            {"start": 12.3, "end": 18.7, "text": "pricing is hard", "hits": ["pricing"]},
            {"start": 40.0, "end": 46.0, "text": "pricing tiers", "hits": ["pricing"]},
        ]
        lines = _cue_match_lines(matches, {"turns": [{"start": 10.0, "end": 30.0, "speaker": "left"}]})
        assert lines[0] == "- [12.3–18.7] pricing is hard (left)"
        assert lines[1] == "- [40.0–46.0] pricing tiers"  # no turn → no speaker tail


class TestSegmentBody:
    def test_under_cap_verbatim(self) -> None:
        from app.chat.perception.executes import _segment_body

        words = [{"word": "hello", "start": 0.0, "end": 0.5}, {"word": "world", "start": 0.6, "end": 1.0}]
        text, truncated = _segment_body(words, 0.0, 1.0)
        assert text == "hello world"
        assert truncated is False

    def test_over_cap_says_so_honestly(self) -> None:
        from app.chat.perception.executes import _SEGMENT_TEXT_LIMIT, _segment_body

        words = [{"word": "p" * _SEGMENT_TEXT_LIMIT, "start": 0.0, "end": 1.0}, {"word": "tail", "start": 1.1, "end": 2.0}]
        text, truncated = _segment_body(words, 0.0, 2.0)
        assert truncated is True
        assert f"truncated at {_SEGMENT_TEXT_LIMIT}" in text
