/** FlowView contract (ADR-036; ADR-057 K3) — the stable surface the two
 * consumers render through: the recipe 说明书 (fit-locked compact thumbs)
 * and the project graph canvas (ADR-057 — the persistent graph read
 * DIRECTLY: node id = graph node id, edge = graph edge, state = the row's
 * state; zero projection, the display model is the domain model). The
 * renderer knows nothing about topology semantics; every edge carries its
 * meaning, every node is real. */

import type { GraphEdgeType, GraphNodeKind, GraphNodeState } from "@/lib/types"

export type { GraphEdgeType, GraphNodeKind, GraphNodeState }

/** 出锚语义律 (2026-09-11 用户拍板): the OUT anchor names the SOURCE's own
 * production medium, never the edge's carried type — an edge reads "from
 * <the source's medium> to <what the consumer takes>", so a video asset
 * never sprouts a T (the transcript's text is born AT the transcript; the
 * edge itself tells video → text). The IN anchor stays the edge's carried
 * type. "image" is the render-side-only fifth value (the still-visual
 * family — image/slides assets): it never crosses the wire as an edge
 * type, it only names an out anchor. */
export type OutPortType = GraphEdgeType | "image"

/** Recipe surface: "asset" | "step" | "output". Graph canvas: the five
 * node types (asset is shared — the same media card on both surfaces). */
export type FlowNodeKind = GraphNodeKind | "output" | "step"

/** Graph canvas node state (the graph row's own state vocabulary). The
 * recipe surface leaves status unset — its cards have no liveness. */
export type FlowNodeStatus = GraphNodeState

/** lineage 血缘边 = derivation (asset→output, output→output);
 * dependency 依赖边 = process order (step→step). Visually distinct.
 * Recipe surface only — the graph canvas's edges carry `edgeType`. */
export type FlowEdgeSemantic = "lineage" | "dependency"

/** Product-node actions (ADR-041 D5) — the old card-face actions moved onto
 * the canvas toolbar. Bar: download / publish / delete; the ⋯ menu (node
 * business): open / focus (2026-08-17 走查拍板, Lovart 解剖). No preview —
 * the video plays inline and the big player is the hover expand. Graph
 * operations (run / rewire) are permanently banned from it. */
export type FlowOutputAction = "open" | "copy" | "download" | "publish" | "delete" | "focus"

/** Asset-node actions (results canvas, 2026-08-17): the source file's own
 * business — download / delete / reprocess. ("open" never travels this
 * channel: the card opens the lightbox directly.) */
export type FlowAssetAction = "download" | "delete" | "reprocess"

/** The asset fields a results-canvas asset node carries (the card derives
 * its toolbar facts — filename / duration / download URL — from these). */
export interface FlowAssetInfo {
  id: string
  type: string
  title: string | null
  file_url: string | null
  stream_url?: string | null
  duration_seconds?: number | null
}

