"""exploration_store — the exploration artifacts' write door (ADR-088 §4, R14).

探索产物族（Candidate Set / Select / Content Plan，NAMING N-55）的唯一写座。
The family lives in the persistent graph (``graph_nodes`` rows with
``type = "exploration"`` + ``spec.prototype = "exploration"`` +
``spec.exploration_kind``) — the zero-projection law (ADR-057) and the
project-delete cascade come for free.

**I-EXPLORE-01 (invariant)**: exploration artifacts MUST NOT participate in
execution topology, execution closure, quote/rank calculation, or
media-flow edge semantics. The door enforces its half: exploration nodes
are born EDGELESS and stay edgeless (no edge writer exists in this
module); the execution door enforces the reverse half
(``graph_store.apply_wiring_ops`` rejects exploration nodes).

**R14 双门**: this door is NOT the execution write door. Two doors, two
invariant sets — the exploration door is FREE but still a real door:
savepoint-scoped validation (flush-only, the caller commits —
``apply_wiring_ops`` precedent), evidence validation (ranges inside the
asset's timeline, excerpts verbatim from its words), and replay
idempotency (an identical call returns the existing artifact).

**R24 journey attribution**: every artifact the door births carries the
owning ``journey_id`` — derived STRUCTURALLY from the chain (candidates
mint or adopt the journey; selects inherit from their candidate set;
plans inherit from their select), never re-stated by the caller. The
journey id is an attribution property, never a graph edge.

**R3 / R7**: a Select stores verdict + one user-safe reason line + the
evidence POINTER (candidate set + member index) — never the source
copied, never a reasoning trace (reasoning never persists, CoT gate
unchanged).

**Layout**: exploration nodes are edgeless islands; the depth law would
stack them into the material column. Iter-1 lane rule (canvas organization
is the P2 ledger entry): ONE dedicated lane one pitch LEFT of the island
column (x = −464), family stacking by birth order — deterministic and
non-overlapping by construction, zero entanglement with the depth law.
Frames are append-only reservations, assigned once at birth.
"""

import hashlib
import json
import re
from typing import Any, Iterable, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Asset, GraphNode, Journey, Project
from app.pipeline.product_graph import EXPLORATION_NODE_TYPE, EXPLORATION_PROTOTYPE
from app.tools.clips.transcript import words_in_range

# ---- family vocabulary ---------------------------------------------------------

# EXPLORATION_PROTOTYPE / EXPLORATION_NODE_TYPE live in product_graph (the
# leaf vocabulary seat — both doors import from there, never from each
# other, so no graph_store ↔ exploration_store cycle can exist).

KIND_CANDIDATE_SET = "candidate_set"
KIND_SELECT = "select"
KIND_CONTENT_PLAN = "content_plan"
EXPLORATION_KINDS: frozenset[str] = frozenset(
    {KIND_CANDIDATE_SET, KIND_SELECT, KIND_CONTENT_PLAN}
)

# The artifact state machine (ADR-088 §3): draft → ready → revised → compiled
# → superseded. Candidates and selects are born ready (evidence-complete at
# birth); plans take draft/ready at birth, ``revised`` via the in-place
# revise verb, ``compiled`` via ``mark_compiled`` when the Start birthplace
# stamps the confirmed snapshot, and ``superseded`` via ``supersede_plan``
# (the post-run revision — a successor row carries the restated spec;
# ``revision_of`` is never built, N-57).
STATE_DRAFT = "draft"
STATE_READY = "ready"
EXPLORATION_STATES: frozenset[str] = frozenset(
    {STATE_DRAFT, STATE_READY, "revised", "compiled", "superseded"}
)

# The producible output families a Content Plan may name (product semantics —
# the compiler (ADR-089 §2, iter-2) maps these to registry tools; they mirror
# the visible product rows' family words, never the tool names).
PLAN_OUTPUT_KINDS: frozenset[str] = frozenset(
    {"clip", "post", "article", "quotes", "carousel"}
)


class ExplorationRejected(ValueError):
    """The exploration door's rejection — sibling to WiringRejected: the
    whole call dies together, the loop echo carries the reason back."""


# ---- spec shapes (graph_nodes.spec JSONB contracts) ----------------------------


class CandidateMember(BaseModel):
    """One evidence member of a Candidate Set — every field traceable back
    to the transcript (ADR-088 §2). ``speaker`` is best-effort (audio
    assets carry no speaker_map — ADR-045 D4)."""

    model_config = ConfigDict(extra="forbid")

    start: float
    end: float
    excerpt: str
    speaker: str | None = None


