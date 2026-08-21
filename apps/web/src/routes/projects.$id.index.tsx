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
import { useReducedMotion } from "@/lib/use-reduced-motion"
import { useRunEvents } from "@/lib/use-run-events"

import type { IntentSlot, Output, WorkflowStep, Project } from "@/lib/types"

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
  // overlay=chat is the canonical conversation surface; "intent" is the
  // retired spelling (pre unification) — tolerated on read.
  const search = Route.useSearch() as { overlay?: "chat" | "intent" | "run" }
  // The composer hands its draft over via router state: the overlay chat
  // sends it as the first /chat message (intent-surface-unification W2).
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

  // ── Results canvas (ADR-041) ─────────────────────────────────────────
  // Desktop (≥768px = iPad up, D1/D10): the terminal state is the results
  // canvas + the chat dock; mobile keeps the list world (prohibition #13).
  const isMobile = useIsMobile()
  const reducedMotion = useReducedMotion()
  const overlayRef = useRef<GenerationOverlayHandle>(null)
  /** The latest COMPLETED run snapshot — the canvas's data source. The
   * sticky copy survives a later refinement run going active/failed (D9:
   * the canvas shows the current run + latest products); the live value
   * takes precedence the moment it exists, so the dock mounts in one pass
   * (no effect lag on refresh). */
  const [stickyCompletedRun, setStickyCompletedRun] = useState<WorkflowRun | null>(null)
  /** Birth-replay gate (prohibition #5): set only when THIS page session
   * watched the run go live → terminal; every other entry renders the
   * final frame instantly. */
  const [witnessedRunId, setWitnessedRunId] = useState<string | null>(null)
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
  const fetchCanvasAssets = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/assets`, {
        toast: false,
      })
      if (res.ok) setCanvasAssets((await res.json()) as RunFlowAsset[])
    } catch {
      /* the canvas keeps the last asset set */
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

  // Attach-mode overlay (?overlay=run): latch the run id once an active run
  // is seen, and keep the overlay mounted on it until IT navigates away.
  // Gating the render on live `runActive` would unmount the overlay mid-flow
  // the moment this page's own SSE refetch flips the run to completed —
  // before the overlay's terminal handler can play the收官转场.
  const [attachRunId, setAttachRunId] = useState<string | null>(null)
  const attachableRunId = runActive && latestRun ? latestRun.id : null
  useEffect(() => {
    if (search.overlay === "run" && attachableRunId) {
      setAttachRunId(attachableRunId)
    }
  }, [search.overlay, attachableRunId])
  const closeAttachOverlay = () => {
    setAttachRunId(null)
    navigate({
      to: "/projects/$id",
      params: { id: projectId },
      replace: true,
    })
  }

  // The completed-run snapshot + the witnessed flag (page-side detection:
  // this session saw the SAME run go active → completed — e.g. the attach
  // flow, where the page's own SSE refetch beats the overlay's hand-off).
  const prevRunRef = useRef<{ id: string; status: string } | null>(null)
  useEffect(() => {
    if (!latestRun) return
    const prev = prevRunRef.current
    if (latestRun.status === "completed") {
      setStickyCompletedRun(latestRun)
      if (
        prev?.id === latestRun.id &&
        (prev.status === "pending" || prev.status === "running")
      ) {
        setWitnessedRunId(latestRun.id)
      }
    }
    prevRunRef.current = { id: latestRun.id, status: latestRun.status }
  }, [latestRun])

  // Cross-project navigation (same route, new params — no remount): every
  // project-scoped latch resets, or the previous project's canvas/dock
  // would bleed into the new page while its results load.
  useEffect(() => {
    setStickyCompletedRun(null)
    setWitnessedRunId(null)
    setCanvasAssets([])
    setDetailOutput(null)
    setPublishOutput(null)
    setFocusedOutputId(null)
    prevRunRef.current = null
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

  const completedRun =
    latestRun?.status === "completed" ? latestRun : stickyCompletedRun



  // Desktop results phase (ADR-041 D1): the canvas + the dock. Mobile and
  // pre-completion states fall through to their own surfaces below.
  const resultsPhase = !isMobile && completedRun != null
  const choreograph =
    !reducedMotion && witnessedRunId != null && completedRun?.id === witnessedRunId

  /** The overlay's completion hand-off: refetch (the canvas data lands),
   * mark the witnessed replay, and on mobile keep the legacy hand-off back
   * to the list (the desktop overlay plays the collapse into the dock). */
  const handleOverlayComplete = async (completedRunId: string | null) => {
    await fetchResults()
    if (completedRunId) setWitnessedRunId(completedRunId)
    if (isMobile) {
      setAttachRunId(null)
      navigate({
        to: "/projects/$id",
        params: { id: projectId },
        replace: true,
      })
    } else if (search.overlay === "chat") {
      // The fullscreen chat shell collapsed into the dock — the overlay is no
      // longer open, so the URL must stop saying it is (navigate without
      // `search` clears the params). A stale ?overlay=chat would keep
      // chatSearchOpen true and permanently gate off the results tour on the
      // fresh-generation path.
      navigate({
        to: "/projects/$id",
        params: { id: projectId },
        replace: true,
      })
    }
  }

  // First-visit results tour. Fires whenever a ready clip exists and the
  // chat overlay is closed — no matter how the user got here (fresh
  // generation or straight from the projects list). Seen flag is its own
  // localStorage key. Anchors: the canvas's first ready product node on
  // desktop (ADR-041 — data-tour="results-*" live on the output card), the
  // clip card in the mobile list world.
  useEffect(() => {
    if (resultsTourCheckedRef.current) return
    if (loading || !results) return
    if (search.overlay) return
    if (!isMobile && !resultsPhase) return
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
  }, [loading, results, search.overlay, activeTab, isMobile, resultsPhase])

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
    carousel: carousels.length,
    article: articles.length,
  }

  const visibleTabs = Array.from(
    new Set<ResultsTab>([
      ...requestedTabs,
      ...(Object.keys(counts) as ResultsTab[]).filter((tab) => (counts[tab] ?? 0) > 0),
    ])
  )

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
    switch (activeTab) {
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

  // ── The one overlay instance (ADR-041 D4) ────────────────────────────
  // chat search = the planning/conversation surface; attach = watching a
  // live run; resultsPhase = the results dock. One mounted instance parks
  // across all three — the input group is never remounted between them.
  const chatSearchOpen = search.overlay === "chat" || search.overlay === "intent"
  const attachOpen = search.overlay === "run" && attachRunId != null && latestRun != null
  const overlayMounted = chatSearchOpen || attachOpen || resultsPhase

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

  const overlayInitialIntent = attachOpen
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
      : resultsPhase
        ? completedRunIntent
        : undefined

  return (
    // Fullscreen canvas world (ADR-041 全屏化): this route lives OUTSIDE the
    // _app layout — no sidebar / header / title block. Floating chrome: the
    // project menu (top-left) + the canvas's own zoom pill (top-right,
    // FlowView `controls`); the canvas fills the viewport, the chat dock
    // parks at the bottom. The fullscreen planning overlay (z-50) naturally
    // covers the chrome while it is open. App chrome (theme / language /
    // notifications) lives in the studio shell — 2026-08-19 走查拍板,
    // confirmed to cover MOBILE too (nearest entry = back to /projects).
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

      {resultsPhase && completedRun ? (
        /* Results phase (ADR-041 D1): the canvas is FULL-BLEED — the dock
           is a completely floating layer above it, never a layout
           reservation (no safe-area padding: reserving space IS the
           occlusion). A node passing under the dock is panned back into
           view — the canvas is explore navigation. */
        <div className="min-h-0 flex-1">
          <ResultsCanvas
            className="h-full"
            assets={canvasAssets}
            steps={completedRun.steps}
            outputs={outputs}
            prompt={prompt || completedRun.context?.instruction || null}
            choreograph={choreograph}
            tourOutputId={resultsTourClipId}
            onOutputClick={handleOutputClick}
            onOutputAction={handleOutputAction}
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
        <div className="min-h-0 flex-1 overflow-y-auto">
          {!latestRun || !isMobile ? (
            /* Centered states: pending plan / desktop first-run failure /
               desktop run-in-flight (D2 — progress never enters the graph). */
            <div className="flex min-h-full items-center justify-center p-6">
              <div className="w-full max-w-md">
                {!latestRun ? (
                  <div className="rounded-lg bg-muted p-8 text-center">
                    <p className="font-medium">{t("results.pendingPlan.title")}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {pendingIntent
                        ? t("results.pendingPlan.desc")
                        : t("results.pendingPlan.descNoPlan")}
                    </p>
                    <Button
                      className="mt-4"
                      onClick={() =>
                        navigate({
                          to: "/projects/$id",
                          params: { id: projectId },
                          search: { overlay: "chat" },
                        })
                      }
                    >
                      {t("results.pendingPlan.cta")}
                    </Button>
                  </div>
                ) : latestRun.status === "failed" ? (
                  /* Desktop, first-run failure (no completed run yet): the
                     retry channel is the conversation (D8 — chat is the only
                     modification channel). */
                  <div className="rounded-lg bg-muted p-8 text-center">
                    <p className="text-sm text-destructive">
                      {latestRun.error || t("results.retryFailed")}
                    </p>
                    <Button
                      variant="outline"
                      className="mt-4"
                      onClick={() =>
                        navigate({
                          to: "/projects/$id",
                          params: { id: projectId },
                          search: { overlay: "chat" },
                        })
                      }
                    >
                      {t("results.failedPanel.cta")}
                    </Button>
                  </div>
                ) : (
                  /* Desktop, run in flight with no completed snapshot:
                     progress belongs to the chat flow alone. */
                  <div className="rounded-lg bg-muted p-8 text-center">
                    <p className="font-medium">{t("results.runActive.title")}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {t("results.runActive.desc")}
                    </p>
                    <Button
                      className="mt-4"
                      onClick={() =>
                        navigate({
                          to: "/projects/$id",
                          params: { id: projectId },
                          search: { overlay: "run" },
                        })
                      }
                    >
                      {t("results.runActive.cta")}
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* Mobile keeps the list world (prohibition #13 — no canvas below
               iPad width); the conversation surface opens through the same
               overlay entries as before. pt-16 clears the floating chrome. */
            <div className="mx-auto w-full max-w-7xl space-y-4 px-4 pb-8 pt-16">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <ResultsTabs
                  active={activeTab}
                  onChange={setActiveTab}
                  counts={counts}
                  visible={visibleTabs}
                  running={runningTabs}
                  failed={failedTabs}
                />
              </div>
              <div>{renderTabContent()}</div>
            </div>
          )}
        </div>
      )}

      {overlayMounted && (
        <GenerationOverlay
          // Remount per project — the message machine's state (run id,
          // conversation, shell) belongs to one project only.
          key={projectId}
          ref={overlayRef}
          projectId={projectId}
          prompt={
            firstMessage?.text ??
            pendingIntent?.prompt ??
            (attachOpen ? latestRun?.context?.instruction : null) ??
            prompt ??
            ""
          }
          firstMessage={
            chatSearchOpen && firstMessage
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
            attachOpen
              ? attachRunId
              : resultsPhase && !pendingIntent
                ? completedRun?.id
                : undefined
          }
          initialShell={resultsPhase ? "dock" : "fullscreen"}
          focusOutput={focusedOutputChip}
          onFocusChange={(id) => setFocusedOutputId(id)}
          completionMode={isMobile ? "navigate" : "dock"}
          onClose={
            attachOpen
              ? closeAttachOverlay
              : chatSearchOpen
                ? () => navigate({ to: "/projects" })
                : () => {}
          }
          onComplete={handleOverlayComplete}
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
