"""Controlled component-v1 previews and fixed Generator media.

The CompositionVersion owns immutable TSX and declared scalar parameters. A
separate upstream bake service turns the exact source + dependency lock into
MP4/PNG bytes; this module fixes those bytes in content-addressed storage.
The final video-spec consumes only the resulting ordinary muted video.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import settings
from app.editing.schemas import (
    COMPONENT_DEPENDENCIES,
    Clip,
    GeneratorObject,
    ProgramOutput,
)
from app.providers import storage
from app.tools.video.preparation import store_source_bytes

_MANIFEST_PREFIX = "video-components"
_MAX_MEDIA_BYTES = 24 * 1024 * 1024
_MAX_PREVIEW_BYTES = 4 * 1024 * 1024
_MAX_RESPONSE_BYTES = 40 * 1024 * 1024


class ComponentError(ValueError):
    """A bounded validation/bake diagnostic safe to return to Chat."""


def assert_component_bake_enabled() -> None:
    """Fail closed before design, cache reuse, or any indirect public bake.

    The current worker's source policy is diagnostic, not a sandbox. Only an
    explicitly isolated deployment may open this seam; the default refuses
    untrusted execution without claiming that static scanning made it safe.
    """
    if not settings.component_bake_enabled:
        raise ComponentError(
            "component-v1 bake is disabled because this deployment has no "
            "verified isolated component runner"
        )


def component_manifest_key(program_digest: str) -> str:
    return f"{_MANIFEST_PREFIX}/{program_digest}.json"


def _bake_url() -> str:
    parts = urlsplit(settings.render_url)
    path = parts.path
    if not path.endswith("/render"):
        raise ComponentError("component-v1 needs the existing /render service URL")
    return urlunsplit(
        (parts.scheme, parts.netloc, path[: -len("/render")] + "/component-bake", "", "")
    )


def _validate_cached_manifest(value: Any, obj: GeneratorObject) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("program_digest") != obj.program_digest():
        raise ComponentError("cached component manifest does not match the requested source")
    if (
        value.get("runtime") != obj.runtime
        or value.get("dependencies") != COMPONENT_DEPENDENCIES
        or value.get("output") != obj.output.model_dump(mode="json")
    ):
        raise ComponentError("cached component runtime/dependency/output identity mismatch")
    media = value.get("media") or {}
    preview = value.get("preview_frame") or {}
    if not media.get("storage_key") or len(str(media.get("digest") or "")) != 64:
        raise ComponentError("cached component manifest lacks fixed media")
    if not preview.get("storage_key") or len(str(preview.get("digest") or "")) != 64:
        raise ComponentError("cached component manifest lacks its representative frame")
    return value


async def _cached_manifest(obj: GeneratorObject, *, verify_media: bool) -> dict[str, Any] | None:
    key = component_manifest_key(obj.program_digest())
    if not await storage.exists(key):
        return None
    try:
        value = json.loads(await storage.read(key))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ComponentError(f"cached component manifest is unreadable: {exc}") from exc
    manifest = _validate_cached_manifest(value, obj)
    if verify_media:
        for field in ("media", "preview_frame"):
            media = manifest[field]
            data = await storage.read(media["storage_key"])
            if hashlib.sha256(data).hexdigest() != media["digest"]:
                raise ComponentError(f"cached component {field} does not match its fixed digest")
    return manifest


def _decode_artifact(value: Any, *, kind: str, cap: int) -> bytes:
    if not isinstance(value, str):
        raise ComponentError(f"component bake returned no {kind} bytes")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ComponentError(f"component bake returned malformed {kind} bytes") from exc
    if not data or len(data) > cap:
        raise ComponentError(f"component {kind} exceeds its {cap}-byte output budget")
    if kind == "video" and (len(data) < 12 or data[4:8] != b"ftyp"):
        raise ComponentError("component bake did not return an MP4")
    if kind == "preview" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ComponentError("component bake did not return a PNG preview")
    return data


async def _bake(obj: GeneratorObject) -> tuple[bytes, bytes, dict[str, Any]]:
    output = obj.output
    if not isinstance(output, ProgramOutput):
        raise ComponentError("component-v1 needs raster output constraints")
    request = {
        "runtime": obj.runtime,
        "program_digest": obj.program_digest(),
        "dependencies": COMPONENT_DEPENDENCIES,
        "code": obj.code,
        "parameters": obj.parameters,
        "output": output.model_dump(mode="json"),
    }
    timeout = min(float(settings.render_timeout_seconds), 300.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream("POST", _bake_url(), json=request) as response:
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > _MAX_RESPONSE_BYTES:
                        raise ComponentError("component bake response exceeded its byte budget")
                    chunks.append(chunk)
                body = b"".join(chunks)
    except ComponentError:
        raise
    except httpx.HTTPError as exc:
        raise ComponentError(f"component bake service failed: {exc}") from exc
    try:
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ComponentError("component bake returned a malformed response") from exc
    if not isinstance(payload, dict):
        raise ComponentError("component bake returned a non-object response")
    if response.status_code != 200:
        detail = str(payload.get("error") or "unknown bake error")[:4000]
        raise ComponentError(f"component bake failed: {detail}")
    if (
        payload.get("program_digest") != obj.program_digest()
        or payload.get("runtime") != obj.runtime
        or payload.get("dependencies") != COMPONENT_DEPENDENCIES
        or payload.get("output") != output.model_dump(mode="json")
    ):
        raise ComponentError("component bake response does not match the requested identity")
    video = _decode_artifact(payload.get("video_base64"), kind="video", cap=_MAX_MEDIA_BYTES)
    preview = _decode_artifact(
        payload.get("preview_base64"), kind="preview", cap=_MAX_PREVIEW_BYTES
    )
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raise ComponentError("component bake returned no execution diagnostics")
    return video, preview, diagnostics


async def ensure_component_clip(
    clip: Clip,
    *,
    on_reuse: Callable[[bool], None] | None = None,
) -> dict[str, Any]:
    """Reuse or bake the exact component; return its fixed execution facts."""
    assert_component_bake_enabled()
    obj = clip.object
    if not isinstance(obj, GeneratorObject) or obj.runtime != "component-v1":
        raise ComponentError(f"clip {clip.clip_id} is not a component-v1 GeneratorObject")
    cached = await _cached_manifest(obj, verify_media=True)
    if cached is not None:
        if on_reuse is not None:
            on_reuse(True)
        return {**cached, "clip_id": clip.clip_id, "object_id": obj.object_id}

    video, preview, diagnostics = await _bake(obj)
    media_key, media_digest = await store_source_bytes(video, ".mp4", "video/mp4")
    preview_key, preview_digest = await store_source_bytes(preview, ".png", "image/png")
    manifest = {
        "schema_version": 1,
        "runtime": obj.runtime,
        "program_digest": obj.program_digest(),
        "dependencies": COMPONENT_DEPENDENCIES,
        "resources": [],
        "output": obj.output.model_dump(mode="json"),
        "media": {"storage_key": media_key, "digest": media_digest},
        "preview_frame": {"storage_key": preview_key, "digest": preview_digest},
        "diagnostics": diagnostics,
    }
    key = component_manifest_key(obj.program_digest())
    if await storage.exists(key):
        cached = _validate_cached_manifest(json.loads(await storage.read(key)), obj)
        if on_reuse is not None:
            on_reuse(False)
        return {**cached, "clip_id": clip.clip_id, "object_id": obj.object_id}
    await storage.save(
        key,
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
        content_type="application/json",
    )
    if on_reuse is not None:
        on_reuse(False)
    return {**manifest, "clip_id": clip.clip_id, "object_id": obj.object_id}
