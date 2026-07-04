import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Player } from "@remotion/player"
import {
  Clip as ClipComposition,
  ASPECT_DIMENSIONS,
  COMPOSITION_FPS,
  totalDurationSeconds,
  type CaptionCue,
  type ClipBrand,
  type ClipSpec,
} from "@repurposer/clip"
import {
  LayoutTemplate,
  Captions,
  ImagePlus,
  Clapperboard,
  Music,
  Eraser,
  Highlighter,
  Undo2,
  Redo2,
  Save,
  Check,
  Trash2,
  Plus,
  Megaphone,
  type LucideIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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

export const Route = createFileRoute("/brand-template")({
  component: BrandTemplatePage,
})

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

const FONTS = [
  { value: "lilita", label: "Lilita One", family: "'Lilita One', system-ui, sans-serif" },
  { value: "inter", label: "Inter", family: "'Inter', system-ui, sans-serif" },
  { value: "playfair", label: "Playfair Display", family: "'Playfair Display', serif" },
  { value: "source-serif", label: "Source Serif 4", family: "'Source Serif 4', serif" },
]

// Renderer supports 9:16 / 1:1 only (vertical-first positioning).
const ASPECTS = ["9:16", "1:1"] as const
const CAPTION_SIZES = [32, 40, 44, 56] as const
const CAPTION_COLORS = ["#ffffff", "#facc15", "#22c55e", "#ec4899", "#6366f1"]
const MOODS = ["calm", "uplifting", "corporate", "none"] as const

/** Normalized center point [0,1] (matches @repurposer/clip Point). */
type Pt = { x: number; y: number }

type Template = {
  aspect: (typeof ASPECTS)[number]
  fillMode: "fill" | "fit"
  captionFont: string
  captionSize: number
  captionColor: string
  captionPosition: Pt
  titleSize: number
  titlePosition: Pt
  ctaPosition: Pt
  logoUrl: string
  cta: string
  introEnabled: boolean
  introText: string
  outroEnabled: boolean
  outroText: string
  musicEnabled: boolean
  musicMood: string
  removeFiller: boolean
  keywordHighlighter: boolean
  voice: string
  audience: string
  contentGuidelines: string
}

type SavedTemplate = { id: string; name: string; config: Partial<Template> }

const NEW_OPTION = "__new__"

const DEFAULT_TEMPLATE: Template = {
  aspect: "9:16",
  fillMode: "fill",
  captionFont: "lilita",
  captionSize: 44,
  captionColor: "#facc15",
  captionPosition: { x: 0.5, y: 0.84 },
  titleSize: 58,
  titlePosition: { x: 0.5, y: 0.12 },
  ctaPosition: { x: 0.5, y: 0.92 },
  logoUrl: "",
  cta: "Read the full talk →",
  introEnabled: false,
  introText: "",
  outroEnabled: false,
  outroText: "",
  musicEnabled: false,
  musicMood: "calm",
  removeFiller: false,
  keywordHighlighter: true,
  voice: "professional",
  audience: "industry professionals",
  contentGuidelines: "",
}

type Section = null | "clipLayout" | "caption" | "overlay" | "introOutro" | "music" | "content"

// Fixed LATIN samples so the brand fonts (Lilita/Inter/Playfair/Source Serif —
// all latin) actually render in the preview. Real text comes from the talk's
// ASR at generation time; these only demonstrate the *style*.
const DEMO_CAPTION = "Your captions show up here"
const DEMO_TITLE = "The hook line"

// ---------------------------------------------------------------------------
// Template -> clip-spec (live preview uses the SAME <Clip> as the real render,
// so the preview is pixel-identical to generated output — mirrors the backend
// services/brand.py mapping).
// ---------------------------------------------------------------------------

function templateToBrand(tpl: Template): ClipBrand {
  return {
    logo_url: tpl.logoUrl || null,
    cta: tpl.cta || null,
    cta_position: tpl.ctaPosition,
    caption_color: tpl.captionColor || null,
    caption_size: tpl.captionSize || null,
    caption_font: tpl.captionFont || null,
    intro_text: tpl.introEnabled ? tpl.introText || null : null,
    outro_text: tpl.outroEnabled ? tpl.outroText || null : null,
    fill_mode: tpl.fillMode,
  }
}

function buildPreviewSpec(tpl: Template): ClipSpec {
  const aspect = tpl.aspect === "1:1" ? "1:1" : "9:16"
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
    aspect,
    segments: [{ start: 0, end, hidden: false }],
    crop: { x: 0.5, y: 0.5, scale: 1 },
    caption_track,
    caption_style_preset: tpl.keywordHighlighter ? "karaoke-highlight" : "clean-bottom",
    caption_position: tpl.captionPosition,
    title: { text: DEMO_TITLE, enabled: true, size: tpl.titleSize, position: tpl.titlePosition },
    // Music is intentionally OFF in the preview: the mood still saves to the
    // template (and drives real renders), but a missing track file would 404 in
    // the browser <Player>. MVP renders are silent anyway (no bundled tracks).
    music: { track_id: null, url: null, enabled: false, gain_db: -18 },
    brand: templateToBrand(tpl),
    brand_ref: null,
    target_language: "en",
  }
}

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

