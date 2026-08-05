import { createFileRoute, useLocation, useNavigate } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { ArticleCard } from "@/components/results/ArticleCard"
import { CarouselCard } from "@/components/results/CarouselCard"
import { ClipCard } from "@/components/results/ClipCard"
import { ClipCardSkeleton } from "@/components/results/ClipCardSkeleton"
import { DerivativeCardSkeleton } from "@/components/results/DerivativeCardSkeleton"
import { GenerationOverlay, normalizeIntent, normalizeSlots } from "@/components/generation/GenerationOverlay"
import { PostCard } from "@/components/results/PostCard"
import { QuotesCard } from "@/components/results/QuotesCard"
import {
  ResultsTabs,
  type ResultsTab,
} from "@/components/results/ResultsTabs"
import { Button } from "@/components/ui/button"
import { Tour, type TourStep } from "@/components/ui/tour"
import { tourCopy, tourVersionOf, type TourStepDef } from "@/lib/tour"
import { apiFetch, apiPost } from "@/lib/api"
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
    side: "top",
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
    /** Slot-shaped on new runs; legacy flat runs carry string outputs +
     * `clip_count` — normalized through `normalizeSlots` at every read. */
    outputs?: (string | IntentSlot)[]
    clip_count?: number
    target_language?: string
    /** 配音语言集 (RECIPES §4.1): absent on pre-recipe runs. */
    dub_languages?: string[]
    brand_template_id?: string | null
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
  /** Slot-shaped on the API (the server upgrades legacy flat rows on read);
   * typed loosely here and normalized at the overlay boundary. */
  intent: unknown
  /** Why the book needs a human check — confirmation is `reasons.length > 0`
   * (the API's redundant needs_clarification bool was retired, B4). */
  reasons?: string[]
  brand_template_id?: string | null
}

interface ProjectResults {
  project: Project
  prompt: string | null
  outputs: Output[]
  latest_run: WorkflowRun | null
  assets?: AssetStatusEntry[]
  pending_intent?: PendingIntent | null
}

const TAB_TO_OUTPUT_KEY: Record<ResultsTab, string> = {
  clips: "clips",
  post: "post",
  quotes: "quotes",
  carousel: "carousel",
  article: "article",
}

const OUTPUT_KEY_TO_TAB: Record<string, ResultsTab> = {
  clips: "clips",
  post: "post",
  quotes: "quotes",
  carousel: "carousel",
  article: "article",
}

/** Node kinds that own a results tab (ADR-028); preprocess/persona/director/
 * script/render nodes drive the stepper, not a tab. */
const NODE_KIND_TO_TAB: Record<string, ResultsTab> = {
  clips_pipeline: "clips",
  post_gen: "post",
  quotes_gen: "quotes",
  carousel_gen: "carousel",
  article_gen: "article",
}

