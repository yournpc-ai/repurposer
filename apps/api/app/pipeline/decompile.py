"""Decompiler — video → craft skeleton (ADR-078), pipeline internal crew.

判词①: the exemplar is a PROGRAMMABLE TEMPORAL STRUCTURE — remix = keep the
craft, swap the content (内容槽替换, 判词③). This node reverse-compiles one
pinned exemplar video into a ``CraftSkeleton`` output row (type
``craft_skeleton``, INTERNAL_OUTPUT_TYPES member — never user-visible as a
deliverable, readable by the plan + the trigger turn).

The two halves join here, never inside one another:

- **Deterministic layer** (``pipeline/craft_scan.py``): shots / rhythm /
  aspect / caption best-fit — zero LLM by construction (the pure suite
  source-scans it). Runs on CPU in a thread (the prosody family shape).
- **Judgment layer** (the ``decompile`` agent, CraftJudgment): music mood /
  hook device / capability gaps — the schema carries ONLY those seats, so
  the LLM structurally cannot write a deterministic field (验收断言).

Storage discipline = the understand row's (判词⑥ 双抽取分工): asset-level,
content-addressed (``source_ref.asset_hash`` = the asset's content_sha256),
cross-project reusable (same-user latest-row match — the upload-time warm
and later runs reference the one row, never copy it).

Degrade honesty (声明化兜底, never silent): an undecodable / missing
exemplar lands a ``noop`` step with an honest summary and NO skeleton row —
downstream exemplar-param mapping then finds nothing and falls to defaults
(the chain proceeds as a regular cut). An LLM-call failure lands the
skeleton with judgment seats None — the deterministic layer stays intact.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import decompile
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AssetStatus,
    AssetType,
    CraftJudgment,
    CraftRhythm,
    CraftShot,
    CraftCaptionScan,
    CraftSkeleton,
    MediaInput,
    MediaInputType,
    Point,
)
from app.models.tables import Asset, Music, Output, Project, WorkflowRun, WorkflowStep
from app.pipeline import craft_scan
from app.pipeline.graph import NodeBase, estimate_agent
from app.pipeline.node_runners import _display_zh
from app.pipeline.step_context import list_assets, _source_language
from app.pipeline.step_display import set_spec_field, set_summary
from app.pipeline.trigger_events import TRIGGER_CRAFT_DECOMPILED, fire_trigger
from app.providers.llm.base import LLMError

logger = structlog.get_logger(__name__)


def _skeleton_digest(asset: Asset) -> str | None:
    """The skeleton's content address: the asset's content_sha256 (stamped by
    the first processor). None = unhashable (legacy / failed processing) —
    reuse then falls back to the per-upload asset id (same-project only)."""
    digest = (asset.meta or {}).get("content_sha256")
    return str(digest) if digest else None


async def find_reusable_skeleton(
    db: AsyncSession, project: Project, asset: Asset
) -> Output | None:
    """The latest same-user skeleton row matching the exemplar's content hash
    (cross-project by design — the find_reusable_understanding precedent:
    content addressing makes any earlier materialization satisfy the reuse;
    the row is referenced, never copied). Without a hash, the per-upload
    asset id is the fallback identity (same-project only)."""
    digest = _skeleton_digest(asset)
    rows = (
        (
            await db.execute(
                select(Output)
                .join(Project, Output.project_id == Project.id)
                .where(
                    Project.user_id == project.user_id,
                    Output.type == "craft_skeleton",
                )
                .order_by(Output.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        ref = row.source_ref or {}
        if digest is not None:
            if ref.get("asset_hash") == digest:
                return row
        elif ref.get("asset_id") == str(asset.id):
            return row
    return None


async def _mood_catalog(db: AsyncSession) -> list[str]:
    """The mood enum the judgment may pick from: the platform default
    catalog's moods plus every library piece's mood (the unique natural
    key). The postprocess clamps to exactly this list — an unknown pick
    reads as None, never a free string reaching a spec."""
    from app.pipeline.music import DEFAULT_MUSIC_CATALOG

    moods: list[str] = [entry["mood"] for entry in DEFAULT_MUSIC_CATALOG]
    seen = set(moods)
    rows = (
        (await db.execute(select(Music.mood).where(Music.mood.isnot(None))))
        .scalars()
        .all()
    )
    for mood in rows:
        if mood not in seen:
            seen.add(mood)
            moods.append(mood)
    return moods


def _keyframe_media(frames: list[dict[str, Any]]) -> list[MediaInput]:
    """Shot-midpoint keyframes → the judgment call's visual evidence."""
    out: list[MediaInput] = []
    for frame in frames:
        data_url = "data:image/png;base64," + base64.b64encode(frame["png"]).decode("ascii")
        out.append(
            MediaInput(
                type=MediaInputType.IMAGE,
                mime="image/png",
                data_url=data_url,
                caption=f"Shot keyframe at {frame['t']}s",
            )
        )
    return out


