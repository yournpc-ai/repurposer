"""Tests for strip_null_params — the ONE params-adjudication funnel.

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP). The
convention under test: "null = take the default" — explicit JSON nulls drop
before schema validation (2026-08-19), and so does the provider dialect's
STRING "null" (2026-09-24, production incident 641cb9fc: M3 serialized
absent params as "null" strings, they slipped the ``is not None`` guard,
and present_plan died at the birthplace after the speech had already
promised the plan — 7-minute repair loop).
"""

import pytest

from app.models.schemas import TaskItem
from app.tools import ToolRejected, strip_null_params, validate_task_list


def test_json_null_drops() -> None:
    assert strip_null_params({"count": None, "aspect": "16:9"}) == {"aspect": "16:9"}


def test_string_null_drops() -> None:
    """The provider dialect's absent-marker — same intent as JSON null."""
    assert strip_null_params({"count": "null", "aspect": " null ", "focus": "NULL"}) == {}


def test_real_values_survive() -> None:
    """Falsy-but-real values are never swept with the nulls."""
    assert strip_null_params({"count": 0, "bilingual": False, "focus": "", "aspect": "9:16"}) == {
        "count": 0,
        "bilingual": False,
        "focus": "",
        "aspect": "9:16",
    }


def test_none_and_empty_input() -> None:
    assert strip_null_params(None) == {}
    assert strip_null_params({}) == {}


def test_incident_payload_adjudicates() -> None:
    """641cb9fc's exact rejection: select_clips with "null"-string params
    passes the door (the defaults take over); a GENUINELY bad value still
    bites."""
    entries = validate_task_list(
        [TaskItem(tool="select_clips", params={"count": "null", "aspect": "null"})]
    )
    assert [e.name for e in entries] == ["select_clips"]
    with pytest.raises(ToolRejected, match="select_clips"):
        validate_task_list([TaskItem(tool="select_clips", params={"count": "lots"})])
