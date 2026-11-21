import { Link } from "@tanstack/react-router"
import { FolderKanban, MoreHorizontal, Pencil, Trash2 } from "lucide-react"
import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { BrandLoader } from "@/components/BrandLoader"
import { ProcessingTile } from "@/components/ProcessingTile"
import { DeleteProjectDialog, RenameProjectDialog } from "@/components/project/project-dialogs"
import { Checkbox } from "@/components/ui/checkbox-clean"
import { Badge } from "@/components/ui/badge-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"
import { Card, CardHeader } from "@/components/ui/card-clean"
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
  /** Bulk-selection state (page-owned). Selected cards keep the accent seat;
   * the circle itself hides on live-run projects (delete is refused mid-run,
   * same law as the ⋯ menu). */
  selected?: boolean
  onToggleSelect?: () => void
}

export function ProjectCard({ project, onChanged, selected, onToggleSelect }: ProjectCardProps) {
  const { t, i18n } = useTranslation()
  // Fall back to the placeholder icon until the video decodes; if it never
  // does (404, corrupt file), stay on the fallback rather than show a blank box.
  const [videoReady, setVideoReady] = useState(false)
  const [videoFailed, setVideoFailed] = useState(false)

  const menuTrigger = useRef<HTMLButtonElement>(null)
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  const thumbnailSrc = project.thumbnail_url
    ? project.thumbnail_url.startsWith("/")
      ? API_URL + project.thumbnail_url
      : project.thumbnail_url
    : null
  const showVideo = thumbnailSrc && !videoFailed

  // Bottom line: one slot, two facts — the stage label (while a run is live)
  // and the relative time. The list is sorted by time, so the time must always
  // be readable; a bare status without its timestamp hides the sort's readout.
  const active = project.status === "processing" || project.status === "uploading"
  // Only a live run gets the mist tile + stage label. Draft carries no status
  // readout (auto 档默认下它不再意味着 "awaiting confirmation" — ADR-117)：
  // 草稿卡渲染同 settled 卡，底行只剩时间。
  const live = active
  const stageLabel = active ? t(`projects.status.${project.status}`) : null
  const when = project.updated_at ?? project.created_at
  const timeLabel = when ? formatRelativeTime(when, i18n.language) : null
  const bottomLine = [stageLabel, timeLabel].filter(Boolean).join(" · ")

  return (
    <>
      <div className="group relative">
        {!active && onToggleSelect && (
          <div className="absolute left-4 top-4 z-10 opacity-100 md:opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 has-[:checked]:opacity-100">
            <Checkbox
              aria-label={t("projects.selection.toggle")}
              checked={!!selected}
              onChange={onToggleSelect}
            />
          </div>
        )}
        <Card interactive selected={selected}>
          <div
            className={`relative flex aspect-video items-center justify-center overflow-hidden rounded-lg ${
              selected
                ? "outline-2 outline-foreground/60"
                : "group-hover:outline-1 group-hover:outline-foreground/30"
            } ${
              // Neutral base for the live mist — bg-primary/10 would leak hue
              // through it; the tinted base is only for the settled thumbnail.
              live ? "bg-muted" : "bg-primary/10"
            }`}
          >
            {live ? (
              // Live run — the layered processing tile is the life signal
              // (matte base, light shaft, mist, grain, halo), so the
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
                    <Badge tone="neutral" className="rounded-md tabular-nums">
                      {formatDuration(project.thumbnail_duration)}
                    </Badge>
                  </div>
                )}
              </>
            )}
          </div>
          <CardHeader
            title={
              <Link to="/projects/$id" params={{ id: project.id }}>
                {project.title}
              </Link>
            }
            description={bottomLine}
            action={
              <DropdownMenu
                open={menuOpen}
                onOpenChange={setMenuOpen}
                align="end"
                trigger={({ triggerProps }) => (
                  <IconButton
                    ref={menuTrigger}
                    {...triggerProps}
                    label={t("projects.menuMore")}
                    icon={<MoreHorizontal />}
                  />
                )}
                items={[
                  {
                    label: t("projects.rename"),
                    icon: <Pencil />,
                    onSelect: () => {
                      menuTrigger.current?.focus()
                      setRenameOpen(true)
                    },
                  },
                  ...(active
                    ? []
                    : [
                        {
                          label: t("common.delete"),
                          danger: true,
                          icon: <Trash2 />,
                          onSelect: () => {
                            menuTrigger.current?.focus()
                            setDeleteOpen(true)
                          },
                        },
                      ]),
                ]}
              />
            }
          />
        </Card>
      </div>

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
