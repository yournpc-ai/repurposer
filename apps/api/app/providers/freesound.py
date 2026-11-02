"""Bounded Freesound API access for CC0 sound-effect candidates."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings

_API_ROOT = "https://freesound.org/apiv2"
_CC0_URLS = {
    "http://creativecommons.org/publicdomain/zero/1.0",
    "https://creativecommons.org/publicdomain/zero/1.0",
}
_FIELDS = "id,name,username,duration,license,url,previews"
_MAX_JSON_BYTES = 1024 * 1024
_MAX_AUDIO_BYTES = 16 * 1024 * 1024
_MAX_REDIRECTS = 3
_TIMEOUT = httpx.Timeout(20.0, connect=8.0)


class FreesoundError(RuntimeError):
    """The provider cannot supply a verified CC0 MP3 candidate."""


@dataclass(frozen=True)
class FreesoundSound:
    provider_id: str
    title: str
    author: str
    duration_seconds: float
    source_url: str
    preview_url: str
    license: str
    attribution: str


def _allowed_https_url(value: Any, *, mp3: bool = False) -> str:
    if not isinstance(value, str):
        raise FreesoundError("Freesound returned a missing media URL")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or (host != "freesound.org" and not host.endswith(".freesound.org"))
        or parsed.username
        or parsed.password
    ):
        raise FreesoundError("Freesound returned an untrusted media URL")
    if mp3 and not parsed.path.lower().endswith(".mp3"):
        raise FreesoundError("the Freesound preview is not an MP3 URL")
    return value


def validate_mp3_preview_url(value: Any) -> str:
    return _allowed_https_url(value, mp3=True)


def _sound_from_payload(payload: Any) -> FreesoundSound:
    if not isinstance(payload, dict):
        raise FreesoundError("Freesound returned a malformed sound")
    provider_id = str(payload.get("id") or "")
    if not provider_id.isdigit():
        raise FreesoundError("Freesound returned an invalid sound id")
    license_url = str(payload.get("license") or "").rstrip("/").lower()
    if license_url not in _CC0_URLS:
        raise FreesoundError(f"Freesound sound {provider_id} is no longer CC0")
    title = str(payload.get("name") or "").strip()
    author = str(payload.get("username") or "").strip()
    duration = payload.get("duration")
    if (
        not title
        or not author
        or not isinstance(duration, int | float)
        or not math.isfinite(float(duration))
        or float(duration) <= 0
    ):
        raise FreesoundError(f"Freesound sound {provider_id} has incomplete metadata")
    source_url = _allowed_https_url(payload.get("url"))
    previews = payload.get("previews") or {}
    preview_url = None
    for key in ("preview-hq-mp3", "preview-lq-mp3"):
        try:
            preview_url = validate_mp3_preview_url(previews.get(key))
            break
        except FreesoundError:
            continue
    if preview_url is None:
        raise FreesoundError(f"Freesound sound {provider_id} has no MP3 preview")
    return FreesoundSound(
        provider_id=provider_id,
        title=title,
        author=author,
        duration_seconds=float(duration),
        source_url=source_url,
        preview_url=preview_url,
        license="CC0",
        attribution=f'"{title}" by {author} on Freesound (CC0 1.0)',
    )


async def _download(
    url: str,
    *,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[bytes, str]:
    current = _allowed_https_url(url)
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=False,
            trust_env=True,
        ) as client:
            for redirect_count in range(_MAX_REDIRECTS + 1):
                async with client.stream("GET", current, headers=headers, params=params) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count >= _MAX_REDIRECTS:
                            raise FreesoundError("Freesound exceeded the redirect limit")
                        location = response.headers.get("location")
                        if not location:
                            raise FreesoundError("Freesound returned an empty redirect")
                        next_url = _allowed_https_url(urljoin(current, location))
                        if (urlparse(next_url).hostname or "").lower() != (
                            urlparse(current).hostname or ""
                        ).lower():
                            headers = None
                        current = next_url
                        continue
                    if response.status_code != 200:
                        raise FreesoundError(
                            f"Freesound request failed with HTTP {response.status_code}"
                        )
                    length = response.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise FreesoundError("Freesound response exceeds the size limit")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > max_bytes:
                            raise FreesoundError("Freesound response exceeds the size limit")
                    return bytes(data), response.headers.get("content-type", "")
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, FreesoundError):
            raise
        raise FreesoundError(f"Freesound request failed: {exc}") from exc
    raise FreesoundError("Freesound request did not complete")


async def _api_json(path: str, *, params: dict[str, Any]) -> Any:
    if not settings.freesound_api_key:
        raise FreesoundError("Freesound is not configured: FREESOUND_API_KEY is missing")
    import json

    data, content_type = await _download(
        f"{_API_ROOT}{path}",
        max_bytes=_MAX_JSON_BYTES,
        headers={"Authorization": f"Token {settings.freesound_api_key}"},
        params=params,
    )
    if content_type and "json" not in content_type.lower():
        raise FreesoundError("Freesound API returned a non-JSON response")
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FreesoundError("Freesound API returned malformed JSON") from exc


async def search_cc0_mp3(query: str, *, limit: int = 3) -> list[FreesoundSound]:
    """Search the official API, then independently verify every returned sound."""
    payload = await _api_json(
        "/search/text/",
        params={
            "query": query,
            "filter": 'license:"Creative Commons 0"',
            "fields": _FIELDS,
            "page_size": max(limit * 3, limit),
        },
    )
    sounds: list[FreesoundSound] = []
    for item in (payload.get("results") or []) if isinstance(payload, dict) else []:
        try:
            sounds.append(_sound_from_payload(item))
        except FreesoundError:
            continue
        if len(sounds) >= limit:
            break
    return sounds


async def get_cc0_mp3(provider_id: str) -> FreesoundSound:
    """Re-read a sound at import time so a license change fails closed."""
    if not provider_id.isdigit():
        raise FreesoundError("invalid Freesound sound id")
    payload = await _api_json(
        f"/sounds/{provider_id}/",
        params={"fields": _FIELDS},
    )
    return _sound_from_payload(payload)


async def download_mp3_preview(sound: FreesoundSound) -> bytes:
    """Download only the provider-declared MP3 preview, never an arbitrary URL."""
    if sound.license != "CC0":
        raise FreesoundError("only CC0 previews can be imported")
    preview_url = validate_mp3_preview_url(sound.preview_url)
    data, content_type = await _download(
        preview_url,
        max_bytes=_MAX_AUDIO_BYTES,
    )
    if content_type and not (
        content_type.lower().startswith("audio/mpeg")
        or content_type.lower().startswith("application/octet-stream")
    ):
        raise FreesoundError(f"Freesound preview is not served as MP3 ({content_type})")
    return data
