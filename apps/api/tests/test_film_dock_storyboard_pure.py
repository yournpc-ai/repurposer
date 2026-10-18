"""Pure tests for the dock-stage film storyboard handoff (ADR-129 — the
DESIGN beat drafts and publishes the board; every dock seat reads the
current version only, and the run consumes exactly the storyboard the user
last saw).

No DB, no LLM, no HTTP (suite discipline). What's gated HERE:

- the fingerprint law (``storyboard_fingerprint``): None without a
  launch_film task; deterministic; invalidated by the film params or the
  instruction (the plan's BIRTH narrative — storyboard feedback never
  enters the hash, it rides ``prepare_dock_storyboard``'s
  ``fresh_instruction`` as a one-time redraft trigger); untouched by
  sibling tasks; CANONICAL — the design beat's sparse params and the
  approval dock's spelled-out defaults hash equal;
- the PendingPlan handoff fields (``film_storyboard`` /
  ``film_storyboard_fingerprint`` + the ADR-129 versioned state): roundtrip
  intact, absent on legacy rows (读容忍);
- ``film_design_state`` (the design beat's versioning): a fresh draft bumps
  the version and rotates the draft token (旧 Start 失效), a reuse
  re-presentation keeps both; the review hold sets / releases / survives;
- ``film_dock_state`` (the dock seat's carry-over): stored fields verbatim,
  the review hold CLEARS (a docking proposal IS the production request);
- ``film_start_draft_match`` (the Start seat's integrity predicate): token
  equality never short-circuits params / version / content digest /
  execution digest — panel edits and tampered stamps fail closed;
- the in-flight draft marker (并发护栏): liveness budget, carry-over, the
  publish beat consuming it, a reuse re-minting the begin-cleared token;
- ``_film_revision_base_from_state`` (the post-Start revision base):
  provenance candidates validate, the version line continues;
- ``rewrite_film_task_params`` (the dock's canonical rewrite);
- the dock payload's ``storyboard_echo`` stamp + ``film_draft_token``.
"""

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from app.models.schemas import (
    FilmStoryboard,
    PendingPlan,
    QuestionPayload,
    TaskItem,
)
from app.tools.film.storyboard import (
    DockStoryboard,
    _DOCK_DRAFT_BUDGET_S,
    _film_revision_base_from_state,
    canonical_film_params,
    film_carry_state,
    film_design_state,
    film_dock_state,
    film_draft_inflight_live,
    film_execution_snapshot_digest,
    film_start_draft_match,
    resolve_film_dock_state,
    rewrite_film_task_params,
    storyboard_content_digest,
    storyboard_fingerprint,
)


def _film_task(**params) -> TaskItem:
    return TaskItem(tool="launch_film", params=params)