def _skeleton_from_scan(scan: dict[str, Any], judgment: CraftJudgment) -> CraftSkeleton:
    """Join the two halves into the contract shape. The deterministic layer
    lands verbatim from the scan dict; the judgment layer fills only its own
    seats (CraftJudgment has no others — the zero-LLM assertion's seat)."""
    captions = scan.get("captions") or {}
    position_y = captions.get("position_y")
    return CraftSkeleton(
        version=scan["version"],
        aspect=scan["aspect"],
        duration_seconds=scan["duration_seconds"],
        shots=[CraftShot(**s) for s in scan.get("shots") or []],
        rhythm=CraftRhythm(**(scan.get("rhythm") or {})),
        captions=CraftCaptionScan(
            present=bool(captions.get("present")),
            preset=captions.get("preset"),
            color=captions.get("color"),
            position=Point(x=0.5, y=position_y) if position_y is not None else None,
        ),
        music_mood=judgment.music_mood,
        hook_device=judgment.hook_device,
        gaps=judgment.gaps,
    )


async def _materialize_skeleton(
    db: AsyncSession, asset: Asset
) -> CraftSkeleton | None:
    """The one decompile pass — the run's node and the warm share it (the
    _materialize_understanding precedent). Returns None when the video
    yields no frames (undecodable / empty): the caller noops honestly and
    no LLM call fires (nothing to judge)."""
    from app.providers.storage import download_to_temp  # deferred: provider edge

    path = await download_to_temp(asset.file_url)
    if path is None:
        return None
    try:
        scan = await asyncio.to_thread(
            craft_scan.scan_video, path, asset.duration_seconds
        )
        if not scan:
            return None
        keyframes = await asyncio.to_thread(
            craft_scan.grab_keyframes, path, scan.get("shots") or []
        )
    finally:
        path.unlink(missing_ok=True)

    facts = {
        "aspect": scan["aspect"],
        "duration_seconds": scan["duration_seconds"],
        "shot_count": scan["rhythm"]["shot_count"],
        "cuts_per_minute": scan["rhythm"]["cuts_per_minute"],
        "median_shot_seconds": scan["rhythm"]["median_shot_seconds"],
        "pace": scan["rhythm"]["pace"],
        "captions": scan["captions"],
    }
    transcript = (asset.transcript or "").strip()
    judgment = CraftJudgment()
    try:
        judgment = await decompile.call(
            facts=facts,
            mood_catalog=await _mood_catalog(db),
            keyframes=_keyframe_media(keyframes),
            # The transcript informs tone/hook only — a no-speech case
            # (JOURNEYS 旅程二 1a) simply omits it (frames-only judgment).
            transcript_excerpt=transcript[:4000] or None,
        )
    except LLMError as e:
        # 声明化兜底: the judgment layer degrades to None seats — the
        # deterministic skeleton still lands intact.
        logger.warning(
            "decompile_judgment_degraded", asset_id=str(asset.id), error=str(e)
        )
    return _skeleton_from_scan(scan, judgment)


def _row(
    project: Project,
    asset: Asset,
    skeleton: CraftSkeleton,
    *,
    step_id: UUID | None,
    warmed: bool = False,
) -> Output:
    return Output(
        project_id=project.id,
        workflow_step_id=step_id,
        type="craft_skeleton",
        language=_source_language(project, [asset]),
        provenance="generated",
        payload=skeleton.model_dump(mode="json"),
        source_ref={
            "asset_id": str(asset.id),
            "asset_hash": _skeleton_digest(asset),
            "warmed": warmed,
        },
    )


# ---- exemplar param source (ADR-078 判词⑤): code maps, the LLM never writes a spec
#
# The skeleton's measured craft becomes run params HERE — plain functions over
# the validated CraftSkeleton, called by the consumers (select_clips /
# materialize_source / plan / music precedence). Precedence everywhere:
# explicit (user-stated slot/spec fields) > exemplar (this source) > defaults
# (skin / catalog / count_default). A missing skeleton ⇒ every helper returns
# None/{} and the regular chain decides (degrade visible, never silent).


async def load_skeleton_for_run(
    db: AsyncSession, run: WorkflowRun, project: Project
) -> CraftSkeleton | None:
    """The run's exemplar skeleton: ``run.context.exemplar_asset_id`` → asset
    → content hash → the latest same-user skeleton row (the reuse query — a
    warmed or earlier-project row serves too). None = this run carries no
    (resolvable) exemplar."""
    ctx = run.context if isinstance(run.context, dict) else {}
    pin = ctx.get("exemplar_asset_id")
    if not pin:
        return None
    try:
        asset = await db.get(Asset, UUID(str(pin)))
    except ValueError:
        return None
    if asset is None:
        return None
    row = await find_reusable_skeleton(db, project, asset)
    if row is None:
        return None
    try:
        return CraftSkeleton.model_validate(row.payload)
    except Exception:  # noqa: BLE001 — stale shape: treat as absent
        logger.warning("craft_skeleton_payload_invalid", output_id=str(row.id))
        return None


