import type { FlowEdge, FlowNode, FlowNodeKind } from "./types"

/** Fixed node dimensions per skin — layout is pure math with zero DOM
 * measurement (SSR-safe, no ResizeObserver feedback loops). */
export const FLOW_NODE_SIZE: Record<FlowNodeKind, { width: number; height: number }> = {
  asset: { width: 128, height: 216 },
  output: { width: 128, height: 216 },
  step: { width: 176, height: 64 },
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
    Math.max(...ns.map((n) => FLOW_NODE_SIZE[n.kind].width), 0),
  )
  const colHeight = ordered.map(
    ({ nodes: ns }) =>
      ns.reduce((h, n) => h + FLOW_NODE_SIZE[n.kind].height, 0) +
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
      offset += FLOW_NODE_SIZE[n.kind].height + GAP_CROSS
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