class TestStoryboardFingerprint:
    def test_no_film_task_no_fingerprint(self) -> None:
        assert storyboard_fingerprint([], None) is None
        assert (
            storyboard_fingerprint([TaskItem(tool="add_post", params={})], "go")
            is None
        )

    def test_deterministic(self) -> None:
        a = storyboard_fingerprint([_film_task(focus="pricing")], "make a film")
        b = storyboard_fingerprint([_film_task(focus="pricing")], "make a film")
        assert a is not None and a == b

    def test_params_invalidate(self) -> None:
        base = storyboard_fingerprint([_film_task(focus="pricing")], "make a film")
        assert storyboard_fingerprint([_film_task(focus="features")], "make a film") != base
        assert storyboard_fingerprint([_film_task()], "make a film") != base
        assert storyboard_fingerprint(
            [_film_task(focus="pricing", aspect="9:16")], "make a film"
        ) != base

    def test_instruction_invalidate(self) -> None:
        base = storyboard_fingerprint([_film_task()], "make a film")
        assert storyboard_fingerprint([_film_task()], "make it shorter") != base
        assert storyboard_fingerprint([_film_task()], None) != base

    def test_sibling_tasks_do_not_invalidate(self) -> None:
        with_post = storyboard_fingerprint(
            [_film_task(focus="pricing"), TaskItem(tool="add_post", params={})],
            "make a film",
        )
        without_post = storyboard_fingerprint([_film_task(focus="pricing")], "make a film")
        assert with_post == without_post

    def test_dict_tasks_read_alike(self) -> None:
        # The fingerprint reads plain dicts too (the dock seats hand
        # TaskItems; the law must not depend on the container type).
        via_model = storyboard_fingerprint([_film_task(focus="pricing")], "x")
        via_dict = storyboard_fingerprint(
            [{"tool": "launch_film", "params": {"focus": "pricing"}}], "x"
        )
        assert via_model == via_dict

    def test_canonical_pinning_design_beat_equals_dock(self) -> None:
        # 设计拍 → dock 拍同键 (ADR-129): the design beat's sparse synthetic
        # task and the approval dock's real task hash EQUAL when they mean
        # the same film — null params drop out, the voiceover default (null
        # = narrated) pins to its explicit twin, a null aspect pins "16:9".
        sparse = storyboard_fingerprint([_film_task(focus="pricing")], "x")
        spelled = storyboard_fingerprint(
            [_film_task(focus="pricing", voiceover=True, aspect="16:9")], "x"
        )
        assert sparse is not None and sparse == spelled
        # A REAL move still invalidates (the pin is not a flattening).
        assert storyboard_fingerprint(
            [_film_task(focus="pricing", voiceover=False)], "x"
        ) != sparse
        assert storyboard_fingerprint(
            [_film_task(focus="pricing", aspect="9:16")], "x"
        ) != sparse

    def test_canonical_film_params_shape(self) -> None:
        assert canonical_film_params({"focus": "x", "voiceover": None}) == {
            "focus": "x",
            "aspect": "16:9",
            "voiceover": True,
        }
        assert canonical_film_params({"voiceover": False}) == {
            "aspect": "16:9",
            "voiceover": False,
        }


class TestPendingPlanStoryboardHandoff:
    def test_roundtrip(self) -> None:
        plan = PendingPlan(
            prompt="make a film",
            film_storyboard={"name": "X", "scenes": []},
            film_storyboard_fingerprint="abc123",
        )
        restored = PendingPlan.model_validate(plan.model_dump(mode="json"))
        assert restored.film_storyboard == {"name": "X", "scenes": []}
        assert restored.film_storyboard_fingerprint == "abc123"

    def test_legacy_rows_read_absent(self) -> None:
        # 读容忍: rows docked before the handoff carry no keys.
        restored = PendingPlan.model_validate({"prompt": "make a film"})
        assert restored.film_storyboard is None
        assert restored.film_storyboard_fingerprint is None
        # The ADR-129 versioned state reads absent too (and the hold
        # defaults off — a legacy dock never blocks on it).
        assert restored.film_storyboard_version is None
        assert restored.film_storyboard_params is None
        assert restored.film_storyboard_content_digest is None
        assert restored.film_storyboard_execution is None
        assert restored.film_design_authorized_by is None
        assert restored.film_presented_message_id is None
        assert restored.film_review_hold is False
        assert restored.film_draft_token is None

    def test_versioned_state_roundtrip(self) -> None:
        plan = PendingPlan(
            prompt="make a film",
            film_storyboard={"name": "X", "scenes": []},
            film_storyboard_fingerprint="abc123",
            film_storyboard_version=2,
            film_storyboard_params={"focus": "x", "aspect": "16:9", "voiceover": True},
            film_storyboard_content_digest="def456",
            film_storyboard_execution={"pages": [], "music": None, "digest": "aaa"},
            film_design_authorized_by="msg-1",
            film_presented_message_id="msg-2",
            film_review_hold=True,
            film_draft_token="tok",
        )
        restored = PendingPlan.model_validate(plan.model_dump(mode="json"))
        assert restored.film_storyboard_version == 2
        assert restored.film_storyboard_params == {
            "focus": "x",
            "aspect": "16:9",
            "voiceover": True,
        }
        assert restored.film_storyboard_content_digest == "def456"
        assert restored.film_storyboard_execution == {
            "pages": [],
            "music": None,
            "digest": "aaa",
        }
        assert restored.film_design_authorized_by == "msg-1"
        assert restored.film_presented_message_id == "msg-2"
        assert restored.film_review_hold is True
        assert restored.film_draft_token == "tok"


