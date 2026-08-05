"use client"

import { Link, useNavigate } from "@tanstack/react-router"
import { useEffect, useMemo, useState, type RefObject } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowUp,
  BrainCircuit,
  Paperclip,
  FileText,
  Mic2,
  Palette,
  SlidersHorizontal,
  ChevronDown,
  Check,
  User,
  Video,
  Image as ImageIcon,
} from "lucide-react"

import { apiFetch } from "@/lib/api"
import { inferAssetType } from "@/lib/asset-type"
import { toast } from "sonner"
import { useAuth } from "@/components/AuthProvider"
import type { ChatMention } from "@/lib/mentions"
import {
  MentionEditor,
  type MentionEditorHandle,
} from "@/components/mentions/MentionEditor"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  SpeakerPickerModal,
  type SpeakerPickerEntry,
} from "@/components/home/SpeakerPickerModal"
import { AssetsModal } from "@/components/home/AssetsModal"
import { Tour, type TourStep } from "@/components/ui/tour"
import { tourCopy, tourVersionOf, type TourStepDef } from "@/lib/tour"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

type Speaker = SpeakerPickerEntry

interface BrandTemplate {
  id: string
  name: string
}

interface Asset {
  id: string
  type: string
  processing_status: "pending" | "processing" | "completed" | "failed"
  processing_error: string | null
}

interface Project {
  id: string
  title: string
  status: string
}

interface HomeComposerProps {
  speakers: Speaker[]
  brandTemplates: BrandTemplate[]
  onGenerateStart?: () => void
  /** The draft (prompt + mentions) is the editor's reported mirror — the DOM
   * owns the text (MentionEditor); Home keeps it only as the send payload
   * and so a card's Remix can act through `editorRef`. */
  prompt: string
  onPromptChange: (value: string) => void
  mentions: ChatMention[]
  onMentionsChange: (value: ChatMention[]) => void
  editorRef: RefObject<MentionEditorHandle | null>
}

const AUTO_GENERATE = "__auto_generate__"

/** First-visit composer tour: the seen flag stores the tour's content hash
 * (version = a pure function of content, lib/tour.ts) — any step or copy
 * change replays the tour exactly once per user, zero manual versioning.
 * Read/write inside effects only — localStorage is never touched during SSR. */
const TOUR_SEEN_KEY = "repurposer-tour-seen"

/** Composer teaching (4 steps): assets → speaker → prompt (send folded in)
 * → the recipe gallery as the alternative entry (lands last; Tour skips the
 * step if the cards haven't loaded yet). */
const COMPOSER_TOUR_STEPS: TourStepDef[] = [
  {
    target: "[data-tour='composer-assets']",
    titleKey: "tour.composer.assetsTitle",
    descKey: "tour.composer.assetsDesc",
    side: "bottom",
  },
  {
    target: "[data-tour='composer-speaker']",
    titleKey: "tour.composer.speakerTitle",
    descKey: "tour.composer.speakerDesc",
    side: "bottom",
  },
  {
    target: "[data-tour='composer-prompt']",
    titleKey: "tour.composer.promptTitle",
    descKey: "tour.composer.promptDesc",
    side: "bottom",
  },
  {
    target: "[data-tour='home-recipes']",
    titleKey: "tour.composer.recipesTitle",
    descKey: "tour.composer.recipesDesc",
    side: "top",
  },
]

const TOUR_VERSION = tourVersionOf(COMPOSER_TOUR_STEPS, tourCopy.composer)

/** Dropdown header: a short title plus a one-line explanation of what this
 * dimension controls, so first-time users understand the pill's purpose. */
function PillHeaderText({ title, desc }: { title: string; desc: string }) {
  return (
    <>
      <span className="block text-xs font-medium">{title}</span>
      <span className="mt-0.5 block text-[11px] font-normal leading-snug text-muted-foreground">
        {desc}
      </span>
    </>
  )
}

