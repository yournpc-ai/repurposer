"""Pure tests for revise_output's code side (iter-3 S3, ADR-089 §6 / E4).

The R19 craft half's deterministic core, gated without DB/LLM/HTTP:

- **ReviseOutputArgs** (schemas): the pointing's read tolerance (target /
  plan_ref / output_id / instruction null → defaults), the pending
  disposition envelope seat, extra-forbid.
- **assemble_craft_revision** (scope_compile, R19 消费侧纯核): the
  prompt-consumer gate (writers + the legacy selector = editable programs;
  cut_segments / translate_clip / dub_clip = deterministic stations, never
  silently "revised"), the ops shape (edit_prompt per editable node + the
  closing bare run), the partial cover's uncovered labels, and the
  all-deterministic honest degrade (None).
- **compose_revised_program**: the program absorbs the instruction verbatim
  as a trailing clause (R12 — code composes, the LLM never writes wiring).
"""

from uuid import uuid4

import pytest

from app.models.schemas import ReviseOutputArgs, ReviseOutputTarget
from app.pipeline.scope_compile import (
    assemble_craft_revision,
    compose_revised_program,
)


class _Node:
    """A graph-row stand-in (the assembly reads id / spec / type off it —
    same duck-typing as the compiler's preview rows)."""

    def __init__(self, tool: str, *, prompt: str = "", summary: str = "", type_: str = "video"):
        self.id = uuid4()
        self.spec = {"tool": tool, "summary": summary}
        if prompt:
            self.spec["prompt"] = prompt
        self.type = type_


# ---- the args shape ---------------------------------------------------------------


class TestReviseOutputArgs:
    def test_read_tolerance_nulls(self) -> None:
        args = ReviseOutputArgs.model_validate(
            {"target": None, "instruction": None}
        )
        assert args.target == ReviseOutputTarget()
        assert args.instruction == ""
        assert args.pending_disposition == "none"

    def test_target_inner_nulls(self) -> None:
        args = ReviseOutputArgs.model_validate(
            {
                "target": {"plan_ref": None, "output_id": None},
                "instruction": "短一点",
            }
        )
        assert args.target.plan_ref is None
        assert args.target.output_id is None
        assert args.instruction == "短一点"

    def test_pointing_channels(self) -> None:
        oid = uuid4()
        by_plan = ReviseOutputArgs.model_validate(
            {"target": {"plan_ref": "2"}, "instruction": "shorter"}
        )
        assert by_plan.target.plan_ref == "2"
        by_pin = ReviseOutputArgs.model_validate(
            {"target": {"output_id": str(oid)}, "instruction": "shorter"}
        )
        assert by_pin.target.output_id == oid

    def test_bare_number_ordinal_coerces(self) -> None:
        # prompt_gate probe G 实测 (2026-09-23): the provider emits the
        # ordinal as an int ('plan 2' → 2); the schema absorbs the dialect.
        args = ReviseOutputArgs.model_validate(
            {"target": {"plan_ref": 2}, "instruction": "shorter"}
        )
        assert args.target.plan_ref == "2"

    def test_pending_disposition_seat(self) -> None:
        args = ReviseOutputArgs.model_validate(
            {
                "target": {"plan_ref": "1"},
                "instruction": "x",
                "pending_disposition": "skip",
            }
        )
        assert args.pending_disposition == "skip"
        with pytest.raises(Exception):
            ReviseOutputArgs.model_validate(
                {
                    "target": {"plan_ref": "1"},
                    "instruction": "x",
                    "pending_disposition": "maybe",
                }
            )

    def test_extra_forbidden(self) -> None:
        with pytest.raises(Exception):
            ReviseOutputArgs.model_validate(
                {"target": {"plan_ref": "1"}, "instruction": "x", "ops": []}
            )


# ---- the program composition --------------------------------------------------------


class TestComposeRevisedProgram:
    def test_instruction_appends_as_a_clause(self) -> None:
        assert compose_revised_program("Write a post in FR", "shorter hook") == (
            "Write a post in FR\n\nshorter hook"
        )

    def test_empty_current_is_the_instruction(self) -> None:
        assert compose_revised_program("", "shorter hook") == "shorter hook"

    def test_empty_instruction_keeps_the_program(self) -> None:
        assert compose_revised_program("Write a post", "  ") == "Write a post"


# ---- the prompt-consumer gate + ops assembly ------------------------------------------


class TestAssembleCraftRevision:
    def test_writer_nodes_get_edit_prompt_plus_bare_run(self) -> None:
        nodes = [
            _Node("write_post", prompt="Write a post in FR", summary="Post FR"),
            _Node("write_quotes", prompt="Write quote cards", summary="Quotes"),
        ]
        craft = assemble_craft_revision(nodes, "更尖锐一点")
        assert craft is not None
        assert craft.uncovered == ()
        *edits, run = craft.ops
        assert [e["op"] for e in edits] == ["edit_prompt", "edit_prompt"]
        assert edits[0]["node"] == str(nodes[0].id)
        assert edits[0]["prompt"] == "Write a post in FR\n\n更尖锐一点"
        assert edits[1]["prompt"] == "Write quote cards\n\n更尖锐一点"
        # The closing run is BARE — the door closes over the edited nodes ∪
        # downstream itself (never name nodes on a run op).
        assert run == {"op": "run"}

    def test_all_deterministic_is_the_honest_degrade(self) -> None:
        nodes = [
            _Node("cut_segments", summary="Cut 0–60s"),
            _Node("translate_clip", summary="Subtitles FR"),
        ]
        assert assemble_craft_revision(nodes, "字幕短一点") is None

    def test_partial_cover_names_the_uncovered(self) -> None:
        nodes = [
            _Node("cut_segments", summary="Cut 0–60s"),
            _Node("write_post", prompt="Write a post", summary="Post"),
        ]
        craft = assemble_craft_revision(nodes, "sharper")
        assert craft is not None
        assert [op["op"] for op in craft.ops] == ["edit_prompt", "run"]
        assert craft.uncovered == ("Cut 0–60s",)

    def test_legacy_writer_without_a_prompt_still_editable(self) -> None:
        # The gate reads the TOOL (the family's semantic), never the prompt
        # key's presence — a legacy row stamped without one composes from
        # the instruction alone.
        craft = assemble_craft_revision(
            [_Node("write_article", summary="Article")], "add a CTA"
        )
        assert craft is not None
        assert craft.ops[0]["prompt"] == "add a CTA"

    def test_legacy_selector_is_prompt_consuming(self) -> None:
        # select_clips (legacy runs only — the compiler never births it):
        # its prompt IS the selection intent, a real program.
        craft = assemble_craft_revision(
            [_Node("select_clips", prompt="Cut 3 clips, focus: pricing")],
            "更争议一点",
        )
        assert craft is not None
        assert craft.ops[0]["prompt"].endswith("更争议一点")
