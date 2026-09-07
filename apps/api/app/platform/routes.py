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
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app.dependencies import DBDep, get_current_user, get_current_user_required
from app.models.schemas import NotificationListResponse
from app.models.tables import User
from app.platform import notifications as svc
from app.platform.auth import (
    RateLimitError,
    create_access_token,
    create_verification_code,
    get_or_create_user,
    verify_code,
)
from app.platform.billing import get_or_create_wallet, held, list_transactions
from app.platform.email import InvalidRecipientError, send_verification_email
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
    await db.commit()
    token = create_access_token(user.id)

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
    # The row's display name: a spend names its run (the task book's
    # instruction, trimmed); grant/topup name their family (+ note).
    label: str
    created_at: datetime


class WalletTransactionsResponse(BaseModel):
    items: list[WalletTransactionItem]
    next_cursor: str | None


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
) -> WalletTransactionsResponse:
    """List the caller's SEMANTIC ledger rows, newest first (keyset
    pagination on the raw ledger — drift-free; the fold rides above it).

    The fold (ADR-057 K4): hold/capture/release collapse per run into ONE
    花费 row (the run's settled net — hold+release cancel; a run with no
    captures yet renders nothing, the ``held`` strip owns the frozen part);
    grant/refund/positive-adjust render as 赠送, purchase as 充值, a
    negative adjust as 花费. Ledger machine kinds never cross the wire."""
    from sqlalchemy import select as _select

    from app.models.tables import WorkflowRun as _Run
    from app.ui_locale import current_ui_language

    keyset = _decode_cursor(cursor) if cursor else None
    rows, nxt = await list_transactions(db, user.id, limit=limit, cursor=keyset)

    # ── Group the run-scoped rows (hold / capture / release) by run ──────
    # Order is preserved newest-first: a group's slot is its LATEST row's.
    groups: dict[str, dict] = {}
    ordered: list[tuple[str, object]] = []  # (group key | "", row) newest-first
    for row in rows:
        ref = row.ref or {}
        run_id = ref.get("run_id") if row.kind in ("hold", "capture", "release") else None
        if run_id:
            group = groups.setdefault(str(run_id), {"captures": 0, "at": row.created_at})
            if row.kind == "capture":
                group["captures"] += int(row.amount)
            ordered.append((str(run_id), row))
        else:
            ordered.append(("", row))

    # Run labels in one batch (a spend names its run's task book).
    run_ids = [UUID(rid) for rid in groups]
    run_rows = (
        list(
            (
                await db.execute(_select(_Run).where(_Run.id.in_(run_ids)))
            )
            .scalars()
            .all()
        )
        if run_ids
        else []
    )
    zh = (current_ui_language() or "").startswith("zh")
    instruction_by_run = {
        str(r.id): str(((r.context or {}).get("instruction") or "")).strip()
        for r in run_rows
    }

    def run_label(run_id: str) -> str:
        text = instruction_by_run.get(run_id) or ""
        if not text:
            return "花费" if zh else "Spent"
        return text if len(text) <= 36 else text[:36] + "…"

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
            items.append(
                WalletTransactionItem(
                    id=f"run:{key}",
                    family="spend",
                    amount=spent,
                    label=run_label(key),
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
        items.append(
            WalletTransactionItem(
                id=str(row.id),
                family=family,
                amount=amount,
                label=row.note or fallback,
                created_at=row.created_at,
            )
        )

    return WalletTransactionsResponse(
        items=items,
        next_cursor=_encode_cursor(*nxt) if nxt is not None else None,
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