def skeleton_clip_count(
    skeleton: CraftSkeleton | None, count_limits: tuple[int, int] | None
) -> int | None:
    """Exemplar-derived clip count: the exemplar's shot count, clamped to the
    node's declared count bounds (birthplace C3's limits bind code-mapped
    values too). None = no skeleton / no shots → the default chain decides."""
    if skeleton is None or skeleton.rhythm.shot_count <= 0:
        return None
    lo, hi = count_limits or (1, 10)
    return max(lo, min(hi, skeleton.rhythm.shot_count))


def skeleton_caption_overrides(skeleton: CraftSkeleton | None) -> dict[str, Any]:
    """The exemplar's caption style as param overrides. ``present=False`` ⇒
    {} — absence is NOT a style signal: the remix keeps the skin's caption
    defaults, never strips them."""
    if skeleton is None or not skeleton.captions.present:
        return {}
    out: dict[str, Any] = {}
    if skeleton.captions.preset:
        out["preset"] = skeleton.captions.preset
    if skeleton.captions.color:
        out["color"] = skeleton.captions.color
    if skeleton.captions.position is not None:
        out["position"] = {
            "x": skeleton.captions.position.x,
            "y": skeleton.captions.position.y,
        }
    return out


async def warm_craft_skeleton(project_id: UUID, asset_id: UUID) -> None:
    """Pin/upload-time materialization (期 1 前移的 exemplar 形态): once a
    pin lands (the pending plan's exemplar_asset_id — the chat layer's
    settle seats fire this) and the asset's processing has completed, the
    skeleton materializes before any run asks, so the decompile node reuses
    it at zero LLM cost.

    Runs outside a workflow step (the warm_understanding precedent);
    never raises — a warm failure only means the run path pays the pass
    later. Only a FRESH materialization fires the trigger turn (a reuse
    hit returns early), mirroring warm_understanding's dedup.
    """
    try:
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, project_id)
            asset = await db.get(Asset, asset_id)
            if project is None or asset is None or asset.project_id != project.id:
                return
            if asset.type != AssetType.VIDEO or not asset.file_url:
                return
            if asset.processing_status != AssetStatus.COMPLETED:
                return  # the processor's completion seat re-fires the warm
            if await find_reusable_skeleton(db, project, asset) is not None:
                logger.info("craft_skeleton_warm_reuse_hit", asset_id=str(asset_id))
                return
            skeleton = await _materialize_skeleton(db, asset)
            if skeleton is None:
                return  # undecodable — the run path's noop reports it honestly
            db.add(_row(project, asset, skeleton, step_id=None, warmed=True))
            await db.commit()
            logger.info(
                "craft_skeleton_warmed",
                project_id=str(project_id),
                asset_id=str(asset_id),
                shots=len(skeleton.shots),
            )
            # 触发回合 (判词③ whitelist #3): 案例拆解完成 — the agent reads the
            # skeleton and speaks (旅程二 ④). Fire-and-forget.
            # (Seam: app.pipeline.trigger_events, ADR-087 §6.)
            fire_trigger(project_id, TRIGGER_CRAFT_DECOMPILED, str(asset_id))
    except Exception as e:  # noqa: BLE001 — warm is best-effort, the run path pays later
        logger.warning(
            "craft_skeleton_warm_failed", asset_id=str(asset_id), error=str(e)
        )


# create_task holds only a weak reference — the GC can collect a fire-and-
# forget task mid-flight. Keep a strong reference until done (the
# asset_processing._warm_tasks precedent, re-homed here so every fire seat
# — the asset processor's completion, the chat layer's role-pin settle —
# shares the one guard).
_WARM_TASKS: set[asyncio.Task] = set()


def fire_warm_craft_skeleton(project_id: UUID, asset_id: UUID) -> None:
    """Fire-and-forget warm with the GC guard owned here. The warm itself
    re-checks every precondition (VIDEO, COMPLETED, reuse hit), so callers
    fire on the pin event without re-deriving eligibility."""
    task = asyncio.create_task(warm_craft_skeleton(project_id, asset_id))
    _WARM_TASKS.add(task)
    task.add_done_callback(_WARM_TASKS.discard)


