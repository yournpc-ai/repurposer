"""Platform-layer routes: file streaming / auth / notifications.

File streaming: the object storage bucket is public-read, so these endpoints
only perform ownership checks and redirect callers to the public object URL.
Range requests and delivery are handled entirely by the object store.

``?proxy=1`` streams the bytes through the API instead of redirecting, for
callers that ``fetch()`` the file programmatically: the 307 hop to the storage
origin is subject to CORS, and the bucket does not send ``Vary: Origin`` — a
no-cors ``<video>`` copy of the same object (e.g. a Remotion preview) poisons
the browser cache and makes later CORS fetches fail with "no ACAO header".
"""

import base64
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select

from app.config import settings as app_settings
from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import NotificationListResponse
from app.models.tables import LoginSession, User, now_utc
from app.platform import notifications as svc
from app.platform.auth import (
    RateLimitError,
    create_access_token,
    create_verification_code,
    get_or_create_user,
    session_claims,
    verify_code,
)
from app.platform.billing import get_or_create_wallet, held, list_transactions
from app.platform.email import InvalidRecipientError, send_verification_email
from app.platform.user_settings import (
    read_confirmation_prefs,
    read_workspace_layout,
)
from app.providers.storage import (
    download_to_temp,
    owner_from_path,
    presign_download,
    public_url,
)

files_router = APIRouter()


def _authorize_path(file_path: str, current_user: User | None) -> None:
    """Refuse access unless the path belongs to the current user."""
    owner = owner_from_path(file_path)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    try:
        if UUID(owner) == current_user.id:
            return
    except ValueError:
        pass
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied",
    )


@files_router.get("/files/{file_path:path}")
async def stream_upload(
    file_path: str,
    background: BackgroundTasks,
    proxy: bool = False,
    current_user: User | None = Depends(get_current_user),
):
    """Stream an uploaded source file by key."""
    _authorize_path(file_path, current_user)
    if proxy:
        tmp = await download_to_temp(file_path)
        if tmp is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )
        background.add_task(tmp.unlink, missing_ok=True)
        return FileResponse(tmp, filename=Path(file_path).name)
    url = public_url(file_path)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@files_router.get("/outputs/{file_path:path}")
async def stream_output(
    file_path: str,
    download: bool = False,
    current_user: User | None = Depends(get_current_user),
):
    """Stream a rendered output (MP4/SRT) by key.

    ``?download=true`` redirects to a presigned GET carrying
    ``Content-Disposition: attachment`` so the browser saves the file instead
    of playing it inline.
    """
    _authorize_path(file_path, current_user)
    if download:
        url = await presign_download(file_path, filename=Path(file_path).name)
    else:
        url = public_url(file_path)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


# ---- Auth (email verification code login) -----------------------------

auth_router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(raw: str) -> str:
    email = raw.lower().strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email address",
        )
    return email


class SendCodeRequest(BaseModel):
    email: str


class SendCodeResponse(BaseModel):
    message: str


class VerifyCodeRequest(BaseModel):
    email: str
    code: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None


class VerifyCodeResponse(BaseModel):
    token: str
    user: UserResponse


# ---- User settings (ADR-117 §1 — 两档确认偏好的用户级座位) -------------------


class UserSettingsResponse(BaseModel):
    """The settings read shape: the two confirmation prefs (ADR-117 D1) +
    the workspace layout pref (ADR-123 — stored only; the effective
    ``canvas_available`` is composed client-side and rides every chat
    request). The internal guardrail (``billing.always_confirm_above``) is
    an ops parameter — never on this response, never a user setting (D6)."""

    confirm_execution: str
    confirm_credits: str
    workspace_layout: str
    theme: Literal["light", "dark", "system"] | None
    locale: Literal["en", "zh"] | None
    publish_alerts: bool
    email_available: bool


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: Literal["light", "dark", "system"] | None = None
    locale: Literal["en", "zh"] | None = None
    publish_alerts: bool | None = None
    confirm_execution: Literal["auto", "ask"] | None = None
    confirm_credits: Literal["auto", "ask"] | None = None
    workspace_layout: Literal["auto", "chat"] | None = None

    @model_validator(mode="after")
    def _at_least_one_key(self) -> "UserSettingsUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("at least one setting is required")
        return self


