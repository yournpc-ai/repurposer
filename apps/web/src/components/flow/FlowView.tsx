"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Background,
  BackgroundVariant,
  getNodesBounds,
  getViewportForBounds,
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

/** Fit + center, computed MANUALLY (getNodesBounds + getViewportForBounds +
 * setViewport) — xyflow's own fitView prop raced node measurement and landed
 * the graph top-hugged on bounded surfaces (2026-08-09). Runs: on mount
 * (double rAF, after paint + measurement), on growth (animated), and on
 * surface resize (ResizeObserver; fit-locked surfaces only — explore
 * surfaces keep the user's own viewport). */
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
      if (!el) return
      const nodes = rf.getNodes()
      if (nodes.length === 0) return
      const width = el.clientWidth
      const height = el.clientHeight
      if (!width || !height) return
      const viewport = getViewportForBounds(
        getNodesBounds(nodes),
        width,
        height,
        0.4,
        1.5,
        0.15,
      )
      rf.setViewport(viewport, { duration })
    },
    [rf, wrapperRef],
  )

  useEffect(() => {
    const first = prevCountRef.current === null
    prevCountRef.current = count
    const raf = requestAnimationFrame(() =>
      requestAnimationFrame(() => fit(first ? 0 : 300)),
    )
    return () => cancelAnimationFrame(raf)
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
        minZoom={0.4}
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
