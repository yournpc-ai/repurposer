"use client"

/** Independent Canvas for source assets and ordinary manual Graph nodes.
 * Composition authoring, Run progress and video delivery stay in Chat. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Clapperboard, Clock, FileText, Image as ImageIcon } from "lucide-react"

import { toAbsoluteUrl } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { GraphNode, ProjectGraph } from "@/lib/types"
import { MediaLightbox, type MediaChip, type MediaLightboxData } from "@/components/results/MediaLightbox"
import { FlowView } from "./FlowView"
import type { FlowAssetAction, FlowAssetInfo, FlowEdge, FlowNode } from "./types"

function getFlowMediaSlot(slotId: string) {
  const root = document.querySelector<HTMLElement>(`[data-flow-node-id="${CSS.escape(slotId)}"]`)
  return root?.querySelector<HTMLElement>("video, img") ?? root
}

export interface ResultsCanvasProps {
  graph: ProjectGraph | null
  visible?: boolean
  baselineReady: boolean
  baselineKey: string
  onAssetAction?: (asset: FlowAssetInfo, action: FlowAssetAction) => void
  className?: string
}

export function ResultsCanvas({
  graph,
  visible = false,
  baselineReady,
  baselineKey,
  onAssetAction,
  className,
}: ResultsCanvasProps) {
  const { t } = useTranslation()
  const { nodes, edges } = useMemo<{ nodes: FlowNode[]; edges: FlowEdge[] }>(() => {
    const nodes = (graph?.nodes ?? []).map((node: GraphNode, index) => {
      const spec = node.spec ?? {}
      const layout = node.layout ?? {}
      const frame = {
        x: Number(layout.x ?? 0),
        y: Number(layout.y ?? 0),
        w: Number(layout.w ?? 280),
        h: Number(layout.h ?? 260),
      }
      if (node.asset) {
        const asset = node.asset
        const mediaUrl = toAbsoluteUrl(asset.stream_url ?? asset.file_url ?? null)
        return {
          id: node.id,
          kind: node.type,
          spec,
          label: t(`generationOverlay.assetTypes.${asset.type ?? spec.asset_type ?? ""}`, {
            defaultValue: String(asset.type ?? spec.asset_type ?? "asset"),
          }),
          detail: asset.title ?? spec.title ?? undefined,
          asset: {
            id: asset.id,
            type: asset.type,
            title: asset.title,
            file_url: asset.file_url,
            stream_url: asset.stream_url,
            duration_seconds: asset.duration_seconds,
            width: asset.width,
            height: asset.height,
            project_id: asset.project_id ?? null,
            processing_status: asset.processing_status ?? null,
            processing_stage: asset.processing_stage ?? null,
          },
          thumbUrl: asset.type === "image" ? mediaUrl : null,
          videoUrl: asset.type === "video" ? mediaUrl : null,
          frame,
          order: index,
        }
      }
      return {
        id: node.id,
        kind: node.type,
        label: spec.summary ?? t(`results.canvas.nodeType.${node.type}`, { defaultValue: node.type }),
        detail: spec.title ?? undefined,
        status: node.state,
        spec,
        frame,
        order: index,
      }
    })
    const edges = (graph?.edges ?? []).map((edge) => ({
      from: edge.from_node,
      to: edge.to_node,
      edgeType: edge.edge_type,
      lineage: edge.from_port === "out:lineage" || undefined,
    }))
    return { nodes, edges }
  }, [graph, t])

  const seenIdsRef = useRef<Set<string> | null>(null)
  const baselinedKeyRef = useRef<string | null>(null)
  const viewportPreserveRef = useRef<{ x: number; y: number; zoom: number } | null>(null)
  const previousViewportKey = useRef(baselineKey)
  if (previousViewportKey.current !== baselineKey) {
    previousViewportKey.current = baselineKey
    viewportPreserveRef.current = null
  }
  const bornIds = useMemo(() => {
    if (!baselineReady || baselinedKeyRef.current !== baselineKey) return undefined
    const seen = seenIdsRef.current ?? new Set<string>()
    const fresh = nodes.filter((node) => !seen.has(node.id))
    return fresh.length > 0 ? new Set(fresh.map((node) => node.id)) : undefined
  }, [nodes, baselineReady, baselineKey])
  useEffect(() => {
    if (!baselineReady) return
    baselinedKeyRef.current = baselineKey
    seenIdsRef.current = new Set(nodes.map((node) => node.id))
  }, [nodes, baselineReady, baselineKey])

  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])
  const [lightbox, setLightbox] = useState<MediaLightboxData | null>(null)
  const handleExpandMedia = useCallback((nodeId: string) => {
    const node = nodeById.get(nodeId)
    const asset = node?.asset
    if (!node || !asset) return
    const url = node.videoUrl ?? node.thumbUrl ?? null
    if (!url) return
    const chips: MediaChip[] = []
    if (node.detail) {
      chips.push({
        Icon: asset.type === "video" ? Clapperboard : asset.type === "image" ? ImageIcon : FileText,
        label: node.detail,
      })
    }
    if (asset.duration_seconds) chips.push({ Icon: Clock, label: `${asset.duration_seconds}s` })
    setLightbox({
      id: asset.id,
      slotId: node.id,
      kind: node.videoUrl ? "video" : "image",
      url,
      aspect: asset.width && asset.height ? asset.width / asset.height : null,
      title: node.detail ?? node.label,
      createdAt: asset.created_at ?? null,
      chips,
      downloadName: node.detail ?? node.label,
    })
  }, [nodeById])
  const handleSelect = useCallback((nodeId: string) => {
    if (nodeById.get(nodeId)?.asset) handleExpandMedia(nodeId)
  }, [handleExpandMedia, nodeById])

  return (
    <div className={cn("relative", className)}>
      <FlowView
        nodes={nodes}
        edges={edges}
        navigation="explore"
        controls
        settleKey={baselineReady && visible ? baselineKey : null}
        bornIds={bornIds}
        dots
        className="h-full"
        onExpandMedia={handleExpandMedia}
        onSelect={handleSelect}
        onAssetAction={onAssetAction}
        viewportPreserveRef={viewportPreserveRef}
      />
      <MediaLightbox
        data={lightbox}
        getSlot={getFlowMediaSlot}
        onOpenChange={(open) => { if (!open) setLightbox(null) }}
      />
    </div>
  )
}
