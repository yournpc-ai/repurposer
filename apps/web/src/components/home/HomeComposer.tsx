"use client"

import { Link, useNavigate } from "@tanstack/react-router"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  ArrowUp,
  Plus,
  FileText,
  Mic2,
  Palette,
  SlidersHorizontal,
  ChevronDown,
  Check,
  Sparkles,
  Video,
  Image as ImageIcon,
} from "lucide-react"

import { apiFetch } from "@/lib/api"
import { toast } from "sonner"
import { useAuth } from "@/components/AuthProvider"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  SpeakerPickerModal,
  type SpeakerPickerEntry,
} from "@/components/home/SpeakerPickerModal"
import { AssetsModal } from "@/components/home/AssetsModal"
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

  const textareaRef = useRef<HTMLTextAreaElement>(null)

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

        // The task book (outputs / language / clip_count) is derived by the
        // pipeline's intent step — the composer sends only the instruction.
        const generateRes = await apiFetch(`/api/v1/projects/${project.id}/generate`, {
          method: "POST",
          body: {
            brand_template_id: brandTemplateId || undefined,
            instruction: prompt.trim(),
          },
        })
        if (!generateRes.ok) {
          const detail = await generateRes.json().catch(() => null)
          throw new Error(detail?.detail || "Generation failed")
        }

        navigate({ to: "/projects/$id", params: { id: project.id } })
      } catch {
        // apiFetch already toasted the server's reason; just reset the UI.
        setIsGenerating(false)
      }
    })
  }

  // First-file preview for the Assets block: object URL for image/video,
  // type icon otherwise. URLs are revoked when the preview changes/unmounts.
  const firstFile = files[0]
  const firstPreviewUrl = useMemo(() => {
    if (!firstFile) return null
    if (firstFile.type.startsWith("image/") || firstFile.type.startsWith("video/")) {
      return URL.createObjectURL(firstFile)
    }
    return null
  }, [firstFile])
  useEffect(() => {
    return () => {
      if (firstPreviewUrl) URL.revokeObjectURL(firstPreviewUrl)
    }
  }, [firstPreviewUrl])

  const selectedSpeaker =
    speakerId === AUTO_GENERATE
      ? undefined
      : speakers.find((s) => s.id === speakerId)

  return (
    <>
    <Card className="overflow-visible py-0 ring-0 edge-glow">
      <CardContent className="p-4 text-left">
        {/* Entity blocks (Assets = source materials, Speaker = whose voice)
            ride the card's top edge via negative margin; the textarea fills
            the remaining width to their right. Both blocks open modals. */}
        <div className="flex items-start gap-3">
          <div className="-mt-12 flex flex-shrink-0 items-start gap-2">
            {/* Assets block */}
            <button
              type="button"
              onClick={() => setAssetsOpen(true)}
              className="relative flex h-24 w-20 flex-col rounded-lg bg-card p-1.5 text-left edge-glow transition-colors hover:bg-accent"
            >
              <span className="flex items-center justify-between px-0.5 pb-1">
                <span className="text-[10px] leading-none text-muted-foreground">
                  {t("composer.assets")}
                </span>
                {files.length > 0 && (
                  <Badge variant="secondary" className="rounded-md px-1 text-[10px]">
                    {files.length}
                  </Badge>
                )}
              </span>
              {files.length === 0 ? (
                <span className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 rounded-md border border-dashed text-muted-foreground">
                  <Plus className="h-4 w-4" />
                  <span className="text-[10px] leading-none">{t("composer.optional")}</span>
                </span>
              ) : firstPreviewUrl && firstFile.type.startsWith("image/") ? (
                <img
                  src={firstPreviewUrl}
                  alt={firstFile.name}
                  className="min-h-0 w-full flex-1 rounded-md object-cover"
                />
              ) : firstPreviewUrl ? (
                <video
                  src={firstPreviewUrl}
                  muted
                  preload="metadata"
                  className="min-h-0 w-full flex-1 rounded-md object-cover"
                />
              ) : (
                <span className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 text-muted-foreground">
                  {(() => {
                    const Icon = fileIconFor(firstFile)
                    return <Icon className="h-5 w-5" />
                  })()}
                  <span className="max-w-full truncate px-0.5 text-[10px] leading-tight">
                    {firstFile.name}
                  </span>
                </span>
              )}
            </button>

            {/* Speaker block */}
            <button
              type="button"
              onClick={() => setSpeakerPickerOpen(true)}
              className="flex h-24 w-24 flex-col rounded-lg bg-card p-1.5 text-left edge-glow transition-colors hover:bg-accent"
            >
              <span className="px-0.5 text-[10px] leading-none text-muted-foreground">
                {t("composer.speaker")}
              </span>
              <span className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1.5">
                {selectedSpeaker ? (
                  <>
                    <Avatar size="sm">
                      {selectedSpeaker.avatar_url ? (
                        <AvatarImage
                          src={selectedSpeaker.avatar_url}
                          alt={selectedSpeaker.name}
                        />
                      ) : null}
                      <AvatarFallback>{selectedSpeaker.name.slice(0, 1)}</AvatarFallback>
                    </Avatar>
                    <span className="flex w-full items-center justify-center gap-0.5 px-0.5">
                      <span className="truncate text-xs">{selectedSpeaker.name}</span>
                      {selectedSpeaker.voice ? (
                        <Mic2 className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
                      ) : null}
                    </span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 text-muted-foreground" />
                    <span className="max-w-full truncate px-0.5 text-xs">
                      {t("composer.autoGenerate")}
                    </span>
                  </>
                )}
              </span>
            </button>
          </div>

          <div className="flex h-20 flex-1 flex-col">
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
    </>
  )
}
