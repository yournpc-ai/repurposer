"""cut_segments — the compiler-only clip birth capability (N-56, iter-2 ①).

Pure coverage (suite discipline: no DB, no LLM, no HTTP):

- **Params adjudication**: span ordering / the 1..5 bound / the aspect
  vocabulary — the compiler's contract lives in the params model, enforced
  through ``validate_task_list``.
- **Compiler-only citizenship**: registry-legal (dispatchable, adjudicates,
  folds into fill keys) but NEVER in the LLM-facing catalog — the agent
  cannot propose what it cannot see (``tool_catalog_lines`` is the only
  catalog projector; the consistency suite covers the prose blocks).
- **Compile composition**: a pure cut chain gets NO plan prelude and NO
  materialize_source injection, and claims with empty inputs; a cut+morph
  chain wires the morph off the cut via the ``after`` declaration; the spec
  carries segments / asset_id / aspect verbatim.
- **Label seat**: the generation branch labels off the compiled node class
  (node_cls.label) — select_clips' preset is byte-identical to the retired
  owner-routed seat, cut_segments labels itself.
- **Quote**: free zeros (mechanical assembly); the mid-run render fan-out
  stays unquoted (P4 NULL — the decision-package quote topic, iter-2 ③).
"""

from types import SimpleNamespace

import pytest

from app.models.schemas import TaskItem
from app.pipeline.graph import (
    MEDIA,
    NODE_KINDS,
    TRANSCRIPT,
    estimate_free,
    node_for_output,
)
from app.pipeline.graph_fill import _fill_key_for_step
from app.pipeline.orchestrator import TaskSpec, compile_graph
from app.models.schemas import IntentSlot
from app.tools import (
    TOOL_REGISTRY,
    ToolRejected,
    dispatchable_tools,
    tool_catalog_lines,
    validate_task_list,
)
from app.tools.clips.params import CutSegmentsParams, CutSegmentSpan


def _compile(tasks: list[TaskItem], **kwargs):
    return compile_graph(TaskSpec(tasks=tasks, ui_language="en"), **kwargs)


def _cut_task(segments=None, **extra) -> TaskItem:
    params = {"segments": segments or [{"start": 12.0, "end": 47.5}]}
    params.update(extra)
    return TaskItem(tool="cut_segments", params=params)


# ---- params adjudication -------------------------------------------------------


class TestParams:
    def test_span_must_be_ordered(self):
        with pytest.raises(ValueError, match="must exceed start"):
            CutSegmentSpan(start=10.0, end=10.0)
        with pytest.raises(ValueError):
            CutSegmentSpan(start=10.0, end=9.9)

    def test_span_count_bound_1_to_5(self):
        with pytest.raises(ValueError):
            CutSegmentsParams(segments=[])
        with pytest.raises(ValueError):
            CutSegmentsParams(
                segments=[{"start": i * 10.0, "end": i * 10.0 + 5} for i in range(6)]
            )
        five = CutSegmentsParams(
            segments=[{"start": i * 10.0, "end": i * 10.0 + 5} for i in range(5)]
        )
        assert len(five.segments) == 5

    def test_aspect_vocabulary(self):
        with pytest.raises(ValueError):
            CutSegmentsParams(
                segments=[{"start": 0.0, "end": 1.0}], aspect="4:3"
            )
        ok = CutSegmentsParams(segments=[{"start": 0.0, "end": 1.0}], aspect="16:9")
        assert ok.aspect == "16:9"

    def test_no_discovery_semantics_by_construction(self):
        """The discovery fields (count / focus / language) do not EXIST on the
        params model — and extra=forbid makes a smuggled key fail loudly."""
        assert set(CutSegmentsParams.model_fields) == {"segments", "asset_id", "aspect"}
        with pytest.raises(ValueError):
            CutSegmentsParams(
                segments=[{"start": 0.0, "end": 1.0}], count=3
            )

    def test_validate_task_list_adjudicates(self):
        """Registry-legal: a compiled chain carrying cut_segments passes the
        door; a bad span set is rejected with the tool named."""
        entries = validate_task_list([_cut_task()])
        assert [e.name for e in entries] == ["cut_segments"]
        with pytest.raises(ToolRejected, match="cut_segments"):
            validate_task_list([_cut_task(segments=[{"start": 5.0, "end": 5.0}])])


# ---- compiler-only citizenship (N-56) ------------------------------------------


