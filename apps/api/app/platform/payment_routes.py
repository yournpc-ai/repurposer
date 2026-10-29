"""Payment routes — hosted Checkout and Stripe's signed server callback."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.dependencies import DBDep, get_current_user_required
from app.models.tables import PaymentOrder, User
from app.platform import payments
from app.platform.payments import (
    InvalidStripeSignature,
    PaymentConfigurationError,
    PaymentPackageNotFound,
    PaymentProviderError,
)

router = APIRouter()


class CreditPackageResponse(BaseModel):
    key: str
    credits: int
    amount_minor: int
    currency: str


class PaymentPackagesResponse(BaseModel):
    items: list[CreditPackageResponse]


class CreateCheckoutSessionRequest(BaseModel):
    package_key: str = Field(min_length=1, max_length=40)


class CheckoutSessionResponse(BaseModel):
    order_id: UUID
    checkout_url: str


class PaymentOrderResponse(BaseModel):
    id: UUID
    package_key: str
    status: str
    credits: int
    amount_minor: int
    currency: str
    paid_at: datetime | None
    credited_at: datetime | None
    created_at: datetime


def _order_response(order: PaymentOrder) -> PaymentOrderResponse:
    return PaymentOrderResponse(
        id=order.id,
        package_key=order.package_key,
        status=order.status,
        credits=int(order.credits),
        amount_minor=int(order.amount_minor),
        currency=order.currency,
        paid_at=order.paid_at,
        credited_at=order.credited_at,
        created_at=order.created_at,
    )


@router.get("/packages", response_model=PaymentPackagesResponse)
async def list_packages(
    user: User = Depends(get_current_user_required),
) -> PaymentPackagesResponse:
    del user  # Authentication is required even though the catalog is global.
    return PaymentPackagesResponse(
        items=[
            CreditPackageResponse(
                key=package.key,
                credits=package.credits,
                amount_minor=package.amount_minor,
                currency=package.currency,
            )
            for package in payments.list_credit_packages()
        ]
    )


@router.post("/checkout-sessions", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    data: CreateCheckoutSessionRequest,
    db: DBDep,
    user: User = Depends(get_current_user_required),
) -> CheckoutSessionResponse:
    try:
        order, checkout_url = await payments.create_checkout_session(
            db, user=user, package_key=data.package_key
        )
    except PaymentPackageNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=e.code) from e
    except PaymentConfigurationError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=e.code) from e
    except PaymentProviderError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=e.code) from e
    return CheckoutSessionResponse(order_id=order.id, checkout_url=checkout_url)


@router.get("/orders/{order_id}", response_model=PaymentOrderResponse)
async def get_payment_order(
    order_id: UUID,
    db: DBDep,
    user: User = Depends(get_current_user_required),
) -> PaymentOrderResponse:
    order = await payments.get_order_for_user(db, order_id=order_id, user_id=user.id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="payments.order_not_found")
    return _order_response(order)


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: DBDep) -> dict[str, Any]:
    # The raw body is the signed payload; JSON parsing happens only inside the
    # SDK's signature verification. No user JWT belongs on this route.
    payload = await request.body()
    try:
        return await payments.process_stripe_webhook(
            db,
            payload=payload,
            signature=request.headers.get("stripe-signature"),
        )
    except InvalidStripeSignature as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=e.code) from e
    except PaymentConfigurationError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=e.code) from e
