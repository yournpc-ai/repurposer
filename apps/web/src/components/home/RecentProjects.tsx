import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { ProjectCard } from "@/components/project/ProjectCard"

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

interface RecentProjectsProps {
  refreshKey?: number
  onCountChange?: (count: number) => void
}

export function RecentProjects({ refreshKey, onCountChange }: RecentProjectsProps) {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const fetchProjects = async () => {
      try {
        const res = await apiFetch("/api/v1/projects")
        if (!res.ok) throw new Error("Failed to load projects")
        const all = (await res.json()) as Project[]
        if (cancelled) return

        const sorted = all.sort(
          (a, b) =>
            new Date(b.updated_at || b.id).getTime() -
            new Date(a.updated_at || a.id).getTime()
        )

        setProjects(sorted)
        onCountChange?.(all.length)
      } catch {
        // Leave lists empty if the API isn't ready yet; user can refresh.
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    fetchProjects()
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  if (loading) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        {t("common.loading")}
      </p>
    )
  }

  if (projects.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        {t("home.noProjects")}
      </p>
    )
  }

  return (
    <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {projects.map((project) => (
        <ProjectCard key={project.id} project={project} isDemo={project.is_demo} />
      ))}
    </div>
  )
}
