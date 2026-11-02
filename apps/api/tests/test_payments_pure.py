"""Pure payment catalog and signed-Session adjudication coverage (PAYMENTS).

No database, HTTP, LLM, or Stripe network call. Real signature, transaction,
concurrency, and Checkout journeys remain in the payment task's live matrix.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import settings
from app.platform.payment_routes import CreateCheckoutSessionRequest
from app.platform.payments import (
    CUSTOM_TOPUP_POLICY,
    CreditPackage,
    PaymentAmountInvalid,
    PaymentConfigurationError,
    _checkout_line_items,
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
