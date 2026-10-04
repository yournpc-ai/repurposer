"""Pure tests for the material-wait lane (ADR-101): the bounded in-turn
wait's verdict core, the retired commitment marker's schema absence, and
the consumed mark's ride on assistant rows (复读禁止律).

No DB, no LLM, no HTTP (suite discipline) — the session below is an
in-memory stub. What is gated HERE:

- ``material_wait_verdict``'s truth table: landed rows never reach it (the
  caller checks first); an empty pending set settles unreadable at once
  (H8 — never wait out the cap for a row that will never come); the
  deadline alone decides timeout vs keep-waiting;
- the ``material_pending`` marker is GONE from both answer schemas — no
  key on the dump, and a stray payload key hits ``extra="forbid"`` (the
  commitment form is structurally unemittable, not prompt-discouraged);
- ``_create_message``: the consumed mark rides the assistant row's OWN
  intent (zero extra rows, zero rendering surface), never a user row's,
  and never without a ref;
- ``_unready_text``'s shape law: the timeout variant names the actual
  wait, the non-wait variant never fabricates one, and the failed-set
  branch stays a distinct fact (I-PFA-07).
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.chat.perception.executes import _unready_text, material_wait_verdict
from app.chat.service import _create_message
from app.models.schemas import ChatAnswerArgs, PlanAnswerArgs


class TestMaterialWaitVerdict:
    def test_no_pending_settles_unreadable_immediately(self) -> None:
        """H8: processing ended with no row (failed / non-digestible set) —
        report the current facts, never wait out the cap."""
        assert (
            material_wait_verdict(pending_count=0, deadline_reached=False)
            == "settled_unreadable"
        )
        assert (
            material_wait_verdict(pending_count=0, deadline_reached=True)
            == "settled_unreadable"
        )

    def test_pending_before_deadline_keeps_waiting(self) -> None:
        assert (
            material_wait_verdict(pending_count=2, deadline_reached=False)
            == "keep_waiting"
        )

    def test_pending_at_deadline_times_out(self) -> None:
        assert (
            material_wait_verdict(pending_count=1, deadline_reached=True)
            == "timeout"
        )


class TestCommitmentMarkerIsGone:
    """The ADR-101 lock: the material-pending lane is structurally
    unemittable — the schema carries no seat for it (mirror of the
    suggestions-form lock in test_suggestion_provenance_pure.py)."""

    @pytest.mark.parametrize("model", [PlanAnswerArgs, ChatAnswerArgs])
    def test_dump_carries_no_material_pending_key(self, model) -> None:
        assert "material_pending" not in model.model_validate({}).model_dump()

    @pytest.mark.parametrize("model", [PlanAnswerArgs, ChatAnswerArgs])
    def test_stray_material_pending_key_rejects(self, model) -> None:
        with pytest.raises(ValidationError):
            model.model_validate({"material_pending": True})


class _StubSession:
    """The _create_message seam's minimum: add/flush/refresh, no DB."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj) -> None:
        pass


class TestConsumedMarkRidesTheAssistantRow:
    @pytest.mark.asyncio
    async def test_assistant_row_carries_the_mark(self) -> None:
        session = _StubSession()
        message = await _create_message(
            session, uuid4(), "assistant", "看过了", consumed_understanding_ref="digest-abc"
        )
        assert message.intent["consumed_understanding"] == "digest-abc"
        # The policy stamp still rides alongside (one intent dump).
        assert message.intent["interaction_policy_version"]

    @pytest.mark.asyncio
    async def test_no_ref_no_key(self) -> None:
        session = _StubSession()
        message = await _create_message(session, uuid4(), "assistant", "普通答复")
        assert "consumed_understanding" not in message.intent

    @pytest.mark.asyncio
    async def test_user_row_never_carries_the_mark(self) -> None:
        session = _StubSession()
        message = await _create_message(
            session, uuid4(), "user", "你好", consumed_understanding_ref="digest-abc"
        )
        assert "consumed_understanding" not in (message.intent or {})


class TestUnreadyTextShapes:
    def test_timeout_variant_names_the_actual_wait(self) -> None:
        text = _unready_text(pending_count=2, failed_count=0, waited_secs=120)
        assert "120s" in text
        assert "2 asset(s)" in text

    def test_non_wait_variant_never_fabricates_a_wait(self) -> None:
        text = _unready_text(pending_count=1, failed_count=0, waited_secs=None)
        assert "wait" not in text.split("—")[0]  # the headline carries no duration

    def test_failed_set_is_a_distinct_fact(self) -> None:
        text = _unready_text(pending_count=0, failed_count=3, waited_secs=None)
        assert "FAILED" in text
        assert "3 asset(s)" in text
