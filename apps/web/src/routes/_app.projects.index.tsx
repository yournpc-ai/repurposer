import { createFileRoute, Link } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { ArrowUpDown, FolderKanban, Search, Trash2, X } from "lucide-react"

import { apiFetch } from "@/lib/api"
import { Button } from "@/components/ui/button-clean"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"
import { EmptyState } from "@/components/ui/empty-state-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Loading, Skeleton } from "@/components/ui/skeleton-clean"
import { ProjectCard } from "@/components/project/ProjectCard"
import { DeleteProjectsDialog } from "@/components/project/project-dialogs"

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

type SortField = "updated" | "created"
type SortDir = "desc" | "asc"

export const Route = createFileRoute("/_app/projects/")({
  component: ProjectsPage,
})

function ProjectsPage() {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [query, setQuery] = useState("")
  const [sortField, setSortField] = useState<SortField>("updated")
  const [sortDir, setSortDir] = useState<SortDir>("desc")
  const [failed, setFailed] = useState(false)
  const [loading, setLoading] = useState(true)
  // Bulk selection (Flora 式): page-owned id set; the circle on each card
  // toggles, the bottom floating bar carries the only honest bulk action
  // (delete) + the clear exit. Selection survives search/sort — ids, not rows.
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set())
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])
  const clearSelection = useCallback(() => setSelectedIds(new Set()), [])

  // Lifted so cards can refetch after a rename/delete (onChanged).
  const fetchProjects = useCallback(async () => {
    setFailed(false)
    try {
      const res = await apiFetch("/api/v1/projects", { toast: false })
      if (!res.ok) throw new Error("Failed to load projects")
      setProjects((await res.json()) as Project[])
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = q ? projects.filter((p) => p.title.toLowerCase().includes(q)) : [...projects]
    // "Last modified" falls back to creation when a project was never
    // touched after birth (and vice versa); id keeps a stable order for
    // rows with no timestamps at all.
    const stamp = (p: Project) =>
      new Date(
        (sortField === "updated" ? (p.updated_at ?? p.created_at) : (p.created_at ?? p.updated_at)) || 0,
      ).getTime()
    return list.sort(
      (a, b) =>
        (sortDir === "desc" ? stamp(b) - stamp(a) : stamp(a) - stamp(b)) || a.id.localeCompare(b.id),
    )
  }, [projects, query, sortField, sortDir])

  return (
    <div className="flex flex-1 flex-col p-6 md:p-8">
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col">
        <div className="mb-4 mt-2 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{t("projects.title")}</h1>
          <div className="flex items-center gap-1">
            <TextField
              type="search"
              prefix={<Search size={16} />}
              className="w-40 sm:w-60"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label={t("projects.search")}
              placeholder={t("projects.searchPlaceholder")}
            />
            <DropdownMenu
              align="end"
              title={t("projects.sort.label")}
              trigger={({ triggerProps }) => (
                <IconButton {...triggerProps} label={t("projects.sort.label")} icon={<ArrowUpDown />} />
              )}
              items={[
                {
                  label: t("projects.sort.byUpdated"),
                  checked: sortField === "updated",
                  onSelect: () => setSortField("updated"),
                },
                {
                  label: t("projects.sort.byCreated"),
                  checked: sortField === "created",
                  onSelect: () => setSortField("created"),
                },
                {
                  label: t("projects.sort.desc"),
                  divider: true,
                  checked: sortDir === "desc",
                  onSelect: () => setSortDir("desc"),
                },
                {
                  label: t("projects.sort.asc"),
                  checked: sortDir === "asc",
                  onSelect: () => setSortDir("asc"),
                },
              ]}
            />
          </div>
        </div>

        {loading ? (
          <Loading label={t("common.loading")} className="ui-as-folders">
            {[0, 1, 2, 3].map((slot) => (
              <Skeleton key={slot} height={144} />
            ))}
          </Loading>
        ) : failed ? (
          <EmptyState
            bare
            title={t("common.requestFailed")}
            action={
              <Button variant="secondary" onClick={fetchProjects}>
                {t("credits.retry")}
              </Button>
            }
          />
        ) : visible.length === 0 && query.trim() ? (
          // A search that finds nothing is not the empty page: quiet line,
          // no CTA (the CTA belongs to the true zero state only).
          <p className="py-16 text-center text-sm text-muted-foreground">
            {t("projects.noSearchResults")}
          </p>
        ) : visible.length === 0 ? (
          <EmptyState
            bare
            tall
            icon={<FolderKanban />}
            title={t("projects.emptyTitle")}
            text={t("projects.emptyDesc")}
            action={
              <Link to="/home" className="underline">
                {t("projects.new")}
              </Link>
            }
          />
        ) : (
          <div className="ui-as-folders">
            {visible.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onChanged={fetchProjects}
                selected={selectedIds.has(project.id)}
                onToggleSelect={() => toggleSelect(project.id)}
              />
            ))}
          </div>
        )}

        {selectedIds.size > 0 ? (
          // 多选悬浮条（Flora 式）：视口底中浮层（overlay-surface 冰霜律），
          // 内容 = 计数 + 唯一真实批量动作（删除）+ × 清选。视口锚定而非
          // 内容锚定——选中态期间恒可见，不随长网格滚走。
          <div className="pointer-events-none fixed inset-x-0 bottom-6 z-40 flex justify-center">
            <div className="overlay-surface pointer-events-auto flex items-center gap-2 rounded-xl px-3 py-2">
              <span className="pl-1 text-sm">
                {t("projects.selection.count", { count: selectedIds.size })}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                onClick={() => setBulkDeleteOpen(true)}
              >
                <Trash2 className="size-4" />
                {t("projects.selection.delete")}
              </Button>
              <IconButton label={t("projects.selection.clear")} icon={<X />} onClick={clearSelection} />
            </div>
          </div>
        ) : null}

        <DeleteProjectsDialog
          projectIds={[...selectedIds]}
          open={bulkDeleteOpen}
          onOpenChange={setBulkDeleteOpen}
          onDeleted={() => {
            clearSelection()
            fetchProjects()
          }}
        />
      </div>
    </div>
  )
}
