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
 * the canvas toolbar: download / publish (no preview — the video plays
 * inline and the big player is the hover expand, 2026-08-16 走查拍板).
 * Graph operations (run / rewire) are permanently banned from it. */
export type FlowOutputAction = "download" | "publish"

export interface FlowNode {
  id: string
  kind: FlowNodeKind
  /** Friendly, pre-localized name — never a model name (prohibition #12). */
  label: string
  status?: FlowNodeStatus
  /** Quantified one-liner / language tag / score. */
  detail?: string
  thumbUrl?: string | null
  /** The product row behind an output node (results canvas only, D5 — the
   * node IS the product card: score / top-pick / next-step live on it).
   * Absent on the recipe surface, whose output nodes stay compact thumbs. */
  output?: import("@/lib/types").Output
  /** The run's prompt, shown in the product card's padded interaction area
   * (results canvas, D5 anatomy: spec on the body — read-only; changes
   * happen in chat, never in place). */
  prompt?: string | null
  /** Video asset nodes (results canvas): the browser-playable URL — the
   * node renders an inline muted-loop <video>, never a file icon. */
  videoUrl?: string | null
  /** Multi-item outputs (quotes = N quote cards, carousel = N slides): the
   * node's display variants — a hover switcher fades in at the top of the
   * node and flips the main display. Items without their own media render
   * as a text tile. */
  variants?: { label: string; sub?: string; thumbUrl?: string | null }[]
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
   * intervenable artifact): the group's key ("plan" / "selection" /
   * "dub:zh" / "music"), the card's body copy, and the representative
   * step id the @workflow_step mention anchors to. */
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
  /** Media expand (results canvas): a node's hover expand icon / media
   * click — the surface opens the media lightbox for the node. */
  onExpandMedia?: (nodeId: string) => void
  /** Pane-only click (node clicks never fire this) — the results canvas's
   * "back to neutral" gesture: collapse the history, clear the focus. */
  onPaneClick?: () => void
  /** "fit" (default) = bounded surface, zoom locked; "explore" = lineage
   * board (zoom / pan / pinch unlocked). */
  navigation?: FlowNavigation
  /** Birth choreography — nodes enter in compile order + edges draw on.
   * Only for a run witnessed live in this session; rehydrated history
   * renders instantly (ADR-036 补记 3). */
  choreograph?: boolean
  /** Dot-grid canvas backdrop (the "流程" tab's drafting-table feel). */
  dots?: boolean
  className?: string
}
