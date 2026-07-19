import { Link } from "@tanstack/react-router"
import { FolderKanban } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { projectRouteParam } from "@/lib/constants"
import { formatDuration } from "@/lib/utils"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

interface Project {
  id: string
  title: string
  status: string
  updated_at?: string | null
  thumbnail_url?: string | null
  thumbnail_duration?: number | null
  thumbnail_aspect?: string | null
  is_demo?: boolean
}

interface ProjectCardProps {
  project: Project
  isDemo?: boolean
}

export function ProjectCard({ project, isDemo }: ProjectCardProps) {
  const { t } = useTranslation()
  // Fall back to the placeholder icon until the video decodes; if it never
  // does (404, corrupt file), stay on the fallback rather than show a blank box.
  const [videoReady, setVideoReady] = useState(false)
  const [videoFailed, setVideoFailed] = useState(false)

  const thumbnailSrc = project.thumbnail_url
    ? project.thumbnail_url.startsWith("/")
      ? API_URL + project.thumbnail_url
      : project.thumbnail_url
    : null
  const showVideo = thumbnailSrc && !videoFailed

  return (
    <Link
      to="/projects/$id"
      params={{ id: projectRouteParam(project) }}
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
        {isDemo && (
          <Badge
            variant="secondary"
            className="absolute left-2 top-2 text-[10px]"
          >
            {t("brandTemplate.demo")}
          </Badge>
        )}
        {showVideo && videoReady && project.thumbnail_duration != null && (
          <div className="absolute bottom-1.5 right-1.5 flex items-center gap-1">
            <span className="rounded bg-black/75 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-white">
              {formatDuration(project.thumbnail_duration)}
            </span>
            {project.thumbnail_aspect ? (
              <span className="rounded bg-black/75 px-1.5 py-0.5 text-[10px] text-white/80">
                {project.thumbnail_aspect}
              </span>
            ) : null}
          </div>
        )}
      </div>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{project.title}</p>
        <p className="mt-0.5 text-xs capitalize text-muted-foreground">
          {project.status}
        </p>
      </div>
    </Link>
  )
}
