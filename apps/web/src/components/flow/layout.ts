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
  output: { width: 128, height: 216 },
  /** 配方说明书 step pills：小尺寸，不抢产物节点视觉权重。 */
  step: { width: 144, height: 48 },
  /** 全文卡 family (text/table — the 2026-09-13 增大批 lane, 260 → 340):
   * the glass text card; the measurement law's chars-per-line scales with
   * the column (see documentTextHeight), floor = the DOCUMENT_MIN_H
   * reading surface. */
  text: { width: 340, height: 280 },
  table: { width: 340, height: 280 },
  /** Media cards (the graph canvas's server-settled frame supersedes these
   * regardless — the Record's completeness forces the rows): the media
   * anatomy's box; modifier/materialize ride the same media card. */
  image: { width: 280, height: 268 },
  video: { width: 280, height: 268 },
  audio: { width: 280, height: 268 },
  modifier: { width: 280, height: 268 },
  materialize: { width: 280, height: 268 },
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

/** The version pager's own band row (2026-09-13 用户拍板): when a node holds
 * more than one product the pager stacks ABOVE the factsbar (never beside it
 * — the side-by-side row outgrew the card's width), one more 8px gap + its
 * 36px pill on top of the 44px factsbar band. Client-side addendum only:
 * frames are born with zero outputs (统一摆位律 stamps the 44px band), so the
 * server mirror never carries this row — the +44 lands on the same beat as
 * the second version's arrival, one coherent reflow, never a quiet shift. */
export const PRODUCT_PAGER_PX = 44

/** Declared handle geometry (2026-09-13 深夜, the draft-time missing-edge
 * 走查): the port law's numeric half, declared INTO the node payload so edge
 * anchors never wait for xyflow's DOM measurement. xyflow rebuilds
 * handleBounds only from a ResizeObserver pass and drops them whenever the
 * controlled `nodes` prop arrives with fresh identities (every refetch) — a
 * handle whose measure pass is lost keeps its edges invisible until remount
 * (the asset's out:video at draft time, terminal remount the only healer).
 * The port seats are pure math off the pinned box, so declare them:
 * parseHandles adopts these bounds on every rebuild and the DOM measure
 * degrades to a confirming backstop reading the same numbers. 判词② mirror:
 * these constants ARE FlowNodeCard NodePorts' CSS seats (28px circle,
 * left/right -34, 34px stack, bottom-anchored in-bases, out top 40) — the
 * card keeps the visual seat, this is the data seat; change one, change
 * both. */
export const PORT_PX = 28
export const PORT_SIDE_PX = 34
export const PORT_STEP_PX = 34
export const OUT_PORT_TOP_PX = 40
export const IN_MEDIA_PORT_BASE_PX = PRODUCT_TOOLBAR_PX + PROGRAM_REGION_PX + 16
/** 词表 v3 (C5): the 全文卡 family (text/table) in-text port base = 16 —
 * its tail furniture lives INSIDE the card (the version pager never adds
 * an external band), so the pager offset applies only to the media-card
 * anatomies. Mirror of FlowNodeCard NodePorts' CSS seat (一条律两镜像). */
export const inTextPortBasePx = (kind: FlowNodeKind, pagerPx = 0): number =>
  kind === "text" || kind === "table" ? 16 : 60 + pagerPx

/** The node payload's declared handles (xyflow first-class `node.handles`).
 * Undefined for portless nodes — their invisible fallback handles keep the
 * DOM-measured path (static surfaces, no churn). x/y = the handle box's
 * node-relative top-left (getHandleBounds semantics): in-ports sit
 * bottom-anchored at their region's corner (y = H − base − circle), the out
 * port top-anchored on the right (x = W + gap). */
