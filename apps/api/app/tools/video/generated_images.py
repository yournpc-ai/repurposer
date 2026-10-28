"""MiniMax image-01 production for image-v1 GeneratorObjects.

The CompositionVersion owns only the reviewable request. An authorized Run
writes a submitted marker before one non-idempotent provider POST, then meters
and pins returned bytes in a fixed execution manifest. A recovery that finds
only the marker fails closed instead of replaying an unconfirmed request.
Normal fixed-media retries reuse the cache; explicit regeneration uses its own
Run-scoped manifest.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
from typing import Any
from uuid import UUID

from PIL import Image

from app.editing.schemas import Clip, GeneratedImageOutput, GeneratorObject
from app.metering import record_media_usage
from app.providers import storage
from app.providers.llm.minimax import minimax_client
from app.tools.video.preparation import store_source_bytes

_MANIFEST_PREFIX = "video-generated-images"


class GeneratedImageError(ValueError):
    """A bounded generation or fixed-media diagnostic safe to return to Chat."""


class GeneratedImageOutcomeUnknown(GeneratedImageError):
    """A prior request may have executed, but no fixed result can be proven."""

    user_key = "provider_image_outcome_unknown"


def _image_object(clip: Clip) -> GeneratorObject:
    obj = clip.object
    if not isinstance(obj, GeneratorObject) or obj.runtime != "image-v1":
        raise GeneratedImageError(f"clip {clip.clip_id} is not an image-v1 GeneratorObject")
    if not isinstance(obj.output, GeneratedImageOutput):
        raise GeneratedImageError(f"clip {clip.clip_id} lacks generated-image output constraints")
    return obj


def _request(obj: GeneratorObject) -> dict[str, Any]:
    return {
        "prompt": obj.prompt,
        "provider": obj.provider,
        "model": obj.model,
        "parameters": obj.parameters,
        "output": obj.output.model_dump(mode="json"),
    }


def _manifest_key(obj: GeneratorObject, execution_id: str | None, regenerate: bool) -> str:
    base = f"{_MANIFEST_PREFIX}/{obj.program_digest()}"
    if not regenerate:
        return f"{base}.json"
    if execution_id is None:
        raise GeneratedImageError("explicit image regeneration needs a Run execution identity")
    return f"{base}/executions/{UUID(execution_id)}.json"


def _composition_key(obj: GeneratorObject, composition_id: str | None) -> str | None:
    if composition_id is None:
        return None
    return (
        f"{_MANIFEST_PREFIX}/compositions/{UUID(composition_id)}/"
        f"{obj.object_id}.json"
    )


def _validate_manifest(value: Any, obj: GeneratorObject) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("program_digest") != obj.program_digest():
        raise GeneratedImageError("fixed image manifest does not match the requested source")
    if value.get("request") != _request(obj):
        raise GeneratedImageError("fixed image manifest request identity mismatch")
    if value.get("state") == "submitted":
        raise GeneratedImageOutcomeUnknown(
            "An earlier image request may have executed, but no fixed result is available; "
            "automatic recovery will not submit it again"
        )
    media = value.get("media") or {}
    if not media.get("storage_key") or len(str(media.get("digest") or "")) != 64:
        raise GeneratedImageError("fixed image manifest lacks immutable media")
    return value


async def _cached_manifest(
    obj: GeneratorObject,
    key: str,
    *,
    stale_source_is_missing: bool = False,
) -> dict[str, Any] | None:
    if not await storage.exists(key):
        return None
    try:
        value = json.loads(await storage.read(key))
    except (ValueError, json.JSONDecodeError) as exc:
        raise GeneratedImageError(f"fixed image manifest is unreadable: {exc}") from exc
    if stale_source_is_missing and (
        not isinstance(value, dict) or value.get("program_digest") != obj.program_digest()
    ):
        return None
    manifest = _validate_manifest(value, obj)
    media = manifest["media"]
    data = await storage.read(media["storage_key"])
    if hashlib.sha256(data).hexdigest() != media["digest"]:
        raise GeneratedImageError("fixed image bytes do not match their manifest digest")
    return manifest


async def has_fixed_generated_image(clip: Clip, *, composition_id: str | None = None) -> bool:
    """Quote one missing image without generating it or mutating any state."""
    obj = _image_object(clip)
    pointer = _composition_key(obj, composition_id)
    if pointer is not None:
        current = await _cached_manifest(obj, pointer, stale_source_is_missing=True)
        if current is not None:
            return True
    return await _cached_manifest(obj, _manifest_key(obj, None, False)) is not None


def _decode_image(encoded: str) -> tuple[bytes, int, int, str, str]:
    try:
        data = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            image_format = image.format
            image.verify()
    except (binascii.Error, OSError, ValueError) as exc:
        raise GeneratedImageError(f"MiniMax returned invalid image bytes: {exc}") from exc
    suffix, mime_type = {
        "PNG": (".png", "image/png"),
        "JPEG": (".jpg", "image/jpeg"),
        "WEBP": (".webp", "image/webp"),
    }.get(image_format or "", (None, None))
    if suffix is None or mime_type is None:
        raise GeneratedImageError(f"unsupported generated image format {image_format!r}")
    return data, width, height, suffix, mime_type


async def _save_manifest(key: str, manifest: dict[str, Any]) -> None:
    await storage.save(
        key,
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        content_type="application/json",
    )


async def ensure_generated_image_clip(
    clip: Clip,
    *,
    execution_id: str | None,
    composition_id: str | None = None,
    regenerate: bool = False,
) -> dict[str, Any]:
    """Return exact fixed image facts, generating only on an authorized miss."""
    obj = _image_object(clip)
    key = _manifest_key(obj, execution_id, regenerate)
    pointer = _composition_key(obj, composition_id)
    cached = None
    if pointer is not None and not regenerate:
        cached = await _cached_manifest(obj, pointer, stale_source_is_missing=True)
    if cached is None:
        cached = await _cached_manifest(obj, key)
    if cached is not None:
        if pointer is not None:
            await _save_manifest(pointer, cached)
        return {**cached, "clip_id": clip.clip_id, "object_id": obj.object_id}

    # Persist the possibility of submission before the non-idempotent POST.
    # A crash or timeout can leave no fixed media; recovery must not replay it.
    await _save_manifest(key, {
        "schema_version": 1,
        "state": "submitted",
        "runtime": obj.runtime,
        "program_digest": obj.program_digest(),
        "request": _request(obj),
        "execution_id": execution_id,
        "regenerated": regenerate,
    })
    images = await minimax_client.generate_image(
        prompt=obj.prompt or "",
        aspect_ratio=obj.output.aspect_ratio,
        response_format="base64",
    )
    if not images:
        raise GeneratedImageError("MiniMax image-01 returned no image")
    await record_media_usage({"images": float(len(images))})
    if len(images) != 1:
        raise GeneratedImageError("MiniMax image-01 returned more than the requested single image")
    data, width, height, suffix, mime_type = _decode_image(images[0])
    media_key, media_digest = await store_source_bytes(data, suffix, mime_type)
    manifest = {
        "schema_version": 1,
        "runtime": obj.runtime,
        "program_digest": obj.program_digest(),
        "request": _request(obj),
        "provider_request": {
            "model": "image-01",
            "prompt": obj.prompt,
            "aspect_ratio": obj.output.aspect_ratio,
            "n": 1,
            "response_format": "base64",
        },
        "execution_id": execution_id,
        "regenerated": regenerate,
        "media": {
            "kind": "image",
            "storage_key": media_key,
            "digest": media_digest,
            "width": width,
            "height": height,
            "mime_type": mime_type,
        },
        "usage": {"images": 1},
    }
    existing = json.loads(await storage.read(key)) if await storage.exists(key) else None
    if isinstance(existing, dict) and existing.get("state") == "submitted":
        # This is the submission marker written above (or a racing attempt whose
        # successful bytes can now close the unknown window). Fixed media wins.
        await _save_manifest(key, manifest)
        cached = manifest
    elif existing is not None:
        # A concurrent producer may have fixed the same request first. Its media
        # wins for subsequent retries; this call's actual usage remains metered.
        cached = _validate_manifest(existing, obj)
    else:
        await _save_manifest(key, manifest)
        cached = manifest
    if pointer is not None:
        # The current work reuses its latest fixed generation after native edits;
        # another Composition's regeneration cannot move this pointer.
        await _save_manifest(pointer, cached)
    return {**cached, "clip_id": clip.clip_id, "object_id": obj.object_id}
