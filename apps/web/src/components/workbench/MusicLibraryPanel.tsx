import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  MessageSquarePlus,
  Music2,
  Pause,
  Play,
  Search,
  Sparkles,
  X,
} from "@/components/ui/icons"

import { Badge } from "@/components/ui/badge-clean"
import { Button } from "@/components/ui/button-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Select } from "@/components/ui/select-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { API_URL, apiFetch } from "@/lib/api"
import { useOptionalWorkbench } from "./WorkbenchContext"

export interface MusicSectionItem {
  name: string
  label?: string | null
  label_zh?: string | null
  start_seconds: number
  end_seconds: number
  energy?: string
  voice_friendly?: boolean
  recommended?: boolean
  note?: string | null
  note_zh?: string | null
}

export interface MusicLibraryItem {
  id: string
  mood: string
  title: string
  title_zh?: string | null
  category?: string | null
  genre?: string | null
  energy: string
  bpm?: number | null
  format_kind?: string | null
  summary?: string | null
  use_for: string[]
  avoid: string[]
  sections: MusicSectionItem[]
  waveform_peaks: number[]
  url: string
  duration_seconds?: number | null
  lufs?: number | null
  tags: string[]
  scope: string
  status: string
}

const CATEGORY_ORDER = ["product_promo", "vlog", "visual_craft", "explainer"] as const

const SWATCH_STYLES: Record<string, string> = {
  product_promo:
    "bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 text-slate-100",
  vlog: "bg-gradient-to-br from-amber-900 via-orange-900 to-stone-900 text-amber-50",
  visual_craft:
    "bg-gradient-to-br from-zinc-900 via-neutral-800 to-emerald-950 text-emerald-50",
  explainer:
    "bg-gradient-to-br from-stone-900 via-slate-800 to-sky-950 text-sky-50",
}

