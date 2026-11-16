import { Position, type NodeHandle } from "@xyflow/react"

import type { FlowEdge, FlowNode, FlowNodeKind, GraphEdgeType, OutPortType } from "./types"

/** Fixed node dimensions per skin — layout is pure math with zero DOM
 * measurement (SSR-safe, no ResizeObserver feedback loops). Step pills are
 * sized for a TWO-LINE label + one detail line (a truncated "Understand
 * the…" node is a bug, never a style — 2026-08-10). The kind rows are
 * fallbacks only — the graph canvas's nodes carry their server-settled
 * `frame` (画布定居取景) and `graphNodeSize` computes the content-driven
 * render size inside the reservation. 词表 v3 (ADR-076, C5 收窄): the
 * graph vocabulary is the five media values + the two transitional words;
 * the recipe surface's own asset/step/output rows ride along. */
export const FLOW_NODE_SIZE: Record<FlowNodeKind, { width: number; height: number }> = {
  asset: { width: 280, height: 260 },
  text: { width: 340, height: 280 },
  table: { width: 340, height: 280 },
  image: { width: 280, height: 268 },
  video: { width: 280, height: 268 },
  audio: { width: 280, height: 268 },
}

/** The results canvas's product card (ADR-041 D5 大卡, 2026-08-17 二轮走查
 * 放大; 2026-09-13 用户拍板 分档加宽): a corner-info band above the card (type
 * left / language right), the media flush full-bleed inside the card, a
 * padded interaction area under it (the run's prompt), and the always-on
 * action bar in a reserved band under the card. The thumb keeps the clip's
 * own frame — three aspect sizes, never a forced crop (2026-08-14 ruling).
 * The media fills the card edge to edge (no inner padding) at the ASPECT'S
 * OWN lane width (9:16 → 280, 1:1 → 340, 16:9 → 400 — 横屏真正能看, the
 * portrait tower stays put); the heights below are aspect-exact at those
 * widths. The server mirrors this table for its per-aspect frame
 * reservations — graph_store._CLIP_FRAME (一条测量律两镜像互引, 判词②). */
export const PRODUCT_THUMB_PX: Record<string, number> = {
  "9:16": 498,
  "1:1": 340,
  "16:9": 225,
}

/** The display-class snap — mirror of graph_store.display_aspect_class
 * (geometric-mean boundaries 0.75 / 4:3; nearest ratio, never a crop). The
 * clip card never snaps client-side (its class is server-stamped on the
 * payload); the ASSET card does (dims ride AssetResponse.width/height). */
export function displayAspectClass(width: number, height: number): string {
  const r = width / height
  if (r < 0.75) return "9:16"
  if (r < 1.334) return "1:1"
  return "16:9"
}

export const PRODUCT_LABEL_PX = 26
export const PRODUCT_TOOLBAR_PX = 44

export const PORT_PX = 28
export const PORT_SIDE_PX = 34
export const PORT_STEP_PX = 34
export const OUT_PORT_TOP_PX = 40
export function declaredHandles(
  node: FlowNode,
  size: { width: number; height: number },
  ports?: { in: Exclude<GraphEdgeType, "ctx">[]; out: OutPortType[] } | null,
): NodeHandle[] | undefined {
  if (!ports) return undefined
  const handles: NodeHandle[] = ports.in.map((type, index) => ({
    id: `in:${type}`,
    type: "target" as const,
    position: Position.Left,
    x: -PORT_SIDE_PX,
    y: size.height - 16 - index * PORT_STEP_PX - PORT_PX,
    width: PORT_PX,
    height: PORT_PX,
  }))
  let outStack = 0
  for (const type of ports.out) {
    const assetType = node.asset?.type
    const regionSeat = type === "text" && (assetType === "video" || assetType === "audio")
    handles.push({
      id: `out:${type}`,
      type: "source",
      position: Position.Right,
      x: size.width + PORT_SIDE_PX - PORT_PX,
      y: regionSeat
        ? size.height - ASSET_TEXT_OUT_BOTTOM_PX - PORT_PX
        : OUT_PORT_TOP_PX + outStack++ * PORT_STEP_PX,
      width: PORT_PX,
      height: PORT_PX,
    })
  }
  return handles
}

