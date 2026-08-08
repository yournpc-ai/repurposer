/** FlowView contract (ADR-036) — the stable surface all four consumers adapt
 * domain data into: recipe fan-out / run flow graph / stage family view /
 * lineage board. The renderer knows nothing about topology semantics; every
 * edge carries its meaning, every node is real (step `inputs` /
 * `derived_from_output_id` — decorative illustration is prohibited). */

export type FlowNodeKind = "asset" | "output" | "step"

export type FlowNodeStatus = "pending" | "running" | "done" | "failed" | "skipped"

/** lineage 血缘边 = derivation (asset→output, output→output);
 * dependency 依赖边 = process order (step→step). Visually distinct. */
export type FlowEdgeSemantic = "lineage" | "dependency"

export interface FlowNode {
  id: string
  kind: FlowNodeKind
  /** Friendly, pre-localized name — never a model name (prohibition #12). */
  label: string
  status?: FlowNodeStatus
  /** Quantified one-liner / language tag / score. */
  detail?: string
  thumbUrl?: string | null
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