_BOARD = {
    "name": "X",
    "scenes": [
        {
            "type": "hero",
            "seconds": 3.0,
            "word": "Anchor",
            "sub": "A steady open.",
        }
    ],
}
_VALID_BOARD = {
    "name": "X",
    "scenes": [
        {
            "type": "hero",
            "seconds": 3.0,
            "word": "Ship faster",
            "sub": "A calm launch.",
        }
    ],
}
_EXECUTION = {"pages": [], "music": None, "timing": {"fps": 30}, "digest": "ex"}


def _execution_snapshot() -> dict:
    snapshot = {"pages": [], "music": None, "timing": {"fps": 30}}
    return {**snapshot, "digest": film_execution_snapshot_digest(snapshot)}


def _versioned_pending(**overrides) -> PendingPlan:
    params = {"focus": "pricing", "aspect": "16:9", "voiceover": True}
    state = {
        "prompt": "make a film",
        "film_storyboard": dict(_VALID_BOARD),
        "film_storyboard_fingerprint": storyboard_fingerprint(
            [_film_task(**params)], "make a film"
        ),
        "film_storyboard_version": 1,
        "film_storyboard_params": params,
        "film_storyboard_content_digest": storyboard_content_digest(_VALID_BOARD),
        "film_storyboard_execution": _execution_snapshot(),
        "film_draft_token": "tok-1",
    }
    state.update(overrides)
    return PendingPlan(**state)


def _dock_storyboard(*, reused: bool = False) -> DockStoryboard:
    return DockStoryboard(
        presentation="# board",
        storyboard=dict(_BOARD),
        fingerprint="fp-1",
        reused=reused,
        execution=None if reused else dict(_EXECUTION),
    )


class TestFilmDesignState:
    def test_first_draft_versions_and_tokens(self) -> None:
        state = film_design_state(
            None,
            film=_dock_storyboard(),
            design_params={"focus": "x"},
            review_hold=None,
            authorized_by="msg-1",
        )
        assert state["film_storyboard_version"] == 1
        assert state["film_draft_token"]  # a fresh token — 旧 Start 失效
        assert state["film_storyboard_params"] == canonical_film_params({"focus": "x"})
        assert state["film_storyboard_content_digest"] == storyboard_content_digest(_BOARD)
        assert state["film_storyboard_execution"] == _EXECUTION
        assert state["film_design_authorized_by"] == "msg-1"
        assert state["film_presented_message_id"] is None  # the publish beat stamps it
        assert state["film_review_hold"] is False

    def test_fresh_redraft_bumps_version_and_rotates_token(self) -> None:
        stored = PendingPlan(
            prompt="p",
            film_storyboard=dict(_BOARD),
            film_storyboard_fingerprint="fp-1",
            film_storyboard_version=1,
            film_draft_token="old-tok",
            film_presented_message_id="msg-old",
        )
        state = film_design_state(
            stored,
            film=_dock_storyboard(),
            design_params={"focus": "y"},
            review_hold=None,
            authorized_by="msg-2",
        )
        assert state["film_storyboard_version"] == 2
        assert state["film_draft_token"] != "old-tok"
        assert state["film_design_authorized_by"] == "msg-2"
        assert state["film_presented_message_id"] is None  # re-stamped by the new publish

    def test_reuse_keeps_version_token_and_hold(self) -> None:
        stored = PendingPlan(
            prompt="p",
            film_storyboard=dict(_BOARD),
            film_storyboard_fingerprint="fp-1",
            film_storyboard_version=3,
            film_storyboard_params={"focus": "x", "aspect": "16:9", "voiceover": True},
            film_storyboard_execution=dict(_EXECUTION),
            film_draft_token="tok-3",
            film_design_authorized_by="msg-1",
            film_presented_message_id="msg-prev",
            film_review_hold=True,
        )
        state = film_design_state(
            stored,
            film=_dock_storyboard(reused=True),
            design_params={"focus": "x"},
            review_hold=None,
            authorized_by="msg-2",
        )
        assert state["film_storyboard_version"] == 3
        assert state["film_draft_token"] == "tok-3"
        assert state["film_storyboard_params"] == stored.film_storyboard_params
        assert state["film_storyboard_execution"] == _EXECUTION
        assert state["film_design_authorized_by"] == "msg-1"  # the original grant survives
        assert state["film_presented_message_id"] == "msg-prev"
        assert state["film_review_hold"] is True  # None = the stored hold survives
        # The digest re-stamps on both paths (same input → same digest).
        assert state["film_storyboard_content_digest"] == storyboard_content_digest(_BOARD)

    def test_review_hold_sets_and_releases(self) -> None:
        held = film_design_state(
            None,
            film=_dock_storyboard(),
            design_params={},
            review_hold=True,
            authorized_by=None,
        )
        assert held["film_review_hold"] is True
        stored = PendingPlan(prompt="p", film_storyboard=dict(_BOARD), film_review_hold=True)
        released = film_design_state(
            stored,
            film=_dock_storyboard(reused=True),
            design_params={},
            review_hold=False,
            authorized_by=None,
        )
        assert released["film_review_hold"] is False


