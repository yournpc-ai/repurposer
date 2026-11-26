import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ArrowUpDown, Folder, LayoutGrid, List, Plus, Search, Trash2, X } from "@/components/ui/icons"

import { apiFetch } from "@/lib/api"
import { Button } from "@/components/ui/button-clean"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"
import { EmptyState } from "@/components/ui/empty-state-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Loading, Skeleton } from "@/components/ui/skeleton-clean"
import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { ProjectCard, type Project } from "@/components/project/ProjectCard"
import { DeleteProjectsDialog } from "@/components/project/project-dialogs"

type ProjectFilter = "all" | "draft" | "active"
type ProjectView = "grid" | "list"

type SortField = "updated" | "created"
type SortDir = "desc" | "asc"

export const Route = createFileRoute("/_app/projects/")({
  component: ProjectsPage,
})

function ProjectsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<ProjectFilter>("all")
  const [view, setView] = useState<ProjectView>("grid")
  const request = useRef<AbortController | null>(null)
  useEffect(() => {
    try { if (localStorage.getItem("projects-view") === "list") setView("list") } catch { /* Storage may be unavailable. */ }
  }, [])
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
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setFailed(false)
    try {
      const items: Project[] = []
      const pageSize = 100
      for (let offset = 0; ; offset += pageSize) {
        const res = await apiFetch(`/api/v1/projects?skip=${offset}&limit=${pageSize}&include_thumbnail=false`, { signal: controller.signal, toast: false })
        if (!res.ok) throw new Error("Failed to load projects")
        const page: Project[] = await res.json()
        items.push(...page)
        if (page.length < pageSize) break
      }
      if (controller.signal.aborted) return
      setProjects(items)
      const selectable = new Set(items.filter(p => p.status !== "uploading" && p.status !== "processing").map(p => p.id))
      setSelectedIds(previous => new Set([...previous].filter(id => selectable.has(id))))
    } catch {
      if (!controller.signal.aborted) setFailed(true)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchProjects()
    return () => request.current?.abort()
  }, [fetchProjects])

  function createProject() {
    void navigate({ to: "/home" })
  }

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = projects.filter(p => {
      if (filter === "draft" && p.status !== "draft") return false
      if (filter === "active" && p.status !== "uploading" && p.status !== "processing") return false
      return p.title.toLowerCase().includes(q)
    })
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
  }, [projects, query, filter, sortField, sortDir])

  return (
    <div className="projects-page">
      <header>
        <h1 className="text-2xl leading-8 font-medium">{t("projects.title")}</h1>
        <p className="mt-1 text-[13px] leading-5 text-muted-foreground">{t("projects.subtitle")}</p>
      </header>
      <section aria-labelledby="project-library-title">
        <h2 id="project-library-title" className="project-section-title">
          {t("projects.library")}
          {!failed && !loading && <span className="tabular-nums">{visible.length}</span>}
        </h2>
        <div className="project-toolbar">
          <SegmentedControl<ProjectFilter>
            aria-label={t("projects.filterLabel")}
            value={filter}
            onChange={setFilter}
            variant="buttons"
            options={[
              { value: "all", label: t("projects.all") },
              { value: "draft", label: t("projects.drafts") },
              { value: "active", label: t("projects.inProgress") },
            ]}
          />
          <div className="project-tools">
            <DropdownMenu
              align="end"
              title={t("projects.sort.label")}
              trigger={({ triggerProps }) => (
                <IconButton variant="secondary" {...triggerProps} label={t("projects.sort.label")} icon={<ArrowUpDown />} />
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
            <SegmentedControl<ProjectView>
              aria-label={t("projects.view")}
              value={view}
              variant="tray"
              onChange={next => {
                setView(next)
                try { localStorage.setItem("projects-view", next) } catch { /* Keep the session choice. */ }
              }}
              options={[
                { value: "grid", ariaLabel: t("projects.grid"), icon: <LayoutGrid size={15} /> },
                { value: "list", ariaLabel: t("projects.list"), icon: <List size={15} /> },
              ]}
            />
            <TextField
              size="sm"
              type="search"
              prefix={<Search size={16} />}
              className="project-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label={t("projects.search")}
              placeholder={t("projects.searchPlaceholder")}
            />
            <Button size="sm" icon={<Plus size={15} />} onClick={createProject}>
              {t("projects.new")}
            </Button>
          </div>
        </div>

        <div className="mt-4">
          {loading ? (
            <Loading label={t("common.loading")} className="ui-as-folders" data-view={view}>
              {[96, 72, 112, 84].map(width => (
                <div className="project-skeleton" key={width} aria-hidden="true">
                  <Skeleton width={26} height={22} radius={6} />
                  <span className="grid gap-2">
                    <Skeleton width={width} height={10} />
                    <Skeleton width={64} height={8} />
                  </span>
                </div>
              ))}
            </Loading>
          ) : failed ? (
            <EmptyState
              title={t("common.requestFailed")}
              action={
                <Button variant="secondary" onClick={() => { setLoading(true); void fetchProjects() }}>
                  {t("credits.retry")}
                </Button>
              }
            />
          ) : projects.length === 0 ? (
            <EmptyState
              icon={<Folder />}
              title={t("projects.emptyTitle")}
              text={<span className="block max-w-64">{t("projects.emptyDesc")}</span>}
              action={
                <Button size="sm" variant="secondary" icon={<Plus size={15} />} onClick={createProject}>
                  {t("projects.new")}
                </Button>
              }
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<Search />}
              title={t(query.trim() ? "projects.noSearchResults" : "projects.noFilterResults")}
              action={
                <Button size="sm" variant="secondary" onClick={() => { setQuery(""); setFilter("all") }}>
                  {t("projects.resetFilters")}
                </Button>
              }
            />
          ) : (
            <div className="ui-as-folders" data-view={view}>
              {visible.map((project) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  onChanged={fetchProjects}
                  selected={selectedIds.has(project.id)}
                  selectionDisabled={selectedIds.size >= 100 && !selectedIds.has(project.id)}
                  onToggleSelect={() => toggleSelect(project.id)}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {selectedIds.size > 0 ? (
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
          void fetchProjects()
        }}
      />
    </div>
  )
}
