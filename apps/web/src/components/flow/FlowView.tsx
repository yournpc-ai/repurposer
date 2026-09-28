"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Background,
  BackgroundVariant,
  getNodesBounds,
  getViewportForBounds,
  Panel,
  ReactFlow,
  useReactFlow,
  useStore,
  ViewportPortal,
} from "@xyflow/react"

import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import "@xyflow/react/dist/style.css"
import "./flow.css"

import { FlowEdge, type FlowEdgeType } from "./FlowEdge"
import { FlowNodeCard, nodeRenderActive, type FlowCardNode } from "./FlowNodeCard"
import { BIRTH_STAGGER_MS, declaredHandles, flowNodeSize, layoutFlow } from "./layout"
import type { FlowGroup, FlowNode, FlowViewProps, GraphEdgeType, OutPortType } from "./types"

const nodeTypes = { flowCard: FlowNodeCard }
const edgeTypes = { flow: FlowEdge }

/** The port law's source half (出锚语义律, 2026-09-11 — see types.ts): a
 * node's OUT anchor = its own production medium. 词表 v3 媒介直出
 * (ADR-076, C5 收窄 — the read face already mapped every row): the node
 * type IS its production medium; text/table read prose, the three media
 * name themselves. The transitional words (modifier/materialize — legacy
 * rows) fall back to the frame class, and the recipe surface's manual
 * asset node reads its own kind. */
function productionPort(n: FlowNode): OutPortType {
  if (n.kind === "video" || n.kind === "audio" || n.kind === "image") return n.kind
  if (n.kind === "text" || n.kind === "table") return "text"
  if (n.kind === "asset") {
    // Recipe surface only (the graph canvas's asset rows arrive mapped).
    const t = n.asset?.type
    if (t === "audio") return "audio"
    if (t === "video") return "video"
    if (t === "image" || t === "slides") return "image"
    return "text"
  }
  // modifier / materialize (transitional read-face words): the frame class
  // names the product medium (clip family = media, text family = prose).
  return n.spec?.frame_class === "text" ? "text" : "video"
}

/** The one fit recipe, shared by the ViewportController (auto-fit) and the
 * FlowControls pill (manual fit) — two hard-won parameter rules:
 * 1. minZoom must go LOW (0.15) — a wide recipe graph needs ~0.36 on the
 *    overlay canvas; when the floor clamps above the needed zoom,
 *    getViewportForBounds still centers, so the graph overflows BOTH edges
 *    (2026-08-10 bug: right column cut off).
 * 2. maxZoom caps at 1 on fit surfaces — a small graph must not upscale
 *    into giant cards.
 * padding 0.2 ≈ 8.3% per side (xyflow's parsePadding: (v − v/(1+p))/2) —
 * clears the overlay's floating tab bar (top-5 + h-9 ≈ 56px). */
const FIT_VIEW_OPTIONS = { minZoom: 0.15, maxZoom: 1, padding: 0.2 } as const

/** Occlusion-aware fit (2026-09-28 — the transcript card birthed UNDER the
 * docked chat panel): frame the graph within the SAFE region — the
 * container minus the docked panel's width. getViewportForBounds centers
 * the bounds in the GIVEN width, so passing the safe width centers the
 * graph clear of the frost; a plain fitView centers in the full container
 * and the right column slides under the panel. Falls back to the plain
 * fitView when nothing occludes. One recipe, three seats: the
 * ViewportController's auto fits, the zoom menu's 适应窗口, and ⌘0. */
function fitInSafeRegion(
  rf: ReturnType<typeof useReactFlow>,
  el: HTMLDivElement,
  occludedRightPx: number,
  duration: number,
): void {
  const graphNodes = rf.getNodes()
  if (graphNodes.length === 0) return
  const safeW = el.clientWidth - occludedRightPx
  if (occludedRightPx > 0 && safeW > 0) {
    const vp = getViewportForBounds(
      getNodesBounds(graphNodes),
      safeW,
      el.clientHeight,
      FIT_VIEW_OPTIONS.minZoom,
      FIT_VIEW_OPTIONS.maxZoom,
      FIT_VIEW_OPTIONS.padding,
    )
    void rf.setViewport(vp, { duration })
    return
  }
  void rf.fitView({ ...FIT_VIEW_OPTIONS, duration })
}

