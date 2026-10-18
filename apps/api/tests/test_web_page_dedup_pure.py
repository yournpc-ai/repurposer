"""Web-page dedup pure tests — the ``web_page_capture_known`` law
(app/pipeline/assets.py).

No DB, no network, no browser. What's gated HERE is the dedup predicate's
truth table — the decision of whether a same-URL sibling genuinely KNOWS
the page:

- in-flight rows (PENDING/PROCESSING) are known — the capture is running;
- FAILED rows are not — re-sending the link re-arms them;
- a COMPLETED row WITHOUT captured page views lost its browser half
  (``screenshot_failed``): the text half alone is not the film's raw
  material and the design preflight rejects it on INSUFFICIENT_VIEWS —
  so it counts as UNKNOWN and re-sending re-arms it through the same
  reset seat (the 2026-10-18 snappify dead-end: a hollow capture used to
  bounce every re-send).
"""

from app.models.schemas import AssetStatus
from app.pipeline.assets import web_page_capture_known


def test_in_flight_rows_are_known() -> None:
    # The capture is running — a re-send must never double-birth nor
    # interrupt it.
    for status in (AssetStatus.PENDING, AssetStatus.PROCESSING):
        assert web_page_capture_known(status, None) is True
        assert web_page_capture_known(status, {}) is True


def test_failed_rows_are_never_known() -> None:
    # Even with stale shots in meta, a FAILED row re-arms (the reset seat
    # owns the status/counter/error write-set).
    assert web_page_capture_known(AssetStatus.FAILED, None) is False
    assert (
        web_page_capture_known(AssetStatus.FAILED, {"shots": [{"key": "k"}]})
        is False
    )


def test_completed_with_views_is_known() -> None:
    assert (
        web_page_capture_known(
            AssetStatus.COMPLETED, {"shots": [{"key": "k", "y": 0}]}
        )
        is True
    )


def test_completed_without_views_is_a_hollow_capture() -> None:
    # The browser half died (screenshot_failed) — text alone never counts.
    assert web_page_capture_known(AssetStatus.COMPLETED, None) is False
    assert web_page_capture_known(AssetStatus.COMPLETED, {}) is False
    assert web_page_capture_known(AssetStatus.COMPLETED, {"shots": []}) is False