function resolveStreamUrl(url: string): string {
  if (/^https?:\/\//i.test(url) || url.startsWith("blob:") || url.startsWith("data:")) {
    return url
  }
  const normalized = url.startsWith("/") ? url : `/${url}`
  return `${API_URL}${normalized}`
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "--:--"
  const total = Math.floor(seconds)
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${String(secs).padStart(2, "0")}`
}

export default function MusicLibraryPanel({
  view = "list",
  hideToolbar = false,
  query: queryProp,
  category: categoryProp,
  onCategoriesChange,
  onCountChange,
  onUsePreset,
}: {
  view?: "grid" | "list"
  hideToolbar?: boolean
  query?: string
  category?: string
  onCategoriesChange?: (categories: { value: string; label: string }[]) => void
  onCountChange?: (count: number) => void
  onUsePreset?: (instruction: string) => void
}) {
  const { t, i18n } = useTranslation()
  const workbench = useOptionalWorkbench()
  const zh = i18n.language.startsWith("zh")

  const [rows, setRows] = useState<MusicLibraryItem[]>([])
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading")
  const [retry, setRetry] = useState(0)
  const [innerCategory, setInnerCategory] = useState("")
  const [innerQuery, setInnerQuery] = useState("")
  const [activeId, setActiveId] = useState<string | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [liveDuration, setLiveDuration] = useState(0)
  const [statusMessage, setStatusMessage] = useState("")

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const category = categoryProp ?? innerCategory
  const query = queryProp ?? innerQuery

  useEffect(() => {
    return () => {
      audioRef.current?.pause()
      audioRef.current = null
    }
  }, [])

  useEffect(() => {
    const abort = new AbortController()
    async function load() {
      setState("loading")
      const response = await apiFetch("/api/v1/music", {
        signal: abort.signal,
        toast: false,
      })
      if (!response.ok) throw new Error("music_library")
      const data = (await response.json()) as MusicLibraryItem[]
      if (!abort.signal.aborted) {
        setRows(Array.isArray(data) ? data : [])
        setState("ready")
      }
    }
    load().catch(() => {
      if (!abort.signal.aborted) setState("failed")
    })
    return () => abort.abort()
  }, [retry])

  const categoryOptions = useMemo(() => {
    const present = new Set(rows.map((r) => r.category).filter((c): c is string => Boolean(c)))
    const ordered = [
      ...CATEGORY_ORDER.filter((c) => present.has(c)),
      ...[...present].filter(
        (c) => !CATEGORY_ORDER.includes(c as (typeof CATEGORY_ORDER)[number]),
      ),
    ]
    return ordered.map((c) => ({
      value: c,
      label: t(`musicLibrary.categories.${c}`, { defaultValue: c }),
    }))
  }, [rows, t])

  useEffect(() => {
    onCategoriesChange?.(categoryOptions)
  }, [categoryOptions, onCategoriesChange])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((row) => {
      if (category && row.category !== category) return false
      if (!q) return true
      const haystack = [
        row.title,
        row.title_zh,
        row.mood,
        row.genre,
        row.category,
        row.summary,
        ...row.tags,
        ...row.use_for,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
      return haystack.includes(q)
    })
  }, [rows, category, query])

  useEffect(() => {
    onCountChange?.(filtered.length)
  }, [filtered.length, onCountChange])

  const activeTrack = useMemo(
    () => rows.find((r) => r.id === activeId) ?? null,
    [rows, activeId],
  )

  const displayTitle = (row: MusicLibraryItem) =>
    zh && row.title_zh ? row.title_zh : row.title

  const secondaryTitle = (row: MusicLibraryItem) =>
    zh && row.title_zh && row.title !== row.title_zh ? row.title : row.genre || ""

  const sectionLabel = (sec: MusicSectionItem) =>
    (zh && sec.label_zh) || sec.label || sec.name

  const sectionNote = (sec: MusicSectionItem) =>
    (zh && sec.note_zh) || sec.note || undefined

  function buildInstruction(row: MusicLibraryItem, section?: MusicSectionItem) {
    const name = displayTitle(row)
    return section
      ? t("musicLibrary.sectionInstruction", {
          name,
          id: row.id,
          section: sectionLabel(section),
          start: Math.round(section.start_seconds),
          end: Math.round(section.end_seconds),
        })
      : t("musicLibrary.trackInstruction", {
          name,
          id: row.id,
        })
  }

  function closePlayer() {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    setActiveId(null)
    setIsPlaying(false)
    setCurrentTime(0)
    setLiveDuration(0)
  }

  function playTrack(row: MusicLibraryItem, startAtSeconds?: number) {
    setStatusMessage("")
    if (activeId === row.id && audioRef.current && startAtSeconds === undefined) {
      if (isPlaying) {
        audioRef.current.pause()
        setIsPlaying(false)
      } else {
        setIsPlaying(true)
        void audioRef.current.play().catch(() => {
          setIsPlaying(false)
          setStatusMessage(t("musicLibrary.playbackError"))
        })
      }
      return
    }
    if (activeId === row.id && audioRef.current && startAtSeconds !== undefined) {
      const target = Math.max(0, startAtSeconds)
      try {
        audioRef.current.currentTime = target
      } catch {
        // Ignore seek error before metadata ready
      }
      setCurrentTime(target)
      setIsPlaying(true)
      void audioRef.current.play().catch(() => {
        setIsPlaying(false)
        setStatusMessage(t("musicLibrary.playbackError"))
      })
      return
    }
    audioRef.current?.pause()
    const audio = new Audio(resolveStreamUrl(row.url))
    audio.preload = "metadata"
    audioRef.current = audio
    setActiveId(row.id)
    setIsPlaying(true)
    const initialOffset = startAtSeconds ?? 0
    setCurrentTime(initialOffset)
    setLiveDuration(row.duration_seconds ?? 0)

    let seekApplied = initialOffset <= 0
    const applyInitialSeek = () => {
      if (audioRef.current !== audio) return
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        setLiveDuration(audio.duration)
      }
      if (!seekApplied && initialOffset > 0) {
        try {
          audio.currentTime = initialOffset
          seekApplied = true
        } catch {
          // Wait for canplay if metadata hasn't buffered seekable ranges yet
        }
      }
    }
    audio.addEventListener("loadedmetadata", applyInitialSeek, { once: true })
    audio.addEventListener("canplay", applyInitialSeek, { once: true })
    audio.addEventListener("timeupdate", () => {
      if (audioRef.current === audio) setCurrentTime(audio.currentTime)
    })
    audio.addEventListener("ended", () => {
      if (audioRef.current === audio) setIsPlaying(false)
    })
    audio.addEventListener("error", () => {
      if (audioRef.current === audio) {
        setIsPlaying(false)
        setStatusMessage(t("musicLibrary.playbackError"))
      }
    })
    void audio.play().catch(() => {
      if (audioRef.current === audio) {
        setIsPlaying(false)
        setStatusMessage(t("musicLibrary.playbackError"))
      }
    })
  }

  function stepTrack(delta: -1 | 1) {
    if (!filtered.length) return
    const idx = filtered.findIndex((r) => r.id === activeId)
    const nextIdx =
      idx === -1 ? 0 : (idx + delta + filtered.length) % filtered.length
    const next = filtered[nextIdx]
    if (next) {
      const rec = next.sections.find((s) => s.recommended)
      playTrack(next, rec ? rec.start_seconds : 0)
    }
  }

  function seekActive(seconds: number) {
    if (!activeTrack) return
    const maxDur = liveDuration || activeTrack.duration_seconds || 0
    const clamped = Math.max(0, maxDur > 0 ? Math.min(maxDur, seconds) : seconds)
    if (audioRef.current) {
      try {
        audioRef.current.currentTime = clamped
      } catch {
        // Ignore seek errors
      }
    }
    setCurrentTime(clamped)
  }

  function deliverInstruction(instruction: string) {
    if (workbench) {
      if (!workbench.citeText(instruction)) {
        setStatusMessage(t("visualGallery.citeFailed"))
      }
      return
    }
    if (onUsePreset) {
      onUsePreset(instruction)
      return
    }
    void navigator.clipboard?.writeText(instruction).then(() => {
      toast.success(t("common.copied"))
    })
  }

  function handleCopy(row: MusicLibraryItem, section?: MusicSectionItem) {
    const instruction = buildInstruction(row, section)
    void navigator.clipboard?.writeText(instruction).then(() => {
      toast.success(t("common.copied"))
    })
  }

  function citeTrack(row: MusicLibraryItem, section?: MusicSectionItem) {
    deliverInstruction(buildInstruction(row, section))
  }

  function citeAtTimestamp(row: MusicLibraryItem, seconds: number) {
    const matchedSection = row.sections.find(
      (s) => seconds >= s.start_seconds && seconds < s.end_seconds,
    )
    const rounded = Math.max(0, Math.floor(seconds))
    if (matchedSection && Math.abs(rounded - matchedSection.start_seconds) <= 3) {
      citeTrack(row, matchedSection)
      return
    }
    deliverInstruction(
      t("musicLibrary.timestampInstruction", {
        name: displayTitle(row),
        id: row.id,
        start: rounded,
        time: formatDuration(rounded),
      }),
    )
  }

  function renderWaveform(row: MusicLibraryItem, compact: boolean) {
    const isActive = activeId === row.id
    const duration =
      (isActive && liveDuration > 0 ? liveDuration : row.duration_seconds) || 0
    const progress =
      isActive && duration > 0 ? Math.min(1, Math.max(0, currentTime / duration)) : 0
    const peaks = row.waveform_peaks.length ? row.waveform_peaks : Array(48).fill(0.35)

    return (
      <div className="relative">
        <div
          role="slider"
          tabIndex={0}
          aria-label={`${t("musicLibrary.seekWaveform")} ${displayTitle(row)}`}
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={isActive ? Math.round(currentTime) : 0}
          onClick={(event) => {
            if (duration <= 0) {
              playTrack(row)
              return
            }
            const rect = event.currentTarget.getBoundingClientRect()
            const ratio = Math.min(
              1,
              Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width)),
            )
            playTrack(row, ratio * duration)
          }}
          onKeyDown={(event) => {
            if (duration <= 0) return
            if (event.key === "ArrowRight") {
              event.preventDefault()
              playTrack(row, Math.min(duration, (isActive ? currentTime : 0) + 5))
            } else if (event.key === "ArrowLeft") {
              event.preventDefault()
              playTrack(row, Math.max(0, (isActive ? currentTime : 0) - 5))
            } else if (event.key === " " || event.key === "Enter") {
              event.preventDefault()
              playTrack(row)
            }
          }}
          className={`relative flex cursor-pointer items-end gap-[2px] overflow-hidden rounded-md bg-muted/70 px-2 py-1.5 transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-foreground ${
            compact ? "h-9" : "h-11"
          }`}
        >
          {duration > 0 &&
            row.sections
              .filter((sec) => sec.recommended)
              .map((sec) => {
                const leftPct = (sec.start_seconds / duration) * 100
                const widthPct = Math.max(
                  1,
                  ((sec.end_seconds - sec.start_seconds) / duration) * 100,
                )
                return (
                  <span
                    key={`band:${row.id}:${sec.name}`}
                    aria-hidden="true"
                    className="pointer-events-none absolute bottom-0 h-[2px] bg-foreground/45"
                    style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                  />
                )
              })}

          {peaks.map((amp, idx) => {
            const ratio = idx / Math.max(1, peaks.length)
            const playedBar = isActive && ratio <= progress
            const secTime = ratio * duration
            const inRecommended =
              duration > 0 &&
              row.sections.some(
                (s) =>
                  s.recommended && secTime >= s.start_seconds && secTime < s.end_seconds,
              )
            return (
              <span
                key={idx}
                className={`flex-1 rounded-xs transition-colors ${
                  playedBar
                    ? "bg-foreground"
                    : inRecommended
                      ? "bg-foreground/35"
                      : "bg-muted-foreground/25"
                }`}
                style={{ height: `${Math.max(14, Math.round(amp * 100))}%` }}
              />
            )
          })}
        </div>

        {isActive && (
          <span className="pointer-events-none absolute top-1 right-1.5 rounded bg-background/85 px-1.5 py-0.5 text-[10px] font-medium text-foreground tabular-nums">
            {formatDuration(currentTime)} / {formatDuration(duration)}
          </span>
        )}
      </div>
    )
  }

  function renderSections(row: MusicLibraryItem) {
    if (!row.sections.length) return null
    const isActive = activeId === row.id
    return (
      <div className="flex flex-wrap items-center gap-1">
        {row.sections.map((sec) => {
          const activeSec =
            isActive &&
            currentTime >= sec.start_seconds &&
            currentTime < sec.end_seconds
          return (
            <button
              key={`${row.id}:${sec.name}`}
              type="button"
              title={sectionNote(sec)}
              onClick={() => playTrack(row, sec.start_seconds)}
              className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] leading-4 transition-colors focus-visible:outline-2 focus-visible:outline-foreground ${
                activeSec
                  ? "border-foreground bg-foreground text-background"
                  : sec.recommended
                    ? "border-foreground/20 bg-muted text-foreground hover:border-foreground/40 hover:bg-accent"
                    : "border-transparent bg-muted/60 text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {sec.recommended ? <Sparkles className="size-2.5 shrink-0 opacity-80" /> : null}
              <span>{sectionLabel(sec)}</span>
              <span className="tabular-nums opacity-75">
                {formatDuration(sec.start_seconds)}
              </span>
            </button>
          )
        })}
      </div>
    )
  }

  function renderActions(row: MusicLibraryItem) {
    const primaryRec = row.sections.find((s) => s.recommended)
    return (
      <div className="inline-flex items-center justify-end gap-1.5">
        {!workbench ? (
          <Button
            variant="ghost"
            size="sm"
            icon={<Copy size={13} />}
            onClick={() => handleCopy(row, primaryRec)}
          >
            {t("common.copy")}
          </Button>
        ) : null}
        <Button
          variant="secondary"
          size="sm"
          icon={workbench ? <MessageSquarePlus size={13} /> : <Sparkles size={13} />}
          onClick={() => citeTrack(row, primaryRec)}
          title={primaryRec ? sectionNote(primaryRec) : undefined}
        >
          {primaryRec
            ? t("musicLibrary.useFromRecommended", {
                time: formatDuration(primaryRec.start_seconds),
              })
            : workbench
              ? t("soundLab.cite")
              : t("presetsPage.usePreset")}
        </Button>
      </div>
    )
  }

  if (state === "loading") {
    return (
      <div className="flex h-48 items-center justify-center gap-2 text-sm text-muted-foreground">
        <Spinner size={16} />
        <span>{t("musicLibrary.loading")}</span>
      </div>
    )
  }

  if (state === "failed") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-subtle bg-card p-10 text-center">
        <p className="text-sm text-muted-foreground">{t("musicLibrary.failed")}</p>
        <Button size="sm" variant="secondary" onClick={() => setRetry((n) => n + 1)}>
          {t("common.retry")}
        </Button>
      </div>
    )
  }

  const activeDuration =
    (activeTrack && (liveDuration || activeTrack.duration_seconds)) || 0
  const activeProgress =
    activeDuration > 0 ? Math.min(1, Math.max(0, currentTime / activeDuration)) : 0
  const activeSection = activeTrack?.sections.find(
    (sec) => currentTime >= sec.start_seconds && currentTime < sec.end_seconds,
  )

  return (
    <section
      className="relative flex min-h-0 flex-1 flex-col gap-4"
      aria-label={t("visualGallery.music")}
    >
      {!hideToolbar && (
        <div className="flex flex-wrap items-center gap-2 px-3 pt-3">
          <div className="min-w-0 flex-1">
            <TextField
              size="sm"
              type="search"
              prefix={<Search className="size-4" />}
              value={innerQuery}
              onChange={(event) => setInnerQuery(event.target.value)}
              aria-label={t("musicLibrary.search")}
              placeholder={t("musicLibrary.search")}
            />
          </div>
          {categoryOptions.length > 0 && (
            <Select
              size="sm"
              aria-label={t("soundLab.category")}
              value={innerCategory}
              onChange={setInnerCategory}
              options={[{ value: "", label: t("visualGallery.all") }, ...categoryOptions]}
            />
          )}
        </div>
      )}

      {statusMessage && (
        <p className="px-1 text-xs text-muted-foreground" role="status">
          {statusMessage}
        </p>
      )}

      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-subtle bg-card px-6 py-14 text-center">
          <Music2 className="size-6 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">{t("musicLibrary.emptyTitle")}</p>
          <p className="max-w-md text-xs leading-5 text-muted-foreground">
            {t("musicLibrary.emptyBody")}
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-subtle bg-card px-6 py-12 text-center text-sm text-muted-foreground">
          {t("musicLibrary.noMatches")}
        </div>
      ) : view === "list" ? (
        <div className="ui-th-table-frame !w-full">
          <table className="ui-th-table ui-th-table--middle">
            <thead className="ui-th-table__head">
              <tr>
                <th className="ui-th-table__th w-64">{t("presetsPage.colTrack")}</th>
                <th className="ui-th-table__th w-40">{t("presetsPage.colSpecs")}</th>
                <th className="ui-th-table__th">{t("presetsPage.colWaveform")}</th>
                <th className="ui-th-table__th text-right">{t("presetsPage.colActions")}</th>
              </tr>
            </thead>
            <tbody className="ui-th-table__body">
              {filtered.map((row) => {
                const isActive = activeId === row.id
                const rowPlaying = isActive && isPlaying
                const duration =
                  (isActive && liveDuration > 0 ? liveDuration : row.duration_seconds) || 0
                const hasVoiceSafe =
                  row.tags.includes("voice-friendly") ||
                  row.sections.some((s) => s.recommended && s.voice_friendly)
                const swatch =
                  SWATCH_STYLES[row.category ?? "product_promo"] ?? SWATCH_STYLES.product_promo
                const sub = secondaryTitle(row)

                return (
                  <tr key={row.id} className="ui-th-table__row">
                    <td className="ui-th-table__td w-64">
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => playTrack(row)}
                          aria-label={`${t(rowPlaying ? "assetsPage.pause" : "assetsPage.play")} ${displayTitle(row)}`}
                          className={`relative flex size-11 shrink-0 items-center justify-center rounded-lg transition-transform active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-foreground ${swatch}`}
                        >
                          {rowPlaying ? (
                            <Pause className="size-4" />
                          ) : (
                            <Play className="size-4 translate-x-[1px]" />
                          )}
                          <span className="pointer-events-none absolute bottom-0.5 left-1 text-[9px] leading-3 font-medium tabular-nums opacity-85">
                            {formatDuration(duration)}
                          </span>
                        </button>
                        <div className="min-w-0">
                          <div className="truncate font-medium text-foreground">
                            {displayTitle(row)}
                          </div>
                          {sub ? (
                            <div className="mt-0.5 truncate text-xs font-normal text-muted-foreground">
                              {sub}
                            </div>
                          ) : null}
                          {hasVoiceSafe ? (
                            <div className="mt-1">
                              <Badge size="sm" tone="info">
                                {t("musicLibrary.voiceFriendly")}
                              </Badge>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </td>
                    <td className="ui-th-table__td w-40 whitespace-nowrap">
                      <div className="flex flex-col items-start gap-1">
                        {row.category ? (
                          <Badge size="sm">
                            {t(`musicLibrary.categories.${row.category}`, {
                              defaultValue: row.category,
                            })}
                          </Badge>
                        ) : null}
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {[
                            row.bpm ? `${row.bpm} BPM` : null,
                            row.lufs != null ? `${row.lufs.toFixed(1)} LUFS` : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </div>
                    </td>
                    <td className="ui-th-table__td min-w-[20rem]">
                      <div className="flex flex-col gap-1.5">
                        {renderWaveform(row, true)}
                        {renderSections(row)}
                      </div>
                    </td>
                    <td className="ui-th-table__td whitespace-nowrap text-right">
                      {renderActions(row)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
          {filtered.map((row) => {
            const isActive = activeId === row.id
            const rowPlaying = isActive && isPlaying
            const duration =
              (isActive && liveDuration > 0 ? liveDuration : row.duration_seconds) || 0
            const hasVoiceSafe =
              row.tags.includes("voice-friendly") ||
              row.sections.some((s) => s.recommended && s.voice_friendly)
            const swatch =
              SWATCH_STYLES[row.category ?? "product_promo"] ?? SWATCH_STYLES.product_promo
            const sub = secondaryTitle(row)

            return (
              <article
                key={row.id}
                className={`flex flex-col gap-3 rounded-xl border bg-card p-4 text-foreground transition-colors ${
                  isActive
                    ? "border-foreground/30 shadow-sm"
                    : "border-subtle shadow-resting hover:border-foreground/15"
                }`}
              >
                <div className="flex items-start gap-3">
                  <button
                    type="button"
                    onClick={() => playTrack(row)}
                    aria-label={`${t(rowPlaying ? "assetsPage.pause" : "assetsPage.play")} ${displayTitle(row)}`}
                    className={`relative flex size-12 shrink-0 items-center justify-center rounded-lg transition-transform active:scale-[0.97] focus-visible:outline-2 focus-visible:outline-foreground ${swatch}`}
                  >
                    {rowPlaying ? (
                      <Pause className="size-4.5" />
                    ) : (
                      <Play className="size-4.5 translate-x-[1px]" />
                    )}
                    <span className="pointer-events-none absolute bottom-0.5 left-1 text-[9px] leading-3 font-medium tabular-nums opacity-85">
                      {formatDuration(duration)}
                    </span>
                  </button>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <h3 className="truncate text-sm font-medium text-foreground">
                        {displayTitle(row)}
                      </h3>
                      {row.category && (
                        <Badge size="sm">
                          {t(`musicLibrary.categories.${row.category}`, {
                            defaultValue: row.category,
                          })}
                        </Badge>
                      )}
                      {hasVoiceSafe && (
                        <Badge size="sm" tone="info">
                          {t("musicLibrary.voiceFriendly")}
                        </Badge>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                      {[
                        sub || null,
                        row.bpm ? `${row.bpm} BPM` : null,
                        row.lufs != null ? `${row.lufs.toFixed(1)} LUFS` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                </div>

                {row.summary && (
                  <p className="text-xs leading-5 text-muted-foreground">{row.summary}</p>
                )}

                {renderWaveform(row, false)}
                {renderSections(row)}

                <div className="mt-auto flex items-center justify-between gap-2 border-t border-subtle pt-2.5">
                  <span className="truncate text-xs text-muted-foreground">
                    {row.use_for[0] ?? ""}
                  </span>
                  {renderActions(row)}
                </div>
              </article>
            )
          })}
        </div>
      )}

      {/* Sticky Bottom Studio Audio Player Bar */}
      {activeTrack && (
        <div
          role="region"
          aria-label={displayTitle(activeTrack)}
          className="sticky bottom-3 z-20 mt-2 flex flex-col gap-2.5 rounded-xl border border-subtle bg-card/95 px-4 py-3 shadow-md backdrop-blur-md sm:flex-row sm:items-center sm:gap-4"
        >
          <div className="flex min-w-0 items-center gap-3 sm:w-56 sm:shrink-0">
            <div
              className={`flex size-10 shrink-0 items-center justify-center rounded-lg ${
                SWATCH_STYLES[activeTrack.category ?? "product_promo"] ??
                SWATCH_STYLES.product_promo
              }`}
            >
              <Music2 className="size-4" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-foreground">
                {displayTitle(activeTrack)}
              </p>
              <p className="truncate text-[11px] text-muted-foreground">
                {activeSection
                  ? `${sectionLabel(activeSection)} · ${formatDuration(activeSection.start_seconds)}–${formatDuration(activeSection.end_seconds)}`
                  : [
                      activeTrack.genre,
                      activeTrack.bpm ? `${activeTrack.bpm} BPM` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
              </p>
            </div>
          </div>

          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <div className="flex items-center justify-center gap-1.5">
              <IconButton
                size="sm"
                variant="ghost"
                label={t("musicLibrary.previousTrack")}
                icon={<ChevronLeft className="size-4" />}
                onClick={() => stepTrack(-1)}
              />
              <IconButton
                size="sm"
                variant="primary"
                pressed={isPlaying}
                label={t(isPlaying ? "assetsPage.pause" : "assetsPage.play")}
                icon={
                  isPlaying ? (
                    <Pause className="size-4" />
                  ) : (
                    <Play className="size-4 translate-x-[1px]" />
                  )
                }
                onClick={() => playTrack(activeTrack)}
              />
              <IconButton
                size="sm"
                variant="ghost"
                label={t("musicLibrary.nextTrack")}
                icon={<ChevronRight className="size-4" />}
                onClick={() => stepTrack(1)}
              />
            </div>

            <div className="flex items-center gap-2.5">
              <span className="w-10 text-right text-[11px] text-muted-foreground tabular-nums">
                {formatDuration(currentTime)}
              </span>
              <div
                role="slider"
                tabIndex={0}
                aria-label={t("musicLibrary.seekWaveform")}
                aria-valuemin={0}
                aria-valuemax={Math.round(activeDuration)}
                aria-valuenow={Math.round(currentTime)}
                onClick={(event) => {
                  if (activeDuration <= 0) return
                  const rect = event.currentTarget.getBoundingClientRect()
                  const ratio = Math.min(
                    1,
                    Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width)),
                  )
                  seekActive(ratio * activeDuration)
                }}
                className="relative flex h-4 flex-1 cursor-pointer items-center"
              >
                <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-foreground transition-[width] duration-75"
                    style={{ width: `${activeProgress * 100}%` }}
                  />
                  {activeDuration > 0 &&
                    activeTrack.sections.map((sec) => {
                      if (sec.start_seconds <= 0) return null
                      const pct = (sec.start_seconds / activeDuration) * 100
                      return (
                        <span
                          key={`tick:${sec.name}`}
                          aria-hidden="true"
                          className="pointer-events-none absolute top-0 bottom-0 w-px bg-background/70"
                          style={{ left: `${pct}%` }}
                        />
                      )
                    })}
                </div>
              </div>
              <span className="w-10 text-[11px] text-muted-foreground tabular-nums">
                {formatDuration(activeDuration)}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-end gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              icon={<Sparkles size={13} />}
              onClick={() => citeAtTimestamp(activeTrack, currentTime)}
            >
              <span className="tabular-nums">
                {t("musicLibrary.useFromCurrent", {
                  time: formatDuration(currentTime),
                })}
              </span>
            </Button>
            <IconButton
              size="sm"
              variant="ghost"
              label={t("musicLibrary.closePlayer")}
              icon={<X className="size-4" />}
              onClick={closePlayer}
            />
          </div>
        </div>
      )}
    </section>
  )
}
