import type { FlowEdge, FlowNode, FlowNodeKind } from "./types"

/** Fixed node dimensions per skin — layout is pure math with zero DOM
 * measurement (SSR-safe, no ResizeObserver feedback loops). Step pills are
 * sized for a TWO-LINE label + one detail line (a truncated "Understand
 * the…" node is a bug, never a style — 2026-08-10). The five graph kinds
 * are fallbacks only — the graph canvas's nodes carry their server-settled
 * `frame` (画布定居取景) and `graphNodeSize` computes the content-driven
 * render size inside the reservation. */
export const FLOW_NODE_SIZE: Record<FlowNodeKind, { width: number; height: number }> = {
  asset: { width: 280, height: 260 },
  output: { width: 128, height: 216 },
  /** 配方说明书 step pills：小尺寸，不抢产物节点视觉权重。 */
  step: { width: 144, height: 48 },
  /** Document node (ADR-057 — the task book, the FLORA text-node form):
   * the glass text card, a six-line relaxed body clamp. */
  document: { width: 260, height: 200 },
  generator: { width: 280, height: 268 },
  processor: { width: 280, height: 268 },
  agent: { width: 340, height: 268 },
}

/** The results canvas's product card (ADR-041 D5 大卡, 2026-08-17 二轮走查
 * 放大): a corner-info band above the card (type left / language right), the
 * media flush full-bleed inside the card, a padded interaction area under it
 * (the run's prompt), and the always-on action bar in a reserved band under
 * the card. The thumb keeps the clip's own frame — three aspect sizes, never
 * a forced crop (2026-08-14 ruling). The media fills the card edge to edge
 * (no inner padding), so the aspect heights are computed at the full lane
 * width (280 — the 208 lane read too narrow next to its toolbar). */
export const PRODUCT_THUMB_PX: Record<string, number> = {
  "9:16": 498,
  "1:1": 280,
  "16:9": 158,
}

/** Non-clip products (no aspect) get the 16:9 strip. */
export const PRODUCT_THUMB_DEFAULT_PX = 158

/** The card-face program region (ADR-057 §5 — generator/agent: the prompt;
 * processor: the params facts): meta label + ≤3-line body + padding. */
export const PROGRAM_REGION_PX = 88

/** The draft/quiet body (ADR-057 §5 — 虚线空态): the dashed region's
 * reserved height (「运行后生成 · 约 N 积分」). */
export const DRAFT_BODY_PX = 120

/** Node-box bands around the product card: corner info above, the action
 * bar below (reserved even while a render leaves it empty — geometry never
 * shifts). Band budgets mirror FlowNodeCard's real chrome: caption = 26px
 * (4px inset + 8px breath), factsbar band = 44px (8px gap + the 36px
 * frosted bar). */
export const PRODUCT_LABEL_PX = 26
export const PRODUCT_TOOLBAR_PX = 44

/** Clip-product card height by aspect (the graph canvas's media node):
 * caption + the aspect-exact thumb + the program region + the factsbar
 * band. Width is the frame's (280 clip class). */
export function clipNodeHeight(aspect?: string | null): number {
  const thumb = (aspect && PRODUCT_THUMB_PX[aspect]) || PRODUCT_THUMB_DEFAULT_PX
  return PRODUCT_LABEL_PX + thumb + PROGRAM_REGION_PX + PRODUCT_TOOLBAR_PX
}

/** Text-product body height by preview line count (post / article — no
 * baked media): padding + optional title + clamped body + hashtag band.
 * Preview clamp 2–12 lines (2026-09-06 ruling — the canvas preview carries
 * a real reading burden before the reader opens). */
export function textBodyHeight(lineCount: number, hasTitle: boolean): number {
  const clamped = Math.max(2, Math.min(lineCount, 12))
  const lineHeight = 18 // text-xs leading-relaxed ≈ 18px per line
  const titleHeight = hasTitle ? 22 : 0
  const hashtagsHeight = 20 // one-row hashtag band
  return 12 + titleHeight + clamped * lineHeight + hashtagsHeight + 12
}

/** Estimate visible lines from the body at the text card's width (~312px
 * inside the 340 text card, text-xs): ~68 chars per line for Latin, ~44 for
 * CJK. */
export function textLineCount(body: string, hasTitle: boolean): number {
  const cjk = /[一-龥぀-ゟ゠-ヿ]/.test(body)
  const charsPerLine = cjk ? 44 : 68
  const bodyLines = Math.max(1, Math.ceil(body.length / charsPerLine))
  return Math.min(12, Math.max(2, (hasTitle ? 1 : 0) + bodyLines))
}

