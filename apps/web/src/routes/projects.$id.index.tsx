import { createFileRoute, useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { ArticleCard } from "@/components/results/ArticleCard"
import { CarouselCard } from "@/components/results/CarouselCard"
import { ClipCard } from "@/components/results/ClipCard"
import { ClipCardSkeleton } from "@/components/results/ClipCardSkeleton"
import { ClipDetailModal } from "@/components/results/ClipDetailModal"
import { DerivativeCardSkeleton } from "@/components/results/DerivativeCardSkeleton"
import { downloadOutput } from "@/components/results/downloadOutput"
import { GenerationOverlay, normalizeIntent, tasksFromRunContext, type DerivedRow, type GenerationOverlayHandle } from "@/components/generation/GenerationOverlay"
import { ResultsCanvas } from "@/components/flow/ResultsCanvas"
import type { FlowAssetAction, FlowAssetInfo, FlowOutputAction } from "@/components/flow/types"
import type { RunFlowAsset } from "@/components/flow/runFlow"
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

import type { IntentSlot, Output, PlaceholderRow, WorkflowStep, Project } from "@/lib/types"

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
  } | null
  cost: Record<string, number> | null
  steps: WorkflowStep[]
  created_at: string
  updated_at: string | null
}

interface PendingIntent {
  prompt: string
  /** Task-shaped on the API (the server upgrades legacy flat/slot rows on
   * read); typed loosely here and normalized at the overlay boundary. */
  intent: unknown
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
  pending_intent?: PendingIntent | null
  /** Live run's placeholder roster (ADR-051 B — server-projected). */
  placeholders?: PlaceholderRow[]
}

