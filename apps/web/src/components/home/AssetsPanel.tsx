"use client"

import { useRef } from "react"
import { useTranslation } from "react-i18next"
import { Plus, X } from "lucide-react"

import {
  ASSETS_ACCEPT,
  fileFormatLabel,
  fileIconFor,
  formatChipDuration,
  formatFileSize,
  useStagedFileMeta,
} from "@/lib/stagedFiles"

/** Assets picker panel — the frosted Popover the Assets pill opens
 * (side="bottom"). Picker weight, not manager: upload row + typed file rows
 * + ×; deep asset management belongs to a future asset-center page.
 * Row anatomy (the 2026-08-21 mock, promoted): a square typed tile (file
 * column = SQUARE, identity column stays round) + name / typed-meta two
 * lines + a vertically-centered ×. */
export function AssetsPanel({
  files,
  onAdd,
  onRemove,
}: {
  files: File[]
  onAdd: (picked: File[]) => void
  onRemove: (index: number) => void
}) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="flex flex-col gap-1">
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        accept={ASSETS_ACCEPT}
        onChange={(e) => {
          onAdd(Array.from(e.target.files ?? []))
          // Reset so picking the same file again after removal still fires.
          e.target.value = ""
        }}
      />

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="flex h-10 items-center justify-center gap-1.5 rounded-md border border-dashed border-foreground/15 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <Plus className="h-3.5 w-3.5" />
        <span className="text-xs">{t("composer.assetsUpload")}</span>
      </button>

      {files.length > 0 && (
        <div className="mt-1 flex max-h-56 flex-col gap-0.5 overflow-y-auto no-scrollbar">
          {files.map((file, index) => (
            <AssetPanelRow
              key={`${file.name}:${file.size}`}
              file={file}
              onRemove={() => onRemove(index)}
            />
          ))}
        </div>
      )}

      <p className="mt-1 px-0.5 text-[10px] leading-relaxed text-meta-foreground">
        {t("composer.assetsFormats")}
      </p>
    </div>
  )
}

function AssetPanelRow({ file, onRemove }: { file: File; onRemove: () => void }) {
  const { t } = useTranslation()
  const meta = useStagedFileMeta(file)
  const Icon = fileIconFor(file)
  const isVideo = file.type.startsWith("video/")
  const isAudio = file.type.startsWith("audio/")
  const isImage = file.type.startsWith("image/")

  // Typed meta line: AV = "Video · 12:34 · 480 MB" (duration joins when the
  // probe lands), image = "Image · 480 KB", doc = "PDF · 12 MB" (the format
  // ext is the informative bit — page counts would take pdf.js, never worth
  // a row).
  const size = formatFileSize(file.size)
  const metaLine =
    isVideo || isAudio
      ? [
          t(isVideo ? "composer.fileKinds.video" : "composer.fileKinds.audio"),
          meta.duration !== undefined ? formatChipDuration(meta.duration) : null,
          size,
        ]
          .filter(Boolean)
          .join(" · ")
      : isImage
        ? [t("composer.fileKinds.image"), size].join(" · ")
        : [fileFormatLabel(file), size].join(" · ")

  return (
    <div className="flex items-center gap-2.5 rounded-md px-1.5 py-1.5">
      {meta.thumbUrl ? (
        <img
          src={meta.thumbUrl}
          alt=""
          className="h-9 w-9 flex-none rounded-md object-cover"
        />
      ) : (
        <span className="flex h-9 w-9 flex-none items-center justify-center rounded-md bg-icon-chip">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-medium text-foreground">
          {file.name}
        </span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {metaLine}
        </span>
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="flex-none rounded-sm p-1 text-muted-foreground transition-colors hover:text-foreground"
        aria-label={`Remove ${file.name}`}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
