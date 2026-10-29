import { createFileRoute, useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { downloadOutput } from "@/components/results/downloadOutput"
import { outputFullText } from "@/components/results/outputText"
import { ChatDock, type DerivedRow, type DecisionPlanRow, type ChatDockHandle } from "@/components/chat/ChatDock"
import { normalizeIntent, tasksFromRunContext } from "@/components/chat/chatProtocol"
import { ResultsCanvas } from "@/components/flow/ResultsCanvas"
import { SoundMutexProvider } from "@/components/flow/sound-mutex"
import type { FlowAssetAction, FlowAssetInfo, FlowOutputAction } from "@/components/flow/types"
import { ProjectHeader } from "@/components/project/ProjectHeader"
import { PublishDialog } from "@/components/publish/PublishDialog"
import { apiDelete, apiFetch, apiPost, downloadFile, toAbsoluteUrl } from "@/lib/api"
import { outputMentionLabel } from "@/lib/mentions"
import { useIsMobile } from "@/hooks/use-mobile"
import { canvasCapableFor } from "@/lib/canvasVisibility"
import { useWorkspaceLayout } from "@/hooks/use-workspace-layout"
import { sseProbe } from "@/lib/sse-probe" // TEMPORARY forensics — delete with the probe
import { useRunEvents } from "@/lib/use-run-events"
import { cn } from "@/lib/utils"
import { isPlanReady } from "@/lib/lifecycleStamp"

import type { IntentSlot, LifecycleStamp, Output, ProjectGraph, WorkflowStep, Project } from "@/lib/types"

interface AssetStatusEntry {
  id: string
  type: string
  processing_status: "pending" | "processing" | "completed" | "failed"
  processing_error?: string | null
}

interface WorkflowRun {
  id: string
  project_id: string
  status: "pending" | "running" | "completed" | "failed"
  progress: number
  error: string | null
  context: {
    /** The confirmed task chain (ADR-043); legacy runs carry slot-shaped
     * outputs instead — `tasksFromRunContext` upgrades either at read time. */
    tasks?: { tool: string; params: Record<string, unknown> }[]
    /** Slot-shaped on new runs; legacy flat runs carry string outputs +
     * `clip_count` — read tolerance only, upgraded by `tasksFromRunContext`. */
    outputs?: (string | IntentSlot)[]
    clip_count?: number
    target_language?: string
    /** 配音语言集 (RECIPES §4.1): absent on pre-recipe runs. */
    dub_languages?: string[]
    /** 字幕语言集 (RECIPES §4.1 字幕卡): absent on pre-R6 runs. */
    caption_languages?: string[]
    /** 画幅 (2026-08-14 三档画幅): absent = the brand default (9:16). */
    aspect?: "9:16" | "1:1" | "16:9" | null
    /** 双语对照 (2026-08-14 双语字幕): absent/false = plain translation. */
    caption_bilingual?: boolean
    /** The run-pinned persona (ADR-038); legacy runs' brand_template_id key
     * is ignored on read — re-runs resolve via the persona chain. */
    persona_id?: string | null
    instruction?: string | null
    tone_settings?: Record<string, unknown> | null
    /** Caption mode of a captioned-chain run (S7); echoed verbatim by an
     * exact retry (ADR-087 §4 D2 — the retry reference, never the proof). */
    caption_mode?: "bilingual" | "source_only" | "target_only" | null
    /** 资产角色 pins (ADR-078); same retry-echo rule as caption_mode. */
    source_asset_id?: string | null
    exemplar_asset_id?: string | null
    /** The proposer's fresh naming of the run (ADR-058 — LLM 建图时命名);
     * absent on typed/legacy paths (readers fall back to the chain label). */
    name?: string | null
    /** "node_revise" = a card-face edit's deterministic node rerun — the
     * dock stays silent about it (ADR-058: zero messages, the node's own
     * state cycle is the feedback). */
    origin?: string | null
  } | null
  cost: Record<string, number> | null
  steps: WorkflowStep[]
  created_at: string
  updated_at: string | null
}

interface PendingBrief {
  prompt: string
  /** Task-shaped on the API (the server upgrades legacy flat/slot rows on
   * read); typed loosely here and normalized at the overlay boundary. Null
   * on brief-only rows (an ask-turn write — no plan parked, ADR-052 B2). */
  intent: unknown | null
  /** The merged brief (预填评审卡, ADR-052 B3) — the plan card's
   * slot rows; typed loosely here and normalized at the dock boundary. */
  brief?: unknown
  /** Why the plan needs a human check — confirmation is `reasons.length > 0`
   * (the API's redundant needs_clarification bool was retired, B4). */
  reasons?: string[]
  persona_id?: string | null
  /** The server-compiled "what you'll get" preview rows (ADR-043). */
  derived?: DerivedRow[]
  /** 决策包阅读层 (iter-2 ③): the Content Plans behind the compiled chain —
   * stamped at dock time so the plan card's reading layer survives refresh.
   * Empty on router-drafted rows (读容忍). */
  plans?: DecisionPlanRow[]
}

interface ProjectResults {
  project: Project
  prompt: string | null
  outputs: Output[]
  latest_run: WorkflowRun | null
  assets?: AssetStatusEntry[]
  pending_brief?: PendingBrief | null
  lifecycle?: LifecycleStamp | null
}

export const Route = createFileRoute("/projects/$id/")({
  component: ProjectDetailPage,
})

function ProjectDetailPage() {
  const { id: projectId } = Route.useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  // The composer hands its draft over via router state: the chat dock sends
  // it as the first /chat message (intent-surface-unification W2). The page
  // is ALWAYS canvas + dock (ADR-051) — the ?overlay= route params and the
  // fullscreen shell are retired; project state drives the dock's form.
  const firstMessage = (
    location.state as {
      firstMessage?: {
        text: string
        mentions?: { type: string; id: string; label: string }[]
        personaId?: string
      }
    }
  ).firstMessage
  const [results, setResults] = useState<ProjectResults | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // ── Results canvas (ADR-041; ADR-051 画布优先) ───────────────────────
  // Desktop (≥768px = iPad up, D1/D10): the page is ALWAYS the canvas + the
  // chat dock — pre-run assets, the live run's projection, and the terminal
  // frame all render on it. Mobile has no canvas (prohibition #13) — the
  // chat dock's full form IS the page at every project age (移动端恒纯
  // chat), and products deliver in the message flow (receipt + anchor
  // cards, ADR-118). The user can pin the chat-first workspace on ANY
  // screen via 设置→通用→工作区布局 = 纯对话 (ADR-123) — canvasCapable is
  // the ONE composition (viewport ∧ setting, lib/canvasVisibility 单源座).
  const isMobile = useIsMobile()
  const workspaceLayout = useWorkspaceLayout()
  const canvasCapable = canvasCapableFor(isMobile, workspaceLayout)
  const dockRef = useRef<ChatDockHandle>(null)
  /** The latest COMPLETED run snapshot — the canvas's terminal frame. The
   * sticky copy survives a later refinement run going active/failed (D9:
   * the canvas shows the current run + latest products); the live value
   * takes precedence the moment it exists, so the dock mounts in one pass
   * (no effect lag on refresh). */
  const [stickyCompletedRun, setStickyCompletedRun] = useState<WorkflowRun | null>(null)
  // The persistent graph's one read frame (ADR-057 — the canvas's ONLY data
  // source; fetched alongside /results on the same cadence).
  const [graph, setGraph] = useState<ProjectGraph | null>(null)

  // ── Product actions (ADR-041 D5/D8) ──────────────────────────────────
  // The canvas's product nodes ARE the cards: click is selection only
  // (2026-09-13 用户拍板——视频点击后不再弹窗, the detail modal retired);
  // the factsbar reports download / publish (the PublishDialog is the old
  // card-face logic, mounted as-is).
  const [publishOutput, setPublishOutput] = useState<Output | null>(null)
  const [selectedOutputId, setSelectedOutputId] = useState<string | null>(null)

  const fetchGraph = useCallback(async () => {
    const graphRes = await apiFetch(`/api/v1/projects/${projectId}/graph`, { toast: false })
    if (!graphRes.ok) return null
    const fresh = (await graphRes.json()) as ProjectGraph
    setGraph(fresh)
    return fresh
  }, [projectId])

  const fetchResults = useCallback(async () => {
    try {
      // The canvas reads the graph directly (ADR-057 — zero projection):
      // one cadence, two fetches, the graph frame and the ledger/results
      // payload always agree.
      const [res, graphRes] = await Promise.all([
        apiFetch(`/api/v1/projects/${projectId}/results`),
        apiFetch(`/api/v1/projects/${projectId}/graph`, { toast: false }),
      ])
      if (!res.ok) throw new Error("Project not found")
      setResults(await res.json())
      if (graphRes.ok) setGraph((await graphRes.json()) as ProjectGraph)
      // One successful pass clears any earlier transient failure — without
      // this the error latch held the placeholder up past recovery and only
      // a manual reload brought the canvas back (2026-09-13 走查).
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project")
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const latestRun = results?.latest_run
  // Lifecycle Projection (ADR-087 §2, Phase 1): the server-named stamp is
  // the ONE readiness truth — this page never derives lifecycle from
  // artifact existence. The stamp rides BOTH frames (results + graph);
  // the graph frame is the fresher source during live turns.
  const lifecycle = graph?.lifecycle ?? results?.lifecycle ?? null
  // 画布可见性律 (ADR-111, 2026-10-08 拍板 — ADR-105 翻案): the desktop
  // canvas reveals at PLAN-READY — the docked plan's draft graph IS the
  // world waiting to start (one rule, two speeds: a recipe arrives
  // instantly, a chat turn arrives gradually). The driver is the
  // server-named lifecycle stamp (ADR-087 §2 — never a local derivation);
  // runs keep revealing too (hasRuns covers every post-start state).
  // Chat-first surfaces stay run-driven (no canvas below iPad width, and
  // none under the user's 纯对话 setting either — the plan's review face
  // there is the prose echo, not a canvas).
  const hasRuns = latestRun != null
  const worldLive = hasRuns || (canvasCapable && isPlanReady(lifecycle))
  // The desktop chat panel is a FROSTED OVERLAY on the full-bleed canvas
  // (2026-09-06 用户拍板, FLORA "Dock panel" parity — float / docked-right,
  // never an in-flow column): the canvas's top-right zoom pill steps clear
  // ONLY when the geometry can cover it — docked is full-height; float
  // starts ~18% down and never reaches the corner (the uniform offset's
  // dead zone above the float panel was user-caught same-day). The dock
  // reports its tucked-away state + geometry up.
  const [panelState, setPanelState] = useState({
    hidden: false,
    docked: false,
  })
  const panelCoversCorner =
    worldLive && canvasCapable && !panelState.hidden && panelState.docked

  // sse-probe: world-liveness flips (TEMPORARY forensics — delete with the probe)
  useEffect(() => {
    sseProbe("state.worldLive", { value: worldLive, hasRuns, isMobile })
  }, [worldLive, hasRuns, isMobile])

  useEffect(() => {
    setLoading(true)
    fetchResults()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // SSE drives the active-run phase (CHAT_ARCH §8): snapshot + step diffs
  // replace the 2.5s polling below. The hook no-ops without a token, so
  // anonymous viewers fall through to the legacy interval.
  const runActive =
    latestRun != null &&
    (latestRun.status === "pending" || latestRun.status === "running")
  const sse = useRunEvents(runActive ? latestRun.id : null, fetchResults)
  const sseActive = runActive && sse.steps.length > 0

  // The canvas's live read (ADR-057 K2 — run 期节点原地填充): graph node
  // states back-write at every step transition (queued → running → done,
  // and landed products write spec.output_ids), so every SSE step diff is
  // also a graph-state change. Refetch the graph on the same beat — the
  // run's start/terminal full refetches stay (they also carry /results).
  const sseSteps = sse.steps
  useEffect(() => {
    if (!sseActive) return
    void fetchGraph()
  }, [sseSteps, sseActive, fetchGraph])

  // The completed-run snapshot (D9): a live completed run takes precedence;
  // the sticky copy keeps the canvas's terminal frame up while a later
  // refinement run is active/failed.
  useEffect(() => {
    if (latestRun?.status === "completed") setStickyCompletedRun(latestRun)
  }, [latestRun])

  // Canvas self-heal (2026-09-13 用户拍板 — xyflow store desync, the
  //「node 消失、刷新才回」走查): the run-tail refetch rebuilds every node
  // while card heights are still settling (products landing), and xyflow's
  // internal store can stay desynced once every refetch loop has stopped —
  // a frozen empty layer only a manual reload healed. ~0.6s after the run
  // lands terminal, bump the epoch: ResultsCanvas remounts the xyflow world
  // (a fresh store re-syncs from settled props — the whole desync family,
  // node AND edge layer). Cost: one viewport re-fit at the exact moment the
  // user is reading the receipt. Rising edge only — the mount observation
  // (a refreshed already-terminal project) never fires.
  const [canvasEpoch, setCanvasEpoch] = useState(0)
  // 相机节拍 (Workspace 合同 v4.2 C5, 2026-09-26 封板): the armed
  // user-initiated camera beat — ONE ensure-in-view semantics (已在安全区
  // 不动 / 不在则最小 pan / zoom 永不自动 fit; the 2026-09-25 fitNow beat
  // reversed 2026-09-26 —「draft 到达 → 整链 fitNow」不入合同). Armed ONLY
  // inside the dock's own send/Start handlers (background polling / SSE
  // refetches never arm, so they never move the camera), consumed by
  // FlowView on the first arrival carrying a node-id delta (or retired by
  // its timeout). Arming is gated on the LIVE canvas: the pre-world morph's
  // settle framing owns the first show (the sole automatic fit), and the
  // mobile dock has no focus business (mobile stays run-driven).
  const [cameraBeat, setCameraBeat] = useState<{ token: number } | null>(null)
  const clearCameraBeat = useCallback(() => setCameraBeat(null), [])
  // 「把当前操作元素移到画布中心」 (v4.2 未覆盖 #3, 2026-09-26 拍板): the
  // explicit one-shot centering capability — pan-locked-zoom, camera-law
  // shields apply. A plain page-level method any surface (or a future
  // agent-driven caller) summons; zero chrome of its own in this batch.
  // 「把当前操作元素移到画布中心」 (v4.2 未覆盖 #3, 2026-09-26 拍板): the
  // explicit one-shot centering capability — pan-locked-zoom, camera-law
  // shields apply. A plain page-level method any surface (or a future
  // agent-driven caller) summons; zero chrome of its own in this batch.
  // The target is a cluster of node ids (a singleton for the single-node
  // gesture; the dock path's newborn cluster rides the same seat).
  const [centerRequest, setCenterRequest] = useState<{
    token: number
    nodeIds: string[]
  } | null>(null)
  const requestCenterNode = useCallback(
    (nodeId: string) => setCenterRequest({ token: Date.now(), nodeIds: [nodeId] }),
    [],
  )
  const clearCenterRequest = useCallback(() => setCenterRequest(null), [])
  const lastRunStatusRef = useRef<string | null>(null)
  useEffect(() => {
    const status = latestRun?.status ?? null
    const prev = lastRunStatusRef.current
    lastRunStatusRef.current = status
    if (prev == null || prev === status) return
    if (status !== "completed" && status !== "failed") return
    // 产出落地跟随 (2026-09-24 user ruling): the run's harvest arrives via
    // the terminal refetch — arm an ensure-in-view beat; CameraBeats pans
    // (minimally, zoom locked) only if the cluster whose product counts
    // grew sits outside the safe viewport (outputs fill EXISTING nodes, so
    // the newborn id-diff alone never saw landings).
    if (hasRuns && canvasCapable) {
      setCameraBeat({ token: Date.now() })
    }
    const timer = setTimeout(() => setCanvasEpoch((e) => e + 1), 600)
    return () => clearTimeout(timer)
  }, [latestRun?.status])

  // Cross-project navigation (same route, new params — no remount): every
  // project-scoped latch resets, or the previous project's canvas/dock
  // would bleed into the new page while its results load.
  useEffect(() => {
    setStickyCompletedRun(null)
    setGraph(null)
    setPublishOutput(null)
    setSelectedOutputId(null)
  }, [projectId])

  // Re-point the modal/focus state at the freshest rows after every refetch
  // (polling and refinement turns replace output objects in place); a focus
  // whose product left the visible set clears itself.
  const outputsList = useMemo(() => results?.outputs ?? [], [results])
  useEffect(() => {
    const byId = new Map(outputsList.map((o) => [o.id, o]))
    setPublishOutput((prev) => (prev ? (byId.get(prev.id) ?? null) : null))
    setSelectedOutputId((prev) => (prev && !byId.has(prev) ? null : prev))
  }, [outputsList])

  // Canvas handlers are useCallback-stable (2026-08-19 二轮 R5): FlowView's
  // rfNodes/rfEdges memo keys on them — plain closures rebuilt the whole
  // graph on every unrelated re-render (SSE ticks, selection changes).
  const handleOutputClick = useCallback((output: Output) => {
    // Click = canvas SELECTION + the dossier swap-in (the inspector owns
    // that half; 2026-09-13 二轮拍板: the right-side dossier STAYS — only
    // the centered player modal retired from the click beat). ADR-058:
    // pointing at a product in chat is an @mention, no hidden focus state.
    setSelectedOutputId(output.id)
  }, [])

  const handleOutputAction = useCallback(async (output: Output, action: FlowOutputAction) => {
    if (action === "open") {
      handleOutputClick(output)
      return
    }
    if (action === "focus") {
      // 在对话中指认 = an @output chip in the dock's editor (ADR-058: the
      // one pointing mechanism — visible in the user's own sentence, the
      // chip's three laws hold). No hidden focus state. v4.2 未覆盖 #3:
      // the named element IS the current operation element — center its
      // node on the canvas (pan-locked-zoom; shields inside FlowView).
      const node = graph?.nodes.find((n) => n.spec.output_ids?.includes(output.id))
      if (node && hasRuns && canvasCapable) requestCenterNode(node.id)
      dockRef.current?.insertMention({
        type: "output",
        id: output.id,
        label: outputMentionLabel(
          output,
          t(`chat.derivativeTypes.${output.type}`, {
            defaultValue: t("results.tabs.clips"),
          }),
        ),
      })
      return
    }
    if (action === "copy") {
      // The text product's primary verb: the full text (title + body +
      // hashtags, outputFullText's one composition) to the clipboard.
      navigator.clipboard
        .writeText(outputFullText(output))
        .then(() => toast.success(t("chat.copied")))
        .catch(() => toast.error(t("common.requestFailed")))
      return
    }
    if (action === "download") downloadOutput(output)
    else if (action === "publish") setPublishOutput(output)
    else if (action === "delete") {
      const res = await apiDelete(`/api/v1/outputs/${output.id}`)
      if (!res.ok) return
      setSelectedOutputId((prev) => (prev === output.id ? null : prev))
      await fetchResults()
    }
  }, [handleOutputClick, fetchResults, graph, hasRuns, canvasCapable, requestCenterNode, t])

  // 选区引用 (2026-09-11 — 段落级指认): the user selected a passage on a
  // text product's card face and pinned 「引用这段」 — the dock gets an
  // @output chip carrying the quote, and the AGENT revises that passage (the
  // pinned passage is the revision's scope; manual editing stays the escape
  // hatch, never the story). v4.2 未覆盖 #3: the quoted element is the
  // current operation element — its node centers on the canvas (the same
  // pan-locked-zoom capability the 指认 gesture rides).
  const handleQuoteOutput = useCallback((output: Output, quote: string) => {
    const node = graph?.nodes.find((n) => n.spec.output_ids?.includes(output.id))
    if (node && hasRuns && canvasCapable) requestCenterNode(node.id)
    dockRef.current?.insertMention({
      type: "output",
      id: output.id,
      label: outputMentionLabel(
        output,
        t(`chat.derivativeTypes.${output.type}`, {
          defaultValue: t("results.tabs.clips"),
        }),
      ),
      quote,
    })
  }, [graph, hasRuns, canvasCapable, requestCenterNode, t])

  // Asset-node factsbar (2026-08-17 走查拍板): the surface owns the source
  // file's actions — download / delete / reprocess ("open" never arrives
  // here: the card opens the lightbox directly).
  const handleAssetAction = useCallback(async (asset: FlowAssetInfo, action: FlowAssetAction) => {
    if (action === "download") {
      const url = toAbsoluteUrl(asset.stream_url ?? asset.file_url)
      if (url) await downloadFile(url, asset.title ?? "asset")
      return
    }
    if (action === "delete") {
      const res = await apiDelete(`/api/v1/projects/${projectId}/assets/${asset.id}`)
      if (res.ok) await fetchResults()
    } else if (action === "reprocess") {
      const res = await apiPost(
        `/api/v1/projects/${projectId}/assets/${asset.id}/reprocess`,
        {}
      )
      if (res.ok) await fetchResults()
    }
  }, [projectId, fetchResults])

  // The card-face prompt direct edit's deterministic dispatch (ADR-058):
  // the pricing confirmation's Start posts the graph revision — code-built
  // edit_prompt + run, zero intent recognition, NOT a chat turn (the dock
  // stays silent; the node's own state cycle on the canvas is the
  // feedback). Resolves true when the run started; failure surfaces here
  // (the confirm card reverts its display on false).
  const handleGraphRevise = useCallback(
    async (nodeId: string, text: string): Promise<boolean> => {
      let res: Response
      try {
        res = await apiPost(
          `/api/v1/projects/${projectId}/graph/revise`,
          { node_id: nodeId, prompt: text },
          { toast: false }
        )
      } catch {
        // apiFetch RETHROWS network-level failures (no response to parse) —
        // the confirm card must still hear it (失败才开口, ADR-058): toast
        // here and let the surface revert the optimistic program.
        toast.error(t("common.networkError"))
        return false
      }
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          detail?: unknown
        }
        const detail = body?.detail
        const credits =
          typeof detail === "object" && detail !== null && (detail as { code?: string }).code === "credits.insufficient"
            ? (detail as { balance: number; required: number })
            : null
        toast.error(
          credits
            ? t("credits.insufficient", { balance: credits.balance, required: credits.required })
            : typeof detail === "string" && detail
              ? detail
              : t("common.requestFailed")
        )
        return false
      }
      // Refetch now: the fresh latest_run flips runActive, the page SSE
      // attaches, and the node's own state cycle (stale → queued → running
      // → filled) renders from the first beat.
      await fetchResults()
      return true
    },
    [projectId, fetchResults, t]
  )

  const completedRun =
    latestRun?.status === "completed" ? latestRun : stickyCompletedRun

  /** The dock's completion hand-off: refetch so the canvas shows the landed
   * products. (The page's own SSE also refetches — this covers the dock's
   * watcher beating it.) */
  const handleDockComplete = async () => {
    await fetchResults()
  }

  const runTasks = tasksFromRunContext(latestRun?.context)

  // Keep polling only for what SSE does not cover: anonymous viewers (no
  // token → hook no-ops) and outputs still rendering after the run settled
  // (renders proceed independently of the run status).
  useEffect(() => {
    if (!results?.latest_run) return
    if (sseActive) return

    const status = results.latest_run.status

    const hasRenderingOutputs = (results.outputs ?? []).some(
      (o: Output) => o.render_status === "pending" || o.render_status === "rendering"
    )

    // A settled run (completed or failed) never progresses its outputs
    // further — stop polling regardless of what the step statuses say.
    // Renders proceed independently of the run, so keep polling only while
    // any are active.
    if ((status === "completed" || status === "failed") && !hasRenderingOutputs) {
      return
    }

    const interval = setInterval(() => {
      fetchResults()
    }, 2500)
    return () => clearInterval(interval)
  }, [results?.latest_run, results?.outputs, sseActive])

  // Lifecycle poll (Phase 1): pre-first-run there is no SSE and the run
  // poll above never arms — but the stamp can still be mid-flight
  // (materials processing toward PLAN_READY). Poll while the stamp says
  // material_pending so the review-surface flip arrives on its own beat.
  // Background refetch never moves the camera (画布相机律 — only explicit
  // beats do).
  const materialPending = lifecycle?.blockers.includes("material_pending") ?? false
  useEffect(() => {
    if (!materialPending) return
    if (results?.latest_run) return // the run poll / SSE owns the cadence
    const interval = setInterval(() => {
      fetchResults()
    }, 2500)
    return () => clearInterval(interval)
  }, [materialPending, results?.latest_run, fetchResults])

  if (loading) {
    return (
      <div className="grid h-dvh place-items-center bg-background text-muted-foreground">
        {t("common.loading")}
      </div>
    )
  }

  if (error || !results) {
    return (
      <div className="grid h-dvh place-items-center bg-background text-destructive">
        {error || "Project not found"}
      </div>
    )
  }

  const { project, prompt, pending_brief: pendingBrief } = results

  // ── The one chat dock (ADR-051) ──────────────────────────────────────
  // Desktop = the canvas + the chat dock; mobile = the chat dock's full
  // form IS the page (移动端恒纯 chat — no canvas below iPad width,
  // products deliver in the message flow, ADR-118). Project state drives
  // the dock's form: a parked plan docks the confirm panel, a live run
  // attaches the step flow, a completed run lands on the results
  // conversation. One mounted instance across all forms — the input group
  // is never remounted between them.

  /** The dock's plan-summary line, rebuilt from the completed run's context
   * (the same read-tolerance shape the attach flow uses); a run with no
   * recorded chain at all shows a bare clips row. */
  const completedRunTasks = tasksFromRunContext(completedRun?.context)
  const completedRunIntent = completedRun
    ? normalizeIntent({
        tasks: completedRunTasks.length
          ? completedRunTasks
          : [{ tool: "select_clips", params: {} }],
        specific_instruction: completedRun.context?.instruction,
        // The run's LLM name (ADR-058) — the receipt title survives the
        // refresh verbatim instead of falling back to the chain label.
        name: completedRun.context?.name,
      })
    : undefined

  const dockInitialIntent = runActive
    ? normalizeIntent({
        tasks: runTasks.length ? runTasks : [{ tool: "select_clips", params: {} }],
        specific_instruction: latestRun?.context?.instruction,
        name: latestRun?.context?.name,
      })
    : pendingBrief?.intent
      ? // A parked plan always wins — it IS the live confirmation
        // surface (a refinement plan parked from any device must be the
        // plan the panel edits and Start answers with, never the stale
        // completed run's). A brief-only row (intent null — an ask-turn
        // write, ADR-052 B2) parks no plan: fall through.
        normalizeIntent(pendingBrief.intent)
      : completedRun
        ? completedRunIntent
        : undefined

  return (
    // Fullscreen canvas world (ADR-041 全屏化; ADR-051 画布优先): this route
    // lives OUTSIDE the _app layout — no sidebar / header / title block.
    // Floating chrome: the project menu (top-left) + the canvas's own zoom
    // pill (top-right, FlowView `controls`); on desktop the canvas fills the
    // viewport and the chat dock overlays it as the right panel; on mobile
    // the chat dock's full form IS the page (两形态机 — 移动端恒纯 chat,
    // no canvas below iPad width). App
    // chrome (theme / language / notifications) lives in the studio shell —
    // 2026-08-19 走查拍板, confirmed to cover MOBILE too (nearest entry =
    // back to /projects).
    <SoundMutexProvider>
    <div className="relative flex h-dvh flex-col overflow-hidden bg-background">
      {/* The full-width glass header (2026-10-15 user ruling — Pexo parity,
          supersedes the floating-corner top chrome): left = the two-form
          machine (back button ↔ ProjectMenu crossfade, driven by worldLive),
          right = the credits read surface. Fixed z-[60] above the ChatDock
          overlay; the canvas's top-right chrome (zoom pill / inspector
          dossier) clears it in FlowView's default seat. */}
      <ProjectHeader
        projectId={project.id}
        title={project.title}
        worldLive={worldLive}
        runActive={runActive}
        onRenamed={(title) =>
          setResults((prev) =>
            prev ? { ...prev, project: { ...prev.project, title } } : prev
          )
        }
        onDeleted={() => navigate({ to: "/projects" })}
        creditsRefreshKey={
          latestRun ? `${latestRun.id}:${latestRun.status}` : "idle"
        }
      />

      {canvasCapable ? (
        /* Canvas-first (ADR-051; ADR-057 K3 直读): the desktop page's
           canvas reads the persistent graph directly (nodes = graph rows:
           assets at upload, run fills in place, draft estimate
           → running wipe → done self-evident). The completion beat = the
           growth-driven birth choreography (ADR-036 补记 3): every node
           born while the surface watches enters staggered in compile order,
           a filling node carries the FLORA wipe, and the hydrated first
           frame never replays. The canvas is FULL-BLEED — the dock/panel is
           a completely floating layer above it, never a layout reservation
           (no safe-area padding: reserving space IS the occlusion; 2026-09-06
           the panel's in-flow flex-row cut was user-retired same-day — the
           frost must have the canvas living beneath it). A node passing
           under the dock is panned back into view — the canvas is explore
           navigation. The whole canvas is gated on worldLive (ADR-111 —
           the reveal beat is PLAN-READY: the docked plan's draft graph
           fades the pane in before any run; runs keep the same gate after
           the start): pre-world it is
           invisible + inert (the full-form chat stage owns the page); the
           reveal fades it in on the same beat as the stage's
           fade-out — 500ms on a 150ms delay (2026-09-06 fade-simplified). */
        <div
          className={cn(
            "min-h-0 flex-1 transition-opacity duration-500 delay-150 ease-out motion-reduce:transition-none",
            !worldLive && "pointer-events-none opacity-0"
          )}
        >
          <ResultsCanvas
            className="h-full"
            controlsClassName={panelCoversCorner ? "md:!mr-[504px]" : undefined}
            graph={graph}
            // Terminal self-heal (2026-09-13 用户拍板): bumps ~0.6s after a
            // run lands terminal — remounts the xyflow world so a desynced
            // store (the frozen empty canvas) never survives the run.
            healEpoch={canvasEpoch}
            // The settle key's visibility half (2026-09-06): the canvas is
            // gated on worldLive, so initial framing joins it with the
            // baseline — partial fetch frames never frame. The reveal's
            // first frame = this settle fit (FIT_VIEW_OPTIONS clamps the
            // zoom, ADR-111 §6).
            visible={worldLive}
            // Birth baseline (ADR-036 补记 3): ready only when the initial
            // /results AND /graph have both settled for THIS project —
            // an early partial frame must not become the baseline (the
            // rest of the graph would "birth" on a plain refresh), and a
            // stale previous-project payload must not contaminate it.
            baselineReady={
              results?.project?.id === projectId && graph != null
            }
            baselineKey={projectId}
            steps={latestRun?.steps ?? []}
            onOutputClick={handleOutputClick}
            onOutputAction={handleOutputAction}
            onQuoteOutput={handleQuoteOutput}
            onNodeRevise={handleGraphRevise}
            onAssetAction={handleAssetAction}
            selectedOutputId={selectedOutputId}
            onPaneClick={() => {
              // 点画布空白 = 回中性: 选中清除.
              setSelectedOutputId(null)
            }}
            cameraBeat={cameraBeat}
            onCameraBeatConsumed={clearCameraBeat}
            centerRequest={centerRequest}
            onCenterRequestConsumed={clearCenterRequest}
            occludedRightPx={panelCoversCorner ? 504 : 0}
          />
        </div>
      ) : null}

      <ChatDock
        // Remount per project — the message machine's state (run id,
        // conversation) belongs to one project only.
        key={projectId}
        ref={dockRef}
        projectId={projectId}
        // The two-form machine (ADR-111: the desktop flip condition is
        // PLAN-READY — the docked plan's draft graph morphs the world open
        // before any run): pre-birth the dock is the centered fullscreen
        // chat; the WORKSPACE's birth morphs it into the DESKTOP panel
        // ("panel" — a frosted overlay on the full-bleed canvas, float /
        // docked-right geometry toggled in its header). MOBILE stays in
        // "full" at every project age — no canvas below iPad width
        // (prohibition #13), the chat stage IS the page and products
        // deliver in the message flow (receipt + anchor cards, ADR-118).
        // Desktop projects already born (a transcript card, runs, or a
        // pending draft) mount straight in "panel" — the loading gate above
        // settles the driver before first render, so the hydrated first
        // frame never replays the morph.
        form={canvasCapable && worldLive ? "panel" : "full"}
        // The server-named lifecycle stamp (ADR-087 §2, Phase 1): the
        // dock's confirm-phase mount + Start gate read it — never a local
        // derivation.
        lifecycle={lifecycle}
        onPanelStateChange={setPanelState}
        canvasAvailable={canvasCapable}
        prompt={
          firstMessage?.text ??
          pendingBrief?.prompt ??
          (runActive ? latestRun?.context?.instruction : null) ??
          prompt ??
          ""
        }
        firstMessage={
          firstMessage
            ? {
                text: firstMessage.text,
                mentions: firstMessage.mentions ?? [],
                personaId: firstMessage.personaId,
              }
            : null
        }
        initialIntent={dockInitialIntent}
        initialRunId={
          // A node-originated run (ADR-058 — the card-face edit's
          // deterministic revision) never attaches to the dock: zero
          // messages, zero receipts — the node's own state cycle on the
          // canvas is the whole feedback.
          latestRun?.context?.origin === "node_revise"
            ? undefined
            : runActive
              ? latestRun.id
              : !pendingBrief && completedRun
                ? completedRun.id
                : undefined
        }
        onComplete={handleDockComplete}
        // A dock-started run (confirm / prose / 修订): refetch NOW — the
        // fresh latest_run flips runActive, the page SSE attaches, and the
        // live canvas (graph nodes filling in place, ADR-057) renders from
        // the first beat instead of arriving whole at terminal. The graph
        // rides the same fetch — a plan-turn can CREATE assets server-side
        // (declared-material promotion) whose nodes land in the same frame.
        onRunStarted={() => {
          // C5 相机律: the run fill's newborns land via the refetch loop —
          // arm an ensure-in-view beat toward where they settled. worldLive
          // (not hasRuns): the first run's start beat predates the refetched
          // latest_run, but the world is already live from the plan's dock.
          if (worldLive && canvasCapable) {
            setCameraBeat({ token: Date.now() })
          }
          void fetchResults()
        }}
        // K5 图先展示后运行: a plan dock / bail changes the draft graph
        // server-side — refetch so the lifecycle stamp's PLAN_READY flip
        // gate sees it (the desktop world must morph on the plan's
        // readiness, before any run; without this the flip only ever fired
        // on the first run and the chain preview never showed —
        // 2026-09-09 取证).
        // C5 相机律·dock 路径 (2026-09-29 用户拍板 — 确定性聚焦): this
        // callback's OWN fetchGraph response IS the arrival — diff the
        // newborn ids off it and center the cluster directly (zoom locked,
        // the centerRequest seat). Never the token machine's blind id-diff
        // window here: a racing unarmed fetch could absorb the delta and
        // the beat starved silently (the 2026-09-29「相机没跟新节点」走查).
        // Bail / restamp (zero newborn ids) never moves the camera; the
        // pre-birth world lets the mount's settle framing own the show.
        onDraftGraphChange={() => {
          const before = new Set((graph?.nodes ?? []).map((n) => n.id))
          void (async () => {
            const fresh = await fetchGraph()
            // worldLive reads the closure's PRE-dock stamp on the reveal
            // beat (the callback fires before the refetch re-renders) —
            // false there, so the reveal's first framing stays the settle
            // fit's own (the sole automatic fit); only LATER draft changes
            // (revision restamps on an already-live world) earn the
            // deterministic newborn-cluster focus (ADR-111 §6 / C5).
            if (!fresh || !worldLive || !canvasCapable) return
            const newbornIds = fresh.nodes
              .filter((n) => !before.has(n.id))
              .map((n) => n.id)
            if (newbornIds.length > 0) {
              setCenterRequest({ token: Date.now(), nodeIds: newbornIds })
            }
          })()
        }}
      />

      {publishOutput && (
        <PublishDialog
          output={publishOutput}
          open
          onOpenChange={(open) => {
            if (!open) setPublishOutput(null)
          }}
        />
      )}
    </div>
    </SoundMutexProvider>
  )
}