export function declaredHandles(
  node: FlowNode,
  size: { width: number; height: number },
  ports?: { in: Exclude<GraphEdgeType, "ctx">[]; out: OutPortType[] } | null,
): NodeHandle[] | undefined {
  if (!ports) return undefined
  const handles: NodeHandle[] = []
  // The version pager's stacked row grows the factsbar band by
  // PRODUCT_PAGER_PX when the node holds more than one product — both
  // bottom-anchored in-port seats ride the band, so both bases shift (the
  // NodePorts mirror applies the same offset; top-anchored out ports don't).
  const pagerPx = (node.outputs?.length ?? 0) > 1 ? PRODUCT_PAGER_PX : 0
  let media = 0
  let text = 0
  for (const t of ports.in) {
    const isMedia = t === "video" || t === "audio"
    const base = isMedia
      ? IN_MEDIA_PORT_BASE_PX + pagerPx + media++ * PORT_STEP_PX
      : inTextPortBasePx(node.kind, pagerPx) + text++ * PORT_STEP_PX
    handles.push({
      id: `in:${t}`,
      type: "target",
      position: Position.Left,
      x: -PORT_SIDE_PX,
      y: size.height - base - PORT_PX,
      width: PORT_PX,
      height: PORT_PX,
    })
  }
  ports.out.forEach((t, i) => {
    handles.push({
      id: `out:${t}`,
      type: "source",
      position: Position.Right,
      x: size.width + PORT_SIDE_PX - PORT_PX,
      y: OUT_PORT_TOP_PX + i * PORT_STEP_PX,
      width: PORT_PX,
      height: PORT_PX,
    })
  })
  return handles
}

/** Clip-product card height by aspect (the graph canvas's media node):
 * caption + the aspect-exact thumb + the program region + the factsbar
 * band. Width is the frame's (per-aspect lane since 2026-09-13). */
export function clipNodeHeight(aspect?: string | null): number {
  const thumb = (aspect && PRODUCT_THUMB_PX[aspect]) || PRODUCT_THUMB_DEFAULT_PX
  return PRODUCT_LABEL_PX + thumb + PROGRAM_REGION_PX + PRODUCT_TOOLBAR_PX
}

/** Text-product body height by preview line count (post / article — no
 * baked media): padding + optional title + clamped body + hashtag band.
 * The line cap is DERIVED FROM THE NODE'S OWN FRAME RESERVATION
 * (2026-09-10 用户拍板——内容长度驱动卡高): taller reservations show more
 * lines, and by construction the body never exceeds the reservation, so
 * settled columns never overlap for ANY generation of nodes (the 2026-09-06
 * 2–12 band becomes the 440-reservation's derived value, unchanged for
 * nodes born under it). The cap bounds the NODE's height only — the full
 * body SCROLLS inside it (2026-09-08: line-clamp truncation retired for
 * in-place scroll, nowheel+nopan). */
export function textBodyHeight(lineCount: number, hasTitle: boolean): number {
  const clamped = Math.max(2, lineCount)
  const lineHeight = 18 // text-xs leading-relaxed ≈ 18px per line
  const titleHeight = hasTitle ? 22 : 0
  const hashtagsHeight = 20 // one-row hashtag band
  return 12 + titleHeight + clamped * lineHeight + hashtagsHeight + 12
}

/** How many preview lines fit inside a frame reservation, by the same
 * anatomy math as textBodyHeight (inverse of it). A 440 reservation → 12
 * lines (the legacy band); 560 (the 2026-09-10 raise) → 18. */
export function textLineCap(frameH: number, hasTitle: boolean): number {
  const bodyPx = frameH - PRODUCT_LABEL_PX - PROGRAM_REGION_PX - PRODUCT_TOOLBAR_PX
  const titleHeight = hasTitle ? 22 : 0
  return Math.max(2, Math.floor((bodyPx - 12 - titleHeight - 20 - 12) / 18))
}

/** Estimate visible lines from the body at the text card's width (~312px
 * inside the 340 text card, text-xs): ~68 chars per line for Latin, ~44 for
 * CJK. The caller clamps with textLineCap (reservation-derived). */
