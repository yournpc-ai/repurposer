"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Maximize, Minus, Plus } from "lucide-react"
import {
  Background,
  BackgroundVariant,
  Panel,
  ReactFlow,
  useReactFlow,
  useViewport,
  ViewportPortal,
} from "@xyflow/react"

import { cn } from "@/lib/utils"

import "@xyflow/react/dist/style.css"
import "./flow.css"

import { FlowEdge, type FlowEdgeType } from "./FlowEdge"
import { FlowNodeCard, type FlowCardNode } from "./FlowNodeCard"
import { flowNodeSize, layoutFlow } from "./layout"
import type { FlowGroup, FlowViewProps } from "./types"

const nodeTypes = { flowCard: FlowNodeCard }
const edgeTypes = { flow: FlowEdge }

/** Fit + center via the framework's own `fitView` (xyflow's recommended
 * centered-with-padding viewport). Two hard-won parameter rules:
 * 1. minZoom must go LOW (0.15) — a wide recipe graph needs ~0.36 on the
 *    overlay canvas; when the floor clamps above the needed zoom,
 *    getViewportForBounds still centers, so the graph overflows BOTH edges
 *    (2026-08-10 bug: right column cut off).
 * 2. maxZoom caps at 1 on fit surfaces — a small graph must not upscale
 *    into giant cards.
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
      // padding 0.2 ≈ 9% per side (xyflow's 1/(1+p) formula) — clears the
      // overlay's floating tab bar (top-5 + h-9 ≈ 56px).
      void rf.fitView({ minZoom: 0.15, maxZoom: 1, padding: 0.2, duration })
    },
    [rf, wrapperRef],
  )

  useEffect(() => {
    const first = prevCountRef.current === null
    prevCountRef.current = count
    // Double rAF (after paint + measurement); BOTH frames are tracked so a
    // mid-flight unmount never leaves a dangling callback.
    let inner = 0
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => fit(first ? 0 : 300))
    })
    return () => {
      cancelAnimationFrame(outer)
      cancelAnimationFrame(inner)
    }
  }, [count, fit])

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
  choreograph,
}: {
  groups: FlowGroup[]
  layout: ReturnType<typeof layoutFlow>
  sizes: Map<string, { width: number; height: number }>
  choreograph: boolean
}) {
  return (
    <ViewportPortal>
      {groups.map((group) => {
        const members = group.nodeIds.flatMap((id) => {
          const pos = layout.positions.get(id)
          const size = sizes.get(id)
          return pos && size ? [{ pos, size, born: layout.revealOrder.get(id) ?? 0 }] : []
        })
        if (members.length === 0) return null
        const minX = Math.min(...members.map((m) => m.pos.x)) - GROUP_PAD
        const minY = Math.min(...members.map((m) => m.pos.y)) - GROUP_PAD
        const maxX =
          Math.max(...members.map((m) => m.pos.x + m.size.width)) + GROUP_PAD
        const maxY =
          Math.max(...members.map((m) => m.pos.y + m.size.height)) + GROUP_PAD
        return (
          <div
            key={group.id}
            aria-hidden
            className={cn(
              "absolute rounded-3xl ring-foreground/10 ring-1",
              choreograph && "flow-node-born",
            )}
            style={{
              left: minX,
              top: minY,
              width: maxX - minX,
              height: maxY - minY,
              zIndex: -1,
              ...(choreograph
                ? { animationDelay: `${Math.max(...members.map((m) => m.born)) * 120}ms` }
                : {}),
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
 * page's home-inherited top-right cluster): one frosted pill, zoom out /
 * live % (click = fit to view) / zoom in. Rides the same dock-surface
 * recipe as the dock and the 任务书 node — parked on the same dot grid.
 * Explore surfaces only (the parent gates it). */
function FlowControls() {
  const { t } = useTranslation()
  const rf = useReactFlow()
  const { zoom } = useViewport()
  const fit = () =>
    void rf.fitView({ minZoom: 0.15, maxZoom: 1, padding: 0.2, duration: 300 })
  const btn =
    "flex h-9 w-9 items-center justify-center text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
  return (
    <Panel position="top-right" className="!m-3 md:!m-4">
      <div className="dock-surface flex items-center rounded-md ring-foreground/10 ring-1">
        <button
          type="button"
          aria-label={t("results.canvas.zoomOut")}
          className={btn}
          onClick={() => void rf.zoomOut({ duration: 200 })}
        >
          <Minus className="h-4 w-4" />
        </button>
        <button
          type="button"
          aria-label={t("results.canvas.zoomFit")}
          title={t("results.canvas.zoomFit")}
          className="flex h-9 w-12 items-center justify-center gap-0.5 text-muted-foreground text-xs tabular-nums transition-colors hover:bg-accent hover:text-foreground"
          onClick={fit}
        >
          <Maximize className="h-3 w-3" />
          {Math.round(zoom * 100)}%
        </button>
        <button
          type="button"
          aria-label={t("results.canvas.zoomIn")}
          className={btn}
          onClick={() => void rf.zoomIn({ duration: 200 })}
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
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
  onPaneClick,
  navigation = "fit",
  controls = false,
  choreograph = false,
  groups = [],
  dots = false,
  className,
}: FlowViewProps) {
  // React Flow measures the DOM — client-only mount (SSR renders the
  // placeholder frame; hydration swaps in the real graph).
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const wrapperRef = useRef<HTMLDivElement>(null)

  const { rfNodes, rfEdges, layout, sizes } = useMemo(() => {
    const layout = layoutFlow(nodes, edges)
    const sizes = new Map(nodes.map((n) => [n.id, flowNodeSize(n)]))
    const rfNodes: FlowCardNode[] = nodes.map((n) => ({
      id: n.id,
      type: "flowCard",
      position: layout.positions.get(n.id) ?? { x: 0, y: 0 },
      // Explicit dims keep the DOM in lockstep with the layout math (fixed
      // sizes = pure-math layout, zero measurement).
      style: flowNodeSize(n),
      data: {
        node: n,
        bornIndex: choreograph ? layout.revealOrder.get(n.id) : undefined,
        selected: n.id === selectedId,
        onOutputAction,
        onAssetAction,
        onExpandMedia,
      },
      draggable: false,
      connectable: false,
    }))
    const rfEdges: FlowEdgeType[] = edges.map((e) => {
      const from = layout.revealOrder.get(e.from) ?? 0
      const to = layout.revealOrder.get(e.to) ?? 0
      return {
        id: `${e.from}->${e.to}`,
        source: e.from,
        target: e.to,
        type: "flow",
        data: {
          semantic: e.semantic,
          // An edge draws once both endpoints have appeared.
          drawDelay: choreograph ? Math.max(from, to) * 120 + 240 : null,
          active:
            nodes.find((n) => n.id === e.to)?.status === "running" ||
            nodes.find((n) => n.id === e.from)?.status === "running",
        },
        selectable: false,
        focusable: false,
      }
    })
    return { rfNodes, rfEdges, layout, sizes }
  }, [nodes, edges, selectedId, choreograph, onOutputAction, onAssetAction, onExpandMedia])

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
          <Background
            variant={BackgroundVariant.Dots}
            gap={28}
            size={1.5}
            color="var(--muted-foreground)"
            className="opacity-30 dark:opacity-40"
          />
        )}
        {groups.length > 0 && (
          <GroupFrames
            groups={groups}
            layout={layout}
            sizes={sizes}
            choreograph={choreograph}
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