/** Fit + center via the framework's own `fitView` (xyflow's recommended
 * centered-with-padding viewport, FIT_VIEW_OPTIONS above).
 * Runs: on mount (double rAF, after paint + measurement), on growth
 * (animated), and on surface resize (ResizeObserver; fit-locked surfaces
 * only — explore surfaces keep the user's own viewport). */
function ViewportController({
  count,
  wrapperRef,
  navigation,
  settleKey,
  occludedRightPx = 0,
}: {
  count: number
  wrapperRef: React.RefObject<HTMLDivElement | null>
  navigation: "fit" | "explore"
  settleKey?: string | null
  occludedRightPx?: number
}) {
  const rf = useReactFlow()
  const prevCountRef = useRef<number | null>(null)

  const fit = useCallback(
    (duration: number) => {
      const el = wrapperRef.current
      if (!el || !el.clientWidth || !el.clientHeight) return
      if (rf.getNodes().length === 0) return
      fitInSafeRegion(rf, el, occludedRightPx, duration)
    },
    [rf, wrapperRef, occludedRightPx],
  )

  useEffect(() => {
    // Settle-driven surfaces (settleKey provided): the count-based initial
    // fit is DISABLED — the count transition fired on the first PARTIAL
    // fetch frame (the three sources resolve in any order) and everything
    // after is growth, which explore never re-frames (refresh / re-entry
    // used to strand the graph at the default top-left viewport).
    if (settleKey != null) return
    const prev = prevCountRef.current
    prevCountRef.current = count
    const firstEver = prev === null
    // Explore surfaces keep the user's own viewport on GROWTH (2026-08-19
    // 二轮 R2): refinement new-arrivals must not yank a hand-set pan/zoom. But empty→non-empty is NOT growth: the project
    // page keeps the canvas MOUNTED behind the fullscreen chat (opacity
    // gate, not unmount), so the controller's true mount fires on an empty
    // graph and the run's nodes arriving with the morph beat IS the first
    // real framing (2026-09-05 fix: the graph used to sit at the default
    // top-left viewport forever). Only a genuinely growing graph skips.
    if (!firstEver && navigation === "explore" && prev! > 0) return
    // Double rAF (after paint + measurement); BOTH frames are tracked so a
    // mid-flight unmount never leaves a dangling callback.
    let inner = 0
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => fit(firstEver ? 0 : 300))
    })
    return () => {
      cancelAnimationFrame(outer)
      cancelAnimationFrame(inner)
    }
  }, [count, fit, navigation, settleKey])

  // ── Settle-driven initial framing (2026-09-06) ────────────────────────
  // Each transition to a NEW non-null key frames once (the surface's
  // visible, settled content is present — for the results canvas:
  // baselineReady && hasRuns). The fired mark lands inside the rAF, not
  // the effect body, so a cancelled pass (unmount / StrictMode remount)
  // re-fires instead of latching the key without framing.
  const firedSettleRef = useRef<string | null>(null)
  useEffect(() => {
    const key = settleKey ?? null
    if (key == null) {
      // A settle withdrawal (runs wiped / project switch loading) re-arms
      // the next settle — a same-key return (a new run after a wipe) must
      // re-frame, not latch on the stale mark.
      firedSettleRef.current = null
      return
    }
    if (firedSettleRef.current === key) return
    let inner = 0
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => {
        firedSettleRef.current = key
        fit(300)
      })
    })
    return () => {
      cancelAnimationFrame(outer)
      cancelAnimationFrame(inner)
    }
  }, [settleKey, fit])

  useEffect(() => {
    if (navigation !== "fit") return
    const el = wrapperRef.current
    if (!el || typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(() => fit(0))
    observer.observe(el)
    return () => observer.disconnect()
  }, [navigation, fit, wrapperRef])

  return null
}

