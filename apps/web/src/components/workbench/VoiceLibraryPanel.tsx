import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Copy, MessageSquarePlus, Mic, Pause, Play, Search, Sparkles } from "@/components/ui/icons"

import { Badge } from "@/components/ui/badge-clean"
import { Button } from "@/components/ui/button-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Select } from "@/components/ui/select-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { apiFetch } from "@/lib/api"
import { useOptionalWorkbench } from "./WorkbenchContext"

export interface VoiceLibraryItem {
  id: string
  owner_id?: string | null
  scope: string
  status: string
  source_kind: string
  name: string
  description?: string | null
  languages: string[]
  gender?: string | null
  age_band?: string | null
  tone_tags: string[]
  compatible_styles: string[]
  provider: string
  provider_voice_id: string
  preview_url?: string | null
  use_count: number
  is_favorite: boolean
}

function formatDuration(seconds: number): string {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) return "--:--"
  const total = Math.round(seconds)
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${String(secs).padStart(2, "0")}`
}

export default function VoiceLibraryPanel({
  view = "grid",
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
  const { t } = useTranslation()
  const workbench = useOptionalWorkbench()

  const [rows, setRows] = useState<VoiceLibraryItem[]>([])
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading")
  const [retry, setRetry] = useState(0)
  const [innerCategory, setInnerCategory] = useState("")
  const [innerQuery, setInnerQuery] = useState("")
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [statusMessage, setStatusMessage] = useState("")

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const blobUrlsRef = useRef<Map<string, string>>(new Map())
  const category = categoryProp ?? innerCategory
  const query = queryProp ?? innerQuery

  useEffect(() => {
    const urls = blobUrlsRef.current
    return () => {
      audioRef.current?.pause()
      audioRef.current = null
      for (const url of urls.values()) {
        URL.revokeObjectURL(url)
      }
      urls.clear()
    }
  }, [])

  useEffect(() => {
    const abort = new AbortController()
    async function load() {
      setState("loading")
      const response = await apiFetch("/api/v1/voices", {
        signal: abort.signal,
        toast: false,
      })
      if (!response.ok) throw new Error("voice_library")
      const data = (await response.json()) as VoiceLibraryItem[]
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
    const present = new Set(
      rows
        .map((r) => (r.gender || "").toLowerCase())
        .filter((g) => g === "female" || g === "male"),
    )
    return (["female", "male"] as const)
      .filter((g) => present.has(g))
      .map((g) => ({
        value: g,
        label: t(`voiceLibrary.categories.${g}`, { defaultValue: g }),
      }))
  }, [rows, t])

  useEffect(() => {
    onCategoriesChange?.(categoryOptions)
  }, [categoryOptions, onCategoriesChange])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((row) => {
      if (category && (row.gender || "").toLowerCase() !== category) return false
      if (!q) return true
      const haystack = [
        row.name,
        row.description,
        row.gender,
        row.source_kind,
        ...row.languages,
        ...row.tone_tags,
        ...row.compatible_styles,
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

  function stopPlayback() {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    setPlayingId(null)
    setCurrentTime(0)
    setDuration(0)
  }

  async function togglePlay(row: VoiceLibraryItem) {
    setStatusMessage("")
    if (playingId === row.id) {
      stopPlayback()
      return
    }
    if (!row.preview_url) {
      setStatusMessage(t("voiceLibrary.playbackError"))
      return
    }
    audioRef.current?.pause()
    setPlayingId(row.id)
    setCurrentTime(0)
    setDuration(0)

    let objectUrl = blobUrlsRef.current.get(row.id)
    if (!objectUrl) {
      try {
        const res = await apiFetch(row.preview_url, { toast: false })
        if (!res.ok) throw new Error("voice_audio_fetch")
        const blob = await res.blob()
        objectUrl = URL.createObjectURL(blob)
        blobUrlsRef.current.set(row.id, objectUrl)
      } catch {
        setPlayingId(null)
        setStatusMessage(t("voiceLibrary.playbackError"))
        return
      }
    }

    const audio = new Audio(objectUrl)
    audioRef.current = audio
    audio.addEventListener("loadedmetadata", () => {
      if (audioRef.current === audio && Number.isFinite(audio.duration)) {
        setDuration(audio.duration)
      }
    })
    audio.addEventListener("timeupdate", () => {
      if (audioRef.current === audio) setCurrentTime(audio.currentTime)
    })
    audio.addEventListener("ended", () => {
      if (audioRef.current === audio) {
        setPlayingId(null)
        setCurrentTime(0)
      }
    })
    audio.addEventListener("error", () => {
      if (audioRef.current === audio) {
        setPlayingId(null)
        setStatusMessage(t("voiceLibrary.playbackError"))
      }
    })
    void audio.play().catch(() => {
      if (audioRef.current === audio) {
        setPlayingId(null)
        setStatusMessage(t("voiceLibrary.playbackError"))
      }
    })
  }

  function buildVoiceInstruction(row: VoiceLibraryItem) {
    return t("voiceLibrary.instruction", {
      name: row.name,
      id: row.id,
    })
  }

  function handleCopyVoice(row: VoiceLibraryItem) {
    void navigator.clipboard?.writeText(buildVoiceInstruction(row)).then(() => {
      toast.success(t("common.copied"))
    })
  }

  function citeVoice(row: VoiceLibraryItem) {
    const instruction = buildVoiceInstruction(row)
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

  function sourceBadgeLabel(kind: string): string {
    if (kind === "minimax_clone") return t("voiceLibrary.sourceCloned")
    if (kind === "minimax_design") return t("voiceLibrary.sourceDesigned")
    return t("voiceLibrary.sourceStock")
  }

  if (state === "loading") {
    return (
      <div className="flex h-48 items-center justify-center gap-2 text-sm text-muted-foreground">
        <Spinner size={16} />
        <span>{t("voiceLibrary.loading")}</span>
      </div>
    )
  }

  if (state === "failed") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-subtle bg-card p-10 text-center">
        <p className="text-sm text-muted-foreground">{t("voiceLibrary.failed")}</p>
        <Button size="sm" variant="secondary" onClick={() => setRetry((n) => n + 1)}>
          {t("common.retry")}
        </Button>
      </div>
    )
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3" aria-label={t("visualGallery.voices")}>
      {!hideToolbar && (
        <div className="flex flex-wrap items-center gap-2 px-3 pt-3">
          <div className="min-w-0 flex-1">
            <TextField
              size="sm"
              type="search"
              prefix={<Search className="size-4" />}
              value={innerQuery}
              onChange={(event) => setInnerQuery(event.target.value)}
              aria-label={t("voiceLibrary.search")}
              placeholder={t("voiceLibrary.search")}
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
        <p className="px-3 text-xs text-muted-foreground" role="status">
          {statusMessage}
        </p>
      )}

      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-subtle bg-card px-6 py-14 text-center">
          <Mic className="size-6 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">{t("voiceLibrary.emptyTitle")}</p>
          <p className="max-w-md text-xs leading-5 text-muted-foreground">
            {t("voiceLibrary.emptyBody")}
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-subtle bg-card px-6 py-12 text-center text-sm text-muted-foreground">
          {t("voiceLibrary.noMatches")}
        </div>
      ) : view === "list" ? (
        <div className="ui-th-table-frame !w-full">
          <table className="ui-th-table ui-th-table--middle">
            <thead className="ui-th-table__head">
              <tr>
                <th className="ui-th-table__th w-64">{t("presetsPage.colVoice")}</th>
                <th className="ui-th-table__th w-40">{t("presetsPage.colAttributes")}</th>
                <th className="ui-th-table__th">{t("presetsPage.colTone")}</th>
                <th className="ui-th-table__th text-right">{t("presetsPage.colActions")}</th>
              </tr>
            </thead>
            <tbody className="ui-th-table__body">
              {filtered.map((row) => {
                const isPlaying = playingId === row.id
                const progress =
                  isPlaying && duration > 0 ? Math.min(1, Math.max(0, currentTime / duration)) : 0
                const langLabel = row.languages.map((l) => l.toUpperCase()).join(" / ")

                return (
                  <tr key={row.id} className="ui-th-table__row">
                    <td className="ui-th-table__td w-64">
                      <div className="flex items-center gap-3">
                        <IconButton
                          size="md"
                          variant={isPlaying ? "primary" : "secondary"}
                          pressed={isPlaying}
                          disabled={!row.preview_url}
                          label={t(isPlaying ? "assetsPage.pause" : "assetsPage.play")}
                          icon={
                            isPlaying ? <Pause className="size-4" /> : <Play className="size-4" />
                          }
                          onClick={() => void togglePlay(row)}
                          className="shrink-0"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate font-medium text-foreground">{row.name}</span>
                            <Badge
                              size="sm"
                              tone={row.source_kind === "minimax_clone" ? "info" : "neutral"}
                            >
                              {sourceBadgeLabel(row.source_kind)}
                            </Badge>
                          </div>
                          {isPlaying && duration > 0 ? (
                            <div className="mt-1.5 flex items-center gap-2">
                              <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
                                <div
                                  className="h-full rounded-full bg-foreground transition-[width] duration-150"
                                  style={{ width: `${Math.round(progress * 100)}%` }}
                                />
                              </div>
                              <span className="text-[11px] text-muted-foreground tabular-nums">
                                {formatDuration(currentTime)}/{formatDuration(duration)}
                              </span>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </td>
                    <td className="ui-th-table__td w-40 whitespace-nowrap">
                      <div className="flex flex-col items-start gap-1">
                        {row.gender ? (
                          <Badge size="sm">
                            {t(`voiceLibrary.categories.${row.gender.toLowerCase()}`, {
                              defaultValue: row.gender,
                            })}
                          </Badge>
                        ) : null}
                        {langLabel ? (
                          <span className="text-xs text-muted-foreground tabular-nums">
                            {langLabel}
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="ui-th-table__td max-w-md">
                      {row.description ? (
                        <p className="text-xs leading-5 text-muted-foreground">{row.description}</p>
                      ) : null}
                      {row.tone_tags.length > 0 ? (
                        <div className="mt-1.5 flex flex-wrap items-center gap-1">
                          {row.tone_tags.slice(0, 6).map((tag) => (
                            <span
                              key={`${row.id}:${tag}`}
                              className="inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-[11px] leading-4 text-muted-foreground"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </td>
                    <td className="ui-th-table__td whitespace-nowrap text-right">
                      <div className="inline-flex items-center justify-end gap-1.5">
                        {!workbench ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            icon={<Copy size={13} />}
                            onClick={() => handleCopyVoice(row)}
                          >
                            {t("common.copy")}
                          </Button>
                        ) : null}
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={workbench ? <MessageSquarePlus size={13} /> : <Sparkles size={13} />}
                          onClick={() => citeVoice(row)}
                        >
                          {workbench ? t("soundLab.cite") : t("presetsPage.usePreset")}
                        </Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {filtered.map((row) => {
            const isPlaying = playingId === row.id
            const progress =
              isPlaying && duration > 0 ? Math.min(1, Math.max(0, currentTime / duration)) : 0
            const langLabel = row.languages.map((l) => l.toUpperCase()).join(" / ")

            return (
              <article
                key={row.id}
                className="flex flex-col gap-3 rounded-xl border border-subtle bg-card p-4 text-foreground shadow-resting"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <IconButton
                      size="md"
                      variant={isPlaying ? "primary" : "secondary"}
                      pressed={isPlaying}
                      disabled={!row.preview_url}
                      label={t(isPlaying ? "assetsPage.pause" : "assetsPage.play")}
                      icon={isPlaying ? <Pause className="size-4" /> : <Play className="size-4" />}
                      onClick={() => void togglePlay(row)}
                      className="shrink-0"
                    />
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <h3 className="truncate text-sm font-medium text-foreground">
                          {row.name}
                        </h3>
                        <Badge size="sm" tone={row.source_kind === "minimax_clone" ? "info" : "neutral"}>
                          {sourceBadgeLabel(row.source_kind)}
                        </Badge>
                        {row.gender && (
                          <Badge size="sm" tone="neutral">
                            {t(`voiceLibrary.categories.${row.gender.toLowerCase()}`, {
                              defaultValue: row.gender,
                            })}
                          </Badge>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                        {[
                          langLabel || null,
                          isPlaying && duration > 0
                            ? `${formatDuration(currentTime)} / ${formatDuration(duration)}`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>
                  </div>
                </div>

                {row.description && (
                  <p className="text-xs leading-5 text-muted-foreground">{row.description}</p>
                )}

                <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
                  <div
                    className="h-full rounded-full bg-foreground transition-[width] duration-150"
                    style={{ width: `${Math.round(progress * 100)}%` }}
                  />
                </div>

                {row.tone_tags.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {row.tone_tags.slice(0, 6).map((tag) => (
                      <span
                        key={`${row.id}:${tag}`}
                        className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-[11px] leading-4 text-muted-foreground"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-auto flex items-center justify-end gap-1.5 border-t border-subtle pt-2.5">
                  {!workbench ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Copy size={13} />}
                      onClick={() => handleCopyVoice(row)}
                    >
                      {t("common.copy")}
                    </Button>
                  ) : null}
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={workbench ? <MessageSquarePlus size={13} /> : <Sparkles size={13} />}
                    onClick={() => citeVoice(row)}
                  >
                    {workbench ? t("soundLab.cite") : t("presetsPage.usePreset")}
                  </Button>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
