import { Link, createFileRoute, useLocation, useNavigate } from "@tanstack/react-router"
import { Minimize2, PanelRight } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { AgentThread } from "@/components/chat/AgentThread"
import { ProjectMenu } from "@/components/project/ProjectMenu"
import { useStudioHeader } from "@/components/StudioHeaderContext"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Tooltip } from "@/components/ui/tooltip-clean"
import { WorkbenchProvider, useWorkbench } from "@/components/workbench/WorkbenchContext"
import { WorkbenchPane } from "@/components/workbench/WorkbenchPane"
import { apiFetch } from "@/lib/api"
import type { FirstMessageHandoff } from "@/lib/chatAttachments"
import type { Project } from "@/lib/types"
import { compactConversation, type CompactSummary } from "@/lib/workbench"

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
    <WorkbenchProvider key={projectId} projectId={projectId}>
      <ProjectThreadPage
        key={projectId}
        projectId={projectId}
        conversationId={conversationId}
      />
    </WorkbenchProvider>
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
  const splitRef = useRef<HTMLDivElement>(null)
  const { isOpen: workbenchOpen, toggleWorkbench } = useWorkbench()
  const [results, setResults] = useState<ProjectResults | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    conversationId ?? null,
  )
  const [compacting, setCompacting] = useState(false)
  const [compactOverride, setCompactOverride] = useState<CompactSummary | null>(null)

  useEffect(() => {
    setActiveConversationId(conversationId ?? null)
    setCompactOverride(null)
  }, [conversationId])

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

  const handleCompact = useCallback(async () => {
    const targetId = activeConversationId ?? conversationId
    if (!targetId || compacting) return
    setCompacting(true)
    try {
      const res = await compactConversation(targetId, projectId)
      setCompactOverride({
        summary: res.summary,
        key_decisions: res.key_decisions,
        compacted_through_seq: res.compacted_through_seq,
        compacted_at: res.compacted_at,
        message_count: res.message_count,
      })
      toast.success(
        t("conversations.compactSuccess", { count: res.message_count }),
      )
    } catch {
      // apiFetch displays toast
    } finally {
      setCompacting(false)
    }
  }, [activeConversationId, conversationId, compacting, projectId, t])

  const project = results?.project ?? null

  const headerSlot = useMemo(() => {
    if (!project) return null
    return {
      left: (
        <div className="flex min-w-0 items-center gap-1.5">
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
          <ProjectMenu
            projectId={project.id}
            title={project.title}
            onRenamed={(title) =>
              setResults((current) =>
                current ? { ...current, project: { ...current.project, title } } : current,
              )
            }
            onDeleted={() => navigate({ to: "/projects" })}
          />
        </div>
      ),
      actions: (
        <>
          <Tooltip content={t("conversations.compactTooltip")} side="bottom">
            <IconButton
              size="md"
              variant="ghost"
              icon={<Minimize2 className="size-4" />}
              label={t("conversations.compact")}
              disabled={compacting || !(activeConversationId ?? conversationId)}
              onClick={() => {
                void handleCompact()
              }}
            />
          </Tooltip>
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
        </>
      ),
    }
  }, [
    project,
    t,
    navigate,
    compacting,
    activeConversationId,
    conversationId,
    handleCompact,
    workbenchOpen,
    toggleWorkbench,
  ])

  useStudioHeader(headerSlot)

  if (loading) {
    return <div className="grid h-full place-items-center bg-background text-muted-foreground">{t("common.loading")}</div>
  }
  if (error || !results) {
    return <div className="grid h-full place-items-center bg-background text-destructive">{error || "Project not found"}</div>
  }

  const { prompt } = results
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-background">
      <div ref={splitRef} className="flex min-h-0 flex-1 overflow-hidden">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <AgentThread
            key={`${projectId}:${conversationId ?? "latest"}`}
            projectId={projectId}
            conversationId={conversationId}
            prompt={firstMessage?.text ?? prompt ?? ""}
            firstMessage={conversationId ? undefined : firstMessage}
            onConversationResolved={setActiveConversationId}
            externalCompactSummary={compactOverride}
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
        <WorkbenchPane containerRef={splitRef} />
      </div>
    </div>
  )
}
