"""Pure tests for the material-readiness lane (ADR-102): the retired
commitment marker's schema absence and the failure observation's
facts-only law.

No DB, no LLM, no HTTP (suite discipline). What is gated HERE:

- the ``material_pending`` marker is GONE from both answer schemas — no
  key on the dump, and a stray payload key hits ``extra="forbid"`` (the
  commitment form is structurally unemittable, not prompt-discouraged) —
  ADR-101 §2's deletion is PERMANENT (ADR-102 §7 inherits it);
- ``_failed_text`` carries WORLD FACTS ONLY (一法一座 — the failure's
  speech law lives in the system prompt's material-readiness line;
  an observation that restates it reads as a speech draft and gets
  paraphrased into the reply).

The terminal wait itself (stamp → poll → landed/failure) needs a real
worker and DB — it belongs to the e2e scenarios, never here.
"""

import pytest
from pydantic import ValidationError

from app.chat.perception.executes import _failed_text
from app.models.schemas import ChatAnswerArgs, PlanAnswerArgs


class TestCommitmentMarkerIsGone:
    """The material-pending lane is structurally unemittable — the schema
    carries no seat for it (mirror of the suggestions-form lock in
    test_suggestion_provenance_pure.py)."""

    @pytest.mark.parametrize("model", [PlanAnswerArgs, ChatAnswerArgs])
    def test_dump_carries_no_material_pending_key(self, model) -> None:
        assert "material_pending" not in model.model_validate({}).model_dump()

    @pytest.mark.parametrize("model", [PlanAnswerArgs, ChatAnswerArgs])
    def test_stray_material_pending_key_rejects(self, model) -> None:
        with pytest.raises(ValidationError):
            model.model_validate({"material_pending": True})


class TestFailureObservationFactsOnly:
    def test_carries_the_count_and_the_fact(self) -> None:
        text = _failed_text(3)
        assert "FAILED processing" in text
        assert "3 asset(s)" in text

    def test_never_carries_the_speech_law(self) -> None:
        """The re-upload offer and the 'say so plainly' coaching live in the
        system prompt's seat — restated here they read as a draft."""
        text = _failed_text(2)
        assert "re-upload" not in text
        assert "Say so" not in text
        assert "plainly" not in text
