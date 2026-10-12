import { createFileRoute, Link } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ArrowUpDown, FolderKanban, Search, Trash2, X } from "lucide-react"

import { apiFetch } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { EmptyState } from "@/components/ui/empty-state"
import { Input } from "@/components/ui/input"
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

/** Collapsed = a quiet circle button; hover (pointer preview) or click grows
 *  the search field leftward. It stays open while focused or holding a query,
 *  folds back on blur-when-empty; Esc clears and folds. Collapsing with an
 *  active query is impossible by construction — the fold requires empty. */
function ExpandingSearch({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  label: string
}) {
  const [open, setOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const expanded = open || value.length > 0

  return (
    <div
      className={cn(
        "overflow-hidden transition-[width] duration-200 ease-out",
        expanded ? "w-52 sm:w-64" : "w-8"
      )}
      onMouseLeave={() => {
        if (!focused && value.length === 0) setOpen(false)
      }}
    >
      {expanded ? (
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => {
              setFocused(false)
              if (value.length === 0) setOpen(false)
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                onChange("")
                setOpen(false)
                inputRef.current?.blur()
              }
            }}
            placeholder={placeholder}
            aria-label={label}
            className="h-8 pl-8"
          />
        </div>
      ) : (
        <Button
          variant="ghost"
          size="icon-lg"
          aria-label={label}
          onMouseEnter={() => setOpen(true)}
          onClick={() => {
            setOpen(true)
            // Focus after the input swaps in.
            requestAnimationFrame(() => inputRef.current?.focus())
          }}
        >
          <Search className="size-4" />
        </Button>
      )}
    </div>
  )
}

function ProjectsPage() {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<Project[]>([])
  const [query, setQuery] = useState("")
  const [sortField, setSortField] = useState<SortField>("updated")
  const [sortDir, setSortDir] = useState<SortDir>("desc")
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
    try {
      const res = await apiFetch("/api/v1/projects", { toast: false })
      if (!res.ok) throw new Error("Failed to load projects")
      setProjects((await res.json()) as Project[])
    } catch {
      // Leave the list empty if the API isn't ready yet; user can refresh.
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = q
      ? projects.filter((p) => p.title.toLowerCase().includes(q))
      : [...projects]
    // "Last modified" falls back to creation when a project was never
    // touched after birth (and vice versa); id keeps a stable order for
    // rows with no timestamps at all.
    const stamp = (p: Project) =>
      new Date(
        (sortField === "updated"
          ? (p.updated_at ?? p.created_at)
          : (p.created_at ?? p.updated_at)) || p.id
      ).getTime()
    return list.sort((a, b) =>
      sortDir === "desc" ? stamp(b) - stamp(a) : stamp(a) - stamp(b)
    )
  }, [projects, query, sortField, sortDir])

  return (
    <div className="flex flex-1 flex-col p-6 md:p-8">
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col">
        {/* mt-10 drops the whole header row below the floating bell chip's
            band (top-4 + h-10 → the bell owns 16–56px from the viewport top,
            ADR-046 reserved corner): the two horizontal bands must not
            interleave. Vertical separation makes horizontal clearance
            unnecessary, so the controls stay flush with the grid's right
            edge. */}
        <div className="mb-8 mt-10 flex items-center justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight">
            {t("projects.title")}
          </h1>
          <div className="flex items-center gap-1">
            <ExpandingSearch
              value={query}
              onChange={setQuery}
              placeholder={t("projects.searchPlaceholder")}
              label={t("projects.search")}
            />
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon-lg"
                    aria-label={t("projects.sort.label")}
                  >
                    <ArrowUpDown className="size-4" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>
                    {t("projects.sort.byField")}
                  </DropdownMenuLabel>
                  <DropdownMenuRadioGroup
                    value={sortField}
                    onValueChange={(v) => setSortField(v as SortField)}
                  >
                    <DropdownMenuRadioItem value="updated">
                      {t("projects.sort.byUpdated")}
                    </DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="created">
                      {t("projects.sort.byCreated")}
                    </DropdownMenuRadioItem>
                  </DropdownMenuRadioGroup>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuGroup>
                  <DropdownMenuLabel>
                    {t("projects.sort.order")}
                  </DropdownMenuLabel>
                  <DropdownMenuRadioGroup
                    value={sortDir}
                    onValueChange={(v) => setSortDir(v as SortDir)}
                  >
                    <DropdownMenuRadioItem value="desc">
                      {t("projects.sort.desc")}
                    </DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="asc">
                      {t("projects.sort.asc")}
                    </DropdownMenuRadioItem>
                  </DropdownMenuRadioGroup>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {loading ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {t("common.loading")}
          </p>
        ) : visible.length === 0 && query.trim() ? (
          // A search that finds nothing is not the empty page: quiet line,
          // no CTA (the CTA belongs to the true zero state only).
          <p className="py-16 text-center text-sm text-muted-foreground">
            {t("projects.noSearchResults")}
          </p>
        ) : visible.length === 0 ? (
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
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("projects.selection.clear")}
                onClick={clearSelection}
              >
                <X className="size-4" />
              </Button>
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
