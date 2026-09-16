"""Poison-pill termination pure tests (R1 B4a — 超限 retry 必有终态).

No DB, no LLM, no HTTP. Two layers:

1. ``_attempt_cap_decision`` — the claim/reap boundary matrix: attempt == cap
   is still claimable (total executions = cap + 1, the NodeBase.retries
   magnitude), attempt > cap is the FAILED terminal.
2. The manual-reprocess reset seats — ``reset_asset_processing`` /
   ``reset_output_render`` move status + error + counter as ONE write-set, so
   a capped-out row gets a genuinely fresh budget (假重开 impossible: a
   status-only flip would terminally fail again on the next tick).
"""

from uuid import uuid4

from app.models.schemas import AssetStatus, RenderStatus
from app.models.tables import Asset, Output
from app.pipeline.jobs import (
    _attempt_cap_decision,
    reset_asset_processing,
    reset_output_render,
)

CAP = 3  # the configured default (settings.asset_max_attempts / render_*)


# ---- the cap boundary matrix -----------------------------------------------


def test_attempt_at_or_below_cap_is_claimable():
    for attempt in (0, 1, 2, CAP):
        assert _attempt_cap_decision(attempt, CAP) == "claim", attempt


def test_attempt_over_cap_is_terminal():
    for attempt in (CAP + 1, CAP + 2, 99):
        assert _attempt_cap_decision(attempt, CAP) == "terminal", attempt


# ---- the reset seats (计数清零 + 状态复位一体) -------------------------------


def test_asset_reprocess_is_a_full_reset():
    asset = Asset()
    asset.processing_status = AssetStatus.FAILED
    asset.processing_error = "processing_gave_up line"
    asset.attempt = CAP + 1

    reset_asset_processing(asset)

    assert asset.processing_status == AssetStatus.PENDING
    assert asset.processing_error is None
    assert asset.attempt == 0  # fresh budget — not an instant re-terminal


def test_render_reprocess_is_a_full_reset():
    output = Output()
    output.render_status = RenderStatus.FAILED
    output.render_error = "render_gave_up line"
    output.render_claim_token = uuid4()
    output.render_attempt = CAP + 1

    reset_output_render(output)

    assert output.render_status == RenderStatus.PENDING
    assert output.render_error is None
    assert output.render_claim_token is None  # ADR-079 fencing re-mints at claim
    assert output.render_attempt == 0