class TestFilmDockState:
    def test_carry_over_verbatim_and_hold_clears(self) -> None:
        stored = PendingPlan(
            prompt="p",
            film_storyboard=dict(_BOARD),
            film_storyboard_fingerprint="fp-1",
            film_storyboard_version=2,
            film_storyboard_params={"focus": "x", "aspect": "16:9", "voiceover": True},
            film_storyboard_content_digest="dg",
            film_storyboard_execution=dict(_EXECUTION),
            film_design_authorized_by="msg-1",
            film_presented_message_id="msg-2",
            film_review_hold=True,
            film_draft_token="tok",
        )
        state = film_dock_state(stored)
        assert state["film_storyboard"] == _BOARD
        assert state["film_storyboard_version"] == 2
        assert state["film_draft_token"] == "tok"
        assert state["film_presented_message_id"] == "msg-2"
        # A docking proposal IS the explicit production request — the hold's
        # one release seat.
        assert state["film_review_hold"] is False

    def test_no_board_writes_empty_state(self) -> None:
        state = film_dock_state(None)
        assert state["film_storyboard"] is None
        assert state["film_storyboard_version"] is None
        assert state["film_review_hold"] is False
        assert state["film_draft_token"] is None
        stored = PendingPlan(prompt="p")  # a non-film dock
        assert film_dock_state(stored) == state

    def test_carry_state_preserves_review_hold(self) -> None:
        stored = _versioned_pending(film_review_hold=True)
        assert film_carry_state(stored)["film_review_hold"] is True
        assert film_dock_state(stored)["film_review_hold"] is False


class TestResolveFilmDockState:
    def test_model_reworded_focus_restores_saved_canonical_params(self) -> None:
        stored = _versioned_pending()
        tasks = [_film_task(focus="the pricing story, reworded")]
        resolved = resolve_film_dock_state(stored, tasks, "make a film")
        assert not isinstance(resolved, str)
        assert resolved.film_chain is True
        assert tasks[0].params["focus"] == "pricing"
        assert resolved.state["film_storyboard_version"] == 1
        assert resolved.state["film_draft_token"] == "tok-1"
        assert resolved.state["film_review_hold"] is False

    def test_digest_or_version_drift_fails_closed(self) -> None:
        stale_digest = _versioned_pending(
            film_storyboard_content_digest="tampered"
        )
        assert isinstance(
            resolve_film_dock_state(
                stale_digest, [_film_task(focus="reworded")], "make a film"
            ),
            str,
        )
        no_version = _versioned_pending(film_storyboard_version=None)
        assert isinstance(
            resolve_film_dock_state(no_version, [_film_task()], "make a film"),
            str,
        )

    def test_execution_drift_fails_closed(self) -> None:
        execution = _execution_snapshot()
        execution["pages"] = [{"asset_id": "moved"}]
        stored = _versioned_pending(film_storyboard_execution=execution)
        assert isinstance(
            resolve_film_dock_state(stored, [_film_task()], "make a film"),
            str,
        )

    def test_non_film_chain_clears_stale_state(self) -> None:
        stored = _versioned_pending()
        tasks = [TaskItem(tool="write_post", params={})]
        resolved = resolve_film_dock_state(stored, tasks, "make a film")
        assert not isinstance(resolved, str)
        assert resolved.film_chain is False
        assert resolved.state["film_storyboard"] is None
        assert resolved.state["film_draft_token"] is None