@auth_router.get("/settings", response_model=UserSettingsResponse)
async def get_settings(
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> UserSettingsResponse:
    """Read the user's settings (读容忍 — absent/unknown values read as the
    defaults)."""
    return _settings_response(current_user)


def _settings_response(user: User) -> UserSettingsResponse:
    saved = user.settings or {}
    execution, credits = read_confirmation_prefs(saved)
    return UserSettingsResponse(
        confirm_execution=execution,
        confirm_credits=credits,
        theme=saved.get("theme") if saved.get("theme") in ("light", "dark", "system") else None,
        locale=saved.get("locale") if saved.get("locale") in ("en", "zh") else None,
        publish_alerts=saved.get("publish_alerts") is True,
        email_available=bool(app_settings.resend_api_key and app_settings.from_email),
        workspace_layout=read_workspace_layout(saved),
    )


@auth_router.put("/settings", response_model=UserSettingsResponse)
async def put_settings(
    data: UserSettingsUpdate,
    db: DBDep,
    current_user: User = Depends(get_current_user_required),
) -> UserSettingsResponse:
    """One-key merge write — the rest of the settings block survives.

    收口修红 (2026-09-24, B3 live 验收实测): the auth dependency loads the
    User in its OWN short-lived session — assigning ``current_user.settings``
    mutated a detached instance and committing the route's session wrote
    NOTHING (PUT echoed the new value with 200 while ``users.settings``
    stayed NULL). The write goes through the route's session."""
    user = await db.get(User, current_user.id, with_for_update=True)
    if user is None:
        raise HTTPException(401, "Account no longer exists")
    user.settings = {**(user.settings or {}), **data.model_dump(exclude_none=True)}
    await db.commit()
    return _settings_response(user)


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


@auth_router.get("/profile", response_model=UserResponse)
async def read_profile(current_user: User = Depends(get_current_user_required)):
    return UserResponse(id=str(current_user.id), email=current_user.email, name=current_user.name)


@auth_router.put("/profile", response_model=UserResponse)
async def save_profile(
    data: ProfileUpdate, db: DBDep, current_user: User = Depends(get_current_user_required)
):
    user = await db.get(User, current_user.id)
    user.name = data.name
    await db.commit()
    return await read_profile(user)


class SessionResponse(BaseModel):
    id: UUID
    user_agent: str
    last_seen_at: datetime
    current: bool


@auth_router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    request: Request, db: DBDep, user: User = Depends(get_current_user_required)
):
    current_id = session_claims(request.headers["authorization"].split()[1])[1]
    rows = await db.scalars(
        select(LoginSession)
        .where(
            LoginSession.user_id == user.id,
            LoginSession.revoked_at.is_(None),
            LoginSession.expires_at > now_utc(),
        )
        .order_by(LoginSession.last_seen_at.desc())
    )
    return [
        SessionResponse(
            id=row.id,
            user_agent=row.user_agent,
            last_seen_at=row.last_seen_at,
            current=row.id == current_id,
        )
        for row in rows
    ]


@auth_router.post("/logout", status_code=204)
async def logout(request: Request, db: DBDep, user: User = Depends(get_current_user_required)):
    session_id = session_claims(request.headers["authorization"].split()[1])[1]
    await revoke_session(session_id, db, user)


@auth_router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: UUID, db: DBDep, user: User = Depends(get_current_user_required)
):
    row = await db.get(LoginSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Session not found")
    row.revoked_at = now_utc()
    await db.commit()


@auth_router.post("/send-code", response_model=SendCodeResponse)
async def send_code(
    data: SendCodeRequest,
    request: Request,
    db: DBDep,
) -> SendCodeResponse:
    """Send a verification code to the given email."""
    email = _normalize_email(data.email)
    ip_address = request.client.host if request.client else None

    try:
        vc = await create_verification_code(db, email, ip_address)
    except RateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        ) from e
    try:
        await send_verification_email(email, vc.code)
    except InvalidRecipientError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    return SendCodeResponse(message="Verification code sent")


@auth_router.post("/verify-code", response_model=VerifyCodeResponse)
async def verify_code_endpoint(
    data: VerifyCodeRequest,
    request: Request,
    db: DBDep,
) -> VerifyCodeResponse:
    """Verify the code and return a JWT."""
    email = _normalize_email(data.email)
    vc = await verify_code(db, email, data.code)
    if vc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user = await get_or_create_user(db, email)
    # Credits (ADR-055): lazy wallet opening + signup grant rides the login
    # chain — every login (re)checks, the wallet opens exactly once (the
    # wallet PK + the signup idempotency key are the dedupe backstop).
    await get_or_create_wallet(db, user.id)
    session_id = uuid4()
    token = create_access_token(user.id, session_id)
    expires = session_claims(token)[2]
    await db.execute(
        delete(LoginSession).where(
            LoginSession.user_id == user.id, LoginSession.expires_at <= now_utc()
        )
    )
    db.add(
        LoginSession(
            id=session_id,
            user_id=user.id,
            user_agent=request.headers.get("user-agent", "")[:512],
            expires_at=expires,
        )
    )
    await db.commit()

    return VerifyCodeResponse(
        token=token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
        ),
    )


