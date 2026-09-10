"""Graph fill (ADR-057 K2; K5 draft stamp) — the run/draft → graph writes.

双写期 (the double-write period): ``create_run`` keeps materializing
``workflow_steps`` exactly as before (the execution ledger — billing
capture / metering / retries ride it), and ADDITIONALLY stamps the run's
intent onto the persistent graph (the product face).

Three directions:

- **run stamp** (``stamp_run_graph``): compiled steps → graph nodes/edges
  via the wiring layer (the graph's only write door — zero bypass). Node
  identity is idempotent (``spec.fill_key``): a re-run of the same slot
  REUSES its node (spec refreshed, state re-queued), a new slot grows a
  node; the graph is edited continuously, never re-grown wholesale.
  Steps carry the back-pointer (``step.spec.graph_node_id``) and nodes
  carry their internal workflow (``spec.step_ids``) — composition, never
  projection: steps stay step-grained INSIDE the node.
- **draft stamp** (``stamp_draft_graph``, K5): the docked task book's
  chain dry-run compiles through the birthplace's own compile and stamps
  the SAME graph as DRAFT nodes (图先展示后运行 — the canvas previews the
  whole chain before a credit moves; Start fills these very nodes in
  place, same deterministic compile → same fill keys).
  ``clear_draft_graph`` tears the unconfirmed preview down (bail /
  uncompilable re-dock).
- **back-write** (``sync_graph_node_for_step``): the orchestrator's
  execute_step calls this at every step terminal — the node's state is the
  aggregate of its internal step family (the retired canvas projection's
  aggregateStatus logic's server-side home), and landed outputs back-write
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
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Asset, GraphEdge, GraphNode, Output, Project, WorkflowRun, WorkflowStep
from app.pipeline.graph import NODE_KINDS
from app.pipeline.graph_store import _TASK_BOOK_ROLE, apply_wiring_ops
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

# 转写稿 document (ADR-057 document 型第二实例): the asset's ASR transcript /
# extracted text as a first-class card. research brief (第三实例): the bounded
# loop's closing artifact as its own card, fed by the agent node.
# (_TASK_BOOK_ROLE's one home is graph_store — the door owns the graph's role
# vocabulary.)
_TRANSCRIPT_ROLE = "transcript"
_RESEARCH_BRIEF_ROLE = "research_brief"
_RESEARCH_BRIEF_KEY = "research_brief"

# States a DRAFT re-stamp may revisit (K5): a live node (queued/running), a
# finished one (done), or one mid-revision (stale) belongs to an earlier
# run's graph truth — the new book's preview never clobbers them (edges
# still derive to them; the run's own stamp re-fills them for real).
_DRAFT_RESTAMP_STATES = frozenset({"draft", "failed", "skipped"})


class _DraftStep:
    """A compile-time stand-in for WorkflowStep (stamp_draft_graph): the
    dry-run compile's _NodeSpec projected to the step shape the stamp core
    reads (id / kind / seq / spec / inputs / estimate). Never persisted —
    Start's birthplace re-compiles and the real steps take over (the same
    deterministic compile → the same fill keys → the draft nodes fill in
    place, never twins)."""

    __slots__ = ("id", "kind", "seq", "spec", "inputs", "estimate")

    def __init__(self, kind: str, seq: int, spec: dict, estimate: dict | None) -> None:
        from uuid import uuid4

        self.id = uuid4()
        self.kind = kind
        self.seq = seq
        self.spec = spec
        self.inputs: list[str] = []
        self.estimate = estimate


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
    canvas projection's aggregateStatus, server-side form): failure always
    visible, then liveness, then terminal honesty (all skipped = skipped)."""
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
    door (edges cascade structurally), and its 转写稿 document goes with it
    (the artifact's owner is gone). Absent node = pre-K2 asset, skip."""
    existing = list(
        (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.project_id == project_id,
                    GraphNode.spec["asset_id"].as_string() == str(asset_id),
                )
            )
        )
        .scalars()
        .all()
    )
    victims = [
        n
        for n in existing
        if n.kind == "asset"
        or (n.kind == "document" and (n.spec or {}).get("role") == _TRANSCRIPT_ROLE)
    ]
    if victims:
        await apply_wiring_ops(
            db,
            project_id,
            [{"op": "delete_node", "node": UUID(str(n.id))} for n in victims],
        )


