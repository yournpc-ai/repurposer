"""Layer 0 pure contracts: SKU pricing, conversation metering ledger, and Stripe payment adjudication."""

from __future__ import annotations
import pytest

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
    assert price_tokens(1_000_000, 1_000_000) == price_tokens(1_000_000, 1_000_000, model=settings.minimax_model)
    assert price_tokens(1_000_000, 1_000_000, model="MiniMax-M3.1-Flash") == pytest.approx(0.75)
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


@pytest.mark.parametrize("cached", [False, True])
def test_config_peek_reads_default_or_override_without_database(monkeypatch, cached):
    """Quote/meter configuration must share a deterministic sync read."""
    from app.platform import configs

    key = "credits.per_cost_usd"
    if cached:
        monkeypatch.setitem(configs._cache, key, 1234)
    else:
        monkeypatch.delitem(configs._cache, key, raising=False)
    expected = 1234 if cached else configs.CONFIG_REGISTRY[key].default
    assert configs.peek_config(key) == expected


def test_config_peek_rejects_unregistered_keys():
    from app.platform.configs import peek_config

    with pytest.raises(KeyError, match="Unknown config key"):
        peek_config("no_such_config_key")


# --- Conversation usage metering ---

import uuid


import pytest


from app.config import settings


from app.metering import (
    bind_conversation_turn,
    collect_execution_cost,
    fold_conversation_usage,
    record_usage,
)


from app.providers.llm.minimax import price_tokens


