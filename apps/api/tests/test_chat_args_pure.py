"""Pure tests for the chat + plan paths' tool-args schemas (ADR-077 判词②
tool-loop form) — the wire contract the provider's tool_calls compile
against.

No DB, no LLM, no HTTP (suite discipline). What is gated HERE:

- P0-② 对账 (2026-09-22): ``ProposeTasksArgs.specific_instruction`` exists and
  carries the distilled-EXTRA contract (the chat path no longer forces the
  raw user message down as the instruction — the model submits distilled
  extras, and the propose seat's fallback reads tolerate its absence);
- 打字机律牙① (read tolerance): an explicit ``null`` on the optional string
  fields reads as the empty default, never a schema rejection (a rejected
  iteration never streams — the prose would pop in as one blob);
- 一问拍一体化 (2026-09-27): the ask card's schema contract — every option
  carries its one-line ``description`` (null reads as ""), the
  ``recommended_id`` mark survives only when it names a shipped option
  (``resolve_recommended_id`` — a stale or imagined id drops silently,
  never a repair round), and the plan path's tools all seat
  ``pending_disposition`` (the deflection settlement the zombie-card
  incident was missing);
- null-as-string 方言 (2026-10-09): the plan emission's ``"language":
  "null"`` token scrubs at ``TaskItem``'s boundary — a junk string must
  never reach spec stamps, spec prompts, or a product's language column;
- ``extra="forbid"`` stays the unknown-key alarm.
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    ChatAnswerArgs,
    ChatAskArgs,
    DesignStoryboardArgs,
    DesignVideoArgs,
    Option,
    PlanAnswerArgs,
    PlanAskArgs,
    PresentPlanArgs,
    ProposeTasksArgs,
    RetryUploadArgs,
    StartRunArgs,
    TaskItem,
    resolve_recommended_id,
)

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


class TestTaskItemParamScrub:
    """null-as-string 方言的边界净化 (2026-10-09, live 取证 = 高光短视频 run
    context 全链 "null"/"1" 字符串): the model fills absent optional params
    with the bare token ``"null"``; scrubbed here so it never reaches spec
    stamps / spec prompts / the product's language column."""

    def test_null_tokens_and_empty_strings_drop(self) -> None:
        item = TaskItem.model_validate(
            {
                "tool": "select_clips",
                "params": {
                    "count": 1,
                    "aspect": "9:16",
                    "language": "null",
                    "focus": " NULL ",
                    "mode": "",
                },
            }
        )
        assert item.params == {"count": 1, "aspect": "9:16"}

    def test_real_content_survives(self) -> None:
        """Exact bare-token match only — a focus merely MENTIONING null is
        content, never junk."""
        item = TaskItem.model_validate(
            {"tool": "write_post", "params": {"focus": "null pointer exceptions"}}
        )
        assert item.params["focus"] == "null pointer exceptions"

    def test_params_null_or_empty_reads_as_absent(self) -> None:
        """The ADR-109 §5 seat stays: params ''/null → the {} default."""
        assert TaskItem.model_validate({"tool": "x", "params": None}).params == {}
        assert TaskItem.model_validate({"tool": "x", "params": ""}).params == {}


# ---- 一问拍一体化 (2026-09-27, Claude-Card parity) -----------------------------
#
# The ask card's schema contract: the option's reason line and the ONE
# recommendation mark ride the wire; the pending-question disposition seats
# on every plan-path terminal tool (the zombie-card incident's missing
# gate). SuggestionItem/WrapUpArgs coverage lives in test_trigger_turn_pure.


class TestOptionDescription:
    def test_reason_line_rides(self) -> None:
        option = Option.model_validate(
            {"id": "1", "label": "长文", "description": "最省事，先出一条"}
        )
        assert option.description == "最省事，先出一条"

    def test_null_and_absent_read_as_empty(self) -> None:
        # 读容忍: code-built options (asset_role) and legacy rows carry no
        # reason line; the model writing null means the same.
        assert Option.model_validate({"id": "1", "label": "x"}).description == ""
        assert (
            Option.model_validate({"id": "1", "label": "x", "description": None}).description
            == ""
        )


