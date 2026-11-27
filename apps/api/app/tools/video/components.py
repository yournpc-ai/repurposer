"""Controlled remotion-project previews and fixed Generator media.

The CompositionVersion owns an immutable multi-file project, typed props and
fixed resource identities. A separate upstream bake service turns that exact
source + dependency lock into MP4/PNG bytes; this module fixes those bytes in
content-addressed storage. The final video-spec consumes only ordinary media.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

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
# Keep in sync with the runner contract. Its 64 MiB HTTP body budget carries
# the 32 MiB aggregate after roughly 4/3 base64 expansion plus project source.
_MAX_RESOURCE_BYTES = 16 * 1024 * 1024
_MAX_TOTAL_RESOURCE_BYTES = 32 * 1024 * 1024


class ComponentError(ValueError):
    """A bounded validation/bake diagnostic safe to return to Chat."""

    def __init__(
        self,
        message: str,
        *,
        source_repairable: bool = False,
        clip_id: str | None = None,
        program_digest: str | None = None,
    ) -> None:
        super().__init__(message)
        self.source_repairable = source_repairable
        self.clip_id = clip_id
        self.program_digest = program_digest

    def at_clip(self, clip: Clip, obj: GeneratorObject) -> ComponentError:
        if self.clip_id is not None:
            return self
        return ComponentError(
            f"clip {clip.clip_id}: {self}",
            source_repairable=self.source_repairable,
            clip_id=clip.clip_id,
            program_digest=obj.program_digest(),
        )


# Product capability baseline: controlled component baking is part of the
# product capability surface (gated at runtime by runner health/isolation
# verification in ``assert_component_bake_available`` rather than an env flag).
_COMPONENT_BAKE_SUPPORTED = True


def component_bake_supported() -> bool:
    """Single domain capability seat for controlled remotion-project TSX baking."""
    return _COMPONENT_BAKE_SUPPORTED


def assert_component_bake_enabled() -> None:
    """Fail closed before design, cache reuse, or any indirect public bake."""
    if not component_bake_supported():
        raise ComponentError(
            "remotion-project bake is disabled because this deployment has no "
            "verified isolated component runner"
        )


async def assert_component_bake_available() -> None:
    """Require both API opt-in and the render runner's measured isolation."""
    assert_component_bake_enabled()
    health_url = _bake_url()[:-len("/component-bake")] + "/health"
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(health_url)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ComponentError(
            f"remotion-project runner health could not be verified: {exc}"
        ) from exc
    capability = payload.get("component_bake") if isinstance(payload, dict) else None
    if (
        response.status_code != 200
        or not isinstance(capability, dict)
        or capability.get("enabled") is not True
        or capability.get("isolation") in {None, "disabled"}
    ):
        raise ComponentError(
            "remotion-project is unavailable: the render service reports no active isolated component runner"
        )


def component_manifest_key(program_digest: str) -> str:
    return f"{_MANIFEST_PREFIX}/{program_digest}.json"


def _bake_url() -> str:
    parts = urlsplit(settings.render_url)
    path = parts.path
    if not path.endswith("/render"):
        raise ComponentError("remotion-project needs the existing /render service URL")
    return urlunsplit(
        (parts.scheme, parts.netloc, path[: -len("/render")] + "/component-bake", "", "")
    )


def _source_facts(obj: GeneratorObject) -> dict[str, Any]:
    if obj.project is None:
        return {"files": [], "resources": []}
    return {
        "entry": obj.project.entry,
        "composition_id": obj.project.composition_id,
        "files": [
            {"path": item.path, "digest": item.digest} for item in obj.project.files
        ],
        "props_schema": obj.project.props_schema,
        "resources": [
            {
                "path": item.path,
                "digest": item.snapshot_digest,
                "content_type": item.content_type,
            }
            for item in obj.project.resources
        ],
    }


def _validate_cached_manifest(value: Any, obj: GeneratorObject) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("program_digest") != obj.program_digest():
        raise ComponentError("cached component manifest does not match the requested source")
    if (
        value.get("producer") != obj.producer
        or value.get("dependencies") != COMPONENT_DEPENDENCIES
        or value.get("output") != obj.output.model_dump(mode="json")
    ):
        raise ComponentError("cached component producer/dependency/output identity mismatch")
    if obj.project is not None and value.get("source") != _source_facts(obj):
        raise ComponentError("cached component project/resource identity mismatch")
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


