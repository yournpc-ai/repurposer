import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowUpDown,
  ArrowUpRight,
  Download,
  FileText,
  Film,
  Folder,
  FolderOpen,
  Image as ImageIcon,
  LayoutGrid,
  Library,
  List,
  MessageSquarePlus,
  Mic,
  Music2,
  Pause,
  Play,
  Search,
  Sparkles,
  Video as VideoIcon,
  X,
} from "@/components/ui/icons"

import { Badge } from "@/components/ui/badge-clean"
import { Button } from "@/components/ui/button-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"
import { EmptyState } from "@/components/ui/empty-state-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { Select } from "@/components/ui/select-clean"
import { Loading, Skeleton } from "@/components/ui/skeleton-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { Tooltip } from "@/components/ui/tooltip-clean"
import { apiFetch } from "@/lib/api"
import type { ChatMention } from "@/lib/mentions"
import { formatFileSize } from "@/lib/stagedFiles"
import { cn, formatDuration, formatRelativeTime } from "@/lib/utils"

interface LibraryProjectFolder {
  id: string
  title: string
  upload_count: number
  export_count: number
  total_count: number
  latest_at: string | null
}

interface LibraryUploadItem {
  id: string
  title: string
  type: string
  project_id: string | null
  project_title: string | null
  stream_url: string | null
  duration_seconds: number | null
  size_bytes: number | null
  width: number | null
  height: number | null
  processing_status: string
  created_at: string | null
}

interface LibraryExportItem {
  id: string
  title: string
  project_id: string
  project_title: string | null
  composition_id: string | null
  composition_version_id: string | null
  composition_version_number: number | null
  video_url: string | null
  poster_url: string | null
  duration_seconds: number | null
  width: number | null
  height: number | null
  created_at: string | null
}

interface LibraryAudioItem {
  id: string
  kind: "music" | "voice"
  title: string
  subtitle: string | null
  stream_url: string | null
  duration_seconds: number | null
  size_bytes: number | null
  tags: string[]
  use_count: number
  created_at: string | null
}

interface LibrarySkillItem {
  skill_id: string
  skill_version_id: string
  name: string
  description: string
  version_number: number
  act_count: number | null
  slot_count: number | null
  duration_s: number | null
  style_preset: string | null
  created_at: string | null
}

interface AssetLibraryResponse {
  projects: LibraryProjectFolder[]
  uploads: LibraryUploadItem[]
  exports: LibraryExportItem[]
  audio: LibraryAudioItem[]
  skills: LibrarySkillItem[]
}

type AssetTab = "all" | "uploads" | "exports" | "audio" | "skills"
type UploadKindFilter = "" | "video" | "image" | "audio" | "document"
type AssetView = "grid" | "list"
type SortMode = "newest" | "oldest" | "name_asc" | "name_desc"

type UnifiedAssetEntry =
  | {
      key: string
      bucket: "upload"
      id: string
      title: string
      mediaKind: "video" | "image" | "audio" | "document"
      rawType: string
      projectId: string | null
      projectTitle: string | null
      previewUrl: string | null
      posterUrl: string | null
      durationSeconds: number | null
      sizeBytes: number | null
      createdAt: string | null
      upload: LibraryUploadItem
    }
  | {
      key: string
      bucket: "export"
      id: string
      title: string
      mediaKind: "video"
      projectId: string
      projectTitle: string | null
      previewUrl: string | null
      posterUrl: string | null
      durationSeconds: number | null
      sizeBytes: null
      versionNumber: number | null
      createdAt: string | null
      exportItem: LibraryExportItem
    }
  | {
      key: string
      bucket: "audio"
      id: string
      title: string
      mediaKind: "audio"
      audioKind: "music" | "voice"
      subtitle: string | null
      projectId: null
      projectTitle: null
      previewUrl: string | null
      posterUrl: null
      durationSeconds: number | null
      sizeBytes: number | null
      tags: string[]
      createdAt: string | null
      audioItem: LibraryAudioItem
    }
  | {
      key: string
      bucket: "skill"
      id: string
      title: string
      mediaKind: "document"
      description: string
      projectId: null
      projectTitle: null
      previewUrl: null
      posterUrl: null
      durationSeconds: number | null
      sizeBytes: null
      createdAt: string | null
      skillItem: LibrarySkillItem
    }

export const Route = createFileRoute("/_app/assets")({
  component: AssetsPage,
})

function normalizeUploadKind(rawType: string): "video" | "image" | "audio" | "document" {
  const lower = rawType.toLowerCase()
  if (lower === "video") return "video"
  if (lower === "image") return "image"
  if (lower === "audio" || lower === "voice_sample") return "audio"
  return "document"
}