class _DbStub:
    """The fold's only session surface is ``add`` — capture it."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, row) -> None:
        self.added.append(row)


def _usage(prompt: int, completion: int, **extra) -> dict:
    return {"prompt_tokens": prompt, "completion_tokens": completion, **extra}


@pytest.mark.asyncio
async def test_record_usage_accumulates_onto_the_bound_conversation_ledger() -> None:
    with bind_conversation_turn() as bound:
        await record_usage(_usage(100, 40))
        await record_usage(_usage(60, 10, prompt_cache_hit_tokens=80))
    assert bound.accrued == {
        "prompt_tokens": 160,
        "completion_tokens": 50,
        "cached_tokens": 80,
        "provider": None,
        "model": None,
        "cost_usd": None,
    }


@pytest.mark.asyncio
async def test_record_usage_without_binding_is_a_silent_noop() -> None:
    # No bind at all: nothing raised, nothing accumulated anywhere.
    await record_usage(_usage(100, 40))
    await record_usage(None)


@pytest.mark.asyncio
async def test_the_two_ledgers_are_independent() -> None:
    # The workflow ledger and the conversation ledger are independent
    # contextvars — each fold seat (execute_step vs the turn tail) reads
    # only its own, so a call lands on whichever ledgers happen to be bound
    # (structurally they never coexist: worker vs request path).
    with collect_execution_cost() as step:
        with bind_conversation_turn() as convo:
            await record_usage(_usage(10, 5))
    assert step.accrued["prompt_tokens"] == 10
    assert convo.accrued["prompt_tokens"] == 10


@pytest.mark.asyncio
async def test_fold_aggregates_the_turn_into_one_priced_row() -> None:
    db = _DbStub()
    user_id, project_id = uuid.uuid4(), uuid.uuid4()
    with bind_conversation_turn() as bound:
        await record_usage(_usage(100, 40, prompt_cache_hit_tokens=70))
        await record_usage(_usage(60, 10))
        await fold_conversation_usage(
            db, user_id=user_id, project_id=project_id, accrued=bound.accrued
        )
    assert len(db.added) == 1
    row = db.added[0]
    assert row.user_id == user_id and row.project_id == project_id
    assert row.prompt_tokens == 160 and row.completion_tokens == 50
    assert row.cached_tokens == 70
    assert row.model == settings.minimax_model
    assert row.cost_usd == pytest.approx(price_tokens(160, 50), abs=1e-9)


@pytest.mark.asyncio
async def test_empty_turn_writes_no_row() -> None:
    db = _DbStub()
    await fold_conversation_usage(
        db, user_id=uuid.uuid4(), project_id=None, accrued=None
    )
    with bind_conversation_turn() as bound:  # bound but never metered
        pass
    await fold_conversation_usage(
        db, user_id=uuid.uuid4(), project_id=None, accrued=bound.accrued
    )
    assert db.added == []


@pytest.mark.asyncio
async def test_pricing_failure_never_breaks_the_fold() -> None:
    db = _DbStub()
    import app.providers.llm.minimax as minimax

    real = minimax.price_tokens
    minimax.price_tokens = None  # type: ignore[assignment]
    try:
        with bind_conversation_turn() as bound:
            await record_usage(_usage(100, 40))
            await fold_conversation_usage(
                db, user_id=uuid.uuid4(), project_id=None, accrued=bound.accrued
            )
    finally:
        minimax.price_tokens = real  # type: ignore[assignment]
    assert len(db.added) == 1
    row = db.added[0]
    assert row.prompt_tokens == 100 and row.completion_tokens == 40
    assert row.cost_usd == 0.0  # degraded, but the token counts stay truthful


@pytest.mark.asyncio
async def test_cached_tokens_null_when_the_provider_says_nothing() -> None:
    db = _DbStub()
    with bind_conversation_turn() as bound:
        await record_usage(_usage(10, 5))
        await fold_conversation_usage(
            db, user_id=uuid.uuid4(), project_id=None, accrued=bound.accrued
        )
    assert db.added[0].cached_tokens is None


@pytest.mark.asyncio
async def test_cached_tokens_tolerates_the_vendor_key_shapes() -> None:
    with bind_conversation_turn() as bound:
        await record_usage(_usage(10, 5, cached_tokens=3))
        await record_usage(
            _usage(10, 5, prompt_tokens_details={"cached_tokens": 7})
        )
    assert bound.accrued["cached_tokens"] == 10


# --- Payments catalog & signed-session adjudication ---

from datetime import UTC, datetime


from types import SimpleNamespace


from uuid import uuid4


import pytest


from pydantic import ValidationError


from app.config import settings


from app.platform.payment_routes import CreateCheckoutSessionRequest


from app.platform.payment_webhooks import _rejected_key, should_alert


from app.platform.payments import (
    CUSTOM_TOPUP_POLICY,
    CreditPackage,
    PaymentAmountInvalid,
    PaymentConfigurationError,
    _checkout_line_items,
    _checkout_return_url,
    _configured_livemode,
    _custom_package,
    list_credit_packages,
    session_mismatch,
)


@pytest.mark.parametrize(
    ("key", "expected"),
    [("sk_test_company", False), ("rk_test_company", False), ("sk_live_company", True)],
)
def test_secret_key_selects_explicit_environment(monkeypatch, key, expected) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", key)
    assert _configured_livemode() is expected


def test_missing_secret_key_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    with pytest.raises(PaymentConfigurationError):
        _configured_livemode()


def test_presets_use_server_side_amounts_and_credits() -> None:
    assert [vars(package) for package in list_credit_packages()] == [
        {"key": "starter", "amount_minor": 1000, "currency": "eur", "credits": 10000},
        {"key": "topup_20", "amount_minor": 2000, "currency": "eur", "credits": 20000},
        {"key": "topup_50", "amount_minor": 5000, "currency": "eur", "credits": 50000},
    ]


def test_custom_amount_uses_server_conversion_and_order_snapshot() -> None:
    package = _custom_package(123)
    assert package.key == "custom"
    assert package.amount_minor == 123
    assert package.currency == CUSTOM_TOPUP_POLICY.currency
    assert package.credits == 1230


@pytest.mark.parametrize(
    "amount_minor",
    [
        CUSTOM_TOPUP_POLICY.min_amount_minor - 1,
        CUSTOM_TOPUP_POLICY.max_amount_minor + 1,
    ],
)
def test_custom_amount_outside_server_bounds_is_rejected(amount_minor: int) -> None:
    with pytest.raises(PaymentAmountInvalid):
        _custom_package(amount_minor)


def test_custom_checkout_uses_server_computed_inline_price() -> None:
    assert _checkout_line_items(_custom_package(123)) == [
        {
            "price_data": {
                "currency": "eur",
                "unit_amount": 123,
                "product_data": {"name": "1230 credits"},
            },
            "quantity": 1,
        }
    ]


def test_preset_checkout_uses_server_inline_price() -> None:
    assert _checkout_line_items(_preset_package()) == [
        {
            "price_data": {
                "currency": "eur",
                "unit_amount": 1000,
                "product_data": {"name": "10000 credits"},
            },
            "quantity": 1,
        }
    ]


def test_checkout_request_requires_exactly_one_amount_source() -> None:
    assert CreateCheckoutSessionRequest(package_key="starter").amount_minor is None
    assert CreateCheckoutSessionRequest(amount_minor=123).package_key is None
    with pytest.raises(ValidationError):
        CreateCheckoutSessionRequest()
    with pytest.raises(ValidationError):
        CreateCheckoutSessionRequest(package_key="starter", amount_minor=123)


def _preset_package() -> CreditPackage:
    return CreditPackage(
        key="starter",
        amount_minor=1000,
        currency="eur",
        credits=10000,
    )


def _order_and_session():
    order_id = uuid4()
    user_id = uuid4()
    order = SimpleNamespace(
        id=order_id,
        user_id=user_id,
        provider="stripe",
        livemode=False,
        package_key="starter",
        provider_checkout_session_id="cs_test_123",
        amount_minor=1000,
        currency="eur",
    )
    session = {
        "id": "cs_test_123",
        "object": "checkout.session",
        "client_reference_id": str(user_id),
        "amount_total": 1000,
        "currency": "eur",
        "metadata": {"order_id": str(order_id), "package_key": "starter"},
    }
    return order, session


def test_signed_session_matches_exact_order_snapshot() -> None:
    order, session = _order_and_session()
    assert session_mismatch(
        order, session, event_livemode=False, configured_livemode=False
    ) is None


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda o, s: s.update(amount_total=999), "amount_mismatch"),
        (lambda o, s: s.update(currency="usd"), "currency_mismatch"),
        (lambda o, s: s.update(id="cs_other"), "checkout_session_mismatch"),
        (lambda o, s: s.update(client_reference_id=str(uuid4())), "user_mismatch"),
        (lambda o, s: s["metadata"].update(order_id=str(uuid4())), "order_metadata_mismatch"),
        (lambda o, s: s["metadata"].update(package_key="other"), "package_mismatch"),
        (lambda o, s: s.update(object="payment_intent"), "provider_mismatch"),
        (lambda o, s: setattr(o, "livemode", True), "livemode_mismatch"),
    ],
)
def test_signed_session_rejects_every_order_boundary_drift(mutate, expected) -> None:
    order, session = _order_and_session()
    mutate(order, session)
    assert session_mismatch(
        order, session, event_livemode=False, configured_livemode=False
    ) == expected


def test_event_environment_must_match_server_key() -> None:
    order, session = _order_and_session()
    assert (
        session_mismatch(order, session, event_livemode=True, configured_livemode=False)
        == "livemode_mismatch"
    )
    assert (
        session_mismatch(order, session, event_livemode=None, configured_livemode=False)
        == "livemode_mismatch"
    )


def test_rejected_deliveries_share_an_hourly_audit_key() -> None:
    first = datetime(2026, 11, 6, 16, 1, tzinfo=UTC)
    same_hour = datetime(2026, 11, 6, 16, 59, tzinfo=UTC)
    next_hour = datetime(2026, 11, 6, 17, 0, tzinfo=UTC)
    assert _rejected_key("invalid_signature", first) == _rejected_key(
        "invalid_signature", same_hour
    )
    assert _rejected_key("invalid_signature", first) != _rejected_key(
        "invalid_signature", next_hour
    )


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        ("failed", "internal_error", True),
        ("ignored", "livemode_mismatch", True),
        ("ignored", "amount_mismatch", True),
        ("ignored", "order_not_found", True),
        ("ignored", "unsupported_event", False),
        ("ignored", "payment_not_paid", False),
        ("processed", None, False),
    ],
)
def test_only_actionable_receipts_request_alerts(status, reason, expected) -> None:
    assert should_alert(status, reason) is expected


def test_checkout_return_url_preserves_safe_app_routes_and_query() -> None:
    order_id = uuid4()
    url = _checkout_return_url(
        "https://app.example.com/",
        "/projects/p-123?c=conv-1&checkout=cancelled&order_id=stale",
        outcome="success",
        order_id=order_id,
    )
    assert (
        url
        == f"https://app.example.com/projects/p-123?c=conv-1&checkout=success&order_id={order_id}"
    )

    settings_url = _checkout_return_url(
        "https://app.example.com",
        "/projects/p-123?checkout_surface=settings",
        outcome="cancelled",
        order_id=order_id,
    )
    assert (
        settings_url
        == f"https://app.example.com/projects/p-123?checkout_surface=settings&checkout=cancelled&order_id={order_id}"
    )


@pytest.mark.parametrize(
    "unsafe",
    [
        None,
        "",
        "   ",
        "https://evil.example/home",
        "//evil.example/home",
        "/\\evil.example",
        "/home/../evil",
        "/api/v1/payments/orders/123",
        "/home\r\nX-Injected: 1",
    ],
)
def test_checkout_return_url_falls_back_to_home_for_unsafe_paths(unsafe) -> None:
    order_id = uuid4()
    url = _checkout_return_url(
        "https://app.example.com",
        unsafe,
        outcome="success",
        order_id=order_id,
    )
    assert url == f"https://app.example.com/home?checkout=success&order_id={order_id}"


