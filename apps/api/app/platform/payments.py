"""Stripe payment adapter — hosted Checkout → exactly-once credit purchase.

Long-term contract: docs/PAYMENTS.md. Stripe owns fiat payment facts,
``payment_orders`` owns the internal purchase snapshot, and the credits ledger
remains the only writer of wallet movements.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import stripe
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tables import PaymentOrder, User, now_utc
from app.platform.billing import purchase_credits

logger = structlog.get_logger()


class PaymentError(Exception):
    """Base payment error with a stable wire/log code."""

    code = "payments.error"


class PaymentConfigurationError(PaymentError):
    code = "payments.not_configured"


class PaymentPackageNotFound(PaymentError):
    code = "payments.package_not_found"


class PaymentProviderError(PaymentError):
    code = "payments.checkout_failed"


class InvalidStripeSignature(PaymentError):
    code = "payments.invalid_signature"


@dataclass(frozen=True)
class CreditPackage:
    key: str
    stripe_price_id: str
    amount_minor: int
    currency: str
    credits: int
    active: bool


@dataclass(frozen=True)
class _PackageSpec:
    amount_minor: int
    currency: str
    credits: int


# Test-first commercial catalog. A missing environment Price makes the package
# inactive, never a zero-priced offer. Values are minor units and credits.
PACKAGE_REGISTRY = {
    "starter": _PackageSpec(amount_minor=1000, currency="eur", credits=10000),
}


def _price_id(package_key: str) -> str:
    if package_key == "starter":
        return settings.stripe_price_starter.strip()
    return ""


def list_credit_packages() -> list[CreditPackage]:
    """Active packages only; the frontend never receives a second price list."""
    packages: list[CreditPackage] = []
    for key, spec in PACKAGE_REGISTRY.items():
        price_id = _price_id(key)
        packages.append(
            CreditPackage(
                key=key,
                stripe_price_id=price_id,
                amount_minor=spec.amount_minor,
                currency=spec.currency,
                credits=spec.credits,
                active=bool(price_id),
            )
        )
    return [package for package in packages if package.active]


def _package(package_key: str) -> CreditPackage:
    for package in list_credit_packages():
        if package.key == package_key:
            return package
    raise PaymentPackageNotFound()


def _configured_livemode() -> bool:
    key = settings.stripe_secret_key.strip()
    if key.startswith(("sk_test_", "rk_test_")):
        return False
    if key.startswith(("sk_live_", "rk_live_")):
        return True
    raise PaymentConfigurationError()


def price_mismatch(package: CreditPackage, price: dict[str, Any]) -> str | None:
    """Reject a mismatched Stripe Price before a customer can pay it."""
    if not price.get("active"):
        return "price_inactive"
    if price.get("type") != "one_time":
        return "price_not_one_time"
    if price.get("unit_amount") != package.amount_minor:
        return "amount_mismatch"
    if str(price.get("currency") or "").lower() != package.currency:
        return "currency_mismatch"
    return None


async def create_checkout_session(
    db: AsyncSession, *, user: User, package_key: str
) -> tuple[PaymentOrder, str]:
    """Persist the order before exposing a payable Checkout Session."""
    package = _package(package_key)
    livemode = _configured_livemode()
    stripe.api_key = settings.stripe_secret_key.strip()
    try:
        price = await stripe.Price.retrieve_async(package.stripe_price_id)
    except stripe.error.StripeError as e:
        logger.warning(
            "stripe_price_read_failed",
            package_key=package.key,
            error_type=type(e).__name__,
        )
        raise PaymentProviderError() from e
    mismatch = price_mismatch(package, price.to_dict_recursive())
    if mismatch:
        logger.warning(
            "stripe_package_misconfigured",
            package_key=package.key,
            reason=mismatch,
        )
        raise PaymentConfigurationError()

    order = PaymentOrder(
        user_id=user.id,
        package_key=package.key,
        provider="stripe",
        livemode=livemode,
        amount_minor=package.amount_minor,
        currency=package.currency,
        credits=package.credits,
        status="pending",
    )
    db.add(order)
    await db.commit()

    base = settings.web_public_url.rstrip("/")
    metadata = {"order_id": str(order.id), "package_key": package.key}
    try:
        session = await stripe.checkout.Session.create_async(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{"price": package.stripe_price_id, "quantity": 1}],
            client_reference_id=str(user.id),
            customer_email=user.email,
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
            success_url=f"{base}/settings?checkout=success&order_id={order.id}",
            cancel_url=f"{base}/settings?checkout=cancelled&order_id={order.id}",
            idempotency_key=f"checkout:{order.id}",
        )
        if not session.url:
            raise PaymentProviderError()
    except stripe.error.StripeError as e:
        order.status = "failed"
        await db.commit()
        logger.warning(
            "stripe_checkout_failed",
            order_id=str(order.id),
            error_type=type(e).__name__,
        )
        raise PaymentProviderError() from e
    except PaymentProviderError:
        order.status = "failed"
        await db.commit()
        raise

    order.provider_checkout_session_id = session.id
    await db.commit()
    logger.info(
        "stripe_checkout_created",
        order_id=str(order.id),
        checkout_session_id=session.id,
        livemode=livemode,
    )
    return order, session.url


async def get_order_for_user(
    db: AsyncSession, *, order_id: UUID, user_id: UUID
) -> PaymentOrder | None:
    """Owner-scoped order read; never a payment or credit trigger."""
    return (
        await db.execute(
            select(PaymentOrder).where(
                PaymentOrder.id == order_id,
                PaymentOrder.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


def session_mismatch(
    order: PaymentOrder,
    session: dict[str, Any],
    *,
    event_livemode: bool | None,
    configured_livemode: bool,
) -> str | None:
    """Pure cross-check between a signed Stripe Session and its internal order."""
    metadata = session.get("metadata") or {}
    if event_livemode != configured_livemode or order.livemode != event_livemode:
        return "livemode_mismatch"
    if order.provider != "stripe" or session.get("object") != "checkout.session":
        return "provider_mismatch"
    if session.get("id") != order.provider_checkout_session_id:
        return "checkout_session_mismatch"
    if metadata.get("order_id") != str(order.id):
        return "order_metadata_mismatch"
    if metadata.get("package_key") != order.package_key:
        return "package_mismatch"
    if session.get("client_reference_id") != str(order.user_id):
        return "user_mismatch"
    if session.get("amount_total") != order.amount_minor:
        return "amount_mismatch"
    if str(session.get("currency") or "").lower() != order.currency:
        return "currency_mismatch"
    return None


def _ignored(reason: str, **log_fields: Any) -> dict[str, Any]:
    logger.info("stripe_webhook_ignored", reason=reason, **log_fields)
    return {"received": True, "ignored": reason}


async def process_stripe_webhook(
    db: AsyncSession, *, payload: bytes, signature: str | None
) -> dict[str, Any]:
    """Verify and apply one Stripe event; only a paid Session moves credits."""
    secret = settings.stripe_webhook_secret.strip()
    if not secret or not signature:
        if not signature:
            raise InvalidStripeSignature()
        raise PaymentConfigurationError()
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except (stripe.error.SignatureVerificationError, ValueError) as e:
        raise InvalidStripeSignature() from e

    data = event.to_dict_recursive()
    event_id = str(data.get("id") or "")
    event_type = str(data.get("type") or "")
    if not event_id:
        raise InvalidStripeSignature()
    if event_type not in {"checkout.session.completed", "checkout.session.expired"}:
        return _ignored("unsupported_event", event_id=event_id, event_type=event_type)

    session = (data.get("data") or {}).get("object") or {}
    if not isinstance(session, dict):
        return _ignored("invalid_session", event_id=event_id)
    metadata = session.get("metadata") or {}
    try:
        order_id = UUID(str(metadata.get("order_id") or ""))
    except ValueError:
        return _ignored("order_not_found", event_id=event_id)

    order = (
        await db.execute(
            select(PaymentOrder).where(PaymentOrder.id == order_id).with_for_update()
        )
    ).scalar_one_or_none()
    if order is None:
        return _ignored("order_not_found", event_id=event_id, order_id=str(order_id))

    mismatch = session_mismatch(
        order,
        session,
        event_livemode=data.get("livemode"),
        configured_livemode=_configured_livemode(),
    )
    if mismatch:
        logger.warning(
            "stripe_webhook_validation_failed",
            event_id=event_id,
            order_id=str(order.id),
            checkout_session_id=order.provider_checkout_session_id,
            reason=mismatch,
        )
        return {"received": True, "ignored": mismatch}

    if event_type == "checkout.session.expired":
        if order.status == "pending":
            order.status = "expired"
            await db.commit()
            logger.info("stripe_order_expired", event_id=event_id, order_id=str(order.id))
        return {"received": True, "status": order.status}

    if session.get("payment_status") != "paid":
        return _ignored("payment_not_paid", event_id=event_id, order_id=str(order.id))
    if order.status == "paid":
        if order.credit_transaction_id is None:
            raise RuntimeError(f"paid payment order {order.id} has no credit transaction")
        return {"received": True, "status": "paid", "duplicate": True}
    if order.credit_transaction_id is not None:
        raise RuntimeError(f"unpaid payment order {order.id} already has a credit transaction")
    # An expired marker may win an out-of-order delivery race; a verified paid
    # Session is the stronger fact. The reverse transition remains forbidden.
    if order.status not in {"pending", "expired"}:
        return _ignored("invalid_order_state", event_id=event_id, order_id=str(order.id))

    transaction = await purchase_credits(
        db,
        user_id=order.user_id,
        order_id=order.id,
        provider_event_id=event_id,
        amount=int(order.credits),
    )
    created = data.get("created")
    order.paid_at = (
        datetime.fromtimestamp(int(created), UTC)
        if isinstance(created, int | float)
        else now_utc()
    )
    order.credited_at = now_utc()
    order.status = "paid"
    order.credit_transaction_id = transaction.id
    payment_intent = session.get("payment_intent")
    if isinstance(payment_intent, dict):
        payment_intent = payment_intent.get("id")
    order.provider_payment_intent_id = (
        payment_intent if isinstance(payment_intent, str) else None
    )
    await db.commit()
    logger.info(
        "stripe_order_paid",
        event_id=event_id,
        order_id=str(order.id),
        credit_transaction_id=str(transaction.id),
    )
    return {"received": True, "status": "paid"}
