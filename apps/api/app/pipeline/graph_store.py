"""Graph store (ADR-057) — the wiring layer, the graph's ONLY write door.

The project graph is a persistent, mutable product object (two tables,
``graph_nodes`` / ``graph_edges``, owner = Pipeline, MODULE_ARCH §4). Every
mutation — chat-built drafts, prompt edits, deletions, run fills — lands
here as a batch of wiring ops; the canvas reads the graph directly (zero
projection). 能力完备、手势缺席: the op set is complete enough to express
anything chat wiring needs (manual wiring capability MUST exist for chat
wiring to rest on), but no UI ever exposes manual gestures.

Ops (the registry below): ``add_node`` / ``connect`` / ``edit_prompt`` /
``edit_text`` / ``delete_node`` / ``run``. Initial generation, revision and
new builds are the SAME op set — the "revision loop" as a separate concept
is retired; there is one graph being edited continuously. Islands are
legal (the graph is a forest, not a single connected DAG).

Adjudication mirrors compile_graph's posture: validate EVERY op first (op
type / reference existence / port-type compatibility / no cycle), land the
batch in one flush (the caller commits — create_run precedent), or reject
the whole batch (WiringRejected). Execution is NOT here: a ``run`` op only
resolves its target subgraph into the returned delta — the run itself is
born at the only birthplace (orchestrator.create_run), zero bypass.
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import GraphEdge, GraphIsland, GraphNode, Project, now_utc
from app.pipeline.product_graph import (
    EXPLORATION_PROTOTYPE,
    RANK_EDGE_TYPES,
    effective_rank_edges,
    is_lineage_edge,
    product_ranks,
)


class WiringRejected(ValueError):
    """A wiring op failed adjudication (unknown op / dangling reference /
    incompatible ports / a cycle). Same family as ToolRejected — request
    handlers translate to 422, chat degrades to a plain-language reply."""


def executable_children_of(edges: Any, node_id: UUID) -> list[UUID]:
    """The run-closure walk's edge set (ADR-097 §5): lineage/display-only
    真边（端口标记 out:lineage）**永不参与** stale/invalidation 闭包——调
    度事实源恒为 run 内编译的 step inputs，新真边零编排语义。没有这道排
    除, 对转写稿节点的 run 闭包会顺着血缘边把下游字幕产物卷进重跑
    （改 transcript edited_text 误伤下游字幕的那一格）。Module-level and
    pure so the walk law stays unit-testable off the DB."""
    return [
        UUID(str(e.to_node))
        for e in edges
        if UUID(str(e.from_node)) == node_id and not is_lineage_edge(e)
    ]


# ---- op schemas (the wiring registry) --------------------------------------


class AddNodeOp(BaseModel):
    """Place a node. ``spec`` is the node's program (prompt / params /
    asset_id / text — well-formed shapes are the producer's knowledge, K2's
    migration mapping); ``after`` wires its birth edges (connect's shorthand).
    ``id`` pins the newborn's identity — the server-side stamper's seat: its
    SAME-batch connect ops reference the pinned id, so frames are born with
    full edge knowledge (布局一开始就定好, 2026-09-08 用户拍板 — never an
    island guess repaired by a second pass). Chat proposals never carry one."""

    op: Literal["add_node"]
    # 词表 v3 (ADR-076; C4 收窄, C5b 终名 type): 出生词表 = 媒介五值 +
    # 服务端内部两词 (asset / document — 素材与文档的出生地词, 读面映射归
    # _read_face)。generator/processor/agent 三死词退役出出生词表 (legacy
    # 容忍条目只留端口表 _NODE_PORTS — 旧行连线仍要过门)。
    type: Literal[
        "asset", "document",
        "text", "table", "image", "video", "audio",
    ]
    spec: dict[str, Any] = Field(default_factory=dict)
    after: list[UUID] = Field(default_factory=list)
    id: UUID | None = None


class ConnectOp(BaseModel):
    """Wire one typed flow. ``edge_type`` None derives from the two ends'
    port offers (ctx = the reference/context flow)."""

    op: Literal["connect"]
    from_node: UUID
    to_node: UUID
    edge_type: Literal["video", "audio", "text", "ctx"] | None = None
    from_port: str | None = None
    to_port: str | None = None


class EditPromptOp(BaseModel):
    """Rewrite a program-bearing node's prompt — the card-face direct edit
    AND the chat-pointed revision are this one op. A done node goes stale
    (its product predates the new program); a running node rejects (it is
    executing the old program — the revision reruns it). Gate (ADR-076
    过渡): ``spec.tool`` 存在 or the legacy generator/agent kinds — a
    tool-less document never has an editable program."""

    op: Literal["edit_prompt"]
    node: UUID
    prompt: str


class EditTextOp(BaseModel):
    """Rewrite a document node's EDITABLE text layer (Workspace 合同 v4.2
    C4 — Transcript 双层, 2026-09-26 封板): the card-face in-place edit and
    the chat-pointed transcript revision are this one op, through the graph's
    ONE write door — same entity identity, version evolution (the displaced
    display text appends to ``spec.text_edits``), never a new work.

    C4 invariants, structural by construction: the write touches ONLY the
    presentation overlay (``spec.edited_text``) — the source mirror
    (``spec.text``), the asset's source transcript (``assets.transcript``),
    the word-level evidence (``assets.meta["words"]``), and every range stay
    untouched: text changed / evidence unchanged / range unchanged. No code
    path reverse-computes a timecode from the edited text.

    ``text`` None = clear the overlay (the card reads the source layer
    again). Gate: a transcript document (``type=="document"`` +
    ``spec.role=="transcript"`` — the companion caption document's direct
    edit rides the same op when its surface lands; program-bearing nodes
    edit via ``edit_prompt``, never this)."""

    op: Literal["edit_text"]
    node: UUID
    text: str | None = None


class DeleteNodeOp(BaseModel):
    """Remove a node; its edges die with it structurally. Products
    (outputs rows) are NOT touched — they have their own lifecycle
    (DELETE /outputs/{id})."""

    op: Literal["delete_node"]
    node: UUID


class DisconnectOp(BaseModel):
    """Sever one typed flow. The stamp reconciliation's seat (2026-09-10
    边对账律, ADR-062): the compiled topology owns every edge among its own
    members — an edge the compile no longer emits is retracted through this
    op, never left lingering next to the new set (the run-fill's grow-only
    law covers nodes/history, never a stale topology claim). A compiler-
    internal gesture: the prompt catalog never lists it, chat proposals
    never emit it."""

    op: Literal["disconnect"]
    from_node: UUID
    to_node: UUID
    edge_type: Literal["video", "audio", "text", "ctx"]


class RunOp(BaseModel):
    """Fill nodes (an execution event, not a graph write). ``nodes`` None =
    the batch's affected subgraph; the resolved set always closes over
    downstream (a node rerun refills what feeds off it). Execution itself
    stays at orchestrator.create_run — this op only resolves the target."""

    op: Literal["run"]
    nodes: list[UUID] | None = None


WiringOp = Annotated[
    AddNodeOp | ConnectOp | DisconnectOp | EditPromptOp | EditTextOp | DeleteNodeOp | RunOp,
    Field(discriminator="op"),
]

WIRING_OPS: dict[str, type[BaseModel]] = {
    "add_node": AddNodeOp,
    "connect": ConnectOp,
    "disconnect": DisconnectOp,
    "edit_prompt": EditPromptOp,
    "edit_text": EditTextOp,
    "delete_node": DeleteNodeOp,
    "run": RunOp,
}

_OPS_ADAPTER: TypeAdapter[Any] = TypeAdapter(list[WiringOp])


def wiring_catalog_lines() -> str:
    """The registry's self-projection as prompt lines (注册表条目扰动 =
    prompt 扰动纪律: entries stay terse + the gate enumerations ride along).
    The chat intent surfaces consume this verbatim — K4 wires it in. 词表
    v3 (ADR-076, C4): the addable vocabulary is the five media values
    (assets / documents are server-born, never proposed)."""
    return "\n".join(
        [
            "- add_node: place a node (type: text|table|image|video|audio; "
            "spec: the node's program — prompt/params; after: upstream node ids to wire from)",
            "- connect: wire a typed flow between two nodes "
            "(edge_type: video|audio|text|ctx — ctx = the reference/context flow)",
            "- edit_prompt: rewrite a node's prompt (nodes carrying spec.tool)",
            "- edit_text: rewrite a transcript document's editable text layer "
            "(presentation overlay — the source evidence never changes; "
            "text: the new text, or null to clear the overlay)",
            "- delete_node: remove a PROVISIONAL draft node (its edges go "
            "with it) — a settled entity is append-only and the door "
            "rejects its deletion",
            "- run: fill nodes with products (nodes optional — default = the "
            "affected subgraph; always closes over downstream)",
        ]
    )


# ---- ports (the port law's data half) ---------------------------------------

# type → (offers, accepts). An edge's type must be offered by its source and
# accepted by its target; ctx is the universal context flow (never the only
# choice when a concrete type is shared — the derivation prefers it last).
_NODE_PORTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    # ── legacy 五型 (读容忍 — 旧行连线仍要过门) ──────────────────────────
    "asset": (frozenset(), frozenset()),  # per asset type — see _offers/_accepts
    "document": (frozenset({"text", "ctx"}), frozenset({"text"})),
    "generator": (
        frozenset({"video", "audio", "text"}),
        frozenset({"video", "audio", "text", "ctx"}),
    ),
    "processor": (
        frozenset({"video"}),
        frozenset({"video", "audio", "text", "ctx"}),
    ),
    "agent": (frozenset({"text"}), frozenset({"text", "ctx"})),
    # ── 词表 v3 媒介五值 (ADR-076, C2a 门层先行) ─────────────────────────
    # accepts 先取并集 (prototype 收紧归后续批次). ctx 过渡必须: 任务书→
    # writer 的 ctx 边打到新 text 型 writer 节点, 缺它整 stamp 批 422 ——
    # 本批最高危交互点.
    "text": (frozenset({"text"}), frozenset({"text", "ctx"})),
    "table": (frozenset({"text"}), frozenset({"text", "ctx"})),
    # image 是渲染侧 glyph: 边类型词表无 image (ConnectOp.edge_type 四值),
    # 它从不过线 —— offers 只有 text.
    "image": (frozenset({"text"}), frozenset({"text", "ctx"})),
    "video": (
        frozenset({"video", "audio", "text"}),
        frozenset({"video", "audio", "text", "ctx"}),
    ),
    "audio": (
        frozenset({"audio", "text"}),
        frozenset({"audio", "text", "ctx"}),
    ),
}

# An asset's out-ports by its asset type (the three-flow source: a video
# offers video + audio + the transcript text).
_ASSET_OFFERS: dict[str, frozenset[str]] = {
    "video": frozenset({"video", "audio", "text"}),
    "audio": frozenset({"audio", "text"}),
    "image": frozenset({"video", "text"}),
    "slides": frozenset({"video", "text"}),
}


def _offers(node: GraphNode) -> frozenset[str]:
    if node.type == "asset":
        return _ASSET_OFFERS.get(
            str((node.spec or {}).get("asset_type") or ""), frozenset({"text"})
        )
    return _NODE_PORTS.get(node.type, (frozenset(), frozenset()))[0]


def _accepts(node: GraphNode) -> frozenset[str]:
    return _NODE_PORTS.get(node.type, (frozenset(), frozenset()))[1]


def _derive_edge_type(from_node: GraphNode, to_node: GraphNode) -> str:
    """The shared concrete type, ctx last — never an invented flow."""
    common = _offers(from_node) & _accepts(to_node)
    for candidate in ("video", "audio", "text"):
        if candidate in common:
            return candidate
    if "ctx" in common or "ctx" in _accepts(to_node):
        return "ctx"
    raise WiringRejected(
        f"No compatible port between {from_node.type} and {to_node.type}"
    )


# ---- layout (画布定居取景: assigned once, append-only) ----------------------

# Canvas frames per SIZE CLASS (w, h) — the graph surface's reserved boxes.
# Heights reserve the class's MAX content height (the frontend renders
# content-driven heights inside the reservation, so a column never overlaps
# and a node fills into its reservation as products land): clip = the 9:16
# product card's full anatomy (caption 26 + thumb 498 + program 88 + bar
# 44); text = the 12-line text card's (caption 26 + body 282 + program 88 +
# bar 44). A node's class comes from spec.frame_class (the fill stamps it
# from the family's product vocabulary); an unstamped generator/processor/
# agent reserves the clip maximum — safe by construction.
_GAP_MAIN = 124
_GAP_CROSS = 16

# ---- display aspect classes (2026-09-13 用户拍板 — 产物卡跟源比例 + 分档加宽)
# The source media's REAL pixels snap to the nearest of the three display
# classes (geometric-mean boundaries: 0.75 sits between 9:16 and 1:1, 4:3
# between 1:1 and 16:9 — the snap picks the least-bars box, off-ratios keep
# their contain slivers, never a crop). "original"-aspect chains
# (whole-source / transform, never reframe) resolve to the source's class at
# stamp time when dims are known (meta.width/height — probed at upload /
# processing); unknown dims keep the 16:9 default strip, read-tolerant.
def display_aspect_class(width: int | float, height: int | float) -> str:
    """One source's dims → its display class (nearest ratio, no crop)."""
    r = width / height
    if r < 0.75:
        return "9:16"
    if r < 1.334:
        return "1:1"
    return "16:9"


