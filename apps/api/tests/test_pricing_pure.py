"""Tests for the provider+model-split price table (providers/llm/minimax —
PRICING / price_units / price_tokens, ADR-077 判词④).

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP). The
table is the ONLY place MiniMax pricing knowledge lives (N-34); these tests
lock the model-keyed shape so a flat-key regression (two SKUs colliding in
one dict) or a silent zero-price default can't sneak back.
"""

import pytest

from app.config import settings
from app.providers.llm.minimax import PRICING, price_tokens, price_units


def test_units_price_against_their_own_sku_lines() -> None:
    """Each unit kind reads the line of the SKU that meters it."""
    assert price_units({}) == 0.0
    assert price_units({"tts_chars": 1_000_000}) == pytest.approx(100.0)
    assert price_units({"voice_clones": 2}) == pytest.approx(3.0)
    assert price_units({"images": 1000}) == pytest.approx(3.5)
    # The free music SKU prices at zero but the line EXISTS.
    assert price_units({"music_pieces": 5}) == 0.0


def test_tokens_default_to_the_configured_chat_model() -> None:
    """The default is settings.minimax_model — and the configured model must
    always HAVE a line (a missing line is a deployment-config error)."""
    assert settings.minimax_model in PRICING
    expected = 1_000_000 / 1_000_000 * 0.30 + 1_000_000 / 1_000_000 * 1.20
    assert price_tokens(1_000_000, 1_000_000) == pytest.approx(expected)
    assert price_tokens(1_000_000, 1_000_000, model="minimax-m3") == pytest.approx(expected)


def test_unknown_model_raises_never_zero_prices() -> None:
    """Fabricated pricing is worse than a loud failure."""
    with pytest.raises(ValueError, match="no PRICING line"):
        price_tokens(100, 100, model="no-such-model")


def test_table_is_model_keyed() -> None:
    """Every line is a per-model/SKU dict of price keys — no flat keys at
    the top level (provider+model 分家)."""
    for key, line in PRICING.items():
        assert isinstance(key, str)
        assert isinstance(line, dict)
        assert all(isinstance(v, int | float) for v in line.values())
