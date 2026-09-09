import { createFileRoute, Link, useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ArrowLeft } from "lucide-react"
import { toast } from "sonner"

import { ArticleCard } from "@/components/results/ArticleCard"
import { CarouselCard } from "@/components/results/CarouselCard"
import { ClipCard } from "@/components/results/ClipCard"
import { ClipCardSkeleton } from "@/components/results/ClipCardSkeleton"
import { ClipDetailModal } from "@/components/results/ClipDetailModal"
import { DerivativeCardSkeleton } from "@/components/results/DerivativeCardSkeleton"
import { downloadOutput } from "@/components/results/downloadOutput"
import { outputFullText } from "@/components/results/outputText"
import { ChatDock, normalizeIntent, tasksFromRunContext, type DerivedRow, type ChatDockHandle } from "@/components/chat/ChatDock"
import { CreditsPill } from "@/components/credits/CreditsPill"
import { ResultsCanvas } from "@/components/flow/ResultsCanvas"
import type { FlowAssetAction, FlowAssetInfo, FlowOutputAction } from "@/components/flow/types"
import { PostCard } from "@/components/results/PostCard"
import { ProjectMenu } from "@/components/project/ProjectMenu"
import { PublishDialog } from "@/components/publish/PublishDialog"
import { QuotesCard } from "@/components/results/QuotesCard"
import { QuoteFrameCard } from "@/components/results/QuoteFrameCard"
import {
  ResultsTabs,
  type ResultsTab,
} from "@/components/results/ResultsTabs"
import { Button } from "@/components/ui/button"
import { Tour, type TourStep } from "@/components/ui/tour"
import { tourCopy, tourVersionOf, type TourStepDef } from "@/lib/tour"
import { apiDelete, apiFetch, apiPost, downloadFile, toAbsoluteUrl } from "@/lib/api"
import { outputMentionLabel } from "@/lib/mentions"
import { useIsMobile } from "@/hooks/use-mobile"
import { useRunEvents } from "@/lib/use-run-events"
import { cn } from "@/lib/utils"

import type { IntentSlot, Output, ProjectGraph, WorkflowStep, Project } from "@/lib/types"

/** A clip counts as tour-ready once its MP4 exists and no render is in
 * flight — the same condition ClipCard uses to leave its rendering state. */
const isClipReady = (o: Output) =>
  o.type === "clip" &&
  !!o.files.video &&
  o.render_status !== "pending" &&
  o.render_status !== "rendering"

/** First-visit results tour: separate seen key from the composer tour, same
 * content-hash rule (lib/tour.ts) — any step or copy change replays once. */
const RESULTS_TOUR_KEY = "repurposer-results-tour-seen"

const RESULTS_TOUR_STEPS: TourStepDef[] = [
  {
    target: "[data-tour='results-score']",
    titleKey: "tour.results.scoreTitle",
    descKey: "tour.results.scoreDesc",
    side: "bottom",
  },
  {
    target: "[data-tour='results-video']",
    titleKey: "tour.results.videoTitle",
    descKey: "tour.results.videoDesc",
    side: "bottom",
  },
  {
    target: "[data-tour='results-menu']",
    titleKey: "tour.results.menuTitle",
    descKey: "tour.results.menuDesc",
    side: "bottom",
    align: "end",
  },
]

const RESULTS_TOUR_VERSION = tourVersionOf(RESULTS_TOUR_STEPS, tourCopy.results)

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
   * on ledger-only rows (an ask-turn write — no book parked, ADR-052 B2). */
  intent: unknown | null
  /** The merged brief ledger (预填评审卡, ADR-052 B3) — the plan card's
   * slot rows; typed loosely here and normalized at the dock boundary. */
  brief?: unknown
  /** Why the book needs a human check — confirmation is `reasons.length > 0`
   * (the API's redundant needs_clarification bool was retired, B4). */
  reasons?: string[]
  persona_id?: string | null
  /** The server-compiled "what you'll get" preview rows (ADR-043). */
  derived?: DerivedRow[]
}

interface ProjectResults {
  project: Project
  prompt: string | null
  outputs: Output[]
  latest_run: WorkflowRun | null
  assets?: AssetStatusEntry[]
  pending_brief?: PendingBrief | null
}