export interface FlowNode {
  id: string
  kind: FlowNodeKind
  /** Friendly, pre-localized name — never a model name (prohibition #12).
   * On media nodes this is the TYPE name (caption = type icon + type name,
   * always top-left; the right slot stays empty — 2026-08-17 走查拍板;
   * ADR-057 §5: 状态原地表达, caption 右槽恒空 — no status badge ever). */
  label: string
  /** Graph canvas: the graph row's state — expressed IN PLACE (draft dashed
   * region / running wipe / done self-evident content / failed in-card red /
   * stale factsbar badge), never a caption badge. */
  status?: FlowNodeStatus
  /** Secondary fact carried as data (the lightbox's info chips read it) —
   * never rendered in the caption's right slot. Asset nodes: the filename. */
  detail?: string
  /** The asset row behind an asset node (results canvas) — the node's
   * toolbar facts (filename / duration / download target) derive from it. */
  asset?: FlowAssetInfo
  thumbUrl?: string | null
  /** Video asset nodes (results canvas): the browser-playable URL — the
   * node renders an inline muted-loop <video>, never a file icon. */
  videoUrl?: string | null
  /** ── Graph canvas (ADR-057) ──────────────────────────────────────────
   * The graph row's program, rendered as-is: generator/agent cards carry
   * `spec.prompt` in the card-face program region (K4 makes it directly
   * editable); processor cards render `spec.params` as fact chips; the
   * document node renders `spec.text` as its body. */
  spec?: {
    summary?: string | null
    prompt?: string | null
    params?: Record<string, unknown> | null
    role?: string | null
    text?: string | null
    [key: string]: unknown
  }
  /** The node's product region: its joined visible product rows (created_at
   * asc — the card's pager flips the display AND the action target among
   * them, ADR-051 F2 mechanics generalized from fork-family to slot
   * siblings). Empty/undefined = the region shows the state-appropriate
   * body (draft estimate / running wipe / quiet done). */
  outputs?: import("@/lib/types").Output[]
  /** The node's quotation in credits (server-folded at read time) — the
   * draft card's 「运行后生成 · 约 N 积分」. Null = unquoted. */
  estimateCredits?: [number, number] | null
  /** 画布定居取景: the server-settled frame — position AND reserved size
   * come from the graph row (append-only; existing frames never move). The
   * card renders content-driven height inside the reservation. */
  frame?: { x: number; y: number; w: number; h: number }
  /** The batch's highest clip score (score triage — what to post first):
   * the card accents the winning product's badge. */
  topClipScore?: number
  /** Size override (pure-math layout stays measurement-free): the results
   * canvas's product cards are bigger than the shared per-kind defaults. */
  size?: { width: number; height: number }
  /** Aspect-shaped thumb (2026-08-15 三档画幅 on the recipe flow surface):
   * the thumb letterboxes (black, object-contain) instead of cover-cropping.
   * Pair with a `size` pinned via thumbNodeSize so frame and media agree. */
  containThumb?: boolean
  /** Carries the surface's data-tour anchors (first ready product only). */
  tourTargets?: boolean
  /** Stable within-layer ordering key (step `seq` / node birth index) —
   * append-only growth stability: chat adds nodes, the graph only grows,
   * existing nodes never move (ADR-036). */
  order: number
}

export interface FlowEdge {
  from: string
  to: string
  /** Graph canvas (ADR-057 port law): the typed flow — colors the stroke
   * (video / audio), text/ctx neutral (every edge solid — ctx, the
   * reference flow, is told by the port glyph, not the stroke). */
  edgeType?: GraphEdgeType
  /** Recipe surface: derivation vs process order. */
  semantic?: FlowEdgeSemantic
}

/** A region frame (2026-08-19 预留, the FLORA technique-workflow form): a
 * large rounded frame rendered BEHIND its member nodes, naming the region's
 * 大叙事 (the recipe frame labels itself "Curated steps" — it wraps only
 * the steps, never borrowing the recipe's name). Purely visual grouping —
 * it never affects layout, edges, or interactions. */
export interface FlowGroup {
  id: string
  /** Pre-localized frame label (the adapter owns copy; FlowView stays
   * text-agnostic). Absent = a bare frame. */
  label?: string
  /** Member node ids — bounds derive from the layout (padding added);
   * unknown ids are ignored, an empty frame renders nothing. */
  nodeIds: string[]
}

/** Zoom/pan are NAVIGATION, not editing (ADR-036 补记) — held by the
 * substrate, gated per surface: bounded surfaces stay fit-first with zoom
 * locked; only the lineage board explores. */
export type FlowNavigation = "fit" | "explore"

