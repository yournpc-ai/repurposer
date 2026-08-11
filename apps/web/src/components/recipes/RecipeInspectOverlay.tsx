"use client"

import { useEffect, useMemo, useRef, useState, type DragEvent } from "react"
import { useTranslation } from "react-i18next"
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"
import {
  FileText,
  Image as ImageIcon,
  Music,
  Upload,
  Video,
  Volume2,
  VolumeX,
  X,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { FlowView } from "@/components/flow/FlowView"
import { useProjectLaunch } from "@/lib/useProjectLaunch"
import type { RecipeCard } from "@/lib/recipes"
import { ASSETS_ACCEPT } from "@/components/home/AssetsModal"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

import { recipeProcessFlow } from "./recipeFlow"

/**
 * Recipe inspect overlay (D6 二次修订 2026-08-08): **inspect tabs + launch
 * zone**. Left = the launch zone — the composer's send mechanism parked here
 * (`useProjectLaunch`, the SAME path: create project → upload → navigate →
 * first /chat message). The overlay never infers, never builds a prior,
 * never runs generation (the A-form rejection stands).
 *
 * Chrome = the shared Dialog primitive (portal → overlay + popup siblings,
 * overlay-surface glass, esc/outside-click, scroll lock — all stock). The
 * popup is composed by hand and centered with `inset-0 m-auto`, NOT
 * DialogContent — a transformed popup becomes the containing block for
 * `fixed` descendants, so a hand-composed popup is the safe host for any
 * viewport-anchored floater (the CLAUDE.md rule), and its chrome MIRRORS
 * DialogContent exactly (overlay-surface + hairline + shadow-xl +
 * rounded-xl).
 *
 * Right = read-only views of the Recipe data pack in ONE screen, with the
 * graph rendered exactly ONCE (ElevenCreative 2026-08-08 evidence):
 * - 示例 = FLAT input/output sections (auto-playing muted cards, one sounds
 *   at a time) — no edges, no canvas;
 * - 流程 = THE canvas — one FlowView graph: source material → curated
 *   process steps (fanout expanded) → the baked outputs as terminal nodes.
 *
 * Preset visibility: the prompt area IS the visible preset — a plain
 * textarea prefilled with the template. The recipe's identity never enters
 * the sentence: the card click already said everything (MENTIONS §3), and
 * `recipeId` rides the launch as a transport field. The only edit entry
 * stays the prompt text (before send) / chat (after send); chat always
 * wins.
 */
/** Input slot type → the Input section's icon (registry-driven, one map). */
const INPUT_TYPE_ICONS: Record<string, typeof Video> = {
  video: Video,
  audio: Music,
  images: ImageIcon,
  transcript: FileText,
}

export function RecipeInspectOverlay({
  card,
  onClose,
}: {
  card: RecipeCard
  onClose: () => void
}) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)
  const { launching, launch } = useProjectLaunch()

  const title = t(`recipes.${card.id}.title`)
  const template = t(`recipes.${card.id}.promptTemplate`)
  // The Input section's icon follows the recipe's first input slot — the
  // material ask is registry data, never per-card branches.
  const InputIcon =
    INPUT_TYPE_ICONS[card.input_slots[0]?.type ?? ""] ?? FileText

  // The draft: the template as plain editable text. The recipe's identity
  // rides the launch as `recipeId` — no chip row (the card click already
  // said everything; a third repetition is noise, MENTIONS §3).
  const [prompt, setPrompt] = useState(template)
  const [files, setFiles] = useState<File[]>([])

  // Inspect tabs (right zone): 示例 = flat cards; 流程 = the one canvas.
  const [tab, setTab] = useState<"examples" | "flow">("examples")
  // The one card currently sounding (autoplay is muted; the toggle circle
  // unmutes one card at a time — the home gallery's pattern).
  const [soundingId, setSoundingId] = useState<string | null>(null)

  const process = useMemo(() => recipeProcessFlow(card, t), [card, t])

  // The baked outputs share the source's content — the source's poster
  // doubles as its thumb when the asset itself has none (demo talk video).
  const sharedPoster =
    card.example_outputs.find((o) => o.poster_url)?.poster_url ?? null

  const addFiles = (picked: File[]) => {
    if (picked.length === 0) return
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}:${f.size}`))
      const additions = picked.filter((f) => !existing.has(`${f.name}:${f.size}`))
      return [...prev, ...additions]
    })
  }
  const removeFile = (index: number) =>
    setFiles((prev) => prev.filter((_, i) => i !== index))

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    addFiles(Array.from(e.dataTransfer.files ?? []))
  }

  // Send = the composer's send, parked here. Nothing to consume onSent — the
  // overlay's draft dies with navigation. Identity rides the default-persona
  // chain server-side (ADR-038) — the overlay carries no persona picker; the
  // recipe's identity rides as `recipeId` (MENTIONS §3).
  const handleLaunch = () =>
    launch({ prompt, mentions: [], files, recipeId: card.id })

  const fileIconFor = (file: File) => {
    if (file.type.startsWith("video/")) return Video
    if (file.type.startsWith("audio/")) return Music
    if (file.type.startsWith("image/")) return ImageIcon
    return FileText
  }

  const materialLabel = (labelKey?: string | null) =>
    labelKey ? t(`recipes.materials.${labelKey}`) : null

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        // Closing is blocked mid-launch (the send owns the spinner →
        // navigation lifecycle).
        if (!open && !launching) onClose()
      }}
    >
      <DialogPortal>
        <DialogOverlay />
        {/* Hand-composed popup (transform-free ancestor, so viewport-anchored
            floaters never teleport) — the chrome MIRRORS DialogContent
            exactly: overlay-surface + the ring-foreground/10 hairline +
            shadow-xl + rounded-xl. Without the hairline the light-theme
            glass dissolves into the white backdrop wash. */}
        <DialogPrimitive.Popup
          className="overlay-surface fixed inset-0 z-50 m-auto flex h-[92vh] w-[calc(100%-2rem)] max-w-7xl flex-col overflow-hidden rounded-xl shadow-xl ring-1 ring-foreground/10 outline-none duration-100 data-open:animate-in data-open:fade-in-0 md:h-[84vh]"
        >
          <DialogClose
            aria-label={t("common.close")}
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                className="absolute top-2 right-2 z-10"
              />
            }
          >
            <X />
          </DialogClose>

          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto md:flex-row md:overflow-hidden">
            {/* LEFT — the launch zone: material is the recipe's only blank, so
                the upload zone is the hero; the prefilled prompt stays visible
                and editable (it IS the visible preset — no picker controls). */}
            <div className="flex w-full flex-shrink-0 flex-col gap-5 p-6 md:w-[360px] md:overflow-y-auto lg:w-[400px]">
              <div>
                <DialogTitle className="text-xl">{title}</DialogTitle>
                <DialogDescription className="mt-1.5 text-sm">
                  {t(`recipes.${card.id}.promise`)}
                </DialogDescription>
              </div>

              {/* The material ask (ElevenCreative modal pattern 2026-08-10):
                  an Input section names what the recipe needs in plain words;
                  the dropzone copy itself stays generic. */}
              <div>
                <p className="flex items-center gap-1.5 text-sm font-medium">
                  <InputIcon className="h-4 w-4 text-muted-foreground" />
                  {t(`recipes.${card.id}.inputTitle`)}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t(`recipes.${card.id}.inputHint`)}
                </p>
              </div>

              <input
                ref={inputRef}
                type="file"
                multiple
                className="hidden"
                accept={ASSETS_ACCEPT}
                onChange={(e) => {
                  addFiles(Array.from(e.target.files ?? []))
                  // Reset so picking the same file again still fires onChange.
                  e.target.value = ""
                }}
              />
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                className="flex h-24 w-full flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Upload className="h-5 w-5" />
                <span className="text-sm">{t("recipes.inspect.dropzone")}</span>
              </button>

              {files.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  {files.map((file, index) => {
                    const Icon = fileIconFor(file)
                    return (
                      <div
                        key={`${file.name}:${file.size}`}
                        className="flex items-center gap-2 rounded-md bg-muted px-2.5 py-1.5"
                      >
                        <Icon className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1 truncate text-xs">
                          {file.name}
                        </span>
                        <button
                          type="button"
                          aria-label={t("common.remove")}
                          onClick={() => removeFile(index)}
                          className="flex-shrink-0 text-muted-foreground hover:text-foreground"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}

              <div>
                <p className="mb-1.5 text-xs text-muted-foreground">
                  {t("recipes.inspect.promptLabel")}
                </p>
                <div className="flex h-36 flex-col gap-1.5 rounded-lg bg-inset p-2.5">
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    disabled={launching}
                    placeholder={t("home.pastePlaceholder")}
                    className="min-h-0 w-full flex-1 resize-none self-stretch bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                  />
                </div>
              </div>

              <Button
                onClick={handleLaunch}
                disabled={launching}
                className="mt-auto h-10 w-full text-sm"
              >
                {launching && (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                )}
                {t("recipes.inspect.send")}
              </Button>
            </div>

            {/* RIGHT — the canvas IS the zone: full-bleed, tabs floating on
                top. Light: NO solid paint — --popover and --background are
                both pure white, so a solid bg-background half would read as a
                two-tone seam against the 92% glass; the glass alone keeps the
                modal one surface (the Login read). Dark: the inverted inset
                well (bg-inset) — a deliberate darker canvas. The left seam is
                the /10 hairline. */}
            <div className="relative min-h-0 flex-1 border-foreground/10 border-t md:border-l md:border-t-0 dark:bg-inset">
              <Tabs
                value={tab}
                onValueChange={(v) => setTab(v as "examples" | "flow")}
                className="flex h-full min-h-0 flex-col"
              >
                <TabsList
                  variant="line"
                  className="absolute left-6 top-5 z-10 gap-2"
                >
                  <TabsTrigger value="examples" className="px-3 text-sm">
                    {t("recipes.inspect.tabs.examples")}
                  </TabsTrigger>
                  <TabsTrigger value="flow" className="px-3 text-sm">
                    {t("recipes.inspect.tabs.flow")}
                  </TabsTrigger>
                </TabsList>

                <TabsContent
                  value="examples"
                  className="h-[70vh] min-h-0 flex-1 overflow-y-auto px-6 pb-6 pt-16 [mask-image:linear-gradient(to_bottom,transparent,black_56px)] md:h-auto"
                >
                  <div className="flex flex-col gap-8">
                    {card.example_outputs.length > 0 && (
                      <section aria-label={t("recipes.inspect.sections.outputs")}>
                        <p className="text-meta mb-3">
                          {t("recipes.inspect.sections.outputs")}
                        </p>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                          {card.example_outputs.map((o, i) => (
                            <ExampleCard
                              key={`output:${i}`}
                              id={`output:${i}`}
                              kind={o.kind}
                              url={o.url}
                              poster={o.poster_url ?? null}
                              label={materialLabel(o.label_key) ?? o.kind}
                              vertical
                              sounding={soundingId === `output:${i}`}
                              onToggleSound={(id) =>
                                setSoundingId((prev) => (prev === id ? null : id))
                              }
                            />
                          ))}
                        </div>
                      </section>
                    )}
                    {card.example_assets.length > 0 && (
                      <section aria-label={t("recipes.inspect.sections.inputs")}>
                        <p className="text-meta mb-3">
                          {t("recipes.inspect.sections.inputs")}
                        </p>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                          {card.example_assets.map((a, i) => (
                            <ExampleCard
                              key={`asset:${i}`}
                              id={`asset:${i}`}
                              kind={a.kind}
                              url={a.url}
                              poster={a.kind === "video" ? sharedPoster : null}
                              label={materialLabel(a.label_key) ?? a.kind}
                              sounding={soundingId === `asset:${i}`}
                              onToggleSound={(id) =>
                                setSoundingId((prev) => (prev === id ? null : id))
                              }
                            />
                          ))}
                        </div>
                      </section>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="flow" className="h-[70vh] min-h-0 flex-1 md:h-auto">
                  {process.nodes.length > 0 && (
                    <FlowView
                      nodes={process.nodes}
                      edges={process.edges}
                      dots
                      className="h-full"
                    />
                  )}
                </TabsContent>
              </Tabs>
            </div>
          </div>
        </DialogPrimitive.Popup>
      </DialogPortal>
    </Dialog>
  )
}

/** One baked example card (示例 tab): auto-playing muted loop with the home
 * gallery's sound-toggle circle (one card sounds at a time). Outputs render
 * vertical (the recipe's aspect); inputs render 16:9 — a source may be
 * landscape (e.g. a two-person interview) and object-cover thumbs both. */
function ExampleCard({
  id,
  kind,
  url,
  poster,
  label,
  vertical = false,
  sounding,
  onToggleSound,
}: {
  id: string
  kind: string
  url: string
  poster: string | null
  label: string
  vertical?: boolean
  sounding: boolean
  onToggleSound: (id: string) => void
}) {
  const { t } = useTranslation()
  const videoRef = useRef<HTMLVideoElement>(null)

  // React's `muted` prop is unreliable after mount (attribute vs property) —
  // drive it imperatively so the sound toggle always lands.
  useEffect(() => {
    if (videoRef.current) videoRef.current.muted = !sounding
  }, [sounding])

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-lg bg-black",
        vertical ? "aspect-[9/16]" : "aspect-video",
      )}
    >
      {kind === "video" ? (
        <video
          ref={videoRef}
          src={url}
          poster={poster ?? undefined}
          className="h-full w-full object-cover"
          autoPlay
          muted
          loop
          playsInline
        />
      ) : (
        <img src={url} alt={label} className="h-full w-full object-cover" />
      )}

      <span className="absolute bottom-2 left-2 rounded-md bg-white/15 px-2 py-0.5 text-xs text-white backdrop-blur-sm">
        {label}
      </span>

      {kind === "video" && (
        <button
          type="button"
          aria-label={sounding ? t("recipes.mute") : t("recipes.unmute")}
          onClick={() => onToggleSound(id)}
          className={cn(
            "absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-white backdrop-blur-sm transition-all duration-300 ease-out hover:bg-white/25",
            sounding
              ? "translate-y-0 opacity-100"
              : "pointer-events-none -translate-y-1 opacity-0 group-hover:pointer-events-auto group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:translate-y-0 group-focus-within:opacity-100",
          )}
        >
          {sounding ? (
            <Volume2 className="h-3.5 w-3.5" />
          ) : (
            <VolumeX className="h-3.5 w-3.5" />
          )}
        </button>
      )}
    </div>
  )
}
