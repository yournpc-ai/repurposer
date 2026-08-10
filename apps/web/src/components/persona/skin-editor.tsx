import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Player } from "@remotion/player"
import {
  Clip as ClipComposition,
  ASPECT_DIMENSIONS,
  CAPTION_PRESETS,
  COMPOSITION_FPS,
  totalDurationSeconds,
  type CaptionCue,
  type CaptionStylePreset,
  type ClipBrand,
  type ClipSpec,
  type IntroOutroCard,
} from "@repurposer/clip"
import { Check, RotateCcw, Save, Upload, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"
import { MusicPanel } from "@/components/persona/music-panel"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

// ---------------------------------------------------------------------------
// Skin block (persona.brand) — skin keys only. Craft/format keys (aspect /
// fillMode / captionEnabled / filler) are task-book defaults (NAMING N-28)
// and never appear here; the preview pins them to the task-book defaults.
// ---------------------------------------------------------------------------

const FONTS = [
  { value: "lilita", label: "Lilita One", family: "'Lilita One', system-ui, sans-serif" },
  { value: "inter", label: "Inter", family: "'Inter', system-ui, sans-serif" },
  { value: "playfair", label: "Playfair Display", family: "'Playfair Display', serif" },
  { value: "source-serif", label: "Source Serif 4", family: "'Source Serif 4', serif" },
]

// Quick-pick presets; both size and color also accept any free-form value.
const CAPTION_COLORS = ["#ffffff", "#facc15", "#22c55e", "#ec4899", "#6366f1"]
// Caption styles come from the catalog (@repurposer/clip captions.ts) — a
// new registered preset appears here automatically.
const CAPTION_STYLES = Object.keys(CAPTION_PRESETS) as CaptionStylePreset[]

/** Normalized center point [0,1] (matches @repurposer/clip Point). */
type Pt = { x: number; y: number }

type IntroOutroKind = "text" | "image" | "video"

export type SkinBlock = {
  captionFont: string
  captionSize: number
  captionColor: string
  captionPosition: Pt
  captionStylePreset: CaptionStylePreset
  titleEnabled: boolean
  titleSize: number
  titlePosition: Pt
  introEnabled: boolean
  introKind: IntroOutroKind
  introText: string
  introMediaUrl: string | null
  introDurationSeconds: number
  outroEnabled: boolean
  outroKind: IntroOutroKind
  outroText: string
  outroMediaUrl: string | null
  outroDurationSeconds: number
  musicEnabled: boolean
  musicId: string | null
  musicGainDb: number
}

/** Mirrors the skin keys of the backend DEFAULT_BRAND_CONFIG (memory/brand.py). */
const DEFAULT_SKIN: SkinBlock = {
  captionFont: "lilita",
  captionSize: 44,
  captionColor: "#facc15",
  captionPosition: { x: 0.5, y: 0.84 },
  captionStylePreset: "clean-bottom",
  titleEnabled: true,
  titleSize: 58,
  titlePosition: { x: 0.5, y: 0.12 },
  introEnabled: false,
  introKind: "image",
  introText: "",
  introMediaUrl: null,
  introDurationSeconds: 2,
  outroEnabled: false,
  outroKind: "image",
  outroText: "",
  outroMediaUrl: null,
  outroDurationSeconds: 2,
  musicEnabled: false,
  musicId: null,
  musicGainDb: -18,
}

/** Merge the persona's saved skin (partial, camelCase) over the defaults. */
function mergeSkin(brand: Record<string, unknown> | null): SkinBlock {
  if (!brand) return DEFAULT_SKIN
  const merged = { ...DEFAULT_SKIN }
  for (const key of Object.keys(DEFAULT_SKIN) as (keyof SkinBlock)[]) {
    const value = brand[key]
    if (value !== undefined && value !== null) {
      ;(merged as Record<string, unknown>)[key] = value
    }
  }
  return merged
}

// Fixed LATIN samples so the brand fonts (Lilita/Inter/Playfair/Source Serif —
// all latin) actually render in the preview. Real text comes from the talk's
// ASR at generation time; these only demonstrate the *style*.
const DEMO_CAPTION = "Your captions show up here"
const DEMO_TITLE = "The hook line"

// ---------------------------------------------------------------------------
// Skin -> clip-spec (live preview uses the SAME <Clip> as the real render, so
// the preview is pixel-identical to generated output; craft keys pin to the
// task-book defaults — 9:16 / fill / captions on).
// ---------------------------------------------------------------------------

function introOutroCard(
  enabled: boolean,
  kind: IntroOutroKind,
  text: string,
  mediaUrl: string | null,
  durationSeconds: number
): IntroOutroCard | null {
  if (!enabled) return null
  if (kind === "text") {
    return text.trim() ? { kind, text: text.trim(), duration_seconds: durationSeconds } : null
  }
  if (!mediaUrl) return null
  // Preview-only: the <Player> renders in the browser, so relative storage-seam
  // URLs need the API origin (mirrors the music.url handling below).
  const url = mediaUrl.startsWith("/") ? API_URL + mediaUrl : mediaUrl
  return { kind, media_url: url, duration_seconds: durationSeconds }
}

function skinToBrand(skin: SkinBlock): ClipBrand {
  return {
    caption_color: skin.captionColor || null,
    caption_size: skin.captionSize || null,
    caption_font: skin.captionFont || null,
    intro: introOutroCard(
      skin.introEnabled,
      skin.introKind,
      skin.introText,
      skin.introMediaUrl,
      skin.introDurationSeconds
    ),
    outro: introOutroCard(
      skin.outroEnabled,
      skin.outroKind,
      skin.outroText,
      skin.outroMediaUrl,
      skin.outroDurationSeconds
    ),
    fill_mode: "fill",
    caption_enabled: true,
  }
}

function buildPreviewSpec(skin: SkinBlock): ClipSpec {
  const words = DEMO_CAPTION.split(/\s+/).filter(Boolean)
  const per = words.length ? Math.max(0.35, 3 / words.length) : 0.5
  const caption_track: CaptionCue[] = words.map((w, i) => ({
    start: i * per,
    end: (i + 1) * per,
    text: w,
    lang: "en",
  }))
  const end = Math.max(1, words.length * per)
  return {
    source: { asset_id: "preview", kind: "stills", url: "", image_urls: [], fps: 30 },
    aspect: "9:16",
    segments: [{ start: 0, end, hidden: false }],
    crop: { x: 0.5, y: 0.5, scale: 1 },
    caption_track,
    caption_style_preset: skin.captionStylePreset,
    caption_position: skin.captionPosition,
    caption_enabled: true,
    title: {
      text: DEMO_TITLE,
      enabled: skin.titleEnabled,
      size: skin.titleSize,
      position: skin.titlePosition,
    },
    // Preview plays the selected music piece via its real stream URL so the
    // skin preview matches the actual render (see memory/brand.py
    // music_from_block).
    music: skin.musicId
      ? {
          music_id: skin.musicId,
          url: `${API_URL}/api/v1/music/${skin.musicId}/stream`,
          enabled: skin.musicEnabled,
          gain_db: skin.musicGainDb,
        }
      : { music_id: null, url: null, enabled: false, gain_db: skin.musicGainDb },
    brand: skinToBrand(skin),
    brand_ref: null,
    target_language: "en",
  }
}

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

/** Clamp a normalized coord into the safe zone [0.05, 0.95]. */
const clampSafe = (v: number) => Math.min(0.95, Math.max(0.05, v))

// Fixed relative width of a title/caption box — matches the renderer's own
// fixed 84%-of-frame text box width (see @repurposer/clip pointStyle()), so
// the hover/resize hit-box lines up with where the text actually renders.
const MARKER_WIDTH_PERCENT = 84

/**
 * A draggable + resizable overlay marker over a title/caption position.
 * Shows its bordered box + corner handles either when the caller forces it
 * via `visible` or when the user hovers the marker's own footprint directly.
 *
 * Resize scales `sizeValue` (font px in composition space) uniformly from
 * corner-drag distance; the renderer only has a single font-size field, not
 * independent box dimensions (ADR-016: no free-form layout), so this is the
 * honest mapping for "resize" rather than a fake independent width/height.
 */
function DraggableMarker({
  point,
  label,
  containerRef,
  sizeValue,
  compositionHeight,
  minSize = 16,
  maxSize = 140,
  onChange,
  onSizeChange,
}: {
  point: Pt
  label: string
  containerRef: React.RefObject<HTMLDivElement | null>
  sizeValue: number
  compositionHeight: number
  minSize?: number
  maxSize?: number
  onChange: (p: Pt) => void
  onSizeChange: (size: number) => void
}) {
  const [shown, setShown] = useState(false)

  const onDown = (e: React.PointerEvent) => {
    e.preventDefault()
    const move = (ev: PointerEvent) => {
      const el = containerRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      onChange({
        x: clampSafe((ev.clientX - r.left) / r.width),
        y: clampSafe((ev.clientY - r.top) / r.height),
      })
    }
    const up = () => {
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", up)
    }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  const onResizeDown = (e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const el = containerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const centerX = r.left + point.x * r.width
    const centerY = r.top + point.y * r.height
    const startDist = Math.hypot(e.clientX - centerX, e.clientY - centerY) || 1
    const startSize = sizeValue
    const move = (ev: PointerEvent) => {
      const dist = Math.hypot(ev.clientX - centerX, ev.clientY - centerY) || 1
      const next = Math.round((startSize * dist) / startDist)
      onSizeChange(Math.min(maxSize, Math.max(minSize, next)))
    }
    const up = () => {
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", up)
    }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
  }

  // Box height as a percentage of the frame, derived from the font size in
  // composition px (same normalized space as position) — an honest
  // approximation of a ~2-line text block, not a pixel-exact text bound.
  const heightPercent = Math.min(30, Math.max(6, (sizeValue / compositionHeight) * 100 * 2.4))

  return (
    <div
      onPointerDown={onDown}
      onMouseEnter={() => setShown(true)}
      onMouseLeave={() => setShown(false)}
      style={{
        position: "absolute",
        left: `${point.x * 100}%`,
        top: `${point.y * 100}%`,
        transform: "translate(-50%, -50%)",
        width: `${MARKER_WIDTH_PERCENT}%`,
        height: `${heightPercent}%`,
        pointerEvents: "auto",
        cursor: "move",
      }}
    >
      {shown && (
        <>
          <div className="pointer-events-none absolute inset-0 rounded-sm border border-dashed border-white/80" />
          <span className="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 select-none whitespace-nowrap rounded-md border border-dashed border-white/70 bg-black/50 px-2 py-1 text-[10px] font-medium text-white shadow">
            {label}
          </span>
          {(["nw", "ne", "sw", "se"] as const).map((corner) => (
            <div
              key={corner}
              onPointerDown={onResizeDown}
              className="absolute h-2.5 w-2.5 rounded-sm border border-white bg-primary shadow"
              style={{
                cursor: corner === "nw" || corner === "se" ? "nwse-resize" : "nesw-resize",
                top: corner.includes("n") ? -5 : undefined,
                bottom: corner.includes("s") ? -5 : undefined,
                left: corner.includes("w") ? -5 : undefined,
                right: corner.includes("e") ? -5 : undefined,
              }}
            />
          ))}
        </>
      )}
    </div>
  )
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] font-medium text-meta">{children}</p>
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  )
}

