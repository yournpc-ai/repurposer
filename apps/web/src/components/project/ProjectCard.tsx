import { Link } from "@tanstack/react-router"
import { FolderKanban, MoreHorizontal, Pencil, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { apiDelete, apiPut } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { formatDuration, formatRelativeTime } from "@/lib/utils"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

interface Project {
  id: string
  title: string
  status: string
  updated_at?: string | null
  thumbnail_url?: string | null
  thumbnail_duration?: number | null
  thumbnail_aspect?: string | null
}

interface ProjectCardProps {
  project: Project
  /** Refetch hook for the list after a rename/delete goes through. */
  onChanged?: () => void
}

export function ProjectCard({ project, onChanged }: ProjectCardProps) {
  const { t, i18n } = useTranslation()
  // Fall back to the placeholder icon until the video decodes; if it never
  // does (404, corrupt file), stay on the fallback rather than show a blank box.
  const [videoReady, setVideoReady] = useState(false)
  const [videoFailed, setVideoFailed] = useState(false)

  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [renameValue, setRenameValue] = useState(project.title)
  const [busy, setBusy] = useState(false)

  const thumbnailSrc = project.thumbnail_url
    ? project.thumbnail_url.startsWith("/")
      ? API_URL + project.thumbnail_url
      : project.thumbnail_url
    : null
  const showVideo = thumbnailSrc && !videoFailed

  // Bottom line: live statuses get a shimmering label; settled projects show
  // the relative update time (the raw enum never leaks into the UI).
  const active = project.status === "processing" || project.status === "uploading"

  const handleRename = async () => {
    const title = renameValue.trim()
    if (!title || busy) return
    if (title === project.title) {
      setRenameOpen(false)
      return
    }
    setBusy(true)
    try {
      const res = await apiPut(`/api/v1/projects/${project.id}`, { title })
      if (res.ok) {
        setRenameOpen(false)
        onChanged?.()
      }
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    if (busy) return
    setBusy(true)
    try {
      const res = await apiDelete(`/api/v1/projects/${project.id}`)
      if (res.ok) {
        setDeleteOpen(false)
        onChanged?.()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Link
        to="/projects/$id"
        params={{ id: project.id }}
        // draft ⟺ plan never confirmed → resume the confirm chat; processing
        // ⟺ a run is live → attach the chat overlay to it instead of landing
        // on the bare results page.
        search={
          project.status === "draft"
            ? { overlay: "intent" }
            : project.status === "processing"
              ? { overlay: "run" }
              : {}
        }
        className="group flex flex-col gap-3 rounded-xl bg-card/50 p-3 transition-all hover:bg-accent"
      >
        <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-primary/10">
          {showVideo ? (
            <video
              src={thumbnailSrc}
              muted
              playsInline
              preload="metadata"
              onLoadedData={() => setVideoReady(true)}
              onError={() => setVideoFailed(true)}
              className={`h-full w-full object-cover transition-transform duration-300 group-hover:scale-105 ${
                videoReady ? "opacity-100" : "opacity-0"
              }`}
            />
          ) : null}
          {!showVideo || !videoReady ? (
            <FolderKanban className="absolute h-7 w-7 text-primary" />
          ) : null}
          {showVideo && videoReady && project.thumbnail_duration != null && (
            <div className="absolute bottom-1.5 right-1.5 flex items-center gap-1">
              <Badge variant="secondary" className="rounded-md tabular-nums">
                {formatDuration(project.thumbnail_duration)}
              </Badge>
            </div>
          )}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{project.title}</p>
          <div className="mt-0.5 flex items-center justify-between gap-1">
            <p className="truncate text-xs text-muted-foreground">
              {active ? (
                <span className="shimmer">{t(`projects.status.${project.status}`)}</span>
              ) : project.status === "draft" ? (
                // draft ⟺ created but generation never confirmed — the only
                // useful action is resuming the plan-confirm chat.
                <span className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                  {t("projects.status.draft")}
                </span>
              ) : project.updated_at ? (
                formatRelativeTime(project.updated_at, i18n.language)
              ) : null}
            </p>
            {/* "···" menu — the wrapper preventDefault+stopPropagation keeps
                the wrapping <a> from navigating (stopPropagation alone leaves
                the browser's default anchor behavior intact). The button's
                hover uses bg-background because --muted == --accent here:
                ghost's default hover would be invisible on the hovered card. */}
            <div
              className="shrink-0"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
              }}
            >
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("projects.menuMore")}
                      className="hover:bg-background"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  }
                />
                <DropdownMenuContent align="end" className="w-40">
                  <DropdownMenuGroup>
                    <DropdownMenuItem
                      onClick={() => {
                        setRenameValue(project.title)
                        setRenameOpen(true)
                      }}
                    >
                      <Pencil className="mr-2 h-4 w-4" />
                      {t("projects.rename")}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={() => setDeleteOpen(true)}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      {t("common.delete")}
                    </DropdownMenuItem>
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </Link>

      {/* Rename */}
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("projects.renameTitle")}</DialogTitle>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleRename()
            }}
            placeholder={t("projects.renamePlaceholder")}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button disabled={!renameValue.trim() || busy} onClick={handleRename}>
              {busy ? t("common.saving") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("projects.deleteConfirm")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t("projects.deleteDesc", { title: project.title })}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" disabled={busy} onClick={handleDelete}>
              {busy ? t("common.loading") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