class TestPlanTurnCurrentPending:
    def test_same_turn_design_state_is_visible_to_the_next_dock_seat(self) -> None:
        from app.chat.plan_turn import PlanTurn

        project = cast(Any, SimpleNamespace(pending_brief=None))
        turn = PlanTurn(
            cast(Any, None),
            uuid4(),
            cast(Any, SimpleNamespace(id=uuid4())),
            project,
            cast(Any, SimpleNamespace(persona_id=None)),
        )
        assert turn.stored is None
        project.pending_brief = _versioned_pending().model_dump(mode="json")
        current = turn._current_pending()
        assert current is turn.stored
        assert current is not None
        assert current.film_storyboard_version == 1
        assert current.film_draft_token == "tok-1"


class TestFilmStartDraftMatch:
    """The Start seat's integrity predicate (ADR-129 fail-closed): token
    equality never short-circuits params / version / digests — a panel edit
    or a tampered stamp fails closed for an explicit re-dock."""

    _TASKS = [_film_task(focus="pricing", aspect="16:9", voiceover=True)]

    def test_consistent_state_passes(self) -> None:
        stored = _versioned_pending()
        assert film_start_draft_match(stored, self._TASKS, "make a film", "tok-1", 1)

    def test_canonical_equivalent_spelling_passes(self) -> None:
        # The sparse design spelling and the spelled-out dock spelling hash
        # to the same canonical params — no false drift.
        stored = _versioned_pending()
        assert film_start_draft_match(
            stored, [_film_task(focus="pricing")], "make a film", "tok-1", 1
        )

    def test_panel_edited_params_fail_closed(self) -> None:
        stored = _versioned_pending()
        for edited in (
            [_film_task(focus="pricing", aspect="9:16", voiceover=True)],
            [_film_task(focus="pricing", aspect="16:9", voiceover=False)],
            [_film_task(focus="features", aspect="16:9", voiceover=True)],
            [_film_task(focus="pricing", aspect="16:9", voiceover=True, language="en")],
        ):
            assert not film_start_draft_match(
                stored, edited, "make a film", "tok-1", 1
            )

    def test_token_match_never_short_circuits_content_digest(self) -> None:
        stored = _versioned_pending(film_storyboard_content_digest="tampered")
        assert not film_start_draft_match(
            stored, self._TASKS, "make a film", "tok-1", 1
        )

    def test_tampered_board_fails_against_its_digest(self) -> None:
        board = dict(_VALID_BOARD, name="Swapped")
        stored = _versioned_pending(film_storyboard=board)
        assert not film_start_draft_match(
            stored, self._TASKS, "make a film", "tok-1", 1
        )

    def test_tampered_execution_snapshot_fails(self) -> None:
        bad = _execution_snapshot()
        bad["timing"] = {"fps": 24}  # digest no longer self-proves
        stored = _versioned_pending(film_storyboard_execution=bad)
        assert not film_start_draft_match(
            stored, self._TASKS, "make a film", "tok-1", 1
        )

    def test_version_mismatch_fails(self) -> None:
        stored = _versioned_pending()
        assert not film_start_draft_match(
            stored, self._TASKS, "make a film", "tok-1", 2
        )

    def test_newer_draft_token_fails(self) -> None:
        stored = _versioned_pending()
        assert not film_start_draft_match(
            stored, self._TASKS, "make a film", "tok-OLD", 1
        )

    def test_fingerprint_fallback_for_tokenless_rows(self) -> None:
        # A row whose token cleared (a begin superseded the old
        # confirmation) still matches on canonical params + birth prompt.
        stored = _versioned_pending(film_draft_token=None)
        assert film_start_draft_match(
            stored, self._TASKS, "make a film", None, 1
        )
        assert not film_start_draft_match(
            stored, self._TASKS, "a different ask", None, 1
        )

    def test_paramless_legacy_row_fails_closed(self) -> None:
        stored = PendingPlan(
            prompt="make a film",
            film_storyboard=dict(_VALID_BOARD),
            film_storyboard_fingerprint="fp",
        )
        assert not film_start_draft_match(
            stored, self._TASKS, "make a film", None, None
        )

    def test_digest_normalizes_sparse_dict_input(self) -> None:
        # ONE canonical digest input form: a sparse hand-built dict and its
        # validated model (defaults materialized) digest identically — the
        # stamp seat, the dock/start checks and the worker check never
        # disagree over pydantic defaults.
        assert storyboard_content_digest(
            dict(_VALID_BOARD)
        ) == storyboard_content_digest(FilmStoryboard.model_validate(_VALID_BOARD))


