import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Pause, Play, Plus } from "lucide-react"

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { cn } from "@/lib/utils"
import type { Template } from "@/routes/brand-template"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

const OFFICIAL_MOODS = ["calm", "uplifting", "corporate"] as const
type OfficialMood = (typeof OFFICIAL_MOODS)[number]
type MoodFilter = "all" | OfficialMood
type Source = "official" | "personal"

type PersonalTrack = {
  id: string
  name: string
  url: string
  duration: number | null
}

function formatDuration(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "--:--"
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, "0")}`
}

function officialTrackUrl(mood: OfficialMood): string {
  return `${API_URL}/api/v1/music/${mood}`
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
  const [personalTracks, setPersonalTracks] = useState<PersonalTrack[]>([])
  const [selectedPersonalId, setSelectedPersonalId] = useState<string | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [officialDurations, setOfficialDurations] = useState<
    Partial<Record<OfficialMood, number | null>>
  >({})
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Lazily probe each built-in track's duration client-side (no backend
  // metadata exists yet — see docs/tasks/todo.md).
  useEffect(() => {
    OFFICIAL_MOODS.forEach((mood) => {
      const probe = new Audio(officialTrackUrl(mood))
      probe.preload = "metadata"
      probe.addEventListener("loadedmetadata", () => {
        setOfficialDurations((d) => ({ ...d, [mood]: probe.duration }))
      })
      probe.addEventListener("error", () => {
        setOfficialDurations((d) => ({ ...d, [mood]: null }))
      })
    })
  }, [])

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

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    const id = crypto.randomUUID()
    const url = URL.createObjectURL(file)
    const name = file.name.replace(/\.[^/.]+$/, "")
    setPersonalTracks((list) => [...list, { id, name, url, duration: null }])
    const probe = new Audio(url)
    probe.addEventListener("loadedmetadata", () => {
      setPersonalTracks((list) =>
        list.map((tr) => (tr.id === id ? { ...tr, duration: probe.duration } : tr))
      )
    })
  }

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
          visibleMoods.map((mood) => (
            <TrackRow
              key={mood}
              name={t(`brandTemplate.music.moods.${mood}`)}
              duration={officialDurations[mood] ?? null}
              selected={template.musicMood === mood}
              playing={playingId === mood}
              onSelect={() => update("musicMood", mood)}
              onTogglePlay={() => handleTogglePlay(mood, officialTrackUrl(mood))}
            />
          ))
        ) : (
          <>
            <label className="flex h-11 cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-border text-sm text-muted-foreground transition-colors hover:bg-accent">
              <Plus className="h-4 w-4" />
              {t("brandTemplate.music.upload")}
              <input type="file" accept="audio/*" className="hidden" onChange={handleUpload} />
            </label>
            {personalTracks.map((tr) => (
              <div key={tr.id}>
                <TrackRow
                  name={tr.name}
                  duration={tr.duration}
                  selected={selectedPersonalId === tr.id}
                  playing={playingId === tr.id}
                  onSelect={() => setSelectedPersonalId(tr.id)}
                  onTogglePlay={() => handleTogglePlay(tr.id, tr.url)}
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
  selected,
  playing,
  onSelect,
  onTogglePlay,
}: {
  name: string
  duration: number | null
  selected: boolean
  playing: boolean
  onSelect: () => void
  onTogglePlay: () => void
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
        <span className="text-xs text-muted-foreground">{formatDuration(duration)} · —</span>
      </button>
    </div>
  )
}
