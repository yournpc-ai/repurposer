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

Migration mapping (词表 v3, ADR-076): assets → asset (媒介×manual) / plan
prelude → the task-book document / writers·research → text×generator /
quotes·carousel → image×generator / select_clips·translate·dub·modifiers →
video×editor (translate/dub 两站拆分: the asm family plus a table×manual
doc-station companion — key `{fill_key}#doc`, role = the doc_station
declaration, the persistent editable cue artifact's home) / revise folds
into its target's family / materialize_source·align_stills fold into the
nearest downstream family (the bare fill key grows no node — their step ids
ride the host's `step_ids`, the host root inherits eat-the-asset) / verify
folds into its executor's node. Render steps join NO family — their state
rides the output row's render_status (the node's product region carries it
in place).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AssetType
from app.models.tables import Asset, GraphEdge, GraphNode, Output, Project, WorkflowRun, WorkflowStep
from app.pipeline.graph import NODE_KINDS
from app.pipeline.graph_store import (
    _TASK_BOOK_ROLE,
    apply_wiring_ops,
    display_aspect_class,
    resolve_source_aspect,
)
from app.pipeline.outputs import compose_spec_prompt
from app.tools.captions.procedure import TRANSLATION_ARTIFACT_KEY

logger = structlog.get_logger()

# Step kinds of the plan prelude — the task-book document's internal
# workflow (the book's birth process: preprocess → persona ∥ understand (∥
# decompile when an exemplar is pinned) → (interrupt) → plan). Kind strings,
# same source as node_runners. decompile rides here (ADR-078): the compile
# injects it parallel to understand off preprocess, so it shares the book's
# internal workflow — never an independent canvas node.
_PRELUDE_KINDS = frozenset({"preprocess", "persona_bootstrap", "understand", "decompile", "interrupt", "plan"})

# Modifier kinds whose editor node carries NO prompt slot (deterministic
# 工序 — the program region stays empty until 批 B4's lever row; the prompt
# gate reads this set, 评审修正 P0-A). translate/dub/select_clips/writers/
# research keep the composed line in the transition (compose 本体 B5 才拆).
_NO_PROMPT_KINDS = frozenset({"materialize_source", "remove_filler", "add_music", "reframe_clip"})

# Folded kinds — they grow no node of their own; their step ids ride the
# nearest downstream family's `step_ids` (词表 v3 materialize 折叠, ADR-072
# ⑦; align_stills 现成先例). A folded step's bare fill key is never a
# family key, so `node_of` returns None and the step-input edge loop skips
# it structurally.
_FOLDED_KINDS = frozenset({"align_stills", "materialize_source"})

# Clip-family kinds — edges between these carry the video flow.
_CLIP_FAMILY_KINDS = frozenset({
    "select_clips", "materialize_source", "translate_clip", "dub_clip",
    "remove_filler", "add_music", "reframe_clip",
})

# 转写稿 document (ADR-057 document 型第二实例): the asset's ASR transcript /
# extracted text as a first-class card.
# (_TASK_BOOK_ROLE's one home is graph_store — the door owns the graph's role
# vocabulary.)
_TRANSCRIPT_ROLE = "transcript"

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


def _decl_of(kind: str) -> tuple[str, str]:
    """The canvas identity declaration for a step kind (词表 v3, ADR-076):
    (node_type, prototype) off the registered NodeBase (注册表纪律 — 禁平行
    映射表; this lookup replaced the retired _graph_kind_of central
    mapping). Unknown / legacy kinds read as text×manual — the full-text
    card is the safest reading."""
    node_cls = NODE_KINDS.get(kind)
    node_type = (node_cls.node_type if node_cls is not None else None) or "text"
    prototype = (node_cls.prototype if node_cls is not None else None) or "manual"
    return node_type, prototype


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


async def merge_translation_artifact(
    node_id: UUID, clip_entries: dict[str, Any]
) -> None:
    """Persist freshly translated cue rows onto the node's translation
    artifact (批 A2 — ADR-072 两站拆分). Own-session read-modify-write (the
    step_display jsonb discipline: never the runner session — its post-runner
    commit would flush a stale in-memory dict and clobber the merge), merging
    per-clip entries into the existing artifact so sibling clips survive.
    Mid-run by design: the translator's tokens are paid the moment the call
    lands — losing the artifact to a later failure would re-buy them."""
    from app.models.database import AsyncSessionLocal  # deferred: session home

    async with AsyncSessionLocal() as s:
        row = await s.get(GraphNode, node_id)
        if row is None:
            return
        artifact = dict((row.spec or {}).get(TRANSLATION_ARTIFACT_KEY) or {})
        clips = dict(artifact.get("clips") or {})
        clips.update(clip_entries)
        artifact["clips"] = clips
        await s.execute(
            update(GraphNode)
            .where(GraphNode.id == node_id)
            .values(
                spec=func.jsonb_set(
                    GraphNode.spec,
                    pg_array([TRANSLATION_ARTIFACT_KEY]),
                    func.to_jsonb(cast(artifact, JSONB)),
                    True,
                )
            )
        )
        await s.commit()


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
                GraphNode.type == "asset",
                GraphNode.spec["asset_id"].as_string() == str(asset.id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    # 素材节点同律 (2026-09-13): the source's real dims (client-probed at
    # upload → meta.width/height) shape its frame from birth — a 1:1 keynote
    # recording no longer letterboxes into the 16:9 default strip. Dims
    # unknown (API-path uploads — the chain-head probe lands after birth)
    # keep the default reservation.
    asset_meta = asset.meta if isinstance(asset.meta, dict) else {}
    aw, ah = asset_meta.get("width"), asset_meta.get("height")
    asset_frame_aspect = (
        display_aspect_class(aw, ah)
        if isinstance(aw, int) and isinstance(ah, int) and aw > 0 and ah > 0
        else None
    )
    delta = await apply_wiring_ops(
        db,
        project_id,
        [
            {
                "op": "add_node",
                "type": "asset",
                "spec": {
                    "asset_id": str(asset.id),
                    "asset_type": str(asset.type.value if hasattr(asset.type, "value") else asset.type),
                    "title": asset.title,
                    **(
                        {"frame_aspect": asset_frame_aspect}
                        if asset_frame_aspect
                        else {}
                    ),
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
        if n.type == "asset"
        or (n.type == "document" and (n.spec or {}).get("role") == _TRANSCRIPT_ROLE)
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
    Flush-only.

    上传即出生 (Phase 1, ADR-087 §2 R2 配套缓做项): an ASR-able / text-
    yielding asset births its transcript card AT UPLOAD in ``queued``
    (loading) — the card holds its seat on the canvas while the worker
    processes, and flips to ``done`` when the text lands (the completion
    path re-enters this same function), to ``failed`` if processing fails.
    Asset types without a text yield (image / voice_sample) never birth one.
    """
    text = asset.transcript or asset.extracted_text
    status = str(
        getattr(asset.processing_status, "value", asset.processing_status)
    ).lower()
    text_yielding = asset.type in (
        AssetType.VIDEO,
        AssetType.AUDIO,
        AssetType.TRANSCRIPT,
        AssetType.PAST_MATERIAL,
    )
    if not text and not text_yielding:
        return None
    existing = (
        await db.execute(
            select(GraphNode).where(
                GraphNode.project_id == project_id,
                GraphNode.type == "document",
                GraphNode.spec["role"].as_string() == _TRANSCRIPT_ROLE,
                GraphNode.spec["asset_id"].as_string() == str(asset.id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if text and (existing.spec or {}).get("text") != text:
            existing.spec = {**(existing.spec or {}), "text": text}
        # State follows ASR: text landed → done; processing failed → failed
        # (the 卡内红 face); completed without words (silence / empty
        # extraction) → done with an empty body, never a perpetual loading
        # card; still waiting → stays queued.
        if text or status == "completed":
            existing.state = "done"
        elif status == "failed":
            existing.state = "failed"
        return existing
    asset_node = await stamp_asset_node(db, project_id, asset)
    spec: dict = {"role": _TRANSCRIPT_ROLE, "asset_id": str(asset.id)}
    if text:
        spec["text"] = text
    delta = await apply_wiring_ops(
        db,
        project_id,
        [
            {
                "op": "add_node",
                "type": "document",
                "spec": spec,
                "after": [UUID(str(asset_node.id))],
            }
        ],
    )
    node = await db.get(GraphNode, delta.affected[0])
    assert node is not None
    # Born done when the text already exists (paste path bypasses the
    # worker); queued (loading) while ASR/extraction is still owed.
    node.state = "done" if text else "queued"
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
        if n.type != "asset"
        and (
            str(n.state) == "draft"
            or (
                n.type == "document"
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

    # The canvas's aspect truth (2026-09-13 用户拍板 — 产物卡跟源比例 +
    # 分档加宽): the project's media dims (probed at upload / processing into
    # meta.width/height) let an "original"-aspect chain reserve the source's
    # real display class at stamp time. Mixed / unknown shapes stay
    # "original" (the conservative default strip), never a coin flip.
    dims_rows = (
        await db.execute(
            select(Asset.meta).where(
                Asset.project_id == project_id,
                Asset.file_url.isnot(None),
            )
        )
    ).scalars().all()
    source_aspect = resolve_source_aspect(
        [
            (meta["width"], meta["height"])
            for meta in dims_rows
            if isinstance(meta, dict)
            and isinstance(meta.get("width"), int)
            and isinstance(meta.get("height"), int)
        ]
    )

    # ── 1. Classify the steps into node families ─────────────────────────
    # node_key → {"type": 媒介 type, "prototype": 能力原型, "steps": [step]};
    # every generation / processor / agent step owns or joins a node; the
    # prelude belongs to the task-book document; folded kinds (align_stills /
    # materialize_source) ride the nearest downstream family; revise rides
    # its target's; verify folds into its executor's node. render joins
    # nothing. 判族读注册表声明 (词表 v3, ADR-076 — _graph_kind_of 退役).
    families: dict[str, dict[str, Any]] = {}

    def family_for(key: str, decl: tuple[str, str]) -> dict[str, Any]:
        fam = families.get(key)
        if fam is None:
            fam = families[key] = {"type": decl[0], "prototype": decl[1], "steps": []}
        return fam

    by_id = {str(s.id): s for s in steps}
    # revise_script is a TARGETED morph (K4): it folds into the node that
    # owns its target output — 修订 = 原地图变更, the revision never grows a
    # twin node. The target's producing step lives outside this run, so the
    # fill key is resolved in one batched lookup (missing/predated target →
    # the bare-kind fallback family, same as any unrecognized step). The
    # family's canvas identity reads the TARGET producer's declaration
    # (the revise fold's hardcoded "generator" is retired with the five-type
    # vocabulary).
    revise_target_keys: dict[str, str] = {}  # revise step id → fill key
    revise_target_decls: dict[str, tuple[str, str]] = {}  # → (type, prototype)
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
            key_by_output: dict[str, str] = {}
            decl_by_output: dict[str, tuple[str, str]] = {}
            for t in targets:
                producer = (
                    producers_by_id.get(str(t.workflow_step_id))
                    if t.workflow_step_id is not None
                    else None
                )
                if producer is None:
                    continue
                key_by_output[str(t.id)] = _fill_key_for_step(producer)
                decl_by_output[str(t.id)] = _decl_of(producer.kind)
            for s in revise_steps:
                tid = str((s.spec or {}).get("target_id") or "")
                if tid in key_by_output:
                    revise_target_keys[str(s.id)] = key_by_output[tid]
                    revise_target_decls[str(s.id)] = decl_by_output.get(
                        tid, ("text", "generator")
                    )

    def family_owner_of(folded: WorkflowStep) -> Any | None:
        """The family a folded step (align_stills / materialize_source)
        rides: its nearest downstream consumer in the compile (the step
        whose inputs name it), resolved TRANSITIVELY when the consumer
        itself folds (stills profile: align_stills → materialize_source →
        translate_clip — both ride the translate family). None = no consumer
        in this run — the step joins nothing (its bare fill key grows no
        node, so `node_of` returns None and it is naturally skipped
        everywhere)."""
        seen: set[str] = set()
        current = folded
        while str(current.id) not in seen:
            seen.add(str(current.id))
            nxt = next(
                (
                    s
                    for s in steps
                    if s.kind not in _PRELUDE_KINDS
                    and s.kind not in ("verify", "render")
                    and str(current.id) in (str(i) for i in (s.inputs or []))
                ),
                None,
            )
            if nxt is None:
                return None
            if nxt.kind not in _FOLDED_KINDS:
                return nxt
            current = nxt
        return None

    for step in steps:
        if step.kind in _PRELUDE_KINDS or step.kind in ("render",):
            continue
        if step.kind == "verify":
            # The executor is the verify's first input (compile contract).
            executor = by_id.get(str((step.inputs or [None])[0]))
            if (
                executor is not None
                and executor.kind not in _PRELUDE_KINDS
                and executor.kind not in _FOLDED_KINDS
            ):
                family_for(_fill_key_for_step(executor), _decl_of(executor.kind))["steps"].append(step)
            continue
        if step.kind in _FOLDED_KINDS:
            owner = family_owner_of(step)
            if owner is not None:
                family_for(_fill_key_for_step(owner), _decl_of(owner.kind))["steps"].append(step)
            continue
        if step.kind == "revise_script" and str(step.id) in revise_target_keys:
            # The revision rides its TARGET's node (原地图变更 — the same
            # fill key, so the reuse path re-queues the node with the new
            # program instead of growing a revise twin).
            family_for(
                revise_target_keys[str(step.id)], revise_target_decls[str(step.id)]
            )["steps"].append(step)
            continue
        family_for(_fill_key_for_step(step), _decl_of(step.kind))["steps"].append(step)

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
            if n.type == "document" and (n.spec or {}).get("role") == _TASK_BOOK_ROLE
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
    # deletes — its graph only grows / re-fills. (The doc-station companion
    # sweeps with its family: its `{fill_key}#doc` key is in `families` only
    # while its asm's chain survives — see the sweep key set below.)
    if draft:
        sweep_keys = set(families) | {f"{key}#doc" for key in families}
        orphans = [
            n
            for n in existing_nodes
            if n.type != "asset"
            and str(n.state) == "draft"
            and not (
                n.type == "document" and (n.spec or {}).get("role") == _TASK_BOOK_ROLE
            )
            and (n.spec or {}).get("fill_key") not in sweep_keys
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
    # 转写稿文档按素材登记 (transcript → 译文稿/配音稿 的 text 边派生,
    # ADR-072 边派生新规 — the A3-lite read-face synthesis turned production):
    # asset id → its transcript document's id (textless assets have none).
    transcript_doc_by_asset: dict[str, UUID] = {}
    for asset in assets:
        node = await stamp_asset_node(db, project_id, asset)
        asset_node_ids.append(UUID(str(node.id)))
        # 转写稿 document 随素材处理落地（幂等；无转写文本的素材跳过）——
        # 上传时处理、run 内 preprocess、存量回填三条路在这一个 ensure 汇合。
        transcript_doc = await stamp_transcript_node(db, project_id, asset)
        if transcript_doc is not None:
            transcript_doc_by_asset[str(asset.id)] = UUID(str(transcript_doc.id))

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
                    "type": "document",
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

    # ── 5. Generation / editor / doc-station nodes (idempotent by fill_key) ──
    doc_pairs: list[tuple[UUID, UUID]] = []  # (doc station id, its asm id) — §7 wires them
    for key, fam in families.items():
        fam_steps = sorted(fam["steps"], key=lambda s: s.seq)
        # The family's head drives label / params / tool / prompt — folded
        # steps (align_stills / materialize_source) never head (their host
        # inherits the eat-the-asset root semantics, 评审修正 P0-C; the
        # family's tool identity stays the consumer's).
        head = next(
            (s for s in fam_steps if s.kind not in _FOLDED_KINDS and s.kind != "verify"),
            fam_steps[0],
        )
        # The doc-station declaration drives two per-family branches below
        # (the companion block + the estimate split) — resolve it once.
        head_cls = NODE_KINDS.get(head.kind)
        doc_role = str(head_cls.doc_station or "") if head_cls is not None else ""
        family_estimate = _family_estimate(fam_steps)
        # 两站估价拆分 (批 A4/C3, 评审修正 P0-D): doc 站 = token 段 (译者就是
        # 文档站的工序), asm 站 = units 段或 None (translate 的 asm 编译期
        # None = 「估价随运行」; voice_clones 归 asm——配音产物的声纹单位).
        # step.estimate 一律不动 — create_run 的 hold fold 步骤级报价不变.
        doc_estimate: dict | None = None
        estimate = family_estimate
        if doc_role:
            doc_estimate, estimate = _split_station_estimate(family_estimate)
        # 评审修正 P0-A (prompt 闸门随词表改判): the #doc companion is not a
        # family (文本站无 prompt 位, ADR-072 ③ — it is stamped in the
        # companion block below, never here); deterministic modifiers carry
        # no prompt slot; everything else keeps the composed / instruction /
        # query line exactly as the five-type era did (compose 本体 B5 才拆).
        prompt = (
            (
                compose_spec_prompt(head, ui_language)
                # revise_script / research carry their program in spec
                # directly (compose has no slot-shaped branch for them).
                or (head.spec or {}).get("instruction")
                or (head.spec or {}).get("query")
            )
            if head.kind not in _NO_PROMPT_KINDS
            else None
        )
        reused = by_fill_key.get(key)
        frame_class, frame_aspect = _frame_class_of(fam_steps)
        # "original" resolves to the source's real display class when the
        # source dims are known (比例跟源 — the card shapes itself to the
        # material, never a black-bar default strip); unknown / mixed keeps
        # the sentinel and its conservative reservation.
        if frame_aspect == "original" and source_aspect is not None:
            frame_aspect = source_aspect
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

        # ── 两站拆分 (ADR-072): the doc-station companion — ensured BEFORE
        # the reused branch so the draft-restamp guard's `continue` still
        # births and registers it (the migration path for pre-v3 rows: a
        # live legacy translate/dub node gains its companion here). The doc
        # never joins the family loop (§3.5.5-1: an empty-steps family would
        # explode `fam_steps[0]`; §6 back-pointing only knows the asm
        # family). Pinned id (任务书同款先定后连); no tool / prompt /
        # step_ids / output_ids — the persistent editable cue artifact is
        # its whole content (spec.role = the doc_station declaration).
        doc_node_id: UUID | None = None
        if doc_role:
            doc_key = f"{key}#doc"
            existing_doc = by_fill_key.get(doc_key)
            if existing_doc is not None:
                doc_node_id = UUID(str(existing_doc.id))
                # grow-only: kind / fill_key / role / text never migrate —
                # only the v3 marker refreshes (read-face mapping兜底归批 C4).
                if (existing_doc.spec or {}).get("prototype") != "manual":
                    existing_doc.spec = {**(existing_doc.spec or {}), "prototype": "manual"}
                # 两站估价归位 (C3): the doc's token section re-quotes with
                # every stamp, same law as the asm's estimate refresh.
                if (existing_doc.spec or {}).get("estimate") != doc_estimate:
                    existing_doc.spec = {
                        **(existing_doc.spec or {}), "estimate": doc_estimate
                    }
            else:
                doc_node_id = uuid4()
                ops.append(
                    {
                        "op": "add_node",
                        "id": doc_node_id,
                        "type": "table",
                        "spec": {
                            "fill_key": doc_key,
                            "role": doc_role,
                            "prototype": "manual",
                            # The text-lane frame reservation (340×560): the
                            # cue text lands mid-run and the client grows
                            # content-height inside it, never outgrowing it.
                            "frame_class": "text",
                            # C3 两站估价: the translator's token section
                            # lives on the doc station (capture-0 units).
                            "estimate": doc_estimate,
                        },
                    }
                )
            node_id_by_key[doc_key] = doc_node_id

        if reused is not None:
            node_id_by_key[key] = UUID(str(reused.id))
            if doc_node_id is not None:
                doc_pairs.append((doc_node_id, UUID(str(reused.id))))
            if draft and str(reused.state) not in _DRAFT_RESTAMP_STATES:
                # A live / finished / mid-revision node belongs to an
                # earlier run's truth — the draft preview leaves its program
                # and state untouched (edges still derive to it via the key
                # map). The doc-station LINK is still written: additive,
                # idempotent, content-free (and it lets the node's next sync
                # mirror the companion immediately).
                if doc_node_id is not None and (reused.spec or {}).get(
                    "doc_node_id"
                ) != str(doc_node_id):
                    reused.spec = {
                        **(reused.spec or {}),
                        "doc_node_id": str(doc_node_id),
                    }
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
                "prototype": fam["prototype"],
                "estimate": estimate,
                "frame_class": frame_class,
                **({"frame_aspect": frame_aspect} if frame_aspect else {}),
                **({} if revise_headed else {"tool": head.kind}),
                **({"doc_node_id": str(doc_node_id)} if doc_node_id is not None else {}),
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
        if doc_node_id is not None:
            doc_pairs.append((doc_node_id, newborn_id))
        ops.append(
            {
                "op": "add_node",
                "id": newborn_id,
                "type": fam["type"],
                "spec": {
                    "fill_key": key,
                    "summary": _node_label(head, ui_language),
                    **({"prompt": prompt} if prompt else {}),
                    "params": _params_of(head),
                    "prototype": fam["prototype"],
                    "estimate": estimate,
                    "frame_class": frame_class,
                    **({"frame_aspect": frame_aspect} if frame_aspect else {}),
                    "tool": head.kind,
                    **({"doc_node_id": str(doc_node_id)} if doc_node_id is not None else {}),
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
    # The doc station's two text legs (ADR-072 边派生新规 — 文流经 doc 站
    # 中转, the transcript → 成片 direct edge is never stamped): the asm's
    # own words arrive from its doc station…
    for doc_id, asm_id in doc_pairs:
        connect(doc_id, asm_id, "text")
    # Assets feed the graph: text into the task book and the writers, the
    # media flow into the clip-family roots. A root = a clip-family node
    # with NO clip-family upstream mapped to a DIFFERENT node (folded
    # upstreams — materialize_source / align_stills — map to None and never
    # disqualify: their host IS the chain's head). A root that acts on the
    # project's EXISTING clips (mode② — the project already has clips from
    # an earlier run) wires from that run's producer node instead: the clips
    # it consumes are that node's products, not the raw assets.
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
            and (up_node := node_of(upstream)) is not None
            and up_node != node_of(s)
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
    # lie (and the port law rejects it). Source consumers (select_clips)
    # ALWAYS eat the raw asset. 评审修正 P0-C (materialize 折叠的宿主继承):
    # materialize_source injects only under the media/stills profile (mode②
    # existing never injects — orchestrator._compile_task_list), so a run
    # CONTAINING one materializes the raw source and EVERY root of that run
    # inherits eat-the-asset — otherwise an old project with existing clips
    # would wire the whole-source chain from the old producer (画布撒谎).
    from app.models.schemas import AssetType  # deferred: schema leaf

    _MEDIA_TYPES = {AssetType.VIDEO, AssetType.AUDIO, AssetType.IMAGE, AssetType.SLIDES}
    _SOURCE_CONSUMERS = {"select_clips", "materialize_source"}
    run_materializes = any(s.kind == "materialize_source" for s in steps)
    asset_fed = False
    for step in clip_roots:
        key = _fill_key_for_step(step)
        target = node_id_by_key[key]
        if (
            step.kind not in _SOURCE_CONSUMERS
            and not run_materializes
            and existing_producer_ids
        ):
            for producer_id in existing_producer_ids:
                connect(producer_id, target, "video")
            continue
        asset_fed = True
        for asset_node_id, asset in zip(asset_node_ids, assets):
            connect(
                asset_node_id,
                target,
                "video" if asset.type in _MEDIA_TYPES else "text",
            )
    # …and the transcript document feeds every doc station its words
    # translate/dub (按 asset_id 找 transcript 文档 — the A3-lite read-face
    # synthesis turned production; mode② chains eat existing clips, so the
    # lineage edge stays the lite patch's business, never stamped here).
    if asset_fed:
        for transcript_doc_id in transcript_doc_by_asset.values():
            for doc_id, _asm_id in doc_pairs:
                connect(transcript_doc_id, doc_id, "text")
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
    if task_book_id is not None:
        claimed.add(str(task_book_id))
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

    # ── 6b. The doc-station companions mirror their asm's state law (两站
    # 双站 sync 之前的第一拍): run = queued with its assembly; draft = the
    # preview's promise (a live/finished doc is an earlier run's truth — the
    # same restamp guard as the asm's). Afterwards sync_graph_node_for_step
    # keeps each doc in lockstep with its asm and renders the cue text.
    for doc_id, _asm_id in doc_pairs:
        doc = await db.get(GraphNode, doc_id)
        if doc is None:
            continue
        if draft:
            if str(doc.state) in _DRAFT_RESTAMP_STATES:
                doc.state = "draft"
        else:
            doc.state = "queued"

    logger.info(
        "graph_stamped",
        run_id=str(run.id) if run is not None else None,
        draft=draft,
        nodes=len(node_id_by_key) + (1 if task_book_node is not None else 0),
        edges=sum(1 for op in ops if op["op"] == "connect"),
    )


def _frame_class_of(fam_steps: list[WorkflowStep]) -> tuple[str, str | None]:
    """The node's reserved-frame size class (graph_store._FRAME_CLASS) plus
    the clip family's frame aspect (graph_store._CLIP_FRAME_H): writers /
    research reserve the text card; a clip-family node reserves its
    ASPECT-EXACT height — the chain's explicit aspect (select_clips' spec)
    wins, otherwise "original" (比例跟源 — whole-source / transform chains
    never reframe, tools/clips/materialize.py 2026-08-17 拍板), so a
    full-video fork no longer reserves the 9:16 max it will never fill (the
    660-reservation / 278-render dead-air walkthrough, 2026-09-11). The
    aspect rides spec.frame_aspect — a FRAME-only key: never in _params_of's
    factsbar whitelist, never read by the runtime tools (node.spec.aspect
    stays the chain's own business). Assets / documents derive from kind."""
    if any(s.kind in _CLIP_FAMILY_KINDS for s in fam_steps):
        for s in fam_steps:
            aspect = (s.spec or {}).get("aspect")
            if aspect:
                return "clip", str(aspect)
        return "clip", "original"
    return "text", None


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


def _split_station_estimate(estimate: dict | None) -> tuple[dict | None, dict | None]:
    """两站估价拆分 (批 A4/C3, 评审修正 P0-D): a doc-station family's folded
    quotation splits into the DOC station's token section (the translator's
    work — the cue rows' price; translate 全量, dub 的 prompt/completion
    段) and the ASM station's mechanical-units section (tts_chars /
    voice_clones — the voiced product's units). translate quotes tokens
    only → its asm is None (the compile-time-unquotable render fan-out =
    「估价随运行」, ADR-063 诚实面). step.estimate itself is never touched
    — create_run's hold folds the step-level quotation (不变性), and the
    two sections fold back to the original whole (draft 确认拍总额不破,
    §3.5.5-6)."""
    if not estimate:
        return None, None
    doc = {
        "prompt_tokens": list(estimate.get("prompt_tokens") or [0, 0]),
        "completion_tokens": list(estimate.get("completion_tokens") or [0, 0]),
        "units": {},
    }
    units = estimate.get("units") or {}
    asm = (
        {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": dict(units)}
        if units
        else None
    )
    return doc, asm


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


def _fmt_cue_time(seconds: Any) -> str:
    """A cue timestamp as m:ss (the doc station's row prefix)."""
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60}:{total % 60:02d}"


def _translation_artifact_text(artifact: Any) -> str | None:
    """The doc station's readable face (ADR-072 两站拆分的文档站卡面): the
    translation artifact's cue rows baked as `start–end text` lines, clips
    separated by a blank line. The rows render as stored — user edits
    included (the edit IS the artifact's content; 词级时间戳永远不动)."""
    if not isinstance(artifact, dict):
        return None
    clips = artifact.get("clips")
    if not isinstance(clips, dict) or not clips:
        return None
    blocks: list[str] = []
    for entry in clips.values():
        rows = entry.get("rows") if isinstance(entry, dict) else None
        if not isinstance(rows, list):
            continue
        lines = [
            f"{_fmt_cue_time(row.get('start'))}–{_fmt_cue_time(row.get('end'))} "
            f"{str(row.get('text') or '').strip()}"
            for row in rows
            if isinstance(row, dict)
        ]
        if lines:
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks) or None


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
    # 失败人话行原地表达 (2026-09-11): the failed card reads the family's
    # baked human line (the orchestrator's user_error_line on the failed
    # step), never the generic 「运行失败」 — spec.error is bake-at-write
    # (UI locale at fail time, same discipline as step summaries) and clears
    # the moment the family recovers (a rerun never leaves a stale epitaph).
    if node.state == "failed":
        failed_step = next((s for s in family if s.status == "failed" and s.error), None)
        error_line = (failed_step.error or "")[:500] if failed_step else None
    else:
        error_line = None
    if error_line != ((node.spec or {}).get("error") or None):
        node.spec = {
            **(node.spec or {}),
            **({"error": error_line} if error_line else {}),
        }
        if not error_line:
            node.spec.pop("error", None)
    # The task-book document's text rides the plan step's runtime book — the
    # refined book_summary overwrites the compile-time fallback when planning
    # lands (same source as the stamp, no flicker).
    if node.type == "document" and (node.spec or {}).get("role") == _TASK_BOOK_ROLE:
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
    # writer 升 text 型 (词表 v3): the landed product's content back-writes
    # the node's spec.text — the 全文卡 reads the node's own words (the
    # latest Output of THIS step; the single-row-per-step invariant is kept
    # by derivative_dispatch's sweep). A revision's morph reassigns the
    # row's workflow_step_id to the revise step, so a revise run refreshes
    # the same card's text.
    if (node.spec or {}).get("tool") in ("write_post", "write_article") and (
        step.output_refs
    ):
        latest = (
            await db.execute(
                select(Output)
                .where(Output.workflow_step_id == step.id)
                .order_by(Output.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        content = ((latest.payload or {}).get("content")) if latest is not None else None
        if (
            isinstance(content, str)
            and content
            and content != (node.spec or {}).get("text")
        ):
            node.spec = {**(node.spec or {}), "text": content}
    # research 塌缩单节点 (词表 v3 — the brief doc / agent mirror retired):
    # the bounded loop's closing artifact renders straight onto the research
    # node's own spec.text.
    if (node.spec or {}).get("tool") == "research":
        brief = (step.spec or {}).get("research_brief")
        text = _research_brief_text(brief) if isinstance(brief, dict) else None
        if text and text != (node.spec or {}).get("text"):
            node.spec = {**(node.spec or {}), "text": text}
    # 两站双站镜像 (ADR-072): the doc station tracks its asm's state in
    # lockstep and renders the translation artifact's cue rows as its
    # readable text (`start–end text` per row — user edits included: the
    # edit IS the row). 迁移期读回退 (§3.5.5-3): pre-v3 rows carried the
    # artifact on the asm — read doc first, fall back to the asm, never
    # re-buy the translation at the boundary.
    doc_id = (node.spec or {}).get("doc_node_id")
    if doc_id:
        doc = await db.get(GraphNode, UUID(str(doc_id)))
        if doc is not None:
            doc.state = node.state
            artifact = (doc.spec or {}).get(TRANSLATION_ARTIFACT_KEY) or (
                (node.spec or {}).get(TRANSLATION_ARTIFACT_KEY)
            )
            text = _translation_artifact_text(artifact)
            if text and text != (doc.spec or {}).get("text"):
                doc.spec = {**(doc.spec or {}), "text": text}
