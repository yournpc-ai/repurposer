"""align_stills node (ADR-039 P1: runner relocated from pipeline/node_runners).

Materialize the estimated timeline onto the transcript asset (deterministic,
zero LLM/provider); idempotent by text hash — a re-run with unchanged
material reuses the timeline instead of rebuilding it.
"""

import hashlib
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AssetType
from app.models.tables import WorkflowStep, Project, WorkflowRun
from app.pipeline.step_context import _list_assets
from app.pipeline.step_display import _fill_summary, _set_spec_field
from app.skills.stills.procedure import cjk_ratio, estimate_words_timeline

logger = structlog.get_logger()


async def run_align_stills(
    db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
) -> list[UUID]:
    """Materialize the estimated timeline onto the transcript asset.

    Deterministic (zero LLM/provider); idempotent by text hash — a re-run
    with unchanged material reuses the timeline instead of rebuilding it.
    The aligned asset id rides ``spec.aligned_asset_id`` so the downstream
    clips node reads its render source off the DAG edge, not an asset scan.
    """
    assets = await _list_assets(db, project.id)
    candidates = [
        a for a in assets if a.type == AssetType.TRANSCRIPT and (a.extracted_text or "").strip()
    ]
    if not candidates:
        raise ValueError("No transcript to align")
    asset = max(candidates, key=lambda a: len(a.extracted_text or ""))
    text = asset.extracted_text or ""
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]

    meta = asset.meta or {}
    if meta.get("aligned_text_hash") == digest and meta.get("words"):
        words = meta["words"]
    else:
        words = estimate_words_timeline(text)
        if not words:
            raise ValueError("Transcript has no text to align")
        language = "zh" if cjk_ratio(text) > 0.2 else (project.language or "en")
        asset.meta = {
            **meta,
            "words": words,
            "language": language,
            "aligned_text_hash": digest,
            "alignment": "estimated",
        }
        asset.duration_seconds = int(float(words[-1]["end"]) + 0.999)
        await db.flush()
        logger.info(
            "stills_aligned",
            project_id=str(project.id),
            asset_id=str(asset.id),
            words=len(words),
        )

    await _set_spec_field(node.id, "aligned_asset_id", str(asset.id))
    await _fill_summary(
        node.id,
        "align_stills",
        n=len(words),
        total_seconds=int(float(words[-1]["end"])),
    )
    return []
