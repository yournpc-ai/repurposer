"""scope_compile — the Content Plan → Execution Scope compiler (iter-2, ADR-089 §2).

Pure coverage (no DB, no LLM, no HTTP). Acceptance #1 of the iter-2
contract: the full output-mapping spectrum (clip ± language version / the
four writers / pointer resolution / the rejection loop), and the structural
law — a compiled chain NEVER contains select_clips (the execution world has
no second discoverer).
"""

from types import SimpleNamespace

import pytest

from app.pipeline.exploration_store import (
    CandidateSetSpec,
    ContentPlanSpec,
    SelectSpec,
)
from app.pipeline.scope_compile import ScopeCompileRejected, compile_plans

CSET_ID = "11111111-1111-1111-1111-111111111111"
SEL_ID = "22222222-2222-2222-2222-222222222222"
PLAN_ID = "33333333-3333-3333-3333-333333333333"
ASSET_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _cset(members=None) -> SimpleNamespace:
    members = members or [
        {"start": 12.0, "end": 18.9, "excerpt": "Our pricing is simple.", "speaker": "host"},
        {"start": 34.0, "end": 39.4, "excerpt": "Every tier includes the dashboard.", "speaker": None},
    ]
    spec = CandidateSetSpec(asset_id=ASSET_ID, topic="pricing", members=members)
    return SimpleNamespace(id=CSET_ID, spec=spec.model_dump(mode="json"), state="ready")


def _select(member_index: int = 0, sel_id: str = SEL_ID) -> SimpleNamespace:
    spec = SelectSpec(
        candidate_set_id=CSET_ID,
        member_index=member_index,
        verdict="Most complete answer",
        reason="It covers pricing end to end",
    )
    return SimpleNamespace(id=sel_id, spec=spec.model_dump(mode="json"), state="ready")


def _plan(outputs, state: str = "ready", plan_id: str = PLAN_ID, issues=None) -> SimpleNamespace:
    spec = ContentPlanSpec(select_id=SEL_ID, title="Pricing clip", outputs=outputs)
    payload = spec.model_dump(mode="json")
    if issues:
        payload["issues"] = issues
    return SimpleNamespace(id=plan_id, spec=payload, state=state)


def _compile(plans, **kwargs):
    kwargs.setdefault("source_language", "en")
    return compile_plans(plans, [_select()], [_cset()], **kwargs)


# ---- clip mapping (± language version) ----------------------------------------


class TestClipMapping:
    def test_bare_clip_compiles_to_cut_only(self):
        tasks = _compile(_plan_rows := [_plan([{"kind": "clip"}])])
        assert [t.tool for t in tasks] == ["cut_segments"]
        params = tasks[0].params
        assert params["segments"] == [{"start": 12.0, "end": 18.9}]
        assert params["asset_id"] == ASSET_ID
        assert "aspect" not in params

    def test_clip_with_aspect_carries_the_birth_frame(self):
        tasks = _compile([_plan([{"kind": "clip", "aspect": "1:1"}])])
        assert tasks[0].params["aspect"] == "1:1"

    def test_language_version_continues_with_translate(self):
        tasks = _compile([_plan([{"kind": "clip", "language": "fr"}])])
        assert [t.tool for t in tasks] == ["cut_segments", "translate_clip"]
        assert tasks[1].params == {"target_language": "fr", "bilingual": False}

    def test_bilingual_caption_mode_maps_the_flag(self):
        tasks = _compile(
            [_plan([{"kind": "clip", "language": "fr", "caption_mode": "bilingual"}])]
        )
        assert tasks[1].params == {"target_language": "fr", "bilingual": True}

    def test_dub_continues_with_dub_clip(self):
        tasks = _compile(
            [_plan([{"kind": "clip", "language": "fr", "dub": True}])]
        )
        assert [t.tool for t in tasks] == ["cut_segments", "dub_clip"]
        assert tasks[1].params == {"target_language": "fr"}

    def test_source_language_clip_needs_no_continuation(self):
        tasks = _compile([_plan([{"kind": "clip", "language": "en"}])])
        assert [t.tool for t in tasks] == ["cut_segments"]

    def test_unknown_source_still_honors_the_named_language(self):
        tasks = compile_plans(
            [_plan([{"kind": "clip", "language": "fr"}])],
            [_select()],
            [_cset()],
            source_language=None,
        )
        assert [t.tool for t in tasks] == ["cut_segments", "translate_clip"]

    def test_source_only_captions_with_a_target_language_is_a_rejection(self):
        with pytest.raises(ScopeCompileRejected, match="source_only"):
            _compile(
                [_plan([{"kind": "clip", "language": "fr", "caption_mode": "source_only"}])]
            )