export const Route = createFileRoute("/_app/projects/$id/")({
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
        brandTemplateId?: string
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

  const fetchResults = async () => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/results`)
      if (!res.ok) throw new Error("Project not found")
      setResults(await res.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project")
    } finally {
      setLoading(false)
    }
  }

  const latestRun = results?.latest_run

  useEffect(() => {
    setLoading(true)
    fetchResults()
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
  // before the overlay's terminal handler can toast + navigate.
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

  // First-visit results tour. Fires whenever clips are ready and the chat
  // overlay is closed — no matter how the user got here (fresh generation or
  // straight from the projects list). Seen flag is its own localStorage key.
  // The targets live on the clips tab, so the tour switches to it first; the
  // tab grid is committed in the same render pass, before Tour queries the
  // DOM in its own effect.
  useEffect(() => {
    if (resultsTourCheckedRef.current) return
    if (loading || !results) return
    if (search.overlay) return
    if (!results.outputs.some(isClipReady)) return
    resultsTourCheckedRef.current = true
    try {
      if (window.localStorage.getItem(RESULTS_TOUR_KEY) === RESULTS_TOUR_VERSION)
        return
    } catch {
      return // storage unavailable — tour simply never auto-opens
    }
    if (activeTab !== "clips") setActiveTab("clips")
    setResultsTourOpen(true)
  }, [loading, results, search.overlay, activeTab])

  const markResultsTourSeen = () => {
    try {
      window.localStorage.setItem(RESULTS_TOUR_KEY, RESULTS_TOUR_VERSION)
    } catch {
      // ignore — worst case the tour shows again next visit
    }
  }

  // Default to the first requested output tab once, when a generation is running.
  const runSlots = normalizeSlots(
    latestRun?.context?.outputs,
    latestRun?.context?.clip_count
  )
  useEffect(() => {
    if (tabInitializedRef.current) return
    if (!runSlots.length) return
    const tab = OUTPUT_KEY_TO_TAB[runSlots[0].type]
    if (tab) {
      setActiveTab(tab)
      tabInitializedRef.current = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestRun?.context?.outputs])

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
  const clipCount = runSlots.find((s) => s.type === "clips")?.count ?? 5

  const requestedTabs = Array.from(
    new Set(
      runSlots.map((s) => OUTPUT_KEY_TO_TAB[s.type]).filter(Boolean)
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
    const outputKey = TAB_TO_OUTPUT_KEY[tab] as IntentSlot["type"]
    setRetrying((prev) => ({ ...prev, [tab]: true }))
    try {
      const ctx = latestRun?.context
      const priorSlot = runSlots.find((s) => s.type === outputKey)
      await apiPost(`/api/v1/projects/${projectId}/generate`, {
        slots: [
          {
            type: outputKey,
            count: priorSlot?.count ?? null,
            focus: null,
            language: null,
            tone_override: null,
            explicit: false,
          },
        ],
        target_language: ctx?.target_language || results.project.language || "en",
        brand_template_id: ctx?.brand_template_id || undefined,
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
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        {t("common.loading")}
      </div>
    )
  }

  if (error || !results) {
    return (
      <div className="flex flex-1 items-center justify-center text-destructive">
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
                onRegenerate={fetchResults}
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

  return (
    <div className="flex flex-1 flex-col p-6 md:p-8">
      <div className="mx-auto w-full max-w-7xl space-y-6">
        {/* Header */}
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{project.title}</h1>
          {prompt && <p className="text-sm text-muted-foreground">{prompt}</p>}
        </div>

        {/* Tabs + content only exist once a run has started; before that the
            project is awaiting plan confirmation (or setup). */}
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
        ) : (
          <>
            {/* Tabs */}
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

            {/* Content — live progress shows inline (running tab indicators,
                skeleton grids, per-clip render spinners); the full-screen
                progress surface is the chat overlay, opened via ?overlay=run. */}
            <div>{renderTabContent()}</div>
          </>
        )}
      </div>

      {(search.overlay === "chat" || search.overlay === "intent") && (
        <GenerationOverlay
          projectId={projectId}
          prompt={firstMessage?.text ?? pendingIntent?.prompt ?? prompt ?? ""}
          firstMessage={
            firstMessage
              ? {
                  text: firstMessage.text,
                  mentions: firstMessage.mentions ?? [],
                  brandTemplateId: firstMessage.brandTemplateId,
                }
              : null
          }
          initialIntent={
            pendingIntent ? normalizeIntent(pendingIntent.intent) : undefined
          }
          initialNeedsClarification={
            pendingIntent ? (pendingIntent.reasons?.length ?? 0) > 0 : true
          }
          initialReasons={pendingIntent?.reasons ?? []}
          brandTemplateId={
            firstMessage?.brandTemplateId ??
            pendingIntent?.brand_template_id ??
            undefined
          }
          onClose={() => navigate({ to: "/projects" })}
          onComplete={() => {
            // The overlay created the run after this page's initial fetch —
            // refetch so latest_run/outputs are live when it unmounts
            // (same-route search navigation does not remount the page).
            fetchResults()
            navigate({
              to: "/projects/$id",
              params: { id: projectId },
              replace: true,
            })
          }}
        />
      )}

      {/* Attach mode (processing project opened from the list): the same
          chat overlay, but bound to the live run — no confirm phase. The
          intent is reconstructed from the run context purely for the
          confirmed-plan summary line. Settled runs fall through to the
          normal results view. */}
      {search.overlay === "run" && attachRunId && latestRun && (
        <GenerationOverlay
          projectId={projectId}
          prompt={latestRun.context?.instruction ?? prompt ?? ""}
          initialIntent={{
            action: "generate",
            answer: null,
            // Language is a per-slot property (book-level field retired):
            // materialize each slot from the run's recorded fallback.
            outputs: (runSlots.length ? runSlots : normalizeSlots(["clips"])).map(
              (slot) => ({
                ...slot,
                language:
                  slot.language ??
                  latestRun.context?.target_language ??
                  project.language ??
                  "en",
              })
            ),
            dub_languages: Array.isArray(latestRun.context?.dub_languages)
              ? (latestRun.context.dub_languages as string[])
              : [],
            specific_instruction: latestRun.context?.instruction ?? null,
          }}
          brandTemplateId={latestRun.context?.brand_template_id ?? undefined}
          initialRunId={attachRunId}
          onClose={closeAttachOverlay}
          onComplete={() => {
            fetchResults()
            closeAttachOverlay()
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
