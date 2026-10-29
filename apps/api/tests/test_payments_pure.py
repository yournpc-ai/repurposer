"""Pure payment catalog and signed-Session adjudication coverage (PAYMENTS).

No database, HTTP, LLM, or Stripe network call. Real signature, transaction,
concurrency, and Checkout journeys remain in the payment task's live matrix.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import settings
from app.platform.payments import (
    CreditPackage,
    PaymentConfigurationError,
    _configured_livemode,
    list_credit_packages,
    price_mismatch,
    session_mismatch,
)


def test_missing_price_hides_package(monkeypatch) -> None:
    monkeypatch.setattr(settings, "stripe_price_starter", "")
    assert list_credit_packages() == []


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


def test_starter_package_uses_server_side_test_price_and_credits(monkeypatch) -> None:
    monkeypatch.setattr(settings, "stripe_price_starter", "price_test_starter")
    assert [vars(package) for package in list_credit_packages()] == [
        {
            "key": "starter",
            "stripe_price_id": "price_test_starter",
            "amount_minor": 1000,
            "currency": "eur",
            "credits": 10000,
            "active": True,
        }
    ]


def _price_package() -> CreditPackage:
    return CreditPackage(
        key="starter",
        stripe_price_id="price_test_starter",
        amount_minor=1000,
        currency="eur",
        credits=10000,
        active=True,
    )


def test_stripe_price_is_validated_before_checkout() -> None:
    price = {"active": True, "type": "one_time", "unit_amount": 1000, "currency": "eur"}
    assert price_mismatch(_price_package(), price) is None


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"active": False}, "price_inactive"),
        ({"type": "recurring"}, "price_not_one_time"),
        ({"unit_amount": 999}, "amount_mismatch"),
        ({"currency": "usd"}, "currency_mismatch"),
    ],
)
def test_invalid_stripe_price_fails_before_customer_payment(patch, expected) -> None:
    price = {"active": True, "type": "one_time", "unit_amount": 1000, "currency": "eur"}
    price.update(patch)
    assert price_mismatch(_price_package(), price) == expected


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