# ---- writer mapping -------------------------------------------------------------


class TestWriterMapping:
    @pytest.mark.parametrize(
        "kind,tool",
        [
            ("post", "write_post"),
            ("article", "write_article"),
            ("quotes", "write_quotes"),
            ("carousel", "write_carousel"),
        ])
    def test_four_writers(self, kind, tool):
        tasks = _compile([_plan([{"kind": kind, "language": "de", "brief": "the pricing angle"}])])
        assert [t.tool for t in tasks] == [tool]
        params = tasks[0].params
        assert params["language"] == "de"
        # The plan's per-output brief rides the existing focus field.
        assert params["focus"] == "the pricing angle"
        # The writer's material narrows to the select's span (iter-2 ②).
        assert params["source_span"] == {
            "start": 12.0,
            "end": 18.9,
            "asset_id": ASSET_ID,
        }

    def test_writer_language_defaults(self):
        tasks = _compile([_plan([{"kind": "post"}])], default_language="zh")
        assert tasks[0].params["language"] == "zh"
        assert "focus" not in tasks[0].params  # no brief → no focus key

    def test_span_pointer_follows_the_selects_member(self):
        tasks = compile_plans(
            [_plan([{"kind": "post", "language": "en"}])],
            [_select(member_index=1)],
            [_cset()],
            source_language="en",
        )
        assert tasks[0].params["source_span"]["start"] == 34.0


# ---- the rejection loop ---------------------------------------------------------


class TestRejections:
    def test_draft_plan_rejects_with_its_issues(self):
        with pytest.raises(ScopeCompileRejected, match="open gaps.*bilingual"):
            _compile(
                [_plan(
                    [{"kind": "clip", "caption_mode": "bilingual"}],
                    state="draft",
                    issues=["output 0: bilingual captions need a target language"],
                )]
            )

    def test_compiled_or_superseded_never_recompile(self):
        for state in ("compiled", "superseded"):
            with pytest.raises(ScopeCompileRejected, match=state):
                _compile([_plan([{"kind": "post"}], state=state)])

    def test_revised_plans_compile(self):
        tasks = _compile([_plan([{"kind": "post", "language": "en"}], state="revised")])
        assert [t.tool for t in tasks] == ["write_post"]

    def test_unresolvable_select_pointer(self):
        with pytest.raises(ScopeCompileRejected, match="not in this journey's selects"):
            compile_plans(
                [_plan([{"kind": "post"}])], [], [_cset()], source_language="en"
            )

    def test_missing_candidate_set(self):
        with pytest.raises(ScopeCompileRejected, match="candidate set"):
            compile_plans(
                [_plan([{"kind": "post"}])], [_select()], [], source_language="en"
            )

    def test_member_index_outside_the_set(self):
        with pytest.raises(ScopeCompileRejected, match="outside the candidate set"):
            compile_plans(
                [_plan([{"kind": "post"}])],
                [_select(member_index=9)],
                [_cset()],
                source_language="en",
            )

    def test_no_plans_is_a_rejection(self):
        with pytest.raises(ScopeCompileRejected, match="no content plans"):
            compile_plans([], [_select()], [_cset()], source_language="en")

    def test_registry_adjudication_reenters(self):
        """The task cap is real money — an over-wide package is a compile
        rejection (B3 上移: only registry-legal chains reach the dock)."""
        plans = [
            _plan(
                [{"kind": "clip"}, {"kind": "post"}],
                plan_id=f"44444444-4444-4444-4444-{i:012d}",
            )
            for i in range(6)  # 6 × 2 = 12 tasks > MAX_TASKS_PER_RUN
        ]
        with pytest.raises(ScopeCompileRejected, match="tasks max"):
            _compile(plans)


