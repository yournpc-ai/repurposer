"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  useReactFlow,
} from "@xyflow/react"

import { cn } from "@/lib/utils"

import "@xyflow/react/dist/style.css"
import "./flow.css"

import { FlowEdge, type FlowEdgeType } from "./FlowEdge"
import { FlowNodeCard, type FlowCardNode } from "./FlowNodeCard"
import { FLOW_NODE_SIZE, layoutFlow } from "./layout"
import type { FlowViewProps } from "./types"

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

/** FlowView (ADR-036): the shared read-only graph substrate. Editing gestures
 * are structurally absent (nodesDraggable / nodesConnectable hard-locked);
 * zoom/pan are navigation, gated per surface (`navigation` prop). */
export function FlowView({
  nodes,
  edges,
  selectedId = null,
  onSelect,
  navigation = "fit",
  choreograph = false,
  dots = false,
  className,
}: FlowViewProps) {
  // React Flow measures the DOM — client-only mount (SSR renders the
  // placeholder frame; hydration swaps in the real graph).
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const wrapperRef = useRef<HTMLDivElement>(null)

  const { rfNodes, rfEdges } = useMemo(() => {
    const layout = layoutFlow(nodes, edges)
    const rfNodes: FlowCardNode[] = nodes.map((n) => ({
      id: n.id,
      type: "flowCard",
      position: layout.positions.get(n.id) ?? { x: 0, y: 0 },
      // Explicit dims keep the DOM in lockstep with the layout math (fixed
      // sizes = pure-math layout, zero measurement).
      style: {
        width: FLOW_NODE_SIZE[n.kind].width,
        height: FLOW_NODE_SIZE[n.kind].height,
      },
      data: {
        node: n,
        bornIndex: choreograph ? layout.revealOrder.get(n.id) : undefined,
        selected: n.id === selectedId,
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
    return { rfNodes, rfEdges }
  }, [nodes, edges, selectedId, choreograph])

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
        <ViewportController
          count={nodes.length}
          wrapperRef={wrapperRef}
          navigation={navigation}
        />
      </ReactFlow>
    </div>
  )
}