def resolve_source_aspect(dims: list[tuple[int, int]]) -> str | None:
    """The faced sources' ONE display class — mixed / unknown shapes stay
    "original" (the conservative default strip), never a coin flip."""
    classes = {display_aspect_class(w, h) for w, h in dims if w > 0 and h > 0}
    return classes.pop() if len(classes) == 1 else None
# A fresh column's first node RISES above its topmost parent (2026-09-09
# 走查拍板, FLORA 同典): out-ports ride the parent's top-RIGHT (~54px from
# its top: outBase 40 + half the 28px anchor), in-ports the child's
# bottom-LEFT (~204px from its top at the draft anatomy: 26+120+88+44 −
# inBase 60 − half the anchor), so a top-aligned child forces every edge
# into a steep S across the gap. Lifting the child by the port-geometry
# delta minus slack (204 − 54 − 62) lets the line arc gently — the slack
# term grew with the C6 间距收紧 (2026-09-14 拍板 88): tighter columns
# rise less above their parents.
_FRESH_COLUMN_RISE = 88
_FRAME_CLASS: dict[str, tuple[int, int]] = {
    "asset": (280, 260),
    # 260 → 340 (2026-09-13 用户拍板——文字节点增大): the document joins the
    # text/agent lane width; the pitch (464) is unaffected since the widest
    # class stays the 400 clip. The measurement law's chars-per-line scales
    # with the column (below); nodes born at 260 keep their stamped frame
    # (append-only 保序律, the text-class precedent).
    "document": (340, 200),
    # 440 → 560 (2026-09-10 用户拍板——内容长度驱动卡高): the taller text
    # reservation derives an 18-line preview cap (was 12) client-side; the
    # cap is computed FROM each node's own reservation, so nodes born under
    # 440 keep their 12-line guarantee — append-only 保序律 covers size law
    # changes without migration.
    "text": (340, 560),
    # The clip entry is the class MAX — the unstamped fallback (wiring-born
    # nodes), safe by construction. Stamped clip nodes reserve their aspect's
    # own anatomy via _CLIP_FRAME.
    "clip": (400, 660),
}
_KIND_FRAME_CLASS = {"asset": "asset", "document": "document"}