# ---- chain shape -----------------------------------------------------------------


class TestChainShape:
    def test_multi_plan_chain_order(self):
        plans = [
            _plan([{"kind": "clip", "language": "fr"}], plan_id="55555555-5555-5555-5555-555555555551"),
            _plan([{"kind": "post", "language": "en"}], plan_id="55555555-5555-5555-5555-555555555552"),
        ]
        tasks = _compile(plans)
        assert [t.tool for t in tasks] == ["cut_segments", "translate_clip", "write_post"]

    def test_never_select_clips(self):
        """The structural law: no compiled chain ever contains the
        discovery-flavored execution tool (R12 + iter-1 开工裁决)."""
        plans = [
            _plan(
                [
                    {"kind": "clip", "language": "fr", "dub": True},
                    {"kind": "post", "language": "en", "brief": "angle"},
                    {"kind": "quotes", "language": "zh"},
                    {"kind": "carousel"},
                    {"kind": "article", "language": "de"},
                ]
            )
        ]
        tasks = _compile(plans)
        assert "select_clips" not in [t.tool for t in tasks]
        assert [t.tool for t in tasks] == [
            "cut_segments",
            "dub_clip",
            "write_post",
            "write_quotes",
            "write_carousel",
            "write_article",
        ]


# ---- ④ Confirmed Scope Snapshot (ADR-089 §4 R20 — 销 P0-①) -------------------


class TestConfirmedScopeSnapshot:
    def test_shape(self):
        from app.models.schemas import TaskItem
        from app.pipeline.scope_compile import build_confirmed_scope

        snap = build_confirmed_scope(
            confirmation_id="msg-1",
            confirmed_at="2026-09-23T00:00:00+00:00",
            confirmed_via="dock_pill",
            plans=[
                {
                    "plan_id": "p1",
                    "title": "Pricing clip",
                    "state": "ready",
                    "outputs": [],
                }
            ],
            tasks=[TaskItem(tool="write_post", params={"language": "en"})],
            quote={"total": [10, 20], "per_task": [[10, 20]]},
        )
        assert snap == {
            "confirmation_id": "msg-1",
            "confirmed_at": "2026-09-23T00:00:00+00:00",
            "confirmed_via": "dock_pill",
            "plans": [
                {
                    "plan_id": "p1",
                    "title": "Pricing clip",
                    "state": "ready",
                    "outputs": [],
                }
            ],
            "compiled_scope": [{"tool": "write_post", "params": {"language": "en"}}],
            "quote": {"total": [10, 20], "per_task": [[10, 20]]},
        }

    def test_router_drafted_dock_carries_empty_plans(self):
        """读容忍: a router-drafted dock has no Content Plans — the chain IS
        the whole package, and the snapshot records plans=[] (never a
        fabricated reading layer)."""
        from app.models.schemas import TaskItem
        from app.pipeline.scope_compile import build_confirmed_scope

        snap = build_confirmed_scope(
            confirmation_id="msg-2",
            confirmed_at="2026-09-23T00:00:00+00:00",
            confirmed_via="chat_reply",
            plans=[],
            tasks=[
                TaskItem(
                    tool="cut_segments",
                    params={"segments": [{"start": 1.0, "end": 2.0}]},
                )
            ],
            quote=None,
        )
        assert snap["plans"] == []
        assert snap["quote"] is None
        assert snap["confirmed_via"] == "chat_reply"
        assert snap["compiled_scope"][0]["tool"] == "cut_segments"

    def test_snapshot_is_json_round_trippable(self):
        """The stamp rides run.context (JSONB) — the shape must serialize."""
        import json

        from app.models.schemas import TaskItem
        from app.pipeline.scope_compile import build_confirmed_scope

        snap = build_confirmed_scope(
            confirmation_id="msg-3",
            confirmed_at="2026-09-23T00:00:00+00:00",
            confirmed_via="dock_pill",
            plans=[],
            tasks=[TaskItem(tool="write_article", params={"language": "de"})],
            quote=None,
        )
        assert json.loads(json.dumps(snap)) == snap


