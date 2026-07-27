"use client"

import { Link, useNavigate } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowUp,
  Paperclip,
  FileText,
  Mic2,
  Palette,
  SlidersHorizontal,
  ChevronDown,
  Check,
  Sparkles,
  User,
  Video,
  Image as ImageIcon,
} from "lucide-react"

import { apiFetch } from "@/lib/api"
import { toast } from "sonner"
import { useAuth } from "@/components/AuthProvider"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  SpeakerPickerModal,
  type SpeakerPickerEntry,
} from "@/components/home/SpeakerPickerModal"
import { AssetsModal } from "@/components/home/AssetsModal"
import { Tour, type TourStep } from "@/components/ui/tour"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

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
}

const AUTO_GENERATE = "__auto_generate__"

/** First-visit composer tour: seen flag lives in localStorage (same
 * `repurposer-*` key family as theme/lang). Written on complete AND skip. */
const TOUR_SEEN_KEY = "repurposer-tour-seen"

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
}: HomeComposerProps) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { requireAuth } = useAuth()

  const [prompt, setPrompt] = useState("")
  const [speakerId, setSpeakerId] = useState(AUTO_GENERATE)
  const [brandTemplateId, setBrandTemplateId] = useState("")
  const [files, setFiles] = useState<File[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [speakerPickerOpen, setSpeakerPickerOpen] = useState(false)
  const [assetsOpen, setAssetsOpen] = useState(false)
  const [tourOpen, setTourOpen] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // First-visit teaching: open the composer tour once per browser. Read in
  // an effect only — localStorage is never touched during SSR.
  useEffect(() => {
    try {
      if (!window.localStorage.getItem(TOUR_SEEN_KEY)) setTourOpen(true)
    } catch {
      // storage unavailable (private mode) — tour simply never auto-opens
    }
  }, [])

  const markTourSeen = () => {
    try {
      window.localStorage.setItem(TOUR_SEEN_KEY, "1")
    } catch {
      // ignore — worst case the tour shows again next visit
    }
  }

  // Sync brand default once templates load.
  useEffect(() => {
    setBrandTemplateId((prev) => prev || (brandTemplates[0]?.id ?? ""))
  }, [brandTemplates])

  const inferAssetType = (file: File): string => {
    if (file.type.startsWith("video/")) return "video"
    if (file.type.startsWith("audio/")) return "audio"
    if (file.type.startsWith("image/")) return "image"
    return "transcript"
  }

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
        const projectRes = await apiFetch("/api/v1/projects", {
          method: "POST",
          body: {
            title: files[0]?.name || prompt.slice(0, 60) || t("common.untitled"),
            event_name: "",
            speaker_id:
              speakerId === AUTO_GENERATE ? undefined : speakerId || undefined,
          },
        })
        if (!projectRes.ok) throw new Error("Failed to create project")
        const project = (await projectRes.json()) as Project

        const materials =
          files.length > 0 ? files : [new File([prompt], "prompt.txt", { type: "text/plain" })]
        await Promise.all(
          materials.map(async (material) => {
            const type = files.length > 0 ? inferAssetType(material) : "transcript"

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
              body: { type, key },
            })
            if (!assetRes.ok) throw new Error("Failed to create asset")
            return (await assetRes.json()) as Asset
          })
        )

        // Resolve the task book via the project-scoped intent endpoint. The
        // overlay on the results page will confirm or edit the inferred
        // outputs / language / clip_count before starting generation.
        const intentRes = await apiFetch(`/api/v1/projects/${project.id}/intent`, {
          method: "POST",
          body: { prompt: prompt.trim() },
        })
        if (!intentRes.ok) {
          const detail = await intentRes.json().catch(() => null)
          throw new Error(detail?.detail || "Intent inference failed")
        }
        const intentData = (await intentRes.json()) as {
          intent: {
            action: "generate" | "answer"
            answer: string | null
            language: string
            outputs: string[]
            clip_count: number | null
            specific_instruction: string | null
          }
          needs_clarification: boolean
        }

        sessionStorage.setItem(
          `repurposer-generation-${project.id}`,
          JSON.stringify({
            prompt: prompt.trim(),
            intent: intentData.intent,
            needsClarification: intentData.needs_clarification,
            brandTemplateId: brandTemplateId || undefined,
          })
        )

        navigate({
          to: "/projects/$id",
          params: { id: project.id },
          search: { overlay: "intent" },
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

  // Composer teaching tour: assets → speaker → prompt → send. Built per
  // render so a language switch re-labels the steps (Tour reads via ref).
  const tourSteps: TourStep[] = [
    {
      target: "[data-tour='composer-assets']",
      title: t("tour.composer.assetsTitle"),
      description: t("tour.composer.assetsDesc"),
      side: "bottom",
    },
    {
      target: "[data-tour='composer-speaker']",
      title: t("tour.composer.speakerTitle"),
      description: t("tour.composer.speakerDesc"),
      side: "bottom",
    },
    {
      target: "[data-tour='composer-prompt']",
      title: t("tour.composer.promptTitle"),
      description: t("tour.composer.promptDesc"),
      side: "bottom",
    },
    {
      target: "[data-tour='composer-send']",
      title: t("tour.composer.sendTitle"),
      description: t("tour.composer.sendDesc"),
      side: "top",
      align: "end",
    },
  ]

  return (
    <>
    <Card className="overflow-visible py-0 ring-0 edge-glow">
      <CardContent className="p-4 text-left">
        {/* Entity blocks (Assets = source materials, Speaker = whose voice)
            ride the card's top edge via negative margin; the textarea fills
            the remaining width to their right. Both blocks open modals. */}
        <div className="flex items-start gap-3">
          <div className="-mt-9 flex flex-shrink-0 items-start gap-2">
            {/* Assets block — Opus anatomy: icon at the top, spacer, then
                title with the info line at the very bottom. */}
            <button
              type="button"
              data-tour="composer-assets"
              onClick={() => setAssetsOpen(true)}
              className="relative flex h-24 w-20 flex-col rounded-lg bg-card p-2 text-left edge-glow transition-colors hover:bg-accent"
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

            {/* Speaker block — same anatomy: avatar/sparkle top, "Speaker"
                title, current value at the very bottom. */}
            <button
              type="button"
              data-tour="composer-speaker"
              onClick={() => setSpeakerPickerOpen(true)}
              className="flex h-24 w-20 flex-col rounded-lg bg-card p-2 text-left edge-glow transition-colors hover:bg-accent"
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

          <div className="flex h-20 flex-1 flex-col" data-tour="composer-prompt">
            <Textarea
              ref={textareaRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleGenerate()
                }
              }}
              placeholder={t("home.pastePlaceholder")}
              className="min-h-0 flex-1 resize-none border-0 bg-transparent p-2 text-base shadow-none focus-visible:ring-0 dark:bg-transparent"
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

            {/* AI model — display-only for now (single provider) */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto h-9 gap-1.5 rounded-md px-2 text-xs font-normal"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>{t("composer.aiModel")}</span>
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  </Button>
                }
              />
              <DropdownMenuContent align="start" className="w-56">
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="px-2 py-1.5">
                    <PillHeaderText
                      title={t("composer.aiModel")}
                      desc={t("composer.aiModelDesc")}
                    />
                  </DropdownMenuLabel>
                  <DropdownMenuItem>
                    <Sparkles className="mr-2 h-4 w-4 text-muted-foreground" />
                    <span className="flex-1">MiniMax M3</span>
                    <Check className="ml-2 h-4 w-4" />
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>

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
