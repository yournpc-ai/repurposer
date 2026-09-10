"""Unified outputs read surface (ADR-030).

``visible_outputs_stmt`` is THE filter every user-facing read path must use —
results, library, export, and future MCP/gallery surfaces. Internal node
artifacts (``INTERNAL_OUTPUT_TYPES``, e.g. the plan prelude's material_understanding
/ storyboard) are node bookkeeping, never user products, and must not leak
into any listing.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.schemas import (
    INTERNAL_OUTPUT_TYPES,
    StepResponse,
    RunResponse,
)
from app.models.tables import Output, WorkflowStep, WorkflowRun
from app.pipeline.graph import fold_estimates, node_for
from app.platform.billing import cost_usd, credits_at_ratio, estimate_usd_range
from app.platform.configs import get_config


def visible_outputs_stmt() -> Select:
    """Base SELECT over user-facing outputs only (internal types excluded)."""
    return select(Output).where(Output.type.notin_(INTERNAL_OUTPUT_TYPES))


async def list_visible_outputs(
    db: AsyncSession,
    project_id: UUID,
    *,
    output_type: str | None = None,
) -> list[Output]:
    """List a project's user-facing outputs, newest first."""
    stmt = visible_outputs_stmt().where(Output.project_id == project_id)
    if output_type is not None:
        stmt = stmt.where(Output.type == output_type)
    result = await db.execute(stmt.order_by(Output.created_at.desc()))
    return list(result.scalars().all())


def workflow_step_to_response(node: WorkflowStep, *, ratio: int) -> StepResponse:
    """Serialize a node; ``stage`` is the display hint from spec (results.stepper.* keys).

    ``ratio`` (credits.per_cost_usd) is read ONCE per response by the caller
    and injected — the credits fields are the serialization-layer derivation
    (BILLING §7: USD stays in estimate/cost, credits are folded at read time
    and never persisted), so one config edit moves every surface at once.
    """
    estimate_credits: list[int] | None = None
    if node.estimate:
        usd_low, usd_high = estimate_usd_range(node.estimate)
        estimate_credits = [
            credits_at_ratio(usd_low, ratio),
            credits_at_ratio(usd_high, ratio),
        ]
    return StepResponse(
        id=node.id,
        kind=node.kind,
        status=node.status,
        seq=node.seq,
        error=node.error,
        cost=node.cost,
        stage=(node.spec or {}).get("stage"),
        summary=(node.spec or {}).get("summary"),
        noop=(node.spec or {}).get("noop") or None,
        output_refs=[UUID(str(ref)) for ref in (node.output_refs or [])],
        inputs=[UUID(str(upstream)) for upstream in (node.inputs or [])],
        estimate_credits=estimate_credits,
        cost_credits=(
            credits_at_ratio(cost_usd(node.cost), ratio) if node.cost else None
        ),
        started_at=node.started_at,
        finished_at=node.finished_at,
    )


def compose_spec_prompt(step: WorkflowStep, ui_language: str) -> str | None:
    """The product's own spec as a prompt-style line (ADR-051 F — hover
    prompt 框): the producing step's slot/params composed in the run's
    pinned ui_language. The 框 prefills with it (the product's "make this"
    instruction); the user edits it into any revision ask. Language tags
    are uppercase ISO (slot_tag's house style). None for steps whose
    product has no meaningful spec to edit (materialize_source — the whole
    video is the source itself)."""
    spec = step.spec or {}
    zh = ui_language.startswith("zh")
    slot = spec.get("slot") or {}
    lang = (spec.get("target_language") or slot.get("language") or "").upper()

    if step.kind == "select_clips":
        count = int(slot.get("count") or 1)
        parts = [
            f"切 {count} 条短片" if zh else f"Cut {count} clips",
        ]
        if spec.get("aspect"):
            parts.append(f"画幅 {spec['aspect']}" if zh else f"in {spec['aspect']}")
        if slot.get("focus"):
            parts.append(
                f"主题：{slot['focus']}" if zh else f"focus: {slot['focus']}"
            )
        if lang:
            parts.append(f"屏幕文字 {lang}" if zh else f"titles in {lang}")
        return ("，" if zh else ", ").join(parts)

    if step.kind in ("translate_clip", "dub_clip"):
        if step.kind == "translate_clip":
            base = f"字幕翻译成 {lang}" if zh else f"Translate captions to {lang}"
            if spec.get("bilingual"):
                base += "（双语）" if zh else " (bilingual)"
            return base
        return f"配音成 {lang}" if zh else f"Dub into {lang}"

    node_cls = node_for(step.kind)
    if node_cls is None or not node_cls.produces_outputs or not node_cls.output_type:
        return None
    word = (
        (node_cls.slot_label_zh if zh and node_cls.slot_label_zh else None)
        or node_cls.slot_label
        or node_cls.output_type
    )
    base = f"写{word}" if zh else f"Write {word.lower()}"
    parts = [base]
    if lang:
        parts.append(f"用 {lang}" if zh else f"in {lang}")
    if slot.get("count") and node_cls.output_type in ("quotes", "carousel"):
        parts.append(f"{slot['count']} 条" if zh else f"{slot['count']} items")
    if slot.get("focus"):
        parts.append(f"主题：{slot['focus']}" if zh else f"focus: {slot['focus']}")
    if slot.get("tone_override"):
        parts.append(
            f"语气：{slot['tone_override']}"
            if zh
            else f"tone: {slot['tone_override']}"
        )
    return ("，" if zh else ", ").join(parts)


