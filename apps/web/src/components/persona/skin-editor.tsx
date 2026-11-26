import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Player } from "@remotion/player"
import { Video } from "@repurposer/video-remotion"
import { videoSpecSchema, type VideoSpec } from "@repurposer/video-spec"
import { Check, RotateCcw, Save, Upload, X } from "@/components/ui/icons"

import { IconButton } from "@/components/ui/icon-button-clean"
import { Button } from "@/components/ui/button-clean"
import { Card, CardHeader, CardContent } from "@/components/ui/card-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { Switch } from "@/components/ui/switch-clean"
import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import { Select } from "@/components/ui/select-clean"
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
/** Normalized center point [0,1] (matches @repurposer/clip Point). */
type Pt = { x: number; y: number }

type IntroOutroKind = "text" | "image" | "video"

export type SkinBlock = {
  captionFont: string
  captionSize: number
  captionColor: string
  captionPosition: Pt
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
  captionSize: 68,
  captionColor: "#facc15",
  captionPosition: { x: 0.5, y: 0.84 },
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
// Skin -> ordinary native TextObject and AudioObject video-spec.
// ---------------------------------------------------------------------------

function buildPreviewSpec(skin: SkinBlock): VideoSpec {
  const textObject = (id: string, text: string, size: number, position: Pt): VideoSpec["tracks"][number]["clips"][number]["object"] => ({
    kind: "text", object_id: id, text,
    layout: { x: 54, y: Math.max(0, position.y * 1920 - 90), width: 972, height: 180 },
    style: {
      font_size: size, color: skin.captionColor, background: null,
      background_mode: "box", background_opacity: 1, background_padding: [0, 0],
      background_radius: 0, border: null,
      weight: 600, align: "center", line_height: 1.3, letter_spacing: 0,
      text_transform: "none", secondary_line_scale: 1, secondary_line_opacity: 1,
      stroke: null, shadow: null, font: { font_id: "noto-sans-sc", digest: "85571c8f24f75610320baf3cec0302ba4766b15cea9efc9782b38ecc2b96511c" },
    },
    transform: { x: 0, y: 0, scale: 1, rotation: 0, origin: "center" },
    opacity: 1, segmentation_version: "scalar-grapheme-v1", layout_version: "explicit-line-inline-v1",
    parts: [{ part_id: `${id}-line`, kind: "line", text, text_range: { start: 0, end: text.length }, layout_range: { start: 0, end: text.length } }],
  })
  const clips = [
    { clip_id: "preview-caption", start_frame: 0, end_frame: 120, scene_id: "preview", source: null,
      object: textObject("preview-caption", DEMO_CAPTION, skin.captionSize, skin.captionPosition), animations: [] },
    ...(skin.titleEnabled ? [{ clip_id: "preview-title", start_frame: 0, end_frame: 120, scene_id: "preview", source: null,
      object: textObject("preview-title", DEMO_TITLE, skin.titleSize, skin.titlePosition), animations: [] }] : []),
  ]
  const tracks: VideoSpec["tracks"] = [{ track_id: "preview-text", kind: "visual", role: "caption", order: 0, clips }]
  if (skin.musicId) {
    tracks.push({ track_id: "preview-music", kind: "audio", role: "music", order: 0, clips: [{
      clip_id: "preview-music", start_frame: 0, end_frame: 120, scene_id: "preview",
      source: { url: `${API_URL}/api/v1/music/${skin.musicId}/stream`, digest: "0".repeat(64), start_frame: 0, end_frame: 120 },
      object: { kind: "audio", object_id: "preview-music", gain_db: skin.musicEnabled ? skin.musicGainDb : -60 }, animations: [],
    }] })
  }
  return {
    family: "video", format: 1, fps: { num: 30, den: 1 }, width: 1080, height: 1920,
    background: "#111827", sample_rate: 48000, duration_frames: 120,
    fonts: [{ font_id: "noto-sans-sc", font_set_digest: "85571c8f24f75610320baf3cec0302ba4766b15cea9efc9782b38ecc2b96511c", family: "Noto Sans SC", weight: 700, format: "opentype", url: `${API_URL}/api/v1/files/fonts/noto-sans-sc/c6cb5a93abaa9edc8ee7463b7ebb7f42d618d40e6ed2f7a5371c97b0b64767c0.otf`, digest: "c6cb5a93abaa9edc8ee7463b7ebb7f42d618d40e6ed2f7a5371c97b0b64767c0" }], tracks,
    provenance: { composition_id: "persona-preview", composition_version_id: `skin-${skin.captionSize}-${skin.captionColor}`, content_digest: "0".repeat(64) },
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
      <label className="text-xs text-muted-foreground">{label}</label>
      {children}
    </div>
  )
}

/** Free-form font-size control: drag the slider or type an exact value. */
function SizeControl({
  label,
  value,
  onChange,
  min = 16,
  max = 120,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
}) {
  return (
    <div className="flex items-center gap-3">
      <input type="range"
        min={min}
        max={max}
        step={1}
        aria-label={label} value={value}
        onChange={(e) => onChange(e.target.valueAsNumber)}
        className="flex-1"
      />
      <TextField aria-label={label}
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
            <IconButton variant="secondary" size="sm" label={t("common.upload")} onClick={() => inputRef.current?.click()} icon={<Upload />} />
            <IconButton variant="secondary" size="sm" label={t("common.remove")} onClick={onClear} icon={<X />} />
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

  const previewSpec = useMemo(() => videoSpecSchema.parse(buildPreviewSpec(skin)), [skin])
  const previewRef = useRef<HTMLDivElement | null>(null)

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto]">
      {/* Settings — single column, grouped (craft keys are task-book defaults
          and intentionally absent, NAMING N-28) */}
      <Card>
        <CardHeader title={t("personaDetail.skin.title")} description={t("personaDetail.skin.desc")} />
        <CardContent className="space-y-6">
          <section className="space-y-4">
            <GroupLabel>{t("personaDetail.skin.groups.caption")}</GroupLabel>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("personaDetail.skin.caption.font")}>
                <Select aria-label={t("personaDetail.skin.caption.font")} value={skin.captionFont}
                  options={FONTS.map(({ value, label }) => ({ value, label }))} onChange={(value) => update("captionFont", value)} />
              </Field>
            </div>
            <Field label={t("personaDetail.skin.caption.size")}>
              <SizeControl label={t("personaDetail.skin.caption.size")}
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
                      "h-7 w-7 rounded-md outline-2 outline-offset-2 transition-all focus-visible:outline-primary",
                      skin.captionColor === c ? "outline-primary" : "outline-transparent"
                    )}
                  />
                ))}
                <label
                  className={cn(
                    "relative flex h-7 w-7 cursor-pointer items-center justify-center rounded-md outline-2 outline-offset-2 transition-all focus-within:outline-primary",
                    CAPTION_COLORS.includes(skin.captionColor)
                      ? "outline-transparent"
                      : "outline-primary"
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
              <TextField
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
                aria-label={t("personaDetail.skin.groups.title")}
                onChange={(event) => update("titleEnabled", event.target.checked)}
              />
            </div>
            {skin.titleEnabled && (
              <>
                <Field label={t("personaDetail.skin.titleCard.size")}>
              <SizeControl label={t("personaDetail.skin.titleCard.size")}
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
                    aria-label={t(`personaDetail.skin.groups.${slot}`)}
                    onChange={(event) => update(enabledKey, event.target.checked)}
                  />
                </div>
                {skin[enabledKey] && (
                  <>
                    <Field label={t("personaDetail.skin.introOutro.type")}>
                      <SegmentedControl value={skin[kindKey]} aria-label={t("personaDetail.skin.introOutro.type")}
                        onChange={(value) => update(kindKey, value)}
                        options={(["text", "image", "video"] as const).map((value) => ({
                          value, label: t(`personaDetail.skin.introOutro.kinds.${value}`),
                        }))} />
                    </Field>
                    {skin[kindKey] === "text" ? (
                      <Field label={t(`personaDetail.skin.introOutro.${textKey}`)}>
                        <TextField
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
                        <TextField
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
              size="sm"
              onClick={handleReset}
              disabled={saving || brand === null}
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              {t("personaDetail.skin.reset")}
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving || !dirty}>
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

      {/* Native video-spec preview; markers edit ordinary text layout. */}
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
          className="relative h-[480px] rounded-2xl border border-subtle md:h-[560px]"
          style={{ aspectRatio: "9 / 16" }}
        >
          {mounted ? (
            <Player
              component={Video}
              inputProps={{ spec: previewSpec }}
              durationInFrames={previewSpec.duration_frames}
              fps={previewSpec.fps.num / previewSpec.fps.den}
              compositionWidth={previewSpec.width}
              compositionHeight={previewSpec.height}
              style={{ height: "100%", width: "100%", borderRadius: 16, overflow: "hidden" }}
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
                  compositionHeight={1920}
                  onChange={(p) => update("titlePosition", p)}
                  onSizeChange={(s) => update("titleSize", s)}
                />
              )}
              <DraggableMarker
                point={skin.captionPosition}
                label={t("personaDetail.skin.groups.caption")}
                containerRef={previewRef}
                sizeValue={skin.captionSize}
                compositionHeight={1920}
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
