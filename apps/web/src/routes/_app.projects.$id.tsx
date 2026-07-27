import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { ArticleCard } from "@/components/results/ArticleCard"
import { CarouselCard } from "@/components/results/CarouselCard"
import { ClipCard } from "@/components/results/ClipCard"
import { ClipCardSkeleton } from "@/components/results/ClipCardSkeleton"
import { DerivativeCardSkeleton } from "@/components/results/DerivativeCardSkeleton"
import { GenerationOverlay } from "@/components/generation/GenerationOverlay"
import { GenerationStepper, type UiStep } from "@/components/results/GenerationStepper"
import { PostCard } from "@/components/results/PostCard"
import { QuotesCard } from "@/components/results/QuotesCard"
import {
  ResultsTabs,
  type ResultsTab,
} from "@/components/results/ResultsTabs"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { apiFetch, apiPost } from "@/lib/api"
import { resolveProjectId } from "@/lib/constants"
import { useRunEvents } from "@/lib/use-run-events"

import type { Output, WorkflowStep, Project } from "@/lib/types"

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
    outputs?: string[]
    clip_count?: number
    target_language?: string
    brand_template_id?: string | null
    instruction?: string | null
    tone_settings?: Record<string, unknown> | null
  } | null
  cost: Record<string, number> | null
  steps: WorkflowStep[]
  created_at: string
  updated_at: string | null
}

interface ProjectResults {
  project: Project
  prompt: string | null
  outputs: Output[]
  latest_run: WorkflowRun | null
  assets?: AssetStatusEntry[]
  ui_step?: UiStep | null
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

export const Route = createFileRoute("/_app/projects/$id")({
  component: ProjectDetailPage,
})

function ProjectDetailPage() {
  const { id } = Route.useParams()
  const projectId = resolveProjectId(id)
  const { t } = useTranslation()
  const navigate = useNavigate()
  const search = Route.useSearch() as { overlay?: "intent" }
  const [results, setResults] = useState<ProjectResults | null>(null)
  const [activeTab, setActiveTab] = useState<ResultsTab>("clips")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<Partial<Record<ResultsTab, boolean>>>({})
  const tabInitializedRef = useRef(false)

  const generationState = useMemo(() => {
    try {
      const raw = sessionStorage.getItem(`repurposer-generation-${projectId}`)
      if (!raw) return null
      return JSON.parse(raw) as {
        prompt?: string
        intent?: {
          action: "generate" | "answer"
          answer: string | null
          language: string
          outputs: string[]
          clip_count: number | null
          specific_instruction: string | null
        }
        needsClarification?: boolean
        brandTemplateId?: string
      }
    } catch {
      return null
    }
  }, [projectId])

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
  // anonymous demo viewers fall through to the legacy interval.
  const runActive =
    latestRun != null &&
    (latestRun.status === "pending" || latestRun.status === "running")
  const sse = useRunEvents(runActive ? latestRun.id : null, fetchResults)
  const sseActive = runActive && sse.steps.length > 0

  // Default to the first requested output tab once, when a generation is running.
  useEffect(() => {
    if (tabInitializedRef.current) return
    if (!latestRun?.context?.outputs?.length) return
    const firstRequested = latestRun.context.outputs[0]
    const tab = OUTPUT_KEY_TO_TAB[firstRequested]
    if (tab) {
      setActiveTab(tab)
      tabInitializedRef.current = true
    }
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
  const clipCount = latestRun?.context?.clip_count ?? 5

  const requestedTabs = (latestRun?.context?.outputs ?? [])
    .map((o) => OUTPUT_KEY_TO_TAB[o])
    .filter(Boolean) as ResultsTab[]

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

  // While SSE is active the stepper derives from the live step stream:
  // percent = settled/total (via the existing (index+1)/total formula),
  // label = the running step's stage (or kind). Structure is untouched.
  const sseUiStep = useMemo<UiStep | null>(() => {
    if (!sseActive) return null
    const total = sse.steps.length
    if (!total) return null
    const settled = sse.steps.filter(
      (s) => s.status === "done" || s.status === "failed" || s.status === "skipped"
    ).length
    const running = sse.steps.find((s) => s.status === "running")
    return {
      key: running?.stage ?? running?.kind ?? "queued",
      index: settled - 1,
      total,
    }
  }, [sseActive, sse.steps])

  // The loading dialog's lifecycle is driven by the backend's ui_step
  // (asset processing → generation run → first render), with the live SSE
  // derivation taking over while a run is streaming.
  const uiStep = sseUiStep ?? results?.ui_step
  const showProgress = uiStep != null

  const handleRetry = async (tab: ResultsTab) => {
    if (!results) return
    const outputKey = TAB_TO_OUTPUT_KEY[tab]
    setRetrying((prev) => ({ ...prev, [tab]: true }))
    try {
      const ctx = latestRun?.context
      await apiPost(`/api/v1/projects/${projectId}/generate`, {
        outputs: [outputKey],
        clip_count: outputKey === "clips" ? clipCount : undefined,
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
      <div className="flex min-h-svh items-center justify-center text-muted-foreground">
        {t("common.loading")}
      </div>
    )
  }

  if (error || !results) {
    return (
      <div className="flex min-h-svh items-center justify-center text-destructive">
        {error || "Project not found"}
      </div>
    )
  }

  const { project, prompt, outputs } = results

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
      <Card className="p-8 text-center ring-1 ring-border shadow-xl">
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
      </Card>
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
    <div className="flex min-h-svh flex-col p-6 md:p-8">
      <div className="mx-auto w-full max-w-7xl space-y-6">
        {/* Header */}
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{project.title}</h1>
          {prompt && <p className="text-sm text-muted-foreground">{prompt}</p>}
        </div>

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

        {showProgress && (
          <GenerationStepper open={showProgress} uiStep={uiStep} />
        )}

        {/* Content */}
        <div>{renderTabContent()}</div>
      </div>

      {search.overlay === "intent" && (
        <GenerationOverlay
          projectId={projectId}
          prompt={generationState?.prompt ?? results?.prompt ?? ""}
          initialIntent={generationState?.intent}
          initialNeedsClarification={generationState?.needsClarification ?? true}
          brandTemplateId={generationState?.brandTemplateId}
          onClose={() => navigate({ to: "/projects" })}
          onComplete={() => {
            sessionStorage.removeItem(`repurposer-generation-${projectId}`)
            navigate({
              to: "/projects/$id",
              params: { id: projectId },
              replace: true,
            })
          }}
        />
      )}
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return (
    <Card className="p-8 text-center text-sm text-muted-foreground ring-1 ring-border shadow-xl">
      {text}
    </Card>
  )
}
