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

  // Bottom line: live statuses show the current stage as plain text (the
  // animated tile carries the motion); settled projects show the relative
  // update time (the raw enum never leaks into the UI).
  const active = project.status === "processing" || project.status === "uploading"
  // Unsettled projects (draft included) never show a bare static tile: the
  // card stays alive — drifting glow + brand fill. A draft is "waiting on
  // you", a live run is "working"; the label below disambiguates.
  const live = active || project.status === "draft"

  return (
    <>
      <Link
        to="/projects/$id"
        params={{ id: project.id }}
        // The project page is always canvas + dock (ADR-051) — its own state
        // drives the dock's form (draft ⟺ the parked task book docks the
        // confirm panel; processing ⟺ the dock attaches to the live run).
        className="group flex flex-col gap-2"
      >
        {/* Full-bleed thumbnail — no card container, no inset padding: the
            image carries its own radius and the text lives below it
            (LTX/ElevenLabs projects-grid pattern, 2026-08-04). */}
        <div
          className={`relative flex aspect-video items-center justify-center overflow-hidden rounded-xl ${
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
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{project.title}</p>
          <div className="mt-0.5 flex items-center justify-between gap-1">
            <p className="truncate text-xs text-muted-foreground">
              {active ? (
                // Plain text — the animated tile above already carries the
                // "working" signal, so the stage label doesn't shimmer.
                t(`projects.status.${project.status}`)
              ) : project.status === "draft" ? (
                // Same muted gray as every other status in this slot — no
                // amber dot, no color coding.
                t("projects.status.draft")
              ) : project.updated_at ? (
                formatRelativeTime(project.updated_at, i18n.language)
              ) : null}
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
