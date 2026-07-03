import { Link } from "@tanstack/react-router"
import { FolderKanban } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"

interface Project {
  id: string
  title: string
  status: string
  updated_at?: string | null
}

interface ProjectCardProps {
  project: Project
  isDemo?: boolean
}

export function ProjectCard({ project, isDemo }: ProjectCardProps) {
  const { t } = useTranslation()

  return (
    <Link
      to="/projects/$id"
      params={{ id: project.id }}
      className="group flex flex-col gap-3 rounded-xl bg-card/50 p-3 ring-1 ring-border transition-colors hover:bg-accent"
    >
      <div className="relative flex aspect-video items-center justify-center rounded-lg bg-primary/10">
        <FolderKanban className="h-7 w-7 text-primary" />
        {isDemo && (
          <Badge
            variant="secondary"
            className="absolute left-2 top-2 text-[10px]"
          >
            {t("brandTemplate.demo")}
          </Badge>
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
