"""Graph fill (ADR-057 K2) — the run → graph double-write and back-write.

双写期 (the double-write period): ``create_run`` keeps materializing
``workflow_steps`` exactly as before (the execution ledger — billing
capture / metering / retries ride it), and ADDITIONALLY stamps the run's
intent onto the persistent graph (the product face). The old canvas is
untouched until K3 flips the data source.

Two directions:

- **stamp** (``stamp_run_graph``): compiled steps → graph nodes/edges via
  the wiring layer (the graph's only write door — zero bypass). Node
  identity is idempotent (``spec.fill_key``): a re-run of the same slot
  REUSES its node (spec refreshed, state re-queued), a new slot grows a
  node; the graph is edited continuously, never re-grown wholesale.
  Steps carry the back-pointer (``step.spec.graph_node_id``) and nodes
  carry their internal workflow (``spec.step_ids``) — composition, never
  projection: steps stay step-grained INSIDE the node.
- **back-write** (``sync_graph_node_for_step``): the orchestrator's
  execute_step calls this at every step terminal — the node's state is the
  aggregate of its internal step family (the runFlow.ts aggregateStatus
  logic's server-side home), and landed outputs back-write
  ``spec.output_ids``.

Migration mapping (简报 §3): assets → asset / plan prelude → the task-book
document / select_clips·writers·revise·translate·dub → generator /
materialize·remove_filler·add_music·reframe → processor / research →
agent. Render steps join NO family — their state rides the output row's
render_status (the node's product region carries it in place).
align_stills / verify live inside their downstream producer / their
executor's node.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Asset, GraphEdge, GraphNode, Output, Project, WorkflowRun, WorkflowStep
from app.pipeline.graph import NODE_KINDS
from app.pipeline.graph_store import apply_wiring_ops
from app.pipeline.outputs import compose_spec_prompt

logger = structlog.get_logger()

# Step kinds of the plan prelude — the task-book document's internal
# workflow (the book's birth process: preprocess → persona ∥ understand →
# (interrupt) → plan). Kind strings, same source as node_runners.
_PRELUDE_KINDS = frozenset({"preprocess", "persona_bootstrap", "understand", "interrupt", "plan"})

# Modifier kinds that own a PROCESSOR node (deterministic, no LLM prompt —
# params live in the factsbar); translate/dub are generators (parameterized
# intent on the card). Kind-derived via NODE_KINDS at fill time — this set
# only names the deterministic processor instances (简报 §3).
_PROCESSOR_KINDS = frozenset({"materialize_source", "remove_filler", "add_music", "reframe_clip"})

# Clip-family kinds — edges between these carry the video flow.
_CLIP_FAMILY_KINDS = frozenset({
    "select_clips", "materialize_source", "translate_clip", "dub_clip",
    "remove_filler", "add_music", "reframe_clip",
})

_TASK_BOOK_ROLE = "task_book"


def _fill_key_for_step(step: WorkflowStep) -> str:
    """The node's idempotency fingerprint (a re-run of the same slot finds
    its node; a new slot grows one). Producers: kind#type#ordinal (the
    compile's slot_index is stable per output type across chains).
    translate/dub: kind#language#bilingual#fork. Deterministic processors /
    materialize / research: the bare kind (one工序, one node)."""
    kind = step.kind
    spec = step.spec or {}
    if kind in ("translate_clip", "dub_clip"):
        return (
            f"{kind}#{spec.get('target_language') or ''}"
            f"#{bool(spec.get('bilingual'))}#{bool(spec.get('fork'))}"
        )
    slot = spec.get("slot")
    if isinstance(slot, dict):
        return f"{kind}#{slot.get('type') or ''}#{spec.get('slot_index') or 0}"
    return kind


def _node_label(step: WorkflowStep, ui_language: str) -> str | None:
    """The node's caption name — the step's own builder-written summary
    preset (it already carries the sibling tag, e.g. "翻译字幕 · DE"),
    falling back to NodeBase.label for legacy rows without one. Never a
    frontend dictionary."""
    summary = (step.spec or {}).get("summary")
    if summary:
        return str(summary)
    node_cls = NODE_KINDS.get(step.kind)
    if node_cls is None:
        return step.kind
    from app.models.schemas import IntentSlot  # deferred: schema leaf

    slot = (step.spec or {}).get("slot")
    return node_cls.label(
        IntentSlot.model_validate(slot) if isinstance(slot, dict) else None,
        ui_language,
    ) or step.kind


def _aggregate_family(states: list[str]) -> str:
    """Node state = its internal step family's aggregate (the retired
    runFlow aggregateStatus's server-side form): failure always visible,
    then liveness, then terminal honesty (all skipped = skipped)."""
    if not states:
        return "queued"
    if any(s == "failed" for s in states):
        return "failed"
    if any(s in ("running", "waiting") for s in states):
        return "running"
    if all(s == "skipped" for s in states):
        return "skipped"
    if all(s in ("done", "skipped") for s in states):
        return "done"
    if any(s == "done" for s in states):
        return "running"
    return "queued"


async def stamp_asset_node(
    db: AsyncSession, project_id: UUID, asset: Asset
) -> GraphNode:
    """上传即落图 (简报 §3): the asset node is born with its asset row —
    or found (idempotent on spec.asset_id). Flush-only; the caller commits
    with the asset. Assets are inputs, not execution units — the node is
    born done (content self-evident; processing rides the asset row)."""
    existing = (
        await db.execute(
            select(GraphNode).where(
                GraphNode.project_id == project_id,
                GraphNode.kind == "asset",
                GraphNode.spec["asset_id"].as_string() == str(asset.id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    delta = await apply_wiring_ops(
        db,
        project_id,
        [
            {
                "op": "add_node",
                "kind": "asset",
                "spec": {
                    "asset_id": str(asset.id),
                    "asset_type": str(asset.type.value if hasattr(asset.type, "value") else asset.type),
                    "title": asset.title,
                },
            }
        ],
    )
    node = await db.get(GraphNode, delta.affected[0])
    assert node is not None
    return node


async def remove_asset_node(db: AsyncSession, project_id: UUID, asset_id: UUID) -> None:
    """Asset deletion's graph twin — the node goes through the same wiring
    door (edges cascade structurally). Absent node = pre-K2 asset, skip."""
    existing = (
        await db.execute(
            select(GraphNode).where(
                GraphNode.project_id == project_id,
                GraphNode.kind == "asset",
                GraphNode.spec["asset_id"].as_string() == str(asset_id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        await apply_wiring_ops(
            db, project_id, [{"op": "delete_node", "node": UUID(str(existing.id))}]
        )


async def stamp_run_graph(
    db: AsyncSession,
    project: Project,
    run: WorkflowRun,
    steps: list[WorkflowStep],
) -> None:
    """Stamp one run's intent onto the persistent graph (create_run's
    graph twin — flush-only, same transaction as the run).

    Works purely off the run's persisted step rows (kind / seq / inputs /
    spec — the compile is fully persisted), so the backfill script replays
    the exact same stamping. Filled nodes leave the call at state=queued.
    """
    ui_language = str((run.context or {}).get("ui_language") or "en")
    project_id = UUID(str(project.id))

    # ── 1. Classify the steps into node families ─────────────────────────
    # node_key → {"kind": graph kind, "steps": [step]}; every generation /
    # processor / agent step owns or joins a node; the prelude belongs to
    # the task-book document; align_stills folds into its downstream
    # producer; verify folds into its executor's node. render joins nothing.
    families: dict[str, dict[str, Any]] = {}

    def family_for(key: str, kind: str) -> dict[str, Any]:
        fam = families.get(key)
        if fam is None:
            fam = families[key] = {"kind": kind, "steps": []}
        return fam

    by_id = {str(s.id): s for s in steps}
    producers = [s for s in steps if s.kind not in _PRELUDE_KINDS and s.kind != "verify" and s.kind != "render" and s.kind != "align_stills"]
    for step in steps:
        if step.kind in _PRELUDE_KINDS or step.kind in ("render",):
            continue
        if step.kind == "verify":
            # The executor is the verify's first input (compile contract).
            executor = by_id.get(str((step.inputs or [None])[0]))
            if executor is not None and executor.kind not in _PRELUDE_KINDS:
                family_for(_fill_key_for_step(executor), _graph_kind_of(executor))["steps"].append(step)
            continue
        if step.kind == "align_stills":
            # Folds into the nearest downstream producer (its id appears in
            # that step's inputs — direct child in the compile).
            owner = next(
                (s for s in producers if str(step.id) in (str(i) for i in (s.inputs or []))),
                None,
            )
            if owner is not None:
                family_for(_fill_key_for_step(owner), _graph_kind_of(owner))["steps"].append(step)
            continue
        family_for(_fill_key_for_step(step), _graph_kind_of(step))["steps"].append(step)

    # ── 2. Read the current graph (idempotent reuse) ─────────────────────
    existing_nodes = list(
        (
            await db.execute(
                select(GraphNode).where(GraphNode.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    by_fill_key = {
        str((n.spec or {}).get("fill_key")): n
        for n in existing_nodes
        if (n.spec or {}).get("fill_key")
    }
    task_book_node = next(
        (
            n
            for n in existing_nodes
            if n.kind == "document" and (n.spec or {}).get("role") == _TASK_BOOK_ROLE
        ),
        None,
    )
    existing_edges = list(
        (
            await db.execute(
                select(GraphEdge).where(GraphEdge.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    have_edge = {
        (str(e.from_node), str(e.to_node), e.edge_type) for e in existing_edges
    }

    ops: list[dict[str, Any]] = []
    node_id_by_key: dict[str, UUID] = {}

    # ── 3. Asset nodes (the run's inputs, born with their asset rows — the
    # stamp only ensures the older ones missing from the graph) ───────────
    assets = list(
        (
            await db.execute(
                select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at)
            )
        )
        .scalars()
        .all()
    )
    asset_node_ids: list[UUID] = []
    for asset in assets:
        node = await stamp_asset_node(db, project_id, asset)
        asset_node_ids.append(UUID(str(node.id)))

    # ── 4. The task-book document (the plan prelude's artifact — FLORA
    # text-node form; the prelude's steps are its internal workflow). Only
    # a run WITH a prelude births it — a targeted render/hook scope never
    # grows an empty book card.
    prelude_steps = [s for s in steps if s.kind in _PRELUDE_KINDS]
    book_text = _task_book_text(steps)
    if task_book_node is None:
        if prelude_steps:
            ops.append(
                {
                    "op": "add_node",
                    "kind": "document",
                    "spec": {
                        "role": _TASK_BOOK_ROLE,
                        "text": book_text,
                    },
                }
            )
    elif book_text:
        # A revised chain re-stamps the book — the runtime plan summary
        # overwrites it at back-write time (same source, no flicker).
        task_book_node.spec = {**(task_book_node.spec or {}), "text": book_text}

    # ── 5. Generation / processor / agent nodes (idempotent by fill_key) ──
    new_node_specs: dict[str, dict[str, Any]] = {}  # fill_key → add_node spec
    for key, fam in families.items():
        fam_steps = sorted(fam["steps"], key=lambda s: s.seq)
        head = next((s for s in fam_steps if s.kind not in ("verify", "align_stills")), fam_steps[0])
        estimate = _family_estimate(fam_steps)
        prompt = (
            (
                compose_spec_prompt(head, ui_language)
                # revise_script / research carry their program in spec
                # directly (compose has no slot-shaped branch for them).
                or (head.spec or {}).get("instruction")
                or (head.spec or {}).get("query")
            )
            if fam["kind"] in ("generator", "agent")
            else None
        )
        reused = by_fill_key.get(key)
        frame_class = _frame_class_of(fam_steps)
        if reused is not None:
            node_id_by_key[key] = UUID(str(reused.id))
            # The node is being re-filled: refresh its program + internal
            # workflow and re-queue it (修订/重跑 = 原地图变更, never a twin).
            reused.spec = {
                **(reused.spec or {}),
                "summary": _node_label(head, ui_language),
                **({"prompt": prompt} if prompt else {}),
                "params": _params_of(head),
                "estimate": estimate,
                "frame_class": frame_class,
                "step_ids": [str(s.id) for s in fam_steps],
                "run_id": str(run.id),
                "output_ids": [],
            }
            reused.state = "queued"
            continue
        new_node_specs[key] = {
            "fill_key": key,
            "summary": _node_label(head, ui_language),
            **({"prompt": prompt} if prompt else {}),
            "params": _params_of(head),
            "estimate": estimate,
            "frame_class": frame_class,
            "step_ids": [str(s.id) for s in fam_steps],
            "run_id": str(run.id),
            "output_ids": [],
        }
        ops.append({"op": "add_node", "kind": fam["kind"], "spec": new_node_specs[key]})

    if ops:
        delta = await apply_wiring_ops(db, project_id, ops)
        # Map newborn ids back to their fill keys / the task book (the ops
        # order is the construction order above).
        added = iter(delta.affected)
        for op in ops:
            node_id = next(added)
            spec = op.get("spec") or {}
            if op["kind"] == "document" and spec.get("role") == _TASK_BOOK_ROLE:
                task_book_node = await db.get(GraphNode, node_id)
            elif spec.get("fill_key"):
                node_id_by_key[str(spec["fill_key"])] = node_id

    # ── 6. Back-pointer the steps to their nodes + queue the task book ────
    for key, fam in families.items():
        node_id = node_id_by_key.get(key)
        if node_id is None:
            continue
        for step in fam["steps"]:
            step.spec = {**(step.spec or {}), "graph_node_id": str(node_id)}
    if task_book_node is not None and prelude_steps:
        task_book_node.spec = {
            **(task_book_node.spec or {}),
            "step_ids": [str(s.id) for s in prelude_steps],
            "run_id": str(run.id),
        }
        task_book_node.state = "queued"
        for step in prelude_steps:
            step.spec = {**(step.spec or {}), "graph_node_id": str(task_book_node.id)}

    # ── 7. Edges (dedupe against the existing set) ────────────────────────
    def connect(from_id: UUID, to_id: UUID, edge_type: str) -> None:
        if (str(from_id), str(to_id), edge_type) in have_edge or from_id == to_id:
            return
        have_edge.add((str(from_id), str(to_id), edge_type))
        pending_edges.append(
            {"op": "connect", "from_node": from_id, "to_node": to_id, "edge_type": edge_type}
        )

    def node_of(step: WorkflowStep) -> UUID | None:
        return node_id_by_key.get(_fill_key_for_step(step))

    pending_edges: list[dict[str, Any]] = []
    # Step-input topology → node edges (the compiled DAG's shape, resolved
    # to the graph's nouns — never invented wiring).
    for step in steps:
        target_node = node_of(step)
        if target_node is None:
            continue
        for upstream_id in step.inputs or []:
            upstream = by_id.get(str(upstream_id))
            if upstream is None:
                continue
            if upstream.kind in _PRELUDE_KINDS:
                if task_book_node is not None:
                    connect(UUID(str(task_book_node.id)), target_node, "ctx")
                continue
            source_node = node_of(upstream)
            if source_node is None:
                continue
            connect(
                source_node,
                target_node,
                "video" if upstream.kind in _CLIP_FAMILY_KINDS else "text",
            )
    # Assets feed the graph: text into the task book and the writers, the
    # media flow into the clip-family roots (a root = no clip-family
    # upstream inside this run). A root that acts on the project's EXISTING
    # clips (mode② — the project already has clips from an earlier run)
    # wires from that run's producer node instead: the clips it consumes
    # are that node's products, not the raw assets.
    if task_book_node is not None:
        for asset_node_id in asset_node_ids:
            connect(asset_node_id, UUID(str(task_book_node.id)), "text")
    existing_producer_ids = await _existing_clip_producer_nodes(db, project_id)
    clip_roots = [
        s
        for s in steps
        if s.kind in _CLIP_FAMILY_KINDS
        and node_of(s) is not None
        and not any(
            (by_id.get(str(u)) or WorkflowStep()).kind in _CLIP_FAMILY_KINDS
            for u in (s.inputs or [])
        )
    ]
    writer_heads = [
        s
        for s in steps
        if s.kind.startswith("write_") and node_of(s) is not None
    ]
    # The asset's flow type is its own truth: media assets carry the video
    # flow into clip roots; text-only assets (transcripts / pasted text)
    # carry text everywhere — a "video" edge from a transcript would be a
    # lie (and the port law rejects it). Source consumers (select_clips /
    # materialize_source) ALWAYS eat the raw asset; only modifiers hanging
    # off no in-run producer eat the existing clips' producer node.
    from app.models.schemas import AssetType  # deferred: schema leaf

    _MEDIA_TYPES = {AssetType.VIDEO, AssetType.AUDIO, AssetType.IMAGE, AssetType.SLIDES}
    _SOURCE_CONSUMERS = {"select_clips", "materialize_source"}
    for step in clip_roots:
        target = node_id_by_key[_fill_key_for_step(step)]
        if step.kind not in _SOURCE_CONSUMERS and existing_producer_ids:
            for producer_id in existing_producer_ids:
                connect(producer_id, target, "video")
            continue
        for asset_node_id, asset in zip(asset_node_ids, assets):
            connect(
                asset_node_id,
                target,
                "video" if asset.type in _MEDIA_TYPES else "text",
            )
    for asset_node_id, asset in zip(asset_node_ids, assets):
        for step in writer_heads:
            connect(asset_node_id, node_id_by_key[_fill_key_for_step(step)], "text")
    if pending_edges:
        await apply_wiring_ops(db, project_id, pending_edges)

    logger.info(
        "graph_stamped",
        run_id=str(run.id),
        nodes=len(node_id_by_key) + (1 if task_book_node is not None else 0),
        edges=len(pending_edges),
    )


def _graph_kind_of(step: WorkflowStep) -> str:
    """Step kind → the graph node's five-type (简报 §3 migration mapping)."""
    if step.kind == "research":
        return "agent"
    if step.kind in _PROCESSOR_KINDS:
        return "processor"
    return "generator"