class TestResolveRecommendedId:
    _OPTIONS = [Option(id="1", label="a"), Option(id="2", label="b")]

    def test_a_shipped_option_id_survives(self) -> None:
        assert resolve_recommended_id("2", self._OPTIONS) == "2"

    def test_stale_or_imagined_ids_drop_silently(self) -> None:
        # Cosmetic, never worth a rejection round — the asset_role
        # code-built options invalidate any LLM-written id the same way.
        assert resolve_recommended_id("3", self._OPTIONS) is None
        assert resolve_recommended_id("asset-uuid", self._OPTIONS) is None

    def test_none_and_empty_options_pass_through_to_none(self) -> None:
        assert resolve_recommended_id(None, self._OPTIONS) is None
        assert resolve_recommended_id("1", []) is None


class TestPlanAskArgsCardFields:
    def test_reason_mark_and_disposition_ride(self) -> None:
        args = PlanAskArgs.model_validate(
            {
                "question": "接下来做什么？",
                "options": [
                    {"id": "1", "label": "长文", "description": "最省事"},
                    {"id": "2", "label": "金句卡"},
                ],
                "recommended_id": "1",
                "pending_disposition": "answer",
            }
        )
        assert args.recommended_id == "1"
        assert args.options[1].description == ""
        assert args.pending_disposition == "answer"

    def test_nulls_read_as_defaults(self) -> None:
        # 打字机律牙①: the model writes null for "no mark / nothing pending"
        # — never a schema rejection burning a non-streaming iteration.
        args = PlanAskArgs.model_validate(
            {
                "question": "q",
                "options": None,
                "recommended_id": None,
                "pending_disposition": None,
                "slot": None,
            }
        )
        assert args.options == []
        assert args.recommended_id is None
        assert args.pending_disposition == "none"
        assert args.slot is None


class TestPendingDispositionSeats:
    """The zombie-card fix: every plan-path terminal tool seats the
    disposition so an engaging free-text reply (incl. the deflection
    'which do you recommend?') settles the docked question."""

    def test_present_plan_seats_disposition(self) -> None:
        args = PresentPlanArgs.model_validate({"pending_disposition": "answer"})
        assert args.pending_disposition == "answer"
        assert PresentPlanArgs.model_validate({}).pending_disposition == "none"
        assert (
            PresentPlanArgs.model_validate({"pending_disposition": None}).pending_disposition
            == "none"
        )

    def test_plan_answer_seats_disposition(self) -> None:
        args = PlanAnswerArgs.model_validate({"pending_disposition": "skip"})
        assert args.pending_disposition == "skip"
        assert PlanAnswerArgs.model_validate({}).pending_disposition == "none"

    def test_an_invented_disposition_rejects(self) -> None:
        with pytest.raises(ValidationError):
            PlanAskArgs.model_validate(
                {"question": "q", "pending_disposition": "defer"}
            )


class TestChatAskArgsCardFields:
    def test_recommended_id_null_reads_as_absent(self) -> None:
        args = ChatAskArgs.model_validate(
            {"question": "q", "recommended_id": None, "options": None}
        )
        assert args.recommended_id is None
        assert args.options == []

    def test_disposition_defaults_to_none(self) -> None:
        assert ChatAskArgs.model_validate({"question": "q"}).pending_disposition == "none"

    def test_null_disposition_reads_as_none(self) -> None:
        # 打字机律牙① on the chat path's seats too: the model's
        # null-means-skip habit must never reject the call (a rejected
        # iteration never streams).
        assert (
            ChatAskArgs.model_validate(
                {"question": "q", "pending_disposition": None}
            ).pending_disposition
            == "none"
        )
        assert (
            ChatAnswerArgs.model_validate(
                {"pending_disposition": None}
            ).pending_disposition
            == "none"
        )


