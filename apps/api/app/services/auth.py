"""Authentication service: verification codes and JWT."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tables import User, VerificationCode

logger = structlog.get_logger()

CODE_LENGTH = 6
CODE_EXPIRE_MINUTES = 10
MAX_ATTEMPTS = 5
JWT_ALGORITHM = "HS256"


def _generate_code() -> str:
    """Generate a 6-digit numeric verification code."""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


async def create_verification_code(
    db: AsyncSession, email: str, ip_address: str | None = None
) -> VerificationCode:
    """Create a new verification code for the given email."""
    code = _generate_code()
    expires_at = datetime.now(UTC) + timedelta(minutes=CODE_EXPIRE_MINUTES)
    vc = VerificationCode(
        email=email.lower().strip(),
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