# Step kinds whose products are LLM-written (the "copy" modality).
_LLM_PRODUCT_KINDS = (
    "select_clips",
    "translate_clip",
    "write_post",
    "write_article",
    "write_quotes",
    "write_carousel",
)


def model_facts_for(step_kind: str | None, output: Output) -> list[dict[str, str]]:
    """Per-product model/provider facts (ADR-051 H — 详情面模型事实): the
    producing step's kind projected to its REAL model usage — one provider
    per modality today, so a static registry, never a guess and never a
    selector / SKU shelf (禁令2). Every clip's captions derive from ASR
    (self-hosted Whisper), so the captions fact is clip-intrinsic; a music
    fact appears only when the clip's payload pins a matched mood (the
    music bed was actually burned). Display names are DATA (proper nouns,
    locale-invariant — the same strings the composer models panel shows);
    the modality key localizes in the UI. Facts display ONLY on the detail
    surface (the lightbox info column) — the node caption never carries a
    model name (prohibition #12)."""
    facts: list[dict[str, str]] = []
    if output.type == "clip":
        facts.append({"modality": "captions", "model": "Whisper"})
        if (output.payload or {}).get("music_mood"):
            facts.append({"modality": "music", "model": "MiniMax music-2.6"})
    if step_kind in _LLM_PRODUCT_KINDS:
        facts.append({"modality": "copy", "model": "MiniMax M3"})
    elif step_kind == "dub_clip":
        facts.append({"modality": "voice", "model": "MiniMax speech-2.6-hd"})
    return facts


def aggregate_step_cost(nodes: list[WorkflowStep]) -> dict | None:
    """Run-level cost = sum over node cost ledgers (ADR-025)."""
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "fixed_cost": 0.0}
    seen = False
    for node in nodes:
        if not node.cost:
            continue
        seen = True
        totals["prompt_tokens"] += int(node.cost.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(node.cost.get("completion_tokens") or 0)
        totals["fixed_cost"] += float(node.cost.get("fixed_cost") or 0.0)
    return totals if seen else None


def aggregate_step_estimate(nodes: list[WorkflowStep]) -> dict | None:
    """Run-level quotation = fold over node estimates (P4, N-34 — the read
    side of 报价=图 fold; the write side is create_run's per-node estimate).
    None when every node is unquoted (NULL estimates)."""
    quoted = [node.estimate for node in nodes if node.estimate]
    if not quoted:
        return None
    return fold_estimates(quoted)


def step_estimate_deviation(node: WorkflowStep) -> dict | None:
    """actual (cost ledger) vs estimate (quotation), per token field — the
    calibration regression's read shape (AGENT_ARCH §8):

        {prompt_tokens:     {actual, low, high, delta},
         completion_tokens: {actual, low, high, delta},
         units?:            {<unit>: {expected, actual, delta}}}

    delta = actual − clamp(actual, low, high): 0 = in range, positive = the
    quote undershot, negative = it overshot. None when either side is
    missing (a node without an estimate or without metered usage yet). The
    SQL twin for the fleet-wide regression:

        SELECT kind,
               count(*) FILTER (WHERE (cost->>'prompt_tokens')::int
                  BETWEEN (estimate->'prompt_tokens'->>0)::int
                      AND (estimate->'prompt_tokens'->>1)::int) AS prompt_in_range,
               count(*) AS n
        FROM workflow_steps
        WHERE estimate IS NOT NULL AND cost IS NOT NULL
        GROUP BY kind;
    """
    if not node.estimate or not node.cost:
        return None

    def field(name: str) -> dict:
        low, high = (int(v) for v in node.estimate[name])
        actual = int(node.cost.get(name) or 0)
        return {
            "actual": actual,
            "low": low,
            "high": high,
            "delta": actual - min(max(actual, low), high),
        }

    out = {
        "prompt_tokens": field("prompt_tokens"),
        "completion_tokens": field("completion_tokens"),
    }
    # Mechanical units (media metering, record_media_usage): estimate carries
    # exact quantities, cost carries actuals — delta is signed drift.
    est_units = node.estimate.get("units") or {}
    act_units = node.cost.get("units") or {}
    if est_units or act_units:
        out["units"] = {
            key: {
                "expected": float(est_units.get(key) or 0.0),
                "actual": float(act_units.get(key) or 0.0),
                "delta": float(act_units.get(key) or 0.0) - float(est_units.get(key) or 0.0),
            }
            for key in sorted(set(est_units) | set(act_units))
        }
    return out


async def run_to_response(
    db: AsyncSession,
    run: WorkflowRun,
    *,
    with_steps: bool = True,
) -> RunResponse:
    """Serialize a run with its workflow steps and aggregated cost."""
    resp = RunResponse.model_validate(run)
    if with_steps:
        result = await db.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id).order_by(WorkflowStep.seq)
        )
        nodes = list(result.scalars().all())
        ratio = await get_config(db, "credits.per_cost_usd")
        resp.steps = [workflow_step_to_response(n, ratio=ratio) for n in nodes]
        resp.cost = aggregate_step_cost(nodes)
    return resp