class CandidateSetSpec(BaseModel):
    """R1 合集律: the set is ONE artifact (collapsed by default, expandable)
    — never N independent cards (the canvas density law)."""

    model_config = ConfigDict(extra="forbid")

    prototype: Literal["exploration"] = EXPLORATION_PROTOTYPE
    exploration_kind: Literal["candidate_set"] = KIND_CANDIDATE_SET
    asset_id: str
    topic: str
    members: list[CandidateMember]
    idem: str = ""


class SelectSpec(BaseModel):
    """R7 证据引用: the Select points at its evidence (candidate set +
    member index) and never copies the source; R3: the reason is an
    ATTRIBUTE (verdict + one user-safe line) — reasoning never persists."""

    model_config = ConfigDict(extra="forbid")

    prototype: Literal["exploration"] = EXPLORATION_PROTOTYPE
    exploration_kind: Literal["select"] = KIND_SELECT
    candidate_set_id: str
    member_index: int
    verdict: str = Field(max_length=300)
    reason: str = Field(max_length=300)
    idem: str = ""


class PlanOutput(BaseModel):
    """One named deliverable of a Content Plan (product semantics: what the
    user gets — language / captions / a per-output brief; never task
    params, R8).

    Iter-2 ① field completion (N-56, product-first ruling 2026-09-23): the
    clip promise's six product facts are now all expressible — the range and
    the source asset arrive STRUCTURALLY (the Select pointer), and the user-
    named variables ride here: language version / caption form / dubbing /
    frame format. ``dub`` splits the "French captions vs French speech"
    ambiguity; ``caption_mode`` is the controlled vocabulary (the TaskSpec
    word family); ``aspect`` is a birth-time property (the clip-spec bakes
    the frame at birth — no downstream capability can re-frame it, so the
    plan must carry it). Narrowing ``caption_mode`` from free str is safe in
    exactly this window: the exploration tools are still harness-level (R6
    production wiring lands later this iteration), so no production plan row
    carries a free-form value."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["clip", "post", "article", "quotes", "carousel"]
    language: str | None = Field(
        default=None,
        description="ISO code of the deliverable's language version. For "
        "clips: the captions' language (speech stays the source's unless "
        "dub is set); for writers: the content's language. null = the "
        "source/default.",
    )
    caption_mode: Literal["bilingual", "source_only", "target_only"] | None = Field(
        default=None,
        description="Caption form of a language version (clips / quotes): "
        "bilingual = source + target side by side; target_only = the "
        "translation replaces the source captions; source_only = "
        "source-language captions (the default anyway). Meaningless without "
        "language. null = default.",
    )
    dub: bool | None = Field(
        default=None,
        description="Clips only: true = re-voice the speech into `language` "
        "(cloned-voice dub — the heavier promise). null/false = the speech "
        "stays the source's.",
    )
    aspect: Literal["9:16", "1:1", "16:9"] | None = Field(
        default=None,
        description="Clips only: frame format — set when the user names one "
        "(竖版/9:16, 方形/1:1, 横版/16:9). null = the persona skin default.",
    )
    brief: str | None = None


class ContentPlanSpec(BaseModel):
    """R8: Content Plan ≠ Task — the product-semantic description of "how
    we will make this Select into content" (source range via the Select
    reference / outputs / persona ref — R9: persona is injected at
    Structure time, never during candidate evaluation)."""

    model_config = ConfigDict(extra="forbid")

    prototype: Literal["exploration"] = EXPLORATION_PROTOTYPE
    exploration_kind: Literal["content_plan"] = KIND_CONTENT_PLAN
    select_id: str
    title: str = Field(default="", max_length=200)
    outputs: list[PlanOutput]
    persona_id: str | None = None
    idem: str = ""


# ---- evidence validation (pure) -------------------------------------------------

_EVIDENCE_KEEP_RE = re.compile(r"[0-9a-z一-鿿]+")


def normalize_evidence(text: str) -> str:
    """The verbatim-evidence normalization: case-folded, alnum+CJK kept,
    everything else (punctuation / whitespace / quotes) dropped — 'the
    LLM retyped the punctuation' never defeats an honest quote, while a
    paraphrase still fails. CJK-safe by construction."""
    return "".join(_EVIDENCE_KEEP_RE.findall(text.casefold()))


def member_issues(
    members: list[CandidateMember],
    *,
    duration_s: float,
    words: list[dict[str, Any]],
) -> list[str]:
    """The candidate evidence gate (ADR-088 §4): start < end, end inside
    the asset's timeline, and every excerpt verbatim-traceable to the
    words spoken inside ITS OWN range (normalized containment — a member
    whose quote lives outside its range is not evidence)."""
    issues: list[str] = []
    if not members:
        return ["candidate set carries no members"]
    for i, m in enumerate(members):
        if not m.start < m.end:
            issues.append(f"member {i}: start ({m.start}) must be < end ({m.end})")
            continue
        if m.end > duration_s:
            issues.append(
                f"member {i}: end ({m.end}) beyond the asset's timeline ({duration_s})"
            )
            continue
        spoken = normalize_evidence(words_in_range(words, m.start, m.end))
        quote = normalize_evidence(m.excerpt)
        if not quote:
            issues.append(f"member {i}: empty excerpt")
        elif quote not in spoken:
            issues.append(
                f"member {i}: excerpt is not verbatim speech inside its own range"
            )
    return issues


def plan_completeness_issues(outputs: list[PlanOutput]) -> list[str]:
    """The deterministic completeness self-check (拍 5a, artifact state
    draft → ready): outputs non-empty and no duplicate (kind, language)
    pair. Ranges resolve structurally (the door validated the select's
    evidence at ITS birth); defaults absorb unnamed languages/captions
    (config 三分流 — an unnamed field is complete, not missing). Iter-2 ①
    additions: a language-dependent form (bilingual / target_only captions,
    dub) without a language is a gap, and clip-only properties (aspect /
    dub) on a non-clip output are a semantic confusion the agent should
    fix — both surface as honest issues, never silent drops."""
    issues: list[str] = []
    if not outputs:
        return ["content plan names no outputs"]
    seen: set[tuple[str, str | None]] = set()
    for i, o in enumerate(outputs):
        key = (o.kind, o.language)
        if key in seen:
            issues.append(f"output {i}: duplicate {o.kind}/{o.language or 'default'}")
        seen.add(key)
        if o.caption_mode in ("bilingual", "target_only") and not o.language:
            issues.append(
                f"output {i}: {o.caption_mode} captions need a target language"
            )
        if o.dub and not o.language:
            issues.append(f"output {i}: dub needs a target language")
        if o.kind != "clip":
            if o.aspect is not None:
                issues.append(f"output {i}: aspect applies to clips only")
            if o.dub:
                issues.append(f"output {i}: dub applies to clips only")
    return issues


# ---- idempotency (pure) ----------------------------------------------------------


def _idem_key(kind: str, journey_id: UUID, payload: dict[str, Any]) -> str:
    """The replay key: journey × kind × the canonical payload. An identical
    call (same turn retry / SSE reconnect replay) returns the existing
    artifact instead of birthing a twin."""
    blob = json.dumps(
        {"kind": kind, "journey": str(journey_id), "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def _find_replay(
    lane: list[GraphNode], journey_id: UUID, kind: str, idem: str
) -> GraphNode | None:
    """The replay lookup — a PURE filter over the lane the door already
    loaded (journey × kind × idem). Deliberately NOT a JSON-path SQL
    filter: the journey_id index already bounds the row set, and a Python
    filter keeps the door's adjudication where the pure tests can see it."""
    return next(
        (
            n
            for n in lane
            if str(n.journey_id) == str(journey_id)
            and (n.spec or {}).get("exploration_kind") == kind
            and (n.spec or {}).get("idem") == idem
        ),
        None,
    )