/** The graph node's content-driven render size (ADR-057 K3): width = the
 * settled frame's (a size class fact), height = the anatomy's content math
 * — a node fills INTO its reserved frame as products land (draft → quiet
 * body, done → the product card). Never exceeds the server's reservation
 * (graph_store._FRAME_CLASS), so settled columns never overlap. */
export function graphNodeSize(node: FlowNode): { width: number; height: number } {
  const frame = node.frame
  const fallback = FLOW_NODE_SIZE[node.kind]
  const width = frame?.w ?? fallback.width
  if (node.kind === "asset") {
    return {
      width,
      height: node.videoUrl
        ? VIDEO_ASSET_NODE_SIZE.height
        : PRODUCT_LABEL_PX + 190 + PRODUCT_TOOLBAR_PX,
    }
  }
  if (node.kind === "document") {
    return { width, height: frame?.h ?? fallback.height }
  }
  // generator / processor / agent: product region + program region + bar.
  const outputs = node.outputs ?? []
  if (outputs.length === 0) {
    // Draft / queued / running / quiet-done body (the dashed region reads
    // the estimate while unrun; a landed-empty node (research) reads its
    // summary in the same body).
    return {
      width,
      height: PRODUCT_LABEL_PX + DRAFT_BODY_PX + PROGRAM_REGION_PX + PRODUCT_TOOLBAR_PX,
    }
  }
  const first = outputs[0]
  const isText = first.type === "post" || first.type === "article"
  if (isText) {
    const title = first.publishing.title ?? (first.payload.title as string | undefined) ?? null
    const body = (first.payload.content as string | undefined) ?? ""
    const lines = textLineCount(body, !!title)
    return {
      width,
      height: PRODUCT_LABEL_PX + textBodyHeight(lines, !!title) + PROGRAM_REGION_PX + PRODUCT_TOOLBAR_PX,
    }
  }
  return { width, height: clipNodeHeight(first.aspect ?? null) }
}

/** A node's resolved size — the per-kind default unless the node pins an
 * override (recipe surface) or carries a graph frame (results canvas). */
export function flowNodeSize(node: FlowNode): { width: number; height: number } {
  if (node.frame) return graphNodeSize(node)
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

/** Source video asset node (results canvas): the media plays inline, so the
 * frame is landscape and wide enough to watch (280 = the product lane);
 * the caption band rides above and the toolbar band below (both included in
 * the height — 2026-08-17 走查拍板: every media node carries a frosted
 * toolbar; 2026-08-19 做薄: 26 caption + 158 media + 44 band). */
export const VIDEO_ASSET_NODE_SIZE = { width: 280, height: 228 }

/** The reserved toolbar band under every media node (results canvas,
 * 2026-08-17; 做薄 2026-08-19): 8px gap + the 36px frosted bar. */
export const ASSET_TOOLBAR_PX = 44

const GAP_MAIN = 96
const GAP_CROSS = 24

/** Birth-choreography stagger quantum (ADR-036 补记 3): the delay between
 * consecutive nodes' entrances in compile-order replay — shared by the node
 * card (FlowNodeCard), the edge draw-on (FlowView), and region frames
 * (GroupFrames), so one retune never desyncs the replay. */
export const BIRTH_STAGGER_MS = 120

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
 * centered against the tallest column on the cross axis.
 *
 * 画布定居取景 (ADR-057): nodes carrying a server-settled `frame` keep
 * THEIR positions — the layout only computes the reveal order for them
 * (append-only is then structural: positions were assigned once at birth
 * and existing frames never move). */
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

  // ── 定居取景: every node framed → positions come from the server ──────
  const settled = nodes.length > 0 && nodes.every((n) => n.frame)
  const positions = new Map<string, { x: number; y: number }>()
  const revealOrder = new Map<string, number>()

  if (settled) {
    let reveal = 0
    for (const { nodes: ns } of ordered) {
      for (const n of ns) {
        positions.set(n.id, { x: n.frame!.x, y: n.frame!.y })
        revealOrder.set(n.id, reveal++)
      }
    }
    let width = 0
    let height = 0
    for (const n of nodes) {
      const size = flowNodeSize(n)
      width = Math.max(width, n.frame!.x + size.width)
      height = Math.max(height, n.frame!.y + size.height)
    }
    return { positions, revealOrder, width, height }
  }

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
