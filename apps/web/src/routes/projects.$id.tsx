import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { ArticleCard } from "@/components/results/ArticleCard"
import { CarouselCard } from "@/components/results/CarouselCard"
import { ClipCard } from "@/components/results/ClipCard"
import { ClipCardSkeleton } from "@/components/results/ClipCardSkeleton"
import { DerivativeCardSkeleton } from "@/components/results/DerivativeCardSkeleton"
import { GenerationStepper } from "@/components/results/GenerationStepper"
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

import type { Clip, Derivative, Project } from "@/lib/types"

interface OutputStatus {
  status: "pending" | "running" | "completed" | "failed"
  progress: number
  error: string | null
  stage?: string | null
}

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
  current_step: string | null
  progress: number
  error: string | null
  context: {
    outputs?: string[]
    clip_count?: number
    output_status?: Record<string, OutputStatus>
    target_language?: string
    brand_template_id?: string | null
    instruction?: string | null
    tone_settings?: Record<string, unknown> | null
  } | null
  created_at: string
  updated_at: string | null
}

interface ProjectResults {
  project: Project
  prompt: string | null
  clips: Clip[]
  derivatives: Derivative[]
  latest_job: WorkflowRun | null
  assets?: AssetStatusEntry[]
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
  // Backward compatibility for jobs created before the output rename.
  linkedin: "post",
  quote_cards: "quotes",
  summary: "post",
  blog: "article",
}

export const Route = createFileRoute("/projects/$id")({
  component: ProjectDetailPage,
})

