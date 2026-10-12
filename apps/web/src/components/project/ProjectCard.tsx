import { Link } from "@tanstack/react-router"
import { Check, FolderKanban, MoreHorizontal, Pencil, Trash2 } from "lucide-react"
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

  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

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
        {/* Flat at rest (Flora 式): the thumbnail's own fill is the only
            separation from the page — no card shell, no hairline (填充优先,
            §4)。hover 语言 = 媒体区 ring-1·/30 交互环 + 浮动钮（非 bg 座——
            accent 在 6px padding 缝里读作糊框；环直接抱住媒体区，空井/视频
            通吃）；选中 = 常驻 ring-2·/60（宽度+深度两档差，与实心勾选圈
            同族），盖住 hover 档。 */}
        <div className="rounded-xl p-1.5">
          <div
            className={`relative flex aspect-video items-center justify-center overflow-hidden rounded-lg ${
              selected
                ? "ring-2 ring-foreground/60"
                : "group-hover:ring-1 group-hover:ring-foreground/30"
            } ${
              // Neutral base for the live mist — bg-primary/10 would leak hue
              // through it; the tinted base is only for the settled thumbnail.
              live ? "bg-muted" : "bg-primary/10"
            }`}
          >
            {!active && onToggleSelect ? (
              // 多选圈（Flora 式）：rest 隐身，hover / 键盘触及 / 已选显形；
              // 选中 = bg-foreground 实底 + Check（gallery 筛选 pill 的
              // active 深底同 token）。点它不导航（⋯ 同款拦截）。
              <button
                type="button"
                aria-label={t("projects.selection.toggle")}
                aria-pressed={selected}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  onToggleSelect()
                }}
                className={`absolute left-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-full transition-opacity ${
                  selected
                    ? "bg-foreground text-background opacity-100"
                    : "bg-background text-transparent opacity-0 ring-1 ring-foreground/20 group-has-[:focus-visible]:opacity-100 group-hover:opacity-100"
                }`}
              >
                <Check className="h-3.5 w-3.5" />
              </button>
            ) : null}
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
            {/* "···" menu — rest 态隐身（扁平律的一部分），hover / 键盘
                触及 / 菜单打开时显形（opacity 互换非 display——保键盘可达
                与槽位几何，§7 同律；键盘触及 = has-[:focus-visible]，鼠标
                点击的粘滞 focus 不算——那是 :focus-visible 的存在意义）。
                wrapper 的 preventDefault + stopPropagation 挡住外层 <a> 的导航。 */}
            <div
              className={`shrink-0 transition-opacity group-has-[:focus-visible]:opacity-100 group-hover:opacity-100 ${
                menuOpen ? "opacity-100" : "opacity-0"
              }`}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
              }}
            >
              <DropdownMenu onOpenChange={setMenuOpen}>
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
