"use client"

import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import {
  Ellipsis,
  MessageSquare,
  Minimize2,
  Pencil,
  Plus,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Button } from "@/components/ui/button-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { TextField } from "@/components/ui/text-field-clean"
import {
  compactConversation,
  CONVERSATIONS_CHANGED_EVENT,
  createProjectConversation,
  formatRelativeTime,
  listProjectConversations,
  renameConversation,
  type ProjectConversationSummary,
} from "@/lib/workbench"
import { cn } from "@/lib/utils"

export interface ProjectConversationsTreeProps {
  projectId: string
  activeConversationId?: string
  onNavigate?: () => void
}

export function ProjectConversationsTree({
  projectId,
  activeConversationId,
  onNavigate,
}: ProjectConversationsTreeProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [items, setItems] = useState<ProjectConversationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [renaming, setRenaming] = useState<ProjectConversationSummary | null>(null)
  const [renameDraft, setRenameDraft] = useState("")
  const [renameBusy, setRenameBusy] = useState(false)
  const [nowMs, setNowMs] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      const list = await listProjectConversations(projectId)
      setItems(list)
    } catch {
      // Keep existing tree visible on transient fetch error
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    setLoading(true)
    void load()
  }, [load])

  useEffect(() => {
    setNowMs(Date.now())
    const timer = window.setInterval(() => setNowMs(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const onChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ projectId?: string }>).detail
      if (!detail?.projectId || detail.projectId === projectId) {
        void load()
      }
    }
    window.addEventListener(CONVERSATIONS_CHANGED_EVENT, onChanged)
    return () => window.removeEventListener(CONVERSATIONS_CHANGED_EVENT, onChanged)
  }, [projectId, load])

  const handleNewChat = async () => {
    if (creating) return
    setCreating(true)
    try {
      const created = await createProjectConversation(projectId)
      setItems((prev) => [created, ...prev.filter((c) => c.id !== created.id)])
      onNavigate?.()
      await navigate({
        to: "/projects/$id",
        params: { id: projectId },
        search: { c: created.id },
      })
    } catch {
      // apiFetch displays toast
    } finally {
      setCreating(false)
    }
  }

  const handleSelect = (conversationId: string) => {
    onNavigate?.()
    void navigate({
      to: "/projects/$id",
      params: { id: projectId },
      search: { c: conversationId },
    })
  }

  const openRename = (conv: ProjectConversationSummary) => {
    setRenaming(conv)
    setRenameDraft(conv.title)
  }

  const handleRenameSubmit = async () => {
    if (!renaming || renameBusy) return
    const trimmed = renameDraft.trim()
    if (!trimmed) return
    setRenameBusy(true)
    try {
      const updated = await renameConversation(renaming.id, trimmed)
      setItems((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
      setRenaming(null)
    } catch {
      // apiFetch displays toast
    } finally {
      setRenameBusy(false)
    }
  }

  const handleCompact = async (conv: ProjectConversationSummary) => {
    try {
      const res = await compactConversation(conv.id, projectId)
      setItems((prev) =>
        prev.map((c) =>
          c.id === conv.id
            ? { ...c, compacted: true, compacted_at: res.compacted_at }
            : c,
        ),
      )
      toast.success(
        t("conversations.compactSuccess", { count: res.message_count }),
      )
    } catch {
      // apiFetch displays toast
    }
  }

  const resolvedActiveId = activeConversationId ?? items[0]?.id

  return (
    <div
      data-slot="project-conversations-tree"
      className="mt-1 flex min-h-0 flex-1 flex-col gap-1 border-t border-border/60 pt-2"
    >
      <div className="flex items-center justify-between gap-1 px-2">
        <span className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {t("conversations.sectionTitle")}
        </span>
        <IconButton
          size="sm"
          variant="ghost"
          icon={<Plus className="size-3.5" />}
          label={t("conversations.newChat")}
          disabled={creating}
          onClick={() => { void handleNewChat() }}
        />
      </div>

      <div className="thin-scroll flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto pr-0.5">
        {!loading && items.length === 0 ? (
          <p className="px-2 py-2 text-xs text-muted-foreground">
            {t("conversations.empty")}
          </p>
        ) : (
          items.map((conv) => {
            const active = conv.id === resolvedActiveId
            const relTime =
              nowMs != null
                ? formatRelativeTime(conv.updated_at ?? conv.created_at, t, nowMs)
                : ""
            return (
              <div
                key={conv.id}
                data-conversation-id={conv.id}
                data-active={active || undefined}
                className={cn(
                  "group relative flex items-center gap-1 rounded-md pr-1 transition-colors",
                  active
                    ? "bg-background text-foreground shadow-2xs"
                    : "text-muted-foreground hover:bg-background/70 hover:text-foreground",
                )}
              >
                <button
                  type="button"
                  onClick={() => handleSelect(conv.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 rounded-md py-1.5 pl-2 pr-1 text-left focus-visible:outline-2 focus-visible:outline-ring"
                >
                  <span className="relative flex size-4 shrink-0 items-center justify-center">
                    <MessageSquare className="size-3.5 opacity-70" />
                    {conv.has_active_job ? (
                      <span
                        title={t("conversations.activeJob")}
                        className="absolute -right-0.5 -top-0.5 size-2 rounded-full bg-foreground/85 ring-2 ring-background motion-safe:animate-pulse"
                      />
                    ) : null}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-medium leading-4">
                      {conv.title || t("conversations.defaultTitle")}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-[10.5px] leading-3 text-muted-foreground/80">
                      <span>{t("conversations.messagesCount", { count: conv.message_count })}</span>
                      {relTime ? <span>· {relTime}</span> : null}
                      {conv.compacted ? (
                        <span className="rounded bg-muted px-1 text-[9.5px]">
                          {t("conversations.compactedBadge")}
                        </span>
                      ) : null}
                    </span>
                  </span>
                </button>
                <div className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 max-md:opacity-100">
                  <DropdownMenu
                    align="end"
                    trigger={({ triggerProps }) => (
                      <IconButton
                        {...triggerProps}
                        size="sm"
                        variant="ghost"
                        icon={<Ellipsis className="size-3.5" />}
                        label={t("conversations.moreActions")}
                      />
                    )}
                    items={[
                      {
                        label: t("conversations.rename"),
                        icon: <Pencil className="size-3.5" />,
                        onSelect: () => openRename(conv),
                      },
                      {
                        label: t("conversations.compact"),
                        icon: <Minimize2 className="size-3.5" />,
                        onSelect: () => { void handleCompact(conv) },
                      },
                    ]}
                  />
                </div>
              </div>
            )
          })
        )}
      </div>

      <Dialog
        open={renaming != null}
        onOpenChange={(open) => { if (!open) setRenaming(null) }}
        title={t("conversations.renameTitle")}
        closeLabel={t("common.close")}
        width={400}
        footer={
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setRenaming(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              variant="primary"
              loading={renameBusy}
              disabled={!renameDraft.trim()}
              onClick={() => { void handleRenameSubmit() }}
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
    </div>
  )
}
