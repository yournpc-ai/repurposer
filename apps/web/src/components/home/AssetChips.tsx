"use client"

import { X } from "lucide-react"

import {
  fileFormatLabel,
  fileIconFor,
  formatChipDuration,
  useStagedFileMeta,
} from "@/lib/stagedFiles"

/** Staged asset chips — the composer's TOP band (the "what I have" list
 * reads above the "what I want" text). Typed anatomy: video = thumbnail
 * sliver + duration, audio = waveform-family icon + duration, image =
 * thumbnail, doc/slides = icon tile + format label; × removes the file.
 * The pill below carries the summary (count); these chips carry the list. */
export function AssetChips({
  files,
  onRemove,
}: {
  files: File[]
  onRemove: (index: number) => void
}) {
  if (files.length === 0) return null
  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {files.map((file, index) => (
        <AssetChip key={`${file.name}:${file.size}`} file={file} onRemove={() => onRemove(index)} />
      ))}
    </div>
  )
}

function AssetChip({ file, onRemove }: { file: File; onRemove: () => void }) {
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
      {metaLabel ? <span className="flex-none text-[10px] text-meta-foreground">{metaLabel}</span> : null}
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
