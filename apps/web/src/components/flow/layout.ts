import type { FlowEdge, FlowNode, FlowNodeKind } from "./types"

/** Fixed node dimensions per skin — layout is pure math with zero DOM
 * measurement (SSR-safe, no ResizeObserver feedback loops). Step pills are
 * sized for a TWO-LINE label + one detail line (a truncated "Understand
 * the…" node is a bug, never a style — 2026-08-10). */
export const FLOW_NODE_SIZE: Record<FlowNodeKind, { width: number; height: number }> = {
  asset: { width: 128, height: 216 },
  output: { width: 128, height: 216 },
  step: { width: 192, height: 72 },
  spine: { width: 192, height: 72 },
  /** Artifact nodes (D6 修订 — plan / selection / dub / music cards): the
   * three-section anatomy (type + status / body copy / spec line) sized for
   * a four-line body clamp. */
  artifact: { width: 224, height: 168 },
}

/** The results canvas's product card (ADR-041 D5 大卡, 2026-08-15 anatomy):
 * a corner-info band above the card (type left / language right), the media
 * flush full-bleed inside the card, a padded interaction area under it (the
 * run's prompt + the deterministic next-step line), and the always-on
 * action pill in a reserved band under the card. The thumb keeps the clip's
 * own frame — three aspect sizes, never a forced crop (2026-08-14 ruling).
 * The media fills the card edge to edge (no inner padding), so the aspect
 * heights are computed at the full lane width (208). */
export const PRODUCT_THUMB_PX: Record<string, number> = {
  "9:16": 370,
  "1:1": 208,
  "16:9": 117,
}

/** Non-clip products (no aspect) get the 16:9 strip. */
export const PRODUCT_THUMB_DEFAULT_PX = 117

/** Node-box bands around the product card: corner info above, the action
 * pill below (reserved even while a render leaves it empty — geometry never
 * shifts), and the card's own padded interaction area. */
const PRODUCT_LABEL_PX = 22
const PRODUCT_TOOLBAR_PX = 44
const PRODUCT_BODY_PX = 96

/** Product node size by clip aspect. */
export function productNodeSize(aspect?: string | null): { width: number; height: number } {
  const thumb = (aspect && PRODUCT_THUMB_PX[aspect]) || PRODUCT_THUMB_DEFAULT_PX
  return {
    width: 208,
    height: PRODUCT_LABEL_PX + thumb + PRODUCT_BODY_PX + PRODUCT_TOOLBAR_PX,
  }
}

/** Source video asset node (results canvas): the media plays inline, so the
 * frame is landscape and wide enough to watch; the caption band rides above
 * (included in the height). */
export const VIDEO_ASSET_NODE_SIZE = { width: 232, height: 152 }

/** A node's resolved size — the per-kind default unless the adapter pinned
 * an override (product cards on the results canvas). */
export function flowNodeSize(node: FlowNode): { width: number; height: number } {
  return node.size ?? FLOW_NODE_SIZE[node.kind]
}

/** Compact thumb-node sizes by aspect (recipe flow surface, 2026-08-15 —
 * the same 三档画幅 no-crop rule as the results product card). Width stays
 * the lane constant (128); height = the corner-info caption band above +
 * the thumb at exact aspect. No aspect = the legacy 172 thumb. */
const THUMB_LABEL_PX = 22
export function thumbNodeSize(aspect?: string | null): { width: number; height: number } {
  const thumb =
    aspect === "9:16" ? 227 : aspect === "1:1" ? 128 : aspect === "16:9" ? 72 : 172
  return { width: 128, height: thumb + THUMB_LABEL_PX }
}

const GAP_MAIN = 96
const GAP_CROSS = 24

export interface FlowLayout {
  positions: Map<string, { x: number; y: number }>
  /** Reveal order for birth choreography: depth-major, then the stable
   * `order` key — a slowed-down replay of the real compile order. */
  revealOrder: Map<string, number>
  width: number
  height: number
}

/** Deterministic layered layout: depth(v) = max(depth(parents)) + 1 over
 * edges; within a layer nodes sort by their stable `order` key (append-only:
 * a new node slots into its layer's tail, existing positions never move —
 * "chat 加节点，图只长不晃"). Layers are columns (main axis left→right),
 * centered against the tallest column on the cross axis. */
export function layoutFlow(nodes: FlowNode[], edges: FlowEdge[]): FlowLayout {
  const parents = new Map<string, string[]>()
  for (const e of edges) {
    parents.set(e.to, [...(parents.get(e.to) ?? []), e.from])
  }

  const depthMemo = new Map<string, number>()
  const depthOf = (id: string, trail: Set<string>): number => {
    const memo = depthMemo.get(id)
    if (memo !== undefined) return memo
    if (trail.has(id)) return 0 // cycle guard — input is a DAG, never trust it
    trail.add(id)
    const ups = parents.get(id) ?? []
    const d = ups.length === 0 ? 0 : Math.max(...ups.map((u) => depthOf(u, trail))) + 1
    depthMemo.set(id, d)
    return d
  }

  const layers = new Map<number, FlowNode[]>()
  for (const n of nodes) {
    const d = depthOf(n.id, new Set())
    layers.set(d, [...(layers.get(d) ?? []), n])
  }

  const ordered = [...layers.entries()]
    .sort(([a], [b]) => a - b)
    .map(([depth, ns]) => ({
      depth,
      nodes: [...ns].sort((a, b) => a.order - b.order),
    }))

  const positions = new Map<string, { x: number; y: number }>()
  const revealOrder = new Map<string, number>()
  // Column widths (main axis) and heights (cross axis).
  const colWidth = ordered.map(({ nodes: ns }) =>
    Math.max(...ns.map((n) => flowNodeSize(n).width), 0),
  )
  const colHeight = ordered.map(
    ({ nodes: ns }) =>
      ns.reduce((h, n) => h + flowNodeSize(n).height, 0) +
      GAP_CROSS * Math.max(ns.length - 1, 0),
  )
  const cross = Math.max(...colHeight, 0)

  let main = 0
  let reveal = 0
  ordered.forEach(({ nodes: ns }, col) => {
    let offset = (cross - colHeight[col]) / 2
    for (const n of ns) {
      positions.set(n.id, { x: main, y: offset })
      revealOrder.set(n.id, reveal++)
      offset += flowNodeSize(n).height + GAP_CROSS
    }
    main += colWidth[col] + GAP_MAIN
  })

  return {
    positions,
    revealOrder,
    width: Math.max(main - GAP_MAIN, 0),
    height: cross,
  }
}
