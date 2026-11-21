import { useId, useEffect, useState } from "react"
import { SlidersHorizontal } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Button } from "@/components/ui/button-clean"
import { Popover } from "@/components/ui/popover-clean"
import { Select } from "@/components/ui/select-clean"
import { apiFetch } from "@/lib/api"
import { CompositionPreview, type VideoPreviewRead } from "./preview/CompositionPreview"

export interface VideoClipFact {
  clip_id: string
  track_id: string
  object_id: string
  object_kind: string
  text?: string
  style?: { font_size: number }
  clip: {
    clip_id: string
    object: {
      kind: string
      object_id: string
      style?: { font_size: number }
      [key: string]: unknown
    }
    [key: string]: unknown
  }
}

export interface ScrubVersionRead {
  composition_version_id: string
  is_current?: boolean
  current_version_id?: string
  base_ref: {
    composition_id: string
    composition_version_id: string
    content_digest: string
  }
  storyboard: {
    scenes: Array<{ number: number; clips: VideoClipFact[] }>
    unassigned_clips: VideoClipFact[]
  }
}

export function TextSizeScrubInput({
  read,
  onDraftChange,
  onApplied,
}: {
  read: ScrubVersionRead
  onDraftChange: (draft: { clipId: string; fontSize: number } | null) => void
  onApplied: (versionId: string) => void
}) {
  const { t } = useTranslation()
  const sliderId = useId()
  const targets = read.storyboard.scenes.flatMap((scene) => scene.clips)
    .concat(read.storyboard.unassigned_clips)
    .filter((clip) =>
      clip.object_kind === "text" &&
      clip.clip.object.kind === "text" &&
      clip.style?.font_size !== undefined,
    )
  const [open, setOpen] = useState(false)
  const [clipId, setClipId] = useState("")
  const [fontSize, setFontSize] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [preview, setPreview] = useState<VideoPreviewRead | null>(null)
  const [conflicted, setConflicted] = useState(false)
  const selected = targets.find((clip) => clip.clip_id === clipId) ?? targets[0]
  const savedSize = selected?.style?.font_size ?? 1
  const value = fontSize ?? savedSize
  const dirty = fontSize !== null && fontSize !== savedSize

  useEffect(() => {
    setOpen(false)
    setClipId("")
    setFontSize(null)
    setConflicted(false)
    setPreview(null)
    onDraftChange(null)
  }, [read.composition_version_id, onDraftChange])

  useEffect(() => {
    if (!open || !selected) {
      setPreview(null)
      return
    }
    let cancelled = false
    setPreview(null)
    const target = { kind: "object", object_id: selected.object_id }
    const query = encodeURIComponent(JSON.stringify(target))
    apiFetch(
      `/api/v1/chat/video/versions/${read.composition_version_id}/storyboard?scrub=${query}`,
      { toast: false },
    ).then(async (response) => {
      const data = await response.json() as ScrubVersionRead & {
        content_digest?: string
        video_preview?: VideoPreviewRead
      }
      if (!response.ok || data.content_digest !== read.base_ref.content_digest) {
        throw new Error("Scrub preview unavailable")
      }
      if (!cancelled) setPreview(data.video_preview ?? { status: "unavailable" })
    }).catch(() => {
      if (!cancelled) setPreview({ status: "unavailable" })
    })
    return () => {
      cancelled = true
    }
  }, [open, read.base_ref.content_digest, read.composition_version_id, selected])

  if (read.is_current !== true || conflicted || targets.length === 0) return null

  const cancel = () => {
    setFontSize(null)
    onDraftChange(null)
  }
  const change = (next: number) => {
    if (!selected) return
    const normalized = Math.max(1, Math.min(400, Math.round(next)))
    setFontSize(normalized)
    onDraftChange({ clipId: selected.clip_id, fontSize: normalized })
  }
  const apply = async () => {
    if (!selected || !dirty || saving) return
    setSaving(true)
    const clip = {
      ...selected.clip,
      object: {
        ...selected.clip.object,
        style: { ...selected.clip.object.style, font_size: value },
      },
    }
    try {
      const response = await apiFetch(
        `/api/v1/chat/video/versions/${read.composition_version_id}/clips/${selected.clip_id}`,
        {
          method: "PUT",
          body: {
            base_ref: read.base_ref,
            track_id: selected.track_id,
            clip,
            request_id: crypto.randomUUID(),
          },
          toast: false,
        },
      )
      if (response.ok) {
        const result = await response.json() as { composition_version_id: string }
        cancel()
        setOpen(false)
        onApplied(result.composition_version_id)
      } else {
        cancel()
        toast.error(t(response.status === 409
          ? "chat.videoStoryboard.scrub.conflict"
          : "chat.videoStoryboard.scrub.applyError"))
        if (response.status === 409) {
          setConflicted(true)
          setOpen(false)
        }
      }
    } catch {
      cancel()
      toast.error(t("chat.videoStoryboard.scrub.applyError"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-2 w-fit">
      <Button
        variant="secondary"
        size="sm"
        icon={<SlidersHorizontal />}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          if (open) cancel()
          setOpen(!open)
        }}
      >
        {t("chat.videoStoryboard.scrub.trigger")}
      </Button>
      <Popover
        open={open}
        onClose={() => {
          cancel()
          setOpen(false)
        }}
        align="start"
        width="20rem"
        aria-label={t("chat.videoStoryboard.scrub.trigger")}
      >
        <div className="grid gap-3">
          <Select
            label={t("chat.videoStoryboard.scrub.target")}
            options={targets.map((clip) => ({ value: clip.clip_id, label: (clip.text ?? "").slice(0, 40) }))}
            value={selected?.clip_id}
            onChange={(next) => {
              cancel()
              setClipId(next)
            }}
          />
          {preview && selected && (
            <div>
              <CompositionPreview
                preview={preview}
                identity={read.base_ref}
                textSizeDraft={dirty ? { clipId: selected.clip_id, fontSize: value } : null}
                onReady={() => {}}
                onError={() => {}}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                {t("chat.videoStoryboard.scrub.isolatedObject")}
              </p>
            </div>
          )}
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <label htmlFor={sliderId}>{t("chat.videoStoryboard.scrub.fontSize")}</label>
              <span className="text-xs text-muted-foreground">{value}px</span>
            </div>
            <input
              type="range"
              id={sliderId}
              className="w-full accent-primary"
              aria-label={t("chat.videoStoryboard.scrub.fontSize")}
              min={1}
              max={400}
              step={1}
              value={value}
              onChange={(event) => change(event.currentTarget.valueAsNumber)}
              disabled={saving}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                cancel()
                setOpen(false)
              }}
              disabled={saving}
            >
              {t("common.cancel")}
            </Button>
            <Button size="sm" onClick={() => void apply()} disabled={!dirty || saving}>
              {t("chat.videoStoryboard.scrub.apply")}
            </Button>
          </div>
        </div>
      </Popover>
    </div>
  )
}