# The shorts craft default (ONE seat, 2026-09-28): the aspect a CUT chain
# (select_clips / cut_segments) resolves to when nothing names one — the
# runtime's own fallback chain (node.spec → run ctx → exemplar skeleton →
# skin block, which never carries aspect) bottoms out here (tools/clips/
# cut.py + node.py), and the graph frame's predictive mirror
# (graph_fill._predict_family_frame_aspect) reads the same seat so the born
# frame can never disagree with the render (the 16:9-frame / 9:16-clip
# walkthrough). Whole-source chains never see it (比例跟源 — "original"
# stays theirs, materialize.py 2026-08-17 拍板).
SHORTS_DEFAULT_ASPECT = "9:16"

# The clip-class frame's per-aspect reservations (2026-09-11 aspect-exact
# heights; 2026-09-13 用户拍板 分档加宽 — the lane WIDTH now follows the
# aspect too: 横屏真正能看, the portrait tower stays put): the fill stamps
# spec.frame_aspect (graph_fill._frame_class_of — the chain's explicit aspect
# wins; an UNSTAMPED clip family predicts the runtime's own resolution —
# graph_fill._predict_family_frame_aspect: cut chains → SHORTS_DEFAULT_ASPECT
# (or the exemplar's measured class), transform chains inherit their upstream
# producer's aspect; only whole-source chains resolve "original" to the
# source's display class — meta.width/height, unknown dims keep the
# "original" default strip). The math is ONE law with the client (layout.ts
# clipNodeHeight = caption 26 + PRODUCT_THUMB_PX[aspect] + program 88 + bar
# 44, media at the lane width) — two mirrors cross-referenced, never a third
# copy (判词②). 9:16 keeps its 660 (the 4px breath included); an unstamped
# clip node keeps the class max.
_CLIP_FRAME: dict[str, tuple[int, int]] = {
    "9:16": (280, 660),
    "1:1": (340, 498),
    "16:9": (400, 383),
    # "original" with unknown dims — the legacy 280-wide 16:9 strip.
    "original": (280, 316),
}

# Asset node frames by the source's display class (2026-09-13 — 素材节点同律,
# media + caption 26 + toolbar 44): stamped at birth by stamp_asset_node from
# meta.width/height (client-probed at upload; the chain-head probe backfills
# API-path uploads too late for the frame — their nodes keep the default).
# One law with the client mirror (layout.ts graphNodeSize's asset branch).
_ASSET_FRAME: dict[str, tuple[int, int]] = {
    "9:16": (280, 568),
    "1:1": (340, 410),
    "16:9": (400, 295),
}
_ASSET_FRAME_DEFAULT = _FRAME_CLASS["asset"]

# The task-book document's role tag. Production stopped (Workspace 合同
# v4.2 C1-b de-stamp, 2026-09-26 封板 — the word survives for legacy-row
# reads: clear_draft_graph's draft sweep and product_graph's HIDDEN_ROLES
# gate). One home here — the graph's role vocabulary is the door's
# business, never a magic string per call site.
_TASK_BOOK_ROLE = "task_book"

# 全文卡律 (2026-09-10 判词④——进了卡面的必须原文全文，无摘要无浓缩) + 封顶
# 滚动律 (2026-09-11): the document card never truncates — it carries the full
# text and SCROLLS in place past the card's cap, so a text-bearing document's
# frame is born at the text's full height CAPPED at _DOCUMENT_MAX_H (above the
# cap the estimate only decides whether the cap binds, so its error can no
# longer push prose past the frame — the 1.7× CJK underestimate that let a
# 340s transcript tower ~3000px and bleed through the task book's confirm
# beat). The line math is ONE law with the client's shared measurement
# (apps/web/src/components/flow/layout.ts — the text card's chars-per-line
# table, scaled proportionally to the document's narrower text width); two
# mirrors cross-referenced, never a third copy (判词②).
_DOCUMENT_LINE_PX = 18  # text-xs leading-relaxed (same as the text card)
_DOCUMENT_CAPTION_PX = 26  # NodeCaption band (= PRODUCT_LABEL_PX)
# The cap — one law with the client mirror (layout.ts DOCUMENT_MAX_H); the
# value = the text frame class's 560 reservation.
_DOCUMENT_MAX_H = 560
# The floor (2026-09-13 用户拍板 高度增大): a short text still gets a reading
# surface, never a 3-line stub — peer to the generator quiet body (~278).
# One law with the client mirror (layout.ts DOCUMENT_MIN_H).
_DOCUMENT_MIN_H = 280
_CJK_RE = re.compile(r"[一-龥぀-ゟ゠-ヿ]")


def _document_frame(spec: dict[str, Any]) -> tuple[int, int]:
    w, _ = _FRAME_CLASS["document"]
    text = str(spec.get("text") or "")
    # The text card's table is 44 CJK / 68 Latin chars per 312px of text
    # width; the document's column is 308px (340 frame − 2×16 padding,
    # 2026-09-13 增大批 — was 228px at 260) — the same proportion (one law),
    # rounding DOWN so the frame errs tall (whitespace, never overflow):
    # 44×308/312 → 43, 68×308/312 → 67.
    cjk = bool(_CJK_RE.search(text))
    chars_per_line = 43 if cjk else 67
    lines = max(1, math.ceil(len(text) / chars_per_line)) if text else 1
    h = _DOCUMENT_CAPTION_PX + 16 + lines * _DOCUMENT_LINE_PX + 16
    return w, min(max(h, _DOCUMENT_MIN_H), _DOCUMENT_MAX_H)

# 统一摆位律 (2026-09-09 拍板): ONE frame law owns every newborn's frame
# (_assign_layout), and columns are DEPTH-pitched — x = depth × _PITCH,
# never derived from a parent's right edge (mixed frame widths made
# parent-right columns ragged: same-column nodes of different widths hand
# their children different starts, and same-depth siblings drift into
# horizontal overlap). Depth = the topological generation (max parent
# depth + 1, islands 0), so a child always lands strictly right of EVERY
# parent by ≥ _GAP_MAIN. A node's column IS its depth — the frame's x is a
# rendering of it, never the source of truth. Frames of projects born
# before this law are replayed once by migration (see
# migrations/versions/e7a9c1d35b28_depth_pitch_frames.py).
_PITCH = max(w for w, _ in _FRAME_CLASS.values()) + _GAP_MAIN  # 400 + 124


