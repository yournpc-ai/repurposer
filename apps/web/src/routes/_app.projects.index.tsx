import { createFileRoute, Link } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { FolderKanban, Search } from "lucide-react"

import { apiFetch } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Input } from "@/components/ui/input"
import { ProjectCard } from "@/components/project/ProjectCard"

interface Project {
  id: string
  title: string
  status: string
  updated_at?: string | null
  thumbnail_url?: string | null
  thumbnail_duration?: number | null
  thumbnail_aspect?: string | null
}

export const Route = createFileRoute("/_app/projects/")({
  component: ProjectsPage,
})

function ProjectsPage() {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(true)

  // Lifted so cards can refetch after a rename/delete (onChanged).
  const fetchProjects = useCallback(async () => {
    try {
      const res = await apiFetch("/api/v1/projects", { toast: false })
      if (!res.ok) throw new Error("Failed to load projects")
      const all = (await res.json()) as Project[]
      const sorted = all.sort(
        (a, b) =>
          new Date(b.updated_at || b.id).getTime() -
          new Date(a.updated_at || a.id).getTime()
      )
      setProjects(sorted)
    } catch {
      // Leave the list empty if the API isn't ready yet; user can refresh.
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return projects
    return projects.filter((p) => p.title.toLowerCase().includes(q))
  }, [projects, query])

  return (
    <div className="flex flex-1 flex-col p-6 md:p-8">
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">
            {t("projects.title")}
          </h1>
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("projects.searchPlaceholder")}
              className="pl-9"
            />
          </div>
        </div>

        {loading ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {t("common.loading")}
          </p>
        ) : filtered.length === 0 && query.trim() ? (
          // A search that finds nothing is not the empty page: quiet line,
          // no CTA (the CTA belongs to the true zero state only).
          <p className="py-16 text-center text-sm text-muted-foreground">
            {t("projects.noSearchResults")}
          </p>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={FolderKanban}
            title={t("projects.emptyTitle")}
            description={t("projects.emptyDesc")}
            action={
              <Button render={<Link to="/home" />}>{t("projects.new")}</Button>
            }
          />
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {filtered.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onChanged={fetchProjects}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