async def _fixed_resources(
    obj: GeneratorObject, snapshots: dict[UUID, dict[str, Any]] | None
) -> list[dict[str, Any]]:
    if obj.project is None:
        return []
    snapshots = snapshots or {}
    rows: list[dict[str, Any]] = []
    total = 0
    for resource in obj.project.resources:
        facts = snapshots.get(resource.snapshot_id)
        if (
            facts is None
            or facts.get("kind") != "image"
            or facts.get("digest") != resource.snapshot_digest
            or not isinstance(facts.get("storage_key"), str)
        ):
            raise ComponentError(f"component resource {resource.path!r} lacks its exact image snapshot")
        data = await storage.read(facts["storage_key"])
        if hashlib.sha256(data).hexdigest() != resource.snapshot_digest:
            raise ComponentError(f"component resource {resource.path!r} bytes differ from its digest")
        total += len(data)
        if not data or len(data) > _MAX_RESOURCE_BYTES or total > _MAX_TOTAL_RESOURCE_BYTES:
            raise ComponentError("component fixed resources exceed their byte budget")
        rows.append({
            "path": resource.path,
            "digest": resource.snapshot_digest,
            "content_type": resource.content_type,
            "data_base64": base64.b64encode(data).decode("ascii"),
        })
    return rows


async def _bake(
    obj: GeneratorObject, *, snapshots: dict[UUID, dict[str, Any]] | None
) -> tuple[bytes, bytes, dict[str, Any]]:
    output = obj.output
    if not isinstance(output, ProgramOutput):
        raise ComponentError("remotion-project needs raster output constraints")
    request: dict[str, Any] = {
        "producer": obj.producer,
        "program_digest": obj.program_digest(),
        "dependencies": COMPONENT_DEPENDENCIES,
        "parameters": obj.parameters,
        "output": output.model_dump(mode="json"),
    }
    if obj.project is not None:
        resources = await _fixed_resources(obj, snapshots)
        request["project"] = {
            "schema_version": obj.project.schema_version,
            "entry": obj.project.entry,
            "composition_id": obj.project.composition_id,
            "files": [item.model_dump(mode="json") for item in obj.project.files],
            "props": obj.project.props,
            "props_schema": obj.project.props_schema,
        }
        request["resources"] = resources
    else:
        # Read compatibility for historical immutable single-component versions.
        request["code"] = obj.code
        request["resources"] = []
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
        repairable = (
            response.status_code in {400, 422}
            and (
                payload.get("code") == "INVALID_COMPONENT_REQUEST"
                or payload.get("source_repairable") is True
            )
        )
        raise ComponentError(
            f"component bake failed: {detail}", source_repairable=repairable
        )
    if (
        payload.get("program_digest") != obj.program_digest()
        or payload.get("producer") != obj.producer
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
    snapshots: dict[UUID, dict[str, Any]] | None = None,
    on_reuse: Callable[[bool], None] | None = None,
) -> dict[str, Any]:
    """Reuse or bake the exact project; return its fixed execution facts."""
    assert_component_bake_enabled()
    obj = clip.object
    if not isinstance(obj, GeneratorObject) or obj.producer != "remotion-project":
        raise ComponentError(f"clip {clip.clip_id} is not a remotion-project GeneratorObject")
    cached = await _cached_manifest(obj, verify_media=True)
    if cached is not None:
        if on_reuse is not None:
            on_reuse(True)
        return {**cached, "clip_id": clip.clip_id, "object_id": obj.object_id}

    try:
        video, preview, diagnostics = await _bake(obj, snapshots=snapshots)
    except ComponentError as exc:
        raise exc.at_clip(clip, obj) from exc
    media_key, media_digest = await store_source_bytes(video, ".mp4", "video/mp4")
    preview_key, preview_digest = await store_source_bytes(preview, ".png", "image/png")
    manifest = {
        "schema_version": 1,
        "producer": obj.producer,
        "program_digest": obj.program_digest(),
        "dependencies": COMPONENT_DEPENDENCIES,
        "source": _source_facts(obj),
        "resources": _source_facts(obj)["resources"],
        "output": obj.output.model_dump(mode="json"),
        "media": {"storage_key": media_key, "digest": media_digest},
        "preview_frame": {"storage_key": preview_key, "digest": preview_digest},
        "diagnostics": diagnostics,
    }
    key = component_manifest_key(obj.program_digest())
    if await storage.exists(key):
        cached = await _cached_manifest(obj, verify_media=True)
        assert cached is not None
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
