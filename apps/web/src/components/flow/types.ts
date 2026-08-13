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
 * the canvas toolbar: preview / download / publish. Graph operations (run /
 * rewire) are permanently banned from it. */
export type FlowOutputAction = "preview" | "download" | "publish"

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
  /** The batch's recommended pick (score triage) — adapter-computed. */
  topPick?: boolean
  /** Size override (pure-math layout stays measurement-free): the results
   * canvas's product cards are bigger than the shared per-kind defaults. */
  size?: { width: number; height: number }
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
