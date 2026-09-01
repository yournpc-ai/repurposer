/** FlowView contract (ADR-036) — the stable surface all four consumers adapt
 * domain data into: recipe fan-out / run flow graph / stage family view /
 * lineage board. The renderer knows nothing about topology semantics; every
 * edge carries its meaning, every node is real (step `inputs` /
 * `derived_from_output_id` — decorative illustration is prohibited). */

export type FlowNodeKind = "asset" | "output" | "step" | "spine" | "artifact"

export type FlowNodeStatus = "pending" | "running" | "done" | "failed" | "skipped"

/** lineage 血缘边 = derivation (asset→output, output→output);
 * dependency 依赖边 = process order (step→step). Visually distinct. */
export type FlowEdgeSemantic = "lineage" | "dependency"

/** Product-node actions (ADR-041 D5) — the old card-face actions moved onto
 * the canvas toolbar. Bar: download / publish / delete; the ⋯ menu (node
 * business): open / focus (2026-08-17 走查拍板, Lovart 解剖). No preview —
 * the video plays inline and the big player is the hover expand. Graph
 * operations (run / rewire) are permanently banned from it. */
export type FlowOutputAction = "open" | "download" | "publish" | "delete" | "focus"

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
   * always top-left; the right slot stays empty — 2026-08-17 走查拍板). */
  label: string
  status?: FlowNodeStatus
  /** Secondary fact carried as data (the lightbox's info chips read it) —
   * never rendered in the caption's right slot. Asset nodes: the filename. */
  detail?: string
  /** The asset row behind an asset node (results canvas) — the node's
   * toolbar facts (filename / duration / download target) derive from it. */
  asset?: FlowAssetInfo
  thumbUrl?: string | null
  /** The product row behind an output node (results canvas only, D5 — the
   * node IS the product card: score / top-pick / next-step live on it).
   * Absent on the recipe surface, whose output nodes stay compact thumbs. */
  output?: import("@/lib/types").Output
  /** Placeholder slot of a live run (ADR-051 B — 占位物化): the node is a
   * quiet placeholder card born at its final size/position; the real output
   * landing from the same producing step fills the slot in place (same
   * roster index, node id swaps placeholder:… → output:…). Carries the
   * display facts the skin needs (type / whole / language / variant /
   * aspect). The node's `status` mirrors the producing step — a running
   * step gives the card its FLORA wipe (the run 期 fill projection); the
   * step narrative still lives in the dock's folded checklist. */
  placeholder?: {
    stepId: string
    type: string
    whole: boolean
    language?: string | null
    variant?: string | null
    aspect?: string | null
  }
  /** The run's prompt, shown in the product card's padded interaction area
   * (results canvas, D5 anatomy: spec on the body — read-only; changes
   * happen in chat, never in place). */
  prompt?: string | null
  /** The product's OWN spec as a prompt-style line (ADR-051 F — the per-
   * card global-prompt display retired into this): the card body shows it
   * at rest; the hover prompt 框 prefills with it (editable — sending rides
   * the chat revision channel with the product pinned as focus). */
  specPrompt?: string | null
  /** Fork family (ADR-051 F2 — 变体分页): every visible row connected
   * through source_ref.derived_from_output_id, created_at ascending — each
   * a REAL row with its own media (morph versions share one row's current
   * media, so they never become pager entries). Present only when the
   * family has ≥2 members; the card's "1 of N" pager flips the display
   * (and the action target) among members. Distinct slot from `variants`
   * (items switcher) — the two never merge. */
  familyOutputs?: import("@/lib/types").Output[]
  /** Video asset nodes (results canvas): the browser-playable URL — the
   * node renders an inline muted-loop <video>, never a file icon. */
  videoUrl?: string | null
  /** Multi-item outputs (quotes = N quote cards, carousel = N slides): the
   * node's display variants — a hover switcher fades in at the top of the
   * node and flips the main display. Items without their own media render
   * as a text tile. */
  variants?: { label: string; sub?: string; thumbUrl?: string | null }[]
  /** Text-product outputs (post / article): a preview of the generated text
   * rendered inside the card, since these types have no baked image/video.
   * The node itself becomes the readable text card (Gamma/Tome-style). */
  textContent?: {
    title: string | null
    body: string
    hashtags: string[]
  }
  /** The batch's recommended pick (score triage) — adapter-computed. */
  topPick?: boolean
  /** Size override (pure-math layout stays measurement-free): the results
   * canvas's product cards are bigger than the shared per-kind defaults. */
  size?: { width: number; height: number }
  /** Aspect-shaped thumb (2026-08-15 三档画幅 on the recipe flow surface):
   * the thumb letterboxes (black, object-contain) instead of cover-cropping.
   * Pair with a `size` pinned via thumbNodeSize so frame and media agree. */
  containThumb?: boolean
  /** Carries the surface's data-tour anchors (first ready product only). */
  tourTargets?: boolean
  /** Spine group node only (results canvas, D6 过程脊): the fold's current
   * state — the card flips its chevron on it. */
  expanded?: boolean
  /** Artifact nodes only (results canvas, D6 修订 — the render unit is the
   * intervenable artifact; 2026-08-19 收窄后恒为 "plan" = 任务书玻璃文本节点;
   * canvas_key 序列化时从节点类现算、从不入行，旧 run 重序列化即同一收窄
   * 画布，无残留 key 可兼容): the group's key, the card's body copy, and
   * the representative step id the @workflow_step mention anchors to. */
  artifact?: string
  body?: string
  anchorStepId?: string
  /** Stable within-layer ordering key (step `seq` / output `created_at`) —
   * append-only growth stability: chat adds nodes, the graph only grows,
   * existing nodes never move (ADR-036). */
  order: number
}

export interface FlowEdge {
  from: string
  to: string
  semantic: FlowEdgeSemantic
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
  /** Hover prompt 框 send (ADR-051 F): the card reports the revision ask
   * with the product pinned — the surface rides it into the chat revision
   * channel (zero new execution channel, prohibition #1). */
  onRevise?: (outputId: string, text: string) => void
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
  /** Dot-grid canvas backdrop (the "流程" tab's drafting-table feel). */
  dots?: boolean
  className?: string
}
