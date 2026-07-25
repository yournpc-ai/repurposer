"""Email sending via Resend."""

import structlog
from httpx import AsyncClient, HTTPStatusError

from app.config import settings

logger = structlog.get_logger()

RESEND_API_URL = "https://api.resend.com/emails"


class InvalidRecipientError(ValueError):
    """Resend rejected the recipient address (4xx validation error)."""


async def send_verification_email(email: str, code: str) -> None:
    """Send a verification code email via Resend.

    Raises ``RuntimeError`` when the API key is missing or the request fails.
    """
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    payload = {
        "from": settings.from_email,
        "to": [email],
        "subject": "Your Repurposer verification code",
        "html": f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
          <h2>Verification code</h2>
          <p>Enter this code to sign in to Repurposer:</p>
          <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; margin: 24px 0;">
            {code}
          </p>
          <p>
            This code expires in 10 minutes.
            If you didn't request it, you can ignore this email.
          </p>
        </div>
        """,
        "text": (
            f"Your Repurposer verification code is: {code}\n\n"
            "It expires in 10 minutes. If you didn't request it, ignore this email."
        ),
    }

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }

    async with AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(RESEND_API_URL, json=payload, headers=headers)
            response.raise_for_status()
        except HTTPStatusError as e:
            logger.error(
                "resend_send_failed",
                status=e.response.status_code,
                body=e.response.text,
                email=email,
            )
            if 400 <= e.response.status_code < 500:
                raise InvalidRecipientError(
                    f"Email address rejected by the mail provider: {email}"
                ) from e
            raise RuntimeError(f"Failed to send verification email: {e.response.text}") from e

    logger.info("verification_email_sent", email=email)
