"""Pure tests for the MG film D3 简式计价 contract (ADR-119 D3, BILLING §3/§4).

No database, no LLM, no HTTP — the ledger is the in-memory contextvar
(``bind_workflow_step``), the config cache is primed/evicted by monkeypatch.

The contract locked here:

- **estimate 形状**: launch_film quotes orchestration tokens (worst case =
  one storyboard pass per candidate) + the film_seconds flat item
  (``ESTIMATE_FILM_SECONDS`` typical — never the 90s validator ceiling).
- **一条价目线**: the estimate fold and the metering ledger price
  film_seconds through the same ``price_units`` line, whose rate is the
  ``film.usd_per_second`` config knob (peek = the sync form of the funnel).
  Moving the knob moves quote and charge together (估价 ≡ 计量).
- **实扣座位**: ``record_media_usage`` accrues the actual allocated seconds
  into ``fixed_cost`` (USD) + ``cost.units`` — capture then converts
  through the one ratio seam; a rejected storyboard never records (失败
  不扣费 by position — the record call sits behind the validator gate).
- **peek 纪律**: unknown keys raise like the async funnel; a cold cache
  reads the registry default (a missing row's get_config answer); a primed
  override is served.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.metering import bind_workflow_step, record_media_usage
from app.pipeline.graph import node_for
from app.platform import configs
from app.platform.billing import cost_usd, credits_at_ratio, estimate_usd_range
from app.platform.configs import CONFIG_REGISTRY, peek_config
from app.providers.llm.minimax import price_units
from app.tools.film.storyboard import (
    ESTIMATE_FILM_SECONDS,
    FILM_FPS,
    MAX_REWRITES,
    allocate_frames,
)

DEFAULT_RATE = CONFIG_REGISTRY["film.usd_per_second"].default


def _launch_film():
    node = node_for("launch_film")
    assert node is not None
    return node


@pytest.fixture(autouse=True)
def _clean_config_cache():
    """Every test starts and ends with a cold cache (the default-reading
    posture) — a primed override must never leak across tests."""
    configs._cache.pop("film.usd_per_second", None)
    yield
    configs._cache.pop("film.usd_per_second", None)


# ---- estimate 形状 ------------------------------------------------------------


def test_estimate_quotes_tokens_worst_case_plus_typical_seconds() -> None:
    est = _launch_film().estimate({})
    n = 1 + MAX_REWRITES
    assert est is not None
    assert est["prompt_tokens"] == [1500 * n, 8000 * n]
    assert est["completion_tokens"] == [400 * n, 2000 * n]
    # The flat seconds item is the TYPICAL film, not the validator ceiling
    # (90s) — the sticker must not promise 3× every real charge. E2 配音:
    # narration speech rides the same estimate (voiceover is the plan
    # default) at ~14 chars/s over the same window.
    assert est["units"] == {
        "film_seconds": ESTIMATE_FILM_SECONDS,
        "tts_chars": ESTIMATE_FILM_SECONDS * 14.0,
    }
    assert ESTIMATE_FILM_SECONDS < 90.0


def test_estimate_fold_prices_film_seconds_on_both_sides() -> None:
    """The fold's USD range carries the film money on low AND high (exact
    units join both sides); the rate is the config knob's default."""
    est = _launch_film().estimate({})
    assert est is not None
    usd_low, usd_high = estimate_usd_range(est)
    film_usd = ESTIMATE_FILM_SECONDS * DEFAULT_RATE
    assert usd_low > film_usd  # tokens low + film
    assert usd_high > usd_low
    # The units share is exact — the low/high spread is tokens only.
    assert usd_high - usd_low == pytest.approx(
        (8000 * 3 - 1500 * 3) / 1_000_000 * 0.30
        + (2000 * 3 - 400 * 3) / 1_000_000 * 1.20
    )


# ---- 一条价目线（knob 动，报价与实扣同动） --------------------------------------


def test_film_seconds_price_reads_the_config_knob() -> None:
    assert price_units({"film_seconds": 30.0}) == pytest.approx(30.0 * DEFAULT_RATE)
    # Unknown keys stay silently zero — a typo'd unit never fabricates money.
    assert price_units({"film_secondz": 30.0}) == 0.0


def test_knob_override_moves_quote_and_meter_together() -> None:
    configs._cache["film.usd_per_second"] = 0.01
    quote_usd = price_units({"film_seconds": ESTIMATE_FILM_SECONDS})
    with bind_workflow_step(uuid4()) as bound:
        asyncio.run(record_media_usage({"film_seconds": 26.0}))
    metered_usd = bound.accrued["fixed_cost"]
    assert quote_usd == pytest.approx(ESTIMATE_FILM_SECONDS * 0.01)
    assert metered_usd == pytest.approx(26.0 * 0.01)


# ---- 实扣座位（actual seconds → fixed_cost → credits） ---------------------------


def test_record_media_usage_accrues_seconds_money_and_units() -> None:
    with bind_workflow_step(uuid4()) as bound:
        asyncio.run(record_media_usage({"film_seconds": 26.0}))
    assert bound.accrued["fixed_cost"] == pytest.approx(26.0 * DEFAULT_RATE)
    assert bound.accrued["units"]["film_seconds"] == pytest.approx(26.0)


def test_capture_math_carries_film_fixed_cost_through_the_one_ratio() -> None:
    """cost_usd (the capture base) folds fixed_cost; credits convert at the
    single ratio seam — film money rides the same path as token money."""
    with bind_workflow_step(uuid4()) as bound:
        asyncio.run(record_media_usage({"film_seconds": 26.0}))
    cost = {
        "prompt_tokens": 9000,
        "completion_tokens": 1500,
        "fixed_cost": bound.accrued["fixed_cost"],
        "units": bound.accrued["units"],
    }
    usd = cost_usd(cost)
    expected_usd = 9000 / 1_000_000 * 0.30 + 1500 / 1_000_000 * 1.20 + 26.0 * DEFAULT_RATE
    assert usd == pytest.approx(expected_usd)
    assert credits_at_ratio(usd, 1000) == round(expected_usd * 1000)


def test_allocated_seconds_are_the_metered_truth() -> None:
    """The actual charge is the ALLOCATED duration (allocator minimums can
    clamp a scene up), never the LLM's seconds intent — estimate ≡ meter
    reads the allocator's output."""
    from app.models.schemas import FilmStoryboard

    storyboard = FilmStoryboard.model_validate(
        {
            "name": None,
            "theme": None,
            "scenes": [
                {"type": "end", "seconds": 2.5, "name": "Acme", "tagline": "Ship faster"},
            ],
        }
    )
    frames = allocate_frames(storyboard)
    # 2.5s intent at 30fps = 75 frames, exactly the end-card floor.
    assert frames == [75]
    assert frames[0] / FILM_FPS == pytest.approx(2.5)


# ---- peek 纪律 ------------------------------------------------------------------


def test_peek_unknown_key_raises_like_the_funnel() -> None:
    with pytest.raises(KeyError, match="Unknown config key"):
        peek_config("film.no_such_key")


def test_peek_cold_cache_reads_registry_default() -> None:
    assert peek_config("film.usd_per_second") == DEFAULT_RATE


def test_peek_primed_cache_serves_the_override() -> None:
    configs._cache["film.usd_per_second"] = 0.007
    assert peek_config("film.usd_per_second") == 0.007