def _frame_of(kind: str, spec: dict[str, Any]) -> tuple[int, int]:
    cls = _KIND_FRAME_CLASS.get(kind) or str(spec.get("frame_class") or "") or "clip"
    if cls == "document":
        return _document_frame(spec)
    if cls == "asset":
        # The source's display class, stamped at birth when its dims were
        # known — unknown dims keep the default reservation.
        return _ASSET_FRAME.get(
            str(spec.get("frame_aspect") or ""), _ASSET_FRAME_DEFAULT
        )
    if cls == "clip":
        # The aspect-exact reservation when the fill stamped one
        # (frame_aspect) — the class max stays the fallback for unstamped
        # nodes (legacy rows, wiring-born nodes), safe by construction.
        return _CLIP_FRAME.get(
            str(spec.get("frame_aspect") or ""), _FRAME_CLASS["clip"]
        )
    return _FRAME_CLASS.get(cls, _FRAME_CLASS["clip"])


def _assign_layout(
    kind: str,
    spec: dict[str, Any],
    depth: int,
    parents: list[GraphNode],
    column: list[GraphNode],
    *,
    x_slot: int | None = None,
    extra_tails: tuple[int, ...] = (),
    island_seat: tuple[GraphIsland, int] | None = None,
) -> dict[str, int]:
    """THE one frame law (统一摆位律) — every newborn's settled frame comes
    from this function and nowhere else:
      x = the band's slot origin × _PITCH   (depth-pitched columns, never
                                             ragged; island slots widen a
                                             band's origin math, C6 below)
      y = ① the column's tail + _GAP_CROSS  (siblings stack in place; the
              tail counts the islands' RESERVED bottoms — an island's empty
              corridor rows are never invaded)
          ② a fresh column → the topmost parent's y − _FRESH_COLUMN_RISE
             (the port-geometry delta — the out→in arc stays gentle)
          ③ an island → 0
    C6 岛内格 (Layout Island, v4.2): an islanded member skips the column
    law entirely — its frame is its FROZEN CELL: x = island.origin_x +
    (seq // cap) × _PITCH, y = island.origin_y + (seq % cap) × row_h.
    True over-capacity (seq ≥ cols × cap) extends the LAST reserved column
    downward (the contact-sheet seat — 留座不实现, 2026-09-26 用户拍板):
    vertical growth, never a right-edge breach.
    Existing frames NEVER move — the graph only grows, it never jolts
    (append-only 保序律)."""
    w, h = _frame_of(kind, spec)
    if island_seat is not None:
        island, seq = island_seat
        col = seq // island.cap
        row = seq % island.cap
        if col >= island.cols:
            col = island.cols - 1
            row = seq - col * island.cap
        return {
            "x": island.origin_x + col * _PITCH,
            "y": island.origin_y + row * island.row_h,
            "w": w,
            "h": h,
        }
    tails = [
        int((n.layout or {}).get("y", 0)) + int((n.layout or {}).get("h", h))
        for n in column
    ]
    tails.extend(extra_tails)
    if tails:
        y = max(tails) + _GAP_CROSS
    elif parents:
        y = min(int((p.layout or {}).get("y", 0)) for p in parents) - _FRESH_COLUMN_RISE
    else:
        y = 0
    return {"x": (x_slot if x_slot is not None else depth) * _PITCH, "y": y, "w": w, "h": h}


# ---- Layout Island (Workspace 合同 v4.2 C6, 2026-09-26 封板) -----------------
#
# 每个 sibling group 出生即定格一块独占布局区域: origin/size 冻结, 宽度按
# 设计容量预留 (含增长廊道), 成员岛内从上往下、到 C 换预留列; 岛的右缘永不
# 越过出生定格 → 后续 depth 带 / 兄弟 group 数学上不可能被侵占. 岛零 UI —
# 数据结构与摆位律, 画布永远没有「岛」的 chrome.

#: 组内容量参数 (C6「设计容量」的注册默认 — MODULE_ARCH §7 登记): 每列 C=4
#: 行; 出生列数 = ⌈成员数/C⌉ + 1 条增长廊道, 封顶 3 列. 廊道只在出生时刻
#: 更深的带还没有定居成员时才保留 (retroactive birth 永不侵占既有领土 —
#: cols 回落 1, 超容量走垂直延伸的 contact-sheet 留座).
_ISLAND_COL_CAPACITY = 4
_ISLAND_CORRIDOR_COLS = 1
_ISLAND_MAX_COLS = 3


def island_reserved_bottom(island: GraphIsland) -> int:
    """The island's frozen vertical reservation (cap rows of row_h) — the
    band tail's floor, so a later band-mate never invades empty corridor
    cells (岛内的事, 岛外永不让位)."""
    return island.origin_y + island.cap * island.row_h - _GAP_CROSS