/** Tools (== node kinds, N-35) that own a results tab (ADR-028): the whole
 * chain's clip-side work (selection, whole-source materialization, the
 * transforms) lands on the clips tab; preprocess/persona/director/revise/
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
  const overlayRef = useRef<GenerationOverlayHandle>(null)
  /** The latest COMPLETED run snapshot — the canvas's terminal frame. The
   * sticky copy survives a later refinement run going active/failed (D9:
   * the canvas shows the current run + latest products); the live value
   * takes precedence the moment it exists, so the dock mounts in one pass
   * (no effect lag on refresh). */
  const [stickyCompletedRun, setStickyCompletedRun] = useState<WorkflowRun | null>(null)
  const [canvasAssets, setCanvasAssets] = useState<RunFlowAsset[]>([])

  // ── Product actions (ADR-041 D5/D8) ──────────────────────────────────
  // The canvas's product nodes ARE the cards: click sets the dock focus
  // (焦点注入) and opens the clip's detail modal; the action bar reports
  // download / publish. Both modals are the old card-face logic,
  // mounted as-is.
  const [detailOutput, setDetailOutput] = useState<Output | null>(null)
  const [publishOutput, setPublishOutput] = useState<Output | null>(null)
  const [focusedOutputId, setFocusedOutputId] = useState<string | null>(null)

  const fetchResults = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/results`)
      if (!res.ok) throw new Error("Project not found")
      setResults(await res.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project")
    } finally {
      setLoading(false)
    }
  }, [projectId])

  // Canvas assets carry titles/file urls (the /results asset list is a
  // lightweight status view) — the full asset endpoint, fetched once per
  // project and after every asset action (delete / reprocess).
  const [canvasAssetsReady, setCanvasAssetsReady] = useState(false)
  const fetchCanvasAssets = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/assets`, {
        toast: false,
      })
      if (res.ok) setCanvasAssets((await res.json()) as RunFlowAsset[])
    } catch {
      /* the canvas keeps the last asset set */
    } finally {
      setCanvasAssetsReady(true)
    }
  }, [projectId])

  const latestRun = results?.latest_run

  useEffect(() => {
    setLoading(true)
    fetchResults()
    fetchCanvasAssets()
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
    setCanvasAssets([])
    setCanvasAssetsReady(false)
    setDetailOutput(null)
    setPublishOutput(null)
    setFocusedOutputId(null)
  }, [projectId])

  // Re-point the modal/focus state at the freshest rows after every refetch
  // (polling and refinement turns replace output objects in place); a focus
  // whose product left the visible set clears itself.
  const outputsList = useMemo(() => results?.outputs ?? [], [results])
  useEffect(() => {
    const byId = new Map(outputsList.map((o) => [o.id, o]))
    setDetailOutput((prev) => (prev ? (byId.get(prev.id) ?? null) : null))
    setPublishOutput((prev) => (prev ? (byId.get(prev.id) ?? null) : null))
    setFocusedOutputId((prev) => (prev && !byId.has(prev) ? null : prev))
  }, [outputsList])

  const focusedOutputChip = useMemo(() => {
    const output = outputsList.find((o) => o.id === focusedOutputId)
    if (!output) return null
    return {
      id: output.id,
      label: outputMentionLabel(
        output,
        t(`chat.derivativeTypes.${output.type}`, {
          defaultValue: t("results.tabs.clips"),
        }),
      ),
    }
  }, [outputsList, focusedOutputId, t])

  // Canvas handlers are useCallback-stable (2026-08-19 二轮 R5): FlowView's
  // rfNodes/rfEdges memo keys on them — plain closures rebuilt the whole
  // graph on every unrelated re-render (SSE ticks, focus changes).
  const handleOutputClick = useCallback((output: Output) => {
    setFocusedOutputId(output.id)
    // 单击 = detail modal 旧逻辑原样 (D5): clips with a render open the
    // detail view; every product click also becomes the dock's focus.
    if (output.type === "clip" && output.files.video) setDetailOutput(output)
  }, [])

  const handleOutputAction = useCallback(async (output: Output, action: FlowOutputAction) => {
    if (action === "open") {
      handleOutputClick(output)
      return
    }
    if (action === "focus") {
      setFocusedOutputId(output.id)
      return
    }
    if (action === "download") downloadOutput(output)
    else if (action === "publish") setPublishOutput(output)
    else if (action === "delete") {
      const res = await apiDelete(`/api/v1/outputs/${output.id}`)
      if (!res.ok) return
      setDetailOutput((prev) => (prev?.id === output.id ? null : prev))
      setFocusedOutputId((prev) => (prev === output.id ? null : prev))
      await fetchResults()
    }
  }, [handleOutputClick, fetchResults])

  // Asset-node toolbar (2026-08-17 走查拍板): the surface owns the source
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
      if (res.ok) await Promise.all([fetchResults(), fetchCanvasAssets()])
    } else if (action === "reprocess") {
      const res = await apiPost(
        `/api/v1/projects/${projectId}/assets/${asset.id}/reprocess`,
        {}
      )
      if (res.ok) await Promise.all([fetchResults(), fetchCanvasAssets()])
    }
  }, [projectId, fetchResults, fetchCanvasAssets])

  // 点过程节点 = @workflow_step 指认 (D8): the chip lands in the dock's
  // input — the mention rides the next turn as a definite reference.
  const handleStepClick = useCallback((stepId: string, label: string) => {
    overlayRef.current?.insertMention({ type: "workflow_step", id: stepId, label })
  }, [])

  // Hover prompt 框 send (ADR-051 F): the card's revision ask rides the
  // dock's chat channel with the product pinned as the one-shot focus
  // (zero new execution channel — the ask is a plain chat turn).
  const handleRevise = useCallback((output: Output, text: string) => {
    overlayRef.current?.sendRevision(text, {
      id: output.id,
      label: outputMentionLabel(
        output,
        t(`chat.derivativeTypes.${output.type}`, {
          defaultValue: t("results.tabs.clips"),
        }),
      ),
    })
  }, [t])

  const completedRun =
    latestRun?.status === "completed" ? latestRun : stickyCompletedRun

  /** The dock's completion hand-off: refetch so the canvas / list world
   * shows the landed products. (The page's own SSE also refetches — this
   * covers the dock's watcher beating it.) */
  const handleOverlayComplete = async () => {
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

  const { project, prompt, outputs, pending_intent: pendingIntent } = results

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
      })
    : undefined

  const overlayInitialIntent = runActive
    ? normalizeIntent({
        tasks: runTasks.length ? runTasks : [{ tool: "select_clips", params: {} }],
        specific_instruction: latestRun?.context?.instruction,
      })
    : pendingIntent
      ? // A parked task book always wins — it IS the live confirmation
        // surface (a refinement book parked from any device must be the
        // book the panel edits and Start answers with, never the stale
        // completed run's).
        normalizeIntent(pendingIntent.intent)
      : completedRun
        ? completedRunIntent
        : undefined

  return (
    // Fullscreen canvas world (ADR-041 全屏化; ADR-051 画布优先): this route
    // lives OUTSIDE the _app layout — no sidebar / header / title block.
    // Floating chrome: the project menu (top-left) + the canvas's own zoom
    // pill (top-right, FlowView `controls`); the canvas fills the viewport,
    // the chat dock floats at the bottom (click-through above itself). App
    // chrome (theme / language / notifications) lives in the studio shell —
    // 2026-08-19 走查拍板, confirmed to cover MOBILE too (nearest entry =
    // back to /projects).
    <div className="relative flex h-dvh flex-col overflow-hidden bg-background">
      <div className="absolute left-3 top-3 z-30 md:left-4 md:top-4">
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
      {/* Top-right stays CANVAS chrome (2026-08-19 走查拍板): the zoom pill
          rides FlowView's `controls` prop inside the canvas; the home-
          inherited cluster (theme / language / notifications) left the
          fullscreen world — app chrome lives in the studio shell. */}

      {!isMobile ? (
        /* Canvas-first (ADR-051): the desktop page is ALWAYS the canvas —
           pre-run it carries the source assets; a live run's spine / plan /
           placeholder slots project onto it in place, products land as
           in-place fills. The completion beat = the growth-driven birth
           choreography (ADR-036 补记 3, FLORA-reconciled 2026-09-01): every
           node born while the surface watches enters staggered in compile
           order (placeholders materialize, fills birth in place), a running
           placeholder carries the FLORA wipe, and the hydrated first frame
           never replays. The canvas is FULL-BLEED — the dock is a
           completely floating layer above it, never a layout reservation
           (no safe-area padding: reserving space IS the occlusion). A node
           passing under the dock is panned back into view — the canvas is
           explore navigation. */
        <div className="min-h-0 flex-1">
          <ResultsCanvas
            className="h-full"
            assets={canvasAssets}
            steps={latestRun?.steps ?? []}
            outputs={outputs}
            placeholders={results?.placeholders ?? []}
            prompt={prompt || latestRun?.context?.instruction || null}
            // Birth baseline (ADR-036 补记 3): ready only when the initial
            // /results AND /assets have both settled for THIS project —
            // an early partial frame must not become the baseline (the
            // rest of the graph would "birth" on a plain refresh), and a
            // stale previous-project payload must not contaminate it.
            baselineReady={
              results?.project?.id === projectId && canvasAssetsReady
            }
            baselineKey={projectId}
            tourOutputId={resultsTourClipId}
            onOutputClick={handleOutputClick}
            onOutputAction={handleOutputAction}
            onRevise={handleRevise}
            onAssetAction={handleAssetAction}
            onStepClick={handleStepClick}
            focusedOutputId={focusedOutputId}
            onPaneClick={() => {
              // 点画布空白 = 回中性: history 收起 + 焦点清除 (D4/D8).
              overlayRef.current?.closeHistory()
              setFocusedOutputId(null)
            }}
          />
        </div>
      ) : (
        /* Mobile keeps the list world (prohibition #13 — no canvas below
           iPad width); the same chat dock floats over it. pt-16 clears the
           floating chrome; pb-36 keeps the last card above the dock. */
        <div className="min-h-0 flex-1 overflow-y-auto">
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

      <GenerationOverlay
        // Remount per project — the message machine's state (run id,
        // conversation) belongs to one project only.
        key={projectId}
        ref={overlayRef}
        projectId={projectId}
        prompt={
          firstMessage?.text ??
          pendingIntent?.prompt ??
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
        initialIntent={overlayInitialIntent}
        initialDerived={pendingIntent?.derived}
        initialRunId={
          runActive
            ? latestRun.id
            : !pendingIntent && completedRun
              ? completedRun.id
              : undefined
        }
        focusOutput={focusedOutputChip}
        onFocusChange={(id) => setFocusedOutputId(id)}
        onComplete={handleOverlayComplete}
        // A dock-started run (confirm / prose / 修订): refetch NOW — the
        // fresh latest_run flips runActive, the page SSE attaches, and the
        // run 期活画布 (placeholder materialization / wipe / fills) renders
        // from the first beat instead of arriving whole at terminal. The
        // assets endpoint rides along: a plan-turn can CREATE assets
        // server-side (declared-material promotion) after the page's
        // initial fetch — the canvas's source node comes from this list.
        onRunStarted={() => {
          void fetchResults()
          void fetchCanvasAssets()
        }}
      />

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