# ---- iter-3 S1: CompiledScope (E1) + plan_task_map (E2) + R20 router ---------------


class TestCompiledScopeMap:
    """E1/E2: the map is born WITH the compile — every plan pinned to its
    half-open task range; ranges tile the chain contiguously, in plan
    order; the iter-2 wrapper diffs zero."""

    def test_map_pins_every_plan_to_its_slice(self):
        from app.pipeline.scope_compile import compile_scope

        plans = [
            _plan(
                [{"kind": "clip", "language": "fr", "dub": True}],  # 2 tasks
                plan_id="55555555-5555-5555-5555-555555555551",
            ),
            _plan(
                [{"kind": "post"}, {"kind": "quotes", "language": "de"}],  # 2 tasks
                plan_id="55555555-5555-5555-5555-555555555552",
            ),
            _plan(
                [{"kind": "clip"}],  # 1 task
                plan_id="55555555-5555-5555-5555-555555555553",
            ),
        ]
        scope = compile_scope(plans, [_select()], [_cset()], source_language="en")
        assert scope.plan_task_map == {
            "55555555-5555-5555-5555-555555555551": [0, 2],
            "55555555-5555-5555-5555-555555555552": [2, 4],
            "55555555-5555-5555-5555-555555555553": [4, 5],
        }
        # Ranges tile the whole chain, contiguously, in plan order.
        assert [t.tool for t in scope.tasks] == [
            "cut_segments", "dub_clip", "write_post", "write_quotes", "cut_segments",
        ]

    def test_wrapper_is_a_thin_passthrough(self):
        from app.pipeline.scope_compile import compile_scope

        plans = [_plan([{"kind": "post", "language": "de"}])]
        scope = compile_scope(plans, [_select()], [_cset()], source_language="en")
        legacy = compile_plans(plans, [_select()], [_cset()], source_language="en")
        assert [t.model_dump() for t in legacy] == [t.model_dump() for t in scope.tasks]
        assert scope.plan_task_map == {PLAN_ID: [0, 1]}


class TestSnapshotPlanTaskMap:
    def test_map_rides_when_provided(self):
        from app.models.schemas import TaskItem
        from app.pipeline.scope_compile import build_confirmed_scope

        snap = build_confirmed_scope(
            confirmation_id="msg-1",
            confirmed_at="2026-09-23T00:00:00+00:00",
            confirmed_via="dock_pill",
            plans=[{"plan_id": "p1", "title": "t", "state": "ready", "outputs": []}],
            tasks=[TaskItem(tool="write_post", params={"language": "en"})],
            quote=None,
            plan_task_map={"p1": [0, 1]},
        )
        assert snap["plan_task_map"] == {"p1": [0, 1]}

    def test_legacy_snapshot_omits_the_key(self):
        """读容忍: router-drafted docks carry no map — the key is ABSENT
        (never null), so the router's absence check is a single lookup."""
        from app.models.schemas import TaskItem
        from app.pipeline.scope_compile import build_confirmed_scope

        snap = build_confirmed_scope(
            confirmation_id="msg-2",
            confirmed_at="2026-09-23T00:00:00+00:00",
            confirmed_via="chat_reply",
            plans=[],
            tasks=[TaskItem(tool="write_post", params={"language": "en"})],
            quote=None,
        )
        assert "plan_task_map" not in snap