function triggerBrowserDownload(url: string, filename?: string) {
  const anchor = document.createElement("a")
  anchor.href = url
  if (filename) anchor.download = filename
  anchor.rel = "noopener noreferrer"
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

export function AssetsPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [data, setData] = useState<AssetLibraryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [tab, setTab] = useState<AssetTab>("all")
  const [kindFilter, setKindFilter] = useState<UploadKindFilter>("")
  const [projectFilter, setProjectFilter] = useState<string | null>(null)
  const [sortMode, setSortMode] = useState<SortMode>("newest")
  const [view, setView] = useState<AssetView>("grid")
  const [query, setQuery] = useState("")
  const [mounted, setMounted] = useState(false)
  const [previewEntry, setPreviewEntry] = useState<UnifiedAssetEntry | null>(null)
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null)
  const [playingAudioKey, setPlayingAudioKey] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const requestRef = useRef<AbortController | null>(null)

  useEffect(() => {
    setMounted(true)
    try {
      const saved = localStorage.getItem("assets-view")
      if (saved === "grid" || saved === "list") setView(saved)
    } catch {
      // Storage may be unavailable
    }
  }, [])

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
    }
  }, [])

  const fetchLibrary = useCallback(async () => {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    setFailed(false)
    try {
      const res = await apiFetch("/api/v1/assets/library", {
        signal: controller.signal,
        toast: false,
      })
      if (!res.ok) throw new Error("Failed to load assets")
      const json = (await res.json()) as AssetLibraryResponse
      if (controller.signal.aborted) return
      setData(json)
    } catch {
      if (!controller.signal.aborted) setFailed(true)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchLibrary()
    return () => requestRef.current?.abort()
  }, [fetchLibrary])

  const allEntries = useMemo<UnifiedAssetEntry[]>(() => {
    if (!data) return []
    const list: UnifiedAssetEntry[] = []
    for (const u of data.uploads) {
      list.push({
        key: `upload:${u.id}`,
        bucket: "upload",
        id: u.id,
        title: u.title,
        mediaKind: normalizeUploadKind(u.type),
        rawType: u.type,
        projectId: u.project_id,
        projectTitle: u.project_title,
        previewUrl: u.stream_url,
        posterUrl: null,
        durationSeconds: u.duration_seconds,
        sizeBytes: u.size_bytes,
        createdAt: u.created_at,
        upload: u,
      })
    }
    for (const ex of data.exports) {
      list.push({
        key: `export:${ex.id}`,
        bucket: "export",
        id: ex.id,
        title: ex.title,
        mediaKind: "video",
        projectId: ex.project_id,
        projectTitle: ex.project_title,
        previewUrl: ex.video_url,
        posterUrl: ex.poster_url,
        durationSeconds: ex.duration_seconds,
        sizeBytes: null,
        versionNumber: ex.composition_version_number,
        createdAt: ex.created_at,
        exportItem: ex,
      })
    }
    for (const au of data.audio) {
      list.push({
        key: `audio:${au.kind}:${au.id}`,
        bucket: "audio",
        id: au.id,
        title: au.title,
        mediaKind: "audio",
        audioKind: au.kind,
        subtitle: au.subtitle,
        projectId: null,
        projectTitle: null,
        previewUrl: au.stream_url,
        posterUrl: null,
        durationSeconds: au.duration_seconds,
        sizeBytes: au.size_bytes,
        tags: au.tags,
        createdAt: au.created_at,
        audioItem: au,
      })
    }
    for (const sk of data.skills) {
      list.push({
        key: `skill:${sk.skill_version_id}`,
        bucket: "skill",
        id: sk.skill_version_id,
        title: sk.name,
        mediaKind: "document",
        description: sk.description,
        projectId: null,
        projectTitle: null,
        previewUrl: null,
        posterUrl: null,
        durationSeconds: sk.duration_s,
        sizeBytes: null,
        createdAt: sk.created_at,
        skillItem: sk,
      })
    }
    return list
  }, [data])

  const filteredEntries = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = allEntries.filter((entry) => {
      if (tab === "uploads" && entry.bucket !== "upload") return false
      if (tab === "exports" && entry.bucket !== "export") return false
      if (tab === "audio" && entry.bucket !== "audio") return false
      if (tab === "skills" && entry.bucket !== "skill") return false
      if (projectFilter && entry.projectId !== projectFilter) return false
      if ((tab === "all" || tab === "uploads") && kindFilter && entry.mediaKind !== kindFilter) {
        return false
      }
      if (!q) return true
      const haystack = [
        entry.title,
        entry.projectTitle ?? "",
        entry.bucket === "audio" ? (entry.subtitle ?? "") : "",
        entry.bucket === "audio" ? entry.tags.join(" ") : "",
        entry.bucket === "skill" ? entry.description : "",
      ]
        .join(" ")
        .toLowerCase()
      return haystack.includes(q)
    })

    const stamp = (e: UnifiedAssetEntry) =>
      e.createdAt ? new Date(e.createdAt).getTime() || 0 : 0

    return list.sort((a, b) => {
      if (sortMode === "newest") return stamp(b) - stamp(a) || a.title.localeCompare(b.title)
      if (sortMode === "oldest") return stamp(a) - stamp(b) || a.title.localeCompare(b.title)
      if (sortMode === "name_asc") return a.title.localeCompare(b.title)
      return b.title.localeCompare(a.title)
    })
  }, [allEntries, tab, projectFilter, kindFilter, query, sortMode])

  const activeProjectFolder = useMemo(
    () => (projectFilter ? data?.projects.find((p) => p.id === projectFilter) ?? null : null),
    [data, projectFilter],
  )

  const toggleAudioPlay = useCallback(
    (entry: UnifiedAssetEntry) => {
      if (!entry.previewUrl) return
      if (playingAudioKey === entry.key && audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
        setPlayingAudioKey(null)
        return
      }
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
      const el = new Audio(entry.previewUrl)
      el.onended = () => {
        setPlayingAudioKey((current) => (current === entry.key ? null : current))
      }
      el.onerror = () => {
        setPlayingAudioKey((current) => (current === entry.key ? null : current))
      }
      audioRef.current = el
      setPlayingAudioKey(entry.key)
      void el.play().catch(() => {
        setPlayingAudioKey((current) => (current === entry.key ? null : current))
      })
    },
    [playingAudioKey],
  )

  const handleDownload = useCallback(async (entry: UnifiedAssetEntry) => {
    if (entry.bucket === "skill") return
    setDownloadingKey(entry.key)
    try {
      if (entry.bucket === "upload") {
        const res = await apiFetch(`/api/v1/assets/${entry.id}/download`)
        if (!res.ok) return
        const payload = (await res.json()) as { url?: string }
        if (payload.url) triggerBrowserDownload(payload.url, entry.title)
      } else if (entry.bucket === "export") {
        const res = await apiFetch(`/api/v1/outputs/${entry.id}/playback?download=true`)
        if (!res.ok) return
        const payload = (await res.json()) as { url?: string }
        if (payload.url) triggerBrowserDownload(payload.url, `${entry.title}.mp4`)
      } else if (entry.bucket === "audio" && entry.previewUrl) {
        triggerBrowserDownload(entry.previewUrl, entry.title)
      }
    } finally {
      setDownloadingKey((current) => (current === entry.key ? null : current))
    }
  }, [])

  const handleUseInNewChat = useCallback(
    (entry: UnifiedAssetEntry) => {
      if (entry.bucket === "upload") {
        const mention: ChatMention = {
          type: "asset",
          id: entry.id,
          label: entry.title,
        }
        void navigate({
          to: "/home",
          state: { prefillMention: mention } as Record<string, unknown>,
        })
      } else if (entry.bucket === "export") {
        const mention: ChatMention = {
          type: "output",
          id: entry.id,
          label: entry.title,
        }
        void navigate({
          to: "/home",
          state: { prefillMention: mention } as Record<string, unknown>,
        })
      } else if (entry.bucket === "skill") {
        void navigate({
          to: "/home",
          state: { prefillSkillVersionId: entry.skillItem.skill_version_id } as Record<string, unknown>,
        })
      } else if (entry.bucket === "audio") {
        const instruction =
          entry.audioKind === "music"
            ? t("assetsPage.musicPrompt", { name: entry.title, id: entry.id })
            : t("assetsPage.voicePrompt", { name: entry.title, id: entry.id })
        void navigate({
          to: "/home",
          state: { prefillPrompt: instruction } as Record<string, unknown>,
        })
      }
    },
    [navigate, t],
  )

  const openProject = useCallback(
    (projectId: string) => {
      void navigate({ to: "/projects/$id", params: { id: projectId } })
    },
    [navigate],
  )

  const kindLabel = useCallback(
    (entry: UnifiedAssetEntry): string => {
      if (entry.bucket === "export") {
        return entry.versionNumber != null
          ? `${t("assetsPage.kinds.export")} · v${entry.versionNumber}`
          : t("assetsPage.kinds.export")
      }
      if (entry.bucket === "audio") {
        return entry.audioKind === "music"
          ? t("assetsPage.kinds.music")
          : t("assetsPage.kinds.voice")
      }
      if (entry.bucket === "skill") {
        return t("assetsPage.kinds.skill")
      }
      return t(`assetsPage.kinds.${entry.mediaKind}`)
    },
    [t],
  )

  const formatMeta = useCallback(
    (entry: UnifiedAssetEntry): string => {
      const parts: string[] = [kindLabel(entry)]
      if (entry.durationSeconds != null && entry.durationSeconds > 0) {
        parts.push(formatDuration(entry.durationSeconds))
      }
      if (entry.sizeBytes != null && entry.sizeBytes > 0) {
        parts.push(formatFileSize(entry.sizeBytes))
      }
      if (entry.bucket === "skill" && entry.skillItem.slot_count != null) {
        parts.push(t("assetsPage.skillSlots", { count: entry.skillItem.slot_count }))
      }
      if (mounted && entry.createdAt) {
        const rel = formatRelativeTime(entry.createdAt, i18n.language)
        if (rel) parts.push(rel)
      }
      return parts.join(" · ")
    },
    [i18n.language, kindLabel, mounted, t],
  )

  const totalCount = allEntries.length
  const showKindSelect = tab === "all" || tab === "uploads"

  return (
    <div className="projects-page">
      <header>
        <h1 className="text-2xl leading-8 font-medium">{t("assetsPage.title")}</h1>
        <p className="mt-1 text-[13px] leading-5 text-muted-foreground">
          {t("assetsPage.subtitle")}
        </p>
      </header>

      {/* Section 1: Project folders (only real projects with stored assets or exports) */}
      {loading ? (
        <section aria-labelledby="assets-folders-title">
          <h2 id="assets-folders-title" className="project-section-title">
            {t("assetsPage.projectFolders")}
          </h2>
          <Loading label={t("common.loading")} className="ui-as-folders">
            {[96, 76, 112, 84].map((width) => (
              <div className="project-skeleton" key={width} aria-hidden="true">
                <Skeleton width={22} height={22} radius={6} />
                <span className="grid gap-2">
                  <Skeleton width={width} height={10} />
                  <Skeleton width={64} height={8} />
                </span>
              </div>
            ))}
          </Loading>
        </section>
      ) : data && data.projects.length > 0 ? (
        <section aria-labelledby="assets-folders-title">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 id="assets-folders-title" className="project-section-title !mb-0">
              {t("assetsPage.projectFolders")}
              <span className="tabular-nums">{data.projects.length}</span>
            </h2>
            {projectFilter ? (
              <button
                type="button"
                onClick={() => setProjectFilter(null)}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
              >
                <X className="size-3" />
                {t("assetsPage.clearProjectFilter")}
              </button>
            ) : null}
          </div>
          <div className="ui-as-folders">
            {data.projects.map((folder) => {
              const selected = projectFilter === folder.id
              return (
                <div
                  key={folder.id}
                  className={cn(
                    "group relative flex h-14 items-center gap-3 rounded-[var(--aui-radius-lg,10px)] bg-card px-3 shadow-[var(--shadow-card)] transition-colors",
                    selected
                      ? "outline-1 outline-foreground/45 bg-accent"
                      : "hover:bg-accent/50",
                  )}
                >
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => {
                      setProjectFilter((prev) => (prev === folder.id ? null : folder.id))
                      if (tab === "audio" || tab === "skills") setTab("all")
                    }}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    <span className="grid size-8 shrink-0 place-items-center rounded-md bg-muted text-foreground/80">
                      {selected ? (
                        <FolderOpen className="size-4" aria-hidden="true" />
                      ) : (
                        <Folder className="size-4" aria-hidden="true" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        title={folder.title}
                        className="block truncate text-[13px] leading-5 font-medium text-foreground"
                      >
                        {folder.title}
                      </span>
                      <span className="block truncate text-[11px] leading-4 text-muted-foreground">
                        {t("assetsPage.folderMeta", {
                          uploads: folder.upload_count,
                          exports: folder.export_count,
                        })}
                      </span>
                    </span>
                  </button>
                  <Tooltip content={t("assetsPage.openProject")} side="top">
                    <IconButton
                      size="sm"
                      variant="ghost"
                      className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 max-md:opacity-100"
                      icon={<ArrowUpRight className="size-3.5" />}
                      label={t("assetsPage.openProject")}
                      onClick={() => openProject(folder.id)}
                    />
                  </Tooltip>
                </div>
              )
            })}
          </div>
        </section>
      ) : null}

      {/* Section 2: Media & Assets Library */}
      <section aria-labelledby="assets-library-title">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h2 id="assets-library-title" className="project-section-title !mb-0">
            {t("assetsPage.filesHeading")}
            {!loading && !failed ? (
              <span className="tabular-nums">{filteredEntries.length}</span>
            ) : null}
          </h2>
          {activeProjectFolder ? (
            <Badge tone="neutral" size="sm">
              {activeProjectFolder.title}
            </Badge>
          ) : null}
        </div>

        <div className="project-toolbar">
          <SegmentedControl<AssetTab>
            aria-label={t("assetsPage.filterTabs")}
            value={tab}
            onChange={(next) => {
              setTab(next)
              if (next !== "all" && next !== "uploads") setKindFilter("")
              if (next === "audio" || next === "skills") setProjectFilter(null)
            }}
            variant="buttons"
            options={[
              { value: "all", label: t("assetsPage.tabs.all") },
              { value: "uploads", label: t("assetsPage.tabs.uploads") },
              { value: "exports", label: t("assetsPage.tabs.exports") },
              { value: "audio", label: t("assetsPage.tabs.audio") },
              { value: "skills", label: t("assetsPage.tabs.skills") },
            ]}
          />

          <div className="project-tools">
            {showKindSelect ? (
              <Select
                size="sm"
                aria-label={t("assetsPage.typeFilter")}
                value={kindFilter}
                onChange={(val) => setKindFilter(val as UploadKindFilter)}
                options={[
                  { value: "", label: t("assetsPage.kinds.all") },
                  { value: "video", label: t("assetsPage.kinds.video") },
                  { value: "image", label: t("assetsPage.kinds.image") },
                  { value: "audio", label: t("assetsPage.kinds.audio") },
                  { value: "document", label: t("assetsPage.kinds.document") },
                ]}
              />
            ) : null}

            <DropdownMenu
              align="end"
              title={t("assetsPage.sort.label")}
              trigger={({ triggerProps }) => (
                <IconButton
                  variant="secondary"
                  {...triggerProps}
                  label={t("assetsPage.sort.label")}
                  icon={<ArrowUpDown />}
                />
              )}
              items={[
                {
                  label: t("assetsPage.sort.newest"),
                  checked: sortMode === "newest",
                  onSelect: () => setSortMode("newest"),
                },
                {
                  label: t("assetsPage.sort.oldest"),
                  checked: sortMode === "oldest",
                  onSelect: () => setSortMode("oldest"),
                },
                {
                  label: t("assetsPage.sort.nameAsc"),
                  divider: true,
                  checked: sortMode === "name_asc",
                  onSelect: () => setSortMode("name_asc"),
                },
                {
                  label: t("assetsPage.sort.nameDesc"),
                  checked: sortMode === "name_desc",
                  onSelect: () => setSortMode("name_desc"),
                },
              ]}
            />

            <SegmentedControl<AssetView>
              aria-label={t("projects.view")}
              value={view}
              variant="tray"
              onChange={(next) => {
                setView(next)
                try {
                  localStorage.setItem("assets-view", next)
                } catch {
                  // Keep session choice
                }
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
              aria-label={t("assetsPage.searchPlaceholder")}
              placeholder={t("assetsPage.searchPlaceholder")}
            />
          </div>
        </div>

        <div className="mt-4">
          {loading ? (
            <Loading
              label={t("common.loading")}
              className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            >
              {[120, 96, 136, 108].map((width) => (
                <div
                  key={width}
                  className="flex flex-col gap-2.5 rounded-[var(--aui-radius-lg,10px)] bg-card p-2.5 shadow-[var(--shadow-card)]"
                  aria-hidden="true"
                >
                  <Skeleton width="100%" height={124} radius={8} />
                  <Skeleton width={width} height={12} />
                  <Skeleton width={88} height={9} />
                </div>
              ))}
            </Loading>
          ) : failed ? (
            <EmptyState
              title={t("common.requestFailed")}
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setLoading(true)
                    void fetchLibrary()
                  }}
                >
                  {t("credits.retry")}
                </Button>
              }
            />
          ) : totalCount === 0 ? (
            <EmptyState
              icon={<Library />}
              title={t("assetsPage.emptyTitle")}
              text={<span className="block max-w-72">{t("assetsPage.emptyDesc")}</span>}
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void navigate({ to: "/home" })}
                >
                  {t("assetsPage.startCreating")}
                </Button>
              }
            />
          ) : filteredEntries.length === 0 ? (
            <EmptyState
              icon={<Search />}
              title={t("assetsPage.noResultsTitle")}
              text={t("assetsPage.noResultsDesc")}
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setQuery("")
                    setKindFilter("")
                    setProjectFilter(null)
                    setTab("all")
                  }}
                >
                  {t("projects.resetFilters")}
                </Button>
              }
            />
          ) : view === "grid" ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {filteredEntries.map((entry) => (
                <AssetGridCard
                  key={entry.key}
                  entry={entry}
                  metaLine={formatMeta(entry)}
                  isPlaying={playingAudioKey === entry.key}
                  isDownloading={downloadingKey === entry.key}
                  onPreview={() => {
                    if (entry.mediaKind === "audio") toggleAudioPlay(entry)
                    else if (entry.previewUrl) setPreviewEntry(entry)
                  }}
                  onDownload={() => void handleDownload(entry)}
                  onUseInChat={() => handleUseInNewChat(entry)}
                  onOpenProject={entry.projectId ? () => openProject(entry.projectId!) : undefined}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {filteredEntries.map((entry) => (
                <AssetListRow
                  key={entry.key}
                  entry={entry}
                  metaLine={formatMeta(entry)}
                  isPlaying={playingAudioKey === entry.key}
                  isDownloading={downloadingKey === entry.key}
                  onPreview={() => {
                    if (entry.mediaKind === "audio") toggleAudioPlay(entry)
                    else if (entry.previewUrl) setPreviewEntry(entry)
                  }}
                  onDownload={() => void handleDownload(entry)}
                  onUseInChat={() => handleUseInNewChat(entry)}
                  onOpenProject={entry.projectId ? () => openProject(entry.projectId!) : undefined}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Media Preview Dialog (video & image) */}
      <Dialog
        open={previewEntry != null}
        onOpenChange={(open) => {
          if (!open) setPreviewEntry(null)
        }}
        title={previewEntry?.title ?? ""}
        closeLabel={t("common.close")}
        width={760}
        footer={
          previewEntry ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="truncate text-xs text-muted-foreground">
                {formatMeta(previewEntry)}
                {previewEntry.projectTitle ? ` · ${previewEntry.projectTitle}` : ""}
              </span>
              <div className="flex items-center gap-2">
                {previewEntry.projectId ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<ArrowUpRight className="size-4" />}
                    onClick={() => {
                      const pid = previewEntry.projectId
                      setPreviewEntry(null)
                      if (pid) openProject(pid)
                    }}
                  >
                    {t("assetsPage.openProject")}
                  </Button>
                ) : null}
                {previewEntry.bucket !== "skill" ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={downloadingKey === previewEntry.key}
                    icon={<Download className="size-4" />}
                    onClick={() => void handleDownload(previewEntry)}
                  >
                    {t("assetsPage.download")}
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  variant="primary"
                  icon={<MessageSquarePlus className="size-4" />}
                  onClick={() => {
                    const target = previewEntry
                    setPreviewEntry(null)
                    handleUseInNewChat(target)
                  }}
                >
                  {t("assetsPage.useInNewChat")}
                </Button>
              </div>
            </div>
          ) : null
        }
      >
        {previewEntry?.previewUrl ? (
          previewEntry.mediaKind === "video" ? (
            <video
              key={previewEntry.previewUrl}
              src={previewEntry.previewUrl}
              poster={previewEntry.posterUrl ?? undefined}
              controls
              playsInline
              className="max-h-[65dvh] w-full rounded-lg bg-muted object-contain"
            />
          ) : previewEntry.mediaKind === "image" ? (
            <img
              src={previewEntry.previewUrl}
              alt={previewEntry.title}
              className="max-h-[65dvh] w-full rounded-lg bg-muted object-contain"
            />
          ) : null
        ) : null}
      </Dialog>
    </div>
  )
}

function AssetEntryIcon({
  entry,
  className = "size-5",
}: {
  entry: UnifiedAssetEntry
  className?: string
}) {
  if (entry.bucket === "export") return <Film className={className} aria-hidden="true" />
  if (entry.bucket === "skill") return <Sparkles className={className} aria-hidden="true" />
  if (entry.bucket === "audio") {
    return entry.audioKind === "voice" ? (
      <Mic className={className} aria-hidden="true" />
    ) : (
      <Music2 className={className} aria-hidden="true" />
    )
  }
  if (entry.mediaKind === "video") return <VideoIcon className={className} aria-hidden="true" />
  if (entry.mediaKind === "image") return <ImageIcon className={className} aria-hidden="true" />
  if (entry.mediaKind === "audio") return <Music2 className={className} aria-hidden="true" />
  return <FileText className={className} aria-hidden="true" />
}

function AssetGridCard({
  entry,
  metaLine,
  isPlaying,
  isDownloading,
  onPreview,
  onDownload,
  onUseInChat,
  onOpenProject,
}: {
  entry: UnifiedAssetEntry
  metaLine: string
  isPlaying: boolean
  isDownloading: boolean
  onPreview: () => void
  onDownload: () => void
  onUseInChat: () => void
  onOpenProject?: () => void
}) {
  const { t } = useTranslation()
  const canVisualPreview =
    (entry.mediaKind === "video" || entry.mediaKind === "image") && Boolean(entry.previewUrl)
  const canAudioPlay = entry.mediaKind === "audio" && Boolean(entry.previewUrl)

  return (
    <article className="group flex flex-col overflow-hidden rounded-[var(--aui-radius-lg,10px)] bg-card shadow-[var(--shadow-card)] transition-colors">
      {/* Preview Surface */}
      <div className="relative aspect-video w-full overflow-hidden bg-muted">
        {entry.mediaKind === "image" && entry.previewUrl ? (
          <button
            type="button"
            onClick={onPreview}
            aria-label={`${t("assetsPage.preview")} ${entry.title}`}
            className="block h-full w-full cursor-pointer focus-visible:outline-2 focus-visible:outline-ring"
          >
            <img
              src={entry.previewUrl}
              alt={entry.title}
              loading="lazy"
              className="h-full w-full object-contain transition-transform duration-200 group-hover:scale-[1.02]"
            />
          </button>
        ) : entry.mediaKind === "video" && entry.previewUrl ? (
          <button
            type="button"
            onClick={onPreview}
            aria-label={`${t("assetsPage.preview")} ${entry.title}`}
            className="relative block h-full w-full cursor-pointer focus-visible:outline-2 focus-visible:outline-ring"
          >
            {entry.posterUrl ? (
              <img
                src={entry.posterUrl}
                alt={entry.title}
                loading="lazy"
                className="h-full w-full object-contain"
              />
            ) : (
              <video
                src={entry.previewUrl}
                muted
                playsInline
                preload="metadata"
                className="h-full w-full object-contain"
              />
            )}
            <span className="pointer-events-none absolute inset-0 grid place-items-center bg-black/0 transition-colors group-hover:bg-black/20">
              <span className="grid size-9 place-items-center rounded-full bg-background/90 text-foreground opacity-0 shadow-sm transition-opacity group-hover:opacity-100">
                <Play className="size-4 translate-x-[1px]" aria-hidden="true" />
              </span>
            </span>
          </button>
        ) : canAudioPlay ? (
          <button
            type="button"
            onClick={onPreview}
            aria-label={`${t(isPlaying ? "assetsPage.pause" : "assetsPage.play")} ${entry.title}`}
            className="flex h-full w-full cursor-pointer flex-col items-center justify-center gap-2 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
          >
            <span className="grid size-10 place-items-center rounded-full bg-card text-foreground shadow-[var(--shadow-card)]">
              {isPlaying ? (
                <Pause className="size-4" aria-hidden="true" />
              ) : (
                <Play className="size-4 translate-x-[1px]" aria-hidden="true" />
              )}
            </span>
            <span className="max-w-[85%] truncate text-[11px] text-muted-foreground">
              {entry.bucket === "audio" && entry.subtitle ? entry.subtitle : entry.title}
            </span>
          </button>
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-4 text-center text-muted-foreground">
            <AssetEntryIcon entry={entry} className="size-6 opacity-75" />
            {entry.bucket === "skill" && entry.description ? (
              <p className="line-clamp-2 text-[11px] leading-4 text-muted-foreground">
                {entry.description}
              </p>
            ) : null}
          </div>
        )}

        {/* Top-left subtle type indicator for exports/skills */}
        {entry.bucket === "export" ? (
          <span className="pointer-events-none absolute left-2 top-2 rounded-md bg-background/85 px-1.5 py-0.5 text-[10px] font-medium text-foreground backdrop-blur-xs">
            {entry.versionNumber != null ? `v${entry.versionNumber}` : t("assetsPage.kinds.export")}
          </span>
        ) : null}

        {/* Bottom-right duration chip */}
        {entry.durationSeconds != null && entry.durationSeconds > 0 ? (
          <span className="pointer-events-none absolute bottom-2 right-2 rounded-md bg-background/85 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-foreground backdrop-blur-xs">
            {formatDuration(entry.durationSeconds)}
          </span>
        ) : null}
      </div>

      {/* Metadata & Actions */}
      <div className="flex flex-1 flex-col justify-between gap-2 p-3">
        <div className="min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h3
              title={entry.title}
              className="min-w-0 flex-1 truncate text-[13px] leading-5 font-medium text-foreground"
            >
              {entry.title}
            </h3>
          </div>
          <p className="mt-0.5 truncate text-[11px] leading-4 text-muted-foreground">
            {metaLine}
          </p>
          {entry.projectTitle ? (
            <button
              type="button"
              onClick={onOpenProject}
              className="mt-1 inline-flex max-w-full items-center gap-1 truncate text-[11px] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
            >
              <Folder className="size-3 shrink-0" aria-hidden="true" />
              <span className="truncate">{entry.projectTitle}</span>
            </button>
          ) : null}
        </div>

        <div className="flex items-center justify-between gap-1 border-t border-subtle pt-2">
          <Button
            size="sm"
            variant="ghost"
            icon={<MessageSquarePlus className="size-3.5" />}
            onClick={onUseInChat}
          >
            {t("assetsPage.useInNewChat")}
          </Button>
          <div className="flex items-center gap-0.5">
            {canVisualPreview ? (
              <Tooltip content={t("assetsPage.preview")} side="top">
                <IconButton
                  size="sm"
                  variant="ghost"
                  icon={<Play className="size-3.5" />}
                  label={t("assetsPage.preview")}
                  onClick={onPreview}
                />
              </Tooltip>
            ) : null}
            {entry.bucket !== "skill" && entry.previewUrl ? (
              <Tooltip content={t("assetsPage.download")} side="top">
                <IconButton
                  size="sm"
                  variant="ghost"
                  disabled={isDownloading}
                  icon={<Download className="size-3.5" />}
                  label={t("assetsPage.download")}
                  onClick={onDownload}
                />
              </Tooltip>
            ) : null}
            {onOpenProject ? (
              <Tooltip content={t("assetsPage.openProject")} side="top">
                <IconButton
                  size="sm"
                  variant="ghost"
                  icon={<ArrowUpRight className="size-3.5" />}
                  label={t("assetsPage.openProject")}
                  onClick={onOpenProject}
                />
              </Tooltip>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  )
}

function AssetListRow({
  entry,
  metaLine,
  isPlaying,
  isDownloading,
  onPreview,
  onDownload,
  onUseInChat,
  onOpenProject,
}: {
  entry: UnifiedAssetEntry
  metaLine: string
  isPlaying: boolean
  isDownloading: boolean
  onPreview: () => void
  onDownload: () => void
  onUseInChat: () => void
  onOpenProject?: () => void
}) {
  const { t } = useTranslation()
  const canAudioPlay = entry.mediaKind === "audio" && Boolean(entry.previewUrl)
  const canVisualPreview =
    (entry.mediaKind === "video" || entry.mediaKind === "image") && Boolean(entry.previewUrl)

  return (
    <div className="group flex items-center gap-3 rounded-[var(--aui-radius-lg,10px)] bg-card px-3 py-2 shadow-[var(--shadow-card)] transition-colors hover:bg-accent/50">
      {/* Compact thumbnail or icon tile */}
      <button
        type="button"
        disabled={!canAudioPlay && !canVisualPreview}
        onClick={onPreview}
        aria-label={`${t(canAudioPlay ? (isPlaying ? "assetsPage.pause" : "assetsPage.play") : "assetsPage.preview")} ${entry.title}`}
        className="relative grid size-10 shrink-0 place-items-center overflow-hidden rounded-md bg-muted text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring"
      >
        {entry.mediaKind === "image" && entry.previewUrl ? (
          <img src={entry.previewUrl} alt="" loading="lazy" className="h-full w-full object-cover" />
        ) : entry.mediaKind === "video" && entry.posterUrl ? (
          <img src={entry.posterUrl} alt="" loading="lazy" className="h-full w-full object-cover" />
        ) : canAudioPlay ? (
          isPlaying ? (
            <Pause className="size-4 text-foreground" aria-hidden="true" />
          ) : (
            <Play className="size-4 translate-x-[1px] text-foreground" aria-hidden="true" />
          )
        ) : (
          <AssetEntryIcon entry={entry} className="size-4" />
        )}
      </button>

      {/* Title & metadata */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span title={entry.title} className="truncate text-[13px] leading-5 font-medium text-foreground">
            {entry.title}
          </span>
          {entry.projectTitle ? (
            <button
              type="button"
              onClick={onOpenProject}
              className="hidden shrink-0 items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground sm:inline-flex"
            >
              <Folder className="size-3" aria-hidden="true" />
              <span className="max-w-36 truncate">{entry.projectTitle}</span>
            </button>
          ) : null}
        </div>
        <p className="truncate text-[11px] leading-4 text-muted-foreground">{metaLine}</p>
      </div>

      {/* Inline actions */}
      <div className="flex shrink-0 items-center gap-1">
        <Button
          size="sm"
          variant="ghost"
          icon={<MessageSquarePlus className="size-3.5" />}
          onClick={onUseInChat}
        >
          <span className="hidden sm:inline">{t("assetsPage.useInNewChat")}</span>
        </Button>
        {entry.bucket !== "skill" && entry.previewUrl ? (
          <Tooltip content={t("assetsPage.download")} side="top">
            <IconButton
              size="sm"
              variant="ghost"
              disabled={isDownloading}
              icon={<Download className="size-3.5" />}
              label={t("assetsPage.download")}
              onClick={onDownload}
            />
          </Tooltip>
        ) : null}
        {onOpenProject ? (
          <Tooltip content={t("assetsPage.openProject")} side="top">
            <IconButton
              size="sm"
              variant="ghost"
              icon={<ArrowUpRight className="size-3.5" />}
              label={t("assetsPage.openProject")}
              onClick={onOpenProject}
            />
          </Tooltip>
        ) : null}
      </div>
    </div>
  )
}
