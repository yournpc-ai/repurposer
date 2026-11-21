import { createFileRoute, useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { AgentThread } from "@/components/chat/AgentThread"
import { ProjectMenu } from "@/components/project/ProjectMenu"
import { apiFetch } from "@/lib/api"
import type { FirstMessageHandoff } from "@/lib/chatAttachments"
import type { Project } from "@/lib/types"

interface ProjectResults {
  project: Project
  prompt: string | null
  assets: { processing_status: string; processing_requested_at: string | null }[]
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

  const materialPending = results?.assets.some((asset) =>
    asset.processing_status === "processing" ||
    (asset.processing_status === "pending" && asset.processing_requested_at != null)
  )

  useEffect(() => {
    if (!materialPending) return
    const interval = setInterval(() => { void fetchResults() }, 2500)
    return () => clearInterval(interval)
  }, [materialPending, fetchResults])

  if (loading) {
    return <div className="grid h-full place-items-center bg-background text-muted-foreground">{t("common.loading")}</div>
  }
  if (error || !results) {
    return <div className="grid h-full place-items-center bg-background text-destructive">{error || "Project not found"}</div>
  }

  const { project, prompt } = results
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-background">
      <ProjectMenu
        projectId={project.id}
        title={project.title}
        onRenamed={(title) => setResults((current) => current ? { ...current, project: { ...current.project, title } } : current)}
        onDeleted={() => navigate({ to: "/projects" })}
      />

      <AgentThread
        projectId={projectId}
        prompt={firstMessage?.text ?? prompt ?? ""}
        firstMessage={firstMessage}
        onFirstMessageRetracted={() => {
          void navigate({
            to: "/projects/$id",
            params: { id: projectId },
            replace: true,
            state: {} as Record<string, unknown>,
          })
        }}
        onProjectChanged={fetchResults}
      />
    </div>
  )
}