# ---- the exploration lane (pure) -------------------------------------------------

# Birth frame reservations per kind — ONE law with the client mirror
# (apps/web/src/components/flow/layout.ts exploration frames, landing with
# the cards in this batch): the frame is the reservation the card is built
# to fit (candidate set = the COLLAPSED summary row; expansion is the
# card's in-place max-height scroll, the 封顶滚动律 precedent — the frame
# never grows).
_EXPLORATION_FRAME: dict[str, tuple[int, int]] = {
    KIND_CANDIDATE_SET: (340, 96),
    KIND_SELECT: (320, 140),
    KIND_CONTENT_PLAN: (360, 220),
}
# The lane: one pitch LEFT of the island column (the depth law's x = depth
# × 464; exploration is edgeless so its "depth" would be 0 — the family
# gets its own column at −464 instead, never mixing into the material
# lane). _GAP_MAIN/_PITCH mirror, cross-referenced — canvas organization
# is the P2 ledger entry, this is the iter-1 deterministic rule.
_EXPLORATION_LANE_X = -464
_LANE_GAP_Y = 16  # _GAP_CROSS mirror (graph_store) — sibling stacking


def exploration_lane_frame(kind: str, lane_nodes: list[GraphNode]) -> dict[str, int]:
    """The family's birth frame: the lane's tail + gap, or the lane top.
    Append-only — existing frames never move (保序律)."""
    w, h = _EXPLORATION_FRAME[kind]
    if lane_nodes:
        y = (
            max(
                int((n.layout or {}).get("y", 0)) + int((n.layout or {}).get("h", h))
                for n in lane_nodes
            )
            + _LANE_GAP_Y
        )
    else:
        y = 0
    return {"x": _EXPLORATION_LANE_X, "y": y, "w": w, "h": h}