class TestFilmDraftInflight:
    """The in-flight draft marker (并发护栏): liveness budget, carry-over on
    non-dock rewrites, consumed by the publish beat."""

    def test_liveness_predicate(self) -> None:
        assert not film_draft_inflight_live(None)
        assert not film_draft_inflight_live({})
        assert not film_draft_inflight_live({"started_at": 1000.0})
        # An unreadable clock fails closed (reads LIVE).
        assert film_draft_inflight_live({"draft_id": "d"})
        assert film_draft_inflight_live(
            {"draft_id": "d", "started_at": 1000.0}, now=1000.0 + 10
        )
        # Older than the design budget → stale (the offset DERIVES from the
        # budget constant — the 30min floor is the law, never a hardcoded
        # shadow of it).
        assert not film_draft_inflight_live(
            {"draft_id": "d", "started_at": 1000.0},
            now=1000.0 + _DOCK_DRAFT_BUDGET_S + 1,
        )

    def test_carry_state_preserves_the_marker(self) -> None:
        marker = {"draft_id": "d", "started_at": 1.0}
        stored = _versioned_pending(film_draft_inflight=marker)
        assert film_carry_state(stored)["film_draft_inflight"] == marker

    def test_carry_state_preserves_marker_without_board(self) -> None:
        marker = {"draft_id": "d", "started_at": 1.0}
        stored = SimpleNamespace(film_storyboard=None, film_draft_inflight=marker)
        assert film_carry_state(stored)["film_draft_inflight"] == marker

    def test_design_state_consumes_the_marker(self) -> None:
        marker = {"draft_id": "d", "started_at": 1.0}
        stored = _versioned_pending(film_draft_inflight=marker)
        state = film_design_state(
            stored,
            film=_dock_storyboard(reused=True),
            design_params={},
            review_hold=None,
            authorized_by=None,
        )
        assert state["film_draft_inflight"] is None

    def test_reuse_remints_a_cleared_token(self) -> None:
        # The begin beat cleared the stored token (旧确认作废); a reuse
        # re-presentation finding none re-mints so the follow-up dock's
        # draft-token conjunct can pass.
        stored = _versioned_pending(film_draft_token=None)
        state = film_design_state(
            stored,
            film=_dock_storyboard(reused=True),
            design_params={},
            review_hold=None,
            authorized_by=None,
        )
        assert state["film_draft_token"]


class TestFilmRevisionBase:
    """The recovered revision base (ADR-129 修订基准): a read-only
    provenance snapshot a post-Start revision re-enters from — version line
    continues, unusable candidates skip."""
    def test_valid_candidate_recovers_and_continues_the_version_line(self) -> None:
        base = _film_revision_base_from_state(
            board=dict(_VALID_BOARD),
            fingerprint="fp-1",
            version=3,
            params={"focus": "pricing", "aspect": "16:9", "voiceover": True},
            content_digest=storyboard_content_digest(_VALID_BOARD),
            execution=_execution_snapshot(),
        )
        assert base is not None
        assert base.film_storyboard_version == 3
        assert base.film_draft_token is None
        assert base.film_draft_inflight is None
        assert base.film_review_hold is False
        # The revision creates the NEXT version over the recovered base.
        state = film_design_state(
            base,
            film=_dock_storyboard(reused=False),
            design_params={"focus": "pricing"},
            review_hold=None,
            authorized_by="msg-1",
        )
        assert state["film_storyboard_version"] == 4
        assert state["film_draft_token"]  # fresh draft re-mints

    def test_digest_mismatch_skips_the_candidate(self) -> None:
        assert (
            _film_revision_base_from_state(
                board=dict(_VALID_BOARD),
                fingerprint="fp-1",
                version=3,
                params={},
                content_digest="tampered",
                execution=None,
            )
            is None
        )

    def test_unusable_board_skips(self) -> None:
        for bad_board in (None, "nope", {"scenes": "not-a-list"}):
            assert (
                _film_revision_base_from_state(
                    board=bad_board,
                    fingerprint=None,
                    version=None,
                    params=None,
                    content_digest=None,
                    execution=None,
                )
                is None
            )

    def test_digest_less_legacy_candidate_recovers(self) -> None:
        # A pre-digest run's stamp carries no content digest — 读容忍.
        base = _film_revision_base_from_state(
            board=dict(_VALID_BOARD),
            fingerprint=None,
            version=None,
            params=None,
            content_digest=None,
            execution=None,
        )
        assert base is not None
        assert base.film_storyboard_version is None