/** The document card's height cap (2026-09-11 封顶滚动律 — the transcript
 * tower walkthrough): 全文卡律 still holds (the body carries the FULL text,
 * never a summary), but the CARD caps here and the body scrolls in place —
 * the text product card's 2026-09-08 posture, now the document's too. Above
 * the cap the estimate math's error stops mattering (it only decides WHETHER
 * the cap binds), so a frame can never be outgrown and columns never overlap.
 * ONE law with the server mirror graph_store._document_frame's
 * _DOCUMENT_MAX_H — the value = the text frame class's 560 reservation. */
export const DOCUMENT_MAX_H = 560

/** The document card's height FLOOR (2026-09-13 用户拍板 高度增大): a short
 * text still gets a reading surface, never a 3-line stub — peer to the
 * generator quiet body (~278). One law with the server mirror
 * (graph_store._document_frame's _DOCUMENT_MIN_H). */
export const DOCUMENT_MIN_H = 280

/** 全文卡律 (2026-09-10 判词④——进了卡面的必须原文全文) + 封顶滚动律
 * (2026-09-11): the document card never truncates — it renders the full text
 * and SCROLLS when the need exceeds DOCUMENT_MAX_H (applied in graphNodeSize
 * and in the server mirror, never here — this helper still answers the FULL
 * need so both callers can cap it). ONE measurement law with the server's
 * frame mirror (apps/api/app/pipeline/graph_store.py _document_frame — the
 * same chars-per-line proportion off the text card's table, the same 18px
 * line, the same caption/padding anatomy; two mirrors cross-referenced,
 * never a third copy — 判词②). Phase 3 Batch A (2026-09-19 判词 1): the
 * task_book confirm-anatomy reservation (+88) is RETIRED with the canvas
 * confirm seat — the client no longer reserves it (the server's birth-frame
 * mirror keeps its reservation; the render fills less of the frame, which
 * the reservation law already permits — extra whitespace, never overlap). */
export function documentTextHeight(text: string): number {
  const cjk = /[一-龥぀-ゟ゠-ヿ]/.test(text)
  const charsPerLine = cjk ? 43 : 67 // the server's 308px-column values (340 frame, 2026-09-13 增大批 — was 32/50 at 228px)
  const lines = text ? Math.max(1, Math.ceil(text.length / charsPerLine)) : 1
  return 26 + 16 + lines * 18 + 16
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
  // 素材节点 (C4 读面后 kind 已是媒介值 — the joined asset dossier is the
  // birth certificate). 素材节点同律 (2026-09-13 用户拍板): the source's
  // real pixels shape the node — snapped to its display class's anatomy
  // (media + caption + bar, ONE law with the server's graph_store._ASSET_FRAME
  // mirror). Never outgrow the born frame: dims that landed after birth
  // (API-path uploads) keep the conservative default reservation — the
  // media flexes smaller inside (contain slivers), never an overlap.
  if (node.asset) {
    // ADR-113 §3: the transcript section rides the asset card for
    // text-yielding types (media assets: below the media; paste/transcript:
    // AS the body) — ONE law with the server mirror (graph_store._frame_of's
    // asset branch).
    const assetType = node.asset.type
    const textBearingMedia = assetType === "video" || assetType === "audio"
    if (assetType === "transcript" || assetType === "past_material") {
      // Medialess text assets: the transcript section IS the body. Legacy
      // frames (born pre-section at the 260 default) stay the cap — the
      // body scrolls tighter inside (never outgrow the born frame).
      return { width, height: Math.min(ASSET_TEXT_ONLY_H, frame?.h ?? ASSET_TEXT_ONLY_H) }
    }
    const dimsH = assetDimsHeight(node.asset?.width, node.asset?.height)
    const videoH =
      dimsH != null
        ? Math.min(dimsH, (frame?.h ?? dimsH) - (textBearingMedia ? TRANSCRIPT_SECTION_PX : 0))
        : VIDEO_ASSET_NODE_SIZE.height
    return {
      width,
      height: node.videoUrl
        ? videoH + (textBearingMedia ? TRANSCRIPT_SECTION_PX : 0)
        : PRODUCT_LABEL_PX + 190 + PRODUCT_TOOLBAR_PX + (textBearingMedia ? TRANSCRIPT_SECTION_PX : 0),
    }
  }
  if (node.kind === "text" || node.kind === "table") {
    // 全文卡律 + 封顶滚动律: height = the full text's need CAPPED at
    // DOCUMENT_MAX_H — the body scrolls past the cap, so the render never
    // outgrows the reservation (new frames are born with exactly this via
    // the server's mirror math, so the two agree; a legacy frame may be
    // taller than the cap — extra whitespace, never overlap).
    const text = (node.spec?.prompt ?? node.spec?.text ?? "") as string
    // Floor + cap (DOCUMENT_MIN_H / MAX_H, one law with the server mirror):
    // the body scrolls past the cap; short texts fill the floor with air.
    return { width, height: Math.min(Math.max(documentTextHeight(text), DOCUMENT_MIN_H), DOCUMENT_MAX_H) }
  }
  return { width, height: frame?.h ?? fallback.height }
}