# ---- door helpers -----------------------------------------------------------------


async def _exploration_nodes(db: AsyncSession, project_id: UUID) -> list[GraphNode]:
    return list(
        (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.project_id == project_id,
                    GraphNode.type == EXPLORATION_NODE_TYPE,
                )
            )
        )
        .scalars()
        .all()
    )


async def read_journey_evidence(
    db: AsyncSession, project_id: UUID, journey_id: UUID
) -> tuple[list[GraphNode], list[GraphNode]]:
    """The compiler's read seat (iter-2 ③, R14 编译器半边——门外侧只读):
    the journey's Select and Candidate Set rows, so ``compile_plans`` can
    dereference the R7 evidence pointers. Returns (selects, candidate_sets)
    in birth order. Pure read — the exploration door's invariants never
    relax for the compiler (the door writes, the compiler translates)."""
    rows = list(
        (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.project_id == project_id,
                    GraphNode.type == EXPLORATION_NODE_TYPE,
                    GraphNode.journey_id == journey_id,
                )
            )
        )
        .scalars()
        .all()
    )
    selects = [
        n for n in rows if (n.spec or {}).get("exploration_kind") == KIND_SELECT
    ]
    candidate_sets = [
        n for n in rows if (n.spec or {}).get("exploration_kind") == KIND_CANDIDATE_SET
    ]
    return selects, candidate_sets


def _get_exploration_node(
    nodes: list[GraphNode], node_id: UUID, kind: str
) -> GraphNode:
    node = next((n for n in nodes if UUID(str(n.id)) == node_id), None)
    if node is None:
        raise ExplorationRejected(f"{kind}: node {node_id} not found in this project")
    actual = (node.spec or {}).get("exploration_kind")
    if actual != kind:
        raise ExplorationRejected(
            f"{kind}: node {node_id} is a {actual or 'non-exploration'} node"
        )
    return node


async def _timeline_of(db: AsyncSession, project: Project, asset_id: UUID) -> tuple[Asset, list[dict[str, Any]], float]:
    """The evidence substrate: the asset + its word stream + its timeline
    length. Honest degradation (拍 2 的前提是理解链完成): exploration needs
    word-level timestamps — an asset without words is a door rejection,
    never a fabricated range."""
    asset = await db.get(Asset, asset_id)
    if asset is None or UUID(str(asset.project_id)) != UUID(str(project.id)):
        raise ExplorationRejected(f"asset {asset_id} not found in this project")
    words = (asset.meta or {}).get("words") or []
    if not words:
        raise ExplorationRejected(
            f"asset {asset_id} has no timeline yet — exploration needs the "
            "understanding chain's word-level timestamps"
        )
    duration = asset.duration_seconds
    if duration is None:
        duration = float(words[-1].get("end") or 0.0)
    return asset, words, float(duration)


# ---- the write door (flush-only — the caller commits) ----------------------------


