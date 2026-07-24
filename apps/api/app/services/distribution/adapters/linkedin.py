"""LinkedIn adapter (DISTRIBUTION.md §2/§10).

Personal profile publishing only (P1 定: 个人号 ``w_member_social`` 先行,
company pages deferred). OAuth = Authorization Code + OpenID Connect.

Publish paths by payload media:
- no media (text derivative) → ``POST /rest/posts``, completes synchronously.
- image (quote card) → ``/rest/images?action=initializeUpload`` → PUT bytes →
  post referencing the image URN (synchronous).
- video (clip) → ``/rest/videos?action=initializeUpload`` → PUT bytes → the
  video processes asynchronously; ``await_publish`` polls
  ``GET /rest/videos/{urn}`` and creates the post once ``AVAILABLE``.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode

import httpx
import structlog

from app.config import settings
from app.services.distribution.adapters.base import (
    normalize_network_errors,
    ChannelAccountPayload,
    JobHandle,
    PlatformError,
    PlatformErrorKind,
    PublishResult,
)

logger = structlog.get_logger()

_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_API = "https://api.linkedin.com"
_SCOPES = ["openid", "profile", "email", "w_member_social"]

_VIDEO_POLL_STATUS_AVAILABLE = "AVAILABLE"


def _err(kind: PlatformErrorKind, detail: str) -> PlatformError:
    logger.warning("linkedin_api_error", kind=kind.value, detail=detail[:300])
    return PlatformError(kind, detail)


def _check(resp: httpx.Response, what: str) -> httpx.Response:
    """Map LinkedIn HTTP failures onto the unified error taxonomy."""
    if resp.status_code < 400:
        return resp
    body = resp.text[:300]
    if resp.status_code in (401, 403):
        raise _err(PlatformErrorKind.TOKEN, f"{what}: {resp.status_code} {body}")
    if resp.status_code == 429:
        raise _err(PlatformErrorKind.RATE_LIMIT, f"{what}: 429 {body}")
    if resp.status_code == 422:
        raise _err(PlatformErrorKind.CONTENT_POLICY, f"{what}: 422 {body}")
    if resp.status_code >= 500:
        raise _err(PlatformErrorKind.TRANSIENT, f"{what}: {resp.status_code} {body}")
    raise _err(PlatformErrorKind.UNKNOWN, f"{what}: {resp.status_code} {body}")


def _bearer(credentials: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {credentials['access_token']}"}


class LinkedInAdapter:
    """LinkedIn personal-profile OAuth + posts/images/videos publishing."""

    platform = "linkedin"

    # ── OAuth ────────────────────────────────────────────────────────────

    def oauth_url(self, *, redirect_uri: str, state: str) -> str:
        if not settings.linkedin_client_id:
            raise _err(PlatformErrorKind.VALIDATION, "LinkedIn channel not configured")
        params = {
            "response_type": "code",
            "client_id": settings.linkedin_client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(_SCOPES),
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    @normalize_network_errors
    async def exchange_code(
        self, *, code: str, redirect_uri: str
    ) -> ChannelAccountPayload:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": settings.linkedin_client_id,
                    "client_secret": settings.linkedin_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            _check(resp, "linkedin exchange_code")
            token = resp.json()
            credentials = {
                "access_token": token["access_token"],
                "refresh_token": token.get("refresh_token"),
            }
            expires_at = datetime.now(UTC) + timedelta(
                seconds=int(token.get("expires_in", 5184000))
            )
            profile = await self._fetch_profile(client, credentials)
            return ChannelAccountPayload(
                platform_user_id=profile["sub"],
                display_name=profile.get("name", ""),
                avatar_url=profile.get("picture"),
                scopes=_SCOPES,
                credentials=credentials,
                token_expires_at=expires_at,
            )

    @normalize_network_errors
    async def refresh(self, credentials: dict[str, Any]) -> ChannelAccountPayload:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise _err(PlatformErrorKind.TOKEN, "linkedin: no refresh token stored")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.linkedin_client_id,
                    "client_secret": settings.linkedin_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            _check(resp, "linkedin refresh")
            token = resp.json()
            profile = await self._fetch_profile(
                client, {"access_token": token["access_token"]}
            )
            return ChannelAccountPayload(
                platform_user_id=profile["sub"],
                display_name=profile.get("name", ""),
                avatar_url=profile.get("picture"),
                scopes=_SCOPES,
                credentials={
                    "access_token": token["access_token"],
                    "refresh_token": token.get("refresh_token") or refresh_token,
                },
                token_expires_at=datetime.now(UTC)
                + timedelta(seconds=int(token.get("expires_in", 5184000))),
            )

    async def _fetch_profile(
        self, client: httpx.AsyncClient, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        resp = await client.get(f"{_API}/v2/userinfo", headers=_bearer(credentials))
        _check(resp, "linkedin userinfo")
        return resp.json()

    # ── Publishing ───────────────────────────────────────────────────────

    @normalize_network_errors
    async def begin_publish(
        self, credentials: dict[str, Any], payload: dict[str, Any]
    ) -> JobHandle:
        media = payload.get("media") or {}
        video_url = media.get("video")
        image_url = media.get("image") or payload.get("cover_image_url")
        async with httpx.AsyncClient(timeout=120) as client:
            if video_url:
                video_urn = await self._upload_media(
                    client, credentials, video_url, kind="videos", urn_field="video"
                )
                # Video processing is async — the URN is the reconciliation
                # anchor; await_publish creates the post once AVAILABLE.
                return JobHandle(job_id=video_urn)
            if image_url:
                image_urn = await self._upload_media(
                    client, credentials, image_url, kind="images", urn_field="image"
                )
                post_urn = await self._create_post(
                    client, credentials, payload, media_urn=image_urn, media_kind="image"
                )
                return JobHandle(
                    job_id=post_urn, post_id=post_urn, post_url=self._post_url(post_urn)
                )
            post_urn = await self._create_post(client, credentials, payload)
            return JobHandle(
                job_id=post_urn, post_id=post_urn, post_url=self._post_url(post_urn)
            )

    @normalize_network_errors
    async def await_publish(
        self, credentials: dict[str, Any], job: JobHandle, payload: dict[str, Any]
    ) -> PublishResult:
        """Poll an async video upload; create the post once AVAILABLE."""
        if job.post_id:
            return PublishResult(
                status="published", post_id=job.post_id, post_url=job.post_url
            )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_API}/rest/videos/{quote(job.job_id, safe='')}",
                headers=_bearer(credentials),
            )
            _check(resp, "linkedin video status")
            status_value = resp.json().get("status")
            if status_value == _VIDEO_POLL_STATUS_AVAILABLE:
                post_urn = await self._create_post(
                    client, credentials, payload, media_urn=job.job_id, media_kind="video"
                )
                return PublishResult(
                    status="published",
                    post_id=post_urn,
                    post_url=self._post_url(post_urn),
                )
            if status_value in ("PROCESSING", "PROCESSING_PROGRESS", "WAITING_UPLOAD"):
                return PublishResult(status="pending")
            raise _err(
                PlatformErrorKind.CONTENT_POLICY,
                f"linkedin video processing failed: {status_value}",
            )

    async def _upload_media(
        self,
        client: httpx.AsyncClient,
        credentials: dict[str, Any],
        source_url: str,
        *,
        kind: str,
        urn_field: str,
    ) -> str:
        """initializeUpload → download our object → PUT bytes → return URN."""
        owner = f"urn:li:person:{credentials['platform_user_id']}"
        resp = await client.post(
            f"{_API}/rest/{kind}?action=initializeUpload",
            headers={**_bearer(credentials), "X-Restli-Protocol-Version": "2.0.0"},
            json={"initializeUploadRequest": {"owner": owner}},
        )
        _check(resp, f"linkedin {kind} initializeUpload")
        data = resp.json()["value"]
        upload_url, urn = data["uploadUrl"], data[urn_field]

        media = await client.get(source_url, timeout=120, follow_redirects=True)
        if media.status_code >= 400:
            raise _err(
                PlatformErrorKind.VALIDATION,
                f"linkedin: source media unreadable ({media.status_code})",
            )
        put = await client.put(
            upload_url,
            content=media.content,
            headers={**_bearer(credentials), "Content-Type": "application/octet-stream"},
            timeout=300,
        )
        _check(put, f"linkedin {kind} binary upload")
        return urn

    async def _create_post(
        self,
        client: httpx.AsyncClient,
        credentials: dict[str, Any],
        payload: dict[str, Any],
        *,
        media_urn: str | None = None,
        media_kind: str | None = None,
    ) -> str:
        commentary = payload.get("caption") or payload.get("title") or ""
        hashtags = payload.get("hashtags") or []
        if hashtags:
            tags = " ".join(
                f"#{t.lstrip('#').replace(' ', '')}" for t in hashtags if str(t).strip()
            )
            commentary = f"{commentary}\n\n{tags}".strip()
        body: dict[str, Any] = {
            "author": f"urn:li:person:{credentials['platform_user_id']}",
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        title = payload.get("title") or ""
        if media_urn and media_kind:
            body["content"] = {
                "media": {"id": media_urn, **({"title": title} if title else {})}
            }
        resp = await client.post(
            f"{_API}/rest/posts",
            headers={**_bearer(credentials), "X-Restli-Protocol-Version": "2.0.0"},
            json=body,
        )
        _check(resp, "linkedin create post")
        post_urn = resp.headers.get("x-restli-id") or resp.json().get("id", "")
        if not post_urn:
            raise _err(PlatformErrorKind.UNKNOWN, "linkedin: post id missing")
        return post_urn

    @staticmethod
    def _post_url(post_urn: str) -> str | None:
        # urn:li:share:{id} / urn:li:ugcPost:{id} → web URL
        parts = post_urn.split(":")
        if len(parts) == 4 and parts[1] == "li":
            return f"https://www.linkedin.com/feed/update/{post_urn}/"
        return None
