"""Pure-function tests for the intent/ask/checkpoint layer.

Scope discipline (why this suite exists and what it must never become): the
old API test suite was removed because it drifted with storage/API changes.
This suite therefore covers ONLY deterministic pure functions — no database,
no LLM, no HTTP, no fixtures beyond in-memory model objects. If a behavior
needs a DB or an LLM to verify, it belongs to a manual e2e run, not here.

Covered:
- compile_graph topologies (orchestrator): auto/review full runs, targeted,
  mode②, hook/clip, render; ordered_slots; slot_step_label
- derive_context_fields (mode② backfill)
- _match_option (deterministic autoResume mapping)
- merge_explicit_slots (pin-merge)
- _align_storyboard_slots (explicit slot fields binding)
- _checkpoint_direction (answer → task_book direction; stub db)
- _format_step_progress (G-2 node-level progress lines)
- is_pending_task_book (G-1 startable-confirmation predicate)
- AnswerProposal in the IntentResult union (G-4 fourth state)
- InferredIntent action="start" (G-1 third action)
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.chat.service import (
    _format_step_progress,
    _match_option,
    is_pending_task_book,
    merge_explicit_slots,
)
from app.models.schemas import (
    AnswerProposal,
    Option,
    InferredIntent,
    IntentResult,
    IntentSlot,
    StoryboardSlot,
    TaskItem,
)
from app.models.tables import Message, WorkflowStep
from app.pipeline.node_runners import (
    _align_storyboard_slots,
    _checkpoint_direction,
)
from app.pipeline.orchestrator import (
    TaskSpec,
    _compile_task_list,
    compile_graph,
    derive_context_fields,
    ordered_slots,
    slot_step_label,
)


def _kinds(nodes):
    return [n.kind for n in nodes]


# ---------------------------------------------------------------------------
# compile_graph
# ---------------------------------------------------------------------------


class TestCompileGraph:
    def test_auto_full_run_has_no_checkpoint(self):
        nodes = compile_graph(TaskSpec(outputs=[IntentSlot(type="post")], autonomy="auto"))
        assert _kinds(nodes) == [
            "preprocess",
            "persona_bootstrap",
            "understand",
            "plan",
            "post_gen",
        ]
        plan = nodes[3]
        assert plan.inputs == [1, 2]
        assert nodes[4].inputs == [3]

    def test_review_full_run_inserts_direction_checkpoint(self):
        nodes = compile_graph(TaskSpec(outputs=[IntentSlot(type="post")], autonomy="review"))
        assert _kinds(nodes) == [
            "preprocess",
            "persona_bootstrap",
            "understand",
            "checkpoint",
            "plan",
            "post_gen",
        ]
        checkpoint = nodes[3]
        # Persona + understanding ride the checkpoint's inputs so the plan
        # node's old ordering constraint survives transitively.
        assert checkpoint.inputs == [1, 2]
        assert checkpoint.spec["for"] == "direction"
        assert nodes[4].inputs == [3]  # plan hangs off the checkpoint
        assert nodes[5].inputs == [4]  # executors hang off the plan

    def test_targeted_run_never_inserts_checkpoint(self):
        nodes = compile_graph(
            TaskSpec(scope="post", autonomy="review"), target_type="post"
        )
        assert "checkpoint" not in _kinds(nodes)

    def test_task_list_mode_never_inserts_checkpoint(self):
        nodes = _compile_task_list(
            TaskSpec(tasks=[TaskItem(skill="write_post")], autonomy="review")
        )
        assert "checkpoint" not in _kinds(nodes)

    def test_hook_scope_topology(self):
        nodes = compile_graph(TaskSpec(scope="hook"))
        assert _kinds(nodes) == ["script"]
        assert nodes[0].spec["scope"] == "hook"

    def test_render_scope_topology(self):
        nodes = compile_graph(TaskSpec(scope="render"))
        assert _kinds(nodes) == ["render"]

    def test_per_slot_fanout_two_posts(self):
        nodes = compile_graph(
            TaskSpec(
                outputs=[
                    IntentSlot(type="post", language="en"),
                    IntentSlot(type="post", language="de"),
                ]
            )
        )
        posts = [n for n in nodes if n.kind == "post_gen"]
        assert len(posts) == 2
        assert [n.spec["slot_index"] for n in posts] == [0, 1]
        assert [n.spec["slot"]["language"] for n in posts] == ["en", "de"]

    def test_unknown_scope_raises(self):
        with pytest.raises(ValueError):
            compile_graph(TaskSpec(scope="nope"))


class TestOrderedSlots:
    def test_canonical_order_and_clips_dedup(self):
        slots = [
            IntentSlot(type="post"),
            IntentSlot(type="clips"),
            IntentSlot(type="quotes"),
            IntentSlot(type="clips"),  # duplicate clips — dropped
            IntentSlot(type="post", language="de"),
        ]
        ordered = ordered_slots(slots)
        assert [s.type for s in ordered] == ["clips", "post", "post", "quotes"]
        # Same-type slots keep request order.
        assert ordered[1].language is None
        assert ordered[2].language == "de"


class TestSlotStepLabel:
    def test_label_only_when_distinguishing(self):
        assert slot_step_label(IntentSlot(type="post")) is None
        assert slot_step_label(IntentSlot(type="post", language="de")) == "Post · DE"
        assert slot_step_label(IntentSlot(type="clips", focus="pricing")) == (
            "Clips · pricing"
        )


class TestDeriveContextFields:
    def test_skills_to_slots(self):
        fields = derive_context_fields(
            [
                TaskItem(skill="write_post", params={"count": 2}),
                TaskItem(skill="write_quotes"),
                TaskItem(skill="write_post"),  # duplicate type — first wins
                TaskItem(skill="remove_filler"),  # no output mapping — ignored
            ]
        )
        slots = fields["outputs"]
        assert [(s["type"], s["count"]) for s in slots] == [("post", 2), ("quotes", None)]


# ---------------------------------------------------------------------------
# _match_option (deterministic autoResume)
# ---------------------------------------------------------------------------


class TestMatchOption:
    options = [
        Option(id="a", label="Focus: pricing"),
        Option(id="b", label="Full-talk highlights"),
    ]

    def test_letter_hit(self):
        assert _match_option("a", self.options).id == "a"
        assert _match_option(" B ", self.options).id == "b"

    def test_number_hit_is_one_based(self):
        assert _match_option("1", self.options).id == "a"
        assert _match_option("2", self.options).id == "b"

    def test_verbatim_label_hit_normalized(self):
        assert _match_option("focus: pricing", self.options).id == "a"
        assert _match_option("Full-Talk Highlights。", self.options).id == "b"

    def test_non_hit_is_not_a_match(self):
        assert _match_option("pricing 那个", self.options) is None
        assert _match_option("3", self.options) is None
        assert _match_option("", self.options) is None


# ---------------------------------------------------------------------------
# merge_explicit_slots (pin-merge)
# ---------------------------------------------------------------------------


class TestMergeExplicitSlots:
    def test_pinned_slot_replaces_same_key(self):
        pinned = [IntentSlot(type="quotes", count=7, explicit=True)]
        inferred = [IntentSlot(type="quotes", count=3), IntentSlot(type="post")]
        merged = merge_explicit_slots(pinned, inferred)
        quotes = next(s for s in merged if s.type == "quotes")
        assert quotes.count == 7
        assert any(s.type == "post" for s in merged)

    def test_match_key_includes_language(self):
        pinned = [IntentSlot(type="post", language="de", count=2, explicit=True)]
        inferred = [IntentSlot(type="post")]  # different key — no replace
        merged = merge_explicit_slots(pinned, inferred)
        assert len(merged) == 2
        assert any(s.language == "de" and s.count == 2 for s in merged)

    def test_dropped_pin_is_reappended(self):
        pinned = [IntentSlot(type="article", explicit=True)]
        merged = merge_explicit_slots(pinned, [IntentSlot(type="post")])
        assert {s.type for s in merged} == {"post", "article"}

    def test_non_explicit_pins_ignored(self):
        pinned = [IntentSlot(type="quotes", count=9)]  # not explicit
        merged = merge_explicit_slots(pinned, [IntentSlot(type="quotes", count=3)])
        assert merged[0].count == 3


# ---------------------------------------------------------------------------
# _align_storyboard_slots
# ---------------------------------------------------------------------------


class TestAlignStoryboardSlots:
    def test_explicit_fields_are_binding(self):
        sb = [StoryboardSlot(slot="quotes", count=3, focus="llm angle")]
        intent = [IntentSlot(type="quotes", count=8, focus="user angle", tone_override="punchy")]
        [aligned] = _align_storyboard_slots(sb, intent)
        assert aligned.count == 8
        assert aligned.focus == "user angle"
        assert aligned.tone_override == "punchy"

    def test_vacancies_fall_back_to_llm_slot(self):
        sb = [StoryboardSlot(slot="post", focus="llm angle", argument_ids=["a1"])]
        [aligned] = _align_storyboard_slots(sb, [IntentSlot(type="post")])
        assert aligned.focus == "llm angle"
        assert aligned.argument_ids == ["a1"]

    def test_missing_llm_slot_gets_bare_slot(self):
        [aligned] = _align_storyboard_slots([], [IntentSlot(type="post", count=2)])
        assert aligned.slot == "post"
        assert aligned.count == 2

    def test_same_type_multi_slots_keep_order(self):
        sb = [
            StoryboardSlot(slot="post", focus="first"),
            StoryboardSlot(slot="post", focus="second"),
        ]
        intent = [IntentSlot(type="post", language="en"), IntentSlot(type="post", language="de")]
        aligned = _align_storyboard_slots(sb, intent)
        assert [a.focus for a in aligned] == ["first", "second"]


# ---------------------------------------------------------------------------
# _checkpoint_direction (stub db — async, no real session)
# ---------------------------------------------------------------------------


class _StubDb:
    def __init__(self, rows):
        self.rows = rows

    async def get(self, _model, row_id):
        return self.rows.get(row_id)


def _plan_node(checkpoint: WorkflowStep | None) -> WorkflowStep:
    return WorkflowStep(
        id=uuid4(),
        kind="plan",
        inputs=[str(checkpoint.id)] if checkpoint else [],
    )


def _checkpoint(spec: dict) -> WorkflowStep:
    return WorkflowStep(id=uuid4(), kind="checkpoint", spec=spec)


class TestCheckpointDirection:
    @pytest.mark.asyncio
    async def test_option_maps_to_priority_argument(self):
        ckpt = _checkpoint(
            {
                "answer": {"kind": "option", "option_id": "a", "text": "Focus: pricing"},
                "suspend_payload": {
                    "options": [
                        {"id": "a", "label": "Focus: pricing", "argument_id": "a3"},
                        {"id": "b", "label": "Full-talk highlights", "argument_id": None},
                    ]
                },
            }
        )
        plan = _plan_node(ckpt)
        direction = await _checkpoint_direction(_StubDb({ckpt.id: ckpt}), plan)
        assert direction == {"argument_ids": ["a3"], "text": "Focus: pricing"}

    @pytest.mark.asyncio
    async def test_default_option_means_no_direction(self):
        ckpt = _checkpoint(
            {
                "answer": {"kind": "option", "option_id": "b", "text": "expired"},
                "suspend_payload": {
                    "options": [{"id": "b", "label": "Full-talk highlights", "argument_id": None}]
                },
            }
        )
        plan = _plan_node(ckpt)
        assert await _checkpoint_direction(_StubDb({ckpt.id: ckpt}), plan) is None

    @pytest.mark.asyncio
    async def test_freeform_carries_verbatim_text(self):
        ckpt = _checkpoint({"answer": {"kind": "freeform", "text": "pricing, please"}})
        plan = _plan_node(ckpt)
        direction = await _checkpoint_direction(_StubDb({ckpt.id: ckpt}), plan)
        assert direction == {"text": "pricing, please"}

    @pytest.mark.asyncio
    async def test_empty_freeform_and_missing_answer_mean_no_direction(self):
        ckpt = _checkpoint({"answer": {"kind": "freeform", "text": ""}})
        plan = _plan_node(ckpt)
        assert await _checkpoint_direction(_StubDb({ckpt.id: ckpt}), plan) is None
        ckpt2 = _checkpoint({})
        plan2 = _plan_node(ckpt2)
        assert await _checkpoint_direction(_StubDb({ckpt2.id: ckpt2}), plan2) is None

    @pytest.mark.asyncio
    async def test_no_checkpoint_upstream_means_no_direction(self):
        plan = _plan_node(None)
        assert await _checkpoint_direction(_StubDb({}), plan) is None


class TestMiniMaxErrorWrap:
    """The client's HTTP status failures must surface as MiniMaxError — every
    degradation path upstream (intent fallback, chat ask-back) catches that
    type; a raw httpx.HTTPStatusError slips past all of them into a 500."""

    def test_http_status_error_becomes_minimax_error(self):
        import httpx
        import pytest as _pytest

        from app.clients.minimax import MiniMaxError, _raise_for_status

        response = httpx.Response(
            402, text="payment required",
            request=httpx.Request("POST", "http://test"),
        )
        with _pytest.raises(MiniMaxError) as exc_info:
            _raise_for_status(response)
        assert "402" in str(exc_info.value)

    def test_success_response_passes(self):
        import httpx

        from app.clients.minimax import _raise_for_status

        _raise_for_status(
            httpx.Response(200, text="ok", request=httpx.Request("POST", "http://test"))
        )


# ---------------------------------------------------------------------------
# _format_step_progress (G-2 node-level progress lines)
# ---------------------------------------------------------------------------


def _step(kind: str, status: str, summary: str | None = None) -> WorkflowStep:
    return WorkflowStep(
        id=uuid4(),
        kind=kind,
        status=status,
        spec={"summary": summary} if summary else {},
    )


class TestFormatStepProgress:
    def test_kind_status_summary_line(self):
        rows = _format_step_progress(
            [_step("clips_pipeline", "done", "Selected 3 clips · 87s total")]
        )
        assert rows == ["- clips_pipeline: done — Selected 3 clips · 87s total"]

    def test_missing_summary_omits_dash(self):
        assert _format_step_progress([_step("preprocess", "pending")]) == [
            "- preprocess: pending"
        ]

    def test_waiting_checkpoint_reads_as_waiting_for_you(self):
        rows = _format_step_progress([_step("checkpoint", "waiting")])
        assert rows == ["- checkpoint: waiting"]

    def test_cap_keeps_the_tail_with_an_omitted_lead_in(self):
        steps = [_step(f"kind_{i}", "done", f"s{i}") for i in range(14)]
        rows = _format_step_progress(steps)
        assert len(rows) == 13  # 1 omitted lead-in + 12 kept
        assert rows[0] == "- … (2 earlier steps omitted)"
        assert rows[1] == "- kind_2: done — s2"
        assert rows[-1] == "- kind_13: done — s13"

    def test_empty_steps(self):
        assert _format_step_progress([]) == []


# ---------------------------------------------------------------------------
# is_pending_task_book (G-1 startable-confirmation predicate)
# ---------------------------------------------------------------------------


class TestIsPendingTaskBook:
    def test_unanswered_task_book_is_startable(self):
        message = Message(question={"kind": "task_book"}, answer=None)
        assert is_pending_task_book(message) is True

    def test_answered_task_book_is_not_startable(self):
        message = Message(
            question={"kind": "task_book"},
            answer={"kind": "start"},
        )
        assert is_pending_task_book(message) is False

    def test_plain_question_is_not_startable(self):
        message = Message(question={"kind": "question"}, answer=None)
        assert is_pending_task_book(message) is False

    def test_none_and_non_question_are_not_startable(self):
        assert is_pending_task_book(None) is False
        assert is_pending_task_book(Message(question=None, answer=None)) is False


# ---------------------------------------------------------------------------
# AnswerProposal — the union's fourth state (G-4, N-21)
# ---------------------------------------------------------------------------


class TestAnswerProposal:
    def test_union_validates_answer_shape(self):
        result = IntentResult.model_validate(
            {"proposal": {"type": "answer", "text": "Sure — here's what I can do."}}
        )
        assert isinstance(result.proposal, AnswerProposal)
        assert result.proposal.text.startswith("Sure")

    def test_bare_answer_proposal_wraps(self):
        # Models sometimes drop the {"proposal": ...} wrapper (IntentResult
        # tolerates a bare proposal) — the answer state must survive it too.
        result = IntentResult.model_validate({"type": "answer", "text": "hi"})
        assert isinstance(result.proposal, AnswerProposal)

    def test_extra_keys_are_forbidden(self):
        with pytest.raises(ValidationError):
            IntentResult.model_validate(
                {"proposal": {"type": "answer", "text": "hi", "summary": "sneaky"}}
            )


# ---------------------------------------------------------------------------
# InferredIntent action="start" (G-1 third action)
# ---------------------------------------------------------------------------


class TestInferredIntentStartAction:
    def test_start_action_validates(self):
        intent = InferredIntent.model_validate({"action": "start", "answer": None})
        assert intent.action == "start"
        assert intent.answer is None

    def test_unknown_action_rejected(self):
        with pytest.raises(ValidationError):
            InferredIntent.model_validate({"action": "maybe"})
