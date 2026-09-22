"""Pure tests for the chat path's tool-args schemas (ADR-077 判词② tool-loop
form) — the wire contract the provider's tool_calls compile against.

No DB, no LLM, no HTTP (suite discipline). What is gated HERE:

- P0-② 对账 (2026-09-22): ``ProposeTasksArgs.specific_instruction`` exists and
  carries the distilled-EXTRA contract (the chat path no longer forces the
  raw user message down as the instruction — the model submits distilled
  extras, and the propose seat's fallback reads tolerate its absence);
- 打字机律牙① (read tolerance): an explicit ``null`` on the optional string
  fields reads as the empty default, never a schema rejection (a rejected
  iteration never streams — the prose would pop in as one blob);
- ``extra="forbid"`` stays the unknown-key alarm.
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import ProposeTasksArgs

_TASK = {"tool": "write_post", "params": {"language": "en"}}


class TestProposeTasksArgsSpecificInstruction:
    def test_field_exists_and_defaults_to_none(self) -> None:
        args = ProposeTasksArgs.model_validate({"tasks": [_TASK]})
        assert args.specific_instruction is None

    def test_distilled_value_rides(self) -> None:
        args = ProposeTasksArgs.model_validate(
            {
                "tasks": [_TASK],
                "specific_instruction": "focus on the Q&A section",
            }
        )
        assert args.specific_instruction == "focus on the Q&A section"

    def test_explicit_null_reads_as_absent(self) -> None:
        """读容忍兜底: the model writes null when it means 'nothing extra' —
        that must never be a schema rejection (the rejected-iteration typewriter
        hole); it reads as the empty default."""
        args = ProposeTasksArgs.model_validate(
            {"tasks": [_TASK], "specific_instruction": None, "name": None}
        )
        assert args.specific_instruction is None
        assert args.name == ""

    def test_unknown_keys_still_rejected(self) -> None:
        """extra='forbid' is the drift alarm — the distilled contract never
        licenses invented params."""
        with pytest.raises(ValidationError):
            ProposeTasksArgs.model_validate(
                {"tasks": [_TASK], "instruction": "the old field name"}
            )
