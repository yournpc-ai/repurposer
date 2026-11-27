"use client"

import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import {
  ArrowRight,
  ChevronRight,
  CircleHelp,
  EllipsisVertical,
  Folder,
  FolderOpen,
  Minimize2,
  Pencil,
  Plus,
  Trash2,
} from "@/components/ui/icons"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { DeleteProjectDialog } from "@/components/project/project-dialogs"
import { Button } from "@/components/ui/button-clean"
import { AlertDialog, Dialog } from "@/components/ui/dialog-clean"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { Tooltip } from "@/components/ui/tooltip-clean"
import { apiFetch } from "@/lib/api"
import { AuthContext } from "@/lib/auth-context"
import {
  compactConversation,
  CONVERSATION_ACTIVITY_EVENT,
  CONVERSATIONS_CHANGED_EVENT,
  createProjectConversation,
  deleteConversation,
  getConversationActivitySnapshot,
  listProjectConversations,
  markConversationSeen,
  renameConversation,
  type ProjectConversationSummary,
} from "@/lib/workbench"
import { cn } from "@/lib/utils"

interface SidebarProject {
  id: string
  title: string
}

export interface ProjectConversationsTreeProps {
  projectId?: string
  activeConversationId?: string
  /** When the sidebar is folded into its 48px icon rail, show compact project folder icons. */
  collapsed?: boolean
  onNavigate?: () => void
}

