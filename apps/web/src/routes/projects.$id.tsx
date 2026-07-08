import { createFileRoute, Outlet, useMatches } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { ClipCard } from "@/components/results/ClipCard"
import { LinkedInCard } from "@/components/results/LinkedInCard"
import { QuoteCard } from "@/components/results/QuoteCard"
import {
  ResultsTabs,
  type ResultsTab,
} from "@/components/results/ResultsTabs"
import { SummaryCard } from "@/components/results/SummaryCard"
import { Card } from "@/components/ui/card"
import { apiFetch } from "@/lib/api"

import type { Clip, Derivative, Project } from "@/lib/types"

interface WorkflowRun {
  id: string
  project_id: string
  status: "pending" | "running" | "completed" | "failed"
  current_step: string | null
  progress: number
  error: string | null
  created_at: string
  updated_at: string | null
}

interface ProjectResults {
  project: Project
  prompt: string | null
  clips: Clip[]
  derivatives: Derivative[]
  latest_job: WorkflowRun | null
}

export const Route = createFileRoute("/projects/$id")({
  component: ProjectRouteComponent,
})

/**
 * This route has a child (the clip editor, `projects.$id.clips.$clipId`), so
 * it must render an <Outlet /> when that child is active instead of always
 * showing its own results content.
 */
function ProjectRouteComponent() {
  const matches = useMatches()
  const isLeaf = matches[matches.length - 1]?.routeId === Route.id
  return isLeaf ? <ProjectDetailPage /> : <Outlet />
}

function ProjectDetailPage() {
  const { id } = Route.useParams()
  const { t } = useTranslation()
  const [results, setResults] = useState<ProjectResults | null>(null)
  const [activeTab, setActiveTab] = useState<ResultsTab>("clips")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchResults = async () => {
    try {
      const res = await apiFetch(`/api/v1/projects/${id}/results`)
      if (!res.ok) throw new Error("Project not found")
      setResults(await res.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    fetchResults()
  }, [id])

  // Poll latest job until it settles.
  useEffect(() => {
    if (!results?.latest_job) return
    const status = results.latest_job.status
    if (status === "completed" || status === "failed") return

    const interval = setInterval(() => {
      fetchResults()
    }, 2000)
    return () => clearInterval(interval)
  }, [results?.latest_job?.status, results?.latest_job?.id])

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

  const { project, prompt, clips, derivatives, latest_job } = results

  const linkedin = derivatives.filter((d) => d.type === "linkedin_post")
  const quotes = derivatives.filter((d) => d.type === "quote_card")
  const summaries = derivatives.filter((d) => d.type === "summary")

  const counts = {
    clips: clips.length,
    linkedin: linkedin.length,
    quotes: quotes.length,
    summary: summaries.length,
  }

  const isGenerating =
    latest_job?.status === "pending" || latest_job?.status === "running"

  const renderTabContent = () => {
    switch (activeTab) {
      case "clips":
        if (clips.length === 0) {
          return <EmptyState text={t("results.empty.clips")} />
        }
        return (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {clips.map((clip) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                onRegenerate={fetchResults}
              />
            ))}
          </div>
        )
      case "linkedin":
        if (linkedin.length === 0) {
          return <EmptyState text={t("results.empty.linkedin")} />
        }
        return (
          <div className="grid gap-4 md:grid-cols-2">
            {linkedin.map((d) => (
              <LinkedInCard
                key={d.id}
                derivative={d}
                onRegenerate={fetchResults}
              />
            ))}
          </div>
        )
      case "quotes":
        if (quotes.length === 0) {
          return <EmptyState text={t("results.empty.quotes")} />
        }
        return (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {quotes.map((d) => (
              <QuoteCard
                key={d.id}
                derivative={d}
                onRegenerate={fetchResults}
              />
            ))}
          </div>
        )
      case "summary":
        if (summaries.length === 0) {
          return <EmptyState text={t("results.empty.summary")} />
        }
        return (
          <div className="grid gap-4 md:grid-cols-2">
            {summaries.map((d) => (
              <SummaryCard
                key={d.id}
                derivative={d}
                onRegenerate={fetchResults}
              />
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
          <h1 className="text-2xl font-semibold tracking-tight">
            {project.title}
          </h1>
          {prompt && (
            <p className="text-sm text-muted-foreground">
              {t("results.prompt")}: {prompt}
            </p>
          )}
        </div>

        {/* Tabs + status */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <ResultsTabs
            active={activeTab}
            onChange={setActiveTab}
            counts={counts}
          />
          {isGenerating && (
            <p className="text-sm text-muted-foreground">
              {t("results.generating")}
            </p>
          )}
        </div>

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
