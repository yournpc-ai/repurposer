"use client"

/** ResultsCanvas (ADR-041 D1) — the project page's terminal-state default
 * center: the current run's real topology + latest products, rendered by
 * the shared FlowView substrate (prohibition #9 — no hand-drawn edges or
 * layout here). Navigation is open (pan/zoom, D7); editing gestures are
 * structurally absent in the substrate. Product nodes are cards (D5): the
 * surface owns their actions — click focuses (焦点注入, D8; a clip also
 * opens its detail modal), the action bar carries info + download / delete,
 * and node business (publish / open / focus) lives in the bar's ⋯ menu. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Clapperboard,
  Clock,
  FileText,
  Image as ImageIcon,
  Languages,
  RectangleHorizontal,
  RectangleVertical,
  Scissors,
  Square,
  Star,
} from "lucide-react"

import { toAbsoluteUrl } from "@/lib/api"
import type { Output, PlaceholderRow, WorkflowStep } from "@/lib/types"
import { formatDuration } from "@/lib/utils"
import {
  MediaLightbox,
  type MediaChip,
  type MediaLightboxData,
} from "@/components/results/MediaLightbox"

import { FlowView } from "./FlowView"
import { PRODUCT_TYPE_ICON } from "./FlowNodeCard"
import { runFlowGraph, SPINE_NODE_ID, type RunFlowAsset } from "./runFlow"
import type { FlowAssetAction, FlowAssetInfo, FlowOutputAction } from "./types"

export interface ResultsCanvasProps {
  assets: RunFlowAsset[]
  steps: WorkflowStep[]
  outputs: Output[]
  /** The live run's server-projected placeholder roster (ADR-051 B): slots
   * render as quiet placeholder cards at their final position; landed
   * outputs fill them in place. Empty for terminal/absent runs. */
  placeholders?: PlaceholderRow[]
  /** The run is non-terminal (pending / running / waiting_human) — a
   * promised placeholder slot reads alive (wipe + edge packet) even before
   * its producing step starts (2026-09-02 用户拍板: waiting ⊆ running). */
  runAlive?: boolean
  /** The run's prompt — displayed in every product node's interaction area
   * (read-only; editing happens in the dock). */
  prompt?: string | null
  /** Birth-choreography baseline contract (ADR-036 补记 3): the surface
   * flips `baselineReady` only when its initial fetches have settled (they
   * resolve in any order) and the data belongs to `baselineKey`; the first
   * ready frame under a key is the baseline and animates NOTHING (refresh /
   * reconnect / cross-project navigation render instantly — 铁律), every
   * later growth births. */
  baselineReady: boolean
  baselineKey: string
  /** The node carrying the results tour's data-tour anchors. */
  tourOutputId?: string | null
  /** A product node was clicked — the surface sets the dock focus and opens
   * the detail modal (clips). */
  onOutputClick?: (output: Output) => void
  /** A product node's action-bar action (download / delete in the bar;
   * publish / open / focus ride the ⋯ menu — all one channel). */
  onOutputAction?: (output: Output, action: FlowOutputAction) => void
  /** Hover prompt 框 send (ADR-051 F): the surface rides the revision ask
   * into the dock's chat channel with the product pinned as focus. */
  onRevise?: (output: Output, text: string) => void
  /** An asset node's toolbar action (download / delete / reprocess) — the
   * surface owns them; absent = asset nodes render no toolbar. */
  onAssetAction?: (asset: FlowAssetInfo, action: FlowAssetAction) => void
  /** A process step node was clicked (the spine expanded) — the surface
   * inserts the step's @workflow_step mention into the dock (D8). */
  onStepClick?: (stepId: string, label: string) => void
  /** The dock-focused product id — its node carries the selected ring. */
  focusedOutputId?: string | null
  /** Pane-only click (node clicks excluded) — back to neutral: the surface
   * collapses the dock's history and clears the focus (D4/D8). */
  onPaneClick?: () => void
  className?: string
}