function formatCompactAge(
  iso: string | null | undefined,
  nowMs: number,
  isZh: boolean,
): string {
  if (!iso) return ""
  const parsed = Date.parse(iso)
  if (Number.isNaN(parsed)) return ""
  const diffSec = Math.max(0, Math.floor((nowMs - parsed) / 1000))
  if (diffSec < 60) return isZh ? "刚刚" : "now"
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h`
  const diffDays = Math.floor(diffHr / 24)
  return `${diffDays}d`
}

export function ProjectConversationsTree({
  projectId,
  activeConversationId,
  collapsed = false,
  onNavigate,
}: ProjectConversationsTreeProps) {
  const { t, i18n } = useTranslation()
  const isZh = Boolean(i18n?.language?.startsWith("zh"))
  const navigate = useNavigate()
  const authUserId = useContext(AuthContext)?.user?.id ?? null
  const [projects, setProjects] = useState<SidebarProject[]>([])
  const [expandedIds, setExpandedIds] = useState<ReadonlySet<string>>(() =>
    projectId ? new Set([projectId]) : new Set(),
  )
  const [conversationsByProject, setConversationsByProject] = useState<
    Record<string, ProjectConversationSummary[]>
  >({})
  const [loadedProjects, setLoadedProjects] = useState<ReadonlySet<string>>(
    () => new Set(),
  )
  const fetchedProjectsRef = useRef<Set<string>>(new Set())
  const [creatingForProject, setCreatingForProject] = useState<string | null>(
    null,
  )
  const [renamingConv, setRenamingConv] =
    useState<ProjectConversationSummary | null>(null)
  const [renamingProject, setRenamingProject] =
    useState<SidebarProject | null>(null)
  const [deletingProject, setDeletingProject] =
    useState<SidebarProject | null>(null)
  const [deletingConv, setDeletingConv] =
    useState<ProjectConversationSummary | null>(null)
  const [renameDraft, setRenameDraft] = useState("")
  const [renameBusy, setRenameBusy] = useState(false)
  const [nowMs, setNowMs] = useState<number | null>(null)
  const [activityState, setActivityState] = useState(() =>
    getConversationActivitySnapshot(),
  )

  useEffect(() => {
    const sync = () => setActivityState(getConversationActivitySnapshot())
    sync()
    window.addEventListener(CONVERSATION_ACTIVITY_EVENT, sync)
    return () => window.removeEventListener(CONVERSATION_ACTIVITY_EVENT, sync)
  }, [projectId])

  useEffect(() => {
    setNowMs(Date.now())
    const timer = window.setInterval(() => setNowMs(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const loadConversations = useCallback(async (pid: string) => {
    fetchedProjectsRef.current.add(pid)
    try {
      const list = await listProjectConversations(pid)
      if (Array.isArray(list)) {
        setConversationsByProject((prev) => ({ ...prev, [pid]: list }))
      }
    } catch {
      // Keep existing tree visible on transient fetch error
    } finally {
      setLoadedProjects((prev) => {
        if (prev.has(pid)) return prev
        const next = new Set(prev)
        next.add(pid)
        return next
      })
    }
  }, [])

  // Load recent projects for the sidebar Projects list.
  const loadProjects = useCallback(async () => {
    try {
      const res = await apiFetch(
        "/api/v1/projects?skip=0&limit=10&include_thumbnail=false",
        { toast: false },
      )
      if (!res.ok) return
      const rows = (await res.json()) as { id?: string; title?: string }[]
      if (!Array.isArray(rows)) return
      const parsed = rows
        .filter((r): r is SidebarProject => Boolean(r?.id))
        .map((r) => ({ id: r.id, title: r.title || t("common.untitled") }))
      setProjects(parsed)
      if (!projectId && parsed[0]) {
        setExpandedIds((prev) =>
          prev.size > 0 ? prev : new Set([parsed[0].id]),
        )
      }
    } catch {
      // Keep existing project list on transient fetch error
    }
  }, [projectId, t])

  useEffect(() => {
    void loadProjects()
  }, [loadProjects, authUserId])

  useEffect(() => {
    const onFocus = () => {
      void loadProjects()
    }
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [loadProjects])

  // Always keep the active project expanded.
  useEffect(() => {
    if (!projectId) return
    setExpandedIds((prev) => {
      if (prev.has(projectId)) return prev
      const next = new Set(prev)
      next.add(projectId)
      return next
    })
  }, [projectId])

  // Load conversations once per expanded project when sidebar is expanded.
  useEffect(() => {
    if (collapsed) return
    for (const pid of expandedIds) {
      if (!fetchedProjectsRef.current.has(pid)) {
        void loadConversations(pid)
      }
    }
  }, [expandedIds, collapsed, loadConversations])

  useEffect(() => {
    const onChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ projectId?: string }>).detail
      void loadProjects()
      if (detail?.projectId) {
        void loadConversations(detail.projectId)
      } else if (projectId) {
        void loadConversations(projectId)
      }
    }
    window.addEventListener(CONVERSATIONS_CHANGED_EVENT, onChanged)
    return () =>
      window.removeEventListener(CONVERSATIONS_CHANGED_EVENT, onChanged)
  }, [projectId, loadConversations, loadProjects])

  const orderedProjects = useMemo<SidebarProject[]>(() => {
    const list: SidebarProject[] = []
    const seen = new Set<string>()
    if (projectId) {
      const activeMatch = projects.find((p) => p.id === projectId)
      list.push(
        activeMatch ?? {
          id: projectId,
          title: t("nav.myProjects"),
        },
      )
      seen.add(projectId)
    }
    for (const p of projects) {
      if (seen.has(p.id)) continue
      seen.add(p.id)
      list.push(p)
    }
    return list
  }, [projects, projectId, t])

  const toggleProject = (pid: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(pid)) next.delete(pid)
      else next.add(pid)
      return next
    })
  }

  const handleNewChat = async (pid: string) => {
    if (creatingForProject) return
    setCreatingForProject(pid)
    try {
      const created = await createProjectConversation(pid)
      setConversationsByProject((prev) => {
        const current = prev[pid] ?? []
        return {
          ...prev,
          [pid]: [created, ...current.filter((c) => c.id !== created.id)],
        }
      })
      setExpandedIds((prev) => new Set(prev).add(pid))
      onNavigate?.()
      await navigate({
        to: "/projects/$id",
        params: { id: pid },
        search: { c: created.id },
      })
    } catch {
      // apiFetch displays toast
    } finally {
      setCreatingForProject(null)
    }
  }

  const handleSelect = (pid: string, conversationId: string) => {
    markConversationSeen(pid, conversationId)
    onNavigate?.()
    void navigate({
      to: "/projects/$id",
      params: { id: pid },
      search: { c: conversationId },
    })
  }

  const openRenameConv = (conv: ProjectConversationSummary) => {
    setRenamingProject(null)
    setRenamingConv(conv)
    setRenameDraft(conv.title)
  }

  const openRenameProject = (proj: SidebarProject) => {
    setRenamingConv(null)
    setRenamingProject(proj)
    setRenameDraft(proj.title)
  }

  const handleRenameSubmit = async () => {
    if (renameBusy) return
    const trimmed = renameDraft.trim()
    if (!trimmed) return
    setRenameBusy(true)
    try {
      if (renamingConv) {
        const updated = await renameConversation(renamingConv.id, trimmed)
        setConversationsByProject((prev) => ({
          ...prev,
          [updated.project_id]: (prev[updated.project_id] ?? []).map((c) =>
            c.id === updated.id ? updated : c,
          ),
        }))
        setRenamingConv(null)
      } else if (renamingProject) {
        const res = await apiFetch(`/api/v1/projects/${renamingProject.id}`, {
          method: "PUT",
          body: { title: trimmed },
        })
        if (res.ok) {
          setProjects((prev) =>
            prev.map((p) =>
              p.id === renamingProject.id ? { ...p, title: trimmed } : p,
            ),
          )
          setRenamingProject(null)
        }
      }
    } catch {
      // apiFetch displays toast
    } finally {
      setRenameBusy(false)
    }
  }

  const handleCompact = async (conv: ProjectConversationSummary) => {
    try {
      const res = await compactConversation(conv.id, conv.project_id)
      setConversationsByProject((prev) => ({
        ...prev,
        [conv.project_id]: (prev[conv.project_id] ?? []).map((c) =>
          c.id === conv.id
            ? { ...c, compacted: true, compacted_at: res.compacted_at }
            : c,
        ),
      }))
      toast.success(
        t("conversations.compactSuccess", { count: res.message_count }),
      )
    } catch {
      // apiFetch displays toast
    }
  }

  if (orderedProjects.length === 0) return null

  // Collapsed 48px icon rail: show each project as a clean folder icon (affectUI AppShell rail pattern)
  if (collapsed) {
    return (
      <div
        data-slot="project-conversations-tree"
        className="mt-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto no-scrollbar"
      >
        {orderedProjects.map((proj) => {
          const isCurrent = proj.id === projectId
          return (
            <Tooltip key={proj.id} content={proj.title} side="right">
              <button
                type="button"
                aria-label={proj.title}
                aria-current={isCurrent ? "page" : undefined}
                onClick={() => {
                  onNavigate?.()
                  void navigate({
                    to: "/projects/$id",
                    params: { id: proj.id },
                  })
                }}
                className="ui-as-side__item"
              >
                {isCurrent ? (
                  <FolderOpen size={16} aria-hidden="true" />
                ) : (
                  <Folder size={16} aria-hidden="true" />
                )}
              </button>
            </Tooltip>
          )
        })}
      </div>
    )
  }

  return (
    <div
      data-slot="project-conversations-tree"
      className="mt-3 flex min-h-0 flex-1 flex-col gap-1"
    >
      {/* Pure static gray section label — matches affectUI AppShell .ui-au-shell-side__label */}
      <span className="px-2 pb-0.5 text-xs font-medium text-muted-foreground/75">
        {t("conversations.sectionTitle")}
      </span>

      {/* Projects & Nested Indented Conversations */}
      <div className="thin-scroll flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto">
        {orderedProjects.map((proj) => {
          const isExpanded = expandedIds.has(proj.id)
          const isCurrentProject = proj.id === projectId
          const items = conversationsByProject[proj.id] ?? []
          const isLoaded = loadedProjects.has(proj.id)
          const resolvedActiveId = isCurrentProject
            ? (activeConversationId ?? items[0]?.id)
            : undefined

          return (
            <div key={proj.id} className="flex flex-col gap-0.5">
              {/* Project Folder Row — owns expand/collapse with AppShell hover chevron, hover ⋮ menu, and + new chat */}
              <div className="group/proj relative flex h-8 items-center rounded-lg border border-transparent text-muted-foreground transition-colors hover:bg-[var(--hover)] hover:text-foreground">
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  onClick={() => toggleProject(proj.id)}
                  className="flex h-full min-w-0 flex-1 items-center gap-2 rounded-lg px-2 text-left focus-visible:outline-2 focus-visible:outline-ring"
                >
                  {isExpanded ? (
                    <FolderOpen
                      className="size-4 shrink-0 text-muted-foreground/75"
                      aria-hidden="true"
                    />
                  ) : (
                    <Folder
                      className="size-4 shrink-0 text-muted-foreground/75"
                      aria-hidden="true"
                    />
                  )}
                  <span
                    className="min-w-0 truncate text-[13px] leading-5"
                    title={proj.title}
                  >
                    {proj.title}
                  </span>
                  <ChevronRight
                    className={cn(
                      "-ml-1 size-3.5 shrink-0 text-muted-foreground/65 opacity-0 transition-[opacity,transform] duration-150 group-hover/proj:opacity-100 group-focus-within/proj:opacity-100 max-md:opacity-100",
                      isExpanded && "rotate-90",
                    )}
                    aria-hidden="true"
                  />
                </button>
                <div className="flex shrink-0 items-center pr-0.5 opacity-0 transition-opacity group-hover/proj:opacity-100 group-focus-within/proj:opacity-100 max-md:opacity-100">
                  <DropdownMenu
                    align="end"
                    items={[
                      {
                        label: t("conversations.openProject"),
                        icon: <FolderOpen className="size-3.5" />,
                        onSelect: () => {
                          onNavigate?.()
                          void navigate({
                            to: "/projects/$id",
                            params: { id: proj.id },
                          })
                        },
                      },
                      {
                        label: t("conversations.newChat"),
                        icon: <Plus className="size-3.5" />,
                        onSelect: () => {
                          void handleNewChat(proj.id)
                        },
                      },
                      {
                        label: t("conversations.renameProject"),
                        icon: <Pencil className="size-3.5" />,
                        onSelect: () => openRenameProject(proj),
                      },
                      {
                        label: t("common.delete"),
                        icon: <Trash2 className="size-3.5" />,
                        danger: true,
                        divider: true,
                        onSelect: () => setDeletingProject(proj),
                      },
                    ]}
                    trigger={({ triggerProps }) => (
                      <IconButton
                        {...triggerProps}
                        size="sm"
                        variant="ghost"
                        icon={<EllipsisVertical className="size-3.5" />}
                        label={t("conversations.projectActions")}
                      />
                    )}
                  />
                  <Tooltip content={t("conversations.newChat")} side="right">
                    <IconButton
                      size="sm"
                      variant="ghost"
                      icon={<Plus className="size-3.5" />}
                      label={t("conversations.newChat")}
                      disabled={creatingForProject === proj.id}
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleNewChat(proj.id)
                      }}
                    />
                  </Tooltip>
                </div>
              </div>

              {/* Indented Conversations under this Project — pl-8 + 1px border aligns flush with project title (1px + px-2 + size-4 + gap-2 = 33px) */}
              {isExpanded ? (
                <div className="flex flex-col gap-0.5">
                  {isLoaded && items.length === 0 ? (
                    <p className="py-1 pl-[33px] pr-2 text-xs text-muted-foreground/60">
                      {t("conversations.empty")}
                    </p>
                  ) : (
                    items.map((conv) => {
                      const active =
                        isCurrentProject && conv.id === resolvedActiveId
                      const fallbackActiveKey = `${proj.id}:__active__`
                      const working =
                        conv.has_active_job ||
                        activityState.busy.has(conv.id) ||
                        (active && activityState.busy.has(fallbackActiveKey))
                      const pendingOverride =
                        activityState.pendingQuestion.get(conv.id) ??
                        (active
                          ? activityState.pendingQuestion.get(fallbackActiveKey)
                          : undefined)
                      const awaitingInput =
                        !working &&
                        (pendingOverride ?? Boolean(conv.has_pending_question))
                      const relTime =
                        nowMs != null
                          ? formatCompactAge(
                              conv.updated_at ?? conv.created_at,
                              nowMs,
                              isZh,
                            )
                          : ""

                      return (
                        <div
                          key={conv.id}
                          data-conversation-id={conv.id}
                          data-active={active || undefined}
                          className={cn(
                            "group relative flex h-8 items-center rounded-lg border transition-colors",
                            active
                              ? "border-foreground/15 bg-[var(--select)] text-foreground"
                              : "border-transparent text-muted-foreground hover:bg-[var(--hover)] hover:text-foreground",
                          )}
                        >
                          <button
                            type="button"
                            onClick={() => handleSelect(proj.id, conv.id)}
                            className="flex h-full min-w-0 flex-1 items-center justify-between gap-2 rounded-lg pl-8 pr-2.5 text-left focus-visible:outline-2 focus-visible:outline-ring"
                          >
                            <span
                              className={cn(
                                "min-w-0 flex-1 truncate text-[13px] leading-5",
                                active
                                  ? "font-medium text-foreground"
                                  : "font-normal",
                              )}
                            >
                              {conv.title || t("conversations.defaultTitle")}
                            </span>
                            <span className="flex shrink-0 items-center gap-1.5 text-[11px] tabular-nums text-muted-foreground/65 transition-opacity group-hover:opacity-0 group-focus-within:opacity-0 group-has-[[aria-expanded='true']]:opacity-0">
                              {working ? (
                                <span
                                  title={t("conversations.activeJob")}
                                  aria-label={t("conversations.activeJob")}
                                  className="ui-conv-dots"
                                >
                                  <i
                                    className="bg-foreground/85"
                                    style={{ animationDelay: "0ms" }}
                                  />
                                  <i
                                    className="bg-foreground/85"
                                    style={{ animationDelay: "180ms" }}
                                  />
                                  <i
                                    className="bg-foreground/85"
                                    style={{ animationDelay: "180ms" }}
                                  />
                                  <i
                                    className="bg-foreground/85"
                                    style={{ animationDelay: "360ms" }}
                                  />
                                </span>
                              ) : awaitingInput ? (
                                <Tooltip
                                  content={t("conversations.awaitingInput")}
                                  side="right"
                                >
                                  <span
                                    data-slot="awaiting-input-indicator"
                                    aria-label={t(
                                      "conversations.awaitingInput",
                                    )}
                                    className="relative inline-flex size-5 items-center justify-center text-foreground/80"
                                  >
                                    <CircleHelp
                                      className="size-3.5"
                                      aria-hidden="true"
                                    />
                                    <span
                                      aria-hidden="true"
                                      className="absolute right-0 top-0 size-1.5 rounded-full bg-[var(--aui-warning)]"
                                    />
                                  </span>
                                </Tooltip>
                              ) : relTime ? (
                                <span>{relTime}</span>
                              ) : null}
                            </span>
                          </button>
                          <div className="pointer-events-none absolute inset-y-0.5 right-0.5 flex items-center rounded-r-lg bg-gradient-to-l from-[var(--page)] via-[var(--page)]/90 to-transparent pl-5 pr-1 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 group-has-[[aria-expanded='true']]:pointer-events-auto group-has-[[aria-expanded='true']]:opacity-100 max-md:pointer-events-auto max-md:opacity-100">
                            <DropdownMenu
                              align="start"
                              trigger={({ triggerProps }) => (
                                <IconButton
                                  {...triggerProps}
                                  size="sm"
                                  variant="ghost"
                                  className="rounded-full"
                                  icon={<EllipsisVertical className="size-3.5" />}
                                  label={t("conversations.moreActions")}
                                />
                              )}
                              items={[
                                {
                                  label: t("conversations.rename"),
                                  icon: <Pencil className="size-3.5" />,
                                  onSelect: () => openRenameConv(conv),
                                },
                                {
                                  label: t("conversations.compact"),
                                  icon: <Minimize2 className="size-3.5" />,
                                  onSelect: () => {
                                    void handleCompact(conv)
                                  },
                                },
                                {
                                  label: t("conversations.deleteConversation"),
                                  icon: <Trash2 className="size-3.5" />,
                                  danger: true,
                                  divider: true,
                                  onSelect: () => setDeletingConv(conv),
                                },
                              ]}
                            />
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              ) : null}
            </div>
          )
        })}
        <button
          type="button"
          onClick={() => {
            onNavigate?.()
            void navigate({ to: "/projects" })
          }}
          className="mt-1 flex h-7 w-full items-center justify-between rounded-lg px-2 text-xs text-muted-foreground/80 transition-colors hover:bg-[var(--hover)] hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
        >
          <span>{t("conversations.viewAllProjects")}</span>
          <ArrowRight className="size-3 shrink-0 opacity-70" />
        </button>
      </div>

      <Dialog
        open={renamingConv != null || renamingProject != null}
        onOpenChange={(open) => {
          if (!open) {
            setRenamingConv(null)
            setRenamingProject(null)
          }
        }}
        title={
          renamingProject
            ? t("conversations.renameProject")
            : t("conversations.renameTitle")
        }
        closeLabel={t("common.close")}
        width={400}
        footer={
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setRenamingConv(null)
                setRenamingProject(null)
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              variant="primary"
              loading={renameBusy}
              disabled={!renameDraft.trim()}
              onClick={() => {
                void handleRenameSubmit()
              }}
            >
              {t("common.save")}
            </Button>
          </div>
        }
      >
        <TextField
          value={renameDraft}
          onChange={(e) => setRenameDraft(e.target.value)}
          placeholder={t("conversations.renamePlaceholder")}
          aria-label={t("conversations.renamePlaceholder")}
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) {
              e.preventDefault()
              void handleRenameSubmit()
            }
          }}
        />
      </Dialog>

      {deletingProject ? (
        <DeleteProjectDialog
          projectId={deletingProject.id}
          title={deletingProject.title}
          open={Boolean(deletingProject)}
          onOpenChange={(open) => {
            if (!open) setDeletingProject(null)
          }}
          onDeleted={() => {
            const deletedId = deletingProject.id
            setDeletingProject(null)
            setProjects((prev) => prev.filter((p) => p.id !== deletedId))
            setConversationsByProject((prev) => {
              const next = { ...prev }
              delete next[deletedId]
              return next
            })
            if (deletedId === projectId) {
              onNavigate?.()
              void navigate({ to: "/home" })
            }
          }}
        />
      ) : null}

      <AlertDialog
        open={deletingConv != null}
        onOpenChange={(open) => {
          if (!open) setDeletingConv(null)
        }}
        danger
        title={t("conversations.deleteConversationConfirm")}
        description={t("conversations.deleteConversationDesc", {
          title: deletingConv?.title || t("conversations.defaultTitle"),
        })}
        cancelLabel={t("common.cancel")}
        confirmLabel={t("common.delete")}
        onConfirm={async () => {
          if (!deletingConv) return
          const target = deletingConv
          await deleteConversation(target.id, target.project_id)
          const remaining = (
            conversationsByProject[target.project_id] ?? []
          ).filter((c) => c.id !== target.id)
          setConversationsByProject((prev) => ({
            ...prev,
            [target.project_id]: remaining,
          }))
          setDeletingConv(null)
          if (
            target.project_id === projectId &&
            (activeConversationId === target.id || !activeConversationId)
          ) {
            onNavigate?.()
            if (remaining[0]) {
              void navigate({
                to: "/projects/$id",
                params: { id: target.project_id },
                search: { c: remaining[0].id },
              })
            } else {
              void navigate({
                to: "/projects/$id",
                params: { id: target.project_id },
              })
            }
          }
        }}
      />
    </div>
  )
}