export function HomeComposer({
  speakers,
  brandTemplates,
  onGenerateStart,
  prompt,
  onPromptChange,
  mentions,
  onMentionsChange,
  editorRef,
}: HomeComposerProps) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { requireAuth } = useAuth()

  const [speakerId, setSpeakerId] = useState(AUTO_GENERATE)
  const [brandTemplateId, setBrandTemplateId] = useState("")
  const [files, setFiles] = useState<File[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [speakerPickerOpen, setSpeakerPickerOpen] = useState(false)
  const [assetsOpen, setAssetsOpen] = useState(false)
  const [tourOpen, setTourOpen] = useState(false)

  // First-visit teaching: open the composer tour once per tour version. Read
  // in an effect only — localStorage is never touched during SSR.
  useEffect(() => {
    try {
      if (window.localStorage.getItem(TOUR_SEEN_KEY) !== TOUR_VERSION)
        setTourOpen(true)
    } catch {
      // storage unavailable (private mode) — tour simply never auto-opens
    }
  }, [])

  const markTourSeen = () => {
    try {
      window.localStorage.setItem(TOUR_SEEN_KEY, TOUR_VERSION)
    } catch {
      // ignore — worst case the tour shows again next visit
    }
  }

  // Sync brand default once templates load.
  useEffect(() => {
    setBrandTemplateId((prev) => prev || (brandTemplates[0]?.id ?? ""))
  }, [brandTemplates])

  const fileIconFor = (file: File) => {
    if (file.type.startsWith("video/")) return Video
    if (file.type.startsWith("audio/")) return Mic2
    if (file.type.startsWith("image/")) return ImageIcon
    return FileText
  }

  const addFiles = (picked: File[]) => {
    if (picked.length === 0) return
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}:${f.size}`))
      const additions = picked.filter((f) => !existing.has(`${f.name}:${f.size}`))
      return [...prev, ...additions]
    })
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  // The asset mention's candidate feed (memoized — the picker reloads when
  // the identity changes, so it must track `files`, not renders).
  const mentionContext = useMemo(
    () => ({ files: files.map((f) => ({ name: f.name, type: f.type })) }),
    [files],
  )

  // Mention chip laws (docs/tasks/recipe-mention.md §2.4): visible (inline
  // chip in the sentence, MentionEditor), consumed on send (handleGenerate
  // clears the draft on success, before navigating), × purifies (removing
  // the chip removes every trace — no residual pin).

  const handleGenerate = async () => {
    await requireAuth(async () => {
      // Prompt is required — the pipeline's intent step derives the task
      // book (outputs / language / clip count) from it server-side.
      if (!prompt.trim()) {
        toast.error(t("home.noPromptError"))
        return
      }
      setIsGenerating(true)
      onGenerateStart?.()
      try {
        // Project title = a 15-char split of the user's prompt + "…" — the
        // chat-app convention (a conversation is named from the user's own
        // words), NEVER the material's filename.
        const promptLine = prompt.trim().replace(/\s+/g, " ")
        const title =
          (promptLine.length > 15 ? `${promptLine.slice(0, 15)}…` : promptLine) ||
          t("common.untitled")
        const projectRes = await apiFetch("/api/v1/projects", {
          method: "POST",
          body: {
            title,
            event_name: "",
            speaker_id:
              speakerId === AUTO_GENERATE ? undefined : speakerId || undefined,
          },
        })
        if (!projectRes.ok) throw new Error("Failed to create project")
        const project = (await projectRes.json()) as Project

        // Only real user files upload. A prompt-only send creates NO fake
        // "prompt.txt" transcript asset (retired 2026-08-05 shim): the prompt
        // travels as the first chat message, and declaring pasted text as
        // source material ("this is my transcript: …") is recognized
        // server-side in the chat plan path, which promotes it to a proper
        // transcript asset.
        await Promise.all(
          files.map(async (material) => {
            const type = inferAssetType(material)

            const urlRes = await apiFetch(`/api/v1/projects/${project.id}/assets/upload-url`, {
              method: "POST",
              body: {
                filename: material.name,
                content_type: material.type || undefined,
              },
            })
            if (!urlRes.ok) throw new Error("Failed to get upload URL")
            const { key, upload_url } = (await urlRes.json()) as {
              key: string
              upload_url: string
            }

            const putRes = await fetch(upload_url, {
              method: "PUT",
              body: material,
              headers: material.type ? { "Content-Type": material.type } : {},
            })
            // Direct-to-storage PUT bypasses apiFetch, so toast here.
            if (!putRes.ok) {
              toast.error(t("composer.uploadFailed"))
              throw new Error("Failed to upload file")
            }

            const assetRes = await apiFetch(`/api/v1/projects/${project.id}/assets`, {
              method: "POST",
              body: { type, key, title: material.name },
            })
            if (!assetRes.ok) throw new Error("Failed to create asset")
            return (await assetRes.json()) as Asset
          })
        )

        // Intent recognition lives in the chat loop, not the composer
        // (intent-surface-unification W2): navigate straight to the project
        // and hand the draft to the overlay chat, which sends it as the
        // first /chat message — mentions and the brand choice ride along.
        // A recipe mention is pinned server-side in the plan path
        // (resolve_recipe_mentions) — the composer never builds a prior
        // (docs/tasks/recipe-mention.md, prohibition #1).
        // Send consumes the draft (chip law ②): one clear, before navigating.
        editorRef.current?.clear()

        navigate({
          to: "/projects/$id",
          params: { id: project.id },
          search: { overlay: "chat" },
          state: {
            firstMessage: {
              text: prompt.trim(),
              mentions,
              brandTemplateId: brandTemplateId || undefined,
            },
          } as Record<string, unknown>,
        })
      } catch {
        // apiFetch already toasted the server's reason; just reset the UI.
        setIsGenerating(false)
      }
    })
  }

  const selectedSpeaker =
    speakerId === AUTO_GENERATE
      ? undefined
      : speakers.find((s) => s.id === speakerId)

  // Composer teaching tour: built per render from the static config so a
  // language switch re-labels the steps (Tour reads via ref).
  const tourSteps: TourStep[] = COMPOSER_TOUR_STEPS.map((step) => ({
    target: step.target,
    side: step.side,
    align: step.align,
    title: t(step.titleKey),
    description: t(step.descKey),
  }))

  return (
    <>
    {/* Dark mode: flat tonal steps instead of edge-glow — card 0.195,
        blocks 0.25 (D2 recipe). Light mode keeps edge-glow. */}
    <Card className="overflow-visible rounded-2xl py-0 ring-0 edge-glow dark:bg-[oklch(0.195_0.006_260)] dark:shadow-none">
      <CardContent className="p-5 text-left">
        {/* Entity blocks (Assets = source materials, Speaker = whose voice)
            ride the card's top edge via negative margin; the textarea fills
            the remaining width to their right. Both blocks open modals. */}
        <div className="flex items-start gap-3">
          <div className="-mt-9 flex flex-shrink-0 items-start gap-2">
            {/* Assets block — Opus anatomy: icon at the top, spacer, then
                title with the info line at the very bottom. Hover = a lift of
                the SAME color family (dark: lighter shade of the block's own
                hue), never an accent hop — a different hue reads muddy. */}
            <button
              type="button"
              data-tour="composer-assets"
              onClick={() => setAssetsOpen(true)}
              className="relative flex h-24 w-20 flex-col rounded-lg bg-card p-2 text-left edge-glow transition-colors hover:bg-accent dark:bg-[oklch(0.25_0.008_260)] dark:shadow-none dark:hover:bg-[oklch(0.31_0.008_260)]"
            >
              {files.length === 0 ? (
                <Paperclip className="h-4 w-4 text-muted-foreground" />
              ) : (
                (() => {
                  const Icon = fileIconFor(files[0])
                  return <Icon className="h-4 w-4 text-muted-foreground" />
                })()
              )}
              <span className="mt-auto">
                <span className="block text-xs">{t("composer.assets")}</span>
                <span className="block text-[10px] text-muted-foreground">
                  {files.length === 0
                    ? t("composer.optional")
                    : t("composer.assetsCount", { count: files.length })}
                </span>
              </span>
            </button>

            {/* Speaker block — same anatomy: avatar/user-icon top, "Speaker"
                title, current value at the very bottom. */}
            <button
              type="button"
              data-tour="composer-speaker"
              onClick={() => setSpeakerPickerOpen(true)}
              className="flex h-24 w-20 flex-col rounded-lg bg-card p-2 text-left edge-glow transition-colors hover:bg-accent dark:bg-[oklch(0.25_0.008_260)] dark:shadow-none dark:hover:bg-[oklch(0.31_0.008_260)]"
            >
              {selectedSpeaker ? (
                <Avatar size="sm">
                  {selectedSpeaker.avatar_url ? (
                    <AvatarImage
                      src={selectedSpeaker.avatar_url}
                      alt={selectedSpeaker.name}
                    />
                  ) : null}
                  <AvatarFallback>{selectedSpeaker.name.slice(0, 1)}</AvatarFallback>
                </Avatar>
              ) : (
                <User className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="mt-auto min-w-0">
                <span className="block text-xs">{t("composer.speaker")}</span>
                <span className="block truncate text-[10px] text-muted-foreground">
                  {selectedSpeaker ? selectedSpeaker.name : t("composer.autoGenerate")}
                </span>
              </span>
            </button>
          </div>

          <div className="relative flex h-24 flex-1 flex-col" data-tour="composer-prompt">
            <MentionEditor
              ref={editorRef}
              placeholder={t("home.pastePlaceholder")}
              disabled={isGenerating}
              mentionContext={mentionContext}
              onChange={(text, ms) => {
                onPromptChange(text)
                onMentionsChange(ms)
              }}
              onSubmit={handleGenerate}
            />
          </div>
        </div>

        {/* One continuous bottom row: brand on the left, provider + send on
            the right — no separate action-bar strip. */}
        <div className="mt-2 flex items-center gap-2">
            {/* Brand template */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <Palette className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="max-w-[120px] truncate">
                      {brandTemplates.find((b) => b.id === brandTemplateId)?.name ??
                        t("composer.brandDefault")}
                    </span>
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  </Button>
                }
              />
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="px-2 py-1.5">
                    <PillHeaderText
                      title={t("composer.brandLabel")}
                      desc={t("composer.brandDesc")}
                    />
                  </DropdownMenuLabel>
                  {brandTemplates.map((b) => (
                    <DropdownMenuItem
                      key={b.id}
                      onClick={() => setBrandTemplateId(b.id)}
                    >
                      <Palette className="mr-2 h-4 w-4 text-muted-foreground" />
                      <span className="flex-1 truncate">{b.name}</span>
                      {b.id === brandTemplateId && <Check className="ml-2 h-4 w-4" />}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
                <DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem render={<Link to="/brand-template" />}>
                    <SlidersHorizontal className="mr-2 h-4 w-4" />
                    {t("composer.manageBrand")}
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* AI model — display-only (single provider): hover reveals the
                provider breakdown. A picker lands only when a real second
                provider exists (provider abstraction, PROGRESS 需求池). */}
            <Popover>
              <PopoverTrigger
                openOnHover
                delay={150}
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto h-9 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <BrainCircuit className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{t("composer.aiModel")}</span>
                  </Button>
                }
              />
              <PopoverContent side="top" align="end" className="w-64 ring-0 shadow-xl dark:bg-white/10">
                <div className="flex flex-col gap-1.5 px-0.5 pb-0.5">
                  {(
                    [
                      [t("composer.aiModelRowText"), "MiniMax M3"],
                      [t("composer.aiModelRowVoice"), "MiniMax T2A"],
                      [t("composer.aiModelRowVisual"), "MiniMax"],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground">{label}</span>
                      <span>{value}</span>
                    </div>
                  ))}
                </div>
              </PopoverContent>
            </Popover>

            <Button
              className="h-9 w-9 rounded-full"
              size="icon"
              data-tour="composer-send"
              disabled={isGenerating}
              onClick={handleGenerate}
            >
              {isGenerating ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </Button>
          </div>
      </CardContent>
    </Card>

    <SpeakerPickerModal
      speakers={speakers}
      value={speakerId}
      autoValue={AUTO_GENERATE}
      onSelect={setSpeakerId}
      open={speakerPickerOpen}
      onOpenChange={setSpeakerPickerOpen}
    />
    <AssetsModal
      files={files}
      onAdd={addFiles}
      onRemove={removeFile}
      open={assetsOpen}
      onOpenChange={setAssetsOpen}
    />
    <Tour
      steps={tourSteps}
      open={tourOpen}
      onOpenChange={setTourOpen}
      onComplete={markTourSeen}
      onSkip={markTourSeen}
    />
    </>
  )
}
