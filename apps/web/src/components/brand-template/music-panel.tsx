import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Check, Loader2, Pause, Play, Wand2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { apiFetch } from "@/lib/api"

/** Mirrors the backend MusicResponse (apps/api/app/models/schemas.py). */
export interface MusicPiece {
  id: string
  mood: string
  title: string
  ext: string
  url: string
  size_bytes: number
  duration_seconds: number | null
  prompt: string | null
  model: string | null
  license: string | null
  source_url: string | null
  attribution: string | null
  is_public: boolean
  created_at: string
}

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

function absoluteUrl(url: string): string {
  return url.startsWith("/") ? API_URL + url : url
}

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return "--:--"
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, "0")}`
}

/**
 * Music library panel for the brand template's Music tab: lists available
 * pieces (public + the caller's own), lets the user preview/select a default
 * and generate a new one from a prompt. Mirrors docs/MUSIC_ARCHITECTURE.md §10.1.
 */
export function MusicPanel({
  enabled,
  onEnabledChange,
  musicId,
  onSelect,
  gainDb,
  onGainChange,
}: {
  enabled: boolean
  onEnabledChange: (v: boolean) => void
  musicId: string | null
  onSelect: (id: string | null) => void
  gainDb: number
  onGainChange: (v: number) => void
}) {
  const { t } = useTranslation()
  const [pieces, setPieces] = useState<MusicPiece[]>([])
  const [loading, setLoading] = useState(true)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [prompt, setPrompt] = useState("")
  const [title, setTitle] = useState("")
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState("")
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const loadPieces = async () => {
    try {
      const res = await apiFetch("/api/v1/music")
      if (!res.ok) return
      const list: MusicPiece[] = await res.json()
      setPieces(list)
    } catch {
      /* offline — keep whatever we had */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadPieces()
    return () => {
      audioRef.current?.pause()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const togglePreview = (piece: MusicPiece) => {
    if (playingId === piece.id) {
      audioRef.current?.pause()
      setPlayingId(null)
      return
    }
    audioRef.current?.pause()
    const audio = new Audio(absoluteUrl(piece.url))
    audio.volume = 0.7
    audio.onended = () => setPlayingId(null)
    audioRef.current = audio
    setPlayingId(piece.id)
    void audio.play().catch(() => setPlayingId(null))
  }

  const generate = async () => {
    if (!prompt.trim() || generating) return
    setGenerating(true)
    setError("")
    try {
      const body: { prompt: string; title?: string } = { prompt: prompt.trim() }
      if (title.trim()) body.title = title.trim()
      const res = await apiFetch("/api/v1/music/generate", {
        method: "POST",
        body,
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail || t("brandTemplate.music.generateFailed"))
      }
      const piece: MusicPiece = await res.json()
      setPieces((prev) => [piece, ...prev])
      onSelect(piece.id)
      setPrompt("")
      setTitle("")
    } catch (e) {
      setError(e instanceof Error ? e.message : t("brandTemplate.music.generateFailed"))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-4">
      <label className="flex items-center justify-between">
        <span className="text-sm">{t("brandTemplate.music.enable")}</span>
        <Switch checked={enabled} onCheckedChange={onEnabledChange} />
      </label>

      {enabled ? (
        <>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{t("brandTemplate.music.gain")}</span>
              <span>{gainDb.toFixed(0)} dB</span>
            </div>
            <Slider
              min={-30}
              max={0}
              step={1}
              value={[gainDb]}
              onValueChange={(v) => onGainChange(Array.isArray(v) ? v[0] : v)}
            />
          </div>

          <div className="space-y-1.5">
            <p className="px-0.5 text-xs text-muted-foreground">
              {t("brandTemplate.music.library")}
            </p>
            {loading ? (
              <div className="flex items-center justify-center py-6 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            ) : pieces.length === 0 ? (
              <p className="py-3 text-center text-xs text-muted-foreground">
                {t("brandTemplate.music.empty")}
              </p>
            ) : (
              <div className="space-y-1">
                {pieces.map((piece) => (
                  <div
                    key={piece.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => onSelect(piece.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") onSelect(piece.id)
                    }}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-accent/50"
                  >
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0"
                      aria-label={
                        playingId === piece.id
                          ? t("brandTemplate.music.pause")
                          : t("brandTemplate.music.play")
                      }
                      onClick={(e) => {
                        e.stopPropagation()
                        togglePreview(piece)
                      }}
                    >
                      {playingId === piece.id ? (
                        <Pause className="h-3.5 w-3.5" />
                      ) : (
                        <Play className="h-3.5 w-3.5" />
                      )}
                    </Button>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{piece.title}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {t(`brandTemplate.music.moods.${piece.mood}`, piece.mood)} ·{" "}
                        {formatDuration(piece.duration_seconds)}
                      </p>
                    </div>
                    {musicId === piece.id ? (
                      <Check className="h-4 w-4 shrink-0 text-primary" />
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <p className="px-0.5 text-xs text-muted-foreground">
              {t("brandTemplate.music.generate")}
            </p>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("brandTemplate.music.titlePlaceholder")}
              className="h-9"
              disabled={generating}
            />
            <div className="flex items-center gap-2">
              <Input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={t("brandTemplate.music.generatePrompt")}
                className="h-9 flex-1"
                disabled={generating}
              />
              <Button
                variant="outline"
                size="icon"
                className="h-9 w-9 shrink-0"
                aria-label={t("brandTemplate.music.generate")}
                disabled={!prompt.trim() || generating}
                onClick={generate}
              >
                {generating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="h-4 w-4" />
                )}
              </Button>
            </div>
            {error ? <p className="text-xs text-destructive">{error}</p> : null}
          </div>
        </>
      ) : null}
    </div>
  )
}