class TestFillKeyProjectionParity:
    """One law, two mirrors: the router's TaskItem-sourced projection MUST
    match the stamp-time law (compile_graph + graph_fill._fill_key_for_step)
    across the exploration vocabulary. Drift = a red row here."""

    def _parity(self, tasks):
        from app.pipeline.graph_fill import _fill_key_for_step
        from app.pipeline.orchestrator import TaskSpec, compile_graph
        from app.pipeline.scope_compile import _scope_fill_keys

        real = {
            _fill_key_for_step(ns)
            for ns in compile_graph(TaskSpec(tasks=list(tasks)))
        }
        projected = _scope_fill_keys(list(tasks))
        # Every projected key is a real stamped key (prelude/verify nodes
        # add bare-kind keys outside the projection's scope).
        assert set(projected) <= real
        # And no duplicates inside the projection (a dup = ambiguous target).
        assert len(projected) == len(set(projected))
        return projected

    def test_bare_clip(self):
        from app.models.schemas import TaskItem

        assert self._parity([
            TaskItem(tool="cut_segments", params={"segments": [{"start": 1.0, "end": 2.0}]}),
        ]) == ["cut_segments#clips#0"]

    def test_clip_with_translate_continuation(self):
        from app.models.schemas import TaskItem

        assert self._parity([
            TaskItem(tool="cut_segments", params={"segments": [{"start": 1.0, "end": 2.0}]}),
            TaskItem(tool="translate_clip", params={"target_language": "fr", "bilingual": True}),
        ]) == ["cut_segments#clips#0", "translate_clip#fr#True#False"]

    def test_autofork_flips_two_variants(self):
        from app.models.schemas import TaskItem

        assert self._parity([
            TaskItem(tool="cut_segments", params={"segments": [{"start": 1.0, "end": 2.0}]}),
            TaskItem(tool="translate_clip", params={"target_language": "fr"}),
            TaskItem(tool="dub_clip", params={"target_language": "de"}),
        ]) == [
            "cut_segments#clips#0",
            "translate_clip#fr#False#True",  # autofork
            "dub_clip#de#False#True",
        ]

    def test_same_type_writers_take_ordinals(self):
        from app.models.schemas import TaskItem

        assert self._parity([
            TaskItem(tool="write_post", params={"language": "en"}),
            TaskItem(tool="write_post", params={"language": "de"}),
            TaskItem(tool="write_quotes", params={"language": "zh"}),
        ]) == ["write_post#post#0", "write_post#post#1", "write_quotes#quotes#0"]

    def test_full_house_two_plans(self):
        from app.models.schemas import TaskItem

        assert self._parity([
            TaskItem(tool="cut_segments", params={"segments": [{"start": 1.0, "end": 2.0}]}),
            TaskItem(tool="dub_clip", params={"target_language": "fr"}),
            TaskItem(tool="write_post", params={"language": "en"}),
            TaskItem(tool="cut_segments", params={"segments": [{"start": 3.0, "end": 4.0}]}),
            TaskItem(tool="translate_clip", params={"target_language": "de", "bilingual": True}),
            TaskItem(tool="write_article", params={"language": "de"}),
        ]) == [
            "cut_segments#clips#0",
            "dub_clip#fr#False#True",
            "write_post#post#0",
            "cut_segments#clips#1",
            "translate_clip#de#True#True",
            "write_article#article#0",
        ]


# ---- R20 revision router (iter-3 S1) ----------------------------------------------

_PLAN_A = "55555555-5555-5555-5555-5555555555a1"
_PLAN_B = "55555555-5555-5555-5555-5555555555a2"


def _router_snapshot():
    """Two plans: A = clip+post (tasks 0..2), B = clip (task 3)."""
    from app.models.schemas import TaskItem

    tasks = [
        TaskItem(tool="cut_segments", params={"segments": [{"start": 1.0, "end": 2.0}]}),
        TaskItem(tool="translate_clip", params={"target_language": "fr"}),
        TaskItem(tool="write_post", params={"language": "en"}),
        TaskItem(tool="cut_segments", params={"segments": [{"start": 3.0, "end": 4.0}]}),
    ]
    return {
        "confirmation_id": "msg-1",
        "confirmed_at": "2026-09-23T00:00:00+00:00",
        "confirmed_via": "dock_pill",
        "plans": [
            {"plan_id": _PLAN_A, "title": "A", "state": "compiled", "outputs": []},
            {"plan_id": _PLAN_B, "title": "B", "state": "compiled", "outputs": []},
        ],
        "compiled_scope": [t.model_dump(mode="json") for t in tasks],
        "quote": None,
        "plan_task_map": {_PLAN_A: [0, 3], _PLAN_B: [3, 4]},
    }


