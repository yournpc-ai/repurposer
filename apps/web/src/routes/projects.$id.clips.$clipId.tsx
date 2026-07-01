import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Player } from '@remotion/player'
import {
  Clip as ClipComposition,
  ASPECT_DIMENSIONS,
  COMPOSITION_FPS,
  removeRange,
  setTrim,
  sourceDuration,
  totalDurationSeconds,
  trimBounds,
  type CaptionCue,
  type ClipSpec,
} from '@repurposer/clip'
import { ArrowLeft, Download, FileText, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WORDS_PER_LINE = 7

// Caption target languages (European-market focus per product positioning).
const CAPTION_LANG_CODES = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const

interface Clip {
  id: string
  hook: string
  render_spec: ClipSpec | null
  render_status: string | null
  video_url: string | null
  srt_url: string | null
}

export const Route = createFileRoute('/projects/$id/clips/$clipId')({
  component: ClipEditorPage,
})

function withAbsoluteSource(spec: ClipSpec): ClipSpec {
  let next = spec
  const url = spec.source.url
  if (url && url.startsWith('/')) {
    next = { ...next, source: { ...next.source, url: API_URL + url } }
  }
  // stills: backing images are storage-relative too.
  const images = next.source.image_urls
  if (images && images.some((u) => u.startsWith('/'))) {
    next = {
      ...next,
      source: {
        ...next.source,
        image_urls: images.map((u) => (u.startsWith('/') ? API_URL + u : u)),
      },
    }
  }
  // Brand logo may also be a relative storage URL (external URLs are untouched).
  const logo = next.brand?.logo_url
  if (logo && logo.startsWith('/')) {
    next = { ...next, brand: { ...next.brand, logo_url: API_URL + logo } }
  }
  // Background music track is a storage-relative URL too.
  const track = next.music?.url
  if (track && track.startsWith('/')) {
    next = { ...next, music: { ...next.music, url: API_URL + track } }
  }
  // Dubbed-voice track is storage-relative too.
  if (next.dub?.url && next.dub.url.startsWith('/')) {
    next = { ...next, dub: { ...next.dub, url: API_URL + next.dub.url } }
  }
  return next
}

function toLines(cues: CaptionCue[]): { cue: CaptionCue; index: number }[][] {
  const lines: { cue: CaptionCue; index: number }[][] = []
  for (let i = 0; i < cues.length; i += WORDS_PER_LINE) {
    lines.push(cues.slice(i, i + WORDS_PER_LINE).map((cue, j) => ({ cue, index: i + j })))
  }
  return lines
}

function ClipEditorPage() {
  const { id, clipId } = Route.useParams()
  const { t } = useTranslation()

  const [clip, setClip] = useState<Clip | null>(null)
  const [spec, setSpec] = useState<ClipSpec | null>(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [translating, setTranslating] = useState(false)
  const [dubbing, setDubbing] = useState(false)
  const [error, setError] = useState('')
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const loadClip = () =>
    fetch(`${API_URL}/api/v1/clips/${clipId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('Clip not found'))))
      .then((c: Clip) => {
        setClip(c)
        setSpec((prev) => prev ?? c.render_spec)
        return c
      })

  useEffect(() => {
    loadClip().catch((e) => setError(e instanceof Error ? e.message : 'Failed to load clip'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clipId])

  // Poll render status while a render is in flight.
  const renderingRef = useRef(false)
  renderingRef.current = rendering
  useEffect(() => {
    if (!rendering) return
    const timer = setInterval(async () => {
      try {
        const c = await loadClip()
        if (c.render_status === 'completed' || c.render_status === 'failed') {
          setRendering(false)
          if (c.render_status === 'failed') setError(t('clipEditor.renderFailed'))
        }
      } catch {
        /* transient — keep polling */
      }
    }, 2500)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rendering, clipId])

  const previewSpec = useMemo(() => (spec ? withAbsoluteSource(spec) : null), [spec])
  const lines = spec ? toLines(spec.caption_track) : []

  const patchSpec = (patch: Partial<ClipSpec>) => {
    setSpec((prev) => (prev ? { ...prev, ...patch } : prev))
    setDirty(true)
  }

  const editWord = (index: number, text: string) => {
    setSpec((prev) =>
      prev
        ? { ...prev, caption_track: prev.caption_track.map((c, i) => (i === index ? { ...c, text } : c)) }
        : prev,
    )
    setDirty(true)
  }

  const deleteLine = (line: { cue: CaptionCue; index: number }[]) => {
    if (!spec || line.length === 0) return
    setSpec(removeRange(spec, line[0].cue.start, line[line.length - 1].cue.end))
    setDirty(true)
  }

  const save = async (): Promise<boolean> => {
    if (!spec) return false
    setSaving(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/v1/clips/${clipId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ render_spec: spec }),
      })
      if (!res.ok) throw new Error('Save failed')
      setDirty(false)
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
      return false
    } finally {
      setSaving(false)
    }
  }

  const exportVideo = async () => {
    // The render service renders the SAVED render_spec — persist edits first.
    if (dirty && !(await save())) return
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/v1/clips/${clipId}/render`, { method: 'POST' })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail || 'Render failed')
      }
      setRendering(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Render failed')
    }
  }

  const translateCaptions = async (lang: string) => {
    // The endpoint re-translates the PERSISTED caption_track — save edits first.
    if (!spec || lang === spec.target_language || translating) return
    if (dirty && !(await save())) return
    setTranslating(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/v1/clips/${clipId}/translate-captions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_language: lang }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail || 'Translate failed')
      }
      const c: Clip = await res.json()
      setClip(c)
      if (c.render_spec) setSpec(c.render_spec)
      setDirty(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Translate failed')
    } finally {
      setTranslating(false)
    }
  }

  const dubClip = async (lang: string) => {
    // Clones the speaker's voice from the project's audio/video and dubs the
    // (translated) captions into `lang`. Save pending edits first.
    if (!spec || dubbing) return
    if (dirty && !(await save())) return
    setDubbing(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/v1/clips/${clipId}/dub`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_language: lang }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail || 'Dub failed')
      }
      const c: Clip = await res.json()
      setClip(c)
      if (c.render_spec) setSpec(c.render_spec)
      setDirty(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Dub failed')
    } finally {
      setDubbing(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 p-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('clipEditor.back')}
            render={<Link to="/projects/$id" params={{ id }} />}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <h1 className="truncate text-xl font-bold tracking-tight">
            {clip?.hook || t('clipEditor.title')}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" className="h-9" disabled={!dirty || saving} onClick={save}>
            {saving ? t('common.saving') : t('clipEditor.save')}
          </Button>
          <Button className="h-9 gap-2" disabled={!spec || rendering} onClick={exportVideo}>
            {rendering ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {rendering ? t('clipEditor.rendering') : t('clipEditor.export')}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,360px)_1fr]">
        {/* Left: preview + rendered result */}
        <div className="space-y-4 self-start">
          <div className="overflow-hidden rounded-xl bg-black ring-1 ring-border shadow-xl">
            {mounted && previewSpec ? (
              <Player
                component={ClipComposition}
                inputProps={{ spec: previewSpec }}
                durationInFrames={Math.max(1, Math.round(totalDurationSeconds(previewSpec) * COMPOSITION_FPS))}
                fps={COMPOSITION_FPS}
                compositionWidth={ASPECT_DIMENSIONS[previewSpec.aspect].width}
                compositionHeight={ASPECT_DIMENSIONS[previewSpec.aspect].height}
                style={{ width: '100%', aspectRatio: previewSpec.aspect === '1:1' ? '1 / 1' : '9 / 16' }}
                controls
              />
            ) : (
              <div className="flex aspect-[9/16] items-center justify-center text-sm text-white/60">
                {clip && !spec ? t('clipEditor.noRenderSpec') : t('common.loading')}
              </div>
            )}
          </div>

          {clip?.video_url ? (
            <div className="space-y-2 rounded-xl bg-card p-3 ring-1 ring-border">
              <p className="text-xs font-medium text-muted-foreground">{t('clipEditor.rendered')}</p>
              <video src={`${API_URL}${clip.video_url}`} controls className="w-full rounded-md" />
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1 gap-1.5" render={<a href={`${API_URL}${clip.video_url}`} download />}>
                  <Download className="h-4 w-4" /> MP4
                </Button>
                {clip.srt_url ? (
                  <Button variant="outline" size="sm" className="flex-1 gap-1.5" render={<a href={`${API_URL}${clip.srt_url}`} download />}>
                    <FileText className="h-4 w-4" /> SRT
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        {/* Right: settings + transcript */}
        <div className="space-y-6">
          {spec ? (
            <div className="grid grid-cols-1 gap-4 rounded-xl bg-card p-6 ring-1 ring-border sm:grid-cols-2">
              <label className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{t('clipEditor.aspect')}</span>
                <Select value={spec.aspect} onValueChange={(v) => patchSpec({ aspect: (v as ClipSpec['aspect']) ?? '9:16' })}>
                  <SelectTrigger className="h-9 w-28 rounded-md text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="9:16">9:16</SelectItem>
                    <SelectItem value="1:1">1:1</SelectItem>
                  </SelectContent>
                </Select>
              </label>

              <label className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{t('clipEditor.captionStyle')}</span>
                <Select
                  value={spec.caption_style_preset}
                  onValueChange={(v) => patchSpec({ caption_style_preset: (v as ClipSpec['caption_style_preset']) ?? 'clean-bottom' })}
                >
                  <SelectTrigger className="h-9 w-36 rounded-md text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="clean-bottom">{t('clipEditor.styleClean')}</SelectItem>
                    <SelectItem value="karaoke-highlight">{t('clipEditor.styleKaraoke')}</SelectItem>
                  </SelectContent>
                </Select>
              </label>

              <label className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{t('clipEditor.captionLanguage')}</span>
                <Select
                  value={spec.target_language}
                  onValueChange={(v) => translateCaptions(v ?? spec.target_language)}
                  disabled={translating}
                >
                  <SelectTrigger className="h-9 w-36 rounded-md text-sm">
                    {translating ? (
                      <span className="flex items-center gap-2">
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                        {t('clipEditor.translating')}
                      </span>
                    ) : (
                      <SelectValue />
                    )}
                  </SelectTrigger>
                  <SelectContent>
                    {CAPTION_LANG_CODES.map((code) => (
                      <SelectItem key={code} value={code}>
                        {t(`languages.${code}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>

              <label className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{t('clipEditor.dubLanguage')}</span>
                <Select
                  value={spec.dub?.enabled ? spec.target_language : ''}
                  onValueChange={(v) => v && dubClip(v)}
                  disabled={dubbing || !spec.source.url}
                >
                  <SelectTrigger className="h-9 w-36 rounded-md text-sm">
                    {dubbing ? (
                      <span className="flex items-center gap-2">
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                        {t('clipEditor.dubbing')}
                      </span>
                    ) : (
                      <SelectValue placeholder={t('clipEditor.dubOff')} />
                    )}
                  </SelectTrigger>
                  <SelectContent>
                    {CAPTION_LANG_CODES.map((code) => (
                      <SelectItem key={code} value={code}>
                        {t(`languages.${code}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>

              <label className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{t('clipEditor.musicToggle')}</span>
                <Switch
                  checked={spec.music.enabled}
                  onCheckedChange={(v) => patchSpec({ music: { ...spec.music, enabled: v } })}
                />
              </label>

              <div className="flex items-center gap-2 sm:col-span-2">
                <Switch
                  checked={spec.title.enabled}
                  onCheckedChange={(v) => patchSpec({ title: { ...spec.title, enabled: v } })}
                  aria-label={t('clipEditor.titleToggle')}
                />
                <Input
                  value={spec.title.text}
                  onChange={(e) => patchSpec({ title: { ...spec.title, text: e.target.value } })}
                  placeholder={t('clipEditor.titlePlaceholder')}
                  className="h-9 flex-1"
                />
              </div>

              {/* Reframe via sliders (convention-aligned vs a hand-rolled drag box) */}
              <div className="space-y-3 sm:col-span-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{t('clipEditor.trim')}</span>
                  <span className="text-xs text-muted-foreground">
                    {trimBounds(spec)[0].toFixed(1)}s – {trimBounds(spec)[1].toFixed(1)}s
                  </span>
                </div>
                <Slider
                  min={0}
                  max={Math.ceil(sourceDuration(spec))}
                  step={0.1}
                  value={trimBounds(spec)}
                  onValueChange={(v) => {
                    const arr = Array.isArray(v) ? v : [v, v]
                    setSpec(setTrim(spec, arr[0], arr[1]))
                    setDirty(true)
                  }}
                />
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{t('clipEditor.reframePan')}</span>
                  <span className="text-xs text-muted-foreground">
                    {Math.round(spec.crop.x * 100)}%
                  </span>
                </div>
                <Slider
                  min={0}
                  max={100}
                  value={[Math.round(spec.crop.x * 100)]}
                  onValueChange={(v) =>
                    patchSpec({ crop: { ...spec.crop, x: (Array.isArray(v) ? v[0] : v) / 100 } })
                  }
                />
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{t('clipEditor.reframeZoom')}</span>
                  <span className="text-xs text-muted-foreground">{spec.crop.scale.toFixed(2)}×</span>
                </div>
                <Slider
                  min={100}
                  max={250}
                  value={[Math.round(spec.crop.scale * 100)]}
                  onValueChange={(v) =>
                    patchSpec({ crop: { ...spec.crop, scale: (Array.isArray(v) ? v[0] : v) / 100 } })
                  }
                />
              </div>
            </div>
          ) : null}

          <div className="space-y-3 rounded-xl bg-card p-6 ring-1 ring-border">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">{t('clipEditor.transcript')}</h2>
              <span className="text-xs text-muted-foreground">{t('clipEditor.transcriptHint')}</span>
            </div>

            {!spec ? (
              <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
            ) : lines.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('clipEditor.noCaptions')}</p>
            ) : (
              <div className="space-y-2">
                {lines.map((line, li) => (
                  <div key={li} className="group flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-accent/50">
                    <div className="flex flex-1 flex-wrap items-center gap-x-1.5 gap-y-1 text-sm leading-relaxed">
                      {line.map(({ cue, index }) =>
                        editingIdx === index ? (
                          <Input
                            key={index}
                            autoFocus
                            defaultValue={cue.text}
                            onBlur={(e) => {
                              editWord(index, e.target.value)
                              setEditingIdx(null)
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                            }}
                            className="h-7 w-28 px-2 py-0"
                          />
                        ) : (
                          <button
                            key={index}
                            type="button"
                            onClick={() => setEditingIdx(index)}
                            className="rounded px-0.5 hover:bg-primary/15"
                          >
                            {cue.text}
                          </button>
                        ),
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive"
                      aria-label={t('clipEditor.deleteLine')}
                      onClick={() => deleteLine(line)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
