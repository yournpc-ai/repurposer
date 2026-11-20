import { createFileRoute, useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { AgentThread } from "@/components/chat/AgentThread"
import { normalizeIntent } from "@/components/chat/chatProtocol"
import { ProjectMenu } from "@/components/project/ProjectMenu"
import { apiFetch } from "@/lib/api"
import type { FirstMessageHandoff } from "@/lib/chatAttachments"
import type { LifecycleStamp, Project } from "@/lib/types"

interface WorkflowRun {
  id: string
  status: string
  context: { origin?: string; editor_media?: string; instruction?: string } | null
}

interface ProjectResults {
  project: Project
  prompt: string | null
  latest_run: WorkflowRun | null
  pending_brief?: { prompt: string; intent: unknown } | null
  lifecycle?: LifecycleStamp | null
}

export const Route = createFileRoute("/_app/projects/$id")({
  component: ProjectDetailPage,
})

function ProjectDetailPage() {
  const { id: projectId } = Route.useParams()
  return <ProjectThreadPage key={projectId} projectId={projectId} />
}

function ProjectThreadPage({ projectId }: { projectId: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const firstMessage = (location.state as { firstMessage?: FirstMessageHandoff }).firstMessage
  const [results, setResults] = useState<ProjectResults | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchResults = useCallback(async () => {
    try {
      const response = await apiFetch(`/api/v1/projects/${projectId}/results`)
      if (!response.ok) throw new Error("Project not found")
      setResults(await response.json())
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load project")
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    setLoading(true)
    void fetchResults()
  }, [projectId, fetchResults])

  const latestRun = results?.latest_run ?? null
  const runActive = latestRun != null && ["pending", "running", "waiting_human"].includes(latestRun.status)

  const lifecycle = results?.lifecycle ?? null
  const materialPending = lifecycle?.blockers.includes("material_pending") ?? false

  useEffect(() => {
    if (!materialPending || results?.latest_run) return
    const interval = setInterval(() => { void fetchResults() }, 2500)
    return () => clearInterval(interval)
  }, [materialPending, results?.latest_run, fetchResults])

  if (loading) {
    return <div className="grid h-full place-items-center bg-background text-muted-foreground">{t("common.loading")}</div>
  }
  if (error || !results) {
    return <div className="grid h-full place-items-center bg-background text-destructive">{error || "Project not found"}</div>
  }

  const { project, prompt, pending_brief: pendingBrief } = results
  const attachedRun = runActive && latestRun.context?.origin !== "node_revise" && !latestRun.context?.editor_media
    ? latestRun : null

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-background">
      <ProjectMenu
        projectId={project.id}
        title={project.title}
        runActive={runActive}
        onRenamed={(title) => setResults((current) => current ? { ...current, project: { ...current.project, title } } : current)}
        onDeleted={() => navigate({ to: "/projects" })}
      />

      <AgentThread
        projectId={projectId}
        lifecycle={lifecycle}
        prompt={firstMessage?.text ?? pendingBrief?.prompt ?? attachedRun?.context?.instruction ?? prompt ?? ""}
        firstMessage={firstMessage}
        onFirstMessageRetracted={() => {
          void navigate({
            to: "/projects/$id",
            params: { id: projectId },
            replace: true,
            state: {} as Record<string, unknown>,
          })
        }}
        initialIntent={pendingBrief?.intent ? normalizeIntent(pendingBrief.intent) : undefined}
        initialRunId={attachedRun?.id}
        onProjectChanged={fetchResults}
      />
    </div>
  )
}
