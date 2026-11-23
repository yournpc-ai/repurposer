"""Deterministic SFX synthesis via @repurposer/sound-engine on the render service.

Zero new SQL tables: stores synthesized 48 kHz stereo PCM16 WAV as a fixed project
SourceSnapshot with typed versioned `SoundRecipeOrigin` in `meta["origin"]`,
reusing existing audio analysis and single-flight deduplication per
`(owner_id, project_id, spec_sha256)`.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from sqlalchemy import select

from app.config import settings
from app.editing.catalog import build_sound_spec, sound_spec_digest
from app.editing.sources import register_snapshot
from app.editing.timing import SOURCE_TIMEBASE, quantize_ticks
from app.models.database import AsyncSessionLocal
from app.models.ids import source_snapshot_id
from app.models.tables import SourceSnapshot
from app.tools.video.media_analysis import (
    AUDIO_ANALYZER_SET_VERSION,
    analyze_audio_bytes,
    store_media_analysis,
)
from app.tools.video.preparation import store_source_bytes

_IN_FLIGHT_SFX: dict[tuple[UUID, UUID, str], asyncio.Task[dict[str, Any]]] = {}


class SfxSynthesisError(ValueError):
    pass


async def _find_cached_sfx(
    owner_id: UUID, project_id: UUID, spec_sha256: str
) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        rows = list(
            await db.scalars(
                select(SourceSnapshot)
                .where(
                    SourceSnapshot.owner_id == owner_id,
                    SourceSnapshot.origin_project_id == project_id,
                    SourceSnapshot.kind == "audio",
                    SourceSnapshot.meta["origin"]["kind"].astext == "sound_recipe",
                    SourceSnapshot.meta["origin"]["spec_sha256"].astext == spec_sha256,
                )
                .order_by(SourceSnapshot.captured_at.desc())
                .limit(1)
            )
        )
    if not rows:
        return None
    snap = rows[0]
    meta = snap.meta or {}
    origin = meta.get("origin") or {}
    analysis_ref = meta.get("analysis_ref")
    if not isinstance(analysis_ref, dict) or not analysis_ref:
        return None
    acoustics = origin.get("acoustics") or {}
    return {
        "snapshot": {"snapshot_id": str(snap.id), "digest": snap.digest},
        "audio_snapshot_id": str(snap.id),
        "audio_digest": snap.digest,
        "analysis_ref": analysis_ref,
        "duration_seconds": (acoustics.get("duration_ms") or 0) / 1000.0
        or (snap.duration_ticks / SOURCE_TIMEBASE if snap.duration_ticks else 0.0),
        "sound_recipe": origin,
        "acoustics": acoustics,
        "cache_hit": True,
    }


async def _call_render_synthesize_sfx(spec: dict[str, Any]) -> dict[str, Any]:
    endpoint = settings.render_url.removesuffix("/render") + "/synthesize-sfx"
    payload = {
        "recipe_id": spec["recipe_id"],
        "params": spec["params"],
        "seed": spec["seed"],
    }
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            resp = await client.post(endpoint, json=payload)
    except Exception as exc:  # noqa: BLE001
        raise SfxSynthesisError(f"SFX render service unreachable: {exc}") from exc
    if resp.status_code != 200:
        detail = resp.text[:400]
        try:
            detail = resp.json().get("error") or detail
        except Exception:  # noqa: BLE001
            pass
        raise SfxSynthesisError(f"SFX synthesis failed: {detail}")
    return resp.json()


async def _synthesize_and_persist(
    *,
    owner_id: UUID,
    project_id: UUID,
    spec: dict[str, Any],
    spec_sha256: str,
) -> dict[str, Any]:
    cached = await _find_cached_sfx(owner_id, project_id, spec_sha256)
    if cached is not None:
        return cached

    rendered = await _call_render_synthesize_sfx(spec)
    if rendered.get("spec_sha256") != spec_sha256:
        raise SfxSynthesisError("SFX synthesis spec digest mismatch between API and render engine.")
    wav_bytes = base64.b64decode(rendered["wav_base64"])
    wav_digest = hashlib.sha256(wav_bytes).hexdigest()
    if rendered.get("wav_sha256") != wav_digest:
        raise SfxSynthesisError("Synthesized WAV checksum mismatch.")

    identity = uuid5(
        NAMESPACE_URL,
        f"sound-recipe-v1:{owner_id}:{project_id}:{spec_sha256}:{AUDIO_ANALYZER_SET_VERSION}",
    )
    snapshot_id = source_snapshot_id(owner_id, identity, "audio", wav_digest)

    report = await asyncio.to_thread(
        analyze_audio_bytes,
        wav_bytes,
        snapshot_id=str(snapshot_id),
        source_digest=wav_digest,
    )
    if not report.media_facts["decode"]["fully_decoded"]:
        raise SfxSynthesisError("Synthesized SFX WAV failed decode verification.")
    analysis_ref = await store_media_analysis(report)
    storage_key, stored_digest = await store_source_bytes(wav_bytes, ".wav", "audio/wav")
    if stored_digest != wav_digest:
        raise SfxSynthesisError("Stored WAV digest mismatch.")

    duration_ticks = quantize_ticks(
        Fraction(
            report.media_facts["decode"]["sample_count"],
            report.media_facts["sample_rate"],
        )
        * SOURCE_TIMEBASE
    )
    acoustics = rendered["acoustics"]
    origin = {
        "schema_version": 1,
        "kind": "sound_recipe",
        "engine": spec["engine"],
        "engine_version": spec["engine_version"],
        "recipe_id": spec["recipe_id"],
        "recipe_version": spec["recipe_version"],
        "params": spec["params"],
        "seed": spec["seed"],
        "spec_sha256": spec_sha256,
        "wav_digest": wav_digest,
        "acoustics": acoustics,
    }
    meta = {
        "origin": origin,
        "analysis_ref": analysis_ref,
        "media": {
            "content_type": "audio/wav",
            "sample_rate": report.media_facts["sample_rate"],
            "channels": report.media_facts["channels"],
            "duration_seconds": report.media_facts["decode"]["duration_seconds"],
        },
    }
    async with AsyncSessionLocal() as db:
        snapshot = await register_snapshot(
            db,
            owner_id=owner_id,
            asset=None,
            identity=identity,
            origin_project_id=project_id,
            kind="audio",
            storage_key=storage_key,
            digest=wav_digest,
            duration_ticks=duration_ticks,
            captured_at=datetime.now(UTC),
            meta=meta,
        )
        await db.commit()

    return {
        "snapshot": {"snapshot_id": str(snapshot.id), "digest": snapshot.digest},
        "audio_snapshot_id": str(snapshot.id),
        "audio_digest": snapshot.digest,
        "analysis_ref": analysis_ref,
        "duration_seconds": report.media_facts["decode"]["duration_seconds"],
        "sound_recipe": origin,
        "acoustics": acoustics,
        "cache_hit": False,
    }


async def synthesize_project_sfx(
    *,
    owner_id: UUID,
    project_id: UUID,
    recipe_id: str,
    params: dict[str, Any] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Single-flight deduplicated SFX synthesis for (owner_id, project_id, spec_sha256)."""
    spec = build_sound_spec(recipe_id, params=params, seed=seed)
    spec_sha256 = sound_spec_digest(spec)
    key = (owner_id, project_id, spec_sha256)

    task = _IN_FLIGHT_SFX.get(key)
    is_owner = False
    if task is None or task.done():
        task = asyncio.create_task(
            _synthesize_and_persist(
                owner_id=owner_id,
                project_id=project_id,
                spec=spec,
                spec_sha256=spec_sha256,
            )
        )
        _IN_FLIGHT_SFX[key] = task
        is_owner = True

    try:
        result = await asyncio.shield(task)
    finally:
        if is_owner and _IN_FLIGHT_SFX.get(key) is task:
            _IN_FLIGHT_SFX.pop(key, None)

    return dict(result)