/** 相机律 (Workspace 合同 v4.2 C5, 2026-09-26 封板 —— ensure-in-view 一条):
 * user-initiated beats move the camera — NEVER background refetches (the
 * surface arms a beat only inside its own send / Start handlers, so a
 * polling / SSE arrival carrying new ids can't yank the view; the
 * 2026-08-19「增长不动视口」law's narrowing, not its repeal). The rule in
 * full: is the current operation's target inside the safe viewport (the
 * visible region minus the docked panel's occlusion)? Already in: NO move.
 * Not in: the MINIMAL pan that brings it into the readable region. Zoom:
 * NEVER auto-changes — the fit/fitNow beats are deleted (the 2026-09-25
 * confirm-pill whole-chain fitNow was reversed 2026-09-26 in favor of the
 * sealed contract; the sole automatic fit remains the Workspace Birth's
 * initial settle framing, owned by the mount, not by this machine).
 * Guards:
 * - 手势防护: a user drag/zoom within the last 3s shields the beat (they
 *   grabbed the canvas mid-flight — don't fight the hand);
 * - prefers-reduced-motion: the transition degrades to an instant jump;
 * - a hidden surface (no box) spends the beat WITHOUT moving — the
 *   settle/morph framing owns the first show;
 * - docked 面板遮挡补偿: the safe region excludes the occluded right edge.
 * One-shot: consumes on the FIRST arrival carrying a node-id delta — a
 * racing no-delta fetch (SSE tick) never eats the beat early; a ~5s
 * timeout retires an arm whose stamp never lands. */
const GESTURE_SHIELD_MS = 3000
const CAMERA_BEAT_TIMEOUT_MS = 5000
/** The safe viewport's inset (screen px) — a node brushing the chrome edge
 * reads as out of view. */
const SAFE_MARGIN_PX = 24

/** The ONE camera movement primitive (v4.2 C5 + 未覆盖 #3, 2026-09-26
 * 拍板): setCenter with the zoom EXPLICITLY locked to the current
 * viewport's — zoom never auto-changes. Both camera gestures converge on
 * it: ensure-in-view's minimal pan (the target point = the current center
 * + the shortfall delta) and "center the current operation element" (the
 * target point = the element's frame center, occlusion-compensated). */
function panLockedCenter(
  rf: ReturnType<typeof useReactFlow>,
  cx: number,
  cy: number,
  duration: number,
) {
  const zoom = rf.getViewport().zoom
  void rf.setCenter(cx, cy, { zoom, duration })
}

/** An edge endpoint's busy beat: running status OR render-in-flight. */
function nodeBusy(n: FlowNode | undefined): boolean {
  return !!n && (n.status === "running" || nodeRenderActive(n))
}

