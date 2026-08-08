"use client"

import { useRef } from "react"
import { useTranslation } from "react-i18next"
import {
  FileText,
  Mic2,
  Plus,
  Video,
  Image as ImageIcon,
  X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

// Videos / audio / images / transcripts & docs — the three input tiers
// ("bring whatever you have"): recording, audio-only, or transcript + photos.
export const ASSETS_ACCEPT =
  ".mp4,.mov,.webm,.mp3,.wav,.m4a,.png,.jpg,.jpeg,.webp,.txt,.md,.pdf,.doc,.docx,.srt,.vtt"

interface AssetsModalProps {
  files: File[]
  onAdd: (picked: File[]) => void
  onRemove: (index: number) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

function fileIconFor(file: File) {
  if (file.type.startsWith("video/")) return Video
  if (file.type.startsWith("audio/")) return Mic2
  if (file.type.startsWith("image/")) return ImageIcon
  return FileText
}

/** Upload + manage the composer's source materials. All asset content lives
 * here — the composer block only shows a count/preview summary. */
export function AssetsModal({ files, onAdd, onRemove, open, onOpenChange }: AssetsModalProps) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onAdd(Array.from(e.target.files ?? []))
    // Reset so picking the same file again after removal still fires onChange.
    e.target.value = ""
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("composer.assetsModalTitle")}</DialogTitle>
          <DialogDescription>{t("composer.assetsFormats")}</DialogDescription>
        </DialogHeader>

        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          accept={ASSETS_ACCEPT}
          onChange={handleChange}
        />

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex h-24 w-full flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Plus className="h-5 w-5" />
          <span className="text-xs">{t("composer.assetsUpload")}</span>
        </button>

        {files.length > 0 && (
          <div className="grid max-h-[50vh] grid-cols-3 gap-2 overflow-y-auto p-1.5">
            {files.map((file, index) => {
              const Icon = fileIconFor(file)
              return (
                <div
                  key={`${file.name}:${file.size}`}
                  className="relative flex flex-col items-center gap-1.5 rounded-lg bg-muted p-3 text-center"
                >
                  <button
                    type="button"
                    onClick={() => onRemove(index)}
                    className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-muted text-muted-foreground hover:bg-destructive hover:text-destructive-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                  <Icon className="h-5 w-5 text-muted-foreground" />
                  <span className="w-full truncate text-[11px] leading-tight text-muted-foreground">
                    {file.name}
                  </span>
                </div>
              )
            })}
          </div>
        )}

        <div className="flex justify-end">
          <Button size="sm" className="h-9" onClick={() => onOpenChange(false)}>
            {t("composer.apply")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