export interface FlowViewProps {
  nodes: FlowNode[]
  edges: FlowEdge[]
  selectedId?: string | null
  onSelect?: (id: string) => void
  /** Product-node toolbar dispatch (results canvas, ADR-041 D5) — the
   * surface owns the actions; the card only reports them. */
  onOutputAction?: (outputId: string, action: FlowOutputAction) => void
  /** Asset-node toolbar dispatch (results canvas, 2026-08-17) — the surface
   * owns download / delete / reprocess; the card only reports them. When
   * absent the asset node renders NO toolbar (recipe manual surface). */
  onAssetAction?: (asset: FlowAssetInfo, action: FlowAssetAction) => void
  /** Media expand (results canvas): a node's hover expand icon / media
   * click — the surface opens the media lightbox for the node. `outputId`
   * names the displayed member when the version pager flipped the card
   * (ADR-051 F2 — the lightbox follows the shown variant, not the row). */
  onExpandMedia?: (nodeId: string, outputId?: string) => void
  /** The node's pager flipped its displayed product (mount + flip) — the
   * surface tracks it so a node click selects what the user is LOOKING at
   * (the lightbox / dossier / focus follow the shown member). */
  onDisplayChange?: (nodeId: string, outputId: string) => void
  /** Card-face prompt direct edit (ADR-057 K4; ADR-058 deterministic): the
   * card reports the new program; the surface opens the pricing
   * confirmation (锚定受影响子图 + 估价随行) — nothing touches the graph
   * until the confirm's CODE-built edit_prompt + run lands. */
  onPromptEdit?: (nodeId: string, text: string) => void
  /** The edit's optimistic echo (ADR-058 乐观回显): while the confirm is
   * open or the stamp is in flight, the edited node's card face shows the
   * user's verbatim program instead of the domain's last-stamped one —
   * never a revert flash. Null = no pending edit. */
  pendingProgram?: { nodeId: string; text: string } | null
  /** 动作住节点内 (2026-09-10 判词①): the prompt edit's pricing
   * confirmation docks INSIDE the edited node's program region (the
   * retired floating overlay) — the surface computes the blast (锚定子图)
   * and the price, the region renders them under the staged program. */
  promptConfirm?: {
    nodeId: string
    blastLabels: string[]
    blastSingle: boolean
    low: number
    high: number
    unquoted: number
    balance: number | null
    onConfirm: () => void
    onCancel: () => void
  } | null
  /** 动作住节点内 (判词①): the draft world's confirm beat docks INSIDE the
   * task-book document card (the retired floating card) — resident while
   * the docked book's draft graph is up. */
  draftConfirm?: {
    low: number
    high: number
    unquoted: number
    balance: number | null
    onConfirm: () => void
  } | null
  /** Pane-only click (node clicks never fire this) — the results canvas's
   * "back to neutral" gesture: collapse the history, clear the focus. */
  onPaneClick?: () => void
  /** "fit" (default) = bounded surface, zoom locked; "explore" = lineage
   * board (zoom / pan / pinch unlocked). */
  navigation?: FlowNavigation
  /** Canvas navigation controls (2026-08-19 — the project page's top-right
   * swap: app chrome out, canvas controls in): a frosted zoom pill (− / %
   * = fit / +) parked top-right. Explore surfaces only — a fit-locked
   * surface has no zoom business, so the prop is ignored there. */
  controls?: boolean
  /** Extra classes for the controls' Panel (2026-09-06): the project page
   * offsets the zoom pill clear of the open chat panel (a fixed right
   * margin) so it never sits under the frost. The inspector shares it. */
  controlsClassName?: string
  /** Settle-driven initial framing (2026-09-06): surfaces whose data arrives
   * through MULTIPLE async fetches (the results canvas: /results + /assets,
   * gated visible by hasRuns) pass a key that is non-null exactly when their
   * visible, settled content is present. Each transition to a new non-null
   * key frames the graph once; growth afterwards never re-frames (explore
   * law). Absent = the legacy count-based initial fit (first non-empty
   * frame) — which centered PARTIAL arrivals and left the rest of the
   * graph off-center at the default viewport. */
  settleKey?: string | null
  /** Birth choreography (ADR-036 补记 3, growth-driven since ADR-051): the
   * ids of nodes that appeared while the surface was mounted (placeholder
   * materialization, in-place fills, revision growth) — they enter staggered
   * in compile order (BIRTH_STAGGER_MS), edges touching them draw on. The
   * surface owns the witnessing (its first hydrated frame passes NOTHING —
   * refresh / reconnect / history render instantly, 铁律). */
  bornIds?: ReadonlySet<string>
  /** Region frames (2026-08-19 预留 — recipe surface first): large rounded
   * frames behind member node clusters, naming the region. */
  groups?: FlowGroup[]
  /** Surface-owned canvas content (ADR-057 K4 — the pricing-confirmation
   * card): rendered as a ReactFlow child, so the surface composes its own
   * anchoring (ViewportPortal = world space, Panel = screen space). The
   * substrate stays business-blind; the surface owns everything inside. */
  overlay?: React.ReactNode
  /** Dot-grid canvas backdrop (the "流程" tab's drafting-table feel). */
  dots?: boolean
  className?: string
}