function ProjectDetailPage() {
  const { id } = Route.useParams()
  const projectId = resolveProjectId(id)
  const { t } = useTranslation()
  const [results, setResults] = useState<ProjectResults | null>(null)
  const [activeTab, setActiveTab] = useState<ResultsTab>("clips")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<Partial<Record<ResultsTab, boolean>>>({})
  const tabInitializedRef = useRef(false)

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

  const latestJob = results?.latest_job

  useEffect(() => {
    setLoading(true)
    fetchResults()
  }, [projectId])

  // Default to the first requested output tab once, when a generation is running.
  useEffect(() => {
    if (tabInitializedRef.current) return
    if (!latestJob?.context?.outputs?.length) return
    const firstRequested = latestJob.context.outputs[0]
    const tab = OUTPUT_KEY_TO_TAB[firstRequested]
    if (tab) {
      setActiveTab(tab)
      tabInitializedRef.current = true
    }
  }, [latestJob?.context?.outputs])

  // Poll the latest job until the run settles AND no clip from this run is
  // still rendering. Clip renders proceed independently of the run status.
  useEffect(() => {
    if (!results?.latest_job) return

    const status = results.latest_job.status

    const currentRunId = results.latest_job.id
    const currentRunClips = (results?.clips ?? []).filter(
      (c: Clip) => c.workflow_run_id === currentRunId || c.workflow_run_id === null
    )

    const hasRenderingClips = currentRunClips.some(
      (c: Clip) => c.render_status === "pending" || c.render_status === "rendering"
    )

    // A settled run (completed or failed) never progresses its outputs
    // further — stop polling regardless of what the per-output statuses say
    // (legacy runs may carry stale pending entries). Clip renders proceed
    // independently of the run, so keep polling only while any are active.
    if ((status === "completed" || status === "failed") && !hasRenderingClips) {
      return
    }

    const interval = setInterval(() => {
      fetchResults()
    }, 2500)
    return () => clearInterval(interval)
  }, [results?.latest_job, results?.clips])

  const outputStatus = latestJob?.context?.output_status
  const requestedOutputs = latestJob?.context?.outputs ?? []
  const clipCount = latestJob?.context?.clip_count ?? 5

  const requestedTabs = requestedOutputs
    .map((o) => OUTPUT_KEY_TO_TAB[o])
    .filter(Boolean) as ResultsTab[]

  // When the run itself failed, outputs that never reached a terminal state
  // are dead too — present them as failed (with a retry) instead of skeletons.
  const runFailed = latestJob?.status === "failed"

  const runningTabs = outputStatus
    ? (Object.entries(outputStatus)
        .filter(
          ([, s]) =>
            !runFailed && (s.status === "running" || s.status === "pending")
        )
        .map(([output]) => OUTPUT_KEY_TO_TAB[output])
        .filter(Boolean) as ResultsTab[])
    : []

  const failedTabs = outputStatus
    ? (Object.entries(outputStatus)
        .filter(
          ([, s]) =>
            s.status === "failed" || (runFailed && s.status !== "completed")
        )
        .map(([output]) => OUTPUT_KEY_TO_TAB[output])
        .filter(Boolean) as ResultsTab[])
    : []

  const isGenerating =
    latestJob?.status === "pending" || latestJob?.status === "running"

  // The loading covers the full journey: asset transcription/parsing first,
  // then the generation run. It is visible from the moment the user lands on
  // this page after clicking Generate, until the run settles.
  const assetsBusy = (results?.assets ?? []).some(
    (a) => a.processing_status === "pending" || a.processing_status === "processing"
  )
  const showProgress = assetsBusy || isGenerating

  const handleRetry = async (tab: ResultsTab) => {
    if (!results) return
    const outputKey = TAB_TO_OUTPUT_KEY[tab]
    setRetrying((prev) => ({ ...prev, [tab]: true }))
    try {
      const ctx = latestJob?.context
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

  const { project, prompt, clips: allClips, derivatives: allDerivatives } = results

  const currentRunId = latestJob?.id
  const clips = allClips.filter(
    (c) => c.workflow_run_id === currentRunId || c.workflow_run_id === null
  )
  const derivatives = allDerivatives.filter(
    (d) => d.workflow_run_id === currentRunId || d.workflow_run_id === null
  )

  const posts = derivatives.filter((d) => d.type === "post")
  const quotes = derivatives.filter((d) => d.type === "quotes")
  const carousels = derivatives.filter((d) => d.type === "carousel")
  const articles = derivatives.filter((d) => d.type === "article")

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
    const outputKey = TAB_TO_OUTPUT_KEY[tab]
    let status = outputStatus?.[outputKey]
    // Fallback to legacy output keys (e.g., linkedin/summary/blog) for jobs
    // created before the output rename.
    if (!status && outputStatus) {
      const legacyEntry = Object.entries(outputStatus).find(
        ([key, s]) => OUTPUT_KEY_TO_TAB[key] === tab && s.status === "failed"
      )
      if (legacyEntry) {
        status = legacyEntry[1]
      }
    }
    return (
      <Card className="p-8 text-center ring-1 ring-border shadow-xl">
        <p className="text-sm text-destructive">
          {status?.error || latestJob?.error || t("results.retryFailed")}
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
              <ClipCard key={clip.id} clip={clip} onRegenerate={fetchResults} />
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
            {posts.map((d) => (
              <PostCard key={d.id} derivative={d} onRegenerate={fetchResults} />
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
            {quotes.map((d) => (
              <QuotesCard key={d.id} derivative={d} onRegenerate={fetchResults} />
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
            {carousels.map((d) => (
              <CarouselCard key={d.id} derivative={d} onRegenerate={fetchResults} />
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
            {articles.map((d) => (
              <ArticleCard key={d.id} derivative={d} onRegenerate={fetchResults} />
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
          <GenerationStepper
            open={showProgress}
            runStatus={latestJob?.status ?? null}
            currentStep={latestJob?.current_step ?? null}
            progress={latestJob?.progress}
            assets={results?.assets ?? []}
            outputs={requestedOutputs}
            outputStatus={outputStatus ?? {}}
          />
        )}

        {/* Content */}
        <div>{renderTabContent()}</div>
      </div>
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