/** The asset node's content height}

/** The asset node's content height from the source's real dims (media +
 * caption + bar) — the client mirror of graph_store._ASSET_FRAME. Null when
 * dims are unknown (the caller keeps the legacy default). */
function assetDimsHeight(
  width?: number | null,
  height?: number | null,
): number | null {
  if (!width || !height) return null
  return (
    PRODUCT_LABEL_PX + PRODUCT_THUMB_PX[displayAspectClass(width, height)] + ASSET_TOOLBAR_PX
  )
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

/** The transcript section's reservation below the media (ADR-113 §3;
 * ADR-115 素材卡阅读型解剖: media + 检视皮(入舞台底缘) + cue 流): divider 1
 * + pad 8 + header 20 + gap 6 + cue flow 150 + pad 12. ONE law with the
 * server mirror (graph_store._TRANSCRIPT_SECTION_PX) and the card's flex
 * seat (FlowNodeCard.TranscriptSection). */
export const TRANSCRIPT_SECTION_PX = 197
/** 出锚产区律 (2026-10-11 拍板): the out anchor parks at ITS production
 * region's top-right — the media stage's (OUT_PORT_TOP_PX) for the media
 * flow, the transcript section's for a text-bearing asset's T flow (the
 * wire grows out of the words). The section is the ring card's LAST region,
 * so the seat is bottom-anchored and aspect-free: factsbar band + section
 * reservation − 6px into the header row − the circle. NodePorts' CSS seat
 * reads this constant directly; declaredHandles' y = H − this − PORT_PX. */
export const ASSET_TEXT_OUT_BOTTOM_PX =
  PRODUCT_TOOLBAR_PX + TRANSCRIPT_SECTION_PX - 6 - PORT_PX
/** Medialess text assets (paste/transcript — the section IS the body):
 * caption 26 + section 196 + toolbar 44 (server mirror:
 * graph_store._ASSET_TEXT_ONLY_H). */
export const ASSET_TEXT_ONLY_H = 266

// 间距常数 (C6, 2026-09-14 拍板 64/16/88; 2026-09-28 用户走查放宽主距
// 64→124): one law with the server mirror graph_store._GAP_MAIN/_GAP_CROSS
// (the rise is server-stamped). 放宽动因: 09-13 分档加宽后最宽泳道 400,
// 64 净距被左右各凸出 34 的端口圆 (PORT_SIDE_PX) 吃成相碰——124 恢复
// 加宽前的通道宽度.
const GAP_MAIN = 124
const GAP_CROSS = 16


/** Birth-choreography stagger quantum (ADR-036 补记 3): the delay between
 * consecutive nodes' entrances in compile-order replay — shared by the node
 * card (FlowNodeCard), the edge draw-on (FlowView), and region frames
 * (GroupFrames), so one retune never desyncs the replay. */
export const BIRTH_STAGGER_MS = 120

export interface FlowLayout {
  positions: Map<string, { x: number; y: number }>
  /** Reveal order for birth choreography: rank-major (the server's Product
   * Graph projection), then the frame's y seat — a slowed-down replay of the
   * real compile order. */
  revealOrder: Map<string, number>
  width: number
  height: number
}

/** Layer asset and manual nodes by their real connections. */
export function layoutFlow(nodes: FlowNode[], edges: FlowEdge[]): FlowLayout {
  const positions = new Map<string, { x: number; y: number }>()
  const revealOrder = new Map<string, number>()

  // ── Recipe surface (frame-less): the local layered layout ─────────────
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
