"""TikTok adapter (DISTRIBUTION.md §2/§10).

Direct posting only (``video.publish`` scope; no draft-box mode). Videos are
pulled from our public object URL (``PULL_FROM_URL``) — no binary relay
through the API process. Publishing is asynchronous: init returns a
``publish_id`` (the reconciliation anchor), ``await_publish`` polls
``/post/publish/status/fetch/``.

``creator_info`` is queried inside ``begin_publish`` before init (§4: 发布前
必查 creator 能力) — an unconfigured or unprivileged creator fails fast with a
validation error instead of a burned publish attempt.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

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

_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_API = "https://open.tiktokapis.com/v2"
_SCOPES = ["user.info.basic", "video.publish"]


def _err(kind: PlatformErrorKind, detail: str) -> PlatformError:
    logger.warning("tiktok_api_error", kind=kind.value, detail=detail[:300])
    return PlatformError(kind, detail)


def _check_biz(data: dict[str, Any], what: str) -> dict[str, Any]:
    """TikTok returns HTTP 200 with a business error payload — normalize it."""
    error = data.get("error") or {}
    code = error.get("code", "ok")
    if code in (None, "ok"):
        return data
    message = error.get("message", "")
    detail = f"{what}: {code} {message}"
    if code in ("access_token_invalid", "invalid_token", "token_expired"):
        raise _err(PlatformErrorKind.TOKEN, detail)
    if code == "rate_limit_exceeded":
        raise _err(PlatformErrorKind.RATE_LIMIT, detail)
    if code in (
        "spam_risk_too_many_posts",
        "spam_risk_user_banned_from_posting",
        "spam_risk_text",
        "photo_sensitive_content",
        "video_file_is_muted",
    ):
        raise _err(PlatformErrorKind.CONTENT_POLICY, detail)
    raise _err(PlatformErrorKind.UNKNOWN, detail)


def _check(resp: httpx.Response, what: str) -> httpx.Response:
    if resp.status_code < 400:
        return resp
    body = resp.text[:300]
    if resp.status_code in (401, 403):
        raise _err(PlatformErrorKind.TOKEN, f"{what}: {resp.status_code} {body}")
    if resp.status_code == 429:
        raise _err(PlatformErrorKind.RATE_LIMIT, f"{what}: 429 {body}")
    if resp.status_code >= 500:
        raise _err(PlatformErrorKind.TRANSIENT, f"{what}: {resp.status_code} {body}")
    raise _err(PlatformErrorKind.UNKNOWN, f"{what}: {resp.status_code} {body}")


def _bearer(credentials: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {credentials['access_token']}"}


class TikTokAdapter:
    """TikTok OAuth + Content Posting API (video direct post)."""

    platform = "tiktok"

    # ── OAuth ────────────────────────────────────────────────────────────

    def oauth_url(self, *, redirect_uri: str, state: str) -> str:
        if not settings.tiktok_client_key:
            raise _err(PlatformErrorKind.VALIDATION, "TikTok channel not configured")
        params = {
            "client_key": settings.tiktok_client_key,
            "response_type": "code",
            "scope": ",".join(_SCOPES),
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    @normalize_network_errors
    async def exchange_code(
        self, *, code: str, redirect_uri: str
    ) -> ChannelAccountPayload:
        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._token_request(
                client,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            credentials = {
                "access_token": token["access_token"],
                "refresh_token": token.get("refresh_token"),
            }
            profile = await self._fetch_profile(client, credentials)
            open_id = token.get("open_id") or profile.get("open_id", "")
            return ChannelAccountPayload(
                platform_user_id=open_id,
                display_name=profile.get("display_name", ""),
                avatar_url=profile.get("avatar_url"),
                scopes=_SCOPES,
                credentials=credentials,
                token_expires_at=datetime.now(UTC)
                + timedelta(seconds=int(token.get("expires_in", 86400))),
            )

    @normalize_network_errors
    async def refresh(self, credentials: dict[str, Any]) -> ChannelAccountPayload:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise _err(PlatformErrorKind.TOKEN, "tiktok: no refresh token stored")
        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._token_request(
                client,
                {"grant_type": "refresh_token", "refresh_token": refresh_token},
            )
            new_credentials = {
                "access_token": token["access_token"],
                "refresh_token": token.get("refresh_token") or refresh_token,
            }
            profile = await self._fetch_profile(client, new_credentials)
            return ChannelAccountPayload(
                platform_user_id=token.get("open_id") or profile.get("open_id", ""),
                display_name=profile.get("display_name", ""),
                avatar_url=profile.get("avatar_url"),
                scopes=_SCOPES,
                credentials=new_credentials,
                token_expires_at=datetime.now(UTC)
                + timedelta(seconds=int(token.get("expires_in", 86400))),
            )

    async def _token_request(
        self, client: httpx.AsyncClient, extra: dict[str, str]
    ) -> dict[str, Any]:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                **extra,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _check(resp, "tiktok token")
        return _check_biz(resp.json(), "tiktok token")

    async def _fetch_profile(
        self, client: httpx.AsyncClient, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        resp = await client.get(
            f"{_API}/user/info/",
            params={"fields": "open_id,display_name,avatar_url"},
            headers=_bearer(credentials),
        )
        _check(resp, "tiktok user info")
        data = _check_biz(resp.json(), "tiktok user info")
        return data.get("data", {}).get("user", {})

    # ── Publishing ───────────────────────────────────────────────────────

    @normalize_network_errors
    async def begin_publish(
        self, credentials: dict[str, Any], payload: dict[str, Any]
    ) -> JobHandle:
        media = payload.get("media") or {}
        video_url = media.get("video")
        if not video_url:
            raise _err(
                PlatformErrorKind.VALIDATION,
                "tiktok: only video outputs are publishable (clips)",
            )
        async with httpx.AsyncClient(timeout=60) as client:
            creator = await self._query_creator_info(client, credentials)
            max_duration = creator.get("max_video_post_duration_sec")
            duration = payload.get("duration_sec")
            if max_duration and duration and duration > max_duration:
                raise _err(
                    PlatformErrorKind.VALIDATION,
                    f"tiktok: video {duration}s exceeds creator limit {max_duration}s",
                )
            # §4: use the creator's actual privacy options — unaudited apps
            # may only post SELF_ONLY until the app review completes.
            options = creator.get("privacy_level_options") or []
            privacy = next(
                (p for p in ("PUBLIC_TO_EVERYONE", "SELF_ONLY") if p in options),
                None,
            )
            if privacy is None:
                raise _err(
                    PlatformErrorKind.VALIDATION,
                    f"tiktok: no usable privacy level (options={options})",
                )

            title = payload.get("caption") or payload.get("title") or ""
            hashtags = payload.get("hashtags") or []
            if hashtags:
                tags = " ".join(
                    f"#{t.lstrip('#').replace(' ', '')}"
                    for t in hashtags
                    if str(t).strip()
                )
                title = f"{title} {tags}".strip()
            resp = await client.post(
                f"{_API}/post/publish/video/init/",
                headers=_bearer(credentials),
                json={
                    "post_info": {
                        "title": title[:2200],
                        "privacy_level": privacy,
                        # ADR-026 disclosure rides the publish dialog UI only:
                        # no official API field is confirmed yet (§14 开放问题 1)
                        # — do not send unverified fields.
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": video_url,
                    },
                },
            )
            _check(resp, "tiktok publish init")
            data = _check_biz(resp.json(), "tiktok publish init")
            publish_id = data.get("data", {}).get("publish_id")
            if not publish_id:
                raise _err(
                    PlatformErrorKind.UNKNOWN, "tiktok: publish_id missing in init"
                )
            return JobHandle(job_id=publish_id)

    @normalize_network_errors
    async def await_publish(
        self, credentials: dict[str, Any], job: JobHandle, payload: dict[str, Any]
    ) -> PublishResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_API}/post/publish/status/fetch/",
                headers=_bearer(credentials),
                json={"publish_id": job.job_id},
            )
            _check(resp, "tiktok publish status")
            data = _check_biz(resp.json(), "tiktok publish status")
            inner = data.get("data", {})
            status_value = inner.get("status")
            if status_value == "PUBLISH_COMPLETE":
                # TikTok does not hand back a canonical post URL here; the
                # share id is the best available anchor.
                post_id = inner.get("share_id") or job.job_id
                return PublishResult(status="published", post_id=post_id, raw=inner)
            if status_value == "FAILED":
                reason = inner.get("fail_reason", "unknown")
                raise _err(
                    PlatformErrorKind.CONTENT_POLICY,
                    f"tiktok publish failed: {reason}",
                )
            # PROCESSING_DOWNLOAD / PROCESSING / SEND_TO_USER_INBOX → keep polling
            return PublishResult(status="pending", raw=inner)

    async def _query_creator_info(
        self, client: httpx.AsyncClient, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        resp = await client.post(
            f"{_API}/post/publish/creator_info/query/",
            headers=_bearer(credentials),
        )
        _check(resp, "tiktok creator info")
        data = _check_biz(resp.json(), "tiktok creator info")
        return data.get("data", {})