class Decompile(NodeBase):
    """The decompiler node — compile-injected (orchestrator keys off
    ``TaskSpec.exemplar_asset_id``), never a registry tool, never in the
    user's proposal space. Parallel to understand off preprocess; the plan
    node's inputs carry it so the skeleton lands before planning reads it.
    """

    kind = "decompile"
    task_name = "Study the exemplar"
    task_name_zh = "拆解案例"
    agents = (decompile,)

    def estimate(self, ctx: dict) -> dict | None:
        """One multimodal call: the facts block plus ≤ 8 keyframes. A
        content-hash reuse zeroes the ACTUAL — the quote stays the
        fresh-call cost (the understand precedent)."""
        return estimate_agent([1500, 8000], [200, 1200])

    async def reuse(
        self,
        db: AsyncSession,
        run: WorkflowRun,
        node: WorkflowStep,
        project: Project,
        asset: Asset,
        assets: list,
    ) -> UUID | None:
        """Idempotent reuse (asset-hash class — the understand protocol's
        second case): a hit returns the earlier row's id and the node costs
        nothing, whether the row came from a prior run or the warm."""
        latest = await find_reusable_skeleton(db, project, asset)
        if latest is None:
            return None
        try:
            cached = CraftSkeleton.model_validate(latest.payload)
        except Exception:  # noqa: BLE001 — stale shape: fall through, regenerate
            logger.warning(
                "craft_skeleton_reuse_payload_invalid", output_id=str(latest.id)
            )
            return None
        zh = _display_zh(run, project, assets)
        await set_summary(
            node.id,
            f"复用案例拆解 · {len(cached.shots)} 个镜头"
            if zh
            else f"Reused the craft skeleton · {len(cached.shots)} shots",
        )
        logger.info(
            "craft_skeleton_reused",
            project_id=str(project.id),
            output_id=str(latest.id),
        )
        return latest.id

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        assets = await list_assets(db, project.id)
        zh = _display_zh(run, project, assets)
        spec = node.spec or {}
        asset: Asset | None = None
        raw_id = spec.get("asset_id")
        if raw_id:
            try:
                asset = await db.get(Asset, UUID(str(raw_id)))
            except ValueError:
                asset = None
        if (
            asset is None
            or asset.project_id != project.id
            or asset.type != AssetType.VIDEO
            or not asset.file_url
        ):
            # The pin resolved at the birthplace (create_run validates) but
            # the asset may have vanished since — honest noop, the chain
            # proceeds as a regular cut (exemplar params find no skeleton
            # and fall to defaults).
            await set_spec_field(node.id, "noop", True)
            await set_summary(
                node.id,
                "案例不可用——按常规剪辑进行"
                if zh
                else "Exemplar unavailable — proceeding as a regular cut",
            )
            logger.warning("decompile_asset_unusable", project_id=str(project.id))
            return []

        reused = await self.reuse(db, run, node, project, asset, assets)
        if reused is not None:
            return [reused]

        skeleton = await _materialize_skeleton(db, asset)
        if skeleton is None:
            await set_spec_field(node.id, "noop", True)
            await set_summary(
                node.id,
                "案例拆解失败——按常规剪辑进行"
                if zh
                else "Couldn't decompile the exemplar — proceeding as a regular cut",
            )
            logger.warning("decompile_scan_empty", asset_id=str(asset.id))
            return []

        row = _row(project, asset, skeleton, step_id=node.id)
        db.add(row)
        await db.flush()
        pace_zh = {"fast": "快", "steady": "稳", "slow": "缓"}.get(
            skeleton.rhythm.pace, skeleton.rhythm.pace
        )
        caption_note = ""
        if skeleton.captions.present:
            caption_note = (
                f" · 字幕 {skeleton.captions.preset}"
                if zh
                else f" · captions {skeleton.captions.preset}"
            )
        await set_summary(
            node.id,
            f"拆解了案例 · {len(skeleton.shots)} 个镜头 · {pace_zh}节奏{caption_note}"
            if zh
            else f"Decompiled the exemplar · {len(skeleton.shots)} shots · "
            f"{skeleton.rhythm.pace} pace{caption_note}",
        )
        logger.info(
            "craft_skeleton_materialized",
            project_id=str(project.id),
            asset_id=str(asset.id),
            shots=len(skeleton.shots),
            captions=skeleton.captions.present,
            gaps=len(skeleton.gaps),
        )
        # 触发回合 (判词③ whitelist #3): the run path's fresh materialization
        # speaks with the same voice as the warm (:357) — the user in a remix
        # run hears 「我看了你的案例」(旅程二④). Fire-and-forget; a reuse hit
        # above returns early and never re-speaks, and the turn dedups on
        # (conversation, trigger, ref) against the warm's prior speech. The
        # step's session commits right after run() returns (execute_step's
        # done branch) — the trigger turn's own session reads the skeleton
        # only inside its bounded loop, seconds later, and a miss reads
        # honestly (the turn NEVER raises).
        # (Seam: app.pipeline.trigger_events, ADR-087 §6.)
        fire_trigger(project.id, TRIGGER_CRAFT_DECOMPILED, str(asset.id))
        return [row.id]
