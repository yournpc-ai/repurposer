"""Pure-function tests for the Deterministic Scope Classifier (ADR-087 §4,
Phase 4 Batch 1).

Scope discipline (same house rule as test_graph_wiring_pure.py): no
database, no LLM, no HTTP — NodeFact / EdgeFact / ChainFacts are plain
data constructed in place. The gatherers (load_graph_facts /
load_historical_chains) have no pure-test seat by design (the lifecycle
gatherer precedent); they get theirs when B2 / B5 wire the switches.

What this suite locks — the CONTRACT, not the implementation:

- three-value semantics: provably-inside → continuation, provably-outside
  → expansion, provable-neither-way → unproven; UNPROVEN → CONTINUATION
  must stay structurally impossible (Frozen Rule 10)
- the judged object is the RESULTING paid execution scope, never the
  operation name (D4) — the classifier's signature takes no ops at all;
  the unknown-tool / unknown-node-family case must classify by facts
  alone without raising (the op-agnostic extensibility lock, user-ruled
  2026-09-20)
- approved scope = run-born graph nodes (state != "draft") for graph
  entries, and historical confirmed chains for chain entries — a draft
  node executed is NEW paid work, never an approved continuation
- delete semantics (D4 interim): a leaf/island deletion with the
  surviving closure's upstream sets intact is a provable continuation;
  an upstream deletion is unproven, never guessed either way
- chain retry (D2): only an exact canonical match against a persisted
  chain proves approval — null-stripping and map-key order are erased,
  task order is NOT (it is the execution order); display/governance
  fields (name / autonomy / ui_language) are not the work
"""

from app.pipeline.scope_classifier import (
    CONTINUATION,
    EXPANSION,
    UNPROVEN,
    ChainFacts,
    EdgeFact,
    NodeFact,
    classify_chain_against_history,
    classify_graph_scope,
)

# ---- fact builders ---------------------------------------------------------------


def node(
    nid: str,
    *,
    state: str = "done",
    tool: str | None = None,
    fill_key: str | None = None,
    produces: bool | None = None,
    type: str = "text",
) -> NodeFact:
    return NodeFact(
        id=nid,
        type=type,
        state=state,
        fill_key=fill_key,
        tool=tool,
        produces_outputs=produces,
    )


def paid(nid: str, *, state: str = "done", tool: str = "write_post") -> NodeFact:
    """A tool-carrying output node (a generation member of the registry)."""
    return node(
        nid,
        state=state,
        tool=tool,
        fill_key=f"{tool}#{nid}",
        produces=True,
    )


def edge(src: str, dst: str, edge_type: str = "text") -> EdgeFact:
    return EdgeFact(from_node=src, to_node=dst, edge_type=edge_type)


def classify(pre_n, pre_e, post_n, post_e, run):
    return classify_graph_scope(
        pre_nodes=tuple(pre_n),
        pre_edges=tuple(pre_e),
        post_nodes=tuple(post_n),
        post_edges=tuple(post_e),
        run_node_ids=run,
    )


# ---- graph scope: trivial / approved continuation ---------------------------------


def test_no_run_requested_is_continuation():
    # A pure structural edit (no run op resolved) executes nothing paid.
    verdict = classify([], [], [], [], None)
    assert verdict.decision == CONTINUATION
    assert verdict.reasons == ("no_paid_execution",)


def test_approved_member_unchanged_inputs_is_continuation():
    # The edit_prompt-on-filled-node shape: pre done, post stale, same
    # topology — re-running approved work on its approved inputs.
    verdict = classify([paid("a")], [], [paid("a", state="stale")], [], ("a",))
    assert verdict.decision == CONTINUATION
    assert verdict.reasons == ()


def test_approved_member_with_tool_less_new_neighbor_is_continuation():
    # A new tool-less node (document / manual — never executable) riding
    # the closure does not expand the paid scope.
    pre = [paid("a")]
    post = [paid("a"), node("doc1", state="draft", tool=None, type="document")]
    verdict = classify(pre, [], post, [], ("a", "doc1"))
    assert verdict.decision == CONTINUATION
    assert verdict.reasons == ()


# ---- graph scope: provable expansion ----------------------------------------------


def test_new_paid_node_in_closure_is_expansion():
    pre = [paid("a")]
    post = [paid("a"), paid("b", state="draft", tool="translate")]
    verdict = classify(pre, [], post, [edge("a", "b")], ("b",))
    assert verdict.decision == EXPANSION
    assert verdict.reasons == ("new_paid_node:translate#b",)


