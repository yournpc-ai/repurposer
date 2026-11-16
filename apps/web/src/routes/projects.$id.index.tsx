import { createFileRoute, useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { ChatDock, type DerivedRow, type DecisionPlanRow } from "@/components/chat/ChatDock"
import { normalizeIntent, tasksFromRunContext } from "@/components/chat/chatProtocol"
import { SoundMutexProvider } from "@/components/flow/sound-mutex"
import { ProjectHeader } from "@/components/project/ProjectHeader"
import { apiFetch } from "@/lib/api"
import type { FirstMessageHandoff } from "@/lib/chatAttachments"
import { useRunEvents } from "@/lib/use-run-events"
import type { LifecycleStamp, WorkflowStep, Project } from "@/lib/types"

interface AssetStatusEntry {
  id: string
  type: string
  processing_status: "pending" | "processing" | "completed" | "failed"
  processing_error?: string | null
}

interface WorkflowRun {
  id: string
  project_id: string
  status: "pending" | "running" | "waiting_human" | "completed" | "failed" | "cancelled"
  progress: number
  error: string | null
  context: {
    tasks?: { tool: string; params: Record<string, unknown> }[]
    outputs?: unknown[]
    clip_count?: number
    instruction?: string | null
    name?: string | null
    origin?: string | null
    [key: string]: unknown
  } | null
  cost: Record<string, number> | null
  steps: WorkflowStep[]
  created_at: string
  updated_at: string | null
}

interface PendingBrief {
  prompt: string
  intent: unknown | null
  brief?: unknown
  reasons?: string[]
  persona_id?: string | null
  derived?: DerivedRow[]
  plans?: DecisionPlanRow[]
}

interface ProjectResults {
  project: Project
  prompt: string | null
  latest_run: WorkflowRun | null
  assets?: AssetStatusEntry[]
  pending_brief?: PendingBrief | null
  lifecycle?: LifecycleStamp | null
}

export const Route = createFileRoute("/projects/$id/")({
  component: ProjectDetailPage,
})

function ProjectDetailPage() {
  const { id: projectId } = Route.useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const firstMessage = (location.state as { firstMessage?: FirstMessageHandoff }).firstMessage
  const [results, setResults] = useState<ProjectResults | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stickyCompletedRun, setStickyCompletedRun] = useState<WorkflowRun | null>(null)

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

  useEffect(() => {
    setStickyCompletedRun(null)
  }, [projectId])

  const latestRun = results?.latest_run ?? null
  const runActive = latestRun != null && ["pending", "running", "waiting_human"].includes(latestRun.status)
  const sse = useRunEvents(runActive ? latestRun.id : null, fetchResults)
  const sseActive = runActive && sse.steps.length > 0

  useEffect(() => {
    if (latestRun?.status === "completed") setStickyCompletedRun(latestRun)
  }, [latestRun])

  const lifecycle = results?.lifecycle ?? null
  const materialPending = lifecycle?.blockers.includes("material_pending") ?? false

  useEffect(() => {
    if (!results?.latest_run || sseActive) return
    const status = results.latest_run.status
    const hasRenderingOutputs = results.latest_run.steps.some(
      (step) => step.kind === "render" && ["pending", "running"].includes(step.status),
    )
    if (["completed", "failed", "cancelled"].includes(status) && !hasRenderingOutputs) return
    const interval = setInterval(() => { void fetchResults() }, 2500)
    return () => clearInterval(interval)
  }, [results?.latest_run, sseActive, fetchResults])

  useEffect(() => {
    if (!materialPending || results?.latest_run) return
    const interval = setInterval(() => { void fetchResults() }, 2500)
    return () => clearInterval(interval)
  }, [materialPending, results?.latest_run, fetchResults])

  if (loading) {
    return <div className="grid h-dvh place-items-center bg-background text-muted-foreground">{t("common.loading")}</div>
  }
  if (error || !results) {
    return <div className="grid h-dvh place-items-center bg-background text-destructive">{error || "Project not found"}</div>
  }

  const { project, prompt, pending_brief: pendingBrief } = results
  const completedRun = latestRun?.status === "completed" ? latestRun : stickyCompletedRun
  const runTasks = tasksFromRunContext(latestRun?.context)
  const completedRunTasks = tasksFromRunContext(completedRun?.context)
  const completedRunIntent = completedRun
    ? normalizeIntent({
        tasks: completedRunTasks.length ? completedRunTasks : [{ tool: "produce_video", params: {} }],
        specific_instruction: completedRun.context?.instruction,
        name: completedRun.context?.name,
      })
    : undefined
  const dockInitialIntent = runActive
    ? normalizeIntent({
        tasks: runTasks.length ? runTasks : [{ tool: "produce_video", params: {} }],
        specific_instruction: latestRun?.context?.instruction,
        name: latestRun?.context?.name,
      })
    : pendingBrief?.intent
      ? normalizeIntent(pendingBrief.intent)
      : completedRunIntent

  return (
    <SoundMutexProvider>
      <div className="relative flex h-dvh flex-col overflow-hidden bg-background">
        <ProjectHeader
          projectId={project.id}
          title={project.title}
          runActive={runActive}
          onRenamed={(title) => setResults((current) => current ? { ...current, project: { ...current.project, title } } : current)}
          onDeleted={() => navigate({ to: "/projects" })}
          creditsRefreshKey={latestRun ? `${latestRun.id}:${latestRun.status}` : "idle"}
        />

        <ChatDock
          key={projectId}
          projectId={projectId}
          form="full"
          lifecycle={lifecycle}
          canvasAvailable={false}
          prompt={firstMessage?.text ?? pendingBrief?.prompt ?? (runActive ? latestRun?.context?.instruction : null) ?? prompt ?? ""}
          firstMessage={firstMessage ? {
            text: firstMessage.text,
            mentions: firstMessage.mentions ?? [],
            skill: firstMessage.skill,
            skillOption: firstMessage.skillOption,
            personaId: firstMessage.personaId,
            attachments: firstMessage.attachments ?? [],
          } : null}
          onFirstMessageRetracted={() => {
            void navigate({
              to: "/projects/$id",
              params: { id: projectId },
              replace: true,
              state: {} as Record<string, unknown>,
            })
          }}
          initialIntent={dockInitialIntent}
          initialRunId={latestRun?.context?.origin === "node_revise"
            ? undefined
            : runActive
              ? latestRun.id
              : !pendingBrief && completedRun
                ? completedRun.id
                : undefined}
          onComplete={fetchResults}
          onRunStarted={fetchResults}
          onDraftGraphChange={fetchResults}
        />
      </div>
    </SoundMutexProvider>
  )
}