class TestRetryUploadArgs:
    def test_unqualified_recovery_and_null_pin_are_read_tolerant(self) -> None:
        args = RetryUploadArgs.model_validate(
            {"output_id": None, "pending_disposition": None}
        )
        assert args.output_id is None
        assert args.pending_disposition == "none"
        assert RetryUploadArgs.model_validate({}).output_id is None

    def test_definite_output_pin_and_unknown_key_guard(self) -> None:
        output_id = "00000000-0000-0000-0000-000000000001"
        assert str(RetryUploadArgs.model_validate({"output_id": output_id}).output_id) == output_id
        with pytest.raises(ValidationError):
            RetryUploadArgs.model_validate({"run_id": output_id})


class TestStartRunArgsWaiver:
    """start_run's retired waiver param: the film storyboard rides the dock
    echo now (generated before the dock), so no review gate remains to
    waive. The field stays accepted-and-ignored for old clients (the
    autonomy precedent): default off, explicit values accepted, null
    read-tolerant (打字机律牙①: a null never rejects the call), unknown keys
    rejected."""

    def test_default_is_no_waiver(self) -> None:
        assert StartRunArgs.model_validate({}).skip_storyboard_review is False

    def test_explicit_waiver(self) -> None:
        assert (
            StartRunArgs.model_validate({"skip_storyboard_review": True}).skip_storyboard_review
            is True
        )

    def test_null_reads_as_absent(self) -> None:
        assert (
            StartRunArgs.model_validate({"skip_storyboard_review": None}).skip_storyboard_review
            is False
        )

    def test_unknown_keys_reject(self) -> None:
        with pytest.raises(ValidationError):
            StartRunArgs.model_validate({"skip": True})


class TestDesignStoryboardArgs:
    """design_storyboard params (ADR-129 — 分镜不是开工, 分镜也不是方案
    dock): the film family's review beat rides BOTH paths as a NON-terminal
    call (the system drafts inside execute, publishes the markdown as its
    own message, and hands the design facts back for the model's reply).
    The params mirror launch_film's design fields so the approval dock's
    fingerprint can match (null = default on every key); material_urls lets
    the design beat absorb a conversation-carried URL before drafting (the
    proposal seats' same absorb law). ``review_hold`` carries the
    review-only scope (「只看分镜，先别制作」) — True holds, False
    releases, absent leaves the stored hold untouched."""

    def test_defaults_are_all_absent(self) -> None:
        args = DesignStoryboardArgs.model_validate({})
        assert args.focus is None
        assert args.language is None
        assert args.voiceover is None
        assert args.subtitles is None
        assert args.music_mood is None
        assert args.aspect is None
        assert args.specific_instruction is None
        assert args.material_urls is None
        assert args.review_hold is None
        assert args.pending_disposition == "none"

    def test_nulls_read_as_absent(self) -> None:
        # 打字机律牙①: a null never rejects the call (a rejected iteration
        # never streams — 整段瞬移永禁).
        args = DesignStoryboardArgs.model_validate(
            {"focus": None, "voiceover": None, "subtitles": None, "material_urls": None,
             "specific_instruction": None, "review_hold": None,
             "pending_disposition": None}
        )
        assert args.focus is None and args.voiceover is None
        assert args.subtitles is None
        assert args.material_urls is None
        assert args.review_hold is None
        assert args.pending_disposition == "none"

    def test_text_shape_null_is_a_real_clear_not_an_omission(self) -> None:
        keys = ("target_seconds", "scene_count", "group_chars")
        omitted = DesignStoryboardArgs.model_validate({})
        assert all(key not in omitted.model_fields_set for key in keys)

        cleared = DesignStoryboardArgs.model_validate({key: None for key in keys})
        assert all(key in cleared.model_fields_set for key in keys)
        assert cleared.target_seconds is None
        assert cleared.scene_count is None
        assert cleared.group_chars is None

        overridden = DesignStoryboardArgs.model_validate(
            {"target_seconds": 20.0, "scene_count": 8, "group_chars": [2, 4]}
        )
        assert overridden.target_seconds == 20.0
        assert overridden.scene_count == 8
        assert overridden.group_chars == [2, 4]
        assert all(key in overridden.model_fields_set for key in keys)

    def test_patch_rejects_an_explicit_null_compose_field(self) -> None:
        base = {
            "base_ref": "read-reference",
            "edits": [{"op": "update_scene", "scene_id": "s2", "dark": True}],
        }
        DesignStoryboardArgs.model_validate(base)
        with pytest.raises(ValidationError, match="edits never mix with target_seconds"):
            DesignStoryboardArgs.model_validate({**base, "target_seconds": None})
        with pytest.raises(ValidationError, match="edits never mix with subtitles"):
            DesignStoryboardArgs.model_validate({**base, "subtitles": False})

    def test_values_ride_verbatim(self) -> None:
        args = DesignStoryboardArgs.model_validate(
            {
                "focus": "the social features",
                "language": "en",
                "voiceover": True,
                "subtitles": False,
                "aspect": "9:16",
                "specific_instruction": "重点讲社交功能",
                "review_hold": True,
                "material_urls": ["https://example.com"],
            }
        )
        assert args.focus == "the social features"
        assert args.subtitles is False
        assert args.aspect == "9:16"
        assert args.review_hold is True
        assert args.material_urls == ["https://example.com"]

    def test_unknown_keys_reject(self) -> None:
        with pytest.raises(ValidationError):
            DesignStoryboardArgs.model_validate({"scenes": 5})


