"use client"

/** ResultsCanvas (ADR-041 D1; ADR-057 K3) — the project page's center: the
 * persistent graph read DIRECTLY (`GET /projects/{id}/graph` — node id =
 * graph node id, edge = graph edge, state = the row's state; zero
 * projection, the display model IS the domain model). The mapping below is
 * the render boundary only: field pass-through + i18n labels — no topology
 * derivation, no hidden-step resolution (the retired projection's whole
 * job). Navigation is open (pan/zoom, D7); editing gestures are
 * structurally absent in the substrate. Product nodes are cards: the
 * surface owns their actions — click focuses (焦点注入, D8) and summons the
 * OutputInspector (the FLORA-parity dossier under the zoom pill), the
 * factsbar carries info + download / delete, and node business (publish /
 * open / focus) lives in the bar's ⋯ menu. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ViewportPortal } from "@xyflow/react"
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

import { apiFetch, toAbsoluteUrl } from "@/lib/api"
import { cn, formatDuration } from "@/lib/utils"
import type { GraphNode, Output, ProjectGraph, WorkflowStep } from "@/lib/types"
import { Button } from "@/components/ui/button"
import {
  MediaLightbox,
  type MediaChip,
  type MediaLightboxData,
} from "@/components/results/MediaLightbox"
import { OutputInspector } from "@/components/results/OutputInspector"

import { FlowView } from "./FlowView"
import { PRODUCT_TYPE_ICON } from "./FlowNodeCard"
import type {
  FlowAssetAction,
  FlowAssetInfo,
  FlowEdge,
  FlowNode,
  FlowOutputAction,
} from "./types"

export interface ResultsCanvasProps {
  /** The graph's one read frame (ADR-057). Null = not yet loaded — the
   * canvas stays empty behind the page's gate. */
  graph: ProjectGraph | null
  /** The canvas is VISIBLE (the page's graph-world gate: first run OR a
   * docked book's draft graph, K5). The settle key (initial framing) joins
   * this with baselineReady: frame only when the visible, settled content
   * is present, never on a partial fetch frame (2026-09-06). */
  visible?: boolean
  /** Birth-choreography baseline contract (ADR-036 补记 3): the surface
   * flips `baselineReady` only when its initial fetches have settled (they
   * resolve in any order) and the data belongs to `baselineKey`; the first
   * ready frame under a key is the baseline and animates NOTHING (refresh /
   * reconnect / cross-project navigation render instantly — 铁律), every
   * later growth births. */
  baselineReady: boolean
  baselineKey: string
  /** The output carrying the results tour's data-tour anchors (first ready
   * product, chosen by the surface). */
  tourOutputId?: string | null
  /** The dossier's producing-step lookup (latest run's steps — /results
   * payload, execution-ledger facts only). */
  steps?: WorkflowStep[]
  /** A product node was clicked — the surface sets the dock focus and opens
   * the detail modal (clips). */
  onOutputClick?: (output: Output) => void
  /** A product node's factsbar action (download / delete in the bar;
   * publish / open / focus ride the ⋯ menu — all one channel). */
  onOutputAction?: (output: Output, action: FlowOutputAction) => void
  /** The card-face prompt direct edit's deterministic dispatch (ADR-058):
   * the pricing confirmation's Start calls it with the node id + the user's
   * verbatim program — the surface posts the graph revision (code-built
   * edit_prompt + run) and refetches. NOT a chat turn: zero messages in
   * the dock — the node's own state cycle is the feedback. Resolves true
   * when the run started. */
  onNodeRevise?: (nodeId: string, text: string) => Promise<boolean>
  /** The draft-confirm card's Start (ADR-057 K5 — 确认 = 节点锚定): the
   * surface rides it to the dock's one start path (the imperative
   * handle — the task_book question's start answer; same guards, same
   * grey-row failure surface). */
  onDraftConfirm?: () => void
  /** An asset node's factsbar action (download / delete / reprocess) — the
   * surface owns them; absent = asset nodes render no bar. */
  onAssetAction?: (asset: FlowAssetInfo, action: FlowAssetAction) => void
  /** The canvas-selected product id — its node carries the selected ring
   * (canvas SELECTION, not a chat focus — ADR-058). */
  selectedOutputId?: string | null
  /** Pane-only click (node clicks excluded) — back to neutral: the surface
   * collapses the dock's history and clears the selection. */
  onPaneClick?: () => void
  /** Extra classes for the top-right canvas chrome (2026-09-06): the zoom
   * pill's Panel AND the OutputInspector share one corner and one
   * docked-panel avoidance — the page offsets both clear of the open chat
   * panel so nothing sits under the frost. */
  controlsClassName?: string
  className?: string
}

