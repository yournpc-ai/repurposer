"""Unified outputs read surface (ADR-030).

``visible_outputs_stmt`` is THE filter every user-facing read path must use —
results, library, export, and future MCP/gallery surfaces. Internal node
artifacts (``INTERNAL_OUTPUT_TYPES``, e.g. the director's material_understanding
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


def workflow_step_to_response(node: WorkflowStep) -> StepResponse:
    """Serialize a node; ``stage`` is the display hint from spec (results.stepper.* keys)."""
    node_cls = node_for(node.kind)
    return StepResponse(
        id=node.id,
        kind=node.kind,
        status=node.status,
        seq=node.seq,
        error=node.error,
        cost=node.cost,
        stage=(node.spec or {}).get("stage"),
        summary=(node.spec or {}).get("summary"),
        # 渲染单元 (D6 修订) comes from the node CLASS (self-description,
        # like label()), never the row — legacy/unknown kinds fold into the
        # spine by default.
        canvas_key=node_cls.canvas_group(node) if node_cls else None,
        canvas_hidden=node_cls.canvas_hidden if node_cls else False,
        canvas_text=(node_cls.canvas_text(node) if node_cls else None),
        output_refs=[UUID(str(ref)) for ref in (node.output_refs or [])],
        inputs=[UUID(str(upstream)) for upstream in (node.inputs or [])],
        started_at=node.started_at,
        finished_at=node.finished_at,
    )


# Clip-producer kinds a fork can hang off (the fork's card count and aspect
# inherit from the producer it derives from).
_CLIP_PRODUCER_KINDS = ("materialize_source", "select_clips")


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


def _clips_slot_count(step: WorkflowStep) -> int:
    """A select_clips step's promised card count (the slot's count — the
    params model's default rides the persisted spec, so this never guesses)."""
    return int(((step.spec or {}).get("slot") or {}).get("count") or 1)


def derive_placeholder_rows(
    nodes: list[WorkflowStep],
    outputs: list[Output],
) -> list[dict]:
    """The live run's placeholder roster (ADR-051 B — 占位物化): what the
    run's output-creating steps will MAKE, projected from the run's own step
    rows — the materialized compile, i.e. the runtime form of ADR-043's
    dry-run (the roster can never drift from what will actually execute;
    prohibition #4 — never a frontend guess). One row per producing step,
    keyed by ``step_id`` so the surface matches a landed output to its slot
    and fills it in place.

    Morph modifiers (non-fork translate/dub) create NO row — they rewrite an
    existing card in place. A fork's card count + aspect inherit from the
    producer it hangs off (inputs walk); a fork acting on existing clips
    sizes off the current clip list; a targeted fork (target_output_id) is
    always one card. Aspect stays None when unknown — the surface's default
    tier (画幅未知取默认档), never a hardcoded fake.
    """
    by_id = {str(n.id): n for n in nodes}

    def upstream_producer(step: WorkflowStep) -> WorkflowStep | None:
        """Nearest clip producer upstream (BFS over the real edge table —
            modifier chains walk through to materialize/select)."""
        seen: set[str] = set()
        frontier = [str(u) for u in (step.inputs or [])]
        while frontier:
            cur_id = frontier.pop(0)
            if cur_id in seen:
                continue
            seen.add(cur_id)
            cur = by_id.get(cur_id)
            if cur is None:
                continue
            if cur.kind in _CLIP_PRODUCER_KINDS:
                return cur
            frontier.extend(str(u) for u in (cur.inputs or []))
        return None

    rows: list[dict] = []
    for node in nodes:  # the endpoint passes them seq-ordered
        spec = node.spec or {}
        if node.kind == "materialize_source":
            rows.append({"step_id": node.id, "type": "clip", "whole": True})
            continue
        if node.kind == "select_clips":
            rows.append(
                {
                    "step_id": node.id,
                    "type": "clip",
                    "count": _clips_slot_count(node),
                    "language": spec.get("target_language"),
                    "aspect": spec.get("aspect"),
                }
            )
            continue
        if node.kind in ("translate_clip", "dub_clip"):
            if not spec.get("fork"):
                continue  # morph — rewrites an existing card in place
            producer = upstream_producer(node)
            if spec.get("target_output_id"):
                count = 1
            elif producer is not None:
                count = (
                    1
                    if producer.kind == "materialize_source"
                    else _clips_slot_count(producer)
                )
            else:
                # Acting on existing clips (no in-run producer) — one derived
                # card per current clip.
                count = max(1, sum(1 for o in outputs if o.type == "clip"))
            rows.append(
                {
                    "step_id": node.id,
                    "type": "clip",
                    "whole": producer is not None
                    and producer.kind == "materialize_source",
                    "count": count,
                    "language": spec.get("target_language"),
                    "variant": "subs" if node.kind == "translate_clip" else "dub",
                    "aspect": (producer.spec or {}).get("aspect")
                    if producer is not None
                    else None,
                }
            )
            continue
        node_cls = node_for(node.kind)
        if node_cls is None or not node_cls.produces_outputs or not node_cls.output_type:
            continue
        if node_cls.output_type == "clips":
            continue  # select_clips handled above
        rows.append(
            {
                "step_id": node.id,
                "type": node_cls.output_type,
                "language": spec.get("target_language"),
            }
        )
    return rows


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


def aggregate_run_summary(nodes: list[WorkflowStep]) -> str | None:
    """Run-level rollup of step summaries, derived at read time (no column).

    "Wrote a LinkedIn post · 739 words" — the recap tells what the user GOT,
    so only **tool** summaries join (registry members; internal-crew lines —
    understand / plan / render bookkeeping — stay on their own step rows),
    plus any bailed waiting-seat node's user-abort note (deliberate, see
    ``bail_waiting_interrupt`` — direction interrupt, 期 4 hook gate, …).
    Joined in seq order (CHAT_ARCH §8)."""
    from app.tools import TOOL_REGISTRY  # deferred: import cycle

    parts = [
        summary
        for node in sorted(nodes, key=lambda n: n.seq)
        if node.status == "done"
        and (summary := (node.spec or {}).get("summary"))
        and (
            node.kind in TOOL_REGISTRY
            or (node.spec or {}).get("bailed")
        )
    ]
    return " · ".join(parts) if parts else None


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
        resp.steps = [workflow_step_to_response(n) for n in nodes]
        resp.cost = aggregate_step_cost(nodes)
    return resp
