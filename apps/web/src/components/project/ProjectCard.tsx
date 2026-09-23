import { Link } from "@tanstack/react-router"
import { FolderKanban, MoreHorizontal, Pencil, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { BrandLoader } from "@/components/BrandLoader"
import { ProcessingTile } from "@/components/ProcessingTile"
import {
  DeleteProjectDialog,
  RenameProjectDialog,
} from "@/components/project/project-dialogs"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { formatDuration, formatRelativeTime } from "@/lib/utils"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

interface Project {
  id: string
  title: string
  status: string
  created_at?: string | null
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

  const thumbnailSrc = project.thumbnail_url
    ? project.thumbnail_url.startsWith("/")
      ? API_URL + project.thumbnail_url
      : project.thumbnail_url
    : null
  const showVideo = thumbnailSrc && !videoFailed

  // Bottom line: one slot, two facts — the stage label (while unsettled) and
  // the relative time. The list is sorted by time, so the time must always be
  // readable; a bare status without its timestamp hides the sort's readout.
  const active = project.status === "processing" || project.status === "uploading"
  // Unsettled projects (draft included) never show a bare static tile: the
  // card stays alive — drifting glow + brand fill. A draft is "waiting on
  // you", a live run is "working"; the label below disambiguates.
  const live = active || project.status === "draft"
  const stageLabel = active
    ? t(`projects.status.${project.status}`)
    : project.status === "draft"
      ? // Same muted gray as every other status in this slot — no amber dot,
        // no color coding.
        t("projects.status.draft")
      : null
  const when = project.updated_at ?? project.created_at
  const timeLabel = when ? formatRelativeTime(when, i18n.language) : null
  const bottomLine = [stageLabel, timeLabel].filter(Boolean).join(" · ")

  return (
    <>
      <Link
        to="/projects/$id"
        params={{ id: project.id }}
        // The project page is always canvas + dock (ADR-051) — its own state
        // drives the dock's form (draft ⟺ the parked plan docks the
        // confirm panel; processing ⟺ the dock attaches to the live run).
        className="group block"
      >
        {/* Container card — the raised fill step (bg-card on the 0.96 page,
            ADR-046 elevation law) is the whole separation: no shadow, no
            ring (the fills already distinguish). The thumbnail insets inside
            with a concentric radius, the text row lives on the card. */}
        <div className="rounded-xl bg-card p-1.5">
          <div
            className={`relative flex aspect-video items-center justify-center overflow-hidden rounded-lg ${
              // Neutral base for the live mist — bg-primary/10 would leak hue
              // through it; the tinted base is only for the settled thumbnail.
              live ? "bg-muted" : "bg-primary/10"
            }`}
          >
            {live ? (
              // Unsettled project — the layered processing tile is the life
              // signal (matte base, light shaft, mist, grain, halo), so the
              // stage label below stays plain text.
              <ProcessingTile>
                <BrandLoader className="relative h-8 w-8" />
              </ProcessingTile>
            ) : (
              <>
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
              </>
            )}
          </div>
          <div className="min-w-0 px-1.5 pb-1 pt-2">
            <p className="truncate text-sm font-medium">{project.title}</p>
            <div className="mt-0.5 flex items-center justify-between gap-1">
              <p className="truncate text-xs text-muted-foreground">
                {bottomLine}
              </p>
            {/* "···" menu — the wrapper preventDefault+stopPropagation keeps
                the wrapping <a> from navigating (stopPropagation alone leaves
                the browser's default anchor behavior intact). */}
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
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  }
                />
                <DropdownMenuContent align="end" className="w-40">
                  <DropdownMenuGroup>
                    <DropdownMenuItem
                      onClick={() => setRenameOpen(true)}
                    >
                      <Pencil className="mr-2 h-4 w-4" />
                      {t("projects.rename")}
                    </DropdownMenuItem>
                    {/* Hidden while a run is live: deleting mid-run races the
                        worker — it would finish rendering and re-write objects
                        under the already-swept TOS prefixes, leaving orphans. */}
                    {!active && (
                      <DropdownMenuItem
                        variant="destructive"
                        onClick={() => setDeleteOpen(true)}
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        {t("common.delete")}
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            </div>
          </div>
        </div>
      </Link>

      <RenameProjectDialog
        projectId={project.id}
        title={project.title}
        open={renameOpen}
        onOpenChange={setRenameOpen}
        onRenamed={() => onChanged?.()}
      />
      <DeleteProjectDialog
        projectId={project.id}
        title={project.title}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={() => onChanged?.()}
      />
    </>
  )
}