function CameraBeats({
  nodes,
  beat,
  centerRequest,
  wrapperRef,
  occludedRightPx = 0,
  lastGestureRef,
  onConsumed,
  onCenterConsumed,
}: {
  nodes: FlowNode[]
  beat: { token: number } | null | undefined
  /** 「把当前操作元素移到画布中心」 (v4.2 未覆盖 #3 — the camera capability
   * the contract upgrades to): a ONE-SHOT explicit request naming the node
   * to center (zoom locked). Available to any surface/agent-driven caller;
   * it is a deliberate gesture, not an ambient beat, so it needs no
   * node-delta — the element is already on the canvas. */
  centerRequest?: { token: number; nodeId: string } | null
  wrapperRef: React.RefObject<HTMLDivElement | null>
  occludedRightPx?: number
  lastGestureRef: React.RefObject<number>
  onConsumed?: () => void
  onCenterConsumed?: () => void
}) {
  const rf = useReactFlow()
  const prevIdsRef = useRef<ReadonlySet<string> | null>(null)
  const prevOutsRef = useRef<ReadonlyMap<string, number> | null>(null)
  const armedTokenRef = useRef<number | null>(null)

  // Track the current arm by token (declared BEFORE the delta effect so a
  // same-render arm+arrival still reads the fresh token).
  useEffect(() => {
    armedTokenRef.current = beat?.token ?? null
  }, [beat])

  // Timeout: an arm whose stamp never carries new ids expires.
  useEffect(() => {
    if (!beat) return
    const timer = setTimeout(() => onConsumed?.(), CAMERA_BEAT_TIMEOUT_MS)
    return () => clearTimeout(timer)
  }, [beat, onConsumed])

  // 「移到画布中心」— the explicit centering gesture: one shot on arrival,
  // zoom locked, the same shields as the ambient beats. An unknown nodeId
  // (the element left the canvas) spends the request silently.
  useEffect(() => {
    if (!centerRequest) return
    const el = wrapperRef.current
    if (!el || !el.clientWidth || !el.clientHeight) return onCenterConsumed?.()
    if (Date.now() - lastGestureRef.current < GESTURE_SHIELD_MS) {
      return onCenterConsumed?.()
    }
    const node = nodes.find((n) => n.id === centerRequest.nodeId)
    const f = node?.frame
    if (!f) return onCenterConsumed?.()
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    const zoom = rf.getViewport().zoom
    // 遮挡补偿: center the element in the VISIBLE region — anchoring the
    // world point half an occlusion RIGHT of the element's center puts it
    // half an occlusion LEFT of the viewport center (world px = screen px /
    // zoom).
    panLockedCenter(
      rf,
      f.x + f.w / 2 + occludedRightPx / 2 / zoom,
      f.y + f.h / 2,
      reduce ? 0 : 400,
    )
    onCenterConsumed?.()
  }, [centerRequest, nodes, rf, wrapperRef, occludedRightPx, lastGestureRef, onCenterConsumed])

  useEffect(() => {
    const ids = new Set(nodes.map((n) => n.id))
    const prev = prevIdsRef.current
    prevIdsRef.current = ids
    const outCounts = new Map(nodes.map((n) => [n.id, n.outputs?.length ?? 0]))
    const prevOuts = prevOutsRef.current
    prevOutsRef.current = outCounts
    // The baseline frame is never a beat (refresh / reconnect / the heal
    // remount render instantly — 铁律).
    if (prev === null) return
    if (!beat || armedTokenRef.current !== beat.token) return
    const newborns = nodes.filter((n) => !prev.has(n.id))
    // 产出落地跟随 (2026-09-24 user ruling): a node whose product count
    // GREW is a landing the camera follows too — outputs fill EXISTING
    // nodes, so the id-diff alone never saw the run's harvest arrive.
    const filled = nodes.filter(
      (n) => (n.outputs?.length ?? 0) > (prevOuts?.get(n.id) ?? 0),
    )
    const targets = [...newborns, ...filled]
    if (targets.length === 0) return // a racing no-delta fetch — arm survives
    const el = wrapperRef.current
    if (!el || !el.clientWidth || !el.clientHeight) return onConsumed?.()
    if (Date.now() - lastGestureRef.current < GESTURE_SHIELD_MS) {
      return onConsumed?.()
    }
    // ensure-in-view (v4.2 C5): the target cluster's world bbox against the
    // SAFE viewport (the visible region minus the margin and the docked
    // panel's occlusion). Already inside → the beat spends with ZERO
    // movement; outside → the minimal pan that closes the shortfall, zoom
    // locked.
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    let framed = 0
    for (const n of targets) {
      const f = n.frame
      if (!f) continue
      framed += 1
      minX = Math.min(minX, f.x)
      minY = Math.min(minY, f.y)
      maxX = Math.max(maxX, f.x + f.w)
      maxY = Math.max(maxY, f.y + f.h)
    }
    if (framed === 0) return onConsumed?.()
    const vp = rf.getViewport()
    const w = el.clientWidth / vp.zoom
    const h = el.clientHeight / vp.zoom
    const left = -vp.x / vp.zoom
    const top = -vp.y / vp.zoom
    const m = SAFE_MARGIN_PX / vp.zoom
    const safeLeft = left + m
    const safeTop = top + m
    const safeRight = left + w - m - occludedRightPx / vp.zoom
    const safeBottom = top + h - m
    // The per-axis shortfall (world units); a cluster wider/taller than the
    // safe region can never fully fit at a locked zoom — align its near
    // edge (the honest best at this zoom).
    let dx = 0
    if (minX < safeLeft) dx = safeLeft - minX
    else if (maxX > safeRight) dx = Math.max(safeRight - maxX, safeLeft - minX)
    let dy = 0
    if (minY < safeTop) dy = safeTop - minY
    else if (maxY > safeBottom) dy = Math.max(safeBottom - maxY, safeTop - minY)
    if (dx === 0 && dy === 0) return onConsumed?.() // 已在安全区：不动
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    panLockedCenter(rf, left + w / 2 + dx, top + h / 2 + dy, reduce ? 0 : 400)
    onConsumed?.()
  }, [nodes, beat, rf, wrapperRef, occludedRightPx, lastGestureRef, onConsumed])

  return null
}

/** Region frames (2026-08-19 预留, the FLORA technique-workflow form — the
 * recipe surface uses it first): one large rounded frame behind each member
 * cluster, labeled with the region's 大叙事. Bounds are pure layout math
 * (positions + fixed sizes + padding); the frame renders inside the
 * ViewportPortal at zIndex -1 — below edges and nodes (they sit later in
 * the viewport's stacking context), above the dot background, and it never
 * intercepts pointer events (the portal layer is pointer-events: none). */