export function ResultsCanvas({
  graph,
  visible = false,
  baselineReady,
  baselineKey,
  tourOutputId,
  steps,
  onOutputClick,
  onOutputAction,
  onNodeRevise,
  onDraftConfirm,
  onAssetAction,
  selectedOutputId = null,
  onPaneClick,
  controlsClassName,
  className,
}: ResultsCanvasProps) {
  const { t } = useTranslation()

  // ── Graph → the FlowView render contract (ADR-057 直读: field
  // pass-through + i18n labels, zero topology derivation) ────────────────
  const { nodes, edges } = useMemo<{ nodes: FlowNode[]; edges: FlowEdge[] }>(() => {
    const graphNodes = graph?.nodes ?? []
    // The batch's highest clip score (score triage — what to post first):
    // the winning product's badge accents, wherever the pager shows it.
    const topClipScore = Math.max(
      0,
      ...graphNodes.flatMap((n) =>
        (n.outputs ?? [])
          .filter((o) => o.type === "clip")
          .map((o) => (typeof o.score?.value === "number" ? o.score.value : 0)),
      ),
    )
    const nodes: FlowNode[] = graphNodes.map((n: GraphNode, i: number) => {
      const spec = n.spec ?? {}
      const layout = n.layout ?? {}
      const frame = {
        x: Number(layout.x ?? 0),
        y: Number(layout.y ?? 0),
        w: Number(layout.w ?? 280),
        h: Number(layout.h ?? 260),
      }
      if (n.kind === "asset") {
        const asset = n.asset ?? null
        const mediaUrl = toAbsoluteUrl(asset?.stream_url ?? asset?.file_url ?? null)
        return {
          id: n.id,
          kind: "asset",
          label: t(`generationOverlay.assetTypes.${asset?.type ?? spec.asset_type ?? ""}`, {
            defaultValue: String(asset?.type ?? spec.asset_type ?? "asset"),
          }),
          detail: asset?.title ?? spec.title ?? undefined,
          asset: asset
            ? {
                id: asset.id,
                type: asset.type,
                title: asset.title,
                file_url: asset.file_url,
                stream_url: asset.stream_url,
                duration_seconds: asset.duration_seconds,
              }
            : undefined,
          thumbUrl: asset?.type === "image" ? mediaUrl : null,
          videoUrl: asset?.type === "video" ? mediaUrl : null,
          frame,
          order: i,
        }
      }
      if (n.kind === "document") {
        return {
          id: n.id,
          kind: "document",
          label:
            spec.role === "task_book"
              ? t("results.canvas.taskBook")
              : spec.role === "transcript"
                ? t("results.canvas.transcript")
                : spec.role === "research_brief"
                  ? t("results.canvas.researchBrief")
                  : (spec.summary ?? t("results.canvas.document")),
          detail: spec.summary ?? undefined,
          spec,
          frame,
          order: i,
        }
      }
      // generator / processor / agent — the graph card.
      const outputs = n.outputs ?? []
      return {
        id: n.id,
        kind: n.kind,
        label: spec.summary ?? n.kind,
        status: n.state,
        spec,
        outputs,
        estimateCredits: n.estimate_credits ?? null,
        frame,
        topClipScore,
        tourTargets: !!tourOutputId && outputs.some((o) => o.id === tourOutputId),
        order: i,
      }
    })
    const edges: FlowEdge[] = (graph?.edges ?? []).map((e) => ({
      from: e.from_node,
      to: e.to_node,
      edgeType: e.edge_type,
    }))
    return { nodes, edges }
  }, [graph, tourOutputId, t])

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
  const bornIds = useMemo(() => {
    if (!baselineReady) return undefined
    if (baselinedKeyRef.current !== baselineKey) return undefined
    const seen = seenIdsRef.current ?? new Set<string>()
    const fresh = nodes.filter((n) => !seen.has(n.id))
    return fresh.length > 0 ? new Set(fresh.map((n) => n.id)) : undefined
  }, [nodes, baselineReady, baselineKey])
  useEffect(() => {
    if (!baselineReady) return
    baselinedKeyRef.current = baselineKey
    seenIdsRef.current = new Set(nodes.map((n) => n.id))
  }, [nodes, baselineReady, baselineKey])

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const outputById = useMemo(() => {
    const map = new Map<string, Output>()
    for (const n of nodes) for (const o of n.outputs ?? []) map.set(o.id, o)
    return map
  }, [nodes])
  /** output id → its node's id (focus → the selected ring's node). */
  const nodeIdByOutputId = useMemo(() => {
    const map = new Map<string, string>()
    for (const n of nodes) for (const o of n.outputs ?? []) map.set(o.id, n.id)
    return map
  }, [nodes])

  // The pager's displayed product per node (the card reports its display;
  // a node click selects what the user is LOOKING at, not a stale first).
  const displayedRef = useRef(new Map<string, string>())
  const handleDisplayChange = useCallback((nodeId: string, outputId: string) => {
    displayedRef.current.set(nodeId, outputId)
  }, [])

  // ── Output inspector (2026-09-06, FLORA node-detail parity) ─────────────
  // A product click summons its dossier, anchored under the zoom pill
  // (right-aligned — the ADR-056 canvas-chrome slot). View state owned
  // here by the canvas: selecting another product swaps in place, pane
  // click / Esc / the row vanishing (delete / refresh) closes.
  const [inspectedId, setInspectedId] = useState<string | null>(null)
  const inspectedOutput = inspectedId ? (outputById.get(inspectedId) ?? null) : null
  useEffect(() => {
    if (inspectedId && !inspectedOutput) setInspectedId(null)
  }, [inspectedId, inspectedOutput])

  // ── Media lightbox (2026-08-15) ──────────────────────────────────────
  // The expand affordance / asset media click: one frosted dialog — left
  // the scrollable info column (timestamp, full prompt, derived-attribute
  // chips), right the media. Product chips are product facts only (never a
  // model name in the chips row).
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

    // The pager's flipped display: the lightbox follows the SHOWN product,
    // not the node's first row.
    const output =
      (outputId ? outputById.get(outputId) : undefined) ??
      (node.outputs?.length
        ? outputById.get(displayedRef.current.get(nodeId) ?? "") ?? node.outputs[0]
        : undefined)
    if (output) {
      const url = toAbsoluteUrl(output.files.video ?? output.files.image ?? null)
      if (!url) return
      const chips: MediaChip[] = [
        {
          Icon: PRODUCT_TYPE_ICON[output.type] ?? Clapperboard,
          label: node.label,
        },
      ]
      if (output.language) {
        chips.push({ Icon: Languages, label: t(`languages.${output.language}`, { defaultValue: output.language }) })
      }
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
        output.publishing.title || (output.payload.hook as string | undefined) || node.label
      setLightbox({
        kind: output.files.video ? "video" : "image",
        url,
        // Poster derives from the SHOWN output.
        poster: output.files.video
          ? toAbsoluteUrl(output.files.image ?? output.publishing.cover_image_url ?? null)
          : null,
        title,
        createdAt: output.created_at,
        prompt: node.spec?.prompt ?? output.spec_prompt ?? null,
        chips,
        // 模型事实 (ADR-051 H): the shown member's own server-stamped facts —
        // display-only on this detail surface (禁令2 禁选择器).
        modelFacts: output.model_facts ?? null,
        downloadName: downloadName(url, title),
      })
      return
    }

    const asset = node.asset
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
        createdAt: null,
        chips,
        downloadName: node.detail ?? node.label,
      })
    }
  }, [nodeById, outputById, t])

  const handleSelect = useCallback(
    (id: string) => {
      const node = nodeById.get(id)
      if (!node) return
      if (node.kind === "asset") {
        // Source media nodes have no dock business — a click IS the
        // expand gesture (the lightbox; non-media assets no-op inside).
        handleExpandMedia(id)
        return
      }
      if (node.kind === "document") {
        // The task book is read on the card — no dock business; its confirm
        // beat lives on the draft-confirm card anchored above it (K5).
        return
      }
      // A graph card: click = dock focus (D8) + the dossier swap-in, on the
      // product the pager is SHOWING (fallback = the node's first).
      const outputs = node.outputs ?? []
      if (outputs.length === 0) return
      const output =
        outputById.get(displayedRef.current.get(id) ?? "") ?? outputs[0]
      setInspectedId(output.id)
      onOutputClick?.(output)
    },
    [nodeById, outputById, onOutputClick, handleExpandMedia],
  )

  const handleOutputAction = useCallback(
    (id: string, action: FlowOutputAction) => {
      const output = outputById.get(id)
      if (output) onOutputAction?.(output, action)
    },
    [outputById, onOutputAction],
  )

  // ── Prompt direct edit → the pricing confirmation (ADR-057 K4; ADR-058
  // deterministic dispatch) ───────────────────────────────────────────────
  // The card-face program region reports a new program; NOTHING touches
  // the graph here — the confirm card anchors at the edited node (world
  // space, riding pan/zoom like the prototype's scene C), names the
  // affected subgraph (本节点 ∪ 图边下游) as chips, prices it by folding
  // each node's own quote, and soft-compares the balance. The confirmed
  // Start calls the surface's onNodeRevise: CODE-built edit_prompt + run
  // (the node id is structurally exact — zero intent recognition), NOT a
  // chat turn. While the edit is pending (confirm open / awaiting the
  // stamp), the node's card face keeps showing the user's verbatim program
  // (pendingProgram — 乐观回显, never a revert flash).
  const [promptEdit, setPromptEdit] = useState<{ nodeId: string; text: string } | null>(null)
  const handlePromptEdit = useCallback((nodeId: string, text: string) => {
    setPromptEdit({ nodeId, text })
  }, [])

  // ── Draft-confirm card (ADR-057 K5 — 确认 = 节点锚定) ──────────────────
  // While the docked task book's draft graph is on the canvas, the desktop
  // confirm beat lives HERE: anchored at the task-book document node, the
  // whole chain's price folded from the draft nodes' OWN quotes (the same
  // numbers the draft cards read — never a second estimate source), the
  // balance as the soft compare, Start riding the dock's one start path
  // (the imperative handle — same guards, same grey-row failure surface).
  // 任务书密度律 mirror (ADR-054): a one-task chain confirms by the next
  // chat message — no card (it never earns the heavy rendering). The card
  // self-clears when the run starts (the draft nodes re-queue) and refreshes
  // when a refine re-docks (the graph re-stamps).
  const draftNodes = useMemo(
    () =>
      nodes.filter(
        (n) =>
          n.status === "draft" &&
          (n.kind === "generator" || n.kind === "processor" || n.kind === "agent"),
      ),
    [nodes],
  )
  const taskBookDoc = useMemo(
    () =>
      nodes.find((n) => n.kind === "document" && n.spec?.role === "task_book") ??
      null,
    [nodes],
  )
  const draftEstimate = useMemo<[number, number] | null>(() => {
    if (draftNodes.length === 0) return null
    const low = draftNodes.reduce((sum, n) => sum + (n.estimateCredits?.[0] ?? 0), 0)
    const high = draftNodes.reduce(
      (sum, n) => sum + (n.estimateCredits?.[1] ?? n.estimateCredits?.[0] ?? 0),
      0,
    )
    return [low, high]
  }, [draftNodes])
  // 任务书密度律 mirror (ADR-054): the chain's TASK count gates the heavy
  // confirm, not the node count — the compile-injected materialize_source
  // is never a task (whole-source materialization, ADR-043), so a modifier-
  // only one-task book ([remove_filler] → 2 nodes) stays prose-confirmed.
  // The price fold above keeps every node (materialize's cost is real).
  const draftTaskCount = useMemo(
    () => draftNodes.filter((n) => n.spec?.tool !== "materialize_source").length,
    [draftNodes],
  )
  const draftConfirmVisible =
    draftTaskCount >= 2 && taskBookDoc !== null && draftEstimate !== null

  // The balance soft-compare, shared by both confirm cards (K4's prompt-
  // edit card on open, K5's resident draft card while the draft graph is
  // up): lazy + silent (CreditsPill's 防双报 discipline) — a fetch failure
  // just keeps the line blank.
  const [balanceNow, setBalanceNow] = useState<number | null>(null)
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await apiFetch("/api/v1/wallet", { toast: false })
        if (!res.ok) return
        const wallet = (await res.json()) as { balance: number }
        if (!cancelled) setBalanceNow(wallet.balance)
      } catch {
        /* silent */
      }
    })()
    return () => {
      cancelled = true
    }
    // draftConfirmVisible's flip re-arms the fetch (a re-docked chain
    // re-quotes; the balance may have moved with a prior run).
  }, [promptEdit !== null, draftConfirmVisible])

  const editedNode = promptEdit ? (nodeById.get(promptEdit.nodeId) ?? null) : null
  // A refresh / delete vanishing the anchor node closes the card.
  useEffect(() => {
    if (promptEdit && !editedNode) setPromptEdit(null)
  }, [promptEdit, editedNode])
  // The stamp's arrival clears the pending program: after a successful
  // dispatch the graph refetch brings the node stamped with the SAME
  // verbatim text (edit_prompt 钢印), and the card face's pending display
  // hands over to the domain truth seamlessly.
  useEffect(() => {
    if (!promptEdit || !editedNode) return
    if ((editedNode.spec?.prompt ?? "").trim() === promptEdit.text.trim()) {
      setPromptEdit(null)
    }
  }, [promptEdit, editedNode])

  const promptEditBlast = useMemo(() => {
    if (!promptEdit) return null
    // Downstream walk over the graph's own edges (the projection walk's
    // replacement — 修订波及面 = 图边遍历, never a scope guess).
    const adjacency = new Map<string, string[]>()
    for (const e of graph?.edges ?? []) {
      const list = adjacency.get(e.from_node) ?? []
      list.push(e.to_node)
      adjacency.set(e.from_node, list)
    }
    const seen = new Set<string>([promptEdit.nodeId])
    const queue = [promptEdit.nodeId]
    while (queue.length > 0) {
      const current = queue.shift() as string
      for (const next of adjacency.get(current) ?? []) {
        if (!seen.has(next)) {
          seen.add(next)
          queue.push(next)
        }
      }
    }
    // Only the runnable kinds carry a price — asset/document nodes never
    // re-run (and in our topology are never downstream of a generator).
    const affected = [...seen].flatMap((id) => {
      const n = nodeById.get(id)
      return n && (n.kind === "generator" || n.kind === "processor" || n.kind === "agent")
        ? [n]
        : []
    })
    const low = affected.reduce((sum, n) => sum + (n.estimateCredits?.[0] ?? 0), 0)
    const high = affected.reduce(
      (sum, n) => sum + (n.estimateCredits?.[1] ?? n.estimateCredits?.[0] ?? 0),
      0,
    )
    return { affected, low, high }
  }, [promptEdit, graph, nodeById])

  // Esc closes (the edit textarea has already unmounted by the time the
  // card is open, so no gesture collision).
  useEffect(() => {
    if (!promptEdit) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPromptEdit(null)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [promptEdit])

  const handlePromptEditConfirm = useCallback(async () => {
    if (!promptEdit) return
    const ok = (await onNodeRevise?.(promptEdit.nodeId, promptEdit.text)) ?? false
    // Success keeps promptEdit alive — it IS the card face's optimistic
    // program until the stamp arrives (the clear-on-stamp effect above).
    // Failure (credits shortfall / active run / a reject — the surface
    // toasted) reverts the display to the domain truth: nothing landed.
    if (!ok) setPromptEdit(null)
  }, [promptEdit, onNodeRevise])

  const promptEditOverlay =
    promptEdit && editedNode && promptEditBlast ? (
      <ViewportPortal>
        <div
          className="dock-surface pointer-events-auto absolute z-20 w-64 rounded-xl p-3.5 ring-1 ring-foreground/10"
          style={{
            left: editedNode.frame?.x ?? 0,
            top: (editedNode.frame?.y ?? 0) - 12,
            transform: "translateY(-100%)",
          }}
        >
          <p className="text-[13px] font-semibold">
            {t("results.canvas.confirmTitle", { label: editedNode.label })}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
            <span>
              {promptEditBlast.affected.length === 1
                ? t("results.canvas.confirmBlastSingle")
                : t("results.canvas.confirmBlast", {
                    count: promptEditBlast.affected.length,
                  })}
            </span>
            {promptEditBlast.affected.map((n) => (
              <span
                key={n.id}
                className="rounded bg-inset px-1.5 py-0.5 text-[10px] whitespace-nowrap"
              >
                {n.label}
              </span>
            ))}
          </div>
          <p className="mt-2.5 text-xs tabular-nums">
            {promptEditBlast.low === promptEditBlast.high
              ? t("results.canvas.estimateSingle", { count: promptEditBlast.low })
              : t("credits.range", {
                  low: promptEditBlast.low,
                  high: promptEditBlast.high,
                })}
            {balanceNow != null && (
              <span
                className={cn(
                  "ml-1 text-[11px]",
                  balanceNow < promptEditBlast.low
                    ? "text-destructive"
                    : "text-meta-foreground",
                )}
              >
                · {t("credits.balance")} {balanceNow.toLocaleString()}
              </span>
            )}
          </p>
          <div className="mt-3 flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-8"
              onClick={() => setPromptEdit(null)}
            >
              {t("common.cancel")}
            </Button>
            <Button size="sm" className="h-8" onClick={handlePromptEditConfirm}>
              {t("results.canvas.confirmStart")}
            </Button>
          </div>
        </div>
      </ViewportPortal>
    ) : null

  // The draft world'S confirm beat (ADR-057 K5): resident while the docked
  // book's draft graph is up, anchored above the task-book document node —
  // the prototype's confirmCard anatomy (title / price + balance soft
  // compare / Start), no Cancel (non-blocking doctrine: "don't start" is
  // said by not starting — chat revises, walking away keeps the book
  // honestly pending).
  const draftConfirmOverlay =
    draftConfirmVisible && draftEstimate ? (
      <ViewportPortal>
        <div
          className="dock-surface pointer-events-auto absolute z-20 w-64 rounded-xl p-3.5 ring-1 ring-foreground/10"
          style={{
            left: taskBookDoc?.frame?.x ?? 0,
            top: (taskBookDoc?.frame?.y ?? 0) - 12,
            transform: "translateY(-100%)",
          }}
        >
          <p className="text-[13px] font-semibold">{t("results.canvas.taskBook")}</p>
          <p className="mt-2 text-xs tabular-nums">
            {draftEstimate[0] === draftEstimate[1]
              ? t("results.canvas.estimateSingle", { count: draftEstimate[0] })
              : t("credits.range", {
                  low: draftEstimate[0],
                  high: draftEstimate[1],
                })}
            {balanceNow != null && (
              <span
                className={cn(
                  "ml-1 text-[11px]",
                  balanceNow < draftEstimate[0]
                    ? "text-destructive"
                    : "text-meta-foreground",
                )}
              >
                · {t("credits.balance")} {balanceNow.toLocaleString()}
              </span>
            )}
          </p>
          <div className="mt-3 flex justify-end">
            <Button size="sm" className="h-8" onClick={() => onDraftConfirm?.()}>
              {t("results.canvas.confirmStart")}
            </Button>
          </div>
        </div>
      </ViewportPortal>
    ) : null

  // Pane click = back to neutral: the dossier closes with the focus (D4/D8),
  // and a pending pricing confirmation dismisses with it.
  const handlePaneClick = useCallback(() => {
    setInspectedId(null)
    setPromptEdit(null)
    onPaneClick?.()
  }, [onPaneClick])

  // The dossier's asset facts (出生证明 lineage) come from the graph's own
  // asset nodes — one source, zero second fetch.
  const inspectorAssets = useMemo(
    () =>
      nodes.flatMap((n) =>
        n.kind === "asset" && n.asset
          ? [
              {
                id: n.asset.id,
                type: n.asset.type,
                title: n.asset.title,
                file_url: n.asset.file_url,
                stream_url: n.asset.stream_url,
                duration_seconds: n.asset.duration_seconds,
              },
            ]
          : [],
      ),
    [nodes],
  )

  return (
    <div className={cn("relative", className)}>
      <FlowView
        nodes={nodes}
        edges={edges}
        navigation="explore"
        straightEdges
        controls
        controlsClassName={controlsClassName}
        settleKey={baselineReady && visible ? baselineKey : null}
        bornIds={bornIds}
        dots
        overlay={
          promptEditOverlay || draftConfirmOverlay ? (
            <>
              {promptEditOverlay}
              {draftConfirmOverlay}
            </>
          ) : null
        }
        className="h-full"
        selectedId={selectedOutputId ? (nodeIdByOutputId.get(selectedOutputId) ?? null) : null}
        onPaneClick={handlePaneClick}
        onExpandMedia={handleExpandMedia}
        onSelect={handleSelect}
        onOutputAction={handleOutputAction}
        onAssetAction={onAssetAction}
        onDisplayChange={handleDisplayChange}
        onPromptEdit={handlePromptEdit}
        pendingProgram={promptEdit}
      />
      {/* The dossier rides the zoom pill's corner: right-aligned with it,
          stacked below (pill = m-3/m-4 + h-9 → 52/60px), and sharing its
          docked-panel avoidance so both clear the open frost. */}
      {inspectedOutput && (
        <OutputInspector
          output={inspectedOutput}
          step={
            (steps ?? []).find((s) => s.id === inspectedOutput.workflow_step_id) ??
            null
          }
          assets={inspectorAssets}
          onClose={() => setInspectedId(null)}
          onAction={(output, action) => onOutputAction?.(output, action)}
          className={cn(
            "absolute top-[52px] right-3 z-30 md:top-[60px] md:right-4",
            controlsClassName,
          )}
        />
      )}
      <MediaLightbox
        data={lightbox}
        onOpenChange={(open) => {
          if (!open) setLightbox(null)
        }}
      />
    </div>
  )
}