async def propose_candidates(
    db: AsyncSession,
    project: Project,
    *,
    asset_id: UUID,
    topic: str,
    members: list[CandidateMember],
    goal_text: str | None = None,
    journey_id: UUID | None = None,
) -> GraphNode:
    """Birth the journey's Candidate Set (R1: ONE collection artifact).

    Mints the journey when the call opens the chain (``goal_text``
    required then); adopts it when the chain continues. Replay = the
    existing set.
    """
    _asset, words, duration = await _timeline_of(db, project, asset_id)
    issues = member_issues(members, duration_s=duration, words=words)
    if issues:
        raise ExplorationRejected("candidate evidence rejected: " + "; ".join(issues))

    if journey_id is not None:
        journey = await db.get(Journey, journey_id)
        if journey is None or UUID(str(journey.project_id)) != UUID(str(project.id)):
            raise ExplorationRejected(f"journey {journey_id} not found in this project")
    else:
        if not (goal_text or "").strip():
            raise ExplorationRejected(
                "propose_candidates opens a journey — goal_text is required"
            )
        # The goal IS the journey's identity (R24): an identical chain-opener
        # replaying without a journey id ADOPTS the goal's existing journey —
        # so the replay key below still hits and no twin journey is minted
        # (回合幂等 holds for the opener too).
        goal = goal_text.strip()
        journey = (
            await db.execute(
                select(Journey).where(
                    Journey.project_id == project.id,
                    Journey.goal_text == goal,
                )
            )
        ).scalars().first()
        if journey is None:
            journey = Journey(id=uuid4(), project_id=project.id, goal_text=goal)
            db.add(journey)
            await db.flush()

    idem = _idem_key(
        KIND_CANDIDATE_SET,
        UUID(str(journey.id)),
        {
            "asset_id": str(asset_id),
            "topic": topic,
            "members": [m.model_dump() for m in members],
        },
    )
    lane = await _exploration_nodes(db, project.id)
    replay = _find_replay(lane, UUID(str(journey.id)), KIND_CANDIDATE_SET, idem)
    if replay is not None:
        return replay

    spec = CandidateSetSpec(
        asset_id=str(asset_id),
        topic=topic,
        members=members,
        idem=idem,
    )
    node = GraphNode(
        id=uuid4(),
        project_id=project.id,
        type=EXPLORATION_NODE_TYPE,
        state=STATE_READY,
        spec=spec.model_dump(),
        layout=exploration_lane_frame(KIND_CANDIDATE_SET, lane),
        journey_id=journey.id,
    )
    db.add(node)
    await db.flush()
    return node


async def propose_selects(
    db: AsyncSession,
    project: Project,
    *,
    candidate_set_id: UUID,
    selects: list[dict[str, Any]],
) -> list[GraphNode]:
    """Birth the Selects of one Candidate Set (R7 pointer + R3 attribute
    reason). The journey rides structurally from the set."""
    lane = await _exploration_nodes(db, project.id)
    cset = _get_exploration_node(lane, candidate_set_id, KIND_CANDIDATE_SET)
    if not selects:
        raise ExplorationRejected("propose_selects carries no selects")
    cspec = CandidateSetSpec.model_validate(cset.spec)
    journey_id = UUID(str(cset.journey_id))

    born: list[GraphNode] = []
    for s in selects:
        spec = SelectSpec(
            candidate_set_id=str(candidate_set_id),
            member_index=int(s.get("member_index", -1)),
            verdict=str(s.get("verdict") or "").strip(),
            reason=str(s.get("reason") or "").strip(),
        )
        if not (0 <= spec.member_index < len(cspec.members)):
            raise ExplorationRejected(
                f"select: member_index {spec.member_index} outside the candidate "
                f"set's {len(cspec.members)} members"
            )
        if not spec.verdict or not spec.reason:
            raise ExplorationRejected(
                "select: verdict and reason are both required (R3 — the "
                "judgment's output is an attribute)"
            )
        spec.idem = _idem_key(
            KIND_SELECT, journey_id, spec.model_dump(exclude={"idem"})
        )
        replay = _find_replay(lane, journey_id, KIND_SELECT, spec.idem)
        if replay is not None:
            born.append(replay)
            continue
        node = GraphNode(
            id=uuid4(),
            project_id=project.id,
            type=EXPLORATION_NODE_TYPE,
            state=STATE_READY,
            spec=spec.model_dump(),
            layout=exploration_lane_frame(KIND_SELECT, lane),
            journey_id=journey_id,
        )
        db.add(node)
        lane.append(node)
        born.append(node)
    await db.flush()
    return born


async def propose_plans(
    db: AsyncSession,
    project: Project,
    *,
    plans: list[dict[str, Any]],
    persona_id: UUID | None = None,
) -> list[GraphNode]:
    """Birth the Content Plans (one per Select, R8 product semantics) with
    the deterministic completeness self-check (拍 5a): clean → ready, else
    draft with the issues stamped into the spec (honest surface, never a
    silent gap). One call = one journey."""
    lane = await _exploration_nodes(db, project.id)
    if not plans:
        raise ExplorationRejected("propose_plans carries no plans")

    born: list[GraphNode] = []
    journey_id: UUID | None = None
    for p in plans:
        select_id = UUID(str(p.get("select_id")))
        sel = _get_exploration_node(lane, select_id, KIND_SELECT)
        sel_journey = UUID(str(sel.journey_id))
        if journey_id is None:
            journey_id = sel_journey
        elif journey_id != sel_journey:
            raise ExplorationRejected(
                "propose_plans: one call plans one journey — the selects "
                "span two"
            )
        outputs = [PlanOutput.model_validate(o) for o in (p.get("outputs") or [])]
        issues = plan_completeness_issues(outputs)
        spec = ContentPlanSpec(
            select_id=str(select_id),
            title=str(p.get("title") or "").strip(),
            outputs=outputs,
            persona_id=str(persona_id) if persona_id else None,
        )
        spec.idem = _idem_key(
            KIND_CONTENT_PLAN, sel_journey, spec.model_dump(exclude={"idem"})
        )
        replay = _find_replay(lane, sel_journey, KIND_CONTENT_PLAN, spec.idem)
        if replay is not None:
            born.append(replay)
            continue
        payload = spec.model_dump()
        if issues:
            payload["issues"] = issues
        node = GraphNode(
            id=uuid4(),
            project_id=project.id,
            type=EXPLORATION_NODE_TYPE,
            state=STATE_DRAFT if issues else STATE_READY,
            spec=payload,
            layout=exploration_lane_frame(KIND_CONTENT_PLAN, lane),
            journey_id=sel_journey,
        )
        db.add(node)
        lane.append(node)
        born.append(node)
    await db.flush()
    return born


