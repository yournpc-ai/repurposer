import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { ProjectCard } from "@/components/project/ProjectCard"

interface Project {
  id: string
  title: string
  status: string
  updated_at?: string | null
}

const DEMO_PROJECT_ID = "11111111-1111-1111-1111-111111111111"

interface RecentProjectsProps {
  refreshKey?: number
}

export function RecentProjects({ refreshKey }: RecentProjectsProps) {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [demoProject, setDemoProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const fetchProjects = async () => {
      try {
        const res = await apiFetch("/api/v1/projects")
        if (!res.ok) throw new Error("Failed to load projects")
        const all = (await res.json()) as Project[]
        if (cancelled) return

        const demo = all.find((p) => p.id === DEMO_PROJECT_ID)
        const real = all
          .filter((p) => p.id !== DEMO_PROJECT_ID)
          .sort(
            (a, b) =>
              new Date(b.updated_at || b.id).getTime() -
              new Date(a.updated_at || a.id).getTime()
          )
          .slice(0, 3)

        setProjects(real)
        setDemoProject(demo || null)
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

  if (projects.length === 0 && !demoProject) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        {t("home.noProjects")}
      </p>
    )
  }

  return (
    <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {projects.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}
      {demoProject && (
        <ProjectCard key={demoProject.id} project={demoProject} isDemo />
      )}
    </div>
  )
}