export function textLineCount(body: string, hasTitle: boolean): number {
  const cjk = /[一-龥぀-ゟ゠-ヿ]/.test(body)
  const charsPerLine = cjk ? 44 : 68
  const bodyLines = Math.max(1, Math.ceil(body.length / charsPerLine))
  return Math.max(2, (hasTitle ? 1 : 0) + bodyLines)
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
 * never a third copy — 判词②). `confirm` reserves the task_book's dock-time
 * confirm anatomy (price + balance + Start button — the server reserves it
 * from birth; post-Start the card fills less of the frame). */
export function documentTextHeight(text: string, confirm: boolean): number {
  const cjk = /[一-龥぀-ゟ゠-ヿ]/.test(text)
  const charsPerLine = cjk ? 43 : 67 // the server's 308px-column values (340 frame, 2026-09-13 增大批 — was 32/50 at 228px)
  const lines = text ? Math.max(1, Math.ceil(text.length / charsPerLine)) : 1
  return 26 + 16 + lines * 18 + 16 + (confirm ? 88 : 0)
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
    const dimsH = assetDimsHeight(node.asset?.width, node.asset?.height)
    const videoH =
      dimsH != null
        ? Math.min(dimsH, frame?.h ?? dimsH)
        : VIDEO_ASSET_NODE_SIZE.height
    return {
      width,
      height: node.videoUrl
        ? videoH
        : PRODUCT_LABEL_PX + 190 + PRODUCT_TOOLBAR_PX,
    }
  }
  if (node.kind === "text" || node.kind === "table") {
    // 全文卡律 + 封顶滚动律: height = the full text's need CAPPED at
    // DOCUMENT_MAX_H — the body scrolls past the cap, so the render never
    // outgrows the reservation (new frames are born with exactly this via
    // the server's mirror math, so the two agree; a legacy frame may be
    // taller than the cap — extra whitespace, never overlap). The confirm
    // anatomy is reserved only while the book is actually draft (post-Start
    // the card fills less — the frame's +88 is a reservation, not a mandate).
    const text = (node.spec?.text as string | undefined) ?? ""
    const confirm = node.spec?.role === "task_book" && node.status === "draft"
    // Floor + cap (DOCUMENT_MIN_H / MAX_H, one law with the server mirror):
    // the body scrolls past the cap; short texts fill the floor with air.
    return { width, height: Math.min(Math.max(documentTextHeight(text, confirm), DOCUMENT_MIN_H), DOCUMENT_MAX_H) }
  }
  // 媒介卡 (video/image/audio + modifier/materialize 过渡词): product
  // region + program region + bar.
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
  // The version pager's stacked row (2026-09-13 用户拍板): one extra band
  // row above the factsbar once the node holds more than one product.
  const pagerPx = outputs.length > 1 ? PRODUCT_PAGER_PX : 0
  const first = outputs[0]
  const isText = first.type === "post" || first.type === "article"
  if (isText) {
    const title = first.publishing.title ?? (first.payload.title as string | undefined) ?? null
    const body = (first.payload.content as string | undefined) ?? ""
    const lines = Math.min(textLineCount(body, !!title), textLineCap(frame?.h ?? 440, !!title))
    return {
      width,
      height: PRODUCT_LABEL_PX + textBodyHeight(lines, !!title) + PROGRAM_REGION_PX + PRODUCT_TOOLBAR_PX + pagerPx,
    }
  }
  // Never outgrow the born frame (the reservation law, 判词②): a node
  // stamped before the source dims were known keeps its conservative
  // frame — the card's media region caps to fit (FlowNodeCard mirrors the
  // cap), never an overlap. Frames born with dims are aspect-exact — the
  // cap is inert. The pager row rides ON TOP of the capped frame (frames
  // are born with zero outputs, so the reservation never carries it).
  const clipH = clipNodeHeight(first.aspect ?? null)
  return { width, height: (frame?.h ? Math.min(clipH, frame.h) : clipH) + pagerPx }
}

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
