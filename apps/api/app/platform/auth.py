"""Authentication service: verification codes and JWT."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tables import User, VerificationCode

logger = structlog.get_logger()

CODE_LENGTH = 6
CODE_EXPIRE_MINUTES = 10
MAX_ATTEMPTS = 5
JWT_ALGORITHM = "HS256"

# send-code rate limits (abuse control for the email provider)
RESEND_COOLDOWN_SECONDS = 60
MAX_CODES_PER_EMAIL_PER_HOUR = 10
MAX_CODES_PER_IP_PER_HOUR = 30


class RateLimitError(Exception):
    """Raised when a send-code request exceeds the rate limits."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _generate_code() -> str:
    """Generate a 6-digit numeric verification code."""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


async def create_verification_code(
    db: AsyncSession, email: str, ip_address: str | None = None
) -> VerificationCode:
    """Create a new verification code for the given email.

    Enforces a per-email resend cooldown plus hourly caps per email and per
    IP, so the endpoint cannot be used to bomb inboxes or burn email quota.
    """
    email = email.lower().strip()
    now = datetime.now(UTC)

    result = await db.execute(
        select(VerificationCode)
        .where(VerificationCode.email == email)
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    if latest is not None:
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            raise RateLimitError(
                "Please wait before requesting a new code",
                retry_after_seconds=int(RESEND_COOLDOWN_SECONDS - elapsed),
            )

    hour_ago = now - timedelta(hours=1)
    email_count = await db.scalar(
        select(func.count())
        .select_from(VerificationCode)
        .where(
            VerificationCode.email == email,
            VerificationCode.created_at > hour_ago,
        )
    )
    if (email_count or 0) >= MAX_CODES_PER_EMAIL_PER_HOUR:
        raise RateLimitError("Too many codes requested for this email; try again later")

    if ip_address:
        ip_count = await db.scalar(
            select(func.count())
            .select_from(VerificationCode)
            .where(
                VerificationCode.ip_address == ip_address,
                VerificationCode.created_at > hour_ago,
            )
        )
        if (ip_count or 0) >= MAX_CODES_PER_IP_PER_HOUR:
            raise RateLimitError("Too many codes requested; try again later")

    code = _generate_code()
    expires_at = now + timedelta(minutes=CODE_EXPIRE_MINUTES)
    vc = VerificationCode(
        email=email,
        code=code,
        expires_at=expires_at,
        ip_address=ip_address,
    )
    db.add(vc)
    await db.commit()
    await db.refresh(vc)
    logger.info("verification_code_created", email=email, expires_at=expires_at)
    return vc


async def verify_code(
    db: AsyncSession, email: str, code: str
) -> VerificationCode | None:
    """Verify a code for the given email.

    Returns the consumed ``VerificationCode`` on success, ``None`` otherwise.
    Increments ``attempts`` on every check and refuses codes that are expired,
    already consumed, or have too many attempts.
    """
    email = email.lower().strip()
    result = await db.execute(
        select(VerificationCode)
        .where(
            VerificationCode.email == email,
            VerificationCode.consumed_at.is_(None),
            VerificationCode.expires_at > datetime.now(UTC),
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    vc = result.scalar_one_or_none()
    if vc is None:
        return None

    if vc.attempts >= MAX_ATTEMPTS:
        logger.warning("verification_code_max_attempts", email=email)
        return None

    vc.attempts += 1
    if not secrets.compare_digest(vc.code, code.strip()):
        await db.commit()
        logger.warning("verification_code_mismatch", email=email, attempts=vc.attempts)
        return None

    vc.consumed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(vc)
    logger.info("verification_code_consumed", email=email)
    return vc


async def get_or_create_user(db: AsyncSession, email: str) -> User:
    """Get an existing user by email or create a new one."""
    email = email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, name=email.split("@")[0])
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("user_created", email=email, user_id=str(user.id))
    return user


def create_access_token(user_id: UUID) -> str:
    """Create a JWT access token for the given user."""
    expires_delta = timedelta(days=settings.jwt_expire_days)
    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> UUID | None:
    """Decode a JWT access token; returns the user id or ``None`` if invalid."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[JWT_ALGORITHM]
        )
        return UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as e:
        logger.warning("jwt_decode_failed", error=str(e))
        return None