def _node(fill_key, node_id, output_ids=()):
    return SimpleNamespace(
        id=node_id,
        spec={"fill_key": fill_key, "output_ids": list(output_ids)},
    )


def _router_nodes():
    return [
        _node("cut_segments#clips#0", "node-cut-a", ["out-clip-a"]),
        _node("translate_clip#fr#False#False", "node-tr-a", ["out-clip-a-fr"]),
        _node("write_post#post#0", "node-post-a", ["out-post-a"]),
        _node("cut_segments#clips#1", "node-cut-b", ["out-clip-b"]),
    ]


class TestRouteRevision:
    def test_empty_target_degrades(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), _router_nodes())
        assert route.status == "degrade"
        assert "no target" in route.reason

    def test_ordinal_resolves_second_plan(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), _router_nodes(), plan_ref="2")
        assert route.status == "ok"
        assert route.plan_id == _PLAN_B
        assert route.node_ids == ("node-cut-b",)
        assert route.unmatched_keys == ()

    @pytest.mark.parametrize("ref", ["1", "plan 1", "#1", "Plan 1"])
    def test_ordinal_spellings(self, ref):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), _router_nodes(), plan_ref=ref)
        assert route.status == "ok", route.reason
        assert route.plan_id == _PLAN_A
        assert route.node_ids == ("node-cut-a", "node-tr-a", "node-post-a")

    def test_plan_id_verbatim(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), _router_nodes(), plan_ref=_PLAN_B)
        assert route.status == "ok"
        assert route.node_ids == ("node-cut-b",)

    def test_ordinal_out_of_range_degrades(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), _router_nodes(), plan_ref="9")
        assert route.status == "degrade"
        assert "none of the 2 confirmed plans" in route.reason

    def test_unknown_ref_degrades(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), _router_nodes(), plan_ref="the blue one")
        assert route.status == "degrade"

    def test_legacy_run_without_snapshot_degrades(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(None, _router_nodes(), plan_ref="1")
        assert route.status == "degrade"
        assert "predates the confirmed-scope snapshot" in route.reason

    def test_snapshot_without_map_degrades(self):
        from app.pipeline.scope_compile import route_revision

        snap = _router_snapshot()
        del snap["plan_task_map"]
        route = route_revision(snap, _router_nodes(), plan_ref="1")
        assert route.status == "degrade"
        assert "plan→task map" in route.reason

    def test_partial_match_is_honest(self):
        from app.pipeline.scope_compile import route_revision

        nodes = [n for n in _router_nodes() if n.id != "node-tr-a"]
        route = route_revision(_router_snapshot(), nodes, plan_ref="1")
        assert route.status == "ok"
        assert route.node_ids == ("node-cut-a", "node-post-a")
        assert route.unmatched_keys == ("translate_clip#fr#False#False",)

    def test_all_nodes_gone_degrades(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), [], plan_ref="1")
        assert route.status == "degrade"
        assert "gone from the canvas" in route.reason

    def test_output_pin_resolves_the_producer(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), _router_nodes(), output_id="out-clip-a-fr")
        assert route.status == "ok"
        assert route.node_ids == ("node-tr-a",)
        assert route.plan_id == _PLAN_A  # best-effort membership context

    def test_output_pin_unknown_degrades(self):
        from app.pipeline.scope_compile import route_revision

        route = route_revision(_router_snapshot(), _router_nodes(), output_id="out-nope")
        assert route.status == "degrade"
        assert "not on this project's canvas" in route.reason

    def test_output_pin_without_snapshot_still_resolves(self):
        """The @output pin never needs the map — membership context simply
        stays unknown on a legacy run."""
        from app.pipeline.scope_compile import route_revision

        route = route_revision(None, _router_nodes(), output_id="out-post-a")
        assert route.status == "ok"
        assert route.node_ids == ("node-post-a",)
        assert route.plan_id is None