class TestRewriteFilmTaskParams:
    def test_canonical_rewrite_pins_defaults(self) -> None:
        tasks = [_film_task(focus="pricing"), TaskItem(tool="add_post", params={})]
        rewrite_film_task_params(
            tasks, {"focus": "pricing", "aspect": "16:9", "voiceover": True}
        )
        assert tasks[0].params == {
            "focus": "pricing",
            "aspect": "16:9",
            "voiceover": True,
        }
        assert tasks[1].params == {}  # sibling tasks untouched

    def test_dict_tasks_rewrite_alike(self) -> None:
        tasks = [{"tool": "launch_film", "params": {"focus": "x"}}]
        rewrite_film_task_params(tasks, {"focus": "x", "aspect": "16:9", "voiceover": True})
        assert tasks[0]["params"]["voiceover"] is True

    def test_no_version_params_is_noop(self) -> None:
        tasks = [_film_task(focus="pricing")]
        rewrite_film_task_params(tasks, None)
        assert tasks[0].params == {"focus": "pricing"}


class TestStoryboardEchoStamp:
    def test_defaults_false(self) -> None:
        payload = QuestionPayload(kind="task_book")
        assert payload.storyboard_echo is False

    def test_stamped_and_roundtrips(self) -> None:
        payload = QuestionPayload(kind="task_book", storyboard_echo=True)
        restored = QuestionPayload.model_validate(payload.model_dump(mode="json"))
        assert restored.storyboard_echo is True


class TestFilmDraftTokenStamp:
    """ADR-129: the dock stamps the presented draft's token into the payload
    — the Start gate compares it against the ACTIVE draft's token (a redesign
    between dock and Start voids the docked confirmation)."""

    def test_defaults_none(self) -> None:
        assert QuestionPayload(kind="task_book").film_draft_token is None

    def test_stamped_and_roundtrips(self) -> None:
        payload = QuestionPayload(kind="task_book", film_draft_token="tok-1")
        restored = QuestionPayload.model_validate(payload.model_dump(mode="json"))
        assert restored.film_draft_token == "tok-1"


# ---- the presented-message association (2026-10-18 裁决) --------------------
#
# 最终 LLM 分镜消息成功持久化后, 才关联 film_presented_message_id — the
# stamp is version-guarded and never invented.

from app.tools.film.storyboard import presentation_stamp_update


class TestPresentationStampUpdate:
    def _pending(self, **overrides) -> dict:
        state = {
            "prompt": "make a film",
            "film_storyboard": dict(_VALID_BOARD),
            "film_storyboard_version": 1,
            "film_draft_token": "tok-1",
        }
        state.update(overrides)
        return PendingPlan(**state).model_dump(mode="json")

    def test_stamps_when_the_version_matches(self) -> None:
        updated = presentation_stamp_update(
            self._pending(), version=1, message_id="msg-1"
        )
        assert updated is not None
        assert updated["film_presented_message_id"] == "msg-1"
        # Everything else rides verbatim (the version state is untouched).
        assert updated["film_storyboard_version"] == 1
        assert updated["film_draft_token"] == "tok-1"

    def test_re_presentation_restamps_the_latest_message(self) -> None:
        once = presentation_stamp_update(
            self._pending(), version=1, message_id="msg-1"
        )
        assert once is not None
        twice = presentation_stamp_update(once, version=1, message_id="msg-2")
        assert twice is not None
        assert twice["film_presented_message_id"] == "msg-2"

    def test_a_moved_version_never_stamps(self) -> None:
        # A newer draft landed since this presentation's design beat —
        # associating the old presentation with v2 would mislabel what the
        # user saw.
        assert (
            presentation_stamp_update(
                self._pending(film_storyboard_version=2),
                version=1,
                message_id="msg-1",
            )
            is None
        )

    def test_no_stored_board_never_stamps(self) -> None:
        assert (
            presentation_stamp_update(
                {"prompt": "p"}, version=1, message_id="msg-1"
            )
            is None
        )
        assert presentation_stamp_update(None, version=1, message_id="m") is None
        assert presentation_stamp_update("junk", version=1, message_id="m") is None