/** Clamp a normalized coord into the safe zone [0.05, 0.95]. */
const clampSafe = (v: number) => Math.min(0.95, Math.max(0.05, v))

/** A draggable overlay marker that moves a normalized point within the preview. */
function DraggableMarker({
  point,
  label,
  containerRef,
  onBegin,
  onChange,
}: {
  point: Pt
  label: string
  containerRef: React.RefObject<HTMLDivElement | null>
  onBegin: () => void
  onChange: (p: Pt) => void
}) {
  const onDown = (e: React.PointerEvent) => {
    e.preventDefault()
    onBegin()
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
  return (
    <div
      onPointerDown={onDown}
      style={{
        position: "absolute",
        left: `${point.x * 100}%`,
        top: `${point.y * 100}%`,
        transform: "translate(-50%, -50%)",
        pointerEvents: "auto",
        cursor: "move",
      }}
      className="select-none whitespace-nowrap rounded-md border border-dashed border-white/70 bg-black/50 px-2 py-1 text-[10px] font-medium text-white shadow"
    >
      {label}
    </div>
  )
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-2 pb-1 pt-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/60">
      {children}
    </p>
  )
}

function ToggleRow({
  icon: Icon,
  label,
  checked,
  onCheckedChange,
}: {
  icon: LucideIcon
  label: string
  checked: boolean
  onCheckedChange: (v: boolean) => void
}) {
  return (
    <label className="flex w-full cursor-pointer items-center gap-3 rounded-lg px-2 py-2.5">
      <Icon className="h-4.5 w-4.5 shrink-0 text-muted-foreground" />
      <span className="flex-1 text-sm">{label}</span>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </label>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function BrandTemplatePage() {
  const { t } = useTranslation()

  const [template, setTemplate] = useState<Template>(DEFAULT_TEMPLATE)
  const [past, setPast] = useState<Template[]>([])
  const [future, setFuture] = useState<Template[]>([])
  const [section, setSection] = useState<Section>(null)
  const [saved, setSaved] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [templates, setTemplates] = useState<SavedTemplate[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [name, setName] = useState("Default")

  // Remotion <Player> is client-only (SSR would hydration-mismatch).
  useEffect(() => setMounted(true), [])

  const loadTemplates = async (selectId?: string) => {
    try {
      const res = await apiFetch("/api/v1/brand-templates")
      if (!res.ok) return
      const list: SavedTemplate[] = await res.json()
      setTemplates(list)
      const pick = selectId ? list.find((x) => x.id === selectId) : list[0]
      if (pick) {
        setSelectedId(pick.id)
        setName(pick.name)
        setTemplate({ ...DEFAULT_TEMPLATE, ...pick.config })
      }
    } catch {
      /* offline / no backend — keep the local default */
    }
  }

  // Load saved templates on mount (a default is seeded server-side).
  useEffect(() => {
    void loadTemplates()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const commit = (next: Template) => {
    setPast((p) => [...p, template])
    setFuture([])
    setTemplate(next)
    setSaved(false)
  }

  const update = <K extends keyof Template>(key: K, value: Template[K]) =>
    commit({ ...template, [key]: value })

  const undo = () => {
    if (past.length === 0) return
    const prev = past[past.length - 1]
    setPast((p) => p.slice(0, -1))
    setFuture((f) => [template, ...f])
    setTemplate(prev)
    setSaved(false)
  }

  const redo = () => {
    if (future.length === 0) return
    const next = future[0]
    setFuture((f) => f.slice(1))
    setPast((p) => [...p, template])
    setTemplate(next)
    setSaved(false)
  }

  const selectTemplate = (id: string) => {
    if (id === NEW_OPTION) {
      setSelectedId(null)
      setName(t("brandTemplate.untitled"))
      commit(DEFAULT_TEMPLATE)
      return
    }
    const found = templates.find((x) => x.id === id)
    if (!found) return
    setSelectedId(found.id)
    setName(found.name)
    commit({ ...DEFAULT_TEMPLATE, ...found.config })
  }

  const handleSave = async () => {
    try {
      const res = await apiFetch(
        selectedId
          ? `/api/v1/brand-templates/${selectedId}`
          : "/api/v1/brand-templates",
        {
          method: selectedId ? "PUT" : "POST",
          body: { name: name || "Untitled", config: template },
        }
      )
      if (!res.ok) return
      const data = await res.json()
      await loadTemplates(data.id)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      /* save failed — keep editing */
    }
  }

  const handleDelete = async () => {
    if (!selectedId) return
    try {
      await apiFetch(`/api/v1/brand-templates/${selectedId}`, { method: "DELETE" })
      setSelectedId(null)
      await loadTemplates()
    } catch {
      /* ignore */
    }
  }

  const previewSpec = useMemo(() => buildPreviewSpec(template), [template])

  const previewRef = useRef<HTMLDivElement | null>(null)
  // Snapshot once per drag (one undo entry); live updates skip history.
  const beginDrag = () => {
    setPast((p) => [...p, template])
    setFuture([])
  }
  const liveSet = <K extends keyof Template>(key: K, value: Template[K]) => {
    setTemplate((tpl) => ({ ...tpl, [key]: value }))
    setSaved(false)
  }

  return (
    <div className="flex h-svh flex-col">
      {/* Top bar */}
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b px-6">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold tracking-tight">{t("brandTemplate.title")}</h1>
          <p className="hidden text-sm text-muted-foreground md:block">
            {t("brandTemplate.subtitle")}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Select value={selectedId ?? NEW_OPTION} onValueChange={(v) => selectTemplate(v ?? NEW_OPTION)}>
            <SelectTrigger className="h-9 w-44 justify-between rounded-md text-sm">
              <SelectValue placeholder={t("brandTemplate.untitled")} />
            </SelectTrigger>
            <SelectContent>
              {templates.map((tpl) => (
                <SelectItem key={tpl.id} value={tpl.id}>
                  {tpl.name}
                </SelectItem>
              ))}
              <SelectItem value={NEW_OPTION}>
                <span className="flex items-center gap-1.5">
                  <Plus className="h-3.5 w-3.5" />
                  {t("brandTemplate.newTemplate")}
                </span>
              </SelectItem>
            </SelectContent>
          </Select>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("brandTemplate.namePlaceholder")}
            className="h-9 w-40"
          />
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("brandTemplate.undo")}
            disabled={past.length === 0}
            onClick={undo}
          >
            <Undo2 className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("brandTemplate.redo")}
            disabled={future.length === 0}
            onClick={redo}
          >
            <Redo2 className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("brandTemplate.delete")}
            disabled={!selectedId}
            onClick={handleDelete}
          >
            <Trash2 className="h-5 w-5" />
          </Button>
          <Button onClick={handleSave}>
            {saved ? <Check className="mr-2 h-4 w-4" /> : <Save className="mr-2 h-4 w-4" />}
            {t("brandTemplate.save")}
          </Button>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left setting panel — shadcn vertical Tabs: list (left) + detail (right) */}
        <Tabs
          value={section ?? "clipLayout"}
          onValueChange={(v) => setSection((v as Section) ?? null)}
          orientation="vertical"
          className="flex shrink-0 gap-3 overflow-hidden p-4"
        >
          {/* Section list */}
          <div className="w-[244px] shrink-0 overflow-y-auto p-1">
            <div className="overflow-hidden rounded-lg bg-card ring-1 ring-border">
              <div className="border-b px-4 py-3">
                <h2 className="font-semibold">{t("brandTemplate.setting")}</h2>
              </div>
              <div className="p-2">
                <TabsList
                  variant="line"
                  className="h-fit w-full flex-col items-stretch gap-0.5 bg-transparent p-0"
                >
                  <TabsTrigger value="clipLayout" className="justify-start gap-2.5 px-2 py-2 text-sm">
                    <LayoutTemplate className="h-4.5 w-4.5 text-muted-foreground" />
                    {t("brandTemplate.rows.clipLayout")}
                  </TabsTrigger>
                  <TabsTrigger value="caption" className="justify-start gap-2.5 px-2 py-2 text-sm">
                    <Captions className="h-4.5 w-4.5 text-muted-foreground" />
                    {t("brandTemplate.rows.caption")}
                  </TabsTrigger>
                  <TabsTrigger value="overlay" className="justify-start gap-2.5 px-2 py-2 text-sm">
                    <ImagePlus className="h-4.5 w-4.5 text-muted-foreground" />
                    {t("brandTemplate.rows.overlay")}
                  </TabsTrigger>
                  <TabsTrigger value="content" className="justify-start gap-2.5 px-2 py-2 text-sm">
                    <Megaphone className="h-4.5 w-4.5 text-muted-foreground" />
                    {t("brandTemplate.rows.content")}
                  </TabsTrigger>
                  <TabsTrigger value="introOutro" className="justify-start gap-2.5 px-2 py-2 text-sm">
                    <Clapperboard className="h-4.5 w-4.5 text-muted-foreground" />
                    {t("brandTemplate.rows.introOutro")}
                  </TabsTrigger>
                  <TabsTrigger value="music" className="justify-start gap-2.5 px-2 py-2 text-sm">
                    <Music className="h-4.5 w-4.5 text-muted-foreground" />
                    {t("brandTemplate.rows.music")}
                  </TabsTrigger>
                </TabsList>

                <GroupLabel>{t("brandTemplate.groups.ai")}</GroupLabel>
                <ToggleRow
                  icon={Eraser}
                  label={t("brandTemplate.rows.removeFiller")}
                  checked={template.removeFiller}
                  onCheckedChange={(v) => update("removeFiller", v)}
                />
                <ToggleRow
                  icon={Highlighter}
                  label={t("brandTemplate.rows.keywordHighlighter")}
                  checked={template.keywordHighlighter}
                  onCheckedChange={(v) => update("keywordHighlighter", v)}
                />
              </div>
            </div>
          </div>

          {/* Section detail */}
          <div className="w-[324px] shrink-0 overflow-y-auto p-1">
            <Card className="rounded-lg ring-1 ring-border">
              <CardContent className="px-4">
                <TabsContent value="clipLayout" className="space-y-4">
                  <Field label={t("brandTemplate.clipLayout.aspect")}>
                    <ToggleGroup
                      variant="outline"
                      spacing={0}
                      value={[template.aspect]}
                      onValueChange={(v) => v[0] && update("aspect", v[0] as Template["aspect"])}
                      className="w-full"
                    >
                      {ASPECTS.map((a) => (
                        <ToggleGroupItem key={a} value={a} className="flex-1 text-xs">
                          {a}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                  </Field>
                  <Field label={t("brandTemplate.clipLayout.fillMode")}>
                    <ToggleGroup
                      variant="outline"
                      spacing={0}
                      value={[template.fillMode]}
                      onValueChange={(v) => v[0] && update("fillMode", v[0] as "fill" | "fit")}
                      className="w-full"
                    >
                      {(["fill", "fit"] as const).map((m) => (
                        <ToggleGroupItem key={m} value={m} className="flex-1 text-xs">
                          {t(`brandTemplate.clipLayout.${m}`)}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                  </Field>
                </TabsContent>

                <TabsContent value="caption" className="space-y-4">
                  <Field label={t("brandTemplate.caption.font")}>
                    <Select
                      value={template.captionFont}
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
                  <Field label={t("brandTemplate.caption.size")}>
                    <ToggleGroup
                      variant="outline"
                      spacing={0}
                      value={[String(template.captionSize)]}
                      onValueChange={(v) => v[0] && update("captionSize", Number(v[0]))}
                      className="w-full"
                    >
                      {CAPTION_SIZES.map((s) => (
                        <ToggleGroupItem key={s} value={String(s)} className="flex-1 text-xs">
                          {s}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                  </Field>
                  <Field label={t("brandTemplate.caption.color")}>
                    <div className="flex items-center gap-2">
                      {CAPTION_COLORS.map((c) => (
                        <button
                          key={c}
                          type="button"
                          aria-label={c}
                          onClick={() => update("captionColor", c)}
                          style={{ backgroundColor: c }}
                          className={cn(
                            "h-7 w-7 rounded-full ring-2 ring-offset-2 ring-offset-card transition-all",
                            template.captionColor === c ? "ring-primary" : "ring-transparent"
                          )}
                        />
                      ))}
                    </div>
                  </Field>
                </TabsContent>

                <TabsContent value="overlay" className="space-y-4">
                  <Field label={t("brandTemplate.overlay.logo")}>
                    <Input
                      value={template.logoUrl}
                      onChange={(e) => update("logoUrl", e.target.value)}
                      placeholder={t("brandTemplate.overlay.logoPlaceholder")}
                    />
                  </Field>
                  <Field label={t("brandTemplate.overlay.cta")}>
                    <Input
                      value={template.cta}
                      onChange={(e) => update("cta", e.target.value)}
                      placeholder={t("brandTemplate.overlay.ctaPlaceholder")}
                    />
                  </Field>
                </TabsContent>

                <TabsContent value="content" className="space-y-4">
                  <Field label={t("brandTemplate.content.voice")}>
                    <Input
                      value={template.voice}
                      onChange={(e) => update("voice", e.target.value)}
                      placeholder={t("brandTemplate.content.voicePlaceholder")}
                    />
                  </Field>
                  <Field label={t("brandTemplate.content.audience")}>
                    <Input
                      value={template.audience}
                      onChange={(e) => update("audience", e.target.value)}
                      placeholder={t("brandTemplate.content.audiencePlaceholder")}
                    />
                  </Field>
                  <Field label={t("brandTemplate.content.guidelines")}>
                    <Textarea
                      value={template.contentGuidelines}
                      onChange={(e) => update("contentGuidelines", e.target.value)}
                      placeholder={t("brandTemplate.content.guidelinesPlaceholder")}
                      className="min-h-[100px] resize-none"
                    />
                  </Field>
                </TabsContent>

                <TabsContent value="introOutro" className="space-y-4">
                  <label className="flex items-center justify-between">
                    <span className="text-sm">{t("brandTemplate.introOutro.intro")}</span>
                    <Switch
                      checked={template.introEnabled}
                      onCheckedChange={(v) => update("introEnabled", v)}
                    />
                  </label>
                  {template.introEnabled && (
                    <Field label={t("brandTemplate.introOutro.introText")}>
                      <Input
                        value={template.introText}
                        onChange={(e) => update("introText", e.target.value)}
                        placeholder={t("brandTemplate.introOutro.introPlaceholder")}
                      />
                    </Field>
                  )}
                  <label className="flex items-center justify-between">
                    <span className="text-sm">{t("brandTemplate.introOutro.outro")}</span>
                    <Switch
                      checked={template.outroEnabled}
                      onCheckedChange={(v) => update("outroEnabled", v)}
                    />
                  </label>
                  {template.outroEnabled && (
                    <Field label={t("brandTemplate.introOutro.outroText")}>
                      <Input
                        value={template.outroText}
                        onChange={(e) => update("outroText", e.target.value)}
                        placeholder={t("brandTemplate.introOutro.outroPlaceholder")}
                      />
                    </Field>
                  )}
                </TabsContent>

                <TabsContent value="music" className="space-y-4">
                  <label className="flex items-center justify-between">
                    <span className="text-sm">{t("brandTemplate.music.enable")}</span>
                    <Switch
                      checked={template.musicEnabled}
                      onCheckedChange={(v) => update("musicEnabled", v)}
                    />
                  </label>
                  {template.musicEnabled && (
                    <Field label={t("brandTemplate.music.mood")}>
                      <ToggleGroup
                        variant="outline"
                        spacing={0}
                        value={[template.musicMood]}
                        onValueChange={(v) => v[0] && update("musicMood", v[0])}
                        className="w-full"
                      >
                        {MOODS.filter((m) => m !== "none").map((m) => (
                          <ToggleGroupItem key={m} value={m} className="flex-1 text-xs">
                            {t(`brandTemplate.music.moods.${m}`)}
                          </ToggleGroupItem>
                        ))}
                      </ToggleGroup>
                    </Field>
                  )}
                </TabsContent>
              </CardContent>
            </Card>
          </div>
        </Tabs>

        {/* Right preview — the REAL <Clip>, with draggable overlay markers */}
        <main className="flex flex-1 items-center justify-center overflow-hidden p-8">
          <div className="flex h-full max-h-[680px] flex-col items-center gap-2">
            <span className="text-xs text-muted-foreground">{t("brandTemplate.demo")}</span>
            <div
              ref={previewRef}
              className="relative"
              style={{
                height: "100%",
                aspectRatio: previewSpec.aspect === "1:1" ? "1 / 1" : "9 / 16",
              }}
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
                  compositionWidth={ASPECT_DIMENSIONS[previewSpec.aspect].width}
                  compositionHeight={ASPECT_DIMENSIONS[previewSpec.aspect].height}
                  style={{
                    height: "100%",
                    width: "100%",
                    borderRadius: 16,
                    overflow: "hidden",
                    boxShadow: "0 10px 40px rgba(0,0,0,0.45)",
                  }}
                  controls
                  autoPlay
                />
              ) : (
                <div className="h-full w-full rounded-2xl bg-card ring-1 ring-border" />
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
                  <DraggableMarker
                    point={template.titlePosition}
                    label={t("brandTemplate.rows.title")}
                    containerRef={previewRef}
                    onBegin={beginDrag}
                    onChange={(p) => liveSet("titlePosition", p)}
                  />
                  <DraggableMarker
                    point={template.captionPosition}
                    label={t("brandTemplate.rows.caption")}
                    containerRef={previewRef}
                    onBegin={beginDrag}
                    onChange={(p) => liveSet("captionPosition", p)}
                  />
                  <DraggableMarker
                    point={template.ctaPosition}
                    label="CTA"
                    containerRef={previewRef}
                    onBegin={beginDrag}
                    onChange={(p) => liveSet("ctaPosition", p)}
                  />
                </div>
              ) : null}
            </div>
            <p className="max-w-[280px] text-center text-xs text-muted-foreground">
              {t("brandTemplate.previewHint")}
            </p>
          </div>
        </main>
      </div>
    </div>
  )
}