# ---- Wallet (credits, ADR-055) --------------------------------------------

wallet_router = APIRouter()


class WalletResponse(BaseModel):
    """The wallet's read shape (BILLING §7): ``balance`` is the spendable
    truth (negative shown honestly — BILLING §5); ``held`` is the credits
    currently frozen in un-settled run holds."""

    balance: int
    held: int


@wallet_router.get("/wallet", response_model=WalletResponse)
async def get_wallet(
    db: DBDep,
    user: User = Depends(get_current_user_required),
) -> WalletResponse:
    """Read the caller's wallet, lazy-opening it on first contact (the login
    chain is the usual opener; this keeps scripts and fresh tokens honest)."""
    wallet = await get_or_create_wallet(db, user.id)
    frozen = await held(db, user.id)
    await db.commit()
    return WalletResponse(balance=int(wallet.balance), held=frozen)


class WalletTransactionItem(BaseModel):
    """One SEMANTIC ledger row (ADR-057 K4, BILLING §7 — the user面 only ever
    sees three families): the raw hold/capture/release machinery folds
    server-side into per-run-event net rows — a run's captures become ONE
    花费 line named after the run; holds and releases never render (the
    wallet's ``held`` strip already carries the frozen truth). The ledger
    itself is untouched — this is a read projection, and a run split by the
    page edge shows its page-local net (the fold is per page)."""

    id: str
    # 三族: spend = 花费 (a run's settled cost / a negative adjust) /
    # grant = 赠送 (signup grant, refund, a positive adjust) /
    # topup = 充值 (purchase — W11 boundary).
    family: str
    amount: int
    # The row's display name per ADR-058 二源律: grant/topup carry their
    # localized semantic family label; a spend carries its run's
    # LLM-chosen plan name or None — the client then composes the honest
    # fallback from ``output_types`` (世界自证, 产物徽标). The user's prompt
    # text is NEVER the label: it names what the user asked, not what ran.
    label: str | None = None
    # Spend-row facts for the client's honest fallback (the produced PUBLIC
    # output types, INTERNAL_OUTPUT_TYPES excluded) and meta line.
    output_types: list[str] = Field(default_factory=list)
    # A spend's trimmed instruction — the client's last-resort echo (ADR-060:
    # the user's own words) when a run has neither an LLM name nor public
    # outputs (understand-only / aborted runs).
    hint: str | None = None
    project_name: str | None = None
    created_at: datetime
    # Fiat facts for a purchase, joined from its linked payment order in one
    # batch. Grants and legacy purchases without an order link keep these NULL;
    # the client must never infer a fiat amount from the credited amount.
    payment_order_id: str | None = None
    payment_provider: str | None = None
    payment_amount_minor: int | None = None
    payment_currency: str | None = None
    paid_at: datetime | None = None


class WalletTransactionsResponse(BaseModel):
    items: list[WalletTransactionItem]
    next_cursor: str | None
    total: int | None = None