async def _assign_islands(
    db: AsyncSession,
    project_id: UUID,
    islands: list[GraphIsland],
    newborns: list[GraphNode],
    placed: list[GraphNode],
    depth_of: Any,
    parents_of: Any,
    rank_parents_of: Any,
) -> tuple[dict[UUID, tuple[GraphIsland, int]], dict[int, int]]:
    """C6 出生定格分配: sibling family = same topological depth + same
    media-flow parent set (ctx 引用边永不定义同胞关系 — the Product Graph's
    edge boundary). Mutates ``islands`` in place (births append) so the
    settle pass's band-tail math sees them. Returns (node_id → (island,
    seq), band → reserved slot width).

    - Family ≥ 2 at a fresh seat → the island is BORN (origin = the band's
      slot origin × _PITCH / the band tail or the fresh-column rise; row_h
      = the family's max frame height + cross gap — sibling families share
      one frame class by construction).
    - An existing island at the seat → JOIN: the next cells. seq derives
      from LIVE members, so an orphaned island (members deleted — the draft
      re-stamp's delete+re-add) re-seats from 0 and re-lands on the same
      cells.
    - A lone newborn whose seat already holds a non-islanded sibling → the
      second promotion births the island ANCHORED at that sibling's frame
      (it joins as seq 0 WITHOUT moving — frames never move).
    - A lone newborn at an empty seat stays on the plain column law.

    TWO-PHASE (裸 FK flush 轮盘赌律): every birth's row is collected first
    and flushed BEFORE any membership stamp — without a relationship() the
    UOW's inter-table ordering is undriven, so the island INSERTs must
    provably precede the node writes that reference them."""
    seat_of: dict[UUID, tuple[GraphIsland, int]] = {}
    if not newborns:
        return seat_of, {}

    def parent_key(node_id: UUID) -> tuple[str, ...]:
        return tuple(sorted(str(p.id) for p in rank_parents_of(node_id)))

    def live_member_seqs(island: GraphIsland) -> list[int]:
        return [
            int(n.island_seq or 0)
            for n in [*placed, *newborns]
            if getattr(n, "island_id", None) is not None
            and UUID(str(n.island_id)) == UUID(str(island.id))
            and n.island_seq is not None
        ]

    slots: dict[int, int] = {}
    for isl in islands:
        slots[isl.depth] = max(slots.get(isl.depth, 1), isl.cols)

    def band_origin_slot(d: int) -> int:
        return d + sum(s - 1 for b, s in slots.items() if b < d)

    def band_tail(d: int) -> int | None:
        bottoms = [
            int((n.layout or {}).get("y", 0)) + int((n.layout or {}).get("h", 0))
            for n in placed
            if depth_of(UUID(str(n.id)), set()) == d
        ]
        bottoms.extend(
            island_reserved_bottom(i) for i in islands if i.depth == d
        )
        return max(bottoms) if bottoms else None

    deeper_occupied: dict[int, bool] = {}

    def deeper_band_occupied(d: int) -> bool:
        # The scan covers the batch's own newborns, not just settled
        # history: a corridor reserved while the same batch's chain
        # continuation (e.g. the reframe below the clips) is still
        # invisible would punch a permanently empty column into the
        # canvas on day one (2026-09-29 — 同批更深节点同样封死廊道).
        if d not in deeper_occupied:
            deeper_occupied[d] = any(
                depth_of(UUID(str(n.id)), set()) > d
                for n in [*placed, *newborns]
            )
        return deeper_occupied[d]

    # Group the newborns into sibling families (depth-first determinism).
    families: dict[tuple[int, tuple[str, ...]], list[GraphNode]] = {}
    for n in newborns:
        nid = UUID(str(n.id))
        key = (depth_of(nid, set()), parent_key(nid))
        families.setdefault(key, []).append(n)

    # Phase 1: decide every family's seat; birth the new island rows.
    birthed: list[tuple[GraphIsland, list[GraphNode], list[GraphNode]]] = []
    for (d, key), family in sorted(families.items()):
        match = next(
            (
                i
                for i in islands
                if i.depth == d and tuple(str(p) for p in (i.parent_ids or [])) == key
            ),
            None,
        )
        if match is not None:
            seqs = live_member_seqs(match)
            nxt = max(seqs) + 1 if seqs else 0
            for n in family:
                seat_of[UUID(str(n.id))] = (match, nxt)
                nxt += 1
            continue
        siblings = [
            n
            for n in placed
            if depth_of(UUID(str(n.id)), set()) == d
            and parent_key(UUID(str(n.id))) == key
            and getattr(n, "island_id", None) is None
        ]
        if len(family) < 2 and not siblings:
            continue  # a lone newborn at an empty seat — the plain column law
        count = len(family) + len(siblings)
        if deeper_band_occupied(d):
            # The corridor is a BIRTH reservation: deeper bands already
            # settled → no horizontal claim is legal; growth extends the
            # single column downward (the contact-sheet stopgap seat).
            cols = 1
        else:
            cols = min(
                max(1, -(-count // _ISLAND_COL_CAPACITY)) + _ISLAND_CORRIDOR_COLS,
                _ISLAND_MAX_COLS,
            )
        if siblings:
            # 第二次 promotion 定格 (C6: sibling 同列叠放只在第二次 promotion
            # 时才出现): anchor at the FIRST sibling's frame — it joins as
            # seq 0 without moving.
            anchor = siblings[0]
            origin_x = int((anchor.layout or {}).get("x", 0))
            origin_y = int((anchor.layout or {}).get("y", 0))
            heights = [int((s.layout or {}).get("h", 0)) for s in siblings]
        else:
            tail = band_tail(d)
            origin_x = band_origin_slot(d) * _PITCH
            if tail is not None:
                origin_y = tail + _GAP_CROSS
            else:
                # Fresh band: rise above the topmost parent — the frame
                # law's fresh-column rule, ALL parents (ctx included — the
                # rise is visual placement; only the sibling KEY is the
                # media-flow relation).
                ups = parents_of(UUID(str(family[0].id)))
                origin_y = (
                    min(int((p.layout or {}).get("y", 0)) for p in ups)
                    - _FRESH_COLUMN_RISE
                    if ups
                    else 0
                )
            heights = []
        row_h = (
            max(heights + [_frame_of(n.type, dict(n.spec or {}))[1] for n in family])
            + _GAP_CROSS
        )
        island = GraphIsland(
            id=uuid4(),
            project_id=project_id,
            depth=d,
            parent_ids=list(key),
            origin_x=origin_x,
            origin_y=origin_y,
            row_h=row_h,
            cols=cols,
            cap=_ISLAND_COL_CAPACITY,
        )
        db.add(island)
        islands.append(island)
        slots[d] = max(slots.get(d, 1), cols)
        birthed.append((island, siblings, family))

    if birthed:
        # Phase boundary (轮盘赌律): the island INSERTs land before ANY
        # membership stamp — the flush below carries no graph_nodes writes
        # yet (the batch's node rows are still transient at this point).
        await db.flush()

    # Phase 2: stamp memberships (retroactive siblings keep their frames —
    # the anchor's frame IS cell (0, 0), zero movement).
    for island, siblings, family in birthed:
        nxt = 0
        for s in siblings:
            s.island_id = island.id
            s.island_seq = nxt
            nxt += 1
        for n in family:
            seat_of[UUID(str(n.id))] = (island, nxt)
            nxt += 1
    return seat_of, slots


async def settle_frames_with_edges(
    newborns: list[GraphNode],
    placed: list[GraphNode],
    edges: list[GraphEdge],
    island_ctx: tuple[AsyncSession, UUID, list[GraphIsland]] | None = None,
) -> None:
    """The door's frame settle (画布定居取景): every newborn's frame is
    assigned ONCE — by _assign_layout, the one frame law — parents-first
    over the batch's FINAL edge set (a node is born with full edge
    knowledge, never an island guess repaired later; 2026-09-08 用户拍板:
    布局一开始就定好). ``placed`` = the settled history — existing frames
    NEVER move (append-only 保序律); the newborns' provisional add-time
    values are replaced before the flush, so no provisional frame is ever
    persisted."""
    by_id = {UUID(str(n.id)): n for n in [*placed, *newborns]}

    # ADR-098 §1 — Effective Product Graph 唯一拓扑层: the settle eats the
    # EFFECTIVE edge set (persisted + A3-lite synthesized transcript→consumer
    # legs) from the SAME pure function the /graph read face projects — birth
    # frames and the read projection share one graph (a consumer is depth 2
    # AT BIRTH, never re-read deeper later). Two input notes: ① the working
    # set's transcript documents may be same-batch newborns not yet flushed
    # — the function consumes the in-memory object collection, never a DB
    # query; ② synthesized rows are plain dicts (read-time data) — they
    # stay in THIS local, never join ``edges`` (the door's edge flush
    # asserts the landed set is dict-free — 合成边永不落库).
    effective_edges = effective_rank_edges([*placed, *newborns], edges)

    def _eget(edge: Any, key: str) -> Any:
        # The effective set mixes ORM rows (persisted) and dicts
        # (synthesized) — one reader for both (routes' _eget precedent).
        return edge.get(key) if isinstance(edge, dict) else getattr(edge, key)

    def parents_of(node_id: UUID) -> list[GraphNode]:
        return [
            by_id[UUID(str(_eget(e, "from_node")))]
            for e in effective_edges
            if UUID(str(_eget(e, "to_node"))) == node_id
            and UUID(str(_eget(e, "from_node"))) in by_id
        ]

    # Media-flow parents only (物料流三值 — the Product Graph's edge
    # boundary): siblinghood is a product relation; ctx 引用边 never joins
    # the parent key. The depth/parent-key split is deliberate and kept
    # as-is (depth_of below walks ALL effective edges, ctx included — the
    # frame's fresh-column rise is visual placement; only the sibling KEY
    # is the media-flow relation).
    def rank_parents_of(node_id: UUID) -> list[GraphNode]:
        return [
            by_id[UUID(str(_eget(e, "from_node")))]
            for e in effective_edges
            if UUID(str(_eget(e, "to_node"))) == node_id
            and str(_eget(e, "edge_type")) in RANK_EDGE_TYPES
            and UUID(str(_eget(e, "from_node"))) in by_id
        ]

    # Depth = the topological generation (max parent depth + 1, islands 0),
    # memoized over the FINAL edge set — settled history derives it the same
    # way (a node's column IS its depth; the frame's x merely renders it).
    # The cycle guard only keeps a poisoned world from looping forever — the
    # wiring adjudication rejects cycles before this ever runs.
    depth_memo: dict[UUID, int] = {}

    def depth_of(node_id: UUID, trail: set[UUID]) -> int:
        memo = depth_memo.get(node_id)
        if memo is not None:
            return memo
        if node_id in trail:
            return 0
        trail.add(node_id)
        ups = parents_of(node_id)
        d = 0 if not ups else max(depth_of(UUID(str(p.id)), trail) for p in ups) + 1
        depth_memo[node_id] = d
        return d

    # C6 出生定格: seat the sibling families into layout islands BEFORE any
    # frame — the corridor's slot math then applies to every frame in the
    # batch (island cells and the plain column law alike).
    seat_of: dict[UUID, tuple[GraphIsland, int]] = {}
    island_slots: dict[int, int] = {}
    island_rows: list[GraphIsland] = []
    if island_ctx is not None:
        island_db, island_project_id, island_rows = island_ctx
        seat_of, island_slots = await _assign_islands(
            island_db,
            island_project_id,
            island_rows,
            newborns,
            placed,
            depth_of,
            parents_of,
            rank_parents_of,
        )

    def band_origin_slot(d: int) -> int:
        """The band's x slot: depth + the corridor slots the earlier bands'
        islands reserved (a band with no islands keeps the legacy 1:1
        depth↔slot mapping)."""
        return d + sum(s - 1 for b, s in island_slots.items() if b < d)

    def frame_of(node: GraphNode) -> None:
        nid = UUID(str(node.id))
        depth = depth_of(nid, set())
        parents = parents_of(nid)
        seat = seat_of.get(nid)
        if seat is not None:
            island, seq = seat
            node.island_id = island.id
            node.island_seq = seq
        column = [n for n in working if depth_of(UUID(str(n.id)), set()) == depth]
        node.layout = _assign_layout(
            node.type,
            node.spec or {},
            depth,
            parents,
            column,
            x_slot=band_origin_slot(depth),
            # The islands' reserved bottoms floor the band's tail — empty
            # corridor cells are never invaded by a later band-mate.
            extra_tails=tuple(
                island_reserved_bottom(i) for i in island_rows if i.depth == depth
            ),
            island_seat=seat,
        )

    settled = {UUID(str(n.id)) for n in placed}
    working = list(placed)
    pending = list(newborns)
    # Parents-first passes: a newborn whose parent is also a newborn waits
    # for the pass that settles it (a chain settles one link per pass).
    # Structurally cycle-free (the wiring adjudication rejects cycles); the
    # fallback below settles whatever remains rather than loop forever.
    while pending:
        progressed = False
        for node in list(pending):
            nid = UUID(str(node.id))
            if any(UUID(str(p.id)) not in settled for p in parents_of(nid)):
                continue
            frame_of(node)
            working.append(node)
            settled.add(nid)
            pending.remove(node)
            progressed = True
        if not progressed:
            for node in pending:
                frame_of(node)
                working.append(node)
            break


# ---- the delta ---------------------------------------------------------------


class GraphDelta(BaseModel):
    """What a wiring batch changed. ``affected`` = nodes touched (added /
    prompt-edited / deleted). ``run_nodes`` = a run op's resolved target
    subgraph (seeds ∪ downstream, deterministic order); None = the batch
    carried no run op."""

    affected: list[UUID] = Field(default_factory=list)
    run_nodes: list[UUID] | None = None


# ---- the write door ------------------------------------------------------------


async def apply_wiring_ops(
    db: AsyncSession,
    project_id: UUID,
    ops: list[dict[str, Any] | BaseModel],
    *,
    allow_settled_delete: bool = False,
) -> GraphDelta:
    """Validate and land one batch of wiring ops. THE graph's only write.

    Flush-only — the caller commits (the batch commits atomically with the
    turn that caused it, create_run precedent). Raises WiringRejected; the
    whole batch dies together, never a half-applied graph.

    ``allow_settled_delete`` is the settled guard's bypass (Workspace 合同
    v4.2 封板⑤, 2026-09-27): delete_node rejects a non-draft node by
    default — a settled entity is append-only, and the chat/LLM path never
    gets the bypass. The ONE legal settled-delete caller is the asset
    module's own lifecycle (``remove_asset_node`` — an asset's deletion
    takes its graph twin and transcript document with it); every
    provisional cleanup (draft teardown / orphan sweep) deletes draft-state
    nodes and needs no bypass.
    """
    parsed: list[BaseModel] = _OPS_ADAPTER.validate_python(ops)
    project = await db.get(Project, project_id)
    if project is None:
        raise WiringRejected(f"Project not found: {project_id}")

    nodes: dict[UUID, GraphNode] = {
        UUID(str(n.id)): n
        for n in (
            await db.execute(
                select(GraphNode).where(GraphNode.project_id == project_id)
            )
        )
        .scalars()
        .all()
    }
    edges: list[GraphEdge] = list(
        (
            await db.execute(
                select(GraphEdge).where(GraphEdge.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    # Persistent-at-load edges (disconnect needs the distinction: a pre-
    # existing row takes a real DELETE, a same-batch newborn just drops out
    # of the working list before it ever lands).
    persisted_edge_ids = {id(e) for e in edges}

    # I-EXPLORE-01 反向守卫 (ADR-088 §4, R14 双门): the execution door writes
    # the EXECUTION family only — exploration artifacts are born edgeless by
    # exploration_store's own door, and no wiring op may birth, wire, edit,
    # delete, or run them. One seat covers the batch: the op vocabulary
    # (R14's 零 op 词汇 spirit) never grows exploration branches here.
    _exploration_ids = {
        UUID(str(n.id))
        for n in nodes.values()
        if (n.spec or {}).get("prototype") == EXPLORATION_PROTOTYPE
    }
    for op in parsed:
        if isinstance(op, AddNodeOp):
            if (op.spec or {}).get("prototype") == EXPLORATION_PROTOTYPE:
                raise WiringRejected(
                    "add_node: exploration artifacts land via the exploration "
                    "door (exploration_store), never the execution door"
                )
            unknown_exploration = op.after and any(
                parent_id in _exploration_ids for parent_id in op.after
            )
            if unknown_exploration:
                raise WiringRejected(
                    "add_node: an exploration artifact cannot parent an "
                    "execution node (I-EXPLORE-01)"
                )
            continue
        refs: list[UUID] = []
        if isinstance(op, (ConnectOp, DisconnectOp)):
            refs = [op.from_node, op.to_node]
        elif isinstance(op, (EditPromptOp, DeleteNodeOp)):
            refs = [op.node]
        elif isinstance(op, RunOp) and op.nodes is not None:
            refs = list(op.nodes)
        if any(r in _exploration_ids for r in refs):
            raise WiringRejected(
                f"{op.op}: exploration artifacts never participate in "
                "execution topology (I-EXPLORE-01) — the exploration door "
                "owns them"
            )

    def children_of(node_id: UUID) -> list[UUID]:
        return [UUID(str(e.to_node)) for e in edges if UUID(str(e.from_node)) == node_id]

    def reaches(
        start: UUID, target: UUID, *, children=children_of
    ) -> bool:
        """Downstream reachability over the working edge set (cycle checks
        and run-subgraph closure share this one walk; the run closure passes
        the lineage-excluding child set — cycle checks keep the full one)."""
        seen: set[UUID] = set()
        frontier = [start]
        while frontier:
            cur = frontier.pop()
            if cur == target:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            frontier.extend(children(cur))
        return False

    def add_edge(
        from_id: UUID,
        to_id: UUID,
        edge_type: str | None,
        from_port: str | None,
        to_port: str | None,
    ) -> None:
        from_node = nodes.get(from_id)
        to_node = nodes.get(to_id)
        if from_node is None or to_node is None:
            raise WiringRejected(f"connect: dangling reference {from_id} → {to_id}")
        if from_id == to_id:
            raise WiringRejected("connect: a node cannot feed itself")
        etype = edge_type or _derive_edge_type(from_node, to_node)
        if etype not in _offers(from_node):
            raise WiringRejected(
                f"connect: {from_node.type} does not offer {etype}"
            )
        if etype not in _accepts(to_node):
            raise WiringRejected(f"connect: {to_node.type} does not accept {etype}")
        # Settled Rank 冻结律 (ADR-098 §2 — Z): a rank-relevant edge into a
        # non-draft target would re-rank a settled node — rejected at the
        # door. Rank-relevant = 物料流三值 minus the lineage port-marked
        # 真边 (血缘而非物料流, rank 豁免——run fill 的 lineage 盖章合法落
        # 在 queued deliverable 上, graph_fill §7); ctx 永不入 rank, 天然
        # 豁免. Draft targets pass untouched — the provisional machine
        # (reseat / orphan sweep) keeps its old behavior.
        if (
            etype in RANK_EDGE_TYPES
            and not is_lineage_edge({"from_port": from_port or f"out:{etype}"})
            and str(to_node.state) != "draft"
        ):
            raise WiringRejected(
                f"connect: settled target {to_id} (state {to_node.state!r}) — "
                "a node's rank freezes when it leaves draft (ADR-098 Z); "
                "rewiring settled nodes goes through a named lifecycle "
                "exception, never a bare op"
            )
        if reaches(to_id, from_id):
            raise WiringRejected("connect: the edge would close a cycle")
        if any(
            UUID(str(e.from_node)) == from_id
            and UUID(str(e.to_node)) == to_id
            and e.edge_type == etype
            for e in edges
        ):
            raise WiringRejected(f"connect: duplicate {etype} edge {from_id} → {to_id}")
        edges.append(
            GraphEdge(
                id=uuid4(),
                project_id=project_id,
                from_node=from_id,
                from_port=from_port or f"out:{etype}",
                to_node=to_id,
                to_port=to_port or f"in:{etype}",
                edge_type=etype,
            )
        )

    delta = GraphDelta()
    pending_delete: list[UUID] = []
    newborn_ids: list[UUID] = []  # op order — the post-loop layout pass

    for op in parsed:
        if isinstance(op, AddNodeOp):
            if op.id is not None and op.id in nodes:
                raise WiringRejected(f"add_node: id {op.id} already exists")
            parents = []
            for parent_id in op.after:
                parent = nodes.get(parent_id)
                if parent is None:
                    raise WiringRejected(f"add_node: unknown upstream {parent_id}")
                parents.append(parent)
            pw, ph = _frame_of(op.type, dict(op.spec))
            node = GraphNode(
                # Explicit ids: the working map wires after-edges off them
                # BEFORE the flush (the column default only fires at INSERT).
                # A stamper-pinned id (op.id) lets the SAME batch's connect
                # ops reference the newborn — frames born with full edge
                # knowledge.
                id=op.id or uuid4(),
                project_id=project_id,
                type=op.type,
                # Assets are inputs, not execution units — their content is
                # self-evident at birth (processing status lives on the
                # asset row itself). Everything else is born a draft
                # (图先展示后运行 — zero consumption until a run fills it).
                state="done" if op.type == "asset" else "draft",
                spec=dict(op.spec),
                # Provisional frame (a placeholder — the door's settle
                # replaces it with the frame law's output before the flush,
                # so no provisional value is ever persisted). Pitch-monotone
                # (right of every parent, risen with them) so the run op's
                # layout-ordered subgraph reads the same before and after
                # the settle.
                layout={
                    "x": (
                        max(int((p.layout or {}).get("x", 0)) for p in parents) + _PITCH
                        if parents
                        else 0
                    ),
                    "y": (
                        min(int((p.layout or {}).get("y", 0)) for p in parents)
                        - _FRESH_COLUMN_RISE
                        if parents
                        else 0
                    ),
                    "w": pw,
                    "h": ph,
                },
            )
            nodes[UUID(str(node.id))] = node
            newborn_ids.append(UUID(str(node.id)))
            delta.affected.append(UUID(str(node.id)))
            for parent_id in op.after:
                add_edge(parent_id, UUID(str(node.id)), None, None, None)
        elif isinstance(op, ConnectOp):
            add_edge(op.from_node, op.to_node, op.edge_type, op.from_port, op.to_port)
        elif isinstance(op, DisconnectOp):
            match = next(
                (
                    e
                    for e in edges
                    if UUID(str(e.from_node)) == op.from_node
                    and UUID(str(e.to_node)) == op.to_node
                    and e.edge_type == op.edge_type
                ),
                None,
            )
            if match is None:
                raise WiringRejected(
                    f"disconnect: no {op.edge_type} edge {op.from_node} → {op.to_node}"
                )
            # Settled Rank 冻结律 (ADR-098 §2 — Z), the disconnect landing's
            # same predicate: severing a rank-relevant edge into a non-draft
            # target re-ranks a settled node. Lineage port-marked edges and
            # ctx are rank-exempt; draft targets pass untouched.
            disconnect_target = nodes.get(op.to_node)
            if (
                match.edge_type in RANK_EDGE_TYPES
                and not is_lineage_edge(match)
                and disconnect_target is not None
                and str(disconnect_target.state) != "draft"
            ):
                raise WiringRejected(
                    f"disconnect: settled target {op.to_node} (state "
                    f"{disconnect_target.state!r}) — a node's rank freezes "
                    "when it leaves draft (ADR-098 Z)"
                )
            edges.remove(match)
            if id(match) in persisted_edge_ids:
                await db.delete(match)
        elif isinstance(op, EditPromptOp):
            node = nodes.get(op.node)
            if node is None:
                raise WiringRejected(f"edit_prompt: unknown node {op.node}")
            # ADR-076 过渡闸门: the executing body's presence (spec.tool)
            # marks an editable program — a tool-less document (transcript /
            # task book / brief) never has one; the legacy two-kind fallback
            # covers pre-v3 rows stamped without tool. 终态闸门 =
            # prototype=="generator" (批 B4 set_param 落地前 editor 的修订
            # 路不能断), 卡面 hover wash 与本报文同真值 (批 C1).
            if not (node.spec or {}).get("tool") and node.type not in ("generator", "agent"):
                raise WiringRejected(
                    f"edit_prompt: a {node.type} node has no prompt to edit"
                )
            if node.state in ("queued", "running"):
                raise WiringRejected(
                    "edit_prompt: the node is running its program — let it "
                    "finish, then revise"
                )
            node.spec = {**(node.spec or {}), "prompt": op.prompt}
            if node.state == "done":
                # The product now predates the program — stale until the
                # revision reruns it (原型 C: stale = factsbar 可重跑徽章).
                node.state = "stale"
            delta.affected.append(op.node)
        elif isinstance(op, EditTextOp):
            node = nodes.get(op.node)
            if node is None:
                raise WiringRejected(f"edit_text: unknown node {op.node}")
            # C4 gate: the transcript document's presentation overlay is the
            # ONLY editable text layer (the source mirror / word evidence /
            # ranges are never this op's business — structural invariant).
            if node.type != "document" or (node.spec or {}).get("role") != "transcript":
                raise WiringRejected(
                    f"edit_text: a {node.type} node (role "
                    f"{(node.spec or {}).get('role')!r}) has no editable text layer"
                )
            spec = dict(node.spec or {})
            # Version evolution (C2 — Revision ≠ New Work): the displaced
            # display layer appends to the edit history (append-only memory,
            # capped — version memory, not infinite undo); the overlay
            # replaces it. text=None clears the overlay back to the source
            # layer (still a version step — the displaced overlay is kept).
            previous = spec.get("edited_text")
            if previous is None:
                previous = spec.get("text")
            history = list(spec.get("text_edits") or [])
            history.append(
                {"text": previous or "", "at": now_utc().isoformat()}
            )
            del history[:-50]
            spec["text_edits"] = history
            if op.text is None:
                spec.pop("edited_text", None)
            else:
                spec["edited_text"] = op.text
            node.spec = spec
            delta.affected.append(op.node)
        elif isinstance(op, DeleteNodeOp):
            node = nodes.get(op.node)
            if node is None:
                raise WiringRejected(f"delete_node: unknown node {op.node}")
            # Settled guard (Workspace 合同 v4.2 封板⑤ — Settled 只长不消,
            # provisional draft 可弃): a settled entity is append-only —
            # chat/LLM-issued deletes of settled work are rejected at the
            # door. Deletable: draft-state nodes (the provisional teardown
            # paths) and the legacy draft-born task-book document (the
            # pre-de-stamp cleanup's victim shape; none exist post-
            # migration l2b5c8e1f4a7, the path stays honest). The asset
            # module's own lifecycle deletes ride allow_settled_delete.
            if not allow_settled_delete and str(node.state) != "draft" and not (
                node.type == "document"
                and (node.spec or {}).get("role") == _TASK_BOOK_ROLE
                and not (node.spec or {}).get("run_id")
            ):
                raise WiringRejected(
                    f"delete_node: node {op.node} is settled (state "
                    f"{node.state!r}) — a settled entity is append-only; "
                    "only provisional drafts are deletable"
                )
            pending_delete.append(op.node)
            delta.affected.append(op.node)
            nodes.pop(op.node)
            edges[:] = [
                e
                for e in edges
                if UUID(str(e.from_node)) != op.node and UUID(str(e.to_node)) != op.node
            ]
        elif isinstance(op, RunOp):
            seeds = op.nodes if op.nodes is not None else list(delta.affected)
            for seed in seeds:
                if seed not in nodes:
                    raise WiringRejected(f"run: unknown node {seed}")
            resolved: set[UUID] = set()
            for seed in seeds:
                resolved.add(seed)
                # Close over downstream — a node rerun refills what feeds
                # off it (修订 = edit_prompt + run({node} ∪ downstream)).
                # ADR-097 §5: the walk EXCLUDES lineage/display-only edges —
                # a transcript node's rerun closure never swallows the
                # downstream caption artifact through its bloodline edge.
                resolved |= {
                    n
                    for n in nodes
                    if reaches(
                        seed,
                        n,
                        children=lambda nid: executable_children_of(edges, nid),
                    )
                }
            # I-PFA-04 (合同 §7 C-2): execution order = the DAG's topological
            # depth — visual coordinates lost execution authority (a stale or
            # drifted frame can never put a consumer before its producer).
            # Ungated rank: the visibility gate hides morph modifiers from
            # the CANVAS, but they are executable steps that must order
            # between their producers and consumers; the edge boundary
            # (物料流三值) is identical either way. Tiebreak = id str —
            # deterministic, and same-rank nodes are parallel by definition
            # so the order among them is semantically free.
            ranks = product_ranks(nodes.values(), edges, gated=False)
            delta.run_nodes = sorted(
                resolved,
                key=lambda n: (ranks[str(n)], str(n)),
            )

    # Settle the newborns' frames with FULL edge knowledge (画布定居取景):
    # parents-first over the batch's FINAL edge set (the add-time column
    # guess was a placeholder — the real parents are the batch's edges).
    # Each frame is assigned ONCE here, before the flush — born right, never
    # repaired later; existing frames NEVER move (append-only 保序律).
    # C6: the project's island rows ride in — the settle births / joins the
    # sibling groups' layout islands before the passes.
    island_rows = list(
        (
            await db.execute(
                select(GraphIsland).where(GraphIsland.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    placed = [n for n in nodes.values() if UUID(str(n.id)) not in set(newborn_ids)]
    await settle_frames_with_edges(
        [nodes[nid] for nid in newborn_ids],
        placed,
        edges,
        island_ctx=(db, project_id, island_rows),
    )

    # Land the batch: deletions (edges cascade structurally), then the new
    # rows, then the edited rows (ORM-tracked already). TWO flushes, nodes
    # strictly before edges (2026-09-09 取证): the UOW only orders inter-
    # table inserts through relationship()s and these tables have none — a
    # single mixed flush let the edge INSERT precede the node's (SQLA
    # 2.0.51, vacuum-reproduced) and FK-violated at random (轮盘赌, born at
    # K1). The explicit stage boundary makes the order structural — never
    # merge the flushes back.
    for node_id in pending_delete:
        row = await db.get(GraphNode, node_id)
        if row is not None:
            await db.delete(row)
    for node in nodes.values():
        db.add(node)
    await db.flush()
    for edge in edges:
        # 合成边永不落库 (ADR-098 §1 铁律①): the effective topology layer's
        # synthesized rows are plain dicts living in settle_frames_with_edges'
        # LOCAL — the persisted working set only ever carries ORM rows; a
        # dict reaching this flush would be a synthesis leak.
        assert not isinstance(edge, dict), (
            "a synthesized effective edge (dict) reached the flush — "
            "synthesis is read-time projection, never persisted"
        )
        db.add(edge)
    await db.flush()
    return delta


__all__ = [
    "AddNodeOp",
    "ConnectOp",
    "DeleteNodeOp",
    "DisconnectOp",
    "EditPromptOp",
    "GraphDelta",
    "RunOp",
    "WIRING_OPS",
    "WiringOp",
    "WiringRejected",
    "apply_wiring_ops",
    "executable_children_of",
    "island_reserved_bottom",
    "settle_frames_with_edges",
    "wiring_catalog_lines",
]