const GROUP_PAD = 28

function GroupFrames({
  groups,
  layout,
  sizes,
  bornRanks,
}: {
  groups: FlowGroup[]
  layout: ReturnType<typeof layoutFlow>
  sizes: Map<string, { width: number; height: number }>
  bornRanks: Map<string, number>
}) {
  return (
    <ViewportPortal>
      {groups.map((group) => {
        const members = group.nodeIds.flatMap((id) => {
          const pos = layout.positions.get(id)
          const size = sizes.get(id)
          return pos && size ? [{ pos, size, born: bornRanks.get(id) }] : []
        })
        if (members.length === 0) return null
        const minX = Math.min(...members.map((m) => m.pos.x)) - GROUP_PAD
        const minY = Math.min(...members.map((m) => m.pos.y)) - GROUP_PAD
        const maxX =
          Math.max(...members.map((m) => m.pos.x + m.size.width)) + GROUP_PAD
        const maxY =
          Math.max(...members.map((m) => m.pos.y + m.size.height)) + GROUP_PAD
        // The frame enters with its newborn members (保留决定 2026-08-19 拍
        // 板)——此路径未经验证，首个双用 surface 上线时必须抽帧核对框与成员
        // 的入场同步。No newborn member = the frame renders instantly.
        const bornMax = Math.max(...members.map((m) => m.born ?? -1))
        const born = bornMax >= 0
        return (
          <div
            key={group.id}
            aria-hidden
            className={cn(
              "absolute rounded-3xl ring-foreground/10 ring-1",
              born && "flow-node-born",
            )}
            style={{
              left: minX,
              top: minY,
              width: maxX - minX,
              height: maxY - minY,
              zIndex: -1,
              ...(born ? { animationDelay: `${bornMax * BIRTH_STAGGER_MS}ms` } : {}),
            }}
          >
            {group.label && (
              <span className="text-meta absolute top-3 left-4 text-[11px]">
                {group.label}
              </span>
            )}
          </div>
        )
      })}
    </ViewportPortal>
  )
}

/** The canvas's own navigation chrome (2026-08-19 — replaces the project
 * page's home-inherited top-right cluster). 缩放菜单形态 (2026-09-28 用户拍
 * 板, Figma parity — 照抄): the pill (live percentage + chevron) opens a
 * menu — 放大 / 缩小 (center-anchored steps), 适应窗口 (fitView with the
 * shared padding), 缩放至 50/100/150% (zoomTo is center-anchored in xyflow)
 * — with ⌘+/⌘-/⌘0 hints; the shortcuts bind ONLY while the pointer is over
 * the canvas (the browser's own zoom stays untouched outside it). Rides
 * the same dock-surface recipe as the dock and the 计划 node. Explore
 * surfaces only (the parent gates it). Subscribes to zoom ONLY
 * (transform[2]) — useViewport's {x,y,zoom} shallow compare would re-render
 * the pill on every pan frame. */