async def read_journey_plans(
    db: AsyncSession, project_id: UUID, journey_id: UUID
) -> list[GraphNode]:
    """The revise/recompile seat's read (iter-2 ⑦): the journey's CURRENT
    Content Plan rows (the decision package re-docks as a whole — a revise
    targets one plan, the package re-presents every plan). Pure read, same
    door-outside posture as ``read_journey_evidence``.

    Iter-3 E3 (review 注记①): the read is state-filtered to the CURRENT
    package — ``ready``/``revised`` only. ``compiled``/``superseded`` rows
    are settled history (the confirmed snapshot's anchors): without this
    filter the whole-package recompile would hard-reject on them the day
    ``mark_compiled`` lands (缺一天 = 整包重编译炸). ``draft`` rows carry
    open gaps — they re-enter the package only through the repair verb
    (``revise_plan`` targeting them directly)."""
    rows = list(
        (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.project_id == project_id,
                    GraphNode.type == EXPLORATION_NODE_TYPE,
                    GraphNode.journey_id == journey_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        n
        for n in rows
        if (n.spec or {}).get("exploration_kind") == KIND_CONTENT_PLAN
        and n.state in (STATE_READY, "revised")
    ]


async def read_journey_plan_rows(
    db: AsyncSession, project_id: UUID, journey_id: UUID
) -> list[GraphNode]:
    """The revision money-state discriminator's read (iter-3 S4): EVERY
    Content Plan row of the journey regardless of state — the settled rows
    (``compiled``/``superseded``) ARE the post-run signal, so the state
    filter of ``read_journey_plans`` (the recompile seat's CURRENT-package
    read) cannot serve here. Pure read, same door-outside posture."""
    rows = list(
        (
            await db.execute(
                select(GraphNode).where(
                    GraphNode.project_id == project_id,
                    GraphNode.type == EXPLORATION_NODE_TYPE,
                    GraphNode.journey_id == journey_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        n
        for n in rows
        if (n.spec or {}).get("exploration_kind") == KIND_CONTENT_PLAN
    ]


# The three money states of a select revision (iter-3 S4, contract §4 S4 /
# N-58) — judged over the states of the plans RIDING the revised selects:
PHASE_PRE_DOCK = "pre_dock"  # no riding plan row — pure door revision, zero ceremony
PHASE_DOCKED = "docked"  # riding LIVE plans — whole-journey recompile + in-place re-dock
PHASE_POST_RUN = "post_run"  # riding SETTLED plans — supersede-继任 + mini package re-confirm
SELECT_REVISION_PHASES: frozenset[str] = frozenset(
    {PHASE_PRE_DOCK, PHASE_DOCKED, PHASE_POST_RUN}
)


def select_revision_phase(riding_states: Iterable[str]) -> str:
    """The money-state discriminator (pure — the turn paths adjudicate on
    it, never re-derive it): a SETTLED riding row (compiled/superseded)
    means the package already ran → post_run; live riding rows mean a
    package is on the table (or heading to it) → docked; nothing riding →
    pre_dock. A superseded row's successor rides the SAME select (the
    carry-over keeps select_id), so a re-revision before the mini package
    confirms still finds the live successor here → docked/post_run as the
    rows say."""
    states = list(riding_states)
    if any(s in ("compiled", "superseded") for s in states):
        return PHASE_POST_RUN
    if states:
        return PHASE_DOCKED
    return PHASE_PRE_DOCK


async def revise_plan(
    db: AsyncSession,
    project: Project,
    *,
    plan_id: UUID,
    title: str | None = None,
    outputs: list[dict[str, Any]] | None = None,
) -> GraphNode:
    """Revise one Content Plan IN PLACE (iter-2 ⑦, ADR-089 §6 修订分类,
    contract §4.8): the SAME row takes the restated spec — clean → state
    ``revised``, gaps → ``draft`` with the issues re-stamped (the birth
    self-check's 同一律). ``revision_of`` is never built (同一行修订, 无
    版本树 — N-57); the spec's birth ``idem`` survives (a revision never
    re-mints identity). compiled / superseded rows are closed — the
    decision package they rode is settled history. Replay = an identical
    restatement returns the row untouched. Flush-only."""
    lane = await _exploration_nodes(db, project.id)
    node = _get_exploration_node(lane, plan_id, KIND_CONTENT_PLAN)
    if node.state in ("compiled", "superseded"):
        raise ExplorationRejected(
            f"plan {plan_id} is {node.state} — a settled plan is never revised"
        )
    raw = dict(node.spec or {})
    raw.pop("issues", None)
    spec = ContentPlanSpec.model_validate(raw)
    new_title = spec.title if title is None else title.strip()
    new_outputs = (
        spec.outputs
        if outputs is None
        else [PlanOutput.model_validate(o) for o in outputs]
    )
    payload = spec.model_copy(
        update={"title": new_title, "outputs": new_outputs}
    ).model_dump()
    issues = plan_completeness_issues(new_outputs)
    if issues:
        payload["issues"] = issues
    if dict(node.spec or {}) == payload:
        return node  # replay: identical restatement is a no-op
    node.spec = payload
    node.state = STATE_DRAFT if issues else "revised"
    await db.flush()
    return node


async def revise_selects(
    db: AsyncSession,
    project: Project,
    *,
    selects: list[dict[str, Any]],
) -> list[GraphNode]:
    """Revise Selects IN PLACE (iter-3 S4, ADR-089 §6 修订分类 / N-58): the
    pick swaps — ``member_index`` re-points into the SAME candidate set
    (bounds re-validated against the set's members, the birth law's 同一律),
    and the verdict + reason RESTATE for the new pick (R3: the judgment is
    an attribute of the pick — the old lines vouched for the old member,
    they never transfer). The SAME row takes the restatement → state
    ``revised`` (the Select family's first revised writer; the artifact
    state machine's ready → revised path). The birth ``idem`` survives —
    a revision never re-mints identity (revise_plan 同律). One call revises
    ONE journey (propose_plans' one-journey law mirrored — the turn layer's
    follow-up docks one package per journey). compiled/superseded rows are
    closed (settled history — a post-run swap supersedes the riding PLANS,
    the select row itself revises in place all the same). Replay = an
    identical restatement returns the row untouched. Flush-only."""
    lane = await _exploration_nodes(db, project.id)
    if not selects:
        raise ExplorationRejected("revise_selects carries no selects")

    revised: list[GraphNode] = []
    journey_id: UUID | None = None
    for s in selects:
        node = _get_exploration_node(
            lane, UUID(str(s.get("select_id"))), KIND_SELECT
        )
        sel_journey = UUID(str(node.journey_id))
        if journey_id is None:
            journey_id = sel_journey
        elif journey_id != sel_journey:
            raise ExplorationRejected(
                "revise_selects: one call revises one journey — the selects "
                "span two. Split the call."
            )
        if node.state in ("compiled", "superseded"):
            raise ExplorationRejected(
                f"select {node.id} is {node.state} — a settled select is "
                "never revised"
            )
        spec = SelectSpec.model_validate(node.spec)
        cset = _get_exploration_node(
            lane, UUID(spec.candidate_set_id), KIND_CANDIDATE_SET
        )
        cspec = CandidateSetSpec.model_validate(cset.spec)
        new_index = int(s.get("member_index", -1))
        if not (0 <= new_index < len(cspec.members)):
            raise ExplorationRejected(
                f"select: member_index {new_index} outside the candidate "
                f"set's {len(cspec.members)} members"
            )
        verdict = str(s.get("verdict") or "").strip()
        reason = str(s.get("reason") or "").strip()
        if not verdict or not reason:
            raise ExplorationRejected(
                "select: verdict and reason restate for the NEW pick (R3 — "
                "the judgment attribute moves with the pick)"
            )
        payload = spec.model_copy(
            update={"member_index": new_index, "verdict": verdict, "reason": reason}
        ).model_dump()
        if dict(node.spec or {}) == payload:
            revised.append(node)  # replay: identical restatement is a no-op
            continue
        node.spec = payload
        node.state = "revised"
        revised.append(node)
    await db.flush()
    return revised


async def mark_compiled(
    db: AsyncSession, project: Project, *, plan_ids: list[UUID]
) -> list[GraphNode]:
    """E3 双态写者 (first half, iter-3 S1): after the Start birthplace
    stamps the Confirmed Scope Snapshot, the confirmed package's plan rows
    flip ``ready``/``revised`` → ``compiled`` — IN THE SAME TRANSACTION
    (flush-only; the caller commits), so the artifact state machine and the
    paid execution never diverge.

    Idempotent: an already-compiled row is a no-op (Start replays). A
    ``draft`` row is unreachable (an uncompilable package never births a
    run) and a ``superseded`` row is settled history — both reject. An id
    the project doesn't carry rejects too: the snapshot must never name a
    plan the project doesn't have."""
    if not plan_ids:
        return []
    lane = await _exploration_nodes(db, project.id)
    plans = [
        n
        for n in lane
        if (n.spec or {}).get("exploration_kind") == KIND_CONTENT_PLAN
    ]
    by_id = {str(n.id): n for n in plans}
    marked: list[GraphNode] = []
    for plan_id in plan_ids:
        node = by_id.get(str(plan_id))
        if node is None:
            raise ExplorationRejected(
                f"mark_compiled: plan {plan_id} is not an exploration plan "
                "of this project"
            )
        if node.state == "compiled":
            marked.append(node)  # replay: already settled into compiled
            continue
        if node.state not in (STATE_READY, "revised"):
            raise ExplorationRejected(
                f"mark_compiled: plan {plan_id} is {node.state} — only "
                "ready/revised plans can settle into compiled"
            )
        node.state = "compiled"
        marked.append(node)
    await db.flush()
    return marked


async def supersede_plan(
    db: AsyncSession,
    project: Project,
    *,
    plan_id: UUID,
    title: str | None = None,
    outputs: list[dict[str, Any]] | None = None,
) -> GraphNode:
    """E3 双态写者 (second half, iter-3 S1): the POST-RUN plan-level
    revision — the compiled row settles (``compiled → superseded``, an
    in-vocabulary state-machine path) and a SUCCESSOR row is born: new id,
    same journey, the restated spec (unnamed fields carry over verbatim),
    the birth self-check's same law (clean → ``revised``, gaps → ``draft``
    with the issues stamped).

    ``revision_of`` is never built (N-57 无版本树律): the successor holds
    NO pointer back — the replay idem is salted with the superseded row's
    id (a hash input, not a navigable edge), so an identical retry returns
    the existing successor instead of double-superseding. Non-compiled
    rows reject with guidance (pre-run revisions belong to the in-place
    ``revise_plan`` seat). Flush-only."""
    lane = await _exploration_nodes(db, project.id)
    node = _get_exploration_node(lane, plan_id, KIND_CONTENT_PLAN)
    raw = dict(node.spec or {})
    raw.pop("issues", None)
    spec = ContentPlanSpec.model_validate(raw)
    new_title = spec.title if title is None else title.strip()
    new_outputs = (
        spec.outputs
        if outputs is None
        else [PlanOutput.model_validate(o) for o in outputs]
    )
    restated = spec.model_copy(update={"title": new_title, "outputs": new_outputs})
    # Replay first: the successor's idem salts the payload with the
    # superseded row's id — a retry finds the successor even though the old
    # row is already superseded.
    idem = _idem_key(
        KIND_CONTENT_PLAN,
        UUID(str(node.journey_id)),
        {**restated.model_dump(exclude={"idem"}), "supersede_of": str(plan_id)},
    )
    replay = _find_replay(lane, UUID(str(node.journey_id)), KIND_CONTENT_PLAN, idem)
    if replay is not None:
        return replay
    if node.state == "superseded":
        raise ExplorationRejected(
            f"plan {plan_id} is already superseded — address its current "
            "successor instead"
        )
    if node.state != "compiled":
        raise ExplorationRejected(
            f"plan {plan_id} is {node.state} — only a compiled plan "
            "supersedes; pre-run revisions use revise_plan (in place)"
        )
    issues = plan_completeness_issues(new_outputs)
    payload = restated.model_dump()
    payload["idem"] = idem
    if issues:
        payload["issues"] = issues
    successor = GraphNode(
        id=uuid4(),
        project_id=project.id,
        type=EXPLORATION_NODE_TYPE,
        state=STATE_DRAFT if issues else "revised",
        spec=payload,
        layout=exploration_lane_frame(KIND_CONTENT_PLAN, lane),
        journey_id=node.journey_id,
    )
    node.state = "superseded"
    db.add(successor)
    await db.flush()
    return successor