/** Tools (== node kinds, N-35) that own a results tab (ADR-028): the whole
 * chain's clip-side work (selection, whole-source materialization, the
 * transforms) lands on the clips tab; preprocess/persona/plan-prelude/revise/
 * render nodes drive the stepper, not a tab. */
const NODE_KIND_TO_TAB: Record<string, ResultsTab> = {
  select_clips: "clips",
  materialize_source: "clips",
  translate_clip: "clips",
  dub_clip: "clips",
  remove_filler: "clips",
  add_music: "clips",
  write_post: "post",
  write_quotes: "quotes",
  write_carousel: "carousel",
  write_article: "article",
}

/** The producing tool a tab's retry re-runs (a retry replays the producer
 * with its confirmed params — the chain's transforms don't ride it). */
const TAB_TO_RETRY_TOOL: Record<ResultsTab, string> = {
  clips: "select_clips",
  post: "write_post",
  quotes: "write_quotes",
  // Frame cards ride the quotes chain — a quoteFrame retry replays
  // write_quotes, which re-materializes the frame/composite siblings.
  quoteFrame: "write_quotes",
  carousel: "write_carousel",
  article: "write_article",
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
  const [activeTab, setActiveTab] = useState<ResultsTab>("clips")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<Partial<Record<ResultsTab, boolean>>>({})
  const [resultsTourOpen, setResultsTourOpen] = useState(false)
  const tabInitializedRef = useRef(false)
  const resultsTourCheckedRef = useRef(false)
  /** The tour's anchor poll — survives effect re-runs, cleared on success
   * or unmount only. */
  const tourPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(
    () => () => {
      if (tourPollRef.current) clearInterval(tourPollRef.current)
    },
    []
  )

  // ── Results canvas (ADR-041; ADR-051 画布优先) ───────────────────────
  // Desktop (≥768px = iPad up, D1/D10): the page is ALWAYS the canvas + the
  // chat dock — pre-run assets, the live run's projection, and the terminal
  // frame all render on it; mobile keeps the list world (prohibition #13).
  const isMobile = useIsMobile()
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
  // The canvas's product nodes ARE the cards: click sets the dock focus
  // (焦点注入) and opens the clip's detail modal; the action bar reports
  // download / publish. Both modals are the old card-face logic,
  // mounted as-is.
  const [detailOutput, setDetailOutput] = useState<Output | null>(null)
  const [publishOutput, setPublishOutput] = useState<Output | null>(null)
  const [selectedOutputId, setSelectedOutputId] = useState<string | null>(null)

  const fetchGraph = useCallback(async () => {
    const graphRes = await apiFetch(`/api/v1/projects/${projectId}/graph`, { toast: false })
    if (graphRes.ok) setGraph((await graphRes.json()) as ProjectGraph)
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project")
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const latestRun = results?.latest_run
  // The page's two-form choreography driver (2026-09-02 形态机; 2026-09-08
  // K5 拓宽): pre-generation it is the centered fullscreen chat + back pill
  // (no canvas); the GRAPH WORLD's arrival flips it — the chat stage fades
  // out in place (300ms), the canvas fades in on a slight delay, and the
  // back pill crossfades into the full ProjectMenu, all on one beat
  // (2026-09-06 fade-simplified: the old grid-rows collapse read as the
  // chat flying up, user-retired). The graph world arrives on EITHER the
  // first run (hasRuns) OR the docked task book's draft graph
  // (hasDraftGraph — 图先展示后运行, ADR-057 K5: the canvas previews the
  // whole chain as draft nodes before a credit moves; bail tears it down
  // and the world morphs back). The loading/error early returns below
  // guarantee this is settled at first render, so projects WITH runs (or a
  // pending draft) mount straight in the dock world (the hydrated first
  // frame never replays the morph).
  const hasRuns = latestRun != null
  const hasDraftGraph = (graph?.nodes ?? []).some((n) => n.state === "draft")
  const graphLive = hasRuns || hasDraftGraph
  // The driver forks per surface (prohibition #13 — mobile has no canvas):
  // the desktop world morphs on the draft graph's arrival; mobile waits
  // for the first run (its confirm beat stays in the dock).
  const worldLive = isMobile ? hasRuns : graphLive
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
    graphLive && !isMobile && !panelState.hidden && panelState.docked

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

  // Cross-project navigation (same route, new params — no remount): every
  // project-scoped latch resets, or the previous project's canvas/dock
  // would bleed into the new page while its results load.
  useEffect(() => {
    setStickyCompletedRun(null)
    setGraph(null)
    setDetailOutput(null)
    setPublishOutput(null)
    setSelectedOutputId(null)
  }, [projectId])

  // Re-point the modal/focus state at the freshest rows after every refetch
  // (polling and refinement turns replace output objects in place); a focus
  // whose product left the visible set clears itself.
  const outputsList = useMemo(() => results?.outputs ?? [], [results])
  useEffect(() => {
    const byId = new Map(outputsList.map((o) => [o.id, o]))
    setDetailOutput((prev) => (prev ? (byId.get(prev.id) ?? null) : null))
    setPublishOutput((prev) => (prev ? (byId.get(prev.id) ?? null) : null))
    setSelectedOutputId((prev) => (prev && !byId.has(prev) ? null : prev))
  }, [outputsList])

  // Canvas handlers are useCallback-stable (2026-08-19 二轮 R5): FlowView's
  // rfNodes/rfEdges memo keys on them — plain closures rebuilt the whole
  // graph on every unrelated re-render (SSE ticks, selection changes).
  const handleOutputClick = useCallback((output: Output) => {
    // Click = canvas SELECTION (the selected ring + the dossier swap-in —
    // ADR-058: pointing at a product in chat is an @mention, no hidden
    // focus state) + the clip's player modal. Text products (post /
    // article) open NOTHING — the card itself is the reader (in-place
    // scroll + inline edit since 2026-09-08); the dossier carries the
    // details.
    setSelectedOutputId(output.id)
    if (output.type === "clip" && output.files.video) setDetailOutput(output)
  }, [])

  const handleOutputAction = useCallback(async (output: Output, action: FlowOutputAction) => {
    if (action === "open") {
      handleOutputClick(output)
      return
    }
    if (action === "focus") {
      // 在对话中指认 = an @output chip in the dock's editor (ADR-058: the
      // one pointing mechanism — visible in the user's own sentence, the
      // chip's three laws hold). No hidden focus state.
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
      setDetailOutput((prev) => (prev?.id === output.id ? null : prev))
      setSelectedOutputId((prev) => (prev === output.id ? null : prev))
      await fetchResults()
    }
  }, [handleOutputClick, fetchResults, t])

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

  // Canvas draft-confirm card Start (ADR-057 K5 — 确认 = 节点锚定): the
  // desktop confirm beat rides the dock's ONE start path (the task_book
  // question's start answer; guards and failure surfaces live in the dock).
  const handleDraftConfirm = useCallback(() => {
    dockRef.current?.startPendingBook()
  }, [])

  const completedRun =
    latestRun?.status === "completed" ? latestRun : stickyCompletedRun

  /** The dock's completion hand-off: refetch so the canvas / list world
   * shows the landed products. (The page's own SSE also refetches — this
   * covers the dock's watcher beating it.) */
  const handleDockComplete = async () => {
    await fetchResults()
  }

  // First-visit results tour. Fires whenever a ready clip exists and no run
  // is live — no matter how the user got here (fresh generation or straight
  // from the projects list). Seen flag is its own localStorage key.
  // Anchors: the canvas's first ready product node on desktop (ADR-041 —
  // data-tour="results-*" live on the output card), the clip card in the
  // mobile list world.
  useEffect(() => {
    if (resultsTourCheckedRef.current) return
    if (loading || !results) return
    if (runActive) return
    if (!isMobile && !completedRun) return
    if (!results.outputs.some(isClipReady)) return
    resultsTourCheckedRef.current = true
    try {
      if (window.localStorage.getItem(RESULTS_TOUR_KEY) === RESULTS_TOUR_VERSION)
        return
    } catch {
      return // storage unavailable — tour simply never auto-opens
    }
    if (isMobile && activeTab !== "clips") setActiveTab("clips")
    // The canvas's node DOM lands a paint after the data (xyflow mounts
    // client-only) — open once the anchor actually exists; if it never
    // does, the tour closes itself silently (missing targets auto-skip).
    // The poll lives in a ref, NOT the effect cleanup: a results refetch
    // (the 2.5s render polling) re-runs this effect and a cleanup would
    // kill the poll before the anchor appears.
    let tries = 0
    tourPollRef.current = setInterval(() => {
      tries += 1
      if (document.querySelector("[data-tour='results-menu']") || tries > 20) {
        if (tourPollRef.current) clearInterval(tourPollRef.current)
        tourPollRef.current = null
        setResultsTourOpen(true)
      }
    }, 100)
  }, [loading, results, runActive, activeTab, isMobile, completedRun])

  const markResultsTourSeen = () => {
    try {
      window.localStorage.setItem(RESULTS_TOUR_KEY, RESULTS_TOUR_VERSION)
    } catch {
      // ignore — worst case the tour shows again next visit
    }
  }

  // Default to the first requested output tab once, when a generation is running.
  const runTasks = tasksFromRunContext(latestRun?.context)
  useEffect(() => {
    if (tabInitializedRef.current) return
    if (!runTasks.length) return
    const tab = NODE_KIND_TO_TAB[runTasks[0].tool]
    if (tab) {
      setActiveTab(tab)
      tabInitializedRef.current = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestRun?.context])

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

  const nodes = sseActive ? sse.steps : (latestRun?.steps ?? [])
  // Skeleton count for the clips pane: the confirmed count when the chain
  // selects clips; ONE for a whole-video chain (transforms without
  // select_clips — the compile-injected materialize_source makes one
  // whole-source clip); writers-only chains never render the pane. The bare
  // fallback mirrors the server's SelectClipsParams default (count unnamed
  // → 3) — legacy 5-default runs are all settled and never replay skeletons.
  const clipsTask = runTasks.find((task) => task.tool === "select_clips")
  const clipsTaskCount = clipsTask?.params?.count
  const wholeVideoChain =
    !clipsTask && runTasks.some((task) => NODE_KIND_TO_TAB[task.tool] === "clips")
  const clipCount =
    typeof clipsTaskCount === "number" ? clipsTaskCount : wholeVideoChain ? 1 : 3

  const requestedTabs = Array.from(
    new Set(
      runTasks.map((task) => NODE_KIND_TO_TAB[task.tool]).filter(Boolean)
    )
  ) as ResultsTab[]

  // When the run itself failed, nodes that never reached a terminal state
  // are dead too — present them as failed (with a retry) instead of skeletons.
  const runFailed = latestRun?.status === "failed"

  const runningTabs = nodes
    .filter(
      (n) =>
        NODE_KIND_TO_TAB[n.kind] &&
        !runFailed &&
        (n.status === "running" || n.status === "pending")
    )
    .map((n) => NODE_KIND_TO_TAB[n.kind])

  const failedTabs = nodes
    .filter(
      (n) =>
        NODE_KIND_TO_TAB[n.kind] &&
        (n.status === "failed" || (runFailed && n.status !== "done"))
    )
    .map((n) => NODE_KIND_TO_TAB[n.kind])

  const handleRetry = async (tab: ResultsTab) => {
    if (!results) return
    setRetrying((prev) => ({ ...prev, [tab]: true }))
    try {
      const ctx = latestRun?.context
      // 整类重做 = re-run the tab's own chain verbatim (ADR-043): the clips
      // family is the chain's clips-family tasks in order (a whole-video
      // chain has NO select_clips — inventing one would swap the product
      // from "subtitled whole video" to "highlight cuts"); text families
      // are their single writer task. Chat-scoped params (target_output_id)
      // are stripped — a full run deletes the rows they point at.
      const family =
        tab === "clips"
          ? runTasks.filter((task) => NODE_KIND_TO_TAB[task.tool] === "clips")
          : runTasks.filter((task) => task.tool === TAB_TO_RETRY_TOOL[tab])
      const tasks = (family.length > 0 ? family : [{ tool: TAB_TO_RETRY_TOOL[tab], params: {} }]).map(
        (task) => {
          const params = { ...(task.params ?? {}) }
          delete params.target_output_id
          return { tool: task.tool, params }
        },
      )
      await apiPost(`/api/v1/projects/${projectId}/generate`, {
        tasks,
        target_language: ctx?.target_language || results.project.language || "en",
        instruction: ctx?.instruction || undefined,
        tone_settings: ctx?.tone_settings || undefined,
      })
      await fetchResults()
    } catch (e) {
      console.error("Retry failed", e)
    } finally {
      setRetrying((prev) => ({ ...prev, [tab]: false }))
    }
  }

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

  const { project, prompt, outputs, pending_brief: pendingBrief } = results

  // outputs holds the project's current products (targeted runs update in
  // place; full runs delete prior rows), so no per-run filtering is needed.
  const clips = outputs.filter((o) => o.type === "clip")
  const posts = outputs.filter((o) => o.type === "post")
  const quotes = outputs.filter((o) => o.type === "quotes")
  const quoteFrames = outputs.filter((o) => o.type === "quote_frame")
  const carousels = outputs.filter((o) => o.type === "carousel")
  const articles = outputs.filter((o) => o.type === "article")

  // Top pick: the highest recommendation score in the batch gets the accent
  // badge (the score's job is triage — which clip is most worth posting first).
  const topClipScore = Math.max(
    0,
    ...clips.map((c) => (typeof c.score?.value === "number" ? c.score.value : 0))
  )

  // The results tour anchors to one fully-rendered clip — prefer the first
  // that also has a score, so all three targets exist on the same card.
  const readyClips = clips.filter(isClipReady)
  const resultsTourClipId = (
    readyClips.find((c) => typeof c.score?.value === "number") ?? readyClips[0]
  )?.id

  const counts = {
    clips: clips.length,
    post: posts.length,
    quotes: quotes.length,
    quoteFrame: quoteFrames.length,
    carousel: carousels.length,
    article: articles.length,
  }

  const visibleTabs = Array.from(
    new Set<ResultsTab>([
      ...requestedTabs,
      ...(Object.keys(counts) as ResultsTab[]).filter((tab) => (counts[tab] ?? 0) > 0),
    ])
  )

  // The shown tab is always clamped INTO the visible set (终审 P1-2): the
  // auto-select effect only knows NODE_KIND_TO_TAB, so a run whose first
  // task is unmapped (revise_script — every hover-框 revision's tool)
  // leaves activeTab pointing at a tab that isn't rendered — the list
  // world then shows the wrong empty state under a one-tab bar. Derived,
  // never written back: the user's own clicks always land in the set.
  const shownTab: ResultsTab = visibleTabs.includes(activeTab)
    ? activeTab
    : (visibleTabs[0] ?? "clips")

  const isOutputFailed = (tab: ResultsTab) => failedTabs.includes(tab)
  const isOutputRunning = (tab: ResultsTab) => runningTabs.includes(tab)

  // Results teaching tour: score → video area → "···" menu. Built per
  // render from the static config so a language switch re-labels the steps.
  const resultsTourSteps: TourStep[] = RESULTS_TOUR_STEPS.map((step) => ({
    target: step.target,
    side: step.side,
    align: step.align,
    title: t(step.titleKey),
    description: t(step.descKey),
  }))

  const renderSkeletons = (tab: ResultsTab) => {
    if (tab === "clips") {
      return (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: clipCount }).map((_, i) => (
            <ClipCardSkeleton key={i} />
          ))}
        </div>
      )
    }
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <DerivativeCardSkeleton />
      </div>
    )
  }

  const renderFailed = (tab: ResultsTab) => {
    const node = nodes.find(
      (n) =>
        NODE_KIND_TO_TAB[n.kind] === tab &&
        (n.status === "failed" || (runFailed && n.status !== "done"))
    )
    return (
      <div className="rounded-lg bg-muted p-8 text-center">
        <p className="text-sm text-destructive">
          {node?.error || latestRun?.error || t("results.retryFailed")}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          disabled={retrying[tab]}
          onClick={() => handleRetry(tab)}
        >
          {retrying[tab] ? t("common.loading") : t("results.retry")}
        </Button>
      </div>
    )
  }

  const renderTabContent = () => {
    switch (shownTab) {
      case "clips":
        if (isOutputFailed("clips")) return renderFailed("clips")
        if (clips.length === 0 && isOutputRunning("clips")) {
          return renderSkeletons("clips")
        }
        if (clips.length === 0) {
          return <EmptyState text={t("results.empty.clips")} />
        }
        return (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {clips.map((clip) => (
              <ClipCard
                key={clip.id}
                output={clip}
                isTopPick={
                  topClipScore > 0 && clip.score?.value === topClipScore
                }
                tourTargets={clip.id === resultsTourClipId}
              />
            ))}
          </div>
        )
      case "post":
        if (isOutputFailed("post")) return renderFailed("post")
        if (posts.length === 0 && isOutputRunning("post")) {
          return renderSkeletons("post")
        }
        if (posts.length === 0) {
          return <EmptyState text={t("results.empty.post")} />
        }
        return (
          <div className="grid gap-4 md:grid-cols-2">
            {posts.map((o) => (
              <PostCard key={o.id} output={o} onRegenerate={fetchResults} />
            ))}
          </div>
        )
      case "quotes":
        if (isOutputFailed("quotes")) return renderFailed("quotes")
        if (quotes.length === 0 && isOutputRunning("quotes")) {
          return renderSkeletons("quotes")
        }
        if (quotes.length === 0) {
          return <EmptyState text={t("results.empty.quotes")} />
        }
        return (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {quotes.map((o) => (
              <QuotesCard key={o.id} output={o} onRegenerate={fetchResults} />
            ))}
          </div>
        )
      case "quoteFrame":
        // Frame cards are byproducts of the quotes chain — the running /
        // failed state lives on the quotes tab; this tab is products-only.
        if (quoteFrames.length === 0 && isOutputRunning("quotes")) {
          return renderSkeletons("quoteFrame")
        }
        if (quoteFrames.length === 0) {
          return <EmptyState text={t("results.empty.quoteFrame")} />
        }
        return (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {quoteFrames.map((o) => (
              <QuoteFrameCard key={o.id} output={o} />
            ))}
          </div>
        )
      case "carousel":
        if (isOutputFailed("carousel")) return renderFailed("carousel")
        if (carousels.length === 0 && isOutputRunning("carousel")) {
          return renderSkeletons("carousel")
        }
        if (carousels.length === 0) {
          return <EmptyState text={t("results.empty.carousel")} />
        }
        return (
          <div className="grid gap-4 md:grid-cols-2">
            {carousels.map((o) => (
              <CarouselCard key={o.id} output={o} onRegenerate={fetchResults} />
            ))}
          </div>
        )
      case "article":
        if (isOutputFailed("article")) return renderFailed("article")
        if (articles.length === 0 && isOutputRunning("article")) {
          return renderSkeletons("article")
        }
        if (articles.length === 0) {
          return <EmptyState text={t("results.empty.article")} />
        }
        return (
          <div className="grid gap-4 md:grid-cols-2">
            {articles.map((o) => (
              <ArticleCard key={o.id} output={o} onRegenerate={fetchResults} />
            ))}
          </div>
        )
    }
  }

  // ── The one chat dock (ADR-051) ──────────────────────────────────────
  // The page is ALWAYS canvas (desktop) / list world (mobile) + the chat
  // dock — project state drives the dock's form: a parked task book docks
  // the confirm panel, a live run attaches the step flow, a completed run
  // lands on the results conversation. One mounted instance across all
  // forms — the input group is never remounted between them.

  /** The dock's book-summary line, rebuilt from the completed run's context
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
      ? // A parked task book always wins — it IS the live confirmation
        // surface (a refinement book parked from any device must be the
        // book the panel edits and Start answers with, never the stale
        // completed run's). A ledger-only row (intent null — an ask-turn
        // write, ADR-052 B2) parks no book: fall through.
        normalizeIntent(pendingBrief.intent)
      : completedRun
        ? completedRunIntent
        : undefined

  return (
    // Fullscreen canvas world (ADR-041 全屏化; ADR-051 画布优先): this route
    // lives OUTSIDE the _app layout — no sidebar / header / title block.
    // Floating chrome: the project menu (top-left) + the canvas's own zoom
    // pill (top-right, FlowView `controls`); the canvas fills the viewport,
    // the chat dock floats at the bottom on mobile / docks as the right
    // panel on desktop (2026-09-06 三形态机: md+ = flex row, the panel is an
    // in-flow column and the canvas makes room — FLORA docked mode). App
    // chrome (theme / language / notifications) lives in the studio shell —
    // 2026-08-19 走查拍板, confirmed to cover MOBILE too (nearest entry =
    // back to /projects).
    <div className="relative flex h-dvh flex-col overflow-hidden bg-background">
      {/* Top-left chrome — a TWO-FORM machine (2026-09-02 形态机, driven by
          worldLive): pre-generation it is a plain back pill (icon + Projects);
          the graph world's arrival (first run OR the docked book's draft
          graph, desktop) crossfades it into the full ProjectMenu (brand
          mark + title + ops). Both are stacked in one slot — the active
          form in flow, the inactive one absolutely overlaid — so the
          crossfade never shifts layout. z-[60]: above the ChatDock's z-50
          root — in the full form its stage covers the page and would
          otherwise swallow the pill's clicks. */}
      <div className="absolute left-3 top-3 z-[60] md:left-4 md:top-4">
        <div
          className={cn(
            "transition-[opacity,transform] duration-500 ease-out motion-reduce:transition-none",
            worldLive
              ? "opacity-100"
              : "pointer-events-none absolute left-0 top-0 -translate-x-2 opacity-0"
          )}
          aria-hidden={!worldLive}
        >
          <ProjectMenu
            projectId={project.id}
            title={project.title}
            runActive={runActive}
            onRenamed={(title) =>
              setResults((prev) =>
                prev ? { ...prev, project: { ...prev.project, title } } : prev
              )
            }
            onDeleted={() => navigate({ to: "/projects" })}
          />
        </div>
        {/* The pre-generation form — mirrors the ProjectMenu pill anatomy
            (dock-surface h-9 hairline frosted pill), one quiet hover fill. */}
        <div
          className={cn(
            "transition-[opacity,transform] duration-500 ease-out motion-reduce:transition-none",
            worldLive
              ? "pointer-events-none absolute left-0 top-0 -translate-x-2 opacity-0"
              : "opacity-100"
          )}
          aria-hidden={worldLive}
        >
          <Link
            to="/projects"
            tabIndex={worldLive ? -1 : 0}
            className="dock-surface flex h-9 items-center gap-1.5 rounded-md pl-2 pr-3 text-sm ring-1 ring-foreground/10 transition-colors hover:bg-accent"
          >
            <ArrowLeft className="h-4 w-4" />
            {t("projectMenu.backShort")}
          </Link>
        </div>
      </div>
      {/* Top-right stays CANVAS chrome (2026-08-19 走查拍板): the zoom pill
          rides FlowView's `controls` prop inside the canvas; the home-
          inherited cluster (theme / language / notifications) left the
          fullscreen world — app chrome lives in the studio shell. */}

      {!isMobile ? (
        /* Canvas-first (ADR-051; ADR-057 K3 直读): the desktop page is
           ALWAYS the canvas — the persistent graph read directly (nodes =
           graph rows: assets at upload, run fills in place, draft estimate
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
           navigation. The whole canvas is gated on graphLive (2026-09-02
           形态机; K5 拓宽): pre-generation it is invisible + inert (the
           full-form chat stage owns the page); the graph world's arrival
           (first run OR the docked book's draft graph) fades it in on the
           same beat as the stage's fade-out — 500ms on a 150ms delay
           (2026-09-06 fade-simplified). */
        <div
          className={cn(
            "min-h-0 flex-1 transition-opacity duration-500 delay-150 ease-out motion-reduce:transition-none",
            !graphLive && "pointer-events-none opacity-0"
          )}
        >
          <ResultsCanvas
            className="h-full"
            controlsClassName={panelCoversCorner ? "md:!mr-[504px]" : undefined}
            graph={graph}
            // The settle key's visibility half (2026-09-06): the canvas is
            // gated on graphLive, so initial framing joins it with the
            // baseline — partial fetch frames never frame.
            visible={graphLive}
            // Birth baseline (ADR-036 补记 3): ready only when the initial
            // /results AND /graph have both settled for THIS project —
            // an early partial frame must not become the baseline (the
            // rest of the graph would "birth" on a plain refresh), and a
            // stale previous-project payload must not contaminate it.
            baselineReady={
              results?.project?.id === projectId && graph != null
            }
            baselineKey={projectId}
            tourOutputId={resultsTourClipId}
            steps={latestRun?.steps ?? []}
            onOutputClick={handleOutputClick}
            onOutputAction={handleOutputAction}
            onNodeRevise={handleGraphRevise}
            onDraftConfirm={handleDraftConfirm}
            onAssetAction={handleAssetAction}
            selectedOutputId={selectedOutputId}
            onPaneClick={() => {
              // 点画布空白 = 回中性: history 收起 + 选中清除.
              dockRef.current?.closeHistory()
              setSelectedOutputId(null)
            }}
          />
        </div>
      ) : (
        /* Mobile keeps the list world (prohibition #13 — no canvas below
           iPad width); the same chat dock floats over it. pt-16 clears the
           floating chrome; pb-36 keeps the last card above the dock. Same
           hasRuns gate as the canvas — the list fades in with the first
           run (same 500ms/150ms-delay beat as the stage's fade-out). */
        <div
          className={cn(
            "min-h-0 flex-1 overflow-y-auto transition-opacity duration-500 delay-150 ease-out motion-reduce:transition-none",
            !hasRuns && "pointer-events-none opacity-0"
          )}
        >
          <div className="mx-auto w-full max-w-7xl space-y-4 px-4 pb-36 pt-16">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <ResultsTabs
                active={shownTab}
                onChange={setActiveTab}
                counts={counts}
                visible={visibleTabs}
                running={runningTabs}
                failed={failedTabs}
              />
            </div>
            <div>{renderTabContent()}</div>
          </div>
        </div>
      )}

      <ChatDock
        // Remount per project — the message machine's state (run id,
        // conversation) belongs to one project only.
        key={projectId}
        ref={dockRef}
        projectId={projectId}
        // The three-form machine (2026-09-06, FLORA-aligned; K5 拓宽): pre-
        // generation the dock is the centered fullscreen chat; the GRAPH
        // WORLD's arrival morphs it into the DESKTOP panel ("panel" — a
        // frosted overlay on the full-bleed canvas, float / docked-right
        // geometry toggled in its header) or the MOBILE bottom dock
        // ("dock", unchanged). The desktop world arrives on the first run
        // OR the docked book's draft graph (图先展示后运行); mobile has no
        // canvas (prohibition #13) and waits for the first run. The stage
        // fades out in place, the canvas fades in on a slight delay on the
        // same beat. Projects WITH runs (or a pending draft) mount straight
        // in "panel"/"dock" — the loading gate above settles the driver
        // before first render, so the hydrated first frame never replays
        // the morph.
        form={isMobile ? (hasRuns ? "dock" : "full") : graphLive ? "panel" : "full"}
        onPanelStateChange={setPanelState}
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
        initialBrief={pendingBrief?.brief}
        initialDerived={pendingBrief?.derived}
        initialReasons={pendingBrief?.reasons}
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
        // rides the same fetch — a book-turn can CREATE assets server-side
        // (declared-material promotion) whose nodes land in the same frame.
        onRunStarted={() => {
          void fetchResults()
        }}
        // K5 图先展示后运行: a book dock / bail changes the draft graph
        // server-side — refetch so the `hasDraftGraph` flip gate sees it
        // (the desktop world must morph on the book's arrival, before any
        // run; without this the flip only ever fired on the first run and
        // the chain preview never showed — 2026-09-09 取证).
        onDraftGraphChange={() => {
          void fetchGraph()
        }}
      />

      {/* The credits balance pill (BILLING §7 read surface, 2026-09-06) —
          bottom-left on the desktop project page: the one surface where
          credits are spent AND no studio shell carries the account console.
          Graph-world only (the pre-run fullscreen chat owns the bottom row —
          the draft world already shows the canvas, K5); the pill itself is
          hidden below md (the mobile dock owns the small screen's bottom
          edge). refreshKey rides the latest run's id+status — a run's
          hold/capture settles server-side and the pill refetches on the
          flip. */}
      {worldLive && (
        <CreditsPill
          refreshKey={latestRun ? `${latestRun.id}:${latestRun.status}` : "idle"}
        />
      )}

      {detailOutput && (
        <ClipDetailModal
          output={detailOutput}
          open
          onOpenChange={(open) => {
            if (!open) setDetailOutput(null)
          }}
          onRegenerate={fetchResults}
        />
      )}

      {publishOutput && (
        <PublishDialog
          output={publishOutput}
          open
          onOpenChange={(open) => {
            if (!open) setPublishOutput(null)
          }}
        />
      )}

      <Tour
        steps={resultsTourSteps}
        open={resultsTourOpen}
        onOpenChange={setResultsTourOpen}
        onComplete={markResultsTourSeen}
        onSkip={markResultsTourSeen}
      />
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">
      {text}
    </div>
  )
}