function FlowControls({
  className,
  wrapperRef,
  occludedRightPx = 0,
}: {
  className?: string
  wrapperRef: React.RefObject<HTMLDivElement | null>
  occludedRightPx?: number
}) {
  const { t } = useTranslation()
  const rf = useReactFlow()
  const zoom = useStore((s) => s.transform[2])

  // The shortcuts' hover gate lives inside the effect: rf and wrapperRef
  // are both stable, so the listeners re-attach only when the docked
  // panel's occlusion changes geometry.
  useEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    let hovering = false
    const enter = () => {
      hovering = true
    }
    const leave = () => {
      hovering = false
    }
    el.addEventListener("pointerenter", enter)
    el.addEventListener("pointerleave", leave)
    const onKey = (e: KeyboardEvent) => {
      if (!hovering || !(e.metaKey || e.ctrlKey)) return
      if (e.key === "=" || e.key === "+") {
        e.preventDefault()
        void rf.zoomIn({ duration: 200 })
      } else if (e.key === "-") {
        e.preventDefault()
        void rf.zoomOut({ duration: 200 })
      } else if (e.key === "0") {
        e.preventDefault()
        fitInSafeRegion(rf, el, occludedRightPx, 300)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => {
      el.removeEventListener("pointerenter", enter)
      el.removeEventListener("pointerleave", leave)
      window.removeEventListener("keydown", onKey)
    }
  }, [rf, wrapperRef, occludedRightPx])

  return (
    <Panel position="top-right" className={cn("!m-3 md:!m-4", className)}>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <button
              type="button"
              aria-label={t("results.canvas.zoomMenu")}
              title={t("results.canvas.zoomMenu")}
              className="dock-surface flex h-9 items-center gap-1 rounded-md px-3 text-muted-foreground text-xs tabular-nums ring-foreground/10 ring-1 transition-colors hover:bg-accent hover:text-foreground"
            />
          }
        >
          {Math.round(zoom * 100)}%
          <ChevronDown className="size-3.5" aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuGroup>
            <DropdownMenuItem
              onClick={() => void rf.zoomIn({ duration: 200 })}
            >
              {t("results.canvas.zoomIn")}
              <DropdownMenuShortcut>⌘ +</DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => void rf.zoomOut({ duration: 200 })}
            >
              {t("results.canvas.zoomOut")}
              <DropdownMenuShortcut>⌘ -</DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => {
                const el = wrapperRef.current
                if (el) fitInSafeRegion(rf, el, occludedRightPx, 300)
              }}
            >
              {t("results.canvas.zoomFit")}
              <DropdownMenuShortcut>⌘ 0</DropdownMenuShortcut>
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            {[50, 100, 150].map((pct) => (
              <DropdownMenuItem
                key={pct}
                onClick={() => void rf.zoomTo(pct / 100, { duration: 200 })}
              >
                {t("results.canvas.zoomToPct", { pct })}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </Panel>
  )
}

/** FlowView (ADR-036): the shared read-only graph substrate. Editing gestures
 * are structurally absent (nodesDraggable / nodesConnectable hard-locked);
 * zoom/pan are navigation, gated per surface (`navigation` prop). */
export function FlowView({
  nodes,
  edges,
  selectedId = null,
  onSelect,
  onOutputAction,
  onQuoteOutput,
  onAssetAction,
  onExpandMedia,
  onDisplayChange,
  onPromptEdit,
  onTextEdit,
  pendingProgram = null,
  promptConfirm = null,
  onPaneClick,
  navigation = "fit",
  controls = false,
  controlsClassName,
  settleKey,
  bornIds,
  cameraBeat = null,
  onCameraBeatConsumed,
  centerRequest = null,
  onCenterRequestConsumed,
  occludedRightPx = 0,
  groups = [],
  overlay,
  dots = false,
  className,
}: FlowViewProps) {
  // React Flow measures the DOM — client-only mount (SSR renders the
  // placeholder frame; hydration swaps in the real graph).
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const wrapperRef = useRef<HTMLDivElement>(null)
  // 手势防护 (C6): the last USER pan/zoom timestamp — CameraBeats yields to
  // a hand that grabbed the canvas mid-flight. onMoveStart's event arg is
  // null for PROGRAMMATIC moves (fit/setCenter), non-null only for real
  // gestures, so the camera's own beats never self-shield.
  const lastGestureRef = useRef(0)

  const { rfNodes, rfEdges, layout, sizes, bornRanks } = useMemo(() => {
    const layout = layoutFlow(nodes, edges)
    const sizes = new Map(nodes.map((n) => [n.id, flowNodeSize(n)]))
    // The port law's data half (ADR-057): each node's visible handles derive
    // from its incident TYPED edges — in-ports stack from the consumption
    // region's bottom-left corner typed by WHAT THE CONSUMER TAKES (the
    // edge's carried type), out-ports from the production region's
    // top-right typed by THE NODE'S OWN MEDIUM (出锚语义律 — one anchor per
    // node, every out-edge leaves from it; productionPort above). Untyped
    // surfaces (the recipe 说明书) carry no ports and keep the legacy
    // invisible handles.
    const nodeById = new Map(nodes.map((n) => [n.id, n]))
    const portsByNode = new Map<string, { in: Exclude<GraphEdgeType, "ctx">[]; out: OutPortType[] }>()
    for (const e of edges) {
      if (!e.edgeType) continue
      const target = portsByNode.get(e.to) ?? { in: [], out: [] }
      // The in-anchor vocabulary is T / video / audio ONLY (2026-09-12 用户
      // 拍板): the ctx reference flow folds into the T anchor — no @ glyph
      // ever lands on the canvas.
      const inType = e.edgeType === "ctx" ? "text" : e.edgeType
      if (!target.in.includes(inType)) target.in.push(inType)
      portsByNode.set(e.to, target)
      const src = nodeById.get(e.from)
      const outType = src ? productionPort(src) : e.edgeType
      const source = portsByNode.get(e.from) ?? { in: [], out: [] }
      if (!source.out.includes(outType)) source.out.push(outType)
      portsByNode.set(e.from, source)
    }
    // Newborn ids → stagger ranks in compile order (the reveal order IS the
    // slowed-down compile order). One batch births together; the delay gap
    // between consecutive ranks is the shared BIRTH_STAGGER_MS quantum.
    const bornRanks = new Map<string, number>()
    if (bornIds && bornIds.size > 0) {
      ;[...bornIds]
        .sort(
          (a, b) =>
            (layout.revealOrder.get(a) ?? 0) - (layout.revealOrder.get(b) ?? 0),
        )
        .forEach((id, rank) => bornRanks.set(id, rank))
    }
    const rfNodes: FlowCardNode[] = nodes.map((n) => {
      const size = flowNodeSize(n)
      return {
        id: n.id,
        type: "flowCard",
        position: layout.positions.get(n.id) ?? { x: 0, y: 0 },
        // Pinned geometry (2026-09-13 走查取证, the mid-run vanish's root):
        // we KNOW the box — the frame law computes it — so declare it as
        // first-class dims, not just CSS. Every refetch maps fresh node
        // objects; xyflow's adoptUserNodes drops `measured` on identity
        // change and waits for the ResizeObserver to re-measure, and a node
        // whose DOM box never changes size stays `visibility: hidden`
        // forever (only the terminal remount healed it). Carrying `measured`
        // survives every rebuild verbatim — and parseHandles preserves the
        // previous handleBounds ONLY when userNode.measured is set, so edges
        // keep their anchors too. DOM measurement degrades to a confirming
        // backstop (it can only ever read these same numbers off the pinned
        // wrapper style).
        width: size.width,
        height: size.height,
        measured: { width: size.width, height: size.height },
        // Declared port seats (the missing-edge half of the same 走查):
        // parseHandles adopts these as handleBounds on every rebuild, so
        // edges anchor from the first frame — DOM handle measurement becomes
        // a confirming backstop, never the gate.
        handles: declaredHandles(n, size, portsByNode.get(n.id)),
        // Explicit dims keep the DOM in lockstep with the layout math (fixed
        // sizes = pure-math layout, zero measurement).
        style: size,
      data: {
        node: n,
        bornIndex: bornRanks.get(n.id),
        selected: n.id === selectedId,
        ports: portsByNode.get(n.id),
        onOutputAction,
        onQuoteOutput,
        onAssetAction,
        onExpandMedia,
        onDisplayChange,
        onPromptEdit,
        onTextEdit,
        pendingProgram:
          pendingProgram && pendingProgram.nodeId === n.id
            ? pendingProgram.text
            : null,
        promptConfirm:
          promptConfirm && promptConfirm.nodeId === n.id
            ? {
                blastLabels: promptConfirm.blastLabels,
                blastSingle: promptConfirm.blastSingle,
                low: promptConfirm.low,
                high: promptConfirm.high,
                unquoted: promptConfirm.unquoted,
                balance: promptConfirm.balance,
                onConfirm: promptConfirm.onConfirm,
                onCancel: promptConfirm.onCancel,
              }
            : null,
      },
      draggable: false,
      connectable: false,
      }
    })
    const rfEdges: FlowEdgeType[] = edges.map((e) => {
      // An edge draws once a born endpoint enters (delay = the later birth).
      const from = bornRanks.get(e.from) ?? -1
      const to = bornRanks.get(e.to) ?? -1
      const bornAt = Math.max(from, to)
      return {
        id: `${e.from}->${e.to}${e.edgeType ? `:${e.edgeType}` : ""}`,
        source: e.from,
        target: e.to,
        type: "flow",
        // Typed flows land on their named ports (the visible handles): the
        // source anchor = the source node's own production medium (出锚语义律),
        // the target anchor = the carried type — with ctx folded into the
        // shared T anchor (2026-09-12); untyped surfaces fall back to the
        // node's default handle pair.
        ...(e.edgeType
          ? {
              sourceHandle: `out:${nodeById.get(e.from) ? productionPort(nodeById.get(e.from)!) : e.edgeType}`,
              targetHandle: `in:${e.edgeType === "ctx" ? "text" : e.edgeType}`,
            }
          : {}),
        data: {
          semantic: e.semantic,
          edgeType: e.edgeType,
          drawDelay: bornAt >= 0 ? bornAt * BIRTH_STAGGER_MS + 240 : null,
          // Live work = a running node OR a render-in-flight clip output
          // (2026-09-24 统一: the render beat rides the same packet — the
          // producing step flips the node done while the render runs
          // async, and the 转写-era status-only wiring went silent there).
          active:
            nodeBusy(nodes.find((n) => n.id === e.to)) ||
            nodeBusy(nodes.find((n) => n.id === e.from)),
        },
        selectable: false,
        focusable: false,
      }
    })
    return { rfNodes, rfEdges, layout, sizes, bornRanks }
  }, [nodes, edges, selectedId, bornIds, onOutputAction, onQuoteOutput, onAssetAction, onExpandMedia, onDisplayChange, onPromptEdit, pendingProgram, promptConfirm])

  if (!mounted) {
    return <div className={cn("w-full", className)} aria-hidden />
  }

  const explore = navigation === "explore"

  return (
    <div ref={wrapperRef} className={cn("w-full", className)}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        // The store's zoom floor must sit BELOW any fit the controller can
        // compute (a floor above it clamps the fit and overflows the canvas).
        minZoom={0.15}
        maxZoom={1.5}
        // Vendor attribution off — the canvas is product chrome, not an ad slot.
        proOptions={{ hideAttribution: true }}
        // Editing gestures: hard-off (ADR-035 §2 — compile_graph is the sole
        // topology source). Navigation: gated per surface (ADR-036 补记).
        nodesDraggable={false}
        nodesConnectable={false}
        zoomOnScroll={explore}
        zoomOnPinch={explore}
        zoomOnDoubleClick={false}
        panOnDrag={explore}
        panOnScroll={false}
        elementsSelectable
        edgesFocusable={false}
        onMoveStart={(event) => {
          if (event) lastGestureRef.current = Date.now()
        }}
        onNodeClick={(_, node) => onSelect?.(node.id)}
        onPaneClick={onPaneClick}
      >
        {dots && (
          // The workshop dot grid — the canvas SIGNATURE, the only dotted
          // surface (ADR-046 附; home dropped it 2026-09-02: a fixed texture
          // behind a non-pannable surface advertises an affordance that
          // isn't there — single-surface use makes the dots MEAN "you've
          // entered the graph"). Recipe = FLORA's measured world constants:
          // 32px gap, 2px dot (react-flow `size` is a DIAMETER),
          // muted-foreground 32%/30%. Plain world-space — scales with zoom,
          // no re-tiling, never re-add zoom compensation (an earlier
          // zoom-invariant version was over-engineering and retired).
          <Background
            variant={BackgroundVariant.Dots}
            gap={32}
            size={2}
            color="var(--muted-foreground)"
            className="opacity-[0.32] dark:opacity-30"
          />
        )}
        {groups.length > 0 && (
          <GroupFrames
            groups={groups}
            layout={layout}
            sizes={sizes}
            bornRanks={bornRanks}
          />
        )}
        {overlay}
        <ViewportController
          count={nodes.length}
          wrapperRef={wrapperRef}
          navigation={navigation}
          settleKey={settleKey}
          occludedRightPx={occludedRightPx}
        />
        <CameraBeats
          nodes={nodes}
          beat={cameraBeat}
          centerRequest={centerRequest}
          wrapperRef={wrapperRef}
          occludedRightPx={occludedRightPx}
          lastGestureRef={lastGestureRef}
          onConsumed={onCameraBeatConsumed}
          onCenterConsumed={onCenterRequestConsumed}
        />
        {/* The zoom pill is canvas chrome for explore surfaces only — a
            fit-locked surface has no zoom business (the prop is ignored). */}
        {explore && controls && (
          <FlowControls
            className={controlsClassName}
            wrapperRef={wrapperRef}
            occludedRightPx={occludedRightPx}
          />
        )}
      </ReactFlow>
    </div>
  )
}