export function ResultsCanvas({
  assets,
  steps,
  outputs,
  placeholders,
  runAlive = false,
  prompt = null,
  baselineReady,
  baselineKey,
  tourOutputId,
  onOutputClick,
  onOutputAction,
  onRevise,
  onAssetAction,
  onStepClick,
  focusedOutputId = null,
  onPaneClick,
  className,
}: ResultsCanvasProps) {
  const { t } = useTranslation()
  // 过程脊 expand/collapse is view state (D6 — the graph data is always
  // full; only the surface's density flips).
  const [spineExpanded, setSpineExpanded] = useState(false)
  const { nodes, edges } = useMemo(
    () => runFlowGraph({ assets, steps, outputs, placeholders, runAlive, prompt, tourOutputId, spineExpanded }, t),
    [assets, steps, outputs, placeholders, runAlive, prompt, tourOutputId, spineExpanded, t]
  )

  // ── Birth choreography (ADR-036 补记 3, growth-driven since ADR-051) ────
  // The reveal is every graph GROWTH witnessed after the baseline: nodes
  // absent from the last committed frame birth in, staggered by compile
  // order. The BASELINE is the first frame with `baselineReady` under
  // `baselineKey` — the surface gates it on its initial fetches settling
  // (they resolve in any order; an early partial frame must not become the
  // baseline, or the rest of the graph "births" on a plain refresh — 铁律).
  // Cards latch their own born class (FlowNodeCard), so a fast follow-up
  // frame dropping these ids never cuts a keyframe mid-flight.
  const seenIdsRef = useRef<Set<string> | null>(null)
  const baselinedKeyRef = useRef<string | null>(null)
  const prevSpineExpandedRef = useRef(spineExpanded)
  const bornIds = useMemo(() => {
    if (!baselineReady) return undefined
    if (baselinedKeyRef.current !== baselineKey) return undefined
    // A spine density flip is not growth — its step pills must never birth.
    if (spineExpanded !== prevSpineExpandedRef.current) return undefined
    const seen = seenIdsRef.current ?? new Set<string>()
    const fresh = nodes.filter((n) => !seen.has(n.id))
    return fresh.length > 0 ? new Set(fresh.map((n) => n.id)) : undefined
  }, [nodes, spineExpanded, baselineReady, baselineKey])
  useEffect(() => {
    if (!baselineReady) return
    baselinedKeyRef.current = baselineKey
    seenIdsRef.current = new Set(nodes.map((n) => n.id))
    prevSpineExpandedRef.current = spineExpanded
  }, [nodes, spineExpanded, baselineReady, baselineKey])
  const outputById = useMemo(
    () => new Map(outputs.map((o) => [`output:${o.id}`, o])),
    [outputs]
  )
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const assetByNodeId = useMemo(
    () => new Map(assets.map((a) => [`asset:${a.id}`, a])),
    [assets]
  )

  // ── Media lightbox (2026-08-15) ──────────────────────────────────────
  // The expand affordance / asset media click: one frosted dialog — left
  // the scrollable info column (timestamp, full prompt, derived-attribute
  // chips), right the media. Product chips are product facts only (never a
  // model name, prohibition #12).
  const [lightbox, setLightbox] = useState<MediaLightboxData | null>(null)

  // Handlers are useCallback-stable (2026-08-19 二轮 R5): FlowView's
  // rfNodes/rfEdges memo keys on them — inline closures rebuilt the whole
  // graph on every unrelated re-render (SSE ticks, polling, focus changes).
  const handleExpandMedia = useCallback((nodeId: string, outputId?: string) => {
    const node = nodeById.get(nodeId)
    if (!node) return
    const downloadName = (url: string, base: string) => {
      const ext = url.split("?")[0].split(".").pop() ?? ""
      return `${base || "media"}.${ext.length > 0 && ext.length <= 4 ? ext : "mp4"}`
    }

    // The version pager's flipped display (ADR-051 F2): the lightbox follows
    // the SHOWN member, not the node's own row.
    const output =
      (outputId ? outputById.get(`output:${outputId}`) : undefined) ?? node.output
    if (output) {
      const url = toAbsoluteUrl(output.files.video ?? output.files.image ?? null)
      if (!url) return
      const chips: MediaChip[] = [
        {
          Icon: PRODUCT_TYPE_ICON[output.type] ?? Clapperboard,
          label: node.label,
        },
      ]
      if (node.detail) chips.push({ Icon: Languages, label: node.detail })
      const aspect = (output.render_spec as { aspect?: string } | null)?.aspect
      // "original" (whole-source, 2026-08-17) is not a fixed tier — the real
      // pixels are unknown until the media loads, so no shape chip.
      if (aspect === "1:1" || aspect === "16:9" || aspect === "9:16") {
        chips.push({
          Icon:
            aspect === "1:1"
              ? Square
              : aspect === "16:9"
                ? RectangleHorizontal
                : RectangleVertical,
          label: aspect,
        })
      }
      const duration = output.payload.duration
      if (output.type === "clip" && duration) {
        chips.push({ Icon: Clock, label: `${duration}s` })
      }
      const start = output.source_ref?.start_seconds
      const end = output.source_ref?.end_seconds
      if (start != null && end != null) {
        chips.push({
          Icon: Scissors,
          label: `${formatDuration(start)}–${formatDuration(end)}`,
        })
      }
      if (typeof output.score?.value === "number") {
        chips.push({
          Icon: Star,
          label: `${output.score.value}`,
          title: output.score.reason ?? undefined,
        })
      }
      const title =
        output.publishing.title || output.payload.hook || node.label
      setLightbox({
        kind: output.files.video ? "video" : "image",
        url,
        // Poster derives from the SHOWN output (the node's own thumbUrl only
        // describes its own row — the pager may have flipped the display).
        poster: output.files.video
          ? toAbsoluteUrl(output.files.image ?? output.publishing.cover_image_url ?? null)
          : null,
        title,
        createdAt: output.created_at,
        prompt: node.prompt,
        chips,
        // 模型事实 (ADR-051 H): the shown member's own server-stamped facts —
        // display-only on this detail surface (禁令2 禁选择器).
        modelFacts: output.model_facts ?? null,
        downloadName: downloadName(url, title),
      })
      return
    }

    const asset = assetByNodeId.get(nodeId)
    if (asset) {
      const url = node.videoUrl ?? node.thumbUrl ?? null
      if (!url) return
      const chips: MediaChip[] = []
      if (node.detail) {
        chips.push({
          Icon:
            asset.type === "video"
              ? Clapperboard
              : asset.type === "image"
                ? ImageIcon
                : FileText,
          label: node.detail,
        })
      }
      if (asset.duration_seconds) {
        chips.push({ Icon: Clock, label: `${asset.duration_seconds}s` })
      }
      setLightbox({
        kind: node.videoUrl ? "video" : "image",
        url,
        // The caption carries the type name now — the filename (detail) is
        // the lightbox's title.
        title: node.detail ?? node.label,
        createdAt: asset.created_at ?? null,
        chips,
        downloadName: node.detail ?? node.label,
      })
    }
  }, [nodeById, assetByNodeId, outputById])

  const handleSelect = useCallback(
    (id: string) => {
      // The spine group node toggles in place; a step node points the
      // dock at it (@workflow_step); a product node focuses / details.
      if (id === SPINE_NODE_ID) {
        setSpineExpanded((v) => !v)
        return
      }
      const output = outputById.get(id)
      if (output) {
        onOutputClick?.(output)
        return
      }
      if (id.startsWith("asset:")) {
        // Source media nodes have no dock business — a click IS the
        // expand gesture (the lightbox; non-media assets no-op inside).
        handleExpandMedia(id)
        return
      }
      if (id.startsWith("artifact:")) {
        // 工件卡 = 可干预的产出物 (D6 修订): clicking points the dock at
        // the group's representative step (@workflow_step, D8).
        const node = nodeById.get(id)
        if (node?.anchorStepId) onStepClick?.(node.anchorStepId, node.label)
        return
      }
      if (id.startsWith("step:")) {
        const node = nodeById.get(id)
        if (node) onStepClick?.(id.slice(5), node.label)
      }
    },
    [outputById, onOutputClick, onStepClick, nodeById, handleExpandMedia],
  )

  const handleOutputAction = useCallback(
    (id: string, action: FlowOutputAction) => {
      const output = outputById.get(`output:${id}`)
      if (output) onOutputAction?.(output, action)
    },
    [outputById, onOutputAction],
  )

  // Hover prompt 框 send (ADR-051 F): id → row, then up to the surface —
  // the dock's chat channel is the only revision path (prohibition #1).
  const handleRevise = useCallback(
    (id: string, text: string) => {
      const output = outputById.get(`output:${id}`)
      if (output) onRevise?.(output, text)
    },
    [outputById, onRevise],
  )

  return (
    <div className={className}>
      <FlowView
        nodes={nodes}
        edges={edges}
        navigation="explore"
        controls
        bornIds={bornIds}
        dots
        className="h-full"
        selectedId={focusedOutputId ? `output:${focusedOutputId}` : null}
        onPaneClick={onPaneClick}
        onExpandMedia={handleExpandMedia}
        onSelect={handleSelect}
        onOutputAction={handleOutputAction}
        onRevise={handleRevise}
        onAssetAction={onAssetAction}
      />
      <MediaLightbox
        data={lightbox}
        onOpenChange={(open) => {
          if (!open) setLightbox(null)
        }}
      />
    </div>
  )
}