class TestCompilerOnlyCitizenship:
    def test_registered_dispatchable_but_invisible(self):
        entry = TOOL_REGISTRY["cut_segments"]
        assert entry.llm_visible is False
        assert entry.behavior == "deterministic"
        assert entry in dispatchable_tools()
        # The ONLY catalog projector never shows it — both chat prompt call
        # sites read tool_catalog_lines.
        assert "cut_segments" not in tool_catalog_lines()

    def test_every_other_tool_stays_visible(self):
        """The flag's default guards the existing space: introducing a second
        invisible citizen is a deliberate act, never a forgotten field."""
        invisible = [
            name
            for name, entry in TOOL_REGISTRY.items()
            if not entry.llm_visible
        ]
        assert invisible == ["cut_segments"]

    def test_node_declarations(self):
        node = NODE_KINDS["cut_segments"]
        assert node.node_type == "video"
        assert node.prototype == "editor"
        assert node.output_type == "clips"
        assert node.requires == (MEDIA, TRANSCRIPT)
        assert node.produces_outputs is True
        assert node.needs_plan_prelude is False
        assert node.count_limits is None  # the span list IS the count

    def test_proposal_routing_still_owns_clips(self):
        """node_for_output("clips") resolves the PROPOSAL-space owner
        (select_clips), not the compiler-only co-claimant — role-pin dispatch
        and targeted paths keep their semantics regardless of import order."""
        owner = node_for_output("clips")
        assert owner is not None and owner.kind == "select_clips"


# ---- compile composition --------------------------------------------------------


class TestCompileComposition:
    def test_pure_cut_chain_no_prelude_no_injection(self):
        nodes = _compile([_cut_task(asset_id="a-1", aspect="1:1")])
        kinds = [ns.kind for ns in nodes]
        assert kinds == ["cut_segments"]
        ns = nodes[0]
        assert ns.inputs == []
        assert ns.spec["segments"] == [{"start": 12.0, "end": 47.5}]
        assert ns.spec["asset_id"] == "a-1"
        assert ns.spec["aspect"] == "1:1"
        assert ns.spec["slot"] == {"type": "clips"}
        # Label seat: the compiled class labels itself (static task name —
        # the slot carries no distinguishing tag).
        assert ns.spec["summary"] == "Cut segments"

    def test_cut_plus_morph_wires_after_without_injection(self):
        nodes = _compile(
            [
                _cut_task(),
                TaskItem(tool="translate_clip", params={"target_language": "zh"}),
            ]
        )
        kinds = [ns.kind for ns in nodes]
        assert "materialize_source" not in kinds
        assert kinds == ["cut_segments", "translate_clip"]
        cut_idx, tr_idx = 0, 1
        assert nodes[cut_idx].inputs == []
        # The morph hangs off the cut via its `after` declaration.
        assert nodes[tr_idx].inputs == [cut_idx]

    def test_modifier_only_chain_still_injects_materialize(self):
        """Regression guard: the declaration-driven producer check keeps the
        ADR-043 injection alive when NO clips producer rides the chain."""
        nodes = _compile(
            [TaskItem(tool="translate_clip", params={"target_language": "zh"})],
            materialize_profile="media",
        )
        kinds = [ns.kind for ns in nodes]
        assert "materialize_source" in kinds
        assert "preprocess" in kinds

    def test_select_clips_chain_still_skips_injection(self):
        """Regression guard: select_clips keeps its producer semantics under
        the generalized (output_type-declared) check."""
        nodes = _compile(
            [
                TaskItem(tool="select_clips", params={"count": 2}),
                TaskItem(tool="translate_clip", params={"target_language": "zh"}),
            ]
        )
        kinds = [ns.kind for ns in nodes]
        assert "materialize_source" not in kinds
        tr = nodes[kinds.index("translate_clip")]
        assert tr.inputs == [kinds.index("select_clips")]

    def test_mixed_chain_cut_claims_without_plan(self):
        """A writer sibling pulls in the plan prelude; the cut still waits on
        nothing (the exploration chat already did the understanding)."""
        nodes = _compile(
            [_cut_task(), TaskItem(tool="write_post", params={"language": "fr"})]
        )
        kinds = [ns.kind for ns in nodes]
        assert "plan" in kinds  # the writer's prelude
        cut = nodes[kinds.index("cut_segments")]
        post = nodes[kinds.index("write_post")]
        assert cut.inputs == []
        assert post.inputs == [kinds.index("plan")]

    def test_two_cuts_grow_two_fill_keys(self):
        nodes = _compile([_cut_task(), _cut_task(asset_id="a-2")])
        cuts = [ns for ns in nodes if ns.kind == "cut_segments"]
        assert len(cuts) == 2
        keys = {
            _fill_key_for_step(
                SimpleNamespace(kind=ns.kind, spec=ns.spec)
            )
            for ns in cuts
        }
        assert keys == {"cut_segments#clips#0", "cut_segments#clips#1"}

    def test_label_seat_identity_for_select_clips(self):
        """The node_cls.label seat is byte-identical to the retired
        owner-routed seat for every chain that existed before N-56."""
        nodes = _compile([TaskItem(tool="select_clips", params={"count": 2})])
        sel = nodes[[ns.kind for ns in nodes].index("select_clips")]
        owner = NODE_KINDS["select_clips"]
        assert sel.spec["summary"] == owner.label(
            IntentSlot.model_validate(sel.spec["slot"]), "en"
        )


# ---- quotation -----------------------------------------------------------------


class TestEstimate:
    def test_free_zeros(self):
        assert NODE_KINDS["cut_segments"].estimate({}) == estimate_free()
