import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Pause, Play, Plus, Trash2 } from "lucide-react"

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { apiFetch } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { Template } from "@/routes/brand-template"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

const OFFICIAL_MOODS = ["calm", "uplifting", "corporate"] as const
type OfficialMood = (typeof OFFICIAL_MOODS)[number]
type MoodFilter = "all" | OfficialMood
type Source = "official" | "personal"

// Mirrors MusicTrackResponse in apps/api/app/models/schemas.py (see ADR-022).
type MusicTrackApi = {
  id: string
  user_id: string | null
  mood: string | null
  title: string
  duration_seconds: number | null
  source_note: string | null
  created_at: string
  url: string
}

function formatDuration(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "--:--"
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, "0")}`
}

/** Probe a local/blob URL's duration client-side (no server-side audio parsing). */
function probeDuration(url: string): Promise<number | null> {
  return new Promise((resolve) => {
    const probe = new Audio(url)
    probe.addEventListener("loadedmetadata", () => resolve(probe.duration))
    probe.addEventListener("error", () => resolve(null))
  })
}

export function MusicPanel({
  template,
  update,
}: {
  template: Template
  update: <K extends keyof Template>(key: K, value: Template[K]) => void
}) {
  const { t } = useTranslation()
  const [source, setSource] = useState<Source>("official")
  const [moodFilter, setMoodFilter] = useState<MoodFilter>("all")
  const [officialTracks, setOfficialTracks] = useState<MusicTrackApi[]>([])
  const [personalTracks, setPersonalTracks] = useState<MusicTrackApi[]>([])
  const [selectedPersonalId, setSelectedPersonalId] = useState<string | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const fetchOfficialTracks = useCallback(async () => {
    const res = await apiFetch("/api/v1/music?scope=official")
    if (res.ok) setOfficialTracks(await res.json())
  }, [])

  const fetchPersonalTracks = useCallback(async () => {
    const res = await apiFetch("/api/v1/music?scope=personal")
    if (res.ok) setPersonalTracks(await res.json())
  }, [])

  useEffect(() => {
    fetchOfficialTracks()
    fetchPersonalTracks()
  }, [fetchOfficialTracks, fetchPersonalTracks])

  const handleTogglePlay = (id: string, url: string) => {
    const audio = audioRef.current
    if (!audio) return
    if (playingId === id) {
      audio.pause()
      setPlayingId(null)
      return
    }
    audio.src = url
    audio.play().catch(() => {})
    setPlayingId(id)
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    setUploading(true)
    try {
      const objectUrl = URL.createObjectURL(file)
      const duration = await probeDuration(objectUrl)
      const title = file.name.replace(/\.[^/.]+$/, "")
      const formData = new FormData()
      formData.append("file", file)
      formData.append("title", title)
      formData.append("scope", "personal")
      if (duration != null) formData.append("duration_seconds", String(duration))
      const res = await apiFetch("/api/v1/music", { method: "POST", body: formData })
      if (!res.ok) throw new Error("Upload failed")
      await fetchPersonalTracks()
    } catch {
      // Best-effort MVP surface; the track list simply won't gain an entry.
    } finally {
      setUploading(false)
    }
  }

  const handleDeletePersonal = async (id: string) => {
    if (!confirm(t("brandTemplate.music.deleteConfirm"))) return
    const res = await apiFetch(`/api/v1/music/${id}`, { method: "DELETE" })
    if (res.ok) {
      if (selectedPersonalId === id) setSelectedPersonalId(null)
      await fetchPersonalTracks()
    }
  }

  const officialByMood = new Map(officialTracks.filter((t) => t.mood).map((t) => [t.mood, t]))
  const visibleMoods = OFFICIAL_MOODS.filter((m) => moodFilter === "all" || moodFilter === m)

  return (
    <div className="space-y-3">
      <ToggleGroup
        variant="outline"
        spacing={0}
        value={[source]}
        onValueChange={(v) => v[0] && setSource(v[0] as Source)}
        className="w-full"
      >
        <ToggleGroupItem value="official" className="flex-1 text-xs">
          {t("brandTemplate.music.source.official")}
        </ToggleGroupItem>
        <ToggleGroupItem value="personal" className="flex-1 text-xs">
          {t("brandTemplate.music.source.personal")}
        </ToggleGroupItem>
      </ToggleGroup>

      {source === "official" && (
        <div className="overflow-x-auto">
          <ToggleGroup
            variant="outline"
            spacing={0}
            value={[moodFilter]}
            onValueChange={(v) => v[0] && setMoodFilter(v[0] as MoodFilter)}
          >
            <ToggleGroupItem value="all" className="px-3 text-xs">
              {t("brandTemplate.music.moods.all")}
            </ToggleGroupItem>
            {OFFICIAL_MOODS.map((m) => (
              <ToggleGroupItem key={m} value={m} className="px-3 text-xs">
                {t(`brandTemplate.music.moods.${m}`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      )}

      <div className="space-y-1">
        {source === "official" ? (
          visibleMoods.map((mood) => {
            const track = officialByMood.get(mood)
            const url = track ? `${API_URL}${track.url}` : `${API_URL}/api/v1/music/${mood}`
            return (
              <TrackRow
                key={mood}
                name={track?.title ?? t(`brandTemplate.music.moods.${mood}`)}
                duration={track?.duration_seconds ?? null}
                sourceNote={track?.source_note ?? null}
                selected={template.musicMood === mood}
                playing={playingId === mood}
                onSelect={() => update("musicMood", mood)}
                onTogglePlay={() => handleTogglePlay(mood, url)}
              />
            )
          })
        ) : (
          <>
            <label
              className={cn(
                "flex h-11 cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-border text-sm text-muted-foreground transition-colors hover:bg-accent",
                uploading && "pointer-events-none opacity-60"
              )}
            >
              <Plus className="h-4 w-4" />
              {uploading ? t("brandTemplate.music.uploading") : t("brandTemplate.music.upload")}
              <input
                type="file"
                accept="audio/*"
                className="hidden"
                disabled={uploading}
                onChange={handleUpload}
              />
            </label>
            {personalTracks.map((tr) => (
              <div key={tr.id}>
                <TrackRow
                  name={tr.title}
                  duration={tr.duration_seconds}
                  sourceNote={tr.source_note}
                  selected={selectedPersonalId === tr.id}
                  playing={playingId === tr.id}
                  onSelect={() => setSelectedPersonalId(tr.id)}
                  onTogglePlay={() => handleTogglePlay(tr.id, `${API_URL}${tr.url}`)}
                  onDelete={() => handleDeletePersonal(tr.id)}
                />
                {selectedPersonalId === tr.id && (
                  <p className="px-2 pt-0.5 text-xs text-muted-foreground">
                    {t("brandTemplate.music.personalPreviewOnly")}
                  </p>
                )}
              </div>
            ))}
          </>
        )}
      </div>

      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} onEnded={() => setPlayingId(null)} className="hidden" />
    </div>
  )
}

function TrackRow({
  name,
  duration,
  sourceNote,
  selected,
  playing,
  onSelect,
  onTogglePlay,
  onDelete,
}: {
  name: string
  duration: number | null
  sourceNote: string | null
  selected: boolean
  playing: boolean
  onSelect: () => void
  onTogglePlay: () => void
  onDelete?: () => void
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md px-2 py-1.5 transition-colors",
        selected ? "bg-accent" : "hover:bg-accent/50"
      )}
    >
      <button
        type="button"
        onClick={onTogglePlay}
        aria-label={playing ? "Pause" : "Play"}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-muted"
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </button>
      <button
        type="button"
        onClick={onSelect}
        className="flex min-w-0 flex-1 flex-col items-start text-left"
      >
        <span className="w-full truncate text-sm">{name}</span>
        <span className="text-xs text-muted-foreground">
          {formatDuration(duration)} · {sourceNote || "—"}
        </span>
      </button>
      {onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          aria-label="Delete"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-destructive"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
