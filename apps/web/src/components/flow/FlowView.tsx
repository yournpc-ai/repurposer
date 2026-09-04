"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Background,
  BackgroundVariant,
  Panel,
  ReactFlow,
  useReactFlow,
  useStore,
  ViewportPortal,
} from "@xyflow/react"

import { cn } from "@/lib/utils"

import "@xyflow/react/dist/style.css"
import "./flow.css"

import { FlowEdge, type FlowEdgeType } from "./FlowEdge"
import { FlowNodeCard, type FlowCardNode } from "./FlowNodeCard"
import { BIRTH_STAGGER_MS, flowNodeSize, layoutFlow } from "./layout"
import type { FlowGroup, FlowViewProps } from "./types"

const nodeTypes = { flowCard: FlowNodeCard }
const edgeTypes = { flow: FlowEdge }

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

/** Fit + center via the framework's own `fitView` (xyflow's recommended
 * centered-with-padding viewport, FIT_VIEW_OPTIONS above).
 * Runs: on mount (double rAF, after paint + measurement), on growth
 * (animated), and on surface resize (ResizeObserver; fit-locked surfaces
 * only — explore surfaces keep the user's own viewport). */
function ViewportController({
  count,
  wrapperRef,
  navigation,
}: {
  count: number
  wrapperRef: React.RefObject<HTMLDivElement | null>
  navigation: "fit" | "explore"
}) {
  const rf = useReactFlow()
  const prevCountRef = useRef<number | null>(null)

  const fit = useCallback(
    (duration: number) => {
      const el = wrapperRef.current
      if (!el || !el.clientWidth || !el.clientHeight) return
      if (rf.getNodes().length === 0) return
      void rf.fitView({ ...FIT_VIEW_OPTIONS, duration })
    },
    [rf, wrapperRef],
  )

  useEffect(() => {
    const prev = prevCountRef.current
    prevCountRef.current = count
    const firstEver = prev === null
    // Explore surfaces keep the user's own viewport on GROWTH (2026-08-19
    // 二轮 R2): the spine toggle and refinement new-arrivals must not yank
    // a hand-set pan/zoom. But empty→non-empty is NOT growth: the project
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
  }, [count, fit, navigation])

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
 * page's home-inherited top-right cluster; 2026-09-05 比例尺瘦身：只读百
 * 分比——± 步进与 fit icon 全退役（用户拍板），框内就一个数字，点击
 * 仍是 fit to view。Rides the same dock-surface recipe as the dock and
 * the 任务书 node. Explore surfaces only (the parent gates it). Subscribes
 * to zoom ONLY (transform[2]) — useViewport's {x,y,zoom} shallow compare
 * would re-render the pill on every pan frame. */
function FlowControls() {
  const { t } = useTranslation()
  const rf = useReactFlow()
  const zoom = useStore((s) => s.transform[2])
  const fit = () => void rf.fitView({ ...FIT_VIEW_OPTIONS, duration: 300 })
  return (
    <Panel position="top-right" className="!m-3 md:!m-4">
      <button
        type="button"
        aria-label={t("results.canvas.zoomFit")}
        title={t("results.canvas.zoomFit")}
        onClick={fit}
        className="dock-surface flex h-9 items-center rounded-md px-3 text-muted-foreground text-xs tabular-nums ring-foreground/10 ring-1 transition-colors hover:bg-accent hover:text-foreground"
      >
        {Math.round(zoom * 100)}%
      </button>
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
  onAssetAction,
  onExpandMedia,
  onRevise,
  onPaneClick,
  navigation = "fit",
  controls = false,
  bornIds,
  groups = [],
  dots = false,
  className,
}: FlowViewProps) {
  // React Flow measures the DOM — client-only mount (SSR renders the
  // placeholder frame; hydration swaps in the real graph).
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const wrapperRef = useRef<HTMLDivElement>(null)

  const { rfNodes, rfEdges, layout, sizes, bornRanks } = useMemo(() => {
    const layout = layoutFlow(nodes, edges)
    const sizes = new Map(nodes.map((n) => [n.id, flowNodeSize(n)]))
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
    const rfNodes: FlowCardNode[] = nodes.map((n) => ({
      id: n.id,
      type: "flowCard",
      position: layout.positions.get(n.id) ?? { x: 0, y: 0 },
      // Explicit dims keep the DOM in lockstep with the layout math (fixed
      // sizes = pure-math layout, zero measurement).
      style: flowNodeSize(n),
      data: {
        node: n,
        bornIndex: bornRanks.get(n.id),
        selected: n.id === selectedId,
        onOutputAction,
        onAssetAction,
        onExpandMedia,
        onRevise,
      },
      draggable: false,
      connectable: false,
    }))
    const rfEdges: FlowEdgeType[] = edges.map((e) => {
      // An edge draws once a born endpoint enters (delay = the later birth).
      const from = bornRanks.get(e.from) ?? -1
      const to = bornRanks.get(e.to) ?? -1
      const bornAt = Math.max(from, to)
      return {
        id: `${e.from}->${e.to}`,
        source: e.from,
        target: e.to,
        type: "flow",
        data: {
          semantic: e.semantic,
          drawDelay: bornAt >= 0 ? bornAt * BIRTH_STAGGER_MS + 240 : null,
          active:
            nodes.find((n) => n.id === e.to)?.status === "running" ||
            nodes.find((n) => n.id === e.from)?.status === "running",
        },
        selectable: false,
        focusable: false,
      }
    })
    return { rfNodes, rfEdges, layout, sizes, bornRanks }
  }, [nodes, edges, selectedId, bornIds, onOutputAction, onAssetAction, onExpandMedia, onRevise])

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
        <ViewportController
          count={nodes.length}
          wrapperRef={wrapperRef}
          navigation={navigation}
        />
        {/* The zoom pill is canvas chrome for explore surfaces only — a
            fit-locked surface has no zoom business (the prop is ignored). */}
        {explore && controls && <FlowControls />}
      </ReactFlow>
    </div>
  )
}
