"use client"

import { useEffect, useMemo, useRef, useState, type DragEvent } from "react"
import { useTranslation } from "react-i18next"
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"
import {
  FileText,
  Headphones,
  Image as ImageIcon,
  Music,
  Presentation,
  Upload,
  Video,
  Volume2,
  VolumeX,
  X,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { FlowView } from "@/components/flow/FlowView"
import { useProjectLaunch } from "@/lib/useProjectLaunch"
import { slotCoversFile, type RecipePublic } from "@/lib/recipes"
import { ASSETS_ACCEPT } from "@/lib/stagedFiles"
import { Badge } from "@/components/ui/badge"
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
import { Textarea } from "@/components/ui/textarea"

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
 * popup is composed by hand (`inset-0 m-auto` centering) because the
 * split-pane size (max-w-7xl, full-height flex) doesn't fit DialogContent's
 * defaults — and a hand-composed popup must mirror DialogContent chrome
 * exactly (the CLAUDE.md rule): overlay-surface (whisper shadow baked in) + hairline +
 * rounded-xl.
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
 * the sentence nor the wire: the template IS the entire launch payload
 * (2026-08-11 ruling — 配方 = 提示词). The only edit entry stays the
 * prompt text (before send) / chat (after send); chat always wins.
 */
export function RecipeInspectOverlay({
  card,
  onClose,
}: {
  card: RecipePublic
  onClose: () => void
}) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)
  const { launching, launch } = useProjectLaunch()

  const title = t(`recipes.${card.id}.title`)
  const template = t(`recipes.${card.id}.promptTemplate`)

  // The draft: the template as plain editable text. The recipe's identity
  // stays frontend-local — no chip row, no wire field (the template text
  // already says everything; a repetition is noise).
  const [prompt, setPrompt] = useState(template)
  const [files, setFiles] = useState<File[]>([])

  // Inspect tabs (right zone): 示例 = flat cards; 流程 = the one canvas.
  const [tab, setTab] = useState<"examples" | "flow">("examples")
  // The one card currently sounding (autoplay is muted; the toggle circle
  // unmutes one card at a time — the home gallery's pattern).
  const [soundingId, setSoundingId] = useState<string | null>(null)

  // Text-tribe examples (RECIPES §4.6, 2026-08-24): the writer lands JSON
  // under demo/outputs/<stem>-<hash>.json — a textarea for the social-post
  // body, stacked slide cards for carousel. Quote-cards ships an actual PNG
  // poster so its example stays an `<img>`. Fetching is gated on the card
  // id so the other cards don't pay the round-trip.
  const socialPostUrl =
    card.id === "social-post" ? card.example_outputs[0]?.url ?? null : null
  const carouselUrl =
    card.id === "carousel" ? card.example_outputs[0]?.url ?? null : null
  const [socialPost, setSocialPost] = useState<SocialPostPayload | null>(null)
  const [carousel, setCarousel] = useState<CarouselPayload | null>(null)

  useEffect(() => {
    if (!socialPostUrl) {
      setSocialPost(null)
      return
    }
    let alive = true
    fetch(socialPostUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: SocialPostPayload) => {
        if (alive) setSocialPost(d)
      })
      .catch(() => {
        if (alive) setSocialPost(null)
      })
    return () => {
      alive = false
    }
  }, [socialPostUrl])

  useEffect(() => {
    if (!carouselUrl) {
      setCarousel(null)
      return
    }
    let alive = true
    fetch(carouselUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: CarouselPayload) => {
        if (alive) setCarousel(d)
      })
      .catch(() => {
        if (alive) setCarousel(null)
      })
    return () => {
      alive = false
    }
  }, [carouselUrl])

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
  // recipe's identity stays in this overlay (配方 = 提示词).
  // The recipe's required input slots are the launch gate (input_slots is
  // the card's declared blank): a required type with no staged file blocks
  // the send with a toast — same posture as the composer's empty prompt.
  const handleLaunch = () => {
    const uncovered = card.input_slots.some(
      (slot) => slot.required && !files.some((f) => slotCoversFile(slot.type, f))
    )
    if (uncovered) {
      toast.error(
        t("recipes.inspect.requiredMissing", {
          input: t(`recipes.${card.id}.inputTitle`),
        })
      )
      return
    }
    launch({ prompt, mentions: [], files })
  }

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
        {/* Hand-composed popup (custom split-pane size, `inset-0 m-auto`
            centering). All chrome comes from the **single global utility**
            `overlay-surface` (CLAUDE.md "Floating Layers"): it bundles the
            92% white wash + 24px backdrop-blur + the whisper shadow under
            one name. Hand-composed popups stack the structural bits only
            (positioning + the ring hairline that DialogContent also has):
              rounded-xl + ring-1 ring-foreground/10 — DialogContent's
                                                          chrome mirrored
                                                          (without the
                                                          hairline the
                                                          light glass
                                                          dissolves into
                                                          the backdrop
                                                          wash, per the
                                                          2026-08-10
                                                          precedent).
            No `shadow-xl` here — the utility already carries box-shadow. */}
        <DialogPrimitive.Popup
          className="overlay-surface fixed inset-0 z-50 m-auto flex h-[92vh] w-[calc(100%-2rem)] max-w-7xl flex-col overflow-hidden rounded-xl text-popover-foreground ring-1 ring-foreground/10 outline-none duration-100 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95 md:h-[84vh]"
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
                {/* Applied-tool annotation (2026-08-12 ruling): the registry's
                    curated capability tags as chips — facts, not adjectives. */}
                {card.tags.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {card.tags.map((tag) => (
                      <Badge
                        key={tag}
                        variant="secondary"
                        className="rounded-md"
                      >
                        {t(`recipes.tags.${tag}`)}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              {/* The material ask (ElevenCreative modal pattern 2026-08-10):
                  an Input section names what the recipe needs in plain words;
                  the dropzone copy itself stays generic. */}
              <div>
                <p className="flex items-center gap-1.5 text-sm font-medium">
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
                <p className="text-sm font-medium">
                  {t("recipes.inspect.promptTitle")}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t(`recipes.${card.id}.promptHint`)}
                </p>
              </div>

              <div className="flex h-36 flex-col gap-1.5 rounded-lg bg-inset p-2.5">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  disabled={launching}
                  placeholder={t("home.pastePlaceholder")}
                  className="min-h-0 w-full flex-1 resize-none self-stretch bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                />
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

            {/* RIGHT — top/bottom stacked layout (2026-08-24, was a floating
                tabs + opaque strip that overlapped scrolling content):
                the right pane is a flex-col — TabsList at the top in
                normal flow (no absolute positioning, no overlay strip,
                no z-index dance), TabsContent takes the remaining height
                and scrolls on its own. The dialog-level X close button
                sits over the tabs row, no longer needs a strip to sit
                on — the tabs row is its own opaque band in the canvas.
                The /10 hairline on the left seam carries the column
                separation; the canvas itself stays transparent (the
                overlay-surface blur shows through). */}
            <div className="relative min-h-0 flex-1 border-foreground/10 border-t md:border-l md:border-t-0">
              <Tabs
                value={tab}
                onValueChange={(v) => setTab(v as "examples" | "flow")}
                className="flex h-full min-h-0 flex-col"
              >
                <TabsList
                  variant="line"
                  className="shrink-0 gap-2 px-6 pt-4 pb-3"
                  style={{ height: "auto" }}
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
                  className="min-h-0 flex-1 overflow-y-auto px-6 pb-6 md:h-auto"
                >
                  <div className="flex flex-col gap-8">
                    {card.example_outputs.length > 0 && (
                      <section aria-label={t("recipes.inspect.sections.outputs")}>
                        <p className="text-meta mb-3">
                          {t("recipes.inspect.sections.outputs")}
                        </p>
                        {card.id === "social-post" ? (
                          // Writer output is plain text + hashtags. Render as
                          // a readonly textarea so the user reads the post
                          // the way it would actually appear on social —
                          // paragraphs preserved, hashtags inlined (the
                          // upstream writer is Markdown-free; social
                          // platforms render **bold** etc. as raw source).
                          socialPost ? (
                            <Textarea
                              readOnly
                              value={[
                                socialPost.content,
                                ...(socialPost.hashtags ?? []).map(
                                  (h) => `#${h}`,
                                ),
                              ].join("\n\n")}
                              className="min-h-[200px] resize-none text-sm leading-relaxed"
                            />
                          ) : null
                        ) : card.id === "carousel" ? (
                          // Carousel has no render-side product — the
                          // writer drops N slide cards as JSON. Show them
                          // stacked so the user reads the deck top-to-
                          // bottom in the same order it'll post.
                          carousel ? (
                            <div className="flex flex-col gap-3">
                              {carousel.slides.map((s, i) => (
                                <div
                                  key={i}
                                  className="rounded-lg bg-card p-4 ring-1 ring-foreground/10"
                                >
                                  <p className="text-meta mb-2 text-muted-foreground">
                                    {i + 1} / {carousel.slides.length}
                                  </p>
                                  <p className="font-medium leading-snug">
                                    {s.title}
                                  </p>
                                  {s.body ? (
                                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                                      {s.body}
                                    </p>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          ) : null
                        ) : card.id === "quote-cards" &&
                          card.example_outputs[0]?.poster_url ? (
                          // Quote-cards has a real PNG poster (the writer
                          // bakes the first quote card as the thumbnail).
                          // Render it as an `<img>` — the poster IS the
                          // product's look; we don't need to redraw the
                          // cards from JSON. (The other four quotes still
                          // ride inside the JSON for the live run.)
                          <img
                            src={card.example_outputs[0].poster_url}
                            alt={
                              materialLabel(
                                card.example_outputs[0].label_key,
                              ) ?? ""
                            }
                            className="aspect-square w-full max-w-md rounded-lg bg-card object-cover ring-1 ring-foreground/10"
                          />
                        ) : (
                          // Default: video / image outputs (reframe,
                          // highlight-clips, voice-dub, etc.).
                          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                            {card.example_outputs.map((o, i) => (
                              <ExampleCard
                                key={`output:${i}`}
                                id={`output:${i}`}
                                kind={o.kind}
                                url={o.url}
                                poster={o.poster_url ?? null}
                                label={materialLabel(o.label_key) ?? o.kind}
                                aspect={card.aspect}
                                sounding={soundingId === `output:${i}`}
                                onToggleSound={(id) =>
                                  setSoundingId((prev) =>
                                    prev === id ? null : id,
                                  )
                                }
                              />
                            ))}
                          </div>
                        )}
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

                <TabsContent value="flow" className="min-h-0 flex-1 md:h-auto">
                  {process.nodes.length > 0 && (
                    <FlowView
                      nodes={process.nodes}
                      edges={process.edges}
                      groups={process.groups}
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
 * gallery's sound-toggle circle (one card sounds at a time). OUTPUT cards
 * take the card's declared aspect (2026-08-14 三档画幅 — a recipe shows the
 * frame it bakes: vertical, square, or landscape); INPUT cards stay 16:9 —
 * the source material is not the product, the wide thumb reads best. */
function ExampleCard({
  id,
  kind,
  url,
  poster,
  label,
  aspect = "16:9",
  sounding,
  onToggleSound,
}: {
  id: string
  kind: string
  url: string
  poster: string | null
  label: string
  aspect?: string
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

  const aspectClass =
    aspect === "9:16"
      ? "aspect-[9/16]"
      : aspect === "1:1"
        ? "aspect-square"
        : "aspect-video"

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-lg bg-black",
        aspectClass,
      )}
    >
      {kind === "video" ? (
        <video
          ref={videoRef}
          src={url}
          poster={poster ?? undefined}
          className="h-full w-full object-contain"
          autoPlay
          muted
          loop
          playsInline
        />
      ) : kind === "transcript" ||
        kind === "slides" ||
        kind === "audio" ? (
        /* Documents aren't renderable media — a quiet icon tile carries the
           label (per-kind icon so users read what kind of file it is at a
           glance: transcript→doc, slides→deck, audio→waveform; the label
           pill below names the file kind). */
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="flex h-full w-full flex-col items-center justify-center gap-2 bg-muted text-muted-foreground transition-colors hover:bg-accent"
        >
          {kind === "audio" ? (
            <Headphones className="h-6 w-6" />
          ) : kind === "slides" ? (
            <Presentation className="h-6 w-6" />
          ) : (
            <FileText className="h-6 w-6" />
          )}
          <span className="max-w-[85%] truncate text-xs">{url.split("/").pop()}</span>
        </a>
      ) : (
        <img src={url} alt={label} className="h-full w-full object-contain" />
      )}

      {/* The label pill's white veil only works over media (dark imagery);
          on the document tile's light muted fill it washes out — there the
          label is plain meta text directly on the tile (fill-first). */}
      {kind === "transcript" ||
      kind === "slides" ||
      kind === "audio" ? (
        <span className="absolute bottom-2 left-2 px-2 py-0.5 text-xs text-muted-foreground">
          {label}
        </span>
      ) : (
        <span className="absolute bottom-2 left-2 rounded-md bg-white/15 px-2 py-0.5 text-xs text-white backdrop-blur-sm">
          {label}
        </span>
      )}

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

/** Text-tribe writer output payloads (RECIPES §4.6, 2026-08-24): the bake
 * drops the writer's structured result at demo/outputs/<stem>-<hash>.json.
 * Type mirrors the writer schemas — content / hashtags for posts, slides
 * for carousels. Quote-cards ships an actual PNG poster, no JSON fetch. */
type SocialPostPayload = { content: string; hashtags?: string[] }
type CarouselPayload = { slides: { title: string; body?: string }[] }