async def stamp_transcript_node(
    db: AsyncSession, project_id: UUID, asset: Asset
) -> GraphNode | None:
    """转写稿 document (ADR-057 document 型第二实例 — 中间产物升一等公民):
    the asset's transcript / extracted text gets its own card the moment it
    exists, fed by the asset node (text edge — the artifact's derivation
    face). Born done: it is an intermediate artifact, not an execution unit
    (same ruling as the asset itself). Idempotent on role+asset_id; the text
    refreshes on reprocess. A LEAF face — consumers still wire from the asset
    (the execution truth); rewiring consumers arrives with 改稿驱动重剪.
    Flush-only."""
    text = asset.transcript or asset.extracted_text
    if not text:
        return None
    existing = (
        await db.execute(
            select(GraphNode).where(
                GraphNode.project_id == project_id,
                GraphNode.kind == "document",
                GraphNode.spec["role"].as_string() == _TRANSCRIPT_ROLE,
                GraphNode.spec["asset_id"].as_string() == str(asset.id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (existing.spec or {}).get("text") != text:
            existing.spec = {**(existing.spec or {}), "text": text}
        return existing
    asset_node = await stamp_asset_node(db, project_id, asset)
    delta = await apply_wiring_ops(
        db,
        project_id,
        [
            {
                "op": "add_node",
                "kind": "document",
                "spec": {
                    "role": _TRANSCRIPT_ROLE,
                    "asset_id": str(asset.id),
                    "text": text,
                },
                "after": [UUID(str(asset_node.id))],
            }
        ],
    )
    node = await db.get(GraphNode, delta.affected[0])
    assert node is not None
    node.state = "done"  # an artifact, not an execution unit
    return node


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
    await _stamp_graph_core(
        db,
        project,
        steps,
        run=run,
        ui_language=str((run.context or {}).get("ui_language") or "en"),
        draft=False,
        book_text=None,
    )


async def stamp_draft_graph(
    db: AsyncSession,
    project: Project,
    tasks: list,
    ui_language: str | None = None,
    book_text: str | None = None,
) -> None:
    """Draft stamp (ADR-057 K5) — the docked task book's graph twin.

    图先展示后运行: the moment a book docks, the canvas sees the whole chain
    as DRAFT nodes (「运行后生成 · 约 N 积分」 per node, zero consumption
    until Start) — the draft graph IS the "you'll get", the ADR-043 derived
    preview's replacement. The compile is the birthplace's own
    (``compile_graph`` with the same stills/materialize derivations), so
    fill keys collide with the run's and Start fills these very nodes in
    place. Raises ToolRejected / ValueError on an uncompilable chain — the
    caller degrades exactly like the quote-less dock (and tears the stale
    preview down via ``clear_draft_graph``). Flush-only.

    ``book_text`` (2026-09-10 全文卡律, 判词④): the book doc's face is the
    plan's FULL summary prose — the draft verdict's own ``answer`` (the
    LLM's plan restatement, 二源律①), passed by the dock. The deterministic
    slot composition (Plan.book_summary) is the fallback only — it is blind
    to transform chains (translate/dub carry no slot), and a condensed line
    on the card face is the 画蛇添足 the ruling kills.
    """
    from app.models.schemas import IntentSlot  # deferred: schema leaf
    from app.pipeline.graph import known_output_types  # deferred: kernel leaf
    from app.pipeline.node_runners import Plan  # deferred: runner crew
    from app.pipeline.orchestrator import (  # deferred: import cycle
        TaskSpec,
        _materialize_profile,
        _needs_stills_alignment,
        compile_graph,
        first_task_language,
    )
    from app.pipeline.step_context import _estimate_facts  # deferred: facts pack

    spec = TaskSpec(tasks=list(tasks))
    node_specs = compile_graph(
        spec,
        add_stills_align=await _needs_stills_alignment(db, project, spec),
        materialize_profile=await _materialize_profile(db, project, spec),
    )
    facts = await _estimate_facts(db, project)
    steps = [
        _DraftStep(
            ns.kind,
            ns.seq,
            dict(ns.spec or {}),
            NODE_KINDS[ns.kind].estimate(
                {
                    **facts,
                    "spec": ns.spec,
                    "input_kinds": [node_specs[i].kind for i in ns.inputs],
                }
            ),
        )
        for ns in node_specs
    ]
    for step, ns in zip(steps, node_specs, strict=True):
        step.inputs = [str(steps[i].id) for i in ns.inputs]
    # The draft book's text: the dock's LLM prose wins (the parameter);
    # the deterministic composition is the fallback for a prose-less caller.
    if book_text is None:
        parsed = [
            IntentSlot.model_validate(s.spec["slot"])
            for s in steps
            if (s.spec or {}).get("slot")
        ]
        intent_slots = [s for s in parsed if s.type in known_output_types()]
        target_language = first_task_language(tasks) or project.language or "en"
        book_text = Plan.book_summary(intent_slots, target_language)
    await _stamp_graph_core(
        db,
        project,
        steps,
        run=None,
        # None-tolerant at the boundary (2026-09-09): callers pass the
        # request-context locale bare, which is None for a client without
        # Accept-Language — compose_spec_prompt's .startswith crashed the
        # whole book turn. Same default seat as stamp_run_graph above.
        ui_language=ui_language or "en",
        draft=True,
        book_text=book_text,
    )


async def clear_draft_graph(db: AsyncSession, project_id: UUID) -> None:
    """Tear down the unconfirmed book's graph (bail / a re-dock whose chain
    no longer compiles): draft-state generation nodes go, and the draft-born
    task-book document with them (a RUN-born book — ``spec.run_id`` present
    — is history and stays). Asset nodes are the project's inputs, never
    the book's — they stay. Flush-only."""
    nodes = list(
        (
            await db.execute(
                select(GraphNode).where(GraphNode.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    victims = [
        n
        for n in nodes
        if n.kind != "asset"
        and (
            str(n.state) == "draft"
            or (
                n.kind == "document"
                and (n.spec or {}).get("role") == _TASK_BOOK_ROLE
                and not (n.spec or {}).get("run_id")
            )
        )
    ]
    if victims:
        await apply_wiring_ops(
            db,
            project_id,
            [{"op": "delete_node", "node": UUID(str(n.id))} for n in victims],
        )


async def _stamp_graph_core(
    db: AsyncSession,
    project: Project,
    steps: list,
    *,
    run: WorkflowRun | None,
    ui_language: str,
    draft: bool,
    book_text: str | None,
) -> None:
    """The one topology stamper behind the run fill and the draft preview
    (K5 — ONE source, zero drift: the draft's graph and the run's graph are
    the same derivation over the same compile).

    ``draft=False`` (run fill): nodes leave at state=queued, steps back-point
    to their nodes, the task book queues with its prelude. ``draft=True``
    (book dock): nodes leave at state=draft with no run/step linkage, only
    _DRAFT_RESTAMP_STATES nodes are re-stamped, and draft-state orphans of
    the previous dock are torn down (the run fill never deletes)."""
    project_id = UUID(str(project.id))
    run_id_str = str(run.id) if run is not None else None

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
    # revise_script is a TARGETED morph (K4): it folds into the node that
    # owns its target output — 修订 = 原地图变更, the revision never grows a
    # twin node. The target's producing step lives outside this run, so the
    # fill key is resolved in one batched lookup (missing/predated target →
    # the bare-kind fallback family, same as any unrecognized step).
    revise_target_keys: dict[str, str] = {}  # revise step id → fill key
    revise_steps = [s for s in steps if s.kind == "revise_script"]
    if revise_steps:
        target_ids = [
            UUID(str((s.spec or {}).get("target_id")))
            for s in revise_steps
            if (s.spec or {}).get("target_id")
        ]
        if target_ids:
            targets = list(
                (await db.execute(select(Output).where(Output.id.in_(target_ids))))
                .scalars()
                .all()
            )
            producer_ids = [
                t.workflow_step_id for t in targets if t.workflow_step_id is not None
            ]
            producers_by_id = (
                {
                    str(p.id): p
                    for p in (
                        await db.execute(
                            select(WorkflowStep).where(WorkflowStep.id.in_(producer_ids))
                        )
                    )
                    .scalars()
                    .all()
                }
                if producer_ids
                else {}
            )
            key_by_output = {
                str(t.id): _fill_key_for_step(producers_by_id[str(t.workflow_step_id)])
                for t in targets
                if t.workflow_step_id is not None
                and str(t.workflow_step_id) in producers_by_id
            }
            for s in revise_steps:
                key = key_by_output.get(str((s.spec or {}).get("target_id") or ""))
                if key:
                    revise_target_keys[str(s.id)] = key

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
        if step.kind == "revise_script" and str(step.id) in revise_target_keys:
            # The revision rides its TARGET's node (原地图变更 — the same
            # fill key, so the reuse path re-queues the node with the new
            # program instead of growing a revise twin).
            family_for(revise_target_keys[str(step.id)], "generator")["steps"].append(step)
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

    # Orphan sweep (draft only): a re-docked chain replaces the last one —
    # draft-state nodes whose slot vanished from the new compile are torn
    # down through the same wiring door. The task-book document is never an
    # orphan (the draft always re-ensures its book below); live/finished
    # nodes are history, never the preview's business. The run fill never
    # deletes — its graph only grows / re-fills.
    if draft:
        orphans = [
            n
            for n in existing_nodes
            if n.kind != "asset"
            and str(n.state) == "draft"
            and not (
                n.kind == "document" and (n.spec or {}).get("role") == _TASK_BOOK_ROLE
            )
            and not (
                # The brief doc lives as long as its research is in the chain
                n.kind == "document"
                and (n.spec or {}).get("role") == _RESEARCH_BRIEF_ROLE
                and "research" in families
            )
            and (n.spec or {}).get("fill_key") not in families
        ]
        if orphans:
            orphan_ids = {UUID(str(n.id)) for n in orphans}
            await apply_wiring_ops(
                db,
                project_id,
                [{"op": "delete_node", "node": node_id} for node_id in orphan_ids],
            )
            by_fill_key = {
                k: n for k, n in by_fill_key.items() if UUID(str(n.id)) not in orphan_ids
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
        # 转写稿 document 随素材处理落地（幂等；无转写文本的素材跳过）——
        # 上传时处理、run 内 preprocess、存量回填三条路在这一个 ensure 汇合。
        await stamp_transcript_node(db, project_id, asset)

    # ── 4. The task-book document (the plan prelude's artifact — FLORA
    # text-node form; the prelude's steps are its internal workflow). Run
    # mode: only a run WITH a prelude births it — a targeted render/hook
    # scope never grows an empty book card. Draft mode (K5): the book
    # ALWAYS has its face — it is the confirm beat's canvas anchor; its
    # text is the dock-composed summary (the runtime plan's back-write
    # re-composes the identical line). A run-born book (spec.run_id) keeps
    # its historical text through a draft — the bail stays honest.
    prelude_steps = [s for s in steps if s.kind in _PRELUDE_KINDS]
    if book_text is None and not draft:
        book_text = _task_book_text(steps)
        if book_text is None and run is not None:
            # Transform chains carry no output slots — the deterministic
            # composition is blind to them. The run's LLM-given name
            # (ADR-058 二源律①, stamped into context at birth) is the
            # honest fallback face, never an empty card.
            book_text = (run.context or {}).get("name")
    book_newborn_id: UUID | None = None
    if task_book_node is None:
        if prelude_steps or draft:
            # Pinned id — the SAME batch's connect ops wire off it, so the
            # book's frame is born with full edge knowledge (布局一开始就定
            # 好, 2026-09-08 用户拍板 — never stacked-then-repaired).
            book_newborn_id = uuid4()
            ops.append(
                {
                    "op": "add_node",
                    "id": book_newborn_id,
                    "kind": "document",
                    "spec": {
                        "role": _TASK_BOOK_ROLE,
                        "text": book_text,
                    },
                }
            )
    elif book_text or draft:
        # 全文卡律 (判词④) 的双面书文本律:
        if draft:
            # The dock owns the DRAFT book's face: a re-docked / revised
            # chain refreshes the prose (the LLM's latest plan restatement).
            # A run-born book (spec.run_id) is history — the bail keeps it
            # honest, untouched (the old guard's intent).
            if book_text and not (task_book_node.spec or {}).get("run_id"):
                task_book_node.spec = {**(task_book_node.spec or {}), "text": book_text}
        else:
            # Run fill never rewrites the book's face — the draft's prose is
            # the promise being executed. Only an EMPTY face (a run-born
            # book) takes the compile's composition / the run's name: the old
            # "same source, no flicker" back-write had TWO sources, and for
            # transform chains the composition is None — it WIPED the draft's
            # prose at Start.
            if book_text and not (task_book_node.spec or {}).get("text"):
                task_book_node.spec = {**(task_book_node.spec or {}), "text": book_text}
    task_book_id = book_newborn_id or (
        UUID(str(task_book_node.id)) if task_book_node is not None else None
    )

    # ── 5. Generation / processor / agent nodes (idempotent by fill_key) ──
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
        # A revise-headed family revisits an EXISTING node: the node's name,
        # its executable tool identity (spec.tool) and its structured params
        # (the slot the next revision re-runs from) stay the original
        # producer's — only the program line (prompt) refreshes to the
        # revision instruction.
        revise_headed = head.kind == "revise_script"
        # A stale node carries a DIRECTLY-EDITED program (edit_prompt — the
        # card-face edit / the wiring revision): the edit IS the program, so
        # the stamp must not overwrite it with the composed line.
        keep_edited_prompt = (
            reused is not None
            and reused.state == "stale"
            and bool((reused.spec or {}).get("prompt"))
        )
        if reused is not None:
            node_id_by_key[key] = UUID(str(reused.id))
            if draft and str(reused.state) not in _DRAFT_RESTAMP_STATES:
                # A live / finished / mid-revision node belongs to an
                # earlier run's truth — the draft preview leaves it
                # untouched (edges still derive to it via the key map).
                continue
            # The node is being re-filled: refresh its program + internal
            # workflow and re-queue it (修订/重跑 = 原地图变更, never a twin).
            # spec.output_ids SURVIVES the re-fill (版本累积): the new run's
            # products JOIN the node's version lineage at back-write time —
            # the card's pager flips across versions (原型 C 的 2/2), never
            # a cleared-then-refilled blank.
            reused.spec = {
                **(reused.spec or {}),
                **({} if revise_headed else {"summary": _node_label(head, ui_language)}),
                **({"prompt": prompt} if prompt and (revise_headed or not keep_edited_prompt) else {}),
                **({} if revise_headed else {"params": _params_of(head)}),
                "estimate": estimate,
                "frame_class": frame_class,
                **({} if revise_headed else {"tool": head.kind}),
                **(
                    {}
                    if draft
                    else {
                        "step_ids": [str(s.id) for s in fam_steps],
                        "run_id": run_id_str,
                    }
                ),
            }
            reused.state = "draft" if draft else "queued"
            continue
        # Pinned newborn id — known BEFORE the batch, so §7's connect ops
        # reference it directly and the door's frame settle sees the final
        # edge set (布局一开始就定好: the chain is born left→right, never
        # stacked at x=0 and repaired).
        newborn_id = uuid4()
        node_id_by_key[key] = newborn_id
        ops.append(
            {
                "op": "add_node",
                "id": newborn_id,
                "kind": fam["kind"],
                "spec": {
                    "fill_key": key,
                    "summary": _node_label(head, ui_language),
                    **({"prompt": prompt} if prompt else {}),
                    "params": _params_of(head),
                    "estimate": estimate,
                    "frame_class": frame_class,
                    "tool": head.kind,
                    **(
                        {}
                        if draft
                        else {
                            "step_ids": [str(s.id) for s in fam_steps],
                            "run_id": run_id_str,
                        }
                    ),
                    "output_ids": [],
                },
            }
        )

    # ── 6b-create. The research-brief document's add op rides the SAME
    # batch (document 型第三实例 — the loop's closing artifact gets its own
    # card, fed by the agent node): the agent's id is already pinned above,
    # so the after-shorthand resolves in-batch. The doc's state + the
    # agent↔brief link settle after the batch (§6b-tail).
    research_node_id = node_id_by_key.get("research")
    brief_newborn_id: UUID | None = None
    brief_doc: GraphNode | None = None
    if research_node_id is not None:
        brief_doc = by_fill_key.get(_RESEARCH_BRIEF_KEY)
        if brief_doc is None:
            brief_newborn_id = uuid4()
            ops.append(
                {
                    "op": "add_node",
                    "id": brief_newborn_id,
                    "kind": "document",
                    "spec": {
                        "role": _RESEARCH_BRIEF_ROLE,
                        "fill_key": _RESEARCH_BRIEF_KEY,
                    },
                    "after": [research_node_id],
                }
            )
            # Register the after-shorthand's derivation edge — §7's
            # re-ensure dedupes against it.
            have_edge.add((str(research_node_id), str(brief_newborn_id), "text"))
    brief_doc_id = brief_newborn_id or (
        UUID(str(brief_doc.id)) if brief_doc is not None else None
    )

    # ── 7. Edges (dedupe against the existing set) ────────────────────────
    want_edge: set[tuple[str, str, str]] = set()

    def connect(from_id: UUID, to_id: UUID, edge_type: str) -> None:
        want_edge.add((str(from_id), str(to_id), edge_type))
        if (str(from_id), str(to_id), edge_type) in have_edge or from_id == to_id:
            return
        have_edge.add((str(from_id), str(to_id), edge_type))
        ops.append(
            {"op": "connect", "from_node": from_id, "to_node": to_id, "edge_type": edge_type}
        )

    def node_of(step: WorkflowStep) -> UUID | None:
        return node_id_by_key.get(_fill_key_for_step(step))

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
                if task_book_id is not None:
                    connect(task_book_id, target_node, "ctx")
                continue
            source_node = node_of(upstream)
            if source_node is None:
                continue
            connect(
                source_node,
                target_node,
                "video" if upstream.kind in _CLIP_FAMILY_KINDS else "text",
            )
    # The brief doc's derivation edge (newborns got it from the after-
    # shorthand above; a reused doc re-ensures it — dedupe wins).
    if research_node_id is not None and brief_doc_id is not None:
        connect(research_node_id, brief_doc_id, "text")
    # Assets feed the graph: text into the task book and the writers, the
    # media flow into the clip-family roots (a root = no clip-family
    # upstream inside this run). A root that acts on the project's EXISTING
    # clips (mode② — the project already has clips from an earlier run)
    # wires from that run's producer node instead: the clips it consumes
    # are that node's products, not the raw assets.
    if task_book_id is not None:
        for asset_node_id in asset_node_ids:
            connect(asset_node_id, task_book_id, "text")
    existing_producer_ids = await _existing_clip_producer_nodes(db, project_id)
    clip_roots = [
        s
        for s in steps
        if s.kind in _CLIP_FAMILY_KINDS
        and node_of(s) is not None
        and not any(
            (upstream := by_id.get(str(u))) is not None
            and upstream.kind in _CLIP_FAMILY_KINDS
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

    # ── 7b. Edge reconciliation among the stamp's own members (边对账律,
    # ADR-062, 2026-09-10): the compiled topology OWNS every edge whose both
    # endpoints it claims — an existing edge the compile no longer emits is
    # a stale topology claim (born when an older compiler's law differed —
    # e.g. the pre-ADR-061 modifier chain), and the grow-only run fill would
    # otherwise carry it forever (have_edge only dedupes adds). Scope is the
    # ownership boundary: edges with an endpoint outside the claimed set
    # (other runs' history, transcript docs, revision wiring) are never the
    # stamp's business. Orphan-swept draft nodes self-exclude (they are
    # never in the claimed set, so their cascaded edges can't be mis-counted
    # as stale and double-deleted — the door would raise on the missing row).
    claimed: set[str] = {str(nid) for nid in node_id_by_key.values()}
    claimed.update(str(nid) for nid in asset_node_ids)
    for nid in (task_book_id, brief_doc_id, research_node_id):
        if nid is not None:
            claimed.add(str(nid))
    # Disconnects lead the batch: the door's cycle check walks the working
    # edge set, so a topology flip (old B→A stale, new A→B wanted) must see
    # the post-retraction set when its connect is checked — stale edges only
    # ever join reused (pre-existing) nodes, never this batch's newborns.
    disconnect_ops: list[dict[str, Any]] = []
    for e in existing_edges:
        triple = (str(e.from_node), str(e.to_node), str(e.edge_type))
        if (
            triple[0] in claimed
            and triple[1] in claimed
            and triple not in want_edge
        ):
            disconnect_ops.append(
                {
                    "op": "disconnect",
                    "from_node": UUID(triple[0]),
                    "to_node": UUID(triple[1]),
                    "edge_type": triple[2],
                }
            )

    # ── ONE batch — the graph's only write door ───────────────────────────
    # Adds carry pinned ids and every connect references them, so the door's
    # frame settle (画布定居取景) sees the FINAL edge set: the chain is born
    # left→right with full edge knowledge, never stacked-then-repaired.
    if disconnect_ops or ops:
        await apply_wiring_ops(db, project_id, disconnect_ops + ops)
    if book_newborn_id is not None:
        task_book_node = await db.get(GraphNode, book_newborn_id)

    # ── 6. Back-pointer the steps to their nodes + queue the task book ────
    # Run mode only — the draft's stand-in steps have no rows to point, and
    # the draft book keeps its birth state (its text is already present).
    if run is not None:
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
                "run_id": run_id_str,
            }
            task_book_node.state = "queued"
            for step in prelude_steps:
                step.spec = {**(step.spec or {}), "graph_node_id": str(task_book_node.id)}

    # ── 6b-tail. The research-brief document's state + the agent↔brief
    # link (document 型第三实例): draft = the preview's promise / run =
    # queued with its agent; the text back-writes at sync (the agent's
    # terminal mirrors onto it). A LEAF face — consuming writers still wire
    # from the agent (the execution truth), the doc is the artifact's
    # readable face.
    if research_node_id is not None:
        if brief_newborn_id is not None:
            brief_doc = await db.get(GraphNode, brief_newborn_id)
        if brief_doc is not None:
            # The agent↔brief link — sync_graph_node_for_step mirrors the
            # agent's terminal state + renders the brief onto the doc.
            agent_node = await db.get(GraphNode, research_node_id)
            if agent_node is not None and (agent_node.spec or {}).get(
                "brief_doc_id"
            ) != str(brief_doc.id):
                agent_node.spec = {
                    **(agent_node.spec or {}),
                    "brief_doc_id": str(brief_doc.id),
                }
            if draft:
                # A live/finished brief doc is an earlier run's truth — the
                # preview leaves it (the generation nodes' own restamp rule).
                if str(brief_doc.state) in _DRAFT_RESTAMP_STATES:
                    brief_doc.state = "draft"
            else:
                brief_doc.state = "queued"

    logger.info(
        "graph_stamped",
        run_id=str(run.id) if run is not None else None,
        draft=draft,
        nodes=len(node_id_by_key) + (1 if task_book_node is not None else 0),
        edges=sum(1 for op in ops if op["op"] == "connect"),
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
    plan node was stamped with (Plan.book_summary's one source). The plan
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

    return Plan.book_summary(
        [IntentSlot.model_validate(s) for s in slots_raw],
        task_book.get("target_language") or "en",
    )


def _research_brief_text(brief: dict) -> str | None:
    """The brief document's body: summary + key facts (+ the honest caveat)
    — every line is the loop's own words, no fabricated labels."""
    lines: list[str] = []
    summary = str(brief.get("summary") or "").strip()
    if summary:
        lines.append(summary)
    for fact in (brief.get("key_facts") or [])[:6]:
        fact = str(fact).strip()
        if fact:
            lines.append(f"• {fact}")
    caveat = str(brief.get("caveat") or "").strip()
    if caveat:
        lines.append(f"⚠ {caveat}")
    return "\n".join(lines) or None


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
    # 版本累积 (ADR-057 — the pager's version lineage): the new terminal's
    # landed products JOIN the node's existing versions instead of replacing
    # them — a revision's old and new products stay flippable on the card
    # (原型 C 的 2/2); deletions filter at read time (visibility join).
    landed = [str(ref) for s in family for ref in (s.output_refs or [])]
    output_ids = list(
        dict.fromkeys([*((node.spec or {}).get("output_ids") or []), *landed])
    )
    if output_ids != ((node.spec or {}).get("output_ids") or []):
        node.spec = {**(node.spec or {}), "output_ids": output_ids}
    # The research loop's brief document mirrors its agent node: state in
    # lockstep (queued → running → done/failed with the loop), text = the
    # closing artifact rendered the moment it exists.
    if node.kind == "agent":
        doc_id = (node.spec or {}).get("brief_doc_id")
        if doc_id:
            doc = await db.get(GraphNode, UUID(str(doc_id)))
            if doc is not None:
                doc.state = node.state
                brief = (step.spec or {}).get("research_brief")
                text = _research_brief_text(brief) if isinstance(brief, dict) else None
                if text and text != (doc.spec or {}).get("text"):
                    doc.spec = {**(doc.spec or {}), "text": text}