def _frame_class_of(fam_steps: list[WorkflowStep]) -> str:
    """The node's reserved-frame size class (graph_store._FRAME_CLASS): the
    clip family's product region is the 9:16-capable media card; writers /
    research reserve the text card. Assets / documents derive from kind."""
    if any(s.kind in _CLIP_FAMILY_KINDS for s in fam_steps):
        return "clip"
    return "text"


async def _existing_clip_producer_nodes(db: AsyncSession, project_id: UUID) -> list[UUID]:
    """The graph nodes that produced the project's CURRENT clips (mode②'s
    "act on existing clips" wiring source): clip outputs → their producing
    steps → those steps' graph back-pointers. Empty when the clips predate
    the graph (asset-feed fallback wins then)."""
    rows = list(
        (
            await db.execute(
                select(Output.workflow_step_id).where(
                    Output.project_id == project_id,
                    Output.type == "clip",
                    Output.workflow_step_id.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    steps = list(
        (
            await db.execute(select(WorkflowStep).where(WorkflowStep.id.in_(rows)))
        )
        .scalars()
        .all()
    )
    seen: dict[UUID, None] = {}
    for step in steps:
        node_id = (step.spec or {}).get("graph_node_id")
        if node_id:
            seen[UUID(str(node_id))] = None
    return list(seen)


def _params_of(step: WorkflowStep) -> dict[str, Any]:
    """The node's factsbar params (deterministic facts: slot / language /
    count / aspect — never runtime state)."""
    spec = step.spec or {}
    params: dict[str, Any] = {}
    for key in ("slot", "target_language", "bilingual", "fork", "aspect", "mood", "target_id"):
        if spec.get(key) is not None:
            params[key] = spec[key]
    return params


def _family_estimate(fam_steps: list[WorkflowStep]) -> dict | None:
    """The node's quotation = its internal step family's estimate fold
    (报价 = fold, the node卡面空态估价的存储侧). All-NULL → None (未估价)."""
    from app.pipeline.graph import fold_estimates  # deferred: kernel leaf

    quoted = [s.estimate for s in fam_steps if s.estimate]
    return fold_estimates(quoted) if quoted else None


def _task_book_text(steps: list[WorkflowStep]) -> str | None:
    """The task-book document's birth text — the compile-time task book the
    plan node was stamped with (Plan._book_summary's one source). The plan
    step's runtime book_summary overwrites it at back-write time (same
    source, no flicker)."""
    plan_step = next((s for s in steps if s.kind == "plan"), None)
    if plan_step is None:
        return None
    task_book = (plan_step.spec or {}).get("task_book") or {}
    slots_raw = task_book.get("slots") or []
    if not slots_raw:
        return None
    from app.models.schemas import IntentSlot  # deferred: schema leaf
    from app.pipeline.node_runners import Plan  # deferred: runner crew

    return Plan._book_summary(
        [IntentSlot.model_validate(s) for s in slots_raw],
        task_book.get("target_language") or "en",
    )


async def sync_graph_node_for_step(db: AsyncSession, step: WorkflowStep) -> None:
    """Back-write (the orchestrator's execute_step hook): re-aggregate the
    owning node's state from its internal step family and back-write the
    landed product references. No-op for steps outside the graph (render,
    pre-K2 runs). Flush-only — commits with the step's own write point
    (ADR-050 session discipline: same session, same commit)."""
    node_id = (step.spec or {}).get("graph_node_id")
    if not node_id:
        return
    node = await db.get(GraphNode, UUID(str(node_id)))
    if node is None:
        return
    family_ids = [UUID(str(s)) for s in (node.spec or {}).get("step_ids") or []]
    if not family_ids:
        return
    family = list(
        (
            await db.execute(select(WorkflowStep).where(WorkflowStep.id.in_(family_ids)))
        )
        .scalars()
        .all()
    )
    node.state = _aggregate_family([str(s.status) for s in family])
    # The task-book document's text rides the plan step's runtime book — the
    # refined book_summary overwrites the compile-time fallback when planning
    # lands (same source as the stamp, no flicker).
    if node.kind == "document" and (node.spec or {}).get("role") == _TASK_BOOK_ROLE:
        plan_step = next((s for s in family if s.kind == "plan"), None)
        book_summary = ((plan_step.spec or {}).get("book_summary")) if plan_step else None
        if book_summary and book_summary != (node.spec or {}).get("text"):
            node.spec = {**(node.spec or {}), "text": book_summary}
    output_ids = [str(ref) for s in family for ref in (s.output_refs or [])]
    if output_ids != ((node.spec or {}).get("output_ids") or []):
        node.spec = {**(node.spec or {}), "output_ids": output_ids}