class TestDesignVideoCapturedMaterial:
    def test_auto_design_can_reuse_project_captures_without_material_fields(self):
        args = DesignVideoArgs.model_validate({"focus": "key features"})
        assert args.material_urls is None
        assert args.material_asset_ids is None

    def test_motion_graphics_still_requires_text(self):
        with pytest.raises(ValidationError, match="native motion graphics needs exact on-screen text"):
            DesignVideoArgs.model_validate({"mode": "motion_graphics"})


class TestProductionIntentBirthFact:
    """ADR-139: every dock-capable args model carries the birth fact — the
    model's judgment whether the user's message asks for the work to be
    MADE now. Null-tolerant (打字机律牙①): an explicit null or an absent key
    reads as None = unasserted = the safe-side hold; true/false keep."""

    _MINIMAL = {
        "PresentPlanArgs": {},
        "ProposeTasksArgs": {},
        "EditGraphArgs": {},
        "ProposePlansArgs": {"plans": []},
        "RevisePlanArgs": {
            "plan_id": "12345678-1234-1234-1234-123456789012",
            "outputs": [],
        },
        "ReviseSelectsArgs": {"selects": []},
    }

    def _models(self):
        from app.chat.exploration_tools import (
            ProposePlansArgs,
            RevisePlanArgs,
            ReviseSelectsArgs,
        )
        from app.models.schemas import (
            EditGraphArgs,
            PresentPlanArgs,
            ProposeTasksArgs,
        )

        return {
            m.__name__: m
            for m in (
                PresentPlanArgs,
                ProposeTasksArgs,
                EditGraphArgs,
                ProposePlansArgs,
                RevisePlanArgs,
                ReviseSelectsArgs,
            )
        }

    def test_all_six_dock_models_carry_the_field(self) -> None:
        models = self._models()
        assert set(models) == set(self._MINIMAL)
        for name, model in models.items():
            assert "production_intent" in model.model_fields, name

    def test_absent_and_explicit_null_read_as_unasserted(self) -> None:
        for name, model in self._models().items():
            absent = model.model_validate({**self._MINIMAL[name]})
            assert absent.production_intent is None, name
            nulled = model.model_validate(
                {**self._MINIMAL[name], "production_intent": None}
            )
            assert nulled.production_intent is None, name

    def test_true_and_false_keep(self) -> None:
        for name, model in self._models().items():
            for value in (True, False):
                args = model.model_validate(
                    {**self._MINIMAL[name], "production_intent": value}
                )
                assert args.production_intent is value, name