def _encode_cursor(at: datetime, row_id: UUID) -> str:
    """The keyset cursor's opaque wire form: base64url([created_at, id])."""
    raw = json.dumps([at.isoformat(), str(row_id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Inverse of ``_encode_cursor`` — a malformed cursor is a client 422,
    never a 500."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        at_raw, id_raw = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return datetime.fromisoformat(at_raw), UUID(id_raw)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from e


@wallet_router.get("/wallet/transactions", response_model=WalletTransactionsResponse)
async def get_wallet_transactions(
    db: DBDep,
    user: User = Depends(get_current_user_required),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None),
    direction: Literal["in", "out"] | None = Query(default=None),
) -> WalletTransactionsResponse:
    """List the caller's SEMANTIC ledger rows, newest first (keyset
    pagination on the raw ledger — drift-free; the fold rides above it).
    ``direction=in|out`` applies the incoming/spend boundary before keyset
    pagination so the two Settings tables paginate independently.

    The fold (ADR-057 K4): hold/capture/release collapse per run into ONE
    花费 row (the run's settled net — hold+release cancel; a run with no
    captures yet renders nothing, the ``held`` strip owns the frozen part);
    grant/refund/positive-adjust render as 赠送, purchase as 充值, a
    negative adjust as 花费. Ledger machine kinds never cross the wire."""
    from sqlalchemy import select as _select

    from app.models.tables import (
        CreditTransaction as _CreditTransaction,
    )
    from app.models.tables import (
        ExportJob,
        MediaJob,
    )
    from app.models.tables import (
        PaymentOrder as _PaymentOrder,
    )
    from app.models.tables import (
        Project as _Project,
    )
    from app.ui_locale import current_ui_language

    keyset = _decode_cursor(cursor) if cursor else None
    rows, nxt, total = await list_transactions(
        db, user.id, limit=limit, cursor=keyset, direction=direction
    )

    # ── Group the run-scoped rows (hold / capture / release) by run ──────
    # Order is preserved newest-first: a group's slot is its LATEST row's.
    groups: dict[str, dict] = {}
    ordered: list[tuple[str, _CreditTransaction]] = []  # (group key | "", row) newest-first
    for row in rows:
        ref = row.ref or {}
        job_id = (ref.get("export_id") or ref.get("media_job_id")) if row.kind in ("hold", "capture", "release") else None
        if job_id:
            group = groups.setdefault(str(job_id), {"captures": 0, "at": row.created_at})
            if row.kind == "capture":
                group["captures"] += int(row.amount)
            ordered.append((str(job_id), row))
        else:
            ordered.append(("", row))

    purchase_ids = [
        row.id for key, row in ordered if not key and row.kind == "purchase"
    ]
    payment_orders = (
        list(
            (
                await db.execute(
                    _select(_PaymentOrder).where(
                        _PaymentOrder.user_id == user.id,
                        _PaymentOrder.credit_transaction_id.in_(purchase_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        if purchase_ids
        else []
    )
    payment_by_transaction = {
        str(order.credit_transaction_id): order for order in payment_orders
    }

    project_titles = {}
    for model, field in ((ExportJob, "export_id"), (MediaJob, "media_job_id")):
        ids = {UUID(row.ref[field]) for key, row in ordered if key and row.ref.get(field)}
        if ids:
            titles = await db.execute(_select(model.id, _Project.title)
                .join(_Project, _Project.id == model.project_id)
                .where(model.id.in_(ids), _Project.user_id == user.id))
            project_titles.update({str(job_id): title for job_id, title in titles})
    zh = (current_ui_language() or "").startswith("zh")

    items: list[WalletTransactionItem] = []
    emitted: set[str] = set()
    for key, row in ordered:
        if key:
            if key in emitted:
                continue
            emitted.add(key)
            spent = -abs(int(groups[key]["captures"]))
            if spent == 0:
                # A run with no metered captures yet — the held strip owns
                # its frozen part; no row (鸡毛蒜皮不上明面).
                continue
            is_export = bool((row.ref or {}).get("export_id"))
            items.append(
                WalletTransactionItem(
                    id=f"export:{key}" if is_export else f"media:{key}",
                    family="spend",
                    amount=spent,
                    label=(("视频导出" if zh else "MP4 export") if is_export else ("素材生成" if zh else "Media generation")),
                    output_types=["video"] if is_export else [],
                    project_name=project_titles.get(key),
                    created_at=groups[key]["at"],
                )
            )
            continue
        amount = int(row.amount)
        if row.kind == "purchase":
            family = "topup"
        elif row.kind in ("grant", "refund"):
            family = "grant"
        elif row.kind == "adjust":
            family = "grant" if amount >= 0 else "spend"
        else:
            # Unknown kinds (forward-compat) bucket by sign, never raw.
            family = "grant" if amount >= 0 else "spend"
        fallback = {
            "topup": "充值" if zh else "Top-up",
            "grant": "赠送" if zh else "Grant",
            "spend": "花费" if zh else "Spent",
        }[family]
        payment = payment_by_transaction.get(str(row.id))
        items.append(
            WalletTransactionItem(
                id=str(row.id),
                family=family,
                amount=amount,
                # Internal notes are operational metadata, not localized UI
                # copy. Incoming rows use their semantic family label; only
                # spend rows may carry a human-readable adjustment note.
                label=(row.note or fallback) if family == "spend" else fallback,
                created_at=row.created_at,
                payment_order_id=str(payment.id) if payment else None,
                payment_provider=payment.provider if payment else None,
                payment_amount_minor=(
                    int(payment.amount_minor) if payment else None
                ),
                payment_currency=payment.currency if payment else None,
                paid_at=payment.paid_at if payment else None,
            )
        )

    return WalletTransactionsResponse(
        items=items,
        next_cursor=_encode_cursor(*nxt) if nxt is not None else None,
        total=total,
    )


# ---- Notifications ----------------------------------------------------

notifications_router = APIRouter()


@notifications_router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    db: DBDep,
    user: User = Depends(get_current_user_required),
    limit: int = Query(default=30, le=100),
) -> NotificationListResponse:
    items, unread = await svc.list_notifications(db, user.id, limit=limit)
    return NotificationListResponse(items=items, unread_count=unread)


@notifications_router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_notifications(
    db: DBDep,
    user: User = Depends(get_current_user_required),
) -> None:
    await svc.mark_all_read(db, user.id)
    await db.commit()
