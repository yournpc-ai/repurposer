"use client"

import { Loader2, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import {
  fileFormatLabel,
  fileIconFor,
  formatChipDuration,
  useStagedFileMeta,
} from "@/lib/stagedFiles"
import type { StagingUpload } from "@/lib/stagingUploads"

/** Staged asset chips — the composer's TOP band (the "what I have" list
 * reads above the "what I want" text). Typed anatomy: video = thumbnail
 * sliver + duration, audio = waveform-family icon + duration, image =
 * thumbnail, doc/slides = icon tile + format label; × removes the file.
 * Batch A lifecycle (2026-09-18): each chip carries its upload state —
 * uploading = spinner + real %, error = a retry affordance, done = the
 * typed meta label as before. */
export function AssetChips({
  items,
  onRemove,
  onRetry,
}: {
  items: StagingUpload[]
  onRemove: (item: StagingUpload) => void
  onRetry: (item: StagingUpload) => void
}) {
  if (items.length === 0) return null
  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {items.map((item) => (
        <AssetChip
          key={item.localId}
          item={item}
          onRemove={() => onRemove(item)}
          onRetry={() => onRetry(item)}
        />
      ))}
    </div>
  )
}

function AssetChip({
  item,
  onRemove,
  onRetry,
}: {
  item: StagingUpload
  onRemove: () => void
  onRetry: () => void
}) {
  const { t } = useTranslation()
  const { file } = item
  const meta = useStagedFileMeta(file)
  const Icon = fileIconFor(file)
  const isAv = file.type.startsWith("video/") || file.type.startsWith("audio/")
  const metaLabel = isAv
    ? meta.duration !== undefined
      ? formatChipDuration(meta.duration)
      : null
    : fileFormatLabel(file)

  return (
    <span className="inline-flex h-8 max-w-60 items-center gap-1.5 rounded-md bg-muted py-0 pr-1.5 pl-1 text-xs text-foreground">
      {meta.thumbUrl ? (
        <img
          src={meta.thumbUrl}
          alt=""
          className="h-6 w-6 flex-none rounded-[5px] object-cover"
        />
      ) : (
        <span className="flex h-6 w-6 flex-none items-center justify-center rounded-[5px] bg-icon-chip">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        </span>
      )}
      <span className="truncate">{file.name}</span>
      {item.status === "uploading" ? (
        <span className="flex flex-none items-center gap-1 text-[10px] text-meta-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          {Math.round(item.progress * 100)}%
        </span>
      ) : item.status === "error" ? (
        <button
          type="button"
          onClick={onRetry}
          className="flex-none text-[10px] text-destructive hover:underline"
        >
          {t("composer.uploadRetry")}
        </button>
      ) : metaLabel ? (
        <span className="flex-none text-[10px] text-meta-foreground">{metaLabel}</span>
      ) : null}
      <button
        type="button"
        onClick={onRemove}
        className="flex-none rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        aria-label={`Remove ${file.name}`}
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  )
}
