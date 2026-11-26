import { Link, createFileRoute, useLocation, useNavigate } from "@tanstack/react-router"
import { PanelRight } from "@/components/ui/icons"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { AgentThread } from "@/components/chat/AgentThread"
import { ThreadLoadingSkeleton } from "@/components/chat/ThreadLoadingSkeleton"
import { useStudioHeader } from "@/components/StudioHeaderContext"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Tooltip } from "@/components/ui/tooltip-clean"
import { useWorkbench } from "@/components/workbench/WorkbenchContext"
import { apiFetch } from "@/lib/api"
import type { FirstMessageHandoff } from "@/lib/chatAttachments"
import type { Project } from "@/lib/types"
import { CONVERSATION_DELETED_EVENT } from "@/lib/workbench"

interface ProjectResults {
  project: Project
  prompt: string | null
  assets: { processing_status: string; processing_requested_at: string | null }[]
}

export const Route = createFileRoute("/_app/projects/$id")({
  validateSearch: (search: Record<string, unknown>): { c?: string } => {
    const raw = search.c
    return typeof raw === "string" && raw.trim() ? { c: raw.trim() } : {}
  },
  component: ProjectDetailPage,
})

function ProjectDetailPage() {
  const { id: projectId } = Route.useParams()
  const { c: conversationId } = Route.useSearch()
  return (
    <ProjectThreadPage
      key={projectId}
      projectId={projectId}
      conversationId={conversationId}
    />
  )
}

function ProjectThreadPage({
  projectId,
  conversationId,
}: {
  projectId: string
  conversationId?: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const firstMessage = (location.state as { firstMessage?: FirstMessageHandoff }).firstMessage
  const { isOpen: workbenchOpen, toggleWorkbench } = useWorkbench()
  const [results, setResults] = useState<ProjectResults | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [threadResetNonce, setThreadResetNonce] = useState(0)

  useEffect(() => {
    const onDeleted = (event: Event) => {
      const detail = (
        event as CustomEvent<{ conversationId?: string; projectId?: string }>
      ).detail
      if (detail?.projectId && detail.projectId !== projectId) return
      if (!conversationId || detail?.conversationId === conversationId) {
        setThreadResetNonce((n) => n + 1)
      }
    }
    window.addEventListener(CONVERSATION_DELETED_EVENT, onDeleted)
    return () => window.removeEventListener(CONVERSATION_DELETED_EVENT, onDeleted)
  }, [projectId, conversationId])

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

  const project = results?.project ?? null

  const headerSlot = useMemo(() => {
    if (!project) return null
    return {
      left: (
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <Link
            to="/projects"
            className="hidden shrink-0 rounded-md px-1.5 py-1 text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground sm:inline"
          >
            {t("nav.myProjects")}
          </Link>
          <span
            aria-hidden="true"
            className="hidden shrink-0 select-none text-[13px] text-muted-foreground/45 sm:inline"
          >
            /
          </span>
          <span
            title={project.title}
            className="min-w-0 flex-1 truncate px-1 text-[13px] font-medium text-foreground select-text"
          >
            {project.title}
          </span>
        </div>
      ),
      actions: (
        <Tooltip content={t(workbenchOpen ? "workbench.close" : "workbench.open")} side="bottom">
          <IconButton
            size="md"
            variant="ghost"
            pressed={workbenchOpen}
            icon={<PanelRight className="size-4" />}
            label={t(workbenchOpen ? "workbench.close" : "workbench.open")}
            onClick={toggleWorkbench}
          />
        </Tooltip>
      ),
      hideNotifications: true,
    }
  }, [
    project,
    t,
    workbenchOpen,
    toggleWorkbench,
  ])

  useStudioHeader(headerSlot)

  useEffect(() => {
    const projectTitle = project?.title?.trim()
    if (!projectTitle) return
    const prevTitle = document.title
    document.title = `${projectTitle} — Rookie`
    return () => {
      document.title = prevTitle
    }
  }, [project?.title])

  if (loading) {
    return <ThreadLoadingSkeleton label={t("common.loading")} includeComposer />
  }
  if (error || !results) {
    return <div className="grid h-full place-items-center bg-background text-destructive">{error || "Project not found"}</div>
  }

  const { prompt } = results
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-background">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <AgentThread
          key={`${projectId}:${conversationId ?? "latest"}:${threadResetNonce}`}
          projectId={projectId}
          conversationId={conversationId}
          prompt={firstMessage?.text ?? prompt ?? ""}
          firstMessage={conversationId ? undefined : firstMessage}
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
    </div>
  )
}