def test_new_paid_branch_is_expansion():
    pre = [paid("a")]
    post = [paid("a"), paid("b", state="draft", tool="translate"), paid("c", state="draft", tool="dub")]
    edges = [edge("a", "b"), edge("b", "c")]
    verdict = classify(pre, [], post, edges, ("b", "c"))
    assert verdict.decision == EXPANSION
    assert verdict.reasons == ("new_paid_node:translate#b", "new_paid_node:dub#c")


def test_draft_member_executed_is_expansion():
    # Editing an unconfirmed draft never bypasses the dock (Rule 10).
    verdict = classify([paid("a", state="draft")], [], [paid("a", state="draft")], [], ("a",))
    assert verdict.decision == EXPANSION
    assert verdict.reasons == ("draft_node_executed:write_post#a",)


def test_fresh_project_all_draft_closure_is_expansion():
    # Empty approved baseline: every closure member is provably outside it.
    post = [paid("a", state="draft"), paid("b", state="draft", tool="select_clips")]
    verdict = classify([], [], post, [edge("a", "b")], ("a", "b"))
    assert verdict.decision == EXPANSION
    assert len(verdict.reasons) == 2


def test_inputs_grown_is_expansion():
    # A connect re-wires an approved member onto a strictly larger input
    # set — a configuration no approval covered (D4: expanded).
    pre = [paid("a"), node("m", tool=None, type="video")]
    post = [paid("a"), node("m", tool=None, type="video")]
    verdict = classify(pre, [], post, [edge("m", "a", "video")], ("a",))
    assert verdict.decision == EXPANSION
    assert verdict.reasons == ("closure_inputs_expanded:write_post#a",)


# ---- graph scope: unproven (never steered into continuation) -----------------------


def test_inputs_shrunk_is_unproven():
    # Upstream deletion starving an approved member — the D4-interim case.
    pre = [paid("a"), node("m", tool=None, type="video")]
    post = [paid("a")]
    verdict = classify(pre, [edge("m", "a", "video")], post, [], ("a",))
    assert verdict.decision == UNPROVEN
    assert verdict.reasons == ("closure_inputs_reduced:write_post#a",)


def test_mixed_input_change_is_unproven():
    pre = [paid("a"), node("m1", tool=None, type="video"), node("m2", tool=None, type="video")]
    post = list(pre)
    verdict = classify(pre, [edge("m1", "a", "video")], post, [edge("m2", "a", "video")], ("a",))
    assert verdict.decision == UNPROVEN
    assert verdict.reasons == ("closure_inputs_reduced:write_post#a",)


def test_closure_member_unknown_is_unproven():
    verdict = classify([paid("a")], [], [paid("a")], [], ("ghost",))
    assert verdict.decision == UNPROVEN
    assert verdict.reasons == ("closure_member_unknown:ghost",)


def test_unknown_tool_member_is_unproven_not_a_crash():
    # The extensibility lock: a node family / tool the current registry has
    # never heard of must classify BY FACTS (no op semantics, no registry
    # crash) — it can prove nothing, so it docks.
    future = node("x", state="draft", tool="future_tool", produces=None, type="hologram")
    verdict = classify([], [], [future], [], ("x",))
    assert verdict.decision == UNPROVEN
    assert verdict.reasons == ("unclassified_tool_member:future_tool@x",)


def test_unknown_tool_approved_member_changed_inputs_is_unproven():
    pre = [node("r", tool="legacy_tool", produces=None)]
    post = [node("r", tool="legacy_tool", produces=None), node("m", tool=None, type="video")]
    verdict = classify(pre, [], post, [edge("m", "r", "video")], ("r",))
    assert verdict.decision == UNPROVEN
    assert verdict.reasons == ("unclassified_tool_member:legacy_tool@r",)


# ---- graph scope: the delete spectrum (D4 interim) ---------------------------------


def test_island_delete_is_continuation():
    # Deleting an island touches no survivor's inputs — provably inside
    # the approved scope (J1: classification by facts, not by op name).
    pre = [paid("a"), paid("x", tool="write_article")]
    post = [paid("a")]
    verdict = classify(pre, [], post, [], ("a",))
    assert verdict.decision == CONTINUATION


def test_downstream_leaf_delete_is_continuation():
    # Deleting a terminal leaf changes no survivor's upstream set.
    pre = [paid("a"), paid("x", tool="write_article")]
    post = [paid("a")]
    verdict = classify(pre, [edge("a", "x")], post, [], ("a",))
    assert verdict.decision == CONTINUATION


# ---- graph scope: registry-internal members ride as notes only ---------------------