/** Free-form font-size control: drag the slider or type an exact value. */
function SizeControl({
  value,
  onChange,
  min = 16,
  max = 120,
}: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
}) {
  return (
    <div className="flex items-center gap-3">
      <Slider
        min={min}
        max={max}
        step={1}
        value={[value]}
        onValueChange={(v) => onChange(Array.isArray(v) ? v[0] : v)}
        className="flex-1"
      />
      <Input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value) || value)}
        className="h-9 w-16 shrink-0 text-center"
      />
    </div>
  )
}

/** Upload + preview for an intro/outro image or video card. */
function MediaUploadField({
  personaId,
  kind,
  url,
  onUploaded,
  onClear,
}: {
  personaId: string
  kind: "image" | "video"
  url: string | null
  onUploaded: (url: string) => void
  onClear: () => void
}) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [uploading, setUploading] = useState(false)

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    setUploading(true)
    try {
      const urlRes = await apiFetch(`/api/v1/personas/${personaId}/media/upload-url`, {
        method: "POST",
        body: {
          filename: file.name,
          content_type: file.type || undefined,
        },
      })
      if (!urlRes.ok) throw new Error("Failed to get upload URL")
      const { key, upload_url } = (await urlRes.json()) as {
        key: string
        upload_url: string
      }

      const putRes = await fetch(upload_url, {
        method: "PUT",
        body: file,
        headers: file.type ? { "Content-Type": file.type } : {},
      })
      if (!putRes.ok) throw new Error("Upload failed")

      const res = await apiFetch(`/api/v1/personas/${personaId}/media`, {
        method: "POST",
        body: { key },
      })
      if (res.ok) {
        const data = (await res.json()) as { url: string }
        onUploaded(data.url)
      }
    } finally {
      setUploading(false)
    }
  }

  const resolvedUrl = url ? (url.startsWith("/") ? API_URL + url : url) : null

  return (
    <div className="space-y-1.5">
      <input
        ref={inputRef}
        type="file"
        accept={kind === "image" ? "image/*" : "video/*"}
        className="hidden"
        onChange={handleChange}
      />
      {resolvedUrl ? (
        <div className="relative overflow-hidden rounded-md">
          {kind === "image" ? (
            <img src={resolvedUrl} className="h-28 w-full object-cover" alt="" />
          ) : (
            <video src={resolvedUrl} className="h-28 w-full object-cover" muted loop autoPlay />
          )}
          <div className="absolute right-1.5 top-1.5 flex gap-1">
            <Button
              type="button"
              size="icon"
              variant="secondary"
              className="h-6 w-6 rounded-md"
              onClick={() => inputRef.current?.click()}
            >
              <Upload className="h-3 w-3" />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="secondary"
              className="h-6 w-6 rounded-md"
              onClick={onClear}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="flex h-20 w-full flex-col items-center justify-center gap-1 rounded-md border border-dashed text-muted-foreground transition-colors hover:bg-muted"
        >
          <Upload className="h-4 w-4" />
          <span className="text-xs">
            {uploading
              ? t("common.loading")
              : t(`personaDetail.skin.introOutro.upload${kind === "image" ? "Image" : "Video"}`)}
          </span>
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------

export function SkinEditor({
  personaId,
  brand,
  onSaved,
}: {
  personaId: string
  brand: Record<string, unknown> | null
  onSaved: (brand: Record<string, unknown> | null) => void
}) {
  const { t } = useTranslation()

  const [skin, setSkin] = useState<SkinBlock>(() => mergeSkin(brand))
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [mounted, setMounted] = useState(false)

  // Remotion <Player> is client-only (SSR would hydration-mismatch).
  useEffect(() => setMounted(true), [])

  const update = <K extends keyof SkinBlock>(key: K, value: SkinBlock[K]) => {
    setSkin((s) => ({ ...s, [key]: value }))
    setDirty(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await apiFetch(`/api/v1/personas/${personaId}`, {
        method: "PUT",
        body: { brand: skin },
        toast: t("personaDetail.skin.msgSaved"),
      })
      if (res.ok) {
        setDirty(false)
        onSaved(skin)
      }
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    setSaving(true)
    try {
      const res = await apiFetch(`/api/v1/personas/${personaId}`, {
        method: "PUT",
        body: { brand: null },
        toast: t("personaDetail.skin.msgReset"),
      })
      if (res.ok) {
        setSkin(DEFAULT_SKIN)
        setDirty(false)
        onSaved(null)
      }
    } finally {
      setSaving(false)
    }
  }

  const previewSpec = useMemo(() => buildPreviewSpec(skin), [skin])
  const previewRef = useRef<HTMLDivElement | null>(null)

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto]">
      {/* Settings — single column, grouped (craft keys are task-book defaults
          and intentionally absent, NAMING N-28) */}
      <Card className="ring-0 edge-glow">
        <CardHeader>
          <CardTitle>{t("personaDetail.skin.title")}</CardTitle>
          <CardDescription>{t("personaDetail.skin.desc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <section className="space-y-4">
            <GroupLabel>{t("personaDetail.skin.groups.caption")}</GroupLabel>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("personaDetail.skin.caption.font")}>
                <Select
                  value={skin.captionFont}
                  onValueChange={(v) => update("captionFont", v ?? "inter")}
                >
                  <SelectTrigger className="h-9 w-full rounded-md text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FONTS.map((f) => (
                      <SelectItem key={f.value} value={f.value}>
                        {f.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label={t("personaDetail.skin.caption.style")}>
                <Select
                  value={skin.captionStylePreset}
                  onValueChange={(v) =>
                    v && update("captionStylePreset", v as CaptionStylePreset)
                  }
                >
                  <SelectTrigger className="h-9 w-full rounded-md text-sm">
                    <SelectValue>
                      {(value: CaptionStylePreset) => t(`captionPresets.${value}`)}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {CAPTION_STYLES.map((p) => (
                      <SelectItem key={p} value={p}>
                        {t(`captionPresets.${p}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>
            <Field label={t("personaDetail.skin.caption.size")}>
              <SizeControl
                value={skin.captionSize}
                onChange={(v) => update("captionSize", v)}
              />
            </Field>
            <Field label={t("personaDetail.skin.caption.color")}>
              <div className="flex items-center gap-2">
                {CAPTION_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    aria-label={c}
                    aria-pressed={skin.captionColor === c}
                    onClick={() => update("captionColor", c)}
                    style={{ backgroundColor: c }}
                    className={cn(
                      "h-7 w-7 rounded-md ring-2 ring-offset-2 ring-offset-card transition-all focus-visible:outline-none focus-visible:ring-primary",
                      skin.captionColor === c ? "ring-primary" : "ring-transparent"
                    )}
                  />
                ))}
                <label
                  className={cn(
                    "relative flex h-7 w-7 cursor-pointer items-center justify-center rounded-md ring-2 ring-offset-2 ring-offset-card transition-all focus-within:ring-primary",
                    CAPTION_COLORS.includes(skin.captionColor)
                      ? "ring-transparent"
                      : "ring-primary"
                  )}
                  style={{
                    background:
                      "conic-gradient(from 0deg, #ef4444, #f59e0b, #22c55e, #3b82f6, #a855f7, #ef4444)",
                  }}
                  aria-label={t("personaDetail.skin.caption.customColor")}
                >
                  <input
                    type="color"
                    value={skin.captionColor}
                    onChange={(e) => update("captionColor", e.target.value)}
                    className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  />
                </label>
              </div>
              <Input
                value={skin.captionColor}
                onChange={(e) => update("captionColor", e.target.value)}
                placeholder="#ffffff"
                className="mt-2 h-8 font-mono text-xs"
              />
            </Field>
          </section>

          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <GroupLabel>{t("personaDetail.skin.groups.title")}</GroupLabel>
              <Switch
                checked={skin.titleEnabled}
                onCheckedChange={(v) => update("titleEnabled", v)}
              />
            </div>
            {skin.titleEnabled && (
              <>
                <Field label={t("personaDetail.skin.titleCard.size")}>
                  <SizeControl
                    value={skin.titleSize}
                    onChange={(v) => update("titleSize", v)}
                  />
                </Field>
                <p className="text-xs text-muted-foreground">
                  {t("personaDetail.skin.titleCard.hint")}
                </p>
              </>
            )}
          </section>

          {(["intro", "outro"] as const).map((slot) => {
            const enabledKey = slot === "intro" ? "introEnabled" : "outroEnabled"
            const kindKey = slot === "intro" ? "introKind" : "outroKind"
            const textKey = slot === "intro" ? "introText" : "outroText"
            const mediaKey = slot === "intro" ? "introMediaUrl" : "outroMediaUrl"
            const durationKey =
              slot === "intro" ? "introDurationSeconds" : "outroDurationSeconds"
            return (
              <section key={slot} className="space-y-4">
                <div className="flex items-center justify-between">
                  <GroupLabel>{t(`personaDetail.skin.groups.${slot}`)}</GroupLabel>
                  <Switch
                    checked={skin[enabledKey]}
                    onCheckedChange={(v) => update(enabledKey, v)}
                  />
                </div>
                {skin[enabledKey] && (
                  <>
                    <Field label={t("personaDetail.skin.introOutro.type")}>
                      <ToggleGroup
                        variant="outline"
                        spacing={0}
                        value={[skin[kindKey]]}
                        onValueChange={(v) =>
                          v[0] && update(kindKey, v[0] as IntroOutroKind)
                        }
                        className="w-full"
                      >
                        {(["text", "image", "video"] as const).map((k) => (
                          <ToggleGroupItem key={k} value={k} className="flex-1 text-xs">
                            {t(`personaDetail.skin.introOutro.kinds.${k}`)}
                          </ToggleGroupItem>
                        ))}
                      </ToggleGroup>
                    </Field>
                    {skin[kindKey] === "text" ? (
                      <Field label={t(`personaDetail.skin.introOutro.${textKey}`)}>
                        <Input
                          value={skin[textKey]}
                          onChange={(e) => update(textKey, e.target.value)}
                          placeholder={t(
                            `personaDetail.skin.introOutro.${slot}Placeholder`
                          )}
                        />
                      </Field>
                    ) : (
                      <MediaUploadField
                        personaId={personaId}
                        kind={skin[kindKey]}
                        url={skin[mediaKey]}
                        onUploaded={(url) => update(mediaKey, url)}
                        onClear={() => update(mediaKey, null)}
                      />
                    )}
                    {skin[kindKey] !== "video" && (
                      <Field label={t("personaDetail.skin.introOutro.duration")}>
                        <Input
                          type="number"
                          min={0.5}
                          max={10}
                          step={0.5}
                          value={skin[durationKey]}
                          onChange={(e) =>
                            update(durationKey, Number(e.target.value) || 2)
                          }
                        />
                      </Field>
                    )}
                  </>
                )}
              </section>
            )
          })}

          <section className="space-y-4">
            <GroupLabel>{t("personaDetail.skin.groups.music")}</GroupLabel>
            <MusicPanel
              enabled={skin.musicEnabled}
              onEnabledChange={(v) => update("musicEnabled", v)}
              musicId={skin.musicId}
              onSelect={(id) => update("musicId", id)}
              gainDb={skin.musicGainDb}
              onGainChange={(v) => update("musicGainDb", v)}
            />
          </section>

          <div className="flex items-center justify-end gap-2">
            <Button
              variant="ghost"
              onClick={handleReset}
              disabled={saving || brand === null}
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              {t("personaDetail.skin.reset")}
            </Button>
            <Button onClick={handleSave} disabled={saving || !dirty}>
              {dirty ? (
                <Save className="mr-2 h-4 w-4" />
              ) : (
                <Check className="mr-2 h-4 w-4" />
              )}
              {saving ? t("common.saving") : t("personaDetail.skin.save")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Preview — the REAL <Clip>, with draggable overlay markers */}
      <div className="flex flex-col items-center gap-2 lg:pt-2">
        <span className="text-xs text-muted-foreground">
          {t("personaDetail.skin.preview.demo")}
        </span>
        <div className="flex w-full max-w-[280px] flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-lg bg-muted px-3 py-2 text-[11px] text-muted-foreground">
          <span className="font-medium text-foreground">
            {FONTS.find((f) => f.value === skin.captionFont)?.label ?? skin.captionFont}
          </span>
          <span aria-hidden>·</span>
          <span className="inline-flex items-center gap-1">
            <span
              className="h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: skin.captionColor }}
            />
            {skin.captionSize}px
          </span>
          <span aria-hidden>·</span>
          <span>
            {skin.musicEnabled
              ? t("personaDetail.skin.preview.musicOn")
              : t("personaDetail.skin.preview.musicOff")}
          </span>
          {skin.introEnabled ? (
            <>
              <span aria-hidden>·</span>
              <span>{t("personaDetail.skin.groups.intro")}</span>
            </>
          ) : null}
          {skin.outroEnabled ? (
            <>
              <span aria-hidden>·</span>
              <span>{t("personaDetail.skin.groups.outro")}</span>
            </>
          ) : null}
        </div>
        <div
          ref={previewRef}
          className="relative h-[480px] rounded-2xl shadow-lg ring-1 ring-foreground/10 md:h-[560px]"
          style={{ aspectRatio: "9 / 16" }}
        >
          {mounted ? (
            <Player
              component={ClipComposition}
              inputProps={{ spec: previewSpec }}
              durationInFrames={Math.max(
                1,
                Math.round(totalDurationSeconds(previewSpec) * COMPOSITION_FPS)
              )}
              fps={COMPOSITION_FPS}
              compositionWidth={ASPECT_DIMENSIONS["9:16"].width}
              compositionHeight={ASPECT_DIMENSIONS["9:16"].height}
              style={{
                height: "100%",
                width: "100%",
                borderRadius: 16,
                overflow: "hidden",
              }}
              controls
              autoPlay
            />
          ) : (
            <div className="h-full w-full rounded-2xl bg-muted" />
          )}

          {/* Drag overlay (transparent; only markers capture pointer) */}
          {mounted ? (
            <div className="absolute inset-0" style={{ pointerEvents: "none" }}>
              {/* safe zone + center crosshair */}
              <div
                className="absolute rounded-lg"
                style={{ inset: "5%", border: "1px dashed rgba(255,255,255,0.25)" }}
              />
              <div
                className="absolute left-1/2 top-0 bottom-0"
                style={{ width: 1, background: "rgba(255,255,255,0.12)" }}
              />
              <div
                className="absolute left-0 right-0 top-1/2"
                style={{ height: 1, background: "rgba(255,255,255,0.12)" }}
              />
              {skin.titleEnabled && (
                <DraggableMarker
                  point={skin.titlePosition}
                  label={t("personaDetail.skin.groups.title")}
                  containerRef={previewRef}
                  sizeValue={skin.titleSize}
                  compositionHeight={ASPECT_DIMENSIONS["9:16"].height}
                  onChange={(p) => update("titlePosition", p)}
                  onSizeChange={(s) => update("titleSize", s)}
                />
              )}
              <DraggableMarker
                point={skin.captionPosition}
                label={t("personaDetail.skin.groups.caption")}
                containerRef={previewRef}
                sizeValue={skin.captionSize}
                compositionHeight={ASPECT_DIMENSIONS["9:16"].height}
                onChange={(p) => update("captionPosition", p)}
                onSizeChange={(s) => update("captionSize", s)}
              />
            </div>
          ) : null}
        </div>
        <p className="max-w-[280px] text-center text-xs text-muted-foreground">
          {t("personaDetail.skin.preview.hint")}
        </p>
      </div>
    </div>
  )
}