def test_internal_tool_member_is_note_only():
    # produces_outputs=False (e.g. research): cost folds into the family
    # estimate — visible as a note, never a verdict of its own (preflight
    # §8, in-册). (Wiring it INTO a paid member's upstream would be a real
    # input expansion for THAT member — see test_inputs_grown_is_expansion.)
    pre = [paid("a")]
    post = [paid("a"), node("r", state="draft", tool="research", produces=False)]
    verdict = classify(pre, [], post, [], ("r",))
    assert verdict.decision == CONTINUATION
    assert verdict.reasons == ("internal_tool_member:research@r",)


def test_internal_tool_member_note_rides_along_expansion():
    pre = [paid("a")]
    post = [
        paid("a"),
        node("r", state="draft", tool="research", produces=False),
        paid("b", state="draft", tool="translate"),
    ]
    verdict = classify(pre, [], post, [edge("a", "b")], ("r", "b"))
    assert verdict.decision == EXPANSION
    assert verdict.reasons == ("new_paid_node:translate#b", "internal_tool_member:research@r")


# ---- graph scope: determinism -------------------------------------------------------


def test_verdict_is_deterministic():
    pre = [paid("a")]
    post = [paid("a"), paid("b", state="draft", tool="translate")]
    first = classify(pre, [], post, [edge("a", "b")], ("b",))
    second = classify(pre, [], post, [edge("a", "b")], ("b",))
    assert first == second


# ---- chain scope: exact-retry proof (D2) --------------------------------------------

_TASKS = (
    {"tool": "write_post", "params": {"language": "en", "count": 2}},
    {"tool": "translate", "params": {"language": "fr"}},
)

_SPEC = {
    "target_language": "en",
    "persona_id": "p1",
    "caption_mode": "bilingual",
    "source_asset_id": "asset-1",
    "name": "Two posts",  # display — not the work
    "autonomy": "auto",  # execution governance — not the work
}


def _chain(tasks=_TASKS, spec=_SPEC) -> ChainFacts:
    return ChainFacts(tasks=tuple(tasks), spec=spec)


def test_exact_match_is_continuation():
    verdict = classify_chain_against_history(requested=_chain(), historical=(_chain(),))
    assert verdict.decision == CONTINUATION
    assert verdict.reasons == ("exact_retry",)


def test_param_difference_is_unproven():
    requested = _chain(
        tasks=(
            {"tool": "write_post", "params": {"language": "en", "count": 3}},
            {"tool": "translate", "params": {"language": "fr"}},
        )
    )
    verdict = classify_chain_against_history(requested=requested, historical=(_chain(),))
    assert verdict.decision == UNPROVEN
    assert verdict.reasons == ("no_exact_retry",)


def test_task_order_matters():
    requested = _chain(tasks=tuple(reversed(_TASKS)))
    verdict = classify_chain_against_history(requested=requested, historical=(_chain(),))
    assert verdict.decision == UNPROVEN


def test_null_params_and_key_order_are_erased():
    # "null = take the default": an explicit null proves nothing new; map
    # key order is not the work either.
    requested = _chain(
        tasks=(
            {"tool": "write_post", "params": {"count": 2, "language": "en", "tone": None}},
            {"tool": "translate", "params": {"language": "fr"}},
        )
    )
    verdict = classify_chain_against_history(requested=requested, historical=(_chain(),))
    assert verdict.decision == CONTINUATION


def test_display_and_governance_fields_are_not_the_work():
    requested = _chain(spec={**_SPEC, "name": "A different title", "autonomy": "review", "ui_language": "zh"})
    verdict = classify_chain_against_history(requested=requested, historical=(_chain(),))
    assert verdict.decision == CONTINUATION


def test_spec_work_field_difference_is_unproven():
    requested = _chain(spec={**_SPEC, "caption_mode": "source_only"})
    verdict = classify_chain_against_history(requested=requested, historical=(_chain(),))
    assert verdict.decision == UNPROVEN


def test_spec_field_present_in_history_but_absent_in_request_is_unproven():
    # Strictness is deliberate: the request must reproduce every work
    # field the confirmed chain carried (a persona swap is new work).
    requested = _chain(spec={k: v for k, v in _SPEC.items() if k != "persona_id"})
    verdict = classify_chain_against_history(requested=requested, historical=(_chain(),))
    assert verdict.decision == UNPROVEN


def test_empty_history_is_unproven():
    verdict = classify_chain_against_history(requested=_chain(), historical=())
    assert verdict.decision == UNPROVEN


def test_match_against_any_historical_chain():
    other = _chain(tasks=({"tool": "dub", "params": {"language": "de"}},), spec={"target_language": "de"})
    verdict = classify_chain_against_history(requested=_chain(), historical=(other, _chain()))
    assert verdict.decision == CONTINUATION
